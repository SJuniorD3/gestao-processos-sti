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
let usuarioLogado = null;

// ==========================================================================
// SISTEMA DE TOAST NOTIFICATIONS & MICRO-INTERAÇÕES (UX PRO V3.0)
// ==========================================================================
function showToast(mensagem, tipo = "info", duracao = 3800) {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `sti-toast toast-${tipo}`;

  let icone = "ℹ️";
  if (tipo === "sucesso") icone = "✓";
  else if (tipo === "erro") icone = "✕";
  else if (tipo === "alerta") icone = "⚠️";

  toast.innerHTML = `
    <span class="toast-icon">${icone}</span>
    <span class="toast-msg">${escapeHtml(String(mensagem))}</span>
    <button class="toast-close" title="Fechar">&times;</button>
  `;

  const fechar = () => {
    toast.style.animation = "toastSlideOut 0.25s ease forwards";
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 250);
  };

  toast.querySelector(".toast-close").onclick = fechar;
  container.appendChild(toast);

  if (duracao > 0) {
    setTimeout(fechar, duracao);
  }
}

function mostrarConfirmacao({ titulo = "Confirmação", mensagem, icone = "⚠️", textoConfirmar = "Confirmar", tipo = "primary", aoConfirmar }) {
  const modal = document.getElementById("modalConfirmacao");
  if (!modal) {
    if (confirm(mensagem.replace(/<[^>]*>/g, ""))) {
      if (typeof aoConfirmar === "function") aoConfirmar();
    }
    return;
  }

  const elIcone = document.getElementById("confirmaIcone");
  const elTitulo = document.getElementById("confirmaTitulo");
  const elMsg = document.getElementById("confirmaMensagem");
  const btnConf = document.getElementById("btnConfirmaConfirmar");
  const btnCanc = document.getElementById("btnConfirmaCancelar");

  if (elIcone) elIcone.textContent = icone;
  if (elTitulo) elTitulo.textContent = titulo;
  if (elMsg) elMsg.innerHTML = mensagem;

  if (btnConf) {
    btnConf.textContent = textoConfirmar;
    if (tipo === "danger") {
      btnConf.className = "btn btn-primary";
      btnConf.style.background = "#dc2626";
      btnConf.style.borderColor = "#b91c1c";
    } else {
      btnConf.className = "btn btn-primary";
      btnConf.style.background = "#2563eb";
      btnConf.style.borderColor = "#1d4ed8";
    }

    btnConf.onclick = () => {
      modal.style.display = "none";
      if (typeof aoConfirmar === "function") aoConfirmar();
    };
  }

  if (btnCanc) {
    btnCanc.onclick = () => {
      modal.style.display = "none";
    };
  }

  modal.style.display = "flex";
}

async function copiarTexto(texto, btn) {
  try {
    await navigator.clipboard.writeText(texto);
    if (btn) {
      const original = btn.innerHTML;
      btn.innerHTML = "✓";
      btn.style.color = "#16a34a";
      setTimeout(() => {
        btn.innerHTML = original;
        btn.style.color = "";
      }, 1500);
    }
    showToast(`Número copiado: ${texto}`, "sucesso", 2000);
  } catch (err) {
    const tempInput = document.createElement("input");
    tempInput.value = texto;
    document.body.appendChild(tempInput);
    tempInput.select();
    document.execCommand("copy");
    document.body.removeChild(tempInput);
    showToast(`Número copiado: ${texto}`, "sucesso", 2000);
  }
}

function exibirSkeletons() {
  const tbody = document.getElementById("tabelaCorpo");
  if (tbody) {
    let rows = "";
    for (let i = 0; i < 4; i++) {
      rows += `
        <tr class="skeleton-row">
          <td><div class="skeleton-box" style="width: 110px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 50px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 140px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 180px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 120px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 100px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 70px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 90px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 40px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 70px; height: 18px;"></div></td>
          <td><div class="skeleton-box" style="width: 60px; height: 18px;"></div></td>
        </tr>
      `;
    }
    tbody.innerHTML = rows;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  carregarUsuarioAtual();
  carregarDados();
  atualizarStatusAgendador();
  carregarHistoricoDisparos();
  setInterval(atualizarStatusAgendador, 30000);
});

async function carregarUsuarioAtual() {
  try {
    const res = await fetch("/api/auth/me");
    const json = await res.json();
    if (json.success && json.data) {
      usuarioLogado = json.data;
      const lbl = document.getElementById("labelNomeUsuario");
      const badge = document.getElementById("badgePerfilUsuario");
      const btnAdmin = document.getElementById("btnAdminUsuarios");

      if (lbl) lbl.textContent = usuarioLogado.nome || usuarioLogado.usuario;
      if (badge) {
        if (usuarioLogado.perfil === "admin") {
          badge.textContent = "Admin";
          badge.style.background = "#dbeafe";
          badge.style.color = "#1e40af";
        } else if (usuarioLogado.perfil === "operador") {
          badge.textContent = "Operador";
          badge.style.background = "#fef3c7";
          badge.style.color = "#92400e";
        } else {
          badge.textContent = "Leitor";
          badge.style.background = "#f1f5f9";
          badge.style.color = "#475569";
        }
      }

      if (btnAdmin) {
        btnAdmin.style.display = usuarioLogado.perfil === "admin" ? "inline-flex" : "none";
      }

      // Restrições visuais para perfil 'leitor' (Apenas Consulta)
      if (usuarioLogado.perfil === "leitor") {
        const btnProc = document.getElementById("btnHeaderNovoProcesso");
        const btnProj = document.getElementById("btnHeaderNovoProjeto");
        const btnEditProj = document.getElementById("btnHeaderEditarProjeto");
        const btnSync = document.getElementById("btnHeaderSincronizar");
        const btnImport = document.getElementById("btnHeaderImportarLote");
        if (btnProc) btnProc.style.display = "none";
        if (btnProj) btnProj.style.display = "none";
        if (btnEditProj) btnEditProj.style.display = "none";
        if (btnSync) btnSync.style.display = "none";
        if (btnImport) btnImport.style.display = "none";
      }
    }
  } catch (err) {
    console.error("Erro ao carregar usuário atual:", err);
  }
}

