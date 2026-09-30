"""
Preenche, na planilha de controle de certificados (no SharePoint), o link
exato de cada certificado — casando pelo código.

Uso:
    python manage.py sync_certificate_links
    python manage.py sync_certificate_links --dry-run   # só mostra o que faria, não sobe nada

Requer no .env: MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET,
MS_SHAREPOINT_HOSTNAME, MS_SHAREPOINT_SITE_PATH, MS_EXCEL_ITEM_PATH,
MS_CERTIFICATES_FOLDER_PATH.
"""

import io

from django.conf import settings
from django.core.management.base import BaseCommand
from openpyxl import load_workbook

from certificates.graph_client import GraphClient, GraphClientError


class Command(BaseCommand):
    help = 'Preenche a coluna de link exato na planilha de certificados, casando pelo código.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Não sobe a planilha alterada, só mostra o que seria escrito.',
        )

    def handle(self, *args, **options):
        cfg = settings.MS_GRAPH
        excel_path = cfg.get('EXCEL_ITEM_PATH')
        folder_path = cfg.get('CERTIFICATES_FOLDER_PATH')
        excel_share_url = cfg.get('EXCEL_SHARE_URL')
        folder_share_url = cfg.get('CERTIFICATES_FOLDER_SHARE_URL')
        code_col_name = cfg.get('EXCEL_CODE_COLUMN', 'Código')
        link_col_name = cfg.get('EXCEL_LINK_COLUMN', 'Link')

        if not (excel_share_url or excel_path):
            self.stderr.write(self.style.ERROR(
                'Preencha MS_EXCEL_SHARE_URL (recomendado) ou MS_EXCEL_ITEM_PATH no .env.'
            ))
            return
        if not (folder_share_url or folder_path):
            self.stderr.write(self.style.ERROR(
                'Preencha MS_CERTIFICATES_FOLDER_SHARE_URL (recomendado) ou '
                'MS_CERTIFICATES_FOLDER_PATH no .env.'
            ))
            return

        try:
            client = GraphClient()
        except GraphClientError as e:
            self.stderr.write(self.style.ERROR(f'Configuração incompleta: {e}'))
            return

        # Resolve a pasta de certificados (por link direto ou por caminho)
        self.stdout.write('Localizando a pasta de certificados...')
        try:
            if folder_share_url:
                folder_item = client.resolve_share_link(folder_share_url)
                files = client.list_folder_by_ref(
                    folder_item['parentReference']['driveId'], folder_item['id'],
                )
            else:
                files = client.list_folder_files(folder_path)
        except GraphClientError as e:
            self.stderr.write(self.style.ERROR(f'Falha ao listar a pasta: {e}'))
            return
        self.stdout.write(self.style.SUCCESS(f'{len(files)} arquivo(s) encontrado(s).'))

        # mapa: código (tirado do nome do arquivo, sem extensão, maiúsculo) -> webUrl
        file_by_code = {}
        for f in files:
            if 'file' not in f:  # ignora subpastas
                continue
            name = f['name']
            stem = name.rsplit('.', 1)[0].strip().upper()
            file_by_code[stem] = f['webUrl']

        self.stdout.write('Baixando a planilha...')
        try:
            if excel_share_url:
                excel_item = client.resolve_share_link(excel_share_url)
                excel_drive_id = excel_item['parentReference']['driveId']
                excel_item_id = excel_item['id']
                excel_bytes = client.download_item_by_ref(excel_drive_id, excel_item_id)
            else:
                excel_bytes = client.download_item(excel_path)
        except GraphClientError as e:
            self.stderr.write(self.style.ERROR(f'Falha ao baixar a planilha: {e}'))
            return

        wb = load_workbook(io.BytesIO(excel_bytes))
        ws = wb.active

        header = {cell.value: cell.column for cell in ws[1] if cell.value}
        if code_col_name not in header:
            self.stderr.write(self.style.ERROR(
                f'Não encontrei a coluna "{code_col_name}" na primeira linha da planilha. '
                f'Colunas encontradas: {list(header.keys())}'
            ))
            return

        code_col = header[code_col_name]
        if link_col_name in header:
            link_col = header[link_col_name]
        else:
            link_col = ws.max_column + 1
            ws.cell(row=1, column=link_col, value=link_col_name)

        matched, not_found = 0, []
        codes_in_excel = set()
        for row in range(2, ws.max_row + 1):
            code_cell = ws.cell(row=row, column=code_col)
            code = str(code_cell.value or '').strip().upper()
            if not code:
                continue
            codes_in_excel.add(code)
            url = file_by_code.get(code)
            if url:
                ws.cell(row=row, column=link_col, value=url)
                matched += 1
            else:
                not_found.append(code)

        # arquivos que existem na pasta do SharePoint mas não têm linha correspondente no Excel
        extra_files = sorted(set(file_by_code) - codes_in_excel)

        self.stdout.write(f'{matched} link(s) casado(s) e preenchido(s).')
        if not_found:
            self.stdout.write(self.style.WARNING(
                f'{len(not_found)} código(s) no Excel sem arquivo correspondente na pasta: '
                f'{", ".join(not_found[:20])}' + (' ...' if len(not_found) > 20 else '')
            ))
        if extra_files:
            self.stdout.write(self.style.WARNING(
                f'{len(extra_files)} arquivo(s) na pasta do SharePoint SEM linha correspondente no Excel: '
                f'{", ".join(extra_files[:20])}' + (' ...' if len(extra_files) > 20 else '')
            ))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('--dry-run: nada foi salvo no SharePoint.'))
            return

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        self.stdout.write('Salvando planilha atualizada de volta no SharePoint...')
        try:
            if excel_share_url:
                client.upload_bytes_by_ref(excel_drive_id, excel_item_id, buffer.getvalue())
            else:
                client.upload_bytes(excel_path, buffer.getvalue())
        except GraphClientError as e:
            self.stderr.write(self.style.ERROR(f'Falha ao salvar a planilha: {e}'))
            return

        self.stdout.write(self.style.SUCCESS('Planilha atualizada com sucesso!'))
