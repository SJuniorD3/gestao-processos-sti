import sys
import socketserver
import os

# Garante saída compatível com UTF-8 no terminal Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from database import init_db
from scheduler import scheduler
from app_server import ProcessosRequestHandler
from config import HOST, PORT

def run():
    print("================================================================")
    print("  SISTEMA DE GESTÃO, MONITORAMENTO E RESUMOS DE PROCESSOS - STI ")
    print("================================================================")
    
    # 1. Inicializa o banco de dados e popula com dados da planilha de exemplo
    print("[1/3] Inicializando banco de dados SQLite...")
    init_db()
    print("      ✓ Banco de dados pronto e populado com sucesso.")

    # 2. Inicia o agendador de relatórios (08:00, 12:00, 16:00)
    print("[2/3] Iniciando agendador automático dos relatórios...")
    scheduler.start()
    info = scheduler.get_info()
    print(f"      ✓ Horários configurados: {', '.join(info['horarios_configurados'])}")
    print(f"      ✓ Próximo disparo programado: {info['proximo_disparo']}")

    # 3. Inicia o Servidor HTTP
    print(f"[3/3] Iniciando servidor web em http://{HOST}:{PORT} ...")
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.ThreadingTCPServer((HOST, PORT), ProcessosRequestHandler) as httpd:
        print("\n" + "=" * 64)
        print(f"  PAINEL DISPONÍVEL EM: http://{HOST}:{PORT}")
        print("  Pressione Ctrl+C para encerrar o servidor.")
        print("=" * 64 + "\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nEncerrando servidor e agendador...")
            scheduler.stop()
            httpd.server_close()
            print("Servidor finalizado com sucesso.")

if __name__ == "__main__":
    run()
