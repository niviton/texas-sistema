@echo off
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Pedindo permissao de administrador...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
echo VIRADA: o endereco de sempre (porta 8443) passa a levar para a maquina virtual.
echo O servidor atual do Windows sera DESLIGADO (fica guardado como plano B).
set /p OK=Digite SIM para continuar: 
if /i not "%OK%"=="SIM" exit /b
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0redirecionar-portas.ps1"
echo.
pause
