import logging
import os
import tempfile
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from certificates.decorators import admin_required, checklists_required
from dashboard.navigation import CONFIG_KEYS, CONFIG_TABS
from veiculos.emails import supervisor_emails
from veiculos.carimbo import carimbo_da_requisicao
from veiculos.imagens import ImagemInvalida, assinatura_de_dataurl, comprimir_foto
from veiculos.views import _crud, _toggle_active

from .emails import enviar_em_segundo_plano, enviar_execucao
from .forms import AtivoForm, ImportarForm, ItemForm, ModeloForm, NovoModeloForm, RevisaoForm, SecaoForm, TipoAtivoForm
from .importador import FormularioInvalido, importar
from .models import (
    MEDIDOR_NENHUM, MEDIDOR_UNIDADE, OBS_CHOICES, OBS_SE_NEGATIVO, OBS_SEMPRE, TIPO_RESPOSTA_CHOICES, OPCOES_RESPOSTA, RESP_NUMERO, RESP_PORCENTAGEM,
    RESP_TEXTO, STATUS_INATIVO, VALORES_NEGATIVOS, Ativo, Execucao, FotoExecucao, Item, Modelo, Resposta, Revisao,
    Secao, TipoAtivo,
)
from .pdf import pdf_filename, render_execucao_pdf

logger = logging.getLogger(__name__)

_MAX_FOTOS_GERAIS = 10

TABS_ADMIN = [
    ('executar', 'Executar', 'checklists:executar'),
    ('historico', 'Histórico', 'checklists:historico'),
]
TABS_TECNICO = [
    ('executar', 'Executar', 'checklists:executar'),
    ('historico', 'Minhas execuções', 'checklists:historico'),
]


def _ctx(request, active_tab, **extra):
    is_admin = request.user.is_admin_geral
    if active_tab in CONFIG_KEYS:
        base = {'active_nav': 'configuracoes', 'config_mode': True, 'config_tabs': CONFIG_TABS}
    else:
        base = {'active_nav': 'checklists', 'mod_tabs': TABS_ADMIN if request.user.ve_todo_historico else TABS_TECNICO}
    return {**base, 'active_tab': active_tab, 'is_admin': is_admin, 've_tudo': request.user.ve_todo_historico, **extra}


def _execucoes_visiveis(user):
    """Administrador e Logística veem todas; o Técnico, só as próprias."""
    qs = Execucao.objects.select_related('revisao__modelo', 'ativo__tipo')
    if not user.ve_todo_historico:
        qs = qs.filter(executor=user)
    return qs


# ---------------------------------------------------------------- Execução

@checklists_required
def executar_view(request):
    q = request.GET.get('q', '').strip()
    ativos = (Ativo.objects.filter(is_active=True).exclude(status=STATUS_INATIVO)
              .select_related('tipo').annotate(n_modelos=Count('tipo__modelos', filter=Q(tipo__modelos__is_active=True))))
    if q:
        ativos = ativos.filter(Q(nome__icontains=q) | Q(identificacao__icontains=q) | Q(patrimonio__icontains=q) | Q(tipo__nome__icontains=q))
    grupos = {}
    for a in ativos:
        grupos.setdefault(a.tipo, []).append(a)
    return render(request, 'checklists/executar.html', _ctx(request, 'executar', grupos=grupos, q=q))


@checklists_required
def escolher_modelo_view(request, ativo_pk):
    ativo = get_object_or_404(Ativo.objects.select_related('tipo'), pk=ativo_pk, is_active=True)
    modelos = [m for m in ativo.modelos_disponiveis() if m.revisao_vigente]
    if len(modelos) == 1:
        return redirect('checklists:execucao_nova', ativo_pk=ativo.pk, modelo_pk=modelos[0].pk)
    return render(request, 'checklists/escolher_modelo.html', _ctx(request, 'executar', ativo=ativo, modelos=modelos))