async function carregarDados() {
  exibirSkeletons();
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
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="padding: 48px 20px; text-align: center;">
          <div style="max-width: 360px; margin: 0 auto; color: #64748b;">
            <div style="font-size: 40px; margin-bottom: 10px;">🔍</div>
            <strong style="color: #0f172a; font-size: 15px; display: block; margin-bottom: 6px;">Nenhum processo ou projeto encontrado</strong>
            <p style="font-size: 12.5px; line-height: 1.5; margin-bottom: 16px;">Tente alterar os termos de busca ou redefinir os filtros aplicados para visualizar os dados.</p>
            <button class="btn btn-sm btn-outline" onclick="limparFiltrosV3()">Limpar Filtros e Ver Todos</button>
          </div>
        </td>
      </tr>
    `;
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
      const isLeitor = usuarioLogado && usuarioLogado.perfil === "leitor";

      if (idx === 0) {
        celulaProjeto = `
          <td rowspan="${totalP}" class="cell-projeto" style="vertical-align: top; background: white; font-weight: 700; color: #111827;">
            <div style="cursor: pointer;" onclick="${isLeitor ? '' : `abrirModalEditarProjeto(${proj.id})`}" title="${isLeitor ? '' : 'Clique para editar o projeto'}">${escapeHtml(proj.nome)}</div>
            ${!isLeitor ? `
              <div style="margin-top: 6px; display: flex; gap: 4px; flex-wrap: wrap;">
                <button class="btn btn-sm btn-outline" style="font-size: 11px; color: #374151; border: 1px solid #d1d5db; padding: 1px 5px;" onclick="abrirModalEditarProjeto(${proj.id})">
                  ✏️ Editar Projeto
                </button>
                <button class="btn btn-sm btn-outline" style="font-size: 11px; color: #374151; border: 1px solid #d1d5db; padding: 1px 5px;" onclick="abrirModalNovoProcessoComProjeto('${escapeHtml(proj.nome)}')">
                  ➕ Add Processo
                </button>
              </div>
            ` : ''}
          </td>
        `;
        celulaDesc = `
          <td rowspan="${totalP}" class="cell-desc" style="vertical-align: top; background: white; font-size: 12px; color: #374151;">
            ${escapeHtml(proj.descricao || "-")}
          </td>
        `;
      }

      const botoesAcao = !isLeitor ? `
        <div class="action-btns">
          <button class="btn-icon-action" title="Sincronizar no portal" onclick="sincronizarProcessoWeb(${p.id})">🔄</button>
          <button class="btn-icon-action" title="Editar processo" onclick="abrirModalEditarProcesso(${p.id})">✏️</button>
          ${usuarioLogado && usuarioLogado.perfil === "admin" ? `
            <button class="btn-icon-action" title="Excluir processo" onclick="confirmarExclusao(${p.id}, '${escapeHtml(p.numero_processo)}')">🗑️</button>
          ` : ''}
        </div>
      ` : `<span style="font-size: 11px; color: #94a3b8; font-style: italic;">Consulta</span>`;

      htmlTotal += `
        <tr>
          ${celulaProjeto}
          <td class="text-center" style="font-weight: 600;">${p.sistema}</td>
          <td style="font-family: monospace; font-weight: 600;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
              <a href="javascript:void(0)" onclick="abrirProcessoExterno('${escapeHtml(p.sistema)}', '${escapeHtml(p.numero_processo)}')" 
                 style="color: #2563eb; text-decoration: underline; cursor: pointer; white-space: nowrap;" 
                 title="Clique para abrir diretamente no portal ${escapeHtml(p.sistema)}">
                🔗 ${escapeHtml(p.numero_processo)}
              </a>
              <button class="btn-copy-mini" onclick="copiarTexto('${escapeHtml(p.numero_processo)}', this)" title="Copiar número do processo">
                📋
              </button>
            </div>
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
            ${botoesAcao}
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
      showToast("Não foi possível carregar os detalhes do processo.", "erro");
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
    showToast("O Número do Processo é obrigatório.", "alerta");
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
      showToast(id ? `✓ Processo ${numProc} atualizado com sucesso!` : `✓ Processo ${numProc} cadastrado com sucesso!`, "sucesso");
    } else {
      showToast("Erro ao salvar: " + json.error, "erro");
    }
  } catch (err) {
    console.error(err);
    showToast("Falha na requisição ao servidor.", "erro");
  }
}

