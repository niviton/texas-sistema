from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied



def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin_geral:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def veiculos_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.pode_veiculos:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def checklists_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.pode_checklists:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def termos_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.pode_termos:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def professor_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.pode_certificados:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper
