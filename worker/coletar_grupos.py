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
    python coletar_grupos.py --produto auto
        lista os planos de auto ([x] = ignorado, ex.: FUNCIONÁRIO)
    python coletar_grupos.py --produto auto --plano 074
        catálogo do plano 074: lê TODAS as faixas de crédito de uma vez
    python coletar_grupos.py --produto auto --todos-planos
        catálogo completo de auto (pula os planos que a Consorbens não usa)
    python coletar_grupos.py --produto auto --credito 100000
        varre os planos válidos e, nas faixas perto de 100k (±15%), ENTRA na
        grade e traz o grupo (vagas, parcela, taxa, assembleia, lance médio).
        Prioriza os planos da METADE da lista pra frente (os mais recentes) —
        os do início quase nunca têm vaga. Registra cada busca em
        `yamaha_buscas` (mesmo sem achar nada) e pula, no mesmo dia, plano que
        já buscou e não tinha vaga.
        + --n-grupos 5   -> para assim que achar 5 grupos COM vaga
        + --incluir-antigos -> não pula os planos antigos do início da lista
    python coletar_grupos.py --produto auto --plano 074 --com-grupos
        catálogo + entra na grade de todas as faixas do plano
    ...qualquer um + --salvar   -> grava no Supabase (tabelas do
       migracoes/17_grupos_yamaha.sql). Sem --salvar: só imprime + JSON.

    python coletar_grupos.py --produto auto --sync
        checa se a Yamaha criou plano NOVO (ou se o catálogo passou de 1 mês)
        e cataloga só esses. Rode isso periodicamente. Sempre grava.

Toda execução já avisa "[NOVO] plano novo" se achar um que não está no catálogo.
No modo --credito, o robô consulta o catálogo local e vai DIRETO nos planos
que têm aquele valor (+ os planos novos, por garantia).

