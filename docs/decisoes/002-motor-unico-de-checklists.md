# 002 · Um motor único de checklists

**Data:** 05/10/2026 · **Situação:** aceita

## Contexto

A empresa tem ao menos 14 formulários TCB-OTB de checklist, e cada um tem a mesma anatomia: equipamento, itens, fotos, assinatura, documento. O checklist de veículos foi feito como módulo próprio, com itens no código; repetir isso para cada formulário multiplicaria o trabalho e os padrões.

## Decisão

Checklists são **dados**: tipo de ativo, ativo, modelo com revisão, seções e itens com tipo de resposta. Um único motor executa qualquer modelo, gera o PDF TCB-OTB a partir da revisão e envia o comprovante. Formulários em Word podem ser importados direto.

Regra: se um formulário pedir algo novo, o recurso entra no motor como novo tipo de item, disponível para todos. Nunca se cria um módulo separado por checklist.

## Consequências

- Checklist novo é cadastro do administrador, sem desenvolvimento.
- O módulo de veículos será recadastrado como tipo de ativo + modelo (Fase 1), com migração dos dados.
- O motor precisa crescer com cuidado para não ficar genérico demais: cada tipo de item novo nasce de um formulário real.
