"""PDF do termo no layout dos formulários TCB-LO-01 / TCB-LO-02 (mesmo cabeçalho e rodapé dos checklists)."""
import io

from django.utils import timezone
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from checklists.pdf import _CanvasChecklist
from veiculos import pdf as base

from .models import DECLARACAO, ModeloTermo

_s = base._s
AMARELO = base.YELLOW
AZUL = base.BLUE
_cel = ParagraphStyle('cel', fontName='Mont', fontSize=9, leading=11.5, textColor=base.TEXT)
_rot = ParagraphStyle('rot', fontName='Mont-Bold', fontSize=8.5, leading=10.5, textColor=colors.white)
_th = ParagraphStyle('th', fontName='Mont-Bold', fontSize=8.5, leading=10.5, textColor=colors.white)
_decl = ParagraphStyle('decl', fontName='Mont-Bold', fontSize=8.5, leading=11.5, textColor=AZUL, alignment=TA_JUSTIFY)
_barra = ParagraphStyle('barra', fontName='Mont-Bold', fontSize=9, leading=11, textColor=colors.white, alignment=TA_CENTER)
_obsr = ParagraphStyle('obsr', fontName='Mont-Bold', fontSize=8.5, leading=10.5, textColor=AZUL)


def _linhas_amarelas(t, extra=()):
    """Como no formulário: só linhas horizontais amarelas entre as linhas da tabela."""
    t.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, AMARELO),
        ('LINEBELOW', (0, 0), (-1, -1), 1.2, AMARELO),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        *extra,
    ]))
    return t


def _dados(termo):
    r = termo.rotulos
    linhas = [
        ('Nº DO ASSUNTO', termo.numero_assunto),
        (r['motivo'].upper(), termo.motivo),
        (r['data'].upper(), termo.data.strftime('%d/%m/%Y')),
        ('CLIENTE & PESSOA DE CONTATO', termo.cliente_contato),
        ('ORIGEM (PROJETO / PARQUE ESPECÍFICO)', termo.origem),
        ('TRANSPORTE', termo.transporte),
    ]
    rows = [[Paragraph(k, _rot), Paragraph(v or '—', _cel)] for k, v in linhas]
    t = Table(rows, colWidths=[46 * mm, base.CONTENT_W - 46 * mm])
    return _linhas_amarelas(t, [('BACKGROUND', (0, 0), (0, -1), AZUL)])


def _equipamentos(termo):
    rows = [[Paragraph('EQUIPAMENTO', _th), Paragraph('REFERÊNCIA', _th), Paragraph('QUANTIDADE', _th), Paragraph('INFORMAÇÃO', _th)]]
    for n, it in enumerate(termo.itens.all(), start=1):
        rows.append([Paragraph(f'{n}- {it.descricao}', _cel), Paragraph(it.referencia or '—', _cel),
                     Paragraph(str(it.quantidade), _cel), Paragraph(it.informacao or '—', _cel)])
    w = base.CONTENT_W
    t = Table(rows, colWidths=[w * 0.37, w * 0.24, w * 0.17, w * 0.22], repeatRows=1)
    return _linhas_amarelas(t, [('BACKGROUND', (0, 0), (-1, 0), AZUL), ('ALIGN', (2, 1), (2, -1), 'CENTER')])


def _observacoes(termo):
    t = Table([[Paragraph('OBSERVAÇÕES:', _obsr), Paragraph((termo.observacoes or '').replace('\n', '<br/>'), _cel)]],
              colWidths=[30 * mm, base.CONTENT_W - 30 * mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def _barra_azul(texto):
    t = Table([[Paragraph(texto, _barra)]], colWidths=[base.CONTENT_W])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), AZUL), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    return t