def _ler_respostas(request, revisao):
    """Monta as respostas do POST e a lista de erros (um texto por problema)."""
    linhas, erros = [], []
    for item in revisao.itens().select_related('secao'):
        valor = request.POST.get(f'item_{item.pk}', '').strip()
        obs = request.POST.get(f'obs_{item.pk}', '').strip()[:255]
        foto = request.FILES.get(f'foto_{item.pk}')
        validas = [v for v, _ in OPCOES_RESPOSTA.get(item.tipo_resposta, [])]
        if validas:
            if valor not in validas:
                erros.append(f'Responda o item "{item.texto}".')
        elif item.tipo_resposta == RESP_PORCENTAGEM:
            if not valor.isdigit() or not 0 <= int(valor) <= 100:
                erros.append(f'Arraste a barra do item "{item.texto}".')
        elif item.tipo_resposta == RESP_NUMERO:
            try:
                valor = str(Decimal(valor.replace(',', '.')))
            except (InvalidOperation, ValueError):
                erros.append(f'Informe um número no item "{item.texto}".')
        pede_obs = item.observacao == OBS_SEMPRE or (item.observacao == OBS_SE_NEGATIVO and valor in VALORES_NEGATIVOS)
        if pede_obs and not obs:
            erros.append(f'Descreva a observação do item "{item.texto}".')
        if item.exige_foto and not foto:
            erros.append(f'Falta a foto do item "{item.texto}".')
        linhas.append({'item': item, 'valor': valor if item.tipo_resposta != RESP_TEXTO else valor[:255], 'obs': obs, 'foto': foto})
    return linhas, erros


@checklists_required
def execucao_nova_view(request, ativo_pk, modelo_pk):
    ativo = get_object_or_404(Ativo.objects.select_related('tipo'), pk=ativo_pk, is_active=True)
    modelo = get_object_or_404(Modelo, pk=modelo_pk, is_active=True, tipos_ativo=ativo.tipo)
    revisao = modelo.revisao_vigente
    if revisao is None:
        messages.error(request, f'{modelo.codigo} não tem revisão vigente. Fale com o administrador.')
        return redirect('checklists:executar')
    pede_medidor = ativo.tipo.medidor != MEDIDOR_NENHUM
    erros, valores = [], {}

    if request.method == 'POST':
        linhas, erros = _ler_respostas(request, revisao)
        valores = {f'item_{l["item"].pk}': l['valor'] for l in linhas} | {f'obs_{l["item"].pk}': l['obs'] for l in linhas}
        medidor = None
        if pede_medidor:
            try:
                medidor = Decimal(request.POST.get('medidor', '').replace(',', '.'))
                if medidor < 0:
                    raise InvalidOperation
                if ativo.medidor_atual is not None and medidor < ativo.medidor_atual:
                    erros.append(f'A leitura não pode ser menor que a última registrada ({ativo.medidor_atual}).')
            except (InvalidOperation, ValueError):
                erros.append(f'Informe a leitura do {ativo.tipo.get_medidor_display().lower()}.')
        fotos = request.FILES.getlist('fotos')
        if not fotos:
            erros.append('Tire pelo menos uma foto do equipamento.')
        elif len(fotos) > _MAX_FOTOS_GERAIS:
            erros.append(f'Envie no máximo {_MAX_FOTOS_GERAIS} fotos do equipamento.')
        assinatura = None
        try:
            assinatura = assinatura_de_dataurl(request.POST.get('assinatura', ''))
            if assinatura is None:
                erros.append('Falta a assinatura do técnico.')
        except ImagemInvalida as exc:
            erros.append(str(exc))
        if not erros:
            try:
                execucao = _salvar(request, ativo, revisao, linhas, medidor, fotos, assinatura)
            except ImagemInvalida as exc:
                erros.append(str(exc))
            else:
                if supervisor_emails('checklists', ativo.tipo):
                    enviar_em_segundo_plano(execucao.pk)
                    messages.success(request, 'Checklist registrado. O comprovante está sendo enviado aos supervisores.')
                else:
                    messages.success(request, 'Checklist registrado. (Ninguém cadastrado para receber o e-mail deste tipo de equipamento.)')
                return redirect('checklists:execucao', pk=execucao.pk)

    secoes = [(s, list(s.itens.all())) for s in revisao.secoes.prefetch_related('itens')]
    return render(request, 'checklists/execucao_form.html', _ctx(
        request, 'executar', ativo=ativo, modelo=modelo, revisao=revisao, secoes=secoes, erros=erros, valores=valores,
        pede_medidor=pede_medidor, unidade=MEDIDOR_UNIDADE.get(ativo.tipo.medidor, ''), max_fotos=_MAX_FOTOS_GERAIS,
        nome_tecnico=request.user.full_name or request.user.email,
    ))


