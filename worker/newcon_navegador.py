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


def _lancar_solto(args) -> None:
    """Abre o Chrome do Newcon FORA da árvore de processos do robô (16/11/2026).
    Motivo: o watchdog desliga o robô com `taskkill /T` (mata o processo e os FILHOS). Com o
    Chrome como filho do robô, cada desligamento derrubava o navegador → login perdido →
    novo login quando o robô voltava. Pelo `cmd /c start` o Chrome nasce de um cmd que
    termina na hora: fica órfão, o /T não o alcança e a sessão do Newcon continua viva.
    (Também evita o CREATE_BREAKAWAY_FROM_JOB, que dava WinError 5 dentro do Agendador.)"""
    base = dict(close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    if os.name != "nt":
        subprocess.Popen(args, start_new_session=True, **base)
        return
    try:
        # string montada à mão: o `start ""` (título vazio) não sobrevive ao list2cmdline
        subprocess.Popen('cmd /c start "" /b ' + subprocess.list2cmdline(args),
                         creationflags=0x08000000, **base)          # CREATE_NO_WINDOW
        return
    except Exception:
        pass
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(args, creationflags=flags | 0x01000000, **base)   # + BREAKAWAY_FROM_JOB
    except PermissionError:
        subprocess.Popen(args, creationflags=flags, **base)


# ------------------------------------------------------------ contador de logins
ARQ_LOGINS = os.path.join(PASTA, "logs", "logins_newcon.log")
LOGINS_ALERTA_HORA = int(os.getenv("NEWCON_LOGINS_ALERTA_HORA", "4"))


def registrar_login(origem: str) -> int:
    """Anota cada login feito no Newcon (data, origem). Devolve quantos houve na última hora.
    Se passar de LOGINS_ALERTA_HORA, deixa um aviso com as causas prováveis no próprio arquivo
    e no log do robô — para alguém entender o motivo em vez de o robô ficar logando à toa."""
    agora = time.time()
    try:
        os.makedirs(os.path.dirname(ARQ_LOGINS), exist_ok=True)
        with open(ARQ_LOGINS, "a", encoding="utf-8") as f:
            f.write(f"{agora:.0f}\t{time.strftime('%d/%m %H:%M:%S')}\tLOGIN\t{origem}\n")
        n = 0
        with open(ARQ_LOGINS, encoding="utf-8") as f:
            for ln in f:
                try:
                    if "\tLOGIN\t" in ln and agora - float(ln.split("\t", 1)[0]) <= 3600:
                        n += 1
                except ValueError:
                    pass
        if n >= LOGINS_ALERTA_HORA:
            aviso = (f"⚠️ {n} logins no Newcon na última hora (o normal é 0 ou 1). Causas prováveis: "
                     "alguém usando o MESMO usuário do Newcon em outro navegador (um derruba o outro); "
                     "o navegador do robô sendo fechado (PC dormiu/reiniciou, alguém fechou a janela); "
                     "tarefa falhando e reabrindo. Veja logs/logins_newcon.log e logs/robo.log.")
            print("[newcon] " + aviso)
            with open(ARQ_LOGINS, "a", encoding="utf-8") as f:
                f.write(f"{agora:.0f}\t{time.strftime('%d/%m %H:%M:%S')}\tALERTA\t{aviso}\n")
        return n
    except Exception:
        return 0


def resumo_logins(horas=24) -> str:
    agora, linhas = time.time(), []
    try:
        with open(ARQ_LOGINS, encoding="utf-8") as f:
            for ln in f:
                p = ln.rstrip("\n").split("\t")
                if len(p) >= 4 and p[2] == "LOGIN" and agora - float(p[0]) <= horas * 3600:
                    linhas.append(f"{p[1]}  ({p[3]})")
    except Exception:
        pass
    return f"{len(linhas)} login(s) nas últimas {horas} h" + ("".join("\n  " + x for x in linhas) if linhas else "")


# ------------------------------------------------------------ manter a sessão viva
def ping(timeout_ms=30000) -> str:
    """Robô desligado mas o Chrome do Newcon aberto: recarrega a home NA ABA QUE JÁ EXISTE para a
    sessão não expirar (chamado pelo watchdog a cada X min). NUNCA loga e nunca abre aba nova.
    Retorna 'fechado' | 'sem_aba' | 'logado' | 'caiu'."""
    if not _no_ar():
        return "fechado"
    from playwright.sync_api import sync_playwright
    import newcon
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        pages = [p for c in browser.contexts for p in c.pages if "newkey.cny.com.br" in (p.url or "")]
        if not pages:
            return "sem_aba"
        page = pages[0]
        page.goto(newcon.HOME_URL, wait_until="domcontentloaded", timeout=timeout_ms)
        return "logado" if newcon.esta_logado(page) else "caiu"
    finally:
        try:
            pw.stop()            # só desconecta: o Chrome continua aberto
        except Exception:
            pass


def garantir_navegador(pw, visivel=True, url_inicial=None) -> None:
    """Se o navegador único não está aberto, abre (processo separado: fica aberto
    mesmo depois que o script que abriu terminar)."""
    if _no_ar():
        return
    exe = pw.chromium.executable_path
    os.makedirs(PERFIL, exist_ok=True)
    args = [exe, f"--remote-debugging-port={PORTA}", "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={PERFIL}", "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate", "--disable-popup-blocking", "--window-size=1300,850"]
    if not visivel:
        args.append("--start-minimized")
    args.append(url_inicial or os.getenv("NEWCON_URL", "https://newkey.cny.com.br/Intranet/frmMain.aspx"))
    _lancar_solto(args)
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
                    registrar_login("abrir_aba")
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
        print(resumo_logins())
        sys.exit(0)
    if "--ping" in sys.argv:
        sys.path.insert(0, PASTA)
        print("ping:", ping())
        sys.exit(0)
    sys.path.insert(0, PASTA)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PASTA, ".env"))
    from coletar_grupos import _conectar_sb
    pw, aba, ctx, page = abrir_aba(_conectar_sb())
    print("ok — URL:", page.url)
    aba.close(); pw.stop()
