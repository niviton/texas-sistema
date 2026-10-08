"""Comprovante de execução por e-mail. Usa o mesmo envio do módulo de veículos (Gmail, segundo plano)."""
import logging
import threading

from django.conf import settings
from django.db import close_old_connections

from veiculos.emails import _send, supervisor_emails

from .pdf import pdf_filename, render_execucao_pdf

logger = logging.getLogger(__name__)


def titulo_comprovante(execucao):
    a = execucao.ativo
    return f'Comprovante de checklist {execucao.revisao.modelo.codigo}: {a.nome} ({a.identificacao}) e técnico {execucao.executor_nome}'


def enviar_execucao(execucao):
    titulo = titulo_comprovante(execucao)
    enviado = _send(
        titulo, 'checklists/email/comprovante.html', {'titulo': titulo}, to=supervisor_emails('checklists', execucao.ativo.tipo),
        attachments=[(pdf_filename(execucao), render_execucao_pdf(execucao), 'application/pdf')],
    )
    if enviado:
        execucao.email_enviado = True
        execucao.save(update_fields=['email_enviado'])
    return enviado


def _enviar(execucao_id):
    from .models import Execucao

    close_old_connections()
    try:
        enviar_execucao(Execucao.objects.select_related('revisao__modelo', 'ativo__tipo').get(pk=execucao_id))
    except Exception:
        logger.exception('Falha ao enviar o comprovante do checklist %s', execucao_id)
    finally:
        close_old_connections()


def enviar_em_segundo_plano(execucao_id):
    if getattr(settings, 'VEICULOS_EMAIL_ASYNC', True):
        threading.Thread(target=_enviar, args=(execucao_id,), daemon=True).start()
    else:
        _enviar(execucao_id)
