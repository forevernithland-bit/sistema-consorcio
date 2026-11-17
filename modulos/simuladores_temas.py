# -*- coding: utf-8 -*-
"""
Temas visuais da área "🧮 Simuladores" (16/11/2026).

Um tema = um conjunto de tokens (CSS custom properties `--k-*`). Todas as telas do
hub usam só esses tokens: tela inicial (hub_inicio.html), Simulador Consorbens
(universal.html), a skin dos simuladores antigos (hub_skin.css + hub_cartoes.css)
e o modo apresentação (hub_apresentacao.js).

Cada simulador é um iframe separado, então a escolha vive no Streamlit
(st.session_state["sim_tema"]) e é injetada em cada HTML como
<html data-tema="..."> + o CSS de tokens de TODOS os temas (troca instantânea).

Memória entre sessões do mesmo navegador:
  * escolha explícita → st.query_params["tema"] e localStorage("cbx_tema");
  * sessão nova sem escolha → o iframe lê o localStorage, aplica na hora e avisa o
    Streamlit pelo campo oculto "hub_tema" (mesma ponte da tela inicial).
Só aparência: nenhum cálculo, ID ou texto de negócio passa por aqui.
"""
import json

import streamlit as st

PADRAO = "aurora"
_SS = "sim_tema"              # tema escolhido (só existe depois de uma escolha explícita)
_KEY_RADIO = "sim_tema_radio"
LABEL_PONTE = "hub_tema"      # aria-label do campo oculto que o iframe preenche
KEY_PONTE = "hub_tema_raw"
_KEY_PONTE_PROC = "_hub_tema_proc"

FONTES = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800'
          '&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap" rel="stylesheet">')

_SANS = '"Plus Jakarta Sans",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif'
_SERIF = '"Fraunces",Georgia,"Times New Roman",serif'

# --------------------------------------------------------------------------- #
# Tokens
#   página ......... bg, bg-img
#   superfícies .... s1 (card), s2 (elevada), s3 (hover), field, ln, ln2
#   texto .......... tx, tx2, tx3 (todos AA sobre s1 e bg)
#   acento ......... ac (seleção/foco), ac-on (texto sobre ac), ac-tx (acento como texto), ac-soft, ac-ln
#   ação (CTA) ..... act1/act2 (gradiente), act-on (texto), act-glow
#   hero ........... hero (fundo), hero-tx, hero-tx2, hero-glass, hero-ln, hero-hl (destaque), glow1..3, dot
#   kpi destaque ... kpi (fundo), kpi-on, kpi-on2
#   painel profundo  deep (fundo dos totais/resumos), deep-tx, deep-tx2, deep-hl, deep-ok, deep-glass
#   estados ........ ok/warn/bad/info/vio (-tx, -soft, -ln)
#   foto ........... ov (rgb do véu escuro sobre fotos)
#   card do cliente  pc-hd (cabeçalho), pc-hd-tx2, pc-acc (acento sobre branco), pc-soft, pc-soft-ln,
#                    pc-liq (faixa do crédito líquido), pc-liq-on, pc-liq-on2, pc-tag, pc-ink
#   ylg ............ fundo do logo BRANCO da Yamaha (sempre escuro)
# --------------------------------------------------------------------------- #
TEMAS = {
    "aurora": {
        "nome": "Aurora", "emoji": "☀️", "claro": True,
        "desc": "Claro premium: fundo gelo, tinta azul-noite e acento índigo.",
        "tokens": {
            "font": _SANS, "font-d": _SANS,
            "bg": "#f3f5f9",
            "bg-img": "radial-gradient(1100px 520px at 100% -10%,rgba(99,102,241,.10),transparent 60%),"
                      "radial-gradient(900px 520px at -10% 110%,rgba(14,165,233,.07),transparent 60%),"
                      "linear-gradient(180deg,#f7f8fc 0%,#eef1f7 100%)",
            "s1": "#ffffff", "s2": "#ffffff", "s3": "#f2f4fb", "field": "#f7f8fc",
            "ln": "#e2e7f0", "ln2": "#c9d2e0",
            "tx": "#0f172a", "tx2": "#334155", "tx3": "#5a6578",
            "ac": "#4f46e5", "ac-on": "#ffffff", "ac-tx": "#4338ca",
            "ac-soft": "rgba(79,70,229,.08)", "ac-ln": "rgba(79,70,229,.38)",
            "act1": "#5b54f0", "act2": "#4338ca", "act-on": "#ffffff", "act-glow": "rgba(79,70,229,.45)",
            "focus": "rgba(79,70,229,.28)",
            "hero": "radial-gradient(640px 320px at 92% -10%,rgba(129,140,248,.22),transparent 65%),"
                    "radial-gradient(520px 300px at -6% 110%,rgba(56,189,248,.16),transparent 65%),"
                    "linear-gradient(135deg,#ffffff 0%,#f6f7ff 60%,#eef2ff 100%)",
            "hero-tx": "#0f172a", "hero-tx2": "#475569", "hero-glass": "rgba(255,255,255,.72)",
            "hero-ln": "rgba(15,23,42,.10)", "hero-hl": "#4f46e5",
            "glow1": "rgba(129,140,248,.30)", "glow2": "rgba(56,189,248,.22)", "glow3": "rgba(244,114,182,.14)",
            "dot": "rgba(15,23,42,.07)",
            "kpi": "linear-gradient(135deg,#4f46e5,#3730a3)", "kpi-on": "#ffffff", "kpi-on2": "#e0e7ff",
            "deep": "linear-gradient(135deg,#111827 0%,#1e2a44 100%)",
            "deep-tx": "#ffffff", "deep-tx2": "#cbd5e1", "deep-hl": "#a5b4fc", "deep-ok": "#6ee7b7",
            "deep-glass": "rgba(255,255,255,.07)",
            "ok-tx": "#047857", "ok-soft": "#ecfdf5", "ok-ln": "#a7f3d0",
            "warn-tx": "#92400e", "warn-soft": "#fffbeb", "warn-ln": "#fcd34d",
            "bad-tx": "#b91c1c", "bad-soft": "#fef2f2", "bad-ln": "#fecaca",
            "info-tx": "#075985", "info-soft": "#f0f9ff", "vio-tx": "#6d28d9", "vio-soft": "#f5f3ff",
            "ov": "15,23,42",
            "sh-sm": "0 1px 2px rgba(15,23,42,.05),0 6px 16px -10px rgba(15,23,42,.18)",
            "sh": "0 1px 2px rgba(15,23,42,.04),0 18px 40px -22px rgba(15,23,42,.28)",
            "sh-lg": "0 2px 6px rgba(15,23,42,.05),0 34px 70px -34px rgba(15,23,42,.38)",
            "pc-hd": "linear-gradient(135deg,#1e1b4b 0%,#3730a3 100%)", "pc-hd-tx2": "#c7d2fe",
            "pc-acc": "#3730a3", "pc-soft": "#eef2ff", "pc-soft-ln": "#c7d2fe",
            "pc-liq": "linear-gradient(135deg,#4f46e5 0%,#3730a3 100%)", "pc-liq-on": "#ffffff", "pc-liq-on2": "#e0e7ff",
            "pc-tag": "rgba(30,27,75,.92)", "pc-ink": "#1e1b4b",
            "ylg": "#0b2340",
        },
    },
    "noite": {
        "nome": "Noite", "emoji": "🌙", "claro": False,
        "desc": "Escuro elegante: azul-noite e grafite, acento lavanda e botões claros.",
        "tokens": {
            "font": _SANS, "font-d": _SANS,
            "bg": "#0a0f1c",
            "bg-img": "radial-gradient(1100px 520px at 100% -10%,rgba(99,102,241,.16),transparent 60%),"
                      "radial-gradient(900px 520px at -10% 110%,rgba(56,189,248,.07),transparent 60%),"
                      "linear-gradient(180deg,#0a0f1c 0%,#0d1324 100%)",
            "s1": "#10172a", "s2": "#141c33", "s3": "#1a2440", "field": "#0c1222",
            "ln": "#232d47", "ln2": "#323e5e",
            "tx": "#e8ecf6", "tx2": "#bcc5d8", "tx3": "#94a0b8",
            "ac": "#8b9aff", "ac-on": "#0a0f1c", "ac-tx": "#a5b1ff",
            "ac-soft": "rgba(139,154,255,.12)", "ac-ln": "rgba(139,154,255,.45)",
            "act1": "#ffffff", "act2": "#dde3f1", "act-on": "#0a0f1c", "act-glow": "rgba(165,177,255,.35)",
            "focus": "rgba(139,154,255,.35)",
            "hero": "radial-gradient(640px 320px at 92% -10%,rgba(99,102,241,.30),transparent 65%),"
                    "radial-gradient(520px 300px at -6% 110%,rgba(56,189,248,.12),transparent 65%),"
                    "linear-gradient(140deg,#111a33 0%,#141f3d 55%,#1a2550 100%)",
            "hero-tx": "#ffffff", "hero-tx2": "#c3cbe0", "hero-glass": "rgba(255,255,255,.07)",
            "hero-ln": "rgba(255,255,255,.14)", "hero-hl": "#b4bfff",
            "glow1": "rgba(99,102,241,.38)", "glow2": "rgba(56,189,248,.18)", "glow3": "rgba(167,139,250,.16)",
            "dot": "rgba(255,255,255,.08)",
            "kpi": "linear-gradient(135deg,#a5b1ff,#7f8ef9)", "kpi-on": "#0a0f1c", "kpi-on2": "#1e2753",
            "deep": "linear-gradient(135deg,#0c1222 0%,#18213d 100%)",
            "deep-tx": "#ffffff", "deep-tx2": "#bcc5d8", "deep-hl": "#b4bfff", "deep-ok": "#6ee7b7",
            "deep-glass": "rgba(255,255,255,.06)",
            "ok-tx": "#6ee7b7", "ok-soft": "rgba(16,185,129,.14)", "ok-ln": "rgba(16,185,129,.35)",
            "warn-tx": "#fcd34d", "warn-soft": "rgba(251,191,36,.10)", "warn-ln": "rgba(251,191,36,.35)",
            "bad-tx": "#fca5a5", "bad-soft": "rgba(248,113,113,.12)", "bad-ln": "rgba(248,113,113,.35)",
            "info-tx": "#7dd3fc", "info-soft": "rgba(56,189,248,.12)", "vio-tx": "#c4b5fd", "vio-soft": "rgba(167,139,250,.14)",
            "ov": "10,15,28",
            "sh-sm": "0 8px 20px -12px rgba(0,0,0,.6)",
            "sh": "0 24px 50px -28px rgba(0,0,0,.85)",
            "sh-lg": "0 34px 70px -34px rgba(0,0,0,.95)",
            "pc-hd": "linear-gradient(135deg,#0f172a 0%,#1e2a52 100%)", "pc-hd-tx2": "#c7d2fe",
            "pc-acc": "#3341b8", "pc-soft": "#eef0ff", "pc-soft-ln": "#cfd5ff",
            "pc-liq": "linear-gradient(135deg,#1e2a52 0%,#0f172a 100%)", "pc-liq-on": "#ffffff", "pc-liq-on2": "#c7d2fe",
            "pc-tag": "rgba(15,23,42,.9)", "pc-ink": "#0f172a",
            "ylg": "#0b2340",
        },
    },
    "ametista": {
        "nome": "Ametista", "emoji": "💜", "claro": False,
        "desc": "Com personalidade: ameixa profunda, títulos com serifa e dourado champanhe.",
        "tokens": {
            "font": _SANS, "font-d": _SERIF,
            "bg": "#140c1d",
            "bg-img": "radial-gradient(1100px 520px at 100% -10%,rgba(168,85,247,.20),transparent 60%),"
                      "radial-gradient(900px 520px at -10% 110%,rgba(245,196,81,.08),transparent 60%),"
                      "linear-gradient(180deg,#140c1d 0%,#180f23 100%)",
            "s1": "#1c1228", "s2": "#221631", "s3": "#2b1d3d", "field": "#170e21",
            "ln": "#36254b", "ln2": "#4a3364",
            "tx": "#f5effb", "tx2": "#d8cce7", "tx3": "#ad9dc3",
            "ac": "#c79bff", "ac-on": "#1c0f2c", "ac-tx": "#d7b8ff",
            "ac-soft": "rgba(199,155,255,.12)", "ac-ln": "rgba(199,155,255,.45)",
            "act1": "#f8d98a", "act2": "#e9b949", "act-on": "#2a1a00", "act-glow": "rgba(233,185,73,.45)",
            "focus": "rgba(233,185,73,.35)",
            "hero": "radial-gradient(640px 320px at 92% -10%,rgba(192,132,252,.34),transparent 65%),"
                    "radial-gradient(520px 300px at -6% 110%,rgba(245,196,81,.16),transparent 65%),"
                    "linear-gradient(140deg,#24123a 0%,#33175a 55%,#431c6e 100%)",
            "hero-tx": "#ffffff", "hero-tx2": "#e3d6f3", "hero-glass": "rgba(255,255,255,.08)",
            "hero-ln": "rgba(255,255,255,.16)", "hero-hl": "#f5c451",
            "glow1": "rgba(192,132,252,.40)", "glow2": "rgba(245,196,81,.24)", "glow3": "rgba(244,114,182,.16)",
            "dot": "rgba(255,255,255,.08)",
            "kpi": "linear-gradient(135deg,#f8d98a,#e9b949)", "kpi-on": "#2a1a00", "kpi-on2": "#5a3d05",
            "deep": "linear-gradient(135deg,#1a1027 0%,#2d1b45 100%)",
            "deep-tx": "#ffffff", "deep-tx2": "#d8cce7", "deep-hl": "#f5c451", "deep-ok": "#86efac",
            "deep-glass": "rgba(255,255,255,.06)",
            "ok-tx": "#86efac", "ok-soft": "rgba(34,197,94,.13)", "ok-ln": "rgba(34,197,94,.35)",
            "warn-tx": "#fcd34d", "warn-soft": "rgba(251,191,36,.10)", "warn-ln": "rgba(251,191,36,.35)",
            "bad-tx": "#fca5a5", "bad-soft": "rgba(248,113,113,.12)", "bad-ln": "rgba(248,113,113,.35)",
            "info-tx": "#93c5fd", "info-soft": "rgba(96,165,250,.12)", "vio-tx": "#d8b4fe", "vio-soft": "rgba(192,132,252,.14)",
            "ov": "20,12,29",
            "sh-sm": "0 8px 20px -12px rgba(0,0,0,.6)",
            "sh": "0 24px 50px -28px rgba(0,0,0,.85)",
            "sh-lg": "0 34px 70px -34px rgba(0,0,0,.95)",
            "pc-hd": "linear-gradient(135deg,#2e1065 0%,#5b21b6 100%)", "pc-hd-tx2": "#e9d5ff",
            "pc-acc": "#5b21b6", "pc-soft": "#f5f3ff", "pc-soft-ln": "#ddd6fe",
            "pc-liq": "linear-gradient(135deg,#f6d27a 0%,#e4ad35 100%)", "pc-liq-on": "#2a1a00", "pc-liq-on2": "#4a3105",
            "pc-tag": "rgba(46,16,101,.92)", "pc-ink": "#2e1065",
            "ylg": "#0b2340",
        },
    },
    "classico": {
        "nome": "Clássico", "emoji": "🌿", "claro": False,
        "desc": "O visual anterior: teal escuro com laranja nas ações.",
        "tokens": {
            "font": _SANS, "font-d": _SANS,
            "bg": "#071d1a",
            "bg-img": "radial-gradient(1100px 520px at 100% -10%,rgba(45,212,191,.10),transparent 60%),"
                      "radial-gradient(900px 520px at -10% 110%,rgba(246,147,2,.06),transparent 60%),"
                      "linear-gradient(180deg,#061a17 0%,#0a231f 100%)",
            "s1": "#0c2824", "s2": "#10302b", "s3": "#153a34", "field": "#081f1c",
            "ln": "#1f4a43", "ln2": "#2a5d55",
            "tx": "#eaf6f3", "tx2": "#cfe3df", "tx3": "#97b8b2",
            "ac": "#2dd4bf", "ac-on": "#062a24", "ac-tx": "#5eead4",
            "ac-soft": "rgba(45,212,191,.10)", "ac-ln": "rgba(45,212,191,.45)",
            "act1": "#ffb649", "act2": "#f69302", "act-on": "#2b1700", "act-glow": "rgba(246,147,2,.85)",
            "focus": "rgba(45,212,191,.22)",
            "hero": "radial-gradient(640px 320px at 92% -10%,rgba(45,212,191,.30),transparent 65%),"
                    "radial-gradient(520px 300px at -6% 110%,rgba(246,147,2,.20),transparent 65%),"
                    "linear-gradient(140deg,#0b2d28 0%,#123f3e 55%,#17544b 100%)",
            "hero-tx": "#ffffff", "hero-tx2": "#cfe6de", "hero-glass": "rgba(255,255,255,.08)",
            "hero-ln": "rgba(255,255,255,.18)", "hero-hl": "#ffb649",
            "glow1": "rgba(45,212,191,.40)", "glow2": "rgba(246,147,2,.26)", "glow3": "rgba(127,233,180,.18)",
            "dot": "rgba(255,255,255,.10)",
            "kpi": "linear-gradient(135deg,#ffaa2b,#f69302)", "kpi-on": "#2b1700", "kpi-on2": "#5b3600",
            "deep": "linear-gradient(135deg,#123f3e 0%,#1c5e5b 100%)",
            "deep-tx": "#ffffff", "deep-tx2": "#c4e3e3", "deep-hl": "#ffcb7a", "deep-ok": "#6ee7b7",
            "deep-glass": "rgba(255,255,255,.07)",
            "ok-tx": "#86efac", "ok-soft": "rgba(74,222,128,.14)", "ok-ln": "rgba(74,222,128,.35)",
            "warn-tx": "#fde3b5", "warn-soft": "rgba(246,147,2,.10)", "warn-ln": "rgba(246,147,2,.40)",
            "bad-tx": "#fca5a5", "bad-soft": "rgba(239,68,68,.14)", "bad-ln": "rgba(239,68,68,.35)",
            "info-tx": "#99f6e4", "info-soft": "rgba(45,212,191,.10)", "vio-tx": "#c4b5fd", "vio-soft": "rgba(167,139,250,.14)",
            "ov": "7,26,23",
            "sh-sm": "0 8px 20px -12px rgba(0,0,0,.6)",
            "sh": "0 24px 50px -28px rgba(0,0,0,.85)",
            "sh-lg": "0 30px 60px -34px rgba(0,0,0,.9)",
            "pc-hd": "linear-gradient(135deg,#0f3735 0%,#1b5e59 100%)", "pc-hd-tx2": "#bfe0da",
            "pc-acc": "#17544b", "pc-soft": "#eef6f4", "pc-soft-ln": "#bfdcd5",
            "pc-liq": "linear-gradient(135deg,#0b7e54 0%,#0a6b47 100%)", "pc-liq-on": "#ffffff", "pc-liq-on2": "#ffffff",
            "pc-tag": "rgba(15,55,53,.92)", "pc-ink": "#0f3735",
            "ylg": "#0b2340",
        },
    },
}
ORDEM = ["aurora", "noite", "ametista", "classico"]


# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #
def _bloco(tokens):
    return ";".join(f"--k-{k}:{v}" for k, v in tokens.items())


def _css_tokens():
    partes = [f':root,html:not([data-tema]){{{_bloco(TEMAS[PADRAO]["tokens"])}}}']
    for tid in ORDEM:
        partes.append(f'html[data-tema="{tid}"]{{{_bloco(TEMAS[tid]["tokens"])};'
                      f'color-scheme:{"light" if TEMAS[tid]["claro"] else "dark"}}}')
    return "\n".join(partes)


CSS_TOKENS = _css_tokens()


def valido(t):
    return t if t in TEMAS else None


# --------------------------------------------------------------------------- #
# Estado (Streamlit)
# --------------------------------------------------------------------------- #
def _qp_tema():
    try:
        return valido((st.query_params.get("tema") or "").lower())
    except Exception:
        return None


def tema_atual():
    """(tema, origem). origem = 'escolha' (o usuário escolheu: sessão ou URL) ou 'padrao'."""
    t = valido(st.session_state.get(_SS))
    if t:
        return t, "escolha"
    t = _qp_tema()
    if t:
        st.session_state[_SS] = t
        return t, "escolha"
    return PADRAO, "padrao"


def _definir(t):
    t = valido(t)
    if not t:
        return
    st.session_state[_SS] = t
    try:
        if st.query_params.get("tema") != t:
            st.query_params["tema"] = t
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Injeção nos iframes
# --------------------------------------------------------------------------- #
_JS = """<script data-cbx-tema-js>(function(){
var R=document.documentElement,V=%s,t=R.getAttribute("data-tema"),o=R.getAttribute("data-tema-origem"),ls=null;
try{ls=window.localStorage;}catch(e){}
function avisa(s){try{var P=window.parent,d=P&&P.document;if(!d||P===window)return;
 var i=d.querySelector('input[aria-label="%s"]');if(!i)return;
 var set=Object.getOwnPropertyDescriptor(P.HTMLInputElement.prototype,"value").set;
 set.call(i,s+"|"+Date.now());i.dispatchEvent(new P.Event("input",{bubbles:true}));
 i.dispatchEvent(new P.KeyboardEvent("keydown",{key:"Enter",code:"Enter",keyCode:13,which:13,bubbles:true}));}catch(e){}}
if(o==="escolha"){try{ls&&ls.setItem("cbx_tema",t);}catch(e){}}
else{var s=null;try{s=ls&&ls.getItem("cbx_tema");}catch(e){}
 if(s&&V.indexOf(s)>=0&&s!==t){R.setAttribute("data-tema",s);setTimeout(function(){avisa(s);},60);}}
})();</script>""" % (json.dumps(ORDEM), LABEL_PONTE)


