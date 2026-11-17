# -*- coding: utf-8 -*-
"""
Simulador Consorbens (universal) — 16/11/2026.

O cliente diz: nome, produto (auto/moto/imóvel/caminhão), crédito LÍQUIDO que quer na mão,
quanto tem de lance (recurso próprio) e a parcela que aguenta DEPOIS de contemplar.
A página (assets/simulador/universal.html) cruza:
  * Yamaha — grupos com vaga, créditos do plano, taxa, regra de embutido e o histórico de
    lance livre de cada assembleia (tudo que o robô Newcon grava no Supabase);
  * Itaú   — Guia de Oportunidades da semana (créditos, prazo, fundo, lances das 2 últimas
    assembleias);
e devolve os melhores grupos de cada administradora, o comparativo e os cards (card + potencial
de contemplação). Se nenhum lance alcança o histórico, diz quanto falta de lance.

Este módulo só MONTA os dados e injeta na página. O cálculo é o mesmo calibrado com o
"Simular..." do Newcon (base do lance integral 96,191% de C1; reduzida 70%) e as fórmulas do
Simulador Estruturado Itaú.
"""
import os
import json
import datetime

import streamlit as st
import streamlit.components.v1 as components

_ASSETS = os.path.join("assets", "simulador")
PRODUTO_YAMAHA = {"Auto": "auto", "Moto": "moto", "Imóvel": "imovel", "Imovel": "imovel",
                  "Caminhão": "caminhao", "Caminhao": "caminhao"}
EMBUTIDO_GERAL = {"auto": 15, "moto": 15, "imovel": 25, "caminhao": 30}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _cod(x):
    import re
    d = re.sub(r"\D", "", str(x or "").split("-")[0])
    return d.zfill(3) if d else str(x or "").strip()


def dados_yamaha(base):
    """Grupos Yamaha prontos para o motor da página (1 linha por grupo × produto)."""
    planos = {}
    for p in base.get("planos") or []:
        planos[(_cod(p.get("codigo")), PRODUTO_YAMAHA.get(p.get("tipo_bem"), ""))] = p
    hist = {}
    for a in base.get("assembleias") or []:
        mn = _f(a.get("lance_livre_min"))
        if mn is None or not a.get("data_assembleia"):
            continue
        hist.setdefault(str(a.get("grupo")), []).append({
            "d": str(a["data_assembleia"])[:10], "mn": mn, "mx": _f(a.get("lance_livre_max")) or mn,
            "md": _f(a.get("lance_livre_medio")), "ll": _i(a.get("n_lance_livre")) or 0})
    for g in hist:
        hist[g] = sorted(hist[g], key=lambda x: x["d"])[-12:]
    regras = base.get("regras") or {}
    out = []
    for r in base.get("grupos") or []:
        prod = PRODUTO_YAMAHA.get(r.get("tipo_bem"))
        vagas, n = _i(r.get("vagas")), _i(r.get("prazo_restante"))
        tx = _f(r.get("taxa"))
        if not prod or not vagas or vagas <= 0 or not n or n < 6 or tx is None:
            continue
        g = str(r.get("grupo"))
        pl = planos.get((_cod(r.get("plano_codigo")), prod)) or {}
        pt = _i(r.get("prazo_total"))
        creds = []
        for c in pl.get("creditos") or []:
            if pt and _i(c.get("prazo")) not in (None, pt):
                continue
            v = _f(c.get("credito"))
            if v:
                creds.append(v)
        if not creds and pl.get("creditos"):
            creds = [_f(c.get("credito")) for c in pl["creditos"] if _f(c.get("credito"))]
        if _f(r.get("credito")):
            creds.append(_f(r.get("credito")))
        creds = sorted({round(c, 2) for c in creds})
        if not creds:
            continue
        rg = regras.get(g) or {}
        emb = _f(rg.get("embutido_max_pct")) or _f(r.get("embutido_max_pct")) or EMBUTIDO_GERAL[prod]
        red = (_f(r.get("reducao_pct")) or 0) / 100 if r.get("parcela_reduzida") else 0.0
        lib = rg.get("liberadas") or {}
        out.append({
            "adm": "yamaha", "g": g, "prod": prod, "vagas": vagas, "n": n, "pt": pt,
            "tx": tx / 100, "red": red, "emb": emb / 100, "creds": creds,
            "plano": pl.get("nome") or r.get("plano_codigo") or "", "bem": r.get("bem") or "",
            "prox": r.get("prox_assembleia") or "", "fixo": _f(rg.get("fixo_pct")),
            "livre": lib.get("Lance Livre", True) is not False,
            "hist": hist.get(g, []), "visto": str(r.get("consultado_em") or "")[:10],
        })
    return out


