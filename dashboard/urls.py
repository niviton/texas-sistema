from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('novo/', views.novo_view, name='novo'),
    path('historico/', views.historico_view, name='historico'),
    path('concluido/<str:tipo>/<int:pk>/', views.concluido_view, name='concluido'),
]
