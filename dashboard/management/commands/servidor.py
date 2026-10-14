"""
Roda o Polaris como servidor neste computador (rede da oficina), em modo produção.

    python servidor.py              # recomendado: liga o modo produção e grava o log em logs/
    python manage.py servidor       # o mesmo, se DJANGO_DEBUG=False já estiver definido

- HTTPS na porta 8443 (o celular libera o GPS), com o certificado de ssl_local/.
- A porta 8000 só redireciona para o HTTPS, para quem digitar o endereço sem "https".
- Se o IP do computador mudou, gera de novo o certificado do servidor (a autoridade é a mesma,
  os celulares não precisam reinstalar) e usa o IP novo nos links dos e-mails.
"""
import ipaddress
import socket
import threading

from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application


def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return '127.0.0.1'


def _certificado_cobre(caminho, ip):
    from cryptography import x509
    try:
        cert = x509.load_pem_x509_certificate(caminho.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        return ipaddress.ip_address(ip) in san.get_values_for_type(x509.IPAddress)
    except (OSError, ValueError, x509.ExtensionNotFound):
        return False


def _app_redireciona(porta_https):
    def app(environ, start_response):
        host = (environ.get('HTTP_HOST') or environ.get('SERVER_NAME', 'localhost')).split(':')[0]
        caminho = environ.get('PATH_INFO', '/') + (('?' + environ['QUERY_STRING']) if environ.get('QUERY_STRING') else '')
        start_response('301 Moved Permanently', [('Location', f'https://{host}:{porta_https}{caminho}'), ('Content-Length', '0')])
        return [b'']
    return app


class Command(BaseCommand):
    help = 'Roda o Polaris como servidor da oficina (HTTPS 8443, produção).'

    def add_arguments(self, parser):
        parser.add_argument('--porta', type=int, default=8443)
        parser.add_argument('--porta-http', type=int, default=8000, help='Só redireciona para o HTTPS. 0 desliga.')
        parser.add_argument('--threads', type=int, default=24)

    def handle(self, *args, **opts):
        from cheroot import wsgi
        from cheroot.ssl.builtin import BuiltinSSLAdapter

        if settings.DEBUG:
            self.stdout.write(self.style.WARNING('Atenção: DJANGO_DEBUG está ligado. Use "python servidor.py" para o modo produção.'))
        porta, porta_http = opts['porta'], opts['porta_http']
        ip = ip_local()
        pasta = settings.BASE_DIR / 'ssl_local'
        crt, key = pasta / 'polaris.crt', pasta / 'polaris.key'
        if not (crt.exists() and key.exists()) or not _certificado_cobre(crt, ip):
            self.stdout.write(f'Gerando certificado para o IP {ip}...')
            call_command('certificado_local', ip)

        # Endereço atual: links dos e-mails, QR codes impressos daqui e domínios aceitos.
        endereco = f'https://{ip}:{porta}'
        if settings.SITE_URL != endereco:
            self.stdout.write(self.style.WARNING(f'SITE_URL era {settings.SITE_URL}; usando {endereco} (atualize o .env).'))
            settings.SITE_URL = endereco
        for host in [ip, 'localhost', '127.0.0.1', socket.gethostname()]:
            if '*' not in settings.ALLOWED_HOSTS and host not in settings.ALLOWED_HOSTS:
                settings.ALLOWED_HOSTS.append(host)

        app = StaticFilesHandler(get_wsgi_application())
        servidor = wsgi.Server(('0.0.0.0', porta), app, numthreads=opts['threads'], server_name='Polaris')
        servidor.ssl_adapter = BuiltinSSLAdapter(str(crt), str(key))
        redireciona = None
        if porta_http:
            redireciona = wsgi.Server(('0.0.0.0', porta_http), _app_redireciona(porta), numthreads=4, server_name='Polaris')
            threading.Thread(target=redireciona.safe_start, daemon=True).start()

        self.stdout.write(self.style.SUCCESS(f'Polaris no ar: {endereco}  (http://{ip}:{porta_http} redireciona)'))
        try:
            servidor.start()
        except KeyboardInterrupt:
            pass
        except OSError as exc:
            raise CommandError(f'Não consegui abrir a porta {porta}: {exc}. Outro Polaris já está rodando?')
        finally:
            servidor.stop()
            if redireciona:
                redireciona.stop()
