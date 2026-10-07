# Polaris · documentação

O Polaris é o portal da Texas Controls Brasil. É uma plataforma com **módulos** (Certificados, Checklists, Veículos e, em breve, Termos de entrada e saída) sobre um **núcleo comum** de login, permissões, PDF no padrão TCB-OTB, e-mail, fotos e assinaturas.

## Por onde começar

| Quero entender… | Leia |
|---|---|
| A visão geral e o plano | [arquitetura/plataforma.md](arquitetura/plataforma.md) |
| Quem pode fazer o quê | [arquitetura/permissoes.md](arquitetura/permissoes.md) |
| Como funciona o motor de checklists | [modulos/checklists.md](modulos/checklists.md) |
| Como funcionam os termos de entrada e saída | [modulos/termos.md](modulos/termos.md) |
| Quais formulários TCB-OTB já estão no sistema | [checklists/catalogo.md](checklists/catalogo.md) |
| Por que uma escolha foi feita | [decisoes/](decisoes/) |
| O que mudou em cada versão | [../CHANGELOG.md](../CHANGELOG.md) |

## Como rodar

```
pip install -r requirements.txt
cp .env.example .env          # preencha a chave e o Gmail (senha de app)
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### HTTPS na rede da oficina (necessário para o GPS do carimbo das fotos)

O celular só libera a localização em sites HTTPS. Para a rede local:

```
python manage.py certificado_local          # uma vez; gera ssl_local/ (não vai para o Git)
python manage.py runserver_https            # https://<ip-do-computador>:8443
```

Em cada celular, instale o certificado pela página `https://<ip>:8443/certificado-celular/` (passo a passo para Android e iPhone). Se o IP do computador mudar, rode `certificado_local` de novo com o IP novo: a autoridade é reaproveitada e os celulares não precisam reinstalar. Em produção, use um domínio com certificado público (Let's Encrypt).

Para importar formulários TCB-OTB em Word: `python manage.py importar_tcb tcbs/*.docx`
(ou pela tela **Configurações → Modelos de checklist**).

Testes: `python manage.py test checklists veiculos accounts dashboard`

## Glossário

| Termo | Significado |
|---|---|
| **Tipo de ativo** | Família de equipamentos com o mesmo checklist e o mesmo medidor (ex.: Gerador, horímetro). |
| **Ativo** | Um equipamento real, identificado por série, placa ou patrimônio. |
| **Modelo de checklist** | O formulário controlado (ex.: TCB-OTB-80), com código e revisão. |
| **Revisão** | Versão do modelo. Revisão usada em execuções não muda: cria-se a próxima. |
| **Execução** | Um checklist preenchido por um técnico para um ativo. Vira PDF e e-mail. |
| **Vistoria** | Execução do checklist de veículos (módulo Veículos, a ser migrado para o motor). |

## Dados internos

Os formulários da empresa (`tcbs/`, `TCB-OTB-*`, `modelos certificados/`) **não** vão para o repositório, que é público. Eles ficam só na máquina e são importados para o banco.
