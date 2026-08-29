"""
worker_lances.py — Robô de Oferta de Lances (roda no PC do escritório).

O QUE ELE FAZ:
  1. Vigia a tabela 'fila_automacao' no Supabase.
  2. Pega os pedidos PENDENTES do tipo LANCE (mais antigos primeiro).
  3. Marca como PROCESSANDO, oferta no Newcon, espera a confirmação.
  4. Grava o resultado de volta: SUCESSO (com a mensagem) ou ERRO.

COMO RODAR (no PC do escritório):
    cd worker
    pip install -r requirements.txt
    playwright install chromium         (só na 1ª vez; não precisa no modo simulação)
    copie .env.exemplo para .env e preencha
    python worker_lances.py

DICA: comece com MODO_SIMULACAO=true no .env para testar o circuito inteiro
(CRM -> fila -> robô -> CRM) sem tocar no Newcon.
"""

import os
import time
import threading
import traceback
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# --------------------------- Configuração ---------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
NEWCON_URL = os.getenv("NEWCON_URL", "").strip()
NEWCON_EMPRESA_COFRE = os.getenv("NEWCON_EMPRESA_COFRE", "YAMAHA NEWCON").strip()
# Reserva (opcional): só usadas se o cofre não tiver a credencial
NEWCON_LOGIN_RESERVA = os.getenv("NEWCON_LOGIN", "").strip()
NEWCON_SENHA_RESERVA = os.getenv("NEWCON_SENHA", "").strip()

MODO_SIMULACAO = os.getenv("MODO_SIMULACAO", "true").strip().lower() == "true"
NAVEGADOR_VISIVEL = os.getenv("NAVEGADOR_VISIVEL", "true").strip().lower() == "true"
INTERVALO = int(os.getenv("INTERVALO_SEGUNDOS", "30"))
TIMEOUT_CONFIRMACAO = int(os.getenv("TIMEOUT_CONFIRMACAO", "180"))
# Quanto o robô espera CADA campo/botão aparecer antes de agir (servidor lento)
TIMEOUT_ELEMENTO = int(os.getenv("TIMEOUT_ELEMENTO", "60"))
# Quantas vezes tenta a MESMA cota (reiniciando o navegador) antes de desistir
MAX_TENTATIVAS = int(os.getenv("MAX_TENTATIVAS", "3"))
# Dia do mês em que os boletos MENSAIS são gerados automaticamente (padrão: dia 5).
# Se o robô estiver desligado no dia 5, ele dispara assim que for ligado depois.
DIA_ENVIO_MENSAL = int(os.getenv("DIA_ENVIO_MENSAL", "5"))
# De quanto em quanto tempo o robô "bate o ponto" (bolinha SERVER no CRM)
HEARTBEAT_SEG = int(os.getenv("HEARTBEAT_SEG", "25"))
# Administradoras com automação de boleto (espelha ADMINS_COM_BOLETO do CRM)
ADMINS_COM_BOLETO = ["YAMAHA"]


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] {msg}", flush=True)


def _norm(s) -> str:
    """Igual ao normalizar_string do CRM: MAIÚSCULA, sem acento, sem espaço."""
    import unicodedata
    s = str(s or "").strip().upper()
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    return s.replace(" ", "")


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------- Supabase ---------------------------
def conectar_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY não configurados no .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def pegar_proximo_pedido(sb: Client):
    """Busca o pedido mais antigo PENDENTE (LANCE ou BOLETO)."""
    res = (sb.table("fila_automacao")
           .select("*")
           .eq("status", "PENDENTE")
           .in_("tipo", ["LANCE", "BOLETO"])
           .order("criado_em", desc=False)
           .limit(1)
           .execute())
    dados = res.data or []
    return dados[0] if dados else None


def marcar(sb: Client, pedido_id: int, **campos):
    sb.table("fila_automacao").update(campos).eq("id", pedido_id).execute()


def bater_heartbeat(sb: Client) -> None:
    """Atualiza robo_status.atualizado_em = agora. O CRM lê isso para acender
    a bolinha SERVER (🟢 ligado / 🔴 desligado) em cima da logo.
    Nunca derruba o robô se falhar (é só um 'ponto')."""
    try:
        sb.table("robo_status").update({"atualizado_em": agora_iso()}).eq("id", 1).execute()
    except Exception as e:
        log(f"⚠️ Não consegui bater o heartbeat (robo_status): {e}")


