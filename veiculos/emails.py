import logging
from datetime import date

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import AlertaEnviado, Supervisor, Veiculo
from .pdf import pdf_filename, render_inspecao_pdf

logger = logging.getLogger(__name__)


def supervisor_emails():
    return list(Supervisor.objects.filter(is_active=True).values_list('email', flat=True))


def _send(subject, template, context, to, cc=None, attachments=()):
    to = [e for e in to if e]
    cc = [e for e in (cc or []) if e and e not in to]
    if not to and not cc:
        return False
    context = {**context, 'site_url': settings.SITE_URL.rstrip('/')}
    html = render_to_string(template, context)
    msg = EmailMultiAlternatives(subject, strip_tags(html), settings.DEFAULT_FROM_EMAIL, to or cc, cc=cc if to else None)
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


def enviar_inspecao(inspecao):
    """Relatório de toda inspeção feita. Se houver item 'Não OK', o assunto destaca o problema."""
    problemas = inspecao.itens_problema
    v = inspecao.veiculo
    quem = inspecao.motorista or inspecao.created_by
    subject = f'Inspeção de {inspecao.get_tipo_display().lower()} · {v.placa} · {quem}'
    if problemas:
        subject = f'{subject} · {len(problemas)} item(ns) com problema'
    # As fotos e a assinatura já vão dentro do PDF; o corpo fica curto.
    anexos = [(pdf_filename(inspecao), render_inspecao_pdf(inspecao), 'application/pdf')]
    enviado = _send(
        subject, 'veiculos/email/inspecao.html',
        {'inspecao': inspecao, 'problemas': problemas, 'alertas': alertas_texto(v)},
        to=supervisor_emails(), attachments=anexos,
    )
    if enviado:
        inspecao.email_enviado = True
        inspecao.save(update_fields=['email_enviado'])
    return enviado


def _ja_enviado(chave):
    return AlertaEnviado.objects.filter(chave=chave).exists()


def _marcar_enviado(*chaves):
    for chave in chaves:
        AlertaEnviado.objects.get_or_create(chave=chave)


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
        for nome, data_venc, dias in v.vencimentos(dias_vencimento):
            if dias is None:
                # Itens por km: o texto muda a cada km rodado ("faltam 900 km"), então a chave usa
                # só o nome da manutenção e o km alvo, entre parênteses no fim do texto.
                chave = f'venc:{v.pk}:km:{nome.split(":")[0]}:{nome.rsplit("(", 1)[-1]}'
            else:
                if dias < 0:
                    marco = 'vencido'
                else:
                    marco = next(m for m in (0, 7, 15, 30) if dias <= m) if dias <= 30 else None
                chave = f'venc:{v.pk}:{nome}:{data_venc}:{marco}'
            if not _ja_enviado(chave):
                novos_vencimentos.append({'veiculo': v, 'nome': nome, 'data': data_venc, 'dias': dias, 'chave': chave})
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
