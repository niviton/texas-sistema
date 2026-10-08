import base64
import io
import shutil
import tempfile
from datetime import date, timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest import mock
from PIL import Image

from accounts.models import User

from .models import CHECKLIST_LABELS, FOTO_POSICOES, PNEU_KEYS, Inspecao, Manutencao, Motorista, Supervisor, Uso, Veiculo

TMP_MEDIA = tempfile.mkdtemp()


def _jpeg(name='foto.jpg', size=(40, 30)):
    buf = io.BytesIO()
    Image.new('RGB', size, 'red').save(buf, 'JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


def _assinatura():
    buf = io.BytesIO()
    img = Image.new('RGBA', (300, 120), (0, 0, 0, 0))
    for x in range(20, 280):
        img.putpixel((x, 60 + (x % 20) - 10), (13, 27, 46, 255))
    img.save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


@override_settings(MEDIA_ROOT=TMP_MEDIA, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', VEICULOS_EMAIL_ASYNC=False)
class FluxoInspecaoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = User.objects.create_superuser(email='admin@x.com', password='x', full_name='Admin Teste')
        self.vist = User.objects.create_user(
            email='vist@x.com', password='x', full_name='Vist Oriador', is_approved=True, role=User.ROLE_TECNICO,
        )
        self.prof = User.objects.create_user(email='prof@x.com', password='x', full_name='Prof', is_approved=True)
        self.mot = Motorista.objects.create(name='João Motorista', email='joao@x.com', usuario=self.vist)
        self.v = Veiculo.objects.create(placa='abc 1d23', marca='Fiat', modelo='Strada', km_atual=1000, motorista_responsavel=self.mot)
        Supervisor.objects.create(name='Sup Um', email='sup1@x.com')
        Supervisor.objects.create(name='Sup Inativo', email='sup2@x.com', is_active=False)

    def _post(self, tipo, km, sem_fotos=False, sem_assinatura=False, sem_pct=False, **extra):
        data = {'veiculo': self.v.pk, 'motorista': self.mot.pk, 'tipo': tipo, 'km': km, 'combustivel_pct': 75, 'destino': 'Cliente X'}
        if not sem_pct:
            data.update({f'pct_{k}': 80 - n * 10 for n, k in enumerate(PNEU_KEYS)})
        if not sem_fotos:
            data.update({f'foto_{k}': _jpeg(f'{k}.jpg') for k, _, _ in FOTO_POSICOES})
        if not sem_assinatura:
            data['assinatura'] = _assinatura()
        data.update(extra)
        return self.client.post(reverse('veiculos:inspecao_nova'), data)

    def test_placa_normalizada(self):
        self.assertEqual(self.v.placa, 'ABC1D23')

    def test_saida_com_problema_e_foto_envia_email_e_abre_uso(self):
        self.client.force_login(self.vist)
        r = self._post('saida', 1050, item_pneus='nok', obs_pneus='Pneu dianteiro careca', fotos_extra=[_jpeg('avaria.jpg', (3000, 2000))])
        insp = Inspecao.objects.get()
        self.assertRedirects(r, reverse('veiculos:inspecao_detalhe', args=[insp.pk]))
        self.assertTrue(insp.tem_problema)
        self.assertEqual(insp.itens.count(), len(CHECKLIST_LABELS))
        self.assertEqual(insp.fotos.count(), len(FOTO_POSICOES) + 1)
        self.assertEqual(insp.fotos.filter(posicao='painel').count(), 1)
        extra = insp.fotos.get(posicao='')
        self.assertEqual(max(extra.imagem.width, extra.imagem.height), 1920, 'foto grande deve ser reduzida')
        self.assertTrue(insp.assinatura)
        self.assertEqual(insp.combustivel_pct, 75)
        self.assertEqual(insp.combustivel_label, '75%')
        self.assertEqual([p for _, _, p in insp.pneus], [80, 70, 60, 50])
        self.assertTrue(insp.fotos.filter(posicao='cnh').exists())
        self.assertTrue(insp.fotos.filter(posicao='documento').exists())
        self.assertTrue(insp.email_enviado)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, ['sup1@x.com'])
        self.assertEqual(m.subject, 'Comprovante de vistoria do veículo placa: ABC1D23 e condutor João Motorista')
        corpo = m.alternatives[0][0]
        self.assertIn('PDF segue em anexo', corpo)
        self.assertNotIn('Checklist', corpo)
        self.assertEqual(len(m.attachments), 1)
        nome, conteudo, tipo = m.attachments[0]
        self.assertEqual(tipo, 'application/pdf')
        self.assertTrue(nome.startswith('Comprovante_vistoria_ABC1D23_'))
        self.assertTrue(conteudo.startswith(b'%PDF'))
        r = self.client.get(reverse('veiculos:inspecao_pdf', args=[insp.pk]))
        self.assertEqual(r['Content-Type'], 'application/pdf')
        uso = Uso.objects.get()
        self.assertIsNone(uso.chegada_em)
        self.v.refresh_from_db()
        self.assertEqual(self.v.km_atual, 1050)

        # Não pode sair de novo sem chegar
        r = self._post('saida', 1060)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Inspecao.objects.count(), 1)

        # Chegada com km menor que a saída é recusada
        r = self._post('chegada', 1040)
        self.assertEqual(r.status_code, 200)

        r = self._post('chegada', 1200)
        self.assertEqual(r.status_code, 302)
        uso.refresh_from_db()
        self.assertEqual(uso.km_rodados, 150)
        self.assertTrue(mail.outbox[-1].subject.startswith('Comprovante de vistoria do veículo placa: ABC1D23'))

    def test_fotos_e_assinatura_obrigatorias(self):
        self.client.force_login(self.vist)
        r = self._post('rotina', 1000, sem_fotos=True)
        self.assertContains(r, 'Faltam as fotos')
        r = self._post('rotina', 1000, sem_assinatura=True)
        self.assertContains(r, 'Falta a assinatura')
        r = self._post('rotina', 1000, sem_pct=True)
        self.assertContains(r, 'Informe o estado (0 a 100%)')
        r = self._post('rotina', 1000, combustivel_pct='')
        self.assertContains(r, 'Informe o nível de combustível')
        r = self._post('rotina', 1000, assinatura='data:image/png;base64,naoehpng')
        self.assertContains(r, 'Assinatura inválida')
        self.assertFalse(Inspecao.objects.exists())

    def test_manutencao_aparece_no_email_e_avanca(self):
        m = Manutencao.objects.create(veiculo=self.v, nome='Troca de óleo', proximo_km=1500, intervalo_km=10000, aviso_km=1000)
        self.client.force_login(self.vist)
        self._post('rotina', 1499)
        aviso = mail.outbox[-1]
        self.assertIn('Aviso de manutenção: veículo placa ABC1D23', aviso.subject)
        self.assertIn('Troca de óleo: faltam 1 km', aviso.alternatives[0][0])
        self.client.force_login(self.admin)
        r = self.client.post(reverse('veiculos:manutencoes', args=[self.v.pk]), {'acao': 'feita', 'id': m.pk})
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertEqual(m.proximo_km, 1499 + 10000)

    def test_aviso_imediato_quando_km_real_entra_na_faixa(self):
        # Troca de óleo a cada 5.000 km, aviso quando faltarem 500 km; próxima no km 10.500.
        Manutencao.objects.create(veiculo=self.v, nome='Troca de óleo', proximo_km=10500, intervalo_km=5000, aviso_km=500)
        self.client.force_login(self.vist)
        self._post('rotina', 9000)   # faltam 1.500 km: só o comprovante
        self.assertEqual([m.subject.split(':')[0] for m in mail.outbox], ['Comprovante de vistoria do veículo placa'])
        self._post('rotina', 10000)  # faltam 500 km: comprovante + aviso na hora
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn('Aviso de manutenção', mail.outbox[-1].subject)
        self.assertIn('faltam 500 km', mail.outbox[-1].alternatives[0][0])
        self._post('rotina', 10100)  # mesmo aviso não se repete
        self.assertEqual(len(mail.outbox), 4)
        call_command('veiculos_alertas', stdout=io.StringIO())  # nem no resumo diário
        self.assertFalse(any('vencimento' in m.subject for m in mail.outbox))

    def test_alerta_km_nao_repete_quando_km_muda(self):
        Manutencao.objects.create(veiculo=self.v, nome='Troca de óleo', proximo_km=1500, aviso_km=1000)
        call_command('veiculos_alertas', stdout=io.StringIO())
        n = sum('vencimento' in x.subject for x in mail.outbox)
        self.v.km_atual = 1200
        self.v.save()
        call_command('veiculos_alertas', stdout=io.StringIO())
        self.assertEqual(sum('vencimento' in x.subject for x in mail.outbox), n)

    def test_vistoriador_so_ve_o_proprio_historico(self):
        outro = User.objects.create_user(
            email='outro@x.com', password='x', full_name='Outro Vist', is_approved=True, role=User.ROLE_TECNICO,
        )
        self.client.force_login(outro)
        self._post('saida', 1000)
        dele = Inspecao.objects.get()
        self.assertEqual(dele.motorista.usuario, outro, 'o motorista é o próprio vistoriador')
        self.client.force_login(self.vist)
        self.assertNotContains(self.client.get(reverse('veiculos:inspecoes')), dele.veiculo.placa + '</b>')
        self.assertEqual(self.client.get(reverse('veiculos:inspecao_detalhe', args=[dele.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('veiculos:inspecao_pdf', args=[dele.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('veiculos:usos')), 'Outro Vist')
        # e não pode registrar a chegada de um carro que outra pessoa retirou
        r = self._post('chegada', 1100)
        self.assertContains(r, 'em uso por outro condutor')
        # o administrador vê tudo
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('veiculos:inspecao_detalhe', args=[dele.pk])).status_code, 200)

    def test_logistica_ve_todo_historico_sem_configuracoes(self):
        self.client.force_login(self.vist)
        self._post('saida', 1000)
        insp = Inspecao.objects.get()
        log = User.objects.create_user(email='log@x.com', password='x', full_name='Lara Logística', is_approved=True, role=User.ROLE_LOGISTICA)
        self.client.force_login(log)
        self.assertEqual(self.client.get(reverse('veiculos:inspecao_detalhe', args=[insp.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse('veiculos:usos')), 'João Motorista')
        self.assertContains(self.client.get(reverse('veiculos:inspecoes')), 'ABC1D23')
        home = self.client.get(reverse('dashboard:home'))
        self.assertContains(home, 'Últimos registros')
        self.assertContains(home, 'Registrar chegada')
        self.assertNotContains(home, 'Configurações')
        for name in ['veiculos', 'motoristas', 'supervisores', 'email']:
            self.assertEqual(self.client.get(reverse(f'veiculos:{name}')).status_code, 403, name)
        # Logística também faz vistoria em nome próprio
        self.assertNotContains(self.client.get(reverse('veiculos:inspecao_nova')), 'name="motorista"')

    def test_menu_checklists_agrupa_veiculos_e_pre_uso(self):
        self.client.force_login(self.vist)
        r = self.client.get(reverse('veiculos:inspecoes'))
        self.assertContains(r, 'class="nav-group" open')
        self.assertContains(r, 'nav-sublink ">Equipamentos')
        self.assertContains(r, 'nav-sublink active">Veículos')

    def test_configuracoes_reunem_os_cadastros(self):
        self.client.force_login(self.admin)
        for name in ['veiculos', 'motoristas', 'supervisores', 'email']:
            r = self.client.get(reverse(f'veiculos:{name}'))
            self.assertContains(r, '<h1', html=False)
            self.assertContains(r, 'Configurações')
            for area in ['Pessoas', 'Equipamentos', 'Formulários', 'Notificações']:
                self.assertContains(r, area)
        self.assertContains(self.client.get(reverse('accounts_admin:usuarios')), 'Motoristas (CNH)')
        self.assertContains(self.client.get(reverse('veiculos:email')), 'Quem recebe')

    def test_professor_nao_acessa_veiculos(self):
        self.client.force_login(self.prof)
        for name in ['painel', 'inspecao_nova', 'inspecoes', 'usos']:
            self.assertEqual(self.client.get(reverse(f'veiculos:{name}')).status_code, 403, name)
        home = self.client.get(reverse('dashboard:home'))
        self.assertNotContains(home, 'Veículos')

    def test_caminhonete_exige_carga(self):
        self.v.categoria = 'caminhonete'
        self.v.save()
        self.client.force_login(self.vist)
        r = self._post('saida', 1000)
        self.assertContains(r, 'Informe se a caminhonete leva carga')
        r = self._post('saida', 1000, com_carga='sim')
        self.assertEqual(r.status_code, 302)
        insp = Inspecao.objects.get()
        self.assertIs(insp.com_carga, True)
        self.assertIn('Comprovante de vistoria', mail.outbox[-1].subject)

    def test_carro_de_passeio_sem_pergunta_de_carga(self):
        self.client.force_login(self.vist)
        self._post('rotina', 1000)
        self.assertIsNone(Inspecao.objects.get().com_carga)

    def test_emails_vao_em_segundo_plano(self):
        self.client.force_login(self.vist)
        with override_settings(VEICULOS_EMAIL_ASYNC=True), mock.patch('veiculos.emails.threading.Thread') as Thread:
            r = self._post('rotina', 1000)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(mail.outbox), 0, 'a resposta não pode esperar o envio do e-mail')
        Thread.assert_called_once()
        Thread.return_value.start.assert_called_once()
        # Executa o que a thread executaria: o comprovante sai normalmente.
        alvo, args = Thread.call_args.kwargs['target'], Thread.call_args.kwargs['args']
        alvo(*args)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Inspecao.objects.get().email_enviado)

    def test_nao_ok_exige_descricao(self):
        self.client.force_login(self.vist)
        r = self._post('rotina', 1000, item_freios='nok')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Descreva o problema')
        self.assertFalse(Inspecao.objects.exists())

    def test_chegada_sem_saida_recusada(self):
        self.client.force_login(self.vist)
        r = self._post('chegada', 1100)
        self.assertContains(r, 'não tem saída em aberto')

    def test_alertas_vencimento_e_lembrete_uma_vez_so(self):
        self.v.seguro_validade = date.today() + timedelta(days=5)
        self.v.save()
        call_command('veiculos_alertas', stdout=io.StringIO())
        assuntos = [m.subject for m in mail.outbox]
        self.assertTrue(any('vencimento' in s for s in assuntos))
        lembrete = next(m for m in mail.outbox if 'Lembrete' in m.subject)
        self.assertEqual(lembrete.to, ['joao@x.com'])
        self.assertEqual(lembrete.cc, ['sup1@x.com'])

        total = len(mail.outbox)
        call_command('veiculos_alertas', stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), total, 'não deve repetir alertas já enviados')

    def test_paginas_carregam(self):
        self.client.force_login(self.admin)
        for name in ['painel', 'inspecao_nova', 'inspecoes', 'usos', 'veiculos', 'motoristas', 'supervisores', 'email']:
            self.assertEqual(self.client.get(reverse(f'veiculos:{name}')).status_code, 200, name)

    def test_cadastros_so_admin(self):
        self.client.force_login(self.vist)
        self.assertRedirects(self.client.get(reverse('veiculos:painel')), reverse('veiculos:inspecoes'))
        home = self.client.get(reverse('dashboard:home'))
        self.assertContains(home, 'Vistoria de veículo')
        self.assertContains(home, 'Checklist de equipamento')
        self.assertNotContains(home, 'Certificados')
        self.assertNotContains(home, 'Configurações')
        form = self.client.get(reverse('veiculos:inspecao_nova'))
        self.assertNotContains(form, 'name="motorista"')
        self.assertEqual(self.client.get(reverse('accounts_admin:usuarios')).status_code, 403)
        for name in ['veiculos', 'motoristas', 'supervisores', 'email']:
            self.assertEqual(self.client.get(reverse(f'veiculos:{name}')).status_code, 403, name)

    def test_cadastrar_veiculo(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('veiculos:veiculos'), {
            'placa': 'xyz9a87', 'categoria': 'caminhonete', 'marca': 'VW', 'modelo': 'Saveiro', 'km_atual': 0, 'checklist_frequencia_dias': 7,
        })
        self.assertRedirects(r, reverse('veiculos:veiculos'))
        self.assertTrue(Veiculo.objects.filter(placa='XYZ9A87').exists())


class CarimboTests(TestCase):
    """Carimbo de comprovação nas fotos (logo, data e hora do servidor, local)."""

    def test_carimbo_altera_a_foto_e_usa_coordenadas_sem_rede(self):
        from django.test import RequestFactory
        from django.utils import timezone

        from .carimbo import Carimbo, aplicar, carimbo_da_requisicao, data_extenso
        req = RequestFactory().post('/', {'geo_lat': '-5.9172', 'geo_lon': '-35.2633'})
        with override_settings(CARIMBO_ENDERECO=False):
            c = carimbo_da_requisicao(req)
        self.assertEqual(c.local, ['Lat -5.91720, Lon -35.26330'])
        self.assertTrue((timezone.now() - c.quando).total_seconds() < 5, 'hora vem do servidor')
        self.assertRegex(data_extenso(c.quando), r'^\d{1,2} de [a-z]{3}\. de \d{4} \d{2}:\d{2}:\d{2}$')
        original = Image.new('RGB', (800, 600), (40, 40, 40))
        carimbada = aplicar(original, c, 'foto.jpg')
        self.assertNotEqual(list(original.getdata()), list(carimbada.getdata()))

    def test_sem_gps_e_foto_antiga_da_galeria(self):
        import time

        from django.test import RequestFactory

        from .carimbo import _origem_do_arquivo, carimbo_da_requisicao
        c = carimbo_da_requisicao(RequestFactory().post('/', {}))
        self.assertEqual(c.local, [])
        ts = int((time.time() - 2 * 86400) * 1000)
        origem = _origem_do_arquivo(f'IMG_123_t{ts}.jpg')
        self.assertTrue((c.quando - origem).days >= 1)
        self.assertIsNone(_origem_do_arquivo('sem_data.jpg'))


class DestinatariosTests(TestCase):
    def test_cada_destinatario_recebe_so_o_que_escolheu(self):
        from checklists.models import TipoAtivo
        prensa = TipoAtivo.objects.create(nome='Prensa')
        talha = TipoAtivo.objects.create(nome='Talha')
        Supervisor.objects.create(name='Todos', email='todos@ex.com')
        so_frota = Supervisor.objects.create(name='Frota', email='frota@ex.com', recebe_checklists=False, recebe_termos=False)
        so_prensa = Supervisor.objects.create(name='Prensa', email='prensa@ex.com', recebe_veiculos=False, recebe_termos=False)
        so_prensa.tipos_ativo.add(prensa)
        Supervisor.objects.create(name='Arquivado', email='arq@ex.com', is_active=False)

        self.assertCountEqual(Supervisor.emails('veiculos'), ['todos@ex.com', so_frota.email])
        self.assertCountEqual(Supervisor.emails('termos'), ['todos@ex.com'])
        self.assertCountEqual(Supervisor.emails('checklists', prensa), ['todos@ex.com', so_prensa.email])
        self.assertCountEqual(Supervisor.emails('checklists', talha), ['todos@ex.com'])


class PassosVistoriaTests(TestCase):
    def setUp(self):
        from accounts.models import User
        self.tec = User.objects.create_user(email='t@x.com', password='x', full_name='Tec Um', is_approved=True, role=User.ROLE_TECNICO)
        self.livre = Veiculo.objects.create(placa='AAA1A11', marca='Fiat', modelo='Strada')
        self.ocupado = Veiculo.objects.create(placa='BBB2B22', marca='Toyota', modelo='Hilux')
        from django.utils import timezone
        outro = Motorista.objects.create(name='Outra Pessoa')
        Uso.objects.create(veiculo=self.ocupado, motorista=outro, saida_em=timezone.now(), km_saida=10)
        self.client.force_login(self.tec)

    def test_tipo_depois_veiculo_depois_formulario(self):
        url = reverse('veiculos:inspecao_nova')
        r = self.client.get(url)
        self.assertContains(r, 'Qual vistoria você vai fazer?')
        self.assertContains(r, '?tipo=saida')
        r = self.client.get(url, {'tipo': 'saida'})
        self.assertContains(r, 'AAA1A11')
        self.assertContains(r, 'esc-op off')  # o veículo em uso aparece bloqueado
        r = self.client.get(url, {'tipo': 'chegada'})
        self.assertNotContains(r, 'BBB2B22')  # em uso por outra pessoa
        r = self.client.get(url, {'tipo': 'saida', 'veiculo': self.livre.pk})
        self.assertContains(r, 'id="insp-form"')
        self.assertContains(r, 'class="passos"')
