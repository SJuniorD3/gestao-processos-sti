import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import datetime
import requests
import json
from config import (
    EMAIL_ENABLED, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO,
    WEBHOOK_URL
)
from database import (
    listar_processos, listar_projetos_com_processos, registrar_log_relatorio,
    formatar_data_br, formatar_data_hora_br
)

def gerar_conteudo_resumo(tipo="Agendado"):
    """Gera tanto a versão HTML quanto a versão Texto/Markdown do resumo diário.
       AGRUPADO POR PROJETO: Um projeto pode conter múltiplos processos (SEI e STARTGOV).
       Monitore ESTRITAMENTE somente os processos cadastrados ativos para monitoramento."""
    projetos = listar_projetos_com_processos(apenas_monitorados=True)
    agora = datetime.datetime.now()
    data_formatada = agora.strftime("%d/%m/%Y às %H:%M")
    
    total_projetos = len(projetos)
    todos_processos = []
    for p in projetos:
        todos_processos.extend(p.get("processos", []))

    total = len(todos_processos)
    na_sti = sum(1 for proc in todos_processos if "STI" in proc["local_atual"].upper())
    fora_sti = total - na_sti
    criticos = sum(1 for proc in todos_processos if (proc["dias_no_setor"] or 0) > 60)
    
    # ------------------ TEXTO / MARKDOWN AGRUPADO POR PROJETO ------------------
    txt_linhas = []
    txt_linhas.append(f"[STI] RESUMO DE PROCESSOS POR PROJETO ({tipo.upper()})")
    txt_linhas.append(f"Emissao: {data_formatada}")
    txt_linhas.append(f"Total de Projetos: {total_projetos} | Total de Processos Monitorados: {total}")
    txt_linhas.append(f"No setor STI: {na_sti} | Em outros setores: {fora_sti} | Em alerta (>60 dias): {criticos}")
    txt_linhas.append("=" * 64)
    
    for idx_proj, proj in enumerate(projetos, 1):
        procs = proj.get("processos", [])
        txt_linhas.append(f"\n[PROJETO {idx_proj}] {proj['nome'].upper()} ({len(procs)} processos vinculados)")
        if proj.get("descricao"):
            txt_linhas.append(f"Objeto: {proj['descricao']}")
        txt_linhas.append("-" * 50)

        for j, p in enumerate(procs, 1):
            dias = f"{p['dias_no_setor']} dias" if p['dias_no_setor'] is not None else "-"
            txt_linhas.append(f"  ({j}) Sistema: {p['sistema']} | Nº: {p['numero_processo']}")
            txt_linhas.append(f"      Local Atual: {p['local_atual']} (Tempo no Setor: {dias})")
            txt_linhas.append(f"      Ação: {p['acao']}")
            txt_linhas.append(f"      Situação: {p['situacao']}")
            
            status_list = p.get("ultimos_4_status", [])
            if status_list:
                txt_linhas.append("      Últimos 4 Status (4 Movimentações Mais Recentes):")
                for idx_s, s in enumerate(status_list, 1):
                    dt_reg = formatar_data_hora_br(s.get("data_movimentacao") or s.get("data_registro", ""))
                    tag_rec = " [Mais Recente - Posição Atual]" if idx_s == 1 else f" [{idx_s}ª Mais Recente]"
                    txt_linhas.append(f"        • Linha {idx_s}{tag_rec}: [{dt_reg}] ({s.get('local', '-')}) {s.get('situacao', '-')}")
            txt_linhas.append("")

    txt_linhas.append("=" * 64)
    txt_linhas.append("Superintendencia de Tecnologia da Informacao - STI")
    texto_resumo = "\n".join(txt_linhas)

    # ------------------ VERSÃO HTML AGRUPADA POR PROJETO ------------------
    html_projetos = ""
    for proj in projetos:
        procs = proj.get("processos", [])
        total_p = len(procs)

        linhas_proc = ""
        for i, p in enumerate(procs):
            dias = f"{p['dias_no_setor']} dias" if p['dias_no_setor'] is not None else "-"
            badge_dias_cor = "#ef4444" if (p['dias_no_setor'] or 0) > 60 else ("#f59e0b" if (p['dias_no_setor'] or 0) > 30 else "#10b981")
            badge_sistema_cor = "#facc15" if p['sistema'].upper() == "SEI" else "#3b82f6"
            badge_sistema_text = "#854d0e" if p['sistema'].upper() == "SEI" else "#ffffff"

            status_items = ""
            for idx_s, s in enumerate(p.get("ultimos_4_status", []), 1):
                dt_s = formatar_data_hora_br(s.get("data_movimentacao") or s.get("data_registro", ""))
                tag_rec = " <span style='color: #059669; font-size: 10px; font-weight: bold;'>(Mais Recente)</span>" if idx_s == 1 else ""
                status_items += f"""
                <li style="margin-bottom: 5px; font-size: 11px; color: #374151;">
                    <span style="font-weight: bold; color: #2563eb;">Linha {idx_s}:</span> <strong>[{dt_s}]</strong> <span style="background: #e5e7eb; padding: 1px 5px; border-radius: 4px; font-weight: 600;">{s.get('local', '-')}</span>: {s.get('situacao', '-')}{tag_rec}
                </li>
                """
            if not status_items:
                status_items = "<li style='color: #9ca3af; font-size: 11px;'>Sem histórico anterior</li>"

            # Mescla visual da primeira coluna do projeto
            coluna_projeto = ""
            coluna_desc = ""
            if i == 0:
                coluna_projeto = f"""
                <td rowspan="{total_p}" style="padding: 12px; vertical-align: top; font-weight: bold; font-size: 14px; color: #1e3a8a; border-right: 2px solid #cbd5e1; background: #f8fafc;">
                    {proj['nome']}
                    <span style="display: block; font-size: 11px; color: #64748b; font-weight: normal; margin-top: 4px;">({total_p} processos vinculados)</span>
                </td>
                """
                coluna_desc = f"""
                <td rowspan="{total_p}" style="padding: 12px; vertical-align: top; font-size: 12px; color: #475569; max-width: 220px; border-right: 1px solid #e2e8f0; background: #f8fafc;">
                    {proj['descricao'] or '-'}
                </td>
                """

            linhas_proc += f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                {coluna_projeto}
                <td style="padding: 10px; vertical-align: top; text-align: center;">
                    <span style="background: {badge_sistema_cor}; color: {badge_sistema_text}; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{p['sistema']}</span>
                </td>
                <td style="padding: 10px; vertical-align: top; font-family: monospace; font-size: 12px; font-weight: bold; color: #2563eb;">
                    {p['numero_processo']}
                </td>
                {coluna_desc}
                <td style="padding: 10px; vertical-align: top;">
                    <span style="background: #e0e7ff; color: #3730a3; padding: 3px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">{p['local_atual']}</span>
                </td>
                <td style="padding: 10px; vertical-align: top; text-align: center;">
                    <span style="background: {badge_dias_cor}; color: white; padding: 3px 7px; border-radius: 10px; font-weight: bold; font-size: 11px;">{dias}</span>
                </td>
                <td style="padding: 10px; vertical-align: top; font-size: 12px; color: #1f2937;">
                    <strong>Ação:</strong> {p['acao']}<br>
                    <strong>Situação:</strong> {p['situacao']}
                </td>
                <td style="padding: 10px; vertical-align: top; background: #fafafa;">
                    <ol style="margin: 0; padding-left: 16px;">
                        {status_items}
                    </ol>
                </td>
            </tr>
            """

        html_projetos += linhas_proc

    html_resumo = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Resumo de Processos por Projeto - STI</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px;">
        <div style="max-width: 1180px; margin: auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
            <div style="background: #0f172a; color: white; padding: 20px 24px; border-bottom: 3px solid #2563eb;">
                <h1 style="margin: 0; font-size: 20px;">Resumo Executivo de Processos por Projeto - STI</h1>
                <p style="margin: 4px 0 0; opacity: 0.85; font-size: 13px;">Superintendência de Tecnologia da Informação • Emissão: <strong>{data_formatada}</strong> ({tipo})</p>
            </div>
            
            <div style="display: flex; gap: 12px; padding: 14px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                <div style="flex: 1; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Total de Projetos</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #0f172a;">{total_projetos}</h3>
                </div>
                <div style="flex: 1; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Processos Monitorados</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #2563eb;">{total}</h3>
                </div>
                <div style="flex: 1; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">No Setor STI</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #059669;">{na_sti}</h3>
                </div>
                <div style="flex: 1; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Fora da STI</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #64748b;">{fora_sti}</h3>
                </div>
                <div style="flex: 1; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Alerta (>60 dias)</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #ef4444;">{criticos}</h3>
                </div>
            </div>

            <div style="padding: 20px; overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead>
                        <tr style="background: #64748b; color: white; text-align: left;">
                            <th style="padding: 10px;">Projeto</th>
                            <th style="padding: 10px; text-align: center;">Sistema</th>
                            <th style="padding: 10px;">Nº Processo</th>
                            <th style="padding: 10px;">Descrição do Projeto</th>
                            <th style="padding: 10px;">Local Atual</th>
                            <th style="padding: 10px; text-align: center;">Dias</th>
                            <th style="padding: 10px;">Ação / Situação</th>
                            <th style="padding: 10px;">Últimos 4 Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {html_projetos}
                    </tbody>
                </table>
            </div>

            <div style="background: #f8fafc; padding: 14px 24px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0;">
                Sistema Automatizado de Monitoramento da STI • Disparos programados às 08:00, 12:00 e 16:00.
            </div>
        </div>
    </body>
    </html>
    """

    return {
        "texto": texto_resumo,
        "html": html_resumo,
        "total": total,
        "total_projetos": total_projetos,
        "data_formatada": data_formatada
    }