@transaction.atomic
def _salvar(request, ativo, revisao, linhas, medidor, fotos, assinatura):
    execucao = Execucao.objects.create(
        revisao=revisao, ativo=ativo, executor=request.user,
        executor_nome=request.user.full_name or request.user.email, medidor_valor=medidor,
        observacoes=request.POST.get('observacoes', '').strip(), assinatura=assinatura,
        tem_problema=any(l['valor'] in VALORES_NEGATIVOS for l in linhas),
    )
    Resposta.objects.bulk_create([
        Resposta(execucao=execucao, item=l['item'], valor=l['valor'], observacao=l['obs']) for l in linhas
    ])
    carimbo = carimbo_da_requisicao(request)
    for l in linhas:
        if l['foto']:
            FotoExecucao.objects.create(execucao=execucao, item=l['item'], imagem=comprimir_foto(l['foto'], carimbo))
    for f in fotos:
        FotoExecucao.objects.create(execucao=execucao, imagem=comprimir_foto(f, carimbo))
    if medidor is not None and (ativo.medidor_atual is None or medidor > ativo.medidor_atual):
        ativo.medidor_atual = medidor
        ativo.save(update_fields=['medidor_atual'])
    return execucao


@checklists_required
def historico_view(request):
    qs = _execucoes_visiveis(request.user)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(ativo__nome__icontains=q) | Q(ativo__identificacao__icontains=q)
                       | Q(revisao__modelo__codigo__icontains=q) | Q(executor_nome__icontains=q))
    if request.GET.get('problema') == '1':
        qs = qs.filter(tem_problema=True)
    return render(request, 'checklists/historico.html', _ctx(request, 'historico', execucoes=qs[:200], q=q))


@checklists_required
def execucao_view(request, pk):
    execucao = get_object_or_404(_execucoes_visiveis(request.user).prefetch_related('respostas__item__secao', 'fotos__item'), pk=pk)
    secoes = {}
    for r in execucao.respostas.all():
        secoes.setdefault((r.item.secao.ordem, r.item.secao_id, r.item.secao.titulo), []).append(r)
    return render(request, 'checklists/execucao_detalhe.html', _ctx(
        request, 'historico', execucao=execucao, secoes=[(t, rs) for (_, _, t), rs in sorted(secoes.items())],
        fotos=list(execucao.fotos.all()),
    ))


@checklists_required
def execucao_pdf_view(request, pk):
    execucao = get_object_or_404(_execucoes_visiveis(request.user), pk=pk)
    response = HttpResponse(render_execucao_pdf(execucao), content_type='application/pdf')
    disposition = 'attachment' if request.GET.get('download') else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{pdf_filename(execucao)}"'
    return response


@checklists_required
def execucao_reenviar_view(request, pk):
    execucao = get_object_or_404(_execucoes_visiveis(request.user), pk=pk)
    if request.method == 'POST':
        try:
            if enviar_execucao(execucao):
                messages.success(request, 'Comprovante reenviado aos supervisores.')
            else:
                messages.error(request, 'Ninguém cadastrado para receber este e-mail (Configurações → Notificações).')
        except Exception as exc:
            messages.error(request, f'Falha ao enviar o e-mail: {exc}')
    return redirect('checklists:execucao', pk=pk)


# ---------------------------------------------------------------- Configurações (administrador geral)

@admin_required
def tipos_view(request):
    return _crud(request, TipoAtivo, TipoAtivoForm, 'checklists/tipos.html', 'tipos', 'checklists:tipos', 'Tipo de ativo salvo.')


@admin_required
def tipo_arquivar_view(request, pk):
    return _toggle_active(request, TipoAtivo, pk, 'checklists:tipos')


@admin_required
def ativos_view(request):
    return _crud(request, Ativo, AtivoForm, 'checklists/ativos.html', 'ativos', 'checklists:ativos', 'Ativo salvo.')


@admin_required
def ativo_arquivar_view(request, pk):
    return _toggle_active(request, Ativo, pk, 'checklists:ativos')