def iniciar_heartbeat_thread() -> None:
    """Bate o ponto num thread separado a cada HEARTBEAT_SEG segundos, independente
    do que o robô está fazendo. Assim a bolinha SERVER não fica vermelha durante um
    boleto/lance demorado (que segura o loop principal por vários minutos).
    Usa um cliente Supabase PRÓPRIO (não compartilha o do loop — evita conflito entre threads)."""
    def _loop():
        try:
            sb_hb = conectar_supabase()
        except Exception as e:
            log(f"⚠️ Heartbeat não iniciou (sem Supabase): {e}")
            return
        while True:
            bater_heartbeat(sb_hb)
            time.sleep(HEARTBEAT_SEG)
    threading.Thread(target=_loop, daemon=True).start()
    log(f"💓 Heartbeat ligado (a cada {HEARTBEAT_SEG}s).")


def _mes_ref() -> str:
    return datetime.now().strftime("%Y-%m")


def _inicio_mes_atual_iso() -> str:
    h = datetime.now()
    return f"{h.year}-{h.month:02d}-01"


def _tem_boleto_no_mes(sb: Client, venda_id) -> bool:
    """True se a cota já tem um pedido de BOLETO neste mês (evita duplicar)."""
    try:
        res = (sb.table("fila_automacao").select("id")
               .eq("tipo", "BOLETO").eq("venda_id", venda_id)
               .gte("criado_em", _inicio_mes_atual_iso())
               .limit(1).execute())
        return bool(res.data)
    except Exception:
        return True  # na dúvida, NÃO enfileira de novo


def enfileirar_mensais_do_mes(sb: Client) -> None:
    """No dia DIA_ENVIO_MENSAL (ou depois, se o robô só ligou mais tarde), enfileira
    automaticamente os boletos das cotas marcadas com 'Envio Mensal' (vendas.BOLETO_MENSAL).
    Roda uma vez por mês: grava o mês processado em robo_status.ultimo_mensal.
    É idempotente — só enfileira cota que ainda não tem BOLETO neste mês."""
    hoje = datetime.now()
    if hoje.day < DIA_ENVIO_MENSAL:
        return
    mes = _mes_ref()

    # Já processou este mês? (persistente, sobrevive a reinício do robô)
    try:
        st_res = sb.table("robo_status").select("ultimo_mensal").eq("id", 1).execute()
        ja = (st_res.data or [{}])[0].get("ultimo_mensal")
        if ja == mes:
            return
    except Exception as e:
        log(f"⚠️ Não consegui ler robo_status.ultimo_mensal: {e}")
        return

    log(f"📅 Dia {hoje.day} — verificando boletos MENSAIS de {mes}…")
    try:
        vres = (sb.table("vendas")
                .select('id,"Nome do cliente",VENDEDOR,PRODUTO,GRUPO,COTA,'
                        'STATUS,ADMINISTRADORA,BOLETO_MENSAL,"TIPO_PRODUTO"')
                .eq("BOLETO_MENSAL", True).execute())
        vendas = vres.data or []
    except Exception as e:
        # Fallback: nomes de coluna podem variar — tenta sem aspas específicas
        log(f"⚠️ Erro ao ler cotas mensais (tento fallback): {e}")
        try:
            vres = sb.table("vendas").select("*").eq("BOLETO_MENSAL", True).execute()
            vendas = vres.data or []
        except Exception as e2:
            log(f"⚠️ Não consegui ler as cotas mensais: {e2}")
            return

    inseridos = 0
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
        payload = {
            "tipo": "BOLETO", "venda_id": vid,
            "cliente": v.get("Nome do cliente"), "vendedor": v.get("VENDEDOR"),
            "produto": v.get("PRODUTO"), "administradora": "Yamaha",
            "grupo": str(v.get("GRUPO") or "").strip(),
            "cota": str(v.get("COTA") or "").strip(),
            "status": "PENDENTE", "solicitado_por": "AUTO_MENSAL",
        }
        try:
            sb.table("fila_automacao").insert(payload).execute()
            inseridos += 1
        except Exception as e:
            log(f"⚠️ Falha ao enfileirar mensal {v.get('Nome do cliente')} "
                f"({v.get('GRUPO')}/{v.get('COTA')}): {e}")

    # Marca o mês como processado (mesmo com 0 inseridos: já estavam na fila)
    try:
        sb.table("robo_status").update({"ultimo_mensal": mes}).eq("id", 1).execute()
    except Exception as e:
        log(f"⚠️ Não consegui gravar ultimo_mensal={mes}: {e}")
    log(f"📅 Boletos mensais de {mes}: {inseridos} cota(s) enfileirada(s) automaticamente.")


