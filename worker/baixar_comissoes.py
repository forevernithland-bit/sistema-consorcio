"""
baixar_comissoes.py — Baixa em lote os relatorios de "Comissoes Pagas" da Yamaha.

TAREFA AVULSA (nao entra na fila do robo). Roda no PC do escritorio, reaproveitando
o login/sessao do robo de lances (newcon.py). Para cada periodo quinzenal listado
em periodos_comissao.json:

    Venda -> Comissao -> (tela "Comissoes Pagas")
      Encerramento: <ini> a <fim>       (o unico campo que muda entre relatorios)
      Data Alocacao: 01/08/2024 a 31/08/2026   (fixo)
      Data Venda: NAO mexer
      Unidade de Negocio: 000001 YAMAHA ADM DE CONSORCIO LTDA
      Comissionado: 010852 ECOCLIM SUSTENTAVEL
      -> Processar
      -> (tela de opcoes) Analitico + Quebra de Pagina + "Demonstrar 2a linha com
         detalhes do pagamento"  [+ modelo de impressao, ver MODELO abaixo]
      -> Imprimir  => salva o PDF em PASTA_DESTINO com o nome vindo do JSON

MODOS:
    python baixar_comissoes.py --descobrir
        Loga, abre Venda->Comissao e IMPRIME todos os ids de campo / nomes de botao
        da tela (e some). Use isto p/ preencher o dict SELETORES abaixo com precisao.

    python baixar_comissoes.py                 # baixa todos os periodos que faltam
    python baixar_comissoes.py --mes-atual     # as 2 quinzenas do mes corrente
    python baixar_comissoes.py --mes 2026-08   # as 2 quinzenas de agosto/2026
    python baixar_comissoes.py --desde 16/10/2024  # de tal data ate hoje
    python baixar_comissoes.py --so 01/10/2024 # baixa so esse periodo (teste)
    python baixar_comissoes.py --geral         # baixa 1 relatorio 01/10/2024 -> hoje
    python baixar_comissoes.py --refazer       # rebaixa mesmo os PDFs ja existentes

Depois: python conferir_comissoes.py --geral "<...GERAL.pdf>"
"""

import os
import re
import sys
import json
import time
import datetime

from dotenv import load_dotenv

PASTA = os.path.dirname(__file__)
load_dotenv(os.path.join(PASTA, ".env"))

NEWCON_URL = os.getenv("NEWCON_URL", "").strip()
NAVEGADOR_VISIVEL = os.getenv("NAVEGADOR_VISIVEL", "true").strip().lower() == "true"
TIMEOUT_ELEMENTO = int(os.getenv("TIMEOUT_ELEMENTO", "60"))

# Onde salvar (pedido do usuario: Downloads). Subpasta so p/ nao virar bagunca.
PASTA_DESTINO = os.getenv("PASTA_COMISSOES",
                          os.path.join(os.path.expanduser("~"), "Downloads", "Comissoes Yamaha"))

# Modelo de "Impressao em Tela": "Filial" (igual aos PDFs de exemplo e ao que o
# usuario marca na mao) ou "Comissionado". O importador do ERP agora le os dois.
MODELO = os.getenv("MODELO_COMISSAO", "Filial")

# Mensagens de alerta (window.alert) que o Newcon dispara. Preenchido pelo
# handler de dialogo; lido em baixar_um() para saber se o periodo veio vazio.
AVISOS = []
RE_SEM_COMISSAO = re.compile(r"n.o\s+existe\s+comiss.o\s+paga", re.I)

DATA_ALOCACAO_INI = "01/08/2024"
DATA_ALOCACAO_FIM = "31/08/2026"
INICIO_HISTORICO = "01/10/2024"

