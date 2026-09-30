from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ['email']
    list_display = ['email', 'full_name', 'role', 'is_approved', 'is_active', 'is_staff']
    list_filter = ['role', 'is_approved', 'is_active', 'is_staff']
    search_fields = ['email', 'full_name', 'cpf']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Dados pessoais', {'fields': ('full_name', 'cpf', 'phone')}),
        ('Acesso', {'fields': ('role', 'is_approved', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'role', 'is_approved', 'password1', 'password2'),
        }),
    )
