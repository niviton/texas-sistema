def pendencias(request):
    """Contador de pendências no menu (só para o administrador)."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not getattr(user, 'is_admin_geral', False):
        return {}
    from .pendencias import contar
    return {'n_pendencias': contar(user)}
