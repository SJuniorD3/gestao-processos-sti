import sqlite3
import datetime
import os
import hashlib
import hmac
import secrets
from pathlib import Path
from config import DATABASE_FILE, DATABASE_URL, ADMIN_USER, ADMIN_PASS

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

def get_is_postgres():
    return bool(DATABASE_URL and psycopg2)

def gerar_hash_senha(senha):
    """Gera hash PBKDF2-HMAC-SHA256 seguro com salt aleatório de 16 bytes."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"{salt}:{key}"

def verificar_senha(senha, senha_hash):
    """Verifica se a senha em texto puro corresponde ao hash armazenado."""
    if not senha_hash or ":" not in senha_hash:
        return False
    salt, key = senha_hash.split(":", 1)
    test_key = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return hmac.compare_digest(key, test_key)

class UniversalCursor:
    def __init__(self, raw_cursor, is_postgres=False):
        self.cursor = raw_cursor
        self.is_postgres = is_postgres
        self.lastrowid = None

    def execute(self, query, params=None):
        if self.is_postgres:
            # Substitui placeholders ? por %s para PostgreSQL
            pg_query = query.replace("?", "%s")
            stripped = pg_query.strip().rstrip(";")
            
            # Se for INSERT e precisa capturar lastrowid
            if stripped.upper().startswith("INSERT INTO") and "RETURNING" not in stripped.upper():
                pg_query = stripped + " RETURNING id"
                if params is not None:
                    self.cursor.execute(pg_query, params)
                else:
                    self.cursor.execute(pg_query)
                row = self.cursor.fetchone()
                if row:
                    self.lastrowid = row["id"] if isinstance(row, dict) else row[0]
                return self
            
            if params is not None:
                self.cursor.execute(pg_query, params)
            else:
                self.cursor.execute(pg_query)
            return self
        else:
            if params is not None:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            self.lastrowid = getattr(self.cursor, "lastrowid", None)
            return self

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [dict(r) for r in rows]

    @property
    def rowcount(self):
        return self.cursor.rowcount

class UniversalConnection:
    def __init__(self, raw_conn, is_postgres=False):
        self.conn = raw_conn
        self.is_postgres = is_postgres

    def cursor(self):
        if self.is_postgres:
            return UniversalCursor(self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), is_postgres=True)
        else:
            return UniversalCursor(self.conn.cursor(), is_postgres=False)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()

def get_connection():
    if get_is_postgres():
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        raw = psycopg2.connect(url, sslmode="require")
        return UniversalConnection(raw, is_postgres=True)
    else:
        raw = sqlite3.connect(DATABASE_FILE)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        return UniversalConnection(raw, is_postgres=False)

def parse_date(date_str):
    if not date_str or date_str == "-":
        return None
    date_str = str(date_str).strip()
    if " " in date_str:
        date_str = date_str.split(" ")[0]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    return None

def formatar_data_br(date_val):
    """
    Converte qualquer representação de data para o formato brasileiro: DD/MM/AAAA (dia/mês/ano).
    Se for nulo ou inválido, retorna "-".
    """
    if not date_val or str(date_val).strip() in ("", "-", "None", "null"):
        return "-"
    if isinstance(date_val, (datetime.date, datetime.datetime)):
        return date_val.strftime("%d/%m/%Y")
    
    val = str(date_val).strip()
    parte_data = val.split(" ")[0]
    dt = parse_date(parte_data)
    if dt:
        return dt.strftime("%d/%m/%Y")
    return val

def formatar_data_hora_br(date_val):
    """
    Converte data/hora para o formato brasileiro: DD/MM/AAAA HH:MM (ou DD/MM/AAAA se não tiver hora).
    """
    if not date_val or str(date_val).strip() in ("", "-", "None", "null"):
        return "-"
    if isinstance(date_val, datetime.datetime):
        return date_val.strftime("%d/%m/%Y %H:%M")
    if isinstance(date_val, datetime.date):
        return date_val.strftime("%d/%m/%Y")

    val = str(date_val).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.datetime.strptime(val, fmt)
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
    
    dt = parse_date(val)
    if dt:
        return dt.strftime("%d/%m/%Y")
    return val

def calcular_dias_no_setor(data_recebimento_str):
    dt = parse_date(data_recebimento_str)
    if not dt:
        return None
    hoje = datetime.date.today()
    delta = (hoje - dt).days
    return max(0, delta)

def init_db():
    """Inicializa as tabelas com a hierarquia correta: Projetos -> Processos -> Histórico."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if conn.is_postgres:
            # 1. Tabela de Projetos (PostgreSQL / Supabase)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projetos (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL UNIQUE,
                    descricao TEXT,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. Tabela de Processos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processos (
                    id SERIAL PRIMARY KEY,
                    projeto_id INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
                    sistema TEXT NOT NULL,
                    numero_processo TEXT NOT NULL UNIQUE,
                    local_atual TEXT,
                    acao TEXT,
                    data_recebimento TEXT,
                    situacao TEXT,
                    monitorar INTEGER DEFAULT 1,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 3. Tabela de Histórico de Status
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historico_status (
                    id SERIAL PRIMARY KEY,
                    processo_id INTEGER NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
                    data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    data_movimentacao TEXT,
                    local TEXT,
                    situacao TEXT,
                    acao TEXT,
                    observacao TEXT
                )
            """)

            # 4. Tabela de Relatórios Gerados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relatorios_gerados (
                    id SERIAL PRIMARY KEY,
                    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tipo TEXT,
                    total_processos INTEGER,
                    destinatarios TEXT,
                    status TEXT,
                    conteudo TEXT
                )
            """)

            # 5. Tabela de Usuários (PostgreSQL)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    usuario TEXT NOT NULL UNIQUE,
                    senha_hash TEXT NOT NULL,
                    perfil TEXT NOT NULL DEFAULT 'operador',
                    ativo INTEGER DEFAULT 1,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 6. Tabela de Trilha de Auditoria (PostgreSQL)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auditoria_logs (
                    id SERIAL PRIMARY KEY,
                    usuario TEXT NOT NULL,
                    acao TEXT NOT NULL,
                    detalhes TEXT,
                    ip TEXT,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            # 1. Tabela de Projetos (SQLite)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projetos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    descricao TEXT,
                    criado_em TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

            # 2. Tabela de Processos vinculados a um Projeto
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    projeto_id INTEGER NOT NULL,
                    sistema TEXT NOT NULL,
                    numero_processo TEXT NOT NULL UNIQUE,
                    local_atual TEXT,
                    acao TEXT,
                    data_recebimento TEXT,
                    situacao TEXT,
                    monitorar INTEGER DEFAULT 1,
                    criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                    atualizado_em TEXT DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (projeto_id) REFERENCES projetos(id) ON DELETE CASCADE
                )
            """)

            # 3. Tabela de Histórico de Status
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historico_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    processo_id INTEGER NOT NULL,
                    data_registro TEXT DEFAULT (datetime('now', 'localtime')),
                    data_movimentacao TEXT,
                    local TEXT,
                    situacao TEXT,
                    acao TEXT,
                    observacao TEXT,
                    FOREIGN KEY (processo_id) REFERENCES processos(id) ON DELETE CASCADE
                )
            """)

            # 4. Tabela de Relatórios Gerados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relatorios_gerados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_hora TEXT DEFAULT (datetime('now', 'localtime')),
                    tipo TEXT,
                    total_processos INTEGER,
                    destinatarios TEXT,
                    status TEXT,
                    conteudo TEXT
                )
            """)

            # 5. Tabela de Usuários (SQLite)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    usuario TEXT NOT NULL UNIQUE,
                    senha_hash TEXT NOT NULL,
                    perfil TEXT NOT NULL DEFAULT 'operador',
                    ativo INTEGER DEFAULT 1,
                    criado_em TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

            # 6. Tabela de Trilha de Auditoria (SQLite)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auditoria_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT NOT NULL,
                    acao TEXT NOT NULL,
                    detalhes TEXT,
                    ip TEXT,
                    criado_em TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

        # Migração e normalização automática de datas para dia/mês/ano (DD/MM/AAAA)
        try:
            cursor.execute("SELECT id, data_recebimento FROM processos WHERE data_recebimento IS NOT NULL AND data_recebimento != ''")
            for p_row in cursor.fetchall():
                p_id = p_row["id"]
                p_dt = p_row["data_recebimento"]
                d_obj = parse_date(p_dt)
                if d_obj:
                    d_br = d_obj.strftime("%d/%m/%Y")
                    if d_br != p_dt:
                        cursor.execute("UPDATE processos SET data_recebimento = ? WHERE id = ?", (d_br, p_id))

            cursor.execute("SELECT id, data_movimentacao FROM historico_status WHERE data_movimentacao IS NOT NULL AND data_movimentacao != ''")
            for h_row in cursor.fetchall():
                h_id = h_row["id"]
                h_dt = h_row["data_movimentacao"]
                h_br = formatar_data_hora_br(h_dt)
                if h_br != "-" and h_br != h_dt:
                    cursor.execute("UPDATE historico_status SET data_movimentacao = ? WHERE id = ?", (h_br, h_id))
        except Exception:
            pass

        # Seed inicial do usuário Administrador se não houver nenhum usuário cadastrado
        try:
            cursor.execute("SELECT COUNT(*) as total FROM usuarios")
            row = cursor.fetchone()
            total_u = row["total"] if isinstance(row, dict) else row[0]
            if total_u == 0:
                admin_username = (ADMIN_USER or "admin").strip().lower()
                admin_password = (ADMIN_PASS or "STIadmin").strip()
                hash_admin = gerar_hash_senha(admin_password)
                cursor.execute("""
                    INSERT INTO usuarios (nome, usuario, senha_hash, perfil, ativo)
                    VALUES (?, ?, ?, 'admin', 1)
                """, ("Administrador STI", admin_username, hash_admin))
                
                cursor.execute("""
                    INSERT INTO auditoria_logs (usuario, acao, detalhes, ip)
                    VALUES (?, 'SISTEMA_INIT', 'Criação do usuário administrador padrão', '127.0.0.1')
                """, (admin_username,))
        except Exception as e:
            print(f"[!] Aviso ao verificar usuários iniciais: {e}")

        conn.commit()

# -------------------------------------------------------------
# GESTÃO DE USUÁRIOS E PERMISSÕES (RBAC)
# -------------------------------------------------------------
def obter_usuario_por_login(usuario):
    """Busca usuário pelo login (case-insensitive)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        u_limpo = str(usuario).strip().lower()
        cursor.execute("SELECT * FROM usuarios WHERE LOWER(usuario) = ?", (u_limpo,))
        row = cursor.fetchone()
        return dict(row) if row else None

