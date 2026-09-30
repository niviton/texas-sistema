import io

import qrcode
from django.conf import settings as django_settings
from PIL import Image, ImageDraw, ImageFont

from .models import CertificateSettings, Professor

BG_PATH = django_settings.BASE_DIR / 'static' / 'assets' / 'certificado-fundo.png'
CANVAS_SIZE = (1340, 947)

_COLOR_DARK = (58, 58, 58)
_COLOR_GRAY = (122, 122, 122)

_FONT_CANDIDATES = {
    'regular': ['arial.ttf', 'DejaVuSans.ttf'],
    'bold': ['arialbd.ttf', 'DejaVuSans-Bold.ttf'],
    'italic': ['ariali.ttf', 'DejaVuSans-Oblique.ttf'],
    'bold_italic': ['arialbi.ttf', 'DejaVuSans-BoldOblique.ttf'],
}


def _font(style, size):
    for name in _FONT_CANDIDATES[style]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _build_qr(data, size):
    qr = qrcode.QRCode(border=1, box_size=6, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#0d2440', back_color='white').convert('RGBA')
    return img.resize((size, size))


def _paste_signature(canvas, professor, box):
    if not professor or not professor.signature:
        return
    left, top, width, height = box
    try:
        sig = Image.open(professor.signature.path).convert('RGBA')
    except (FileNotFoundError, ValueError):
        return
    sig.thumbnail((width, height - 4), Image.LANCZOS)
    x = left + (width - sig.width) // 2
    y = top + (height - sig.height) - 4
    canvas.paste(sig, (x, y), sig)


def _compose_certificate_image(certificate, verify_url=None):
    canvas = Image.open(BG_PATH).convert('RGBA')
    assert canvas.size == CANVAS_SIZE
    draw = ImageDraw.Draw(canvas)
    settings_obj = CertificateSettings.load()

    draw.text((108, 150), 'Participação e conclusão bem-sucedida', font=_font('italic', 17), fill=_COLOR_DARK)
    draw.text((95, 255), certificate.student_name, font=_font('bold', 26), fill=_COLOR_DARK)
    cpf_display = certificate.cpf
    if len(cpf_display) == 11:
        cpf_display = f'{cpf_display[:3]}.{cpf_display[3:6]}.{cpf_display[6:9]}-{cpf_display[9:]}'
    draw.text((95, 350), cpf_display, font=_font('regular', 19), fill=_COLOR_DARK)

    draw.text((108, 430), 'Conteúdo:', font=_font('bold_italic', 15), fill=_COLOR_DARK)
    course_title = certificate.course_title
    items = certificate.course_template.syllabus_list if certificate.course_template else [course_title]
    y = 456
    item_font = _font('regular', 14)
    for item in items:
        wrapped = _wrap_text(draw, item, item_font, 478 - 20)
        for i, line in enumerate(wrapped):
            prefix = '• ' if i == 0 else '  '
            draw.text((108, y), f'{prefix}{line}', font=item_font, fill=_COLOR_DARK)
            y += 25
        if y > 780:
            break

    footer = (
        '*Válido por três anos a partir da emissão.\n'
        'Verifique em texascontrols.com/verificacao-certificados\n'
        f'com o código {certificate.code}.'
    )
    footer_font = _font('regular', 11)
    fy = 800
    for line in footer.split('\n'):
        draw.text((172, fy), line, font=footer_font, fill=_COLOR_DARK)
        fy += 17

    title_font_label = _font('italic', 21)
    title_font_course = _font('bold', 23)
    center_x = 749 + 582 // 2
    label = 'Formação'
    lw = draw.textlength(label, font=title_font_label)
    draw.text((center_x - lw / 2, 253), label, font=title_font_label, fill=_COLOR_GRAY)
    course_lines = _wrap_text(draw, course_title, title_font_course, 560)
    ty = 290
    for line in course_lines[:3]:
        lw = draw.textlength(line, font=title_font_course)
        draw.text((center_x - lw / 2, ty), line, font=title_font_course, fill=_COLOR_DARK)
        ty += 30

    label_font = _font('regular', 15)
    value_font = _font('bold', 15)
    rows = [
        ('DATA', certificate.course_date.strftime('%d/%m/%Y')),
        ('DURAÇÃO', certificate.duration),
        ('DATA DE EMISSÃO', certificate.issue_date.strftime('%d/%m/%Y')),
        ('CERTIFICADO', certificate.code),
    ]
    ry = 478
    for label_text, value_text in rows:
        draw.text((749, ry), label_text, font=label_font, fill=_COLOR_GRAY)
        draw.text((749 + 145, ry), value_text, font=value_font, fill=_COLOR_DARK)
        ry += 30

    if settings_obj.show_qr_code and verify_url:
        qr_img = _build_qr(verify_url, 100)
        canvas.paste(qr_img, (749, 615), qr_img)

    _paste_signature(canvas, certificate.professor, (784, 761, 185, 110))
    if certificate.professor:
        name_font = _font('bold', 13)
        nw = draw.textlength(certificate.professor.full_name, font=name_font)
        draw.text((784 + 92 - nw / 2, 861), certificate.professor.full_name, font=name_font, fill=_COLOR_DARK)

    chefe = Professor.chief_for(certificate.cert_type)
    if chefe:
        _paste_signature(canvas, chefe, (1035, 759, 235, 110))
        name_font2 = _font('bold', 14)
        nw2 = draw.textlength(chefe.full_name, font=name_font2)
        draw.text((1035 + 117 - nw2 / 2, 859), chefe.full_name, font=name_font2, fill=_COLOR_DARK)

    return canvas


def render_certificate(certificate, verify_url=None):
    """Compose a certificate PDF for the given Certificate instance. Returns a BytesIO.

    Uses the course template's Word (.docx) file via mail-merge + LibreOffice conversion
    when one is attached; falls back to the Pillow/PNG-background renderer otherwise.
    """
    from . import word_merge

    if word_merge.has_word_template(certificate):
        return io.BytesIO(word_merge.render_certificate_word(certificate, fmt='pdf'))

    canvas = _compose_certificate_image(certificate, verify_url=verify_url)
    buffer = io.BytesIO()
    canvas.convert('RGB').save(buffer, format='PDF')
    buffer.seek(0)
    return buffer


def render_certificate_png(certificate, verify_url=None):
    """Compose the certificate as a PNG (used for on-screen previews). Returns a BytesIO."""
    from . import word_merge

    if word_merge.has_word_template(certificate):
        return io.BytesIO(word_merge.render_certificate_word(certificate, fmt='png'))

    canvas = _compose_certificate_image(certificate, verify_url=verify_url)
    buffer = io.BytesIO()
    canvas.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
