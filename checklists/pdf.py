"""
PDF de uma execução no layout dos formulários TCB-OTB.

Reaproveita as peças do PDF de veículos (fontes, logo, rodapé, caixinhas, grade azul e amarela);
o cabeçalho vem da revisão do modelo: código, revisão, preparado por, revisado por e data,
exatamente como no formulário em papel.
"""
import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from veiculos import pdf as base

from .models import RESP_OK_NOK

_s = base._s
PAGE_W, PAGE_H = A4


def _caixa_alta(texto):
    """Títulos em caixa alta como no formulário, preservando siglas com minúscula (ex.: EPIs)."""
    return texto.upper().replace('EPIS', 'EPIs')


class _CanvasChecklist(base._NumberedCanvas):
    cab = None  # dict com titulo, codigo, revisao, preparado, revisado, data

    def _draw_header(self, total):
        cab = self.cab
        top = PAGE_H - 14 * mm
        logo = base.ASSETS / 'logo-texas.png'
        if logo.exists():
            self.drawImage(str(logo), base.MARGIN_X - 3 * mm, top - 32 * mm, width=40 * mm, height=34 * mm,
                           mask='auto', preserveAspectRatio=True)
        x0 = base.MARGIN_X + 62 * mm
        right = PAGE_W - base.MARGIN_X

        def rotulo(x, y, pt, en):
            self.setFillColor(base.TEXT)
            self.setFont('Mont', 7.5)
            self.drawString(x, y, pt)
            self.setFont('Mont-Italic', 7.5)
            self.drawString(x + self.stringWidth(pt, 'Mont', 7.5), y, en)

        rotulo(x0, top - 6 * mm, 'Título ', 'Title')
        # Títulos longos (ex.: bancada RAD 02,24,47 e 716) diminuem até caber na linha.
        tam = 9.5
        while tam > 6.5 and self.stringWidth(cab['titulo'], 'Mont-Bold', tam) > right - x0:
            tam -= 0.25
        self.setFont('Mont-Bold', tam)
        self.setFillColor(base.BLUE)
        self.drawString(x0, top - 12 * mm, cab['titulo'])
        self.setStrokeColor(base.YELLOW)
        self.setLineWidth(1.5)
        self.line(x0, top - 14.5 * mm, right, top - 14.5 * mm)

        cols = [x0, x0 + 46 * mm, x0 + 86 * mm]
        linhas = [
            [('Documento ', 'Document', cab['codigo']), ('Revisão ', 'Review', cab['revisao']), ('Página ', 'Pages', None)],
            [('Preparado por ', 'Prepared by', cab['preparado']), ('Revisado por ', 'Review by', cab['revisado']),
             ('Data ', 'Date', cab['data'])],
        ]
        y = top - 19 * mm
        for linha in linhas:
            for x, (pt, en, valor) in zip(cols, linha):
                rotulo(x, y, pt, en)
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
                    self.setFont('Mont', 7.5)
                    self.drawString(x, y - 3.3 * mm, (valor or '—')[:34])
            y -= 9 * mm
        self.setStrokeColor(base.YELLOW)
        self.line(base.MARGIN_X - 4 * mm, top - 37 * mm, right, top - 37 * mm)


def _info(execucao):
    a = execucao.ativo
    linhas = [
        ('IDENTIFICAÇÃO / N. SÉRIE:', a.identificacao),
        ('EQUIPAMENTO:', f'{a.nome} ({a.tipo.nome})'),
        ('MODELO:', a.modelo or '—'),
        ('MARCA:', a.marca or '—'),
    ]
    if a.patrimonio:
        linhas.append(('PATRIMÔNIO:', a.patrimonio))
    if execucao.medidor_label:
        linhas.append(('HORÍMETRO:' if a.tipo.medidor == 'horimetro' else 'KM NO PAINEL:', execucao.medidor_label))
    rows = [[Paragraph(k, _s['label']), Paragraph(str(v), _s['value'])] for k, v in linhas]
    t = Table(rows, colWidths=[56 * mm, base.CONTENT_W - 56 * mm])
    return base._yellow_grid(t, [('BACKGROUND', (0, 0), (0, -1), base.BLUE)])


def _assinatura(execucao):
    img = ''
    if execucao.assinatura:
        try:
            img = base._assinatura_img(execucao, 70 * mm, 17 * mm)
        except Exception:
            img = ''
    t = Table([[img], [Paragraph(execucao.executor_nome or '[NOME]', _s['sig'])], [Paragraph('TÉCNICO', _s['sig'])]],
              colWidths=[80 * mm], rowHeights=[19 * mm, None, None])
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'), ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 0.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 0.5),
    ]))
    wrapper = Table([['', t]], colWidths=[base.CONTENT_W - 80 * mm, 80 * mm])
    wrapper.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    return wrapper


