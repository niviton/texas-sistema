from django.urls import path

from . import views_admin

app_name = 'accounts_admin'

urlpatterns = [
    path('', views_admin.usuarios_view, name='usuarios'),
]