@admin_required
def modelos_view(request):
    importar_form = ImportarForm()
    novo_form = NovoModeloForm()
    if request.method == 'POST' and request.POST.get('acao') == 'importar':
        importar_form = ImportarForm(request.POST, request.FILES)
        if importar_form.is_valid():
            arquivo = importar_form.cleaned_data['arquivo']
            fd, caminho = tempfile.mkstemp(suffix='.docx')
            try:
                with os.fdopen(fd, 'wb') as tmp:
                    for chunk in arquivo.chunks():
                        tmp.write(chunk)
                modelo, revisao, criado = importar(caminho, importar_form.cleaned_data['tipo_ativo'])
            except FormularioInvalido as exc:
                importar_form.add_error('arquivo', str(exc))
            else:
                acao = 'importado' if criado else 'atualizado'
                messages.success(request, f'{modelo.codigo} rev. {revisao.rotulo} {acao} com {revisao.itens().count()} itens. Confira abaixo.')
                return redirect('checklists:modelo', pk=modelo.pk)
            finally:
                os.remove(caminho)
    elif request.method == 'POST' and request.POST.get('acao') == 'novo':
        novo_form = NovoModeloForm(request.POST)
        if novo_form.is_valid():
            modelo = novo_form.save()
            rev = Revisao.objects.create(modelo=modelo, numero=0)
            Secao.objects.create(revisao=rev, titulo='Verificação do equipamento')
            messages.success(request, f'{modelo.codigo} criado. Adicione os itens.')
            return redirect('checklists:modelo', pk=modelo.pk)
    modelos = Modelo.objects.prefetch_related('tipos_ativo', 'revisoes').order_by('codigo')
    return render(request, 'checklists/modelos.html', _ctx(
        request, 'modelos', modelos=modelos, importar_form=importar_form, novo_form=novo_form,
    ))


@admin_required
def modelo_view(request, pk):
    modelo = get_object_or_404(Modelo, pk=pk)
    revisao = modelo.revisao_vigente or modelo.revisoes.order_by('-numero').first()
    bloqueada = revisao.em_uso
    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'nova_revisao':
            nova = revisao.criar_proxima(notas=request.POST.get('notas', '').strip())
            messages.success(request, f'Revisão {nova.rotulo} criada. As execuções antigas continuam ligadas à revisão {revisao.rotulo}.')
            return redirect('checklists:modelo', pk=pk)
        if acao == 'dados':
            form = ModeloForm(request.POST, instance=modelo)
            rform = RevisaoForm(request.POST, instance=revisao)
            if form.is_valid() and rform.is_valid():
                form.save()
                rform.save()
                messages.success(request, 'Dados do modelo salvos.')
                return redirect('checklists:modelo', pk=pk)
            return _render_modelo(request, modelo, revisao, form, rform)
        if bloqueada:
            messages.error(request, f'A revisão {revisao.rotulo} já foi usada em execuções. Crie uma nova revisão para alterar os itens.')
            return redirect('checklists:modelo', pk=pk)
        if acao == 'nova_secao':
            form = SecaoForm(request.POST)
            if form.is_valid():
                Secao.objects.create(revisao=revisao, titulo=form.cleaned_data['titulo'], ordem=revisao.secoes.count())
        elif acao == 'secao':
            secao = get_object_or_404(Secao, pk=request.POST.get('id'), revisao=revisao)
            if request.POST.get('remover'):
                secao.delete()
            else:
                form = SecaoForm(request.POST, instance=secao)
                if form.is_valid():
                    form.save()
        elif acao == 'novo_item':
            secao = get_object_or_404(Secao, pk=request.POST.get('secao'), revisao=revisao)
            form = ItemForm(request.POST)
            if form.is_valid():
                item = form.save(commit=False)
                item.secao = secao
                item.ordem = secao.itens.count()
                item.save()
        elif acao == 'item':
            item = get_object_or_404(Item, pk=request.POST.get('id'), secao__revisao=revisao)
            if request.POST.get('remover'):
                item.delete()
            else:
                form = ItemForm(request.POST, instance=item)
                if form.is_valid():
                    form.save()
        return redirect(f'{request.path}#secoes')
    return _render_modelo(request, modelo, revisao, ModeloForm(instance=modelo), RevisaoForm(instance=revisao))


def _render_modelo(request, modelo, revisao, form, rform):
    secoes = [(s, list(s.itens.all())) for s in revisao.secoes.prefetch_related('itens')]
    return render(request, 'checklists/modelo.html', _ctx(
        request, 'modelos', modelo=modelo, revisao=revisao, form=form, rform=rform, secoes=secoes,
        bloqueada=revisao.em_uso, n_execucoes=revisao.execucoes.count(), novo_item=ItemForm(),
        tipos_resposta=TIPO_RESPOSTA_CHOICES, obs_choices=OBS_CHOICES,
        revisoes=modelo.revisoes.annotate(n=Count('execucoes')).order_by('-numero'),
    ))
