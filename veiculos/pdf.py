"""Relatório em PDF de uma inspeção, no layout do formulário TCB-OTB-113 da empresa."""
import io
from pathlib import Path

from django.utils import timezone
from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    Flowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .models import CHECKLIST_ITEMS, FOTO_ORDEM, ITEM_NOK, ITEM_OK

ASSETS = Path(__file__).resolve().parent / 'assets'

# Controle do documento (cabeçalho). Ajuste quando o formulário receber número oficial.
DOC_TITULO = 'CHECKLIST DE INSPEÇÃO – VEÍCULO'
DOC_CODE = 'TCB-OTB-VEIC'
DOC_REVISAO = '00'

ENDERECO = 'BR-304 (KM. 11,5), Parque de Exposições, 675-Loja B, Parnamirim – RN, 59.146-750, Brasil'
TELEFONE = '+55 84 3643-2108'
EMAIL = 'office.brasil@texascontrols.com'
SITE = 'www.texascontrols.com'

BLUE = colors.HexColor('#365f91')
YELLOW = colors.HexColor('#ffc000')
TEXT = colors.HexColor('#1f1f1f')
RED = colors.HexColor('#c0392b')
PAGE_W, PAGE_H = A4
MARGIN_X = 21 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X
HEADER_H = 46 * mm
FOOTER_H = 26 * mm


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
    'title': ParagraphStyle('title', fontName='Mont-Bold', fontSize=17, leading=21, textColor=BLUE, alignment=TA_CENTER),
    'section': ParagraphStyle('section', fontName='Mont', fontSize=11, leading=14, textColor=BLUE),
    'body': ParagraphStyle('body', fontName='Mont', fontSize=9, leading=12, textColor=TEXT),
    'label': ParagraphStyle('label', fontName='Mont-Bold', fontSize=9, leading=11, textColor=colors.white),
    'value': ParagraphStyle('value', fontName='Mont', fontSize=9, leading=11, textColor=TEXT),
    'th': ParagraphStyle('th', fontName='Mont', fontSize=9.5, leading=11, textColor=colors.white, alignment=TA_CENTER),
    'item': ParagraphStyle('item', fontName='Mont', fontSize=9, leading=11, textColor=TEXT),
    'obs': ParagraphStyle('obs', fontName='Mont-Italic', fontSize=7.5, leading=9, textColor=RED),
    'sig': ParagraphStyle('sig', fontName='Mont', fontSize=9, leading=11, textColor=TEXT, alignment=TA_CENTER),
    'caption': ParagraphStyle('caption', fontName='Mont', fontSize=7, leading=9, textColor=colors.HexColor('#555555'), alignment=TA_CENTER),
    'right': ParagraphStyle('right', fontName='Mont', fontSize=8, leading=10, alignment=TA_RIGHT),
}


class CheckBox(Flowable):
    """Caixinha ☐ do formulário; marcada com um X quando `checked`."""

    def __init__(self, checked, color=TEXT, size=3.4 * mm):
        super().__init__()
        self.checked, self.color, self.size = checked, color, size
        self.width = self.height = size

    def draw(self):
        c = self.canv
        c.setStrokeColor(TEXT)
        c.setLineWidth(0.7)
        c.rect(0, 0, self.size, self.size)
        if self.checked:
            c.setStrokeColor(self.color)
            c.setLineWidth(1.3)
            p = self.size * 0.2
            c.line(p, p, self.size - p, self.size - p)
            c.line(p, self.size - p, self.size - p, p)


def _yellow_grid(t, extra=()):
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.2, YELLOW),
        ('INNERGRID', (0, 0), (-1, -1), 1.2, YELLOW),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        *extra,
    ]))
    return t


