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
        {'quando': e.created_at, 'titulo': e.ativo.nome, 'detalhe': f'Pré-uso {e.revisao.modelo.codigo}',
         'problema': e.tem_problema, 'url': reverse('checklists:execucao', args=[e.pk])}
        for e in execucoes[:5]
    ]
    ultimos.sort(key=lambda x: x['quando'], reverse=True)

    n_avisos = 0
    if user.is_admin_geral:
        n_avisos = sum(len(alertas_texto(v)) for v in Veiculo.objects.filter(is_active=True))
    return {'em_uso': list(em_uso), 'ultimos': ultimos[:5], 'n_avisos': n_avisos}


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
