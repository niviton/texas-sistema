# Proposta: Polaris em servidor (máquina virtual) com desenvolvimento separado

Data: 15/10/2026. Situação: proposta para decisão, nada foi instalado ainda.

## 1. A ideia em poucas linhas

- O **Polaris de verdade** (o que a equipe usa, com os dados reais) roda dentro de uma **máquina virtual** neste computador. Ela liga sozinha com o Windows e ocupa um pedaço pequeno de memória.
- O **Polaris de desenvolvimento** continua nesta pasta, como hoje, com dados de teste. Você mexe, quebra e conserta à vontade, sem afetar a equipe.
- Quando uma mudança estiver pronta, você manda para o GitHub e roda **um comando de publicação**. A máquina virtual baixa a versão nova, atualiza o banco e reinicia sozinha. Se algo der errado, volta para a versão anterior com outro comando.

## 2. O que este computador tem hoje (medido em 15/10/2026)

| Item | Situação | O que significa |
|---|---|---|
| Windows | 11 Pro | Tem o Hyper-V (máquina virtual gratuita da Microsoft) |
| Processador | Core i5-13400F, 10 núcleos | Sobra capacidade |
| Memória | 16 GB (1,7 GB livres no momento da medição) | É o ponto de atenção: a VM pede cerca de 2 GB |
| Disco | 208 GB livres | De sobra (a VM começa com uns 6 GB usados) |
| Virtualização | Ligada | Pronto para usar |
| Hyper-V | Ainda não instalado | Precisa ligar um recurso do Windows e reiniciar uma vez |
| Rede | Só Wi-Fi em uso (a porta de cabo existe, mas está desconectada) | Muda como a VM se conecta (item 4.2) |

## 3. Como fica

```
  CELULARES E COMPUTADORES DA OFICINA
                 |  https://192.168.1.59:8443   (o mesmo endereço de hoje)
                 v
  +------------------------- ESTE COMPUTADOR (Windows 11) --------------------------+
  |                                                                                 |
  |   DESENVOLVIMENTO                          PRODUÇÃO (máquina virtual, Linux)    |
  |   pasta atual do projeto                   Ubuntu Server 24.04                  |
  |   porta 8001, só neste PC                  nginx (HTTPS) -> gunicorn -> Polaris |
  |   banco e fotos de TESTE                   banco e fotos REAIS                  |
  |   e-mail desligado                         e-mail real (Gmail)                  |
  |           |                                       ^                             |
  +-----------|---------------------------------------|-----------------------------+
              | git push                              | publicar (git pull + migrate)
              v                                       |
          GITHUB (branch "main"  ->  branch "producao")
```

## 4. Decisões e por quê

### 4.1 Tecnologia da máquina virtual: Hyper-V com Ubuntu Server
- É gratuito e já faz parte do Windows 11 Pro.
- Tem a opção **"iniciar automaticamente"**: a VM liga quando o Windows liga, **mesmo sem ninguém ter entrado na conta**. Também desliga com segurança quando o Windows desliga.
- Ubuntu Server é o padrão de mercado para sistemas Django: o que funcionar aí funciona igual em um servidor na nuvem no futuro.
- Alternativas descartadas: VirtualBox (mais lento e mais problemas com Hyper-V ligado), WSL2 (não é um servidor de verdade; para quando ninguém está logado).

### 4.2 Rede: como o celular chega na VM mesmo com o computador no Wi-Fi
Ligar a VM direto na rede Wi-Fi ("ponte") costuma ser instável. Em vez disso:
- A VM fica numa **rede interna** do próprio computador (por exemplo `192.168.50.10`).
- O Windows **redireciona a porta 8443** para a VM.
- Resultado: o endereço continua sendo o **IP deste computador**, `https://192.168.1.59:8443`. Os QR codes já impressos e os celulares com o certificado instalado **continuam funcionando**.

Duas providências para isso ficar estável:
1. **Reservar o IP** deste computador no roteador (hoje já mudou duas vezes).
2. Se possível, ligar um **cabo de rede**. O Wi-Fi funciona, mas cabo é mais confiável para um servidor.