def head_tema():
    """Fontes + tokens de todos os temas + script de memória (vai no <head> ou no início do extra)."""
    return FONTES + '<style data-cbx-tokens="1">' + CSS_TOKENS + "</style>" + _JS


def atributos(tema, origem):
    return f' data-tema="{tema}" data-tema-origem="{origem}"'


def aplicar_html(html, tema=None, origem=None):
    """Põe data-tema no <html ...> e os tokens logo após o <head>. Não toca no resto."""
    if tema is None:
        tema, origem = tema_atual()
    attrs = atributos(tema, origem or "padrao")
    i = html.find("<html")
    if i >= 0:
        j = html.find(">", i)
        html = html[:j] + attrs + html[j:]
    k = html.find("<head>")
    if k >= 0:
        k += len("<head>")
        return html[:k] + head_tema() + html[k:]
    return head_tema() + html


def js_aplicar(tema, origem):
    """Para os simuladores antigos (só recebem um trecho antes do </body>)."""
    return ('<script>(function(){var R=document.documentElement;R.setAttribute("data-tema",%s);'
            'R.setAttribute("data-tema-origem",%s);})();</script>' % (json.dumps(tema), json.dumps(origem)))


# --------------------------------------------------------------------------- #
# Página do Streamlit (fundo + barra do hub + seletor)
# --------------------------------------------------------------------------- #
def css_pagina(tema):
    tk = TEMAS[valido(tema) or PADRAO]["tokens"]
    return ("<style>.stApp{" + _bloco(tk) + "}"
            ".stApp{background:var(--k-bg-img),var(--k-bg) !important;background-color:var(--k-bg) !important;"
            "background-attachment:fixed !important}"
            '[data-testid="stHeader"]{background:transparent !important}'
            ".stApp iframe{background:transparent !important;color-scheme:normal}"
            "</style>")