def _blue_bar(text, top_line=False):
    t = Table([[Paragraph(text, _s['label'])]], colWidths=[CONTENT_W])
    style = [
        ('BACKGROUND', (0, 0), (-1, -1), BLUE),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if top_line:
        style.append(('LINEABOVE', (0, 0), (-1, 0), 1.5, YELLOW))
    t.setStyle(TableStyle(style))
    return t


def _info_block(inspecao):
    v = inspecao.veiculo
    linhas = [
        ('PLACA:', v.placa),
        ('MARCA / MODELO:', f'{v.marca} {v.modelo} ({v.get_categoria_display().lower()})'),
        ('ANO / COR:', ' · '.join(str(x) for x in [v.ano, v.cor] if x) or '—'),
        ('KM NO PAINEL:', f'{inspecao.km:,}'.replace(',', '.') + ' km'),
        ('TIPO DE INSPEÇÃO:', inspecao.get_tipo_display()),
        ('COMBUSTÍVEL:', inspecao.combustivel_label),
    ]
    pneus = inspecao.pneus
    if pneus:
        linhas.append(('ESTADO DOS PNEUS:', '   '.join(
            f'{sigla} {pct}%' if pct is not None else f'{sigla} —' for sigla, _, pct in pneus
        )))
    if inspecao.com_carga is not None:
        linhas.append(('LEVA CARGA:', inspecao.carga_label))
    elif inspecao.destino:
        linhas.append(('DESTINO / MOTIVO:', inspecao.destino))
    rows = [[Paragraph(a, _s['label']), Paragraph(str(b), _s['value'])] for a, b in linhas]
    t = Table(rows, colWidths=[56 * mm, CONTENT_W - 56 * mm])
    return _yellow_grid(t, [('BACKGROUND', (0, 0), (0, -1), BLUE)])


def _assinatura_img(inspecao, max_w, max_h):
    if not inspecao.assinatura:
        return ''
    try:
        with inspecao.assinatura.open('rb') as f:
            img = PILImage.open(f)
            img.load()
        bbox = img.getbbox()  # recorta o espaço em branco em volta do traço
        if bbox:
            img = img.crop(bbox)
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        ratio = min(max_w / img.width, max_h / img.height)
        return Image(buf, width=img.width * ratio, height=img.height * ratio, mask='auto')
    except Exception:
        return ''


def _assinatura(inspecao):
    nome = str(inspecao.motorista) if inspecao.motorista else '[NOME]'
    t = Table([
        [_assinatura_img(inspecao, 70 * mm, 17 * mm)],
        [Paragraph(nome, _s['sig'])],
        [Paragraph('MOTORISTA', _s['sig'])],
    ], colWidths=[80 * mm], rowHeights=[19 * mm, None, None])
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'), ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 0.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 0.5),
    ]))
    wrapper = Table([['', t]], colWidths=[CONTENT_W - 80 * mm, 80 * mm])
    wrapper.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    return wrapper


def _verificacao_block(inspecao):
    por_item = {i.item: i for i in inspecao.itens.all()}
    rows = [[Paragraph('Item', _s['th']), Paragraph('OK', _s['th']), Paragraph('NOK', _s['th'])]]
    for _, itens in CHECKLIST_ITEMS:
        for key, label in itens:
            it = por_item.get(key)
            status = it.status if it else None
            texto = [Paragraph(label + ('' if status in (ITEM_OK, ITEM_NOK) else ' <font size=7 color="#777777">(não se aplica)</font>'), _s['item'])]
            rows.append([texto, CheckBox(status == ITEM_OK), CheckBox(status == ITEM_NOK, color=RED)])
    item_w = 104 * mm
    t = Table(rows, colWidths=[item_w, 16 * mm, 16 * mm], repeatRows=1, hAlign='LEFT')
    return _yellow_grid(t, [
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, BLUE), ('BOX', (0, 0), (-1, 0), 1.2, BLUE),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, 0), 1.5), ('BOTTOMPADDING', (0, 0), (-1, 0), 2.5),
    ])


def _observacoes_block(inspecao):
    problemas = inspecao.itens_problema
    partes = []
    if problemas:
        partes.append(f'<font color="#c0392b"><b>REPROVADO – {len(problemas)} item(ns) com problema:</b></font>')
        partes += [f'• <b>{p.label}:</b> {p.observacao}' for p in problemas]
    else:
        partes.append('<font color="#1e7a4a"><b>APROVADO – todos os itens verificados estão OK.</b></font>')
    outras = [i for i in inspecao.itens.all() if i.observacao and i not in problemas]
    partes += [f'• <b>{i.label}:</b> {i.observacao}' for i in outras]
    if inspecao.observacoes:
        partes.append('<br/>' + inspecao.observacoes.replace('\n', '<br/>'))
    t = Table([[Paragraph('OBSERVAÇÕES', _s['label'])], [Paragraph('<br/>'.join(partes), _s['body'])]], colWidths=[CONTENT_W])
    return _yellow_grid(t, [
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TOPPADDING', (0, 1), (-1, 1), 6), ('BOTTOMPADDING', (0, 1), (-1, 1), 10),
    ])


