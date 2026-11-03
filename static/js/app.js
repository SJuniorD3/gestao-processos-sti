// Interceptor global para envio de token e redirecionamento caso 401
const _originalFetch = window.fetch;
window.fetch = async function(...args) {
  const token = localStorage.getItem("sti_token");
  if (token) {
    if (!args[1]) args[1] = {};
    if (!args[1].headers) args[1].headers = {};
    if (args[1].headers instanceof Headers) {
      if (!args[1].headers.has("Authorization")) {
        args[1].headers.set("Authorization", "Bearer " + token);
      }
    } else {
      if (!args[1].headers["Authorization"]) {
        args[1].headers["Authorization"] = "Bearer " + token;
      }
    }
  }
  const response = await _originalFetch(...args);
  if (response.status === 401 && !window.location.pathname.includes("login.html")) {
    localStorage.removeItem("sti_token");
    window.location.href = "/login.html";
  }
  return response;
};

let todosProjetos = [];
let todosProcessos = [];

document.addEventListener("DOMContentLoaded", () => {
  carregarDados();
  atualizarStatusAgendador();
  carregarHistoricoDisparos();
  setInterval(atualizarStatusAgendador, 30000);
});

async function carregarDados() {
  try {
    const res = await fetch("/api/projetos");
    const json = await res.json();
    if (json.success) {
      todosProjetos = json.data;
      todosProcessos = [];
      todosProjetos.forEach(pr => {
        (pr.processos || []).forEach(p => todosProcessos.push(p));
      });
      renderizarTabela(todosProjetos);
      atualizarKPIs(todosProjetos, todosProcessos);
    }
  } catch (err) {
    console.error("Erro ao carregar dados:", err);
    document.getElementById("tabelaCorpo").innerHTML = `
      <tr><td colspan="12" class="loading-cell text-danger">Erro de conexão ao carregar os projetos.</td></tr>
    `;
  }
}

