"""
worker_consorbens.py — Robô ÚNICO da Consorbens (roda no PC do escritório).

Um processo só, sempre ligado, que:
  • vigia a `fila_automacao` e executa LANCE / BOLETO / coletas / relatórios
    (dispatch por um dicionário HANDLERS — adicionar função = 1 linha);
  • tem um CRON INTERNO que dispara os robôs de API (Gmail Yamaha, Gmail
    Itaú, Importar Anglo) nos horários de `robo_config.toml` — sem Agendador
    de Tarefas do Windows;
  • bate heartbeat em `robo_status` (bolinha 🟢 SERVER no ERP);
  • retoma sozinho o que ficou pela metade (reenfileirar_interrompidos).

Substitui o `worker_lances.py` e as 3 tarefas do Agendador (ver
SETUP_SEMPRE_LIGADO.md).

USO (PC do escritório):
    cd worker
    python worker_consorbens.py                 # sobe o supervisor
    python worker_consorbens.py --rodar-agora gmail_itau   # roda 1 timer na hora
    python worker_consorbens.py --rodar-agora anglo --dry
Config: worker/robo_config.toml  (relido a cada ciclo).
"""

import os
import sys
import time
import json
import threading
import traceback
import tomllib
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)
load_dotenv(os.path.join(_AQUI, ".env"))

import handlers_gmail          # noqa: E402
import handlers_anglo          # noqa: E402
import handlers_coleta         # noqa: E402

CONFIG_PATH = os.path.join(_AQUI, "robo_config.toml")
CRON_ESTADO = os.path.join(_AQUI, "robo_cron_estado.json")
LOG_DIR = os.path.join(_AQUI, "logs")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
NEWCON_URL = os.getenv("NEWCON_URL", "").strip()
NEWCON_EMPRESA_COFRE = os.getenv("NEWCON_EMPRESA_COFRE", "YAMAHA NEWCON").strip()
NEWCON_LOGIN_RESERVA = os.getenv("NEWCON_LOGIN", "").strip()
NEWCON_SENHA_RESERVA = os.getenv("NEWCON_SENHA", "").strip()
TIMEOUT_CONFIRMACAO = int(os.getenv("TIMEOUT_CONFIRMACAO", "180"))
TIMEOUT_ELEMENTO = int(os.getenv("TIMEOUT_ELEMENTO", "60"))
MAX_TENTATIVAS = int(os.getenv("MAX_TENTATIVAS", "3"))
DIA_ENVIO_MENSAL = int(os.getenv("DIA_ENVIO_MENSAL", "5"))
HEARTBEAT_SEG = int(os.getenv("HEARTBEAT_SEG", "25"))
ADMINS_COM_BOLETO = ["YAMAHA"]

_DIAS = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6}


# ----------------------------------------------------------------- infra
def log(msg: str) -> None:
    linha = f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] {msg}"
    print(linha, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "robo.log"), "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s) -> str:
    import unicodedata
    s = str(s or "").strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s.replace(" ", "")


def ler_config() -> dict:
    try:
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        log(f"⚠️ Não li {CONFIG_PATH} ({e}) — usando padrões seguros.")
        return {"geral": {"modo_simulacao": True, "navegador_visivel": True, "intervalo_seg": 25}}


def conectar_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY não configurados no .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def bater_heartbeat(sb: Client) -> None:
    try:
        sb.table("robo_status").update({"atualizado_em": agora_iso()}).eq("id", 1).execute()
    except Exception as e:
        log(f"⚠️ heartbeat falhou: {e}")


def iniciar_heartbeat_thread() -> None:
    def _loop():
        try:
            sb_hb = conectar_supabase()
        except Exception as e:
            log(f"⚠️ heartbeat não iniciou: {e}")
            return
        while True:
            bater_heartbeat(sb_hb)
            time.sleep(HEARTBEAT_SEG)
    threading.Thread(target=_loop, daemon=True).start()
    log(f"💓 heartbeat ligado (a cada {HEARTBEAT_SEG}s).")