def enviar_email(assunto, corpo_html, corpo_texto):
    """Envia o e-mail via servidor SMTP configurado."""
    if not EMAIL_ENABLED or not SMTP_USER or not EMAIL_TO:
        return False, "Envio por e-mail desabilitado ou credenciais incompletas no .env"
    
    destinatarios = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]
    if not destinatarios:
        return False, "Nenhum destinatário de e-mail especificado."
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(destinatarios)
        
        part_text = MIMEText(corpo_texto, "plain", "utf-8")
        part_html = MIMEText(corpo_html, "html", "utf-8")
        msg.attach(part_text)
        msg.attach(part_html)
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, destinatarios, msg.as_string())
        server.quit()
        return True, f"Enviado para: {', '.join(destinatarios)}"
    except Exception as e:
        return False, f"Erro SMTP: {str(e)}"

def enviar_webhook(texto):
    """Envia o resumo para um Webhook configurado (WhatsApp API, Telegram, Teams, Discord)."""
    if not WEBHOOK_URL:
        return False, "Webhook não configurado no .env"
    
    try:
        payload = {"text": texto, "content": texto}
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return True, f"Webhook disparado com sucesso (Status {resp.status_code})"
        else:
            return False, f"Webhook retornou status {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, f"Erro ao chamar Webhook: {str(e)}"

