from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from accounts.models import User


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.ROLE_ADMIN:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def professor_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.ROLE_PROFESSOR:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper
