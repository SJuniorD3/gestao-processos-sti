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

    def _clean_val(self, val):
        if isinstance(val, datetime.datetime):
            return val.strftime("%d/%m/%Y %H:%M:%S")
        if isinstance(val, datetime.date):
            return val.strftime("%d/%m/%Y")
        return val

    def _clean_row(self, row):
        if row is None:
            return None
        d = dict(row)
        for k, v in d.items():
            if isinstance(v, (datetime.datetime, datetime.date)):
                d[k] = self._clean_val(v)
        return d

    def fetchone(self):
        row = self.cursor.fetchone()
        return self._clean_row(row)

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [self._clean_row(r) for r in rows]

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
            # 0. Tabela de Setores da SEDUC (PostgreSQL / Supabase)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS setores (
                    id SERIAL PRIMARY KEY,
                    sigla TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    ativo INTEGER DEFAULT 1,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 1. Tabela de Projetos (PostgreSQL / Supabase)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projetos (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL UNIQUE,
                    descricao TEXT,
                    etiqueta TEXT DEFAULT 'Contratos',
                    setor_sigla TEXT DEFAULT 'STI',
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
                    setor_sigla TEXT DEFAULT 'STI',
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

            # 7. Tabela de Documentos / Peças do Processo (PostgreSQL)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documentos_processo (
                    id SERIAL PRIMARY KEY,
                    processo_id INTEGER NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
                    numero_sei TEXT,
                    tipo_documento TEXT,
                    nome_exibicao TEXT NOT NULL,
                    data_documento TEXT,
                    unidade_geradora TEXT,
                    link_visualizacao TEXT,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            # 0. Tabela de Setores da SEDUC (SQLite)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS setores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sigla TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    ativo INTEGER DEFAULT 1,
                    criado_em TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

            # 1. Tabela de Projetos (SQLite)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projetos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    descricao TEXT,
                    etiqueta TEXT DEFAULT 'Contratos',
                    setor_sigla TEXT DEFAULT 'STI',
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
                    setor_sigla TEXT DEFAULT 'STI',
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

            # 7. Tabela de Documentos / Peças do Processo (SQLite)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documentos_processo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    processo_id INTEGER NOT NULL,
                    numero_sei TEXT,
                    tipo_documento TEXT,
                    nome_exibicao TEXT NOT NULL,
                    data_documento TEXT,
                    unidade_geradora TEXT,
                    link_visualizacao TEXT,
                    criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (processo_id) REFERENCES processos(id) ON DELETE CASCADE
                )
            """)

        # Migração de coluna: etiqueta e setor_sigla na tabela de projetos (SQLite e PostgreSQL)
        try:
            if conn.is_postgres:
                cursor.execute("ALTER TABLE projetos ADD COLUMN IF NOT EXISTS etiqueta TEXT DEFAULT 'Contratos'")
                cursor.execute("ALTER TABLE projetos ADD COLUMN IF NOT EXISTS setor_sigla TEXT DEFAULT 'STI'")
            else:
                cursor.execute("PRAGMA table_info(projetos)")
                colunas_proj = [col["name"] for col in cursor.fetchall()]
                if "etiqueta" not in colunas_proj:
                    cursor.execute("ALTER TABLE projetos ADD COLUMN etiqueta TEXT DEFAULT 'Contratos'")
                if "setor_sigla" not in colunas_proj:
                    cursor.execute("ALTER TABLE projetos ADD COLUMN setor_sigla TEXT DEFAULT 'STI'")
            cursor.execute("UPDATE projetos SET etiqueta = 'Contratos' WHERE etiqueta IS NULL OR etiqueta = ''")
            cursor.execute("UPDATE projetos SET setor_sigla = 'STI' WHERE setor_sigla IS NULL OR setor_sigla = ''")
        except Exception as e_mig:
            print(f"[!] Aviso na migração de projetos: {e_mig}")

        # Migração de coluna: setor_sigla na tabela de usuarios (SQLite e PostgreSQL)
        try:
            if conn.is_postgres:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS setor_sigla TEXT DEFAULT 'STI'")
            else:
                cursor.execute("PRAGMA table_info(usuarios)")
                colunas_user = [col["name"] for col in cursor.fetchall()]
                if "setor_sigla" not in colunas_user:
                    cursor.execute("ALTER TABLE usuarios ADD COLUMN setor_sigla TEXT DEFAULT 'STI'")
            cursor.execute("UPDATE usuarios SET setor_sigla = 'STI' WHERE setor_sigla IS NULL OR setor_sigla = ''")
        except Exception as e_mig_u:
            print(f"[!] Aviso na migração de usuarios: {e_mig_u}")

        # Carga inicial padrão de Setores da SEDUC
        try:
            setores_iniciais = [
                ("STI", "Superintendência de Tecnologia da Informação"),
                ("SAOFC", "Secretaria Adjunta de Orçamento, Finanças e Contabilidade"),
                ("ASJUR", "Assessoria Jurídica"),
                ("GAB", "Gabinete da Secretaria"),
                ("CPL", "Comissão Permanente de Licitação"),
                ("DA", "Diretoria de Administração"),
                ("SGP", "Superintendência de Gestão de Pessoas"),
                ("SEDUC", "Secretaria de Estado da Educação - Sede")
            ]
            for s_sigla, s_nome in setores_iniciais:
                cursor.execute("SELECT id FROM setores WHERE UPPER(sigla) = ?", (s_sigla.upper(),))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO setores (sigla, nome, ativo) VALUES (?, ?, 1)", (s_sigla.upper(), s_nome))
        except Exception as e_sec:
            print(f"[!] Aviso ao verificar setores iniciais: {e_sec}")

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

        # Seed do usuário Administrador se não existir na tabela
        try:
            admin_username = (ADMIN_USER or "admin").strip().lower()
            cursor.execute("SELECT id FROM usuarios WHERE LOWER(usuario) = ?", (admin_username,))
            admin_row = cursor.fetchone()
            if not admin_row:
                admin_password = (ADMIN_PASS or "STIadmin").strip()
                hash_admin = gerar_hash_senha(admin_password)
                cursor.execute("""
                    INSERT INTO usuarios (nome, usuario, senha_hash, perfil, setor_sigla, ativo)
                    VALUES (?, ?, ?, 'admin', 'STI', 1)
                """, ("Administrador STI", admin_username, hash_admin))
                
                cursor.execute("""
                    INSERT INTO auditoria_logs (usuario, acao, detalhes, ip)
                    VALUES (?, 'SISTEMA_INIT', 'Criação do usuário administrador padrão', '127.0.0.1')
                """, (admin_username,))
        except Exception as e:
            print(f"[!] Aviso ao verificar usuários iniciais: {e}")

        conn.commit()

# -------------------------------------------------------------
# GESTÃO DE SETORES DA SEDUC
# -------------------------------------------------------------
def listar_setores(apenas_ativos=False):
    """Retorna a lista de setores da SEDUC cadastrados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT id, sigla, nome, ativo, criado_em FROM setores"
        if apenas_ativos:
            query += " WHERE ativo = 1"
        query += " ORDER BY sigla ASC"
        cursor.execute(query)
        return cursor.fetchall()

