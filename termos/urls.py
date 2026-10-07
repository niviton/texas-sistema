from django.urls import path

from . import views

app_name = 'termos'

urlpatterns = [
    path('', views.lista_view, name='lista'),
    path('novo/', views.novo_view, name='novo'),
    path('<int:pk>/', views.detalhe_view, name='detalhe'),
    path('<int:pk>/editar/', views.editar_view, name='editar'),
    path('<int:pk>/pdf/', views.pdf_view, name='pdf'),
    path('<int:pk>/reenviar/', views.reenviar_view, name='reenviar'),
    path('<int:pk>/excluir/', views.excluir_view, name='excluir'),
    path('configuracoes/', views.documentos_view, name='documentos'),
]
