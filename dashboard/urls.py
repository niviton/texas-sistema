from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('novo/', views.novo_view, name='novo'),
    path('historico/', views.historico_view, name='historico'),
    path('concluido/<str:tipo>/<int:pk>/', views.concluido_view, name='concluido'),
    path('conferir/<str:tipo>/<int:pk>/', views.conferir_view, name='conferir'),
    path('etiquetas/', views.etiquetas_view, name='etiquetas'),
    path('q/e/<int:pk>/', views.qr_equipamento_view, name='qr_equipamento'),
    path('q/v/<int:pk>/', views.qr_veiculo_view, name='qr_veiculo'),
]
