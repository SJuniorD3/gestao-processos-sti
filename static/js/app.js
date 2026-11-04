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
let modoVisualizacaoAtual = "tabela";
let projetosFiltradosCache = [];

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
      const locaisSet = new Set();

      todosProjetos.forEach(pr => {
        (pr.processos || []).forEach(p => {
          todosProcessos.push(p);
          if (p.local_atual && p.local_atual.trim()) {
            locaisSet.add(p.local_atual.trim());
          }
        });
      });

      popularSelectLocais(Array.from(locaisSet).sort());
      popularSelectProjetos(todosProjetos);
      projetosFiltradosCache = todosProjetos;
      renderizarTabela(todosProjetos);
      renderizarTimelineVisual(todosProjetos);
      atualizarKPIs(todosProjetos, todosProcessos);
    }
  } catch (err) {
    console.error("Erro ao carregar dados:", err);
    document.getElementById("tabelaCorpo").innerHTML = `
      <tr><td colspan="12" class="loading-cell text-danger">Erro de conexão ao carregar os projetos.</td></tr>
    `;
  }
}

function popularSelectLocais(locais) {
  const sel = document.getElementById("filtroLocal");
  if (!sel) return;
  const valorAtual = sel.value;
  sel.innerHTML = '<option value="">Todos os Locais</option>';
  locais.forEach(loc => {
    const opt = document.createElement("option");
    opt.value = loc;
    opt.textContent = loc;
    if (loc === valorAtual) opt.selected = true;
    sel.appendChild(opt);
  });
}

function popularSelectProjetos(projetos) {
  const datalist = document.getElementById("listaProjetosDatalist");
  if (datalist) {
    datalist.innerHTML = projetos.map(p => `<option value="${escapeHtml(p.nome)}">`).join("");
  }
  const select = document.getElementById("editProjSelect");
  if (select) {
    select.innerHTML = '<option value="">-- Selecione um projeto para editar --</option>' +
      projetos.map(p => `<option value="${p.id}">${escapeHtml(p.nome)} (${(p.processos || []).length} processos)</option>`).join("");
  }
}

function alternarModoVisualizacao(modo) {
  modoVisualizacaoAtual = modo;
  const containerTabela = document.getElementById("containerTabela");
  const containerTimeline = document.getElementById("containerTimeline");
  const btnTabela = document.getElementById("btnModoTabela");
  const btnTimeline = document.getElementById("btnModoTimeline");

  if (modo === "timeline") {
    containerTabela.style.display = "none";
    containerTimeline.style.display = "flex";
    btnTimeline.classList.add("active");
    btnTabela.classList.remove("active");
  } else {
    containerTabela.style.display = "block";
    containerTimeline.style.display = "none";
    btnTabela.classList.add("active");
    btnTimeline.classList.remove("active");
  }
}

function renderizarTabela(listaProjetos) {
  const tbody = document.getElementById("tabelaCorpo");
  if (!listaProjetos || listaProjetos.length === 0) {
    tbody.innerHTML = `<tr><td colspan="11" class="loading-cell">Nenhum projeto cadastrado.</td></tr>`;
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
          <td colspan="10" style="color: #94a3b8; font-style: italic;">
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
  const diasFiltro = document.getElementById("filtroDias") ? document.getElementById("filtroDias").value : "";
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

      // Filtro por Faixa de Dias (SLA)
      let matchDias = true;
      const dias = typeof p.dias_no_setor === "number" ? p.dias_no_setor : 0;
      if (diasFiltro === "ate_30") matchDias = dias <= 30;
      else if (diasFiltro === "31_60") matchDias = dias > 30 && dias <= 60;
      else if (diasFiltro === "mais_60") matchDias = dias > 60;

      const isMonit = p.monitorar === 1 || p.monitorar === undefined;
      let matchMonit = true;
      if (monit === "1") matchMonit = isMonit;
      else if (monit === "0") matchMonit = !isMonit;

      return matchTexto && matchLocal && matchSistema && matchDias && matchMonit;
    });

    if (procs.length > 0 || (!texto && !local && !sistema && !diasFiltro && !monit)) {
      filtrados.push({
        ...proj,
        processos: procs
      });
    }
  });

  projetosFiltradosCache = filtrados;
  renderizarTabela(filtrados);
  renderizarTimelineVisual(filtrados);
}

