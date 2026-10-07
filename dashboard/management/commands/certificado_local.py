"""
Gera os certificados para rodar o Polaris em HTTPS na rede local (necessário para o GPS do celular).

Cria em ssl_local/:
  - polaris-ca.crt / polaris-ca.key   autoridade certificadora própria (instale o .crt nos celulares)
  - polaris.crt / polaris.key         certificado do servidor, válido para os IPs informados

Uso:  python manage.py certificado_local 192.168.1.57
Depois: python manage.py runserver_https

Isto é para a rede da oficina. Em produção use um domínio com certificado público (ex.: Let's Encrypt).
"""
import datetime
import ipaddress
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.conf import settings
from django.core.management.base import BaseCommand


def _chave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _salvar(caminho, chave=None, cert=None):
    if chave is not None:
        caminho.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                                serialization.NoEncryption()))
    if cert is not None:
        caminho.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


class Command(BaseCommand):
    help = 'Gera certificado HTTPS para a rede local (o celular só libera o GPS em HTTPS).'

    def add_arguments(self, parser):
        parser.add_argument('ips', nargs='*', help='IPs do computador na rede (padrão: detecta automaticamente)')

    def handle(self, *args, **opts):
        pasta = settings.BASE_DIR / 'ssl_local'
        pasta.mkdir(exist_ok=True)
        agora = datetime.datetime.now(datetime.timezone.utc)

        ips = set(opts['ips'] or [])
        if not ips:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 80))
                ips.add(s.getsockname()[0])
                s.close()
            except OSError:
                pass
        ips.add('127.0.0.1')

        # Autoridade certificadora: reaproveitada se já existir, para não precisar reinstalar nos celulares.
        ca_key_path, ca_crt_path = pasta / 'polaris-ca.key', pasta / 'polaris-ca.crt'
        if ca_key_path.exists() and ca_crt_path.exists():
            ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
            ca_cert = x509.load_pem_x509_certificate(ca_crt_path.read_bytes())
            self.stdout.write('Autoridade certificadora existente reaproveitada.')
        else:
            ca_key = _chave()
            nome_ca = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Texas Controls Brasil'),
                                 x509.NameAttribute(NameOID.COMMON_NAME, 'Polaris - rede local')])
            ca_cert = (x509.CertificateBuilder().subject_name(nome_ca).issuer_name(nome_ca)
                       .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(agora - datetime.timedelta(days=1)).not_valid_after(agora + datetime.timedelta(days=3650))
                       .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                       .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                                    key_encipherment=False, data_encipherment=False, key_agreement=False,
                                                    encipher_only=False, decipher_only=False), critical=True)
                       .sign(ca_key, hashes.SHA256()))
            _salvar(ca_key_path, chave=ca_key)
            _salvar(ca_crt_path, cert=ca_cert)
            self.stdout.write('Autoridade certificadora criada.')

        key = _chave()
        san = [x509.DNSName('localhost')] + [x509.IPAddress(ipaddress.ip_address(ip)) for ip in sorted(ips)]
        cert = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, sorted(ips)[0])]))
                .issuer_name(ca_cert.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(agora - datetime.timedelta(days=1)).not_valid_after(agora + datetime.timedelta(days=825))
                .add_extension(x509.SubjectAlternativeName(san), critical=False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .sign(ca_key, hashes.SHA256()))
        _salvar(pasta / 'polaris.key', chave=key)
        _salvar(pasta / 'polaris.crt', cert=cert)
        self.stdout.write(self.style.SUCCESS(f'Certificado do servidor gerado para: {", ".join(sorted(ips))} e localhost'))
        self.stdout.write('Rode: python manage.py runserver_https  (https://<ip>:8443)')
