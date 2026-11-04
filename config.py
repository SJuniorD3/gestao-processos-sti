import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def load_env(env_path=None):
    """Carrega variáveis do arquivo .env sem precisar de dependências externas."""
    if env_path is None:
        env_path = BASE_DIR / ".env"
    
    if not env_path.exists():
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                os.environ[key] = val

# Carrega .env se existir
load_env()

# Configurações do Servidor
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "0.0.0.0")

# Credenciais de Acesso ao Painel Web
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "STIadmin")

# Banco de Dados (PostgreSQL no Supabase / Nuvem ou SQLite local como fallback)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATABASE_FILE = BASE_DIR / "processos_sti.db"

# Horários de Envio Automático
REPORT_HOURS = [
    int(h.strip()) for h in os.environ.get("REPORT_HOURS", "8,12,16").split(",")
]

# Configurações de Notificação
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # Ex: Webhook para Discord, Telegram, Teams ou WhatsApp

# Credenciais dos Sistemas Oficiais (SEI e STARTGOV) - passadas via .env ou variáveis de ambiente
SEI_URL = os.environ.get(
    "SEI_URL",
    "https://sip.sei.ma.gov.br/sip/login.php?sigla_orgao_sistema=GOVMA&sigla_sistema=SEI&infra_url=L3NlaS8="
)
SEI_USER = os.environ.get("SEI_USER", "")
SEI_PASS = os.environ.get("SEI_PASS", "")

STARTGOV_URL = os.environ.get("STARTGOV_URL", "https://bid.startgov.com.br/login")
STARTGOV_USER = os.environ.get("STARTGOV_USER", "")
STARTGOV_PASS = os.environ.get("STARTGOV_PASS", "")
