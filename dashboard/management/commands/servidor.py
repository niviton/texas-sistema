"""
Roda o Polaris como servidor neste computador (rede da oficina), em modo produção.

    python servidor.py              # recomendado: liga o modo produção e grava o log em logs/
    python manage.py servidor       # o mesmo, se DJANGO_DEBUG=False já estiver definido

- HTTPS na porta 8443 (o celular libera o GPS), com o certificado de ssl_local/.
- A porta 8000 só redireciona para o HTTPS, para quem digitar o endereço sem "https".
- Endereço: se a rede já dá um nome a este computador (ex.: e12780.localdomain, pelo DHCP/DNS da
  empresa), o sistema usa esse nome. Diferente do IP, o nome continua certo quando o IP muda — não
  precisa reimprimir os QR codes nem reinstalar o certificado no celular.
- Se o endereço mudou (nome novo ou IP novo), gera de novo o certificado do servidor (a autoridade
  é a mesma, os celulares não precisam reinstalar).
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


def _sufixos_dns_windows():
    """Domínio(s) que a rede (DHCP) deu a este computador, ex.: 'localdomain'. Lido direto do
    registro do Windows, então funciona em qualquer idioma (ipconfig muda de texto por idioma)."""
    import winreg
    sufixos = set()
    base = r'SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            try:
                v, _ = winreg.QueryValueEx(k, 'Domain')
                if v:
                    sufixos.add(v)
            except FileNotFoundError:
                pass
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base + r'\Interfaces') as ifaces:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(ifaces, i)
                except OSError:
                    break
                i += 1
                with winreg.OpenKey(ifaces, sub) as ik:
                    for nome in ('DhcpDomain', 'Domain'):
                        try:
                            v, _ = winreg.QueryValueEx(ik, nome)
                            if v:
                                sufixos.add(v)
                        except FileNotFoundError:
                            pass
    except OSError:
        pass
    return sufixos


def nome_na_rede():
    """Nome deste computador na rede da empresa (ex.: e12780.localdomain), se o DHCP der um domínio.
    Sobrevive à troca de IP; None se não for possível descobrir (ex.: fora do Windows)."""
    try:
        sufixos = _sufixos_dns_windows()
    except ImportError:
        return None  # não é Windows
    if not sufixos:
        return None
    return f'{socket.gethostname().lower()}.{sorted(sufixos)[0].lower()}'


def _certificado_cobre(caminho, hosts):
    """hosts: lista de IPs e/ou nomes que o certificado precisa cobrir."""
    from cryptography import x509
    try:
        cert = x509.load_pem_x509_certificate(caminho.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        ips_no_cert = set(san.get_values_for_type(x509.IPAddress))
        nomes_no_cert = {n.lower() for n in san.get_values_for_type(x509.DNSName)}
        for h in hosts:
            try:
                if ipaddress.ip_address(h) not in ips_no_cert:
                    return False
            except ValueError:
                if h.lower() not in nomes_no_cert:
                    return False
        return True
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
        nome = nome_na_rede()
        pasta = settings.BASE_DIR / 'ssl_local'
        crt, key = pasta / 'polaris.crt', pasta / 'polaris.key'
        hosts_do_certificado = [ip, nome] if nome else [ip]
        if not (crt.exists() and key.exists()) or not _certificado_cobre(crt, hosts_do_certificado):
            self.stdout.write(f'Gerando certificado para {" e ".join(hosts_do_certificado)}...')
            call_command('certificado_local', *hosts_do_certificado)

        # Endereço principal: o nome dado pela rede, se existir (sobrevive à troca de IP);
        # senão o IP, como antes. Usado nos links dos e-mails e nos QR codes impressos daqui.
        preferido = nome or ip
        endereco = f'https://{preferido}:{porta}'
        if settings.SITE_URL != endereco:
            self.stdout.write(self.style.WARNING(f'SITE_URL era {settings.SITE_URL}; usando {endereco} (atualize o .env).'))
            settings.SITE_URL = endereco
        hosts_aceitos = [ip, 'localhost', '127.0.0.1', socket.gethostname()]
        if nome:
            hosts_aceitos.append(nome)
        for host in hosts_aceitos:
            if '*' not in settings.ALLOWED_HOSTS and host not in settings.ALLOWED_HOSTS:
                settings.ALLOWED_HOSTS.append(host)
        if nome:
            self.stdout.write(f'Nome na rede: {nome}  (continua certo mesmo se o IP {ip} mudar)')

        app = StaticFilesHandler(get_wsgi_application())
        servidor = wsgi.Server(('0.0.0.0', porta), app, numthreads=opts['threads'], server_name='Polaris')
        servidor.ssl_adapter = BuiltinSSLAdapter(str(crt), str(key))
        redireciona = None
        if porta_http:
            redireciona = wsgi.Server(('0.0.0.0', porta_http), _app_redireciona(porta), numthreads=4, server_name='Polaris')
            threading.Thread(target=redireciona.safe_start, daemon=True).start()

        extra = f'  (ou pelo IP: https://{ip}:{porta})' if nome else ''
        self.stdout.write(self.style.SUCCESS(f'Polaris no ar: {endereco}{extra}  (http://{preferido}:{porta_http} redireciona)'))
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