### 4.3 Dados: produção e desenvolvimento nunca se misturam
- A produção tem o **próprio banco e as próprias fotos**. Na virada, copia-se **uma vez** o banco e as fotos de hoje para a VM.
- Depois disso, **o banco de desenvolvimento nunca vai para a produção**. O que muda entre os dois é só o código; mudanças na estrutura do banco chegam pelo comando `migrate`, que preserva os dados.
- Para testar com dados reais, o caminho é só um: copiar um backup **da produção para o desenvolvimento**.
- O desenvolvimento roda **sem as credenciais do Gmail**, para um teste seu nunca mandar e-mail de verdade para a equipe.

### 4.4 Como publicar uma versão nova
1. Você desenvolve e testa aqui, e faz o commit normalmente.
2. Quando estiver satisfeito, você junta o trabalho na branch `producao` e marca uma versão (por exemplo `v1.4`).
3. Você roda **`publicar`**. O script, via SSH:
   - faz uma cópia de segurança do banco;
   - baixa a versão nova (`git pull`);
   - instala dependências novas, aplica `migrate` e `collectstatic`;
   - reinicia o Polaris e confere se a página inicial responde;
   - **se algo falhar, volta sozinho para a versão anterior**.
4. Para voltar a mão: `voltar v1.3`.

O repositório é público, então a VM baixa o código sem senha. O arquivo `.env` (chave secreta, senha do Gmail) existe **só dentro da VM** e nunca vai para o GitHub.

### 4.5 HTTPS
Reaproveita a **mesma autoridade certificada local** que os celulares já instalaram. Só o certificado do servidor é gerado de novo (para o IP deste computador). Ninguém precisa reinstalar nada.

### 4.6 Backup
- **Todo dia, de madrugada**, dentro da VM: cópia consistente do banco e das fotos, guardando as últimas 14.
- Uma cópia diária vai para uma pasta do Windows **fora do OneDrive**.
- **Uma vez por semana**, uma cópia em outro lugar (pen drive ou nuvem). Sem isso, um defeito no disco leva produção e backup juntos.
- Os arquivos da VM ficam em `C:\VMs\Polaris`, **fora do OneDrive** (o OneDrive já danificou o Git uma vez e poderia corromper o disco da VM).

### 4.7 Liga e desliga
- O computador precisa estar ligado e **sem suspender** (Configurações do Windows, Energia).
- Se o Windows reiniciar para atualizar, a VM sobe sozinha junto.
- Se preferir ligar à mão, existe a opção de um atalho "Ligar Polaris".

### 4.8 Alertas diários da frota
O agendamento passa do Windows para a VM (cron, às 7h, fuso America/Fortaleza). A tarefa atual do Windows é desativada na virada.

## 5. O que a VM ocupa

| Recurso | Reservado | Observação |
|---|---|---|
| Memória | 2 GB (dinâmica, de 1 a 2 GB) | Hoje há só 1,7 GB livres; feche programas pesados ou limite a 1,5 GB |
| Processador | 2 núcleos | Quase não usa quando ninguém acessa |
| Disco | até 40 GB (cresce só conforme enche) | Cerca de 6 GB no início; fotos somam uns 3 MB por registro |

## 6. Comparativo das opções

| Opção | Liga sozinha | Separa teste de produção | Custo | Observação |
|---|---|---|---|---|
| **VM Hyper-V (esta proposta)** | Sim, antes do login | Sim | Zero | Mesma receita serve para a nuvem depois |
| Como está hoje (Windows direto) | Só depois do login | Não: o mesmo código e banco | Zero | Cada teste seu mexe no sistema da equipe |
| PythonAnywhere gratuito | Sim | Parcial | Zero | Expira todo mês, 512 MB, sem tarefa diária; só funciona com dados e fotos pequenos |
| Servidor na nuvem (VPS) | Sim | Sim | Cerca de R$ 30 a 60 por mês | Não depende deste computador; é a evolução natural |

## 7. Plano de implantação

