from datetime import date

from django.contrib.auth.decorators import login_required
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


def _resumo_veiculos(user):
    """Painel simples da frota para a tela inicial de quem tem acesso a veículos."""
    from veiculos.emails import alertas_texto
    from veiculos.models import Inspecao, Uso, Veiculo

    veiculos = list(Veiculo.objects.filter(is_active=True).select_related('motorista_responsavel'))
    em_uso = list(Uso.objects.filter(chegada_em__isnull=True).select_related('veiculo', 'motorista').order_by('saida_em'))
    alertas = []
    for v in veiculos:
        alertas += [(v, texto) for texto in alertas_texto(v)]
    return {
        'total': len(veiculos),
        'em_uso': em_uso,
        'disponiveis': len(veiculos) - len(em_uso),
        'alertas': alertas[:5],
        'n_alertas': len(alertas),
        'minhas': Inspecao.objects.filter(created_by=user).select_related('veiculo')[:5],
    }


@login_required
def home(request):
    today = date.today()
    today_label = f'{_WEEKDAYS[today.weekday()]}, {today.day} de {_MONTHS[today.month - 1]} de {today.year}'

    context = {
        'is_admin': request.user.role == User.ROLE_ADMIN,
        'today_label': today_label,
        'active_nav': 'inicio',
        'frota': _resumo_veiculos(request.user) if request.user.pode_veiculos else None,
    }
    return render(request, 'dashboard/dashboard.html', context)
