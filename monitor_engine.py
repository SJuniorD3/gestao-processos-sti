import datetime
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from database import (
    listar_processos, obter_processo, atualizar_processo, salvar_historico_4_status, get_connection,
    salvar_documentos_processo
)
from integrations import sei_client, startgov_client

def executar_monitoramento_processos(callback_progresso=None):
    """
    Executa a rotina de monitoramento automático nos sistemas oficiais (SEI e STARTGOV).
    Acessa os portais com as credenciais fornecidas e atualiza:
    - Local Atual
    - Data de Recebimento
    - Ação
    - Situação
    - 4 Últimos Status
    Para TODOS os processos cadastrados ativos para monitoramento.
    """
    processos = listar_processos(apenas_monitorados=True)
    total = len(processos)
    atualizados = 0
    detalhes = []

    print(f"[*] Iniciando rotina de monitoramento de {total} processos cadastrados...")

    for i, proc in enumerate(processos, 1):
        num_proc = proc["numero_processo"]
        sistema = proc["sistema"].upper()
        msg_progresso = f"[{i}/{total}] Consultando {num_proc} no sistema {sistema}..."
        print(f"    {msg_progresso}")
        if callback_progresso:
            callback_progresso(i, total, msg_progresso)

        resultado = None
        if sistema == "SEI":
            resultado = sei_client.consultar_processo(num_proc)
        elif sistema == "STARTGOV":
            resultado = startgov_client.consultar_processo(num_proc)
        else:
            resultado = {"sucesso": False, "mensagem": f"Sistema '{sistema}' não possui integração automática configurada."}

        if resultado.get("sucesso") and (resultado.get("local_atual") or resultado.get("situacao")):
            dados_atualizados = {
                "projeto": proc["projeto"],
                "sistema": proc["sistema"],
                "numero_processo": proc["numero_processo"],
                "descricao": proc["descricao"],
                "local_atual": resultado.get("local_atual") or proc["local_atual"],
                "data_recebimento": resultado.get("data_recebimento") or proc["data_recebimento"],
                "acao": resultado.get("acao") or proc["acao"] or ("Trâmite SEI" if sistema == "SEI" else "Trâmite StartGov"),
                "situacao": resultado.get("situacao") or proc["situacao"],
                "monitorar": proc.get("monitorar", 1),
                "observacao_historico": f"Atualizado pelo robô de monitoramento ({sistema})"
            }

            if resultado.get("historico_4_linhas"):
                salvar_historico_4_status(proc["id"], resultado["historico_4_linhas"], sistema=sistema)
                atualizar_processo(proc["id"], dados_atualizados, registrar_novo_status=False)
            else:
                atualizar_processo(proc["id"], dados_atualizados, registrar_novo_status=True)

            if resultado.get("documentos"):
                salvar_documentos_processo(proc["id"], resultado["documentos"])

            atualizados += 1
            detalhes.append({
                "processo": num_proc,
                "sistema": sistema,
                "status": "Atualizado com sucesso",
                "local": dados_atualizados["local_atual"],
                "situacao": dados_atualizados["situacao"],
                "linhas_capturadas": len(resultado.get("historico_4_linhas", []))
            })
        else:
            # Caso a conexão remota não responda (ex: portal fora do ar, rede restrita ou captcha)
            motivo = resultado.get("mensagem", "Sem resposta do portal")
            detalhes.append({
                "processo": num_proc,
                "sistema": sistema,
                "status": f"Falha ao consultar: {motivo}",
                "local": proc["local_atual"],
                "situacao": proc["situacao"]
            })

    resumo_execucao = {
        "data_hora": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "total_verificados": total,
        "total_atualizados": atualizados,
        "detalhes": detalhes
    }
    print(f"[OK] Monitoramento concluido. {atualizados}/{total} processos atualizados.")
    return resumo_execucao

def monitorar_processo_individual(processo_id):
    """Executa a consulta de monitoramento para um único processo."""
    proc = obter_processo(processo_id)
    if not proc:
        return {"sucesso": False, "mensagem": "Processo não encontrado no banco."}

    num_proc = proc["numero_processo"]
    sistema = proc["sistema"].upper()

    if sistema == "SEI":
        res = sei_client.consultar_processo(num_proc)
    elif sistema == "STARTGOV":
        res = startgov_client.consultar_processo(num_proc)
    else:
        return {"sucesso": False, "mensagem": f"Sistema '{sistema}' não suportado para consulta automática."}

    if res.get("sucesso"):
        dados_atualizados = {
            "projeto": proc["projeto"],
            "sistema": proc["sistema"],
            "numero_processo": proc["numero_processo"],
            "descricao": proc["descricao"],
            "local_atual": res.get("local_atual") or proc["local_atual"],
            "data_recebimento": res.get("data_recebimento") or proc["data_recebimento"],
            "acao": res.get("acao") or proc["acao"] or ("Trâmite SEI" if sistema == "SEI" else "Trâmite StartGov"),
            "situacao": res.get("situacao") or proc["situacao"],
            "monitorar": proc.get("monitorar", 1),
            "observacao_historico": f"Sincronização manual do processo ({sistema})"
        }
        if res.get("historico_4_linhas"):
            salvar_historico_4_status(proc["id"], res["historico_4_linhas"], sistema=sistema)
            atualizar_processo(proc["id"], dados_atualizados, registrar_novo_status=False)
        else:
            atualizar_processo(proc["id"], dados_atualizados, registrar_novo_status=True)

        if res.get("documentos"):
            salvar_documentos_processo(proc["id"], res["documentos"])

        return {
            "sucesso": True,
            "mensagem": "Processo atualizado com sucesso via portal oficial!",
            "dados": dados_atualizados,
            "andamentos_capturados": len(res.get("historico_4_linhas", []))
        }
    else:
        return {"sucesso": False, "mensagem": res.get("mensagem", "Não foi possível extrair dados.")}