async function confirmarExclusao(id, numero) {
  mostrarConfirmacao({
    titulo: "Excluir Processo",
    mensagem: `Tem certeza que deseja excluir permanentemente o processo <strong>${escapeHtml(numero)}</strong> e todo o seu histórico?`,
    icone: "🗑️",
    textoConfirmar: "Sim, Excluir",
    tipo: "danger",
    aoConfirmar: async () => {
      try {
        const res = await fetch(`/api/processos/${id}`, { method: "DELETE" });
        const json = await res.json();
        if (json.success) {
          showToast(`✓ Processo ${numero} excluído com sucesso!`, "sucesso");
          carregarDados();
        } else {
          showToast("Erro ao excluir: " + json.error, "erro");
        }
      } catch (err) {
        console.error(err);
        showToast("Falha ao excluir o processo.", "erro");
      }
    }
  });
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
  mostrarConfirmacao({
    titulo: "Disparar Resumo STI",
    mensagem: "Deseja gerar e disparar agora o resumo consolidado de processos da STI para os canais configurados?",
    icone: "⚡",
    textoConfirmar: "Disparar Agora",
    tipo: "primary",
    aoConfirmar: async () => {
      showToast("Gerando e enviando resumo diário...", "info");
      try {
        const res = await fetch("/api/scheduler/disparar", { method: "POST" });
        const json = await res.json();
        if (json.success) {
          showToast("✓ Resumo gerado e disparado com sucesso!", "sucesso");
          atualizarStatusAgendador();
          carregarHistoricoDisparos();
        } else {
          showToast("Erro ao disparar resumo: " + json.error, "erro");
        }
      } catch (err) {
        console.error(err);
        showToast("Erro ao comunicar com o agendador.", "erro");
      }
    }
  });
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

let cancelandoSincronizacao = false;

async function sincronizarSistemasWeb() {
  const processosMonitorados = todosProcessos.filter(p => p.monitorar === 1 || p.monitorar === undefined);
  if (processosMonitorados.length === 0) {
    showToast("Não há processos com monitoramento ativo cadastrados.", "alerta");
    return;
  }

  cancelandoSincronizacao = false;
  const modal = document.getElementById("modalSincronizacao");
  const tabelaFeed = document.getElementById("syncTabelaFeed");
  const pBar = document.getElementById("syncProgressBar");
  const pTexto = document.getElementById("syncPorcentagem");
  const statusTexto = document.getElementById("syncStatusTexto");
  const subTexto = document.getElementById("syncModalSubtitle");
  const spinIcon = document.getElementById("syncSpinIcon");
  const btnFecharTop = document.getElementById("btnFecharSyncTop");
  const btnCancelar = document.getElementById("btnCancelarSync");
  const btnConcluir = document.getElementById("btnConcluirSync");
  const resumoFinal = document.getElementById("syncResumoFinal");

  // Reset visual do modal
  tabelaFeed.innerHTML = "";
  pBar.style.width = "0%";
  pTexto.textContent = "0%";
  statusTexto.textContent = `Iniciando consulta de ${processosMonitorados.length} processo(s)...`;
  subTexto.textContent = "Consultando portais e capturando andamentos oficiais...";
  spinIcon.className = "icon-sync-spin";
  btnFecharTop.disabled = true;
  btnCancelar.style.display = "inline-flex";
  btnCancelar.disabled = false;
  btnCancelar.textContent = "Parar Sincronização";
  btnConcluir.style.display = "none";
  resumoFinal.textContent = `Total a verificar: ${processosMonitorados.length}`;
  modal.style.display = "flex";

  let sucessoCount = 0;
  let falhaCount = 0;

  for (let i = 0; i < processosMonitorados.length; i++) {
    if (cancelandoSincronizacao) {
      statusTexto.textContent = `Sincronização pausada pelo usuário (${i}/${processosMonitorados.length}).`;
      break;
    }

    const proc = processosMonitorados[i];
    const pct = Math.round(((i + 1) / processosMonitorados.length) * 100);
    statusTexto.textContent = `Consultando [${i + 1}/${processosMonitorados.length}]: ${proc.numero_processo} (${proc.sistema})...`;
    pBar.style.width = `${pct}%`;
    pTexto.textContent = `${pct}%`;

    // Cria linha no feed em estado de carregamento
    const rowId = `sync-row-${proc.id}`;
    const row = document.createElement("tr");
    row.id = rowId;
    row.style.borderBottom = "1px solid #f1f5f9";
    row.innerHTML = `
      <td style="padding: 9px 12px; font-weight: 700;">${escapeHtml(proc.sistema)}</td>
      <td style="padding: 9px 12px; font-family: monospace; font-weight: 600;">${escapeHtml(proc.numero_processo)}</td>
      <td style="padding: 9px 12px;"><span style="background: #fef3c7; color: #92400e; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600;">⏳ Consultando...</span></td>
      <td style="padding: 9px 12px; color: #64748b;">Acessando portal oficial...</td>
    `;
    tabelaFeed.prepend(row);

    try {
      const res = await fetch(`/api/monitoramento/processo/${proc.id}`, { method: "POST" });
      const json = await res.json();
      const updatedRow = document.getElementById(rowId);

      if (json.sucesso) {
        sucessoCount++;
        const setor = json.dados ? (json.dados.local_atual || "Atualizado") : "Atualizado";
        const andamentos = json.andamentos_capturados ? ` (${json.andamentos_capturados} andamentos)` : "";
        if (updatedRow) {
          updatedRow.innerHTML = `
            <td style="padding: 9px 12px; font-weight: 700;">${escapeHtml(proc.sistema)}</td>
            <td style="padding: 9px 12px; font-family: monospace; font-weight: 600; color: #1e3a8a;">${escapeHtml(proc.numero_processo)}</td>
            <td style="padding: 9px 12px;"><span style="background: #dcfce7; color: #15803d; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 700;">✓ Atualizado</span></td>
            <td style="padding: 9px 12px; color: #1e293b;"><strong>${escapeHtml(setor)}</strong><span style="font-size: 11px; color: #64748b;">${andamentos}</span></td>
          `;
        }
      } else {
        falhaCount++;
        const motivo = json.mensagem || "Não foi possível extrair dados";
        if (updatedRow) {
          updatedRow.innerHTML = `
            <td style="padding: 9px 12px; font-weight: 700;">${escapeHtml(proc.sistema)}</td>
            <td style="padding: 9px 12px; font-family: monospace; font-weight: 600; color: #475569;">${escapeHtml(proc.numero_processo)}</td>
            <td style="padding: 9px 12px;"><span style="background: #fee2e2; color: #b91c1c; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 700;">⚠️ Falha</span></td>
            <td style="padding: 9px 12px; color: #ef4444; font-size: 11.5px;">${escapeHtml(motivo)}</td>
          `;
        }
      }
    } catch (err) {
      falhaCount++;
      const updatedRow = document.getElementById(rowId);
      if (updatedRow) {
        updatedRow.innerHTML = `
          <td style="padding: 9px 12px; font-weight: 700;">${escapeHtml(proc.sistema)}</td>
          <td style="padding: 9px 12px; font-family: monospace;">${escapeHtml(proc.numero_processo)}</td>
          <td style="padding: 9px 12px;"><span style="background: #fee2e2; color: #b91c1c; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 700;">⚠️ Erro</span></td>
          <td style="padding: 9px 12px; color: #ef4444; font-size: 11.5px;">Falha de comunicação com o servidor</td>
        `;
      }
    }

    resumoFinal.innerHTML = `Sucessos: <strong style="color: #15803d;">${sucessoCount}</strong> • Falhas/Sem resposta: <strong style="color: #b91c1c;">${falhaCount}</strong>`;
  }

  // Finalização da Sincronização
  spinIcon.className = "";
  btnFecharTop.disabled = false;
  btnCancelar.style.display = "none";
  btnConcluir.style.display = "inline-flex";
  statusTexto.textContent = cancelandoSincronizacao
    ? "Sincronização pausada."
    : `✓ Concluído! ${sucessoCount} processo(s) atualizados com sucesso.`;
  pBar.style.width = "100%";
  pTexto.textContent = "100%";

  exibirToast(`✓ Sincronização concluída: ${sucessoCount} atualizados.`);
}

function cancelarSincronizacao() {
  cancelandoSincronizacao = true;
  const btn = document.getElementById("btnCancelarSync");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Parando...";
  }
}

function fecharModalSincronizacao() {
  document.getElementById("modalSincronizacao").style.display = "none";
  carregarDados();
}

async function sincronizarProcessoWeb(id) {
  let targetBtn = null;
  if (window.event && window.event.target) {
    targetBtn = window.event.target.closest("button");
  }
  const iconOriginal = targetBtn ? targetBtn.textContent : "🔄";
  if (targetBtn) {
    targetBtn.textContent = "⏳";
    targetBtn.disabled = true;
    targetBtn.style.opacity = "0.6";
  }

  try {
    const res = await fetch(`/api/monitoramento/processo/${id}`, { method: "POST" });
    const json = await res.json();
    if (json.sucesso) {
      const setor = json.dados ? json.dados.local_atual : "Portal Oficial";
      showToast(`✓ Sincronizado com sucesso! Setor: ${setor}`, "sucesso");
      await carregarDados();
    } else {
      showToast("Aviso do portal: " + (json.mensagem || "Não foi possível sincronizar"), "alerta");
    }
  } catch (err) {
    console.error(err);
    showToast("Erro de conexão ao sincronizar processo.", "erro");
  } finally {
    if (targetBtn) {
      targetBtn.textContent = iconOriginal;
      targetBtn.disabled = false;
      targetBtn.style.opacity = "1";
    }
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
    showToast("O nome do projeto é obrigatório.", "alerta");
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
      showToast(`✓ Projeto "${nome}" cadastrado com sucesso!`, "sucesso");
    } else {
      showToast("Erro ao cadastrar projeto: " + json.error, "erro");
    }
  } catch (err) {
    console.error(err);
    showToast("Erro na requisição ao salvar novo projeto.", "erro");
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
    showToast("Nenhum projeto cadastrado ainda. Use 'Novo Projeto' para começar.", "info");
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
    showToast("Selecione um projeto para atualizar.", "alerta");
    return;
  }
  if (!nome) {
    showToast("O nome do projeto é obrigatório.", "alerta");
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
      showToast(`✓ Projeto "${nome}" atualizado com sucesso!`, "sucesso");
    } else {
      showToast("Erro ao salvar projeto: " + json.error, "erro");
    }
  } catch (err) {
    console.error(err);
    showToast("Erro na requisição ao salvar projeto.", "erro");
  }
}