def obter_usuario_por_id(user_id):
    """Busca usuário pelo ID (sem retornar o hash de senha)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, usuario, perfil, ativo, criado_em FROM usuarios WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def listar_usuarios():
    """Retorna lista de todos os usuários cadastrados (sem as senhas)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, usuario, perfil, ativo, criado_em FROM usuarios ORDER BY id ASC")
        return cursor.fetchall()

def criar_usuario(nome, usuario, senha, perfil="operador"):
    """Cadastra um novo usuário no sistema com senha criptografada."""
    u_limpo = str(usuario).strip().lower()
    n_limpo = str(nome).strip()
    p_limpo = str(perfil).strip().lower()
    if p_limpo not in ("admin", "operador", "leitor"):
        p_limpo = "operador"

    hash_s = gerar_hash_senha(str(senha).strip())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO usuarios (nome, usuario, senha_hash, perfil, ativo)
            VALUES (?, ?, ?, ?, 1)
        """, (n_limpo, u_limpo, hash_s, p_limpo))
        conn.commit()
        return cursor.lastrowid

def atualizar_usuario(user_id, nome, perfil, ativo=1, nova_senha=None):
    """Atualiza dados do usuário e opcionalmente redefine sua senha."""
    p_limpo = str(perfil).strip().lower()
    if p_limpo not in ("admin", "operador", "leitor"):
        p_limpo = "operador"

    with get_connection() as conn:
        cursor = conn.cursor()
        if nova_senha and str(nova_senha).strip():
            hash_s = gerar_hash_senha(str(nova_senha).strip())
            cursor.execute("""
                UPDATE usuarios
                SET nome = ?, perfil = ?, ativo = ?, senha_hash = ?
                WHERE id = ?
            """, (str(nome).strip(), p_limpo, int(ativo), hash_s, user_id))
        else:
            cursor.execute("""
                UPDATE usuarios
                SET nome = ?, perfil = ?, ativo = ?
                WHERE id = ?
            """, (str(nome).strip(), p_limpo, int(ativo), user_id))
        conn.commit()
        return True

def excluir_usuario(user_id):
    """Remove um usuário do sistema."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
        conn.commit()
        return True

