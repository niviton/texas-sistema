import logging
import threading
from datetime import date

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import close_old_connections
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import AlertaEnviado, Supervisor, Veiculo
from .pdf import pdf_filename, render_inspecao_pdf

logger = logging.getLogger(__name__)


def supervisor_emails():
    return list(Supervisor.objects.filter(is_active=True).values_list('email', flat=True))


def _send(subject, template, context, to, cc=None, attachments=(), connection=None):
    to = [e for e in to if e]
    cc = [e for e in (cc or []) if e and e not in to]
    if not to and not cc:
        return False
    context = {**context, 'site_url': settings.SITE_URL.rstrip('/')}
    html = render_to_string(template, context)
    msg = EmailMultiAlternatives(
        subject, strip_tags(html), settings.DEFAULT_FROM_EMAIL, to or cc, cc=cc if to else None, connection=connection,
    )
    msg.attach_alternative(html, 'text/html')
    for name, content, mimetype in attachments:
        msg.attach(name, content, mimetype)
    msg.send()
    return True


def alertas_texto(veiculo):
    """Frases curtas de manutenção/vencimento do veículo, ex.: 'Troca de óleo: faltam 1.000 km'."""
    linhas = []
    for nome, data, dias in veiculo.vencimentos():
        if dias is None:
            linhas.append(nome)
        elif dias < 0:
            linhas.append(f'{nome}: vencido desde {data:%d/%m/%Y}')
        elif dias == 0:
            linhas.append(f'{nome}: vence hoje')
        else:
            linhas.append(f'{nome}: vence em {dias} dia{"s" if dias > 1 else ""} ({data:%d/%m/%Y})')
    return linhas


def titulo_comprovante(inspecao):
    condutor = inspecao.motorista or inspecao.created_by
    return f'Comprovante de vistoria do veículo placa: {inspecao.veiculo.placa} e condutor {condutor}'


def enviar_inspecao(inspecao, connection=None):
    """Comprovante de toda vistoria: só o título e o PDF em anexo (todo o detalhe está no PDF)."""
    titulo = titulo_comprovante(inspecao)
    anexos = [(pdf_filename(inspecao), render_inspecao_pdf(inspecao), 'application/pdf')]
    enviado = _send(
        titulo, 'veiculos/email/inspecao.html', {'titulo': titulo}, to=supervisor_emails(), attachments=anexos,
        connection=connection,
    )
    if enviado:
        inspecao.email_enviado = True
        inspecao.save(update_fields=['email_enviado'])
    return enviado


def enviar_emails_da_vistoria(inspecao_id):
    """Comprovante + avisos de manutenção, numa única conexão com o Gmail (o login leva ~2 s)."""
    from .models import Inspecao

    close_old_connections()
    try:
        inspecao = Inspecao.objects.select_related('veiculo', 'motorista', 'created_by').get(pk=inspecao_id)
        with get_connection() as conn:
            try:
                enviar_inspecao(inspecao, connection=conn)
            except Exception:
                logger.exception('Falha ao enviar o comprovante da vistoria %s', inspecao_id)
            try:
                enviar_alertas_veiculo(inspecao.veiculo, connection=conn)
            except Exception:
                logger.exception('Falha ao enviar aviso de manutenção do veículo %s', inspecao.veiculo_id)
    except Exception:
        logger.exception('Falha ao preparar os e-mails da vistoria %s', inspecao_id)
    finally:
        close_old_connections()


def enviar_emails_da_vistoria_em_segundo_plano(inspecao_id):
    """Não deixa a tela do vistoriador esperando o Gmail (~4 s por e-mail)."""
    if getattr(settings, 'VEICULOS_EMAIL_ASYNC', True):
        threading.Thread(target=enviar_emails_da_vistoria, args=(inspecao_id,), daemon=True).start()
    else:
        enviar_emails_da_vistoria(inspecao_id)


def _ja_enviado(chave):
    return AlertaEnviado.objects.filter(chave=chave).exists()


def _marcar_enviado(*chaves):
    for chave in chaves:
        AlertaEnviado.objects.get_or_create(chave=chave)


