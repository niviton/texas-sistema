import base64
import binascii
import io
import uuid

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

FOTO_MAX_PX = 1920
_ASSINATURA_MAX_BYTES = 2 * 1024 * 1024


class ImagemInvalida(ValueError):
    pass


def comprimir_foto(upload):
    """Gira conforme o EXIF, limita a 1920px e salva como JPEG (fotos de celular têm 4–8 MB)."""
    try:
        img = Image.open(upload)
        img = ImageOps.exif_transpose(img).convert('RGB')
    except (UnidentifiedImageError, OSError) as exc:
        raise ImagemInvalida(f'O arquivo "{getattr(upload, "name", "")}" não é uma imagem válida.') from exc
    img.thumbnail((FOTO_MAX_PX, FOTO_MAX_PX))
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=82, optimize=True)
    return ContentFile(buf.getvalue(), name=f'{uuid.uuid4().hex[:12]}.jpg')


def assinatura_de_dataurl(data_url):
    """Converte o 'data:image/png;base64,...' do campo de assinatura em arquivo PNG. Vazio → None."""
    if not data_url:
        return None
    prefixo = 'data:image/png;base64,'
    if not data_url.startswith(prefixo) or len(data_url) > _ASSINATURA_MAX_BYTES * 4 // 3:
        raise ImagemInvalida('Assinatura inválida.')
    try:
        raw = base64.b64decode(data_url[len(prefixo):], validate=True)
        img = Image.open(io.BytesIO(raw))
        img.verify()
    except (binascii.Error, UnidentifiedImageError, OSError) as exc:
        raise ImagemInvalida('Assinatura inválida.') from exc
    return ContentFile(raw, name=f'assinatura_{uuid.uuid4().hex[:12]}.png')
