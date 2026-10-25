"""Simulador de comissionamento v2: componente HTML/CSS/JS autossuficiente (tudo calculado no navegador,
sem rerun do Streamlit a cada movimento), no padrão visual da apresentação da Maggi.

`render_simulador_v2(df_admin, cfg, master=False)`:
  - vendedor: comissão estimada, prêmios de superação, próximos 4 meses e linha do tempo. O HTML do vendedor NÃO
    leva nada do lado da corretora: os blocos marcados <!--M-->…<!--/M--> e /*M*/…/*/M*/ são removidos e os dados
    (regras da administradora, imposto, divisão dos sócios, modo de desconto) nem são enviados.
  - master: + tipo de simulação (vendedor / Consorbens / sócios), administradora/produto/tipo de parcela, cascata da
    corretora e tabela mês a mês.

A matemática em JS (window.CB.simular / CB.simularCorretora) replica comissao_vendedor.simular / simular_corretora
(validada contra o Python em centenas de casos). O antigo modulos/simulador_comissao_ui.py fica como reserva.
"""
import base64
import functools
import json
import os
import re
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

import comissao_vendedor as cv
from utils import parse_float_safe

_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE = os.path.join(_DIR, "simulador_comissao_v2.html")
_IMG_DIR = os.path.join(os.path.dirname(_DIR), "assets", "simulador")
_CENAS = ("casa", "imoveis", "auto", "pesados")


@functools.lru_cache(maxsize=1)
def _template():
    with open(_TEMPLATE, encoding="utf-8") as f:
        return f.read()


@functools.lru_cache(maxsize=8)
def _data_uri(nome):
    """Imagem do simulador em base64 (lida do disco uma vez por processo)."""
    for ext, mime in (("jpg", "image/jpeg"), ("png", "image/png")):
        caminho = os.path.join(_IMG_DIR, f"{nome}.{ext}")
        if os.path.exists(caminho):
            with open(caminho, "rb") as f:
                return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")
    return ""


def _so_vendedor(html):
    """Tira do HTML/JS tudo o que é exclusivo da gestão (lado da corretora)."""
    html = re.sub(r"<!--M-->.*?<!--/M-->", "", html, flags=re.S)
    return re.sub(r"/\*M\*/.*?/\*/M\*/", "", html, flags=re.S)


def _regras_admin(df_admin):
    """Linhas da tabela de comissão das administradoras -> [{a, p, t, pc: {parcela: %}}] + listas ordenadas."""
    regras, adms, prods, tipos = [], [], {}, {}
    if df_admin is None or getattr(df_admin, "empty", True):
        return regras, adms, prods, tipos
    for _, row in df_admin.iterrows():
        a = str(row.get("Administradora", "") or "").strip()
        p = str(row.get("Produto", "") or "").strip()
        if not a or a.lower() == "nan" or not p or p.lower() == "nan":
            continue
        t = row.get("Tipo_Parcela", "")
        t = "" if t is None or (isinstance(t, float) and t != t) else str(t)
        pc = {}
        for i in range(1, 26):
            v = parse_float_safe(row.get(f"P{i}", 0))
            if v > 0:
                pc[i] = v
        regras.append({"a": a, "p": p, "t": t, "pc": pc})
    adms = sorted({r["a"] for r in regras})
    for a in adms:
        prods[a] = sorted({r["p"] for r in regras if r["a"] == a})
        for p in prods[a]:
            tipos[f"{a}|{p}"] = sorted({r["t"] for r in regras if r["a"] == a and r["p"] == p})
    return regras, adms, prods, tipos


def dados_simulador(df_admin, cfg, master=False, hoje=None):
    """Dados enviados ao componente. O vendedor recebe só a regra de comissão do vendedor."""
    r = cv.regra(cfg)
    hoje = hoje or datetime.today()
    d = {
        "master": bool(master),
        "hoje": f"{hoje.year:04d}-{hoje.month:02d}",
        "regra": {k: float(r[k]) for k in ("VD_P1", "VD_P2", "VD_M1", "VD_M1_P3", "VD_M2", "VD_M2_P4", "VD_EST_PCT")},
        "imgs": {k: _data_uri(k) for k in _CENAS},
    }
    d["regra"]["VD_EST_MESES"] = int(r["VD_EST_MESES"])
    if master:
        regras, adms, prods, tipos = _regras_admin(df_admin)
        padrao = next((a for a in adms if "YAMAHA" in cv.norm(a)), adms[0] if adms else None)
        d.update({
            "imposto": parse_float_safe((cfg or {}).get("Imposto", 7.16)),
            "desconto": cv.desconta_dos_socios(cfg),
            "div": {"cons": list(cv.divisao_socios(cfg, "consorbens")),
                    "socios": list(cv.divisao_socios(cfg, "socios", "BRENO"))},
            "regras": regras, "adms": adms, "prods": prods, "tipos": tipos, "admPadrao": padrao,
        })
    return d


def montar_html(df_admin, cfg, master=False, hoje=None):
    dados = dados_simulador(df_admin, cfg, master, hoje)
    js = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    html = _template() if master else _so_vendedor(_template())
    return html.replace("__DADOS__", js).replace("__LOGO__", _data_uri("logo"))


_CSS_PAGINA = """
<style>
.st-key-sim_v2 iframe{display:block;width:100%;border:0;}
@media (max-width:640px){ .st-key-sim_v2{margin-left:-19px;margin-right:-19px;width:calc(100% + 38px)!important;max-width:none!important;} }
</style>
"""


def render_simulador_v2(df_admin, cfg, master=False):
    html = montar_html(df_admin, cfg, master)
    with st.container(key="sim_v2"):
        st.markdown(_CSS_PAGINA, unsafe_allow_html=True)
        # altura inicial aproximada; o próprio componente ajusta a altura do iframe ao conteúdo
        components.html(html, height=4200 if master else 2900, scrolling=False)
