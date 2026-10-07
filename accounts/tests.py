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