def obter_setor(setor_id):
    """Busca um setor pelo seu ID numérico."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, sigla, nome, ativo, criado_em FROM setores WHERE id = ?", (setor_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def obter_setor_por_sigla(sigla):
    """Busca um setor pela sigla (case-insensitive)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, sigla, nome, ativo, criado_em FROM setores WHERE UPPER(sigla) = ?", (str(sigla).strip().upper(),))
        row = cursor.fetchone()
        return dict(row) if row else None

def criar_setor(sigla, nome):
    """Cadastra um novo setor da SEDUC no sistema."""
    s_limpa = str(sigla).strip().upper()
    n_limpo = str(nome).strip()
    if not s_limpa or not n_limpo:
        raise ValueError("Sigla e Nome do setor são obrigatórios.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM setores WHERE UPPER(sigla) = ?", (s_limpa,))
        if cursor.fetchone():
            raise ValueError(f"O setor com a sigla '{s_limpa}' já existe no sistema.")
        cursor.execute("""
            INSERT INTO setores (sigla, nome, ativo)
            VALUES (?, ?, 1)
        """, (s_limpa, n_limpo))
        conn.commit()
        return cursor.lastrowid

def atualizar_setor(setor_id, sigla, nome, ativo=1):
    """Atualiza a sigla, o nome e o status de um setor da SEDUC."""
    s_limpa = str(sigla).strip().upper()
    n_limpo = str(nome).strip()
    ativo_val = 1 if int(ativo) == 1 else 0
    if not s_limpa or not n_limpo:
        raise ValueError("Sigla e Nome do setor são obrigatórios.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM setores WHERE UPPER(sigla) = ? AND id != ?", (s_limpa, setor_id))
        if cursor.fetchone():
            raise ValueError(f"A sigla '{s_limpa}' já está sendo utilizada por outro setor.")
        cursor.execute("""
            UPDATE setores
            SET sigla = ?, nome = ?, ativo = ?
            WHERE id = ?
        """, (s_limpa, n_limpo, ativo_val, setor_id))
        conn.commit()
        return cursor.rowcount > 0

def excluir_setor(setor_id):
    """Remove ou desativa um setor caso haja registros vinculados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sigla FROM setores WHERE id = ?", (setor_id,))
        row = cursor.fetchone()
        if not row:
            return False
        sigla = row["sigla"].upper()

        # Verifica se há usuários ou projetos com essa sigla
        cursor.execute("SELECT COUNT(*) AS total FROM usuarios WHERE UPPER(setor_sigla) = ?", (sigla,))
        u_cnt = cursor.fetchone()
        total_u = u_cnt["total"] if u_cnt else 0

        cursor.execute("SELECT COUNT(*) AS total FROM projetos WHERE UPPER(setor_sigla) = ?", (sigla,))
        p_cnt = cursor.fetchone()
        total_p = p_cnt["total"] if p_cnt else 0

        if total_u > 0 or total_p > 0:
            # Desativa o setor para manter a integridade dos dados históricos
            cursor.execute("UPDATE setores SET ativo = 0 WHERE id = ?", (setor_id,))
            conn.commit()
            return True

        cursor.execute("DELETE FROM setores WHERE id = ?", (setor_id,))
        conn.commit()
        return True

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
        if not row:
            return None
        u_dict = dict(row)
        if not u_dict.get("setor_sigla"):
            u_dict["setor_sigla"] = "STI"
        return u_dict

def obter_usuario_por_id(user_id):
    """Busca usuário pelo ID (sem retornar o hash de senha)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, usuario, perfil, setor_sigla, ativo, criado_em FROM usuarios WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        u_dict = dict(row)
        if not u_dict.get("setor_sigla"):
            u_dict["setor_sigla"] = "STI"
        return u_dict