function renderizarTabela(listaProjetos) {
  const tbody = document.getElementById("tabelaCorpo");
  if (!listaProjetos || listaProjetos.length === 0) {
    tbody.innerHTML = `<tr><td colspan="12" class="loading-cell">Nenhum projeto cadastrado.</td></tr>`;
    return;
  }

  let htmlTotal = "";

  listaProjetos.forEach(proj => {
    const procs = proj.processos || [];
    const totalP = procs.length;

    if (totalP === 0) {
      // Projeto sem processos cadastrados ainda
      htmlTotal += `
        <tr>
          <td class="cell-projeto" style="font-weight: 800; color: #1e3a8a;">
            📁 ${escapeHtml(proj.nome)}
            <span style="display: block; font-size: 11px; color: #64748b;">(Sem processos)</span>
          </td>
          <td colspan="11" style="color: #94a3b8; font-style: italic;">
            Nenhum processo vinculado a este projeto.
            <button class="btn btn-sm btn-primary" onclick="abrirModalNovoProcessoComProjeto('${escapeHtml(proj.nome)}')">➕ Adicionar Processo</button>
          </td>
        </tr>
      `;
      return;
    }

    procs.forEach((p, idx) => {
      const dias = p.dias_no_setor !== null ? p.dias_no_setor : "-";
      const isMonit = p.monitorar === 1 || p.monitorar === undefined;
      const dataRec = formatarData(p.data_recebimento);

      // CÉLULA MESCLADA DO PROJETO E DA DESCRIÇÃO (SEM CORES, LINHAS FINAS)
      let celulaProjeto = "";
      let celulaDesc = "";
      if (idx === 0) {
        celulaProjeto = `
          <td rowspan="${totalP}" class="cell-projeto" style="vertical-align: top; background: white; font-weight: 700; color: #111827;">
            <div style="cursor: pointer;" onclick="abrirModalEditarProjeto(${proj.id})" title="Clique para editar o projeto">${escapeHtml(proj.nome)}</div>
            <div style="margin-top: 6px; display: flex; gap: 4px; flex-wrap: wrap;">
              <button class="btn btn-sm btn-outline" style="font-size: 11px; color: #374151; border: 1px solid #d1d5db; padding: 1px 5px;" onclick="abrirModalEditarProjeto(${proj.id})">
                ✏️ Editar Projeto
              </button>
              <button class="btn btn-sm btn-outline" style="font-size: 11px; color: #374151; border: 1px solid #d1d5db; padding: 1px 5px;" onclick="abrirModalNovoProcessoComProjeto('${escapeHtml(proj.nome)}')">
                ➕ Add Processo
              </button>
            </div>
          </td>
        `;
        celulaDesc = `
          <td rowspan="${totalP}" class="cell-desc" style="vertical-align: top; background: white; font-size: 12px; color: #374151; cursor: pointer;" onclick="abrirModalEditarProjeto(${proj.id})" title="Clique para editar a descrição do projeto">
            ${escapeHtml(proj.descricao || "-")}
          </td>
        `;
      }

      htmlTotal += `
        <tr>
          ${celulaProjeto}
          <td class="text-center" style="font-weight: 600;">${p.sistema}</td>
          <td style="font-family: monospace; font-weight: 600;">
            <a href="javascript:void(0)" onclick="abrirProcessoExterno('${escapeHtml(p.sistema)}', '${escapeHtml(p.numero_processo)}')" 
               style="color: #2563eb; text-decoration: underline; cursor: pointer;" 
               title="Clique para abrir diretamente no portal ${escapeHtml(p.sistema)}">
              🔗 ${escapeHtml(p.numero_processo)}
            </a>
          </td>
          ${celulaDesc}
          <td>${escapeHtml(p.local_atual || "-")}</td>
          <td>${escapeHtml(p.acao || "-")}</td>
          <td class="text-center">${dataRec}</td>
          <td>${escapeHtml(p.situacao || "-")}</td>
          <td class="text-center" style="font-weight: 600;">${dias}</td>
          <td class="text-center">
            <button class="btn-status-4" onclick="abrirHistoricoProcesso(${p.id})">
              📜 4 Status
            </button>
          </td>
          <td class="text-center">
            <div class="action-btns">
              <button class="btn-icon-action" title="Sincronizar no portal" onclick="sincronizarProcessoWeb(${p.id})">🔄</button>
              <button class="btn-icon-action" title="Editar processo" onclick="abrirModalEditarProcesso(${p.id})">✏️</button>
              <button class="btn-icon-action" title="Excluir processo" onclick="confirmarExclusao(${p.id}, '${escapeHtml(p.numero_processo)}')">🗑️</button>
            </div>
          </td>
        </tr>
      `;
    });
  });

  tbody.innerHTML = htmlTotal;
}

function atualizarKPIs(listaProjetos, listaProcessos) {
  const totalProj = listaProjetos.length;
  const total = listaProcessos.length;
  const sti = listaProcessos.filter(p => p.local_atual.toUpperCase().includes("STI")).length;
  const fora = total - sti;
  const alertas = listaProcessos.filter(p => (p.dias_no_setor || 0) > 60).length;

  if (document.getElementById("kpiProjetos")) document.getElementById("kpiProjetos").textContent = totalProj;
  document.getElementById("kpiTotal").textContent = total;
  document.getElementById("kpiSTI").textContent = sti;
  document.getElementById("kpiFora").textContent = fora;
  document.getElementById("kpiAlerta").textContent = alertas;
}

