@echo off
chcp 65001 >nul
title Robo de Lances - Consorbens
color 0A

echo.
echo   ============================================================
echo      ROBO DE OFERTA DE LANCES - CONSORBENS
echo   ============================================================
echo.
echo   Vou processar os lances que estao na fila do CRM.
echo   Deixe esta janela ABERTA enquanto ele trabalha.
echo   Para parar a qualquer momento: feche a janela ou Ctrl+C.
echo.
echo   ------------------------------------------------------------
echo.

REM Entra na pasta do robo (mesmo lugar deste arquivo)
cd /d "%~dp0"

REM Confere se o Python esta instalado
where python >nul 2>nul
if errorlevel 1 (
    echo   [ERRO] Python nao encontrado neste PC.
    echo   Instale o Python e rode a instalacao do robo antes ^(veja o README^).
    echo.
    pause
    exit /b 1
)

REM Liga o robo
python worker_lances.py

echo.
echo   ============================================================
echo      O robo foi encerrado. Pode fechar esta janela.
echo   ============================================================
echo.
pause
