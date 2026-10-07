# 003 · Permissões por módulo

**Data:** 05/10/2026 · **Situação:** proposta (implementação parcial)

## Contexto

Hoje cada pessoa tem um único papel (Administrador, Técnico, Logística, Professor). Com mais módulos, uma mesma pessoa pode precisar executar checklists de equipamentos e também vistorias de veículo, ou supervisionar só um módulo.

## Decisão

Evoluir para permissão **por módulo**, com um nível e um escopo:

| Nível | Executa | Histórico | Cadastros | Recebe e-mails |
|---|---|---|---|---|
| Executor | sim | só os próprios | não | não |
| Supervisor | sim | todos do módulo | não | sim |
| Gestor do módulo | sim | todos do módulo | sim | sim |
| Administrador geral | sim | tudo | todos os módulos | configurável |

Opcionalmente, o executor pode ser restrito a alguns tipos de ativo.

## Situação atual

Enquanto a mudança não é feita, cada papel equivale a um nível fixo: Técnico = Executor de Checklists (veículos e equipamentos); Logística = Supervisor de Checklists e Termos; Professor = Executor de Certificados. A migração preserva esses acessos.
