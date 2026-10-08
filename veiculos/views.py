import logging

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from certificates.decorators import admin_required, veiculos_required
from dashboard.navigation import CONFIG_KEYS, CONFIG_TABS

from .emails import (
    enviar_alertas, enviar_emails_da_vistoria_em_segundo_plano, enviar_inspecao, enviar_teste, supervisor_emails,
)
from .forms import InspecaoForm, ManutencaoForm, MotoristaForm, SupervisorForm, VeiculoForm
from .carimbo import carimbo_da_requisicao
from .imagens import ImagemInvalida, assinatura_de_dataurl, comprimir_foto
from .pdf import pdf_filename, render_inspecao_pdf
from .models import (
    CATEGORIA_CAMINHONETE, CHECKLIST_ITEMS, FOTO_GRUPOS, FOTO_LABELS, FOTO_ORDEM, FOTO_POSICOES, PNEU_KEYS, ITEM_NOK, ITEM_OK, ITEM_STATUS_CHOICES, TIPO_CHEGADA, TIPO_CHOICES, TIPO_SAIDA,
    Inspecao, InspecaoFoto, InspecaoItem, Manutencao, Motorista, Supervisor, Uso, Veiculo,
)

logger = logging.getLogger(__name__)

_MAX_FOTOS_EXTRAS = 10

# Abas do dia a dia. Os cadastros ficam em "Configurações" (dashboard.navigation.CONFIG_TABS).
TABS_ADMIN = [
    ('painel', 'Painel', 'veiculos:painel'),
    ('nova', 'Nova vistoria', 'veiculos:inspecao_nova'),
    ('inspecoes', 'Vistorias', 'veiculos:inspecoes'),
    ('usos', 'Uso da frota', 'veiculos:usos'),
]
TABS_VISTORIADOR = [
    ('nova', 'Nova vistoria', 'veiculos:inspecao_nova'),
    ('inspecoes', 'Minhas vistorias', 'veiculos:inspecoes'),
    ('usos', 'Meus usos', 'veiculos:usos'),
]
TABS_LOGISTICA = [
    ('nova', 'Nova vistoria', 'veiculos:inspecao_nova'),
    ('inspecoes', 'Vistorias', 'veiculos:inspecoes'),
    ('usos', 'Uso da frota', 'veiculos:usos'),
]


def _ctx(request, active_tab, **extra):
    is_admin = request.user.is_admin_geral
    if active_tab in CONFIG_KEYS:
        base = {'active_nav': 'configuracoes', 'config_mode': True, 'config_tabs': CONFIG_TABS}
    else:
        if is_admin:
            tabs = TABS_ADMIN
        elif request.user.ve_todo_historico:
            tabs = TABS_LOGISTICA
        else:
            tabs = TABS_VISTORIADOR
        base = {'active_nav': 'veiculos', 'veic_tabs': tabs}
    return {**base, 'active_tab': active_tab, 'is_admin': is_admin, 've_tudo': request.user.ve_todo_historico, **extra}


def _inspecoes_visiveis(user):
    """Administrador e Logística veem todas; o Técnico, só as próprias."""
    qs = Inspecao.objects.all()
    if not user.ve_todo_historico:
        qs = qs.filter(Q(created_by=user) | Q(motorista__usuario=user))
    return qs


def _usos_visiveis(user):
    qs = Uso.objects.all()
    if not user.ve_todo_historico:
        qs = qs.filter(Q(motorista__usuario=user) | Q(inspecao_saida__created_by=user))
    return qs


@veiculos_required
def painel_view(request):
    if not request.user.is_admin_geral:
        return redirect('veiculos:inspecoes')
    veiculos = list(Veiculo.objects.filter(is_active=True).select_related('motorista_responsavel'))
    linhas = []
    alertas = []
    hoje = timezone.localdate()
    for v in veiculos:
        ultima = v.ultima_inspecao
        dias_sem = (hoje - timezone.localtime(ultima.created_at).date()).days if ultima else None
        atrasado = dias_sem is None or dias_sem >= v.checklist_frequencia_dias
        linhas.append({'v': v, 'uso': v.uso_aberto, 'ultima': ultima, 'dias_sem': dias_sem, 'atrasado': atrasado})
        for nome, data, dias in v.vencimentos():
            alertas.append({'v': v, 'nome': nome, 'data': data, 'dias': dias})
    alertas.sort(key=lambda a: a['dias'] if a['dias'] is not None else -999)
    problemas = Inspecao.objects.filter(tem_problema=True).select_related('veiculo', 'motorista')[:6]
    return render(request, 'veiculos/painel.html', _ctx(
        request, 'painel', linhas=linhas, alertas=alertas, problemas=problemas,
        total=len(veiculos), em_uso=sum(1 for l in linhas if l['uso']),
        atrasados=sum(1 for l in linhas if l['atrasado']),
    ))