async function excluirProjetoAtual() {
  const projId = document.getElementById("editProjId").value;
  const nome = document.getElementById("editProjNome").value;

  if (!projId) {
    showToast("Nenhum projeto selecionado para exclusão.", "alerta");
    return;
  }

  mostrarConfirmacao({
    titulo: "Excluir Projeto e Processos",
    mensagem: `Tem certeza que deseja excluir o projeto <strong>${escapeHtml(nome)}</strong>?<br><br><span style="color: #dc2626; font-weight: 700;">ATENÇÃO: Todos os processos vinculados a ele também serão excluídos permanentemente!</span>`,
    icone: "⚠️",
    textoConfirmar: "Sim, Excluir Projeto",
    tipo: "danger",
    aoConfirmar: async () => {
      try {
        const res = await fetch(`/api/projetos/${projId}`, { method: "DELETE" });
        const json = await res.json();
        if (json.success) {
          fecharModalEditarProjeto();
          await carregarDados();
          showToast(`✓ Projeto "${nome}" e seus processos foram excluídos.`, "sucesso");
        } else {
          showToast("Erro ao excluir projeto: " + json.error, "erro");
        }
      } catch (err) {
        console.error(err);
        showToast("Erro na requisição ao excluir projeto.", "erro");
      }
    }
  });
}

// -------------------------------------------------------------
// SISTEMAS E EXPORTAÇÃO
// -------------------------------------------------------------
async function abrirModalSistemas() {
  document.getElementById("modalSistemas").style.display = "flex";
  await carregarStatusSistemas();
}

async function carregarStatusSistemas() {
  try {
    const res = await fetch("/api/sistemas");
    const json = await res.json();
    if (json.success && json.data) {
      const sei = json.data.sei || {};
      const start = json.data.startgov || {};

      const bSei = document.getElementById("badgeStatusSEI");
      const uSei = document.getElementById("txtUserSEI");
      if (bSei && uSei) {
        if (sei.configurado) {
          bSei.textContent = "✓ Configurado";
          bSei.style.background = "#dcfce7";
          bSei.style.color = "#15803d";
          uSei.textContent = sei.usuario ? sei.usuario.replace(/(.{2}).*(.{2})/, "$1***$2") : "Configurado via ambiente";
        } else {
          bSei.textContent = "⚠️ Não Configurado";
          bSei.style.background = "#fee2e2";
          bSei.style.color = "#b91c1c";
          uSei.textContent = "Variáveis SEI_USER/SEI_PASS ausentes";
        }
      }

      const bStart = document.getElementById("badgeStatusStartGov");
      const uStart = document.getElementById("txtUserStartGov");
      if (bStart && uStart) {
        if (start.configurado) {
          bStart.textContent = "✓ Configurado";
          bStart.style.background = "#dcfce7";
          bStart.style.color = "#15803d";
          uStart.textContent = start.usuario ? start.usuario.replace(/(\d{3})\d{6}(\d{2})/, "$1.***.***-$2") : "Configurado via ambiente";
        } else {
          bStart.textContent = "⚠️ Não Configurado";
          bStart.style.background = "#fee2e2";
          bStart.style.color = "#b91c1c";
          uStart.textContent = "Variáveis STARTGOV_USER/STARTGOV_PASS ausentes";
        }
      }
    }
  } catch (err) {
    console.error("Erro ao obter status dos sistemas:", err);
  }
}

async function testarConectividadeRobos() {
  const btn = document.getElementById("btnTestarPortais");
  const origHtml = btn.innerHTML;
  btn.innerHTML = '<span class="icon-sync-spin">🔄</span> Testando autenticação...';
  btn.disabled = true;

  try {
    const res = await fetch("/api/sistemas/testar", { method: "POST" });
    const json = await res.json();
    if (json.success && json.data) {
      const sei = json.data.sei || {};
      const start = json.data.startgov || {};

      const bSei = document.getElementById("badgeStatusSEI");
      const mSei = document.getElementById("msgDiagSEI");
      if (bSei && mSei) {
        if (sei.sucesso) {
          bSei.textContent = "🟢 Autenticado (OK)";
          bSei.style.background = "#dcfce7";
          bSei.style.color = "#15803d";
          mSei.innerHTML = `<span style="color: #15803d; font-weight: 600;">✓ Conexão bem-sucedida: ${escapeHtml(sei.mensagem)}</span>`;
        } else {
          bSei.textContent = "🔴 Falha no Login";
          bSei.style.background = "#fee2e2";
          bSei.style.color = "#b91c1c";
          mSei.innerHTML = `<span style="color: #b91c1c;">⚠️ ${escapeHtml(sei.mensagem)}</span>`;
        }
      }

      const bStart = document.getElementById("badgeStatusStartGov");
      const mStart = document.getElementById("msgDiagStartGov");
      if (bStart && mStart) {
        if (start.sucesso) {
          bStart.textContent = "🟢 Autenticado (OK)";
          bStart.style.background = "#dcfce7";
          bStart.style.color = "#15803d";
          mStart.innerHTML = `<span style="color: #15803d; font-weight: 600;">✓ Conexão bem-sucedida: ${escapeHtml(start.mensagem)}</span>`;
        } else {
          bStart.textContent = "🔴 Falha no Login";
          bStart.style.background = "#fee2e2";
          bStart.style.color = "#b91c1c";
          mStart.innerHTML = `<span style="color: #b91c1c;">⚠️ ${escapeHtml(start.mensagem)}</span>`;
        }
      }

      showToast("✓ Teste de conexão concluído!", "sucesso");
    } else {
      showToast("Erro ao testar robôs: " + (json.error || "Sem resposta"), "erro");
    }
  } catch (err) {
    console.error(err);
    showToast("Falha de conexão com o servidor ao testar robôs.", "erro");
  } finally {
    btn.innerHTML = origHtml;
    btn.disabled = false;
  }
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
  mostrarConfirmacao({
    titulo: "Encerrar Sessão",
    mensagem: "Deseja realmente sair do painel de monitoramento STI?",
    icone: "🚪",
    textoConfirmar: "Sim, Sair",
    tipo: "danger",
    aoConfirmar: async () => {
      try {
        await fetch("/api/auth/logout", { method: "POST" });
      } catch (e) {}
      localStorage.removeItem("sti_token");
      localStorage.removeItem("sti_user");
      window.location.href = "/login.html";
    }
  });
}

// -------------------------------------------------------------
// GESTÃO DE USUÁRIOS E AUDITORIA (MULTI-USUÁRIO & RBAC)
// -------------------------------------------------------------
let usuariosCache = [];

async function abrirModalUsuarios() {
  document.getElementById("modalUsuarios").style.display = "flex";
  alternarAbaUsuarios("usuarios");
}

function fecharModalUsuarios() {
  document.getElementById("modalUsuarios").style.display = "none";
}

