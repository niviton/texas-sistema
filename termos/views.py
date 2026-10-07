import logging
import os
import tempfile

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from certificates.decorators import admin_required, termos_required
from checklists.importador import FormularioInvalido, _ler_cabecalho, FormularioLido
from dashboard.navigation import CONFIG_KEYS, CONFIG_TABS
from veiculos.emails import supervisor_emails
from veiculos.carimbo import carimbo_da_requisicao
from veiculos.imagens import ImagemInvalida, assinatura_de_dataurl, comprimir_foto

from .emails import enviar_em_segundo_plano, enviar_termo
from .forms import ImportarTermoForm, ModeloTermoForm, TermoForm
from .models import ENTRADA, FINALIZADO, RASCUNHO, ROTULOS, SAIDA, TIPO_CHOICES, ModeloTermo, Termo, TermoFoto, TermoItem
from .pdf import pdf_filename, render_termo_pdf

logger = logging.getLogger(__name__)

_MAX_FOTOS = 12
TABS = [
    ('lista', 'Termos', 'termos:lista'),
    ('novo', 'Novo termo', 'termos:novo'),
]


def _ctx(request, active_tab, **extra):
    if active_tab in CONFIG_KEYS:
        base = {'active_nav': 'configuracoes', 'config_mode': True, 'config_tabs': CONFIG_TABS}
    else:
        base = {'active_nav': 'termos', 'mod_tabs': TABS}
    return {**base, 'active_tab': active_tab, 'is_admin': request.user.is_admin_geral, **extra}


@termos_required
def lista_view(request):
    qs = Termo.objects.annotate(n_itens=Count('itens'))
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '')
    if q:
        qs = qs.filter(Q(cliente_contato__icontains=q) | Q(numero_assunto__icontains=q) | Q(motivo__icontains=q)
                       | Q(origem__icontains=q) | Q(itens__descricao__icontains=q) | Q(itens__referencia__icontains=q)).distinct()
    contagem = {'todos': Termo.objects.count(), ENTRADA: Termo.objects.filter(tipo=ENTRADA).count(),
                SAIDA: Termo.objects.filter(tipo=SAIDA).count()}
    if tipo in (ENTRADA, SAIDA):
        qs = qs.filter(tipo=tipo)
    return render(request, 'termos/lista.html', _ctx(request, 'lista', termos=qs[:200], q=q, tipo=tipo, contagem=contagem))


def _itens_do_post(post):
    descricoes = post.getlist('item_descricao')
    referencias = post.getlist('item_referencia')
    quantidades = post.getlist('item_quantidade')
    informacoes = post.getlist('item_informacao')
    itens = []
    for i, desc in enumerate(descricoes):
        desc = desc.strip()[:200]
        if not desc:
            continue
        try:
            qtd = max(1, int(quantidades[i]))
        except (IndexError, ValueError):
            qtd = 1
        itens.append({
            'descricao': desc,
            'referencia': (referencias[i] if i < len(referencias) else '').strip()[:120],
            'quantidade': qtd,
            'informacao': (informacoes[i] if i < len(informacoes) else '').strip()[:200],
        })
    return itens


@termos_required
def novo_view(request):
    return _form(request, None)


@termos_required
def editar_view(request, pk):
    termo = get_object_or_404(Termo, pk=pk)
    if termo.finalizado:
        messages.error(request, 'Termo finalizado não pode ser alterado.')
        return redirect('termos:detalhe', pk=pk)
    return _form(request, termo)