function filtrarTabela() {
  const texto = document.getElementById("filtroTexto").value.toLowerCase().trim();
  const local = document.getElementById("filtroLocal").value;
  const sistema = document.getElementById("filtroSistema").value;
  const monit = document.getElementById("filtroMonitorar") ? document.getElementById("filtroMonitorar").value : "";

  const filtrados = [];

  todosProjetos.forEach(proj => {
    const procs = (proj.processos || []).filter(p => {
      const matchTexto = !texto || 
        (p.numero_processo && p.numero_processo.toLowerCase().includes(texto)) ||
        (proj.nome && proj.nome.toLowerCase().includes(texto)) ||
        (proj.descricao && proj.descricao.toLowerCase().includes(texto)) ||
        (p.acao && p.acao.toLowerCase().includes(texto)) ||
        (p.situacao && p.situacao.toLowerCase().includes(texto));

      const matchLocal = !local || p.local_atual === local;
      const matchSistema = !sistema || p.sistema.toUpperCase() === sistema.toUpperCase();

      const isMonit = p.monitorar === 1 || p.monitorar === undefined;
      let matchMonit = true;
      if (monit === "1") matchMonit = isMonit;
      else if (monit === "0") matchMonit = !isMonit;

      return matchTexto && matchLocal && matchSistema && matchMonit;
    });

    if (procs.length > 0 || (!texto && !local && !sistema && !monit)) {
      filtrados.push({
        ...proj,
        processos: procs
      });
    }
  });

  renderizarTabela(filtrados);
}

function abrirModalNovoProcessoComProjeto(nomeProj) {
  abrirModalNovoProcesso();
  document.getElementById("formProjeto").value = nomeProj;
  // Busca descrição existente
  for (let pr of todosProjetos) {
    if (pr.nome.toUpperCase() === nomeProj.toUpperCase()) {
      document.getElementById("formDescricao").value = pr.descricao || "";
      break;
    }
  }
}

// -------------------------------------------------------------
// HISTÓRICO: 4 ÚLTIMOS STATUS
// -------------------------------------------------------------
async function abrirHistoricoProcesso(procId) {
  try {
    const res = await fetch(`/api/processos/${procId}`);
    const json = await res.json();
    if (!json.success || !json.data) {
      alert("Não foi possível carregar os detalhes do processo.");
      return;
    }
    const proc = json.data;

    document.getElementById("histProcessoNumero").textContent = `Processo: ${proc.numero_processo} (${proc.sistema})`;
    document.getElementById("histProcessoProjeto").textContent = `Projeto: ${proc.projeto} | Local Atual: ${proc.local_atual} | ${proc.dias_no_setor || 0} dias no setor`;

    const container = document.getElementById("timelineContainer");
    const ultimos4 = proc.ultimos_4_status || [];

    if (ultimos4.length === 0) {
      container.innerHTML = `<p class="empty-text">Nenhuma movimentação anterior registrada.</p>`;
    } else {
      container.innerHTML = ultimos4.map((s, idx) => {
        const dt = formatarDataHora(s.data_movimentacao || s.data_registro);
        const isMaisRecente = idx === 0;
        return `
          <div class="timeline-item ${isMaisRecente ? 'recent' : ''}">
            <div class="timeline-dot"></div>
            <div class="timeline-date">Linha ${idx + 1}: <strong>${dt}</strong> ${isMaisRecente ? '• (Posição Atual)' : ''}</div>
            <div class="timeline-card">
              <div class="timeline-title">
                <span>📍 ${escapeHtml(s.local || 'Não informado')}</span>
              </div>
              <div class="timeline-desc">
                <strong>Situação:</strong> ${escapeHtml(s.situacao || '-')}<br>
                ${s.acao ? `<strong>Ação:</strong> ${escapeHtml(s.acao)}<br>` : ''}
                ${s.observacao ? `<small style="color: #64748b;">${escapeHtml(s.observacao)}</small>` : ''}
              </div>
            </div>
          </div>
        `;
      }).join("");
    }

    document.getElementById("modalHistorico").style.display = "flex";
  } catch (err) {
    console.error("Erro ao abrir histórico:", err);
  }
}

function fecharModalHistorico() {
  document.getElementById("modalHistorico").style.display = "none";
}