# -------------------------------------------------------------
# TRILHA DE AUDITORIA
# -------------------------------------------------------------
def registrar_auditoria(usuario, acao, detalhes="", ip=""):
    """Registra uma operação executada por um usuário na trilha de auditoria."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO auditoria_logs (usuario, acao, detalhes, ip)
                VALUES (?, ?, ?, ?)
            """, (str(usuario or "sistema").strip(), str(acao).strip(), str(detalhes).strip(), str(ip or "").strip()))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        print(f"[!] Erro ao registrar auditoria: {e}")
        return None

def listar_auditoria(limite=100):
    """Retorna os registros mais recentes da trilha de auditoria."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, usuario, acao, detalhes, ip, criado_em
            FROM auditoria_logs
            ORDER BY id DESC
            LIMIT ?
        """, (int(limite),))
        return cursor.fetchall()

def limpar_todos_os_dados():
    """Remove absolutamente todos os projetos, processos, históricos e relatórios, deixando o sistema 100% zerado."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historico_status")
        cursor.execute("DELETE FROM processos")
        cursor.execute("DELETE FROM projetos")
        cursor.execute("DELETE FROM relatorios_gerados")
        conn.commit()

def seed_initial_data(conn):
    """Carga inicial desativada - sistema pronto e 100% zerado para novos cadastros."""
    pass

def obter_ou_criar_projeto(nome, descricao="", conn=None):
    """Garante que o projeto seja único e retorna seu ID."""
    deve_fechar = False
    if conn is None:
        conn = get_connection()
        deve_fechar = True

    try:
        cursor = conn.cursor()
        nome_limpo = nome.strip().upper()
        cursor.execute("SELECT id, descricao FROM projetos WHERE UPPER(nome) = ?", (nome_limpo,))
        row = cursor.fetchone()
        if row:
            if descricao and not row["descricao"]:
                cursor.execute("UPDATE projetos SET descricao = ? WHERE id = ?", (descricao.strip(), row["id"]))
                conn.commit()
            return row["id"]
        
        cursor.execute("INSERT INTO projetos (nome, descricao) VALUES (?, ?)", (nome.strip(), descricao.strip()))
        conn.commit()
        return cursor.lastrowid
    finally:
        if deve_fechar:
            conn.close()

def obter_projeto(projeto_id):
    """Retorna os dados de um projeto específico."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projetos WHERE id = ?", (projeto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def atualizar_projeto(projeto_id, nome, descricao=""):
    """Permite editar o nome e a descrição/objeto de um projeto."""
    with get_connection() as conn:
        cursor = conn.cursor()
        nome_limpo = nome.strip()
        desc_limpa = descricao.strip()
        cursor.execute("""
            UPDATE projetos
            SET nome = ?, descricao = ?
            WHERE id = ?
        """, (nome_limpo, desc_limpa, projeto_id))
        conn.commit()
        return cursor.rowcount > 0

def excluir_projeto(projeto_id):
    """Exclui um projeto e todos os seus processos vinculados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projetos WHERE id = ?", (projeto_id,))
        conn.commit()
        return cursor.rowcount > 0

def listar_projetos_com_processos(apenas_monitorados=False):
    """
    Retorna os projetos agrupados com seus respectivos processos vinculados (SEI / STARTGOV).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projetos ORDER BY nome ASC")
        projetos_rows = cursor.fetchall()
        
        resultado = []
        for p_row in projetos_rows:
            proj = dict(p_row)
            
            # Busca processos do projeto
            q_proc = "SELECT * FROM processos WHERE projeto_id = ?"
            if apenas_monitorados:
                q_proc += " AND monitorar = 1"
            q_proc += " ORDER BY id ASC"

            cursor.execute(q_proc, (proj["id"],))
            proc_rows = cursor.fetchall()

            processos_list = []
            for r in proc_rows:
                proc = dict(r)
                proc["projeto"] = proj["nome"]
                proc["descricao"] = proj["descricao"]
                proc["dias_no_setor"] = calcular_dias_no_setor(proc["data_recebimento"])
                proc["data_recebimento"] = formatar_data_br(proc["data_recebimento"]) if proc["data_recebimento"] else ""

                # Busca 4 últimos status
                cursor.execute("""
                    SELECT id, data_registro, data_movimentacao, local, situacao, acao, observacao
                    FROM historico_status
                    WHERE processo_id = ?
                    ORDER BY id DESC
                    LIMIT 4
                """, (proc["id"],))
                status_list = []
                for h in cursor.fetchall():
                    h_dict = dict(h)
                    if h_dict.get("data_movimentacao"):
                        h_dict["data_movimentacao"] = formatar_data_hora_br(h_dict["data_movimentacao"])
                    status_list.append(h_dict)
                proc["ultimos_4_status"] = status_list
                processos_list.append(proc)

            # Se pediu apenas monitorados e o projeto não tem nenhum processo monitorado ativo, pula
            if apenas_monitorados and len(processos_list) == 0:
                continue

            proj["processos"] = processos_list
            proj["total_processos"] = len(processos_list)
            resultado.append(proj)

        return resultado

def listar_processos(apenas_monitorados=False):
    """
    Retorna a lista de todos os processos individualmente, contendo o nome e a descrição do seu Projeto.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                p.id,
                p.projeto_id,
                proj.nome AS projeto,
                proj.descricao AS descricao,
                p.sistema,
                p.numero_processo,
                p.local_atual,
                p.acao,
                p.data_recebimento,
                p.situacao,
                p.monitorar,
                p.criado_em,
                p.atualizado_em
            FROM processos p
            INNER JOIN projetos proj ON p.projeto_id = proj.id
        """
        if apenas_monitorados:
            query += " WHERE p.monitorar = 1"
        query += " ORDER BY proj.nome ASC, p.id ASC"

        cursor.execute(query)
        rows = cursor.fetchall()

        resultado = []
        for row in rows:
            proc = dict(row)
            proc["dias_no_setor"] = calcular_dias_no_setor(proc["data_recebimento"])
            proc["data_recebimento"] = formatar_data_br(proc["data_recebimento"]) if proc["data_recebimento"] else ""

            # 4 últimos status
            cursor.execute("""
                SELECT id, data_registro, data_movimentacao, local, situacao, acao, observacao
                FROM historico_status
                WHERE processo_id = ?
                ORDER BY id DESC
                LIMIT 4
            """, (proc["id"],))
            status_list = []
            for h in cursor.fetchall():
                h_dict = dict(h)
                if h_dict.get("data_movimentacao"):
                    h_dict["data_movimentacao"] = formatar_data_hora_br(h_dict["data_movimentacao"])
                status_list.append(h_dict)
            proc["ultimos_4_status"] = status_list
            resultado.append(proc)

        return resultado

def obter_processo(processo_id):
    """Retorna detalhes de um processo, seu projeto vinculado e histórico completo."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                p.id,
                p.projeto_id,
                proj.nome AS projeto,
                proj.descricao AS descricao,
                p.sistema,
                p.numero_processo,
                p.local_atual,
                p.acao,
                p.data_recebimento,
                p.situacao,
                p.monitorar,
                p.criado_em,
                p.atualizado_em
            FROM processos p
            INNER JOIN projetos proj ON p.projeto_id = proj.id
            WHERE p.id = ?
        """, (processo_id,))
        row = cursor.fetchone()
        if not row:
            return None
        proc = dict(row)
        proc["dias_no_setor"] = calcular_dias_no_setor(proc["data_recebimento"])
        proc["data_recebimento"] = formatar_data_br(proc["data_recebimento"]) if proc["data_recebimento"] else ""

        cursor.execute("""
            SELECT id, data_registro, data_movimentacao, local, situacao, acao, observacao
            FROM historico_status
            WHERE processo_id = ?
            ORDER BY id DESC
        """, (processo_id,))
        historico = []
        for h in cursor.fetchall():
            h_dict = dict(h)
            if h_dict.get("data_movimentacao"):
                h_dict["data_movimentacao"] = formatar_data_hora_br(h_dict["data_movimentacao"])
            historico.append(h_dict)
        proc["historico_completo"] = historico
        proc["ultimos_4_status"] = historico[:4]
        return proc

