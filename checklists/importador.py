"""
Importa um formulário TCB-OTB em Word (.docx) como modelo de checklist.

Lê do cabeçalho o título, o código, a revisão, quem preparou, quem revisou e a data;
do corpo, cada tabela "Item | OK | NOK" vira uma seção, com o parágrafo anterior como título.
"""
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

import docx
from django.db import transaction
from docx.table import Table
from docx.text.paragraph import Paragraph

from .models import finalidade_do_titulo, RESP_OK_NOK, Item, Modelo, Revisao, Secao, TipoAtivo

_CODIGO = re.compile(r'\b([A-Z]{2,5}-[A-Z]{2,5}-\d{1,4})\b')
_DATA = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')
# Rótulos fixos do cabeçalho bilíngue dos formulários da empresa.
_ROTULOS = {'título', 'title', 'documento', 'document', 'revisão', 'review', 'página', 'pages',
            'preparado por', 'prepared by', 'revisado por', 'review by', 'reviewed by', 'data', 'date'}


class FormularioInvalido(ValueError):
    pass


@dataclass
class FormularioLido:
    codigo: str = ''
    titulo: str = ''
    revisao: int = 0
    preparado_por: str = ''
    revisado_por: str = ''
    data: object = None
    secoes: list = field(default_factory=list)  # [(titulo, [itens])]

    @property
    def total_itens(self):
        return sum(len(itens) for _, itens in self.secoes)


def _frase(texto):
    """'VERIFICAÇÃO DOS EPIs' -> 'Verificação dos EPIs' (sem caixa alta na tela)."""
    texto = ' '.join(texto.split())
    if sum(c.isupper() for c in texto) < sum(c.islower() for c in texto):
        return texto
    out = texto.lower().capitalize()
    for sigla in ('EPIs', 'EPI', 'RAD', 'CRLV', 'CNH'):
        out = re.sub(rf'\b{sigla.lower()}\b', sigla, out)
    return out


def _textos_cabecalho(caminho):
    with zipfile.ZipFile(caminho) as z:
        nomes = sorted(n for n in z.namelist() if re.fullmatch(r'word/header\d+\.xml', n))
        for nome in nomes:
            xml = z.read(nome).decode('utf-8', 'ignore')
            paras = re.findall(r'<w:p[ >].*?</w:p>', xml, re.S)
            textos = [''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p)).strip() for p in paras]
            textos = [t for t in textos if t]
            if any(_CODIGO.search(t) for t in textos):
                return textos
    return []


def _ler_cabecalho(caminho, f):
    textos = _textos_cabecalho(caminho)
    valores = [t for t in textos if t.lower() not in _ROTULOS]
    for i, t in enumerate(valores):
        m = _CODIGO.search(t)
        if m and not f.codigo:
            f.codigo = m.group(1)
            if i + 1 < len(valores) and valores[i + 1].isdigit():
                f.revisao = int(valores[i + 1])
    titulos = [t for t in valores if len(t) > 12 and not _CODIGO.search(t) and not _DATA.search(t)]
    if titulos:
        f.titulo = titulos[0]
    datas = [_DATA.search(t).group(1) for t in valores if _DATA.search(t)]
    if datas:
        f.data = datetime.strptime(datas[0], '%d/%m/%Y').date()
        # Nomes vêm logo antes da data: "Preparado por" e "Revisado por".
        idx = next(i for i, t in enumerate(valores) if _DATA.search(t))
        nomes = [t for t in valores[:idx] if re.fullmatch(r"[A-Za-zÀ-ÿ' .]{5,}", t) and t != f.titulo]
        if len(nomes) >= 2:
            f.preparado_por, f.revisado_por = nomes[-2], nomes[-1]


def _blocos(documento):
    """Parágrafos e tabelas do corpo, na ordem em que aparecem."""
    for filho in documento.element.body.iterchildren():
        if filho.tag.endswith('}p'):
            yield Paragraph(filho, documento)
        elif filho.tag.endswith('}tbl'):
            yield Table(filho, documento)


def _ler_corpo(documento, f):
    ultimo_titulo = ''
    for bloco in _blocos(documento):
        if isinstance(bloco, Paragraph):
            texto = bloco.text.strip()
            if texto and len(texto) <= 80 and not texto.upper().startswith('DATA'):
                ultimo_titulo = texto
            continue
        linhas = [[c.text.strip() for c in row.cells] for row in bloco.rows]
        if not linhas:
            continue
        cab = [c.lower() for c in dict.fromkeys(linhas[0])]
        if cab[:1] == ['item'] and 'ok' in cab and 'nok' in cab:
            itens = []
            for linha in linhas[1:]:
                texto = ' '.join(linha[0].split())
                if texto and texto not in itens:
                    itens.append(texto)
            if itens:
                f.secoes.append((_frase(ultimo_titulo or 'Verificação'), itens))


def ler_formulario(caminho):
    try:
        documento = docx.Document(caminho)
    except Exception as exc:
        raise FormularioInvalido('O arquivo não é um documento Word (.docx) válido.') from exc
    f = FormularioLido()
    _ler_cabecalho(caminho, f)
    _ler_corpo(documento, f)
    if not f.codigo:
        raise FormularioInvalido('Não encontrei o código do documento (ex.: TCB-OTB-80) no cabeçalho do formulário.')
    if not f.secoes:
        raise FormularioInvalido('Não encontrei nenhuma tabela "Item | OK | NOK" no formulário.')
    if not f.titulo:
        f.titulo = f.codigo
    return f


def nome_do_tipo(titulo):
    """'CHECKLIST DE PRÉ-USO – BANCADA DE CALIBRAÇÃO RAD 02' -> 'Bancada de calibração RAD 02'."""
    parte = re.split(r'\s[–-]\s', titulo, maxsplit=1)
    return _frase(parte[1] if len(parte) > 1 else titulo)[:120]


@transaction.atomic
def importar(caminho, tipo_ativo=None):
    """
    Cria (ou atualiza com nova revisão) o modelo a partir do .docx.
    Retorna (modelo, revisao, criado). Se a revisão já existir, não duplica.
    """
    f = ler_formulario(caminho)
    modelo, criado = Modelo.objects.get_or_create(
        codigo=f.codigo, defaults={'titulo': _frase(f.titulo), 'finalidade': finalidade_do_titulo(f.titulo)},
    )
    revisao = modelo.revisoes.filter(numero=f.revisao).first()
    if revisao is None:
        revisao = Revisao.objects.create(
            modelo=modelo, numero=f.revisao, preparado_por=f.preparado_por, revisado_por=f.revisado_por,
            data=f.data, vigente=True, notas='Importado do formulário Word.',
        )
        modelo.revisoes.exclude(pk=revisao.pk).update(vigente=False)
        for ordem_s, (titulo, itens) in enumerate(f.secoes):
            secao = Secao.objects.create(revisao=revisao, titulo=titulo, ordem=ordem_s)
            Item.objects.bulk_create([
                Item(secao=secao, texto=texto, tipo_resposta=RESP_OK_NOK, ordem=ordem_i)
                for ordem_i, texto in enumerate(itens)
            ])
    if tipo_ativo is None:
        tipo_ativo, _ = TipoAtivo.objects.get_or_create(nome=nome_do_tipo(f.titulo))
    modelo.tipos_ativo.add(tipo_ativo)
    return modelo, revisao, criado
