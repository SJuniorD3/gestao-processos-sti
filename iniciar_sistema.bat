@echo off
title Sistema de Gestao e Monitoramento de Processos STI
cd /d "%~dp0"
python app_gui.py
if errorlevel 1 pause
