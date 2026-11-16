# -*- coding: utf-8 -*-
r"""
explorar_newcon.py — MÓDULO DE APRENDIZADO do robô Yamaha (não é outro robô).

Quem chama é o próprio robô:
    python robo_yamaha.py --explorar               # explora o Newcon inteiro (retoma sozinho)
    python robo_yamaha.py --explorar --limite 5    # só 5 telas (teste)
    python robo_yamaha.py --explorar --so GR/AA,VE/VP   # só esses submenus
    python robo_yamaha.py --explorar --refazer     # recomeça a exploração do zero
    python robo_yamaha.py --mapa                   # só regera o MAPA/ONDE_ACHAR com o que já sabe
  modo antigo (alguém navega e ele anota):  python explorar_newcon.py --manual

O QUE ELE FAZ
  1. Lê o menu do Newcon (Venda, Grupo, Cobrança, Contemplação, Crédito, Atendimento):
     cada submenu tem endereço fixo  frmMainMenu.aspx?ID_Modulo=XX&ID_SubGrupo=YY.
  2. Em cada submenu lê a ÁRVORE de telas (tvwMenu) e abre tela por tela.
  3. Em cada tela anota: título, todos os campos (rótulo, tipo, TODAS as opções dos
     combos), botões, abas, tabelas (cabeçalho + amostra) e o texto da tela.
  4. "Entende os campos": escolhe a 1ª opção de cada combo que dispara postback
     e anota o que ele libera (ex.: Produto -> preenche Tipo de Venda).
  5. Clica SÓ em botões de CONSULTA (Buscar/Localizar/Pesquisar/Consultar/Listar/
     Filtrar/Visualizar/Exibir) para ver o resultado.
  6. Dá nota a cada tela para os dados que interessam ao simulador
     (grupos por produto, vagas, créditos, taxa, seguro, lance) e escreve:
        conhecimento_newcon/MAPA_NEWCON.md   (todas as telas e para que serve cada uma)
        conhecimento_newcon/ONDE_ACHAR.md    (onde está cada dado, da melhor tela p/ pior)

SEGURANÇA (só leitura)
  * NUNCA clica Confirmar / Avançar / Gravar / Salvar / Emitir / Imprimir / Ofertar /
    Cancelar / Excluir / Alterar / Logout. Diálogos de confirmação são RECUSADOS.
  * Telas com nome sensível (cancelamento, estorno, transferência, oferta, emissão,
    senha...) só são LISTADAS, não abertas.
  * Se aparecer LANCE/BOLETO na fila_automacao, para (salvando) e cede a vez.

MEMÓRIA / RETOMADA (se cair, volta de onde parou)
  conhecimento_newcon/estado_exploracao.json  -> fila do que falta, o que já fez,
      falhas por tela e a tela "em_andamento" (se o PC cair no meio, na volta ela
      conta como 1 falha; com 3 falhas a tela é pulada e anotada).
  conhecimento_newcon/diario.log             -> cada passo com data/hora; ao iniciar,
      o robô mostra as últimas linhas ("o que eu fiz por último").
  conhecimento_newcon/telas/*.json            -> o que ele aprendeu de cada tela.
"""
import os
import re
import sys
import json
import time
import glob
import hashlib
import datetime

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)
BASE = "https://newkey.cny.com.br/Intranet/"
HOME_URL = BASE + "frmMain.aspx"
CON = os.path.join(PASTA, "conhecimento_newcon")
TELAS = os.path.join(CON, "telas")
ERROS = os.path.join(CON, "erros")
ESTADO = os.path.join(CON, "estado_exploracao.json")
DIARIO = os.path.join(CON, "diario.log")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ----------------------------------------------------------------- regras de segurança
RE_TELA_BLOQUEADA = re.compile(
    r"cancel|exclu|estorn|transfer|devolu|alterar|altera[çc][ãa]o|senha|logout|\bsair\b|oferta|"
    r"efetiv|desist|quita[çc]|resgate|emiss[ãa]o|emitir|inclus[ãa]o|incluir|grava|baixa manual|"
    r"reativ|substitui|cess[ãa]o", re.I)
RE_BOTAO_CONSULTA = re.compile(
    r"^\s*(buscar|localizar|pesquisar|consultar|listar|filtrar|visualizar|exibir|pesquisa|consulta|"
    r"buscar grupos|ok)\s*$", re.I)
RE_BOTAO_PROIBIDO = re.compile(
    r"confirm|avan[çc]|grav|salv|emit|imprim|ofert|cancel|exclu|alter|logout|sair|enviar|"
    r"process|efetiv|gerar|baixar|download|incluir|novo|aprovar|reprovar|finaliz", re.I)
