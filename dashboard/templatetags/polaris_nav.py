from django import template

from dashboard.navigation import CONFIG_AREAS, area_da_aba

register = template.Library()


@register.inclusion_tag('dashboard/_config_tabs.html')
def config_nav(active_tab):
    area_ativa, abas = area_da_aba(active_tab)
    areas = [(chave, rotulo, sub[0][2]) for chave, rotulo, sub in CONFIG_AREAS]
    return {'areas': areas, 'area_ativa': area_ativa, 'abas': abas, 'active_tab': active_tab}