def listar_usuarios():
    """Retorna lista de todos os usuários cadastrados (sem as senhas)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, usuario, perfil, setor_sigla, ativo, criado_em FROM usuarios ORDER BY id ASC")
        rows = cursor.fetchall()
        
        # Garante que o administrador padrão conste no banco e na listagem
        admin_user = (ADMIN_USER or "admin").strip().lower()
        has_admin = any(str(r.get("usuario", "")).lower() == admin_user for r in rows)
        if not has_admin:
            try:
                hash_admin = gerar_hash_senha((ADMIN_PASS or "STIadmin").strip())
                cursor.execute("""
                    INSERT INTO usuarios (nome, usuario, senha_hash, perfil, setor_sigla, ativo)
                    VALUES (?, ?, ?, 'admin', 'STI', 1)
                """, ("Administrador STI", admin_user, hash_admin))
                conn.commit()
                cursor.execute("SELECT id, nome, usuario, perfil, setor_sigla, ativo, criado_em FROM usuarios ORDER BY id ASC")
                rows = cursor.fetchall()
            except Exception as e:
                print(f"[!] Erro ao auto-inserir admin padrão em listar_usuarios: {e}")
        
        resultado = []
        for r in rows:
            u_dict = dict(r)
            if not u_dict.get("setor_sigla"):
                u_dict["setor_sigla"] = "STI"
            resultado.append(u_dict)
        return resultado

def criar_usuario(nome, usuario, senha, perfil="operador", setor_sigla="STI"):
    """Cadastra um novo usuário no sistema com senha criptografada e vinculação ao seu setor."""
    u_limpo = str(usuario).strip().lower()
    n_limpo = str(nome).strip()
    p_limpo = str(perfil).strip().lower()
    s_limpo = str(setor_sigla or "STI").strip().upper()
    if p_limpo not in ("admin", "operador", "leitor"):
        p_limpo = "operador"

    hash_s = gerar_hash_senha(str(senha).strip())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO usuarios (nome, usuario, senha_hash, perfil, setor_sigla, ativo)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (n_limpo, u_limpo, hash_s, p_limpo, s_limpo))
        conn.commit()
        return cursor.lastrowid

def atualizar_usuario(user_id, nome, perfil, ativo=1, nova_senha=None, setor_sigla=None):
    """Atualiza dados do usuário, setor e opcionalmente redefine sua senha."""
    p_limpo = str(perfil).strip().lower()
    if p_limpo not in ("admin", "operador", "leitor"):
        p_limpo = "operador"

    with get_connection() as conn:
        cursor = conn.cursor()
        updates = ["nome = ?", "perfil = ?", "ativo = ?"]
        params = [str(nome).strip(), p_limpo, int(ativo)]

        if setor_sigla:
            updates.append("setor_sigla = ?")
            params.append(str(setor_sigla).strip().upper())

        if nova_senha and str(nova_senha).strip():
            hash_s = gerar_hash_senha(str(nova_senha).strip())
            updates.append("senha_hash = ?")
            params.append(hash_s)

        params.append(user_id)
        cursor.execute(f"""
            UPDATE usuarios
            SET {', '.join(updates)}
            WHERE id = ?
        """, tuple(params))
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

def obter_ou_criar_projeto(nome, descricao="", etiqueta="Contratos", setor_sigla="STI", conn=None):
    """Garante que o projeto seja único e retorna seu ID, salvando ou atualizando a etiqueta e o setor responsável."""
    deve_fechar = False
    if conn is None:
        conn = get_connection()
        deve_fechar = True

    etiqueta_limpa = "Pagamentos" if str(etiqueta or "").strip().lower() == "pagamentos" else "Contratos"
    setor_limpo = str(setor_sigla or "STI").strip().upper()

    try:
        cursor = conn.cursor()
        nome_limpo = nome.strip().upper()
        cursor.execute("SELECT id, descricao, etiqueta, setor_sigla FROM projetos WHERE UPPER(nome) = ?", (nome_limpo,))
        row = cursor.fetchone()
        if row:
            updates = []
            params = []
            if descricao and not row["descricao"]:
                updates.append("descricao = ?")
                params.append(descricao.strip())
            # Se forneceu uma etiqueta explicitamente diferente da padrão, ou se o banco estava nulo/vazio
            if etiqueta and (not row.get("etiqueta") or (str(etiqueta).strip() and row.get("etiqueta") != etiqueta_limpa and etiqueta != "Contratos")):
                updates.append("etiqueta = ?")
                params.append(etiqueta_limpa)
            if setor_sigla and (not row.get("setor_sigla") or (row.get("setor_sigla") != setor_limpo and setor_sigla != "STI")):
                updates.append("setor_sigla = ?")
                params.append(setor_limpo)
            if updates:
                params.append(row["id"])
                cursor.execute(f"UPDATE projetos SET {', '.join(updates)} WHERE id = ?", tuple(params))
                conn.commit()
            return row["id"]
        
        cursor.execute("INSERT INTO projetos (nome, descricao, etiqueta, setor_sigla) VALUES (?, ?, ?, ?)", (nome.strip(), descricao.strip(), etiqueta_limpa, setor_limpo))
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
        if not row:
            return None
        p_dict = dict(row)
        if not p_dict.get("etiqueta"):
            p_dict["etiqueta"] = "Contratos"
        if not p_dict.get("setor_sigla"):
            p_dict["setor_sigla"] = "STI"
        return p_dict

def atualizar_projeto(projeto_id, nome, descricao="", etiqueta="Contratos", setor_sigla="STI"):
    """Permite editar o nome, a descrição/objeto, a etiqueta e o setor responsável de um projeto."""
    with get_connection() as conn:
        cursor = conn.cursor()
        nome_limpo = nome.strip()
        desc_limpa = descricao.strip()
        etiqueta_limpa = "Pagamentos" if str(etiqueta or "").strip().lower() == "pagamentos" else "Contratos"
        setor_limpo = str(setor_sigla or "STI").strip().upper()
        cursor.execute("""
            UPDATE projetos
            SET nome = ?, descricao = ?, etiqueta = ?, setor_sigla = ?
            WHERE id = ?
        """, (nome_limpo, desc_limpa, etiqueta_limpa, setor_limpo, projeto_id))
        conn.commit()
        return cursor.rowcount > 0

def excluir_projeto(projeto_id):
    """Exclui um projeto e todos os seus processos vinculados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projetos WHERE id = ?", (projeto_id,))
        conn.commit()
        return cursor.rowcount > 0

def listar_projetos_com_processos(apenas_monitorados=False, setor=None):
    """
    Retorna os projetos agrupados com seus respectivos processos vinculados (SEI / STARTGOV).
    Permite filtrar por setor (setor_sigla).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if setor and str(setor).strip():
            cursor.execute("SELECT * FROM projetos WHERE UPPER(setor_sigla) = ? ORDER BY nome ASC", (str(setor).strip().upper(),))
        else:
            cursor.execute("SELECT * FROM projetos ORDER BY nome ASC")
        projetos_rows = cursor.fetchall()
        
        resultado = []
        for p_row in projetos_rows:
            proj = dict(p_row)
            if not proj.get("etiqueta"):
                proj["etiqueta"] = "Contratos"
            if not proj.get("setor_sigla"):
                proj["setor_sigla"] = "STI"
            
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
                proc["etiqueta"] = proj["etiqueta"]
                proc["setor_sigla"] = proj["setor_sigla"]
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

                # Contagem de documentos/peças anexadas
                try:
                    cursor.execute("SELECT COUNT(*) AS total FROM documentos_processo WHERE processo_id = ?", (proc["id"],))
                    doc_row = cursor.fetchone()
                    proc["total_documentos"] = doc_row["total"] if (doc_row and "total" in doc_row) else 0
                except Exception:
                    proc["total_documentos"] = 0

                processos_list.append(proc)

            # Se pediu apenas monitorados e o projeto não tem nenhum processo monitorado ativo, pula
            if apenas_monitorados and len(processos_list) == 0:
                continue

            proj["processos"] = processos_list
            proj["total_processos"] = len(processos_list)
            resultado.append(proj)

        return resultado

def listar_processos(apenas_monitorados=False, setor=None):
    """
    Retorna a lista de todos os processos individualmente, contendo o nome, setor e a descrição do seu Projeto.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                p.id,
                p.projeto_id,
                proj.nome AS projeto,
                proj.descricao AS descricao,
                proj.etiqueta AS etiqueta,
                proj.setor_sigla AS setor_sigla,
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
        where_clauses = []
        params = []
        if apenas_monitorados:
            where_clauses.append("p.monitorar = 1")
        if setor and str(setor).strip():
            where_clauses.append("UPPER(proj.setor_sigla) = ?")
            params.append(str(setor).strip().upper())

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY proj.nome ASC, p.id ASC"

        cursor.execute(query, tuple(params) if params else None)
        rows = cursor.fetchall()

        resultado = []
        for row in rows:
            proc = dict(row)
            if not proc.get("etiqueta"):
                proc["etiqueta"] = "Contratos"
            if not proc.get("setor_sigla"):
                proc["setor_sigla"] = "STI"
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

            # Contagem de documentos/peças anexadas
            try:
                cursor.execute("SELECT COUNT(*) AS total FROM documentos_processo WHERE processo_id = ?", (proc["id"],))
                doc_row = cursor.fetchone()
                proc["total_documentos"] = doc_row["total"] if (doc_row and "total" in doc_row) else 0
            except Exception:
                proc["total_documentos"] = 0

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
                proj.etiqueta AS etiqueta,
                proj.setor_sigla AS setor_sigla,
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
        if not proc.get("etiqueta"):
            proc["etiqueta"] = "Contratos"
        if not proc.get("setor_sigla"):
            proc["setor_sigla"] = "STI"
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
        etiqueta_projeto = dados.get("etiqueta", "").strip() or "Contratos"
        setor_projeto = dados.get("setor_sigla", "").strip() or dados.get("setor", "").strip() or "STI"
        
        # Garante o projeto único
        projeto_id = obter_ou_criar_projeto(nome_projeto, descricao_projeto, etiqueta=etiqueta_projeto, setor_sigla=setor_projeto, conn=conn)

        cursor = conn.cursor()
        monitorar_val = 1 if dados.get("monitorar", 1) in (1, "1", True, "true", "True") else 0
        local_atual = dados.get("local_atual", "").strip() or "Aguardando Sincronização"
        situacao = dados.get("situacao", "").strip() or "Aguardando Robô STI"
        acao = dados.get("acao", "").strip() or "Sincronização pendente"
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
            f"Processo cadastrado no projeto {nome_projeto}. Aguardando 1ª sincronização automática."
        ))
        conn.commit()
        return proc_id

