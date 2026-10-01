from django.contrib import admin

from .models import Inspecao, InspecaoFoto, InspecaoItem, Motorista, Supervisor, Uso, Veiculo


class InspecaoItemInline(admin.TabularInline):
    model = InspecaoItem
    extra = 0


class InspecaoFotoInline(admin.TabularInline):
    model = InspecaoFoto
    extra = 0


@admin.register(Inspecao)
class InspecaoAdmin(admin.ModelAdmin):
    list_display = ['veiculo', 'tipo', 'motorista', 'km', 'tem_problema', 'created_at']
    list_filter = ['tipo', 'tem_problema']
    inlines = [InspecaoItemInline, InspecaoFotoInline]


admin.site.register([Veiculo, Motorista, Supervisor, Uso])