function limparFiltrosV3() {
  if (document.getElementById("filtroTexto")) document.getElementById("filtroTexto").value = "";
  if (document.getElementById("filtroLocal")) document.getElementById("filtroLocal").value = "";
  if (document.getElementById("filtroSistema")) document.getElementById("filtroSistema").value = "";
  if (document.getElementById("filtroDias")) document.getElementById("filtroDias").value = "";
  if (document.getElementById("filtroMonitorar")) document.getElementById("filtroMonitorar").value = "1";
  filtrarTabela();
}

function obterIconeStatus(texto) {
  if (!texto) return "📄";
  const t = texto.toLowerCase();
  if (t.includes("parecer") || t.includes("jurídic") || t.includes("asjur")) return "⚖️";
  if (t.includes("despacho") || t.includes("assinad") || t.includes("autoriz") || t.includes("gab")) return "✍️";
  if (t.includes("licita") || t.includes("cota") || t.includes("pregão") || t.includes("edital") || t.includes("cpl")) return "🏷️";
  if (t.includes("empenh") || t.includes("pagament") || t.includes("financeir") || t.includes("saofc")) return "💰";
  if (t.includes("conclu") || t.includes("finaliz") || t.includes("homolog")) return "🏁";
  if (t.includes("recebid") || t.includes("chegad") || t.includes("autuad")) return "📥";
  return "🔄";
}