FUNDO_PAGINA = css_pagina(PADRAO)

CSS_BARRA = """<style>
.hub-ou{font-size:12.5px;color:var(--k-tx3);margin:2px 0 4px}
[class*="st-key-hubsel_"] button{min-height:0 !important;padding:4px 12px !important;border-radius:999px !important;
  background:var(--k-s1) !important;border:1px solid var(--k-ln) !important;color:var(--k-tx2) !important;box-shadow:none !important}
[class*="st-key-hubsel_"] button:hover{border-color:var(--k-ac) !important;color:var(--k-tx) !important}
[class*="st-key-hubsel_"] button p{font-size:13px !important;color:inherit !important}
.st-key-hub_escolha_raw,.st-key-hub_tema_raw{position:absolute !important;left:-9999px !important;width:1px !important;height:1px !important;
  overflow:hidden !important;opacity:0 !important}
.st-key-hub_seg [data-testid="stWidgetLabel"]{display:none}
.st-key-hub_seg [role="radiogroup"]{gap:4px;padding:5px;border-radius:999px;background:var(--k-s1);border:1px solid var(--k-ln);
  width:max-content;max-width:100%;flex-wrap:wrap;box-shadow:var(--k-sh-sm)}
.st-key-hub_seg button{border:0 !important;border-radius:999px !important;background:transparent !important;color:var(--k-tx2) !important;
  min-height:0 !important;padding:7px 16px !important;box-shadow:none !important;transition:background .2s,color .2s}
.st-key-hub_seg button p{font-size:14px !important;font-weight:700 !important;color:inherit !important}
.st-key-hub_seg button:hover{background:var(--k-s3) !important;color:var(--k-tx) !important}
.st-key-hub_seg button[aria-checked="true"]{background:linear-gradient(135deg,var(--k-act1),var(--k-act2)) !important;color:var(--k-act-on) !important;
  box-shadow:0 10px 22px -12px var(--k-act-glow) !important}
.st-key-hub_seg button:focus-visible{outline:2px solid var(--k-ac) !important;outline-offset:2px}
[data-testid="stColumn"]:has(.st-key-hub_trocar) [data-testid="stVerticalBlock"],
[data-testid="stColumn"]:has(.st-key-hub_tema) [data-testid="stVerticalBlock"]{align-items:flex-end}
.st-key-hub_trocar button,.st-key-hub_tema button{min-height:0 !important;padding:8px 16px !important;border-radius:999px !important;
  background:var(--k-s1) !important;border:1px solid var(--k-ln2) !important;color:var(--k-tx2) !important;width:auto !important;box-shadow:none !important}
.st-key-hub_trocar button:hover,.st-key-hub_tema button:hover{border-color:var(--k-ac) !important;color:var(--k-tx) !important;background:var(--k-s3) !important}
.st-key-hub_trocar button p,.st-key-hub_tema button p{font-size:13.5px !important;font-weight:700 !important;color:inherit !important}
.st-key-hub_tema button svg{color:inherit !important}
@media (max-width:640px){
  [data-testid="stHorizontalBlock"]:has(.st-key-hub_tema){flex-wrap:wrap !important;gap:8px !important}
}
</style>"""


