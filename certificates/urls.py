from django.urls import path

from . import views

app_name = 'certificates'

urlpatterns = [
    path('', views.verify_view, name='verify'),
]
