"""
Importa um formulário TCB-OTB em Word (.docx) como modelo de checklist.

Lê do cabeçalho o título, o código, a revisão, quem preparou, quem revisou e a data.
O corpo é lido por formato de tabela (os TCB foram feitos em épocas diferentes):
  - "Item | OK | NOK"                      -> OK / NOK / N/A (formato atual)
  - "Item | SIM | NÃO"                     -> Sim / Não
  - "Descrição | C | N | P | NA"           -> Conforme / Não conforme / Parcialmente / N/A
  - tabela única com linhas de seção e "C | NC | NA" (TCB-OTB-02 a 06)
  - "Item | DOM | SEG | ... | SAB"         -> grade semanal: cada execução é um dia, OK / NOK / N/A
  - "Descrição | Verificação"              -> [INSERIR FOTO] vira foto obrigatória, [VALOR] vira número
O parágrafo anterior à tabela vira o título da seção.
"""
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

import docx
from django.db import transaction
from docx.table import Table
from docx.text.paragraph import Paragraph

from .models import (
    RESP_CONFORMIDADE, RESP_NUMERO, RESP_OK_NOK, RESP_SIM_NAO, RESP_TEXTO, Item, Modelo, Revisao, Secao, TipoAtivo,
    finalidade_do_titulo,
)

_CODIGO = re.compile(r'\b([A-Z]{2,5}-[A-Z]{2,5}-\d{1,4})\b')
_DATA = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')
# Rótulos fixos do cabeçalho bilíngue dos formulários da empresa.
_ROTULOS = {'título', 'title', 'documento', 'document', 'revisão', 'review', 'página', 'pages',
            'preparado por', 'prepared by', 'revisado por', 'review by', 'reviewed by', 'data', 'date'}


class FormularioInvalido(ValueError):
    pass


@dataclass
class ItemLido:
    texto: str
    tipo: str = RESP_OK_NOK
    exige_foto: bool = False


@dataclass
class FormularioLido:
    codigo: str = ''
    titulo: str = ''
    revisao: int = 0
    preparado_por: str = ''
    revisado_por: str = ''
    data: object = None
    secoes: list = field(default_factory=list)  # [(titulo, [ItemLido])]

    @property
    def total_itens(self):
        return sum(len(itens) for _, itens in self.secoes)


def _frase(texto):
    """'VERIFICAÇÃO DOS EPIs' -> 'Verificação dos EPIs' (sem caixa alta na tela)."""
    texto = ' '.join(texto.split())
    if sum(c.isupper() for c in texto) < sum(c.islower() for c in texto):
        return texto
    out = texto.lower().capitalize()
    for sigla in ('EPIs', 'EPI', 'RAD', 'CRLV', 'CNH', 'GMG'):
        out = re.sub(rf'\b{sigla.lower()}\b', sigla, out)
    return out.replace('r/s/t', 'R/S/T')


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
            if i + 1 < len(valores) and re.fullmatch(r'\d+(\.0)?', valores[i + 1]):
                f.revisao = int(float(valores[i + 1]))
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


