from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from accounts.models import User

_WEEKDAYS = [
    'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira',
    'sexta-feira', 'sábado', 'domingo',
]
_MONTHS = [
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]


def _resumo_checklists(user):
    """Só o que pede ação na tela inicial: veículos em uso, avisos (admin) e os últimos registros."""
    from django.urls import reverse

    from checklists.models import Execucao
    from veiculos.emails import alertas_texto
    from veiculos.models import Inspecao, Uso, Veiculo

    em_uso = Uso.objects.filter(chegada_em__isnull=True).select_related('veiculo', 'motorista').order_by('saida_em')
    vistorias = Inspecao.objects.select_related('veiculo')
    execucoes = Execucao.objects.select_related('ativo', 'revisao__modelo')
    if not user.ve_todo_historico:
        em_uso = em_uso.filter(Q(motorista__usuario=user) | Q(inspecao_saida__created_by=user))
        vistorias = vistorias.filter(Q(created_by=user) | Q(motorista__usuario=user))
        execucoes = execucoes.filter(executor=user)

    ultimos = [
        {'quando': v.created_at, 'titulo': v.veiculo.placa, 'detalhe': f'Vistoria de {v.get_tipo_display().lower()}',
         'problema': v.tem_problema, 'url': reverse('veiculos:inspecao_detalhe', args=[v.pk])}
        for v in vistorias[:5]
    ] + [
        {'quando': e.created_at, 'titulo': e.ativo.nome, 'detalhe': f'{e.revisao.modelo.get_finalidade_display()} {e.revisao.modelo.codigo}',
         'problema': e.tem_problema, 'url': reverse('checklists:execucao', args=[e.pk])}
        for e in execucoes[:5]
    ]
    ultimos.sort(key=lambda x: x['quando'], reverse=True)

    n_avisos = 0
    if user.is_admin_geral:
        n_avisos = sum(len(alertas_texto(v)) for v in Veiculo.objects.filter(is_active=True))
    return {'em_uso': list(em_uso), 'ultimos': ultimos[:5], 'n_avisos': n_avisos}


def certificado_view(request):
    """Página pública com o certificado da rede local para instalar no celular (tira o aviso de site inseguro)."""
    from django.conf import settings
    from django.http import Http404, HttpResponse

    ca = settings.BASE_DIR / 'ssl_local' / 'polaris-ca.crt'
    if request.GET.get('baixar'):
        if not ca.exists():
            raise Http404
        resp = HttpResponse(ca.read_bytes(), content_type='application/x-x509-ca-cert')
        resp['Content-Disposition'] = 'attachment; filename="polaris-ca.crt"'
        return resp
    return render(request, 'dashboard/certificado.html', {'tem_certificado': ca.exists()})


@login_required
def home(request):
    today = date.today()
    today_label = f'{_WEEKDAYS[today.weekday()]}, {today.day} de {_MONTHS[today.month - 1]} de {today.year}'

    context = {
        'is_admin': request.user.role == User.ROLE_ADMIN,
        'today_label': today_label,
        'active_nav': 'inicio',
        'resumo': _resumo_checklists(request.user) if request.user.pode_checklists else None,
    }
    return render(request, 'dashboard/dashboard.html', context)


# ------------------------------------------------------------ Registros (vistoria, checklist e termo juntos)

def _registros_required(view):
    from functools import wraps

    from django.core.exceptions import PermissionDenied

    from .registros import tipos_permitidos

    @wraps(view)
    @login_required
    def inner(request, *args, **kwargs):
        if not tipos_permitidos(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return inner


@_registros_required
def novo_view(request):
    """Ponto de partida único: o que você vai registrar? Daí seguem os passos de cada módulo."""
    from django.shortcuts import redirect
    from django.urls import reverse

    from .registros import TIPO_CHECKLIST, TIPO_TERMO, TIPO_VISTORIA, tipos_permitidos

    opcoes_por_tipo = {
        TIPO_VISTORIA: {'titulo': 'Veículo', 'detalhe': 'Vistoria de saída, chegada ou rotina',
                        'url': reverse('veiculos:inspecao_nova')},
        TIPO_CHECKLIST: {'titulo': 'Equipamento', 'detalhe': 'Checklist de pré-uso, inspeção ou manutenção',
                         'url': reverse('checklists:executar')},
        TIPO_TERMO: {'titulo': 'Termo de material', 'detalhe': 'Entrada ou saída de material de cliente, com assinaturas',
                     'url': reverse('termos:novo')},
    }
    opcoes = [opcoes_por_tipo[t] for t in tipos_permitidos(request.user)]
    if len(opcoes) == 1:
        return redirect(opcoes[0]['url'])
    escolha = {'pergunta': 'O que você vai registrar?', 'opcoes': opcoes}
    return render(request, 'dashboard/novo.html', {'active_nav': 'novo', 'escolha': escolha})


@_registros_required
def historico_view(request):
    """Histórico único: tudo o que a pessoa pode ver, com filtros por tipo, texto, pessoa e período."""
    from datetime import date as _date

    from .registros import TIPOS, buscar, tipos_permitidos

    def data(nome):
        try:
            return _date.fromisoformat(request.GET.get(nome, ''))
        except ValueError:
            return None

    user = request.user
    tipo = request.GET.get('tipo', '')
    q = request.GET.get('q', '').strip()
    pessoa = None
    pessoas = []
    if user.ve_todo_historico:
        pessoas = User.objects.filter(is_active=True).exclude(role=User.ROLE_PROFESSOR).order_by('full_name')
        pid = request.GET.get('pessoa', '')
        pessoa = pessoas.filter(pk=pid).first() if pid.isdigit() else None
    de, ate = data('de'), data('ate')
    so_problema = request.GET.get('problema') == '1'
    registros = buscar(user, tipo, q, pessoa, de, ate)
    if so_problema:
        registros = [r for r in registros if r.problema]
    permitidos = tipos_permitidos(user)
    return render(request, 'dashboard/historico.html', {
        'active_nav': 'historico', 'registros': registros, 'tipos': [t for t in TIPOS if t[0] in permitidos],
        'f': {'tipo': tipo, 'q': q, 'pessoa': pessoa.pk if pessoa else '', 'de': de, 'ate': ate, 'problema': so_problema},
        'pessoas': pessoas, 'filtrado': bool(tipo or q or pessoa or de or ate or so_problema),
    })


@_registros_required
def concluido_view(request, tipo, pk):
    """Depois de enviar: confirmação clara e os próximos passos."""
    from django.urls import reverse

    from .registros import TIPO_CHECKLIST, TIPO_VISTORIA, como_registro, pegar

    obj = pegar(request.user, tipo, pk)
    reg = como_registro(tipo, obj)
    if tipo == TIPO_VISTORIA:
        titulo = 'Vistoria registrada'
        outro = ('Nova vistoria deste veículo', reverse('veiculos:inspecao_nova') + f'?veiculo={obj.veiculo_id}')
    elif tipo == TIPO_CHECKLIST:
        titulo = 'Checklist registrado'
        outro = ('Outro checklist neste equipamento', reverse('checklists:escolher_modelo', args=[obj.ativo_id]))
    else:
        titulo = 'Termo finalizado'
        outro = ('Novo termo', reverse('termos:novo'))
    return render(request, 'dashboard/concluido.html', {
        'active_nav': 'novo', 'titulo': titulo, 'reg': reg, 'outro': outro,
    })
