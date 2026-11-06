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
import socket

try:
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

from config import PORT, HOST, BASE_DIR, ADMIN_USER, ADMIN_PASS
from database import (
    init_db,
    listar_processos, listar_projetos_com_processos, obter_processo, criar_processo, atualizar_processo,
    excluir_processo, obter_projeto, obter_ou_criar_projeto, atualizar_projeto, excluir_projeto, listar_ultimos_relatorios,
    formatar_data_br, formatar_data_hora_br,
    listar_setores, obter_setor, obter_setor_por_sigla, criar_setor, atualizar_setor, excluir_setor,
    obter_usuario_por_login, obter_usuario_por_id, listar_usuarios, criar_usuario, atualizar_usuario, excluir_usuario,
    registrar_auditoria, listar_auditoria, verificar_senha,
    obter_processo_por_numero, obter_metricas_gargalos,
    listar_documentos_processo, salvar_documentos_processo, adicionar_documento_manual, excluir_documento_processo
)
from scheduler import scheduler
from notifier import gerar_conteudo_resumo, gerar_relatorio_executivo_formal_html
from monitor_engine import executar_monitoramento_processos, monitorar_processo_individual
from integrations import sei_client, startgov_client

# Garante que todas as tabelas e migrações existam no banco de dados (SQLite ou Supabase/PostgreSQL)
try:
    init_db()
except Exception as _e_init:
    print(f"[!] Aviso ao inicializar schema do banco: {_e_init}")

STATIC_DIR = BASE_DIR / "static"
SECRET_KEY = os.environ.get("SECRET_KEY", "sti_session_secret_token_2026_salt")

def gerar_token(usuario, perfil="operador"):
    expira_em = int(time.time()) + (7 * 24 * 3600)  # 7 dias
    dado = f"{usuario}:{perfil}:{expira_em}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), dado, hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{usuario}:{perfil}:{expira_em}:{sig}".encode("utf-8")).decode("utf-8")
    return token

def validar_token(token):
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        partes = decoded.split(":")
        # Suporta formato novo (4 partes: user:perfil:expira:sig)
        if len(partes) == 4:
            user, perfil, expira_str, sig = partes
            expira_em = int(expira_str)
            if time.time() > expira_em:
                return None
            dado = f"{user}:{perfil}:{expira_str}".encode("utf-8")
            expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), dado, hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig, expected_sig):
                return {"usuario": user, "perfil": perfil}
        # Formato legado (3 partes: user:expira:sig)
        elif len(partes) == 3:
            user, expira_str, sig = partes
            expira_em = int(expira_str)
            if time.time() > expira_em:
                return None
            dado = f"{user}:{expira_str}".encode("utf-8")
            expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), dado, hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig, expected_sig):
                return {"usuario": user, "perfil": "admin" if user.lower() == (ADMIN_USER or "admin").lower() else "operador"}
        return None
    except Exception:
        return None

