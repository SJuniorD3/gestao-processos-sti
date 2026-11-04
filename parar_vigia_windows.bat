@echo off
chcp 65001 > nul
echo Encerrando processo do Agente Vigia STI...
wmic process where "commandline like '%%sync_agent.py%%'" call terminate > nul 2>&1
echo [OK] Agente Vigia STI encerrado.
timeout /t 3 > nul