# ----------------------------------------------------------- fila / erros
MARCADORES_TECNICOS = [
    "targetclosederror", "has been closed", "target page, context or browser",
    "browser has been closed", "connection closed", "não consegui voltar",
    "nao consegui voltar", "tela de atendimento", "timeouterror",
]
MARCADORES_PERIGO = ["confirmar", "comprovante", "protocolo"]


def _deve_reofertar(mensagem: str) -> bool:
    msg = (mensagem or "").lower()
    if any(p in msg for p in MARCADORES_PERIGO):
        return False
    return any(m in msg for m in MARCADORES_TECNICOS)


def marcar(sb: Client, pid, **campos):
    sb.table("fila_automacao").update(campos).eq("id", pid).execute()


def _prio_pedido(pedido: dict, cfg: dict) -> int:
    tipo = (pedido.get("tipo") or "").upper()
    p = pedido.get("prioridade")
    if p is not None:
        return int(p)
    return int(cfg.get("fila", {}).get("prioridade", {}).get(tipo, 50))


def pegar_proximo_pedido(sb: Client, cfg: dict):
    """Mais urgente primeiro. LANCE/BOLETO entram sem `prioridade` do ERP —
    o coalesce no Python garante que fiquem à frente das coletas."""
    tipos = list(HANDLERS.keys())
    res = (sb.table("fila_automacao").select("*")
           .eq("status", "PENDENTE").in_("tipo", tipos)
           .order("criado_em", desc=False).limit(50).execute())
    dados = res.data or []
    if not dados:
        return None
    dados.sort(key=lambda r: (_prio_pedido(r, cfg), r.get("criado_em") or ""))
    return dados[0]


def deve_ceder(sb: Client, cfg: dict, prioridade_atual: int) -> bool:
    """True se há um PENDENTE mais urgente (nº de prioridade menor) esperando."""
    try:
        res = (sb.table("fila_automacao").select("tipo,prioridade,criado_em")
               .eq("status", "PENDENTE").in_("tipo", ["LANCE", "BOLETO"])
               .limit(1).execute())
        if res.data:
            return _prio_pedido(res.data[0], cfg) < prioridade_atual
    except Exception:
        pass
    return False


def reenfileirar_interrompidos(sb: Client):
    try:
        proc = (sb.table("fila_automacao").select("id,cliente,grupo,cota,tipo")
                .in_("tipo", list(HANDLERS.keys())).eq("status", "PROCESSANDO").execute())
        err = (sb.table("fila_automacao").select("id,cliente,grupo,cota,mensagem,tipo")
               .in_("tipo", ["LANCE", "BOLETO"]).eq("status", "ERRO").execute())
        alvos = list(proc.data or [])
        for r in (err.data or []):
            if _deve_reofertar(r.get("mensagem")):
                alvos.append(r)
        for r in alvos:
            marcar(sb, r["id"], status="PENDENTE", mensagem=None,
                   iniciado_em=None, concluido_em=None)
            log(f"↩️  reenfileirado #{r['id']} [{r.get('tipo')}] {r.get('cliente') or ''}")
        if alvos:
            log(f"↩️  {len(alvos)} tarefa(s) interrompida(s) voltaram para a fila.")
    except Exception as e:
        log(f"⚠️ erro ao reenfileirar: {e}")


# --------------------------------------------------------- Newcon (sessão)
def buscar_credenciais_newcon(sb: Client):
    try:
        res = (sb.table("senhas_sistema").select("login,senha,empresa")
               .ilike("empresa", NEWCON_EMPRESA_COFRE).execute())
        if res.data:
            reg = res.data[0]
            login, senha = (reg.get("login") or "").strip(), (reg.get("senha") or "").strip()
            if login and senha:
                return login, senha
    except Exception as e:
        log(f"⚠️ cofre de senhas: {e}")
    if NEWCON_LOGIN_RESERVA and NEWCON_SENHA_RESERVA:
        return NEWCON_LOGIN_RESERVA, NEWCON_SENHA_RESERVA
    raise RuntimeError("Sem credencial do Newcon (cofre 'senhas_sistema' ou .env).")


