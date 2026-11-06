# Sistema de Gestão e Monitoramento de Processos por Projeto - STI (v3.0 - Homologação)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/SJuniorD3/gestao-processos-sti)

Sistema corporativo da **Superintendência de Tecnologia da Informação (STI)** da **Secretaria de Estado da Educação do Maranhão (SEDUC-MA)** para gerenciamento de projetos estratégicos, acompanhamento de múltiplos processos administrativos vinculados (**SEI** e **STARTGOV**), governança por setores da SEDUC e emissão automatizada de resumos executivos pontualmente às **08:00**, **12:00** e **16:00**.

---

## 🚀 Principais Funcionalidades da Versão 3.0

1. **🏢 Governança Multi-Setorial (SEDUC-MA):**
   - Suporte completo ao cadastro de setores da SEDUC (`STI`, `SAOFC`, `ASJUR`, `GAB`, `CPL`, `DA`, `SGP`, `SEDUC`, etc.).
   - Projetos vinculados ao setor responsável.
   - **Controle de Visualização por Perfil:** Usuários operadores visualizam os projetos do seu respectivo setor; o perfil **`admin`** possui visão corporativa global de todos os setores e projetos cadastrados.

2. **🏷️ Categorização por Etiquetas de Projeto:**
   - Classificação ágil de projetos em **`Contratos`** ou **`Pagamentos`**.
   - Filtros dinâmicos na interface e relatórios com totalização por etiqueta e setor.

3. **⚡ Cadastro Simplificado e Inteligente de Processos:**
   - **Fim do preenchimento manual desnecessário:** não é mais necessário digitar local/setor atual, data de recebimento, situação e providência no formulário de cadastro.
   - Basta selecionar o projeto e informar os números oficiais (**SEI** e/ou **STARTGOV**). Os robôs de integração realizam a captura imediata e sincronizam todos os dados oficiais automaticamente.
   - Inclusão contextualizada com o botão **`➕ Adicionar Processo`** na linha de cada projeto da grid.

4. **⚙️ Menu Administrativo Unificado (5 Pilares):**
   - **👥 Cadastro & Gestão de Usuários:** Criação, edição de perfis (`admin`, `operador`, `leitor`), redefinição de senhas e vínculo obrigatório com o setor SEDUC.
   - **🏢 Setores da SEDUC:** Manutenção de siglas, nomes completos e status de ativação dos setores do órgão.
   - **📡 Canais de Disparo:** Configuração dinâmica de servidor SMTP (servidor, porta, usuário, senha, e-mails de destino) e Webhook com botão de envio de teste em tempo real.
   - **🔑 Portais Oficiais & Robôs:** Status de credenciais do SEI e STARTGOV com ferramenta de **Diagnóstico de Conectividade dos Robôs** em 1 clique.
   - **📜 Trilha de Auditoria:** Registro cronológico de todas as operações sensíveis (usuário, ação, IP e data/hora).

5. **📊 Central de Relatórios Executivos & Operacionais:**
   - Relatórios executivos consolidados, relatórios de gargalos e análise de SLA.
   - Totalmente compatíveis com a divisão por setores e etiquetas de projetos.
   - Exportação para Excel/CSV com codificação brasileira (`utf-8-sig` e delimitador `;`).

6. **💾 Suporte Dual Database (SQLite & PostgreSQL / Supabase):**
   - Compatibilidade automática com banco de dados local **SQLite** (`processos_sti.db`) para desenvolvimento/desktop.
   - Suporte nativo a **PostgreSQL na nuvem (Supabase / Neon / Render)** via variável `DATABASE_URL`, com migrações automáticas idempotentes.

---

## 🎯 Arquitetura de Projetos e Processos

* **Um Projeto é uma entidade única** (ex.: `DUARTE JR`, `PROTOCOLO`, `ADESÃO CHROMEBOOK`).
* **Etiqueta do Projeto:** Define a natureza da demanda (`Contratos` ou `Pagamentos`).
* **Setor Responsável:** Sigla do setor da SEDUC (`STI`, `SAOFC`, etc.).
* **Múltiplos Processos Vinculados (1:N):**
  - Cada projeto pode agrupar 1 ou mais processos do **SEI**.
  - Cada projeto pode agrupar 1 ou mais processos do **STARTGOV**.
  - Todos os processos herdam o objeto e o setor do projeto mantendo rastreabilidade total.

---

## 🌐 Hospedagem Online e Deploy Web

### Opção 1: Deploy em 1 Clique no Render
1. Conecte com seu repositório GitHub `SJuniorD3/gestao-processos-sti`.
2. Configure a variável `DATABASE_URL` com sua connection string do Supabase (ou utilize o SQLite local).
3. O Render utilizará automaticamente o `render.yaml` e a aplicação estará no ar com HTTPS em menos de 2 minutos.

### Opção 2: Deploy via Docker
```bash
docker build -t gestao-processos-sti .
docker run -d -p 8080:8080 -e PORT=8080 gestao-processos-sti
```

---

## 🖥️ Execução Local

### 1. Criar e Ativar Ambiente Virtual
```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou no Windows: .venv\Scripts\activate
```

### 2. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar Variáveis de Ambiente
Copie `.env.example` para `.env` e ajuste suas credenciais:
```ini
PORT=8080
HOST=127.0.0.1
ADMIN_USER=admin
ADMIN_PASS=STIadmin
REPORT_HOURS=8,12,16
```

### 4. Iniciar Servidor
```bash
python run.py
```
Acesse no seu navegador: `http://localhost:8080` (ou o IP do servidor na rede local).

---

## ⏰ Horários de Disparos Automáticos

O agendador integrado (`scheduler.py`) monitora os portais e dispara relatórios executivos 3 vezes ao dia:
* 🌅 **08:00** — Abertura do expediente matutino.
* ☀️ **12:00** — Fechamento do turno da manhã.
* 🌆 **16:00** — Fechamento do expediente vespertino.
