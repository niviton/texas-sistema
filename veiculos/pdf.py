"""Comprovante de vistoria em PDF: layout enxuto, com a identidade da Texas Controls."""
import io
from pathlib import Path

from django.utils import timezone
from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import CHECKLIST_ITEMS, FOTO_ORDEM, ITEM_NOK, ITEM_OK

ASSETS = Path(__file__).resolve().parent / 'assets'

# Controle do documento (rodapé). Ajuste quando o formulário receber número oficial.
DOC_CODE = 'TCB-OTB-VEIC'
DOC_REVISAO = '00'
RODAPE = ('Texas Controls Brasil · BR-304 (KM 11,5), Parque de Exposições, 675, Loja B, Parnamirim/RN · '
          '+55 84 3643-2108 · office.brasil@texascontrols.com')

INK = colors.HexColor('#1b2430')
MUTED = colors.HexColor('#6b7480')
RULE = colors.HexColor('#e3e7ec')
BLUE = colors.HexColor('#365f91')
YELLOW = colors.HexColor('#ffc000')
RED = colors.HexColor('#b3261e')
GREEN = colors.HexColor('#2f7d4f')
PAGE_W, PAGE_H = A4
MARGIN_X = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X - 12  # o Frame do ReportLab tem 6pt de margem interna de cada lado


def _register_fonts():
    if 'Mont' in pdfmetrics.getRegisteredFontNames():
        return
    fonts = ASSETS / 'fonts'
    pdfmetrics.registerFont(TTFont('Mont', str(fonts / 'Montserrat-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('Mont-Bold', str(fonts / 'Montserrat-Bold.ttf')))
    pdfmetrics.registerFont(TTFont('Mont-Italic', str(fonts / 'Montserrat-Italic.ttf')))
    pdfmetrics.registerFont(TTFont('Mont-Semi', str(fonts / 'Montserrat-SemiBold.ttf')))
    pdfmetrics.registerFontFamily('Mont', normal='Mont', bold='Mont-Bold', italic='Mont-Italic', boldItalic='Mont-Bold')


_register_fonts()

_s = {
    'h1': ParagraphStyle('h1', fontName='Mont-Bold', fontSize=16, leading=19, textColor=INK),
    'meta': ParagraphStyle('meta', fontName='Mont', fontSize=8.5, leading=11, textColor=MUTED),
    'h2': ParagraphStyle('h2', fontName='Mont-Semi', fontSize=10, leading=13, textColor=BLUE),
    'k': ParagraphStyle('k', fontName='Mont', fontSize=7.5, leading=9.5, textColor=MUTED),
    'v': ParagraphStyle('v', fontName='Mont-Semi', fontSize=9.5, leading=12, textColor=INK),
    'body': ParagraphStyle('body', fontName='Mont', fontSize=9, leading=12.5, textColor=INK),
    'item': ParagraphStyle('item', fontName='Mont', fontSize=8.5, leading=10.5, textColor=INK),
    'obs': ParagraphStyle('obs', fontName='Mont-Italic', fontSize=7.5, leading=9, textColor=RED),
    'mark': ParagraphStyle('mark', fontName='Mont-Bold', fontSize=7.5, leading=10, alignment=TA_CENTER),
    'caption': ParagraphStyle('caption', fontName='Mont', fontSize=7, leading=9, textColor=MUTED, alignment=TA_CENTER),
    'sig': ParagraphStyle('sig', fontName='Mont', fontSize=8.5, leading=11, textColor=INK, alignment=TA_CENTER),
}


def _h2(text):
    return [Spacer(1, 6 * mm), Paragraph(text, _s['h2']), Spacer(1, 2 * mm)]


def _cabecalho(inspecao):
    data = timezone.localtime(inspecao.created_at)
    logo = Image(str(ASSETS / 'logo-texas.png'), width=19 * mm, height=16 * mm) if (ASSETS / 'logo-texas.png').exists() else ''
    texto = [
        Paragraph('Comprovante de vistoria', _s['h1']),
        Spacer(1, 1.2 * mm),
        Paragraph(f'Vistoria nº {inspecao.pk:05d} · {inspecao.get_tipo_display()} · {data:%d/%m/%Y às %H:%M}', _s['meta']),
    ]
    t = Table([[texto, logo]], colWidths=[CONTENT_W - 24 * mm, 24 * mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, 0), 1.6, YELLOW),
    ]))
    return t


def _status(inspecao):
    problemas = inspecao.itens_problema
    if problemas:
        texto = f'<font color="#b3261e"><b>{len(problemas)} item(ns) com problema</b></font>  ' + \
            ', '.join(p.label for p in problemas)
    else:
        texto = '<font color="#2f7d4f"><b>Aprovado</b></font>  Nenhum problema encontrado no checklist.'
    return Paragraph(texto, _s['body'])


def _dados(inspecao):
    v = inspecao.veiculo
    pares = [
        ('Placa', v.placa),
        ('Veículo', f'{v.marca} {v.modelo} ({v.get_categoria_display().lower()})'),
        ('Condutor', str(inspecao.motorista or '—')),
        ('Km no painel', f'{inspecao.km:,}'.replace(',', '.') + ' km'),
        ('Combustível', inspecao.combustivel_label),
    ]
    pneus = inspecao.pneus
    if pneus:
        pares.append(('Pneus (DE · DD · TE · TD)', ' · '.join(f'{p}%' if p is not None else '—' for _, _, p in pneus)))
    if inspecao.com_carga is not None:
        pares.append(('Leva carga', inspecao.carga_label))
    pares.append(('Registrado por', str(inspecao.created_by or '—')))
    if len(pares) % 2:
        pares.append(('', ''))
    rows = []
    for i in range(0, len(pares), 2):
        rows.append([[Paragraph(k, _s['k']), Paragraph(val, _s['v'])] if k else '' for k, val in pares[i:i + 2]])
    t = Table(rows, colWidths=[CONTENT_W / 2] * 2)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, RULE),
    ]))
    return t