def _foto_flowable(foto, max_w, max_h):
    with foto.imagem.open('rb') as f:
        img = ImageOps.exif_transpose(PILImage.open(f)).convert('RGB')
    img.thumbnail((1200, 1200))
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=80)
    buf.seek(0)
    ratio = min(max_w / img.width, max_h / img.height)
    return Image(buf, width=img.width * ratio, height=img.height * ratio)


def _fotos_block(inspecao):
    # Primeiro as fotos guiadas (na ordem das posições), depois as adicionais.
    fotos = sorted(inspecao.fotos.all(), key=lambda f: (FOTO_ORDEM.get(f.posicao, 999), f.pk))
    if not fotos:
        return [Paragraph('<font color="#777777">Nenhuma foto registrada.</font>', _s['body'])]
    col_w = CONTENT_W / 2
    cells = []
    for n, foto in enumerate(fotos, start=1):
        try:
            cells.append([_foto_flowable(foto, col_w - 8 * mm, 62 * mm), Paragraph(foto.titulo, _s['caption'])])
        except Exception:
            cells.append([Paragraph(f'Foto {n} (não foi possível carregar)', _s['caption'])])
    # Uma tabela por linha de fotos, para a quebra de página acontecer entre as linhas.
    linhas = []
    for i in range(0, len(cells), 2):
        row = cells[i:i + 2] + [''] * (2 - len(cells[i:i + 2]))
        t = Table([row], colWidths=[col_w, col_w])
        t.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        linhas.append(t)
    return linhas


class _NumberedCanvas(rl_canvas.Canvas):
    """Desenha cabeçalho e rodapé depois de saber o total de páginas ("1 de N")."""

    inspecao = None

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
            self._draw_header(total)
            self._draw_footer()
            super().showPage()
        super().save()

    def _draw_header(self, total):
        insp = self.inspecao
        top = PAGE_H - 14 * mm
        logo = ASSETS / 'logo-texas.png'
        if logo.exists():
            self.drawImage(str(logo), MARGIN_X - 3 * mm, top - 32 * mm, width=40 * mm, height=34 * mm, mask='auto', preserveAspectRatio=True)
        x0 = MARGIN_X + 62 * mm
        right = PAGE_W - MARGIN_X
        self.setFillColor(TEXT)
        self.setFont('Mont', 7.5)
        self.drawString(x0, top - 6 * mm, 'Título ')
        self.setFont('Mont-Italic', 7.5)
        self.drawString(x0 + self.stringWidth('Título ', 'Mont', 7.5), top - 6 * mm, 'Title')
        self.setFont('Mont-Bold', 9.5)
        self.setFillColor(BLUE)
        self.drawString(x0, top - 12 * mm, DOC_TITULO)
        self.setStrokeColor(YELLOW)
        self.setLineWidth(1.5)
        self.line(x0, top - 14.5 * mm, right, top - 14.5 * mm)

        data = timezone.localtime(insp.created_at)
        cols = [x0, x0 + 46 * mm, x0 + 86 * mm]
        linhas = [
            [('Documento ', 'Document', DOC_CODE), ('Revisão ', 'Review', DOC_REVISAO), ('Página ', 'Pages', None)],
            [('Preparado por ', 'Prepared by', str(insp.created_by or '—')), ('Inspeção nº ', 'Number', f'{insp.pk:05d}'),
             ('Data ', 'Date', f'{data:%d/%m/%Y}')],
        ]
        y = top - 19 * mm
        for linha in linhas:
            for x, (pt, en, valor) in zip(cols, linha):
                self.setFillColor(TEXT)
                self.setFont('Mont', 7.5)
                self.drawString(x, y, pt)
                self.setFont('Mont-Italic', 7.5)
                self.drawString(x + self.stringWidth(pt, 'Mont', 7.5), y, en)
                self.setFont('Mont', 7.5)
                if valor is None:
                    pag = str(self._pageNumber)
                    self.setFont('Mont-Bold', 7.5)
                    self.drawString(x, y - 3.3 * mm, pag)
                    w = self.stringWidth(pag, 'Mont-Bold', 7.5)
                    self.setFont('Mont', 7.5)
                    self.drawString(x + w, y - 3.3 * mm, ' de ')
                    w += self.stringWidth(' de ', 'Mont', 7.5)
                    self.setFont('Mont-Bold', 7.5)
                    self.drawString(x + w, y - 3.3 * mm, str(total))
                else:
                    self.drawString(x, y - 3.3 * mm, valor[:34])
            y -= 9 * mm
        self.setStrokeColor(YELLOW)
        self.line(MARGIN_X - 4 * mm, top - 37 * mm, right, top - 37 * mm)

    def _draw_footer(self):
        y = 18 * mm
        self.setStrokeColor(YELLOW)
        self.setLineWidth(1.5)
        self.line(MARGIN_X, y, PAGE_W - MARGIN_X, y)
        self.setFillColor(TEXT)
        self.setFont('Mont', 6)

        def item(icon, text, x, yy):
            path = ASSETS / icon
            if path.exists():
                self.drawImage(str(path), x, yy - 1 * mm, width=4 * mm, height=4 * mm, mask='auto')
            self.drawString(x + 5.5 * mm, yy, text)
            return x + 5.5 * mm + self.stringWidth(text, 'Mont', 6)

        w1 = 5.5 * mm + self.stringWidth(ENDERECO, 'Mont', 6) + 8 * mm + 5.5 * mm + self.stringWidth(TELEFONE, 'Mont', 6)
        x = (PAGE_W - w1) / 2
        x = item('icon-local.png', ENDERECO, x, y - 6 * mm)
        item('icon-fone.png', TELEFONE, x + 8 * mm, y - 6 * mm)
        w2 = 5.5 * mm + self.stringWidth(EMAIL, 'Mont', 6) + 10 * mm + 5.5 * mm + self.stringWidth(SITE, 'Mont', 6)
        x = (PAGE_W - w2) / 2
        x = item('icon-email.png', EMAIL, x, y - 13 * mm)
        item('icon-web.png', SITE, x + 10 * mm, y - 13 * mm)