// -------------------------------------------------------------
// CADASTRO / EDIÇÃO DE PROCESSO
// -------------------------------------------------------------
function abrirModalNovoProcesso() {
  document.getElementById("formProcessoTitulo").textContent = "Cadastrar Novo Processo para Monitoramento";
  document.getElementById("formProcesso").reset();
  document.getElementById("formProcId").value = "";
  document.getElementById("formDataRecebimento").value = new Date().toISOString().split("T")[0];
  document.getElementById("formMonitorar").checked = true;
  document.getElementById("modalProcesso").style.display = "flex";
}

async function abrirModalEditarProcesso(procId) {
  try {
    const res = await fetch(`/api/processos/${procId}`);
    const json = await res.json();
    if (!json.success || !json.data) return;

    const p = json.data;
    document.getElementById("formProcessoTitulo").textContent = "Editar Processo / Atualizar Trâmite";
    document.getElementById("formProcId").value = p.id;
    document.getElementById("formProjeto").value = p.projeto || "";
    document.getElementById("formSistema").value = p.sistema || "SEI";
    document.getElementById("formNumero").value = p.numero_processo || "";
    document.getElementById("formDescricao").value = p.descricao || "";
    document.getElementById("formLocal").value = p.local_atual || "";
    document.getElementById("formAcao").value = p.acao || "";
    document.getElementById("formSituacao").value = p.situacao || "";
    if (p.data_recebimento) {
      if (/^\d{2}\/\d{2}\/\d{4}$/.test(p.data_recebimento)) {
        const [d, m, a] = p.data_recebimento.split("/");
        document.getElementById("formDataRecebimento").value = `${a}-${m}-${d}`;
      } else {
        document.getElementById("formDataRecebimento").value = p.data_recebimento;
      }
    } else {
      document.getElementById("formDataRecebimento").value = "";
    }
    document.getElementById("formMonitorar").checked = (p.monitorar === 1 || p.monitorar === undefined);

    document.getElementById("modalProcesso").style.display = "flex";
  } catch (err) {
    console.error(err);
  }
}

function fecharModalProcesso() {
  document.getElementById("modalProcesso").style.display = "none";
}

async function salvarProcesso(e) {
  e.preventDefault();
  const id = document.getElementById("formProcId").value;
  const numProc = document.getElementById("formNumero").value.trim();
  if (!numProc) {
    alert("O Número do Processo é obrigatório.");
    return;
  }

  const dados = {
    projeto: document.getElementById("formProjeto").value.trim() || "STI",
    sistema: document.getElementById("formSistema").value.trim() || "SEI",
    numero_processo: numProc,
    descricao: document.getElementById("formDescricao").value.trim(),
    local_atual: document.getElementById("formLocal").value.trim(),
    acao: document.getElementById("formAcao").value.trim(),
    situacao: document.getElementById("formSituacao").value.trim(),
    data_recebimento: document.getElementById("formDataRecebimento").value,
    monitorar: document.getElementById("formMonitorar").checked ? 1 : 0
  };

  try {
    const method = id ? "PUT" : "POST";
    const url = id ? `/api/processos/${id}` : "/api/processos";
    const res = await fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dados)
    });
    const json = await res.json();
    if (json.success) {
      fecharModalProcesso();
      carregarDados();
    } else {
      alert("Erro ao salvar: " + json.error);
    }
  } catch (err) {
    console.error(err);
    alert("Falha na requisição ao servidor.");
  }
}

async function confirmarExclusao(id, numero) {
  if (confirm(`Tem certeza que deseja excluir o processo "${numero}" e todo o seu histórico?`)) {
    try {
      const res = await fetch(`/api/processos/${id}`, { method: "DELETE" });
      const json = await res.json();
      if (json.success) {
        carregarDados();
      } else {
        alert("Erro ao excluir: " + json.error);
      }
    } catch (err) {
      console.error(err);
    }
  }
}

// -------------------------------------------------------------
// AGENDADOR E DISPARO DE RESUMOS (08:00, 12:00, 16:00)
// -------------------------------------------------------------
async function atualizarStatusAgendador() {
  try {
    const res = await fetch("/api/scheduler/info");
    const json = await res.json();
    if (json.success) {
      const data = json.data;
      document.getElementById("proximoDisparoTexto").textContent = `Próximo: ${data.proximo_disparo}`;
    }
  } catch (err) {
    console.error(err);
  }
}

async function dispararResumoAgora() {
  if (!confirm("Deseja gerar e disparar o resumo diário dos processos da STI agora?")) return;
  try {
    const res = await fetch("/api/scheduler/disparar", { method: "POST" });
    const json = await res.json();
    if (json.success) {
      alert("✓ Resumo gerado com sucesso!\n\nStatus: " + json.data.status);
      atualizarStatusAgendador();
      carregarHistoricoDisparos();
    } else {
      alert("Erro ao disparar resumo: " + json.error);
    }
  } catch (err) {
    console.error(err);
    alert("Erro ao comunicar com o agendador.");
  }
}

async function verPreviewRelatorio() {
  try {
    const res = await fetch("/api/relatorios/preview");
    const json = await res.json();
    if (json.success) {
      document.getElementById("previewHtmlContainer").innerHTML = json.data.html;
      document.getElementById("modalPreview").style.display = "flex";
    }
  } catch (err) {
    console.error(err);
  }
}

function fecharModalPreview() {
  document.getElementById("modalPreview").style.display = "none";
}

async function carregarHistoricoDisparos() {
  try {
    const res = await fetch("/api/relatorios/ultimos");
    const json = await res.json();
    if (json.success && json.data) {
      const container = document.getElementById("listaLogsDisparos");
      if (json.data.length === 0) {
        container.innerHTML = `<p class="empty-text">Nenhum disparo anterior registrado.</p>`;
        return;
      }
      container.innerHTML = json.data.map(log => `
        <div class="log-item">
          <div>
            <span class="log-time">${log.data_hora}</span>
            <span class="log-type">${log.tipo}</span>
            <span>• ${log.total_processos} processos listados</span>
          </div>
          <span class="log-status">${escapeHtml(log.status)}</span>
        </div>
      `).join("");
    }
  } catch (err) {
    console.error(err);
  }
}

async function sincronizarSistemasWeb() {
  if (!confirm("Deseja iniciar o robô de monitoramento e consultar todos os processos cadastrados no SEI e STARTGOV agora?")) return;
  try {
    const res = await fetch("/api/monitoramento/executar", { method: "POST" });
    const json = await res.json();
    if (json.success) {
      alert(`✓ Sincronização concluída!\n\nProcessos verificados: ${json.data.total_verificados}\nAtualizados: ${json.data.total_atualizados}`);
      carregarDados();
    } else {
      alert("Erro na sincronização: " + json.error);
    }
  } catch (err) {
    console.error(err);
    alert("Falha ao comunicar com o servidor.");
  }
}

async function sincronizarProcessoWeb(id) {
  try {
    const res = await fetch(`/api/monitoramento/processo/${id}`, { method: "POST" });
    const json = await res.json();
    if (json.sucesso) {
      alert("✓ Processo sincronizado com sucesso via portal oficial!");
      carregarDados();
    } else {
      alert("Aviso do portal: " + (json.mensagem || "Não foi possível sincronizar"));
    }
  } catch (err) {
    console.error(err);
    alert("Erro ao sincronizar processo.");
  }
}