# Mensagens de erro TÉCNICO que aconteceram ANTES de confirmar — seguro repetir,
# porque o lance NÃO chegou a ser registrado.
MARCADORES_TECNICOS = [
    "targetclosederror",
    "has been closed",
    "target page, context or browser",
    "browser has been closed",
    "connection closed",
    "não consegui voltar",
    "nao consegui voltar",
    "tela de atendimento",
    "timeouterror",   # timeout técnico (ex: Localizar) — mas veja MARCADORES_PERIGO abaixo
]

# Se a mensagem citar qualquer um destes, o erro foi PERTO/DEPOIS de confirmar:
# o lance PODE ter sido registrado. Nesse caso NÃO repetimos sozinhos (evita lance duplo).
MARCADORES_PERIGO = ["confirmar", "comprovante", "protocolo"]


def _deve_reofertar(mensagem: str) -> bool:
    """True se é seguro devolver o lance para a fila e tentar de novo."""
    msg = (mensagem or "").lower()
    if any(p in msg for p in MARCADORES_PERIGO):
        return False  # zona de risco: pode ter ofertado — deixa para conferência manual
    return any(m in msg for m in MARCADORES_TECNICOS)


def reenfileirar_interrompidos(sb: Client):
    """No arranque, devolve para a fila (PENDENTE) os lances que ficaram pela metade
    por interrupção/erro técnico ANTES de confirmar (presos em PROCESSANDO, ou com
    ERRO técnico seguro). NÃO repete erros de negócio (nome não confere, sem lance)
    nem erros perto do Confirmar (para não ofertar em dobro)."""
    try:
        proc = (sb.table("fila_automacao").select("id,cliente,grupo,cota")
                .in_("tipo", ["LANCE", "BOLETO"]).eq("status", "PROCESSANDO").execute())
        err = (sb.table("fila_automacao").select("id,cliente,grupo,cota,mensagem")
               .in_("tipo", ["LANCE", "BOLETO"]).eq("status", "ERRO").execute())

        alvos = list(proc.data or [])
        for r in (err.data or []):
            if _deve_reofertar(r.get("mensagem")):
                alvos.append(r)

        if not alvos:
            return

        for r in alvos:
            marcar(sb, r["id"], status="PENDENTE", mensagem=None,
                   iniciado_em=None, concluido_em=None)
            log(f"↩️  Reenfileirado #{r['id']}: {r.get('cliente')} "
                f"(Grupo {r.get('grupo')}/Cota {r.get('cota')})")
        log(f"↩️  {len(alvos)} lance(s) interrompido(s) voltaram para a fila e serão tentados de novo.")
    except Exception as e:
        log(f"⚠️ Erro ao reenfileirar interrompidos: {e}")


def buscar_credenciais_newcon(sb: Client) -> tuple[str, str]:
    """Lê login e senha do Newcon do cofre de senhas do CRM (tabela senhas_sistema),
    procurando pela empresa configurada em NEWCON_EMPRESA_COFRE.
    Se não achar, cai para as credenciais de reserva do .env."""
    try:
        res = (sb.table("senhas_sistema")
               .select("login,senha,empresa")
               .ilike("empresa", NEWCON_EMPRESA_COFRE)
               .execute())
        if res.data:
            reg = res.data[0]
            login = (reg.get("login") or "").strip()
            senha = (reg.get("senha") or "").strip()
            if login and senha:
                log(f"Credencial do Newcon lida do cofre (empresa '{NEWCON_EMPRESA_COFRE}').")
                return login, senha
            log(f"⚠️ Empresa '{NEWCON_EMPRESA_COFRE}' achada no cofre, mas login/senha vazios.")
        else:
            log(f"⚠️ Não achei a empresa '{NEWCON_EMPRESA_COFRE}' no cofre de senhas.")
    except Exception as e:
        log(f"⚠️ Erro ao ler o cofre de senhas: {e}")

    if NEWCON_LOGIN_RESERVA and NEWCON_SENHA_RESERVA:
        log("Usando credencial de RESERVA do .env.")
        return NEWCON_LOGIN_RESERVA, NEWCON_SENHA_RESERVA

    raise RuntimeError(
        f"Sem credencial do Newcon: cadastre login e senha na aba 'Senhas' do CRM "
        f"com a empresa '{NEWCON_EMPRESA_COFRE}', ou preencha NEWCON_LOGIN/NEWCON_SENHA no .env."
    )


