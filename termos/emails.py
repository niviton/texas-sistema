"""Comprovante do termo finalizado por e-mail aos supervisores (mesmo envio em segundo plano dos checklists)."""
import logging
import threading

from django.conf import settings
from django.db import close_old_connections

from veiculos.emails import _send, supervisor_emails

from .models import ModeloTermo
from .pdf import pdf_filename, render_termo_pdf

logger = logging.getLogger(__name__)


def titulo_termo(termo):
    doc = termo.documento or ModeloTermo.do_tipo(termo.tipo)
    return f'Termo de {termo.get_tipo_display().lower()} {doc.codigo} nº {termo.numero}: {termo.cliente_contato}'


def enviar_termo(termo):
    titulo = titulo_termo(termo)
    enviado = _send(titulo, 'termos/email/termo.html', {'titulo': titulo}, to=supervisor_emails(),
                    attachments=[(pdf_filename(termo), render_termo_pdf(termo), 'application/pdf')])
    if enviado:
        termo.email_enviado = True
        termo.save(update_fields=['email_enviado'])
    return enviado


def _enviar(termo_id):
    from .models import Termo

    close_old_connections()
    try:
        enviar_termo(Termo.objects.get(pk=termo_id))
    except Exception:
        logger.exception('Falha ao enviar o termo %s', termo_id)
    finally:
        close_old_connections()


def enviar_em_segundo_plano(termo_id):
    if getattr(settings, 'VEICULOS_EMAIL_ASYNC', True):
        threading.Thread(target=_enviar, args=(termo_id,), daemon=True).start()
    else:
        _enviar(termo_id)
