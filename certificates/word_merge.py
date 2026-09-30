import io
import posixpath
import re
import subprocess
import tempfile
import unicodedata
import zipfile
from pathlib import Path

from django.conf import settings
from docxtpl import DocxTemplate
from lxml import etree
from PIL import Image

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{%s}' % W_NS
A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
A = '{%s}' % A_NS
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
R = '{%s}' % R_NS
WP_NS = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
WP = '{%s}' % WP_NS
PIC_NS = 'http://schemas.openxmlformats.org/drawingml/2006/picture'
PIC = '{%s}' % PIC_NS
MC_NS = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
MC = '{%s}' % MC_NS
PKG_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

_FIELDNAME_RE = re.compile(r'MERGEFIELD\s+([^\\\s]+)')
_XML_PARTS_WITH_FIELDS = re.compile(r'^word/(document|header\d*|footer\d*)\.xml$')
_NAME_PLACEHOLDER_TEXT = '<Nome>'
_SIGNATURE_GAP_EMU = 40000
_RASTER_DPI = 150

_FIELD_SYNONYMS = {
    'NOME': 'NOME',
    'CPF': 'CPF',
    'IDENTIFICACAO': 'CPF',
    'DATA': 'DATA',
    'DURACAO': 'DURACAO',
    'DATA_EMISSAO': 'DATA_EMISSAO',
    'DATA_DE_EMISSAO': 'DATA_EMISSAO',
    'CERTIFICADO': 'CERTIFICADO',
    'CODIGO': 'CERTIFICADO',
    'INSTRUTOR_NOME': 'INSTRUTOR_NOME',
    'INSTRUTOR_CHEFE_NOME': 'INSTRUTOR_CHEFE_NOME',
}


def _strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')


def _normalize_field_name(raw_name):
    key = _strip_accents(raw_name).upper().replace(' ', '_').strip('_')
    return _FIELD_SYNONYMS.get(key, key)


def _strip_theme_colors(root):
    """Removes w:themeColor/w:themeShade/w:themeTint from every w:color element that also
    has an explicit w:val, leaving just the literal RGB value. Word-compliant renderers are
    supposed to prefer the theme-resolved color over w:val when both are present; LibreOffice
    resolves some theme+shade combinations differently than Word (producing a washed-out
    result for at least the 'Formação' label, and potentially others), so pinning every run
    to its explicit fallback color keeps the certificate visually consistent regardless of
    which engine renders it. Returns True if anything changed."""
    changed = False
    for color_el in root.iter(W + 'color'):
        if color_el.get(W + 'val') is None:
            continue
        for attr in ('themeColor', 'themeShade', 'themeTint'):
            if color_el.get(W + attr) is not None:
                del color_el.attrib[W + attr]
                changed = True
    return changed


def _convert_mergefields_to_jinja(root):
    """Rewrites real Word MERGEFIELD complex-field codes («NOME», «CPF», ...) into plain
    docxtpl/Jinja placeholders ({{ NOME }}, {{ CPF }}, ...), mutating `root` in place.
    Returns True if anything changed. Files that already use {{ }} placeholders are left
    untouched (there's nothing for this to match)."""
    all_runs = list(root.iter(W + 'r'))
    i = 0
    changed = False
    while i < len(all_runs):
        run = all_runs[i]
        fldchar = run.find(W + 'fldChar')
        if fldchar is None or fldchar.get(W + 'fldCharType') != 'begin':
            i += 1
            continue

        group = [run]
        field_name = None
        j = i + 1
        end_found = False
        while j < len(all_runs):
            r2 = all_runs[j]
            group.append(r2)
            instr = r2.find(W + 'instrText')
            if instr is not None and instr.text:
                m = _FIELDNAME_RE.search(instr.text)
                if m:
                    field_name = m.group(1)
            fc2 = r2.find(W + 'fldChar')
            if fc2 is not None and fc2.get(W + 'fldCharType') == 'end':
                end_found = True
                break
            j += 1

        if not end_found:
            i += 1
            continue

        if field_name:
            canonical = _normalize_field_name(field_name)
            rpr = run.find(W + 'rPr')
            new_run = etree.Element(W + 'r')
            if rpr is not None:
                new_run.append(etree.fromstring(etree.tostring(rpr)))
            t = etree.SubElement(new_run, W + 't')
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            t.text = '{{ ' + canonical + ' }}'
            run.addprevious(new_run)
            for r in group:
                r.getparent().remove(r)
            changed = True

        i = j + 1

    return changed