| Fase | O que acontece | Quem | Tempo |
|---|---|---|---|
| 0. Preparação | Ligar o Hyper-V (um comando como administrador) e reiniciar; reservar o IP no roteador; desligar a suspensão do PC | Você | 15 min |
| 1. Receita | Eu preparo no repositório os scripts: criar a VM e a rede, instalar o servidor, `publicar`, `voltar`, backup. Testo tudo numa VM de teste | Eu | 1 a 2 sessões |
| 2. Ensaio | Cria a VM definitiva, copia o banco e as fotos, e sobe a produção numa porta paralela (9443) para testar lado a lado com a atual | Juntos | 1 h |
| 3. Virada | Desativa o servidor atual do Windows, passa a porta 8443 para a VM, confere no celular. O servidor antigo fica desligado, mas intacto, por 1 semana como plano B | Juntos | 15 min |
| 4. Rotina | Desenvolvimento normal; `publicar` quando quiser | Você | ... |

Eu não consigo concluir a Fase 1 sozinho enquanto o Hyper-V não estiver ativo, porque preciso testar os scripts numa VM de verdade.

## 8. Sua rotina depois de pronto

1. Desenvolve em `C:\...\texas` e abre `http://127.0.0.1:8001` (dados de teste).
2. Faz commit e push no GitHub como hoje.
3. Quando estiver pronto: junta em `producao`, marca a versão e roda `publicar`.
4. Confere no celular. Se algo estiver errado: `voltar v1.3`.

## 9. Riscos e como tratamos

| Risco | O que fazemos |
|---|---|
| Computador desligado ou suspenso | Desligar a suspensão; avisar a equipe se for desligar; nobreak seria ideal |
| Windows reinicia para atualizar | VM com início automático |
| Wi-Fi cai | Cabo de rede; IP reservado |
| Memória apertada durante o desenvolvimento | VM limitada a 2 GB; acompanhar o uso |
| Uma versão nova quebra algo | Backup antes de cada publicação e volta automática |
| Disco enche de fotos | Alerta de espaço; arquivar fotos antigas |
| Defeito no disco | Backup semanal fora do computador |

## 10. Segurança

- Só acessível dentro da rede da oficina; o Windows libera apenas a porta 8443 (e a 22 só para o seu computador, para publicar).
- Acesso de administração à VM por chave SSH, sem senha.
- Atualizações de segurança do Ubuntu automáticas.
- Pendente no sistema (independe da VM): limite de tentativas de login.

## 11. O que não muda

O endereço (`https://192.168.1.59:8443`), os QR codes impressos, o certificado nos celulares, os usuários, os papéis, os checklists e todos os dados.

## 12. O que preciso que você decida

1. **Hyper-V:** posso contar com ligar esse recurso do Windows (pede reiniciar uma vez)?
2. **Rede:** vai reservar o IP no roteador e consegue ligar um cabo de rede?
3. **Memória:** 2 GB para a VM está bom para você?
4. **Backup semanal:** onde guardar a cópia fora do computador (pen drive, Google Drive da empresa)?
5. **Branch `producao`:** aceita esse fluxo de junção e versões marcadas?

## Apêndice: comandos de referência (esboço, a validar na Fase 1)

Ligar o Hyper-V (PowerShell como administrador, depois reiniciar):
```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
```

Rede interna e redirecionamento da porta 8443 para a VM (depois que a VM existir):
```powershell
New-VMSwitch -Name PolarisNAT -SwitchType Internal
New-NetIPAddress -IPAddress 192.168.50.1 -PrefixLength 24 -InterfaceAlias "vEthernet (PolarisNAT)"
New-NetNat -Name PolarisNAT -InternalIPInterfaceAddressPrefix 192.168.50.0/24
netsh interface portproxy add v4tov4 listenport=8443 listenaddress=0.0.0.0 connectport=8443 connectaddress=192.168.50.10
New-NetFirewallRule -DisplayName "Polaris 8443" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow
```

Início automático da VM:
```powershell
Set-VM -Name Polaris -AutomaticStartAction Start -AutomaticStopAction ShutDown -AutomaticStartDelay 30
```