function renderizarTimelineVisual(listaProjetos) {
  const container = document.getElementById("containerTimeline");
  if (!container) return;

  if (!listaProjetos || listaProjetos.length === 0) {
    container.innerHTML = `
      <div style="background: white; padding: 40px; text-align: center; border-radius: 14px; border: 1px dashed #cbd5e1; color: #64748b;">
        <span style="font-size: 36px; display: block; margin-bottom: 8px;">🔍</span>
        <strong style="color: #0f172a; font-size: 14px;">Nenhum projeto ou processo encontrado com os filtros selecionados.</strong>
        <p style="font-size: 12px; margin-top: 4px;">Tente redefinir os filtros para visualizar os dados.</p>
        <button class="btn btn-primary" style="margin-top: 14px; font-size: 12px;" onclick="limparFiltrosV3()">Redefinir Filtros</button>
      </div>
    `;
    return;
  }

  let htmlTotal = "";

  listaProjetos.forEach(proj => {
    const procs = proj.processos || [];
    if (procs.length === 0) return;

    // Verifica se algum processo tem alerta crítico
    const temCritico = procs.some(p => (p.dias_no_setor || 0) > 60);

    htmlTotal += `
      <div class="project-card">
        <div class="project-card-header">
          <div>
            <div class="project-title">
              <span>📁 ${escapeHtml(proj.nome)}</span>
              <span style="background: rgba(255,255,255,0.15); font-size: 11px; padding: 2px 8px; border-radius: 9999px; font-weight: 500;">
                ${procs.length} processo(s)
              </span>
              ${temCritico ? '<span style="background: rgba(239,68,68,0.25); color: #fca5a5; font-size: 11px; padding: 2px 8px; border-radius: 6px; font-weight: 600; border: 1px solid rgba(239,68,68,0.4);">⚠️ Alerta Crítico</span>' : ''}
            </div>
            <div class="project-desc">${escapeHtml(proj.descricao || "Sem descrição cadastrada")}</div>
          </div>
          <div style="display: flex; gap: 6px;">
            <button class="btn btn-sm btn-outline" style="border-color: rgba(255,255,255,0.3); color: white;" onclick="abrirModalNovoProcessoComProjeto('${escapeHtml(proj.nome)}')">
              ➕ Add Processo
            </button>
            <button class="btn btn-sm btn-outline" style="border-color: rgba(255,255,255,0.3); color: white;" onclick="abrirModalEditarProjeto(${proj.id})">
              ✏️ Editar
            </button>
          </div>
        </div>
        <div>
    `;

    procs.forEach(p => {
      const dias = p.dias_no_setor !== null ? p.dias_no_setor : "-";
      let badgeSla = "";
      if (typeof dias === "number") {
        if (dias > 60) {
          badgeSla = `<span class="badge-sla-critico">⚠️ ${dias} dias no setor (Crítico)</span>`;
        } else if (dias > 30) {
          badgeSla = `<span class="badge-sla-atencao">⏳ ${dias} dias no setor (Atenção)</span>`;
        } else {
          badgeSla = `<span class="badge-sla-ok">✓ ${dias} dias no setor</span>`;
        }
      } else {
        badgeSla = `<span class="badge-sla-ok">- dias</span>`;
      }

      const tagSistema = (p.sistema && p.sistema.toUpperCase().includes("STARTGOV"))
        ? `<span class="badge-tag-start">STARTGOV</span>`
        : `<span class="badge-tag-sei">SEI</span>`;

      // Monta os andamentos da Timeline
      const ultimos = p.ultimos_4_status || [];
      let timelineItemsHtml = "";

      if (ultimos.length > 0) {
        ultimos.forEach((st, sIdx) => {
          const isAtual = sIdx === 0;
          const bulletCls = isAtual ? "timeline-bullet current" : "timeline-bullet";
          const contentCls = isAtual ? "timeline-content current" : "timeline-content";
          const dataFormatada = st.data_movimentacao || formatarData(st.data_registro) || "-";
          const icone = isAtual ? "📍" : obterIconeStatus((st.situacao || "") + " " + (st.acao || "") + " " + (st.local || ""));

          timelineItemsHtml += `
            <div class="timeline-item">
              <div class="${bulletCls}">${icone}</div>
              <div class="${contentCls}">
                <div class="timeline-content-header">
                  <div>
                    <strong style="color: ${isAtual ? '#1e3a8a' : '#1e293b'}; font-weight: 700;">
                      ${escapeHtml(st.local || p.local_atual || "-")}
                    </strong>
                    ${isAtual ? '<span style="background: #2563eb; color: white; font-size: 10px; font-weight: 800; padding: 2px 7px; border-radius: 4px; margin-left: 6px; text-transform: uppercase;">Posição Atual</span>' : ''}
                  </div>
                  <span style="font-family: monospace; color: #64748b; font-size: 11px;">
                    ${escapeHtml(dataFormatada)}
                  </span>
                </div>
                <div style="color: #334155; line-height: 1.45;">
                  ${escapeHtml(st.situacao || p.situacao || "-")}
                  ${st.acao ? ` <span style="color: #64748b;">(Ação: ${escapeHtml(st.acao)})</span>` : ''}
                </div>
              </div>
            </div>
          `;
        });
      } else {
        timelineItemsHtml = `
          <div class="timeline-item">
            <div class="timeline-bullet current">📍</div>
            <div class="timeline-content current">
              <div class="timeline-content-header">
                <div>
                  <strong style="color: #1e3a8a; font-weight: 700;">${escapeHtml(p.local_atual || "-")}</strong>
                  <span style="background: #2563eb; color: white; font-size: 10px; font-weight: 800; padding: 2px 7px; border-radius: 4px; margin-left: 6px; text-transform: uppercase;">Posição Atual</span>
                </div>
                <span style="font-family: monospace; color: #64748b; font-size: 11px;">${formatarData(p.data_recebimento)}</span>
              </div>
              <div style="color: #334155;">${escapeHtml(p.situacao || "Em tramitação")} - ${escapeHtml(p.acao || "")}</div>
            </div>
          </div>
        `;
      }

      htmlTotal += `
        <div class="process-card-item">
          <div class="process-header-bar">
            <div class="process-identifier">
              ${tagSistema}
              <a href="javascript:void(0)" onclick="abrirProcessoExterno('${escapeHtml(p.sistema)}', '${escapeHtml(p.numero_processo)}')"
                 style="font-family: monospace; font-weight: 700; font-size: 14px; color: #1d4ed8; text-decoration: underline;"
                 title="Clique para abrir diretamente no portal oficial">
                🔗 ${escapeHtml(p.numero_processo)}
              </a>
              <button class="btn btn-sm btn-secondary" style="padding: 2px 7px; font-size: 11px;" title="Copiar número" onclick="copiarNumeroProcesso('${escapeHtml(p.numero_processo)}')">
                📋 Copiar
              </button>
              <span style="color: #cbd5e1;">•</span>
              <span style="font-size: 13px; color: #475569;">
                Setor Atual: <strong style="color: #0f172a;">${escapeHtml(p.local_atual || "-")}</strong>
              </span>
            </div>

            <div style="display: flex; align-items: center; gap: 8px;">
              ${badgeSla}
              <button class="btn-icon-action" title="Sincronizar no portal" onclick="sincronizarProcessoWeb(${p.id})">🔄</button>
              <button class="btn-icon-action" title="Editar processo" onclick="abrirModalEditarProcesso(${p.id})">✏️</button>
              <button class="btn-icon-action" title="Excluir processo" onclick="confirmarExclusao(${p.id}, '${escapeHtml(p.numero_processo)}')">🗑️</button>
            </div>
          </div>

          <!-- LINHA DO TEMPO VISUAL -->
          <div class="timeline-track">
            <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; margin-bottom: 2px; display: flex; align-items: center; gap: 5px;">
              <span>⏱️ Trilha de Tramitação do Processo</span>
            </div>
            ${timelineItemsHtml}
          </div>
        </div>
      `;
    });

    htmlTotal += `
        </div>
      </div>
    `;
  });

  container.innerHTML = htmlTotal;
}

