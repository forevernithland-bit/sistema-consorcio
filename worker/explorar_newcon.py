"""
explorar_newcon.py — Navegador guiado do Newcon.

Abre o Newcon logado numa janela VISÍVEL e fica anotando cada tela nova que
você abrir. Você navega com o mouse; o script escreve o "mapa" de cada tela
(URL, campos, botões, abas e o CONTEÚDO das tabelas/grids) no arquivo
`explorar_newcon.txt`. O Claude lê esse arquivo e vai entendendo o sistema.

USO (no PC do escritório):
    cd worker
    python explorar_newcon.py                 # começa; navegue à vontade
    python explorar_newcon.py --intervalo 3   # checa a tela a cada 3s (padrão 4)

Pare com Ctrl+C quando terminar. Não grava nada no Newcon — só lê telas.
"""
import os
import sys
import time
import hashlib
import datetime

from dotenv import load_dotenv

PASTA = os.path.dirname(__file__)
load_dotenv(os.path.join(PASTA, ".env"))
NEWCON_URL = os.getenv("NEWCON_URL", "").strip()
SAIDA = os.path.join(PASTA, "explorar_newcon.txt")

_JS_DUMP = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const txt = el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const rotulo = el => {
    if (el.id) { const l = document.querySelector('label[for="' + el.id + '"]');
                 if (l) return txt(l).slice(0, 45); }
    const td = el.closest('td');
    if (td && td.previousElementSibling) return txt(td.previousElementSibling).slice(0, 45);
    return '';
  };
  const out = { campos: [], acoes: [], tabelas: [] };
  for (const el of document.querySelectorAll('input,select,textarea')) {
    if (!vis(el)) continue;
    out.campos.push({ tag: el.tagName.toLowerCase(), type: el.type || '', id: el.id || '',
                      name: el.name || '', value: (el.value || '').slice(0, 40),
                      hint: rotulo(el),
                      opcoes: el.tagName === 'SELECT'
                        ? [...el.options].slice(0, 12).map(o => txt(o)).join(' | ') : '' });
  }
  for (const el of document.querySelectorAll(
      'a,button,[role=button],[role=menuitem],[role=tab],input[type=submit],input[type=image]')) {
    if (!vis(el)) continue;
    const t = txt(el) || el.value || el.title || el.getAttribute('aria-label') || '';
    if (!t && !el.id) continue;
    out.acoes.push({ id: el.id || '', txt: t.slice(0, 50) });
  }
  // tabelas/grids com pelo menos 2 linhas e algum número — as que interessam
  for (const tb of document.querySelectorAll('table')) {
    const linhas = [...tb.querySelectorAll('tr')].slice(0, 25)
      .map(tr => [...tr.querySelectorAll('th,td')].map(c => txt(c)).join(' | '))
      .filter(l => l.replace(/[\s|]/g, '').length > 0);
    if (linhas.length >= 2 && linhas.join('').match(/\d/)) {
      out.tabelas.push({ id: tb.id || '', linhas: linhas });
    }
  }
  return out;
}"""


def _dump(page):
    partes = []
    alvos = [page] + [f for f in page.frames if f is not page.main_frame]
    for i, fr in enumerate(alvos):
        try:
            d = fr.evaluate(_JS_DUMP)
        except Exception:
            continue
        if not (d["campos"] or d["acoes"] or d["tabelas"]):
            continue
        tag = "PAGINA" if i == 0 else f"IFRAME {getattr(fr, 'url', '')[:70]}"
        partes.append(f"--- {tag} ---")
        if d["campos"]:
            partes.append("  CAMPOS:")
            for c in d["campos"]:
                extra = f"  opcoes=[{c['opcoes']}]" if c["opcoes"] else ""
                partes.append(f"    <{c['tag']} type={c['type']}> id={c['id']!r} "
                              f"name={c['name']!r} value={c['value']!r} "
                              f"rotulo={c['hint']!r}{extra}")
        if d["acoes"]:
            partes.append("  BOTOES/LINKS:")
            for a in d["acoes"][:60]:
                partes.append(f"    id={a['id']!r}  txt={a['txt']!r}")
        for t in d["tabelas"]:
            partes.append(f"  TABELA id={t['id']!r}:")
            for l in t["linhas"]:
                partes.append(f"    {l}")
    return "\n".join(partes)


def main():
    args = sys.argv[1:]
    intervalo = 4
    if "--intervalo" in args:
        intervalo = int(args[args.index("--intervalo") + 1])

    from playwright.sync_api import sync_playwright
    from supabase import create_client
    import newcon

    url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_KEY", "").strip()
    sb = create_client(url, key) if url and key and "xxxx" not in url else None

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    kw = {"accept_downloads": True}
    if os.path.exists(newcon.STORAGE_STATE):
        ctx = browser.new_context(storage_state=newcon.STORAGE_STATE, **kw)
    else:
        ctx = browser.new_context(**kw)
    page = ctx.new_page()
    page.set_default_timeout(30000)
    page.on("dialog", lambda d: d.accept())
    page.goto(NEWCON_URL)

    if not newcon.esta_logado(page):
        if sb is None:
            print("Sem credencial e sessão inválida. Configure o worker/.env."); return
        try:
            res = sb.table("senhas_sistema").select("login,senha,empresa") \
                .ilike("empresa", os.getenv("NEWCON_EMPRESA_COFRE", "YAMAHA NEWCON")).execute()
            login, senha = res.data[0]["login"].strip(), (res.data[0].get("senha") or "").strip()
        except Exception:
            login = os.getenv("NEWCON_LOGIN", "").strip()
            senha = os.getenv("NEWCON_SENHA", "").strip()
        newcon.fazer_login(page, ctx, login, senha)
        ctx.storage_state(path=newcon.STORAGE_STATE)
        print("Login efetuado.")
    else:
        print("Sessão reaproveitada.")

    open(SAIDA, "w", encoding="utf-8").write(
        f"# Exploração do Newcon — iniciada {datetime.datetime.now():%d/%m/%Y %H:%M}\n"
        f"# Navegue na janela do robô. Cada tela nova é anotada aqui. Ctrl+C para parar.\n")
    print(f"\nPronto. NAVEGUE na janela que abriu.")
    print(f"O mapa de cada tela vai sendo escrito em:\n  {SAIDA}\n")
    print("Deixe rodando e me avise a cada tela importante que abrir. Ctrl+C encerra.\n")

    ultimo_hash = None
    try:
        while True:
            page.wait_for_timeout(intervalo * 1000)
            try:
                # a aba ativa pode ter mudado (popup)
                pg = ctx.pages[-1] if ctx.pages else page
                corpo = _dump(pg)
                cabecalho = f"URL: {pg.url}"
            except Exception as e:
                corpo, cabecalho = f"(erro ao ler: {e})", "URL: ?"
            h = hashlib.md5((cabecalho + corpo).encode("utf-8", "ignore")).hexdigest()
            if h == ultimo_hash or not corpo.strip():
                continue
            ultimo_hash = h
            bloco = (f"\n{'=' * 92}\n"
                     f"[{datetime.datetime.now():%H:%M:%S}] {cabecalho}\n"
                     f"{'=' * 92}\n{corpo}\n")
            with open(SAIDA, "a", encoding="utf-8") as f:
                f.write(bloco)
            print(f"[{datetime.datetime.now():%H:%M:%S}] anotei uma tela nova "
                  f"({len(corpo)} chars) — {pg.url[:80]}")
    except KeyboardInterrupt:
        print("\nEncerrado. Mapa salvo em", SAIDA)
    finally:
        try:
            browser.close(); pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
