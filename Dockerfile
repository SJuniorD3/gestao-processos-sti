# ==============================================================================
# Dockerfile - Sistema de Gestão e Monitoramento de Processos STI (SEDUC-MA)
# Padrão Corporativo para Implantação em Ambientes de Data Center / ATI
# ==============================================================================

FROM python:3.11-slim

# Metadados e variáveis de ambiente do sistema operacional
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Fortaleza \
    HOST=0.0.0.0 \
    PORT=8080 \
    DATABASE_FILE=/app/data/processos_sti.db

WORKDIR /app

# Instala pacotes do sistema:
# - tzdata: garante o fuso horário oficial UTC-3 (Maranhão / Brasília) para agendamentos e logs
# - ca-certificates: certificados raiz atualizados para conexões TLS seguras com SEI e StartGov
# - curl: utilizado pelo HEALTHCHECK nativo do container
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
    curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Cria usuário sem privilégios de root para conformidade de segurança corporativa
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Cria o diretório de dados persistentes para banco SQLite e define permissões
RUN mkdir -p /app/data && \
    chown -R appuser:appgroup /app

# Altera para o usuário seguro não-root
USER appuser

# Expõe a porta de serviço HTTP
EXPOSE 8080

# Sonda de integridade (Healthcheck) compatível com Docker, Swarm e Kubernetes
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Comando de inicialização do servidor e agendador
CMD ["python", "run.py"]
