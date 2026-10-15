# Deixa o ambiente de DESENVOLVIMENTO (esta pasta) seguro depois que a produção passa para a máquina virtual:
#  - tira a senha do Gmail (um teste seu nunca manda e-mail de verdade para a equipe);
#  - usa o endereço http://127.0.0.1:8001 só neste computador;
#  - liga o modo de desenvolvimento.
# Guarda uma cópia do .env antigo em .env.antes-da-vm.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..'))
if (-not (Test-Path .env)) { throw 'Não achei o arquivo .env nesta pasta.' }
Copy-Item .env .env.antes-da-vm -Force

$linhas = Get-Content .env -Encoding UTF8
$saida = foreach ($l in $linhas) {
    if ($l -match '^\s*(EMAIL_HOST_USER|EMAIL_HOST_PASSWORD)\s*=') { "# (desligado no desenvolvimento) $l" }
    elseif ($l -match '^\s*SITE_URL\s*=') { 'SITE_URL=http://127.0.0.1:8001' }
    elseif ($l -match '^\s*DJANGO_DEBUG\s*=') { 'DJANGO_DEBUG=True' }
    else { $l }
}
$saida | Set-Content .env -Encoding UTF8
Write-Host 'Pronto. Para trabalhar: .\deploy\windows\desenvolver.ps1  (abre http://127.0.0.1:8001)'
Write-Host 'Os e-mails agora só aparecem no terminal, sem enviar nada.'
