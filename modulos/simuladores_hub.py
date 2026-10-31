# -*- coding: utf-8 -*-
"""
Simuladores Consorbens — tela única (hub).

Junta num lugar só os simuladores das administradoras (Yamaha, Itaú por IA e
Itaú manual; outras entram em OPCOES quando existirem). O usuário escolhe a
administradora e o hub:
  1) mostra o painel de grupos daquela administradora (KPIs, "menores lances
     com vaga" e a Guia de grupos) — só leitura, a partir dos MESMOS dados que
     os simuladores já usam (tabelas do robô Yamaha / Guia de Oportunidades Itaú);
  2) renderiza o simulador original, sem tocar na conta — só injeta a camada
     de "Apresentar ao cliente" (assets/simulador/hub_apresentacao.js).

Os robôs (coleta Yamaha, download da Guia Itaú) não são afetados: este módulo
só lê o que eles gravam.
"""
import os
import json
import datetime
import statistics

import streamlit as st
import streamlit.components.v1 as components

HUB_MENU = "🧮 Simuladores"

# id, permissão (seguranca.PERMISSOES), rótulo, ícone, descrição
OPCOES = [
    {"id": "yamaha", "perm": "sim_yamaha", "titulo": "Yamaha", "ico": "🏍️",
     "sub": "Motos, autos, imóveis e pesados · dados do robô Newcon"},
    {"id": "itau_ia", "perm": "sim_itau_v2", "titulo": "Itaú · IA", "ico": "🚀",
     "sub": "A IA monta a proposta direto da Guia de Oportunidades"},
    {"id": "itau_manual", "perm": "sim_itau", "titulo": "Itaú · Manual", "ico": "🏦",
     "sub": "Você digita os dados do grupo e do lance"},
]
EM_BREVE = ["Porto Seguro", "Embracon", "Bradesco"]
PERMS_HUB = {o["perm"] for o in OPCOES}

_ASSETS = os.path.join("assets", "simulador")


def tem_acesso(perms, is_master):
    return is_master or bool(PERMS_HUB & set(perms or ()))


