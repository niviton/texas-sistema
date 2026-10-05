from django.urls import path

from . import views

app_name = 'checklists'

urlpatterns = [
    path('', views.executar_view, name='executar'),
    path('executar/<int:ativo_pk>/', views.escolher_modelo_view, name='escolher_modelo'),
    path('executar/<int:ativo_pk>/<int:modelo_pk>/', views.execucao_nova_view, name='execucao_nova'),
    path('historico/', views.historico_view, name='historico'),
    path('historico/<int:pk>/', views.execucao_view, name='execucao'),
    path('historico/<int:pk>/pdf/', views.execucao_pdf_view, name='execucao_pdf'),
    path('historico/<int:pk>/reenviar/', views.execucao_reenviar_view, name='execucao_reenviar'),
    path('configuracoes/tipos/', views.tipos_view, name='tipos'),
    path('configuracoes/tipos/<int:pk>/arquivar/', views.tipo_arquivar_view, name='tipo_arquivar'),
    path('configuracoes/ativos/', views.ativos_view, name='ativos'),
    path('configuracoes/ativos/<int:pk>/arquivar/', views.ativo_arquivar_view, name='ativo_arquivar'),
    path('configuracoes/modelos/', views.modelos_view, name='modelos'),
    path('configuracoes/modelos/<int:pk>/', views.modelo_view, name='modelo'),
]