def atualizar_processo(processo_id, dados, registrar_novo_status=True):
    """Atualiza dados do processo e permite renomear ou trocar o projeto."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Pega estado anterior
        cursor.execute("""
            SELECT p.local_atual, p.acao, p.situacao, p.data_recebimento, p.projeto_id, proj.nome as projeto_nome, proj.etiqueta as projeto_etiqueta, proj.setor_sigla as projeto_setor
            FROM processos p
            INNER JOIN projetos proj ON p.projeto_id = proj.id
            WHERE p.id = ?
        """, (processo_id,))
        anterior = cursor.fetchone()
        if not anterior:
            return False

        nome_projeto = dados.get("projeto", "").strip() or anterior["projeto_nome"]
        descricao_projeto = dados.get("descricao", "").strip()
        etiqueta_projeto = dados.get("etiqueta", "").strip() or anterior.get("projeto_etiqueta", "Contratos")
        setor_projeto = dados.get("setor_sigla", "").strip() or dados.get("setor", "").strip() or anterior.get("projeto_setor", "STI")
        projeto_id = obter_ou_criar_projeto(nome_projeto, descricao_projeto, etiqueta=etiqueta_projeto, setor_sigla=setor_projeto, conn=conn)

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

def obter_processo_por_numero(numero_processo):
    """Busca um processo pelo número (comparação ignorando espaços)."""
    if not numero_processo:
        return None
    num_limpo = str(numero_processo).strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, projeto_id, sistema, numero_processo FROM processos WHERE TRIM(numero_processo) = ? LIMIT 1", (num_limpo,))
        row = cursor.fetchone()
        return dict(row) if row else None

def obter_metricas_gargalos():
    """
    Calcula e retorna indicadores de gargalo operacional e cumprimento de SLA:
    - Faixas de atraso (<=15d, 16-30d, 31-60d, >60d)
    - Agrupamento por setor com tempo médio e máximo de retenção
    - Top processos que exigem atenção urgente
    """
    processos = listar_processos()
    
    total = len(processos)
    soma_dias = 0
    cont_com_dias = 0
    
    faixas = {
        "ate_15_dias": 0,
        "de_16_a_30": 0,
        "de_31_a_60": 0,
        "mais_de_60": 0
    }
    
    setores_map = {}
    sistemas_map = {}
    etiquetas_map = {"Contratos": 0, "Pagamentos": 0}
    lista_com_dias = []
    
    for p in processos:
        dias = p.get("dias_no_setor")
        sis = p.get("sistema") or "SEI"
        sistemas_map[sis] = sistemas_map.get(sis, 0) + 1
        
        etq = p.get("etiqueta") or "Contratos"
        etiquetas_map[etq] = etiquetas_map.get(etq, 0) + 1
        
        setor = (p.get("local_atual") or "Não informado").strip()
        if setor not in setores_map:
            setores_map[setor] = {
                "setor": setor,
                "total": 0,
                "soma_dias": 0,
                "max_dias": 0,
                "processos": []
            }
        
        setores_map[setor]["total"] += 1
        
        if dias is not None and isinstance(dias, (int, float)):
            soma_dias += dias
            cont_com_dias += 1
            lista_com_dias.append(p)
            
            if dias <= 15:
                faixas["ate_15_dias"] += 1
            elif dias <= 30:
                faixas["de_16_a_30"] += 1
            elif dias <= 60:
                faixas["de_31_a_60"] += 1
            else:
                faixas["mais_de_60"] += 1
                
            setores_map[setor]["soma_dias"] += dias
            if dias > setores_map[setor]["max_dias"]:
                setores_map[setor]["max_dias"] = dias
                
        setores_map[setor]["processos"].append({
            "id": p["id"],
            "numero_processo": p["numero_processo"],
            "projeto": p["projeto"],
            "etiqueta": etq,
            "sistema": sis,
            "dias_no_setor": dias,
            "situacao": p.get("situacao", ""),
            "total_documentos": p.get("total_documentos", 0)
        })

    # Calcula médias por setor
    lista_setores = []
    for s_info in setores_map.values():
        total_s = s_info["total"]
        s_info["media_dias"] = round(s_info["soma_dias"] / total_s, 1) if total_s > 0 else 0
        lista_setores.append(s_info)
        
    # Ordena setores por total de processos decrescente e média de dias
    lista_setores.sort(key=lambda x: (x["total"], x["media_dias"]), reverse=True)
    
    # Top 10 mais parados
    top_atrasados = sorted(
        [p for p in lista_com_dias if p.get("dias_no_setor") is not None],
        key=lambda x: x["dias_no_setor"],
        reverse=True
    )[:10]

    media_geral = round(soma_dias / cont_com_dias, 1) if cont_com_dias > 0 else 0

    return {
        "total_processos": total,
        "media_dias_geral": media_geral,
        "faixas_sla": faixas,
        "por_setor": lista_setores,
        "por_sistema": sistemas_map,
        "por_etiqueta": etiquetas_map,
        "top_atrasados": [
            {
                "id": p["id"],
                "numero_processo": p["numero_processo"],
                "projeto": p["projeto"],
                "etiqueta": p.get("etiqueta") or "Contratos",
                "sistema": p.get("sistema") or "SEI",
                "local_atual": p["local_atual"],
                "dias_no_setor": p["dias_no_setor"],
                "situacao": p.get("situacao", ""),
                "total_documentos": p.get("total_documentos", 0)
            }
            for p in top_atrasados
        ]
    }

# -------------------------------------------------------------
# DOCUMENTOS E PEÇAS DO PROCESSO (SEI & ANEXOS)
# -------------------------------------------------------------
def salvar_documentos_processo(processo_id, lista_documentos):
    """
    Substitui ou atualiza os documentos/peças associadas a um processo.
    """
    if not processo_id or lista_documentos is None:
        return 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documentos_processo WHERE processo_id = ?", (processo_id,))
        
        inseridos = 0
        for doc in lista_documentos:
            nome = str(doc.get("nome_exibicao") or doc.get("nome") or "Documento").strip()
            num_sei = str(doc.get("numero_sei") or "").strip()
            tipo = str(doc.get("tipo_documento") or doc.get("tipo") or "Documento").strip()
            dt_doc = str(doc.get("data_documento") or doc.get("data") or "").strip()
            unidade = str(doc.get("unidade_geradora") or doc.get("unidade") or "").strip()
            link = str(doc.get("link_visualizacao") or doc.get("link") or "").strip()

            cursor.execute("""
                INSERT INTO documentos_processo (processo_id, numero_sei, tipo_documento, nome_exibicao, data_documento, unidade_geradora, link_visualizacao)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (processo_id, num_sei, tipo, nome, dt_doc, unidade, link))
            inseridos += 1

        conn.commit()
        return inseridos

