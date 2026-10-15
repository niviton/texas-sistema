# Liga o Polaris de DESENVOLVIMENTO: http://127.0.0.1:8001 (só neste computador, dados de teste).
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..'))
python manage.py runserver 127.0.0.1:8001
