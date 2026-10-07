# Módulo Termos de entrada e saída

## O que faz

Registra o **material de cliente** que entra na Texas (termo de entrada, **TCB-LO-01**) ou que é entregue ao cliente (termo de saída, **TCB-LO-02**), com a lista de equipamentos, fotos e as assinaturas do responsável Texas e do cliente. Gera o PDF no layout dos formulários e envia aos supervisores.

Quem acessa: **Administrador** e **Logística** (o Técnico não vê o módulo).

## Fluxo

1. **Novo termo** (de entrada ou de saída) a partir da lista, do menu "Termos" ou do botão na tela inicial.
2. Preenche nº do assunto, motivo, data, cliente e contato, origem e transporte; os rótulos mudam com o tipo ("Motivo da entrada"/"Motivo da entrega", "Data da entrada"/"Data da saída"), como nos formulários.
3. Inclui os equipamentos (equipamento, referência, quantidade, informação), observações e fotos.
4. **Salvar rascunho** a qualquer momento, por exemplo para colher a assinatura do cliente na entrega.
5. **Finalizar termo**: exige pelo menos um equipamento, as duas assinaturas e o nome legível do cliente. O termo finalizado fica travado, guarda a revisão do documento em vigor e o PDF segue por e-mail aos supervisores.

Rascunhos podem ser excluídos pela Logística; termos finalizados, só pelo administrador.

## Entidades (`termos/models.py`)

- **ModeloTermo**: cabeçalho de cada tipo (código, título, revisão, preparado por, revisado por, data). Editado em **Configurações → Termos** ou importado do `.docx`.
- **Termo**: dados, assinaturas (imagens), nome e telefone do cliente, status, revisão do documento usada ao finalizar.
- **TermoItem** e **TermoFoto**.

## PDF (`termos/pdf.py`)

Mesmo cabeçalho e rodapé dos checklists (`checklists/pdf.py`), com: bloco de dados em azul com linhas amarelas, tabela de equipamentos numerada, observações, registro fotográfico, assinaturas (Texas; cliente com nome legível e telefone) e a declaração de responsabilidade do formulário. Com uma foto, cabe em uma página, como o formulário.

A declaração usa a grafia correta "extravio" (o formulário Word traz "estravío").
