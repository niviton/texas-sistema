# Cria a máquina virtual do Polaris (Hyper-V). Roda como administrador (o 2-CRIAR-VM.bat já pede isso).
param(
    [string]$Iso,
    [string]$Pasta = 'C:\VMs\Polaris',
    [int]$MemoriaGB = 2,
    [int]$DiscoGB = 40
)
$ErrorActionPreference = 'Stop'

if (-not (Get-Command New-VM -ErrorAction SilentlyContinue)) {
    throw 'O Hyper-V ainda não está ativo. Rode antes o 1-ATIVAR-HYPERV.bat e reinicie o computador.'
}
if (Get-VM -Name Polaris -ErrorAction SilentlyContinue) {
    throw 'Já existe uma máquina virtual chamada Polaris. Nada foi alterado.'
}

# Arquivo de instalação do Ubuntu Server (ISO)
if (-not $Iso) {
    $achou = Get-ChildItem 'C:\VMs', "$env:USERPROFILE\Downloads" -Filter 'ubuntu-*server*.iso' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($achou) { $Iso = $achou.FullName }
}
if (-not $Iso -or -not (Test-Path $Iso)) {
    throw "Não achei o arquivo ISO do Ubuntu Server. Baixe 'Ubuntu Server 24.04 LTS' em ubuntu.com/download/server e salve em C:\VMs (ou na pasta Downloads)."
}
Write-Host "ISO: $Iso"
New-Item -ItemType Directory -Force $Pasta | Out-Null

# Rede interna da VM (192.168.50.0/24) com saída para a internet (NAT)
$sw = 'PolarisNAT'
if (-not (Get-VMSwitch -Name $sw -ErrorAction SilentlyContinue)) { New-VMSwitch -Name $sw -SwitchType Internal | Out-Null }
$ifc = "vEthernet ($sw)"
if (-not (Get-NetIPAddress -InterfaceAlias $ifc -IPAddress 192.168.50.1 -ErrorAction SilentlyContinue)) {
    New-NetIPAddress -IPAddress 192.168.50.1 -PrefixLength 24 -InterfaceAlias $ifc | Out-Null
}
if (-not (Get-NetNat -Name $sw -ErrorAction SilentlyContinue)) {
    New-NetNat -Name $sw -InternalIPInterfaceAddressPrefix 192.168.50.0/24 | Out-Null
}

# A máquina virtual
New-VM -Name Polaris -Generation 2 -MemoryStartupBytes ($MemoriaGB * 1GB) `
    -NewVHDPath "$Pasta\polaris.vhdx" -NewVHDSizeBytes ($DiscoGB * 1GB) -SwitchName $sw -Path $Pasta | Out-Null
Set-VMMemory Polaris -DynamicMemoryEnabled $true -MinimumBytes 1GB -StartupBytes ($MemoriaGB * 1GB) -MaximumBytes ($MemoriaGB * 1GB)
Set-VMProcessor Polaris -Count 2
Set-VMFirmware Polaris -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority
$dvd = Add-VMDvdDrive Polaris -Path $Iso -Passthru
Set-VMFirmware Polaris -FirstBootDevice $dvd
# Liga sozinha quando o Windows liga (mesmo sem ninguém ter entrado na conta) e desliga com segurança
Set-VM Polaris -AutomaticStartAction Start -AutomaticStartDelay 30 -AutomaticStopAction ShutDown -AutomaticCheckpointsEnabled $false
Enable-VMIntegrationService -VMName Polaris -Name 'Guest Service Interface'

Start-VM Polaris
Write-Host ''
Write-Host 'Máquina virtual criada e ligada. Agora siga o passo 3 do deploy\LEIA-ME.md (instalar o Ubuntu).'
Write-Host 'Abrindo a tela da máquina virtual...'
Start-Process vmconnect.exe -ArgumentList 'localhost', 'Polaris'
