# Faz o endereço deste computador (o IP do Windows) levar para a máquina virtual.
# Roda como administrador (o 3-REDIRECIONAR-PORTAS.bat já pede isso).
#
#   -Teste   ensaio: usa as portas 9443 e 9000, sem mexer no servidor atual (que continua na 8443)
#   (sem)    virada: usa 8443 e 8000 e DESLIGA o servidor atual do Windows
param([switch]$Teste)
$ErrorActionPreference = 'Stop'

$vm = '192.168.50.10'
$https = if ($Teste) { 9443 } else { 8443 }
$http = if ($Teste) { 9000 } else { 8000 }

if (-not $Teste) {
    Write-Host 'Desligando o servidor atual do Windows (ele usa a porta 8443)...'
    Get-ScheduledTask -TaskName 'Polaris - servidor' -ErrorAction SilentlyContinue | Disable-ScheduledTask | Out-Null
    Get-ScheduledTask -TaskName 'Polaris - alertas da frota' -ErrorAction SilentlyContinue | Disable-ScheduledTask | Out-Null
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -like '*servidor.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Sleep -Seconds 2
}

Set-Service iphlpsvc -StartupType Automatic
Start-Service iphlpsvc

foreach ($par in @(@($https, 8443), @($http, 8000))) {
    $entrada, $destino = $par
    netsh interface portproxy delete v4tov4 listenport=$entrada listenaddress=0.0.0.0 | Out-Null
    netsh interface portproxy add v4tov4 listenport=$entrada listenaddress=0.0.0.0 connectport=$destino connectaddress=$vm | Out-Null
    Remove-NetFirewallRule -DisplayName "Polaris $entrada" -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "Polaris $entrada" -Direction Inbound -Protocol TCP -LocalPort $entrada -Action Allow | Out-Null
}

Write-Host ''
netsh interface portproxy show v4tov4
Write-Host ''
if ($Teste) {
    Write-Host "Ensaio pronto: abra https://$((Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi').IPAddress):$https no celular."
} else {
    Write-Host 'Virada feita: o endereço de sempre agora leva para a máquina virtual.'
    Write-Host 'O servidor antigo do Windows ficou desligado, mas intacto, como plano B.'
}
