"""Simulates, on the local filesystem, the folder structure the certificates would
eventually live in on SharePoint (see TCB-OTB-57 in O.T. BRASIL):

    {INTERNO|EXTERNO}/{ANO}/{INSTRUTOR}/{CURSO}/{CLIENTE} - {DATA}/CERTIFICADOS/{CODIGO} - {NOME}.pdf

Only applies to certificates issued going forward — historical/imported records are
left untouched. Never raises: a failure here should not block certificate issuance.
"""
import os
import re
from pathlib import Path

from django.conf import settings

from .pdf import render_certificate

SIMULATION_ROOT = settings.BASE_DIR / 'sharepoint_simulado'

_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')


def _sanitize(value):
    value = _INVALID_CHARS.sub('', str(value or '')).strip()
    return value.rstrip('.') or 'SEM_INFORMACAO'


def _long_path(path):
    """Windows caps normal paths at 260 chars (MAX_PATH) — the nested SharePoint-style
    folder structure blows past that easily. The \\\\?\\ prefix opts into the real
    ~32k-char limit; harmless (and unnecessary but safe) on other platforms."""
    if os.name != 'nt':
        return path
    resolved = str(path.resolve())
    if not resolved.startswith('\\\\?\\'):
        resolved = '\\\\?\\' + resolved
    return Path(resolved)


def write_certificate_to_simulation(certificate, request=None):
    tipo = 'EXTERNO' if certificate.cert_type == 'externo' else 'INTERNO'
    instrutor = _sanitize(certificate.instructor_name or (certificate.professor.full_name if certificate.professor else 'SEM_INSTRUTOR'))
    curso = _sanitize(certificate.course_title)
    cliente = _sanitize(certificate.client_name or 'SEM_CLIENTE')
    data_str = certificate.course_date.strftime('%d-%m-%Y')

    folder = (
        SIMULATION_ROOT / tipo / str(certificate.course_date.year) / instrutor
        / curso / f'{cliente} - {data_str}' / 'CERTIFICADOS'
    )
    _long_path(folder).mkdir(parents=True, exist_ok=True)

    filename = _sanitize(f'{certificate.code} - {certificate.student_name}') + '.pdf'
    verify_url = None
    if request is not None:
        from .views_admin import _verify_url
        verify_url = _verify_url(request, certificate.code)
    pdf_bytes = render_certificate(certificate, verify_url=verify_url).getvalue()
    file_path = folder / filename
    _long_path(file_path).write_bytes(pdf_bytes)
    return file_path