def _fotos(termo):
    fotos = list(termo.fotos.all())
    if not fotos:
        return [Paragraph('<font color="#777777">Nenhuma foto registrada.</font>', _s['body'])]
    col_w = base.CONTENT_W / 2
    cells = []
    for foto in fotos:
        try:
            cells.append(base._foto_flowable(foto, col_w - 8 * mm, 60 * mm))
        except Exception:
            cells.append(Paragraph('(foto não pôde ser carregada)', _s['caption']))
    if len(cells) == 1:  # uma foto só fica centralizada, como no formulário
        t = Table([[cells[0]]], colWidths=[base.CONTENT_W])
        t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        return [t]
    linhas = []
    for i in range(0, len(cells), 2):
        row = cells[i:i + 2] + [''] * (2 - len(cells[i:i + 2]))
        t = Table([row], colWidths=[col_w, col_w])
        t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        linhas.append(t)
    return linhas


def _imagem_assinatura(campo, max_w, max_h):
    """Imagem da assinatura; sem assinatura (rascunho), um espaço em branco do mesmo tamanho."""
    vazio = Spacer(max_w, max_h)
    if not campo:
        return vazio
    try:
        with campo.open('rb') as f:
            img = PILImage.open(f)
            img.load()
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        r = min(max_w / img.width, max_h / img.height)
        return Image(buf, width=img.width * r, height=img.height * r, mask='auto')
    except Exception:
        return vazio


def _assinaturas(termo):
    w = base.CONTENT_W
    texas = [_imagem_assinatura(termo.assinatura_texas, 70 * mm, 12 * mm), Paragraph(termo.responsavel_texas or '', _s['caption'])]
    cliente = [_imagem_assinatura(termo.assinatura_cliente, 60 * mm, 12 * mm), Paragraph(termo.nome_cliente or '', _s['caption'])]
    rows = [
        [Paragraph('ASSINATURA RESPONSÁVEL PELA TEXAS', _rot), texas, '', ''],
        [Paragraph('ASSINATURA RESPONSÁVEL PELO CLIENTE (Nome Legível)', _rot), cliente, Paragraph('TELEFONE', _rot),
         Paragraph(termo.telefone_cliente or '', _cel)],
    ]
    t = Table(rows, colWidths=[38 * mm, w - 38 * mm - 52 * mm, 22 * mm, 30 * mm], rowHeights=[19 * mm, 19 * mm])
    return _linhas_amarelas(t, [
        ('SPAN', (1, 0), (3, 0)),
        ('BACKGROUND', (0, 0), (0, -1), AZUL), ('BACKGROUND', (2, 1), (2, 1), AZUL),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
    ])


def render_termo_pdf(termo):
    doc_ctrl = termo.documento or ModeloTermo.do_tipo(termo.tipo)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=base.MARGIN_X, rightMargin=base.MARGIN_X,
        topMargin=base.HEADER_H + 9 * mm, bottomMargin=base.FOOTER_H,
        title=f'{doc_ctrl.codigo} nº {termo.numero}', author='Texas Controls',
    )
    fotos = _fotos(termo)
    story = [
        _dados(termo), Spacer(1, 0), _equipamentos(termo), _observacoes(termo), Spacer(1, 2 * mm),
        KeepTogether([_barra_azul('REGISTRO FOTOGRÁFICO'), Spacer(1, 3 * mm), fotos[0]]),
        *fotos[1:],
        Spacer(1, 4 * mm),
        KeepTogether([_assinaturas(termo), Spacer(1, 5 * mm), Paragraph(DECLARACAO, _decl)]),
    ]
    cab = {
        'titulo': doc_ctrl.titulo.upper(), 'codigo': doc_ctrl.codigo,
        'revisao': termo.documento_revisao or doc_ctrl.revisao,
        'preparado': doc_ctrl.preparado_por, 'revisado': doc_ctrl.revisado_por,
        'data': doc_ctrl.data.strftime('%d/%m/%Y') if doc_ctrl.data else '',
    }
    doc.build(story, canvasmaker=type('CanvasTermo', (_CanvasChecklist,), {'cab': cab}))
    return buf.getvalue()


def pdf_filename(termo):
    doc_ctrl = termo.documento or ModeloTermo.do_tipo(termo.tipo)
    cliente = ''.join(c for c in termo.cliente_contato[:30] if c.isalnum() or c in ' -_').strip().replace(' ', '_') or 'cliente'
    return f'{doc_ctrl.codigo}_{termo.numero}_{cliente}_{termo.data:%Y-%m-%d}.pdf'