def preparar_newcon(sb: Client, visivel: bool):
    from playwright.sync_api import sync_playwright
    import newcon
    login_newcon, senha_newcon = buscar_credenciais_newcon(sb)
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=not visivel)
    ctx_kwargs = {"accept_downloads": True,
                  "permissions": ["clipboard-read", "clipboard-write"]}
    if os.path.exists(newcon.STORAGE_STATE):
        context = browser.new_context(storage_state=newcon.STORAGE_STATE, **ctx_kwargs)
    else:
        context = browser.new_context(**ctx_kwargs)
    page = context.new_page()
    page.set_default_timeout(TIMEOUT_ELEMENTO * 1000)
    page.set_default_navigation_timeout(TIMEOUT_ELEMENTO * 1000)
    page.on("dialog", lambda d: d.dismiss())
    page.goto(NEWCON_URL)
    try:
        logado = newcon.esta_logado(page)
    except NotImplementedError:
        logado = False
    if not logado:
        log("Newcon: sessão inválida — logando…")
        newcon.fazer_login(page, context, login_newcon, senha_newcon)
        context.storage_state(path=newcon.STORAGE_STATE)
    else:
        log("Newcon: sessão salva reutilizada. 👍")
    return {"pw": pw, "browser": browser, "context": context, "page": page}


def _fechar_navegador(ctx):
    if not ctx:
        return
    for k in ("browser", "pw"):
        try:
            (ctx[k].close if k == "browser" else ctx[k].stop)()
        except Exception:
            pass


# --------------------------------------------------------------- HANDLERS
def h_lance_boleto(sb, pedido, ctx, cfg):
    """LANCE / BOLETO — copiado do worker_lances.processar_pedido."""
    pid = pedido["id"]
    tipo = (pedido.get("tipo") or "LANCE").upper()
    n = (pedido.get("tentativas") or 0) + 1
    sim = bool(cfg.get("geral", {}).get("modo_simulacao", True))
    desc = f"{pedido.get('cliente')} (G{pedido.get('grupo')}/C{pedido.get('cota')})"
    log(f"→ #{pid} [{tipo}] tent {n}: {desc}")
    marcar(sb, pid, status="PROCESSANDO", iniciado_em=agora_iso(), tentativas=n)
    try:
        protocolo, extras = None, {}
        if sim:
            time.sleep(4)
            status = "OK"
            if tipo == "BOLETO":
                mensagem = "Boleto gerado (SIMULAÇÃO)"
                extras = {"codigo_barras": "00000.00000 (SIM)",
                          "vencimento": datetime.now().strftime("%d/%m/%Y"), "em_atraso": False}
            else:
                mensagem = "Lance ofertado (SIMULAÇÃO)"
                protocolo = "SIMULACAO"
        else:
            page = ctx["page"]
            if tipo == "BOLETO":
                from newcon import gerar_boleto
                status, mensagem, extras = gerar_boleto(page, pedido, TIMEOUT_CONFIRMACAO)
            else:
                from newcon import ofertar_lance
                status, mensagem, protocolo = ofertar_lance(page, pedido, TIMEOUT_CONFIRMACAO)

        if status == "OK":
            campos = {"status": "SUCESSO", "mensagem": mensagem,
                      "protocolo": protocolo, "concluido_em": agora_iso()}
            campos.update(extras)
            marcar(sb, pid, **campos)
            log(f"   ✅ #{pid} OK: {mensagem}")
            return {"ok": True}
        if status in ("JA_PAGO", "SEM_BOLETO", "JA_OFERTADO"):
            campos = {"status": status, "mensagem": mensagem, "concluido_em": agora_iso()}
            campos.update(extras)
            marcar(sb, pid, **campos)
            log(f"   ℹ️ #{pid} {status}: {mensagem}")
            return {"ok": True}
        marcar(sb, pid, status="ERRO", mensagem=mensagem, concluido_em=agora_iso())
        log(f"   ❌ #{pid} ERRO (conferir): {mensagem}")
        return {"ok": False, "negocio": True}
    except Exception as e:
        erro = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        if n < MAX_TENTATIVAS:
            marcar(sb, pid, status="PENDENTE",
                   mensagem=f"Erro técnico (tent {n}/{MAX_TENTATIVAS}): {erro}",
                   iniciado_em=None, concluido_em=None)
        else:
            marcar(sb, pid, status="ERRO",
                   mensagem=f"Falhou após {n} tentativas: {erro}", concluido_em=agora_iso())
        return {"ok": False, "reiniciar": True}


