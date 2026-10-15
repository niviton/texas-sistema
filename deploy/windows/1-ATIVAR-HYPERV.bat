@echo off
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Pedindo permissao de administrador...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
echo.
echo Ligando o Hyper-V (o recurso do Windows que cria o computador virtual)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -NoRestart"
echo.
echo Impedindo que o computador suspenda sozinho quando ligado na tomada...
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
echo.
echo PRONTO. Agora REINICIE o computador. Depois do reinicio, rode o 2-CRIAR-VM.bat
pause