# --------------------------- Processamento ---------------------------
def processar_pedido(sb: Client, pedido: dict, contexto_newcon) -> str:
    """Processa um pedido. Retorna:
       'ok'          -> ofertado com sucesso
       'erro_negocio'-> falha que NÃO se repete sozinha (nome não confere, sem lance,
                        ou 'confirmar sem comprovante'); o navegador continua bom
       'reiniciar'   -> erro técnico (voltar travou, navegação lenta, navegador fechado);
                        o navegador precisa ser reiniciado do zero e a cota volta pra fila"""
    pid = pedido["id"]
    tipo = (pedido.get("tipo") or "LANCE").upper()
    n = (pedido.get("tentativas") or 0) + 1
    desc = f"{pedido.get('cliente')} (Grupo {pedido.get('grupo')}/Cota {pedido.get('cota')})"
    log(f"→ Processando #{pid} (tentativa {n}) [{tipo}]: {desc}")

    marcar(sb, pid, status="PROCESSANDO", iniciado_em=agora_iso(), tentativas=n)

    try:
        protocolo = None
        extras = {}  # campos extras do BOLETO (codigo_barras, vencimento, em_atraso)

        if MODO_SIMULACAO:
            time.sleep(5)  # finge o tempo de processamento do Newcon
            status = "OK"
            if tipo == "BOLETO":
                mensagem = "Boleto gerado com sucesso (SIMULAÇÃO)"
                extras = {
                    "codigo_barras": "34191.79001 01234.567890 12345.678901 2 99990000012345 (SIM)",
                    "vencimento": datetime.now().strftime("%d/%m/%Y"),
                    "em_atraso": False,
                }
            else:
                lance = pedido.get("pct_lance"); emb = pedido.get("pct_embutido"); prop = pedido.get("pct_proprio")
                mensagem = (f"Lance ofertado com sucesso (SIMULAÇÃO) — "
                            f"lance {lance}% / embutido {emb}% / próprios {prop}%")
                protocolo = "SIMULACAO"
        else:
            page = contexto_newcon["page"]
            if tipo == "BOLETO":
                from newcon import gerar_boleto
                status, mensagem, extras = gerar_boleto(page, pedido, TIMEOUT_CONFIRMACAO)
            else:
                from newcon import ofertar_lance
                status, mensagem, protocolo = ofertar_lance(page, pedido, TIMEOUT_CONFIRMACAO)

        if status == "OK":
            campos = {"status": "SUCESSO", "mensagem": mensagem,
                      "protocolo": protocolo, "concluido_em": agora_iso()}
            campos.update(extras)  # só o boleto traz codigo_barras/vencimento/em_atraso
            marcar(sb, pid, **campos)
            log(f"   ✅ #{pid} OK [{tipo}]: {mensagem}")
            return "ok"
        elif status in ("JA_PAGO", "SEM_BOLETO"):
            # Boleto do mês já pago, ou não há boleto neste mês — não é erro.
            campos = {"status": status, "mensagem": mensagem, "concluido_em": agora_iso()}
            campos.update(extras)
            marcar(sb, pid, **campos)
            log(f"   ℹ️ #{pid} [{tipo}] {status}: {mensagem}")
            return "ok"
        elif status == "JA_OFERTADO":
            marcar(sb, pid, status="JA_OFERTADO", mensagem=mensagem,
                   protocolo=protocolo, concluido_em=agora_iso())
            log(f"   ☑️ #{pid} JÁ ESTAVA OFERTADO: {mensagem}")
            return "ok"
        else:  # FALHA
            # Falha "de negócio": não repete sozinha, fica para conferência
            marcar(sb, pid, status="ERRO", mensagem=mensagem, concluido_em=agora_iso())
            log(f"   ❌ #{pid} ERRO (conferir): {mensagem}")
            return "erro_negocio"

    except Exception as e:
        # Erro técnico (voltar travou, navegador fechado, etc.): reinicia do zero
        erro = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        if n < MAX_TENTATIVAS:
            marcar(sb, pid, status="PENDENTE",
                   mensagem=f"Erro técnico (tentativa {n}/{MAX_TENTATIVAS}) — reiniciando: {erro}",
                   iniciado_em=None, concluido_em=None)
            log(f"   ⚠️ #{pid} erro técnico — vou reiniciar o navegador e tentar de novo.")
        else:
            marcar(sb, pid, status="ERRO",
                   mensagem=f"Falhou após {n} tentativas: {erro}", concluido_em=agora_iso())
            log(f"   ❌ #{pid} desisti após {n} tentativas.")
        return "reiniciar"


