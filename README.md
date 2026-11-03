# Sistema de Gestão e Monitoramento de Processos por Projeto - STI (v2.0)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/SJuniorD3/gestao-processos-sti)

Sistema desenvolvido para a **Superintendência de Tecnologia da Informação (STI)** para gerenciar projetos e monitorar múltiplos processos administrativos vinculados (**SEI** e **STARTGOV**), emitindo resumos consolidados **3 vezes ao dia** (pontualmente às **08:00**, **12:00** e **16:00**).

---

## 🌐 Hospedagem Online (Acesso Web por Link)

### Opção 1: Deploy em 1 Clique no Render (Gratuito)
1. Clique no botão acima **"Deploy to Render"** ou acesse [dashboard.render.com](https://dashboard.render.com).
2. Conecte com seu GitHub e selecione o repositório `SJuniorD3/gestao-processos-sti`.
3. O Render detectará automaticamente as configurações do arquivo `render.yaml`.
4. Em menos de 2 minutos seu painel web estará online com link HTTPS próprio (ex: `https://gestao-processos-sti.onrender.com`).

### Opção 2: Deploy com Docker
```bash
docker build -t gestao-processos-sti .
docker run -d -p 8080:8080 gestao-processos-sti
```

---

## 🎯 Arquitetura de Projetos e Processos

* **Um Projeto é uma entidade única** (ex.: `DUARTE JR`, `PROTOCOLO`).
* **Um mesmo Projeto pode conter múltiplos processos vinculados:**
  - Pode ter 1, 2 ou mais processos do **SEI**.
  - Pode ter 1, 2 ou mais processos do **STARTGOV**.
  - Todos os processos ficam agrupados sob o mesmo Projeto e compartilham o mesmo objeto/descrição!
* **Exemplo Real:**
  - 📁 **PROJETO:** `DUARTE JR` *(R$ 2,5 milhões em equipamentos de TI)*
    - ↳ Processo 1: `[SEI] 202.522.010.200.056` (SAOFC/SEDUC - 152 dias)
    - ↳ Processo 2: `[SEI] 202.611.022.016.414` (STI/SEDUC - 87 dias)
    - ↳ Processo 3: `[STARTGOV] SEDUC/00469/2026` (SUMES - 70 dias)

---

## 🖥️ Como Iniciar o Sistema (Versão 2.0)

Dê um duplo clique em qualquer um dos atalhos na sua Área de Trabalho:
👉 **`INICIAR_SISTEMA_STI_V2.bat`** *(Novo atalho da v2.0)*
👉 **`INICIAR_SISTEMA_STI.bat`**

---

## 📋 Recursos da Interface Gráfica (v2.0)

1. **🔗 Acesso Direto aos Processos (Novo na v2.0):**
   - Ao clicar no número do processo na coluna **`Nº PROCESSO (CLIQUE P/ ABRIR)`**, o navegador abre diretamente o portal oficial (**SEI** ou **STARTGOV**).
   - O número do processo é automaticamente copiado para a Área de Transferência (Ctrl+V pronto para uso).
   - Clique com o botão direito no número para abrir um menu com opções rápidas (Pesquisa Pública, histórico, etc.).

2. **📅 Formato de Data Brasileiro (DD/MM/AAAA):**
   - Todas as datas de recebimento, movimentações e histórico são exibidas rigorosamente no formato `dia/mês/ano`.

3. **Visão Hierárquica por Projeto:**
   - A tabela agrupa os processos diretamente abaixo do seu respectivo Projeto.

4. **Vincular Múltiplos Processos a um Projeto:**
   - Adicione facilmente 1 ou mais processos ao mesmo projeto.

5. **Robô de Monitoramento Integrado:**
   - Botão **`🔄 Sincronizar Sistemas`**: acessa o SEI e o STARTGOV com as credenciais cadastradas e atualiza os trâmites, locais e status.

6. **Resumos Diários às 08h, 12h e 16h:**
   - Relatórios consolidados enviados por e-mail (HTML) e Webhook.
