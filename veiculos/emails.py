import email.policy
import functools
import html as html_lib
import io
import logging
import re
import threading
from datetime import date

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import close_old_connections
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import AlertaEnviado, Supervisor, Veiculo
from .pdf import pdf_filename, render_inspecao_pdf

logger = logging.getLogger(__name__)


def supervisor_emails(modulo=None, tipo_ativo=None):
    return Supervisor.emails(modulo, tipo_ativo)


def _png(img):
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def _icone_rede(nome, tamanho=44):
    """Ícone quadrado azul-marinho com o símbolo da rede em branco (desenhado aqui: não depende de site externo)."""
    from PIL import Image, ImageDraw, ImageFont
    k = 4
    t = tamanho * k
    img = Image.new('RGBA', (t, t), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    azul, branco = (13, 36, 64, 255), (255, 255, 255, 255)
    d.rounded_rectangle((0, 0, t - 1, t - 1), radius=int(t * 0.14), fill=azul)
    fonte = str(settings.BASE_DIR / 'veiculos' / 'assets' / 'fonts' / 'Montserrat-Bold.ttf')
    if nome in ('facebook', 'linkedin'):
        texto = 'f' if nome == 'facebook' else 'in'
        f = ImageFont.truetype(fonte, int(t * (0.78 if nome == 'facebook' else 0.5)))
        x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=f)
        dx = int(t * 0.08) if nome == 'facebook' else 0
        d.text(((t - (x1 - x0)) / 2 - x0 + dx, (t - (y1 - y0)) / 2 - y0 + (int(t * 0.06) if nome == 'facebook' else 0)), texto, font=f, fill=branco)
    elif nome == 'youtube':
        d.rounded_rectangle((t * 0.17, t * 0.27, t * 0.83, t * 0.73), radius=int(t * 0.13), fill=branco)
        d.polygon([(t * 0.43, t * 0.38), (t * 0.43, t * 0.62), (t * 0.63, t * 0.5)], fill=azul)
    elif nome == 'instagram':
        d.rounded_rectangle((t * 0.2, t * 0.2, t * 0.8, t * 0.8), radius=int(t * 0.17), outline=branco, width=int(t * 0.07))
        d.ellipse((t * 0.35, t * 0.35, t * 0.65, t * 0.65), outline=branco, width=int(t * 0.07))
        d.ellipse((t * 0.64, t * 0.25, t * 0.72, t * 0.33), fill=branco)
    return _png(img.resize((tamanho, tamanho), Image.LANCZOS))


@functools.lru_cache(maxsize=1)
def imagens_do_email():
    """Imagens embutidas no próprio e-mail (o Gmail não abre imagens do servidor da oficina):
    cid -> bytes. Logo branca (cabeçalho), logo colorida e ícones das redes (assinatura)."""
    from django.contrib.staticfiles import finders
    from PIL import Image
    saida = {}
    for cid, arquivo, largura in [('logo-texas', 'logo-texas-branco.png', 220), ('logo-texas-cor', 'logo-texas-cor-hd.png', 300)]:
        caminho = finders.find('assets/' + arquivo)
        if caminho:
            img = Image.open(caminho).convert('RGBA')
            img.thumbnail((largura, largura))
            saida[cid] = _png(img)
    for nome, _, _ in settings.EMAIL_ASSINATURA['redes']:
        saida[f'rede-{nome}'] = _icone_rede(nome)
    return saida


class _EmailTexas(EmailMultiAlternatives):
    """E-mail com as imagens embutidas (cid:...). Não contam como anexo: o PDF continua sendo o único."""

    def message(self, *, policy=email.policy.default):
        msg = super().message(policy=policy)
        corpo = msg.get_body(preferencelist=('html',))
        if corpo is not None:
            html = corpo.get_content()
            for cid, dados in imagens_do_email().items():
                if f'cid:{cid}"' in html:
                    corpo.add_related(dados, 'image', 'png', cid=f'<{cid}>', disposition='inline')
        return msg


def _texto_simples(html):
    """Versão só texto do e-mail (para leitores sem HTML e para a prévia): sem tags nem linhas em excesso."""
    t = re.sub(r'(?is)<(style|head)[^>]*>.*?</\1>', '', html)
    t = re.sub(r'(?is)<div[^>]*display:\s*none[^>]*>.*?</div>', '', t)
    t = re.sub(r'(?i)<br\s*/?>|</p>|</tr>|</h1>|</div>|</table>', '\n', t)
    t = html_lib.unescape(strip_tags(t))
    linhas = [re.sub(r'[ \t\u00a0]+', ' ', l).strip() for l in t.splitlines()]
    saida = []
    for l in linhas:
        if l or (saida and saida[-1]):
            saida.append(l)
    return '\n'.join(saida).strip()


def _itens_nc(n):
    return f'{n} item não conforme' if n == 1 else f'{n} itens não conformes'


def _quando(dt):
    return timezone.localtime(dt).strftime('%d/%m/%Y às %H:%M')


def _send(subject, template, context, to, cc=None, attachments=(), connection=None):
    to = [e for e in to if e]
    cc = [e for e in (cc or []) if e and e not in to]
    if not to and not cc:
        return False
    context = {**context, 'site_url': settings.SITE_URL.rstrip('/'), 'anexos': [nome for nome, _, _ in attachments],
               'assinatura': settings.EMAIL_ASSINATURA}
    html = render_to_string(template, context)
    msg = _EmailTexas(
        subject, _texto_simples(html), settings.DEFAULT_FROM_EMAIL, to or cc, cc=cc if to else None, connection=connection,
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
    from django.urls import reverse
    v, problemas = inspecao.veiculo, inspecao.itens_problema
    condutor = inspecao.motorista or inspecao.created_by
    contexto = {
        'titulo': titulo,
        'status': 'problema' if problemas else 'ok',
        'status_texto': _itens_nc(len(problemas)) if problemas else 'Sem problemas',
        'resumo': [
            ('Veículo', f'{v.placa} · {v.marca} {v.modelo}'.strip()),
            ('Vistoria', f'{inspecao.get_tipo_display()} · {inspecao.km} km'),
            ('Condutor', str(condutor)),
            ('Data', _quando(inspecao.created_at)),
        ],
        'link': settings.SITE_URL.rstrip('/') + reverse('veiculos:inspecao_detalhe', args=[inspecao.pk]),
    }
    enviado = _send(
        titulo, 'veiculos/email/inspecao.html', contexto, to=supervisor_emails('veiculos'), attachments=anexos,
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
    if _send(assunto, 'veiculos/email/aviso_veiculo.html', {'veiculo': veiculo, 'avisos': novos}, to=supervisor_emails('veiculos'),
             connection=connection):
        _marcar_enviado(*(n['chave'] for n in novos))
        return len(novos)
    return 0


def enviar_alertas(dias_vencimento=30):
    """
    Envia (1) um resumo de vencimentos próximos aos destinatários e (2) lembretes de
    checklist atrasado ao motorista responsável, com cópia para os supervisores.
    Cada alerta só é enviado uma vez por marco (30, 15, 7 dias, vencido), então pode
    rodar todo dia sem repetir e-mails.
    Retorna (qtde_vencimentos, qtde_lembretes).
    """
    hoje = date.today()
    supervisores = supervisor_emails('veiculos')

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
