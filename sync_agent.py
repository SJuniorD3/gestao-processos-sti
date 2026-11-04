#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
  AGENTE DE SINCRONIZAÇÃO LOCAL STI (SEI-MA & STARTGOV -> SUPABASE)
=============================================================================
Este script roda em qualquer máquina conectada à rede da STI / SEDUC-MA.
Ele realiza o login nos portais oficiais (com o IP autorizado da rede local)
e atualiza o banco de dados Supabase na nuvem em tempo real.
=============================================================================
"""

import sys
import time
import datetime
import argparse
import os
import socket

# Força resolução IPv4 para máxima compatibilidade de rede
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

def imprimir_banner():
    print("=" * 68)
    print("      AGENTE DE SINCRONIZAÇÃO EM TEMPO REAL - STI / SEDUC-MA        ")
    print("=" * 68)
    modo_db = "Supabase PostgreSQL (Nuvem)" if get_is_postgres() else "SQLite (Local)"
    print(f"[*] Banco de Dados Conectado : {modo_db}")
    print(f"[*] Credenciais SEI          : {'Configuradas (' + SEI_USER + ')' if SEI_USER else 'NÃO configuradas'}")
    print(f"[*] Credenciais StartGov     : {'Configuradas (' + STARTGOV_USER + ')' if STARTGOV_USER else 'NÃO configuradas'}")
    print(f"[*] Data/Hora de Início      : {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 68 + "\n")

def executar_ciclo_sincronizacao():
    """Executa uma rodada completa de sincronização de todos os processos monitorados."""
    processos = listar_processos(apenas_monitorados=True)
    if not processos:
        print("[!] Nenhum processo marcado para monitoramento ativo no banco.")
        return 0, 0

    print(f"[>] Iniciando verificação de {len(processos)} processo(s) monitorado(s)...\n")

    sucessos = 0
    falhas = 0

    for idx, proc in enumerate(processos, 1):
        num_proc = proc["numero_processo"]
        sistema = str(proc.get("sistema", "")).upper()
        p_id = proc["id"]

        print(f"[{idx}/{len(processos)}] Consultando {sistema}: {num_proc} ...", end=" ", flush=True)

        res = None
        if sistema == "SEI":
            res = sei_client.consultar_processo(num_proc)
        elif sistema == "STARTGOV":
            res = startgov_client.consultar_processo(num_proc)
        else:
            print(f"[IGNORADO] Sistema '{sistema}' não suportado.")
            falhas += 1
            continue

        if res and res.get("sucesso"):
            sucessos += 1
            setor = res.get("local_atual") or proc["local_atual"] or "Sem local"
            total_and = len(res.get("historico_4_linhas", []))
            total_docs = len(res.get("documentos", []))

            # Monta payload com dados atualizados
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
                "observacao_historico": f"Sincronização via Agente STI ({sistema})"
            }

            if res.get("historico_4_linhas"):
                salvar_historico_4_status(p_id, res["historico_4_linhas"], sistema=sistema)
                atualizar_processo(p_id, dados_atualizados, registrar_novo_status=False)
            else:
                atualizar_processo(p_id, dados_atualizados, registrar_novo_status=True)

            if res.get("documentos"):
                salvar_documentos_processo(p_id, res["documentos"])

            print(f"✓ OK! -> Setor: '{setor}' | Andamentos: {total_and} | Peças: {total_docs}")
        else:
            falhas += 1
            erro_msg = res.get("mensagem", "Sem resposta") if res else "Falha desconhecida"
            print(f"✕ FALHA: {erro_msg}")

    # Registra no log de auditoria
    registrar_auditoria(
        "sync_agent_local",
        "SYNC_AGENTE_LOCAL",
        f"Sincronização concluída: {sucessos} sucesso(s), {falhas} falha(s) de {len(processos)} processos",
        "127.0.0.1"
    )

    print("\n" + "-" * 68)
    print(f"[*] Resumo da Rodada: {sucessos} processo(s) atualizado(s) com sucesso | {falhas} falha(s).")
    print(f"[*] Os dados já estão gravados e visíveis no sistema web em tempo real.")
    print("-" * 68 + "\n")

    return sucessos, falhas

def main():
    parser = argparse.ArgumentParser(description="Agente Local de Sincronização STI (SEI & StartGov -> Supabase)")
    parser.add_argument("--loop", type=int, default=0, help="Intervalo em minutos para rodar continuamente em segundo plano (Ex: --loop 30)")
    args = parser.parse_args()

    imprimir_banner()

    # Garante que o schema do banco exista
    try:
        init_db()
    except Exception as e:
        print(f"[!] Aviso na conexão com o banco de dados: {e}")

    if args.loop and args.loop > 0:
        print(f"[🔄] Modo Vigia Contínuo ativado: executando a cada {args.loop} minuto(s).")
        print("[*] Pressione Ctrl+C para encerrar o agente a qualquer momento.\n")
        try:
            while True:
                executar_ciclo_sincronizacao()
                proxima_execucao = datetime.datetime.now() + datetime.timedelta(minutes=args.loop)
                print(f"[⏳] Aguardando próximo ciclo em {proxima_execucao.strftime('%H:%M:%S')} (dormindo {args.loop}m)...")
                time.sleep(args.loop * 60)
        except KeyboardInterrupt:
            print("\n[!] Agente de sincronização encerrado pelo usuário.")
    else:
        # Execução única (1 clique)
        executar_ciclo_sincronizacao()
        print("[✓] Processo finalizado com sucesso!")

if __name__ == "__main__":
    main()