# ============================================================================
# SELETORES  --  tela frmConVeRelComissaoPaga.aspx (mapeados via --descobrir 29/08/26)
# ============================================================================
SELETORES = {
    "enc_ini":     "#ctl00_Conteudo_edtEncerramentoInicial",
    "enc_fim":     "#ctl00_Conteudo_edtEncerramentoFinal",
    "aloc_ini":    "#ctl00_Conteudo_edtDataAlocacaoInicial",
    "aloc_fim":    "#ctl00_Conteudo_edtDataAlocacaoFinal",
    # Data Venda: NAO mexer (fica 01/01/1900 a 01/01/3000)
    "chk_unidade":   "#ctl00_Conteudo_grdSelecaoUnidade_ctl02_chkSelecionado",     # 000001 YAMAHA ADM
    "chk_comissionado": "#ctl00_Conteudo_grdAlocacaoComissionado_ctl02_chkSelecionado",  # 010852 ECOCLIM SUSTENTAVEL
    "chk_vigente":     "#ctl00_Conteudo_chkSituacaoComissionado_0",
    "chk_nao_vigente": "#ctl00_Conteudo_chkSituacaoComissionado_1",
    "rb_nf_todas":     "#ctl00_Conteudo_rblST_Nota_Fiscal_0",
    "btn_processar":   "#ctl00_Conteudo_btnProcessar",
    # ---- overlay de opcoes de impressao (mesma pagina, aparece apos Processar) ----
    "opt_analitico":     "#ctl00_Conteudo_rblST_Relatorio_1",   # Sintetico = _0
    "opt_modelo_filial": "#ctl00_Conteudo_rblImprimir_0",       # FL
    "opt_modelo_comis":  "#ctl00_Conteudo_rblImprimir_5",       # CM
    "chk_quebra_pagina": "#ctl00_Conteudo_ckbQuebra",
    "chk_segunda_linha": "#ctl00_Conteudo_ckbBaseCalculo",      # "Demonstrar 2a linha c/ detalhes do pagamento"
    "btn_imprimir":      "#ctl00_Conteudo_btnImprimir",
}


# --------------------------------------------------------------------------
def _cred_newcon(sb):
    """Login/senha do Newcon (mesmo cofre do robo de lances)."""
    empresa = os.getenv("NEWCON_EMPRESA_COFRE", "YAMAHA NEWCON").strip()
    try:
        res = sb.table("senhas_sistema").select("login,senha,empresa").ilike("empresa", empresa).execute()
        if res.data and res.data[0].get("login"):
            return res.data[0]["login"].strip(), (res.data[0].get("senha") or "").strip()
    except Exception as e:
        print(f"[cofre] {e}")
    return os.getenv("NEWCON_LOGIN", "").strip(), os.getenv("NEWCON_SENHA", "").strip()


def _abrir(sb):
    from playwright.sync_api import sync_playwright
    import newcon
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=not NAVEGADOR_VISIVEL)
    kw = {"accept_downloads": True}
    if os.path.exists(newcon.STORAGE_STATE):
        ctx = browser.new_context(storage_state=newcon.STORAGE_STATE, **kw)
    else:
        ctx = browser.new_context(**kw)
    page = ctx.new_page()
    page.set_default_timeout(TIMEOUT_ELEMENTO * 1000)
    page.set_default_navigation_timeout(TIMEOUT_ELEMENTO * 1000)
    # Dialogos do Newcon: sempre clicar OK, guardando a mensagem. O aviso
    # "Nao existe comissao paga para o periodo informado" chega por aqui.
    def _dialogo(d):
        try:
            AVISOS.append(d.message or "")
            _log(f"  [dialogo] {d.message}")
        except Exception:
            pass
        try:
            d.accept()
        except Exception:
            pass

    ctx.on("dialog", _dialogo)     # vale para todas as abas/popups
    page.on("dialog", _dialogo)
    page.goto(NEWCON_URL)
    if not newcon.esta_logado(page):
        login, senha = _cred_newcon(sb)
        if not login:
            raise RuntimeError("Sem credencial do Newcon (cofre vazio e .env sem NEWCON_LOGIN).")
        newcon.fazer_login(page, ctx, login, senha)
        ctx.storage_state(path=newcon.STORAGE_STATE)
        print("[newcon] login efetuado, sessao salva.")
    else:
        print("[newcon] sessao reaproveitada.")
    return pw, browser, ctx, page


def _loc(page, sel):
    """Aceita string (CSS/text=) ou dict {'role','name'}."""
    if isinstance(sel, dict):
        return page.get_by_role(sel["role"], name=sel["name"])
    return page.locator(sel)