def processar_ponte():
    """Campo oculto que o iframe preenche com o tema salvo no navegador (sessão nova)."""
    raw = st.text_input(LABEL_PONTE, key=KEY_PONTE, label_visibility="collapsed")
    if raw and raw != st.session_state.get(_KEY_PONTE_PROC):
        st.session_state[_KEY_PONTE_PROC] = raw
        t = valido(raw.split("|", 1)[0].strip())
        if t and st.session_state.get(_SS) != t:
            _definir(t)
            st.session_state.pop(_KEY_RADIO, None)
            st.rerun()


def _ao_trocar():
    _definir(st.session_state.get(_KEY_RADIO))


def render_seletor():
    """Botão discreto "🎨 Tema" com as opções (vale para todos os simuladores)."""
    tema, _ = tema_atual()
    if st.session_state.get(_KEY_RADIO) not in TEMAS:
        st.session_state.pop(_KEY_RADIO, None)
    cfg = TEMAS[tema]
    with st.popover(f"🎨 {cfg['nome']}", key="hub_tema", help="Tema dos simuladores"):
        st.radio("Tema dos simuladores", ORDEM, index=ORDEM.index(tema), key=_KEY_RADIO, on_change=_ao_trocar,
                 format_func=lambda t: f"{TEMAS[t]['emoji']} {TEMAS[t]['nome']}" + ("  · padrão" if t == PADRAO else ""),
                 captions=[TEMAS[t]["desc"] for t in ORDEM])
        st.caption("A escolha vale para a tela inicial, os quatro simuladores e o modo apresentação, "
                   "e fica salva neste navegador.")
