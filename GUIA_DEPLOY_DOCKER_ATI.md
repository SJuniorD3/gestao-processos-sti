# Guia de Implantação em Docker para o Ambiente da ATI (SEDUC-MA)

**Sistema:** Sistema de Gestão e Monitoramento de Processos por Projeto - STI  
**Versão:** v3.0 - Homologação  
**Público-Alvo:** Equipe de Infraestrutura, Operações e DevOps da **ATI** e **SEDUC-MA**  

---

## 1. Visão Geral da Arquitetura em Container

O sistema foi containerizado seguindo as melhores práticas de engenharia de software e segurança corporativa governamental:

* **Imagem Base Leve e Segura:** Construída a partir de `python:3.11-slim` com pacotes mínimos necessários.
* **Execução Não-Root:** O processo roda sob o usuário sem privilégios `appuser` (UID 1001), atendendo aos padrões de conformidade e *CIS Benchmark*.
* **Fuso Horário Oficial (Timezone):** Configurado explicitamente para `America/Fortaleza` (UTC-3), garantindo que os agendamentos pontuais (08:00, 12:00 e 16:00), datas de trâmite e logs reflitam exatamente a hora local do Maranhão.
* **Sonda de Integridade Nativa (Healthcheck):** Endpoint `/api/health` para monitoramento automático de *liveness/readiness* no Docker, Swarm, Kubernetes ou Rancher.
* **Persistência de Dados e Volumes:** Dados persistidos em volume nomeado Docker (`sti_processos_data`), imune a recriações de containers ou reinicializações do servidor.

---

## 2. Requisitos de Infraestrutura

* **Sistema Operacional:** Linux (RHEL, Rocky Linux, Debian, Ubuntu Server).
* **Docker Engine:** Versão `20.10.x` ou superior.
* **Docker Compose:** Plugin Compose v2 (`docker compose`) ou v1.29+.
* **Recursos Mínimos Recomendados por Container:**
  - CPU: 0.5 core (limite configurado até 1.5 cores no Compose).
  - Memória RAM: 512 MB (limite configurado até 1 GB no Compose).
  - Disco: 5 GB disponíveis para imagens, logs e dados.
* **Portas de Rede:**
  - Porta `8080` (interna do container). Pode ser mapeada para `8080`, `80` ou proxy reverso interno.
* **Acessos Externos de Saída (HTTPS Porta 443):**
  - `sip.sei.ma.gov.br` / `sei.ma.gov.br` (Portal SEI Maranhão).
  - `bid.startgov.com.br` (Portal StartGov de Licitações).
  - Servidor SMTP de e-mail (caso o envio por e-mail seja habilitado).

---

## 3. Modos de Banco de Dados Suportados

O sistema opera de forma transparente em dois cenários:

### Cenário A: SQLite Integrado com Volume Persistente (Padrão / Pronto de Fábrica)
* Não requer banco de dados externo ou servidor adicional.
* O arquivo do banco é mantido em `/app/data/processos_sti.db` no volume nomeado `sti_processos_data`.
* Ideal para implantação imediata com manutenção simplificada.

### Cenário B: PostgreSQL Corporativo da ATI ou Supabase
* Conecta a um banco PostgreSQL já existente na infraestrutura da ATI/SEDUC.
* Basta definir a variável de ambiente no `.env`:
  ```ini
  DATABASE_URL=postgresql://usuario:senha@pg-servidor.ati.ma.gov.br:5432/sti_processos
  ```
* O sistema cria as tabelas e migrações automaticamente no primeiro boot.

---

## 4. Passo a Passo de Instalação e Subida

### Passo 1: Obter o Código do Repositório
```bash
git clone -b v3.0-homologacao https://github.com/SJuniorD3/gestao-processos-sti.git /opt/gestao-processos-sti
cd /opt/gestao-processos-sti
```

### Passo 2: Configurar o Arquivo de Ambiente (.env)
Copie o modelo `.env.example` para `.env`:
```bash
cp .env.example .env
```
Edite as variáveis principais:
```ini
PORT=8080
HOST=0.0.0.0
ADMIN_USER=admin
ADMIN_PASS=SenhaForteAdminSTI2026!

# Credenciais de integração com os robôs
SEI_USER=cpf_ou_login_orgao
SEI_PASS=senha_oficial_sei
STARTGOV_USER=cpf_ou_login_startgov
STARTGOV_PASS=senha_oficial_startgov

# Se utilizar banco PostgreSQL da ATI:
# DATABASE_URL=postgresql://usuario:senha@host:5432/nome_banco
```

### Passo 3: Construir e Iniciar os Containers
```bash
docker compose up -d --build
```

### Passo 4: Verificar a Saúde do Serviço
```bash
# Verificar status do container e healthcheck
docker compose ps

# Testar o endpoint de saúde
curl -i http://localhost:8080/api/health
```
Resposta esperada (HTTP 200 OK):
```json
{
  "status": "healthy",
  "version": "3.0-homologacao",
  "database": {
    "status": "connected",
    "engine": "sqlite"
  },
  "timestamp": "2026-11-06T12:00:00.000000"
}
```

---

## 5. Exemplo de Configuração de Proxy Reverso (Nginx com SSL)

Recomendamos posicionar o container atrás de um proxy reverso padrão da ATI com certificado institucional (`*.ma.gov.br`):

```nginx
server {
    listen 80;
    server_name processos-sti.seduc.ma.gov.br;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name processos-sti.seduc.ma.gov.br;

    ssl_certificate /etc/ssl/certs/seduc_ma_gov_br.crt;
    ssl_certificate_key /etc/ssl/private/seduc_ma_gov_br.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Suporte a WebSockets / SSE se necessário
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 6. Procedimentos de Manutenção e Operação

### Ver Logs em Tempo Real
```bash
docker compose logs -f --tail=100
```

### Backup Rápido do Banco SQLite (em caso de uso do Cenário A)
```bash
docker compose exec gestao-processos-sti sqlite3 /app/data/processos_sti.db ".backup '/app/data/backup_processos_$(date +%Y%m%d_%H%M%S).db'"
```

### Atualização para Novas Versões
```bash
cd /opt/gestao-processos-sti
git pull origin v3.0-homologacao
docker compose up -d --build
```
Como os dados residem no volume `sti_data_volume` (ou banco PostgreSQL externo), a atualização é 100% segura e não gera perda de dados.
