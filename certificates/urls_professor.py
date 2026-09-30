from django.urls import path

from . import views_professor

app_name = 'cert_prof'

urlpatterns = [
    path('', views_professor.folders_view, name='folders'),
    path('<int:template_id>/', views_professor.groups_view, name='groups'),
    path('<int:template_id>/cadastrar/', views_professor.form_view, name='form'),
]