def _checklist_from_post(post):
    """Monta as seções do checklist com o que foi marcado (ou OK por padrão)."""
    valid = {k for k, _ in ITEM_STATUS_CHOICES}
    secoes = []
    for secao, itens in CHECKLIST_ITEMS:
        linhas = []
        for key, label in itens:
            status = post.get(f'item_{key}', ITEM_OK)
            linhas.append({
                'key': key, 'label': label,
                'status': status if status in valid else ITEM_OK,
                'obs': post.get(f'obs_{key}', '')[:255],
            })
        secoes.append((secao, linhas))
    return secoes


# Caminho da vistoria, uma pergunta por tela (mesma lógica dos checklists de equipamentos):
#   tipo (saída, chegada, rotina) -> veículo -> formulário.
_TIPO_DESCRICAO = {
    'saida': 'Vou pegar um veículo',
    'chegada': 'Vou devolver o veículo que estou usando',
    'rotina': 'Vistoria periódica, sem sair com o veículo',
}


def _escolha_vistoria(request):
    tipos = dict(TIPO_CHOICES)
    tipo = request.GET.get('tipo')
    base = reverse('veiculos:inspecao_nova')
    if tipo not in tipos:
        return {
            'pergunta': 'Qual vistoria você vai fazer?',
            'opcoes': [{'titulo': rotulo, 'detalhe': _TIPO_DESCRICAO[valor], 'url': f'{base}?tipo={valor}'} for valor, rotulo in TIPO_CHOICES],
        }
    opcoes = []
    for v in Veiculo.objects.filter(is_active=True).order_by('placa'):
        uso = v.uso_aberto
        op = {'titulo': v.placa, 'detalhe': f'{v.marca} {v.modelo}'.strip(), 'url': f'{base}?tipo={tipo}&veiculo={v.pk}'}
        if tipo == TIPO_SAIDA and uso:
            op.update(off=True, selo=f'Em uso: {uso.motorista.name.split()[0]}' if uso.motorista else 'Em uso')
        if tipo == TIPO_CHEGADA:
            if not uso:
                continue
            if not request.user.is_admin_geral and (not uso.motorista or uso.motorista.usuario_id != request.user.pk):
                continue
            op['selo'] = f'Saiu {timezone.localtime(uso.saida_em):%d/%m %H:%M}'
        opcoes.append(op)
    return {
        'passos': [('Veículos', base), (tipos[tipo], None)],
        'pergunta': 'Qual veículo?',
        'ajuda': {'saida': 'Veículos em uso aparecem bloqueados até a chegada ser registrada.',
                  'chegada': 'Só aparecem os veículos com saída em aberto.'}.get(tipo, ''),
        'opcoes': opcoes,
        'vazio': 'Nenhum veículo com saída em aberto para você.' if tipo == TIPO_CHEGADA else 'Nenhum veículo cadastrado.',
    }