# mesmos filtros do Itaú · IA (itau_v2.html): só grupos com 5+ vagas e prazo dentro da faixa do produto
ITAU_VAGAS_MIN = 5
ITAU_PRAZO = {"imovel": (90, 240), "auto": (24, 140)}


def dados_itau(guia):
    out = []
    for g in (guia or {}).get("grupos") or []:
        prod = "imovel" if str(g.get("aba", "")).lower().startswith("im") else "auto"
        lo, hi = ITAU_PRAZO[prod]
        if (g.get("vagas") or 0) < ITAU_VAGAS_MIN or not (lo <= (g.get("prazo") or 0) <= hi):
            continue
        la = (list(g.get("lances") or []) + [0, 0, 0, 0])[:4]
        hist = []
        # Guia: [mín, máx] das 2 assembleias que ela traz (frações do crédito)
        for mn, mx, rot in ((la[0], la[1], "Assemb. 1"), (la[2], la[3], "Assemb. 2")):
            if mn and mn > 0:
                hist.append({"d": rot, "mn": mn * 100, "mx": max(mx or 0, mn) * 100, "md": None, "ll": None})
        out.append({
            "adm": "itau", "g": str(g["grupo"]), "prod": prod, "vagas": g.get("vagas"), "n": g.get("prazo"),
            "tx": 0.16, "fr": g.get("fundo") or 0, "red": 0.3 if g.get("red") and prod == "auto" else 0,
            "redOk": bool(g.get("red")), "emb": 0.30, "creds": g.get("valores") or [],
            "fixo": g.get("fixoPct"), "livre": True, "hist": hist, "prox": g.get("assembleia") or "",
            "cont": g.get("contLivre"),
        })
    return out


def _img(pasta, nome):
    from modulos.simuladores_hub import _img_data_uri
    return _img_data_uri(os.path.join(pasta, _ASSETS, nome))


def montar_payload(supabase, pasta):
    from modulos.yamaha_sim import carregar_base_yamaha
    erros = []
    try:
        base = carregar_base_yamaha(supabase)
        ya = dados_yamaha(base)
        ya_att = ((base.get("atualizacao") or {}).get("grupos") or "")[:10]
    except Exception as e:                      # noqa: BLE001
        ya, ya_att = [], ""
        erros.append(f"Yamaha: {e}")
    try:
        from modulos.itau_v2 import _carregar_dados_itau
        guia, _log = _carregar_dados_itau()
        it = dados_itau(guia)
        it_att = (guia.get("meta") or {}).get("baixado_em") or ""
    except Exception as e:                      # noqa: BLE001
        it, it_att = [], ""
        erros.append(f"Itaú: {e}")
    return {
        "grupos": ya + it,
        "meta": {"yamaha": ya_att, "itau": it_att, "hoje": datetime.date.today().isoformat(), "erros": erros},
        "logos": {"consorbens": _img(pasta, "logo.png"), "yamaha": _img(pasta, "logo_yamaha_h.png"),
                  "itau": _img(pasta, "logo_itau.svg")},
        "fotos": {"auto": _img(pasta, "auto.jpg"), "moto": _img(pasta, "yamaha_moto.jpg"),
                  "imovel": _img(pasta, "imoveis.jpg"), "caminhao": _img(pasta, "pesados.jpg")},
        "contato": "(31) 99894-2219 · consorbens.com.br",
    }


def html_universal(supabase, pasta):
    payload = json.dumps(montar_payload(supabase, pasta), ensure_ascii=False).replace("</", "<\\/")
    from modulos.simuladores_hub import _ler
    html = _ler(os.path.join(pasta, _ASSETS, "universal.html"))
    html = html.replace('"__DADOS_UNIVERSAL__"', payload, 1)
    from modulos.simuladores_temas import aplicar_universal   # tema escolhido no hub (16/11/2026)
    return aplicar_universal(html)


