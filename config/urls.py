from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('dashboard/usuarios/', include('accounts.urls_admin')),
    path('dashboard/certificados/', include('certificates.urls_admin')),
    path('dashboard/meus-certificados/', include('certificates.urls_professor')),
    path('dashboard/veiculos/', include('veiculos.urls')),
    path('dashboard/checklists/', include('checklists.urls')),
    path('verificacao-certificados/', include('certificates.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