@veiculos_required
def inspecao_nova_view(request):
    if request.method != 'POST' and not (request.GET.get('veiculo') and request.GET.get('tipo')):
        return render(request, 'veiculos/inspecao_passos.html', _ctx(request, 'nova', escolha=_escolha_vistoria(request)))
    initial = {}
    if request.GET.get('veiculo'):
        initial['veiculo'] = request.GET['veiculo']
    if request.GET.get('tipo'):
        initial['tipo'] = request.GET['tipo']

    if request.method == 'POST':
        form = InspecaoForm(request.POST, user=request.user)
        secoes = _checklist_from_post(request.POST)
        fotos = [(key, request.FILES.get(f'foto_{key}')) for key, _, _ in FOTO_POSICOES]
        extras = request.FILES.getlist('fotos_extra')
        nok_sem_obs = [l['label'] for _, ls in secoes for l in ls if l['status'] == ITEM_NOK and not l['obs'].strip()]
        if nok_sem_obs:
            form.add_error(None, 'Descreva o problema nos itens marcados como "Não OK": ' + ', '.join(nok_sem_obs) + '.')
        faltando = [label for (key, label, obrigatoria), (_, f) in zip(FOTO_POSICOES, fotos) if obrigatoria and not f]
        if faltando:
            form.add_error(None, 'Faltam as fotos: ' + ', '.join(faltando) + '.')
        pneus_pct = {}
        sem_pct = []
        for key in PNEU_KEYS:
            try:
                valor = int(request.POST.get(f'pct_{key}', ''))
            except ValueError:
                valor = None
            if valor is None or not 0 <= valor <= 100:
                sem_pct.append(FOTO_LABELS[key])
            else:
                pneus_pct[key] = valor
        if sem_pct:
            form.add_error(None, 'Informe o estado (0 a 100%) de: ' + ', '.join(sem_pct) + '.')
        if len(extras) > _MAX_FOTOS_EXTRAS:
            form.add_error(None, f'Envie no máximo {_MAX_FOTOS_EXTRAS} fotos adicionais.')
        assinatura = None
        try:
            assinatura = assinatura_de_dataurl(request.POST.get('assinatura', ''))
            if assinatura is None:
                form.add_error(None, 'Falta a assinatura do motorista.')
        except ImagemInvalida as exc:
            form.add_error(None, str(exc))
        if form.is_valid():
            try:
                inspecao = _salvar_inspecao(request, form.cleaned_data, secoes, fotos, extras, assinatura, pneus_pct)
            except ImagemInvalida as exc:
                form.add_error(None, str(exc))
            else:
                if supervisor_emails('veiculos'):
                    enviar_emails_da_vistoria_em_segundo_plano(inspecao.pk)
                    messages.success(request, 'Vistoria registrada. O comprovante está sendo enviado aos supervisores.')
                else:
                    messages.success(request, 'Vistoria registrada. (Ninguém cadastrado para receber o e-mail das vistorias.)')
                return redirect('veiculos:inspecao_detalhe', pk=inspecao.pk)
    else:
        form = InspecaoForm(initial=initial, user=request.user)
        secoes = _checklist_from_post({})

    veiculos_info = {
        str(v.pk): {
            'km': v.km_atual, 'motorista': v.motorista_responsavel_id, 'em_uso': bool(v.uso_aberto),
            'caminhonete': v.categoria == CATEGORIA_CAMINHONETE,
            'manutencoes': [
                {
                    'nome': m.nome, 'proximo_km': m.proximo_km, 'intervalo_km': m.intervalo_km, 'aviso_km': m.aviso_km,
                    'data': m.proxima_data.strftime('%d/%m/%Y') if m.proxima_data else None,
                    'dias': (m.proxima_data - timezone.localdate()).days if m.proxima_data else None,
                    'aviso_dias': m.aviso_dias,
                }
                for m in v.manutencoes.filter(is_active=True)
            ],
            'vencimentos': [
                {'nome': nome, 'data': d.strftime('%d/%m/%Y'), 'dias': (d - timezone.localdate()).days}
                for nome, d in [('Licenciamento', v.licenciamento_validade), ('Seguro', v.seguro_validade), ('Revisão', v.revisao_data)]
                if d
            ],
        }
        for v in Veiculo.objects.filter(is_active=True)
    }
    dados = request.POST if request.method == 'POST' else request.GET
    tipo_txt = dict(TIPO_CHOICES).get(dados.get('tipo'), '')
    veic = Veiculo.objects.filter(pk=dados.get('veiculo')).first() if str(dados.get('veiculo', '')).isdigit() else None
    base = reverse('veiculos:inspecao_nova')
    passos = [('Veículos', base)] + ([(tipo_txt, f"{base}?tipo={dados.get('tipo')}")] if tipo_txt else []) + ([(veic.placa, None)] if veic else [])
    passos[-1] = (passos[-1][0], None)
    return render(request, 'veiculos/inspecao_form.html', _ctx(
        request, 'nova', form=form, secoes=secoes, veiculos_info=veiculos_info, passos=passos,
        foto_grupos=_foto_grupos(), max_extras=_MAX_FOTOS_EXTRAS,
        nome_condutor='' if request.user.is_admin_geral else (request.user.full_name or request.user.email),
    ))


def _foto_grupos():
    obrig = {k: req for k, _, req in FOTO_POSICOES}
    return [
        (grupo, [{'key': k, 'label': FOTO_LABELS[k], 'req': obrig[k], 'pneu': k in PNEU_KEYS} for k in keys])
        for grupo, keys in FOTO_GRUPOS
    ]


