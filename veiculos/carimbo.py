"""
Carimbo de comprovação nas fotos: logo Texas, data e hora e endereço de onde a foto foi feita.

- Data e hora vêm do relógio do **servidor** no momento do envio (não dá para adiantar ou
  atrasar pelo celular).
- O local vem do GPS do celular (enviado pelo formulário) e é convertido em endereço pelo
  OpenStreetMap (Nominatim). O navegador só libera o GPS em sites com HTTPS.
- Se a foto veio da galeria e é antiga (data do arquivo), o carimbo avisa:
  "Foto da galeria, feita em ...".
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

_MESES = ['jan.', 'fev.', 'mar.', 'abr.', 'mai.', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.']
_FONTE = Path(__file__).resolve().parent / 'assets' / 'fonts' / 'Montserrat-SemiBold.ttf'
_LOGO_BRANCO = Path(settings.BASE_DIR) / 'static' / 'assets' / 'logo-texas-branco.png'
_LOGO_COR = Path(settings.BASE_DIR) / 'static' / 'assets' / 'logo-texas-cor-hd.png'
_GALERIA_MINUTOS = 15  # arquivo mais velho que isso, em relação ao envio, é marcado como foto da galeria
_TS_NO_NOME = re.compile(r'_t(\d{13})(?=\.\w+$)')


@dataclass
class Carimbo:
    quando: datetime
    local: list = field(default_factory=list)  # linhas do endereço; vazio = local não registrado


def data_extenso(dt):
    dt = timezone.localtime(dt)
    return f'{dt.day} de {_MESES[dt.month - 1]} de {dt.year} {dt:%H:%M:%S}'


@lru_cache(maxsize=256)
def _endereco(lat4, lon4):
    """Endereço em linhas, como no app da Texas: número e rua / bairro / cidade / estado."""
    try:
        r = requests.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={'format': 'jsonv2', 'lat': lat4, 'lon': lon4, 'zoom': 18, 'addressdetails': 1},
            headers={'User-Agent': 'Polaris-TexasControls/1.0 (carimbo de fotos)', 'Accept-Language': 'pt-BR'},
            timeout=4,
        )
        r.raise_for_status()
        a = r.json().get('address', {})
    except Exception:
        logger.warning('Não foi possível converter a localização em endereço', exc_info=True)
        return ()
    rua = ' '.join(x for x in [a.get('house_number'), a.get('road')] if x)
    bairro = a.get('suburb') or a.get('neighbourhood') or a.get('quarter') or ''
    cidade = a.get('city') or a.get('town') or a.get('village') or a.get('municipality') or ''
    estado = a.get('state') or ''
    return tuple(x for x in [rua, bairro, cidade, estado] if x)


def carimbo_da_requisicao(request):
    """Monta o carimbo uma vez por envio de formulário (todas as fotos do envio usam o mesmo)."""
    linhas = []
    try:
        lat = float(request.POST.get('geo_lat', ''))
        lon = float(request.POST.get('geo_lon', ''))
    except ValueError:
        lat = lon = None
    if lat is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        if getattr(settings, 'CARIMBO_ENDERECO', True):
            linhas = list(_endereco(round(lat, 4), round(lon, 4)))
        if not linhas:
            linhas = [f'Lat {lat:.5f}, Lon {lon:.5f}']
    return Carimbo(quando=timezone.now(), local=linhas)


def _origem_do_arquivo(nome):
    """O formulário põe a data original do arquivo no nome (…_t1696600000000.jpg)."""
    m = _TS_NO_NOME.search(nome or '')
    if not m:
        return None
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.get_current_timezone())
    except (OverflowError, OSError, ValueError):
        return None


def aplicar(img, carimbo, nome_arquivo=''):
    """Desenha logo (canto superior direito) e texto (canto inferior direito) na imagem RGB."""
    w, h = img.size
    base = min(w, h)
    linhas = [data_extenso(carimbo.quando)]
    linhas += carimbo.local or ['Local não registrado']
    origem = _origem_do_arquivo(nome_arquivo)
    if origem and (carimbo.quando - origem).total_seconds() > _GALERIA_MINUTOS * 60:
        linhas.append(f'Foto da galeria, feita em {timezone.localtime(origem):%d/%m/%Y %H:%M}')

    tam = max(14, int(base * 0.042))
    try:
        fonte = ImageFont.truetype(str(_FONTE), tam)
    except OSError:
        fonte = ImageFont.load_default(size=tam)
    camada = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    margem = int(base * 0.03)
    espaco = int(tam * 1.28)
    y = h - margem - espaco * len(linhas)
    for linha in linhas:
        largura = d.textlength(linha, font=fonte)
        x = w - margem - largura
        d.text((x, y), linha, font=fonte, fill=(255, 255, 255, 255), stroke_width=max(2, tam // 9), stroke_fill=(0, 0, 0, 170))
        y += espaco

    lw = int(w * 0.22) if w >= h else int(w * 0.30)
    pos = (w - margem - lw, margem)
    # Fundo claro no canto: logo colorida (texto azul); fundo escuro: logo branca.
    canto = img.crop((pos[0], pos[1], pos[0] + lw, pos[1] + int(lw * 0.86))).convert('L')
    claro = sum(canto.getdata()) / max(1, canto.width * canto.height) > 150
    arquivo = _LOGO_COR if claro else _LOGO_BRANCO
    if arquivo.exists():
        logo = Image.open(arquivo).convert('RGBA')
        logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
        sombra = Image.new('RGBA', logo.size, (0, 0, 0, 0))
        sombra.putalpha(logo.getchannel('A').point(lambda a: int(a * 0.55)))
        sombra = sombra.filter(ImageFilter.GaussianBlur(max(2, lw // 60)))
        if not claro:
            camada.alpha_composite(sombra, (pos[0] + 2, pos[1] + 3))
        camada.alpha_composite(logo, pos)

    return Image.alpha_composite(img.convert('RGBA'), camada).convert('RGB')
