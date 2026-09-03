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

where python >nul 2>nul
if errorlevel 1 (
    echo   [ERRO] Python nao encontrado neste PC.
    pause
    exit /b 1
)

if not exist logs mkdir logs

REM Sobe o supervisor. stdout/stderr tambem vao pro console.log (o robo.log
REM ja e escrito pelo proprio Python).
python worker_consorbens.py >> logs\console.log 2>&1

echo.
echo   ============================================================
echo      O robo foi encerrado. Pode fechar esta janela.
echo   ============================================================
echo.
pause
