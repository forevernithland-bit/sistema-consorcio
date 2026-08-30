"""
coletar_grupos.py — Cataloga planos e grupos Yamaha ATIVOS (via Newcon).

O QUE ELE ENTENDEU DO NEGÓCIO (Uriel, 29/08/2026):
  Em "Venda -> Venda de Proposta -> Venda de Propostas" o vendedor escolhe:
    Produto (Moto/Auto/Imóvel/Caminhão) -> Tipo de Venda (= o PLANO, ex.: 074
    "S GRUPO PRIME IPCA + TX 11,6") -> Prazo -> Convênio -> e um "Bem"
    (cada opção do Bem é uma FAIXA DE CRÉDITO daquele plano, ex.: 1403TX =
    R$ 100.000). Ao Avançar, o sistema lista o GRUPO daquele plano+crédito,
    com Vagas, Parcela, Taxa, próxima Assembleia, Prazo e Lance Médio.

  Planos diferentes têm créditos parecidos (074 dá R$ 100k, 069 dá R$ 105k…),
  então pra atender "cliente quer R$ 100k" o robô precisa varrer VÁRIOS planos.

DISCIPLINA (não é sair apertando botão):
  cada seleção dispara postback e a lista de baixo demora a carregar. O robô
  SELECIONA -> ESPERA a lista dependente ter opções de verdade -> LÊ -> decide.
  Vai gravando tudo (`planos_yamaha`, `grupos_yamaha`) com data da consulta,
  pra na próxima já saber por onde ir.

USO (PC do escritório):
    python coletar_grupos.py --produto auto --plano 074
    python coletar_grupos.py --produto auto --credito 100000
        varre os planos cujo crédito chega perto de 100k (±15%)
    python coletar_grupos.py --produto auto --todos-planos
        varre TUDO (demorado; use pra montar/atualizar o catálogo)
    ...qualquer um + --salvar   -> grava no Supabase (tabelas do
       migracoes/17_grupos_yamaha.sql). Sem --salvar: só imprime + JSON.
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
CPF = re.sub(r"\D", "", os.getenv("SIMULACAO_CPF", "").strip())

PRODUTOS = {"moto": "1", "auto": "4", "automovel": "4", "carro": "4",
            "imovel": "7", "imóvel": "7", "caminhao": "10", "caminhão": "10"}
PROD_NOME = {"1": "Moto", "4": "Auto", "7": "Imóvel", "10": "Caminhão"}

# Planos (Tipo de Venda) que a Consorbens NÃO usa — ignorados na varredura.
# Ajuste conforme o Uriel/Breno definirem. Pode sobrescrever com PLANOS_IGNORAR
# no .env (lista separada por vírgula, casa por trecho do nome).
IGNORAR_PADRAO = ["FUNCIONÁRIO", "FUNCIONARIO"]
IGNORAR = [x.strip().upper() for x in
           os.getenv("PLANOS_IGNORAR", ",".join(IGNORAR_PADRAO)).split(",") if x.strip()]


def _plano_valido(txt):
    up = (txt or "").upper()
    return not any(bad in up for bad in IGNORAR)

S = {
    "cpf_vend":   "#ctl00_Conteudo_edtCPFVendedor",
    "cpf_cli":    "#ctl00_Conteudo_edtCD_Inscricao_Nacional",
    "produto":    "#ctl00_Conteudo_cbxProduto",
    "tp_venda":   "#ctl00_Conteudo_cbxTp_Venda",
    "prazo":      "#ctl00_Conteudo_cbxPl_Prazo",
    "convenio":   "#ctl00_Conteudo_cbxConvenio",
    "negociacao": "#ctl00_Conteudo_cbxTipoNegociacao",
    "rb_bem":     "#ctl00_Conteudo_rblTipoPesquisa_0",   # value=B
    "bem":        "#ctl00_Conteudo_cbxBem_Objeto",
    "avancar":    "#ctl00_Conteudo_btnAvancar",
    "voltar":     "#ctl00_Conteudo_Button1",
    "grade":      "#ctl00_Conteudo_grdProposta_Prazo",
}
COLS = ["grupo_raw", "bem", "valor", "taxa", "assembleia", "vencto",
        "prazo_cg", "vagas", "particip", "parcela", "lance_medio"]


# --------------------------------------------------------------------------
def _num(s):
    t = re.sub(r"[^\d,.\-]", "", str(s or "")).replace(".", "").replace(",", ".")
    try:
        return float(t or 0)
    except ValueError:
        return 0.0


def _rs_na_str(txt):
    """pega o 1º valor em R$ de um texto de opção ('... R$ 100.000,00 ...')."""
    m = re.search(r"R\$\s*([\d.]+,\d{2})", str(txt or ""))
    return _num(m.group(1)) if m else 0.0


def _conectar_sb():
    from supabase import create_client
    url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key or "xxxx" in url:
        raise RuntimeError("Configure SUPABASE_URL/KEY no worker/.env")
    return create_client(url, key)


def _abrir(sb, visivel):
    from playwright.sync_api import sync_playwright
    import newcon
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=not visivel)
    kw = {"accept_downloads": True}
    ctx = (browser.new_context(storage_state=newcon.STORAGE_STATE, **kw)
           if os.path.exists(newcon.STORAGE_STATE) else browser.new_context(**kw))
    page = ctx.new_page()
    page.set_default_timeout(30000)
    page.on("dialog", lambda d: d.accept())
    page.goto(NEWCON_URL)
    if not newcon.esta_logado(page):
        try:
            r = sb.table("senhas_sistema").select("login,senha,empresa") \
                .ilike("empresa", os.getenv("NEWCON_EMPRESA_COFRE", "YAMAHA NEWCON")).execute()
            login, senha = r.data[0]["login"].strip(), (r.data[0].get("senha") or "").strip()
        except Exception:
            login = os.getenv("NEWCON_LOGIN", "").strip()
            senha = os.getenv("NEWCON_SENHA", "").strip()
        newcon.fazer_login(page, ctx, login, senha)
        ctx.storage_state(path=newcon.STORAGE_STATE)
        print("[newcon] login efetuado.")
    else:
        print("[newcon] sessão reaproveitada.")
    return pw, browser, ctx, page


def _clic(page, txt, timeout=10000):
    for t in (lambda: page.get_by_role("link", name=txt, exact=False),
              lambda: page.get_by_role("button", name=txt, exact=False),
              lambda: page.get_by_text(txt, exact=True)):
        try:
            loc = t().first
            if loc.count() and loc.is_visible():
                loc.click(timeout=timeout)
                page.wait_for_load_state("networkidle")
                return True
        except Exception:
            continue
    return False


def _ir_para_form(page):
    _clic(page, "Venda")
    _clic(page, "Venda de Proposta")
    for tent in (lambda: page.locator("#ctl00_Conteudo_ctl00_tvwMenut2"),
                 lambda: page.get_by_text("Venda de Propostas", exact=True)):
        try:
            loc = tent().first
            if loc.count():
                loc.click(timeout=10000)
                page.wait_for_load_state("networkidle")
                break
        except Exception:
            continue
    page.wait_for_selector(S["produto"], timeout=30000)


def _opcoes(page, sel):
    """[(value, texto), ...] de um <select>, tirando o '--Selecione--'."""
    try:
        raw = page.eval_on_selector(sel, """el => [...el.options].map(o =>
            [o.value, (o.textContent||'').replace(/\\s+/g,' ').trim()])""")
    except Exception:
        return []
    return [(v, t) for v, t in raw if v not in ("0", "", None) and "selecione" not in t.lower()]


def _esperar_opcoes(page, sel, minimo=1, timeout=20000):
    """Espera o <select> dependente terminar de carregar (após um postback)."""
    fim = time.time() + timeout / 1000
    while time.time() < fim:
        page.wait_for_load_state("networkidle")
        if len(_opcoes(page, sel)) >= minimo:
            return True
        page.wait_for_timeout(600)
    return False


def _sel(page, sel, value):
    page.locator(sel).first.select_option(value=value)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(700)


def _fill(page, sel, val):
    el = page.locator(sel).first
    try:
        el.fill(str(val))
    except Exception:
        el.click(); el.press("Control+a"); el.type(str(val), delay=20)
    el.press("Tab"); page.wait_for_timeout(300)


def _preambulo(page, prod_cod):
    """CPF + Produto. Deixa a tela pronta pra escolher o plano."""
    if CPF:
        _fill(page, S["cpf_vend"], CPF)
        try:
            _fill(page, S["cpf_cli"], CPF)
        except Exception:
            pass
    _sel(page, S["produto"], prod_cod)
    _esperar_opcoes(page, S["tp_venda"], 1)


def _ler_grade(page):
    if not page.locator(S["grade"]).count():
        return []
    linhas = page.evaluate("""(sel) => {
      const tb = document.querySelector(sel); if (!tb) return [];
      return [...tb.querySelectorAll('tr')].map(tr =>
        [...tr.querySelectorAll('td')].map(td => (td.innerText||'').replace(/\\s+/g,' ').trim()));
    }""", S["grade"])
    out = []
    for cel in linhas:
        if len(cel) < 10 or not re.search(r"\d", cel[0] or ""):
            continue
        d = dict(zip(COLS, cel + [""] * (len(COLS) - len(cel))))
        g = re.match(r"0*(\d+)", d["grupo_raw"] or "")
        pcg = re.findall(r"\d+", d["prazo_cg"] or "")
        out.append({
            "grupo": g.group(1) if g else d["grupo_raw"].strip(),
            "grupo_raw": d["grupo_raw"].strip(),
            "bem": d["bem"], "credito": _num(d["valor"]), "taxa": _num(d["taxa"]),
            "prox_assembleia": d["assembleia"].strip(),
            "vencto_assembleia": d["vencto"].strip(),
            "prazo_restante": int(pcg[0]) if len(pcg) > 0 else 0,
            "prazo_total": int(pcg[1]) if len(pcg) > 1 else 0,
            "vagas": int(_num(d["vagas"])), "participantes": int(_num(d["particip"])),
            "parcela": _num(d["parcela"]), "lance_medio": _num(d["lance_medio"]),
        })
    return out


def _coletar_plano(page, plano_val, plano_txt, alvo=None, tol=0.15, com_grupos=False):
    """Seleciona o plano e MEMORIZA de uma vez todas as faixas de crédito
    (basta ler o dropdown 'Bem' — não precisa entrar/voltar por faixa).
    Só entra na grade do grupo quando há um alvo de crédito OU --com-grupos.
    Retorna (meta_do_plano, [grupos])."""
    print(f"\n== PLANO {plano_txt} ==")
    _sel(page, S["tp_venda"], plano_val)
    _esperar_opcoes(page, S["prazo"], 1)
    prazos = _opcoes(page, S["prazo"]) or [(None, "(único)")]

    conv = _opcoes(page, S["convenio"])
    if conv:
        try:
            _sel(page, S["convenio"], conv[0][0])
        except Exception:
            pass

    grupos, creditos_plano = [], []
    for pz_val, pz_txt in prazos:
        if pz_val:
            _sel(page, S["prazo"], pz_val)
        try:
            page.locator(S["rb_bem"]).first.check()
            page.wait_for_load_state("networkidle"); page.wait_for_timeout(600)
        except Exception:
            pass
        if not _esperar_opcoes(page, S["bem"], 1, timeout=15000):
            print(f"   prazo {pz_txt}: lista de crédito não carregou — pulando")
            continue

        # >>> LÊ TODAS AS FAIXAS DE UMA VEZ (o "print interno") <<<
        bens = _opcoes(page, S["bem"])
        faixas = [(bv, bt, _rs_na_str(bt)) for bv, bt in bens]
        for bv, bt, c in faixas:
            if c > 0:
                creditos_plano.append({"bem_cod": bv, "texto": bt, "credito": c,
                                       "prazo": pz_txt})
        vals = sorted({c for _, _, c in faixas if c})
        faixa_str = (f"{vals[0]:,.0f}–{vals[-1]:,.0f}" if len(vals) > 1
                     else (f"{vals[0]:,.0f}" if vals else "?"))
        print(f"   prazo {pz_txt}: {len(faixas)} faixa(s) de crédito  ({faixa_str})")

        # Só entra na grade se precisar dos grupos (alvo ou --com-grupos)
        if not (alvo or com_grupos):
            continue
        if alvo:
            alvos = [f for f in faixas if f[2] and abs(f[2] - alvo) <= alvo * tol]
            if not alvos and any(f[2] for f in faixas):
                alvos = [min((f for f in faixas if f[2]),
                             key=lambda f: abs(f[2] - alvo))]
        else:
            alvos = [f for f in faixas if f[2]]
        for bv, bt, cval in alvos:
            _sel(page, S["bem"], bv)
            try:
                page.locator(S["avancar"]).first.click(timeout=10000, no_wait_after=True)
            except Exception:
                pass
            page.wait_for_timeout(2500); page.wait_for_load_state("networkidle")
            gs = _ler_grade(page)
            for g in gs:
                g.update({"plano_cod": re.match(r"0*(\d+)", plano_txt).group(1)
                          if re.match(r"0*(\d+)", plano_txt) else plano_val,
                          "plano_txt": plano_txt, "prazo_label": pz_txt,
                          "credito_faixa": cval or g["credito"]})
            if gs:
                print(f"      R$ {cval:,.0f} → grupo(s) "
                      + ", ".join(f"{g['grupo']} ({g['vagas']} vagas)" for g in gs))
            grupos += gs
            # volta para o form pra próxima faixa
            try:
                page.locator(S["voltar"]).first.click(timeout=10000, no_wait_after=True)
                page.wait_for_load_state("networkidle"); page.wait_for_timeout(1200)
                page.wait_for_selector(S["bem"], timeout=15000)
            except Exception:
                _ir_para_form(page)
                _preambulo(page, page.locator(S["produto"]).first.input_value())
                _sel(page, S["tp_venda"], plano_val)
                if pz_val:
                    _sel(page, S["prazo"], pz_val)
                page.locator(S["rb_bem"]).first.check()
                _esperar_opcoes(page, S["bem"], 1)

    # dedup faixas
    vistas, fx = set(), []
    for c in creditos_plano:
        if c["bem_cod"] not in vistas:
            vistas.add(c["bem_cod"]); fx.append(c)
    m = re.match(r"0*(\d+)", plano_txt)
    meta = {"plano_cod": (grupos[0]["plano_cod"] if grupos
                          else (m.group(1) if m else plano_val)),
            "plano_txt": plano_txt, "creditos": fx}
    return meta, grupos


def _salvar(sb, prod_nome, metas, grupos):
    agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for m in metas:
        try:
            sb.table("planos_yamaha").upsert({
                "codigo": m["plano_cod"], "tipo_bem": prod_nome, "nome": m["plano_txt"],
                "creditos": m["creditos"], "consultado_em": agora,
            }, on_conflict="codigo,tipo_bem").execute()
        except Exception as e:
            print(f"  ! plano {m['plano_cod']}: {str(e)[:120]}")
    n = 0
    for g in grupos:
        try:
            sb.table("grupos_yamaha").upsert({
                "grupo": g["grupo"], "tipo_bem": prod_nome, "plano_codigo": g["plano_cod"],
                "bem": g["bem"], "credito": g["credito"], "taxa": g["taxa"],
                "prox_assembleia": g["prox_assembleia"] or None,
                "prazo_restante": g["prazo_restante"], "prazo_total": g["prazo_total"],
                "vagas": g["vagas"], "parcela": g["parcela"],
                "lance_medio": g["lance_medio"] or None,
                "consultado_em": agora, "fonte": "newcon-venda-proposta",
            }, on_conflict="grupo,tipo_bem").execute()
            sb.table("grupos_yamaha_consultas").insert({
                "grupo": g["grupo"], "tipo_bem": prod_nome, "vagas": g["vagas"],
                "credito": g["credito"], "consultado_em": agora}).execute()
            n += 1
        except Exception as e:
            print(f"  ! grupo {g['grupo']}: {str(e)[:120]}")
    return n


# --------------------------------------------------------------------------
def main():
    a = sys.argv[1:]
    if not a or "--help" in a or "-h" in a:
        print(__doc__); return

    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a else d

    prod_in = (opt("--produto", "auto") or "auto").lower()
    if prod_in not in PRODUTOS:
        print("produto: moto|auto|imovel|caminhao"); return
    prod_cod = PRODUTOS[prod_in]
    prod_nome = PROD_NOME[prod_cod]
    alvo = _num(opt("--credito")) or None
    salvar = "--salvar" in a

    sb = _conectar_sb()
    pw, browser, ctx, page = _abrir(sb, visivel=("--headless" not in a))
    try:
        _ir_para_form(page)
        _preambulo(page, prod_cod)

        planos_todos = _opcoes(page, S["tp_venda"])
        com_grupos = "--com-grupos" in a

        if opt("--planos"):                                 # lista explícita "069,073,074"
            querid = {re.sub(r"\D", "", x) for x in opt("--planos").split(",")}
            planos = [(v, t) for v, t in planos_todos
                      if re.sub(r"\D", "", t.split("-")[0]) in querid]
        elif opt("--plano"):
            alvo_cod = re.sub(r"\D", "", opt("--plano"))
            planos = [(v, t) for v, t in planos_todos
                      if re.sub(r"\D", "", t.split("-")[0]) == alvo_cod]
        elif opt("--todos-planos") or alvo:
            planos = [(v, t) for v, t in planos_todos if _plano_valido(t)]
        else:
            print("Escolha: --plano NNN | --planos 069,073,074 | --credito VALOR | --todos-planos")
            print(f"\nPlanos de {prod_nome} (❌ = ignorado por padrão):")
            for v, t in planos_todos:
                print(f"  {'❌' if not _plano_valido(t) else '  '} {t}")
            return

        ignorados = [t for v, t in planos_todos
                     if (v, t) not in planos and not _plano_valido(t)]
        if ignorados and (opt("--todos-planos") or alvo):
            print(f"   (ignorando {len(ignorados)}: " + "; ".join(ignorados[:4])
                  + ("…" if len(ignorados) > 4 else "") + ")")
        print(f">>> {prod_nome} | {len(planos)} plano(s) a varrer"
              + (f" | alvo R$ {alvo:,.0f}" if alvo else "")
              + (" | + grupos" if com_grupos else ""))

        metas, grupos = [], []
        for pv, pt in planos:
            try:
                m, gs = _coletar_plano(page, pv, pt, alvo=alvo, com_grupos=com_grupos)
                metas.append(m); grupos += gs
            except Exception as e:
                print(f"  x plano {pt}: {str(e)[:150]}")
            # recomeça limpo pro próximo plano
            _ir_para_form(page); _preambulo(page, prod_cod)

        print(f"\n{'='*90}\nCATÁLOGO: {len(metas)} plano(s), "
              f"{sum(len(m['creditos']) for m in metas)} faixa(s) de crédito, "
              f"{len(grupos)} grupo(s)\n{'='*90}")
        for m in metas:
            vals = sorted({c["credito"] for c in m["creditos"] if c["credito"]})
            amostra = ", ".join(f"{v:,.0f}" for v in vals[:8]) + ("…" if len(vals) > 8 else "")
            print(f"  Plano {m['plano_cod']:<4} {m['plano_txt'][:44]:<44} "
                  f"{len(m['creditos']):>2} faixas  [{amostra}]")

        if grupos:
            print(f"\n{'Grupo':>7} {'Plano':>6} {'Crédito':>12} {'Taxa':>7} {'Vagas':>6} "
                  f"{'Prazo':>9} {'Assembleia':>12} {'Parcela':>12} {'LanceMéd':>9}")
            print("-" * 92)
            for g in sorted(grupos, key=lambda x: (x["plano_cod"], -x["vagas"])):
                print(f"{g['grupo']:>7} {g['plano_cod']:>6} {g['credito']:>12,.0f} "
                      f"{g['taxa']:>6.2f}% {g['vagas']:>6} "
                      f"{g['prazo_restante']}/{g['prazo_total']:<6} "
                      f"{g['prox_assembleia']:>12} {g['parcela']:>12,.2f} "
                      f"{g['lance_medio']:>9.4f}")

        if salvar:
            n = _salvar(sb, prod_nome, metas, grupos)
            print(f"\n✅ {n} grupo(s) + {len(metas)} plano(s) gravados no Supabase.")
        else:
            out = os.path.join(PASTA, "grupos_ultima_coleta.json")
            open(out, "w", encoding="utf-8").write(
                json.dumps({"metas": metas, "grupos": grupos}, ensure_ascii=False, indent=1))
            print(f"\n(modo teste — nada gravado. JSON: {out})")
    finally:
        try:
            browser.close(); pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
