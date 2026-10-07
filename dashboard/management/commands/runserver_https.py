"""
Servidor de desenvolvimento em HTTPS para a rede local (o celular só libera o GPS em HTTPS).

    python manage.py certificado_local          # uma vez (gera ssl_local/)
    python manage.py runserver_https            # https://<ip>:8443

Diferente do runserver_plus, não liga o depurador interativo do Werkzeug: numa rede com outros
aparelhos, ele permitiria executar comandos neste computador a partir de uma página de erro.
"""
from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application


class Command(BaseCommand):
    help = 'Roda o Polaris em HTTPS na rede local (padrão 0.0.0.0:8443), sem depurador interativo.'

    def add_arguments(self, parser):
        parser.add_argument('endereco', nargs='?', default='0.0.0.0:8443')
        parser.add_argument('--noreload', action='store_true', help='Não reinicia sozinho quando o código muda.')

    def handle(self, *args, **opts):
        from werkzeug.serving import run_simple

        pasta = settings.BASE_DIR / 'ssl_local'
        crt, key = pasta / 'polaris.crt', pasta / 'polaris.key'
        if not (crt.exists() and key.exists()):
            raise CommandError('Certificado não encontrado. Rode antes: python manage.py certificado_local')
        host, _, porta = opts['endereco'].rpartition(':')
        app = StaticFilesHandler(get_wsgi_application())
        self.stdout.write(self.style.SUCCESS(f'Polaris em https://{host or "0.0.0.0"}:{porta}/  (Ctrl+C para parar)'))
        run_simple(host or '0.0.0.0', int(porta), app, ssl_context=(str(crt), str(key)),
                   use_reloader=not opts['noreload'], use_debugger=False, threaded=True)
