# Perfis e permissões

O administrador geral define o papel de cada pessoa em **Configurações → Usuários**.

## Papéis atuais

| Papel | Acessa | Vê histórico | Configurações |
|---|---|---|---|
| **Administrador** | Tudo | Tudo | Sim |
| **Professor** | Certificados (os próprios grupos) | Os próprios | Não |
| **Vistoriador (mobilização)** | Veículos: faz vistorias, é o próprio motorista | Só as próprias vistorias e usos | Não |
| **Técnico de campo (checklists)** | Checklists de equipamentos | Só as próprias execuções | Não |

Regras que valem para todos os papéis que não são administrador:

- Não veem cadastros nem configurações; a aba "Configurações" só aparece para o administrador.
- Não abrem registros de outras pessoas nem pelo link direto (o sistema responde "não encontrado").
- O vistoriador só registra a chegada de um veículo que ele mesmo retirou.

## Onde isso está no código

- Papéis: `accounts/models.py` (`ROLE_*`, `pode_veiculos`, `pode_checklists`, `is_admin_geral`).
- Bloqueio das telas: `certificates/decorators.py` (`admin_required`, `veiculos_required`, `checklists_required`).
- "Só os próprios": `_inspecoes_visiveis` (veículos) e `_execucoes_visiveis` (checklists) nas views.

## Evolução planejada

A proposta prevê trocar o papel único por **permissão por módulo** (Executor, Supervisor, Gestor do módulo, Administrador geral), com restrição opcional por tipo de ativo. Ver [decisoes/003-permissoes-por-modulo.md](../decisoes/003-permissoes-por-modulo.md).