# ------------------------------------------------------------------ #
# Conferência automática pelo robô (16/11/2026)
#   A página, depois de gerar a simulação, manda pelo campo oculto "univ_conferir" os
#   grupos Yamaha que apareceram. Aqui a gente olha a base e, se a vaga estiver velha
#   (>6 dias ou <10 vagas) ou faltar assembleia recente, pede ao robô (fila_automacao,
#   tipo CONFERIR_GRUPOS) e mostra "Aguarde, atualizando grupos enquanto o robô atualiza".
#   Robô desligado / Newcon não entrou / demorou → segue com a base mais recente e avisa.
# ------------------------------------------------------------------ #
_LABEL_CONF = "univ_conferir"
_KEY_CONF = "univ_conferir_raw"
_KEY_PROC = "_univ_conferir_proc"
POUCAS_VAGAS = 10
VALIDADE_VAGAS_DIAS = 6
VALIDADE_ASSEMB_DIAS = 35          # assembleia é mensal: passou disso, falta a última
ROBO_ONLINE_SEG = 90               # mesmo limite do Painel do Robô
ESPERA_FILA_SEG = 180              # robô ligado mas não pegou a tarefa → segue com a base
ESPERA_TOTAL_SEG = 600
REPETIR_APOS_SEG = 3600            # não pede o mesmo grupo de novo na mesma hora
MOSTRAR_FIM_SEG = 900              # recado final some depois de 15 min


def _idade_dias(ts):
    try:
        d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds() / 86400
    except Exception:
        return None


def _o_que_conferir(sb, grupos):
    """(vagas, assembleias): grupos que precisam ir ao Newcon. Só lê a base."""
    vagas, assemb = [], []
    try:
        rows = (sb.table("grupos_yamaha").select("grupo,vagas,consultado_em")
                .in_("grupo", grupos).execute().data or [])
    except Exception:
        rows = []
    try:
        ass = (sb.table("yamaha_assembleias").select("grupo,data_assembleia")
               .in_("grupo", grupos).execute().data or [])
    except Exception:
        ass = []
    ult_ass = {}
    for a in ass:
        g = str(a.get("grupo"))
        d = str(a.get("data_assembleia") or "")[:10]
        if d > ult_ass.get(g, ""):
            ult_ass[g] = d
    por_grupo = {}
    for r in rows:
        g = str(r.get("grupo"))
        if g not in por_grupo or str(r.get("consultado_em") or "") > str(por_grupo[g].get("consultado_em") or ""):
            por_grupo[g] = r
    for g in grupos:
        r = por_grupo.get(g)
        if r is None:
            continue                      # grupo fora da base: não dá para saber o plano
        idade = _idade_dias(r.get("consultado_em"))
        v = r.get("vagas")
        if v is None or int(v) < POUCAS_VAGAS or idade is None or idade > VALIDADE_VAGAS_DIAS:
            vagas.append(g)
        ia = _idade_dias(ult_ass[g] + "T12:00:00+00:00") if g in ult_ass else None
        if ia is None or ia > VALIDADE_ASSEMB_DIAS:
            assemb.append(g)
    return vagas, assemb


def _robo_situacao(sb):
    """(online, login_travado)."""
    try:
        r = sb.table("robo_status").select("*").eq("id", 1).execute().data or [{}]
        idade = _idade_dias(r[0].get("atualizado_em"))
        online = idade is not None and idade * 86400 <= ROBO_ONLINE_SEG
        return online, bool(r[0].get("login_travado"))
    except Exception:
        return False, False


def _quem():
    return str(st.session_state.get("usuario_logado") or "ERP")