# "OK" só conta como consulta se a tela for de filtro/relatório (sem palavra perigosa no caminho)

ALVOS = {
    "grupos_por_produto": r"\bgrupo|produto|esp[ée]cie|tipo de bem|segmento|moto|autom|im[óo]ve|caminh",
    "vagas": r"vaga|participant|cotas? (ativ|vend|dispon)|dispon[íi]ve|capacidade|n[ºo]\.? de cotas|qtd\.? cotas",
    "creditos": r"cr[ée]dito|valor do bem|\bbem\b|faixa|valor da carta|pre[çc]o do bem|valor base",
    "taxa": r"taxa|tx\.? ?adm|administra[çc][ãa]o|fundo de reserva|\bf\.?r\.?\b|% ?adm",
    "seguro": r"seguro|prestamista|\bseg\.",
    "lance": r"lance|m[ée]dia|contempla",
}


# ----------------------------------------------------------------- util
def _agora():
    return datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _diario(msg):
    os.makedirs(CON, exist_ok=True)
    linha = f"[{_agora()}] {msg}"
    print("  " + linha, flush=True)
    with open(DIARIO, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def _ultimas_do_diario(n=6):
    try:
        return open(DIARIO, encoding="utf-8").read().strip().splitlines()[-n:]
    except Exception:
        return []


def _slug(txt):
    import unicodedata
    t = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")
    return (t[:70] or "tela") + "_" + hashlib.md5(txt.encode()).hexdigest()[:6]


def _gravar_json(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)          # gravação atômica: nunca fica arquivo pela metade


def _estado_ler():
    try:
        return json.load(open(ESTADO, encoding="utf-8"))
    except Exception:
        return None


def _estado_novo():
    return {"inicio": _agora(), "fase": "menu", "fila": [], "feitas": {}, "falhas": {},
            "bloqueadas": {}, "em_andamento": None, "submenus": {}}


def _estado_gravar(e):
    e["atualizado_em"] = _agora()
    _gravar_json(ESTADO, e)


# ----------------------------------------------------------------- leitura da tela (JS)
_JS_MENU = r"""() => {
 const t = el => (el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
 const out=[];
 for (const li of document.querySelectorAll('#menu li[id^="menu_trigger"]')) {
   const top = t(li.querySelector(':scope > a'));
   for (const a of li.querySelectorAll('ul a[href*="frmMainMenu.aspx"]'))
     out.push({modulo: top, nome: t(a), href: a.getAttribute('href')});
 }
 return out;
}"""

_JS_ARVORE = r"""() => {
 const t = el => (el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
 const nos = [...document.querySelectorAll("a[id*='tvwMenut']")];
 return nos.map(a => {
   let pai = '', e = a.parentElement;
   while (e) { if (e.tagName === 'DIV' && /tvwMenun\d+Nodes$/.test(e.id)) {
       const pid = e.id.replace(/Nodes$/, '').replace(/n(\d+)$/, 't$1');
       const p = document.getElementById(pid); pai = p ? t(p) : ''; break; }
     e = e.parentElement; }
   const h = a.getAttribute('href') || '';
   const m = h.match(/~\/([^'"\\]+\.aspx)/);
   return {id: a.id, txt: t(a), pai: pai, alvo: m ? m[1] : ''};
 }).filter(n => n.txt);
}"""

_JS_TELA = r"""() => {
 const vis = el => { const r = el.getBoundingClientRect();
   return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
 const t = el => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
 const RUIDO = /tvwEmpresa|tvwAgenda|tvwConexoes|img_AlteraSenha|img_Atendimento|lkbSair|tvwMenu/;
 const rotulo = el => {
   if (el.id) { const l = document.querySelector('label[for="' + el.id + '"]'); if (l && t(l)) return t(l).slice(0, 60); }
   const td = el.closest('td');
   if (td) { let p = td.previousElementSibling; while (p && !t(p)) p = p.previousElementSibling;
             if (p) return t(p).slice(0, 60);
             const tr = td.parentElement, trp = tr && tr.previousElementSibling;
             if (trp && trp.children[td.cellIndex]) { const x = t(trp.children[td.cellIndex]); if (x) return x.slice(0, 60); } }
   let s = el.previousSibling, n = 0;
   while (s && n < 4) { const x = (s.textContent || '').replace(/\s+/g, ' ').trim(); if (x) return x.slice(0, 60); s = s.previousSibling; n++; }
   return (el.title || el.placeholder || '').slice(0, 60);
 };
 const out = { titulo: document.title || '', cabecalhos: [], campos: [], botoes: [], abas: [], tabelas: [], links: [] };
 for (const h of document.querySelectorAll('h1,h2,h3,legend,.titulo,.Titulo,[id*=lblTitulo],[id*=Titulo]'))
   { const x = t(h); if (x && x.length < 120) out.cabecalhos.push(x); }
 for (const el of document.querySelectorAll('input,select,textarea')) {
   if (RUIDO.test(el.id || '')) continue;
   const tp = (el.type || '').toLowerCase();
   if (tp === 'hidden') continue;
   if (['submit', 'button', 'image', 'reset'].includes(tp)) {
     out.botoes.push({ id: el.id || '', txt: (el.value || el.title || el.alt || '').trim().slice(0, 60), vis: vis(el), tipo: tp });
     continue; }
   const c = { tag: el.tagName.toLowerCase(), tipo: tp, id: el.id || '', rotulo: rotulo(el), vis: vis(el),
               valor: (el.value || '').slice(0, 60),
               postback: /__doPostBack/.test(el.getAttribute('onchange') || '') || /__doPostBack/.test(el.getAttribute('onclick') || '') };
   if (el.tagName === 'SELECT') { const ops = [...el.options].map(o => [o.value, t(o)]);
     c.n_opcoes = ops.length; c.opcoes = ops.slice(0, 400); c.selecionado = el.selectedIndex >= 0 ? t(el.options[el.selectedIndex]) : ''; }
   if (tp === 'checkbox' || tp === 'radio') c.marcado = el.checked;
   out.campos.push(c);
 }
 for (const el of document.querySelectorAll('button,a[id],[role=button]')) {
   if (RUIDO.test(el.id || '') || el.closest('#menu')) continue;
   const x = t(el) || el.title || '';
   if (!x) continue;
   if (el.tagName === 'A') out.links.push({ id: el.id, txt: x.slice(0, 60), vis: vis(el) });
   else out.botoes.push({ id: el.id || '', txt: x.slice(0, 60), vis: vis(el), tipo: el.tagName.toLowerCase() });
 }
 for (const el of document.querySelectorAll('[role=tab]')) { const x = t(el); if (x) out.abas.push(x.slice(0, 60)); }
 for (const tb of document.querySelectorAll('table')) {
   if (tb.querySelector('table')) continue;                       // só tabela "folha"
   const linhas = [...tb.querySelectorAll('tr')].map(tr => [...tr.querySelectorAll('th,td')].map(c => t(c).slice(0, 50)))
                    .filter(l => l.join('').trim());
   if (linhas.length < 2 || Math.max(...linhas.map(l => l.length)) < 2) continue;
   const ehGrid = /grd|gv|grid|Grid|lst/.test(tb.id || '') || tb.querySelector('th');
   if (!ehGrid && linhas.length < 3) continue;
   out.tabelas.push({ id: tb.id || '', vis: vis(tb), n_linhas: linhas.length, cabecalho: linhas[0], amostra: linhas.slice(1, 13) });
 }
 const corpo = document.querySelector('#ctl00_Conteudo_pnlConteudo, #conteudo, form') || document.body;
 out.texto = t(corpo).slice(0, 4000);
 return out;
}"""


def _ler_tela(page):
    """Lê a página e os iframes. Retorna dict com 'url', 'frames': [...]"""
    res = {"url": (page.url or "").split("?")[0], "frames": []}
    for i, fr in enumerate([page.main_frame] + [f for f in page.frames if f is not page.main_frame]):
        try:
            d = fr.evaluate(_JS_TELA)
        except Exception:
            continue
        if not (d["campos"] or d["botoes"] or d["tabelas"] or d["texto"]):
            continue
        d["frame"] = "principal" if i == 0 else (fr.url or "").split("?")[0]
        res["frames"].append(d)
    return res


def _esperar(page, ms=20000):
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass
    page.wait_for_timeout(600)


def _snap_selects(page):
    try:
        return page.evaluate(r"""() => Object.fromEntries([...document.querySelectorAll('select')]
          .filter(s => s.id).map(s => [s.id, [...s.options].map(o => (o.textContent||'').replace(/\s+/g,' ').trim())]))""")
    except Exception:
        return {}


def _entender_campos(page, tela, max_testes=8):
    """Escolhe a 1ª opção real de cada combo que dispara postback e anota o que mudou."""
    aprendizado = []
    feitos = set()
    for _ in range(max_testes):
        info = _ler_tela(page)
        if not info["frames"]:
            break
        cand = [c for c in info["frames"][0]["campos"]
                if c["tag"] == "select" and c["vis"] and c["postback"] and c["id"] not in feitos
                and 2 <= c.get("n_opcoes", 0) <= 400]
        if not cand:
            break
        c = cand[0]; feitos.add(c["id"])
        reais = [(v, t) for v, t in c["opcoes"] if v not in ("", "0", "-1") and "selecione" not in t.lower()]
        if not reais:
            continue
        antes = _snap_selects(page)
        v, txt = reais[0]
        try:
            page.locator("#" + c["id"]).select_option(value=v, timeout=8000)
        except Exception as e:
            aprendizado.append({"campo": c["rotulo"] or c["id"], "erro": str(e)[:120]})
            continue
        _esperar(page, 20000)
        depois = _snap_selects(page)
        liberou = []
        for sid, ops in depois.items():
            if sid == c["id"]:
                continue
            if ops != antes.get(sid):
                rot = next((x["rotulo"] for x in info["frames"][0]["campos"] if x["id"] == sid), sid)
                liberou.append({"campo": rot or sid, "id": sid, "n_opcoes": len(ops), "exemplos": ops[:15]})
        aprendizado.append({"campo": c["rotulo"] or c["id"], "id": c["id"], "escolhi": txt,
                            "n_opcoes": len(reais), "liberou": liberou})
    return aprendizado


def _consultar(page, caminho, dialogos):
    """Clica UM botão de consulta visível (se houver) e devolve o que apareceu."""
    if RE_TELA_BLOQUEADA.search(caminho):
        return None
    info = _ler_tela(page)
    for fr in info["frames"][:1]:
        for b in fr["botoes"]:
            if not b["vis"] or not b["id"] or not RE_BOTAO_CONSULTA.match(b["txt"] or ""):
                continue
            if RE_BOTAO_PROIBIDO.search(b["txt"]):
                continue
            if (b["txt"] or "").strip().lower() == "ok" and not re.search(r"consult|relat|result|filtro|pesquis", caminho, re.I):
                continue
            n_dialogos = len(dialogos)
            try:
                page.locator("#" + b["id"]).click(timeout=8000)
            except Exception as e:
                return {"botao": b["txt"], "erro": str(e)[:120]}
            _esperar(page, 30000)
            depois = _ler_tela(page)
            return {"botao": b["txt"], "url_depois": depois["url"], "avisos": dialogos[n_dialogos:],
                    "frames": depois["frames"]}
    return None


def _pontuar(tela):
    """Nota de 0..n para cada dado-alvo + as evidências (rótulos/cabeçalhos que bateram)."""
    pedacos = []
    def add(x, origem):
        if x:
            pedacos.append((str(x), origem))
    for bloco in [tela.get("leitura")] + [((tela.get("consulta") or {}))]:
        for fr in (bloco or {}).get("frames", []) or []:
            for c in fr["campos"]:
                add(c["rotulo"], "campo")
                for _, t in (c.get("opcoes") or [])[:25]:
                    add(t, "opção")
            for tb in fr["tabelas"]:
                for h in tb["cabecalho"]:
                    add(h, "coluna")
            for h in fr["cabecalhos"]:
                add(h, "título")
            add(fr["texto"][:1500], "texto")
    add(tela.get("caminho"), "nome da tela")
    notas, provas = {}, {}
    for alvo, rx in ALVOS.items():
        r = re.compile(rx, re.I)
        hits = [(x, o) for x, o in pedacos if r.search(x)]
        peso = sum(3 if o in ("coluna", "campo") else 2 if o == "nome da tela" else 1 for _, o in hits)
        notas[alvo] = peso
        provas[alvo] = sorted({f"{o}: {x[:50]}" for x, o in hits if o != "texto"})[:8]
    return notas, provas


# ----------------------------------------------------------------- fila / cessão
def _deve_ceder(sb):
    try:
        r = (sb.table("fila_automacao").select("tipo").eq("status", "PENDENTE").execute().data or [])
        return any(re.search(r"LANCE|BOLETO", str(x.get("tipo") or ""), re.I) for x in r)
    except Exception:
        return False


def _recusar_dialogos(page, dialogos):
    """Troca o 'aceitar tudo' do _abrir por: anota a mensagem e RECUSA (confirm) / fecha (alert)."""
    try:
        page.remove_all_listeners("dialog")
    except Exception:
        pass
    def h(d):
        dialogos.append(f"{d.type}: {d.message[:200]}")
        try:
            d.dismiss()
        except Exception:
            pass
    page.on("dialog", h)


# ----------------------------------------------------------------- passos
def _passo_menu(page, est):
    page.goto(HOME_URL, wait_until="domcontentloaded"); _esperar(page)
    itens = page.evaluate(_JS_MENU)
    for it in itens:
        m = re.search(r"ID_Modulo=(\w+)&(?:amp;)?ID_SubGrupo=(\w+)", it["href"])
        if not m:
            continue
        chave = f"{m.group(1)}/{m.group(2)}"
        est["submenus"][chave] = {"modulo": it["modulo"], "nome": it["nome"],
                                  "url": BASE + f"frmMainMenu.aspx?ID_Modulo={m.group(1)}&ID_SubGrupo={m.group(2)}&ID_Empresa=1"}
        est["fila"].append({"tipo": "submenu", "chave": chave})
    est["fase"] = "telas"
    _diario(f"menu lido: {len(est['submenus'])} submenus -> " + ", ".join(
        f"{v['modulo']}>{v['nome']}" for v in est["submenus"].values()))


def _passo_submenu(page, est, item):
    sm = est["submenus"][item["chave"]]
    page.goto(sm["url"], wait_until="domcontentloaded"); _esperar(page)
    nos = page.evaluate(_JS_ARVORE)
    sm["telas"] = nos
    novos = 0
    for n in nos:
        caminho = f"{sm['modulo']} > {sm['nome']} > " + (f"{n['pai']} > " if n["pai"] else "") + n["txt"]
        chave = f"{item['chave']}|{n['pai']}|{n['txt']}"
        if RE_TELA_BLOQUEADA.search(n["txt"]) or RE_TELA_BLOQUEADA.search(n["pai"] or ""):
            est["bloqueadas"][chave] = {"caminho": caminho, "motivo": "nome sensível (só listada)", "alvo": n["alvo"]}
            continue
        if chave in est["feitas"]:
            continue
        est["fila"].append({"tipo": "tela", "chave": chave, "submenu": item["chave"], "txt": n["txt"],
                            "pai": n["pai"], "id": n["id"], "caminho": caminho})
        novos += 1
    _diario(f"submenu {sm['modulo']} > {sm['nome']}: {len(nos)} itens na árvore, {novos} telas na fila")


def _abrir_no(page, est, item):
    sm = est["submenus"][item["submenu"]]
    page.goto(sm["url"], wait_until="domcontentloaded"); _esperar(page)
    nos = page.evaluate(_JS_ARVORE)
    alvo = next((n for n in nos if n["txt"] == item["txt"] and n["pai"] == item["pai"]), None) \
        or next((n for n in nos if n["txt"] == item["txt"]), None) \
        or next((n for n in nos if n["id"] == item["id"]), None)
    if not alvo:
        raise RuntimeError("item não está mais na árvore do menu")
    url_antes = page.url
    page.evaluate("id => document.getElementById(id).click()", alvo["id"])
    _esperar(page, 30000)
    for _ in range(10):
        if page.url != url_antes:
            break
        page.wait_for_timeout(500)
    return page.url != url_antes


def _passo_tela(page, est, item, dialogos, opts):
    caminho = item["caminho"]
    if RE_TELA_BLOQUEADA.search(caminho):          # trava pelo caminho inteiro (pai incluso)
        est["bloqueadas"][item["chave"]] = {"caminho": caminho, "motivo": "caminho sensível (só listada)"}
        _diario(f"pulei (sensível): {caminho}")
        return "bloqueada"
    mudou = _abrir_no(page, est, item)
    tela = {"caminho": caminho, "submenu": item["submenu"], "lido_em": _agora(),
            "url": (page.url or "").split("?")[0], "abriu_tela_nova": mudou}
    tela["leitura"] = _ler_tela(page)
    tela["avisos_ao_abrir"] = list(dialogos)
    if mudou and opts["campos"] and not RE_TELA_BLOQUEADA.search(caminho):
        tela["campos_entendidos"] = _entender_campos(page, tela)
    if mudou and opts["consulta"]:
        tela["consulta"] = _consultar(page, caminho, dialogos)
    tela["notas"], tela["provas"] = _pontuar(tela)
    arq = os.path.join(TELAS, _slug(caminho) + ".json")
    _gravar_json(arq, tela)
    top = sorted(((v, k) for k, v in tela["notas"].items() if v), reverse=True)[:3]
    n_campos = sum(len(f["campos"]) for f in tela["leitura"]["frames"])
    n_tab = sum(len(f["tabelas"]) for f in tela["leitura"]["frames"])
    _diario(f"tela OK: {caminho} | {tela['url'].replace(BASE, '')} | {n_campos} campos, {n_tab} tabelas"
            + (f" | consulta: {tela['consulta']['botao']}" if tela.get("consulta") else "")
            + (" | interessa p/ " + ", ".join(f"{k}({v})" for v, k in top) if top else ""))
    return os.path.basename(arq)


# ----------------------------------------------------------------- laço principal
def explorar(sessao, reabrir, sb, opts):
    os.makedirs(TELAS, exist_ok=True); os.makedirs(ERROS, exist_ok=True)
    est = _estado_ler()
    if opts.get("refazer") or not est:
        est = _estado_novo()
        _diario("=== exploração NOVA iniciada ===")
    elif est.get("fase") == "fim":
        _diario("exploração anterior já tinha terminado; recomeçando a fila (telas já lidas são relidas)")
        est = _estado_novo()
    else:
        ult = _ultimas_do_diario()
        print("  O que eu fiz por último:")
        for l in ult:
            print("    " + l)
        _diario(f"=== retomando: {len(est['fila'])} item(ns) na fila, {len(est['feitas'])} já feitos ===")
    # a tela que estava aberta quando o robô caiu conta como 1 falha
    if est.get("em_andamento"):
        k = est["em_andamento"]["chave"]
        est["falhas"][k] = est["falhas"].get(k, 0) + 1
        _diario(f"a última vez parei NO MEIO de: {est['em_andamento'].get('caminho', k)} (falha {est['falhas'][k]}/3)")
        if est["falhas"][k] < 3:
            est["fila"].insert(0, est["em_andamento"])
        else:
            est["bloqueadas"][k] = {"caminho": est["em_andamento"].get("caminho", k), "motivo": "travou 3 vezes"}
        est["em_andamento"] = None
    _estado_gravar(est)

    dialogos = []
    _recusar_dialogos(sessao["page"], dialogos)
    feitos_agora, erros_seguidos = 0, 0
    while True:
        if est["fase"] == "menu":
            _passo_menu(sessao["page"], est); _estado_gravar(est); continue
        if not est["fila"]:
            est["fase"] = "fim"; _estado_gravar(est)
            _diario("=== exploração TERMINADA ===")
            return True
        if opts.get("limite") and feitos_agora >= opts["limite"]:
            _diario(f"parei no limite de {opts['limite']} tela(s) — rode de novo para continuar")
            return "LIMITE"
        ceder = opts.get("ceder_cb") or (lambda: sb is not None and _deve_ceder(sb))
        if ceder():
            _diario("tem tarefa mais urgente (LANCE/BOLETO) na fila -> paro aqui (salvo) e cedo a vez")
            return "CEDEU"
        item = est["fila"][0]
        if opts.get("so") and item.get("chave" if item["tipo"] == "submenu" else "submenu") not in opts["so"]:
            est["fila"].pop(0); est["fila"].append(item)
            if all((i.get("chave" if i["tipo"] == "submenu" else "submenu") not in opts["so"]) for i in est["fila"]):
                _diario("nada mais na fila para os submenus pedidos (--so)")
                return True
            continue
        if item.get("chave") in est["feitas"] and item["tipo"] == "tela":
            est["fila"].pop(0); continue
        est["em_andamento"] = item; _estado_gravar(est)
        dialogos.clear()
        try:
            if item["tipo"] == "submenu":
                _passo_submenu(sessao["page"], est, item)
                est["feitas"]["submenu:" + item["chave"]] = {"em": _agora()}
            else:
                arq = _passo_tela(sessao["page"], est, item, dialogos, opts)
                est["feitas"][item["chave"]] = {"em": _agora(), "arquivo": arq}
                feitos_agora += 1
            est["fila"].pop(0); est["em_andamento"] = None; erros_seguidos = 0
        except Exception as e:
            erros_seguidos += 1
            k = item.get("chave")
            est["falhas"][k] = est["falhas"].get(k, 0) + 1
            try:
                sessao["page"].screenshot(path=os.path.join(ERROS, _slug(item.get("caminho") or k) + ".png"))
            except Exception:
                pass
            _diario(f"ERRO em {item.get('caminho') or k}: {str(e)[:140]} (falha {est['falhas'][k]}/3)")
            est["fila"].pop(0); est["em_andamento"] = None
            if est["falhas"][k] < 3:
                est["fila"].append(item)                 # tenta de novo no fim da fila
            else:
                est["bloqueadas"][k] = {"caminho": item.get("caminho", k), "motivo": f"3 erros: {str(e)[:100]}"}
            if erros_seguidos >= 2:
                _diario("2 erros seguidos -> reabrindo o navegador (novo login)")
                try:
                    reabrir(); _recusar_dialogos(sessao["page"], dialogos); erros_seguidos = 0
                except Exception as e2:
                    _estado_gravar(est)
                    _diario(f"não consegui reabrir: {str(e2)[:120]} — progresso salvo")
                    return False
        _estado_gravar(est)


# ----------------------------------------------------------------- mapa / onde achar
NOMES_ALVO = {"grupos_por_produto": "Nº dos grupos por produto", "vagas": "Quantidade de vagas",
              "creditos": "Créditos disponíveis", "taxa": "Taxa dos grupos (adm / fundo)",
              "seguro": "Seguro dos grupos", "lance": "Média de lance"}


def gerar_mapa():
    telas = []
    for f in sorted(glob.glob(os.path.join(TELAS, "*.json"))):
        try:
            telas.append(json.load(open(f, encoding="utf-8")))
        except Exception:
            pass
    est = _estado_ler() or {}
    L = [f"# Mapa do Newcon (aprendido pelo robô) — gerado {_agora()}", "",
         f"{len(telas)} telas lidas · {len(est.get('bloqueadas', {}))} só listadas/puladas · "
         f"fila restante: {len(est.get('fila', []))} · fase: {est.get('fase', '?')}", ""]
    por_sub = {}
    for t in telas:
        por_sub.setdefault(t["caminho"].split(" > ")[0] + " > " + t["caminho"].split(" > ")[1], []).append(t)
    for sub, ts in sorted(por_sub.items()):
        L.append(f"## {sub}")
        for t in sorted(ts, key=lambda x: x["caminho"]):
            fr = (t.get("leitura") or {}).get("frames") or []
            campos = [c for f in fr for c in f["campos"] if c["vis"]]
            tabs = [tb for f in fr for tb in f["tabelas"]]
            botoes = sorted({b["txt"] for f in fr for b in f["botoes"] if b["vis"] and b["txt"]})
            L.append(f"### {' > '.join(t['caminho'].split(' > ')[2:])}")
            L.append(f"- página: `{t['url'].replace(BASE, '')}`" + ("" if t.get("abriu_tela_nova") else " (não abriu tela nova)"))
            if campos:
                L.append("- campos: " + "; ".join(
                    f"{c['rotulo'] or c['id'].split('_')[-1]} ({c['tag']}" + (f", {c['n_opcoes']} opções" if c.get("n_opcoes") else "") + ")"
                    for c in campos[:25]))
            for c in campos:
                if c.get("n_opcoes") and 1 < c["n_opcoes"] <= 30:
                    L.append(f"  - opções de *{c['rotulo'] or c['id']}*: " + " | ".join(o[1] for o in c["opcoes"][:30]))
            if botoes:
                L.append("- botões: " + ", ".join(botoes[:20]))
            for tb in tabs[:4]:
                L.append(f"- tabela `{tb['id'] or '-'}` ({tb['n_linhas']} linhas): " + " | ".join(tb["cabecalho"][:14]))
            for ce in t.get("campos_entendidos") or []:
                if ce.get("liberou"):
                    L.append(f"- ao escolher **{ce['campo']}** = {ce['escolhi']} → libera: " + "; ".join(
                        f"{x['campo']} ({x['n_opcoes']} opções, ex.: {', '.join(x['exemplos'][1:4])})" for x in ce["liberou"]))
            cs = t.get("consulta")
            if cs and cs.get("frames"):
                for tb in [tb for f in cs["frames"] for tb in f["tabelas"]][:3]:
                    L.append(f"- resultado do **{cs['botao']}**: tabela ({tb['n_linhas']} linhas) " + " | ".join(tb["cabecalho"][:14]))
                    for a in tb["amostra"][:2]:
                        L.append("    - ex.: " + " | ".join(a[:14]))
            if cs and cs.get("avisos"):
                L.append(f"- aviso ao consultar: {cs['avisos'][:2]}")
            L.append("")
    if est.get("bloqueadas"):
        L.append("## Telas só listadas (sensíveis) ou puladas")
        for k, v in est["bloqueadas"].items():
            L.append(f"- {v['caminho']} — {v['motivo']}")
    _gravar_txt(os.path.join(CON, "MAPA_NEWCON.md"), "\n".join(L))

    O = [f"# Onde achar cada dado no Newcon — gerado {_agora()}", "",
         "Nota = quantas vezes o assunto aparece em coluna/campo (peso 3), nome da tela (2) e opções/título (1).",
         "Use como ponto de partida; a decisão final de qual tela o robô usa fica registrada em CONHECIMENTO.md.", ""]
    for alvo, nome in NOMES_ALVO.items():
        rank = sorted(telas, key=lambda t: -(t.get("notas") or {}).get(alvo, 0))
        rank = [t for t in rank if (t.get("notas") or {}).get(alvo, 0) > 0][:6]
        O.append(f"## {nome}")
        for t in rank:
            O.append(f"- **{t['notas'][alvo]}** · {t['caminho']} · `{t['url'].replace(BASE, '')}`")
            if t.get("provas", {}).get(alvo):
                O.append("    - " + "; ".join(t["provas"][alvo][:6]))
        if not rank:
            O.append("- (nenhuma tela ainda)")
        O.append("")
    _gravar_txt(os.path.join(CON, "ONDE_ACHAR.md"), "\n".join(O))
    print(f"  mapa: {os.path.join(CON, 'MAPA_NEWCON.md')}\n  onde achar: {os.path.join(CON, 'ONDE_ACHAR.md')}")


def _gravar_txt(caminho, txt):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    open(tmp, "w", encoding="utf-8").write(txt + "\n")
    os.replace(tmp, caminho)


# ----------------------------------------------------------------- entrada pelo robô
def main_robo(a):
    """Chamado por robo_yamaha.py --explorar / --mapa (mesmo login e sessão do robô)."""
    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a else d
    if "--mapa" in a:
        gerar_mapa(); return
    from coletar_grupos import _abrir, _conectar_sb
    opts = {"limite": int(opt("--limite")) if opt("--limite") else None,
            "so": set(x.strip().upper() for x in opt("--so").split(",")) if opt("--so") else None,
            "refazer": "--refazer" in a, "consulta": "--sem-consulta" not in a,
            "campos": "--sem-campos" not in a}
    headless = "--headless" in a
    print(">>> ROBÔ YAMAHA — EXPLORAR O NEWCON (só leitura, aprende as telas)")
    sb = _conectar_sb()
    pw, browser, ctx, page = _abrir(sb, visivel=not headless)
    sessao = {"pw": pw, "browser": browser, "ctx": ctx, "page": page}
    n = [0]

    def reabrir():
        n[0] += 1
        if n[0] > 4:
            raise RuntimeError("reabri o navegador vezes demais")
        try:
            sessao["browser"].close(); sessao["pw"].stop()
        except Exception:
            pass
        p2, b2, c2, pg2 = _abrir(sb, visivel=not headless)
        sessao.update(pw=p2, browser=b2, ctx=c2, page=pg2)
        return pg2

    ok = False
    try:
        ok = explorar(sessao, reabrir, sb, opts)
    except KeyboardInterrupt:
        _diario("interrompido (Ctrl+C) — progresso salvo")
    finally:
        try:
            sessao["browser"].close(); sessao["pw"].stop()
        except Exception:
            pass
        gerar_mapa()
    print("[OK] exploração terminada." if ok is True else
          "[!] não terminou — rode o MESMO comando para continuar de onde parou.")


# ----------------------------------------------------------------- modo manual (antigo)
def main_manual():
    """Você navega na janela; ele anota cada tela nova em explorar_newcon.txt."""
    from coletar_grupos import _abrir, _conectar_sb
    saida = os.path.join(PASTA, "explorar_newcon.txt")
    sb = _conectar_sb()
    pw, browser, ctx, page = _abrir(sb, visivel=True)
    open(saida, "w", encoding="utf-8").write(f"# Exploração manual — {_agora()}\n")
    print("Navegue na janela. Ctrl+C encerra.")
    ultimo = None
    try:
        while True:
            page.wait_for_timeout(4000)
            pg = ctx.pages[-1] if ctx.pages else page
            d = _ler_tela(pg)
            h = hashlib.md5(json.dumps(d, ensure_ascii=False).encode()).hexdigest()
            if h == ultimo:
                continue
            ultimo = h
            with open(saida, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 90}\n[{_agora()}] {pg.url}\n{json.dumps(d, ensure_ascii=False, indent=1)}\n")
            print(f"[{_agora()}] anotei {pg.url[:80]}")
    except KeyboardInterrupt:
        pass
    finally:
        try:
            browser.close(); pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    if "--manual" in sys.argv:
        main_manual()
    else:
        main_robo(sys.argv[1:] + ["--explorar"])
