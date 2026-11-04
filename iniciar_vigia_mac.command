#!/bin/bash
cd "$(dirname "$0")"
echo "================================================================"
echo "    MODO VIGIA CONTÍNUO STI (SINCRONIZAÇÃO AUTOMÁTICA A CADA 30M) "
echo "================================================================"
if [ -d ".venv" ]; then
    .venv/bin/python3 sync_agent.py --loop 30
else
    python3 sync_agent.py --loop 30
fi
