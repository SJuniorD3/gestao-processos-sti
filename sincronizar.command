#!/bin/bash
cd "$(dirname "$0")"
echo "Iniciando Agente de Sincronização STI..."
if [ -d ".venv" ]; then
    .venv/bin/python3 sync_agent.py
else
    python3 sync_agent.py
fi
echo ""
read -p "Pressione ENTER para fechar..."