// -------------------------------------------------------------
// GESTÃO E EDIÇÃO DE PROJETOS
// -------------------------------------------------------------
function abrirModalEditarProjeto(projId) {
  let proj = null;
  if (!projId && todosProjetos.length > 0) {
    proj = todosProjetos[0];
  } else if (projId) {
    proj = todosProjetos.find(p => p.id === projId);
  }

  if (!proj) {
    alert("Nenhum projeto encontrado para edição.");
    return;
  }

  document.getElementById("editProjetoId").value = proj.id;
  document.getElementById("editProjetoNome").value = proj.nome || "";
  document.getElementById("editProjetoDescricao").value = proj.descricao || "";
  document.getElementById("modalProjetoTitle").textContent = `Editar Projeto: ${proj.nome}`;

  const numProcs = (proj.processos || []).length;
  document.getElementById("editProjetoProcessosInfo").textContent =
    `ℹ️ Este projeto possui ${numProcs} processo(s) vinculado(s).`;

  document.getElementById("modalEditarProjeto").style.display = "flex";
}

function fecharModalProjeto() {
  document.getElementById("modalEditarProjeto").style.display = "none";
}

async function salvarProjeto(e) {
  e.preventDefault();
  const projId = document.getElementById("editProjetoId").value;
  const nome = document.getElementById("editProjetoNome").value.trim();
  const descricao = document.getElementById("editProjetoDescricao").value.trim();

  if (!nome) {
    alert("O nome do projeto é obrigatório.");
    return;
  }

  try {
    const res = await fetch(`/api/projetos/${projId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome, descricao })
    });
    const json = await res.json();
    if (json.success) {
      fecharModalProjeto();
      carregarProjetos();
    } else {
      alert("Erro ao salvar projeto: " + json.error);
    }
  } catch (err) {
    console.error(err);
    alert("Erro na requisição ao salvar projeto.");
  }
}

async function excluirProjetoAtual() {
  const projId = document.getElementById("editProjetoId").value;
  const nome = document.getElementById("editProjetoNome").value;

  if (!confirm(`Tem certeza que deseja excluir o projeto "${nome}"?\n\nATENÇÃO: Todos os processos vinculados a ele também serão excluídos!`)) {
    return;
  }

  try {
    const res = await fetch(`/api/projetos/${projId}`, {
      method: "DELETE"
    });
    const json = await res.json();
    if (json.success) {
      fecharModalProjeto();
      carregarProjetos();
    } else {
      alert("Erro ao excluir projeto: " + json.error);
    }
  } catch (err) {
    console.error(err);
    alert("Erro na requisição ao excluir projeto.");
  }
}

// -------------------------------------------------------------
// SISTEMAS E EXPORTAÇÃO
// -------------------------------------------------------------
function abrirModalSistemas() {
  document.getElementById("modalSistemas").style.display = "flex";
}

function fecharModalSistemas() {
  document.getElementById("modalSistemas").style.display = "none";
}

function exportarCSV() {
  window.location.href = "/api/export/csv";
}

// -------------------------------------------------------------
// AUXILIARES
// -------------------------------------------------------------
function formatarData(dataStr) {
  if (!dataStr || dataStr === "-") return "-";
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(dataStr)) return dataStr;
  const partes = dataStr.split(" ")[0].split("-");
  if (partes.length === 3) {
    return `${partes[2]}/${partes[1]}/${partes[0]}`;
  }
  return dataStr;
}

function formatarDataHora(dtStr) {
  if (!dtStr || dtStr === "-") return "-";
  const m = dtStr.match(/^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?/);
  if (m) {
    const [, a, m_mes, d, hora] = m;
    return hora ? `${d}/${m_mes}/${a} ${hora.slice(0, 5)}` : `${d}/${m_mes}/${a}`;
  }
  return dtStr;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function abrirProcessoExterno(sistema, numero) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(numero).catch(() => {});
  }
  let url = "https://sei.ma.gov.br/sei/controlador.php?acao=procedimento_controlar";
  if (sistema && sistema.toUpperCase().includes("STARTGOV")) {
    url = `https://bid.startgov.com.br/processos?type=all&search=${encodeURIComponent(numero)}`;
  }
  window.open(url, "_blank");
}

async function fazerLogout() {
  if (!confirm("Deseja realmente sair do painel STI?")) return;
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (e) {}
  localStorage.removeItem("sti_token");
  window.location.href = "/login.html";
}