def h_relatorio_comissao(sb, pedido, ctx, cfg):
    """RELATORIO_COMISSAO — baixa PDF(s) de comissão pagos (Newcon).
    `baixar_comissoes` abre o SEU PRÓPRIO navegador — então fechamos o do
    supervisor antes, pra não haver 2 sessões Newcon ao mesmo tempo."""
    import importlib
    pid = pedido["id"]
    payload = pedido.get("payload") or {}
    mes = payload.get("mes")            # "AAAA-MM" ou None = mês atual
    if _newcon_ref["c"] is not None:
        _fechar_navegador(_newcon_ref["c"])
        _newcon_ref["c"] = None
    marcar(sb, pid, status="PROCESSANDO", iniciado_em=agora_iso())
    argv0 = list(sys.argv)
    try:
        sys.argv = ["baixar_comissoes.py"] + (["--mes", mes] if mes else ["--mes-atual"])
        mod = importlib.import_module("baixar_comissoes")
        importlib.reload(mod)
        mod.main()
        marcar(sb, pid, status="SUCESSO",
               mensagem=f"Relatório de comissão baixado ({mes or 'mês atual'})",
               concluido_em=agora_iso())
        return {"ok": True}
    except Exception as e:
        marcar(sb, pid, status="ERRO", mensagem=f"{type(e).__name__}: {e}",
               concluido_em=agora_iso())
        return {"ok": False, "negocio": True}
    finally:
        sys.argv[:] = argv0


def _ceder_cb_factory(sb, cfg, prioridade):
    return lambda: deve_ceder(sb, cfg, prioridade)


def h_coleta_grupos(sb, pedido, ctx, cfg):
    pid = pedido["id"]
    prio = _prio_pedido(pedido, cfg)
    payload = pedido.get("payload") or {}
    marcar(sb, pid, status="PROCESSANDO", iniciado_em=agora_iso())
    r = handlers_coleta.coleta_grupos(
        sb, ctx, _reabrir_holder["fn"],
        produtos=payload.get("produtos"), prazo_pref=payload.get("prazo", "longo"),
        salvar=True, forcar=bool(payload.get("forcar")),
        ceder_cb=_ceder_cb_factory(sb, cfg, prio))
    return _fechar_fila(sb, pid, r)


def h_coleta_assembleias(sb, pedido, ctx, cfg):
    pid = pedido["id"]
    prio = _prio_pedido(pedido, cfg)
    payload = pedido.get("payload") or {}
    marcar(sb, pid, status="PROCESSANDO", iniciado_em=agora_iso())
    r = handlers_coleta.coleta_assembleias(
        sb, ctx, _reabrir_holder["fn"],
        n_ass=int(payload.get("assembleias", 3)), salvar=True,
        forcar=bool(payload.get("forcar")),
        ceder_cb=_ceder_cb_factory(sb, cfg, prio))
    return _fechar_fila(sb, pid, r)


def h_coleta_tabelas(sb, pedido, ctx, cfg):
    pid = pedido["id"]
    payload = pedido.get("payload") or {}
    marcar(sb, pid, status="PROCESSANDO", iniciado_em=agora_iso())
    r = handlers_coleta.coleta_tabelas(salvar=True, forcar=bool(payload.get("forcar")))
    return _fechar_fila(sb, pid, r)


def h_stub(sb, pedido, ctx, cfg):
    pid = pedido["id"]
    marcar(sb, pid, status="ERRO",
           mensagem="PLANEJAR_SIMULACAO ainda não liberado (gate da seção 6 do plano).",
           concluido_em=agora_iso())
    return {"ok": False, "negocio": True}


