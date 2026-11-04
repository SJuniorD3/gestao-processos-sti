import http.server
import json
import urllib.parse
from pathlib import Path
import csv
import io
import datetime
import os
import hmac
import hashlib
import time
import base64

from config import PORT, HOST, BASE_DIR, ADMIN_USER, ADMIN_PASS
from database import (
    listar_processos, listar_projetos_com_processos, obter_processo, criar_processo, atualizar_processo,
    excluir_processo, obter_projeto, obter_ou_criar_projeto, atualizar_projeto, excluir_projeto, listar_ultimos_relatorios,
    formatar_data_br, formatar_data_hora_br
)
from scheduler import scheduler
from notifier import gerar_conteudo_resumo
from monitor_engine import executar_monitoramento_processos, monitorar_processo_individual
from integrations import sei_client, startgov_client

STATIC_DIR = BASE_DIR / "static"
SECRET_KEY = os.environ.get("SECRET_KEY", "sti_session_secret_token_2026_salt")

def gerar_token():
    expira_em = int(time.time()) + (7 * 24 * 3600)  # 7 dias
    dado = f"{ADMIN_USER}:{expira_em}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), dado, hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{ADMIN_USER}:{expira_em}:{sig}".encode("utf-8")).decode("utf-8")
    return token

def validar_token(token):
    if not token:
        return False
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        partes = decoded.split(":")
        if len(partes) != 3:
            return False
        user, expira_str, sig = partes
        expira_em = int(expira_str)
        if time.time() > expira_em:
            return False
        dado = f"{user}:{expira_em}".encode("utf-8")
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), dado, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig) and user == ADMIN_USER
    except Exception:
        return False

class ProcessosRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _is_authenticated(self):
        # 1. Header Authorization: Bearer <token>
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            if validar_token(token):
                return True

        # 2. Cookie sti_session=<token>
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            cookies = [c.strip() for c in cookie_header.split(";")]
            for c in cookies:
                if c.startswith("sti_session="):
                    token = c.split("=", 1)[1].strip()
                    if validar_token(token):
                        return True
        return False

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def _read_json(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(body)
        return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Rota pública: verificação de status de auth
        if path == "/api/auth/check":
            self._send_json({"success": True, "authenticated": self._is_authenticated()})
            return

        # Página de login
        if path == "/login.html":
            if self._is_authenticated():
                self._redirect("/index.html")
                return
            return super().do_GET()

        # Página Inicial
        if path == "/" or path == "" or path == "/index.html":
            if not self._is_authenticated():
                self._redirect("/login.html")
                return
            self.path = "/index.html"
            return super().do_GET()

        # Recursos estáticos permitidos publicamente
        if (path.startswith("/css/") or path.startswith("/js/") or 
            path.endswith(".ico") or path.endswith(".png") or path.endswith(".svg")):
            return super().do_GET()

        # Todas as rotas /api/... exigem autenticação
        if path.startswith("/api/"):
            if not self._is_authenticated():
                self._send_json({"success": False, "error": "Acesso não autorizado. Faça login primeiro."}, 401)
                return

        # Rota da API: Lista de Processos
        if path == "/api/processos":
            processos = listar_processos()
            self._send_json({"success": True, "data": processos})
            return

        # Rota da API: Projetos Agrupados com seus Processos
        if path == "/api/projetos":
            projetos = listar_projetos_com_processos()
            self._send_json({"success": True, "data": projetos})
            return

        # Rota da API: Detalhes de um Projeto Específico
        if path.startswith("/api/projetos/"):
            try:
                proj_id = int(path.split("/")[-1])
                proj = obter_projeto(proj_id)
                if proj:
                    self._send_json({"success": True, "data": proj})
                else:
                    self._send_json({"success": False, "error": "Projeto não encontrado"}, 404)
            except ValueError:
                self._send_json({"success": False, "error": "ID de projeto inválido"}, 400)
            return

        # Rota da API: Detalhes do Processo (incluindo histórico completo)
        if path.startswith("/api/processos/"):
            try:
                proc_id = int(path.split("/")[-1])
                proc = obter_processo(proc_id)
                if proc:
                    self._send_json({"success": True, "data": proc})
                else:
                    self._send_json({"success": False, "error": "Processo não encontrado"}, 404)
            except ValueError:
                self._send_json({"success": False, "error": "ID inválido"}, 400)
            return

        # Rota da API: Informações do Agendador
        if path == "/api/scheduler/info":
            info = scheduler.get_info()
            self._send_json({"success": True, "data": info})
            return

        # Rota da API: Histórico de Relatórios Gerados
        if path == "/api/relatorios/ultimos":
            rels = listar_ultimos_relatorios(15)
            self._send_json({"success": True, "data": rels})
            return

        # Rota da API: Pré-visualização do Relatório
        if path == "/api/relatorios/preview":
            resumo = gerar_conteudo_resumo("Pré-visualização")
            self._send_json({"success": True, "data": resumo})
            return

        # Rota da API: Informações dos Sistemas Integrados
        if path == "/api/sistemas":
            self._send_json({
                "success": True,
                "data": {
                    "sei": sei_client.get_info(),
                    "startgov": startgov_client.get_info()
                }
            })
            return

        # Exportar CSV para Excel
        if path == "/api/export/csv":
            processos = listar_processos()
            output = io.StringIO()
            # Adiciona BOM para o Excel abrir em UTF-8 corretamente no Windows
            output.write('\ufeff')
            writer = csv.writer(output, delimiter=';')
            writer.writerow([
                "ID", "PROJETO", "SISTEMA", "Nº - PROCESSO", "DESCRIÇÃO",
                "LOCAL ATUAL", "AÇÃO", "DATA RECEBIMENTO", "SITUAÇÃO", "DIAS NO SETOR", "4 ÚLTIMOS STATUS"
            ])
            for p in processos:
                status_str = " | ".join([
                    f"[{formatar_data_hora_br(s.get('data_movimentacao') or s.get('data_registro', ''))} - {s.get('local')}]: {s.get('situacao')}"
                    for s in p.get("ultimos_4_status", [])
                ])
                writer.writerow([
                    p["id"], p["projeto"], p["sistema"], p["numero_processo"],
                    p["descricao"], p["local_atual"], p["acao"],
                    formatar_data_br(p["data_recebimento"]) if p["data_recebimento"] else "-", p["situacao"],
                    p["dias_no_setor"] if p["dias_no_setor"] is not None else "-",
                    status_str
                ])
            
            csv_data = output.getvalue().encode("utf-8-sig")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8-sig")
            self.send_header("Content-Disposition", 'attachment; filename="processos_sti.csv"')
            self.send_header("Content-Length", str(len(csv_data)))
            self.end_headers()
            self.wfile.write(csv_data)
            return

        # Página Inicial
        if path == "/" or path == "":
            if not self._is_authenticated():
                self._redirect("/login.html")
                return
            self.path = "/index.html"
            return super().do_GET()

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Rota de Login (Pública)
        if path == "/api/auth/login":
            dados = self._read_json()
            user = str(dados.get("username", "")).strip()
            pwd = str(dados.get("password", ""))

            if user == ADMIN_USER and pwd == ADMIN_PASS:
                token = gerar_token()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie", f"sti_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "token": token, "message": "Login realizado com sucesso!"}).encode("utf-8"))
            else:
                self._send_json({"success": False, "error": "Usuário ou senha incorretos."}, 401)
            return

        # Rota de Logout
        if path == "/api/auth/logout":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", "sti_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": "Logout realizado com sucesso."}).encode("utf-8"))
            return

        # Demais rotas POST exigem autenticação
        if not self._is_authenticated():
            self._send_json({"success": False, "error": "Acesso não autorizado. Faça login primeiro."}, 401)
            return

        # Criar Projeto Diretamente
        if path == "/api/projetos":
            dados = self._read_json()
            nome = str(dados.get("nome", "")).strip()
            desc = str(dados.get("descricao", "")).strip()
            if not nome:
                self._send_json({"success": False, "error": "O nome do projeto é obrigatório."}, 400)
                return
            try:
                proj_id = obter_ou_criar_projeto(nome, desc)
                self._send_json({"success": True, "id": proj_id, "message": "Projeto cadastrado com sucesso!"}, 201)
            except Exception as e:
                self._send_json({"success": False, "error": f"Erro ao cadastrar projeto: {str(e)}"}, 400)
            return

        # Criar Processo
        if path == "/api/processos":
            dados = self._read_json()
            if not dados.get("numero_processo"):
                self._send_json({"success": False, "error": "O Número do Processo é obrigatório para cadastro."}, 400)
                return
            try:
                novo_id = criar_processo(dados)
                self._send_json({"success": True, "id": novo_id, "message": "Processo cadastrado com sucesso!"}, 201)
            except Exception as e:
                self._send_json({"success": False, "error": f"Erro ao cadastrar: {str(e)}"}, 400)
            return

        # Disparo Manual do Relatório
        if path == "/api/scheduler/disparar":
            try:
                res = scheduler.disparar_manual()
                self._send_json({"success": True, "data": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        # Executar Monitoramento Completo nos Portais SEI / STARTGOV
        if path == "/api/monitoramento/executar":
            try:
                resumo = executar_monitoramento_processos()
                self._send_json({"success": True, "data": resumo})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        # Executar Monitoramento de um Processo Específico
        if path.startswith("/api/monitoramento/processo/"):
            try:
                proc_id = int(path.split("/")[-1])
                res = monitorar_processo_individual(proc_id)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        # Testar Credenciais e Conexão dos Robôs SEI e STARTGOV
        if path == "/api/sistemas/testar":
            try:
                res_sei = {}
                res_startgov = {}

                # Teste SEI
                if sei_client.username and sei_client.password:
                    ok_sei, msg_sei = sei_client.autenticar(forcar=True)
                    res_sei = {"configurado": True, "sucesso": ok_sei, "mensagem": msg_sei}
                else:
                    res_sei = {"configurado": False, "sucesso": False, "mensagem": "Variáveis SEI_USER ou SEI_PASS não preenchidas no ambiente."}

                # Teste StartGov
                if startgov_client.username and startgov_client.password:
                    ok_start, msg_start = startgov_client.autenticar(forcar=True)
                    res_startgov = {"configurado": True, "sucesso": ok_start, "mensagem": msg_start}
                else:
                    res_startgov = {"configurado": False, "sucesso": False, "mensagem": "Variáveis STARTGOV_USER ou STARTGOV_PASS não preenchidas no ambiente."}

                self._send_json({
                    "success": True,
                    "data": {
                        "sei": res_sei,
                        "startgov": res_startgov
                    }
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        self._send_json({"success": False, "error": "Rota POST não encontrada"}, 404)

    def do_PUT(self):
        if not self._is_authenticated():
            self._send_json({"success": False, "error": "Acesso não autorizado. Faça login primeiro."}, 401)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Atualizar Projeto
        if path.startswith("/api/projetos/"):
            try:
                proj_id = int(path.split("/")[-1])
                dados = self._read_json()
                sucesso = atualizar_projeto(proj_id, dados.get("nome", ""), dados.get("descricao", ""))
                if sucesso:
                    self._send_json({"success": True, "message": "Projeto atualizado com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Projeto não encontrado para atualização"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Atualizar Processo
        if path.startswith("/api/processos/"):
            try:
                proc_id = int(path.split("/")[-1])
                dados = self._read_json()
                sucesso = atualizar_processo(proc_id, dados)
                if sucesso:
                    self._send_json({"success": True, "message": "Processo atualizado com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Processo não encontrado para atualização"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        self._send_json({"success": False, "error": "Rota PUT não encontrada"}, 404)

    def do_DELETE(self):
        if not self._is_authenticated():
            self._send_json({"success": False, "error": "Acesso não autorizado. Faça login primeiro."}, 401)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Excluir Projeto (e seus processos vinculados)
        if path.startswith("/api/projetos/"):
            try:
                proj_id = int(path.split("/")[-1])
                sucesso = excluir_projeto(proj_id)
                if sucesso:
                    self._send_json({"success": True, "message": "Projeto e seus processos removidos com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Projeto não encontrado"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        if path.startswith("/api/processos/"):
            try:
                proc_id = int(path.split("/")[-1])
                sucesso = excluir_processo(proc_id)
                if sucesso:
                    self._send_json({"success": True, "message": "Processo removido com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Processo não encontrado"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        self._send_json({"success": False, "error": "Rota DELETE não encontrada"}, 404)