def _form(request, termo):
    erros = []
    if request.method == 'POST':
        form = TermoForm(request.POST, instance=termo)
        itens = _itens_do_post(request.POST)
        novas_fotos = request.FILES.getlist('fotos')
        remover = set(request.POST.getlist('remover_foto'))
        ja_tem = termo.fotos.exclude(pk__in=remover).count() if termo else 0
        if ja_tem + len(novas_fotos) > _MAX_FOTOS:
            erros.append(f'O termo aceita no máximo {_MAX_FOTOS} fotos.')
        assinaturas = {}
        for campo in ('assinatura_texas', 'assinatura_cliente'):
            try:
                assinaturas[campo] = assinatura_de_dataurl(request.POST.get(campo, ''))
            except ImagemInvalida as exc:
                erros.append(str(exc))
        if form.is_valid() and not erros:
            try:
                termo = _salvar(request, form, itens, novas_fotos, remover, assinaturas)
            except ImagemInvalida as exc:
                erros.append(str(exc))
            else:
                if request.POST.get('acao') == 'finalizar':
                    return _finalizar(request, termo)
                messages.success(request, f'Rascunho do termo nº {termo.numero} salvo.')
                return redirect('termos:detalhe', pk=termo.pk)
        itens_tela = itens
    else:
        tipo = request.GET.get('tipo') if request.GET.get('tipo') in (ENTRADA, SAIDA) else ENTRADA
        form = TermoForm(instance=termo, initial=None if termo else {'tipo': tipo, 'data': timezone.localdate()})
        itens_tela = [{'descricao': i.descricao, 'referencia': i.referencia, 'quantidade': i.quantidade, 'informacao': i.informacao}
                      for i in termo.itens.all()] if termo else []
    return render(request, 'termos/form.html', _ctx(
        request, 'novo' if termo is None else 'lista', form=form, termo=termo, itens=itens_tela or [{}],
        erros=erros, rotulos=ROTULOS, max_fotos=_MAX_FOTOS, nome_responsavel=request.user.full_name or request.user.email,
    ))


@transaction.atomic
def _salvar(request, form, itens, novas_fotos, remover, assinaturas):
    termo = form.save(commit=False)
    if termo.pk is None:
        termo.created_by = request.user
    if assinaturas.get('assinatura_texas'):
        termo.assinatura_texas = assinaturas['assinatura_texas']
        termo.responsavel_texas = request.user.full_name or request.user.email
    elif request.POST.get('limpar_assinatura_texas'):
        termo.assinatura_texas = None
        termo.responsavel_texas = ''
    if assinaturas.get('assinatura_cliente'):
        termo.assinatura_cliente = assinaturas['assinatura_cliente']
    elif request.POST.get('limpar_assinatura_cliente'):
        termo.assinatura_cliente = None
    termo.save()
    termo.itens.all().delete()
    TermoItem.objects.bulk_create([TermoItem(termo=termo, ordem=n, **i) for n, i in enumerate(itens)])
    if remover:
        termo.fotos.filter(pk__in=remover).delete()
    carimbo = carimbo_da_requisicao(request) if novas_fotos else None
    for f in novas_fotos:
        TermoFoto.objects.create(termo=termo, imagem=comprimir_foto(f, carimbo))
    return termo


def _finalizar(request, termo):
    faltas = termo.pendencias_para_finalizar()
    if faltas:
        messages.error(request, 'Rascunho salvo, mas o termo ainda não pode ser finalizado: ' + '; '.join(faltas) + '.')
        return redirect('termos:editar', pk=termo.pk)
    doc = ModeloTermo.do_tipo(termo.tipo)
    termo.status = FINALIZADO
    termo.documento = doc
    termo.documento_revisao = doc.revisao
    termo.finalizado_em = timezone.now()
    termo.save(update_fields=['status', 'documento', 'documento_revisao', 'finalizado_em'])
    if supervisor_emails():
        enviar_em_segundo_plano(termo.pk)
        messages.success(request, f'Termo nº {termo.numero} finalizado. O PDF está sendo enviado aos supervisores.')
    else:
        messages.success(request, f'Termo nº {termo.numero} finalizado. (Nenhum supervisor cadastrado para receber o e-mail.)')
    return redirect('termos:detalhe', pk=termo.pk)


@termos_required
def detalhe_view(request, pk):
    termo = get_object_or_404(Termo.objects.prefetch_related('itens', 'fotos'), pk=pk)
    return render(request, 'termos/detalhe.html', _ctx(
        request, 'lista', termo=termo, faltas=[] if termo.finalizado else termo.pendencias_para_finalizar(),
    ))


