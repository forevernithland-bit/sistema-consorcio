# -*- coding: utf-8 -*-
"""
Simuladores Consorbens — tela única (hub).

Junta num lugar só os simuladores das administradoras (Yamaha, Itaú por IA e
Itaú manual; outras entram em OPCOES quando existirem). O usuário escolhe a
administradora e o hub:
  1) renderiza o simulador original, sem tocar na conta — só injeta a camada
     visual (assets/simulador/hub_skin.css + hub_apresentacao.js): hero com
     KPIs, barra de abas, aba "📘 Guia de Grupos" (menores lances com vaga e
     guia completa, a partir dos MESMOS dados que os simuladores já usam —
     tabelas do robô Yamaha / Guia de Oportunidades Itaú) e o modo
     "Apresentar ao cliente".
  A tela inicial é um iframe animado (assets/simulador/hub_inicio.html).

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
     "sub": "Motos, autos, imóveis e pesados · dados do robô Newcon",
     "adm": "Consórcio Yamaha", "selo": "Robô Newcon", "img": "pesados.jpg", "icone": "moto",
     "desc": "Motos, autos, imóveis e pesados com grupos, vagas e lances de referência "
             "coletados pelo robô Newcon.",
     "tags": ["Motos", "Autos", "Imóveis", "Pesados"]},
    {"id": "itau_ia", "perm": "sim_itau_v2", "titulo": "Itaú · IA", "ico": "🚀",
     "sub": "A IA monta a proposta direto da Guia de Oportunidades",
     "adm": "Consórcio Itaú", "selo": "IA + Guia de Oportunidades", "img": "auto.jpg", "icone": "ia",
     "desc": "A IA lê a Guia de Oportunidades da semana e monta a proposta com os grupos "
             "mais aderentes ao perfil do cliente.",
     "tags": ["Autos", "Imóveis", "Guia semanal"]},
    {"id": "itau_manual", "perm": "sim_itau", "titulo": "Itaú · Manual", "ico": "🏦",
     "sub": "Você digita os dados do grupo e do lance",
     "adm": "Consórcio Itaú", "selo": "Digitação livre", "img": "casa.jpg", "icone": "manual",
     "desc": "Você informa os dados do grupo e do lance e gera a simulação completa, "
             "do seu jeito, para qualquer cenário.",
     "tags": ["Autos", "Imóveis", "Cenário livre"]},
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
_FONTE = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800'
          '&display=swap" rel="stylesheet">')
# foto da capa do modo apresentação por produto (moto usa arte em SVG da própria camada)
_FOTOS = {"imovel": "casa.jpg", "auto": "auto.jpg", "caminhao": "pesados.jpg"}


@st.cache_data
def _fotos_uri(pasta):
    base = os.path.join(pasta, _ASSETS)
    return {k: _img_data_uri(os.path.join(base, f)) for k, f in _FOTOS.items()}


def _camada(pasta, opc, linhas, meta):
    """Skin + hero/abas/Guia de Grupos + modo apresentação, injetados no simulador.
    Só aparência e leitura: nenhuma função de cálculo do simulador é tocada."""
    from modulos.yamaha_sim import _logo_data_uri
    ctx = {
        "sim": opc, "adm": meta.get("adm"), "logo": _logo_data_uri(pasta),
        "contato": "(31) 99894-2219 · consorbensmg.com.br",
        "grupos": {l["g"]: l for l in linhas},
        "meta": {k: meta.get(k) for k in ("adm", "fonte", "atualizado", "erro") if meta.get(k)},
        "fotos": {k: v for k, v in _fotos_uri(pasta).items() if v},
    }
    css = _ler(os.path.join(pasta, _ASSETS, "hub_skin.css"))
    js = _ler(os.path.join(pasta, _ASSETS, "hub_apresentacao.js"))
    payload = json.dumps(ctx, ensure_ascii=False, default=str).replace("</", "<\\/")
    return (_FONTE + '<style data-cbx-skin="1">' + css + "</style>"
            + "<script>window.CBX_CTX=" + payload + ";</script><script>" + js + "</script>")


# ------------------------------------------------------------------ #
# Tela
# ------------------------------------------------------------------ #
_CSS = """<style>
.hub-ou{font-size:12.5px;color:#94a3b8;margin:2px 0 4px}
[class*="st-key-hubsel_"] button{min-height:0 !important;padding:4px 12px !important;border-radius:999px !important;
  background:transparent !important;border:1px solid #334155 !important;color:#cbd5e1 !important}
[class*="st-key-hubsel_"] button:hover{border-color:#2dd4bf !important;color:#fff !important}
[class*="st-key-hubsel_"] button p{font-size:13px !important}
.st-key-hub_escolha_raw{position:absolute !important;left:-9999px !important;width:1px !important;height:1px !important;
  overflow:hidden !important;opacity:0 !important}
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
        _tela_inicial(pasta, opcoes, ids)
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
            _limpar_ponte()
            st.rerun()

    # o Guia de Grupos agora é uma aba DENTRO do simulador (camada injetada)
    linhas, meta = _dados_painel(escolha, supabase)
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
        components.html(_injetar(html, extra), height=1300, scrolling=True)


# ------------------------------------------------------------------ #
# Tela inicial (iframe animado + ponte de escolha)
# ------------------------------------------------------------------ #
_LABEL_ESCOLHA = "hub_escolha"          # aria-label do campo oculto (o iframe procura por ele)
_KEY_ESCOLHA = "hub_escolha_raw"
_KEY_PROC = "_hub_escolha_proc"
_CAMPOS_CARD = ("id", "titulo", "sub", "selo", "adm", "img", "icone", "desc", "tags")


@st.cache_data
def _img_data_uri(caminho):
    import base64
    ext = os.path.splitext(caminho)[1].lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
    try:
        with open(caminho, "rb") as f:
            return f"data:image/{mime};base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


@st.cache_data
def _html_inicio(pasta, ids):
    """HTML da tela inicial com os dados já injetados. Cacheado por (pasta, ids):
    o conteúdo fica idêntico entre reruns e o iframe não recarrega."""
    base = os.path.join(pasta, _ASSETS)
    opcoes = [{k: o.get(k) for k in _CAMPOS_CARD} for o in OPCOES if o["id"] in ids]
    imgs = {o["img"]: _img_data_uri(os.path.join(base, o["img"])) for o in opcoes if o.get("img")}
    hub = {"opcoes": opcoes, "em_breve": EM_BREVE, "imgs": imgs,
           "logo": _img_data_uri(os.path.join(base, "logo.png"))}
    payload = json.dumps(hub, ensure_ascii=False).replace("</", "<\\/")
    html = _ler(os.path.join(base, "hub_inicio.html"))
    return html.replace('"__HUB_INICIO__"', payload, 1)


def _limpar_ponte():
    st.session_state.pop(_KEY_ESCOLHA, None)
    st.session_state.pop(_KEY_PROC, None)


def _tela_inicial(pasta, opcoes, ids):
    # ponte: o iframe escreve "id|nonce" neste campo oculto e dá Enter
    raw = st.text_input(_LABEL_ESCOLHA, key=_KEY_ESCOLHA, label_visibility="collapsed")
    if raw and raw != st.session_state.get(_KEY_PROC):
        st.session_state[_KEY_PROC] = raw
        alvo = raw.split("|", 1)[0].strip()
        if alvo in ids:
            st.session_state["hub_sim"] = alvo
            st.rerun()

    altura = 760 if len(opcoes) > 1 else 700
    components.html(_html_inicio(pasta, tuple(ids)), height=altura, scrolling=False)

    # fallback acessível (se a ponte do iframe não funcionar)
    st.markdown('<div class="hub-ou">Ou escolha aqui:</div>', unsafe_allow_html=True)
    cols = st.columns(len(opcoes) + 2)
    for col, o in zip(cols, opcoes):
        with col:
            if st.button(f"{o['ico']} {o['titulo']}", key=f"hubsel_{o['id']}", use_container_width=True):
                st.session_state["hub_sim"] = o["id"]
                st.rerun()


def _injetar(html, extra):
    """Acrescenta `extra` antes do </body> (ou no fim). Não altera nada do original."""
    if not extra:
        return html
    i = html.rfind("</body>")
    return html[:i] + extra + html[i:] if i >= 0 else html + extra
