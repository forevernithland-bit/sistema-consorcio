"""
watchdog_robo.py — vigia o robô único e o re-sobe se travar.

Roda pelo Agendador de Tarefas do Windows "a cada 2 minutos" (ver
SETUP_SEMPRE_LIGADO.md). Não fica em loop: executa 1 checagem e sai.

Lógica:
  1. lê robo_status.atualizado_em (o supervisor bate a cada ~25 s);
  2. se está há mais de LIMITE_SEG parado → mata o processo (robo.pid) e
     re-executa iniciar_robo.bat;
  3. se robo.pid não existe / processo não está vivo → sobe também.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

_AQUI = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_AQUI, ".env"))

PID_FILE = os.path.join(_AQUI, "robo.pid")
VBS = os.path.join(_AQUI, "iniciar_robo_oculto.vbs")   # sobe SEM janela
BAT = os.path.join(_AQUI, "iniciar_robo.bat")
LOG = os.path.join(_AQUI, "logs", "watchdog.log")
LIMITE_SEG = int(os.getenv("WATCHDOG_LIMITE_SEG", "180"))


def log(msg):
    linha = f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] {msg}"
    print(linha, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def _heartbeat_atrasado() -> bool:
    try:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL", "").strip(),
                           os.getenv("SUPABASE_KEY", "").strip())
        r = sb.table("robo_status").select("atualizado_em").eq("id", 1).execute()
        ts = (r.data or [{}])[0].get("atualizado_em")
        if not ts:
            return True
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        idade = (datetime.now(timezone.utc) - dt).total_seconds()
        log(f"heartbeat: {idade:.0f}s atrás (limite {LIMITE_SEG}s)")
        return idade > LIMITE_SEG
    except Exception as e:
        log(f"não consegui ler robo_status ({e}) — assumo que precisa subir")
        return True


def _pid_vivo() -> int | None:
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
    except Exception:
        return None
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True, timeout=20)
        return pid if str(pid) in out.stdout else None
    except Exception:
        return None


def _matar(pid: int):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"],
                       capture_output=True, text=True, timeout=30)
        log(f"matei o processo {pid}")
    except Exception as e:
        log(f"falha ao matar {pid}: {e}")


def _subir():
    # Prefere o .vbs (sobe SEM janela). Se não existir, cai pro .bat minimizado.
    try:
        if os.path.exists(VBS):
            subprocess.Popen(["wscript.exe", VBS], cwd=_AQUI, close_fds=True)
            log("iniciei o robô oculto (iniciar_robo_oculto.vbs)")
        else:
            subprocess.Popen(["cmd", "/c", "start", "", "/min", BAT],
                             cwd=_AQUI, close_fds=True)
            log("iniciei o iniciar_robo.bat (minimizado)")
    except Exception as e:
        log(f"falha ao subir o robô: {e}")


def main():
    atrasado = _heartbeat_atrasado()
    pid = _pid_vivo()
    if not atrasado and pid:
        log("ok — robô vivo e batendo ponto.")
        return
    log(f"⚠️ robô precisa de atenção (atrasado={atrasado}, pid_vivo={pid}).")
    if pid:
        _matar(pid)
    _subir()


if __name__ == "__main__":
    main()
    sys.exit(0)
