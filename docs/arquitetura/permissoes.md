# Perfis e permissões

O administrador geral define o papel de cada pessoa em **Configurações → Usuários**.

## Papéis

| Papel | Faz checklists (veículos e pré-uso) | Histórico | Termos de entrada e saída | Certificados | Configurações |
|---|---|---|---|---|---|
| **Administrador** | Sim | De todos | Sim | Sim | Sim |
| **Técnico** (executor) | Sim | Só o próprio | Não | Não | Não |
| **Logística** | Sim | De todos | Sim (rascunhos; excluir finalizado só o admin) | Não | Não |
| **Professor** | Não | — | Não | Os próprios grupos | Não |

Regras gerais:

- Quem faz a vistoria de veículo (Técnico ou Logística) é o próprio motorista: o campo motorista não aparece.
- Fora o administrador, ninguém registra a chegada de um veículo retirado por outra pessoa.
- Registros fora do escopo não abrem nem pelo link direto (o sistema responde "não encontrado").
- Usuários com o antigo papel "Vistoriador" foram migrados para **Técnico** (migração `accounts 0004`).

## Navegação por papel

```
Início                       ← dois botões: Vistoria de veículo · Pré-uso de equipamento
Certificados                 ← Administrador e Professor
Checklists ▾                 ← Administrador, Técnico, Logística
   Veículos
   Pré-uso de equipamentos
Termos                       ← Administrador e Logística
Aparência (no rodapé)        ← todos
Configurações (no rodapé)    ← só Administrador
```

## Onde isso está no código

- Papéis: `accounts/models.py` (`ROLE_*`, `pode_checklists`, `ve_todo_historico`, `is_admin_geral`).
- Bloqueio das telas: `certificates/decorators.py` (`admin_required`, `veiculos_required`, `checklists_required`).
- Escopo do histórico: `_inspecoes_visiveis` e `_usos_visiveis` (veículos), `_execucoes_visiveis` (checklists), `_resumo_checklists` (início).
- Menu: `templates/dashboard/_shell.html` (grupo Checklists).

## Evolução planejada

Permissão por módulo (Executor, Supervisor, Gestor do módulo, Administrador geral), com restrição opcional por tipo de ativo. Ver [decisoes/003-permissoes-por-modulo.md](../decisoes/003-permissoes-por-modulo.md).
