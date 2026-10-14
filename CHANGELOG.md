# Histórico de mudanças

Escrito em linguagem simples, do mais recente para o mais antigo.

## 14/10/2026 – Assinatura deitada no celular

- No celular, tocar no quadro de assinatura abre uma tela cheia na horizontal (vistoria, checklist e termo, inclusive a do cliente). No Android a tela gira sozinha; no iPhone a área aparece girada para assinar com o celular deitado. No computador continua igual.

## 14/10/2026 – Cadastro do motorista e QR code direto

- Conta nova entra sem acesso a nada até o administrador escolher o papel. Novo papel pronto: **Motorista** (só vistoria de veículos).
- Na primeira vistoria, o motorista completa **Meus dados**: telefone, nº, categoria, validade e foto da CNH. CNH vencida não é aceita. A CNH sai no comprovante de cada vistoria e não é mais fotografada a cada vez.
- Fotos dos pneus deixaram de ser obrigatórias (o estado de 0 a 100% continua).
- Login fica guardado no celular por 6 meses (renovado a cada uso) e, depois de entrar, a pessoa volta para a tela aberta pelo QR code.

## 14/10/2026 – QR codes por tela e servidor da oficina

- Configurações → Sistema → **QR codes**: escolha telas (ex.: "Pré-uso › Gerador", "Vistoria de saída", "Novo termo") ou equipamentos e veículos específicos e imprima as etiquetas.
- `python servidor.py`: o Polaris roda neste computador em modo produção (HTTPS 8443, porta 8000 redireciona), reinicia sozinho se cair e acompanha a mudança de IP. O Windows liga o servidor ao entrar na conta e envia os alertas da frota todo dia às 7h.

## 14/10/2026 – Papéis e acessos configuráveis

- Em Configurações → Pessoas → **Papéis e acessos**, o administrador cria papéis (ex.: Motorista) e marca o que cada um usa: vistoria de veículos, checklist de equipamentos, termos, certificados, histórico de todos ou administrador.
- Os papéis de antes (Administrador, Técnico, Logística, Professor) viraram papéis editáveis; cada pessoa ficou com o mesmo acesso. Arquivar um papel tira o acesso de quem o tem.
- O professor vê só Certificados e Histórico; no histórico aparecem os cadastros de alunos que ele fez.
- Menu, tela inicial e permissões seguem o papel de cada pessoa.

## 13/10/2026 – Usabilidade: um caminho só para tudo

- **Novo registro**: botão único no menu. Pergunta "Veículo, Equipamento ou Termo?" e segue os passos de cada um; o caminho escolhido aparece no topo.
- **Histórico único**: vistorias, checklists e termos numa lista só, com filtros por tipo, texto, pessoa, período e "só com problema". O técnico vê só os próprios registros.
- **Tela de concluído**: depois de enviar, confirmação com "Ver PDF", "Outro checklist neste equipamento" (ou "Nova vistoria deste veículo"), "Novo registro" e "Voltar ao início".
- **Etapas no celular**: vistoria e checklist aparecem uma etapa por vez (dados, itens, fotos, assinatura), com barra de progresso. Um erro no envio abre a etapa do problema.
- **Rascunho automático**: respostas, fotos e assinatura ficam guardadas no celular enquanto a pessoa preenche. Se o sinal cair ou a página fechar, tudo volta ao abrir de novo (por até 3 dias).
- **QR code**: etiquetas para imprimir em Configurações → Equipamentos e Veículos. O QR leva direto ao checklist do equipamento ou à vistoria do veículo.
- **Para conferir**: o administrador vê na tela inicial (com contador no menu) os equipamentos cadastrados na hora pelos técnicos e os registros com problema, e marca cada um como conferido.
- Palavras iguais em todo o sistema: "equipamento" (não "ativo"), "formulário" (não "modelo de checklist") e "destinatários" (não "supervisores").

## 13/10/2026 – Pronto para o PythonAnywhere

- `SITE_URL` passa a definir também o domínio aceito e a proteção dos formulários (CSRF). Em produção (`DJANGO_DEBUG=False`) o sistema exige chave secreta própria e liga cookies seguros e HTTPS.
- `STATIC_ROOT` para o `collectstatic`; envio de e-mail em segundo plano configurável (`EMAIL_SEGUNDO_PLANO`).
- Guia passo a passo em `docs/deploy/pythonanywhere.md`.

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