@st.cache_data
def _ler(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ #
# Normalização dos grupos (mesmo formato p/ qualquer administradora)
# ------------------------------------------------------------------ #
def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _data_br(v):
    """'2026-11-05' / date / '05/11/2026' -> '05/11/2026' (ou '')."""
    if not v:
        return ""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.strftime("%d/%m/%Y")
    s = str(v).strip()[:10]
    try:
        return datetime.date.fromisoformat(s).strftime("%d/%m/%Y")
    except ValueError:
        return s


def _grupos_yamaha(base):
    resumo = {str(r.get("grupo")): r for r in base.get("resumo") or []}
    agg = {}
    for r in base.get("grupos") or []:
        k = (str(r.get("grupo")), r.get("tipo_bem") or "")
        a = agg.setdefault(k, {"creds": [], "vagas": None, "prazo": None, "assemb": "", "lm": None})
        c = _f(r.get("credito"))
        if c:
            a["creds"].append(c)
        v = r.get("vagas")
        if v is not None:
            a["vagas"] = max(a["vagas"] or 0, int(v))
        a["prazo"] = a["prazo"] or r.get("prazo_restante")
        a["assemb"] = a["assemb"] or (r.get("prox_assembleia") or "")
        a["lm"] = a["lm"] or _f(r.get("lance_medio"))
    linhas = []
    for (g, tipo), a in agg.items():
        rs = resumo.get(g) or {}
        media = _f(rs.get("lance_livre_medio_periodo")) or a["lm"]
        linhas.append({
            "g": g, "tipo": tipo, "vagas": a["vagas"], "prazo": a["prazo"],
            "cmin": min(a["creds"]) if a["creds"] else None,
            "cmax": max(a["creds"]) if a["creds"] else None,
            "media": media, "menor": _f(rs.get("lance_livre_min_periodo")),
            "maior": _f(rs.get("lance_livre_max_periodo")),
            "cont": rs.get("contempl_lance_livre"), "assemb": _data_br(a["assemb"]),
            "obs": (f"{rs.get('assembleias_analisadas')} assembleias analisadas"
                    if rs.get("assembleias_analisadas") else ""),
        })
    att = (base.get("atualizacao") or {}).get("geral") or ""
    return linhas, {"adm": "Yamaha", "fonte": "Robô Newcon (grupos e assembleias)",
                    "atualizado": _data_br(att)}


def _grupos_itau(dados):
    linhas = []
    for g in dados.get("grupos") or []:
        # a Guia traz o lance em fração (0,65 = 65%); o painel trabalha em %
        ls = [x * 100 for x in (g.get("lances") or []) if x and x > 0]
        vals = g.get("valores") or []
        linhas.append({
            "g": str(g.get("grupo")), "tipo": g.get("aba") or "", "vagas": g.get("vagas"),
            "prazo": g.get("prazo"), "cmin": min(vals) if vals else None, "cmax": max(vals) if vals else None,
            # mesma média do simulador Itaú V2 (lMed = média dos lances > 0 da Guia)
            "media": statistics.mean(ls) if ls else None,
            "menor": min(ls) if ls else None, "maior": max(ls) if ls else None,
            "cont": g.get("contLivre"), "assemb": g.get("assembleia") or "",
            "obs": ("Lance fixo %s%%" % str(g.get("fixoPct")).replace(".", ",") if g.get("fixoOk") else "")
                   + (" · parcela reduzida" if g.get("red") else ""),
        })
    m = dados.get("meta") or {}
    return linhas, {"adm": "Itaú", "fonte": m.get("fonte") or "Guia de Oportunidades",
                    "atualizado": m.get("baixado_em") or ""}


def _dados_painel(opc, supabase):
    """Linhas normalizadas do painel. Nunca derruba a tela: erro vira aviso."""
    try:
        if opc == "yamaha":
            from modulos.yamaha_sim import carregar_base_yamaha
            return _grupos_yamaha(carregar_base_yamaha(supabase))
        from modulos.itau_v2 import _carregar_dados_itau
        dados, _log = _carregar_dados_itau()
        return _grupos_itau(dados)
    except Exception as e:  # noqa: BLE001 — painel é complemento, o simulador segue
        adm = "Yamaha" if opc == "yamaha" else "Itaú"
        return [], {"adm": adm, "fonte": "", "atualizado": "", "erro": str(e)[:300]}


# ------------------------------------------------------------------ #
# Camada de apresentação injetada no simulador original
# ------------------------------------------------------------------ #
def _camada(pasta, opc, linhas, meta):
    from modulos.yamaha_sim import _logo_data_uri
    ctx = {
        "sim": opc, "adm": meta.get("adm"), "logo": _logo_data_uri(pasta),
        "contato": "(31) 99894-2219 · consorbensmg.com.br",
        "grupos": {l["g"]: l for l in linhas},
    }
    js = _ler(os.path.join(pasta, _ASSETS, "hub_apresentacao.js"))
    return ("<script>window.CBX_CTX=" + json.dumps(ctx, ensure_ascii=False, default=str)
            + ";</script><script>" + js + "</script>")


def _painel(pasta, linhas, meta):
    html = _ler(os.path.join(pasta, _ASSETS, "hub_painel.html"))
    payload = json.dumps({"linhas": linhas, "meta": meta}, ensure_ascii=False, default=str)
    components.html(html.replace('"__HUB_DADOS__"', payload, 1), height=640, scrolling=False)


# ------------------------------------------------------------------ #
# Tela
# ------------------------------------------------------------------ #
_CSS = """<style>
.hub-hero{position:relative;overflow:hidden;border-radius:22px;padding:30px 34px;margin:4px 0 18px;
  background:radial-gradient(600px 260px at 92% -20%,rgba(45,212,191,.35),transparent 60%),
  radial-gradient(500px 240px at 0% 120%,rgba(246,147,2,.18),transparent 60%),linear-gradient(135deg,#0b2d28,#123f3e 55%,#17544b);
  color:#fff;box-shadow:0 30px 60px -30px rgba(0,0,0,.6)}
.hub-hero small{display:block;font-size:12px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:#7fe9b4}
.hub-hero h1{font-size:34px;line-height:1.1;margin:8px 0 6px;font-weight:900;letter-spacing:-.02em;color:#fff;padding:0}
.hub-hero h1 em{font-style:normal;color:#ffb649}
.hub-hero p{margin:0;color:#cfe6de;font-size:15px}
.hub-soon{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.hub-soon span{font-size:12px;font-weight:700;color:#94a3b8;border:1px dashed #475569;border-radius:999px;padding:5px 12px}
[class*="st-key-hubsel_"] button{min-height:118px;border-radius:18px !important;text-align:left !important;
  background:linear-gradient(160deg,#16253f,#0f1b30) !important;border:1px solid #2a3a57 !important;color:#e2e8f0 !important;
  transition:transform .2s,border-color .2s,box-shadow .2s;white-space:pre-line}
[class*="st-key-hubsel_"] button > div{align-self:flex-start;width:100%}
[class*="st-key-hubsel_"] button:hover{transform:translateY(-3px);border-color:#2dd4bf !important;box-shadow:0 18px 40px -20px rgba(45,212,191,.6)}
[class*="st-key-hubsel_"] button p{font-size:15px !important;line-height:1.45}
.st-key-hub_trocar button{border-radius:999px !important}
</style>"""


def render_hub(supabase, pasta, perms, is_master):
    st.markdown(_CSS, unsafe_allow_html=True)
    opcoes = [o for o in OPCOES if is_master or o["perm"] in (perms or ())]
    if not opcoes:
        st.warning("🔒 Nenhum simulador liberado para o seu usuário.")
        return
    ids = [o["id"] for o in opcoes]
    escolha = st.session_state.get("hub_sim")
    if escolha not in ids:
        escolha = None

    if escolha is None:
        st.markdown(
            '<div class="hub-hero"><small>Simuladores Consorbens</small>'
            '<h1>Simule, compare e <em>apresente</em> o consórcio certo.</h1>'
            '<p>Escolha a administradora. A lógica de cada simulador continua a mesma; '
            'agora com guia de grupos, menores lances com vaga e modo apresentação para o cliente.</p></div>',
            unsafe_allow_html=True)
        cols = st.columns(len(opcoes))
        for col, o in zip(cols, opcoes):
            with col:
                if st.button(f"{o['ico']}  **{o['titulo']}**\n\n{o['sub']}", key=f"hubsel_{o['id']}",
                             use_container_width=True):
                    st.session_state["hub_sim"] = o["id"]
                    st.rerun()
        st.markdown('<div class="hub-soon">' + "".join(f"<span>🔜 {n} · em breve</span>" for n in EM_BREVE)
                    + "</div>", unsafe_allow_html=True)
        return

    # ---- barra de troca ----
    c1, c2 = st.columns([5, 1.2])
    with c1:
        nova = st.segmented_control(
            "Simulador", ids, default=escolha, key="hub_seg", label_visibility="collapsed",
            format_func=lambda i: next(f"{o['ico']} {o['titulo']}" for o in opcoes if o["id"] == i))
        if nova and nova != escolha:
            st.session_state["hub_sim"] = nova
            st.rerun()
    with c2:
        if st.button("← Início", key="hub_trocar", use_container_width=True):
            st.session_state.pop("hub_sim", None)
            st.session_state.pop("hub_seg", None)
            st.rerun()

    linhas, meta = _dados_painel(escolha, supabase)
    _painel(pasta, linhas, meta)
    extra = _camada(pasta, escolha, linhas, meta)

    if escolha == "yamaha":
        from modulos.yamaha_sim import render_yamaha_sim
        render_yamaha_sim(supabase, pasta, extra_html=extra)
    elif escolha == "itau_ia":
        from modulos.itau_v2 import render_itau_v2
        render_itau_v2(pasta, extra_html=extra)
    else:
        try:
            html = _ler(os.path.join(pasta, "itau.html"))
        except FileNotFoundError:
            st.error("⚠️ itau.html não encontrado no servidor.")
            return
        components.html(_injetar(html, extra), height=1000, scrolling=True)


def _injetar(html, extra):
    """Acrescenta `extra` antes do </body> (ou no fim). Não altera nada do original."""
    if not extra:
        return html
    i = html.rfind("</body>")
    return html[:i] + extra + html[i:] if i >= 0 else html + extra
