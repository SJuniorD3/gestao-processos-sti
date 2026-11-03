import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import datetime
import threading
import webbrowser
import csv
import urllib.parse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import (
    REPORT_HOURS, SEI_URL, SEI_USER, SEI_PASS,
    STARTGOV_URL, STARTGOV_USER, STARTGOV_PASS
)
from database import (
    init_db, listar_projetos_com_processos, listar_processos,
    obter_processo, criar_processo, atualizar_processo, excluir_processo,
    obter_ou_criar_projeto, obter_projeto, atualizar_projeto, excluir_projeto,
    formatar_data_br, formatar_data_hora_br, parse_date
)
from scheduler import scheduler
from notifier import gerar_conteudo_resumo, executar_envio_resumo
from monitor_engine import executar_monitoramento_processos, monitorar_processo_individual

class SistemaProcessosGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("STI - Sistema de Gestão e Monitoramento de Processos por Projeto - v2.0")
        self.root.geometry("1340x780")
        self.root.minsize(1100, 680)

        # Inicializa banco de dados e agendador
        init_db()
        scheduler.start()

        self.projetos_cache = []

        # Constrói a interface
        self._construir_interface()

        # Carga inicial
        self.recarregar_dados()

        # Atualização periódica do relógio e agendador
        self._atualizar_relogio_agendador()

    def _construir_interface(self):
        # 1. TOPO / CABEÇALHO
        top_frame = tk.Frame(self.root, bg="#0f172a", height=65)
        top_frame.pack(fill=tk.X, side=tk.TOP)

        title_box = tk.Frame(top_frame, bg="#0f172a")
        title_box.pack(side=tk.LEFT, padx=20, pady=10)

        badge_lbl = tk.Label(
            title_box, text="STI v2.0", bg="#2563eb", fg="white",
            font=("Segoe UI", 12, "bold"), padx=10, pady=2
        )
        badge_lbl.pack(side=tk.LEFT, padx=(0, 10))

        text_sub_box = tk.Frame(title_box, bg="#0f172a")
        text_sub_box.pack(side=tk.LEFT)

        main_title = tk.Label(
            text_sub_box, text="Superintendência de Tecnologia da Informação",
            bg="#0f172a", fg="white", font=("Segoe UI", 13, "bold")
        )
        main_title.pack(anchor="w")

        sub_title = tk.Label(
            text_sub_box, text="Gestão por Projeto • Acesso Direto aos Processos (v2.0)",
            bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 9)
        )
        sub_title.pack(anchor="w")

        self.sched_status_lbl = tk.Label(
            top_frame, text="Agendador Ativo (08:00, 12:00, 16:00)",
            bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 9, "bold"),
            padx=14, pady=6, relief="groove", bd=1
        )
        self.sched_status_lbl.pack(side=tk.RIGHT, padx=20, pady=12)

        # 2. CARDS DE KPIS
        kpi_frame = tk.Frame(self.root, bg="#f1f5f9", pady=10)
        kpi_frame.pack(fill=tk.X, padx=15)

        self.kpi_projetos = self._criar_kpi_card(kpi_frame, "Total de Projetos", "0", "#0f172a")
        self.kpi_monitorados = self._criar_kpi_card(kpi_frame, "Processos Monitorados", "0", "#059669")
        self.kpi_sti = self._criar_kpi_card(kpi_frame, "No Setor STI", "0", "#2563eb")
        self.kpi_outros = self._criar_kpi_card(kpi_frame, "Em Outros Setores", "0", "#475569")
        self.kpi_alertas = self._criar_kpi_card(kpi_frame, "Em Alerta (>60 dias)", "0", "#dc2626")

        # 3. BARRA DE FERRAMENTAS E FILTROS
        toolbar = tk.Frame(self.root, bg="#e2e8f0", pady=8, padx=15)
        toolbar.pack(fill=tk.X)

        tk.Label(toolbar, text="Pesquisar:", bg="#e2e8f0", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.entry_busca = ttk.Entry(toolbar, width=22)
        self.entry_busca.pack(side=tk.LEFT, padx=(0, 10))
        self.entry_busca.bind("<KeyRelease>", lambda e: self.filtrar_projetos())

        tk.Label(toolbar, text="Local:", bg="#e2e8f0", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 4))
        self.combo_local = ttk.Combobox(toolbar, values=["Todos", "STI/SEDUC", "SAOFC/SEDUC", "SUMES"], width=13, state="readonly")
        self.combo_local.set("Todos")
        self.combo_local.pack(side=tk.LEFT, padx=(0, 10))
        self.combo_local.bind("<<ComboboxSelected>>", lambda e: self.filtrar_projetos())

        tk.Label(toolbar, text="Sistema:", bg="#e2e8f0", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 4))
        self.combo_sistema = ttk.Combobox(toolbar, values=["Todos", "SEI", "STARTGOV"], width=10, state="readonly")
        self.combo_sistema.set("Todos")
        self.combo_sistema.pack(side=tk.LEFT, padx=(0, 10))
        self.combo_sistema.bind("<<ComboboxSelected>>", lambda e: self.filtrar_projetos())

        tk.Label(toolbar, text="Monitorar:", bg="#e2e8f0", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 4))
        self.combo_monit = ttk.Combobox(toolbar, values=["Somente Monitorados", "Todos os Processos"], width=18, state="readonly")
        self.combo_monit.set("Somente Monitorados")
        self.combo_monit.pack(side=tk.LEFT, padx=(0, 10))
        self.combo_monit.bind("<<ComboboxSelected>>", lambda e: self.filtrar_projetos())

        # Botões de Ação na Toolbar
        btn_novo = tk.Button(
            toolbar, text="➕ Novo Processo", bg="#2563eb", fg="white",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=3,
            command=self.abrir_dialog_novo_processo
        )
        btn_novo.pack(side=tk.RIGHT, padx=4)

        btn_editar_proj_top = tk.Button(
            toolbar, text="✏️ Editar Projeto", bg="#f3f4f6", fg="#111827",
            font=("Segoe UI", 9, "bold"), relief="solid", bd=1, padx=10, pady=3,
            command=lambda: self.abrir_dialog_editar_projeto()
        )
        btn_editar_proj_top.pack(side=tk.RIGHT, padx=4)

        btn_sync = tk.Button(
            toolbar, text="🔄 Sincronizar Sistemas", bg="#047857", fg="white",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=3,
            command=self.sincronizar_sistemas_gui
        )
        btn_sync.pack(side=tk.RIGHT, padx=4)

        btn_disparar = tk.Button(
            toolbar, text="⚡ Disparar Resumo Agora", bg="#d97706", fg="white",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=3,
            command=self.disparar_resumo_manual
        )
        btn_disparar.pack(side=tk.RIGHT, padx=4)

        btn_preview = tk.Button(
            toolbar, text="👁️ Ver Resumo", bg="#475569", fg="white",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=3,
            command=self.abrir_dialog_preview
        )
        btn_preview.pack(side=tk.RIGHT, padx=4)

        # 4. TABELA ESTILO PLANILHA COM CÉLULAS MESCLADAS E LINHAS FINAS
        table_container = tk.Frame(self.root, bg="#ffffff", padx=15, pady=8)
        table_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(table_container, bg="white", highlightthickness=0)
        self.scroll_y = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scroll_x = ttk.Scrollbar(table_container, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        # Cor de fundo define a cor das linhas finas da grade (cinza claro suave de 1px)
        self.grid_frame = tk.Frame(self.canvas, bg="#d1d5db")

        self.grid_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.scroll_x.grid(row=1, column=0, sticky="ew")

        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

        # Suporte ao scroll com a roda do mouse
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # 5. BARRA DE BOTÕES INFERIOR
        btn_bar = tk.Frame(self.root, bg="#f8fafc", pady=8, padx=15)
        btn_bar.pack(fill=tk.X)

        btn_export = tk.Button(
            btn_bar, text="📥 Exportar Excel (CSV)",
            bg="#e2e8f0", fg="#0f172a", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=12, pady=5, command=self.exportar_csv
        )
        btn_export.pack(side=tk.RIGHT, padx=5)

        btn_refresh = tk.Button(
            btn_bar, text="🔄 Atualizar Lista",
            bg="#e2e8f0", fg="#0f172a", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=12, pady=5, command=self.recarregar_dados
        )
        btn_refresh.pack(side=tk.RIGHT, padx=5)

        btn_sistemas = tk.Button(
            btn_bar, text="🔑 Acesso SEI / STARTGOV",
            bg="#0f172a", fg="white", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=12, pady=5, command=self.abrir_dialog_sistemas
        )
        btn_sistemas.pack(side=tk.LEFT, padx=5)

        # 6. RODAPÉ DE STATUS
        self.status_bar = tk.Label(
            self.root, text="Pronto.",
            bg="#e2e8f0", fg="#475569", anchor="w", font=("Segoe UI", 8), padx=10, pady=3
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _criar_kpi_card(self, parent, titulo, valor_inicial, cor_destaque):
        card = tk.Frame(parent, bg="white", relief="groove", bd=1, padx=15, pady=8)
        card.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        t_lbl = tk.Label(card, text=titulo.upper(), font=("Segoe UI", 8, "bold"), fg="#64748b", bg="white")
        t_lbl.pack(anchor="w")

        v_lbl = tk.Label(card, text=valor_inicial, font=("Segoe UI", 16, "bold"), fg=cor_destaque, bg="white")
        v_lbl.pack(anchor="w")
        return v_lbl

    def _atualizar_relogio_agendador(self):
        agora = datetime.datetime.now()
        info = scheduler.get_info()
        txt = f"Horários: 08:00, 12:00, 16:00 | Próximo Envio: {info['proximo_disparo']} | Agora: {agora.strftime('%H:%M:%S')}"
        self.sched_status_lbl.config(text=txt)
        self.root.after(1000, self._atualizar_relogio_agendador)

    def recarregar_dados(self):
        self.projetos_cache = listar_projetos_com_processos(apenas_monitorados=False)
        self.filtrar_projetos()

        total_projetos = len(self.projetos_cache)
        todos_procs = []
        for p in self.projetos_cache:
            todos_procs.extend(p.get("processos", []))

        total_procs = len(todos_procs)
        monitorados = sum(1 for p in todos_procs if p.get("monitorar", 1) == 1)
        sti = sum(1 for p in todos_procs if "STI" in p["local_atual"].upper() and p.get("monitorar", 1) == 1)
        outros = monitorados - sti
        alertas = sum(1 for p in todos_procs if (p["dias_no_setor"] or 0) > 60 and p.get("monitorar", 1) == 1)

        self.kpi_projetos.config(text=str(total_projetos))
        self.kpi_monitorados.config(text=str(monitorados))
        self.kpi_sti.config(text=str(sti))
        self.kpi_outros.config(text=str(outros))
        self.kpi_alertas.config(text=str(alertas))

        self.status_bar.config(text=f"{total_projetos} projetos cadastrados com {monitorados} processos monitorados nos resumos.")

    def filtrar_projetos(self):
        """Renderiza a grade no estilo planilha limpa, sem cores chamativas e com linhas finas de 1px."""
        texto = self.entry_busca.get().lower().strip()
        local = self.combo_local.get()
        sistema = self.combo_sistema.get()
        monit = self.combo_monit.get()

        # Limpa widgets anteriores
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        # CABEÇALHOS (Neutro, limpo, fundo cinza claro sutil com texto preto e linhas finas)
        headers = [
            "PROJETO",
            "SISTEMA",
            "Nº PROCESSO (CLIQUE P/ ABRIR)",
            "DESCRIÇÃO",
            "LOCAL",
            "AÇÃO",
            "DATA REC.",
            "SITUAÇÃO",
            "DIAS",
            "OPÇÕES"
        ]

        for col_idx, h_title in enumerate(headers):
            h_lbl = tk.Label(
                self.grid_frame, text=h_title, bg="#f3f4f6", fg="#111827",
                font=("Segoe UI", 9, "bold"), padx=8, pady=6, relief="flat", bd=0
            )
            h_lbl.grid(row=0, column=col_idx, sticky="nsew", padx=1, pady=1)

        current_row = 1

        for proj in self.projetos_cache:
            procs = proj.get("processos", [])
            procs_filtrados = []

            for p in procs:
                if texto:
                    txt_alvo = f"{p['numero_processo']} {proj['nome']} {proj['descricao']} {p['acao']} {p['situacao']}".lower()
                    if texto not in txt_alvo:
                        continue

                if local != "Todos" and p["local_atual"] != local:
                    continue

                if sistema != "Todos" and p["sistema"].upper() != sistema.upper():
                    continue

                is_monit = (p.get("monitorar", 1) == 1)
                if monit == "Somente Monitorados" and not is_monit:
                    continue

                procs_filtrados.append(p)

            if not procs_filtrados and (texto or local != "Todos" or sistema != "Todos" or monit == "Somente Monitorados"):
                continue

            total_p = len(procs_filtrados)
            if total_p == 0:
                continue

            # CÉLULA MESCLADA DO PROJETO (Fundo branco limpo, sem amarelo, linha fina)
            proj_cell_frame = tk.Frame(self.grid_frame, bg="white", relief="flat", bd=0)
            proj_cell_frame.grid(row=current_row, column=0, rowspan=total_p, sticky="nsew", padx=1, pady=1)

            lbl_proj_nome = tk.Label(
                proj_cell_frame, text=proj["nome"], bg="white", fg="#111827",
                font=("Segoe UI", 10, "bold"), padx=10, pady=8, cursor="hand2"
            )
            lbl_proj_nome.pack(expand=True)
            lbl_proj_nome.bind("<Double-1>", lambda e, p_id=proj["id"]: self.abrir_dialog_editar_projeto(p_id))

            btn_box_p = tk.Frame(proj_cell_frame, bg="white")
            btn_box_p.pack(pady=(0, 6))

            btn_ed_proj = tk.Button(
                btn_box_p, text="✏️ Editar Projeto", bg="#f3f4f6", fg="#374151",
                font=("Segoe UI", 7), relief="solid", bd=1, padx=4, pady=1,
                command=lambda p_id=proj["id"]: self.abrir_dialog_editar_projeto(p_id)
            )
            btn_ed_proj.pack(side=tk.LEFT, padx=2)

            btn_add_proc = tk.Button(
                btn_box_p, text="➕ Add Processo", bg="#f3f4f6", fg="#374151",
                font=("Segoe UI", 7), relief="solid", bd=1, padx=4, pady=1,
                command=lambda p_nome=proj["nome"]: self.abrir_dialog_novo_processo(projeto_padrao=p_nome)
            )
            btn_add_proc.pack(side=tk.LEFT, padx=2)

            # CÉLULA MESCLADA DA DESCRIÇÃO (Fundo branco limpo, linha fina)
            desc_cell = tk.Label(
                self.grid_frame, text=proj["descricao"] or "-", bg="white", fg="#374151",
                font=("Segoe UI", 8), wraplength=190, justify="left", padx=8, pady=6,
                relief="flat", bd=0, cursor="hand2"
            )
            desc_cell.grid(row=current_row, column=3, rowspan=total_p, sticky="nsew", padx=1, pady=1)
            desc_cell.bind("<Double-1>", lambda e, p_id=proj["id"]: self.abrir_dialog_editar_projeto(p_id))

            # LINHAS INDIVIDUAIS DE CADA PROCESSO VINCULADO
            for idx_p, p in enumerate(procs_filtrados):
                r = current_row + idx_p

                # 1. SISTEMA (Texto preto limpo)
                lbl_sis = tk.Label(
                    self.grid_frame, text=p["sistema"], bg="white", fg="#111827",
                    font=("Segoe UI", 9), padx=6, pady=5, relief="flat", bd=0
                )
                lbl_sis.grid(row=r, column=1, sticky="nsew", padx=1, pady=1)

                # 2. Nº PROCESSO (Link Clicável para abrir o processo diretamente no portal oficial)
                lbl_num = tk.Label(
                    self.grid_frame, text=p["numero_processo"], bg="white", fg="#1d4ed8",
                    font=("Consolas", 9, "bold", "underline"), padx=6, pady=5, relief="flat", bd=0,
                    cursor="hand2"
                )
                lbl_num.grid(row=r, column=2, sticky="nsew", padx=1, pady=1)

                # Feedback visual de hover e eventos de clique
                lbl_num.bind("<Enter>", lambda e, lbl=lbl_num: lbl.config(fg="#1e40af", bg="#eff6ff"))
                lbl_num.bind("<Leave>", lambda e, lbl=lbl_num: lbl.config(fg="#1d4ed8", bg="white"))
                lbl_num.bind("<Button-1>", lambda e, proc=p: self.abrir_processo_direto(proc))
                lbl_num.bind("<Button-3>", lambda e, proc=p: self.mostrar_menu_processo(e, proc))

                # 3. LOCAL (Texto preto limpo)
                lbl_loc = tk.Label(
                    self.grid_frame, text=p["local_atual"] or "Aguardando", bg="white", fg="#111827",
                    font=("Segoe UI", 9), padx=6, pady=5, relief="flat", bd=0
                )
                lbl_loc.grid(row=r, column=4, sticky="nsew", padx=1, pady=1)

                # 4. AÇÃO (Texto preto limpo)
                lbl_acao = tk.Label(
                    self.grid_frame, text=p["acao"] or "-", bg="white", fg="#111827",
                    font=("Segoe UI", 8), wraplength=180, justify="left", padx=6, pady=5,
                    relief="flat", bd=0
                )
                lbl_acao.grid(row=r, column=5, sticky="nsew", padx=1, pady=1)

                # 5. DATA RECEBIMENTO (Formato DD/MM/AAAA)
                data_rec_fmt = formatar_data_br(p["data_recebimento"]) if p["data_recebimento"] else "-"
                lbl_data = tk.Label(
                    self.grid_frame, text=data_rec_fmt, bg="white", fg="#111827",
                    font=("Segoe UI", 8), padx=6, pady=5, relief="flat", bd=0
                )
                lbl_data.grid(row=r, column=6, sticky="nsew", padx=1, pady=1)

                # 6. SITUAÇÃO (Texto preto limpo)
                lbl_sit = tk.Label(
                    self.grid_frame, text=p["situacao"] or "-", bg="white", fg="#111827",
                    font=("Segoe UI", 8), wraplength=180, justify="left", padx=6, pady=5,
                    relief="flat", bd=0
                )
                lbl_sit.grid(row=r, column=7, sticky="nsew", padx=1, pady=1)

                # 7. DIAS NO SETOR (Texto preto limpo, sem cores chamativas)
                dias_val = p["dias_no_setor"]
                dias_str = str(dias_val) if dias_val is not None else "-"
                lbl_dias = tk.Label(
                    self.grid_frame, text=dias_str, bg="white", fg="#111827",
                    font=("Segoe UI", 9), padx=6, pady=5, relief="flat", bd=0
                )
                lbl_dias.grid(row=r, column=8, sticky="nsew", padx=1, pady=1)

                # 8. OPÇÕES E AÇÕES (Botões neutros e discretos)
                ops_frame = tk.Frame(self.grid_frame, bg="white", relief="flat", bd=0, padx=4, pady=3)
                ops_frame.grid(row=r, column=9, sticky="nsew", padx=1, pady=1)

                p_id = p["id"]
                p_num = p["numero_processo"]

                btn_s4 = tk.Button(
                    ops_frame, text="📜 4 Status", bg="#f3f4f6", fg="#111827",
                    font=("Segoe UI", 8), relief="solid", bd=1, padx=4, pady=1,
                    command=lambda proc_id=p_id: self.abrir_dialog_status(proc_id)
                )
                btn_s4.pack(side=tk.LEFT, padx=2)

                btn_sync_p = tk.Button(
                    ops_frame, text="🔄", bg="#f3f4f6", fg="#111827",
                    font=("Segoe UI", 8), relief="solid", bd=1, padx=4, pady=1,
                    command=lambda proc_id=p_id, num=p_num: self.sincronizar_processo(proc_id, num)
                )
                btn_sync_p.pack(side=tk.LEFT, padx=2)

                btn_ed = tk.Button(
                    ops_frame, text="✏️", bg="#f3f4f6", fg="#111827",
                    font=("Segoe UI", 8), relief="solid", bd=1, padx=4, pady=1,
                    command=lambda proc_id=p_id: self.abrir_dialog_editar(proc_id)
                )
                btn_ed.pack(side=tk.LEFT, padx=2)

                btn_del = tk.Button(
                    ops_frame, text="🗑️", bg="#f3f4f6", fg="#111827",
                    font=("Segoe UI", 8), relief="solid", bd=1, padx=4, pady=1,
                    command=lambda proc_id=p_id, num=p_num: self.excluir_processo(proc_id, num)
                )
                btn_del.pack(side=tk.LEFT, padx=2)

            current_row += total_p

        if current_row == 1:
            empty_cell = tk.Label(
                self.grid_frame,
                text="Nenhum processo cadastrado no momento.\nO sistema está 100% zerado e pronto para você cadastrar os processos.\nClique no botão '➕ Novo Processo' acima para iniciar.",
                bg="white", fg="#4b5563", font=("Segoe UI", 10),
                padx=20, pady=35, relief="flat", bd=0, justify="center"
            )
            empty_cell.grid(row=1, column=0, columnspan=len(headers), sticky="nsew", padx=1, pady=1)

    # ---------------------------------------------------------
    # ACESSO DIRETO AO PROCESSO NO PORTAL OFICIAL (SEI / STARTGOV)
    # ---------------------------------------------------------
    def abrir_processo_direto(self, proc):
        """
        Abre o processo diretamente no portal oficial (SEI ou STARTGOV) no navegador padrão,
        copia o número do processo para a Área de Transferência e exibe status na barra inferior.
        """
        num = proc.get("numero_processo", "").strip()
        sistema = (proc.get("sistema") or "SEI").upper()

        # Copia o número para a área de transferência do Windows (Ctrl+V pronto para uso)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(num)
            self.root.update()
        except Exception:
            pass

        url_alvo = ""
        if "SEI" in sistema:
            # Portal SEI - se já estiver autenticado no navegador, cai direto na tela de controle
            url_alvo = "https://sei.ma.gov.br/sei/controlador.php?acao=procedimento_controlar"
        elif "STARTGOV" in sistema:
            # Portal StartGov - com busca direta pelo número
            url_alvo = f"https://bid.startgov.com.br/processos?type=all&search={urllib.parse.quote(num)}"
        else:
            url_alvo = "https://sei.ma.gov.br"

        try:
            webbrowser.open(url_alvo)
            self.status_bar.config(
                text=f"🌐 Abrindo portal {sistema} para o processo {num}... | Nº copiado para a Área de Transferência (Ctrl+V)!",
                fg="#1d4ed8"
            )
        except Exception as e:
            messagebox.showerror("Erro ao Abrir Navegador", f"Não foi possível abrir o navegador:\n{e}", parent=self.root)

    def mostrar_menu_processo(self, event, proc):
        """Menu de contexto ao clicar com o botão direito no número do processo."""
        num = proc.get("numero_processo", "").strip()
        sistema = (proc.get("sistema") or "SEI").upper()

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(
            label=f"🌐 Abrir no Portal {sistema} (Navegador)",
            command=lambda: self.abrir_processo_direto(proc)
        )
        menu.add_command(
            label=f"📋 Copiar Nº ({num})",
            command=lambda: self.copiar_numero_processo(num)
        )
        if "SEI" in sistema:
            menu.add_command(
                label="🔍 Pesquisa Pública do SEI (GOVMA)",
                command=lambda: webbrowser.open("https://sei.ma.gov.br/sei/controlador_externo.php?acao=pesquisa_processo&id_orgao_acesso_externo=0")
            )
        menu.add_separator()
        menu.add_command(
            label="📜 Ver Histórico e Detalhes no Sistema",
            command=lambda: self.abrir_dialog_status(proc["id"])
        )
        menu.tk_popup(event.x_root, event.y_root)

    def copiar_numero_processo(self, num):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(num)
            self.root.update()
            self.status_bar.config(
                text=f"✓ Número {num} copiado para a Área de Transferência (Ctrl+V pronto)!",
                fg="#059669"
            )
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível copiar: {e}", parent=self.root)

    # ---------------------------------------------------------
    # GESTÃO DE PROJETOS E PROCESSOS
    # ---------------------------------------------------------
    def abrir_dialog_editar_projeto(self, proj_id=None):
        if not proj_id:
            if not self.projetos_cache:
                messagebox.showinfo("Aviso", "Nenhum projeto cadastrado no momento.", parent=self.root)
                return
            if len(self.projetos_cache) == 1:
                proj_id = self.projetos_cache[0]["id"]
            else:
                proj_id = self._selecionar_projeto_dialog()
                if not proj_id:
                    return

        proj = obter_projeto(proj_id)
        if not proj:
            messagebox.showerror("Erro", "Projeto não encontrado no banco de dados.", parent=self.root)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Editar Projeto - {proj['nome']}")
        dlg.geometry("560x420")
        dlg.transient(self.root)
        dlg.grab_set()

        frame = tk.Frame(dlg, padx=20, pady=18)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame, text="EDITAR DADOS DO PROJETO",
            font=("Segoe UI", 11, "bold"), fg="#111827"
        ).pack(anchor="w", pady=(0, 12))

        tk.Label(frame, text="Nome do Projeto *", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        ent_nome = ttk.Entry(frame, width=50)
        ent_nome.insert(0, proj["nome"])
        ent_nome.pack(fill=tk.X, pady=(0, 10))

        tk.Label(frame, text="Descrição / Itens / Objeto do Projeto:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        txt_desc = tk.Text(frame, wrap=tk.WORD, height=4, font=("Segoe UI", 9))
        if proj.get("descricao"):
            txt_desc.insert(tk.END, proj["descricao"])
        txt_desc.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Identificar processos vinculados
        procs_vinculados = []
        for p_item in self.projetos_cache:
            if p_item["id"] == proj_id:
                procs_vinculados = p_item.get("processos", [])
                break

        resumo_sistemas = {}
        for p in procs_vinculados:
            resumo_sistemas[p["sistema"]] = resumo_sistemas.get(p["sistema"], 0) + 1
        sis_desc = ", ".join([f"{k}: {v}" for k, v in resumo_sistemas.items()]) or "nenhum"

        lbl_info = tk.Label(
            frame,
            text=f"ℹ️ Processos vinculados: {len(procs_vinculados)} ({sis_desc}).",
            font=("Segoe UI", 8, "italic"), fg="#4b5563"
        )
        lbl_info.pack(anchor="w", pady=(0, 12))

        btn_box = tk.Frame(frame)
        btn_box.pack(fill=tk.X, pady=(10, 0))

        def salvar():
            novo_nome = ent_nome.get().strip()
            nova_desc = txt_desc.get("1.0", tk.END).strip()
            if not novo_nome:
                messagebox.showwarning("Atenção", "O nome do projeto não pode ficar em branco.", parent=dlg)
                return

            try:
                atualizar_projeto(proj_id, novo_nome, nova_desc)
                messagebox.showinfo("Sucesso", f"Projeto '{novo_nome}' atualizado com sucesso!", parent=dlg)
                dlg.destroy()
                self.recarregar_dados()
            except Exception as e:
                messagebox.showerror("Erro ao Salvar", str(e), parent=dlg)

        def excluir():
            msg = f"Tem certeza que deseja excluir o projeto '{proj['nome']}'?\n\nATENÇÃO: Todos os {len(procs_vinculados)} processo(s) vinculado(s) também serão excluídos!"
            if messagebox.askyesno("Confirmar Exclusão de Projeto", msg, parent=dlg):
                try:
                    excluir_projeto(proj_id)
                    messagebox.showinfo("Projeto Excluído", f"Projeto '{proj['nome']}' excluído com sucesso.", parent=self.root)
                    dlg.destroy()
                    self.recarregar_dados()
                except Exception as e:
                    messagebox.showerror("Erro ao Excluir", str(e), parent=dlg)

        btn_salvar = tk.Button(
            btn_box, text="💾 Salvar Alterações", bg="#2563eb", fg="white",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=5, command=salvar
        )
        btn_salvar.pack(side=tk.RIGHT, padx=5)

        btn_cancelar = tk.Button(
            btn_box, text="Cancelar", bg="#e2e8f0", fg="#374151",
            font=("Segoe UI", 9), relief="flat", padx=12, pady=5, command=dlg.destroy
        )
        btn_cancelar.pack(side=tk.RIGHT, padx=5)

        btn_del_proj = tk.Button(
            btn_box, text="🗑️ Excluir Projeto", bg="#fee2e2", fg="#dc2626",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=5, command=excluir
        )
        btn_del_proj.pack(side=tk.LEFT)

    def _selecionar_projeto_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Selecionar Projeto para Editar")
        dlg.geometry("400x190")
        dlg.transient(self.root)
        dlg.grab_set()

        selected_id = [None]

        frame = tk.Frame(dlg, padx=20, pady=18)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Selecione o Projeto que deseja editar:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 10))

        opcoes = [f"{p['nome']} (ID: {p['id']})" for p in self.projetos_cache]
        id_map = {f"{p['nome']} (ID: {p['id']})": p['id'] for p in self.projetos_cache}

        combo = ttk.Combobox(frame, values=opcoes, state="readonly", width=38)
        combo.current(0)
        combo.pack(fill=tk.X, pady=(0, 15))

        def confirmar():
            sel = combo.get()
            if sel in id_map:
                selected_id[0] = id_map[sel]
            dlg.destroy()

        btn_box = tk.Frame(frame)
        btn_box.pack(fill=tk.X)

        btn_ok = tk.Button(btn_box, text="Continuar", bg="#2563eb", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=4, command=confirmar)
        btn_ok.pack(side=tk.RIGHT, padx=5)

        btn_cancel = tk.Button(btn_box, text="Cancelar", bg="#e2e8f0", fg="#374151", font=("Segoe UI", 9), relief="flat", padx=10, pady=4, command=dlg.destroy)
        btn_cancel.pack(side=tk.RIGHT)

        self.root.wait_window(dlg)
        return selected_id[0]

    def abrir_dialog_novo_processo(self, projeto_padrao=""):
        self._dialog_salvar_processo(titulo="Cadastrar Novo Processo / Projeto", projeto_padrao=projeto_padrao)

    def abrir_dialog_editar(self, proc_id):
        proc = obter_processo(proc_id)
        if not proc:
            return
        self._dialog_salvar_processo(titulo=f"Atualizar Processo {proc['numero_processo']}", processo=proc)

    def _dialog_salvar_processo(self, titulo, processo=None, projeto_padrao=""):
        dlg = tk.Toplevel(self.root)
        dlg.title(titulo)
        dlg.geometry("560x650")
        dlg.transient(self.root)
        dlg.grab_set()

        frame = tk.Frame(dlg, padx=20, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)

        def add_field(label_text, default=""):
            lbl = tk.Label(frame, text=label_text, font=("Segoe UI", 9, "bold"))
            lbl.pack(anchor="w", pady=(5, 1))
            entry = ttk.Entry(frame, width=55)
            entry.insert(0, default)
            entry.pack(fill=tk.X)
            return entry

        # SEÇÃO 1: PROJETO E SISTEMA
        sec1_lbl = tk.Label(
            frame, text="1. DADOS DO PROJETO E DO SISTEMA",
            font=("Segoe UI", 9, "bold"), fg="#1e3a8a"
        )
        sec1_lbl.pack(anchor="w", pady=(0, 6))

        lbl_proj = tk.Label(frame, text="Projeto * (Digite ou selecione o nome do projeto)", font=("Segoe UI", 9, "bold"))
        lbl_proj.pack(anchor="w", pady=(5, 1))

        nomes_projetos = [p["nome"] for p in self.projetos_cache]

        combo_proj = ttk.Combobox(frame, values=nomes_projetos)
        val_inicial_proj = processo["projeto"] if processo else (projeto_padrao or (nomes_projetos[0] if nomes_projetos else ""))
        combo_proj.set(val_inicial_proj)
        combo_proj.pack(fill=tk.X)

        entry_desc = add_field(
            "Descrição / Objeto do Projeto (Opcional)",
            processo["descricao"] if processo else ""
        )

        def on_change_proj(e=None):
            p_sel = combo_proj.get().strip().upper()
            for pr in self.projetos_cache:
                if pr["nome"].upper() == p_sel and pr.get("descricao"):
                    entry_desc.delete(0, tk.END)
                    entry_desc.insert(0, pr["descricao"])
                    break
        combo_proj.bind("<<ComboboxSelected>>", on_change_proj)

        lbl_sis = tk.Label(frame, text="Sistema *", font=("Segoe UI", 9, "bold"))
        lbl_sis.pack(anchor="w", pady=(5, 1))
        combo_sis = ttk.Combobox(frame, values=["SEI", "STARTGOV", "OUTRO"], state="readonly")
        combo_sis.set(processo["sistema"] if processo else "SEI")
        combo_sis.pack(fill=tk.X)

        entry_num = add_field(
            "Nº - Processo * (Obrigatório)",
            processo["numero_processo"] if processo else ""
        )

        # SEÇÃO 2: DADOS DE TRÂMITE (PREENCHIDOS PELO MONITORAMENTO)
        sep = ttk.Separator(frame, orient="horizontal")
        sep.pack(fill=tk.X, pady=10)

        sec2_box = tk.Frame(frame, bg="#f8fafc", padx=10, pady=6, relief="groove", bd=1)
        sec2_box.pack(fill=tk.X, pady=(0, 6))

        sec2_lbl = tk.Label(
            sec2_box, text="2. DADOS DE TRÂMITE (PREENCHIDOS PELO MONITORAMENTO)",
            font=("Segoe UI", 9, "bold"), fg="#0f172a", bg="#f8fafc"
        )
        sec2_lbl.pack(anchor="w")

        info_lbl = tk.Label(
            sec2_box,
            text="ℹ️ Os campos abaixo NÃO são obrigatórios no cadastro.\nEles serão preenchidos após o monitoramento nos portais.",
            font=("Segoe UI", 8), fg="#64748b", bg="#f8fafc", justify="left"
        )
        info_lbl.pack(anchor="w", pady=(2, 0))

        entry_local = add_field(
            "Local Atual (Opcional)",
            processo["local_atual"] if processo else ""
        )

        entry_data = add_field(
            "Data de Recebimento (DD/MM/AAAA) (Opcional)",
            formatar_data_br(processo["data_recebimento"]) if (processo and processo["data_recebimento"]) else ""
        )

        entry_acao = add_field(
            "Ação (Opcional)",
            processo["acao"] if processo else ""
        )

        entry_sit = add_field(
            "Situação (Opcional)",
            processo["situacao"] if processo else ""
        )

        var_monit = tk.IntVar(value=processo.get("monitorar", 1) if processo else 1)
        chk_monit = tk.Checkbutton(
            frame, text="Ativar monitoramento deste processo nos resumos diários (08h, 12h, 16h)",
            variable=var_monit, font=("Segoe UI", 9, "bold"), fg="#1e3a8a"
        )
        chk_monit.pack(anchor="w", pady=(10, 8))

        def salvar():
            num_proc = entry_num.get().strip()
            proj_nome = combo_proj.get().strip()
            if not num_proc or not proj_nome:
                messagebox.showerror(
                    "Campo Obrigatório",
                    "Por favor, informe o Nome do Projeto e o Nº do Processo.",
                    parent=dlg
                )
                return

            raw_dt = entry_data.get().strip()
            dt_obj = parse_date(raw_dt)
            dt_salvar = dt_obj.strftime("%d/%m/%Y") if dt_obj else (raw_dt if raw_dt and raw_dt != "-" else "")

            dados = {
                "projeto": proj_nome,
                "sistema": combo_sis.get().strip() or "SEI",
                "numero_processo": num_proc,
                "descricao": entry_desc.get().strip(),
                "local_atual": entry_local.get().strip(),
                "data_recebimento": dt_salvar,
                "acao": entry_acao.get().strip(),
                "situacao": entry_sit.get().strip(),
                "monitorar": var_monit.get()
            }

            try:
                if processo:
                    atualizar_processo(processo["id"], dados)
                    messagebox.showinfo("Sucesso", "Processo atualizado com sucesso!", parent=dlg)
                else:
                    criar_processo(dados)
                    messagebox.showinfo("Sucesso", f"Processo vinculado ao projeto '{proj_nome}' com sucesso!", parent=dlg)
                dlg.destroy()
                self.recarregar_dados()
            except Exception as e:
                messagebox.showerror("Erro ao Salvar", str(e), parent=dlg)

        btn_box = tk.Frame(frame)
        btn_box.pack(fill=tk.X, pady=(10, 0))

        btn_cancelar = tk.Button(btn_box, text="Cancelar", command=dlg.destroy, padx=12, pady=4)
        btn_cancelar.pack(side=tk.RIGHT, padx=5)

        btn_ok = tk.Button(btn_box, text="Salvar Processo", bg="#2563eb", fg="white", font=("Segoe UI", 9, "bold"), command=salvar, padx=15, pady=4)
        btn_ok.pack(side=tk.RIGHT)

    # ---------------------------------------------------------
    # 4 ÚLTIMOS STATUS
    # ---------------------------------------------------------
    def abrir_dialog_status(self, proc_id):
        proc = obter_processo(proc_id)
        if not proc:
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"4 Últimos Status - Processo {proc['numero_processo']}")
        dlg.geometry("680x480")
        dlg.transient(self.root)

        header = tk.Frame(dlg, bg="#1e3a8a", padx=15, pady=12)
        header.pack(fill=tk.X)

        title_sub_frame = tk.Frame(header, bg="#1e3a8a")
        title_sub_frame.pack(side=tk.LEFT)

        tk.Label(
            title_sub_frame, text=f"Projeto: {proc['projeto']}  •  Processo: {proc['numero_processo']} ({proc['sistema']})",
            font=("Segoe UI", 12, "bold"), fg="white", bg="#1e3a8a"
        ).pack(anchor="w")

        tk.Label(
            title_sub_frame, text=f"Local Atual: {proc['local_atual']} | {proc['dias_no_setor'] or 0} dias no setor",
            font=("Segoe UI", 9), fg="#93c5fd", bg="#1e3a8a"
        ).pack(anchor="w")

        btn_portal = tk.Button(
            header, text=f"🌐 Abrir no Portal {proc['sistema']}", bg="#2563eb", fg="white",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=4, cursor="hand2",
            command=lambda p=proc: self.abrir_processo_direto(p)
        )
        btn_portal.pack(side=tk.RIGHT, padx=5)

        body = tk.Frame(dlg, padx=20, pady=15)
        body.pack(fill=tk.BOTH, expand=True)

        sis_nome = proc.get("sistema", "SEI / STARTGOV").upper()
        tk.Label(
            body, text=f"📜 Histórico dos 4 Status Mais Recentes (Portal {sis_nome}):",
            font=("Segoe UI", 10, "bold"), fg="#1e293b"
        ).pack(anchor="w", pady=(0, 10))

        ultimos = proc.get("ultimos_4_status", [])
        if not ultimos:
            tk.Label(body, text="Nenhum status anterior registrado.", fg="#64748b").pack(pady=20)
        else:
            for idx, s in enumerate(ultimos):
                box = tk.Frame(body, bg="#f8fafc", relief="groove", bd=1, padx=12, pady=8)
                box.pack(fill=tk.X, pady=4)

                dt = formatar_data_hora_br(s.get("data_movimentacao") or s.get("data_registro", ""))
                rec_tag = " (Mais Recente - Posição Atual)" if idx == 0 else ""

                top_l = tk.Label(box, text=f"Linha {idx + 1}: [{dt}] - Setor: {s.get('local', '-')}{rec_tag}", font=("Segoe UI", 9, "bold"), fg="#2563eb", bg="#f8fafc")
                top_l.pack(anchor="w")

                sit_l = tk.Label(box, text=f"  Descrição: {s.get('situacao', '-')}", font=("Segoe UI", 9), fg="#0f172a", bg="#f8fafc")
                sit_l.pack(anchor="w")

                if s.get("observacao") and s.get("observacao") != "SEI Oficial":
                    obs_l = tk.Label(box, text=f"  {s.get('observacao')}", font=("Segoe UI", 8), fg="#64748b", bg="#f8fafc")
                    obs_l.pack(anchor="w")

        btn_close = tk.Button(dlg, text="Fechar", command=dlg.destroy, padx=15, pady=4)
        btn_close.pack(pady=10)

    # ---------------------------------------------------------
    # SINCRONIZAÇÃO / MONITORAMENTO
    # ---------------------------------------------------------
    def sincronizar_sistemas_gui(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Sincronizando com SEI e STARTGOV...")
        dlg.geometry("620x420")
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_header = tk.Label(
            dlg, text="Robô de Monitoramento nos Sistemas Oficiais",
            font=("Segoe UI", 11, "bold"), fg="#047857"
        )
        lbl_header.pack(anchor="w", padx=15, pady=(15, 4))

        lbl_sub = tk.Label(
            dlg, text="Acessando portais com as credenciais cadastradas e buscando trâmites...",
            font=("Segoe UI", 8), fg="#64748b"
        )
        lbl_sub.pack(anchor="w", padx=15, pady=(0, 10))

        prog_bar = ttk.Progressbar(dlg, mode="determinate")
        prog_bar.pack(fill=tk.X, padx=15, pady=5)

        log_box = tk.Text(dlg, wrap=tk.WORD, font=("Consolas", 9), height=14)
        log_box.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        def log(msg):
            log_box.insert(tk.END, msg + "\n")
            log_box.see(tk.END)

        log("[*] Autenticando nos portais...")
        log(f"    SEI: Usuário {SEI_USER}")
        log(f"    STARTGOV: Usuário {STARTGOV_USER}")

        def atualizar_progresso(atual, total, msg):
            self.root.after(0, lambda: [
                prog_bar.config(maximum=total, value=atual),
                log(msg)
            ])

        def tarefa():
            try:
                resumo = executar_monitoramento_processos(callback_progresso=atualizar_progresso)
                self.root.after(0, lambda: [
                    log("\n" + "=" * 50),
                    log(f"✓ Concluído: {resumo['total_atualizados']} de {resumo['total_verificados']} processos verificados."),
                    self.recarregar_dados(),
                    self.status_bar.config(text=f"Sincronização concluída às {resumo['data_hora']}.")
                ])
            except Exception as e:
                self.root.after(0, lambda: log(f"\n[!] Erro durante execução: {str(e)}"))

        threading.Thread(target=tarefa, daemon=True).start()

    def sincronizar_processo(self, proc_id, num):
        proc = obter_processo(proc_id)
        if not proc:
            return

        sis = proc["sistema"]
        self.status_bar.config(text=f"Consultando processo {num} no {sis}...")

        def tarefa():
            res = monitorar_processo_individual(proc_id)
            if res.get("sucesso"):
                self.root.after(0, lambda: [
                    messagebox.showinfo(
                        "Processo Sincronizado",
                        f"✓ Processo {num} atualizado com sucesso via SEI!\n\n"
                        f"Local Atual: {res['dados']['local_atual']}\n"
                        f"Situação: {res['dados']['situacao']}\n"
                        f"Data: {formatar_data_br(res['dados'].get('data_recebimento'))}\n\n"
                        f"As 4 primeiras linhas do Histórico Completo foram gravadas com sucesso no relatório."
                    ),
                    self.recarregar_dados()
                ])
            else:
                self.root.after(0, lambda: [
                    messagebox.showwarning("Aviso de Conexão", f"Não foi possível sincronizar no momento.\nMotivo: {res.get('mensagem')}"),
                    self.recarregar_dados()
                ])

        threading.Thread(target=tarefa, daemon=True).start()

    def excluir_processo(self, proc_id, num):
        if messagebox.askyesno("Confirmar Exclusão", f"Tem certeza que deseja excluir o processo {num}?"):
            excluir_processo(proc_id)
            self.recarregar_dados()

    # ---------------------------------------------------------
    # RESUMO E PRÉVIA
    # ---------------------------------------------------------
    def abrir_dialog_preview(self):
        resumo = gerar_conteudo_resumo("Pré-visualização GUI")

        dlg = tk.Toplevel(self.root)
        dlg.title("Prévia do Resumo de Processos por Projeto - STI")
        dlg.geometry("780x540")
        dlg.transient(self.root)

        txt_box = tk.Text(dlg, wrap=tk.WORD, font=("Consolas", 10), padx=10, pady=10)
        txt_box.pack(fill=tk.BOTH, expand=True)
        txt_box.insert(tk.END, resumo["texto"])
        txt_box.config(state=tk.DISABLED)

        b_frame = tk.Frame(dlg, pady=10)
        b_frame.pack(fill=tk.X)

        btn_disparar = tk.Button(
            b_frame, text="⚡ Disparar Este Resumo Agora", bg="#d97706", fg="white",
            font=("Segoe UI", 9, "bold"), padx=12, pady=4,
            command=lambda: [dlg.destroy(), self.disparar_resumo_manual()]
        )
        btn_disparar.pack(side=tk.RIGHT, padx=15)

        btn_fechar = tk.Button(b_frame, text="Fechar", command=dlg.destroy, padx=12, pady=4)
        btn_fechar.pack(side=tk.RIGHT)

    def disparar_resumo_manual(self):
        if not messagebox.askyesno("Confirmar", "Deseja emitir e enviar o resumo dos processos por projeto agora?"):
            return

        def tarefa():
            self.status_bar.config(text="Emitindo e enviando resumo diário...")
            res = executar_envio_resumo(tipo="Manual (Interface GUI)")
            self.root.after(0, lambda: messagebox.showinfo("Resumo Emitido", f"✓ Resumo concluído com sucesso!\n\nStatus: {res['status']}"))
            self.root.after(0, self.recarregar_dados)

        threading.Thread(target=tarefa, daemon=True).start()

    def abrir_dialog_sistemas(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Credenciais e Acesso aos Sistemas Oficiais")
        dlg.geometry("520x360")
        dlg.transient(self.root)

        frame = tk.Frame(dlg, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)

        box_sei = tk.LabelFrame(frame, text=" SISTEMA SEI (GOVMA) ", font=("Segoe UI", 10, "bold"), fg="#854d0e", bg="#fef9c3", padx=12, pady=10)
        box_sei.pack(fill=tk.X, pady=(0, 12))

        tk.Label(box_sei, text=f"Usuário: {SEI_USER} | Senha: {SEI_PASS}", font=("Consolas", 9, "bold"), bg="#fef9c3").pack(anchor="w")
        btn_sei = tk.Button(box_sei, text="Abrir Portal SEI ↗", bg="#ca8a04", fg="white", font=("Segoe UI", 8, "bold"), command=lambda: webbrowser.open(SEI_URL))
        btn_sei.pack(anchor="e", pady=(4, 0))

        box_sg = tk.LabelFrame(frame, text=" SISTEMA STARTGOV ", font=("Segoe UI", 10, "bold"), fg="#1e40af", bg="#eff6ff", padx=12, pady=10)
        box_sg.pack(fill=tk.X, pady=(0, 12))

        tk.Label(box_sg, text=f"Usuário: {STARTGOV_USER} | Senha: {STARTGOV_PASS}", font=("Consolas", 9, "bold"), bg="#eff6ff").pack(anchor="w")
        btn_sg = tk.Button(box_sg, text="Abrir Portal STARTGOV ↗", bg="#2563eb", fg="white", font=("Segoe UI", 8, "bold"), command=lambda: webbrowser.open(STARTGOV_URL))
        btn_sg.pack(anchor="e", pady=(4, 0))

        btn_fechar = tk.Button(frame, text="Fechar", command=dlg.destroy, padx=12, pady=4)
        btn_fechar.pack(pady=5)

    def exportar_csv(self):
        caminho = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Arquivo CSV (Excel)", "*.csv")],
            initialfile="processos_por_projeto_sti.csv"
        )
        if not caminho:
            return

        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([
                    "ID_PROCESSO", "PROJETO", "DESCRIÇÃO DO PROJETO", "SISTEMA", "Nº - PROCESSO",
                    "LOCAL ATUAL", "AÇÃO", "DATA RECEBIMENTO", "SITUAÇÃO", "DIAS NO SETOR", "MONITORADO"
                ])
                for proj in self.projetos_cache:
                    for p in proj.get("processos", []):
                        writer.writerow([
                            p["id"], proj["nome"], proj["descricao"] or "-", p["sistema"], p["numero_processo"],
                            p["local_atual"], p["acao"] or "-", formatar_data_br(p["data_recebimento"]) if p["data_recebimento"] else "-", p["situacao"] or "-",
                            p["dias_no_setor"] if p["dias_no_setor"] is not None else "-",
                            "Sim" if p.get("monitorar", 1) == 1 else "Não"
                        ])
            messagebox.showinfo("Exportado", f"Arquivo exportado com sucesso em:\n{caminho}")
        except Exception as e:
            messagebox.showerror("Erro ao Exportar", str(e))

def main():
    root = tk.Tk()
    app = SistemaProcessosGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