def render_inspecao_pdf(inspecao):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=HEADER_H + 9 * mm, bottomMargin=FOOTER_H,
        title=f'Checklist {inspecao.veiculo.placa} {inspecao.pk:05d}', author='Polaris · Texas Controls',
    )
    data = timezone.localtime(inspecao.created_at)
    story = [
        Paragraph('CHECKLIST DE INSPEÇÃO VEICULAR', _s['title']), Spacer(1, 5 * mm),
        Paragraph('INFORMAÇÕES DO VEÍCULO', _s['section']), Spacer(1, 4 * mm),
        Paragraph(f'<b>DATA:</b> {data:%d/%m/%Y} às {data:%H:%M}', _s['body']), Spacer(1, 3 * mm),
        _info_block(inspecao), Spacer(1, 4 * mm),
        _assinatura(inspecao), Spacer(1, 2 * mm),
        Paragraph('VERIFICAÇÃO DO VEÍCULO', _s['section']), Spacer(1, 4 * mm),
        _verificacao_block(inspecao), Spacer(1, 7 * mm),
        KeepTogether([Paragraph('INFORMAÇÕES ADICIONAIS', _s['section']), Spacer(1, 4 * mm), _observacoes_block(inspecao)]),
        Spacer(1, 9 * mm),
    ]
    fotos = _fotos_block(inspecao)
    story += [
        KeepTogether([_blue_bar('FOTOS DO VEÍCULO', top_line=True), Spacer(1, 3 * mm), fotos[0]]),
        *fotos[1:],
    ]
    canvasmaker = type('InspCanvas', (_NumberedCanvas,), {'inspecao': inspecao})
    doc.build(story, canvasmaker=canvasmaker)
    return buf.getvalue()


def pdf_filename(inspecao):
    data = timezone.localtime(inspecao.created_at)
    return f'Comprovante_vistoria_{inspecao.veiculo.placa}_{data:%Y-%m-%d_%H%M}.pdf'
