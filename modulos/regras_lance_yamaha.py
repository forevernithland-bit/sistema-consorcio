# -*- coding: utf-8 -*-
"""
regras_lance_yamaha.py — REGRAS e MÉDIAS de lance de cada grupo Yamaha (16/11/2026).

Junta, por grupo, numa resposta só (usada pela tela "Ofertar Lance" e pelo
Simulador Yamaha):
  * modalidades liberadas (Livre / Fixo / 2º Fixo / Limitado / Fidelidade)
      1º o que o ROBÔ leu na tela "Oferta de Lance" do Newcon (yamaha_regras_lance)
      2º o que já apareceu nas contemplações do grupo (yamaha_contemplacoes)
      3º regra geral: Livre e Fixo sempre
  * % do lance fixo / 2º fixo, limitado e fidelidade máximos
  * % de EMBUTIDO permitido: tabela do grupo (grupos_yamaha.embutido_max_pct) >
    lido no Newcon > regra geral do produto
  * MÉDIA de lance de cada modalidade nas últimas assembleias (yamaha_contemplacoes)

Regra geral (sem tabela do grupo) — igual ao yamaha.html e ao coletar_tabelas_yamaha.py:
  Moto 15% emb / fixo 35 ou 25 · Auto 15% / 35 · Imóvel 25% / 30 · Caminhão 30% / 25
"""
import re
import unicodedata
from collections import defaultdict

import streamlit as st

MODALIDADES = ["Lance Livre", "Lance Fixo", "2º Lance Fixo", "Lance Limitado", "Lance Fidelidade"]
CURTO = {"Lance Livre": "Livre", "Lance Fixo": "Fixo", "2º Lance Fixo": "2º Fixo",
         "Lance Limitado": "Limitado", "Lance Fidelidade": "Fidelidade"}
DO_CURTO = {v: k for k, v in CURTO.items()}

REGRAS_GERAIS = {
    "MOTO":     {"embutido": 15.0, "fixo": [35.0, 25.0]},
    "AUTO":     {"embutido": 15.0, "fixo": [35.0]},
    "IMOVEL":   {"embutido": 25.0, "fixo": [30.0]},
    "CAMINHAO": {"embutido": 30.0, "fixo": [25.0]},
}
N_ASSEMBLEIAS_MEDIA = 6


def _n(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper().strip()


def produto_canonico(p):
    s = _n(p)
    if "MOTO" in s:
        return "MOTO"
    if "IMOV" in s or "IMOB" in s:
        return "IMOVEL"
    if "CAMIN" in s or "PESAD" in s:
        return "CAMINHAO"
    return "AUTO"


def modalidade_canonica(m):
    s = _n(m)
    if re.match(r"^2\s*[O]?\s*LANCE FIXO", s) or s.startswith("2") and "FIXO" in s:
        return "2º Lance Fixo"
    if "FIXO" in s:
        return "Lance Fixo"
    if "LIVRE" in s:
        return "Lance Livre"
    if "LIMIT" in s:
        return "Lance Limitado"
    if "FIDEL" in s:
        return "Lance Fidelidade"
    return None


def _f(v):
    try:
        return float(v) if v is not None and str(v).strip() != "" else None
    except Exception:
        return None


def _lista_pct(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [float(x) for x in v if _f(x)]
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(v))]


def _ler(supabase, tabela, cols="*"):
    out, ini = [], 0
    try:
        while True:
            d = supabase.table(tabela).select(cols).range(ini, ini + 999).execute().data or []
            out += d
            if len(d) < 1000:
                return out
            ini += 1000
    except Exception:
        return out


