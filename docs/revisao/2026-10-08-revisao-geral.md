# Revisão geral do Polaris (08/10/2026)

Princípio usado em toda a revisão: **cada mudança deve resolver vários problemas de uma vez**. Onde hoje existem três coisas parecidas (três telas, três envios de e-mail, três cadastros de pessoas), a proposta é ter uma só, que sirva a todos os módulos.

---

## 1. Acesso seguro (HTTPS) de qualquer lugar, sem configurar celular

### O problema de hoje
- O celular só libera o GPS em site HTTPS com certificado reconhecido.
- O certificado que geramos é "caseiro": funciona, mas exige instalar em cada celular. Não é viável.
- O endereço `192.168.x.x` só existe dentro do Wi-Fi da oficina. Com dados móveis ele não abre.

### Por que "só o endereço IP" não resolve
- Certificados reconhecidos são emitidos para **nomes** (ex.: `polaris.empresa.com.br`). Para IP existe, mas vale poucos dias, exige IP fixo e porta aberta no roteador.
- O IP da internet da oficina muda e abrir porta expõe o computador diretamente.

### Solução recomendada: um endereço com nome + túnel seguro
**Cloudflare Tunnel** (gratuito) instalado no computador que roda o Polaris:

| Resolve | Como |
|---|---|
| HTTPS válido | Certificado público automático, renovação automática |
| GPS no celular | Site seguro: o celular pede a permissão normalmente, sem instalar nada |
| Dados móveis | Abre de qualquer lugar pela internet |
| Segurança da rede | Não abre porta no roteador; o IP da oficina fica escondido |
| IP que muda | O túnel se reconecta sozinho |
| Links dos e-mails | `SITE_URL` passa a ser o endereço fixo, os links funcionam fora da oficina |

O que é preciso:
1. Um domínio. Melhor opção: pedir ao TI um subdomínio do domínio da empresa (ex.: `polaris.<dominio-da-empresa>`). Alternativa: registrar um domínio próprio (`.com.br`, cerca de R$ 40/ano).
2. Uma conta gratuita na Cloudflare apontando esse domínio.
3. Eu configuro o túnel e o "modo produção" do Polaris (item 2).

Limitação: o computador precisa ficar ligado. A evolução natural (fase seguinte) é um **servidor na nuvem** (VPS, cerca de R$ 30–60/mês), que resolve de uma vez: computador desligado, backup automático, velocidade e independência da oficina. O mesmo "modo produção" serve para os dois caminhos.

### Antes de abrir para a internet (obrigatório)
Uma única configuração "modo produção", derivada do `SITE_URL`, que resolve tudo junto:
- `DEBUG` desligado (hoje páginas de erro mostram detalhes internos).
- Chave secreta só no `.env` (hoje há uma chave padrão no código público).
- Endereços permitidos e proteção de formulários (CSRF) calculados a partir do `SITE_URL`, sem listas separadas.
- Cookies só em HTTPS, HSTS e redirecionamento para HTTPS.
- Servidor de produção (Waitress no Windows) no lugar do `runserver`, servindo estáticos com WhiteNoise.
- Limite de tentativas de login.
- Backup diário automático do banco e das fotos.
- Remover do histórico do GitHub a senha que ficou exposta em `Login Polaris.dc.html` (e trocar a senha).

---

## 2. Configurações: organizar por assunto, não por módulo

### Hoje
Nove abas soltas: Usuários, Veículos, Motoristas, Supervisores, E-mails da frota, Tipos de ativo, Ativos, Modelos de checklist, Termos. Cada módulo novo acrescenta mais abas, e coisas iguais ficam em lugares diferentes.

### Proposta: cinco áreas que valem para todos os módulos

| Área | Junta | Ganho |
|---|---|---|
| **Pessoas** | Usuários + Motoristas + Supervisores | Uma pessoa = um cadastro. CNH vira um dado da pessoa, não um cadastro à parte. |
| **Equipamentos** | Veículos + Tipos de ativo + Ativos | Veículo passa a ser um tipo de ativo. Uma tela: tipo → equipamentos → formulários aplicáveis. |
| **Formulários** | Modelos de checklist + Termos | Todos são documentos TCB com código e revisão; mesma tela de importar, revisar e publicar. |
| **Notificações** | E-mails da frota + supervisores | Quem recebe o quê, por módulo e por tipo de equipamento. Resolve a pendência "supervisores por tipo de checklist". |
| **Sistema** | Endereço do site, certificado, backup, teste de e-mail | Tudo o que é técnico num só lugar. |

