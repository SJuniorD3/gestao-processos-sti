@echo off
chcp 65001 > nul
title Agente de Sincronizacao STI (SEI & StartGov)
cd /d "%~dp0"
echo ================================================================
echo   Iniciando Agente de Sincronizacao STI (SEI ^& StartGov)
echo ================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" sync_agent.py
) else (
    python sync_agent.py
)
echo.
pause
