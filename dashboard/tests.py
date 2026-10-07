from django.test import TestCase

# Create your tests here.


class CertificadoCelularTests(TestCase):
    def test_pagina_publica_do_certificado(self):
        from django.urls import reverse
        r = self.client.get(reverse('certificado_celular'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Certificado do Polaris para o celular')
