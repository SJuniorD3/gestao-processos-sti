#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
  AGENTE DE SINCRONIZAÇÃO EM TEMPO REAL - STI / SEDUC-MA (MODO VIGIA CONTÍNUO)
=============================================================================
Este script roda em qualquer máquina da STI conectada à rede da SEDUC/Governo.
Ele consulta o SEI-MA e o STARTGOV com o IP local autorizado e atualiza
o banco de dados Supabase na nuvem automaticamente a cada X minutos.

Modos de uso:
  python sync_agent.py              (Sincronização imediata de 1 ciclo)
  python sync_agent.py --loop 30    (Modo Vigia Contínuo a cada 30 minutos)
=============================================================================
"""

import sys
import time
import datetime
import argparse
import os
import socket
import logging
from pathlib import Path

# Configuração de Logs em Arquivo e Console
BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "sync_agent.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SyncAgentSTI")

# Força resolução estritamente IPv4 para compatibilidade total de rede
try:
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

from config import (
    DATABASE_URL, DATABASE_FILE,
    SEI_USER, SEI_PASS, SEI_URL,
    STARTGOV_USER, STARTGOV_PASS, STARTGOV_URL
)
from database import (
    init_db,
    listar_processos,
    obter_processo,
    atualizar_processo,
    salvar_historico_4_status,
    salvar_documentos_processo,
    registrar_auditoria,
    get_is_postgres
)
from integrations import sei_client, startgov_client

DEFAULT_INTERVAL_MINUTES = int(os.environ.get("SYNC_INTERVAL_MINUTES", "30"))

def imprimir_banner():
    modo_db = "Supabase PostgreSQL (Nuvem)" if get_is_postgres() else "SQLite (Local)"
    logger.info("=" * 68)
    logger.info("      AGENTE DE SINCRONIZAÇÃO EM TEMPO REAL - STI / SEDUC-MA        ")
    logger.info("=" * 68)
    logger.info(f"[*] Banco de Dados Conectado : {modo_db}")
    logger.info(f"[*] Credenciais SEI          : {'Configuradas (' + SEI_USER + ')' if SEI_USER else 'NÃO configuradas'}")
    logger.info(f"[*] Credenciais StartGov     : {'Configuradas (' + STARTGOV_USER + ')' if STARTGOV_USER else 'NÃO configuradas'}")
    logger.info(f"[*] Arquivo de Logs          : {LOG_FILE}")
    logger.info("=" * 68 + "\n")

def executar_ciclo_sincronizacao():
    """
    Executa uma rodada completa de sincronização de todos os processos monitorados.
    Possui tratamento completo de exceções para garantir que oscilações temporárias
    de internet nunca derrubem o agente em modo vigia contínuo.
    """
    logger.info("[>] Iniciando verificação dos processos monitorados...")
    try:
        processos = listar_processos(apenas_monitorados=True)
    except Exception as e_db:
        logger.error(f"[!] Erro ao consultar processos no banco de dados: {e_db}")
        return 0, 0

    if not processos:
        logger.info("[!] Nenhum processo marcado para monitoramento ativo no banco.")
        return 0, 0

    sucessos = 0
    falhas = 0

    for idx, proc in enumerate(processos, 1):
        num_proc = proc.get("numero_processo", "")
        sistema = str(proc.get("sistema", "")).upper()
        p_id = proc.get("id")

        logger.info(f"[{idx}/{len(processos)}] Consultando {sistema}: {num_proc} ...")

        res = None
        try:
            if sistema == "SEI":
                res = sei_client.consultar_processo(num_proc)
            elif sistema == "STARTGOV":
                res = startgov_client.consultar_processo(num_proc)
            else:
                logger.warning(f"    [IGNORADO] Sistema '{sistema}' não suportado.")
                falhas += 1
                continue
        except Exception as e_con:
            logger.error(f"    [ERRO DE CONEXÃO] Falha ao consultar {sistema} ({num_proc}): {e_con}")
            falhas += 1
            continue

        if res and res.get("sucesso"):
            sucessos += 1
            setor = res.get("local_atual") or proc["local_atual"] or "Sem local"
            total_and = len(res.get("historico_4_linhas", []))
            total_docs = len(res.get("documentos", []))

            dados_atualizados = {
                "projeto": proc["projeto"],
                "sistema": proc["sistema"],
                "numero_processo": proc["numero_processo"],
                "descricao": proc["descricao"],
                "local_atual": setor,
                "data_recebimento": res.get("data_recebimento") or proc["data_recebimento"],
                "acao": res.get("acao") or proc["acao"] or ("Trâmite SEI" if sistema == "SEI" else "Trâmite StartGov"),
                "situacao": res.get("situacao") or proc["situacao"],
                "monitorar": proc.get("monitorar", 1),
                "observacao_historico": f"Sincronização via Agente Vigia STI ({sistema})"
            }

            try:
                if res.get("historico_4_linhas"):
                    salvar_historico_4_status(p_id, res["historico_4_linhas"], sistema=sistema)
                    atualizar_processo(p_id, dados_atualizados, registrar_novo_status=False)
                else:
                    atualizar_processo(p_id, dados_atualizados, registrar_novo_status=True)

                if res.get("documentos"):
                    salvar_documentos_processo(p_id, res["documentos"])

                logger.info(f"    ✓ OK! Setor: '{setor}' | Andamentos: {total_and} | Peças: {total_docs}")
            except Exception as e_save:
                logger.error(f"    [ERRO AO GRAVAR NO BANCO] Processo {num_proc}: {e_save}")
        else:
            falhas += 1
            erro_msg = res.get("mensagem", "Sem resposta") if res else "Falha desconhecida"
            logger.warning(f"    ✕ NÃO ATUALIZADO: {erro_msg}")

    # Registro de auditoria
    try:
        registrar_auditoria(
            "sync_agent_vigia",
            "SYNC_VIGIA_CONTINUO",
            f"Ciclo concluído: {sucessos} sucesso(s), {falhas} falha(s) de {len(processos)} processos",
            "127.0.0.1"
        )
    except Exception:
        pass

    logger.info(f"[*] Resumo do Ciclo: {sucessos} processo(s) atualizado(s) | {falhas} falha(s).\n")
    return sucessos, falhas

def main():
    parser = argparse.ArgumentParser(description="Agente Local de Sincronização STI (SEI & StartGov -> Supabase)")
    parser.add_argument(
        "--loop",
        type=int,
        nargs="?",
        const=DEFAULT_INTERVAL_MINUTES,
        default=0,
        help=f"Ativa o Modo Vigia Contínuo a cada X minutos (padrão: {DEFAULT_INTERVAL_MINUTES}m)"
    )
    args = parser.parse_args()

    imprimir_banner()

    # Inicializa ou migra o banco de dados se necessário
    try:
        init_db()
    except Exception as e:
        logger.warning(f"[!] Conexão inicial com banco de dados: {e}")

    intervalo = args.loop
    if intervalo and intervalo > 0:
        logger.info(f"[🔄] MODO VIGIA CONTÍNUO ATIVADO: executando automaticamente a cada {intervalo} minuto(s).")
        logger.info("[*] Para encerrar a qualquer momento, pressione Ctrl+C.\n")

        while True:
            try:
                executar_ciclo_sincronizacao()
            except Exception as e_ciclo:
                logger.error(f"[!] Ocorreu uma exceção inesperada durante o ciclo: {e_ciclo}")

            proxima = datetime.datetime.now() + datetime.timedelta(minutes=intervalo)
            logger.info(f"[⏳] Aguardando próximo ciclo às {proxima.strftime('%H:%M:%S')} (dormindo {intervalo} minutos)...")
            try:
                time.sleep(intervalo * 60)
            except KeyboardInterrupt:
                logger.info("\n[!] Modo Vigia Contínuo finalizado voluntariamente pelo usuário.")
                break
    else:
        # Execução única
        executar_ciclo_sincronizacao()
        logger.info("[✓] Sincronização finalizada com sucesso!")

if __name__ == "__main__":
    main()