def _fechar_fila(sb, pid, r: dict):
    """Traduz o retorno de um handler de coleta para o estado da fila."""
    if r.get("ceder"):
        marcar(sb, pid, status="PENDENTE", iniciado_em=None,
               progresso=(r.get("mensagem") or "pausado (cede a vez)"))
        log(f"   ⏸️  #{pid} cedeu a vez — volta pra fila.")
        return {"ok": True}
    if r.get("ok"):
        marcar(sb, pid, status="SUCESSO", mensagem=r.get("mensagem"),
               concluido_em=agora_iso())
        log(f"   ✅ #{pid} {r.get('mensagem')}")
        return {"ok": True}
    marcar(sb, pid, status="ERRO", mensagem=r.get("mensagem"), concluido_em=agora_iso())
    log(f"   ❌ #{pid} {r.get('mensagem')}")
    return {"ok": False, "negocio": True}


HANDLERS = {
    "LANCE": h_lance_boleto,
    "BOLETO": h_lance_boleto,
    "RELATORIO_COMISSAO": h_relatorio_comissao,
    "COLETA_GRUPOS": h_coleta_grupos,
    "COLETA_ASSEMBLEIAS": h_coleta_assembleias,
    "COLETA_TABELAS": h_coleta_tabelas,
    "PLANEJAR_SIMULACAO": h_stub,
}
# handlers que precisam da sessão Newcon aberta
PRECISA_NEWCON = {"LANCE", "BOLETO", "RELATORIO_COMISSAO",
                  "COLETA_GRUPOS", "COLETA_ASSEMBLEIAS"}

_reabrir_holder = {"fn": None}   # o loop principal injeta a função de reabrir o Newcon
_newcon_ref = {"c": None}        # referência viva ao contexto Newcon (o loop mantém)


