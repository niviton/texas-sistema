"""
Comando pra testar a conexão com o Microsoft Graph / SharePoint sem precisar
mexer no fluxo de certificados.

Uso:
    python manage.py test_graph_connection
"""

from django.core.management.base import BaseCommand

from certificates.graph_client import GraphClient, GraphClientError


class Command(BaseCommand):
    help = 'Testa a conexão com o Microsoft Graph API e a resolução do site do SharePoint.'

    def handle(self, *args, **options):
        try:
            client = GraphClient()
        except GraphClientError as e:
            self.stderr.write(self.style.ERROR(f'Configuração incompleta: {e}'))
            return

        self.stdout.write('Obtendo token de acesso...')
        try:
            token = client._get_token()
            self.stdout.write(self.style.SUCCESS(f'Token obtido com sucesso ({token[:15]}...)'))
        except GraphClientError as e:
            self.stderr.write(self.style.ERROR(f'Falha ao obter token: {e}'))
            return

        self.stdout.write('Resolvendo Site ID do SharePoint...')
        try:
            site_id = client.get_site_id()
            self.stdout.write(self.style.SUCCESS(f'Site ID: {site_id}'))
        except GraphClientError as e:
            self.stderr.write(self.style.ERROR(
                f'Falha ao resolver o site: {e}\n'
                'Verifique se: (1) MS_SHAREPOINT_HOSTNAME e MS_SHAREPOINT_SITE_PATH '
                'estão corretos no .env, e (2) o admin já rodou o comando de vínculo '
                'do app ao site (permissão Sites.Selected concedida especificamente '
                'para este site).'
            ))
            return

        self.stdout.write(self.style.SUCCESS('Conexão com o Graph API e o site do SharePoint OK!'))
