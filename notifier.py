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
    na_sti = sum(1 for proc in todos_processos if "STI" in (proc.get("local_atual") or "").upper())
    fora_sti = total - na_sti
    criticos = sum(1 for proc in todos_processos if (proc.get("dias_no_setor") or 0) > 60)
    total_contratos = sum(1 for proj in projetos if (proj.get("etiqueta") or "Contratos") == "Contratos")
    total_pagamentos = sum(1 for proj in projetos if proj.get("etiqueta") == "Pagamentos")
    
    # ------------------ TEXTO / MARKDOWN AGRUPADO POR PROJETO ------------------
    txt_linhas = []
    txt_linhas.append(f"[STI] RESUMO DE PROCESSOS POR PROJETO ({tipo.upper()})")
    txt_linhas.append(f"Emissao: {data_formatada}")
    txt_linhas.append(f"Total de Projetos: {total_projetos} (Contratos: {total_contratos} | Pagamentos: {total_pagamentos})")
    txt_linhas.append(f"Processos Monitorados: {total} | No setor STI: {na_sti} | Em outros setores: {fora_sti} | Em alerta (>60 dias): {criticos}")
    txt_linhas.append("=" * 64)
    
    if not projetos:
        txt_linhas.append("\nNenhum processo monitorado ativo cadastrado no sistema.")

    for idx_proj, proj in enumerate(projetos, 1):
        procs = proj.get("processos", [])
        etq_proj = proj.get("etiqueta") or "Contratos"
        setor_proj = proj.get("setor_sigla") or "STI"
        txt_linhas.append(f"\n[PROJETO {idx_proj}] {proj['nome'].upper()} [SETOR: {setor_proj}] [{etq_proj.upper()}] ({len(procs)} processos vinculados)")
        if proj.get("descricao"):
            txt_linhas.append(f"Objeto: {proj['descricao']}")
        txt_linhas.append("-" * 50)

        for j, p in enumerate(procs, 1):
            dias = f"{p['dias_no_setor']} dias" if p.get('dias_no_setor') is not None else "-"
            tot_docs = p.get('total_documentos', 0)
            docs_txt = f" | Peças SEI: {tot_docs}" if tot_docs > 0 else ""
            txt_linhas.append(f"  ({j}) Sistema: {p.get('sistema', 'SEI')} | Nº: {p.get('numero_processo', '-')}{docs_txt}")
            txt_linhas.append(f"      Local Atual: {p.get('local_atual') or '-'} (Tempo no Setor: {dias})")
            txt_linhas.append(f"      Ação: {p.get('acao') or '-'}")
            txt_linhas.append(f"      Situação: {p.get('situacao') or '-'}")
            
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
            dias = f"{p['dias_no_setor']} dias" if p.get('dias_no_setor') is not None else "-"
            badge_dias_cor = "#ef4444" if (p.get('dias_no_setor') or 0) > 60 else ("#f59e0b" if (p.get('dias_no_setor') or 0) > 30 else "#10b981")
            sis = str(p.get('sistema') or "SEI").upper()
            badge_sistema_cor = "#facc15" if sis == "SEI" else "#3b82f6"
            badge_sistema_text = "#854d0e" if sis == "SEI" else "#ffffff"

            tot_docs = p.get('total_documentos', 0)
            badge_docs = f'<br><span style="display:inline-block; font-size:10px; background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; padding:1px 5px; border-radius:4px; font-weight:bold; margin-top:3px;">📎 {tot_docs} peças</span>' if tot_docs > 0 else ''

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
                etq = proj.get('etiqueta') or 'Contratos'
                etq_cor = "#047857" if etq == "Pagamentos" else "#1d4ed8"
                etq_bg = "#ecfdf5" if etq == "Pagamentos" else "#eff6ff"
                etq_border = "#a7f3d0" if etq == "Pagamentos" else "#bfdbfe"
                etq_icon = "💳" if etq == "Pagamentos" else "📄"
                setor_sig = proj.get('setor_sigla') or 'STI'

                coluna_projeto = f"""
                <td rowspan="{total_p}" style="padding: 12px; vertical-align: top; font-weight: bold; font-size: 14px; color: #1e3a8a; border-right: 2px solid #cbd5e1; background: #f8fafc;">
                    <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px;">
                        <span style="display: inline-block; font-size: 10px; font-weight: bold; padding: 2px 7px; border-radius: 9999px; background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe;">🏢 {setor_sig}</span>
                        <span style="display: inline-block; font-size: 10px; font-weight: bold; padding: 2px 7px; border-radius: 9999px; background: {etq_bg}; color: {etq_cor}; border: 1px solid {etq_border};">{etq_icon} {etq}</span>
                    </div>
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
                    <span style="background: {badge_sistema_cor}; color: {badge_sistema_text}; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{p.get('sistema', 'SEI')}</span>
                </td>
                <td style="padding: 10px; vertical-align: top; font-family: monospace; font-size: 12px; font-weight: bold; color: #2563eb;">
                    {p.get('numero_processo', '-')}
                    {badge_docs}
                </td>
                {coluna_desc}
                <td style="padding: 10px; vertical-align: top;">
                    <span style="background: #e0e7ff; color: #3730a3; padding: 3px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">{p.get('local_atual') or '-'}</span>
                </td>
                <td style="padding: 10px; vertical-align: top; text-align: center;">
                    <span style="background: {badge_dias_cor}; color: white; padding: 3px 7px; border-radius: 10px; font-weight: bold; font-size: 11px;">{dias}</span>
                </td>
                <td style="padding: 10px; vertical-align: top; font-size: 12px; color: #1f2937;">
                    <strong>Ação:</strong> {p.get('acao') or '-'}<br>
                    <strong>Situação:</strong> {p.get('situacao') or '-'}
                </td>
                <td style="padding: 10px; vertical-align: top; background: #fafafa;">
                    <ol style="margin: 0; padding-left: 16px;">
                        {status_items}
                    </ol>
                </td>
            </tr>
            """

        html_projetos += linhas_proc

    if not html_projetos.strip():
        html_projetos = """
        <tr>
            <td colspan="8" style="padding: 32px 20px; text-align: center; color: #64748b; font-size: 13px;">
                Nenhum processo monitorado ativo cadastrado no sistema.
            </td>
        </tr>
        """

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
            
            <div style="display: flex; gap: 10px; padding: 14px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 110px; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Total Projetos</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #0f172a;">{total_projetos}</h3>
                </div>
                <div style="flex: 1; min-width: 110px; background: white; padding: 10px; border-radius: 6px; border: 1px solid #bfdbfe; text-align: center;">
                    <span style="font-size: 11px; color: #1d4ed8; text-transform: uppercase; font-weight: bold;">📄 Contratos</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #1d4ed8;">{total_contratos}</h3>
                </div>
                <div style="flex: 1; min-width: 110px; background: white; padding: 10px; border-radius: 6px; border: 1px solid #a7f3d0; text-align: center;">
                    <span style="font-size: 11px; color: #047857; text-transform: uppercase; font-weight: bold;">💳 Pagamentos</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #047857;">{total_pagamentos}</h3>
                </div>
                <div style="flex: 1; min-width: 110px; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Monitorados</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #2563eb;">{total}</h3>
                </div>
                <div style="flex: 1; min-width: 110px; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">No Setor STI</span>
                    <h3 style="margin: 2px 0 0; font-size: 18px; color: #059669;">{na_sti}</h3>
                </div>
                <div style="flex: 1; min-width: 110px; background: white; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Alerta (>60d)</span>
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

