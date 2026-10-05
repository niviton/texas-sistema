# Abas da área "Configurações" (somente administrador geral).
CONFIG_TABS = [
    ('usuarios', 'Usuários', 'accounts_admin:usuarios'),
    ('veiculos', 'Veículos', 'veiculos:veiculos'),
    ('motoristas', 'Motoristas', 'veiculos:motoristas'),
    ('supervisores', 'Supervisores', 'veiculos:supervisores'),
    ('email', 'E-mails da frota', 'veiculos:email'),
    ('tipos', 'Tipos de ativo', 'checklists:tipos'),
    ('ativos', 'Ativos', 'checklists:ativos'),
    ('modelos', 'Modelos de checklist', 'checklists:modelos'),
]
CONFIG_KEYS = {k for k, _, _ in CONFIG_TABS}
