# -*- coding: utf-8 -*-
r"""
newcon_navegador.py — UM navegador do Newcon, sempre aberto e logado (Breno, 16/11/2026).

Antes: cada script (worker, robô de grupos/assembleias, comissões, explorador)
abria o PRÓPRIO Chromium, logava, fazia o serviço e fechava. Resultado: o Newcon
abrindo/fechando e logando o tempo todo.

Agora:
  * existe UM Chromium "do robô" com porta de controle local (127.0.0.1:9333) e
    perfil próprio (o login fica guardado no perfil);
  * quem precisa do Newcon CONECTA nele e abre uma ABA; ao terminar fecha SÓ a aba;
  * o navegador continua aberto e logado para o próximo serviço;
  * se ele não estiver aberto, o primeiro que precisar abre (e loga 1 vez, com a
    senha do cofre `senhas_sistema`, igual sempre foi).

Uso direto (opcional):
    python newcon_navegador.py            # abre/garante o navegador e confere o login
    python newcon_navegador.py --status   # só diz se está aberto e logado
"""
import os
import sys
import time
import json
import subprocess
import urllib.request

PASTA = os.path.dirname(os.path.abspath(__file__))
PORTA = int(os.getenv("NEWCON_CDP_PORTA", "9333"))
CDP_URL = f"http://127.0.0.1:{PORTA}"
PERFIL = os.getenv("NEWCON_PERFIL_DIR", os.path.join(os.path.expanduser("~"), ".newcon_navegador_robo"))
TRAVA_LOGIN = os.path.join(PASTA, "newcon_login.lock")


def _no_ar() -> bool:
    try:
        with urllib.request.urlopen(CDP_URL + "/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def garantir_navegador(pw, visivel=True, url_inicial=None) -> None:
    """Se o navegador único não está aberto, abre (processo separado: fica aberto
    mesmo depois que o script que abriu terminar)."""
    if _no_ar():
        return
    exe = pw.chromium.executable_path
    os.makedirs(PERFIL, exist_ok=True)
    args = [exe, f"--remote-debugging-port={PORTA}", "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={PERFIL}", "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate", "--window-size=1300,850"]
    if not visivel:
        args.append("--start-minimized")
    args.append(url_inicial or os.getenv("NEWCON_URL", "https://newkey.cny.com.br/Intranet/frmMain.aspx"))
    flags = 0
    if os.name == "nt":
        # BREAKAWAY: o navegador não morre quando o processo que abriu termina/é encerrado
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                 | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000))
    subprocess.Popen(args, creationflags=flags, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    for _ in range(60):
        if _no_ar():
            time.sleep(1.5)
            return
        time.sleep(0.5)
    raise RuntimeError("não consegui abrir o navegador único do Newcon (porta %d)" % PORTA)


class _Trava:
    """Trava simples entre processos para só UM logar por vez."""
    def __enter__(self):
        fim = time.time() + 120
        while True:
            try:
                self.fd = os.open(TRAVA_LOGIN, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:                                   # trava velha (processo morreu)
                    if time.time() - os.path.getmtime(TRAVA_LOGIN) > 180:
                        os.remove(TRAVA_LOGIN)
                        continue
                except Exception:
                    pass
                if time.time() > fim:
                    raise RuntimeError("outro processo está logando no Newcon há muito tempo")
                time.sleep(1)

    def __exit__(self, *a):
        try:
            os.close(self.fd); os.remove(TRAVA_LOGIN)
        except Exception:
            pass


class AbaNewcon:
    """Faz o papel do 'browser' para quem já chamava browser.close():
    aqui close() fecha SÓ a aba deste script (e popups que ela abriu)."""
    def __init__(self, browser, page):
        self._browser, self._page, self._popups = browser, page, []
        page.on("popup", lambda p: self._popups.append(p))

    def close(self):
        for p in self._popups:
            try:
                if not p.is_closed():
                    p.close()
            except Exception:
                pass
        try:
            outras = [x for x in self._page.context.pages if x is not self._page and not x.is_closed()]
            if outras:
                self._page.close()
            else:
                # é a última aba: NÃO fecha (fecharia a janela). Deixa na home, logada.
                import newcon
                self._page.goto(newcon.HOME_URL, wait_until="domcontentloaded")
        except Exception:
            pass

    def __getattr__(self, k):
        return getattr(self._browser, k)


def _credenciais(sb):
    try:
        r = sb.table("senhas_sistema").select("login,senha,empresa") \
            .ilike("empresa", os.getenv("NEWCON_EMPRESA_COFRE", "YAMAHA NEWCON")).execute()
        return r.data[0]["login"].strip(), (r.data[0].get("senha") or "").strip()
    except Exception:
        return os.getenv("NEWCON_LOGIN", "").strip(), os.getenv("NEWCON_SENHA", "").strip()


def abrir_aba(sb=None, visivel=True, dialogo="aceitar", login=None, senha=None, timeout_ms=30000):
    """Conecta no navegador único (abre se precisar), cria UMA aba nova e garante login.
    Retorna (pw, aba_como_browser, contexto, page) — mesma forma do antigo _abrir().
    dialogo: 'aceitar' | 'recusar' | None (quem chamou cuida)."""
    from playwright.sync_api import sync_playwright
    import newcon
    pw = sync_playwright().start()
    try:
        garantir_navegador(pw, visivel=visivel)
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        try:
            ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://newkey.cny.com.br")
        except Exception:
            pass
        # aba "em branco" que o Chromium abre sozinho: reaproveita em vez de criar outra
        livre = [p for p in ctx.pages if (p.url or "").startswith(("about:blank", "chrome://newtab"))]
        page = livre[0] if livre else ctx.new_page()
        page.set_default_timeout(timeout_ms)
        page.set_default_navigation_timeout(timeout_ms)
        if dialogo == "aceitar":
            page.on("dialog", lambda d: d.accept())
        elif dialogo == "recusar":
            page.on("dialog", lambda d: d.dismiss())
        # vai na HOME (não na URL de login do .env, que sempre mostra o formulário de login)
        page.goto(newcon.HOME_URL, wait_until="domcontentloaded")
        if not newcon.esta_logado(page):
            with _Trava():
                page.goto(newcon.HOME_URL, wait_until="domcontentloaded")   # outro pode ter logado enquanto esperava
                if not newcon.esta_logado(page) and not page.locator("#edtUsuario").count():
                    page.goto(os.getenv("NEWCON_URL", newcon.HOME_URL))
                if not newcon.esta_logado(page):
                    if not (login and senha):
                        if sb is None:
                            raise RuntimeError("sem credencial para logar no Newcon")
                        login, senha = _credenciais(sb)
                    newcon.fazer_login(page, ctx, login, senha)
                    print("[newcon] login feito no navegador único (fica aberto e logado).")
        else:
            print("[newcon] navegador único já aberto e logado — só abri uma aba.")
        return pw, AbaNewcon(browser, page), ctx, page
    except Exception:
        try:
            pw.stop()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    if "--status" in sys.argv:
        print("navegador único:", "ABERTO" if _no_ar() else "fechado", f"(porta {PORTA}, perfil {PERFIL})")
        sys.exit(0)
    sys.path.insert(0, PASTA)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PASTA, ".env"))
    from coletar_grupos import _conectar_sb
    pw, aba, ctx, page = abrir_aba(_conectar_sb())
    print("ok — URL:", page.url)
    aba.close(); pw.stop()
