# Polaris em servidor (máquina virtual): passo a passo

Este guia coloca o Polaris de verdade numa máquina virtual neste computador e mantém o desenvolvimento separado. A proposta e os motivos estão em [docs/deploy/servidor-maquina-virtual.md](../docs/deploy/servidor-maquina-virtual.md).

**Importante:** os scripts desta pasta foram escritos e conferidos (sintaxe, travas de segurança, testes do lado do sistema), mas a instalação dentro da máquina virtual só pode ser testada de verdade nos passos 3 a 8. Siga a ordem, e se alguma mensagem de erro aparecer, mande para mim.

O que existe aqui:

| Pasta | Para que serve |
|---|---|
| `windows/` | Atalhos de duplo clique e comandos que rodam no Windows (criar a máquina virtual, publicar, voltar, backup) |
| `vm/` | Programas que rodam dentro da máquina virtual (instalar, publicar, backup) |

---

## Passo 0. Pedir ao TI (pode mandar hoje)

A rede da empresa tem servidor próprio de endereços (DHCP) e de nomes (DNS). Como o IP deste computador já mudou duas vezes, e os QR codes e celulares dependem dele, o TI precisa fixar. Mande esta mensagem:

> Olá! Preciso de uma reserva de IP (DHCP) para o computador **E12780**, que vai rodar o sistema Polaris da Oficina Técnica (acessado por celulares na rede interna).
>
> - Wi-Fi: MAC `2C-98-11-53-E4-F9` (IP atual: 192.168.1.59)
> - Cabo de rede: MAC `20-88-10-87-80-DC`
>
> Se for possível, também gostaria de um nome no DNS interno apontando para esse IP, por exemplo `polaris.texascontrols.local`. Assim o endereço do sistema não depende do número do IP.
>
> Obrigado!

Se o TI criar o nome, avise: o certificado e os QR codes passam a usar o nome, e aí o IP pode até mudar sem estragar nada. Enquanto o TI não responde, tudo continua funcionando; só **espere para imprimir QR codes** até o endereço estar fixo.

## Passo 1. Ligar o Hyper-V

Hyper-V é o recurso do Windows que cria o "computador dentro do computador". Já vem no seu Windows 11 Pro, só está desligado.

1. Abra a pasta `deploy\windows`.
2. Dê dois cliques em **`1-ATIVAR-HYPERV.bat`** e aceite o pedido de administrador.
3. **Reinicie o computador.** (O mesmo atalho já impede o computador de suspender sozinho quando ligado na tomada.)

## Passo 2. Baixar o Ubuntu Server

1. Entre em **ubuntu.com/download/server** e baixe o **Ubuntu Server 24.04 LTS** (arquivo `.iso`, uns 3 GB).
2. Crie a pasta `C:\VMs` e salve o arquivo lá.

## Passo 3. Criar a máquina virtual e instalar o Ubuntu

1. Dê dois cliques em **`2-CRIAR-VM.bat`**. Ele cria a máquina virtual (2 GB de memória, 2 núcleos, disco de até 40 GB, liga sozinha com o Windows) e abre a tela dela.
2. Na tela da máquina virtual, o instalador do Ubuntu aparece. Responda assim:
   - Idioma: **Português** (ou English, como preferir) e teclado: **Portuguese (Brazil)**.
   - Tipo de instalação: **Ubuntu Server**.
   - **Rede:** escolha a placa, **Edit IPv4**, método **Manual** e preencha:
     - Subnet: `192.168.50.0/24`
     - Address: `192.168.50.10`
     - Gateway: `192.168.50.1`
     - Name servers: `8.8.8.8,1.1.1.1`
   - Armazenamento: aceite o padrão (disco inteiro).
   - **Perfil:** seu nome `Polaris`, nome do servidor `polaris`, **usuário `polaris`** e uma senha (anote em lugar seguro).
   - **Install OpenSSH server**: marque (sim).
   - Pacotes extras ("snaps"): não marque nenhum.
3. Quando terminar, escolha **Reboot Now**. Se pedir para remover o disco de instalação, aperte Enter.
4. Se ele voltar para o instalador, desligue a máquina virtual e rode no PowerShell (como administrador):
   `Get-VMDvdDrive -VMName Polaris | Set-VMDvdDrive -Path $null`
   e ligue de novo.

## Passo 4. Conectar o Windows à máquina virtual sem senha

No PowerShell comum (não precisa de administrador):

```powershell
ssh-keygen -t ed25519
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh polaris@192.168.50.10 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

(Aperte Enter nas perguntas do primeiro comando; no segundo, digite a senha do usuário `polaris`. Se perguntar "continue connecting", digite `yes`.) Teste: `ssh polaris@192.168.50.10 "echo funcionou"`.

## Passo 5. Certificado para o novo servidor

Os celulares já têm o certificado da empresa instalado. Só é preciso gerar o certificado do servidor, com a mesma autoridade, e enviar para a máquina virtual. Na pasta do projeto:

```powershell
python manage.py certificado_local 192.168.1.59
scp ssl_local\polaris.crt ssl_local\polaris.key polaris@192.168.50.10:/home/polaris/
```

(Se o TI criar o nome, use: `python manage.py certificado_local 192.168.1.59 polaris.texascontrols.local`.)

## Passo 6. Instalar o Polaris dentro da máquina virtual

Antes, a pasta `deploy` precisa estar no GitHub (já está, depois do commit desta etapa). Entre na máquina virtual e instale:

```powershell
ssh polaris@192.168.50.10
```

Já dentro dela:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/niviton/texas-sistema.git
sudo bash texas-sistema/deploy/vm/provisionar.sh https://192.168.1.59:8443
```