def _fit_signature_png(sig_bytes, target_size):
    """Letterboxes the signature onto a transparent canvas matching the target aspect
    ratio, so Word's stretch-to-frame doesn't distort it."""
    target_w, target_h = target_size
    sig = Image.open(io.BytesIO(sig_bytes)).convert('RGBA')
    scale = min(target_w / sig.width, target_h / sig.height)
    new_size = (max(1, int(sig.width * scale)), max(1, int(sig.height * scale)))
    sig_resized = sig.resize(new_size, Image.LANCZOS)
    canvas = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
    canvas.paste(sig_resized, ((target_w - new_size[0]) // 2, (target_h - new_size[1]) // 2), sig_resized)
    buffer = io.BytesIO()
    canvas.save(buffer, format='PNG')
    return buffer.getvalue()


def _find_body_picture_blips(root):
    """`<a:blip>` elements for pictures in the document body, in document order."""
    return [blip for blip in root.iter(A + 'blip') if blip.get(R + 'embed')]


def _shift_anchor_position(blip, offset_x, offset_y):
    """Nudges the floating picture hosting `blip` by (offset_x, offset_y) EMU, in place."""
    if not offset_x and not offset_y:
        return
    anchor = None
    for ancestor in blip.iterancestors():
        if ancestor.tag == WP + 'anchor':
            anchor = ancestor
            break
    if anchor is None:
        return
    pos_h_el = anchor.find(f'{WP}positionH/{WP}posOffset')
    if offset_x and pos_h_el is not None and pos_h_el.text is not None:
        pos_h_el.text = str(int(pos_h_el.text) + offset_x)
    pos_v_el = anchor.find(f'{WP}positionV/{WP}posOffset')
    if offset_y and pos_v_el is not None and pos_v_el.text is not None:
        pos_v_el.text = str(int(pos_v_el.text) + offset_y)


def _rels_path_for(part_name):
    directory, _, filename = part_name.rpartition('/')
    prefix = f'{directory}/' if directory else ''
    return f'{prefix}_rels/{filename}.rels'


def _load_image_targets(zin, part_name):
    """Maps relationship id -> media file path (e.g. 'rId11' -> 'word/media/image1.png')
    for image relationships of the given part."""
    rels_path = _rels_path_for(part_name)
    if rels_path not in zin.namelist():
        return {}
    rels_root = etree.fromstring(zin.read(rels_path))
    directory = part_name.rsplit('/', 1)[0]
    targets = {}
    for rel in rels_root:
        if rel.get('Type', '').endswith('/image'):
            targets[rel.get('Id')] = posixpath.normpath(f"{directory}/{rel.get('Target')}")
    return targets


def _signature_bytes(professor):
    if not professor or not professor.signature:
        return None
    try:
        with open(professor.signature.path, 'rb') as f:
            return f.read()
    except (FileNotFoundError, ValueError):
        return None


def _resolve_chefe(certificate):
    from .models import Professor
    return Professor.chief_for(certificate.cert_type)


def _swap_body_signatures(root, media_cache, zin, document_part, certificate):
    """Replaces the 1st body picture with the certificate's instructor signature and the
    2nd body picture with the resolved chefe (Interno/Externo) signature, preserving each
    picture's original aspect ratio. Missing signatures / missing 2nd picture are no-ops —
    templates that don't have a swappable slot yet keep whatever image they already had."""
    blips = _find_body_picture_blips(root)
    if not blips:
        return

    image_targets = _load_image_targets(zin, document_part)
    slot_professors = [certificate.professor, _resolve_chefe(certificate)]
    slots = [_signature_bytes(professor) for professor in slot_professors]

    for blip, new_sig_bytes, professor in zip(blips, slots, slot_professors):
        if not new_sig_bytes:
            continue
        media_path = image_targets.get(blip.get(R + 'embed'))
        if not media_path or media_path not in zin.namelist():
            continue
        original = Image.open(io.BytesIO(zin.read(media_path)))
        media_cache[media_path] = _fit_signature_png(new_sig_bytes, original.size)
        _shift_anchor_position(
            blip,
            professor.signature_offset_x_pt * 12700,
            professor.signature_offset_y_pt * 12700,
        )


_NAME_BASE_CHARS = 17  # roughly how many chars fit on one line at the box's original width


def _widen_box_for_name(anchor, name_text, base_width):
    """Widens the placeholder's text box (symmetrically, re-centered on the same point)
    so a long name stays on one line at the template's own font size, instead of shrinking
    the text or letting it wrap into the label below."""
    if anchor is None or len(name_text) <= _NAME_BASE_CHARS:
        return
    new_width = round(base_width * len(name_text) / _NAME_BASE_CHARS)
    delta = new_width - base_width

    extent = anchor.find(f'{WP}extent')
    if extent is not None:
        extent.set('cx', str(new_width))
    shape_ext = anchor.find(f'.//{A}xfrm/{A}ext')
    if shape_ext is not None:
        shape_ext.set('cx', str(new_width))
    pos_h_el = anchor.find(f'{WP}positionH/{WP}posOffset')
    if pos_h_el is not None:
        pos_h_el.text = str(int(pos_h_el.text) - delta // 2)


def _in_choice_not_fallback(element):
    """True if `element` sits inside an mc:Choice branch (not an mc:Fallback) — used to
    avoid double-processing the same logical shape's legacy VML fallback copy."""
    for ancestor in element.iterancestors():
        if ancestor.tag == MC + 'Fallback':
            return False
        if ancestor.tag == MC + 'Choice':
            return True
    return False


def _find_name_placeholder_slots(root):
    """Finds the manually-typed '<Nome>' placeholders left in a signature-area text box,
    classifying each as 'left' (instructor) or 'right' (chefe) by horizontal position.
    Returns a list of dicts: paragraph (hosting body paragraph — its whole subtree,
    including any legacy VML fallback copy, gets the text substitution), pos_h, pos_v,
    width, height (all EMU, from the Choice branch's own anchor)."""
    slots = []
    seen_hosts = set()
    for t in root.iter(W + 't'):
        if t.text != _NAME_PLACEHOLDER_TEXT or not _in_choice_not_fallback(t):
            continue
        node = t
        host_run = None
        while node is not None:
            node = node.getparent()
            if node is None:
                break
            if (
                node.tag == W + 'r' and node.getparent() is not None
                and node.getparent().tag == W + 'p' and node.find(MC + 'AlternateContent') is not None
            ):
                host_run = node
                break
        if host_run is None or id(host_run) in seen_hosts:
            continue
        anchor = host_run.find(f'.//{WP}anchor')
        if anchor is None:
            continue
        pos_h_el = anchor.find(f'{WP}positionH/{WP}posOffset')
        pos_v_el = anchor.find(f'{WP}positionV/{WP}posOffset')
        ext = anchor.find(f'{WP}extent')
        if pos_h_el is None or pos_v_el is None or ext is None:
            continue
        seen_hosts.add(id(host_run))
        slots.append({
            'paragraph': host_run.getparent(),
            'host_run': host_run,
            'anchor': anchor,
            'pos_h': int(pos_h_el.text),
            'pos_v': int(pos_v_el.text),
            'width': int(ext.get('cx')),
            'height': int(ext.get('cy')),
        })

    slots.sort(key=lambda s: s['pos_h'])
    for i, slot in enumerate(slots):
        slot['side'] = 'left' if i == 0 else 'right'
    return slots


def _build_signature_picture_xml(rid, pos_h, pos_v, width, height, doc_id):
    xml = (
        f'<w:r xmlns:w="{W_NS}"><w:rPr><w:noProof/></w:rPr>'
        f'<w:drawing xmlns:wp="{WP_NS}">'
        f'<wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" '
        f'relativeHeight="{doc_id}" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
        f'<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="margin"><wp:posOffset>{pos_h}</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>{pos_v}</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{width}" cy="{height}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
        f'<wp:docPr id="{doc_id}" name="Assinatura {doc_id}"/>'
        f'<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="{A_NS}" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
        f'<a:graphic xmlns:a="{A_NS}"><a:graphicData uri="{PIC_NS}">'
        f'<pic:pic xmlns:pic="{PIC_NS}">'
        f'<pic:nvPicPr><pic:cNvPr id="{doc_id}" name="Imagem {doc_id}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip xmlns:r="{R_NS}" r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width}" cy="{height}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        f'</pic:pic></a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>'
    )
    return etree.fromstring(xml.encode('utf-8'))


def _next_relationship_id(rels_root):
    max_num = 0
    for rel in rels_root:
        rid = rel.get('Id', '')
        if rid.startswith('rId') and rid[3:].isdigit():
            max_num = max(max_num, int(rid[3:]))
    return f'rId{max_num + 1}'


def _insert_placeholder_signatures(root, certificate, pending_media):
    """Fills in manually-typed '<Nome>' placeholders (real name text) and inserts a
    signature picture above each, for templates where the admin removed the old static
    signature entirely rather than leaving a swappable picture behind. `pending_media` is
    a list this appends (filename, png_bytes) tuples to. Returns the list of slots that
    need a new picture + relationship wired in by the caller (each with 'paragraph',
    'picture_filename', 'picture_xml_args') — lxml Elements don't support arbitrary custom
    attributes, so this can't just be stashed on `root`."""
    slots = _find_name_placeholder_slots(root)
    if not slots:
        return []

    from .models import CertificateSettings
    settings_obj = CertificateSettings.load()
    width_emu = settings_obj.signature_width_pt * 12700
    height_emu = settings_obj.signature_height_pt * 12700
    width_px = max(1, round(settings_obj.signature_width_pt / 72 * _RASTER_DPI))
    height_px = max(1, round(settings_obj.signature_height_pt / 72 * _RASTER_DPI))

    chefe = _resolve_chefe(certificate)
    pending_slots = []
    for index, slot in enumerate(slots):
        if slot['side'] == 'left':
            person, placeholder = certificate.professor, '{{ INSTRUTOR_NOME }}'
        else:
            person, placeholder = chefe, '{{ INSTRUTOR_CHEFE_NOME }}'

        name_text = person.full_name if person else ''
        _widen_box_for_name(slot['anchor'], name_text, slot['width'])
        for t in slot['host_run'].iter(W + 't'):
            if t.text == _NAME_PLACEHOLDER_TEXT:
                t.text = placeholder

        sig_bytes = _signature_bytes(person)
        if not sig_bytes or not person:
            continue

        png_bytes = _fit_signature_png(sig_bytes, (width_px, height_px))
        filename = f'generated_signature_{slot["side"]}_{certificate.pk or "preview"}_{index}.png'
        pending_media.append((filename, png_bytes))

        pos_h = slot['pos_h'] + (slot['width'] - width_emu) // 2 + person.signature_offset_x_pt * 12700
        pos_v = (
            slot['pos_v'] - height_emu - _SIGNATURE_GAP_EMU
            + person.signature_offset_y_pt * 12700
        )
        doc_id = 900000000 + index
        pending_slots.append({
            'paragraph': slot['paragraph'],
            'picture_filename': filename,
            'picture_xml_args': (pos_h, pos_v, width_emu, height_emu, doc_id),
        })

    return pending_slots


def _prepare_template(template_path, tmp_dir, certificate):
    """Returns a path to a docxtpl-ready copy of the template: real Word MERGEFIELD codes
    are rewritten to {{ }} placeholders, body signature pictures are swapped for the
    certificate's actual instructor/chefe signatures where a swappable picture already
    exists, and manually-typed '<Nome>' placeholders get a real name + an inserted
    signature picture where the template has no picture left at all. If nothing needs
    changing, the original file is used as-is."""
    with zipfile.ZipFile(template_path) as zin:
        xml_rewrites = {}
        media_rewrites = {}
        pending_media = []

        pending_slots = []
        for info in zin.infolist():
            if not _XML_PARTS_WITH_FIELDS.match(info.filename):
                continue
            root = etree.fromstring(zin.read(info.filename))
            text_changed = _convert_mergefields_to_jinja(root)
            text_changed = _strip_theme_colors(root) or text_changed
            if info.filename == 'word/document.xml':
                _swap_body_signatures(root, media_rewrites, zin, info.filename, certificate)
                pending_slots = _insert_placeholder_signatures(root, certificate, pending_media)
                if pending_slots:
                    text_changed = True
            if text_changed:
                xml_rewrites[info.filename] = root  # keep as element for now; serialize after rels patch

        rels_path = 'word/_rels/document.xml.rels'
        if pending_slots:
            rels_root = etree.fromstring(zin.read(rels_path)) if rels_path in zin.namelist() else \
                etree.fromstring(f'<Relationships xmlns="{PKG_REL_NS}"/>'.encode('utf-8'))
            for slot in pending_slots:
                new_rid = _next_relationship_id(rels_root)
                rel_el = etree.SubElement(rels_root, f'{{{PKG_REL_NS}}}Relationship')
                rel_el.set('Id', new_rid)
                rel_el.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image')
                rel_el.set('Target', f'media/{slot["picture_filename"]}')

                pos_h, pos_v, width, height, doc_id = slot['picture_xml_args']
                picture_run = _build_signature_picture_xml(new_rid, pos_h, pos_v, width, height, doc_id)
                slot['paragraph'].append(picture_run)
            xml_rewrites[rels_path] = rels_root

        for path, element in list(xml_rewrites.items()):
            xml_rewrites[path] = etree.tostring(element, xml_declaration=True, encoding='UTF-8', standalone=True)
        for filename, png_bytes in pending_media:
            media_rewrites[f'word/media/{filename}'] = png_bytes

        if not xml_rewrites and not media_rewrites:
            return Path(template_path)

        prepared_path = tmp_dir / 'prepared_template.docx'
        with zipfile.ZipFile(prepared_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = xml_rewrites.get(info.filename) or media_rewrites.get(info.filename) or zin.read(info.filename)
                zout.writestr(info, data)
            for path, data in media_rewrites.items():
                if path not in zin.namelist():
                    zout.writestr(path, data)
        return prepared_path


def _cpf_display(cpf):
    if cpf and len(cpf) == 11:
        return f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}'
    return cpf or ''


def _merge_context(certificate):
    chefe = _resolve_chefe(certificate)
    return {
        'NOME': certificate.student_name,
        'CPF': _cpf_display(certificate.cpf),
        'DATA': certificate.course_date.strftime('%d/%m/%Y'),
        'DURACAO': certificate.duration,
        'DATA_EMISSAO': certificate.issue_date.strftime('%d/%m/%Y'),
        'CERTIFICADO': certificate.code,
        'INSTRUTOR_NOME': certificate.professor.full_name if certificate.professor else '',
        'INSTRUTOR_CHEFE_NOME': chefe.full_name if chefe else '',
    }


def _convert(docx_path, out_dir, fmt):
    # Each call gets its own LibreOffice user profile. Without this, concurrent
    # `soffice --headless` invocations contend for the same default profile lock
    # and the second call hangs indefinitely instead of erroring out.
    profile_dir = out_dir / 'lo_profile'
    profile_dir.mkdir(exist_ok=True)
    user_installation = profile_dir.as_uri()

    try:
        subprocess.run(
            [
                settings.SOFFICE_PATH, '--headless', '--norestore',
                f'-env:UserInstallation={user_installation}',
                '--convert-to', fmt, '--outdir', str(out_dir), str(docx_path),
            ],
            check=True, capture_output=True, timeout=45,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('A conversão do certificado (LibreOffice) demorou demais e foi cancelada.') from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f'Falha ao converter o certificado: {exc.stderr.decode(errors="replace")}') from exc

    out_path = out_dir / f'{docx_path.stem}.{fmt}'
    if not out_path.exists():
        raise RuntimeError(f'LibreOffice did not produce {out_path}')
    return out_path.read_bytes()


def render_certificate_word(certificate, fmt='pdf'):
    """Fills the CourseTemplate's Word template with this certificate's data (text fields
    + instructor/chefe signature pictures) and converts it to `fmt` ('pdf' or 'png') via
    headless LibreOffice. Returns raw bytes.

    Accepts a template using plain {{ }} placeholders, a genuine Word mail-merge document
    (real MERGEFIELD codes), or one with manually-typed '<Nome>' placeholders in the
    signature area — all are normalized before rendering.
    """
    template_path = certificate.course_template.word_template.path

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        prepared_path = _prepare_template(template_path, tmp_dir, certificate)

        tpl = DocxTemplate(prepared_path)
        tpl.render(_merge_context(certificate))

        docx_path = tmp_dir / f'{certificate.code}.docx'
        tpl.save(docx_path)
        return _convert(docx_path, tmp_dir, fmt)


def has_word_template(certificate):
    return bool(certificate.course_template and certificate.course_template.word_template)