_DIAS = {'dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'sáb'}
_FIM_DA_LISTA = ('operador', 'superior imediato', 'legenda', 'observa', 'obs.', 'assinatura')


def _limpo(texto):
    return ' '.join(texto.split())


def _titulo_de_paragrafo(texto):
    """Parágrafo que pode ser título de seção: curto, sem campo a preencher ("DATA:", "[XXXX]")."""
    t = texto.strip()
    if not t or len(t) > 80 or '[' in t or t.endswith(':') or ':' in t[:25]:
        return False
    return not t.lower().startswith(('data', 'legenda', 'os itens', 'informações'))


def _tipo_da_tabela(cab):
    """Formato pelo cabeçalho (primeira linha, sem células repetidas de mesclagem)."""
    c = [x.lower() for x in cab]
    if c[:1] == ['item'] and 'ok' in c and 'nok' in c:
        return 'ok_nok'
    if c[:1] == ['item'] and 'sim' in c and ('não' in c or 'nao' in c):
        return 'sim_nao'
    if c[:1] == ['item'] and _DIAS & set(c):
        return 'semanal'
    if c[:1] == ['descrição'] and {'c', 'na'} <= set(c):
        return 'conformidade'
    if c[:1] == ['descrição'] and 'verificação' in c:
        return 'verificacao'
    return None


def _item_de_verificacao(texto, valor):
    v = valor.upper()
    if 'FOTO' in v:
        return ItemLido(_frase(texto), RESP_TEXTO, exige_foto=True)
    if 'VALOR' in v:
        # "Corrente R/S/T" tem três leituras: vai como texto.
        return ItemLido(_frase(texto), RESP_TEXTO if '/' in texto else RESP_NUMERO)
    if v.startswith('[DESCREVER') or v.startswith('[DESCREVA'):
        return ItemLido(_frase(texto), RESP_TEXTO)
    return ItemLido(_frase(texto), RESP_OK_NOK)


def _ler_tabela_cnc(linhas, f):
    """Tabela única (TCB-OTB-02 a 06): linha de seção, linha "| C | NC | NA", itens; para no rodapé."""
    titulo, itens, dentro = '', [], False
    for linha in linhas:
        unicas = [c for c in dict.fromkeys(linha) if c]
        if not unicas:
            continue
        primeira = unicas[0].lower()
        if primeira.startswith(_FIM_DA_LISTA):
            break
        if {'c', 'nc', 'na'} <= {u.lower() for u in unicas}:
            dentro = True
            continue
        if len(unicas) == 1 and len(set(linha)) == 1:  # linha mesclada: título de seção
            if itens:
                f.secoes.append((_frase(titulo or 'Verificação'), itens))
            titulo, itens, dentro = unicas[0], [], False
            if primeira.startswith('checklist'):
                titulo = ''
            continue
        if dentro and len(unicas) == 1:
            itens.append(ItemLido(_frase(unicas[0]), RESP_CONFORMIDADE))
    if itens:
        f.secoes.append((_frase(titulo or 'Verificação'), itens))


def _ler_corpo(documento, f):
    ultimo_titulo = ''
    campos = []  # "IDENTIFICAÇÃO: [XXXX]" antes da tabela vira item de texto da seção
    for bloco in _blocos(documento):
        if isinstance(bloco, Paragraph):
            texto = _limpo(bloco.text)
            if _titulo_de_paragrafo(texto):
                ultimo_titulo, campos = texto, []
            elif '[' in texto and ':' in texto and ultimo_titulo:
                rotulo = texto.split(':', 1)[0].strip()
                if rotulo.lower() not in ('empresa', 'responsável', 'data'):
                    campos.append(ItemLido(_frase(rotulo), RESP_TEXTO))
            continue
        linhas = [[_limpo(c.text) for c in row.cells] for row in bloco.rows]
        if not linhas:
            continue
        if any({'c', 'nc', 'na'} <= {x.lower() for x in linha} for linha in linhas[:8]):
            _ler_tabela_cnc(linhas, f)
            continue
        formato = _tipo_da_tabela(list(dict.fromkeys(linhas[0])))
        if not formato:
            continue
        itens, vistos = list(campos), set()
        for linha in linhas[1:]:
            texto = linha[0]
            if not texto or texto in vistos or texto.lower().startswith(_FIM_DA_LISTA):
                continue
            vistos.add(texto)
            if formato == 'verificacao':
                valor = next((c for c in linha[1:] if c and c != texto), '')
                itens.append(_item_de_verificacao(texto, valor))
            elif formato == 'semanal' and texto.lower().startswith('anotar horímetro'):
                itens.append(ItemLido('Horímetro', RESP_NUMERO))
            elif formato == 'sim_nao':
                itens.append(ItemLido(_frase(texto), RESP_SIM_NAO))
            elif formato == 'conformidade':
                itens.append(ItemLido(_frase(texto), RESP_CONFORMIDADE))
            else:
                itens.append(ItemLido(_frase(texto) if formato == 'semanal' else texto, RESP_OK_NOK))
        if itens:
            f.secoes.append((_frase(ultimo_titulo or 'Verificação'), itens))
        campos = []


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
        raise FormularioInvalido('Não encontrei nenhuma tabela de checklist no formulário (ex.: "Item | OK | NOK").')
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
                Item(secao=secao, texto=it.texto[:255], tipo_resposta=it.tipo, exige_foto=it.exige_foto, ordem=ordem_i)
                for ordem_i, it in enumerate(itens)
            ])
    if tipo_ativo is None:
        tipo_ativo, _ = TipoAtivo.objects.get_or_create(nome=nome_do_tipo(f.titulo))
    modelo.tipos_ativo.add(tipo_ativo)
    return modelo, revisao, criado
