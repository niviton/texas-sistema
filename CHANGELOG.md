# Histórico de mudanças

Escrito em linguagem simples, do mais recente para o mais antigo.

## 08/10/2026 – PDF: motivo só nas observações

- Nos PDFs da vistoria e do checklist de equipamento, a tabela de itens mostra só o X. O motivo de cada item marcado como NOK (ou de qualquer item com observação) aparece uma única vez, no quadro "Observações".

## 08/10/2026 – Cadastro do equipamento na hora do checklist

- Se o equipamento não está na lista, o técnico informa uma vez (ex.: "Gerador Toyama 1000 W", série e patrimônio opcionais) e já cai no checklist. Ele fica salvo e aparece nas próximas vezes; o mesmo nome não é cadastrado duas vezes.
- Em Configurações → Equipamentos, esses cadastros aparecem marcados com quem cadastrou, para o administrador conferir e completar.

## 08/10/2026 – Todos os checklists TCB-OTB no sistema

- O importador passou a ler os formatos antigos: Sim / Não, Conforme / Não conforme / Parcialmente / N/A, tabela única C / NC / NA, grade semanal e "Descrição | Verificação" (foto obrigatória e medições numéricas).
- Importados os 9 que faltavam, com destaque para os geradores: TCB-OTB-24 (manutenção) e TCB-OTB-28 (inspeção), além de 02 a 06, 26 (empilhadeira) e 53 (bombas, chaves de torque, tensionadores e mangueiras).

## 08/10/2026 – Navegação em passos

- Checklist de equipamento agora segue um caminho, uma pergunta por tela: **Pré-uso / Inspeção / Manutenção → tipo de equipamento → unidade (ex.: RAD 02) → formulário**. O caminho escolhido aparece no topo e cada passo é clicável para voltar.
- Cada modelo de checklist tem uma "finalidade" (pré-uso, inspeção, manutenção, geral), preenchida sozinha a partir do título do TCB na importação.
- A vistoria de veículos segue a mesma lógica: **Saída / Chegada / Rotina → veículo → formulário**. Na saída, veículos em uso aparecem bloqueados; na chegada, só aparecem os veículos que a pessoa está usando.
- A tela de escolha em passos é uma só (`templates/dashboard/_escolha.html`) e serve a qualquer módulo novo.

## 08/10/2026 – Configurações por assunto e e-mails por módulo

- Configurações reorganizadas em quatro áreas que valem para todos os módulos: Pessoas, Equipamentos, Formulários e Notificações.
- Supervisores viraram "destinatários": cada um escolhe se recebe vistorias de veículos, checklists e termos; nos checklists, pode limitar a alguns tipos de equipamento.
- Fotos reduzidas no celular e assinatura com o dedo agora vêm de um único arquivo (`static/js/polaris-campo.js`), usado pela vistoria, pelo checklist e pelo termo.

## 07/10/2026 – 36 checklists de equipamentos importados

- Importados os formulários TCB-OTB 38 a 49, 65 a 85, 114 e 127 (pré-uso, inspeção e manutenção). Cada família de equipamento tem um tipo de ativo único, compartilhado pelos três formulários.
- Ficam pendentes os formulários com layout diferente (TCB-OTB-02 a 06, 24, 26, 28 e 53); veja `docs/checklists/catalogo.md`.

## 07/10/2026 · HTTPS na rede local e GPS ao entrar

- Novos comandos `certificado_local` (gera certificado para o IP da oficina) e `runserver_https` (Polaris em `https://<ip>:8443`, sem depurador interativo).
- Página pública `/certificado-celular/` com o certificado e o passo a passo para Android e iPhone.
- O Polaris pede a permissão de localização ao abrir qualquer tela; os formulários de foto avisam se o local foi registrado.
- Carimbo de comprovação nas fotos (logo, data e hora do servidor, endereço) e escolha "Tirar foto agora" ou "Galeria" no celular.

## 07/10/2026 · Termos de entrada e saída

- Novo módulo **Termos** (Administrador e Logística): termos de entrada (TCB-LO-01) e saída (TCB-LO-02) de material de cliente, com equipamentos, fotos e assinaturas da Texas e do cliente.
- Rascunho para colher assinaturas depois; ao finalizar, o termo trava e o PDF no layout do formulário vai aos supervisores.
- Cabeçalho dos formulários importado do Word em **Configurações → Termos**.
- Fotos: os campos de foto deixaram de forçar a câmera e de ficar ocultos de um jeito que alguns celulares ignoravam o toque; agora o celular oferece "tirar foto" ou "galeria".

## 07/10/2026 · Aparência por pessoa

- Novo item **Aparência** no menu (para todos): tema Claro, Escuro ou Automático e escolha da fonte (Manrope, Inter, Roboto, Open Sans, Atkinson Hyperlegible, Lexend). Vale só para a própria conta.

## 07/10/2026 · Checklists num só lugar e novos papéis

- Menu: **Checklists** virou um grupo com **Veículos** e **Pré-uso de equipamentos**; Veículos saiu do primeiro nível.
- Tela inicial minimalista: dois botões (Vistoria de veículo, Pré-uso de equipamento), veículos para registrar chegada e os últimos registros.
- Papéis reorganizados: **Administrador**, **Técnico** (faz checklists e vê o próprio histórico), **Logística** (faz checklists e vê o histórico de todos) e **Professor**. Quem era Vistoriador virou Técnico.

## 05/10/2026 · Início da plataforma de checklists

- Novo módulo **Checklists**: um único motor executa qualquer formulário TCB-OTB.
- Importação de formulários em Word: o sistema lê código, revisão, preparado e revisado por, seções e itens.
- TCB-OTB-80 (bancada de calibração) e TCB-OTB-113 (transpaleteira) importados; bancadas RAD 02, 24, 47 e 716 cadastradas.
- Controle de revisão: revisão usada não muda; criar a próxima preserva o histórico.
- PDF no layout dos formulários, com o cabeçalho vindo da revisão; comprovante por e-mail aos supervisores.
- Novo papel **Técnico de campo**: só executa checklists e só vê as próprias execuções.
- Configurações ganha as abas Tipos de ativo, Ativos e Modelos de checklist.
- Pasta `docs/` com arquitetura, permissões, módulo, catálogo e registros de decisão.

## Até 02/10/2026 · Veículos

- Vistoria de veículos com fotos guiadas, pneus e combustível em %, carga, assinatura com o dedo e PDF no padrão TCB-OTB-113.
- Manutenção por km e data com aviso imediato aos supervisores; comprovante por e-mail em segundo plano.
- Papel Vistoriador (só os próprios registros) e Configurações reunidas para o administrador.
- Layout para celular e janela de confirmação própria do sistema.
