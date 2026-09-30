"""
Cliente para o Microsoft Graph API, usado para enviar certificados ao
SharePoint (site O.T.BRASIL) via permissão Sites.Selected.

Credenciais vêm de settings.MS_GRAPH, que por sua vez lê do arquivo .env
(nunca commitado). Ver .env.example para as variáveis necessárias.

Uso típico:

    from certificates.graph_client import GraphClient

    client = GraphClient()
    site_id = client.get_site_id()  # descobre e cacheia o Site ID
    result = client.upload_file(local_path, filename, folder_path='Certificados')
    # result['webUrl'] -> link para salvar em Certificate.external_link
"""

import base64

import msal
import requests
from django.conf import settings

GRAPH_BASE_URL = 'https://graph.microsoft.com/v1.0'
GRAPH_SCOPE = ['https://graph.microsoft.com/.default']


class GraphClientError(Exception):
    """Erro genérico de comunicação com o Graph API."""


class GraphClient:
    def __init__(self):
        cfg = settings.MS_GRAPH
        self.tenant_id = cfg.get('TENANT_ID')
        self.client_id = cfg.get('CLIENT_ID')
        self.client_secret = cfg.get('CLIENT_SECRET')
        self.hostname = cfg.get('SHAREPOINT_HOSTNAME')
        self.site_path = cfg.get('SHAREPOINT_SITE_PATH')
        self._site_id = cfg.get('SHAREPOINT_SITE_ID') or None

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise GraphClientError(
                'Credenciais do Microsoft Graph ausentes. Preencha MS_TENANT_ID, '
                'MS_CLIENT_ID e MS_CLIENT_SECRET no arquivo .env.'
            )

        self._app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f'https://login.microsoftonline.com/{self.tenant_id}',
        )

    def _get_token(self):
        result = self._app.acquire_token_silent(GRAPH_SCOPE, account=None)
        if not result:
            result = self._app.acquire_token_for_client(scopes=GRAPH_SCOPE)
        if 'access_token' not in result:
            raise GraphClientError(
                f"Falha ao obter token: {result.get('error')} - {result.get('error_description')}"
            )
        return result['access_token']

    def _headers(self):
        return {'Authorization': f'Bearer {self._get_token()}'}

    def get_site_id(self):
        """
        Resolve e cacheia o Site ID a partir de hostname + site path
        (ex: texascontrols.sharepoint.com + /sites/OTBRASIL).
        Se MS_SHAREPOINT_SITE_ID já estiver definido no .env, usa ele direto.
        """
        if self._site_id:
            return self._site_id

        if not self.hostname or not self.site_path:
            raise GraphClientError(
                'MS_SHAREPOINT_HOSTNAME e MS_SHAREPOINT_SITE_PATH precisam estar '
                'preenchidos no .env (ou defina MS_SHAREPOINT_SITE_ID direto).'
            )

        url = f'{GRAPH_BASE_URL}/sites/{self.hostname}:{self.site_path}'
        resp = requests.get(url, headers=self._headers())
        if resp.status_code != 200:
            raise GraphClientError(f'Erro ao resolver site ({resp.status_code}): {resp.text}')

        self._site_id = resp.json()['id']
        return self._site_id

    def get_default_drive_id(self):
        site_id = self.get_site_id()
        url = f'{GRAPH_BASE_URL}/sites/{site_id}/drive'
        resp = requests.get(url, headers=self._headers())
        if resp.status_code != 200:
            raise GraphClientError(f'Erro ao obter drive padrão ({resp.status_code}): {resp.text}')
        return resp.json()['id']

    def upload_file(self, local_path, filename, folder_path=''):
        """
        Envia um arquivo local para a biblioteca de documentos padrão do site.
        folder_path: caminho dentro da biblioteca (ex: 'Certificados/2026'). Vazio = raiz.

        Retorna o JSON do item criado no SharePoint (inclui 'webUrl', 'id', etc).
        """
        site_id = self.get_site_id()
        drive_id = self.get_default_drive_id()

        path = f'{folder_path.strip("/")}/{filename}' if folder_path else filename
        url = f'{GRAPH_BASE_URL}/sites/{site_id}/drives/{drive_id}/root:/{path}:/content'

        with open(local_path, 'rb') as f:
            data = f.read()

        headers = self._headers()
        headers['Content-Type'] = 'application/octet-stream'
        resp = requests.put(url, headers=headers, data=data)

        if resp.status_code not in (200, 201):
            raise GraphClientError(f'Erro ao enviar arquivo ({resp.status_code}): {resp.text}')

        return resp.json()

    def resolve_share_link(self, share_url):
        """
        Resolve um link de compartilhamento do SharePoint/OneDrive (o link que
        aparece na barra de endereço ao abrir um arquivo ou pasta) direto para
        o driveItem correspondente via Graph, sem precisar adivinhar o caminho
        interno na biblioteca de documentos.

        Retorna o JSON do driveItem (tem 'id', 'name', 'webUrl', 'parentReference'
        com 'driveId', e 'file' ou 'folder' conforme o tipo).
        """
        encoded = base64.urlsafe_b64encode(share_url.encode('utf-8')).decode('utf-8')
        share_id = 'u!' + encoded.rstrip('=')

        url = f'{GRAPH_BASE_URL}/shares/{share_id}/driveItem'
        resp = requests.get(url, headers=self._headers())
        if resp.status_code != 200:
            raise GraphClientError(f'Erro ao resolver link compartilhado ({resp.status_code}): {resp.text}')
        return resp.json()

    def download_item_by_ref(self, drive_id, item_id):
        url = f'{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/content'
        resp = requests.get(url, headers=self._headers())
        if resp.status_code != 200:
            raise GraphClientError(f'Erro ao baixar arquivo ({resp.status_code}): {resp.text}')
        return resp.content

    def upload_bytes_by_ref(self, drive_id, item_id, data):
        url = f'{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/content'
        headers = self._headers()
        headers['Content-Type'] = 'application/octet-stream'
        resp = requests.put(url, headers=headers, data=data)
        if resp.status_code not in (200, 201):
            raise GraphClientError(f'Erro ao salvar arquivo ({resp.status_code}): {resp.text}')
        return resp.json()

    def list_folder_by_ref(self, drive_id, item_id):
        items = []
        url = f'{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/children'
        while url:
            resp = requests.get(url, headers=self._headers())
            if resp.status_code != 200:
                raise GraphClientError(f'Erro ao listar pasta ({resp.status_code}): {resp.text}')
            data = resp.json()
            items.extend(data.get('value', []))
            url = data.get('@odata.nextLink')
        return items

    def list_folder_files(self, folder_path):
        """
        Lista os arquivos dentro de uma pasta da biblioteca de documentos padrão.
        Retorna uma lista de dicts com pelo menos 'name' e 'webUrl'.
        """
        site_id = self.get_site_id()
        drive_id = self.get_default_drive_id()

        folder_path = folder_path.strip('/')
        url = f'{GRAPH_BASE_URL}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}:/children'

        items = []
        while url:
            resp = requests.get(url, headers=self._headers())
            if resp.status_code != 200:
                raise GraphClientError(f'Erro ao listar pasta ({resp.status_code}): {resp.text}')
            data = resp.json()
            items.extend(data.get('value', []))
            url = data.get('@odata.nextLink')

        return items

    def download_item(self, item_path):
        """
        Baixa o conteúdo de um arquivo (por caminho na biblioteca padrão).
        Retorna os bytes do arquivo.
        """
        site_id = self.get_site_id()
        drive_id = self.get_default_drive_id()

        item_path = item_path.strip('/')
        url = f'{GRAPH_BASE_URL}/sites/{site_id}/drives/{drive_id}/root:/{item_path}:/content'
        resp = requests.get(url, headers=self._headers())
        if resp.status_code != 200:
            raise GraphClientError(f'Erro ao baixar arquivo ({resp.status_code}): {resp.text}')
        return resp.content

    def upload_bytes(self, item_path, data):
        """
        Sobe (substitui) um arquivo existente na biblioteca padrão a partir de bytes em memória.
        Usado para gravar de volta um Excel editado, por exemplo.
        """
        site_id = self.get_site_id()
        drive_id = self.get_default_drive_id()

        item_path = item_path.strip('/')
        url = f'{GRAPH_BASE_URL}/sites/{site_id}/drives/{drive_id}/root:/{item_path}:/content'

        headers = self._headers()
        headers['Content-Type'] = 'application/octet-stream'
        resp = requests.put(url, headers=headers, data=data)
        if resp.status_code not in (200, 201):
            raise GraphClientError(f'Erro ao salvar arquivo ({resp.status_code}): {resp.text}')
        return resp.json()
