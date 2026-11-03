import threading
import time
import datetime
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import REPORT_HOURS
from notifier import executar_envio_resumo
from monitor_engine import executar_monitoramento_processos

class RelatorioScheduler:
    def __init__(self, report_hours=None):
        self.report_hours = report_hours or REPORT_HOURS
        self.running = False
        self.thread = None
        self.last_run = None
        self.last_status = "Aguardando primeiro disparo"

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"[*] Agendador iniciado para os horários: {self.report_hours}h pontualmente.")

    def stop(self):
        self.running = False

    def _run_loop(self):
        disparos_feitos_hoje = set()
        ultimo_dia = datetime.date.today()

        while self.running:
            agora = datetime.datetime.now()
            
            # Reset diário à meia-noite
            if agora.date() != ultimo_dia:
                disparos_feitos_hoje.clear()
                ultimo_dia = agora.date()

            # Checa se a hora atual está nos horários de disparo (minuto 0)
            if agora.hour in self.report_hours and agora.minute == 0:
                chave = (agora.date(), agora.hour)
                if chave not in disparos_feitos_hoje:
                    disparos_feitos_hoje.add(chave)
                    print(f"\n[!] Horário atingido ({agora.hour:02d}:00). Iniciando rotina de monitoramento nos portais...")
                    
                    # 1. Executa monitoramento nos sistemas SEI e STARTGOV para atualizar trâmites
                    try:
                        executar_monitoramento_processos()
                    except Exception as e:
                        print(f"[!] Aviso no monitoramento automático: {e}")

                    # 2. Gera e despacha o resumo das 08h, 12h ou 16h com os dados atualizados
                    print(f"[!] Disparando resumo consolidado das {agora.hour:02d}:00...")
                    resultado = executar_envio_resumo(tipo=f"Agendado {agora.hour:02d}:00")
                    self.last_run = agora.strftime("%d/%m/%Y %H:%M:%S")
                    self.last_status = resultado["status"]
                    print(f"[✓] Relatório das {agora.hour:02d}:00 concluído: {resultado['status']}")

            time.sleep(20)

    def disparar_manual(self):
        """Permite disparo forçado via interface web."""
        agora = datetime.datetime.now()
        resultado = executar_envio_resumo(tipo="Manual (Interface)")
        self.last_run = agora.strftime("%d/%m/%Y %H:%M:%S")
        self.last_status = resultado["status"]
        return resultado

    def get_info(self):
        agora = datetime.datetime.now()
        proximos = []
        for h in sorted(self.report_hours):
            dt = agora.replace(hour=h, minute=0, second=0, microsecond=0)
            if dt > agora:
                proximos.append(dt.strftime("%H:%M"))
        if not proximos and self.report_hours:
            proximos.append(f"{min(self.report_hours):02d}:00 (Amanhã)")
            
        return {
            "running": self.running,
            "horarios_configurados": [f"{h:02d}:00" for h in sorted(self.report_hours)],
            "proximo_disparo": proximos[0] if proximos else "Não agendado",
            "ultimo_disparo": self.last_run or "Nenhum ainda",
            "ultimo_status": self.last_status
        }

scheduler = RelatorioScheduler()