_JS_CLICAVEIS = """() => {
  const vis = el => { const r = el.getBoundingClientRect();
    return r.width>0 && r.height>0 && getComputedStyle(el).visibility!=='hidden'; };
  const rotulo = el => {
    // dica de rotulo: <label for>, ou texto da celula/linha a esquerda
    if (el.id) { const l = document.querySelector('label[for=\"'+el.id+'\"]');
                 if (l) return l.textContent.replace(/\\s+/g,' ').trim().slice(0,40); }
    let td = el.closest('td'); if (td && td.previousElementSibling)
      return td.previousElementSibling.textContent.replace(/\\s+/g,' ').trim().slice(0,40);
    let tr = el.closest('tr'); if (tr)
      return tr.textContent.replace(/\\s+/g,' ').trim().slice(0,50);
    return '';
  };
  const out = [];
  for (const el of document.querySelectorAll(
      "a,button,input,select,textarea,[role=button],[role=link],[role=menuitem],[role=tab],[onclick]")) {
    if (!vis(el)) continue;
    out.push({tag: el.tagName.toLowerCase(), type: el.type||'', role: el.getAttribute('role')||'',
              id: el.id||'', name: el.name||'', value: (el.value||'').slice(0,40),
              text: (el.innerText||el.textContent||'').replace(/\\s+/g,' ').trim().slice(0,60),
              hint: rotulo(el)});
  }
  return out;
}"""


def _dump(page, titulo):
    print(f"\n===== {titulo} =====")
    print(f"URL: {page.url}")
    try:
        itens = page.evaluate(_JS_CLICAVEIS)
    except Exception as e:
        print(f"(nao consegui ler a pagina: {e})")
        itens = []
    for it in itens:
        print(f"  <{it['tag']} type={it['type']} role={it['role']}> "
              f"id={it['id']!r} name={it['name']!r} value={it['value']!r} "
              f"txt={it['text']!r} hint={it.get('hint','')!r}")
    # frames (o Newcon usa iframe em varias telas)
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        try:
            sub = fr.evaluate(_JS_CLICAVEIS)
        except Exception:
            continue
        if sub:
            print(f"  --- iframe {fr.url[:90]} ---")
            for it in sub:
                print(f"    <{it['tag']} type={it['type']} role={it['role']}> "
                      f"id={it['id']!r} name={it['name']!r} txt={it['text']!r} hint={it.get('hint','')!r}")
    return itens


def _tentar_clicar(page, textos):
    """Tenta clicar num item cujo texto/nome bate (button, link, aba, texto solto)."""
    for t in textos:
        for tentativa in (
            lambda: page.get_by_role("button", name=t, exact=False),
            lambda: page.get_by_role("link", name=t, exact=False),
            lambda: page.get_by_role("menuitem", name=t, exact=False),
            lambda: page.get_by_role("tab", name=t, exact=False),
            lambda: page.get_by_text(t, exact=True),
        ):
            try:
                loc = tentativa().first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=8000)
                    page.wait_for_load_state("networkidle")
                    print(f"[nav] cliquei em '{t}'")
                    return True
            except Exception:
                continue
    return False


def _abrir_comissoes_pagas(page):
    """Venda -> Comissao -> (arvore) Comissoes Pagas."""
    _tentar_clicar(page, ["Venda", "Venda de Proposta"])
    _tentar_clicar(page, ["Comissão", "Comissao"])
    # a arvore da esquerda: no "Comissoes Pagas" (id conhecido do dump)
    for tentativa in (
        lambda: page.locator("#ctl00_Conteudo_ctl00_tvwMenut2"),
        lambda: page.get_by_role("link", name="Comissões Pagas", exact=False),
        lambda: page.get_by_text("Comissões Pagas", exact=True),
    ):
        try:
            loc = tentativa().first
            if loc.count():
                loc.click(timeout=8000)
                page.wait_for_load_state("networkidle")
                print("[nav] abri 'Comissoes Pagas'")
                return True
        except Exception:
            continue
    return False