def criar_processo(dados):
    """
    Cadastra um novo processo vinculando ao seu Projeto.
    Se o Projeto já existir, reutiliza o mesmo projeto e vincula o novo processo (SEI ou STARTGOV)!
    """
    with get_connection() as conn:
        nome_projeto = dados.get("projeto", "").strip() or "STI"
        descricao_projeto = dados.get("descricao", "").strip()
        
        # Garante o projeto único
        projeto_id = obter_ou_criar_projeto(nome_projeto, descricao_projeto, conn=conn)

        cursor = conn.cursor()
        monitorar_val = 1 if dados.get("monitorar", 1) in (1, "1", True, "true", "True") else 0
        local_atual = dados.get("local_atual", "").strip() or "Aguardando Monitoramento"
        situacao = dados.get("situacao", "").strip() or "Cadastrado para monitoramento"
        acao = dados.get("acao", "").strip() or "Aguardando trâmite"
        raw_dt = dados.get("data_recebimento", "").strip()
        dt_parsed = parse_date(raw_dt)
        data_recebimento = dt_parsed.strftime("%d/%m/%Y") if dt_parsed else (raw_dt if raw_dt else "")

        cursor.execute("""
            INSERT INTO processos (projeto_id, sistema, numero_processo, local_atual, acao, data_recebimento, situacao, monitorar)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            projeto_id,
            dados.get("sistema", "").strip() or "SEI",
            dados.get("numero_processo", "").strip(),
            local_atual,
            acao,
            data_recebimento,
            situacao,
            monitorar_val
        ))
        proc_id = cursor.lastrowid

        data_reg = data_recebimento if data_recebimento else datetime.date.today().strftime("%d/%m/%Y")
        cursor.execute("""
            INSERT INTO historico_status (processo_id, data_movimentacao, local, situacao, acao, observacao)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            proc_id,
            data_reg,
            local_atual,
            situacao,
            acao,
            f"Processo vinculado ao projeto {nome_projeto}"
        ))
        conn.commit()
        return proc_id