@termos_required
def pdf_view(request, pk):
    termo = get_object_or_404(Termo, pk=pk)
    response = HttpResponse(render_termo_pdf(termo), content_type='application/pdf')
    disposition = 'attachment' if request.GET.get('download') else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{pdf_filename(termo)}"'
    return response


@termos_required
def reenviar_view(request, pk):
    termo = get_object_or_404(Termo, pk=pk, status=FINALIZADO)
    if request.method == 'POST':
        try:
            if enviar_termo(termo):
                messages.success(request, 'Termo reenviado aos supervisores.')
            else:
                messages.error(request, 'Nenhum supervisor ativo cadastrado.')
        except Exception as exc:
            messages.error(request, f'Falha ao enviar o e-mail: {exc}')
    return redirect('termos:detalhe', pk=pk)


@termos_required
def excluir_view(request, pk):
    termo = get_object_or_404(Termo, pk=pk)
    if request.method == 'POST':
        if termo.finalizado and not request.user.is_admin_geral:
            messages.error(request, 'Só o administrador pode excluir um termo finalizado.')
            return redirect('termos:detalhe', pk=pk)
        numero = termo.numero
        termo.delete()
        messages.success(request, f'Termo nº {numero} excluído.')
    return redirect('termos:lista')


@admin_required
def documentos_view(request):
    """Configurações → Termos: código, revisão e responsáveis do cabeçalho de cada formulário."""
    docs = {t: ModeloTermo.do_tipo(t) for t, _ in TIPO_CHOICES}
    forms_ = {t: ModeloTermoForm(instance=d, prefix=t) for t, d in docs.items()}
    importar = ImportarTermoForm()
    if request.method == 'POST' and request.POST.get('acao') in docs:
        t = request.POST['acao']
        forms_[t] = ModeloTermoForm(request.POST, instance=docs[t], prefix=t)
        if forms_[t].is_valid():
            forms_[t].save()
            messages.success(request, f'Cabeçalho do termo de {dict(TIPO_CHOICES)[t].lower()} salvo.')
            return redirect('termos:documentos')
    elif request.method == 'POST' and request.POST.get('acao') == 'importar':
        importar = ImportarTermoForm(request.POST, request.FILES)
        if importar.is_valid():
            fd, caminho = tempfile.mkstemp(suffix='.docx')
            try:
                with os.fdopen(fd, 'wb') as tmp:
                    for chunk in importar.cleaned_data['arquivo'].chunks():
                        tmp.write(chunk)
                doc = importar_documento(caminho)
            except FormularioInvalido as exc:
                importar.add_error('arquivo', str(exc))
            else:
                messages.success(request, f'{doc.codigo} rev. {doc.revisao} importado para o termo de {doc.get_tipo_display().lower()}.')
                return redirect('termos:documentos')
            finally:
                os.remove(caminho)
    return render(request, 'termos/documentos.html', _ctx(
        request, 'termos_doc', blocos=[(t, rotulo, forms_[t]) for t, rotulo in TIPO_CHOICES], importar=importar,
    ))


def importar_documento(caminho):
    """Lê do cabeçalho do .docx o código, título, revisão, preparado/revisado por e data."""
    f = FormularioLido()
    _ler_cabecalho(caminho, f)
    if not f.codigo:
        raise FormularioInvalido('Não encontrei o código do documento (ex.: TCB-LO-01) no cabeçalho.')
    titulo = (f.titulo or '').upper()
    if 'SAÍDA' in titulo or 'SAIDA' in titulo:
        tipo = SAIDA
    elif 'ENTRADA' in titulo:
        tipo = ENTRADA
    else:
        raise FormularioInvalido('O título do formulário não diz se é termo de entrada ou de saída.')
    doc = ModeloTermo.do_tipo(tipo)
    doc.codigo = f.codigo
    doc.titulo = f.titulo[:1] + f.titulo[1:].lower() if f.titulo.isupper() else f.titulo
    doc.revisao = f'{f.revisao:02d}'
    doc.preparado_por, doc.revisado_por, doc.data = f.preparado_por, f.revisado_por, f.data
    doc.save()
    return doc