def _ir_para_comissao(page):
    if not _abrir_comissoes_pagas(page):
        raise RuntimeError("Nao cheguei em 'Comissoes Pagas' — ver dump.")


def descobrir(page):
    _dump(page, "TELA POS-LOGIN (menu principal)")
    _tentar_clicar(page, ["Venda", "Venda de Proposta"])
    _dump(page, "APOS 'Venda' (submenu)")
    _tentar_clicar(page, ["Comissão", "Comissao"])
    _dump(page, "APOS 'Comissao' (arvore do modulo)")
    try:
        _abrir_comissoes_pagas(page)
        page.wait_for_timeout(2000)
        _dump(page, "TELA 'Comissoes Pagas' — CAMPOS DO FILTRO")

        # vai um passo alem: preenche 1 periodo curto, marca os filtros e clica
        # Processar, so p/ CAPTURAR A TELA DE OPCOES DE IMPRESSAO (Analitico etc.)
        print("\n[descobrir] preenchendo 01/07/2026 a 15/07/2026 e clicando Processar...")
        for k, v in (("enc_ini", "01/07/2026"), ("enc_fim", "15/07/2026"),
                     ("aloc_ini", DATA_ALOCACAO_INI), ("aloc_fim", DATA_ALOCACAO_FIM)):
            try:
                _preencher(page, k, v)
            except Exception as e:
                print(f"  ! {k}: {e}")
        for key in ("chk_unidade", "chk_comissionado", "chk_vigente", "chk_nao_vigente"):
            try:
                c = _loc(page, SELETORES[key]).first
                if c.count() and not c.is_checked():
                    c.check()
            except Exception as e:
                print(f"  ! {key}: {e}")
        antes = list(page.context.pages)
        _loc(page, SELETORES["btn_processar"]).first.click()
        page.wait_for_timeout(4000)
        for pg in [p for p in page.context.pages if p not in antes]:
            _dump(pg, "POPUP APOS 'Processar' (opcoes de impressao?)")
        _dump(page, "TELA APOS 'Processar' (mesma aba)")
    except Exception as e:
        print(f"\n[descobrir] parou em: {e}")
    print("\n(cole tudo na conversa — vou fechar os seletores de impressao)")


def _log(msg):
    print(msg, flush=True)


def _preencher(page, sel_key, valor):
    css = SELETORES[sel_key]
    el = page.locator(css).first
    try:
        el.wait_for(state="visible", timeout=15000)
    except Exception as e:
        _log(f"  ! {sel_key}: campo nao apareceu ({e})")
        return
    ok = False
    for estrategia in ("fill", "type", "js"):
        try:
            if estrategia == "fill":
                el.fill(valor, timeout=8000)
            elif estrategia == "type":
                el.click(timeout=5000)
                el.press("Control+a")
                el.press("Delete")
                el.type(valor, delay=30)
            else:  # js: seta value direto e dispara os eventos do ASP.NET
                page.evaluate(
                    """([sel, v]) => { const e = document.querySelector(sel);
                       e.value = v; e.dispatchEvent(new Event('input',{bubbles:true}));
                       e.dispatchEvent(new Event('change',{bubbles:true}));
                       e.dispatchEvent(new Event('blur',{bubbles:true})); }""",
                    [css, valor],
                )
            page.wait_for_timeout(200)
            atual = el.input_value(timeout=3000)
            if atual.strip() == valor:
                ok = True
                _log(f"  . {sel_key} = {valor}  ({estrategia})")
                break
            _log(f"  ~ {sel_key}: pos-{estrategia} ficou {atual!r}, tentando outra")
        except Exception as e:
            _log(f"  ~ {sel_key}: {estrategia} falhou ({str(e)[:80]})")
    if not ok:
        _log(f"  ! {sel_key}: NAO consegui preencher com '{valor}'")


