from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.auth_view, name='auth'),
    path('sair/', views.PolarisLogoutView.as_view(), name='logout'),
    path('aparencia/', views.aparencia_view, name='aparencia'),
]