def gerar_relatorio_executivo_formal_html(usuario="STI"):
    """Gera um documento HTML completo, timbrado e formatado para impressão executiva A4 / PDF."""
    projetos = listar_projetos_com_processos(apenas_monitorados=True)
    agora = datetime.datetime.now()
    data_formatada = agora.strftime("%d/%m/%Y às %H:%M:%S")

    todos_processos = []
    for p in projetos:
        todos_processos.extend(p.get("processos", []))

    total = len(todos_processos)
    na_sti = sum(1 for proc in todos_processos if "STI" in (proc.get("local_atual") or "").upper())
    fora_sti = total - na_sti
    criticos = sum(1 for proc in todos_processos if (proc.get("dias_no_setor") or 0) > 60)
    alerta_medio = sum(1 for proc in todos_processos if 15 < (proc.get("dias_no_setor") or 0) <= 60)
    no_prazo = sum(1 for proc in todos_processos if (proc.get("dias_no_setor") or 0) <= 15)
    total_contratos = sum(1 for proj in projetos if (proj.get("etiqueta") or "Contratos") == "Contratos")
    total_pagamentos = sum(1 for proj in projetos if proj.get("etiqueta") == "Pagamentos")

    linhas_html = []
    for idx_proj, proj in enumerate(projetos, 1):
        procs = proj.get("processos", [])
        if not procs:
            continue

        etq = proj.get('etiqueta') or 'Contratos'
        etq_cor = "#047857" if etq == "Pagamentos" else "#1d4ed8"
        etq_bg = "#ecfdf5" if etq == "Pagamentos" else "#eff6ff"
        etq_border = "#a7f3d0" if etq == "Pagamentos" else "#bfdbfe"
        etq_icon = "💳" if etq == "Pagamentos" else "📄"
        setor_sig = proj.get('setor_sigla') or 'STI'

        linhas_html.append(f"""
        <div class="projeto-bloco">
          <div class="projeto-header">
            <h3>{idx_proj}. {proj['nome']} <span style="font-size: 11px; padding: 2px 8px; border-radius: 9999px; background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe; font-weight: bold; margin-left: 8px;">🏢 {setor_sig}</span> <span style="font-size: 11px; padding: 2px 8px; border-radius: 9999px; background: {etq_bg}; color: {etq_cor}; border: 1px solid {etq_border}; font-weight: bold; margin-left: 4px;">{etq_icon} {etq}</span></h3>
            {f'<p class="projeto-desc"><strong>Objeto:</strong> {proj["descricao"]}</p>' if proj.get("descricao") else ''}
          </div>
          <table class="tabela-executiva">
            <thead>
              <tr>
                <th style="width: 14%;">Sistema / Nº</th>
                <th style="width: 24%;">Local Atual</th>
                <th style="width: 14%;">Data Entrada</th>
                <th style="width: 12%;">Dias no Setor</th>
                <th style="width: 36%;">Último Andamento / Situação</th>
              </tr>
            </thead>
            <tbody>
        """)

        for p in procs:
            dias = p.get("dias_no_setor")
            dias_txt = f"{dias} dias" if dias is not None else "-"
            cor_badge = "#16a34a" if (dias or 0) <= 15 else ("#ca8a04" if (dias or 0) <= 60 else "#dc2626")
            bg_badge = "#dcfce7" if (dias or 0) <= 15 else ("#fef9c3" if (dias or 0) <= 60 else "#fee2e2")

            tot_docs = p.get('total_documentos', 0)
            badge_docs = f'<br><span style="display:inline-block; font-size:9px; background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; padding:1px 5px; border-radius:4px; font-weight:700; margin-top:2px;">📎 {tot_docs} peças</span>' if tot_docs > 0 else ''

            ult_status = p.get("ultimos_4_status", [])
            ult_texto = "-"
            if ult_status:
                s0 = ult_status[0]
                dt_mov = s0.get("data_movimentacao") or s0.get("data_registro") or ""
                ult_texto = f"<strong>[{dt_mov}]</strong> {s0.get('situacao', '-')}"
            elif p.get("situacao"):
                ult_texto = p.get("situacao")

            linhas_html.append(f"""
              <tr>
                <td>
                  <span class="badge-sis badge-{p.get('sistema', 'sei').lower()}">{p.get('sistema')}</span><br>
                  <strong style="font-family: monospace; font-size: 11px;">{p.get('numero_processo')}</strong>
                  {badge_docs}
                </td>
                <td><strong>{p.get('local_atual') or '-'}</strong></td>
                <td>{formatar_data_br(p.get('data_recebimento'))}</td>
                <td>
                  <span class="badge-sla" style="background: {bg_badge}; color: {cor_badge};">
                    {dias_txt}
                  </span>
                </td>
                <td style="font-size: 11px; line-height: 1.4;">{ult_texto}</td>
              </tr>
            """)

        linhas_html.append("""
            </tbody>
          </table>
        </div>
        """)

    conteudo_tabelas = "".join(linhas_html)
    if not conteudo_tabelas.strip():
        conteudo_tabelas = """
        <div style="text-align: center; padding: 40px 20px; color: #64748b; background: #f8fafc; border-radius: 8px; border: 1px dashed #cbd5e1; margin-bottom: 24px;">
            <p style="font-size: 14px; font-weight: 700; color: #1e293b;">Nenhum processo monitorado ativo cadastrado no momento.</p>
            <p style="font-size: 12px; margin-top: 4px;">Cadastre novos processos ou ative a opção de monitoramento para consolidar os dados neste relatório.</p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Relatório Executivo de Processos - SEDUC / STI</title>
  <style>
    @page {{
      size: A4 portrait;
      margin: 12mm 15mm 15mm 15mm;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    }}
    body {{
      background: #f1f5f9;
      color: #0f172a;
      padding: 20px;
      font-size: 12px;
    }}
    .no-print-bar {{
      max-width: 900px;
      margin: 0 auto 20px auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #ffffff;
      padding: 12px 20px;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.06);
      border: 1px solid #e2e8f0;
    }}
    .btn {{
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
    }}
    .btn-print {{
      background: #2563eb;
      color: white;
    }}
    .btn-back {{
      background: #f1f5f9;
      color: #334155;
      border: 1px solid #cbd5e1;
    }}
    .btn-print:hover {{ background: #1d4ed8; }}
    .btn-back:hover {{ background: #e2e8f0; }}

    .documento-folha {{
      max-width: 900px;
      margin: 0 auto;
      background: #ffffff;
      padding: 32px 36px;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      border: 1px solid #e2e8f0;
    }}
    .cabecalho-institucional {{
      text-align: center;
      border-bottom: 2px solid #0f172a;
      padding-bottom: 16px;
      margin-bottom: 20px;
    }}
    .cabecalho-institucional h1 {{
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 1px;
      color: #1e293b;
      text-transform: uppercase;
      margin-bottom: 2px;
    }}
    .cabecalho-institucional h2 {{
      font-size: 13px;
      font-weight: 700;
      color: #334155;
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .cabecalho-institucional h3 {{
      font-size: 12px;
      font-weight: 600;
      color: #2563eb;
      text-transform: uppercase;
      margin-bottom: 12px;
    }}
    .titulo-relatorio {{
      font-size: 17px;
      font-weight: 800;
      color: #0f172a;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      background: #f8fafc;
      padding: 6px 12px;
      border-radius: 6px;
      border: 1px solid #e2e8f0;
      display: inline-block;
    }}
    .meta-emissao {{
      margin-top: 10px;
      font-size: 11px;
      color: #64748b;
    }}

    .kpi-resumo-grid {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 10px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 10px;
      text-align: center;
    }}
    .kpi-card .valor {{
      font-size: 20px;
      font-weight: 800;
      color: #0f172a;
      margin-bottom: 2px;
    }}
    .kpi-card .rotulo {{
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      color: #64748b;
    }}

    .projeto-bloco {{
      margin-bottom: 24px;
      page-break-inside: avoid;
    }}
    .projeto-header {{
      background: #f1f5f9;
      border-left: 4px solid #2563eb;
      padding: 8px 12px;
      margin-bottom: 8px;
      border-radius: 0 4px 4px 0;
    }}
    .projeto-header h3 {{
      font-size: 13px;
      font-weight: 800;
      color: #0f172a;
    }}
    .projeto-desc {{
      font-size: 11px;
      color: #475569;
      margin-top: 2px;
    }}

    .tabela-executiva {{
      width: 100%;
      border-collapse: collapse;
      font-size: 11.5px;
      margin-bottom: 8px;
    }}
    .tabela-executiva th {{
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      padding: 6px 8px;
      text-align: left;
      font-weight: 700;
      color: #334155;
      font-size: 10.5px;
      text-transform: uppercase;
    }}
    .tabela-executiva td {{
      border: 1px solid #e2e8f0;
      padding: 6px 8px;
      vertical-align: middle;
    }}
    .tabela-executiva tr:nth-child(even) {{
      background: #fafafa;
    }}

    .badge-sis {{
      font-size: 9.5px;
      font-weight: 800;
      padding: 2px 6px;
      border-radius: 4px;
      display: inline-block;
      margin-bottom: 2px;
    }}
    .badge-sei {{ background: #fef08a; color: #854d0e; }}
    .badge-startgov {{ background: #dbeafe; color: #1e40af; }}

    .badge-sla {{
      font-weight: 700;
      font-size: 10.5px;
      padding: 2px 6px;
      border-radius: 4px;
      display: inline-block;
      white-space: nowrap;
    }}

    .rodape-documento {{
      border-top: 1px solid #cbd5e1;
      padding-top: 12px;
      margin-top: 24px;
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: #64748b;
    }}

    @media print {{
      body {{
        background: transparent !important;
        padding: 0 !important;
      }}
      .no-print-bar {{
        display: none !important;
      }}
      .documento-folha {{
        box-shadow: none !important;
        border: none !important;
        padding: 0 !important;
        max-width: 100% !important;
      }}
      .projeto-bloco {{
        page-break-inside: avoid;
      }}
    }}
  </style>
</head>
<body>
  <div class="no-print-bar">
    <div>
      <a href="/" class="btn btn-back">← Voltar ao Sistema</a>
    </div>
    <div style="display: flex; gap: 8px;">
      <button onclick="window.print()" class="btn btn-print">🖨️ Imprimir / Salvar PDF (A4)</button>
    </div>
  </div>

  <div class="documento-folha">
    <div class="cabecalho-institucional">
      <h1>Governo do Estado</h1>
      <h2>Secretaria de Estado da Educação &bull; SEDUC</h2>
      <h3>Superintendência de Tecnologia da Informação &bull; STI</h3>
      <div class="titulo-relatorio">Relatório Executivo de Tramitação & SLA</div>
      <div class="meta-emissao">
        Documento Oficial Gerado em <strong>{data_formatada}</strong> &bull; Emissor: <strong>{usuario}</strong>
      </div>
    </div>

    <div class="kpi-resumo-grid" style="grid-template-columns: repeat(6, 1fr);">
      <div class="kpi-card">
        <div class="valor">{total}</div>
        <div class="rotulo">Total Processos</div>
      </div>
      <div class="kpi-card">
        <div class="valor" style="color: #1d4ed8;">{total_contratos}</div>
        <div class="rotulo">📄 Contratos</div>
      </div>
      <div class="kpi-card">
        <div class="valor" style="color: #047857;">{total_pagamentos}</div>
        <div class="rotulo">💳 Pagamentos</div>
      </div>
      <div class="kpi-card">
        <div class="valor" style="color: #2563eb;">{na_sti}</div>
        <div class="rotulo">No Setor STI</div>
      </div>
      <div class="kpi-card">
        <div class="valor" style="color: #ca8a04;">{alerta_medio}</div>
        <div class="rotulo">Atenção (16-60d)</div>
      </div>
      <div class="kpi-card">
        <div class="valor" style="color: #dc2626;">{criticos}</div>
        <div class="rotulo">Crítico (&gt; 60d)</div>
      </div>
    </div>

    {conteudo_tabelas}

    <div class="rodape-documento">
      <div>Superintendência de Tecnologia da Informação &bull; SEDUC</div>
      <div>Sistema de Monitoramento SEI &amp; STARTGOV &bull; Página 1</div>
    </div>
  </div>
</body>
</html>"""

