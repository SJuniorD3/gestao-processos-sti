#!/bin/bash
cd "$(dirname "$0")"

PID_FILE="sync_agent.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "[!] O Agente Vigia já está rodando em segundo plano (PID: $PID)."
        exit 0
    fi
fi

echo "[*] Iniciando Agente Vigia STI em segundo plano (a cada 30 minutos)..."

if [ -d ".venv" ]; then
    PYTHON_CMD=".venv/bin/python3"
else
    PYTHON_CMD="python3"
fi

nohup $PYTHON_CMD sync_agent.py --loop 30 >> sync_agent.log 2>&1 &
PID=$!
echo $PID > "$PID_FILE"

echo "[✓] Agente iniciado com sucesso em segundo plano!"
echo "[*] PID do processo: $PID"
echo "[*] Acompanhe os logs em tempo real executando: tail -f sync_agent.log"