def executar_envio_resumo(tipo="Agendado"):
    """Função central chamada pelo agendador ou manualmente."""
    resumo = gerar_conteudo_resumo(tipo)
    assunto = f"[STI] Resumo de Processos ({tipo}) - {resumo['data_formatada']}"
    
    status_email = "Não configurado"
    if EMAIL_ENABLED:
        ok_mail, msg_mail = enviar_email(assunto, resumo["html"], resumo["texto"])
        status_email = "Sucesso: " + msg_mail if ok_mail else "Falha: " + msg_mail
        
    status_webhook = "Não configurado"
    if WEBHOOK_URL:
        ok_hook, msg_hook = enviar_webhook(resumo["texto"])
        status_webhook = "Sucesso: " + msg_hook if ok_hook else "Falha: " + msg_hook
        
    status_final = f"Email: {status_email} | Webhook: {status_webhook}"
    
    # Registra no log de relatórios
    registrar_log_relatorio(
        tipo=tipo,
        total_processos=resumo["total"],
        destinatarios=EMAIL_TO if EMAIL_ENABLED else "Nenhum (Log local)",
        status=status_final,
        conteudo=resumo["texto"]
    )
    
    return {
        "assunto": assunto,
        "status": status_final,
        "resumo_texto": resumo["texto"],
        "resumo_html": resumo["html"],
        "total": resumo["total"],
        "data_formatada": resumo["data_formatada"]
    }
