@echo off
chcp 65001 >nul
title Robo Unico - Consorbens
color 0A

echo.
echo   ============================================================
echo      ROBO UNICO - CONSORBENS  (lance / boleto / coletas / robos de API)
echo   ============================================================
echo.
echo   Deixe esta janela ABERTA (pode minimizar).
echo   Config: worker\robo_config.toml  ^|  Log: worker\logs\robo.log
echo   Para parar: feche a janela ou Ctrl+C.
echo.

REM Entra na pasta do robo (mesmo lugar deste arquivo)
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo   [ERRO] Python (py launcher) nao encontrado neste PC.
    pause
    exit /b 1
)

if not exist logs mkdir logs

REM (04/11/2026: python padrao virou 3.15 sem as libs do robo -> fixado no 3.14)
REM Sobe o supervisor. stdout/stderr tambem vao pro console.log (o robo.log
REM ja e escrito pelo proprio Python).
py -V:3.14 worker_consorbens.py >> logs\console.log 2>&1

echo.
echo   ============================================================
echo      O robo foi encerrado. Pode fechar esta janela.
echo   ============================================================
echo.
pause
