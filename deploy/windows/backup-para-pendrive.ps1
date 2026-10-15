# Copia os backups da máquina virtual para o pen drive (ou qualquer pasta fora deste computador).
#
#   .\deploy\windows\backup-para-pendrive.ps1 -Destino E:\backup-polaris
#
# Faça isso uma vez por semana. O backup que fica só dentro da máquina virtual não protege
# contra um defeito no disco do computador.
param(
    [Parameter(Mandatory = $true)][string]$Destino,
    [string]$Servidor = 'polaris@192.168.50.10'
)
$ErrorActionPreference = 'Stop'
$pasta = Join-Path $Destino (Get-Date -Format 'yyyy-MM-dd')
New-Item -ItemType Directory -Force $pasta | Out-Null
Write-Host "Copiando os backups para $pasta ..."
scp -r -o StrictHostKeyChecking=accept-new "${Servidor}:/opt/polaris/backups" $pasta
if ($LASTEXITCODE -ne 0) { throw 'A cópia falhou. A máquina virtual está ligada?' }
# guarda só as 8 últimas semanas no pen drive
Get-ChildItem $Destino -Directory | Sort-Object Name -Descending | Select-Object -Skip 8 | Remove-Item -Recurse -Force
Write-Host 'Pronto. Bancos de dados e fotos copiados.'
