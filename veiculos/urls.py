from django.urls import path

from . import views

app_name = 'veiculos'

urlpatterns = [
    path('', views.painel_view, name='painel'),
    path('inspecao/nova/', views.inspecao_nova_view, name='inspecao_nova'),
    path('inspecoes/', views.inspecoes_view, name='inspecoes'),
    path('inspecoes/<int:pk>/', views.inspecao_detalhe_view, name='inspecao_detalhe'),
    path('inspecoes/<int:pk>/pdf/', views.inspecao_pdf_view, name='inspecao_pdf'),
    path('inspecoes/<int:pk>/reenviar/', views.inspecao_reenviar_view, name='inspecao_reenviar'),
    path('uso/', views.usos_view, name='usos'),
    path('cadastro/veiculos/', views.veiculos_view, name='veiculos'),
    path('cadastro/veiculos/<int:pk>/arquivar/', views.veiculo_arquivar_view, name='veiculo_arquivar'),
    path('cadastro/veiculos/<int:pk>/manutencoes/', views.manutencoes_view, name='manutencoes'),
    path('cadastro/motoristas/', views.motoristas_view, name='motoristas'),
    path('cadastro/motoristas/<int:pk>/arquivar/', views.motorista_arquivar_view, name='motorista_arquivar'),
    path('cadastro/supervisores/', views.supervisores_view, name='supervisores'),
    path('cadastro/supervisores/<int:pk>/arquivar/', views.supervisor_arquivar_view, name='supervisor_arquivar'),
    path('emails/', views.email_view, name='email'),
]
