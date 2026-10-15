# Publica uma versão do Polaris na máquina virtual (produção).
#
#   .\deploy\windows\publicar.ps1 v1.4
#
# O que faz: confere que está tudo salvo (commit), roda os testes, marca a versão, envia ao GitHub
# (branch "producao") e manda a máquina virtual atualizar. Se a versão nova não subir, ela volta sozinha.
param(
    [Parameter(Mandatory = $true)][string]$Versao,
    [switch]$PularTestes,
    [string]$Servidor = 'polaris@192.168.50.10'
)
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..'))

if ($Versao -notmatch '^v\d+(\.\d+)*$') { throw "Use o formato v1.4 (letra v e números). Você digitou: $Versao" }
if (git status --porcelain) { throw 'Há alterações sem commit. Faça o commit antes de publicar.' }
$ramo = (git rev-parse --abbrev-ref HEAD).Trim()
if ($ramo -ne 'main') { throw "Você está na branch '$ramo'. Publique a partir da 'main'." }
if (git tag --list $Versao) { throw "A versão $Versao já existe. Escolha o próximo número (veja: git tag)." }

if (-not $PularTestes) {
    Write-Host '==> Rodando os testes...'
    python manage.py test termos checklists veiculos accounts dashboard
    if ($LASTEXITCODE -ne 0) { throw 'Os testes falharam. Nada foi publicado.' }
}

Write-Host "==> Enviando $Versao ao GitHub"
git tag -a $Versao -m "Versão $Versao"
git push origin main
git push origin "main:refs/heads/producao"
git push origin $Versao

Write-Host "==> Atualizando a máquina virtual ($Servidor)"
ssh -o StrictHostKeyChecking=accept-new $Servidor "/opt/polaris/app/deploy/vm/publicar.sh $Versao"
if ($LASTEXITCODE -ne 0) { throw "A publicação de $Versao não concluiu. Veja as mensagens acima; a versão anterior foi mantida." }
Write-Host "Pronto: $Versao está no ar."
