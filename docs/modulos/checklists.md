# Módulo Checklists (motor genérico)

## O que faz

Executa qualquer formulário de checklist da empresa a partir de um **modelo** cadastrado: o técnico escolhe o equipamento, responde os itens, tira fotos e assina; o sistema gera o PDF no layout TCB-OTB e envia o comprovante aos supervisores.

## Entidades (`checklists/models.py`)

```
TipoAtivo 1──n Ativo 1──n Execucao n──1 Revisao n──1 Modelo n──n TipoAtivo
                              │              │
                              ├─n Resposta ──┤ Revisao 1──n Secao 1──n Item
                              └─n FotoExecucao
```

- **TipoAtivo**: nome e medidor (`nenhum`, `horimetro`, `km`). O medidor é pedido em toda execução.
- **Ativo**: tipo, nome, identificação/série, patrimônio, marca, modelo, status, última leitura do medidor.
- **Modelo**: código do documento (único), título, tipos de ativo a que se aplica, disponível ou não.
- **Revisao**: número, preparado por, revisado por, data, vigente. Alimenta o cabeçalho do PDF.
- **Secao / Item**: o conteúdo do formulário. Cada item tem tipo de resposta, se exige foto e quando pede observação.
- **Execucao / Resposta / FotoExecucao**: o checklist preenchido, sempre ligado à revisão usada.

## Tipos de resposta

| Código | Opções | Negativas (pedem observação) |
|---|---|---|
| `ok_nok` | OK, NOK, N/A | NOK |
| `conformidade` | Conforme, Não conforme, Parcialmente, N/A | Não conforme, Parcialmente |
| `sim_nao` | Sim, Não | nenhuma |
| `porcentagem` | barra 0 a 100% | nenhuma |
| `numero` | valor numérico | nenhuma |
| `texto` | campo livre (opcional) | nenhuma |

Precisa de algo novo (ex.: tabela de medições de torque)? Crie um **tipo de item** no motor; nunca um módulo separado.

## Controle de revisão

- Enquanto a revisão vigente não tem execuções, os itens podem ser editados livremente.
- Depois da primeira execução, a revisão fica **bloqueada**. "Criar nova revisão" copia seções e itens para a próxima (00 → 01), que passa a ser a vigente.
- Execuções antigas continuam apontando para a revisão em que foram feitas; o PDF delas não muda.

## Importar um formulário TCB em Word

`checklists/importador.py` lê o `.docx`:

- **Cabeçalho**: título, código (`TCB-OTB-nn`), revisão, preparado por, revisado por e data.
- **Corpo**: cada tabela com cabeçalho `Item | OK | NOK` vira uma seção; o parágrafo anterior à tabela vira o título da seção.
- Se o tipo de ativo não for informado, é criado a partir do título (o texto depois do travessão).

Pela tela: **Configurações → Modelos de checklist → Importar formulário TCB**.
Pela linha de comando: `python manage.py importar_tcb arquivo.docx [--tipo "Gerador"]`.

Reimportar a mesma revisão não duplica nada. Uma revisão nova do Word cria a nova revisão no sistema.

## Telas

| Quem | Tela | Endereço |
|---|---|---|
| Técnico e administrador | Executar (lista de equipamentos por tipo) | `/dashboard/checklists/` |
| Técnico e administrador | Formulário de execução | `/dashboard/checklists/executar/<ativo>/<modelo>/` |
| Técnico (só os próprios) e administrador | Histórico, detalhe e PDF | `/dashboard/checklists/historico/` |
| Administrador | Tipos de ativo, Ativos, Modelos e editor de itens | `/dashboard/checklists/configuracoes/...` |

## E-mail

Assunto: `Comprovante de checklist TCB-OTB-80: Bancada de calibração RAD 02 (RAD 02) e técnico Fulano`. Corpo curto, PDF em anexo, envio em segundo plano. Destinatários: os supervisores ativos (mesma lista do módulo de veículos, por enquanto).