def baixar_um(page, enc_ini, enc_fim, arquivo, refazer=False):
    destino = os.path.join(PASTA_DESTINO, arquivo)
    if os.path.exists(destino) and not refazer:
        print(f"  = ja existe, pulando: {arquivo}")
        return "PULADO"

    page.set_default_timeout(20000)
    _log(f"  -> abrindo Comissoes Pagas...")
    _ir_para_comissao(page)
    _log(f"  -> preenchendo datas...")
    _preencher(page, "enc_ini", enc_ini)
    _preencher(page, "enc_fim", enc_fim)
    _preencher(page, "aloc_ini", DATA_ALOCACAO_INI)
    _preencher(page, "aloc_fim", DATA_ALOCACAO_FIM)
    # Data Venda: nao mexer (fica 01/01/1900 a 01/01/3000)

    _log(f"  -> marcando checkboxes...")
    for key in ("chk_unidade", "chk_comissionado", "chk_vigente", "chk_nao_vigente"):
        try:
            c = _loc(page, SELETORES[key]).first
            if c.count() and not c.is_checked():
                c.check(timeout=8000)
            _log(f"  . {key} ok")
        except Exception as e:
            _log(f"  ! nao marquei {key}: {str(e)[:80]}")
    try:
        _loc(page, SELETORES["rb_nf_todas"]).first.check(timeout=5000)
    except Exception:
        pass

    # fecha qualquer date-picker/calendario que tenha ficado aberto sobre o form
    for _ in range(3):
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
    for txt in ("Fechar", "Close"):
        try:
            b = page.get_by_role("button", name=txt, exact=False).first
            if b.count() and b.is_visible():
                b.click(timeout=3000)
        except Exception:
            pass
    page.wait_for_timeout(300)

    try:
        page.screenshot(path=os.path.join(PASTA, "diag_antes_processar.png"))
        _log(f"  -> screenshot: worker/diag_antes_processar.png")
    except Exception:
        pass

    _log(f"  -> clicando Processar (Newcon e lento, pode demorar)...")
    AVISOS.clear()
    try:
        _loc(page, SELETORES["btn_processar"]).first.click(timeout=8000, no_wait_after=True)
    except Exception as e:
        _log(f"  ~ Processar: clique nao retornou limpo ({str(e)[:60]}) — seguindo")

    # Espera a telinha de opcoes OU o aviso "nao existe comissao paga" (ate 3 min).
    achou_opcoes = False
    for _ in range(90):
        if any(RE_SEM_COMISSAO.search(m) for m in AVISOS):
            _log(f"  -> periodo SEM COMISSAO ({enc_ini} a {enc_fim}) — pulando para o proximo")
            return "VAZIO"
        try:
            if page.locator(SELETORES["btn_imprimir"]).first.is_visible(timeout=1000):
                achou_opcoes = True
                break
        except Exception:
            pass
        page.wait_for_timeout(2000)
    if not achou_opcoes:
        try:
            page.screenshot(path=os.path.join(PASTA, "diag_apos_processar.png"))
        except Exception:
            pass
        _log(f"  x telinha de opcoes NAO apareceu em 3min — ver worker/diag_apos_processar.png")
        return "ERRO"
    _log(f"  -> telinha de opcoes apareceu")
    page.wait_for_timeout(800)
    try:
        page.screenshot(path=os.path.join(PASTA, "diag_apos_processar.png"))
    except Exception:
        pass

    # overlay de opcoes de impressao (mesma pagina)
    try:
        _loc(page, SELETORES["opt_analitico"]).first.check()
    except Exception as e:
        _log(f"  ! Analitico: {e}")
    modelo_key = "opt_modelo_comis" if MODELO.lower().startswith("comis") else "opt_modelo_filial"
    try:
        _loc(page, SELETORES[modelo_key]).first.check()
    except Exception as e:
        _log(f"  ! modelo ({MODELO}): {e}")
    for key in ("chk_quebra_pagina", "chk_segunda_linha"):
        try:
            c = _loc(page, SELETORES[key]).first
            if not c.is_checked():
                c.check()
            _log(f"  . {key} ok")
        except Exception as e:
            _log(f"  ! checkbox {key}: {e}")

    # Imprimir -> o Newcon renderiza o relatorio (frmConCmNewconReports.aspx) e
    # em algum momento serve um application/pdf. Capturamos OUVINDO a rede.
    os.makedirs(PASTA_DESTINO, exist_ok=True)
    ctx = page.context
    antes = set(ctx.pages)
    capturado = {"bytes": None, "url": None}

    def _on_response(resp):
        if capturado["bytes"]:
            return
        try:
            ct = (resp.headers or {}).get("content-type", "").lower()
            u = resp.url or ""
            if "pdf" in ct or u.lower().endswith(".pdf"):
                b = resp.body()
                if b[:4] == b"%PDF":
                    capturado["bytes"], capturado["url"] = b, u
                    _log(f"  -> PDF capturado da rede: {u[:90]} ({len(b)//1024} KB)")
        except Exception:
            pass

    ctx.on("response", _on_response)
    _log(f"  -> clicando Imprimir...")
    AVISOS.clear()
    try:
        _loc(page, SELETORES["btn_imprimir"]).first.click(no_wait_after=True)
    except Exception as e:
        _log(f"  ~ Imprimir: clique nao retornou limpo ({str(e)[:60]})")
    # IMPORTANTE: usar page.wait_for_timeout (nao time.sleep) — so ele "roda" o
    # event loop do Playwright, que e quem entrega os dialogos (window.alert).
    page.wait_for_timeout(4000)
    if any(RE_SEM_COMISSAO.search(m) for m in AVISOS):
        _log(f"  -> periodo SEM COMISSAO ({enc_ini} a {enc_fim}) — pulando para o proximo")
        try:
            ctx.remove_listener("response", _on_response)
        except Exception:
            pass
        return "VAZIO"

    # abre o visualizador de relatorio (ReportViewer). O PDF so sai quando
    # clicamos no botao Exportar/Salvar (disquete) com formato "Adobe PDF File".
    page.wait_for_timeout(6000)
    if any(RE_SEM_COMISSAO.search(m) for m in AVISOS):
        _log(f"  -> periodo SEM COMISSAO ({enc_ini} a {enc_fim}) — pulando para o proximo")
        try:
            ctx.remove_listener("response", _on_response)
        except Exception:
            pass
        return "VAZIO"
    resultado_export = _clicar_exportar_pdf(page, ctx)
    if resultado_export == "VAZIO":
        _log(f"  -> periodo SEM COMISSAO ({enc_ini} a {enc_fim}) — pulando para o proximo")
        try:
            ctx.remove_listener("response", _on_response)
        except Exception:
            pass
        return "VAZIO"
    if isinstance(resultado_export, (bytes, bytearray)) and resultado_export[:4] == b"%PDF":
        capturado["bytes"] = bytes(resultado_export)
        capturado["url"] = "download-stimulsoft"

    # espera ate ~3 min o PDF aparecer (na rede, num popup ou num frame)
    for i in range(90):
        if capturado["bytes"]:
            break
        if any(RE_SEM_COMISSAO.search(m) for m in AVISOS):
            _log(f"  -> periodo SEM COMISSAO ({enc_ini} a {enc_fim}) — pulando")
            try:
                ctx.remove_listener("response", _on_response)
            except Exception:
                pass
            return "VAZIO"
        page.wait_for_timeout(2000)
        for pg in [p for p in ctx.pages if p not in antes] + list(ctx.pages):
            for u in [pg.url] + [f.url for f in pg.frames]:
                if not u or u.startswith("about:") or not u.startswith("http"):
                    continue
                try:
                    b = ctx.request.get(u).body()
                    if b[:4] == b"%PDF":
                        capturado["bytes"], capturado["url"] = b, u
                        break
                except Exception:
                    pass
            if capturado["bytes"]:
                break
        if i == 20 and not capturado["bytes"]:
            try:
                page.screenshot(path=os.path.join(PASTA, "diag_apos_imprimir.png"))
                _log(f"  -> ainda procurando... screenshot worker/diag_apos_imprimir.png")
                for pg in ctx.pages:
                    _log(f"     aba: {pg.url[:110]}")
                    for f in pg.frames:
                        if f.url and f.url.startswith("http"):
                            _log(f"       frame: {f.url[:110]}")
            except Exception:
                pass

    try:
        ctx.remove_listener("response", _on_response)
    except Exception:
        pass
    for p in [p for p in ctx.pages if p not in antes]:
        try:
            p.close()
        except Exception:
            pass

    if not capturado["bytes"]:
        _log(f"  x NAO capturei o PDF de {enc_ini} a {enc_fim} — ver worker/diag_apos_imprimir.png")
        return "ERRO"
    with open(destino, "wb") as f:
        f.write(capturado["bytes"])
    _log(f"  ok {arquivo}  ({len(capturado['bytes'])//1024} KB)")
    return "OK"


