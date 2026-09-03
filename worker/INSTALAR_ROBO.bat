@echo off
chcp 65001 >nul
title Instalar Robo Unico Consorbens (startup + watchdog)
cd /d "%~dp0"

echo ============================================================
echo   INSTALAR ROBO UNICO - CONSORBENS
echo   Faz 2 coisas:
echo    1) atalho na Inicializacao do Windows (sobe SEM janela no logon)
echo    2) tarefa "watchdog a cada 2 min" no Agendador (re-sobe se cair)
echo ============================================================
echo.
echo   Rode este arquivo como ADMINISTRADOR (botao direito - Executar
echo   como administrador) para a parte 2 funcionar.
echo.
pause

set "AQUI=%~dp0"
set "VBS=%AQUI%iniciar_robo_oculto.vbs"

echo.
echo [1/2] Criando atalho na Inicializacao...
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell); $lnk=$s.CreateShortcut([Environment]::GetFolderPath('Startup')+'\Robo Consorbens.lnk'); $lnk.TargetPath='wscript.exe'; $lnk.Arguments='\"%VBS%\"'; $lnk.WorkingDirectory='%AQUI%'; $lnk.Save(); Write-Host '   OK: ' ([Environment]::GetFolderPath('Startup')+'\Robo Consorbens.lnk')"

echo.
echo [2/2] Registrando o watchdog no Agendador (a cada 2 min)...
schtasks /Create /F /TN "Robo Consorbens - Watchdog" ^
  /TR "python \"%AQUI%watchdog_robo.py\"" ^
  /SC MINUTE /MO 2 /RL LIMITED
if errorlevel 1 (
  echo   [!] Nao consegui criar a tarefa. Rode este .bat COMO ADMINISTRADOR
  echo       ou crie a tarefa na mao (ver SETUP_SEMPRE_LIGADO.md, secao 4).
) else (
  echo   OK: tarefa "Robo Consorbens - Watchdog" criada.
)

echo.
echo ============================================================
echo   PRONTO. No proximo logon o robo sobe sozinho (sem janela).
echo   Pra ver o robo: 2 cliques em  ver_robo.bat
echo   Pra subir agora sem reiniciar:  wscript "%VBS%"
echo ============================================================
echo.
pause