function alternarAbaUsuarios(aba) {
  const btnU = document.getElementById("tabBtnUsuarios");
  const btnA = document.getElementById("tabBtnAuditoria");
  const abaU = document.getElementById("abaConteudoUsuarios");
  const abaA = document.getElementById("abaConteudoAuditoria");

  if (aba === "usuarios") {
    btnU.className = "view-btn active";
    btnU.style.borderBottom = "2px solid #2563eb";
    btnU.style.fontWeight = "700";
    btnA.className = "view-btn";
    btnA.style.borderBottom = "none";
    btnA.style.fontWeight = "600";
    abaU.style.display = "block";
    abaA.style.display = "none";
    carregarUsuarios();
  } else {
    btnA.className = "view-btn active";
    btnA.style.borderBottom = "2px solid #2563eb";
    btnA.style.fontWeight = "700";
    btnU.className = "view-btn";
    btnU.style.borderBottom = "none";
    btnU.style.fontWeight = "600";
    abaA.style.display = "block";
    abaU.style.display = "none";
    carregarLogsAuditoria();
  }
}

async function carregarUsuarios() {
  const tbody = document.getElementById("tabelaUsuariosCorpo");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="5" class="loading-cell">Carregando usuários...</td></tr>`;

  try {
    const res = await fetch("/api/usuarios");
    const json = await res.json();
    if (json.success) {
      usuariosCache = json.data || [];
      renderizarTabelaUsuarios(usuariosCache);
    } else {
      tbody.innerHTML = `<tr><td colspan="5" class="loading-cell text-danger">${escapeHtml(json.error)}</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="loading-cell text-danger">Erro de comunicação com o servidor.</td></tr>`;
  }
}

function renderizarTabelaUsuarios(lista) {
  const tbody = document.getElementById("tabelaUsuariosCorpo");
  if (!tbody) return;

  if (lista.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="loading-cell">Nenhum usuário cadastrado.</td></tr>`;
    return;
  }

  let html = "";
  lista.forEach(u => {
    let perfilBadge = "";
    if (u.perfil === "admin") {
      perfilBadge = `<span style="background: #dbeafe; color: #1e40af; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px;">Admin</span>`;
    } else if (u.perfil === "operador") {
      perfilBadge = `<span style="background: #fef3c7; color: #92400e; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px;">Operador</span>`;
    } else {
      perfilBadge = `<span style="background: #f1f5f9; color: #475569; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px;">Leitor</span>`;
    }

    const statusBadge = u.ativo === 1
      ? `<span style="background: #dcfce7; color: #15803d; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px;">Ativo</span>`
      : `<span style="background: #fee2e2; color: #b91c1c; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px;">Inativo</span>`;

    const isSelf = usuarioLogado && (usuarioLogado.usuario.toLowerCase() === u.usuario.toLowerCase());

    html += `
      <tr style="border-bottom: 1px solid #f1f5f9;">
        <td style="padding: 10px 12px; font-weight: 600; color: #0f172a;">${escapeHtml(u.nome)}</td>
        <td style="padding: 10px 12px; font-family: monospace;">${escapeHtml(u.usuario)}</td>
        <td style="padding: 10px 12px;">${perfilBadge}</td>
        <td style="padding: 10px 12px;">${statusBadge}</td>
        <td style="padding: 10px 12px; text-align: center;">
          <div style="display: flex; gap: 4px; justify-content: center;">
            <button class="btn btn-sm btn-outline" style="font-size: 11px; padding: 3px 7px;" onclick="editarUsuario(${u.id})">✏️ Editar</button>
            ${!isSelf ? `
              <button class="btn btn-sm btn-outline" style="font-size: 11px; padding: 3px 7px; color: ${u.ativo === 1 ? '#d97706' : '#15803d'};" onclick="alternarAtivoUsuario(${u.id}, ${u.ativo})">
                ${u.ativo === 1 ? '⏸ Desativar' : '▶ Ativar'}
              </button>
              <button class="btn btn-sm btn-outline" style="font-size: 11px; padding: 3px 7px; color: #dc2626;" onclick="excluirUsuario(${u.id})">🗑️</button>
            ` : '<span style="font-size: 11px; color: #94a3b8; font-style: italic;">(Sua conta)</span>'}
          </div>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

function editarUsuario(id) {
  const u = usuariosCache.find(x => x.id === id);
  if (!u) return;

  document.getElementById("formUsuarioId").value = u.id;
  document.getElementById("formUsuarioNome").value = u.nome;
  document.getElementById("formUsuarioLogin").value = u.usuario;
  document.getElementById("formUsuarioLogin").disabled = true; // Login não deve ser alterado após criação
  document.getElementById("formUsuarioPerfil").value = u.perfil;
  document.getElementById("formUsuarioSenha").value = "";
  document.getElementById("formUsuarioSenha").required = false;
  document.getElementById("formUsuarioSenha").placeholder = "Deixe em branco para manter a senha atual";
  document.getElementById("lblUsuarioSenha").textContent = "Nova Senha (Opcional)";

  document.getElementById("tituloFormUsuario").textContent = `✏️ Editando Usuário: ${u.usuario}`;
  document.getElementById("btnSalvarUsuario").textContent = "Atualizar Usuário";
  document.getElementById("btnCancelarEdicaoUsuario").style.display = "inline-flex";
}

function cancelarEdicaoUsuario() {
  document.getElementById("formUsuario").reset();
  document.getElementById("formUsuarioId").value = "";
  document.getElementById("formUsuarioLogin").disabled = false;
  document.getElementById("formUsuarioSenha").required = true;
  document.getElementById("formUsuarioSenha").placeholder = "Digite uma senha forte...";
  document.getElementById("lblUsuarioSenha").textContent = "Senha *";
  document.getElementById("tituloFormUsuario").textContent = "+ Cadastrar Novo Usuário";
  document.getElementById("btnSalvarUsuario").textContent = "Salvar Usuário";
  document.getElementById("btnCancelarEdicaoUsuario").style.display = "none";
}

async function salvarUsuario(e) {
  e.preventDefault();
  const id = document.getElementById("formUsuarioId").value;
  const nome = document.getElementById("formUsuarioNome").value.trim();
  const usuario = document.getElementById("formUsuarioLogin").value.trim().toLowerCase();
  const perfil = document.getElementById("formUsuarioPerfil").value;
  const senha = document.getElementById("formUsuarioSenha").value;

  const method = id ? "PUT" : "POST";
  const url = id ? `/api/usuarios/${id}` : "/api/usuarios";
  const payload = { nome, perfil };
  if (!id) {
    payload.usuario = usuario;
    payload.senha = senha;
  } else {
    if (senha) payload.senha = senha;
  }

  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const json = await res.json();
    if (json.success) {
      showToast(id ? "✓ Usuário atualizado com sucesso!" : `✓ Usuário ${usuario} cadastrado!`, "sucesso");
      cancelarEdicaoUsuario();
      await carregarUsuarios();
    } else {
      showToast("Erro: " + json.error, "erro");
    }
  } catch (err) {
    showToast("Falha de conexão ao salvar usuário.", "erro");
  }
}

async function alternarAtivoUsuario(id, statusAtual) {
  const novoStatus = statusAtual === 1 ? 0 : 1;
  const acaoTexto = novoStatus === 1 ? "ativar" : "desativar";
  const u = usuariosCache.find(x => x.id === id);
  if (!u) return;

  mostrarConfirmacao({
    titulo: `${novoStatus === 1 ? 'Ativar' : 'Desativar'} Usuário`,
    mensagem: `Deseja realmente ${acaoTexto} o acesso do usuário <strong>${escapeHtml(u.usuario)}</strong>?`,
    icone: novoStatus === 1 ? "▶" : "⏸",
    textoConfirmar: `Sim, ${acaoTexto}`,
    tipo: novoStatus === 1 ? "primary" : "danger",
    aoConfirmar: async () => {
      try {
        const res = await fetch(`/api/usuarios/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nome: u.nome, perfil: u.perfil, ativo: novoStatus })
        });
        const json = await res.json();
        if (json.success) {
          showToast(`✓ Usuário ${novoStatus === 1 ? 'ativado' : 'desativado'} com sucesso!`, "sucesso");
          await carregarUsuarios();
        } else {
          showToast("Erro ao alterar status: " + json.error, "erro");
        }
      } catch (err) {
        showToast("Falha ao comunicar com o servidor.", "erro");
      }
    }
  });
}

