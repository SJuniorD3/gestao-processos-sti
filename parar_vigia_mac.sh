#!/bin/bash
cd "$(dirname "$0")"

PID_FILE="sync_agent.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "[*] Encerrando Agente Vigia STI (PID: $PID)..."
        kill "$PID"
        rm -f "$PID_FILE"
        echo "[✓] Agente Vigia encerrado com sucesso."
        exit 0
    fi
    rm -f "$PID_FILE"
fi

echo "[!] O Agente Vigia não está em execução."