def atualizar_processo(processo_id, dados, registrar_novo_status=True):
    """Atualiza dados do processo e permite renomear ou trocar o projeto."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Pega estado anterior
        cursor.execute("""
            SELECT p.local_atual, p.acao, p.situacao, p.data_recebimento, p.projeto_id, proj.nome as projeto_nome
            FROM processos p
            INNER JOIN projetos proj ON p.projeto_id = proj.id
            WHERE p.id = ?
        """, (processo_id,))
        anterior = cursor.fetchone()
        if not anterior:
            return False

        nome_projeto = dados.get("projeto", "").strip() or anterior["projeto_nome"]
        descricao_projeto = dados.get("descricao", "").strip()
        projeto_id = obter_ou_criar_projeto(nome_projeto, descricao_projeto, conn=conn)

        monitorar_val = 1 if dados.get("monitorar", 1) in (1, "1", True, "true", "True") else 0
        local_atual = dados.get("local_atual", "").strip() or anterior["local_atual"] or "Aguardando Monitoramento"
        situacao = dados.get("situacao", "").strip() or anterior["situacao"] or "Em tramitação"
        acao = dados.get("acao", "").strip() or anterior["acao"] or "Aguardando trâmite"
        raw_dt = dados.get("data_recebimento", "").strip()
        if raw_dt:
            dt_parsed = parse_date(raw_dt)
            data_recebimento = dt_parsed.strftime("%d/%m/%Y") if dt_parsed else raw_dt
        else:
            data_recebimento = anterior["data_recebimento"]

        cursor.execute("""
            UPDATE processos
            SET projeto_id = ?,
                sistema = ?,
                numero_processo = ?,
                local_atual = ?,
                acao = ?,
                data_recebimento = ?,
                situacao = ?,
                monitorar = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            projeto_id,
            dados.get("sistema", "").strip(),
            dados.get("numero_processo", "").strip(),
            local_atual,
            acao,
            data_recebimento,
            situacao,
            monitorar_val,
            processo_id
        ))

        houve_mudanca = (
            anterior["local_atual"] != local_atual or
            anterior["situacao"] != situacao or
            anterior["acao"] != acao
        )

        if registrar_novo_status and houve_mudanca:
            cursor.execute("""
                INSERT INTO historico_status (processo_id, data_movimentacao, local, situacao, acao, observacao)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                processo_id,
                data_recebimento or datetime.date.today().strftime("%d/%m/%Y"),
                local_atual,
                situacao,
                acao,
                dados.get("observacao_historico", "Atualização de status")
            ))

        conn.commit()
        return True

def salvar_historico_4_linhas_sei(processo_id, historico_4_linhas, sistema="OFICIAL"):
    """
    Substitui os status anteriores do processo pelas 4 linhas mais recentes extraídas
    diretamente do 'Ver Histórico Completo' do SEI ou do histórico de movimentações do STARTGOV.
    Insere na ordem cronológica inversa para que a Linha 1 (mais recente) fique no topo (ORDER BY id DESC).
    """
    if not historico_4_linhas:
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historico_status WHERE processo_id = ?", (processo_id,))
        
        # Insere em ordem inversa para que a Linha 1 seja a de maior ID (mais recente)
        for item in reversed(historico_4_linhas):
            acao_val = item.get("acao") or ("Trâmite SEI" if "SEI" in str(sistema).upper() else "Trâmite StartGov")
            obs_val = f"Usuário: {item.get('usuario', '')}" if item.get('usuario') else f"Portal {sistema}"
            dt_mov = formatar_data_hora_br(item.get("data_hora") or item.get("data_movimentacao", "-"))
            cursor.execute("""
                INSERT INTO historico_status (processo_id, data_registro, data_movimentacao, local, situacao, acao, observacao)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                processo_id,
                datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                dt_mov,
                item.get("local") or item.get("unidade", "-"),
                item.get("situacao") or item.get("descricao", "-"),
                acao_val,
                obs_val
            ))
        conn.commit()

# Alias genérico para gravação dos 4 status mais recentes
salvar_historico_4_status = salvar_historico_4_linhas_sei

def excluir_processo(processo_id):
    """Exclui processo e histórico associado."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM processos WHERE id = ?", (processo_id,))
        conn.commit()
        return cursor.rowcount > 0

def registrar_log_relatorio(tipo, total_processos, destinatarios, status, conteudo):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO relatorios_gerados (tipo, total_processos, destinatarios, status, conteudo)
            VALUES (?, ?, ?, ?, ?)
        """, (tipo, total_processos, destinatarios, status, conteudo))
        conn.commit()

def listar_ultimos_relatorios(limit=10):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, data_hora, tipo, total_processos, destinatarios, status, conteudo
            FROM relatorios_gerados
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(r) for r in cursor.fetchall()]