def _secao(titulo, respostas):
    """Seção só com itens OK/NOK sai como no formulário (caixinhas); as demais, com a resposta escrita."""
    so_ok_nok = all(r.item.tipo_resposta == RESP_OK_NOK for r in respostas)
    if so_ok_nok:
        rows = [[Paragraph('Item', _s['th']), Paragraph('OK', _s['th']), Paragraph('NOK', _s['th'])]]
    else:
        rows = [[Paragraph('Item', _s['th']), Paragraph('Resposta', _s['th'])]]
    for r in respostas:
        texto = [Paragraph(r.item.texto + (' <font size=7 color="#777777">(não se aplica)</font>' if r.valor == 'na' and so_ok_nok else ''), _s['item'])]
        if r.observacao:
            texto.append(Paragraph(r.observacao, _s['obs']))
        if so_ok_nok:
            rows.append([texto, base.CheckBox(r.valor == 'ok'), base.CheckBox(r.valor == 'nok', color=base.RED)])
        else:
            cor = '#c0392b' if r.negativa else '#1f1f1f'
            rows.append([texto, Paragraph(f'<font color="{cor}"><b>{r.rotulo}</b></font>', _s['item'])])
    widths = [104 * mm, 16 * mm, 16 * mm] if so_ok_nok else [104 * mm, 32 * mm]
    t = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
    base._yellow_grid(t, [
        ('BACKGROUND', (0, 0), (-1, 0), base.BLUE),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, base.BLUE), ('BOX', (0, 0), (-1, 0), 1.2, base.BLUE),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, 0), 1.5), ('BOTTOMPADDING', (0, 0), (-1, 0), 2.5),
    ])
    return [Paragraph(_caixa_alta(titulo), _s['section']), Spacer(1, 4 * mm), t, Spacer(1, 7 * mm)]


def _observacoes(execucao):
    problemas = execucao.problemas
    partes = []
    if problemas:
        partes.append(f'<font color="#c0392b"><b>{len(problemas)} item(ns) com não conformidade:</b></font>')
        partes += [f'• <b>{r.item.texto}</b> {r.observacao}' for r in problemas]
    else:
        partes.append('<font color="#1e7a4a"><b>Todos os itens verificados estão conformes.</b></font>')
    if execucao.observacoes:
        partes.append('<br/>' + execucao.observacoes.replace('\n', '<br/>'))
    t = Table([[Paragraph('OBSERVAÇÕES', _s['label'])], [Paragraph('<br/>'.join(partes), _s['body'])]], colWidths=[base.CONTENT_W])
    return base._yellow_grid(t, [
        ('BACKGROUND', (0, 0), (-1, 0), base.BLUE),
        ('TOPPADDING', (0, 1), (-1, 1), 6), ('BOTTOMPADDING', (0, 1), (-1, 1), 10),
    ])


def _fotos(execucao):
    fotos = list(execucao.fotos.select_related('item'))
    if not fotos:
        return [Paragraph('<font color="#777777">Nenhuma foto registrada.</font>', _s['body'])]
    col_w = base.CONTENT_W / 2
    cells = []
    for foto in fotos:
        try:
            cells.append([base._foto_flowable(foto, col_w - 8 * mm, 62 * mm), Paragraph(foto.titulo, _s['caption'])])
        except Exception:
            cells.append([Paragraph(f'{foto.titulo} (não foi possível carregar)', _s['caption'])])
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


def render_execucao_pdf(execucao):
    rev = execucao.revisao
    modelo = rev.modelo
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=base.MARGIN_X, rightMargin=base.MARGIN_X,
        topMargin=base.HEADER_H + 9 * mm, bottomMargin=base.FOOTER_H,
        title=f'{modelo.codigo} {execucao.ativo.identificacao}', author='Texas Controls',
    )
    data = timezone.localtime(execucao.created_at)
    respostas = list(execucao.respostas.select_related('item__secao'))
    por_secao = {}
    for r in respostas:
        por_secao.setdefault((r.item.secao.ordem, r.item.secao_id, r.item.secao.titulo), []).append(r)

    story = [
        Paragraph(modelo.titulo.upper(), _s['title']), Spacer(1, 5 * mm),
        Paragraph('INFORMAÇÕES DO EQUIPAMENTO', _s['section']), Spacer(1, 4 * mm),
        Paragraph(f'<b>DATA:</b> {data:%d/%m/%Y} às {data:%H:%M}', _s['body']), Spacer(1, 3 * mm),
        _info(execucao), Spacer(1, 4 * mm), _assinatura(execucao), Spacer(1, 4 * mm),
    ]
    for (_, _, titulo), itens in sorted(por_secao.items()):
        story += _secao(titulo, itens)
    story += [
        KeepTogether([Paragraph('INFORMAÇÕES ADICIONAIS', _s['section']), Spacer(1, 4 * mm), _observacoes(execucao)]),
        Spacer(1, 9 * mm),
    ]
    fotos = _fotos(execucao)
    story += [KeepTogether([base._blue_bar('FOTOS DO EQUIPAMENTO', top_line=True), Spacer(1, 3 * mm), fotos[0]]), *fotos[1:]]

    cab = {
        'titulo': modelo.titulo.upper(), 'codigo': modelo.codigo, 'revisao': rev.rotulo,
        'preparado': rev.preparado_por, 'revisado': rev.revisado_por,
        'data': rev.data.strftime('%d/%m/%Y') if rev.data else '',
    }
    canvasmaker = type('CanvasExec', (_CanvasChecklist,), {'cab': cab})
    doc.build(story, canvasmaker=canvasmaker)
    return buf.getvalue()


def pdf_filename(execucao):
    data = timezone.localtime(execucao.created_at)
    ident = ''.join(c for c in execucao.ativo.identificacao if c.isalnum() or c in '-_') or 'equipamento'
    return f'{execucao.revisao.modelo.codigo}_{ident}_{data:%Y-%m-%d_%H%M}.pdf'
