"""
watchdog_robo.py — liga, vigia e desliga o robô único (modo SOB DEMANDA).

Roda pelo Agendador de Tarefas do Windows "a cada 1 minuto" no notebook servidor
(ver instalar_robo_sob_demanda.ps1). Não fica em loop: executa 1 checagem e sai.

Modo sob demanda (robo_config.toml → [sob_demanda] ativo = true):
  • O CRM grava robo_status.crm_ativo_em (no máx. 1x/min por sessão) enquanto
    alguém está logado e usando o sistema.
  • crm_ativo_em recente (< minutos_apos_sair, padrão 60) → o robô DEVE estar ligado:
    sobe se estiver parado e re-sobe se o heartbeat travar.
  • crm_ativo_em velho → o robô é desligado — mas só quando a fila de lance/boleto
    está vazia (nada PENDENTE/PROCESSANDO), para não matar um lance no meio.
  • Os timers (Gmail, Anglo, Fraga e Bitello, backup) disparam sozinhos assim que o
    robô sobe, se perderam o horário (ver robo_config.toml) — nada se perde.
Se a coluna crm_ativo_em não existir (migração 33 não rodada) ou sob_demanda estiver
desligado, volta ao modo antigo: robô sempre ligado.

Uso: python watchdog_robo.py            # age
     python watchdog_robo.py --simular  # só mostra a decisão, não sobe nem mata
"""

import os
import subprocess
import sys
import tomllib
from datetime import datetime, timezone

from dotenv import load_dotenv

_AQUI = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_AQUI, ".env"))

PID_FILE = os.path.join(_AQUI, "robo.pid")
LOG = os.path.join(_AQUI, "logs", "watchdog.log")
CONSOLE = os.path.join(_AQUI, "logs", "console.log")
CONFIG = os.path.join(_AQUI, "robo_config.toml")
LIMITE_SEG = int(os.getenv("WATCHDOG_LIMITE_SEG", "180"))
PY_ROBO = ["py", "-V:3.14", "worker_consorbens.py"]   # o python padrão (3.15) não tem as libs
SIMULAR = "--simular" in sys.argv


def log(msg):
    linha = f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] {msg}"
    print(linha, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def _config_sob_demanda() -> tuple[bool, int]:
    """(ativo, minutos_apos_sair). Padrão: ativo, 60 min."""
    try:
        with open(CONFIG, "rb") as f:
            c = tomllib.load(f).get("sob_demanda", {})
        return bool(c.get("ativo", True)), int(c.get("minutos_apos_sair", 60))
    except Exception:
        return True, 60


def _idade_seg(ts) -> float | None:
    if not ts:
        return None
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _ler_estado():
    """(hb_idade_seg, crm_idade_seg|None, coluna_existe, fila_ocupada)."""
    from supabase import create_client
    sb = create_client(os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_KEY", "").strip())
    hb = _idade_seg((sb.table("robo_status").select("atualizado_em").eq("id", 1).execute().data or [{}])[0]
                    .get("atualizado_em"))
    try:
        r = sb.table("robo_status").select("crm_ativo_em").eq("id", 1).execute()
        crm, coluna = _idade_seg((r.data or [{}])[0].get("crm_ativo_em")), True
    except Exception:
        crm, coluna = None, False          # migração 33 ainda não rodou
    try:
        fila = sb.table("fila_automacao").select("id").in_("status", ["PENDENTE", "PROCESSANDO"]).limit(1).execute()
        ocupada = bool(fila.data)
    except Exception:
        ocupada = True                     # na dúvida, não desliga
    return hb, crm, coluna, ocupada


def decidir(hb_idade, crm_idade, coluna, fila_ocupada, sob_demanda, minutos, pid_vivo) -> tuple[str, str]:
    """Devolve (acao, motivo). acao ∈ {'ok', 'subir', 'reiniciar', 'desligar', 'nada'}."""
    atrasado = hb_idade is None or hb_idade > LIMITE_SEG
    if not sob_demanda or not coluna:
        modo = "sempre ligado" + ("" if coluna or not sob_demanda else " (coluna crm_ativo_em não existe — rode a migração 33)")
        if not atrasado and pid_vivo:
            return "ok", f"{modo}: robô vivo"
        return ("reiniciar" if pid_vivo else "subir"), f"{modo}: robô parado/travado"
    querido = crm_idade is not None and crm_idade <= minutos * 60
    if querido:
        if not atrasado and pid_vivo:
            return "ok", f"CRM ativo há {crm_idade/60:.0f} min: robô vivo"
        return ("reiniciar" if pid_vivo else "subir"), f"CRM ativo há {crm_idade/60:.0f} min: robô precisa estar ligado"
    quando = "nunca" if crm_idade is None else f"há {crm_idade/60:.0f} min"
    if not pid_vivo:
        return "nada", f"CRM sem uso ({quando}) e robô já desligado"
    if fila_ocupada:
        return "ok", f"CRM sem uso ({quando}), mas há lance/boleto na fila — mantenho ligado"
    return "desligar", f"CRM sem uso ({quando}) e fila vazia — desligo o robô"


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
    """Sobe o robô direto no Python 3.14, sem janela, com a saída indo para logs/console.log."""
    try:
        os.makedirs(os.path.dirname(CONSOLE), exist_ok=True)
        saida = open(CONSOLE, "ab")
        flags = 0x08000000 | 0x00000008          # CREATE_NO_WINDOW | DETACHED_PROCESS
        subprocess.Popen(PY_ROBO, cwd=_AQUI, stdout=saida, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        log("subi o robô (py -V:3.14 worker_consorbens.py, oculto)")
    except Exception as e:
        log(f"falha ao subir o robô: {e}")


def main():
    sob, minutos = _config_sob_demanda()
    try:
        hb, crm, coluna, ocupada = _ler_estado()
    except Exception as e:
        log(f"não consegui ler o Supabase ({e}) — não mexo no robô.")
        return
    pid = _pid_vivo()
    acao, motivo = decidir(hb, crm, coluna, ocupada, sob, minutos, pid)
    log(f"{acao.upper()} — {motivo} (heartbeat {'?' if hb is None else f'{hb:.0f}s'}, pid {pid})")
    if SIMULAR or acao in ("ok", "nada"):
        return
    if acao == "desligar":
        _matar(pid)
    elif acao == "reiniciar":
        _matar(pid)
        _subir()
    elif acao == "subir":
        _subir()


if __name__ == "__main__":
    main()
    sys.exit(0)