def listar_documentos_processo(processo_id):
    """Retorna todas as peças/documentos de um processo."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, processo_id, numero_sei, tipo_documento, nome_exibicao, data_documento, unidade_geradora, link_visualizacao, criado_em
            FROM documentos_processo
            WHERE processo_id = ?
            ORDER BY id ASC
        """, (processo_id,))
        return [dict(r) for r in cursor.fetchall()]

def adicionar_documento_manual(processo_id, dados):
    """Permite anexar manualmente um documento/peça relevante."""
    with get_connection() as conn:
        cursor = conn.cursor()
        nome = str(dados.get("nome_exibicao") or dados.get("nome") or "").strip()
        if not nome:
            raise ValueError("O nome do documento é obrigatório.")

        num_sei = str(dados.get("numero_sei") or "").strip()
        tipo = str(dados.get("tipo_documento") or "Documento").strip()
        dt_doc = str(dados.get("data_documento") or "").strip()
        unidade = str(dados.get("unidade_geradora") or "STI").strip()
        link = str(dados.get("link_visualizacao") or "").strip()

        cursor.execute("""
            INSERT INTO documentos_processo (processo_id, numero_sei, tipo_documento, nome_exibicao, data_documento, unidade_geradora, link_visualizacao)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (processo_id, num_sei, tipo, nome, dt_doc, unidade, link))
        conn.commit()
        return cursor.lastrowid

def excluir_documento_processo(doc_id):
    """Remove um documento da lista de peças do processo."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documentos_processo WHERE id = ?", (doc_id,))
        conn.commit()
        return cursor.rowcount > 0
