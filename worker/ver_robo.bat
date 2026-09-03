@echo off
chcp 65001 >nul
title Robo Consorbens - LOG AO VIVO (pode fechar sem parar o robo)
color 0B
cd /d "%~dp0"
echo.
echo   Mostrando o log do robo ao vivo. Esta janela e SO leitura —
echo   fechar aqui NAO para o robo. Ctrl+C para sair.
echo.
powershell -NoProfile -Command "if (Test-Path logs\robo.log) { Get-Content logs\robo.log -Tail 40 -Wait } else { Write-Host 'Ainda nao existe logs\robo.log — o robo ja subiu?' }"
