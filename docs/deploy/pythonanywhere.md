# Publicar o Polaris no PythonAnywhere

Com o Polaris no PythonAnywhere, o endereço fica `https://SEUUSUARIO.pythonanywhere.com`:

- HTTPS válido, sem instalar certificado no celular. O GPS e o carimbo de local nas fotos funcionam.
- Abre de qualquer lugar, inclusive com dados móveis.
- Não depende do computador da oficina ficar ligado, nem do IP dele.

Troque `SEUUSUARIO` pelo seu usuário do PythonAnywhere em todos os comandos.

## 0. Plano (conferido em 14/10/2026)

| | Gratuito (Beginner) | Pago (a partir de cerca de US$ 5/mês) |
|---|---|---|
| Endereço | `SEUUSUARIO.pythonanywhere.com`, com HTTPS | Também permite domínio próprio |
| Espaço em disco | 512 MB | 1 GB ou mais |
| Validade do site | Expira em 1 mês: é preciso entrar na aba "Web" e clicar em "Run until 1 month from today" | Não expira |
| Tarefa diária agendada | Contas criadas depois de 15/01/2026 **não têm** | Tem |
| Acesso à internet de dentro do servidor | Só sites de uma lista liberada. O mapa do carimbo (nominatim.openstreetmap.org) e o SharePoint (graph.microsoft.com) estão nela | Livre |

**Dá para usar o gratuito**, com estes cuidados:

- **Renovação:** todo mês, renove o site na aba "Web". Se esquecer, ele sai do ar até renovar; os dados não se perdem.
- **Alertas diários da frota:** sem tarefa agendada, use o botão "Enviar alertas" em Configurações → Notificações → Envio e teste.
- **Espaço:** as fotos enchem os 512 MB com o tempo, então acompanhe em "Account". Cada vistoria ocupa cerca de 2 a 4 MB.
- **E-mail:** o envio pelo Gmail precisa ser testado no próprio PythonAnywhere. Use o botão "Enviar teste" depois de publicar. Se o plano gratuito bloquear, os registros continuam funcionando, só o e-mail não sai.

## 1. Baixar o código (aba "Consoles" → "Bash")

```bash
git clone https://github.com/niviton/texas-sistema.git
cd texas-sistema
mkvirtualenv --python=python3.12 polaris
pip install -r requirements.txt
```

O Django 6 exige Python 3.12 ou mais novo. Se o `python3.12` não existir, use `python3.13`.

## 2. Configurar o `.env`

```bash
cp .env.example .env
nano .env
```

Preencha pelo menos:

```
DJANGO_SECRET_KEY=   (gere com o comando abaixo e cole aqui)
DJANGO_DEBUG=False
SITE_URL=https://SEUUSUARIO.pythonanywhere.com
EMAIL_HOST_USER=     (o Gmail que envia os comprovantes)
EMAIL_HOST_PASSWORD= (a senha de app do Gmail)
EMAIL_SEGUNDO_PLANO=0
```

Para gerar a chave secreta:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Salve com `Ctrl+O`, `Enter` e saia com `Ctrl+X`.

`EMAIL_SEGUNDO_PLANO=0` é necessário porque o PythonAnywhere não roda tarefas em segundo plano dentro do site. O e-mail sai na hora, e a tela espera alguns segundos depois de enviar o checklist.

## 3. Banco de dados e arquivos

Há dois caminhos.

**A) Levar tudo o que já existe na oficina (recomendado).** Mantém usuários, os 46 checklists importados, equipamentos, vistorias e fotos.

1. No computador da oficina, pare o Polaris e copie `db.sqlite3` e a pasta `media/`. Para enviar mais fácil, compacte a pasta `media` em `media.zip`.
2. Na aba "Files" do PythonAnywhere, abra `/home/SEUUSUARIO/texas-sistema/` e use "Upload a file" para enviar `db.sqlite3` e `media.zip`.
3. No console:

```bash
cd ~/texas-sistema
unzip media.zip
python manage.py migrate
python manage.py collectstatic --noinput
```

**B) Começar do zero.**

```bash
cd ~/texas-sistema
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

Os formulários TCB **não estão no GitHub**, de propósito, porque o repositório é público. Envie a pasta `tcbs/` pela aba "Files" e importe:

```bash
python manage.py importar_tcb tcbs/*.docx
```

Depois ajuste em **Configurações → Formulários** o tipo de equipamento e a finalidade de cada formulário. O caminho A evita esse retrabalho.

## 4. Criar o site (aba "Web")

1. **Add a new web app** → **Manual configuration** (não escolha "Django") → **Python 3.12**.
2. **Virtualenv:** `/home/SEUUSUARIO/.virtualenvs/polaris`
3. **Source code:** `/home/SEUUSUARIO/texas-sistema`
4. Clique no link do **WSGI configuration file** e troque todo o conteúdo por:

```python
import os
import sys

from dotenv import load_dotenv

projeto = '/home/SEUUSUARIO/texas-sistema'
if projeto not in sys.path:
    sys.path.insert(0, projeto)
load_dotenv(os.path.join(projeto, '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

5. Em **Static files**, adicione:

| URL | Directory |
|---|---|
| `/static/` | `/home/SEUUSUARIO/texas-sistema/staticfiles` |
| `/media/` | `/home/SEUUSUARIO/texas-sistema/media` |

6. Em **Security**, ligue **Force HTTPS**.
7. Clique no botão verde **Reload**.
8. Abra `https://SEUUSUARIO.pythonanywhere.com` e entre com seu usuário.

## 5. Alertas diários da frota (aba "Tasks", só no plano pago)

No plano gratuito, use o botão "Enviar alertas" em Configurações → Notificações. No pago, crie uma tarefa diária, por exemplo às 07:00:

```bash
cd ~/texas-sistema && ~/.virtualenvs/polaris/bin/python manage.py veiculos_alertas
```

Ela envia os avisos de vencimento e os lembretes de vistoria atrasada. O mesmo aviso não é enviado duas vezes.

## 6. Atualizar depois de uma mudança

Sempre que houver alteração no GitHub:

```bash
cd ~/texas-sistema
git pull
workon polaris
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Depois clique em **Reload** na aba "Web".

## 7. Cuidados

- **Backup:** baixe o `db.sqlite3` e a pasta `media/` pela aba "Files" de vez em quando. No plano pago, dá para agendar uma cópia em "Tasks".
- **Fotos:** cada foto ocupa cerca de 200 a 400 KB depois de reduzida. Acompanhe o espaço em "Account".
- **Certificados (módulo do professor):** a geração em PDF usa o LibreOffice, que o PythonAnywhere não oferece por padrão. Esse módulo pode continuar rodando na oficina até ser adaptado.
- **Erros:** se o site mostrar "Something went wrong", veja o **Error log** na aba "Web".
- **Senha de app do Gmail:** fica só no `.env` do servidor e nunca vai para o GitHub.
