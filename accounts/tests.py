from django.test import TestCase

# Create your tests here.


class AparenciaTests(TestCase):
    def setUp(self):
        from .models import User
        self.user = User.objects.create_user(email='ap@x.com', password='x', full_name='Ana', is_approved=True, role=User.ROLE_TECNICO)
        self.client.force_login(self.user)

    def test_cada_pessoa_escolhe_tema_e_fonte(self):
        from django.urls import reverse
        r = self.client.get(reverse('dashboard:home'))
        self.assertContains(r, 'data-tema="claro" data-fonte="manrope"')
        self.assertContains(r, 'Aparência')
        r = self.client.post(reverse('accounts:aparencia'), {'tema': 'escuro', 'fonte': 'atkinson'})
        self.assertRedirects(r, reverse('accounts:aparencia'))
        self.user.refresh_from_db()
        self.assertEqual((self.user.tema, self.user.fonte), ('escuro', 'atkinson'))
        r = self.client.get(reverse('dashboard:home'))
        self.assertContains(r, 'data-tema="escuro" data-fonte="atkinson"')
        self.assertContains(r, 'family=Atkinson+Hyperlegible')
        self.assertContains(r, "'Atkinson Hyperlegible', system-ui, sans-serif !important")

    def test_valores_invalidos_sao_ignorados(self):
        from django.urls import reverse
        self.client.post(reverse('accounts:aparencia'), {'tema': 'roxo', 'fonte': 'comic'})
        self.user.refresh_from_db()
        self.assertEqual((self.user.tema, self.user.fonte), ('claro', 'manrope'))


import tempfile  # noqa: E402

from django.test import override_settings  # noqa: E402


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PapeisTests(TestCase):
    """O administrador cria papéis (ex.: Motorista) e escolhe o que cada um acessa."""

    def setUp(self):
        from .models import Papel, User
        self.admin = User.objects.create_superuser(email='adm@x.com', password='x', full_name='Admin')
        self.pessoa = User.objects.create_user(email='m@x.com', password='x', full_name='Mário Motorista', is_approved=True)
        self.Papel = Papel

    def test_admin_cria_papel_motorista_so_com_vistoria(self):
        from django.urls import reverse
        self.client.force_login(self.admin)
        r = self.client.post(reverse('accounts_admin:papeis'), {
            'nome': 'Motorista de entrega', 'descricao': 'Só vistoria', 'acesso_vistoria': 'on',
        })
        self.assertRedirects(r, reverse('accounts_admin:papeis'))
        motorista = self.Papel.objects.get(nome='Motorista de entrega')
        self.assertContains(self.client.get(reverse('accounts_admin:papeis')), 'Vistoria de veículos')
        # papel sem nenhum acesso não é aceito
        r = self.client.post(reverse('accounts_admin:papeis'), {'nome': 'Vazio'})
        self.assertContains(r, 'Marque pelo menos um acesso')
        # atribui o papel à pessoa
        r = self.client.post(reverse('accounts_admin:usuarios'), {
            'editing_id': self.pessoa.pk, 'full_name': self.pessoa.full_name, 'email': self.pessoa.email,
            'papel': motorista.pk, 'is_approved': 'on',
        })
        self.assertRedirects(r, reverse('accounts_admin:usuarios'))
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.papel, motorista)
        # a pessoa vê só a vistoria (depois de completar a CNH)
        from veiculos.tests import _completar_motorista
        _completar_motorista(self.pessoa)
        self.client.force_login(self.pessoa)
        self.assertEqual(self.client.get(reverse('veiculos:inspecao_nova')).status_code, 200)
        self.assertEqual(self.client.get(reverse('checklists:executar')).status_code, 403)
        self.assertEqual(self.client.get(reverse('termos:lista')).status_code, 403)
        self.assertEqual(self.client.get(reverse('accounts_admin:usuarios')).status_code, 403)
        home = self.client.get(reverse('dashboard:home'))
        self.assertContains(home, 'Vistoria de veículo')
        self.assertNotContains(home, 'Checklist de equipamento')
        # arquivar o papel tira o acesso
        motorista.is_active = False
        motorista.save()
        self.assertEqual(self.client.get(reverse('veiculos:inspecao_nova')).status_code, 403)

    def test_professor_ve_historico_e_certificados(self):
        from datetime import date

        from django.urls import reverse

        from certificates.models import CourseTemplate, Professor, StudentRegistration
        prof_papel = self.Papel.objects.get(nome='Professor')
        self.pessoa.papel = prof_papel
        self.pessoa.save()
        curso = CourseTemplate.objects.create(title='Torque hidráulico')
        prof = Professor.objects.create(full_name='Prof Teste')
        StudentRegistration.objects.create(student_name='Aluno Um', cpf='12345678901', course_template=curso, professor=prof,
                                           created_by=self.pessoa, subject_code='1234', course_date=date.today(), duration='8 HORAS')
        self.client.force_login(self.pessoa)
        home = self.client.get(reverse('dashboard:home'))
        self.assertContains(home, reverse('cert_prof:folders'))
        self.assertContains(home, reverse('dashboard:historico'))
        self.assertNotContains(home, 'Vistoria de veículo')
        r = self.client.get(reverse('dashboard:historico'))
        self.assertContains(r, 'ALUNO UM')
        self.assertContains(r, 'Torque hidráulico')
        self.assertEqual(self.client.get(reverse('cert_prof:folders')).status_code, 200)
        self.assertEqual(self.client.get(reverse('checklists:executar')).status_code, 403)
