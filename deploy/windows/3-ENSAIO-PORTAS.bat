@echo off
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Pedindo permissao de administrador...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
echo ENSAIO: libera as portas 9443 e 9000 para testar a maquina virtual. O servidor atual NAO e desligado.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0redirecionar-portas.ps1" -Teste
echo.
pause
