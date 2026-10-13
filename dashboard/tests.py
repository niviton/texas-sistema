from django.test import TestCase

# Create your tests here.


class CertificadoCelularTests(TestCase):
    def test_pagina_publica_do_certificado(self):
        from django.urls import reverse
        r = self.client.get(reverse('certificado_celular'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Certificado do Polaris para o celular')


class RegistrosTests(TestCase):
    """Novo registro, histórico único e tela de concluído, iguais para todos os módulos."""

    def setUp(self):
        from datetime import date

        from accounts.models import User
        from checklists.models import Ativo, Execucao, Modelo, Revisao, TipoAtivo
        from termos.models import Termo
        from veiculos.models import Inspecao, Motorista, Veiculo

        self.admin = User.objects.create_superuser(email='a@x.com', password='x', full_name='Admin')
        self.log = User.objects.create_user(email='l@x.com', password='x', full_name='Lu Logística', is_approved=True, role=User.ROLE_LOGISTICA)
        self.tec = User.objects.create_user(email='t@x.com', password='x', full_name='Tito Técnico', is_approved=True, role=User.ROLE_TECNICO)
        outro = User.objects.create_user(email='o@x.com', password='x', full_name='Outro', is_approved=True, role=User.ROLE_TECNICO)
        v = Veiculo.objects.create(placa='ABC1D23', marca='Fiat', modelo='Strada')
        Inspecao.objects.create(veiculo=v, motorista=Motorista.objects.create(name='Tito', usuario=self.tec), tipo='rotina', km=10, created_by=self.tec)
        tipo = TipoAtivo.objects.create(nome='Gerador')
        ativo = Ativo.objects.create(tipo=tipo, nome='Gerador Toyama 1000 W')
        modelo = Modelo.objects.create(codigo='TCB-OTB-24', titulo='Manutenção – gerador', finalidade='manutencao')
        rev = Revisao.objects.create(modelo=modelo, numero=1)
        Execucao.objects.create(revisao=rev, ativo=ativo, executor=outro, executor_nome='Outro', tem_problema=True)
        Termo.objects.create(tipo='entrada', data=date.today(), cliente_contato='Cliente Eólica', created_by=self.log)

    def test_novo_registro_mostra_so_o_permitido(self):
        from django.urls import reverse
        self.client.force_login(self.log)
        r = self.client.get(reverse('dashboard:novo'))
        for txt in ['Veículo', 'Equipamento', 'Termo de material']:
            self.assertContains(r, txt)
        self.client.force_login(self.tec)
        r = self.client.get(reverse('dashboard:novo'))
        self.assertContains(r, 'Equipamento')
        self.assertNotContains(r, 'Termo de material')

    def test_historico_unico_respeita_quem_ve_o_que(self):
        from django.urls import reverse
        url = reverse('dashboard:historico')
        self.client.force_login(self.log)
        r = self.client.get(url)
        for txt in ['ABC1D23', 'Gerador Toyama 1000 W', 'Cliente Eólica']:
            self.assertContains(r, txt)
        self.assertContains(self.client.get(url, {'tipo': 'checklist'}), 'Gerador Toyama')
        self.assertNotContains(self.client.get(url, {'tipo': 'checklist'}), 'ABC1D23')
        self.assertNotContains(self.client.get(url, {'q': 'toyama'}), 'Cliente Eólica')
        self.assertContains(self.client.get(url, {'problema': '1'}), 'Gerador Toyama')
        self.assertNotContains(self.client.get(url, {'problema': '1'}), 'ABC1D23')
        # o técnico vê só os próprios registros e nenhum termo
        self.client.force_login(self.tec)
        r = self.client.get(url)
        self.assertContains(r, 'ABC1D23')
        self.assertNotContains(r, 'Gerador Toyama')
        self.assertNotContains(r, 'Cliente Eólica')
        self.assertEqual(self.client.get(reverse('dashboard:concluido', args=['termo', 1])).status_code, 404)

    def test_pendencias_e_conferencia_do_administrador(self):
        from django.urls import reverse

        from checklists.models import Ativo, Execucao
        Ativo.objects.filter(nome='Gerador Toyama 1000 W').update(conferido=False, cadastrado_por=self.tec)
        self.client.force_login(self.admin)
        home = self.client.get(reverse('dashboard:home'))
        self.assertContains(home, 'Para conferir')
        self.assertContains(home, 'class="nav-cont"')
        self.assertEqual(home.context['n_pendencias'], 2)  # equipamento novo + checklist com problema
        ex = Execucao.objects.get()
        r = self.client.post(reverse('dashboard:conferir', args=['checklist', ex.pk]), {'next': '/dashboard/'})
        self.assertRedirects(r, '/dashboard/', fetch_redirect_response=False)
        ex.refresh_from_db()
        self.assertEqual(ex.conferido_por, self.admin)
        a = Ativo.objects.get()
        self.client.post(reverse('dashboard:conferir', args=['equipamento', a.pk]), {'next': 'https://outro-site.com/'})
        self.assertNotContains(self.client.get(reverse('dashboard:home')), 'Para conferir')
        # só o administrador confere
        self.client.force_login(self.log)
        self.assertEqual(self.client.post(reverse('dashboard:conferir', args=['equipamento', a.pk])).status_code, 403)

    def test_qr_leva_direto_ao_checklist_e_a_vistoria(self):
        from django.urls import reverse

        from checklists.models import Ativo
        from veiculos.models import Veiculo
        a, v = Ativo.objects.get(), Veiculo.objects.get()
        self.client.force_login(self.tec)
        self.assertRedirects(self.client.get(reverse('dashboard:qr_equipamento', args=[a.pk])),
                             reverse('checklists:escolher_modelo', args=[a.pk]), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('dashboard:qr_veiculo', args=[v.pk])),
                             reverse('veiculos:inspecao_nova') + f'?veiculo={v.pk}', fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('dashboard:etiquetas')).status_code, 403)
        self.client.force_login(self.admin)
        r = self.client.get(reverse('dashboard:etiquetas'), {'equip': 'todos', 'veic': str(v.pk)})
        self.assertContains(r, '<svg', count=2)
        self.assertContains(r, 'Gerador Toyama 1000 W')
        self.assertContains(r, 'ABC1D23')
        # sem login, o QR pede o login e depois volta para o checklist
        self.client.logout()
        r = self.client.get(reverse('dashboard:qr_equipamento', args=[a.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn('next=', r['Location'])