# --------------------------- Newcon (login/sessão) ---------------------------
def preparar_newcon(sb: Client):
    """Abre o navegador e garante o login no Newcon.
    Retorna um dicionário de contexto (ou None no modo simulação)."""
    if MODO_SIMULACAO:
        log("MODO SIMULAÇÃO ligado — o Newcon NÃO será aberto.")
        return None

    from playwright.sync_api import sync_playwright
    import newcon

    # Pega a credencial atual direto do cofre de senhas do CRM
    login_newcon, senha_newcon = buscar_credenciais_newcon(sb)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=not NAVEGADOR_VISIVEL)

    # Reaproveita a sessão salva, se existir (login persistente).
    # accept_downloads + permissão de clipboard = necessários para os BOLETOS
    # (baixar o PDF e ler o "Copiar Código").
    ctx_kwargs = {"accept_downloads": True, "permissions": ["clipboard-read", "clipboard-write"]}
    if os.path.exists(newcon.STORAGE_STATE):
        context = browser.new_context(storage_state=newcon.STORAGE_STATE, **ctx_kwargs)
    else:
        context = browser.new_context(**ctx_kwargs)

    page = context.new_page()
    # Dá folga para o Newcon lento: espera cada elemento até TIMEOUT_ELEMENTO
    page.set_default_timeout(TIMEOUT_ELEMENTO * 1000)
    page.set_default_navigation_timeout(TIMEOUT_ELEMENTO * 1000)
    # Segurança: qualquer caixa de diálogo do Newcon (ex.: "já credenciado, deseja
    # continuar?") é CANCELADA automaticamente — o robô nunca oferta em dobro.
    page.on("dialog", lambda d: d.dismiss())
    page.goto(NEWCON_URL)

    # Tenta usar a sessão salva; se não estiver logado, loga com a credencial reserva
    try:
        logado = newcon.esta_logado(page)
    except NotImplementedError:
        logado = False

    if not logado:
        log("Sessão inválida/expirada — fazendo login com a credencial do cofre…")
        newcon.fazer_login(page, context, login_newcon, senha_newcon)
        context.storage_state(path=newcon.STORAGE_STATE)  # salva a nova sessão
        log("Login efetuado e sessão salva.")
    else:
        log("Sessão salva reutilizada — já estava logado. 👍")

    return {"pw": pw, "browser": browser, "context": context, "page": page}


def _fechar_navegador(ctx):
    """Fecha o navegador com segurança (usado para reiniciar do zero)."""
    if not ctx:
        return
    try:
        ctx["browser"].close()
    except Exception:
        pass
    try:
        ctx["pw"].stop()
    except Exception:
        pass


# --------------------------- Loop principal ---------------------------
def main():
    log("=== Robô de Lances iniciado ===")
    log(f"Modo: {'SIMULAÇÃO' if MODO_SIMULACAO else 'NEWCON REAL'} | "
        f"Intervalo: {INTERVALO}s | Timeout confirmação: {TIMEOUT_CONFIRMACAO}s")

    sb = conectar_supabase()

    # Bate o ponto já no arranque e liga o heartbeat contínuo (bolinha SERVER no CRM)
    bater_heartbeat(sb)
    iniciar_heartbeat_thread()

    # Recupera lances que ficaram pela metade por interrupção (ex: navegador fechado sem querer)
    reenfileirar_interrompidos(sb)

    contexto_newcon = None

    try:
        while True:
            # Agenda mensal: no dia 5 (ou depois), enfileira os boletos mensais automáticos
            enfileirar_mensais_do_mes(sb)

            try:
                pedido = pegar_proximo_pedido(sb)
            except Exception as e:
                log(f"Erro ao ler a fila: {e}. Tentando de novo em {INTERVALO}s.")
                time.sleep(INTERVALO)
                continue

            if not pedido:
                time.sleep(INTERVALO)
                continue

            # Só abre o Newcon quando aparece um pedido (economia). Se o navegador
            # foi reiniciado, ele é recriado aqui já com um novo acesso + login.
            if contexto_newcon is None and not MODO_SIMULACAO:
                contexto_newcon = preparar_newcon(sb)

            resultado = processar_pedido(sb, pedido, contexto_newcon)

            # Erro técnico -> reinicia o navegador do zero (novo acesso e login).
            # A cota já voltou para a fila e será tentada de novo no próximo ciclo,
            # continuando de onde parou (as demais cotas seguem depois).
            if resultado == "reiniciar" and not MODO_SIMULACAO:
                log("🔄 Reiniciando o navegador do zero (novo acesso e login)...")
                _fechar_navegador(contexto_newcon)
                contexto_newcon = None
            # segue imediatamente para o próximo pendente (sem esperar o intervalo)

    except KeyboardInterrupt:
        log("Encerrando por Ctrl+C…")
    finally:
        _fechar_navegador(contexto_newcon)
        log("=== Robô encerrado ===")


if __name__ == "__main__":
    main()
