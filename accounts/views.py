from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.shortcuts import redirect, render

from .forms import EmailAuthenticationForm, RegisterForm
from .models import FONTES, TEMA_CHOICES


def auth_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')

    tab = request.POST.get('form_type') or request.GET.get('tab') or 'login'
    submitted = False
    register_first_name = ''
    register_email = ''

    login_form = EmailAuthenticationForm(request, data=request.POST if (request.method == 'POST' and tab == 'login') else None)
    register_form = RegisterForm(request.POST if (request.method == 'POST' and tab == 'register') else None)

    if request.method == 'POST' and tab == 'login':
        if login_form.is_valid():
            auth_login(request, login_form.get_user())
            return redirect('dashboard:home')
    elif request.method == 'POST' and tab == 'register':
        if register_form.is_valid():
            user = register_form.save()
            submitted = True
            register_first_name = user.first_name_display
            register_email = user.email
            register_form = RegisterForm()
            tab = 'register'

    context = {
        'tab': tab,
        'login_form': login_form,
        'register_form': register_form,
        'submitted': submitted,
        'register_first_name': register_first_name,
        'register_email': register_email,
    }
    return render(request, 'accounts/auth.html', context)


class PolarisLogoutView(LogoutView):
    next_page = 'accounts:auth'


@login_required
def aparencia_view(request):
    """Cada pessoa escolhe a fonte e o tema (claro, escuro ou automático) do próprio Polaris."""
    if request.method == 'POST':
        tema = request.POST.get('tema')
        fonte = request.POST.get('fonte')
        if tema in dict(TEMA_CHOICES) and fonte in FONTES:
            request.user.tema = tema
            request.user.fonte = fonte
            request.user.save(update_fields=['tema', 'fonte'])
            messages.success(request, 'Aparência salva.')
        return redirect('accounts:aparencia')
    fontes = [{'chave': k, 'rotulo': v[0], 'css': v[1], 'google': v[2]} for k, v in FONTES.items()]
    return render(request, 'accounts/aparencia.html', {
        'active_nav': 'aparencia', 'fontes': fontes, 'temas': TEMA_CHOICES,
    })