---

## 3. Um núcleo comum para "registros"

Vistoria de veículo, checklist e termo fazem a mesma coisa: **preencher → fotos com carimbo → assinatura → PDF → e-mail → histórico**. Hoje isso está repetido em cada módulo.

| Repetido hoje | Proposta | Resolve |
|---|---|---|
| Redução de foto no navegador copiada em 3 telas | Um único arquivo JavaScript de fotos/GPS/assinatura | Correção feita uma vez vale para todos (ex.: problema da câmera no Android) |
| Envio de e-mail em segundo plano em 3 módulos | Um serviço `enviar_comprovante(registro)` | Mesmo layout, mesmos destinatários, reenvio e falhas tratados igual |
| Cabeçalho TCB e numeração de páginas dentro do módulo Veículos | Módulo `nucleo` com PDF, fotos, carimbo, e-mail | Módulos novos nascem prontos |
| Três históricos separados | **Histórico único** com filtro por tipo, equipamento, pessoa e período | Uma busca para tudo; a tela inicial já mostra isso parcialmente |

Ponto principal: **migrar a vistoria de veículos para o motor de checklists** (já planejado). Depois disso, veículo, prensa e transpaleteira usam o mesmo fluxo, o mesmo PDF e o mesmo histórico.

---

## 4. Equipamentos: QR code e vencimentos

- **QR code por equipamento** (etiqueta colada nele). O técnico aponta a câmera e cai direto no checklist certo daquele equipamento. Resolve juntos: identificação errada, tempo de preenchimento, histórico por equipamento e conferência em auditoria.
- **Vencimentos genéricos**: hoje os alertas de vencimento existem só para veículos (documentos, manutenção). O mesmo mecanismo pode valer para qualquer ativo: calibração da bancada, inspeção periódica da talha, manutenção da prensa. Um aviso só, um e-mail só, para tudo.
- **Periodicidade por formulário**: pré-uso (a cada uso), inspeção (mensal), manutenção (semestral) já vêm dos TCB. O sistema pode avisar quando uma inspeção está atrasada.

---

## 5. Importador de formulários

- Hoje lê um formato (tabela "Item | OK | NOK"). Ficaram 9 formulários com 4 formatos diferentes.
- Proposta: um leitor por formato (OK/NOK, C/NC/NA, SIM/NÃO, grade semanal, descrição/verificação) escolhido automaticamente. O mesmo leitor também serve para os termos.
- Quando um TCB mudar de revisão, basta importar o novo Word: o sistema cria a revisão nova e mantém as execuções antigas na revisão antiga (já funciona assim).

---

## 6. Visual e manutenção das telas

- 56 telas usam estilos escritos dentro do HTML. Isso explica os ajustes repetidos de modo escuro, fonte e celular.
- Proposta: um arquivo de estilo com cores e tamanhos definidos uma vez. Resolve juntos: modo escuro sem "inversão de cores", fonte escolhida pelo usuário, layout de celular e aparência consistente entre módulos.

---

## 7. Celular em campo

- Com o endereço público (item 1), o Polaris pode virar **aplicativo instalável** (PWA): ícone na tela inicial, abre em tela cheia, sem barra do navegador.
- Mesma base permite, depois, **salvar o checklist sem sinal** e enviar quando a internet voltar, útil em cliente/campo.

---

## Ordem sugerida

| # | Etapa | Por quê primeiro |
|---|---|---|
| 1 | Modo produção + Cloudflare Tunnel + domínio + backup | Destrava GPS, dados móveis e uso real pela equipe |
| 2 | Núcleo comum (fotos, PDF, e-mail) + Notificações por tipo | Base para todo o resto; elimina repetição |
| 3 | Configurações em 5 áreas (Pessoas, Equipamentos, Formulários, Notificações, Sistema) | Fica fácil de administrar conforme crescem os módulos |
| 4 | Veículos dentro do motor de checklists + histórico único | Um fluxo só para tudo |
| 5 | QR code e vencimentos por equipamento | Ganho direto no chão de fábrica |
| 6 | Importador para os 4 formatos restantes | Completa o catálogo de TCB |
| 7 | Estilo central + PWA | Acabamento e uso em campo |

## O que preciso de você para começar a etapa 1
- Usar subdomínio da empresa (falar com o TI) ou registrar um domínio próprio?
- Criar a conta gratuita na Cloudflare (com o e-mail da empresa, de preferência).
- Confirmar que este computador pode ficar ligado como servidor por enquanto.