@transaction.atomic
def _salvar_inspecao(request, data, secoes, fotos, extras, assinatura, pneus_pct):
    veiculo = data['veiculo']
    tem_problema = any(l['status'] == ITEM_NOK for _, ls in secoes for l in ls)
    inspecao = Inspecao.objects.create(
        veiculo=veiculo, motorista=data['motorista'], tipo=data['tipo'], km=data['km'],
        combustivel_pct=data['combustivel_pct'],
        com_carga=(data['com_carga'] == 'sim') if veiculo.categoria == CATEGORIA_CAMINHONETE else None, observacoes=data['observacoes'],
        tem_problema=tem_problema, created_by=request.user, assinatura=assinatura,
    )
    InspecaoItem.objects.bulk_create([
        InspecaoItem(inspecao=inspecao, item=l['key'], status=l['status'], observacao=l['obs'])
        for _, ls in secoes for l in ls
    ])
    carimbo = carimbo_da_requisicao(request)
    for key, f in fotos:
        if f:
            InspecaoFoto.objects.create(
                inspecao=inspecao, posicao=key, imagem=comprimir_foto(f, carimbo), percentual=pneus_pct.get(key),
            )
    for f in extras:
        InspecaoFoto.objects.create(inspecao=inspecao, imagem=comprimir_foto(f, carimbo))

    if data['tipo'] == TIPO_SAIDA:
        Uso.objects.create(
            veiculo=veiculo, motorista=data['motorista'],
            saida_em=inspecao.created_at, km_saida=data['km'], inspecao_saida=inspecao,
        )
    elif data['tipo'] == TIPO_CHEGADA:
        uso = veiculo.uso_aberto
        uso.chegada_em = inspecao.created_at
        uso.km_chegada = data['km']
        uso.inspecao_chegada = inspecao
        uso.save()

    if data['km'] > veiculo.km_atual:
        veiculo.km_atual = data['km']
        veiculo.save(update_fields=['km_atual'])
    return inspecao


@veiculos_required
def inspecoes_view(request):
    qs = _inspecoes_visiveis(request.user).select_related('veiculo', 'motorista').prefetch_related('fotos')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(veiculo__placa__icontains=q) | Q(motorista__name__icontains=q) | Q(veiculo__modelo__icontains=q))
    if request.GET.get('problema') == '1':
        qs = qs.filter(tem_problema=True)
    if request.GET.get('tipo'):
        qs = qs.filter(tipo=request.GET['tipo'])
    return render(request, 'veiculos/inspecoes.html', _ctx(request, 'inspecoes', inspecoes=qs[:200], q=q))


@veiculos_required
def inspecao_detalhe_view(request, pk):
    inspecao = get_object_or_404(
        _inspecoes_visiveis(request.user).select_related('veiculo', 'motorista', 'created_by').prefetch_related('itens', 'fotos'),
        pk=pk,
    )
    labels = {k: l for _, itens in CHECKLIST_ITEMS for k, l in itens}
    por_item = {i.item: i for i in inspecao.itens.all()}
    secoes = [
        (secao, [por_item[k] for k, _ in itens if k in por_item])
        for secao, itens in CHECKLIST_ITEMS
    ]
    fotos = sorted(inspecao.fotos.all(), key=lambda f: (FOTO_ORDEM.get(f.posicao, 999), f.pk))
    return render(request, 'veiculos/inspecao_detalhe.html', _ctx(
        request, 'inspecoes', inspecao=inspecao, secoes=secoes, labels=labels, fotos=fotos,
    ))


@veiculos_required
def inspecao_pdf_view(request, pk):
    inspecao = get_object_or_404(_inspecoes_visiveis(request.user).select_related('veiculo', 'motorista', 'created_by'), pk=pk)
    response = HttpResponse(render_inspecao_pdf(inspecao), content_type='application/pdf')
    disposition = 'attachment' if request.GET.get('download') else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{pdf_filename(inspecao)}"'
    return response


@veiculos_required
def inspecao_reenviar_view(request, pk):
    inspecao = get_object_or_404(_inspecoes_visiveis(request.user), pk=pk)
    if request.method == 'POST':
        try:
            if enviar_inspecao(inspecao):
                messages.success(request, 'E-mail reenviado aos supervisores.')
            else:
                messages.error(request, 'Ninguém cadastrado para receber este e-mail (Configurações → Notificações).')
        except Exception as exc:
            messages.error(request, f'Falha ao enviar e-mail: {exc}')
    return redirect('veiculos:inspecao_detalhe', pk=pk)


@veiculos_required
def usos_view(request):
    usos = _usos_visiveis(request.user).select_related('veiculo', 'motorista', 'inspecao_saida')
    if request.GET.get('abertos') == '1':
        usos = usos.filter(chegada_em__isnull=True)
    return render(request, 'veiculos/usos.html', _ctx(request, 'usos', usos=usos[:200]))


# ---------- Cadastros (somente administrador) ----------