def _marca(status):
    if status == ITEM_OK:
        return Paragraph('<font color="#2f7d4f">OK</font>', _s['mark'])
    if status == ITEM_NOK:
        return Paragraph('<font color="#b3261e">NOK</font>', _s['mark'])
    return Paragraph('<font color="#9aa3ad">N/A</font>', _s['mark'])


def _checklist(inspecao):
    """Lista compacta em duas colunas; itens com problema ganham a descrição em vermelho."""
    por_item = {i.item: i for i in inspecao.itens.all()}
    celulas = []
    for _, itens in CHECKLIST_ITEMS:
        for key, label in itens:
            it = por_item.get(key)
            texto = [Paragraph(label, _s['item'])]
            if it and it.observacao:
                texto.append(Paragraph(it.observacao, _s['obs']))
            celulas.append((texto, _marca(it.status if it else None)))
    metade = (len(celulas) + 1) // 2
    esq, dir_ = celulas[:metade], celulas[metade:] + [('', '')] * (metade - len(celulas[metade:]))
    col = CONTENT_W / 2
    rows = [[a[0], a[1], '', b[0], b[1]] for a, b in zip(esq, dir_)]
    t = Table(rows, colWidths=[col - 16 * mm, 11 * mm, 10 * mm, col - 16 * mm, 11 * mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (1, -1), 0.5, RULE), ('LINEBELOW', (3, 0), (4, -1), 0.5, RULE),
    ]))
    return t


def _foto(foto, max_w, max_h):
    with foto.imagem.open('rb') as f:
        img = ImageOps.exif_transpose(PILImage.open(f)).convert('RGB')
    img.thumbnail((900, 900))
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=78)
    buf.seek(0)
    ratio = min(max_w / img.width, max_h / img.height)
    return Image(buf, width=img.width * ratio, height=img.height * ratio)


def _fotos(inspecao):
    fotos = sorted(inspecao.fotos.all(), key=lambda f: (FOTO_ORDEM.get(f.posicao, 999), f.pk))
    if not fotos:
        return []
    col = CONTENT_W / 3
    cells = []
    for foto in fotos:
        try:
            cells.append([_foto(foto, col - 5 * mm, 38 * mm), Paragraph(foto.titulo, _s['caption'])])
        except Exception:
            cells.append([Paragraph(f'{foto.titulo} (não foi possível carregar)', _s['caption'])])
    linhas = []
    for i in range(0, len(cells), 3):
        row = cells[i:i + 3] + [''] * (3 - len(cells[i:i + 3]))
        t = Table([row], colWidths=[col] * 3)
        t.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        linhas.append(t)
    return linhas


def _assinatura(inspecao):
    img = ''
    if inspecao.assinatura:
        try:
            with inspecao.assinatura.open('rb') as f:
                pil = PILImage.open(f)
                pil.load()
            bbox = pil.getbbox()
            if bbox:
                pil = pil.crop(bbox)
            buf = io.BytesIO()
            pil.save(buf, 'PNG')
            buf.seek(0)
            ratio = min(62 * mm / pil.width, 15 * mm / pil.height)
            img = Image(buf, width=pil.width * ratio, height=pil.height * ratio, mask='auto')
        except Exception:
            img = ''
    t = Table([[img], [Paragraph(f'{inspecao.motorista or "Condutor"}<br/><font color="#6b7480" size="7.5">Condutor</font>', _s['sig'])]],
              colWidths=[72 * mm], rowHeights=[17 * mm, None])
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, INK),
        ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    t.hAlign = 'LEFT'
    return t


class _NumberedCanvas(rl_canvas.Canvas):
    """Rodapé discreto com 'página X de N'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setStrokeColor(RULE)
            self.setLineWidth(0.6)
            self.line(MARGIN_X, 14 * mm, PAGE_W - MARGIN_X, 14 * mm)
            self.setFont('Mont', 6.5)
            self.setFillColor(MUTED)
            self.drawString(MARGIN_X, 10 * mm, RODAPE)
            self.drawRightString(PAGE_W - MARGIN_X, 6.5 * mm, f'{DOC_CODE} · rev. {DOC_REVISAO} · página {self._pageNumber} de {total}')
            super().showPage()
        super().save()


def render_inspecao_pdf(inspecao):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f'Comprovante de vistoria {inspecao.veiculo.placa} {inspecao.pk:05d}', author='Texas Controls',
    )
    story = [_cabecalho(inspecao), Spacer(1, 4 * mm), _status(inspecao)]
    story += _h2('Dados da vistoria') + [_dados(inspecao)]
    story += _h2('Checklist') + [_checklist(inspecao)]
    if inspecao.observacoes:
        story += [KeepTogether(_h2('Observações') + [Paragraph(inspecao.observacoes.replace('\n', '<br/>'), _s['body'])])]
    fotos = _fotos(inspecao)
    if fotos:
        story += [KeepTogether(_h2('Fotos') + fotos[:1])] + fotos[1:]
    story += [KeepTogether([Spacer(1, 9 * mm), _assinatura(inspecao)])]
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buf.getvalue()


def pdf_filename(inspecao):
    data = timezone.localtime(inspecao.created_at)
    return f'Comprovante_vistoria_{inspecao.veiculo.placa}_{data:%Y-%m-%d_%H%M}.pdf'
