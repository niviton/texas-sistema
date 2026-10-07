import base64
import io
import shutil
import tempfile

import docx
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from veiculos.models import Supervisor

from .models import FINALIZADO, RASCUNHO, ModeloTermo, Termo
from .pdf import render_termo_pdf

TMP_MEDIA = tempfile.mkdtemp()


def _jpeg():
    buf = io.BytesIO()
    Image.new('RGB', (80, 60), 'teal').save(buf, 'JPEG')
    return SimpleUploadedFile('foto.jpg', buf.getvalue(), content_type='image/jpeg')


def _assinatura():
    buf = io.BytesIO()
    img = Image.new('RGBA', (200, 80), (0, 0, 0, 0))
    for x in range(10, 190):
        img.putpixel((x, 40), (13, 27, 46, 255))
    img.save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def _docx_termo(codigo, titulo):
    d = docx.Document()
    for t in ['Título', 'Title', titulo, 'Documento', 'Document', 'Revisão', 'Review', 'Página', 'Pages', codigo, '01',
              '1 de 1', 'Preparado por  prepared by', 'Revisado por Review by', 'Data Date', 'Ana Exemplo', 'Bruno Exemplo', '20/06/2024']:
        d.sections[0].header.add_paragraph(t)
    buf = io.BytesIO()
    d.save(buf)
    return SimpleUploadedFile(f'{codigo}.docx', buf.getvalue())


@override_settings(MEDIA_ROOT=TMP_MEDIA, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', VEICULOS_EMAIL_ASYNC=False)
class TermosTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = User.objects.create_superuser(email='admin@x.com', password='x', full_name='Admin Geral')
        self.log = User.objects.create_user(email='log@x.com', password='x', full_name='Lara Logística', is_approved=True, role=User.ROLE_LOGISTICA)
        self.tec = User.objects.create_user(email='tec@x.com', password='x', full_name='Tiago', is_approved=True, role=User.ROLE_TECNICO)
        Supervisor.objects.create(name='Sup', email='sup@x.com')

    def _dados(self, **extra):
        d = {
            'tipo': 'saida', 'numero_assunto': 'ASS: 202600001', 'motivo': 'Manutenção finalizada', 'data': '2026-10-07',
            'cliente_contato': 'Cliente Exemplo - Fulano', 'origem': 'Parque Exemplo', 'transporte': 'Texas',
            'item_descricao': ['Chave elétrica + maleta', ''], 'item_referencia': ['NS: 0001', ''],
            'item_quantidade': ['1', '1'], 'item_informacao': ['NF 123', ''],
            'observacoes': 'Sem avarias.', 'nome_cliente': 'Fulano de Tal', 'telefone_cliente': '(84) 99999-0000',
            'fotos': [_jpeg()], 'acao': 'rascunho',
        }
        d.update(extra)
        return d

    def test_rascunho_depois_finaliza_com_assinaturas(self):
        self.client.force_login(self.log)
        r = self.client.post(reverse('termos:novo'), self._dados())
        termo = Termo.objects.get()
        self.assertRedirects(r, reverse('termos:detalhe', args=[termo.pk]))
        self.assertEqual(termo.status, RASCUNHO)
        self.assertEqual(termo.itens.count(), 1, 'linhas vazias são ignoradas')
        self.assertEqual(termo.fotos.count(), 1)

        # Sem assinaturas não finaliza
        r = self.client.post(reverse('termos:editar', args=[termo.pk]), self._dados(acao='finalizar', fotos=[]))
        self.assertRedirects(r, reverse('termos:editar', args=[termo.pk]))
        termo.refresh_from_db()
        self.assertEqual(termo.status, RASCUNHO)
        self.assertEqual(termo.fotos.count(), 1, 'foto anterior continua')

        r = self.client.post(reverse('termos:editar', args=[termo.pk]), self._dados(
            acao='finalizar', fotos=[], assinatura_texas=_assinatura(), assinatura_cliente=_assinatura()))
        termo.refresh_from_db()
        self.assertEqual(termo.status, FINALIZADO)
        self.assertEqual(termo.responsavel_texas, 'Lara Logística')
        self.assertEqual(termo.documento.codigo, 'TCB-LO-02')
        m = mail.outbox[-1]
        self.assertIn('Termo de saída TCB-LO-02', m.subject)
        self.assertTrue(m.attachments[0][1].startswith(b'%PDF'))
        # Finalizado não edita mais
        r = self.client.get(reverse('termos:editar', args=[termo.pk]))
        self.assertRedirects(r, reverse('termos:detalhe', args=[termo.pk]))
        # Logística não exclui finalizado; admin pode
        self.client.post(reverse('termos:excluir', args=[termo.pk]))
        self.assertTrue(Termo.objects.exists())
        self.client.force_login(self.admin)
        self.client.post(reverse('termos:excluir', args=[termo.pk]))
        self.assertFalse(Termo.objects.exists())

    def test_campos_obrigatorios(self):
        self.client.force_login(self.log)
        r = self.client.post(reverse('termos:novo'), self._dados(cliente_contato='', data=''))
        self.assertContains(r, 'Informe o cliente e a pessoa de contato.')
        self.assertContains(r, 'Informe a data.')
        self.assertFalse(Termo.objects.exists())

    def test_pdf_de_entrada_e_saida(self):
        self.client.force_login(self.log)
        for tipo in ('entrada', 'saida'):
            self.client.post(reverse('termos:novo'), self._dados(tipo=tipo, fotos=[_jpeg(), _jpeg()]))
        for t in Termo.objects.all():
            self.assertTrue(render_termo_pdf(t).startswith(b'%PDF'))
            r = self.client.get(reverse('termos:pdf', args=[t.pk]))
            self.assertEqual(r['Content-Type'], 'application/pdf')

    def test_permissoes(self):
        self.client.force_login(self.tec)
        self.assertEqual(self.client.get(reverse('termos:lista')).status_code, 403)
        self.assertNotContains(self.client.get(reverse('dashboard:home')), 'Termo de entrada ou saída')
        self.client.force_login(self.log)
        self.assertEqual(self.client.get(reverse('termos:lista')).status_code, 200)
        self.assertContains(self.client.get(reverse('dashboard:home')), 'Termo de entrada ou saída')
        self.assertEqual(self.client.get(reverse('termos:documentos')).status_code, 403)

    def test_importa_cabecalho_do_word(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('termos:documentos'), {'acao': 'importar',
                                                            'arquivo': _docx_termo('TCB-LO-01', 'TERMO DE ENTRADA - MATERIAL CLIENTE')})
        self.assertRedirects(r, reverse('termos:documentos'))
        doc = ModeloTermo.objects.get(tipo='entrada')
        self.assertEqual((doc.codigo, doc.revisao, doc.preparado_por, doc.revisado_por), ('TCB-LO-01', '01', 'Ana Exemplo', 'Bruno Exemplo'))
        self.assertEqual(doc.data.isoformat(), '2024-06-20')