async function excluirUsuario(id) {
  const u = usuariosCache.find(x => x.id === id);
  if (!u) return;

  mostrarConfirmacao({
    titulo: "Remover Usuário",
    mensagem: `Tem certeza absoluta que deseja remover o usuário <strong>${escapeHtml(u.usuario)}</strong>?<br><span style="color: #dc2626; font-size: 11.5px;">Essa ação não pode ser desfeita.</span>`,
    icone: "🗑️",
    textoConfirmar: "Sim, Remover Usuário",
    tipo: "danger",
    aoConfirmar: async () => {
      try {
        const res = await fetch(`/api/usuarios/${id}`, { method: "DELETE" });
        const json = await res.json();
        if (json.success) {
          showToast(`✓ Usuário ${u.usuario} removido com sucesso!`, "sucesso");
          await carregarUsuarios();
        } else {
          showToast("Erro ao excluir: " + json.error, "erro");
        }
      } catch (err) {
        showToast("Falha ao comunicar com o servidor.", "erro");
      }
    }
  });
}

async function carregarLogsAuditoria() {
  const tbody = document.getElementById("tabelaAuditoriaCorpo");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="5" class="loading-cell">Carregando trilha de auditoria...</td></tr>`;

  try {
    const res = await fetch("/api/auditoria");
    const json = await res.json();
    if (json.success) {
      const logs = json.data || [];
      if (logs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="loading-cell">Nenhum evento registrado ainda.</td></tr>`;
        return;
      }

      let html = "";
      logs.forEach(l => {
        let badgeAcao = `<span style="background: #f1f5f9; color: #475569; padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 11px;">${escapeHtml(l.acao)}</span>`;
        if (l.acao.includes("LOGIN_FALHA") || l.acao.includes("EXCLUIR")) {
          badgeAcao = `<span style="background: #fee2e2; color: #b91c1c; padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 11px;">${escapeHtml(l.acao)}</span>`;
        } else if (l.acao.includes("LOGIN") || l.acao.includes("CRIAR")) {
          badgeAcao = `<span style="background: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 11px;">${escapeHtml(l.acao)}</span>`;
        } else if (l.acao.includes("EDITAR") || l.acao.includes("SINCRONIZAR")) {
          badgeAcao = `<span style="background: #e0e7ff; color: #3730a3; padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 11px;">${escapeHtml(l.acao)}</span>`;
        }

        html += `
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; font-family: monospace; color: #64748b; font-size: 11.5px;">${formatarDataHora(l.criado_em)}</td>
            <td style="padding: 8px 12px; font-weight: 600; color: #0f172a;">${escapeHtml(l.usuario)}</td>
            <td style="padding: 8px 12px;">${badgeAcao}</td>
            <td style="padding: 8px 12px; color: #334155;">${escapeHtml(l.detalhes || "-")}</td>
            <td style="padding: 8px 12px; font-family: monospace; color: #64748b; font-size: 11px;">${escapeHtml(l.ip || "-")}</td>
          </tr>
        `;
      });
      tbody.innerHTML = html;
    } else {
      tbody.innerHTML = `<tr><td colspan="5" class="loading-cell text-danger">${escapeHtml(json.error)}</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="loading-cell text-danger">Erro ao carregar auditoria.</td></tr>`;
  }
}

// ==========================================================================
// ITEM 5: RELATÓRIOS EXECUTIVOS, IMPRESSÃO A4, GARGALOS & IMPORTAÇÃO EM LOTE
// ==========================================================================

// -------------------------------------------------------------
// RELATÓRIO EXECUTIVO OFICIAL (IMPRESSÃO / PDF A4)
// -------------------------------------------------------------
function abrirRelatorioExecutivo() {
  window.open("/relatorio-executivo", "_blank");
}

function imprimirResumoAtual() {
  window.print();
}

// -------------------------------------------------------------
// IMPORTAÇÃO EM LOTE (CSV / PLANILHA EXCEL)
// -------------------------------------------------------------
let dadosLoteParaImportar = [];

function abrirModalImportacao() {
  dadosLoteParaImportar = [];
  const modal = document.getElementById("modalImportacaoLote");
  if (!modal) return;
  
  alternarAbaImportacao("arquivo");
  document.getElementById("txtColarPlanilha").value = "";
  document.getElementById("inputFileCSV").value = "";
  document.getElementById("boxPreviewImport").style.display = "none";
  document.getElementById("boxStatusImport").style.display = "none";
  document.getElementById("btnConfirmarImportacao").disabled = true;
  document.getElementById("btnConfirmarImportacao").innerHTML = '<span class="icon">🚀</span> Confirmar e Importar';
  
  configurarDropzoneCSV();
  modal.style.display = "flex";
}

function fecharModalImportacao() {
  const modal = document.getElementById("modalImportacaoLote");
  if (modal) modal.style.display = "none";
}

function alternarAbaImportacao(aba) {
  const btnArq = document.getElementById("tabBtnImportArquivo");
  const btnColar = document.getElementById("tabBtnImportColar");
  const boxArq = document.getElementById("abaImportArquivo");
  const boxColar = document.getElementById("abaImportColar");

  if (aba === "arquivo") {
    btnArq.classList.add("active");
    btnArq.style.borderBottom = "2px solid #2563eb";
    btnArq.style.fontWeight = "700";
    btnColar.classList.remove("active");
    btnColar.style.borderBottom = "none";
    btnColar.style.fontWeight = "600";
    boxArq.style.display = "block";
    boxColar.style.display = "none";
  } else {
    btnColar.classList.add("active");
    btnColar.style.borderBottom = "2px solid #2563eb";
    btnColar.style.fontWeight = "700";
    btnArq.classList.remove("active");
    btnArq.style.borderBottom = "none";
    btnArq.style.fontWeight = "600";
    boxColar.style.display = "block";
    boxArq.style.display = "none";
  }
}

