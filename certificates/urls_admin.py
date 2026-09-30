from django.urls import path

from . import views_admin

app_name = 'cert_admin'

urlpatterns = [
    path('pendentes/', views_admin.pendentes_view, name='pendentes'),
    path('emitir/', views_admin.emitir_view, name='emitir'),
    path('emitir/preview-ajax/', views_admin.emitir_preview_ajax_view, name='emitir_preview_ajax'),
    path('emitir/cpf-lookup/', views_admin.cpf_lookup_ajax_view, name='cpf_lookup'),
    path('historico/', views_admin.historico_view, name='historico'),
    path('historico/zip-grupo/', views_admin.historico_zip_group_view, name='historico_zip_group'),
    path('historico/zip/', views_admin.historico_zip_selected_view, name='historico_zip_selected'),
    path('professores/', views_admin.professores_view, name='professores'),
    path('professores/<int:pk>/remover/', views_admin.professor_remove_view, name='professor_remove'),
    path('professores/<int:pk>/arquivar/', views_admin.professor_archive_view, name='professor_archive'),
    path('importar/', views_admin.importar_view, name='importar'),
    path('modelos/', views_admin.modelos_view, name='modelos'),
    path('modelos/<int:pk>/remover/', views_admin.modelo_remove_view, name='modelo_remove'),
    path('certificado/<int:pk>/pdf/', views_admin.certificate_pdf_view, name='certificate_pdf'),
    path('certificado/<int:pk>/preview.png', views_admin.certificate_preview_view, name='certificate_preview'),
    path('certificado/<int:pk>/apagar/', views_admin.certificate_delete_view, name='certificate_delete'),
    path('configuracoes/', views_admin.configuracoes_view, name='configuracoes'),
]
