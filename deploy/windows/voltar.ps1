# Volta a produção para uma versão anterior.
#
#   .\deploy\windows\voltar.ps1 v1.3                   volta o código
#   .\deploy\windows\voltar.ps1 v1.3 -RestaurarBanco   volta o código E o banco ao estado de antes da última publicação
#                                                      (cuidado: registros feitos depois dela são perdidos)
param(
    [Parameter(Mandatory = $true)][string]$Versao,
    [switch]$RestaurarBanco,
    [string]$Servidor = 'polaris@192.168.50.10'
)
$ErrorActionPreference = 'Stop'
if ($RestaurarBanco) {
    $r = Read-Host 'Isso apaga os registros feitos depois da última publicação. Digite SIM para continuar'
    if ($r -ne 'SIM') { throw 'Cancelado.' }
}
$extra = if ($RestaurarBanco) { '--restaurar' } else { '' }
ssh -o StrictHostKeyChecking=accept-new $Servidor "/opt/polaris/app/deploy/vm/publicar.sh $Versao $extra"
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível voltar. Veja as mensagens acima.' }