def _chave_vencimento(v, nome, data_venc, dias):
    if dias is None:
        # Itens por km: o texto muda a cada km rodado ("faltam 900 km"), então a chave usa
        # só o nome da manutenção e o km alvo, entre parênteses no fim do texto.
        return f'venc:{v.pk}:km:{nome.split(":")[0]}:{nome.rsplit("(", 1)[-1]}'
    if dias < 0:
        marco = 'vencido'
    else:
        marco = next(m for m in (0, 7, 15, 30) if dias <= m) if dias <= 30 else None
    return f'venc:{v.pk}:{nome}:{data_venc}:{marco}'


def _vencimentos_novos(v, dias_vencimento=30):
    novos = []
    for nome, data_venc, dias in v.vencimentos(dias_vencimento):
        chave = _chave_vencimento(v, nome, data_venc, dias)
        if not _ja_enviado(chave):
            novos.append({'veiculo': v, 'nome': nome, 'data': data_venc, 'dias': dias, 'chave': chave})
    return novos


def enviar_alertas_veiculo(veiculo, connection=None):
    """
    Chamado logo depois de uma vistoria, já com o km real do painel: se alguma manutenção ou
    vencimento entrou na faixa de aviso configurada, avisa os supervisores na hora.
    Usa as mesmas chaves do resumo diário, então o mesmo aviso nunca chega duas vezes.
    """
    novos = _vencimentos_novos(veiculo)
    if not novos:
        return 0
    if len(novos) == 1:
        assunto = f'Aviso de manutenção: veículo placa {veiculo.placa}, {novos[0]["nome"].split(" (no km")[0]}'
    else:
        assunto = f'Aviso de manutenção: veículo placa {veiculo.placa}, {len(novos)} itens'
    if _send(assunto, 'veiculos/email/aviso_veiculo.html', {'veiculo': veiculo, 'avisos': novos}, to=supervisor_emails(),
             connection=connection):
        _marcar_enviado(*(n['chave'] for n in novos))
        return len(novos)
    return 0


def enviar_alertas(dias_vencimento=30):
    """
    Envia (1) um resumo de vencimentos próximos aos supervisores e (2) lembretes de
    checklist atrasado ao motorista responsável, com cópia para os supervisores.
    Cada alerta só é enviado uma vez por marco (30, 15, 7 dias, vencido), então pode
    rodar todo dia sem repetir e-mails.
    Retorna (qtde_vencimentos, qtde_lembretes).
    """
    hoje = date.today()
    supervisores = supervisor_emails()

    novos_vencimentos = []
    for v in Veiculo.objects.filter(is_active=True).select_related('motorista_responsavel'):
        novos_vencimentos += _vencimentos_novos(v, dias_vencimento)
    if novos_vencimentos and _send(
        f'[Frota] {len(novos_vencimentos)} vencimento(s) próximo(s)', 'veiculos/email/vencimentos.html',
        {'vencimentos': novos_vencimentos, 'hoje': hoje}, to=supervisores,
    ):
        _marcar_enviado(*(n['chave'] for n in novos_vencimentos))
    else:
        novos_vencimentos = []

    lembretes = 0
    for v in Veiculo.objects.filter(is_active=True).select_related('motorista_responsavel'):
        ultima = v.ultima_inspecao
        dias_sem = (hoje - ultima.created_at.date()).days if ultima else None
        if dias_sem is not None and dias_sem < v.checklist_frequencia_dias:
            continue
        # Um lembrete por período de atraso (não repete todo dia).
        chave = f'lembrete:{v.pk}:{hoje.toordinal() // max(v.checklist_frequencia_dias, 1)}'
        if _ja_enviado(chave):
            continue
        motorista = v.motorista_responsavel
        if _send(
            f'[Checklist] Lembrete: inspeção do veículo {v.placa}', 'veiculos/email/lembrete.html',
            {'veiculo': v, 'motorista': motorista, 'ultima': ultima, 'dias_sem': dias_sem},
            to=[motorista.email] if motorista and motorista.email else [], cc=supervisores,
        ):
            _marcar_enviado(chave)
            lembretes += 1

    return len(novos_vencimentos), lembretes


def enviar_teste(destino):
    return _send('[Polaris] Teste de e-mail da frota', 'veiculos/email/teste.html', {}, to=[destino])
