@echo off
chcp 65001 > nul
title Agente Vigia STI - Sincronizacao Continua a cada 30m
cd /d "%~dp0"
echo ================================================================
echo   MODO VIGIA CONTÍNUO STI (SINCRONIZAÇÃO AUTOMÁTICA A CADA 30M)
echo ================================================================
echo [*] Este processo monitora o SEI e o StartGov automaticamente.
echo [*] Pressione Ctrl+C para encerrar.
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" sync_agent.py --loop 30
) else (
    python sync_agent.py --loop 30
)

pause
