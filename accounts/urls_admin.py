from django.urls import path

from . import views_admin

app_name = 'accounts_admin'

urlpatterns = [
    path('', views_admin.usuarios_view, name='usuarios'),
    path('papeis/', views_admin.papeis_view, name='papeis'),
    path('papeis/<int:pk>/arquivar/', views_admin.papel_arquivar_view, name='papel_arquivar'),
]