Planos ignorados por padrão: FUNCIONÁRIO. Ajuste com PLANOS_IGNORAR no .env
ou passe --planos 069,073,074 para varrer só os que quiser.
"""
import os
import re
import sys
import json
import time
import datetime

from dotenv import load_dotenv

for _st in (sys.stdout, sys.stderr):
    try: _st.reconfigure(encoding='utf-8')
    except Exception: pass

PASTA = os.path.dirname(__file__)
load_dotenv(os.path.join(PASTA, ".env"))
NEWCON_URL = os.getenv("NEWCON_URL", "").strip()
CPF = re.sub(r"\D", "", os.getenv("SIMULACAO_CPF", "").strip())

# chave do usuário -> (nome interno, palavras que identificam a opção no dropdown)
PRODUTOS = {
    "moto":     ("Moto", ["MOTOCICLET"]),
    "auto":     ("Auto", ["AUTOM"]),
    "automovel": ("Auto", ["AUTOM"]),
    "carro":    ("Auto", ["AUTOM"]),
    "imovel":   ("Imóvel", ["IMÓVE", "IMOVE"]),
    "imóvel":   ("Imóvel", ["IMÓVE", "IMOVE"]),
    "caminhao": ("Caminhão", ["CAMINH"]),
    "caminhão": ("Caminhão", ["CAMINH"]),
}

# Planos (Tipo de Venda) que a Consorbens NÃO usa — ignorados na varredura.
# Ajuste conforme o Uriel/Breno definirem. Pode sobrescrever com PLANOS_IGNORAR
# no .env (lista separada por vírgula, casa por trecho do nome).
IGNORAR_PADRAO = ["FUNCIONÁRIO", "FUNCIONARIO"]
IGNORAR = [x.strip().upper() for x in
           os.getenv("PLANOS_IGNORAR", ",".join(IGNORAR_PADRAO)).split(",") if x.strip()]


def _plano_valido(txt):
    up = (txt or "").upper()
    return not any(bad in up for bad in IGNORAR)

_PROD_PAL = ["AUTOM"]     # palavras do produto atual (setado em main)
_DIAG_FEITO = [False]

# Tolerância de crédito ao redor do alvo (Uriel): +15% p/ cima, -10% p/ baixo,
# sempre priorizando o valor exato. Catálogo só "vence" depois de 1 mês.
TOL_ALTO, TOL_BAIXO = 0.15, 0.10
CATALOGO_MAX_DIAS = 30


def _perto_do_alvo(valor, alvo):
    return bool(valor) and (alvo * (1 - TOL_BAIXO) <= valor <= alvo * (1 + TOL_ALTO))


# Quanto tempo o dado de um grupo "vale" antes de ter que re-consultar as vagas.
# Grupo com poucas vagas esgota rápido -> revalida sempre; grupo cheio pode
# usar cache por dias. (regra do Uriel, 30/08/2026)
def dias_de_validade(vagas):
    v = int(vagas or 0)
    if v < 10:   return 0          # sempre re-consulta
    if v <= 25:  return 1
    if v <= 40:  return 2
    if v <= 50:  return 3          # (faixa 40–50: interpolado)
    if v <= 80:  return 4
    if v <= 120: return 7
    if v <= 170: return 12
    return 20                      # >170: cache longo


def precisa_reconsultar(vagas, consultado_em):
    """True se o dado do grupo está velho demais pra confiar (usar no orquestrador
    antes de mandar o robô re-checar as vagas de um grupo já catalogado)."""
    lim = dias_de_validade(vagas)
    if lim == 0:
        return True
    try:
        d = datetime.datetime.fromisoformat(str(consultado_em).replace("Z", "+00:00"))
        idade = (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds() / 86400
        return idade > lim
    except Exception:
        return True

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


def _valores_rs(txt):
    """Todos os valores em R$ de um texto ('R$ 21.000,00 - R$ 30.000,00' -> [21000, 30000])."""
    return [_num(v) for v in re.findall(r"R\$\s*([\d.]+,\d{2})", str(txt or ""))]


def _rs_na_str(txt):
    """crédito da faixa = MAIOR valor em R$ do texto (o 1º pode ser a base reduzida)."""
    vs = _valores_rs(txt)
    return max(vs) if vs else 0.0


def _tem_pr(txt):
    """True se o texto indica parcela reduzida: 'PR' como palavra, 'REDUZ...' ou 'REDUÇ...'."""
    up = (txt or "").upper()
    return bool(re.search(r"\bPR\b", up) or "REDUZ" in up or "REDUÇ" in up
                or re.search(r"REDU[CÇ]", up))


def _reducao_faixa(texto_opcao):
    """(credito, base_parcela, reducao_pct). Se o texto tem 2 valores e o 1º < 2º,
    a parcela é calculada sobre o menor (parcela reduzida)."""
    vs = _valores_rs(texto_opcao)
    if not vs:
        return 0.0, 0.0, 0
    credito = max(vs)
    base = min(vs)
    red = round((credito - base) / credito * 100) if credito and base < credito else 0
    return credito, base, int(red)


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


HOME_URL = "https://newkey.cny.com.br/Intranet/frmMain.aspx"


def _ir_para_form(page, tentativas=4):
    """Garante que estamos no form de Venda de Proposta. Se já estivermos, sai
    na hora. Senão navega pelo menu; e, se travou numa tela intermediária,
    volta pra HOME (não a URL de login) e tenta de novo."""
    for i in range(tentativas):
        try:
            # já estamos no form? não mexe.
            if page.locator(S["produto"]).count() and \
               page.locator(S["produto"]).first.is_visible():
                return True
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            if i:                                   # nas retentativas, home limpa
                page.goto(HOME_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
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
            page.wait_for_selector(S["produto"], state="visible", timeout=20000)
            return True
        except Exception as e:
            print(f"   [nav] tentativa {i+1}/{tentativas}: {str(e)[:70]}")
            page.wait_for_timeout(1500)
    raise RuntimeError("não consegui abrir o formulário de Venda de Proposta")


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


def _sel_por_texto(page, sel, *palavras):
    """Seleciona no <select> a opção cujo texto contém alguma das palavras."""
    page.wait_for_selector(sel, timeout=20000)
    for _ in range(20):
        ops = _opcoes(page, sel)
        for v, t in ops:
            up = (t or "").upper()
            if any(p.upper() in up for p in palavras):
                _sel(page, sel, v)
                return t
        page.wait_for_timeout(500)
        page.wait_for_load_state("networkidle")
    raise RuntimeError(f"Não achei opção com {palavras} em {sel}. "
                       f"Opções: {[t for _, t in _opcoes(page, sel)]}")


def _fill(page, sel, val):
    el = page.locator(sel).first
    try:
        el.fill(str(val))
    except Exception:
        el.click(); el.press("Control+a"); el.type(str(val), delay=20)
    el.press("Tab"); page.wait_for_timeout(300)


def _preambulo(page, palavras_produto):
    """CPF + Produto (selecionado pelo texto). Deixa a tela pronta p/ escolher o plano."""
    if CPF:
        _fill(page, S["cpf_vend"], CPF)
        try:
            _fill(page, S["cpf_cli"], CPF)
        except Exception:
            pass
    _sel_por_texto(page, S["produto"], *palavras_produto)
    _esperar_opcoes(page, S["tp_venda"], 1)


_JS_GRADE = r"""() => {
  const docs = [document, ...[...document.querySelectorAll('iframe')]
        .map(f => { try { return f.contentDocument; } catch (e) { return null; } })
        .filter(Boolean)];
  const linhaGrupo = /^\s*\d{4,6}\s*-\s*[A-Za-z]/;   // "010011 - A", "9600 - F"
  const cand = [];
  for (const doc of docs) {
    for (const tb of doc.querySelectorAll('table')) {
      const rows = [...tb.querySelectorAll('tr')].map(tr =>
        [...tr.querySelectorAll('td')].map(td =>
          (td.innerText || '').replace(/\s+/g, ' ').trim()));
      const nData = rows.filter(r => r.length >= 8 && linhaGrupo.test(r[0] || '')).length;
      if (nData) cand.push({ rows, nData,
                             leaf: tb.querySelectorAll('table').length === 0,
                             tot: rows.length });
    }
  }
  if (!cand.length) return [];
  // prefere a tabela FOLHA (sem tabela aninhada) e mais enxuta
  cand.sort((a, b) => (b.leaf - a.leaf) || (a.tot - b.tot));
  return cand[0].rows;
}"""


# linha da grade em TEXTO (fallback quando não é <table> normal):
#  010011 - A  IMÓVEL R$200 MIL  200.000,00  23,0000  21/09/2026  16/09/2026  186 / 216  002  600  1.390,50  67,6194
RE_LINHA_GRUPO = re.compile(
    r"(\d{4,6})\s*-\s*([A-Za-z])\s+"          # grupo + fase
    r"(.+?)\s+"                                # bem
    r"([\d.]+,\d{2})\s+"                       # valor/crédito
    r"(\d{1,3},\d{2,4})\s+"                    # taxa
    r"(\d{2}/\d{2}/\d{4})\s+"                  # assembleia
    r"(\d{2}/\d{2}/\d{4})\s+"                  # vencto
    r"(\d{1,3})\s*/\s*(\d{1,3})\s+"            # prazo restante / total
    r"(\d{1,4})\s+"                            # vagas
    r"(\d{1,5})\s+"                            # participantes
    r"([\d.]+,\d{2})\s+"                       # parcela
    r"([\d.]+,\d{2,4})"                        # lance médio
)


def _linhas_do_texto(txt):
    out = []
    for m in RE_LINHA_GRUPO.finditer(txt or ""):
        (grp, fase, bem, valor, taxa, ass, venc, pr_r, pr_t,
         vagas, part, parc, lance) = m.groups()
        out.append({
            "grupo": str(int(grp)), "grupo_raw": f"{grp} - {fase}",
            "bem": bem.strip(), "credito": _num(valor), "taxa": _num(taxa),
            "prox_assembleia": ass, "vencto_assembleia": venc,
            "prazo_restante": int(pr_r), "prazo_total": int(pr_t),
            "vagas": int(vagas), "participantes": int(part),
            "parcela": _num(parc), "lance_medio": _num(lance),
        })
    return out


def _ler_grade(page, espera=12000):
    """Extrai a grade de grupos. Tenta como <table>; se não achar, parseia o texto."""
    fim = time.time() + espera / 1000
    while time.time() < fim:
        # 1) tenta como tabela
        try:
            linhas = page.evaluate(_JS_GRADE)
        except Exception:
            linhas = []
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
        if out:
            return out
        # 2) fallback: parseia o texto visível da página (e dos iframes extras)
        try:
            txt = page.evaluate("() => document.body.innerText")
            for fr in page.frames:
                if fr is page.main_frame:
                    continue
                try:
                    txt += "\n" + fr.evaluate("() => document.body.innerText")
                except Exception:
                    pass
        except Exception:
            txt = ""
        out = _linhas_do_texto(txt)
        if out:
            vistos, unicos = set(), []          # dedup por grupo
            for g in out:
                if g["grupo"] not in vistos:
                    vistos.add(g["grupo"]); unicos.append(g)
            return unicos
        page.wait_for_timeout(700)
    return []


def _prazos_ordenados(prazos, pref):
    """pref='curto'  -> SÓ o menor prazo do plano.
       pref='longo'  -> SÓ o maior prazo do plano.
       None/'todos'  -> TODOS os prazos (varredura completa)."""
    def _n(txt):
        m = re.search(r"\d+", txt or "")
        return int(m.group(0)) if m else 999
    if pref == "curto":
        return sorted(prazos, key=lambda p: _n(p[1]))[:1]
    if pref == "longo":
        return sorted(prazos, key=lambda p: -_n(p[1]))[:1]
    return prazos


def _coletar_plano(page, plano_val, plano_txt, alvo=None, com_grupos=False,
                   prazo_pref=None, max_faixas=1):
    """Seleciona o plano e MEMORIZA de uma vez todas as faixas de crédito.
    Com `alvo`: NÃO clica crédito por crédito — pega só o valor exato (ou o(s)
    `max_faixas` mais próximo(s)) por prazo. Se `prazo_pref` for 'curto'/'longo',
    tenta primeiro esses prazos e só cai nos outros se não achar grupo.
    Retorna (meta_do_plano, [grupos])."""
    print(f"\n== PLANO {plano_txt} ==")
    pr_plano = _tem_pr(plano_txt)          # PR / REDUZIDA no nome do plano
    _sel(page, S["tp_venda"], plano_val)
    _esperar_opcoes(page, S["prazo"], 1)
    prazos = _prazos_ordenados(_opcoes(page, S["prazo"]) or [(None, "(único)")], prazo_pref)

    # campos que podem ser obrigatórios pro Avançar (convênio, tipo de negociação)
    for campo in ("convenio", "negociacao"):
        try:
            ops = _opcoes(page, S[campo])
            atual = page.locator(S[campo]).first.input_value()
            if ops and (not atual or atual in ("0", "")):
                _sel(page, S[campo], ops[0][0])
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
        n_red = 0
        for bv, bt, c in faixas:
            if c > 0:
                cred, base, red = _reducao_faixa(bt)
                pr = red > 0 or _tem_pr(bt) or pr_plano
                if pr and red == 0:
                    red = 30            # PR no nome sem valor duplo: redução padrão Yamaha 30%
                if pr:
                    n_red += 1
                creditos_plano.append({
                    "bem_cod": bv, "texto": bt, "credito": cred or c,
                    "base_parcela": base or (cred or c), "reducao_pct": red,
                    "parcela_reduzida": bool(pr), "prazo": pz_txt})
        vals = sorted({(_reducao_faixa(bt)[0] or c) for _, bt, c in faixas if c})
        faixa_str = (f"{vals[0]:,.0f}–{vals[-1]:,.0f}" if len(vals) > 1
                     else (f"{vals[0]:,.0f}" if vals else "?"))
        pr_str = f"  [{n_red} c/ parcela reduzida]" if n_red else ""
        print(f"   prazo {pz_txt}: {len(faixas)} faixa(s) de crédito  ({faixa_str}){pr_str}")

        # Só entra na grade se precisar dos grupos (alvo ou --com-grupos)
        if not (alvo or com_grupos):
            continue
        if alvo:
            # 1º: valor EXATO. 2º: os `max_faixas` mais próximos dentro da
            # janela (-10% / +15%). NÃO clica crédito por crédito.
            exatas = [f for f in faixas if f[2] and abs(f[2] - alvo) < 1]
            if exatas:
                alvos = exatas[:max_faixas]
            else:
                candidatas = sorted((f for f in faixas if _perto_do_alvo(f[2], alvo)),
                                    key=lambda f: abs(f[2] - alvo))
                if not candidatas and any(f[2] for f in faixas):
                    candidatas = [min((f for f in faixas if f[2]),
                                      key=lambda f: abs(f[2] - alvo))]
                alvos = candidatas[:max_faixas]
        else:
            alvos = [f for f in faixas if f[2]]
        for bv, bt, cval in alvos:
            cred_f, base_f, red_f = _reducao_faixa(bt)
            pr_f = red_f > 0 or _tem_pr(bt) or pr_plano
            if pr_f and red_f == 0:
                red_f = 30
            print(f"      prazo {pz_txt}, R$ {cval:,.0f} → Avançar...", end=" ", flush=True)
            _sel(page, S["bem"], bv)
            try:
                page.locator(S["avancar"]).first.click(timeout=10000, no_wait_after=True)
            except Exception as e:
                print(f"(Avançar: {str(e)[:40]})", end=" ")
            page.wait_for_timeout(1500); page.wait_for_load_state("networkidle")
            gs = _ler_grade(page)
            print(f"{len(gs)} grupo(s)")
            if not gs and not _DIAG_FEITO[0]:
                _DIAG_FEITO[0] = True
                try:
                    page.screenshot(path=os.path.join(PASTA, "diag_grade_vazia.png"))
                    txt = page.evaluate("() => document.body.innerText.replace(/\\s+/g,' ').slice(0,600)")
                    print(f"      [diag] url={page.url[:80]}")
                    print(f"      [diag] tela: {txt[:400]}")
                    print(f"      [diag] screenshot: worker/diag_grade_vazia.png")
                except Exception:
                    pass
            for g in gs:
                g.update({"plano_cod": _cod(plano_txt), "plano_txt": plano_txt,
                          "prazo_label": pz_txt, "credito_faixa": cred_f or cval or g["credito"],
                          "base_parcela": base_f or None, "reducao_pct": red_f,
                          "parcela_reduzida": bool(pr_f)})
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
                _preambulo(page, _PROD_PAL)
                _sel(page, S["tp_venda"], plano_val)
                if pz_val:
                    _sel(page, S["prazo"], pz_val)
                page.locator(S["rb_bem"]).first.check()
                _esperar_opcoes(page, S["bem"], 1)

    # dedup por (código do Bem + prazo) — o mesmo Bem existe em vários prazos
    vistas, fx = set(), []
    for c in creditos_plano:
        ch = (c["bem_cod"], c.get("prazo"))
        if ch not in vistas:
            vistas.add(ch); fx.append(c)
    meta = {"plano_cod": _cod(plano_txt), "plano_txt": plano_txt,
            "parcela_reduzida": bool(pr_plano or any(c["parcela_reduzida"] for c in fx)),
            "creditos": fx}
    return meta, grupos


def _salvar(sb, prod_nome, metas, grupos):
    agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for m in metas:
        try:
            sb.table("planos_yamaha").upsert({
                "codigo": m["plano_cod"], "tipo_bem": prod_nome, "nome": m["plano_txt"],
                "parcela_reduzida": m.get("parcela_reduzida", False),
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
                "parcela_reduzida": g.get("parcela_reduzida", False),
                "reducao_pct": g.get("reducao_pct") or None,
                "base_parcela": g.get("base_parcela"),
                "consultado_em": agora, "fonte": "newcon-venda-proposta",
            }, on_conflict="grupo,tipo_bem").execute()
            sb.table("grupos_yamaha_consultas").insert({
                "grupo": g["grupo"], "tipo_bem": prod_nome, "vagas": g["vagas"],
                "credito": g["credito"], "consultado_em": agora}).execute()
            n += 1
        except Exception as e:
            print(f"  ! grupo {g['grupo']}: {str(e)[:120]}")
    return n


def _registrar_busca(sb, prod_nome, plano_cod, alvo, grupos_do_plano):
    """Grava em yamaha_buscas o resultado da busca (plano+crédito), MESMO vazio.
    Assim o robô não repete hoje uma busca que já fez e não achou vaga."""
    if not alvo:
        return
    try:
        com_vaga = [g for g in grupos_do_plano if (g.get("vagas") or 0) > 0]
        prazos = sorted({str(g.get("prazo_total") or "") for g in grupos_do_plano}) or [""]
        sb.table("yamaha_buscas").upsert({
            "tipo_bem": prod_nome, "plano_codigo": _cod(plano_cod),
            "credito": float(alvo), "prazo_label": prazos[0] or "(único)",
            "grupos_encontrados": len(com_vaga),
            "vagas_total": sum(int(g.get("vagas") or 0) for g in com_vaga),
            "grupos": [str(g["grupo"]) for g in com_vaga],
            "consultado_em": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }, on_conflict="tipo_bem,plano_codigo,credito,prazo_label").execute()
    except Exception as e:
        print(f"  ! não registrei a busca do plano {plano_cod}: {str(e)[:100]}")


def _carregar_catalogo(sb, prod_nome):
    """{codigo: {'nome','creditos','consultado_em'}} da tabela planos_yamaha."""
    try:
        rows = sb.table("planos_yamaha").select("*").eq("tipo_bem", prod_nome).execute().data or []
    except Exception:
        return {}
    return {_cod(r["codigo"]): r for r in rows}


def _idade_dias(iso):
    try:
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - d).days
    except Exception:
        return 9999


def _cod(x):
    """Normaliza código de plano: '074', ' 074 - Nome', 74 -> '074'."""
    d = re.sub(r"\D", "", str(x or "").split("-")[0])
    return d.zfill(3) if d else str(x or "").strip()


_cod_do_txt = _cod   # alias (compat)


def _planos_novos_ou_velhos(planos_newcon, catalogo, max_dias):
    """(novos, velhos) — planos do Newcon que faltam no catálogo ou estão desatualizados."""
    novos, velhos = [], []
    for v, t in planos_newcon:
        cod = _cod_do_txt(t)
        reg = catalogo.get(cod)
        if reg is None:
            novos.append((v, t))
        elif _idade_dias(reg.get("consultado_em")) > max_dias:
            velhos.append((v, t))
    return novos, velhos


def _planos_para_alvo(catalogo, alvo):
    """Códigos de plano que, no catálogo, têm faixa de crédito perto do alvo."""
    ok = []
    for cod, reg in catalogo.items():
        for c in (reg.get("creditos") or []):
            cv = c.get("credito") or 0
            if _perto_do_alvo(cv, alvo):
                ok.append(cod)
                break
    return set(ok)


# --------------------------------------------------------------------------
def main():
    a = sys.argv[1:]
    if not a or "--help" in a or "-h" in a:
        print(__doc__); return

    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a else d

    global _PROD_PAL
    prod_in = (opt("--produto", "auto") or "auto").lower()
    if prod_in not in PRODUTOS:
        print("produto: moto|auto|imovel|caminhao"); return
    prod_nome, prod_pal = PRODUTOS[prod_in]
    _PROD_PAL = prod_pal
    alvo = _num(opt("--credito")) or None
    prazo_pref = (opt("--prazo") or "").lower().strip() or None   # curto | longo
    if prazo_pref not in (None, "curto", "longo", "todos"):
        print("--prazo: curto | longo | todos"); return
    if prazo_pref == "todos":
        prazo_pref = None
    max_faixas = int(opt("--faixas", "1"))     # quantas faixas de crédito por prazo
    n_grupos = int(opt("--n-grupos", "0")) or None   # para quando achar N grupos c/ vaga
    salvar = "--salvar" in a
    sync = "--sync" in a
    max_dias = int(opt("--max-idade-dias", str(CATALOGO_MAX_DIAS)))

    sb = _conectar_sb()
    pw, browser, ctx, page = _abrir(sb, visivel=("--headless" not in a))
    try:
        _ir_para_form(page)
        _preambulo(page, prod_pal)

        planos_todos = _opcoes(page, S["tp_venda"])
        planos_validos = [(v, t) for v, t in planos_todos if _plano_valido(t)]
        com_grupos = "--com-grupos" in a

        # --- SEMPRE: a Yamaha cria planos novos toda hora. Detecta e avisa. ---
        catalogo = _carregar_catalogo(sb, prod_nome)
        novos, velhos = _planos_novos_ou_velhos(planos_validos, catalogo, max_dias)
        if novos:
            print(f"[NOVO] {len(novos)} plano(s) NOVO(S) que não estão no catálogo: "
                  + "; ".join(t for _, t in novos))
        if velhos and (sync or alvo):
            print(f"[VELHO] {len(velhos)} plano(s) com catálogo desatualizado (> {max_dias}d)")

        if sync:
            # varre catálogo dos planos novos + desatualizados (sem entrar em grupo)
            planos = novos + velhos
            if not planos:
                print("\n[OK] Catálogo já em dia — nenhum plano novo nem vencido.")
                return
            com_grupos = False
            salvar = True
            print(f">>> SYNC: catalogando {len(planos)} plano(s)")
        elif opt("--planos"):
            querid = {_cod(x) for x in opt("--planos").split(",")}
            planos = [(v, t) for v, t in planos_todos if _cod(t) in querid]
        elif opt("--plano"):
            alvo_cod = _cod(opt("--plano"))
            planos = [(v, t) for v, t in planos_todos if _cod(t) == alvo_cod]
        elif "--todos-planos" in a:
            planos = planos_validos
        elif alvo:
            # usa o CATÁLOGO pra ir direto nos planos que têm esse crédito;
            # + planos novos (crédito ainda desconhecido) por garantia.
            cods_alvo = _planos_para_alvo(catalogo, alvo)
            planos = [(v, t) for v, t in planos_validos
                      if _cod(t) in cods_alvo or (v, t) in novos]
            if not planos:
                print(f"   catálogo não tem plano perto de R$ {alvo:,.0f} "
                      f"(ou está vazio) → varrendo todos os planos válidos")
                planos = planos_validos
            # PRIORIDADE: planos do MEIO da lista pra frente (os mais recentes).
            # Os do início quase nunca têm vaga — só se o usuário pedir
            # (--incluir-antigos ou --planos explícito).
            if not opt("--planos") and "--incluir-antigos" not in a and len(planos) > 2:
                cods_ord = sorted(_cod(t) for _, t in planos_validos)
                meio = cods_ord[len(cods_ord) // 2]
                recentes = [(v, t) for v, t in planos if _cod(t) >= meio]
                antigos = len(planos) - len(recentes)
                if recentes:
                    planos = recentes
                    if antigos:
                        print(f"   (pulando {antigos} plano(s) antigo(s) — raramente têm "
                              f"vaga; use --incluir-antigos pra varrer tudo)")
            print(f"   catálogo: {len(planos)} plano(s) com crédito ~R$ {alvo:,.0f}")
            com_grupos = True                   # com alvo, sempre traz os grupos
            # pula plano cuja busca (plano+crédito) já foi feita HOJE sem achar vaga
            if "--refazer" not in a:
                try:
                    hoje0 = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                    bv = sb.table("yamaha_buscas").select("plano_codigo,vagas_total,consultado_em") \
                        .eq("tipo_bem", prod_nome).gte("credito", alvo * (1 - TOL_BAIXO)) \
                        .lte("credito", alvo * (1 + TOL_ALTO)).execute().data or []
                    sem_vaga_hoje = {r["plano_codigo"] for r in bv
                                     if (r.get("vagas_total") or 0) == 0
                                     and str(r.get("consultado_em", ""))[:10] == hoje0}
                    if sem_vaga_hoje:
                        antes = len(planos)
                        planos = [(v, t) for v, t in planos if _cod(t) not in sem_vaga_hoje]
                        if antes != len(planos):
                            print(f"   (pulando {antes - len(planos)} plano(s) que já busquei "
                                  f"hoje e não tinham vaga)")
                except Exception:
                    pass
        else:
            print("Escolha: --plano NNN | --planos 069,073,074 | --credito VALOR | "
                  "--todos-planos | --sync")
            print(f"\nPlanos de {prod_nome} ([x] = ignorado por padrão):")
            for v, t in planos_todos:
                print(f"  {'[x]' if not _plano_valido(t) else '  '} {t}")
            return

        # RETOMADA: pula planos já catalogados hoje (a não ser --refazer).
        # Assim, se travou no meio, é só rodar de novo que continua de onde parou.
        refazer = "--refazer" in a
        # retomada só no CATÁLOGO puro. Com alvo/--com-grupos sempre re-entra
        # nas grades (vagas mudam) — nunca pula.
        if salvar and not refazer and not com_grupos and not alvo:
            ja = {c for c, r in catalogo.items()
                  if _idade_dias(r.get("consultado_em")) < 1 and (r.get("creditos") or r.get("consultado_em"))}
            antes = len(planos)
            planos = [(v, t) for v, t in planos if _cod(t) not in ja]
            if antes != len(planos):
                print(f"   (retomada: {antes - len(planos)} plano(s) já feito(s) hoje — pulando; "
                      f"use --refazer pra rever tudo)")

        print(f">>> {prod_nome} | {len(planos)} plano(s) a varrer"
              + (f" | alvo R$ {alvo:,.0f}" if alvo else "")
              + (" | + grupos" if com_grupos else ""))

        metas, grupos, falhas, parou_em = [], [], [], None
        for i, (pv, pt) in enumerate(planos, 1):
            print(f"\n[{i}/{len(planos)}]", end=" ")
            ok_plano = False
            for tent in (1, 2):                          # 1 retry por plano
                try:
                    m, gs = _coletar_plano(page, pv, pt, alvo=alvo, com_grupos=com_grupos,
                                           prazo_pref=prazo_pref, max_faixas=max_faixas)
                    metas.append(m); grupos += gs
                    if salvar:
                        try:
                            _salvar(sb, prod_nome, [m], gs)
                            _registrar_busca(sb, prod_nome, m["plano_cod"], alvo, gs)
                        except Exception as e:
                            print(f"  ! não gravei o plano {m['plano_cod']}: {str(e)[:100]}")
                    ok_plano = True
                    break
                except Exception as e:
                    print(f"  ~ plano {pt} tentativa {tent}: {str(e)[:110]}")
                    try:
                        _ir_para_form(page); _preambulo(page, prod_pal)
                    except Exception:
                        pass
            if not ok_plano:
                falhas.append(pt)
                print(f"  x plano {pt} FALHOU nas 2 tentativas")
            # já achei grupos com vaga suficientes? (--n-grupos)
            if n_grupos:
                com_vaga = len({g["grupo"] for g in grupos if (g.get("vagas") or 0) > 0})
                if com_vaga >= n_grupos:
                    print(f"\n  >> {com_vaga} grupo(s) com vaga encontrados "
                          f"(--n-grupos {n_grupos}) — encerrando a varredura.")
                    break
            # recomeça limpo pro próximo plano
            try:
                _ir_para_form(page); _preambulo(page, prod_pal)
            except Exception as e:
                parou_em = (i, pt)
                print(f"\n  !! NÃO CONSEGUI VOLTAR AO FORM ({str(e)[:70]})")
                print(f"  !! PAROU no plano {pt} ({i}/{len(planos)}). "
                      f"O que já foi coletado ESTÁ salvo. Rode o MESMO comando de novo "
                      f"que ele continua de onde parou.")
                break

        print(f"\n{'='*90}\nCATÁLOGO: {len(metas)} plano(s), "
              f"{sum(len(m['creditos']) for m in metas)} faixa(s) de crédito, "
              f"{len(grupos)} grupo(s)\n{'='*90}")
        if falhas:
            print(f"[!] {len(falhas)} plano(s) falharam (rode de novo p/ tentar): "
                  + "; ".join(falhas))
        if parou_em:
            print(f"[!] INTERROMPIDO no plano {parou_em[1]} ({parou_em[0]}/{len(planos)}). "
                  f"Rode o mesmo comando de novo para continuar.")
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

        out = os.path.join(PASTA, "grupos_ultima_coleta.json")
        open(out, "w", encoding="utf-8").write(
            json.dumps({"metas": metas, "grupos": grupos}, ensure_ascii=False, indent=1))
        if salvar:
            print(f"\n[OK] {len(metas)} plano(s) + {len(grupos)} grupo(s) gravados no "
                  f"Supabase (plano a plano, à medida que coletou).")
        else:
            print(f"\n(modo teste — nada gravado. JSON: {out})")
    finally:
        try:
            browser.close(); pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