function copiarNumeroProcesso(num) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(num).catch(() => {});
  }
  exibirToast(`✓ Processo ${num} copiado para a área de transferência!`);
}

function exibirToast(msg) {
  let toast = document.getElementById("toastNotification");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toastNotification";
    toast.style.cssText = "position: fixed; bottom: 24px; right: 24px; background: #0f172a; color: white; padding: 12px 20px; border-radius: 12px; font-size: 13px; font-weight: 600; box-shadow: 0 10px 20px -3px rgba(0,0,0,0.3); z-index: 9999; display: flex; align-items: center; gap: 8px; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); transform: translateY(50px); opacity: 0; pointer-events: none;";
    document.body.appendChild(toast);
  }
  toast.innerText = msg;
  toast.style.transform = "translateY(0)";
  toast.style.opacity = "1";
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => {
    toast.style.transform = "translateY(50px)";
    toast.style.opacity = "0";
  }, 2500);
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
  const tituloEl = document.getElementById("modalProcessoTitulo");
  if (tituloEl) tituloEl.textContent = "Cadastrar Novo Processo";
  document.getElementById("formProcesso").reset();
  document.getElementById("formProcId").value = "";
  const dtEl = document.getElementById("formDataRec");
  if (dtEl) dtEl.value = new Date().toISOString().split("T")[0];
  const monEl = document.getElementById("formMonitorar");
  if (monEl) monEl.checked = true;
  document.getElementById("modalProcesso").style.display = "flex";
}

