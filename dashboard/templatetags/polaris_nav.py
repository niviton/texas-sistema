import os

from django import template

from dashboard.navigation import CONFIG_AREAS, area_da_aba

register = template.Library()


@register.inclusion_tag('dashboard/_config_tabs.html')
def config_nav(active_tab):
    area_ativa, abas = area_da_aba(active_tab)
    areas = [(chave, rotulo, sub[0][2]) for chave, rotulo, sub in CONFIG_AREAS]
    return {'areas': areas, 'area_ativa': area_ativa, 'abas': abas, 'active_tab': active_tab}


@register.simple_tag
def static_v(caminho):
    """Endereço do arquivo estático com a versão (data da última alteração): o celular baixa de novo
    sempre que o arquivo muda, em vez de usar a cópia antiga guardada no navegador."""
    from django.contrib.staticfiles import finders
    from django.templatetags.static import static
    arquivo = finders.find(caminho)
    versao = int(os.path.getmtime(arquivo)) if arquivo else 0
    return f'{static(caminho)}?v={versao}'