function baixarModeloCSV() {
  const cabecalho = "Projeto;Sistema;Numero_Processo;Descricao;Local_Atual;Acao;Data_Recebimento;Situacao";
  const linha1 = "STI;SEI;00010.000123/2026;Aquisição de Switches e Roteadores;STI;Análise Técnica;01/03/2026;Em tramitação";
  const linha2 = "CONECTIVIDADE;STARTGOV;00010.000456/2026;Licitação de Links Dedicados;CPL / Licitações;Elaboração de Edital;15/02/2026;Aguardando Publicação";
  const conteudo = "\ufeff" + cabecalho + "\n" + linha1 + "\n" + linha2;
  
  const blob = new Blob([conteudo], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "Modelo_Importacao_Processos_STI.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function carregarExemploColar() {
  const exemplo = `Projeto;Sistema;Numero_Processo;Descricao;Local_Atual;Acao;Data_Recebimento;Situacao
STI;SEI;00010.000123/2026;Aquisição de Switches e Roteadores;STI;Análise Técnica;01/03/2026;Em tramitação
INFRAESTRUTURA;STARTGOV;00010.000789/2026;Manutenção de Data Center;STI/Suporte;Em execução;10/02/2026;Em andamento`;
  const textarea = document.getElementById("txtColarPlanilha");
  textarea.value = exemplo;
  parsearTextoColado();
}

function configurarDropzoneCSV() {
  const dropzone = document.getElementById("dropzoneCSV");
  if (!dropzone || dropzone._configurado) return;
  dropzone._configurado = true;

  ["dragenter", "dragover"].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("dragover");
    }, false);
  });

  ["dragleave", "drop"].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("dragover");
    }, false);
  });

  dropzone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length) {
      processarArquivoCSV(files[0]);
    }
  }, false);
}

function aoSelecionarArquivoCSV(event) {
  const file = event.target.files[0];
  if (file) {
    processarArquivoCSV(file);
  }
}

function processarArquivoCSV(file) {
  const reader = new FileReader();
  reader.onload = function(e) {
    const texto = e.target.result;
    parsearConteudoCSV(texto);
  };
  reader.readAsText(file, "UTF-8");
}

function parsearTextoColado() {
  const texto = document.getElementById("txtColarPlanilha").value;
  parsearConteudoCSV(texto);
}

