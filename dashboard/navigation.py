# Área "Configurações" (somente administrador geral), organizada por assunto e não por módulo:
# cada área junta o que é igual em todos os módulos (pessoas, equipamentos, formulários, e-mails).
CONFIG_AREAS = [
    ('pessoas', 'Pessoas', [
        ('usuarios', 'Usuários e acesso', 'accounts_admin:usuarios'),
        ('motoristas', 'Motoristas (CNH)', 'veiculos:motoristas'),
    ]),
    ('equipamentos', 'Equipamentos', [
        ('ativos', 'Equipamentos', 'checklists:ativos'),
        ('veiculos', 'Veículos', 'veiculos:veiculos'),
        ('tipos', 'Tipos', 'checklists:tipos'),
    ]),
    ('formularios', 'Formulários', [
        ('modelos', 'Checklists (TCB-OTB)', 'checklists:modelos'),
        ('termos_doc', 'Termos (TCB-LO)', 'termos:documentos'),
    ]),
    ('notificacoes', 'Notificações', [
        ('supervisores', 'Quem recebe', 'veiculos:supervisores'),
        ('email', 'Envio e teste', 'veiculos:email'),
    ]),
]

# Lista plana (chave, rótulo, url) usada pelas views para saber se a tela é de configuração.
CONFIG_TABS = [aba for _, _, abas in CONFIG_AREAS for aba in abas]
CONFIG_KEYS = {k for k, _, _ in CONFIG_TABS}


def area_da_aba(chave):
    for area, rotulo, abas in CONFIG_AREAS:
        if any(k == chave for k, _, _ in abas):
            return area, abas
    return None, []