def pedir_conferencia(sb, grupos):
    agora = datetime.datetime.now().timestamp()
    feitos = st.session_state.setdefault("univ_conferidos", {})
    grupos = [g for g in dict.fromkeys(str(x).strip() for x in grupos) if g and agora - feitos.get(g, 0) > REPETIR_APOS_SEG]
    if not grupos:
        return
    vagas, assemb = _o_que_conferir(sb, grupos)
    if not vagas and not assemb:
        return
    alvo = sorted(set(vagas) | set(assemb), key=lambda x: int(x) if x.isdigit() else 0)
    for g in alvo:
        feitos[g] = agora
    est = {"grupos": alvo, "vagas": vagas, "assembleias": assemb, "criado": agora}
    online, travado = _robo_situacao(sb)
    if not online:
        est.update(estado="offline", fim=agora)
    elif travado:
        est.update(estado="erro", fim=agora, msg="o login do Newcon está travado no robô")
    else:
        try:
            row = sb.table("fila_automacao").insert({
                "tipo": "CONFERIR_GRUPOS", "status": "PENDENTE", "prioridade": 30,
                "payload": {"vagas": vagas, "assembleias": assemb, "origem": "simulador_universal"},
                "solicitado_por": f"SIMULADOR:{_quem()}",
            }).execute().data or [{}]
            est.update(estado="fila", id=row[0].get("id"))
        except Exception as e:                                  # noqa: BLE001
            est.update(estado="erro", fim=agora, msg=f"não consegui pedir ao robô ({str(e)[:80]})")
    st.session_state["univ_robo"] = est


def _lista(gs):
    return ", ".join(gs[:6]) + (f" e mais {len(gs) - 6}" if len(gs) > 6 else "")


def _detalhe(est):
    p = []
    if est.get("vagas"):
        p.append(f"vagas do(s) grupo(s) {_lista(est['vagas'])}")
    if est.get("assembleias"):
        p.append(f"assembleias do(s) grupo(s) {_lista(est['assembleias'])}")
    return " · ".join(p)


def _base_txt(sb):
    try:
        from modulos.yamaha_sim import carregar_base_yamaha
        att = carregar_base_yamaha(sb).get("atualizacao") or {}
        def f(k):
            s = str(att.get(k) or "")[:10]
            return "/".join(s.split("-")[::-1]) if s else "—"
        return f"grupos de {f('grupos')}, assembleias de {f('assembleias')}"
    except Exception:
        return "a mais recente do sistema"


@st.fragment(run_every=5)
def _acompanhar(sb):
    """Roda a cada 5 s só enquanto o robô está com a tarefa; quando acaba, recarrega a tela."""
    est = st.session_state.get("univ_robo") or {}
    if est.get("estado") not in ("fila", "rodando"):
        return
    agora = datetime.datetime.now().timestamp()
    row = {}
    try:
        row = (sb.table("fila_automacao").select("status,mensagem,progresso,iniciado_em")
               .eq("id", est.get("id")).execute().data or [{}])[0]
    except Exception:
        pass
    s = (row.get("status") or "").upper()
    if s == "SUCESSO":
        est.update(estado="ok", fim=agora, msg=row.get("mensagem") or "")
    elif s == "ERRO":
        est.update(estado="erro", fim=agora, msg=row.get("mensagem") or "o Newcon não respondeu")
    elif s == "PROCESSANDO":
        est.update(estado="rodando", prog=row.get("progresso") or "")
    if est["estado"] in ("fila", "rodando"):
        espera = agora - est.get("criado", agora)
        online, _ = _robo_situacao(sb)
        if not online:
            est.update(estado="offline", fim=agora)
        elif (est["estado"] == "fila" and espera > ESPERA_FILA_SEG) or espera > ESPERA_TOTAL_SEG:
            est.update(estado="demorou", fim=agora)
    st.session_state["univ_robo"] = est
    if est["estado"] not in ("fila", "rodando"):
        try:
            from modulos.yamaha_sim import carregar_base_yamaha
            carregar_base_yamaha.clear()
        except Exception:
            pass
        st.rerun(scope="app")
    fase = "O robô está no Newcon conferindo" if est["estado"] == "rodando" else "Pedido enviado ao robô — vai conferir"
    c1, c2 = st.columns([5, 1.4], vertical_alignment="center")
    with c1:
        st.info(f"⏳ **Aguarde, atualizando grupos enquanto o robô atualiza.** {fase}: {_detalhe(est)}. "
                f"A simulação abaixo já aparece com a base mais recente e se atualiza sozinha quando o robô terminar. "
                f"Com pressa? Use a base salva."
                + (f"  \n_{est.get('prog')}_" if est.get("prog") else ""), icon=None)
    with c2:
        if st.button("⚡ Usar base salva", key="univ_base_salva", use_container_width=True,
                     help="Para de esperar o robô e segue com os dados que já estão no sistema. "
                          "O robô continua atualizando em segundo plano para a próxima simulação."):
            usar_base_salva()
            st.rerun(scope="app")