function parsearConteudoCSV(texto) {
  dadosLoteParaImportar = [];
  const statusBox = document.getElementById("boxStatusImport");
  const previewBox = document.getElementById("boxPreviewImport");
  const btnConfirmar = document.getElementById("btnConfirmarImportacao");
  const tbody = document.getElementById("tabelaPreviewImportCorpo");

  if (!texto || !texto.trim()) {
    previewBox.style.display = "none";
    btnConfirmar.disabled = true;
    return;
  }

  // Detecta quebra de linha
  const linhas = texto.trim().split(/\r?\n/).filter(l => l.trim().length > 0);
  if (linhas.length < 2) {
    statusBox.style.display = "block";
    statusBox.style.background = "#fef2f2";
    statusBox.style.color = "#b91c1c";
    statusBox.textContent = "O conteúdo precisa ter pelo menos 1 linha de cabeçalho e 1 linha de dados.";
    btnConfirmar.disabled = true;
    return;
  }

  // Detecta delimitador (, ; ou \t)
  const primeiraLinha = linhas[0];
  let delimitador = ";";
  if (primeiraLinha.includes("\t")) delimitador = "\t";
  else if (primeiraLinha.includes(";") && !primeiraLinha.includes(",")) delimitador = ";";
  else if (primeiraLinha.includes(",")) delimitador = ",";

  const cabecalho = primeiraLinha.split(delimitador).map(c => c.trim().toLowerCase().replace(/["']/g, ""));

  function getIdx(nomes, padrao) {
    for (const n of nomes) {
      const idx = cabecalho.indexOf(n);
      if (idx !== -1) return idx;
    }
    return padrao;
  }

  const iProj = getIdx(["projeto", "nome do projeto", "proj"], 0);
  const iSis = getIdx(["sistema", "tipo", "origem"], 1);
  const iNum = getIdx(["numero_processo", "processo", "nº processo", "nº - processo", "numero", "nº"], 2);
  const iDesc = getIdx(["descricao", "descrição", "objeto", "objeto/descrição"], 3);
  const iLocal = getIdx(["local_atual", "local", "setor", "unidade"], 4);
  const iAcao = getIdx(["acao", "ação"], 5);
  const iData = getIdx(["data_recebimento", "data", "recebimento", "dt_recebimento"], 6);
  const iSit = getIdx(["situacao", "situação", "status"], 7);

  for (let i = 1; i < linhas.length; i++) {
    const colunas = linhas[i].split(delimitador).map(c => c.trim().replace(/^["']|["']$/g, ""));
    const col = (idx, def) => (idx >= 0 && idx < colunas.length && colunas[idx]) ? colunas[idx] : def;
    
    const num = col(iNum, "");
    if (!num) continue;

    dadosLoteParaImportar.push({
      projeto: col(iProj, "STI"),
      sistema: (col(iSis, "SEI").toUpperCase().includes("START") ? "STARTGOV" : "SEI"),
      numero_processo: num,
      descricao: col(iDesc, ""),
      local_atual: col(iLocal, "Aguardando Monitoramento"),
      acao: col(iAcao, "Aguardando trâmite"),
      data_recebimento: col(iData, ""),
      situacao: col(iSit, "Em tramitação"),
      monitorar: 1
    });
  }

  if (dadosLoteParaImportar.length === 0) {
    statusBox.style.display = "block";
    statusBox.style.background = "#fef2f2";
    statusBox.style.color = "#b91c1c";
    statusBox.textContent = "Nenhum processo válido encontrado. Verifique a coluna com o Número do Processo.";
    previewBox.style.display = "none";
    btnConfirmar.disabled = true;
    return;
  }

  // Preenche a tabela de preview
  statusBox.style.display = "none";
  document.getElementById("lblQtdImportDetectados").textContent = dadosLoteParaImportar.length;
  
  let html = "";
  dadosLoteParaImportar.slice(0, 50).forEach(p => {
    html += `
      <tr style="border-bottom: 1px solid #f1f5f9;">
        <td style="padding: 6px 8px;"><span class="badge-${p.sistema.toLowerCase()}" style="padding: 2px 5px; border-radius: 4px; font-weight: 700; font-size: 10px;">${escapeHtml(p.sistema)}</span></td>
        <td style="padding: 6px 8px; font-family: monospace; font-weight: 600;">${escapeHtml(p.numero_processo)}</td>
        <td style="padding: 6px 8px; color: #0f172a;">${escapeHtml(p.projeto)}</td>
        <td style="padding: 6px 8px; color: #475569;">${escapeHtml(p.local_atual)}</td>
        <td style="padding: 6px 8px; color: #64748b;">${escapeHtml(p.data_recebimento || "-")}</td>
      </tr>
    `;
  });
  if (dadosLoteParaImportar.length > 50) {
    html += `<tr><td colspan="5" style="text-align: center; color: #64748b; font-size: 11px; padding: 6px;">... e mais ${dadosLoteParaImportar.length - 50} processos listados</td></tr>`;
  }

  tbody.innerHTML = html;
  previewBox.style.display = "block";
  btnConfirmar.disabled = false;
  btnConfirmar.innerHTML = `<span class="icon">🚀</span> Importar ${dadosLoteParaImportar.length} Processos`;
}

async function executarImportacaoLote() {
  if (dadosLoteParaImportar.length === 0) return;
  
  const btn = document.getElementById("btnConfirmarImportacao");
  const statusBox = document.getElementById("boxStatusImport");
  
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> Importando ${dadosLoteParaImportar.length} processos...`;
  
  statusBox.style.display = "block";
  statusBox.style.background = "#eff6ff";
  statusBox.style.color = "#1e40af";
  statusBox.textContent = "Processando registros no banco de dados...";

  try {
    const res = await fetch("/api/processos/importar-lote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ registros: dadosLoteParaImportar })
    });
    const json = await res.json();

    if (json.success) {
      statusBox.style.background = "#dcfce7";
      statusBox.style.color = "#15803d";
      statusBox.innerHTML = `
        <strong>✓ ${escapeHtml(json.message)}</strong><br>
        <span style="font-size: 11.5px;">Novos cadastrados: ${json.criados} | Atualizados: ${json.atualizados}</span>
        ${json.erros && json.erros.length > 0 ? `<br><span style="color: #b91c1c; font-size: 11px;">Avisos: ${json.erros.join("; ")}</span>` : ""}
      `;
      btn.innerHTML = `<span>✓</span> Importação Concluída!`;
      
      // Recarrega os dados do sistema
      carregarDados();
      setTimeout(() => {
        fecharModalImportacao();
      }, 2200);
    } else {
      statusBox.style.background = "#fef2f2";
      statusBox.style.color = "#b91c1c";
      statusBox.textContent = "Erro na importação: " + json.error;
      btn.disabled = false;
      btn.innerHTML = `<span class="icon">🚀</span> Tentar Novamente`;
    }
  } catch (err) {
    statusBox.style.background = "#fef2f2";
    statusBox.style.color = "#b91c1c";
    statusBox.textContent = "Erro de conexão ao importar: " + err.message;
    btn.disabled = false;
    btn.innerHTML = `<span class="icon">🚀</span> Tentar Novamente`;
  }
}

// -------------------------------------------------------------
// PAINEL DE GARGALOS & CUMPRIMENTO DE SLA
// -------------------------------------------------------------
async function abrirModalGargalos() {
  const modal = document.getElementById("modalGargalos");
  if (!modal) return;
  modal.style.display = "flex";
  await carregarMetricasGargalos();
}

function fecharModalGargalos() {
  const modal = document.getElementById("modalGargalos");
  if (modal) modal.style.display = "none";
}

async function carregarMetricasGargalos() {
  const s15 = document.getElementById("gargaloSla15");
  const s30 = document.getElementById("gargaloSla30");
  const s60 = document.getElementById("gargaloSla60");
  const sMais60 = document.getElementById("gargaloSlaMais60");
  const lblMedia = document.getElementById("gargaloMediaGeral");
  const containerSetores = document.getElementById("listaGargalosSetores");
  const containerTop = document.getElementById("listaGargalosTopAtrasados");

  containerSetores.innerHTML = `<div style="text-align: center; color: #64748b; font-size: 12px; padding: 20px;">Carregando indicadores...</div>`;
  containerTop.innerHTML = `<div style="text-align: center; color: #64748b; font-size: 12px; padding: 20px;">Carregando processos críticos...</div>`;

  try {
    const res = await fetch("/api/metricas/gargalos");
    const json = await res.json();
    if (json.success && json.data) {
      const d = json.data;
      const faixas = d.faixas_sla || {};

      if (s15) s15.textContent = faixas.ate_15_dias || 0;
      if (s30) s30.textContent = faixas.de_16_a_30 || 0;
      if (s60) s60.textContent = faixas.de_31_a_60 || 0;
      if (sMais60) sMais60.textContent = faixas.mais_de_60 || 0;
      if (lblMedia) lblMedia.textContent = `Média Geral: ${d.media_dias_geral || 0} dias`;

      // Renderiza Setores com barras proporcionais
      const setores = d.por_setor || [];
      if (setores.length === 0) {
        containerSetores.innerHTML = `<div style="color: #64748b; font-size: 12px; text-align: center;">Nenhum setor com processos ativos.</div>`;
      } else {
        const maxQtd = Math.max(...setores.map(s => s.total), 1);
        let htmlSetores = "";
        setores.forEach(s => {
          const pct = Math.round((s.total / maxQtd) * 100);
          const corBadge = s.media_dias > 60 ? "#ef4444" : (s.media_dias > 30 ? "#f59e0b" : "#2563eb");
          htmlSetores += `
            <div class="gargalo-setor-item">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; font-size: 12px;">
                <strong style="color: #0f172a; max-width: 220px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(s.setor)}">${escapeHtml(s.setor)}</strong>
                <span style="font-weight: 700; color: ${corBadge};">${s.total} proc. (Média: ${s.media_dias}d)</span>
              </div>
              <div style="background: #e2e8f0; height: 6px; border-radius: 9999px; overflow: hidden;">
                <div style="background: ${corBadge}; width: ${pct}%; height: 100%; border-radius: 9999px;"></div>
              </div>
            </div>
          `;
        });
        containerSetores.innerHTML = htmlSetores;
      }

      // Renderiza Top Processos Críticos
      const top = d.top_atrasados || [];
      if (top.length === 0) {
        containerTop.innerHTML = `<div style="color: #16a34a; font-size: 12px; text-align: center; padding: 20px;">✓ Nenhum processo com atraso crítico registrado!</div>`;
      } else {
        let htmlTop = "";
        top.forEach(p => {
          htmlTop += `
            <div class="gargalo-top-item">
              <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 700; font-family: monospace; font-size: 12px; color: #0f172a;">${escapeHtml(p.numero_processo)}</div>
                <div style="font-size: 11px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(p.projeto)} &bull; ${escapeHtml(p.local_atual)}</div>
              </div>
              <div style="text-align: right; margin-left: 10px;">
                <span style="background: #fee2e2; color: #dc2626; font-weight: 800; padding: 2px 6px; border-radius: 4px; font-size: 11px; white-space: nowrap;">
                  ${p.dias_no_setor} dias
                </span>
              </div>
            </div>
          `;
        });
        containerTop.innerHTML = htmlTop;
      }
    }
  } catch (err) {
    containerSetores.innerHTML = `<div style="color: #ef4444; font-size: 12px;">Falha ao carregar métricas.</div>`;
    containerTop.innerHTML = `<div style="color: #ef4444; font-size: 12px;">Falha ao carregar métricas.</div>`;
  }
}