# --------------------------------------------------------------- CRON API
def _cron_ler():
    try:
        with open(CRON_ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _cron_gravar(d):
    try:
        with open(CRON_ESTADO, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log(f"⚠️ não gravei {CRON_ESTADO}: {e}")


def _venceu(quando: str, ultimo_iso: str) -> bool:
    """`quando` = '<dia> HH:MM'. True se já passou da hora hoje e ainda não rodou hoje."""
    try:
        dia_txt, hhmm = quando.split()
        hh, mm = map(int, hhmm.split(":"))
    except Exception:
        return False
    agora = datetime.now()
    if dia_txt != "diario":
        if agora.weekday() != _DIAS.get(dia_txt, -1):
            return False
    if (agora.hour, agora.minute) < (hh, mm):
        return False
    if ultimo_iso:
        try:
            ult = datetime.fromisoformat(ultimo_iso)
            if ult.date() == agora.date():
                return False
        except Exception:
            pass
    return True


def _rodar_timer(nome: str, cfg: dict, dry: bool = False) -> dict:
    tconf = cfg.get("timers", {}).get(nome, {})
    if nome == "gmail_yamaha":
        r = handlers_gmail.baixar_yamaha(
            cfg.get("caminhos", {}).get("gmail_yamaha_scripts", handlers_gmail._DEF_YAMAHA))
    elif nome == "gmail_itau":
        r = handlers_gmail.baixar_itau(
            cfg.get("caminhos", {}).get("gmail_itau_scripts", handlers_gmail._DEF_ITAU))
    elif nome == "anglo":
        r = handlers_anglo.importar_anglo(
            cfg.get("caminhos", {}).get("anglo_dir", handlers_anglo._DEF_ANGLO), dry=dry)
    else:
        return {"ok": False, "mensagem": f"timer desconhecido: {nome}"}
    # encadeamento (ex.: depois do gmail_yamaha, enfileira COLETA_TABELAS)
    for tipo in tconf.get("encadear", []):
        _enfileirar_interno(nome, tipo)
    return r


_SB_ENQ = {"c": None}


def _enfileirar_interno(origem: str, tipo: str, payload: dict | None = None):
    try:
        sb = _SB_ENQ["c"] or conectar_supabase()
        _SB_ENQ["c"] = sb
        # não duplica se já há um PENDENTE/PROCESSANDO do mesmo tipo
        ex = (sb.table("fila_automacao").select("id")
              .eq("tipo", tipo).in_("status", ["PENDENTE", "PROCESSANDO"])
              .limit(1).execute())
        if ex.data:
            return
        sb.table("fila_automacao").insert({
            "tipo": tipo, "status": "PENDENTE", "solicitado_por": f"CRON:{origem}",
            "payload": payload or {},
        }).execute()
        log(f"🗓️  cron enfileirou {tipo} (origem {origem}).")
    except Exception as e:
        log(f"⚠️ não enfileirei {tipo}: {e}")


def cron_tick(cfg: dict):
    est = _cron_ler()
    # timers de API (sem navegador) — rodam inline
    for nome, tconf in (cfg.get("timers", {}) or {}).items():
        if not isinstance(tconf, dict) or not tconf.get("ativo"):
            continue
        if _venceu(tconf.get("quando", ""), est.get(nome, "")):
            log(f"🗓️  timer '{nome}' venceu — rodando…")
            try:
                r = _rodar_timer(nome, cfg)
                log(f"   {'✅' if r.get('ok') else '⚠️'} {nome}: {r.get('mensagem')}")
            except Exception as e:
                log(f"   ❌ {nome} falhou: {e}")
            est[nome] = datetime.now().isoformat()
            _cron_gravar(est)
    # coletas que usam o Newcon — vão pela fila
    for nome, cconf in (cfg.get("coleta", {}) or {}).items():
        if not isinstance(cconf, dict) or not cconf.get("ativo"):
            continue
        if _venceu(cconf.get("quando", ""), est.get(f"coleta_{nome}", "")):
            tipo = {"grupos_sync": "COLETA_GRUPOS", "tabelas": "COLETA_TABELAS"}.get(nome)
            if tipo:
                _enfileirar_interno(f"cron:{nome}", tipo)
                est[f"coleta_{nome}"] = datetime.now().isoformat()
                _cron_gravar(est)


# --------------------------------------------------------------- boletos mês
def _tem_boleto_no_mes(sb, venda_id) -> bool:
    try:
        h = datetime.now()
        res = (sb.table("fila_automacao").select("id").eq("tipo", "BOLETO")
               .eq("venda_id", venda_id).gte("criado_em", f"{h.year}-{h.month:02d}-01")
               .limit(1).execute())
        return bool(res.data)
    except Exception:
        return True


def enfileirar_mensais_do_mes(sb):
    hoje = datetime.now()
    if hoje.day < DIA_ENVIO_MENSAL:
        return
    mes = hoje.strftime("%Y-%m")
    try:
        st = sb.table("robo_status").select("ultimo_mensal").eq("id", 1).execute()
        if (st.data or [{}])[0].get("ultimo_mensal") == mes:
            return
    except Exception:
        return
    try:
        vendas = (sb.table("vendas").select("*").eq("BOLETO_MENSAL", True).execute().data or [])
    except Exception as e:
        log(f"⚠️ cotas mensais: {e}")
        return
    ins = 0
    for v in vendas:
        if _norm(v.get("ADMINISTRADORA")) not in ADMINS_COM_BOLETO:
            continue
        if _norm(v.get("STATUS")) not in ("EMANDAMENTO", "EMATRASO"):
            continue
        if _norm(v.get("TIPO_PRODUTO")) == "CONSORCIOCONTEMPLADO":
            continue
        vid = v.get("id")
        if vid is None or _tem_boleto_no_mes(sb, vid):
            continue
        try:
            sb.table("fila_automacao").insert({
                "tipo": "BOLETO", "venda_id": vid,
                "cliente": v.get("Nome do cliente"), "vendedor": v.get("VENDEDOR"),
                "produto": v.get("PRODUTO"), "administradora": "Yamaha",
                "grupo": str(v.get("GRUPO") or "").strip(),
                "cota": str(v.get("COTA") or "").strip(),
                "status": "PENDENTE", "solicitado_por": "AUTO_MENSAL",
            }).execute()
            ins += 1
        except Exception as e:
            log(f"⚠️ mensal {v.get('GRUPO')}/{v.get('COTA')}: {e}")
    try:
        sb.table("robo_status").update({"ultimo_mensal": mes}).eq("id", 1).execute()
    except Exception:
        pass
    if ins:
        log(f"📅 boletos mensais de {mes}: {ins} cota(s) enfileirada(s).")


# --------------------------------------------------------------- guardas
def _checar_caminhos(cfg):
    faltando = []
    for k, p in (cfg.get("caminhos", {}) or {}).items():
        if k.endswith(("_yamaha", "_itau")) and not os.path.isdir(p):
            faltando.append(f"{k} -> {p}")
    if faltando:
        raise SystemExit("Drive não montado / pastas faltando:\n  " + "\n  ".join(faltando))


# --------------------------------------------------------------- CLI direto
def _rodar_agora():
    cfg = ler_config()
    nome = sys.argv[sys.argv.index("--rodar-agora") + 1]
    dry = "--dry" in sys.argv
    log(f"--rodar-agora {nome}{' (dry)' if dry else ''}")
    r = _rodar_timer(nome, cfg, dry=dry)
    log(f"resultado: {r}")
    sys.exit(0 if r.get("ok") else 1)


# --------------------------------------------------------------- loop
def main():
    if "--rodar-agora" in sys.argv:
        _rodar_agora()
        return

    log("=== ROBÔ ÚNICO CONSORBENS — iniciando ===")
    try:
        with open(os.path.join(_AQUI, "robo.pid"), "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    cfg = ler_config()
    _checar_caminhos(cfg)
    sim = bool(cfg.get("geral", {}).get("modo_simulacao", True))
    visivel = bool(cfg.get("geral", {}).get("navegador_visivel", True))
    intervalo = int(cfg.get("geral", {}).get("intervalo_seg", 25))
    log(f"modo: {'SIMULAÇÃO' if sim else 'NEWCON REAL'} | navegador {'visível' if visivel else 'segundo plano'} | intervalo {intervalo}s")

    sb = conectar_supabase()
    bater_heartbeat(sb)
    iniciar_heartbeat_thread()
    reenfileirar_interrompidos(sb)

    n_reab = [0]

    def reabrir_newcon():
        n_reab[0] += 1
        log(f"🔄 reabrindo o Newcon (reabertura {n_reab[0]})…")
        _fechar_navegador(_newcon_ref["c"])
        novo = preparar_newcon(sb, visivel)
        _newcon_ref["c"] = novo
        return novo["page"]

    _reabrir_holder["fn"] = reabrir_newcon

    try:
        while True:
            cfg = ler_config()          # config a quente
            try:
                enfileirar_mensais_do_mes(sb)
                cron_tick(cfg)
            except Exception as e:
                log(f"⚠️ cron/mensais: {e}")

            try:
                pedido = pegar_proximo_pedido(sb, cfg)
            except Exception as e:
                log(f"⚠️ ler fila: {e}")
                time.sleep(intervalo)
                continue

            if not pedido:
                time.sleep(intervalo)
                continue

            tipo = (pedido.get("tipo") or "").upper()
            handler = HANDLERS.get(tipo)
            if not handler:
                marcar(sb, pedido["id"], status="ERRO",
                       mensagem=f"tipo sem handler: {tipo}", concluido_em=agora_iso())
                continue

            sim = bool(cfg.get("geral", {}).get("modo_simulacao", True))
            precisa = tipo in PRECISA_NEWCON and not sim
            if precisa and _newcon_ref["c"] is None:
                _newcon_ref["c"] = preparar_newcon(sb, visivel)

            r = handler(sb, pedido, _newcon_ref["c"], cfg)

            if r.get("reiniciar") and not sim:
                _fechar_navegador(_newcon_ref["c"])
                _newcon_ref["c"] = None
            # segue imediatamente pro próximo pendente

    except KeyboardInterrupt:
        log("Encerrando por Ctrl+C…")
    finally:
        _fechar_navegador(_newcon_ref["c"])
        log("=== ROBÔ ÚNICO encerrado ===")


if __name__ == "__main__":
    main()