def _frames_e_pagina(page_or_ctx):
    """Todos os frames de todas as abas (para procurar o toolbar do ReportViewer)."""
    ctx = page_or_ctx if hasattr(page_or_ctx, "pages") else page_or_ctx.context
    alvos = []
    for pg in ctx.pages:
        alvos.append(pg)          # o page tambem serve de 'frame-like' p/ locator
        alvos.extend(pg.frames)
    return alvos


def _clicar_exportar_pdf(page, ctx):
    """Acha o toolbar do visualizador de relatorio do Newcon e dispara o export PDF.
    Tenta em todas as abas/frames. Loga o que encontrou."""
    page.wait_for_timeout(2000)
    if any(RE_SEM_COMISSAO.search(m) for m in AVISOS):
        return "VAZIO"
    cand_select = [
        "#ctl00_Conteudo_StiWebRelatorio_SaveTypeList",   # Stimulsoft (Newcon)
        "select[id*='SaveTypeList']", "select[id*='ctl05_ctl00']", "select",
    ]
    cand_botao = [
        "#ctl00_Conteudo_StiWebRelatorio_Save",           # Stimulsoft (Newcon)
        "input[type=image][id*='StiWebRelatorio_Save']", "input[id$='_Save']",
        "a[id*='ctl05_ctl01']", "a[title*='Export']", "input[type=image][title*='Export']",
        "img[src*='Export']", "a[href*='Export']", "[onclick*='Export']",
    ]
    for fr in _frames_e_pagina(ctx):
        # 1) garante formato = Adobe PDF
        for sel in cand_select:
            try:
                s = fr.locator(sel).first
                if s.count():
                    for tentativa in (
                        lambda: s.select_option(label="Adobe PDF File..."),
                        lambda: s.select_option(index=0),
                    ):
                        try:
                            tentativa()
                            _log(f"  -> formato PDF selecionado ({sel})")
                            break
                        except Exception:
                            continue
                    break
            except Exception:
                continue
        # 2) clica o botao de exportar/salvar (o Stimulsoft dispara um DOWNLOAD)
        for sel in cand_botao:
            try:
                b = fr.locator(sel).first
                if not (b.count() and b.is_visible()):
                    continue
                try:
                    with page.expect_download(timeout=60000) as dl:
                        b.click(no_wait_after=True, timeout=8000)
                    caminho = dl.value.path()
                    dados = open(caminho, "rb").read()
                    _log(f"  -> export baixou {len(dados)//1024} KB via download ({sel})")
                    return dados
                except Exception:
                    b.click(no_wait_after=True, timeout=8000)
                    _log(f"  -> cliquei exportar (sem download direto): {sel}")
                    return True
            except Exception:
                continue
    _log("  ~ nao achei o botao de exportar do ReportViewer — vou dumpar a tela")
    for fr in _frames_e_pagina(ctx):
        try:
            itens = fr.evaluate(_JS_CLICAVEIS)
        except Exception:
            continue
        if not itens:
            continue
        url = getattr(fr, "url", "")
        _log(f"  --- frame/aba {str(url)[:100]} ---")
        for it in itens:
            _log(f"     <{it['tag']} type={it['type']}> id={it['id']!r} "
                 f"name={it['name']!r} txt={it['text']!r} hint={it.get('hint','')!r}")
    try:
        page.screenshot(path=os.path.join(PASTA, "diag_reportviewer.png"))
        _log("  -> screenshot worker/diag_reportviewer.png")
    except Exception:
        pass
    return False