def _crud(request, model, form_class, template, tab, redirect_name, success_msg, **extra):
    editing = None
    if request.GET.get('edit'):
        editing = get_object_or_404(model, pk=request.GET['edit'])
    if request.method == 'POST':
        instance = get_object_or_404(model, pk=request.POST['editing_id']) if request.POST.get('editing_id') else None
        form = form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, success_msg)
            return redirect(redirect_name)
        editing = instance
    else:
        inicial = None if editing else {k: v for k, v in request.GET.items() if k in form_class.base_fields}
        form = form_class(instance=editing, initial=inicial)
    show_archived = request.GET.get('arquivados') == '1'
    objects = model.objects.all() if show_archived else model.objects.filter(is_active=True)
    return render(request, template, _ctx(
        request, tab, form=form, editing=editing, objects=objects, show_archived=show_archived, **extra,
    ))


def _toggle_active(request, model, pk, redirect_name):
    obj = get_object_or_404(model, pk=pk)
    if request.method == 'POST':
        obj.is_active = not obj.is_active
        obj.save(update_fields=['is_active'])
        messages.success(request, f'{obj} {"reativado" if obj.is_active else "arquivado"}.')
    return redirect(redirect_name)


@admin_required
def veiculos_view(request):
    return _crud(request, Veiculo, VeiculoForm, 'veiculos/veiculos.html', 'veiculos', 'veiculos:veiculos', 'Veículo salvo.')


@admin_required
def veiculo_arquivar_view(request, pk):
    return _toggle_active(request, Veiculo, pk, 'veiculos:veiculos')


@admin_required
def manutencoes_view(request, pk):
    veiculo = get_object_or_404(Veiculo, pk=pk)
    editing = None
    if request.GET.get('edit'):
        editing = get_object_or_404(Manutencao, pk=request.GET['edit'], veiculo=veiculo)
    if request.method == 'POST':
        acao = request.POST.get('acao', 'salvar')
        if acao in ('feita', 'remover'):
            m = get_object_or_404(Manutencao, pk=request.POST.get('id'), veiculo=veiculo)
            if acao == 'feita':
                m.registrar_feita(veiculo.km_atual)
                messages.success(request, f'{m.nome}: registrada como feita, próxima atualizada.')
            else:
                m.delete()
                messages.success(request, f'{m.nome}: removida.')
            return redirect('veiculos:manutencoes', pk=veiculo.pk)
        if request.POST.get('editing_id'):
            instance = get_object_or_404(Manutencao, pk=request.POST['editing_id'], veiculo=veiculo)
        else:
            instance = Manutencao(veiculo=veiculo)
        form = ManutencaoForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Manutenção salva.')
            return redirect('veiculos:manutencoes', pk=veiculo.pk)
        editing = instance if instance.pk else None
    else:
        form = ManutencaoForm(instance=editing)
    itens = [
        {'m': m, 'faltam_km': m.km_restante(veiculo.km_atual), 'alertas': m.alertas(veiculo.km_atual)}
        for m in veiculo.manutencoes.all()
    ]
    return render(request, 'veiculos/manutencoes.html', _ctx(
        request, 'veiculos', veiculo=veiculo, form=form, editing=editing, itens=itens,
    ))


@admin_required
def motoristas_view(request):
    return _crud(request, Motorista, MotoristaForm, 'veiculos/motoristas.html', 'motoristas', 'veiculos:motoristas', 'Motorista salvo.')


@admin_required
def motorista_arquivar_view(request, pk):
    return _toggle_active(request, Motorista, pk, 'veiculos:motoristas')


@admin_required
def supervisores_view(request):
    return _crud(request, Supervisor, SupervisorForm, 'veiculos/supervisores.html', 'supervisores', 'veiculos:supervisores', 'Destinatário salvo.')


@admin_required
def supervisor_arquivar_view(request, pk):
    return _toggle_active(request, Supervisor, pk, 'veiculos:supervisores')


@admin_required
def email_view(request):
    if request.method == 'POST':
        acao = request.POST.get('acao')
        try:
            if acao == 'teste':
                destino = request.POST.get('destino', '').strip() or request.user.email
                enviar_teste(destino)
                messages.success(request, f'E-mail de teste enviado para {destino}.')
            elif acao == 'alertas':
                venc, lemb = enviar_alertas()
                messages.success(request, f'Alertas processados: {venc} vencimento(s) e {lemb} lembrete(s) de checklist enviados.')
        except Exception as exc:
            logger.exception('Falha no envio de e-mail')
            messages.error(request, f'Falha ao enviar: {exc}')
        return redirect('veiculos:email')
    return render(request, 'veiculos/email.html', _ctx(
        request, 'email',
        configurado=bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD),
        remetente=settings.EMAIL_HOST_USER, supervisores=supervisor_emails(),
    ))