(Ou o endereço com o nome, se o TI criou.) Leva uns 5 a 10 minutos. No final deve aparecer **"PRONTO. O Polaris respondeu (HTTP 200)"**.

Depois, preencha o e-mail na máquina virtual (use o mesmo usuário e a senha de app que estão no `.env` do seu computador):

```bash
nano /opt/polaris/app/.env      # preencher EMAIL_HOST_USER e EMAIL_HOST_PASSWORD
sudo systemctl restart polaris
```

## Passo 7. Levar os dados de hoje para a máquina virtual

No Windows, pare o servidor atual para o banco ficar parado e copie:

```powershell
Stop-ScheduledTask -TaskName "Polaris - servidor"
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*servidor.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
scp db.sqlite3 polaris@192.168.50.10:/home/polaris/
scp -r media polaris@192.168.50.10:/home/polaris/media-hoje
Start-ScheduledTask -TaskName "Polaris - servidor"
```

Dentro da máquina virtual (`ssh polaris@192.168.50.10`):

```bash
sudo systemctl stop polaris
cp ~/db.sqlite3 /opt/polaris/dados/db.sqlite3
rsync -a ~/media-hoje/ /opt/polaris/dados/media/
cd /opt/polaris/app && /opt/polaris/venv/bin/python manage.py migrate --noinput
sudo systemctl start polaris
rm -rf ~/db.sqlite3 ~/media-hoje
```

Esse passo é repetido na virada (passo 9), para levar o que foi registrado no meio tempo.

## Passo 8. Ensaio lado a lado (nada muda para a equipe)

1. Na máquina virtual, libere o endereço de ensaio no Django: `nano /opt/polaris/app/.env` e acrescente a linha
   `DJANGO_CSRF_TRUSTED_ORIGINS=https://192.168.1.59:9443`
   depois `sudo systemctl restart polaris`.
2. No Windows, dois cliques em **`3-ENSAIO-PORTAS.bat`**. O servidor atual continua na 8443.
3. No celular, abra **https://192.168.1.59:9443**, entre e faça um checklist de teste com foto e assinatura. Confira se o e-mail chegou.

## Passo 9. A virada

1. Avise a equipe (leva uns 10 minutos).
2. Repita o **passo 7** (copiar os dados de novo, para levar o que foi registrado depois do ensaio).
3. Na máquina virtual, apague a linha `DJANGO_CSRF_TRUSTED_ORIGINS` do `.env` e reinicie (`sudo systemctl restart polaris`).
4. No Windows, dois cliques em **`4-VIRADA-PORTAS.bat`** e digite SIM. O endereço de sempre, **https://192.168.1.59:8443**, passa a levar para a máquina virtual. O servidor antigo fica desligado, mas intacto, por 1 semana.
5. Marque a primeira versão e publique, na pasta do projeto: `.\deploy\windows\publicar.ps1 v1.0`
6. Teste no celular.
7. Deixe o desenvolvimento seguro: `.\deploy\windows\preparar-dev.ps1`. Isso tira a senha do Gmail do seu `.env`, para um teste seu nunca mandar e-mail de verdade.

---

## Depois: a rotina

**Desenvolver:** `.\deploy\windows\desenvolver.ps1` e abra `http://127.0.0.1:8001` (dados de teste, sem e-mail).

**Publicar uma versão pronta:** salve tudo com commit e rode
```powershell
.\deploy\windows\publicar.ps1 v1.1
```
Ele roda os testes, envia ao GitHub e atualiza a máquina virtual. Se a versão nova não subir, volta sozinho para a anterior. Use sempre o próximo número (v1.2, v1.3...).

**Voltar uma versão:**
```powershell
.\deploy\windows\voltar.ps1 v1.0                  # só o código
.\deploy\windows\voltar.ps1 v1.0 -RestaurarBanco  # código e banco (perde o que foi registrado depois)
```

**Backup semanal no pen drive** (espete o pen drive e rode):
```powershell
.\deploy\windows\backup-para-pendrive.ps1 -Destino E:\backup-polaris
```
Além disso, a máquina virtual guarda sozinha um backup por dia (14 dias).

**Se o IP do computador mudar** (e o TI ainda não fixou): rode no Windows
`python manage.py certificado_local <novo-ip>`, envie o `polaris.crt` e o `polaris.key` de novo (passo 5), e na máquina virtual `sudo bash /opt/polaris/app/deploy/vm/provisionar.sh https://<novo-ip>:8443`. As etiquetas QR já impressas precisarão ser impressas de novo.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| O Polaris não abre no celular | O computador está ligado e a máquina virtual também? No Windows: `Get-VM Polaris` deve mostrar `Running` |
| Máquina virtual desligada | `Start-VM Polaris` (PowerShell como administrador) |
| Mensagem de erro ao publicar | Rode `ssh polaris@192.168.50.10 "journalctl -u polaris -n 50 --no-pager"` e me mande o resultado |
| Disco enchendo | `ssh polaris@192.168.50.10 "df -h /"`; apague backups antigos em `/opt/polaris/backups` |
| E-mail não sai | Confira `EMAIL_HOST_USER` e `EMAIL_HOST_PASSWORD` em `/opt/polaris/app/.env` |