def usar_base_salva():
    """O usuário está com pressa: para de esperar. A tarefa do robô continua na fila
    (atualiza a base para as próximas simulações), só não recarrega mais esta tela."""
    est = st.session_state.get("univ_robo") or {}
    if est.get("estado") in ("fila", "rodando"):
        est.update(estado="base_salva", fim=datetime.datetime.now().timestamp())
        st.session_state["univ_robo"] = est


def _mostrar_status(sb):
    est = st.session_state.get("univ_robo") or {}
    e = est.get("estado")
    if e in ("fila", "rodando"):
        _acompanhar(sb)
        return
    if not e or datetime.datetime.now().timestamp() - est.get("fim", 0) > MOSTRAR_FIM_SEG:
        return
    if e == "ok":
        hora = datetime.datetime.fromtimestamp(est["fim"]).strftime("%H:%M")
        st.success(f"✅ Robô atualizou agora ({hora}): {_detalhe(est)}. A simulação abaixo já usa os dados novos."
                   + (f"  \n_{est.get('msg')}_" if est.get("msg") else ""))
    elif e == "offline":
        st.warning(f"🔌 O robô (PC servidor) está desligado, então não deu para conferir {_detalhe(est)}. "
                   f"A simulação usa a base mais recente do sistema ({_base_txt(sb)}). Confira a vaga antes de fechar.")
    elif e == "erro":
        st.warning(f"⚠️ O robô não conseguiu conferir no Newcon agora ({est.get('msg')}). "
                   f"A simulação usa a base mais recente do sistema ({_base_txt(sb)}).")
    elif e == "demorou":
        st.info(f"⌛ O robô ainda não terminou de conferir {_detalhe(est)} (pode estar ocupado ou o Newcon não entrou). "
                f"A simulação usa a base mais recente ({_base_txt(sb)}); a conferência continua na fila.")
    elif e == "base_salva":
        st.info(f"⚡ Usando a base salva ({_base_txt(sb)}). O robô continua conferindo {_detalhe(est)} "
                f"em segundo plano: na próxima simulação os dados já estarão atualizados.")


def _robo_para_pagina(est):
    e = est.get("estado")
    if not e or (e not in ("fila", "rodando") and datetime.datetime.now().timestamp() - est.get("fim", 0) > MOSTRAR_FIM_SEG):
        return {}
    return {"estado": e, "grupos": est.get("grupos", []), "detalhe": _detalhe(est),
            "hora": datetime.datetime.fromtimestamp(est.get("fim") or est.get("criado") or 0).strftime("%H:%M")}


_CSS_PONTE = ("<style>.st-key-univ_conferir_raw{position:absolute !important;left:-9999px !important;"
              "width:1px !important;height:1px !important;overflow:hidden !important}</style>")


def render_universal(supabase, pasta):
    st.markdown(_CSS_PONTE, unsafe_allow_html=True)
    # ponte: a página escreve "9510,9049|nonce" (ou "__BASE__|nonce" = botão "Usar base salva"
    # da faixa do simulador) neste campo oculto e dá Enter
    raw = st.text_input(_LABEL_CONF, key=_KEY_CONF, label_visibility="collapsed")
    if raw and raw != st.session_state.get(_KEY_PROC):
        st.session_state[_KEY_PROC] = raw
        if raw.startswith("__BASE__"):
            usar_base_salva()
        else:
            pedir_conferencia(supabase, raw.split("|")[0].split(","))
    with st.container():
        _mostrar_status(supabase)
    html = html_universal(supabase, pasta)
    from modulos.simuladores_hub import _ler
    try:
        js = _ler(os.path.join(pasta, _ASSETS, "universal_robo.js"))
    except FileNotFoundError:
        js = ""
    robo = json.dumps(_robo_para_pagina(st.session_state.get("univ_robo") or {}), ensure_ascii=False).replace("</", "<\\/")
    extra = f"<script>window.__ROBO={robo};</script><script>{js}</script>"
    i = html.rfind("</body>")
    html = html[:i] + extra + html[i:] if i >= 0 else html + extra
    components.html(html, height=1100, scrolling=True)
