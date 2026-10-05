from django.contrib import admin

from .models import Ativo, Execucao, Item, Modelo, Resposta, Revisao, Secao, TipoAtivo


class SecaoInline(admin.TabularInline):
    model = Secao
    extra = 0


class RespostaInline(admin.TabularInline):
    model = Resposta
    extra = 0


@admin.register(Revisao)
class RevisaoAdmin(admin.ModelAdmin):
    list_display = ['modelo', 'numero', 'vigente', 'preparado_por', 'revisado_por', 'data']
    inlines = [SecaoInline]


@admin.register(Execucao)
class ExecucaoAdmin(admin.ModelAdmin):
    list_display = ['revisao', 'ativo', 'executor_nome', 'tem_problema', 'created_at']
    inlines = [RespostaInline]


admin.site.register([TipoAtivo, Ativo, Modelo, Item])