def _conectar_sb():
    from supabase import create_client
    url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key or "xxxx" in url:
        raise RuntimeError("Configure SUPABASE_URL/SUPABASE_KEY no worker/.env")
    return create_client(url, key)


def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args or "/?" in args:
        print(__doc__)
        return
    if "--descobrir" in args:
        sb = _conectar_sb()
        pw, browser, ctx, page = _abrir(sb)
        try:
            descobrir(page)
        finally:
            browser.close(); pw.stop()
        return

    dados = json.load(open(os.path.join(PASTA, "periodos_comissao.json"), encoding="utf-8"))
    periodos = dados["periodos"]

    if "--so" in args:
        so = args[args.index("--so") + 1]
        periodos = [p for p in periodos if p["ini"] == so]
    if "--desde" in args:
        desde = args[args.index("--desde") + 1]
        d0 = datetime.datetime.strptime(desde, "%d/%m/%Y").date()
        periodos = [p for p in periodos
                    if datetime.datetime.strptime(p["ini"], "%d/%m/%Y").date() >= d0]
        print(f">>> comecando de {desde} ({len(periodos)} periodos)")
    if "--mes" in args or "--mes-atual" in args:
        # "--mes AAAA-MM" (ou --mes-atual) = as 2 quinzenas daquele mes.
        # Se o mes ainda nao esta no periodos_comissao.json (mes recente), gera na hora.
        if "--mes-atual" in args:
            alvo = datetime.date.today().strftime("%Y-%m")
        else:
            alvo = args[args.index("--mes") + 1]              # ex.: 2026-08
        ano, mes = int(alvo[:4]), int(alvo[5:7])
        import calendar
        ult = calendar.monthrange(ano, mes)[1]
        do_mes = [p for p in periodos if p["ini"][3:10] == f"{mes:02d}/{ano}"]
        if not do_mes:                                        # mes fora do JSON -> monta
            do_mes = [
                {"ini": f"01/{mes:02d}/{ano}", "fim": f"15/{mes:02d}/{ano}",
                 "arquivo": f"{ano}-{mes:02d}-1a-quinzena - Comissoes Yamaha CCY10852.pdf"},
                {"ini": f"16/{mes:02d}/{ano}", "fim": f"{ult:02d}/{mes:02d}/{ano}",
                 "arquivo": f"{ano}-{mes:02d}-2a-quinzena - Comissoes Yamaha CCY10852.pdf"},
            ]
        periodos = do_mes
        print(f">>> mes {alvo}: {len(periodos)} quinzena(s)")
    refazer = "--refazer" in args

    sb = _conectar_sb()
    pw, browser, ctx, page = _abrir(sb)
    resultados = {}
    try:
        if "--geral" in args:
            hoje = datetime.date.today().strftime("%d/%m/%Y")
            arq = f"GERAL {INICIO_HISTORICO.replace('/','-')} a {hoje.replace('/','-')} - Comissoes Yamaha CCY10852.pdf"
            print(f"\n>>> RELATORIO GERAL {INICIO_HISTORICO} a {hoje}")
            resultados[arq] = baixar_um(page, INICIO_HISTORICO, hoje, arq, refazer=True)
        else:
            print(f"\n>>> {len(periodos)} periodo(s) | modelo={MODELO} | destino={PASTA_DESTINO}\n")
            for i, p in enumerate(periodos, 1):
                print(f"[{i}/{len(periodos)}] {p['ini']} a {p['fim']}")
                try:
                    resultados[p["arquivo"]] = baixar_um(page, p["ini"], p["fim"], p["arquivo"], refazer)
                except Exception as e:
                    resultados[p["arquivo"]] = f"ERRO: {e}"
                    print(f"  x {e}")
    finally:
        browser.close(); pw.stop()

    print("\n===== RESUMO =====")
    for k, v in resultados.items():
        print(f"  {v:<8} {k}")
    conta = lambda alvo: sum(1 for v in resultados.values() if v == alvo)
    print(f"\n{conta('OK')} baixado(s), {conta('PULADO')} ja existia(m), "
          f"{conta('VAZIO')} sem comissao no periodo, "
          f"{sum(1 for v in resultados.values() if str(v).startswith('ERRO'))} com erro.")
    print("Confira com:  python conferir_comissoes.py")


if __name__ == "__main__":
    main()
