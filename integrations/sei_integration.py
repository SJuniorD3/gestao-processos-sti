import re
import datetime
from urllib.parse import urljoin
import requests
from config import SEI_URL, SEI_USER, SEI_PASS

class SEIIntegration:
    """
    Integração oficial com o SEI (Sistema Eletrônico de Informações - GOVMA/SEDUC).
    
    Fluxo obrigatório de navegação:
    1. Login no SEI com credenciais (SEDUC).
    2. Localização do processo via pesquisa rápida.
    3. Acesso à tela do processo e clique em 'Consultar Andamento'.
    4. Clique em 'Ver Histórico Completo' (hdnTipoHistorico='P').
    5. Captura das 4 primeiras linhas do histórico completo para o relatório.
    """
    def __init__(self):
        self.login_url = SEI_URL
        self.username = SEI_USER
        self.password = SEI_PASS
        self.session = None
        self.base_url = "https://sei.ma.gov.br"
        self.main_page_html = None
        self.main_page_url = None
        self.is_authenticated = False

    def get_info(self):
        return {
            "sistema": "SEI",
            "url": self.login_url,
            "usuario": self.username,
            "configurado": bool(self.username and self.password)
        }

    def _obter_sessao(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive"
            })
        return self.session

    def autenticar(self, forcar=False):
        """
        Efetua login no portal SEI (SIP) usando as credenciais configuradas e selecionando SEDUC.
        """
        if self.is_authenticated and not forcar and self.main_page_html:
            return True, "Sessão já autenticada no SEI"

        session = self._obter_sessao()
        try:
            # 1. Carrega página inicial do login SIP
            resp_login = session.get(self.login_url, timeout=15)
            if resp_login.status_code != 200:
                return False, f"Falha ao carregar tela de login do SEI (HTTP {resp_login.status_code})"

            # Extrai opções de órgãos disponíveis
            orgaos = dict(re.findall(r'<option[^>]+value=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)</option>', resp_login.text, re.I))
            
            # Localiza ID do órgão SEDUC (geralmente '36' no GOVMA)
            sel_orgao = "36"
            for k, v in orgaos.items():
                if "SEDUC" in v.upper():
                    sel_orgao = k
                    break

            payload = {
                "txtUsuario": self.username,
                "pwdSenha": self.password,
                "selOrgao": sel_orgao,
                "hdnAcao": "2",  # Ação acaoLogin(2)
                "sbmAcessar": "Acessar"
            }

            headers_post = {
                "Origin": "https://sip.sei.ma.gov.br",
                "Referer": self.login_url
            }

            resp_auth = session.post(self.login_url, data=payload, headers=headers_post, timeout=20, allow_redirects=True)

            # Verifica mensagens de validação / erro exibidas pelo SIP
            m_validacao = re.search(r'<textarea[^>]*id=[\'"]txaInfraValidacao[\'"][^>]*>(.*?)</textarea>', resp_auth.text, re.DOTALL | re.I)
            if m_validacao and m_validacao.group(1).strip():
                erro_msg = m_validacao.group(1).strip()
                return False, f"Validação do SEI: {erro_msg}"

            if "procedimento_controlar" in resp_auth.url or "sei.ma.gov.br/sei" in resp_auth.url:
                self.is_authenticated = True
                self.main_page_html = resp_auth.text
                self.main_page_url = resp_auth.url
                return True, "Autenticado com sucesso no SEI (SEDUC)"

            # Se não redirecionou para a página de controle
            return False, "Login não completou o redirecionamento para o Painel de Controle do SEI."

        except requests.exceptions.RequestException as e:
            self.is_authenticated = False
            return False, f"Erro de conexão com o SEI: {str(e)}"
        except Exception as e:
            self.is_authenticated = False
            return False, f"Erro no processo de login do SEI: {str(e)}"

    def consultar_processo(self, numero_processo):
        """
        Executa rigorosamente o fluxo solicitado:
        1. Entrar no SEI.
        2. Localizar o processo e ir em 'Consultar Andamento'.
        3. Ir em 'Ver Histórico Completo'.
        4. Extrair as quatro primeiras linhas do histórico completo e estruturar para o relatório.
        """
        session = self._obter_sessao()

        # Garante autenticação
        auth_ok, auth_msg = self.autenticar()
        if not auth_ok:
            return {
                "sucesso": False,
                "mensagem": auth_msg,
                "local_atual": None,
                "data_recebimento": None,
                "acao": None,
                "situacao": None,
                "historico_4_linhas": []
            }

        try:
            # 1. Localiza o formulário de Pesquisa Rápida na página principal do SEI
            m_search_form = re.search(
                r'<form[^>]*id=[\'"]frmProtocoloPesquisaRapida[\'"][^>]*action=[\'"]([^\'"]*)[\'"]',
                self.main_page_html,
                re.I
            )
            if not m_search_form:
                # Recarrega a página principal se o formulário não estiver no cache
                r_main = session.get(self.main_page_url, timeout=15)
                self.main_page_html = r_main.text
                m_search_form = re.search(
                    r'<form[^>]*id=[\'"]frmProtocoloPesquisaRapida[\'"][^>]*action=[\'"]([^\'"]*)[\'"]',
                    self.main_page_html,
                    re.I
                )

            if not m_search_form:
                return {"sucesso": False, "mensagem": "Formulário de pesquisa rápida não localizado no SEI."}

            search_action = urljoin("https://sei.ma.gov.br/sei/", m_search_form.group(1))

            # 2. Pesquisa o número do processo (tenta o formato original; se falhar, tenta apenas números)
            termos_busca = [numero_processo.strip()]
            num_so_digitos = re.sub(r"[^\d]", "", numero_processo)
            if num_so_digitos and num_so_digitos != numero_processo.strip():
                termos_busca.append(num_so_digitos)

            r_search = None
            for termo in termos_busca:
                r_tentativa = session.post(
                    search_action,
                    data={"txtPesquisaRapida": termo},
                    timeout=15,
                    allow_redirects=True
                )
                if "procedimento_trabalhar" in r_tentativa.url:
                    r_search = r_tentativa
                    break
                # Se caiu numa lista de resultados de busca, procura o link para trabalhar no procedimento
                m_proc_link = re.search(r'href=[\'"](controlador\.php\?acao=procedimento_trabalhar[^\'"]+)[\'"]', r_tentativa.text)
                if m_proc_link:
                    r_search = session.get(urljoin("https://sei.ma.gov.br/sei/", m_proc_link.group(1)), timeout=15)
                    break

            if not r_search or "procedimento_trabalhar" not in r_search.url:
                return {
                    "sucesso": False,
                    "mensagem": f"Processo '{numero_processo}' não encontrado no SEI."
                }

            # 3. Localiza o iframe de visualização do processo (procedimento_visualizar)
            iframes = re.findall(r'<iframe[^>]*src=[\'"]([^\'"]+)[\'"]', r_search.text, re.I)
            if not iframes:
                return {"sucesso": False, "mensagem": "Iframe do processo não encontrado no SEI."}

            viz_url = urljoin("https://sei.ma.gov.br/sei/", iframes[0])
            r_viz = session.get(viz_url, timeout=15)

            # 4. Localiza o botão/ação 'Consultar Andamento'
            m_andamento = re.search(r"consultarAndamento\([\'\"]([^\'\"]+)[\'\"]\)", r_viz.text)
            if not m_andamento:
                # Procura por link direto de histórico de andamentos
                m_andamento = re.search(r'href=[\'"](controlador\.php\?acao=procedimento_consultar_historico[^\'"]+)[\'"]', r_viz.text)

            if not m_andamento:
                return {"sucesso": False, "mensagem": "Opção 'Consultar Andamento' não encontrada para o processo."}

            andamento_url = urljoin("https://sei.ma.gov.br/sei/", m_andamento.group(1))
            r_andamento = session.get(andamento_url, timeout=15)

            # 5. Localiza e aciona 'Ver Histórico Completo'
            # No SEI, o botão 'Ver histórico completo' executa:
            # document.getElementById('hdnTipoHistorico').value = 'P';
            # document.getElementById('frmProcedimentoHistorico').submit();
            form_m = re.search(r'<form[^>]*id=[\'"]frmProcedimentoHistorico[\'"][^>]*>(.*?)</form>', r_andamento.text, re.DOTALL | re.I)
            action_m = re.search(r'<form[^>]*id=[\'"]frmProcedimentoHistorico[\'"][^>]*action=[\'"]([^\'"]*)[\'"]', r_andamento.text, re.I)
            
            action_rel = action_m.group(1) if action_m else andamento_url
            post_hist_url = urljoin(andamento_url, action_rel)

            inputs = {}
            if form_m:
                inputs = dict(re.findall(r'<input[^>]+name=[\'"]([^\'"]+)[\'"][^>]*value=[\'"]([^\'"]*)[\'"]', form_m.group(1), re.I))

            # Define 'P' para carregar todo o histórico completo do processo
            inputs['hdnTipoHistorico'] = 'P'

            r_hist = session.post(post_hist_url, data=inputs, timeout=20)
            if r_hist.status_code != 200:
                return {"sucesso": False, "mensagem": f"Erro HTTP {r_hist.status_code} ao carregar Histórico Completo."}

            # 6. Extrai as 4 movimentações MAIS RECENTES da tabela tblHistorico
            table_m = re.search(r'<table[^>]*id=[\'"]tblHistorico[\'"][^>]*>(.*?)</table>', r_hist.text, re.DOTALL | re.I)
            if not table_m:
                return {"sucesso": False, "mensagem": "Tabela de Histórico de Andamentos não encontrada na página."}

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_m.group(1), re.DOTALL | re.I)
            
            # rows[0] é o cabeçalho: ['Data/Hora', 'Unidade', 'Usuário', 'Descrição']
            todos_andamentos = []
            for r_item in rows[1:]:
                cols = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r_item, re.DOTALL | re.I)
                clean_cols = [re.sub(r'<[^>]+>', ' ', c).strip() for c in cols]
                if not clean_cols or len(clean_cols) < 2:
                    continue
                
                dt_str = clean_cols[0] if len(clean_cols) > 0 else ""
                unidade = clean_cols[1] if len(clean_cols) > 1 else ""
                usuario = clean_cols[2] if len(clean_cols) > 2 else ""
                desc = clean_cols[3] if len(clean_cols) > 3 else ""

                # Converte para datetime para garantir ordenação 100% precisa (mais recente primeiro)
                dt_obj = None
                m_dt = re.search(r'(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?', dt_str)
                if m_dt:
                    d, m_mes, a, hh, mm = m_dt.groups()
                    hh = hh or "00"
                    mm = mm or "00"
                    try:
                        dt_obj = datetime.datetime(int(a), int(m_mes), int(d), int(hh), int(mm))
                    except ValueError:
                        pass

                todos_andamentos.append({
                    "dt_obj": dt_obj,
                    "data_hora": dt_str,
                    "local": unidade,
                    "usuario": usuario,
                    "situacao": desc,
                    "acao": "Trâmite SEI"
                })

            # Garante que a lista esteja rigorosamente ordenada da mais recente para a mais antiga
            if any(item["dt_obj"] for item in todos_andamentos):
                todos_andamentos.sort(key=lambda x: x["dt_obj"] or datetime.datetime.min, reverse=True)

            # Seleciona exatamente as 4 movimentações mais recentes
            historico_4_linhas = todos_andamentos[:4]
            for idx, item in enumerate(historico_4_linhas, 1):
                item["ordem"] = idx
                item.pop("dt_obj", None)

            # Da movimentação mais recente (1ª), extraímos a posição atual do processo
            local_atual = None
            data_recebimento = None
            situacao = None
            acao = None

            if historico_4_linhas:
                mais_recente = historico_4_linhas[0]
                local_atual = mais_recente["local"]
                situacao = mais_recente["situacao"]
                acao = "Trâmite SEI"

                dt_match = re.search(r'(\d{2})/(\d{2})/(\d{4})', mais_recente["data_hora"])
                if dt_match:
                    d, m_mes, a = dt_match.groups()
                    data_recebimento = f"{d}/{m_mes}/{a}"

            # 7. Rastreia também documentos da árvore do processo se disponível
            documentos_capturados = []
            try:
                for ifr in iframes:
                    if "arvore" in ifr.lower() or "visualizar" in ifr.lower():
                        r_tree = session.get(urljoin("https://sei.ma.gov.br/sei/", ifr), timeout=10)
                        docs = self.extrair_documentos_arvore(r_tree.text)
                        if docs:
                            documentos_capturados.extend(docs)
            except Exception:
                pass

            return {
                "sucesso": True,
                "mensagem": f"Histórico completo obtido com sucesso ({len(historico_4_linhas)} linhas capturadas)",
                "numero_processo": numero_processo,
                "local_atual": local_atual,
                "data_recebimento": data_recebimento,
                "situacao": situacao,
                "acao": acao,
                "historico_4_linhas": historico_4_linhas,
                "documentos": documentos_capturados
            }

        except requests.exceptions.RequestException as e:
            return {"sucesso": False, "mensagem": f"Falha de conexão com o SEI: {str(e)}"}
        except Exception as e:
            return {"sucesso": False, "mensagem": f"Erro na navegação do SEI: {str(e)}"}

    def rastrear_documentos_processo(self, numero_processo):
        """
        Navega até a árvore do processo no SEI e extrai especificamente
        todas as peças documentais juntadas (Termo de Referência, Pareceres, Despachos, Empenhos).
        """
        session = self._obter_sessao()
        auth_ok, auth_msg = self.autenticar()
        if not auth_ok:
            return {"sucesso": False, "mensagem": auth_msg, "documentos": []}

        try:
            m_search_form = re.search(
                r'<form[^>]*id=[\'"]frmProtocoloPesquisaRapida[\'"][^>]*action=[\'"]([^\'"]*)[\'"]',
                self.main_page_html or "",
                re.I
            )
            if not m_search_form:
                r_main = session.get(self.main_page_url or "https://sei.ma.gov.br/sei/controlador.php?acao=procedimento_controlar", timeout=15)
                self.main_page_html = r_main.text
                m_search_form = re.search(
                    r'<form[^>]*id=[\'"]frmProtocoloPesquisaRapida[\'"][^>]*action=[\'"]([^\'"]*)[\'"]',
                    self.main_page_html,
                    re.I
                )

            if not m_search_form:
                return {"sucesso": False, "mensagem": "Formulário de pesquisa do SEI não localizado.", "documentos": []}

            search_action = urljoin("https://sei.ma.gov.br/sei/", m_search_form.group(1))
            r_search = session.post(search_action, data={"txtPesquisaRapida": numero_processo.strip()}, timeout=15, allow_redirects=True)

            if "procedimento_trabalhar" not in r_search.url:
                m_proc_link = re.search(r'href=[\'"](controlador\.php\?acao=procedimento_trabalhar[^\'"]+)[\'"]', r_search.text)
                if m_proc_link:
                    r_search = session.get(urljoin("https://sei.ma.gov.br/sei/", m_proc_link.group(1)), timeout=15)

            if "procedimento_trabalhar" not in r_search.url:
                return {"sucesso": False, "mensagem": f"Processo '{numero_processo}' não encontrado no SEI.", "documentos": []}

            # Localiza os iframes
            iframes = re.findall(r'<iframe[^>]*src=[\'"]([^\'"]+)[\'"]', r_search.text, re.I)
            documentos = []

            # Varre os iframes da árvore
            for ifr in iframes:
                try:
                    r_ifr = session.get(urljoin("https://sei.ma.gov.br/sei/", ifr), timeout=12)
                    docs_ifr = self.extrair_documentos_arvore(r_ifr.text)
                    if docs_ifr:
                        documentos.extend(docs_ifr)
                except Exception:
                    pass

            # Varre também o próprio HTML da tela
            docs_main = self.extrair_documentos_arvore(r_search.text)
            if docs_main:
                documentos.extend(docs_main)

            # Deduplica por nome_exibicao
            vistos = set()
            docs_unicos = []
            for d in documentos:
                chave = (d.get("nome_exibicao") or "").strip().lower()
                if chave and chave not in vistos:
                    vistos.add(chave)
                    docs_unicos.append(d)

            return {
                "sucesso": True,
                "mensagem": f"{len(docs_unicos)} documento(s) rastreado(s) no SEI.",
                "total": len(docs_unicos),
                "documentos": docs_unicos
            }

        except Exception as e:
            return {"sucesso": False, "mensagem": f"Erro ao rastrear documentos no SEI: {str(e)}", "documentos": []}

    def extrair_documentos_arvore(self, html_arvore, base_url="https://sei.ma.gov.br/sei/"):
        """
        Extrai todas as peças documentais juntadas ao processo a partir do HTML da árvore do SEI.
        """
        documentos = []
        if not html_arvore:
            return documentos

        # Links de visualização
        links = re.findall(r'<a[^>]+href=[\'"]([^\'"]*documento_visualizar[^\'"]*)[\'"][^>]*>(.*?)</a>', html_arvore, re.I | re.DOTALL)
        for href, rotulo_html in links:
            nome_limpo = re.sub(r'<[^>]+>', ' ', rotulo_html).strip()
            nome_limpo = re.sub(r'\s+', ' ', nome_limpo)
            if not nome_limpo or len(nome_limpo) < 2:
                continue

            m_id = re.search(r'id_documento=([0-9]+)', href, re.I)
            num_sei = m_id.group(1) if m_id else ""
            if not num_sei:
                m_num = re.search(r'\(([0-9]{4,10})\)', nome_limpo)
                if m_num:
                    num_sei = m_num.group(1)

            tipo_doc = self._classificar_tipo_documento(nome_limpo)
            link_completo = urljoin(base_url, href)

            documentos.append({
                "nome_exibicao": nome_limpo,
                "numero_sei": num_sei,
                "tipo_documento": tipo_doc,
                "data_documento": "",
                "unidade_geradora": "SEI",
                "link_visualizacao": link_completo
            })

        # Padrão secundário: nós com classes de árvore
        if not documentos:
            nos = re.findall(r'<span[^>]*class=[\'"][^\'"]*arvore[^\'"]*[\'"][^>]*>(.*?)</span>', html_arvore, re.I | re.DOTALL)
            for no_html in nos:
                texto_no = re.sub(r'<[^>]+>', ' ', no_html).strip()
                if texto_no and any(p in texto_no.lower() for p in ["despacho", "termo", "parecer", "ofício", "oficio", "nota", "edital", "certidão", "anexo"]):
                    tipo_doc = self._classificar_tipo_documento(texto_no)
                    documentos.append({
                        "nome_exibicao": texto_no,
                        "numero_sei": "",
                        "tipo_documento": tipo_doc,
                        "data_documento": "",
                        "unidade_geradora": "SEI",
                        "link_visualizacao": ""
                    })

        return documentos

    def _classificar_tipo_documento(self, nome):
        n = nome.lower()
        if "termo de referência" in n or "referência" in n or " tr " in n or n.startswith("tr "):
            return "Termo de Referência"
        if "parecer" in n or "nota técnica" in n or "asjur" in n or "jurídic" in n:
            return "Parecer Jurídico"
        if "despacho" in n or "decisão" in n:
            return "Despacho"
        if "empenho" in n or "financeir" in n or "ordem bancária" in n or "liquid" in n:
            return "Nota de Empenho"
        if "ofício" in n or "oficio" in n or "memorando" in n or "comunicação" in n:
            return "Ofício / Memorando"
        if "edital" in n or "aviso" in n or "licita" in n:
            return "Edital / Licitação"
        if "contrato" in n or "minuta" in n or "aditivo" in n:
            return "Contrato / Minuta"
        if "certidão" in n or "certidao" in n or "regularidade" in n or "declaração" in n:
            return "Certidão / Regularidade"
        if "cotação" in n or "proposta" in n or "orçamento" in n or "pesquisa de preço" in n:
            return "Cotação / Proposta"
        return "Documento Anexo"