@st.cache_data(ttl=120, show_spinner=False)
def carregar_regras(_supabase):
    """{grupo: {...}} para todos os grupos conhecidos (grupos_yamaha + lidos no Newcon + contemplações)."""
    sb = _supabase
    grupos = {str(g["grupo"]).strip(): g for g in _ler(sb, "grupos_yamaha",
              "grupo,tipo_bem,embutido_max_pct,lance_fixo_pct,lance_regras_fonte,lance_medio")}
    lidos = {str(r["grupo"]).strip(): r for r in _ler(sb, "yamaha_regras_lance")}
    contem = _ler(sb, "yamaha_contemplacoes", "grupo,num_assembleia,modalidade,pct_lance,situacao,tipo_bem")

    # médias por modalidade nas últimas N assembleias do grupo
    por_grupo = defaultdict(list)
    for c in contem:
        if (c.get("situacao") or "ativo") != "ativo":
            continue
        por_grupo[str(c["grupo"]).strip()].append(c)

    todos = set(grupos) | set(lidos) | set(por_grupo)
    out = {}
    for g in todos:
        gy = grupos.get(g, {})
        rl = lidos.get(g, {})
        cs = por_grupo.get(g, [])
        prod = produto_canonico(gy.get("tipo_bem") or (cs[0].get("tipo_bem") if cs else "") or "")
        geral = REGRAS_GERAIS[prod]

        nums = sorted({int(c["num_assembleia"]) for c in cs if c.get("num_assembleia") is not None}, reverse=True)
        ult = set(nums[:N_ASSEMBLEIAS_MEDIA])
        medias = {}
        for m in MODALIDADES:
            v = [_f(c.get("pct_lance")) for c in cs
                 if modalidade_canonica(c.get("modalidade")) == m and int(c.get("num_assembleia") or 0) in ult]
            v = [x for x in v if x]
            if v:
                medias[m] = {"media": round(sum(v) / len(v), 2), "min": round(min(v), 2),
                             "max": round(max(v), 2), "n": len(v)}
        vistas = {modalidade_canonica(c.get("modalidade")) for c in cs} - {None}

        # modalidades
        mods_newcon = rl.get("modalidades") or {}
        if rl.get("formulario_aberto") and mods_newcon:
            liberadas = {m: bool(mods_newcon.get(CURTO[m])) for m in MODALIDADES}
            fonte_mod = f"Newcon (lido em {rl.get('lido_em')})"
        else:
            hist = set(rl.get("modalidades_no_historico") or [])
            liberadas = {m: (m in ("Lance Livre", "Lance Fixo") or m in vistas
                             or any(modalidade_canonica(h) == m for h in hist)) for m in MODALIDADES}
            fonte_mod = "contemplações do grupo + regra geral"

        # fixo
        fixos_tab = _lista_pct(gy.get("lance_fixo_pct"))
        fixo = _f(rl.get("lance_fixo_pct")) or (fixos_tab[0] if fixos_tab else None) or geral["fixo"][0]
        fixo2 = _f(rl.get("lance_2fixo_pct"))
        if fixo2 is None and liberadas["2º Lance Fixo"]:
            fixo2 = (medias.get("2º Lance Fixo") or {}).get("media") or (fixos_tab[1] if len(fixos_tab) > 1 else None)

        # embutido
        if _f(gy.get("embutido_max_pct")) is not None:
            emb, emb_f = _f(gy["embutido_max_pct"]), "tabela do grupo"
        elif _f(rl.get("embutido_max_pct")) is not None:
            emb, emb_f = _f(rl["embutido_max_pct"]), rl.get("embutido_fonte") or "Newcon"
        else:
            emb, emb_f = geral["embutido"], f"regra geral ({prod.lower()})"
        usado = _f(rl.get("embutido_usado_max_pct"))

        out[g] = {
            "grupo": g, "produto": prod,
            "liberadas": liberadas, "fonte_modalidades": fonte_mod,
            "fixo_pct": fixo, "fixo2_pct": fixo2,
            "lance_min_pct": _f(rl.get("lance_min_pct")), "lance_max_pct": _f(rl.get("lance_max_pct")),
            "limitado_min_pct": _f(rl.get("limitado_min_pct")), "limitado_max_pct": _f(rl.get("limitado_max_pct")),
            "fidelidade_max_pct": _f(rl.get("fidelidade_max_pct")),
            "embutido_max_pct": emb, "embutido_fonte": emb_f, "embutido_usado_max_pct": usado,
            "medias": medias, "assembleias_media": len(ult),
            "formulario_aberto": rl.get("formulario_aberto"), "lido_em": rl.get("lido_em"),
        }
    return out


def regra_do_grupo(regras, grupo, produto=None):
    """Regra do grupo; se o grupo não está em lugar nenhum, devolve a regra geral do produto."""
    g = str(grupo or "").strip()
    if g in regras:
        return regras[g]
    prod = produto_canonico(produto)
    geral = REGRAS_GERAIS[prod]
    return {"grupo": g, "produto": prod,
            "liberadas": {m: m in ("Lance Livre", "Lance Fixo") for m in MODALIDADES},
            "fonte_modalidades": "regra geral", "fixo_pct": geral["fixo"][0], "fixo2_pct": None,
            "lance_min_pct": None, "lance_max_pct": None, "limitado_min_pct": None, "limitado_max_pct": None,
            "fidelidade_max_pct": None, "embutido_max_pct": geral["embutido"],
            "embutido_fonte": f"regra geral ({prod.lower()})", "embutido_usado_max_pct": None,
            "medias": {}, "assembleias_media": 0, "formulario_aberto": None, "lido_em": None}


def pct_txt(v):
    if v is None:
        return "—"
    return (f"{v:.2f}".rstrip("0").rstrip(".") + "%").replace(".", ",")


def resumo_txt(r):
    """Uma linha curta para a tabela: 'Livre·Fixo 35·2ºFixo 25·Limitado | emb ≤15%'."""
    p = []
    for m in MODALIDADES:
        if not r["liberadas"].get(m):
            continue
        if m == "Lance Fixo":
            p.append(f"Fixo {pct_txt(r['fixo_pct'])}")
        elif m == "2º Lance Fixo":
            p.append(f"2ºFixo {pct_txt(r['fixo2_pct'])}" if r.get("fixo2_pct") else "2ºFixo")
        elif m == "Lance Limitado":
            p.append("Limitado (sem embutido)")
        else:
            p.append(CURTO[m])
    return " · ".join(p) + f" | emb até {pct_txt(r['embutido_max_pct'])}"


def medias_txt(r):
    p = []
    for m in MODALIDADES:
        x = r["medias"].get(m)
        if x:
            p.append(f"{CURTO[m]} {pct_txt(x['media'])}")
    return " · ".join(p) or "sem histórico"