def json_serial(obj):
    """Serializador universal para tipos que o json padrão do Python não serializa (datetime, date, Decimal, etc.)."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.strftime("%d/%m/%Y %H:%M:%S") if isinstance(obj, datetime.datetime) else obj.strftime("%d/%m/%Y")
    if hasattr(obj, "__str__"):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

class ProcessosRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _get_current_user(self):
        # 1. Header Authorization: Bearer <token>
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            user_data = validar_token(token)
            if user_data:
                return user_data

        # 2. Cookie sti_session=<token>
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            cookies = [c.strip() for c in cookie_header.split(";")]
            for c in cookies:
                if c.startswith("sti_session="):
                    token = c.split("=", 1)[1].strip()
                    user_data = validar_token(token)
                    if user_data:
                        return user_data
        return None

    def _is_authenticated(self):
        return self._get_current_user() is not None

    def _require_role(self, *roles):
        user = self._get_current_user()
        if not user:
            self._send_json({"success": False, "error": "Acesso não autorizado. Faça login primeiro."}, 401)
            return None
        if roles and user.get("perfil") not in roles:
            self._send_json({"success": False, "error": f"Acesso restrito. Seu perfil ({user.get('perfil')}) não possui permissão para esta ação."}, 403)
            return None
        return user

    def _get_client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = self.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

    def _send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False, indent=2, default=json_serial).encode("utf-8")
        except Exception as e:
            body = json.dumps({"success": False, "error": f"Erro de serialização: {str(e)}"}).encode("utf-8")
            status = 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

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

        # Rota da API: Lista de Setores da SEDUC
        if path == "/api/setores":
            apenas_ativos = query.get("apenas_ativos", ["0"])[0] in ("1", "true", "True")
            setores = listar_setores(apenas_ativos=apenas_ativos)
            self._send_json({"success": True, "data": setores})
            return

        # Rota da API: Lista de Processos
        if path == "/api/processos":
            try:
                filtro_setor = query.get("setor", [None])[0]
                processos = listar_processos(setor=filtro_setor)
                self._send_json({"success": True, "data": processos})
            except Exception as e:
                self._send_json({"success": False, "error": f"Erro ao listar processos: {str(e)}"}, 500)
            return

        # Rota da API: Projetos Agrupados com seus Processos
        if path == "/api/projetos":
            try:
                curr = self._get_current_user()
                filtro_setor = query.get("setor", [None])[0]
                # Se não for admin e nenhum filtro for passado explicitamente, filtra pelo setor do usuário logado
                if curr and curr.get("perfil") != "admin" and not filtro_setor:
                    u_db = obter_usuario_por_login(curr["usuario"])
                    filtro_setor = u_db.get("setor_sigla", "STI") if u_db else "STI"
                projetos = listar_projetos_com_processos(setor=filtro_setor)
                self._send_json({"success": True, "data": projetos, "setor_filtrado": filtro_setor})
            except Exception as e:
                self._send_json({"success": False, "error": f"Erro ao listar projetos: {str(e)}"}, 500)
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

        # Rota da API: Documentos e Peças de um Processo
        if path.startswith("/api/processos/") and path.endswith("/documentos"):
            try:
                proc_id = int(path.split("/")[3])
                docs = listar_documentos_processo(proc_id)
                self._send_json({"success": True, "data": docs, "total": len(docs)})
            except ValueError:
                self._send_json({"success": False, "error": "ID de processo inválido"}, 400)
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

        # Rota da API / Página: Relatório Executivo Formal para Impressão / Salvar PDF (A4)
        if path == "/relatorio-executivo":
            curr = self._get_current_user()
            user_nome = (curr.get("nome") or curr.get("usuario") or "STI") if curr else "STI"
            html_exec = gerar_relatorio_executivo_formal_html(usuario=user_nome)
            self._send_html(html_exec)
            return

        if path == "/api/relatorios/executivo":
            curr = self._get_current_user()
            user_nome = (curr.get("nome") or curr.get("usuario") or "STI") if curr else "STI"
            html_exec = gerar_relatorio_executivo_formal_html(usuario=user_nome)
            self._send_json({"success": True, "html": html_exec})
            return

        # Rota da API: Informações do Usuário Atual
        if path == "/api/auth/me":
            curr = self._get_current_user()
            if curr:
                u_db = obter_usuario_por_login(curr["usuario"])
                nome = u_db.get("nome", curr["usuario"]) if u_db else curr["usuario"]
                user_id = u_db.get("id") if u_db else 0
                setor_sigla = u_db.get("setor_sigla", "STI") if u_db else "STI"
                self._send_json({
                    "success": True,
                    "data": {
                        "id": user_id,
                        "usuario": curr["usuario"],
                        "nome": nome,
                        "perfil": curr["perfil"],
                        "setor_sigla": setor_sigla
                    }
                })
            else:
                self._send_json({"success": False, "error": "Não autenticado"}, 401)
            return

        # Rota da API: Lista de Usuários (Admin)
        if path == "/api/usuarios":
            if not self._require_role("admin"):
                return
            users = listar_usuarios()
            self._send_json({"success": True, "data": users})
            return

        # Rota da API: Trilha de Auditoria (Admin)
        if path == "/api/auditoria":
            if not self._require_role("admin"):
                return
            logs = listar_auditoria(100)
            self._send_json({"success": True, "data": logs})
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

        # Rota da API: Métricas de Gargalos e Produtividade (SLA)
        if path == "/api/metricas/gargalos":
            gargalos = obter_metricas_gargalos()
            self._send_json({"success": True, "data": gargalos})
            return

        # Exportar CSV para Excel
        if path == "/api/export/csv":
            filtro_setor = query.get("setor", [None])[0]
            processos = listar_processos(setor=filtro_setor)
            output = io.StringIO()
            # Adiciona BOM para o Excel abrir em UTF-8 corretamente no Windows
            output.write('\ufeff')
            writer = csv.writer(output, delimiter=';')
            writer.writerow([
                "ID", "SETOR", "PROJETO", "ETIQUETA", "SISTEMA", "Nº - PROCESSO", "PEÇAS/ANEXOS", "DESCRIÇÃO",
                "LOCAL ATUAL", "AÇÃO", "DATA RECEBIMENTO", "SITUAÇÃO", "DIAS NO SETOR", "4 ÚLTIMOS STATUS"
            ])
            for p in processos:
                status_str = " | ".join([
                    f"[{formatar_data_hora_br(s.get('data_movimentacao') or s.get('data_registro', ''))} - {s.get('local')}]: {s.get('situacao')}"
                    for s in p.get("ultimos_4_status", [])
                ])
                writer.writerow([
                    p["id"], p.get("setor_sigla", "STI"), p["projeto"], p.get("etiqueta", "Contratos"), p["sistema"], p["numero_processo"],
                    p.get("total_documentos", 0),
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
            user_input = str(dados.get("username", "")).strip().lower()
            pwd_input = str(dados.get("password", ""))

            if not user_input or not pwd_input:
                self._send_json({"success": False, "error": "Usuário e senha são obrigatórios."}, 400)
                return

            autenticado = False
            perfil = "operador"
            nome_usuario = user_input

            u_db = obter_usuario_por_login(user_input)
            if u_db:
                if u_db.get("ativo", 1) == 0:
                    self._send_json({"success": False, "error": "Este usuário foi desativado. Contate o administrador."}, 403)
                    return
                if verificar_senha(pwd_input, u_db["senha_hash"]):
                    autenticado = True
                    perfil = u_db.get("perfil", "operador")
                    nome_usuario = u_db.get("nome", user_input)
            elif user_input == (ADMIN_USER or "admin").strip().lower() and pwd_input == (ADMIN_PASS or "STIadmin"):
                autenticado = True
                perfil = "admin"
                nome_usuario = "Administrador STI"

            if autenticado:
                token = gerar_token(user_input, perfil)
                ip = self._get_client_ip()
                registrar_auditoria(user_input, "LOGIN", f"Login efetuado com sucesso (Perfil: {perfil})", ip)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie", f"sti_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "token": token,
                    "user": {
                        "usuario": user_input,
                        "nome": nome_usuario,
                        "perfil": perfil
                    },
                    "message": "Login realizado com sucesso!"
                }).encode("utf-8"))
            else:
                ip = self._get_client_ip()
                registrar_auditoria(user_input or "anonimo", "LOGIN_FALHA", "Tentativa de login sem sucesso", ip)
                self._send_json({"success": False, "error": "Usuário ou senha incorretos."}, 401)
            return

        # Rota de Logout
        if path == "/api/auth/logout":
            curr = self._get_current_user()
            if curr:
                registrar_auditoria(curr["usuario"], "LOGOUT", "Encerramento voluntário de sessão", self._get_client_ip())
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

        # Cadastrar Novo Setor da SEDUC (Admin)
        if path == "/api/setores":
            curr = self._require_role("admin")
            if not curr:
                return
            dados = self._read_json()
            sigla = str(dados.get("sigla", "")).strip().upper()
            nome = str(dados.get("nome", "")).strip()

            if not sigla or not nome:
                self._send_json({"success": False, "error": "Sigla e Nome do setor são obrigatórios."}, 400)
                return

            try:
                novo_id = criar_setor(sigla, nome)
                registrar_auditoria(curr["usuario"], "CRIAR_SETOR", f"Cadastrou setor '{sigla}' ({nome})", self._get_client_ip())
                self._send_json({"success": True, "id": novo_id, "message": f"Setor '{sigla}' cadastrado com sucesso!"}, 201)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Cadastrar Novo Usuário (Admin)
        if path == "/api/usuarios":
            curr = self._require_role("admin")
            if not curr:
                return
            dados = self._read_json()
            nome = str(dados.get("nome", "")).strip()
            usuario = str(dados.get("usuario", "")).strip().lower()
            senha = str(dados.get("senha", "")).strip()
            perfil = str(dados.get("perfil", "operador")).strip().lower()
            setor_sigla = str(dados.get("setor_sigla", "STI")).strip().upper() or "STI"

            if not nome or not usuario or not senha:
                self._send_json({"success": False, "error": "Nome, login e senha são obrigatórios."}, 400)
                return

            existente = obter_usuario_por_login(usuario)
            if existente:
                self._send_json({"success": False, "error": f"O usuário '{usuario}' já existe no sistema."}, 400)
                return

            try:
                novo_id = criar_usuario(nome, usuario, senha, perfil, setor_sigla=setor_sigla)
                registrar_auditoria(curr["usuario"], "CRIAR_USUARIO", f"Cadastrou usuário '{usuario}' ({perfil} - Setor: {setor_sigla})", self._get_client_ip())
                self._send_json({"success": True, "id": novo_id, "message": f"Usuário '{usuario}' cadastrado com sucesso!"}, 201)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Criar Projeto Diretamente
        if path == "/api/projetos":
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            dados = self._read_json()
            nome = str(dados.get("nome", "")).strip()
            desc = str(dados.get("descricao", "")).strip()
            etiqueta = str(dados.get("etiqueta", "Contratos")).strip()
            setor_sigla = str(dados.get("setor_sigla", "")).strip().upper()

            if not setor_sigla:
                u_db = obter_usuario_por_login(curr["usuario"])
                setor_sigla = u_db.get("setor_sigla", "STI") if u_db else "STI"

            if not nome:
                self._send_json({"success": False, "error": "O nome do projeto é obrigatório."}, 400)
                return
            try:
                proj_id = obter_ou_criar_projeto(nome, desc, etiqueta=etiqueta, setor_sigla=setor_sigla)
                registrar_auditoria(curr["usuario"], "CRIAR_PROJETO", f"Cadastrou projeto '{nome}' (ID {proj_id}) com etiqueta '{etiqueta}' e setor '{setor_sigla}'", self._get_client_ip())
                self._send_json({"success": True, "id": proj_id, "message": "Projeto cadastrado com sucesso!"}, 201)
            except Exception as e:
                self._send_json({"success": False, "error": f"Erro ao cadastrar projeto: {str(e)}"}, 400)
            return

        # Criar Processo
        if path == "/api/processos":
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            dados = self._read_json()
            if not dados.get("numero_processo"):
                self._send_json({"success": False, "error": "O Número do Processo é obrigatório para cadastro."}, 400)
                return
            if not dados.get("setor_sigla") and not dados.get("setor"):
                u_db = obter_usuario_por_login(curr["usuario"])
                dados["setor_sigla"] = u_db.get("setor_sigla", "STI") if u_db else "STI"
            try:
                novo_id = criar_processo(dados)
                registrar_auditoria(curr["usuario"], "CRIAR_PROCESSO", f"Cadastrou processo '{dados.get('numero_processo')}' no sistema '{dados.get('sistema')}'", self._get_client_ip())
                self._send_json({"success": True, "id": novo_id, "message": "Processo cadastrado com sucesso!"}, 201)
            except Exception as e:
                self._send_json({"success": False, "error": f"Erro ao cadastrar: {str(e)}"}, 400)
            return

        # Importação em Lote via Planilha / CSV
        if path == "/api/processos/importar-lote":
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                dados = self._read_json()
                registros = dados.get("registros", [])

                # Se veio como texto CSV bruto, faz o parse
                if not registros and "csv_texto" in dados:
                    csv_raw = dados["csv_texto"]
                    delimitador = ";" if ";" in csv_raw else ("," if "," in csv_raw else "\t")
                    reader = csv.reader(io.StringIO(csv_raw), delimiter=delimitador)
                    linhas = list(reader)
                    if linhas:
                        cabecalho = [str(c).strip().lower() for c in linhas[0]]
                        
                        def idx(nomes_possiveis, padrao=-1):
                            for n in nomes_possiveis:
                                if n in cabecalho:
                                    return cabecalho.index(n)
                            return padrao

                        i_proj = idx(["projeto", "nome do projeto", "proj"], 0)
                        i_etiqueta = idx(["etiqueta", "tag", "categoria", "tipo projeto"], -1)
                        i_setor = idx(["setor", "setor_sigla", "sigla_setor", "unidade_setor"], -1)
                        i_sis = idx(["sistema", "tipo", "origem"], 1)
                        i_num = idx(["numero_processo", "processo", "nº processo", "nº - processo", "numero", "nº"], 2)
                        i_desc = idx(["descricao", "descrição", "objeto", "objeto/descrição"], 3)
                        i_local = idx(["local_atual", "local", "unidade"], 4)
                        i_acao = idx(["acao", "ação"], 5)
                        i_data = idx(["data_recebimento", "data", "recebimento", "dt_recebimento"], 6)
                        i_sit = idx(["situacao", "situação", "status"], 7)

                        for l in linhas[1:]:
                            if not l or not any(l):
                                continue
                            def col(i, def_val=""):
                                return l[i].strip() if 0 <= i < len(l) else def_val

                            num_proc = col(i_num)
                            if not num_proc:
                                continue
                            
                            registros.append({
                                "projeto": col(i_proj, "STI"),
                                "etiqueta": col(i_etiqueta, "Contratos"),
                                "setor_sigla": col(i_setor, "STI"),
                                "sistema": col(i_sis, "SEI"),
                                "numero_processo": num_proc,
                                "descricao": col(i_desc, ""),
                                "local_atual": col(i_local, "Aguardando Monitoramento"),
                                "acao": col(i_acao, "Aguardando trâmite"),
                                "data_recebimento": col(i_data, ""),
                                "situacao": col(i_sit, "Em tramitação"),
                                "monitorar": 1
                            })

                if not registros:
                    self._send_json({"success": False, "error": "Nenhum registro válido encontrado para importação."}, 400)
                    return

                criados = 0
                atualizados = 0
                erros = []

                for idx_item, item in enumerate(registros, 1):
                    num = str(item.get("numero_processo", "")).strip()
                    if not num:
                        erros.append(f"Linha {idx_item}: Número do processo ausente.")
                        continue
                    try:
                        existente = obter_processo_por_numero(num)
                        if existente:
                            atualizar_processo(existente["id"], item, registrar_novo_status=True)
                            atualizados += 1
                        else:
                            criar_processo(item)
                            criados += 1
                    except Exception as ex_item:
                        erros.append(f"Linha {idx_item} ({num}): {str(ex_item)}")

                resumo_msg = f"Importação em lote concluída: {criados} novos criados, {atualizados} atualizados."
                registrar_auditoria(
                    curr["usuario"],
                    "IMPORTACAO_LOTE",
                    f"{resumo_msg} (Total processado: {len(registros)}, Erros: {len(erros)})",
                    self._get_client_ip()
                )

                self._send_json({
                    "success": True,
                    "message": resumo_msg,
                    "criados": criados,
                    "atualizados": atualizados,
                    "total_processados": len(registros),
                    "erros": erros
                })
            except Exception as e:
                self._send_json({"success": False, "error": f"Falha na importação em lote: {str(e)}"}, 500)
            return

        # Disparo Manual do Relatório
        if path == "/api/scheduler/disparar":
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                res = scheduler.disparar_manual()
                registrar_auditoria(curr["usuario"], "DISPARAR_RELATORIO", "Disparou resumo diário manualmente", self._get_client_ip())
                self._send_json({"success": True, "data": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        # Executar Monitoramento Completo nos Portais SEI / STARTGOV
        if path == "/api/monitoramento/executar":
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                resumo = executar_monitoramento_processos()
                registrar_auditoria(curr["usuario"], "SINCRONIZAR_TODOS", f"Executou sincronização geral ({resumo.get('total_atualizados')}/{resumo.get('total_verificados')} atualizados)", self._get_client_ip())
                self._send_json({"success": True, "data": resumo})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        # Executar Monitoramento de um Processo Específico
        if path.startswith("/api/monitoramento/processo/"):
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                proc_id = int(path.split("/")[-1])
                res = monitorar_processo_individual(proc_id)
                if res.get("sucesso"):
                    registrar_auditoria(curr["usuario"], "SINCRONIZAR_PROCESSO", f"Sincronizou processo ID {proc_id} ({res.get('dados', {}).get('local_atual')})", self._get_client_ip())
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        # Rastrear Documentos do Processo no SEI em Tempo Real
        if path.startswith("/api/processos/") and path.endswith("/documentos/rastrear-sei"):
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                proc_id = int(path.split("/")[3])
                proc = obter_processo(proc_id)
                if not proc:
                    self._send_json({"success": False, "error": "Processo não encontrado"}, 404)
                    return

                res_sei = sei_client.rastrear_documentos_processo(proc["numero_processo"])
                if res_sei.get("sucesso") and res_sei.get("documentos"):
                    salvar_documentos_processo(proc_id, res_sei["documentos"])
                    registrar_auditoria(
                        curr["usuario"],
                        "RASTREAR_DOCUMENTOS_SEI",
                        f"Rastreou {len(res_sei['documentos'])} peças do processo {proc['numero_processo']}",
                        self._get_client_ip()
                    )
                self._send_json(res_sei)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        # Adicionar Documento/Peça Manual ao Processo
        if path.startswith("/api/processos/") and path.endswith("/documentos"):
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                proc_id = int(path.split("/")[3])
                dados = self._read_json()
                doc_id = adicionar_documento_manual(proc_id, dados)
                registrar_auditoria(
                    curr["usuario"],
                    "ANEXAR_DOCUMENTO",
                    f"Anexou peça '{dados.get('nome_exibicao')}' ao processo ID {proc_id}",
                    self._get_client_ip()
                )
                self._send_json({"success": True, "id": doc_id, "message": "Documento adicionado com sucesso!"}, 201)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Testar Credenciais e Conexão dos Robôs SEI e STARTGOV
        if path == "/api/sistemas/testar":
            curr = self._require_role("admin")
            if not curr:
                return
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

                registrar_auditoria(curr["usuario"], "TESTAR_ROBOS", f"Testou conexões (SEI: {res_sei.get('sucesso')}, StartGov: {res_startgov.get('sucesso')})", self._get_client_ip())

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

        # Atualizar Setor da SEDUC (Admin)
        if path.startswith("/api/setores/"):
            curr = self._require_role("admin")
            if not curr:
                return
            try:
                setor_id = int(path.split("/")[-1])
                dados = self._read_json()
                sigla = str(dados.get("sigla", "")).strip().upper()
                nome = str(dados.get("nome", "")).strip()
                ativo = dados.get("ativo", 1)
                sucesso = atualizar_setor(setor_id, sigla, nome, ativo)
                if sucesso:
                    registrar_auditoria(curr["usuario"], "EDITAR_SETOR", f"Atualizou setor ID {setor_id} ({sigla} - {nome}, Ativo: {ativo})", self._get_client_ip())
                    self._send_json({"success": True, "message": "Setor atualizado com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Setor não encontrado para atualização"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Atualizar Usuário (Admin)
        if path.startswith("/api/usuarios/"):
            curr = self._require_role("admin")
            if not curr:
                return
            try:
                user_id = int(path.split("/")[-1])
                dados = self._read_json()
                nome = dados.get("nome", "")
                perfil = dados.get("perfil", "operador")
                ativo = dados.get("ativo", 1)
                senha = dados.get("senha")
                setor_sigla = dados.get("setor_sigla")
                atualizar_usuario(user_id, nome, perfil, ativo, senha, setor_sigla=setor_sigla)
                registrar_auditoria(curr["usuario"], "EDITAR_USUARIO", f"Atualizou usuário ID {user_id} (Perfil: {perfil}, Setor: {setor_sigla}, Ativo: {ativo})", self._get_client_ip())
                self._send_json({"success": True, "message": "Usuário atualizado com sucesso!"})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Atualizar Projeto
        if path.startswith("/api/projetos/"):
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                proj_id = int(path.split("/")[-1])
                dados = self._read_json()
                nome = dados.get("nome", "")
                descricao = dados.get("descricao", "")
                etiqueta = dados.get("etiqueta", "Contratos")
                setor_sigla = dados.get("setor_sigla", "STI")
                sucesso = atualizar_projeto(proj_id, nome, descricao, etiqueta, setor_sigla=setor_sigla)
                if sucesso:
                    registrar_auditoria(curr["usuario"], "EDITAR_PROJETO", f"Atualizou projeto ID {proj_id} ({nome}) - Etiqueta: {etiqueta}, Setor: {setor_sigla}", self._get_client_ip())
                    self._send_json({"success": True, "message": "Projeto atualizado com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Projeto não encontrado para atualização"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Atualizar Processo
        if path.startswith("/api/processos/"):
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                proc_id = int(path.split("/")[-1])
                dados = self._read_json()
                sucesso = atualizar_processo(proc_id, dados)
                if sucesso:
                    registrar_auditoria(curr["usuario"], "EDITAR_PROCESSO", f"Atualizou processo ID {proc_id} ({dados.get('numero_processo')})", self._get_client_ip())
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

        # Excluir / Desativar Setor da SEDUC (Admin apenas)
        if path.startswith("/api/setores/"):
            curr = self._require_role("admin")
            if not curr:
                return
            try:
                s_id = int(path.split("/")[-1])
                setor_alvo = obter_setor(s_id)
                if not setor_alvo:
                    self._send_json({"success": False, "error": "Setor não encontrado."}, 404)
                    return
                excluir_setor(s_id)
                registrar_auditoria(curr["usuario"], "EXCLUIR_SETOR", f"Removeu ou inativou setor '{setor_alvo['sigla']}' (ID {s_id})", self._get_client_ip())
                self._send_json({"success": True, "message": f"Setor '{setor_alvo['sigla']}' processado com sucesso!"})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Excluir Usuário (Admin apenas)
        if path.startswith("/api/usuarios/"):
            curr = self._require_role("admin")
            if not curr:
                return
            try:
                u_id = int(path.split("/")[-1])
                alvo = obter_usuario_por_id(u_id)
                if not alvo:
                    self._send_json({"success": False, "error": "Usuário não encontrado."}, 404)
                    return
                if alvo["usuario"].lower() == curr["usuario"].lower():
                    self._send_json({"success": False, "error": "Você não pode excluir sua própria conta de usuário logada."}, 400)
                    return
                excluir_usuario(u_id)
                registrar_auditoria(curr["usuario"], "EXCLUIR_USUARIO", f"Removeu usuário '{alvo['usuario']}' (ID {u_id})", self._get_client_ip())
                self._send_json({"success": True, "message": f"Usuário '{alvo['usuario']}' excluído com sucesso!"})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Excluir Projeto (Admin apenas)
        if path.startswith("/api/projetos/"):
            curr = self._require_role("admin")
            if not curr:
                return
            try:
                proj_id = int(path.split("/")[-1])
                sucesso = excluir_projeto(proj_id)
                if sucesso:
                    registrar_auditoria(curr["usuario"], "EXCLUIR_PROJETO", f"Excluiu projeto ID {proj_id}", self._get_client_ip())
                    self._send_json({"success": True, "message": "Projeto e seus processos removidos com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Projeto não encontrado"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Excluir Processo (Admin apenas)
        if path.startswith("/api/processos/"):
            curr = self._require_role("admin")
            if not curr:
                return
            try:
                proc_id = int(path.split("/")[-1])
                sucesso = excluir_processo(proc_id)
                if sucesso:
                    registrar_auditoria(curr["usuario"], "EXCLUIR_PROCESSO", f"Excluiu processo ID {proc_id}", self._get_client_ip())
                    self._send_json({"success": True, "message": "Processo removido com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Processo não encontrado"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        # Excluir Documento/Peça do Processo
        if path.startswith("/api/documentos/"):
            curr = self._require_role("admin", "operador")
            if not curr:
                return
            try:
                doc_id = int(path.split("/")[-1])
                ok = excluir_documento_processo(doc_id)
                if ok:
                    registrar_auditoria(curr["usuario"], "EXCLUIR_DOCUMENTO", f"Removeu peça ID {doc_id}", self._get_client_ip())
                    self._send_json({"success": True, "message": "Documento removido com sucesso!"})
                else:
                    self._send_json({"success": False, "error": "Documento não encontrado"}, 404)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            return

        self._send_json({"success": False, "error": "Rota DELETE não encontrada"}, 404)
