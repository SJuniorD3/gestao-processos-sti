import re
import datetime
import urllib.parse
import requests
from config import STARTGOV_URL, STARTGOV_USER, STARTGOV_PASS

class StartGovIntegration:
    """
    Integração oficial com o STARTGOV (https://bid.startgov.com.br).
    
    Fluxo obrigatório de navegação:
    1. Clicar em 'Acessar' (autenticação com CPF e Senha via POST /v1/auth/login).
    2. Acessar o menu 'Processos' -> 'Todos os Processos' (GET /v1/process?type=all).
    3. Mandar procurar o processo desejado pelo número (query param 'type=all&search={numero_processo}').
    4. Carregar os detalhes completos do processo (GET /v1/process/{id}).
    5. Converter datas para o fuso horário oficial de Brasília (UTC-3).
    6. Extrair e ordenar todas as movimentações por data/hora decrescente.
    7. Selecionar exatamente as 4 movimentações MAIS RECENTES (Linha 1 a Linha 4) para o relatório.
    8. Atualizar Local Atual, Data de Recebimento, Ação e Situação com base na posição mais recente.
    """
    def __init__(self):
        self.login_url = STARTGOV_URL
        self.api_base = "https://api-bid.startgov.com.br/v1"
        self.username = STARTGOV_USER
        self.password = STARTGOV_PASS
        self.session = None
        self.token = None
        self.user_data = None
        self.tz_brasilia = datetime.timezone(datetime.timedelta(hours=-3))

    def get_info(self):
        return {
            "sistema": "STARTGOV",
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
                "Accept": "application/json, text/plain, */*"
            })
        return self.session

    def _converter_data_hora(self, raw_date):
        """Converte timestamp ISO UTC da API do StartGov para horário oficial de Brasília (UTC-3) no formato dia/mês/ano."""
        if not raw_date:
            return None, "", ""
        try:
            clean_date = str(raw_date).replace("Z", "+00:00")
            dt_utc = datetime.datetime.fromisoformat(clean_date)
            dt_local = dt_utc.astimezone(self.tz_brasilia)
            return dt_local, dt_local.strftime("%d/%m/%Y %H:%M"), dt_local.strftime("%d/%m/%Y")
        except Exception:
            s = str(raw_date)
            m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
            if m:
                a, m_mes, d = m.groups()
                return None, f"{d}/{m_mes}/{a}", f"{d}/{m_mes}/{a}"
            return None, s[:16], s[:10]

    def _limpar_html(self, text):
        """Remove tags HTML e normaliza espaços."""
        if not text:
            return ""
        sem_tags = re.sub(r"<[^>]+>", " ", str(text))
        return re.sub(r"\s+", " ", sem_tags).strip()

    def _extrair_sigla(self, texto):
        """Extrai sigla de setor/unidade entre parênteses, ex.: (ATI-MA), (STI), (SUORC)."""
        if not texto:
            return None
        siglas = re.findall(r"\(([A-Z0-9_\-\/]{2,})\)", texto)
        if siglas:
            return siglas[-1]  # Destino no final
        return None

    def autenticar(self, forcar=False):
        """Passo 1: Clicar em 'Acessar' (Login no StartGov com CPF e Senha)."""
        if self.token and not forcar:
            return True, "Sessão já ativa no STARTGOV"

        session = self._obter_sessao()
        url_auth = f"{self.api_base}/auth/login"
        payload = {
            "cpf": self.username,
            "password": self.password
        }
        headers = {
            "Content-Type": "application/json",
            "Origin": "https://bid.startgov.com.br",
            "Referer": self.login_url
        }

        try:
            resp = session.post(url_auth, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                self.token = data.get("token")
                self.user_data = data.get("user")
                if self.token:
                    session.headers.update({"Authorization": f"Bearer {self.token}"})
                    return True, "Autenticado com sucesso no STARTGOV"
                return False, "Token de autenticação não retornado pelo STARTGOV."
            elif resp.status_code in (401, 422):
                return False, "Credenciais inválidas no STARTGOV (CPF ou senha incorretos)."
            else:
                return False, f"Falha de autenticação no STARTGOV (HTTP {resp.status_code})"
        except requests.exceptions.RequestException as e:
            return False, f"Erro de conexão com STARTGOV: {str(e)}"
        except Exception as e:
            return False, f"Erro ao autenticar no STARTGOV: {str(e)}"

    def consultar_processo(self, numero_processo):
        """
        Passos 2, 3 e 4:
        2. Navegar em Menu Processos -> Todos os Processos (type=all)
        3. Procurar o processo
        4. Abrir detalhes e coletar as 4 movimentações mais recentes
        """
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

        session = self._obter_sessao()
        numero_limpo = numero_processo.strip()

        # Termos de busca em 'Todos os Processos' (type=all)
        termos_busca = [numero_limpo]
        so_num = re.sub(r"[^\d]", "", numero_limpo)
        if "/" in numero_limpo:
            partes = numero_limpo.split("/")
            if len(partes) >= 2:
                termos_busca.append(f"{partes[-2]}/{partes[-1]}")
                termos_busca.append(partes[-2])
        if so_num and so_num not in termos_busca:
            termos_busca.append(so_num)

        headers_get = {
            "Origin": "https://bid.startgov.com.br",
            "Referer": "https://bid.startgov.com.br/processos"
        }

        processo_encontrado = None
        for termo in termos_busca:
            if not termo:
                continue
            try:
                # OBRIGATÓRIO: type=all para acessar a aba 'Todos os processos'
                url_busca = f"{self.api_base}/process?type=all&search={urllib.parse.quote(termo)}"
                resp_busca = session.get(url_busca, headers=headers_get, timeout=15)
                if resp_busca.status_code == 401:
                    # Token expirou, tenta reautenticar
                    self.autenticar(forcar=True)
                    resp_busca = session.get(url_busca, headers=headers_get, timeout=15)

                if resp_busca.status_code == 200:
                    lista = resp_busca.json().get("data", {}).get("data", [])
                    if lista:
                        # Tenta correspondência exata ou por substring
                        for item in lista:
                            num_item = str(item.get("number", "")).strip().upper()
                            if numero_limpo.upper() in num_item or num_item in numero_limpo.upper():
                                processo_encontrado = item
                                break
                        if not processo_encontrado:
                            processo_encontrado = lista[0]
                        break
            except Exception:
                pass

        if not processo_encontrado:
            return {
                "sucesso": False,
                "mensagem": f"Processo '{numero_processo}' não localizado em 'Todos os Processos' do STARTGOV.",
                "local_atual": None,
                "data_recebimento": None,
                "acao": None,
                "situacao": None,
                "historico_4_linhas": []
            }

        # 4. Detalhes completos do processo (GET /v1/process/{id})
        proc_id = processo_encontrado.get("id")
        try:
            url_det = f"{self.api_base}/process/{proc_id}"
            resp_det = session.get(url_det, headers=headers_get, timeout=15)
            if resp_det.status_code != 200:
                return {
                    "sucesso": False,
                    "mensagem": f"Erro HTTP {resp_det.status_code} ao obter detalhes do processo {numero_processo} no STARTGOV."
                }

            detalhes = resp_det.json().get("data", {})
            movements_raw = detalhes.get("movements", [])
            last_tram = detalhes.get("lastest_tramitation") or {}
            last_mov = detalhes.get("lastest_movement") or detalhes.get("last_movement") or {}

            # Processa e normaliza as movimentações
            movimentacoes_processadas = []
            for m in movements_raw:
                date_raw = m.get("date") or m.get("created_at") or ""
                dt_obj, data_hora_str, _ = self._converter_data_hora(date_raw)

                title = str(m.get("title") or "").strip()
                desc_raw = str(m.get("description") or title or "")
                desc = self._limpar_html(desc_raw)

                resp = m.get("responsible")
                user_name = resp.get("name") if isinstance(resp, dict) else (resp or "")

                # Extrai setor / unidade a partir da descrição ou tramitação
                local_mov = self._extrair_sigla(desc)
                if not local_mov and " de " in desc and " para " in desc:
                    m_tram = re.search(r"de\s+([A-Za-z0-9_\-\/]+(?:\s*\([A-Z0-9_\-\/]+\))?)\s+para\s+([A-Za-z0-9_\-\/]+(?:\s*\([A-Z0-9_\-\/]+\))?)", desc)
                    if m_tram:
                        local_mov = f"{m_tram.group(1)} -> {m_tram.group(2)}"

                if not local_mov:
                    src_u = detalhes.get("source_unity", {})
                    local_mov = src_u.get("company_name_short") or src_u.get("company_name") or "STARTGOV"

                # Trunca se for texto gigantesco (ex: termo de referência ou ofício anexado)
                desc_resumida = desc[:240] + ("..." if len(desc) > 240 else "")

                movimentacoes_processadas.append({
                    "dt_obj": dt_obj,
                    "id": m.get("id", 0),
                    "data_hora": data_hora_str,
                    "local": local_mov,
                    "usuario": user_name,
                    "situacao": desc_resumida,
                    "acao": title or "Trâmite StartGov"
                })

            # Ordena decrescente (mais recente primeiro)
            movimentacoes_processadas.sort(
                key=lambda x: (x["dt_obj"] or datetime.datetime.min, x["id"]),
                reverse=True
            )

            # Extrai exatamente as 4 mais recentes
            historico_4_linhas = movimentacoes_processadas[:4]
            for idx, item in enumerate(historico_4_linhas, 1):
                item["ordem"] = idx
                item.pop("dt_obj", None)

            # ------------------------------------------------------------------
            # DETERMINAÇÃO DO LOCAL ATUAL, DATA, SITUAÇÃO E AÇÃO
            # ------------------------------------------------------------------
            local_atual = None
            data_recebimento = None
            situacao = None
            acao = None

            # 1. Local Atual: extrai da última tramitação (unidade atual onde o processo se encontra)
            if last_tram:
                local_atual = (
                    last_tram.get("source_unity_company_name_short") or
                    (last_tram.get("source_unity") or {}).get("company_name_short") or
                    last_tram.get("destination_unity_company_name_short") or
                    (last_tram.get("destination_unity") or {}).get("company_name_short")
                )

            # Se não veio na tramitação, extrai da última movimentação
            if not local_atual or local_atual == "STARTGOV":
                desc_last_mov = str(last_mov.get("description") or "")
                local_atual = self._extrair_sigla(desc_last_mov)

            # Fallback para o local da movimentação mais recente
            if not local_atual and historico_4_linhas:
                local_atual = historico_4_linhas[0]["local"]

            # 2. Data de Recebimento / Envio (em horário local de Brasília)
            if last_tram:
                raw_tram_date = last_tram.get("received_date") or last_tram.get("created_at")
                if raw_tram_date:
                    _, _, data_recebimento = self._converter_data_hora(raw_tram_date)

            if not data_recebimento and last_mov.get("date"):
                _, _, data_recebimento = self._converter_data_hora(last_mov.get("date"))

            # 3. Situação e Ação
            if historico_4_linhas:
                mais_recente = historico_4_linhas[0]
                situacao = mais_recente["situacao"]
                acao = mais_recente["acao"]

            # Caso especial do StartGov: processo enviado aguardando recebimento/movimentação na unidade de destino
            if last_tram.get("received") is False and "enviado" in (acao or "").lower():
                if "aguardando movimentação" not in situacao.lower():
                    situacao = f"{situacao} (Aguardando movimentação...)"

            # Fallbacks seguros
            if not local_atual:
                local_atual = "STI"
            if not data_recebimento:
                data_recebimento = datetime.date.today().isoformat()
            if not situacao:
                situacao = self._limpar_html(processo_encontrado.get("description", "Em análise na unidade"))
            if not acao:
                acao = "Trâmite StartGov"

            return {
                "sucesso": True,
                "mensagem": f"Histórico completo obtido com sucesso no STARTGOV ({len(historico_4_linhas)} linhas mais recentes capturadas)",
                "numero_processo": processo_encontrado.get("number", numero_processo),
                "local_atual": local_atual,
                "data_recebimento": data_recebimento,
                "situacao": situacao,
                "acao": acao,
                "historico_4_linhas": historico_4_linhas
            }

        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro ao processar dados do processo no STARTGOV: {str(e)}",
                "local_atual": None,
                "data_recebimento": None,
                "acao": None,
                "situacao": None,
                "historico_4_linhas": []
            }
