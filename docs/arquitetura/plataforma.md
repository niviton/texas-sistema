# Arquitetura da plataforma

Documento de referência: **PROP-POLARIS-01 rev. 00** (proposta completa, com diagramas, aprovada para início em 05/10/2026).

## Princípio

> Um motor de checklists, muitos tipos.

Todo checklist da empresa tem a mesma anatomia: alguém inspeciona um **ativo** seguindo um **formulário controlado**, responde itens, tira fotos, assina, e o resultado vira um documento. Por isso o Polaris não cria um sistema por checklist: cria **modelos** dentro de um único módulo. Um checklist novo é cadastro, não programação.

## Camadas

```
Interface única (computador e celular)
  Início · Executar · Histórico · Configurações
        │
Módulos de negócio
  Certificados · Checklists (motor genérico) · Veículos* · Termos
        │
Núcleo comum
  Acessos · Documentos controlados e PDF TCB-OTB · Notificações · Fotos · Assinaturas · Auditoria (planejado)
```

\* Veículos é hoje um módulo próprio e será recadastrado como tipo de ativo + modelo do motor (Fase 1 do plano).

## Onde está cada coisa no código

| Pasta | Conteúdo |
|---|---|
| `accounts/` | Login, perfis (papel por usuário) |
| `certificates/` | Certificados de treinamento; `decorators.py` tem os controles de acesso |
| `checklists/` | Motor genérico: tipos de ativo, ativos, modelos, revisões, execuções, PDF, importador de .docx |
| `veiculos/` | Vistoria de veículos, manutenção, uso da frota; hoje também guarda as peças compartilhadas de PDF, e-mail e fotos |
| `dashboard/` | Tela inicial e navegação (`navigation.py` define as abas de Configurações) |
| `templates/` | Telas; `dashboard/_shell.html` é o layout comum (menu, celular, janela de confirmação) |

**Próximo passo técnico:** extrair de `veiculos/` para um app `core/` as peças compartilhadas (`pdf.py` base, `emails.py`, `imagens.py`), sem mudar comportamento.

## Plano

| Fase | Entrega | Situação |
|---|---|---|
| 0 | Servidor com HTTPS, núcleo extraído, permissões por módulo, `docs/` | `docs/` e perfil Técnico feitos; servidor e núcleo pendentes |
| 1 | Motor de checklists; veículos migrados para o motor | **Motor feito**; migração de veículos pendente |
| 2 | Checklist de equipamentos (TCB-OTB-80), importação do Checklist Pro | TCB-OTB-80 e TCB-OTB-113 importados; dados do Base44 pendentes |
| 3 | Termos de entrada e saída com assinatura dupla | **Feito** (TCB-LO-01 e TCB-LO-02) |
| 4 | QR code no ativo, rascunho offline, painel gerencial | Não iniciado |

## Decisões em aberto

1. Onde hospedar (servidor da empresa ou nuvem). Hoje roda no computador da oficina, só no mesmo Wi-Fi.
2. Número oficial do checklist de veículos (provisório: TCB-OTB-VEIC).
3. Se há dados reais no Checklist Pro (Base44) para migrar.
4. Quais supervisores recebem cada tipo de checklist (hoje todos recebem tudo).
