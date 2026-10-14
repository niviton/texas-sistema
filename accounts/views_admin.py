from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from certificates.decorators import admin_required

from dashboard.navigation import CONFIG_TABS

from .forms import AdminUserEditForm, PapelForm
from .models import Papel, User


@admin_required
def usuarios_view(request):
    editing = None
    edit_id = request.GET.get('edit')
    if edit_id:
        editing = get_object_or_404(User, pk=edit_id)

    if request.method == 'POST':
        instance = get_object_or_404(User, pk=request.POST.get('editing_id'))
        form = AdminUserEditForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, f'Usuário {instance.full_name} atualizado.')
            return redirect('accounts_admin:usuarios')
        editing = instance
    else:
        form = AdminUserEditForm(instance=editing) if editing else None

    users = User.objects.all().order_by('full_name')
    return render(request, 'accounts/usuarios.html', {
        'active_nav': 'configuracoes',
        'config_tabs': CONFIG_TABS,
        'active_tab': 'usuarios',
        'users': users,
        'editing': editing,
        'form': form,
    })


@admin_required
def papeis_view(request):
    """Papéis e acessos: o administrador cria papéis (ex.: Motorista) e marca o que cada um pode usar."""
    from django.db.models import Count

    from veiculos.views import _crud
    return _crud(request, Papel, PapelForm, 'accounts/papeis.html', 'papeis', 'accounts_admin:papeis', 'Papel salvo.',
                 contagem={p.pk: p.n for p in Papel.objects.annotate(n=Count('usuarios'))})


@admin_required
def papel_arquivar_view(request, pk):
    from veiculos.views import _toggle_active
    return _toggle_active(request, Papel, pk, 'accounts_admin:papeis')
