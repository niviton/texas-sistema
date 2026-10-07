from django.contrib import admin

from .models import ModeloTermo, Termo, TermoFoto, TermoItem


class ItemInline(admin.TabularInline):
    model = TermoItem
    extra = 0


class FotoInline(admin.TabularInline):
    model = TermoFoto
    extra = 0


@admin.register(Termo)
class TermoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tipo', 'cliente_contato', 'data', 'status']
    list_filter = ['tipo', 'status']
    inlines = [ItemInline, FotoInline]


admin.site.register(ModeloTermo)