async function abrirModalEditarProcesso(procId) {
  try {
    const res = await fetch(`/api/processos/${procId}`);
    const json = await res.json();
    if (!json.success || !json.data) return;

    const p = json.data;
    const tituloEl = document.getElementById("modalProcessoTitulo");
    if (tituloEl) tituloEl.textContent = "Editar Processo " + (p.numero_processo || "");
    document.getElementById("formProcId").value = p.id;
    document.getElementById("formProjeto").value = p.projeto || "";
    document.getElementById("formSistema").value = p.sistema || "SEI";
    document.getElementById("formNumero").value = p.numero_processo || "";
    document.getElementById("formDescricao").value = p.descricao || "";
    document.getElementById("formLocal").value = p.local_atual || "";
    document.getElementById("formAcao").value = p.acao || "";
    document.getElementById("formSituacao").value = p.situacao || "";
    
    const dtEl = document.getElementById("formDataRec");
    if (dtEl) {
      if (p.data_recebimento) {
        if (/^\d{2}\/\d{2}\/\d{4}$/.test(p.data_recebimento)) {
          const [d, m, a] = p.data_recebimento.split("/");
          dtEl.value = `${a}-${m}-${d}`;
        } else {
          dtEl.value = p.data_recebimento;
        }
      } else {
        dtEl.value = "";
      }
    }
    const monEl = document.getElementById("formMonitorar");
    if (monEl) monEl.checked = (p.monitorar === 1 || p.monitorar === undefined);

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

  const dtEl = document.getElementById("formDataRec");
  const dados = {
    projeto: document.getElementById("formProjeto").value.trim() || "STI",
    sistema: document.getElementById("formSistema").value.trim() || "SEI",
    numero_processo: numProc,
    descricao: document.getElementById("formDescricao").value.trim(),
    local_atual: document.getElementById("formLocal").value.trim(),
    acao: document.getElementById("formAcao").value.trim(),
    situacao: document.getElementById("formSituacao").value.trim(),
    data_recebimento: dtEl ? dtEl.value : "",
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
      await carregarDados();
      exibirToast(id ? `✓ Processo ${numProc} atualizado!` : `✓ Processo ${numProc} cadastrado!`);
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
// GESTÃO, CADASTRO E EDIÇÃO DE PROJETOS
// -------------------------------------------------------------
function abrirModalNovoProjeto() {
  const form = document.getElementById("formNovoProjeto");
  if (form) form.reset();
  const modal = document.getElementById("modalNovoProjeto");
  if (modal) modal.style.display = "flex";
  setTimeout(() => {
    const el = document.getElementById("novoProjNome");
    if (el) el.focus();
  }, 50);
}

function fecharModalNovoProjeto() {
  const modal = document.getElementById("modalNovoProjeto");
  if (modal) modal.style.display = "none";
}

async function salvarNovoProjeto(e) {
  e.preventDefault();
  const nome = document.getElementById("novoProjNome").value.trim();
  const descricao = document.getElementById("novoProjDescricao").value.trim();

  if (!nome) {
    alert("O nome do projeto é obrigatório.");
    return;
  }

  try {
    const res = await fetch("/api/projetos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome, descricao })
    });
    const json = await res.json();
    if (json.success) {
      fecharModalNovoProjeto();
      await carregarDados();
      exibirToast(`✓ Projeto "${nome}" cadastrado com sucesso!`);
    } else {
      alert("Erro ao cadastrar projeto: " + json.error);
    }
  } catch (err) {
    console.error(err);
    alert("Erro na requisição ao salvar novo projeto.");
  }
}

function abrirModalEditarProjeto(projId) {
  let proj = null;
  if (projId) {
    proj = todosProjetos.find(p => p.id === projId);
  } else if (todosProjetos.length > 0) {
    proj = todosProjetos[0];
  }

  if (!proj && todosProjetos.length === 0) {
    alert("Nenhum projeto cadastrado ainda. Use 'Novo Projeto' para começar.");
    return;
  }

  if (proj) {
    preencherCamposEdicaoProjeto(proj);
  }

  const modal = document.getElementById("modalEditarProjeto");
  if (modal) modal.style.display = "flex";
}

function selecionarProjetoParaEditar(projId) {
  if (!projId) return;
  const proj = todosProjetos.find(p => p.id === parseInt(projId, 10));
  if (proj) {
    preencherCamposEdicaoProjeto(proj);
  }
}

function preencherCamposEdicaoProjeto(proj) {
  const idEl = document.getElementById("editProjId");
  const nomeEl = document.getElementById("editProjNome");
  const descEl = document.getElementById("editProjDescricao");
  const titleEl = document.getElementById("modalProjetoTitle");
  const infoEl = document.getElementById("editProjProcessosInfo");
  const selEl = document.getElementById("editProjSelect");

  if (idEl) idEl.value = proj.id;
  if (nomeEl) nomeEl.value = proj.nome || "";
  if (descEl) descEl.value = proj.descricao || "";
  if (titleEl) titleEl.textContent = `Editar Projeto: ${proj.nome}`;
  if (selEl) selEl.value = proj.id;

  const numProcs = (proj.processos || []).length;
  if (infoEl) {
    infoEl.textContent = `ℹ️ Este projeto possui ${numProcs} processo(s) vinculado(s).`;
  }
}

function fecharModalEditarProjeto() {
  const modal = document.getElementById("modalEditarProjeto");
  if (modal) modal.style.display = "none";
}

async function salvarProjetoEdicao(e) {
  e.preventDefault();
  const projId = document.getElementById("editProjId").value;
  const nome = document.getElementById("editProjNome").value.trim();
  const descricao = document.getElementById("editProjDescricao").value.trim();

  if (!projId) {
    alert("Selecione um projeto para atualizar.");
    return;
  }
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
      fecharModalEditarProjeto();
      await carregarDados();
      exibirToast(`✓ Projeto "${nome}" atualizado com sucesso!`);
    } else {
      alert("Erro ao salvar projeto: " + json.error);
    }
  } catch (err) {
    console.error(err);
    alert("Erro na requisição ao salvar projeto.");
  }
}

async function excluirProjetoAtual() {
  const projId = document.getElementById("editProjId").value;
  const nome = document.getElementById("editProjNome").value;

  if (!projId) {
    alert("Nenhum projeto selecionado para exclusão.");
    return;
  }

  if (!confirm(`Tem certeza que deseja excluir o projeto "${nome}"?\n\nATENÇÃO: Todos os processos vinculados a ele também serão excluídos!`)) {
    return;
  }

  try {
    const res = await fetch(`/api/projetos/${projId}`, {
      method: "DELETE"
    });
    const json = await res.json();
    if (json.success) {
      fecharModalEditarProjeto();
      await carregarDados();
      exibirToast(`✓ Projeto "${nome}" e seus processos foram excluídos.`);
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
