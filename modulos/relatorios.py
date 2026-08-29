"""
relatorios.py — Relatórios Gerenciais da Consorbens.

Duas grandezas diferentes convivem aqui, e a distinção é a chave do módulo:

  • VOLUME DE VENDAS  — quanto de crédito foi vendido (tabela `vendas`).
    É o tamanho do negócio, NÃO é dinheiro que entrou.

  • FATURAMENTO       — o que a corretora realmente recebeu:
      - Consórcio Tradicional: comissão paga pela administradora
        (`comissoes_pagas`, importada da NF quinzenal).
      - Cartas Contempladas:   o ágio das operações concluídas no Site.

Misturar as duas é o erro clássico desse tipo de relatório — por isso cada
quadro diz explicitamente qual delas está mostrando.

O faturamento PREVISTO sai do mesmo motor do resto do ERP (`regras.py`), que
aplica a regra de comissão da administradora + produto (tabela
`administradoras`, colunas P1..P25), desconta imposto e divide entre os sócios.
"""
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from utils import (formatar_brl_puro, parse_float_safe, limpar_str_nan,
                   normalizar_produto)
from regras import gerar_previsao_pendente, cotas_duplicadas
from modulos.integracao_site import carregar_operacoes_site


# ==========================================================
# HELPERS
# ==========================================================
def _ym_de(data_br):
    """'31/07/2026' -> '2026-07'. None se inválida."""
    d = pd.to_datetime(data_br, dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m")


def _label_mes(ym):
    try:
        return datetime.strptime(str(ym), "%Y-%m").strftime("%m/%Y")
    except (ValueError, TypeError):
        return str(ym)


def _norm_gc(v):
    """Grupo/cota comparável ('009045', '9045', 9045.0 -> '9045')."""
    s = limpar_str_nan(v)
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s.strip()


def _tabela_brl(df, colunas_moeda, ordem=None):
    """Cópia formatada em R$ para exibição (não altera o original)."""
    if df is None or df.empty:
        return df
    out = df[ordem].copy() if ordem else df.copy()
    for c in colunas_moeda:
        if c in out.columns:
            out[c] = out[c].apply(formatar_brl_puro)
    return out


def _vazio(msg):
    st.info(msg)


def _meses_de(*fontes):
    """União dos meses ('AAAA-MM') presentes nas fontes informadas."""
    meses = set()
    for df, col in fontes:
        if df is None or getattr(df, "empty", True) or col not in df.columns:
            continue
        if col == "Data_Real":
            meses |= {d.strftime("%Y-%m") for d in df[col].dropna()}
        else:
            meses |= set(df[col].dropna().astype(str))
    return {m for m in meses if m and m != "None"}


def _filtra_vendas_por_mes(df_vendas, yms):
    if df_vendas is None or df_vendas.empty:
        return pd.DataFrame()
    d = df_vendas[df_vendas["Data_Real"].notna()]
    return d[d["Data_Real"].dt.strftime("%Y-%m").isin(yms)]


# ==========================================================
# FONTES DE DADOS
# ==========================================================
def _carregar_comissoes(supabase):
    """Histórico de comissões recebidas (Consórcio Tradicional)."""
    try:
        rows = supabase.table("comissoes_pagas").select("*").execute().data or []
    except Exception as e:
        st.error(f"Não consegui ler o histórico de comissões: {e}")
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for c in ["valor_nota", "valor_liquido", "breno", "uriel", "credito", "valor_imposto"]:
        df[c] = df[c].apply(parse_float_safe) if c in df.columns else 0.0
    # mês = mês de referência do relatório da administradora (igual ao Financeiro)
    df["ym"] = df["data_pagamento"].apply(_ym_de)
    if "mes_competencia" in df.columns:
        df["ym"] = df["ym"].fillna(df["mes_competencia"])
    df["gc"] = df["grupo"].apply(_norm_gc) + "/" + df["cota"].apply(_norm_gc)
    df["administradora"] = df["administradora"].astype(str).str.strip().str.upper()
    return df


def _enriquecer_com_venda(df_com, df_vendas):
    """`comissoes_pagas` não guarda o PRODUTO — ele vem da venda (grupo+cota)."""
    if df_com is None or df_com.empty:
        return df_com
    mapa = {}
    if df_vendas is not None and not df_vendas.empty:
        for _, v in df_vendas.iterrows():
            mapa[f"{_norm_gc(v.get('GRUPO'))}/{_norm_gc(v.get('COTA'))}"] = {
                "produto": normalizar_produto(v.get("PRODUTO")) or "—",
                "vendedor": v.get("VENDEDOR") or "—",
            }
    df = df_com.copy()
    df["produto"] = df["gc"].map(lambda k: mapa.get(k, {}).get("produto", "—"))
    # o vendedor gravado na NF é a fonte da verdade; a venda é só reserva
    df["vendedor"] = df.apply(
        lambda r: (str(r.get("vendedor") or "").strip()
                   or mapa.get(r["gc"], {}).get("vendedor", "—")), axis=1)
    return df


def _previsto(df_vendas, df_admin, cfg, status_dict):
    """Comissões ainda NÃO recebidas. Fonte única: `regras.gerar_previsao_pendente`
    — a mesma que o Financeiro usa, para as duas telas nunca divergirem."""
    try:
        return gerar_previsao_pendente(df_vendas, df_admin, cfg, status_dict)
    except Exception as e:
        st.warning(f"Não consegui projetar as comissões previstas: {e}")
        return pd.DataFrame(columns=["ym", "cliente", "gc", "admin", "produto", "vendedor",
                                     "parcela", "data", "bruto", "liquido", "breno",
                                     "uriel", "atrasada"]), []


def _cartas_site():
    """(concluídas, em análise). Vazio se a integração com o Site estiver desligada."""
    try:
        s = carregar_operacoes_site()
    except Exception:
        return pd.DataFrame(), pd.DataFrame()
    if s is None or s.empty:
        return pd.DataFrame(), pd.DataFrame()
    return s[s["status"] == "concluido"].copy(), s[s["status"] == "em_analise"].copy()


# ==========================================================
# FILTRO DE PERÍODO (sobre uma coluna 'AAAA-MM')
# ==========================================================
def _seletor_periodo(chave, meses_disponiveis):
    """Devolve (lista_de_ym, rótulo). 'Todos' = tudo o que existe."""
    hoje = datetime.today()
    ym_atual = f"{hoje.year:04d}-{hoje.month:02d}"
    ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
    ym_ant = f"{aa:04d}-{ma:02d}"
    disp = sorted(meses_disponiveis)

    opcoes = ["Mês Atual", "Mês Anterior", "Últimos 6 meses", "Últimos 12 meses",
              "Ano Atual", "Todos", "Escolher meses"]
    c1, c2 = st.columns([1, 2])
    with c1:
        modo = st.selectbox("⏳ Período", opcoes, index=0, key=f"rel_per_{chave}")

    if modo == "Mês Atual":
        return [ym_atual], _label_mes(ym_atual)
    if modo == "Mês Anterior":
        return [ym_ant], _label_mes(ym_ant)
    if modo in ("Últimos 6 meses", "Últimos 12 meses"):
        n = 6 if "6" in modo else 12
        base = pd.Timestamp(hoje.year, hoje.month, 1)
        yms = sorted((base - pd.DateOffset(months=i)).strftime("%Y-%m") for i in range(n))
        return yms, modo
    if modo == "Ano Atual":
        return [f"{hoje.year}-{i:02d}" for i in range(1, 13)], f"Ano {hoje.year}"
    if modo == "Todos":
        return disp, "Todo o período"

    with c2:
        rotulos = [_label_mes(m) for m in sorted(disp, reverse=True)]
        padrao = [_label_mes(ym_atual)] if _label_mes(ym_atual) in rotulos else rotulos[:1]
        sel = st.multiselect("📆 Meses", rotulos, default=padrao, key=f"rel_mes_{chave}")
    escolhidos = sorted(m for m in disp if _label_mes(m) in sel)
    return escolhidos, ", ".join(sorted(sel)) if sel else "—"


# ==========================================================
# ABA 1 — FATURAMENTO POR MÊS
# ==========================================================
def _aba_faturamento_mes(com, site_ok, prev):
    st.markdown("#### 💵 Faturamento mês a mês")
    st.caption("Dinheiro que **entrou** na Consorbens: comissão do Consórcio Tradicional "
               "(NF da administradora) + ágio das Cartas Contempladas concluídas. "
               "A coluna *Previsto* é o que ainda está por vir das cotas ativas.")

    meses = _meses_de((com, "ym"), (site_ok, "ym"), (prev, "ym"))
    if not meses:
        return _vazio("Ainda não há faturamento registrado.")
    yms, rotulo = _seletor_periodo("fatmes", meses)
    if not yms:
        return _vazio("Selecione ao menos um mês.")

    linhas = []
    for ym in yms:
        c = com[com["ym"] == ym] if not com.empty else com
        s = site_ok[site_ok["ym"] == ym] if not site_ok.empty else site_ok
        p = prev[prev["ym"] == ym] if not prev.empty else prev
        f_trad = c["valor_nota"].sum() if not c.empty else 0.0
        f_site = s["agio"].sum() if not s.empty else 0.0
        linhas.append({
            "Mês": _label_mes(ym),
            "Tradicional": f_trad,
            "Cartas Contempladas": f_site,
            "Faturamento Total": f_trad + f_site,
            "Líquido (s/ imposto)": (c["valor_liquido"].sum() if not c.empty else 0.0) + f_site,
            "Breno": (c["breno"].sum() if not c.empty else 0.0)
                     + (s["breno"].sum() if not s.empty else 0.0),
            "Uriel": (c["uriel"].sum() if not c.empty else 0.0)
                     + (s["uriel"].sum() if not s.empty else 0.0),
            "Previsto a receber": p["bruto"].sum() if not p.empty else 0.0,
        })
    res = pd.DataFrame(linhas)

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("💵 Faturamento Total", formatar_brl_puro(res["Faturamento Total"].sum()))
    t2.metric("🏦 Tradicional", formatar_brl_puro(res["Tradicional"].sum()))
    t3.metric("🎯 Cartas Contempladas", formatar_brl_puro(res["Cartas Contempladas"].sum()))
    t4.metric("🔮 Previsto no período", formatar_brl_puro(res["Previsto a receber"].sum()))

    s1, s2, s3 = st.columns(3)
    s1.metric("🧾 Líquido (s/ imposto)", formatar_brl_puro(res["Líquido (s/ imposto)"].sum()))
    s2.metric("👤 Breno", formatar_brl_puro(res["Breno"].sum()))
    s3.metric("👤 Uriel", formatar_brl_puro(res["Uriel"].sum()))

    moeda = ["Tradicional", "Cartas Contempladas", "Faturamento Total",
             "Líquido (s/ imposto)", "Breno", "Uriel", "Previsto a receber"]
    show = res
    if len(res) > 1:
        tot = {"Mês": "TOTAL"}
        tot.update({c: res[c].sum() for c in moeda})
        show = pd.concat([res, pd.DataFrame([tot])], ignore_index=True)
    st.dataframe(_tabela_brl(show, moeda), use_container_width=True, hide_index=True)

    if len(res) > 1:
        st.markdown("##### 📈 Evolução")
        g = res.melt(id_vars="Mês",
                     value_vars=["Tradicional", "Cartas Contempladas", "Previsto a receber"],
                     var_name="Tipo", value_name="Valor")
        st.altair_chart(
            alt.Chart(g).mark_bar().encode(
                x=alt.X("Mês:N", sort=list(res["Mês"]), title=None),
                y=alt.Y("Valor:Q", title="R$"),
                color=alt.Color("Tipo:N", title=None),
                tooltip=["Mês", "Tipo", alt.Tooltip("Valor:Q", format=",.2f")],
            ).properties(height=300), use_container_width=True)

    st.caption(f"Período: **{rotulo}**. O ágio das Cartas Contempladas hoje entra sem imposto.")


# ==========================================================
# ABA 2 — POR ADMINISTRADORA
# ==========================================================
def _aba_administradora(com, df_vendas, prev):
    st.markdown("#### 🏢 Por Administradora")
    st.caption("**Faturamento** = comissão já recebida. "
               "**Volume vendido** = crédito das cotas vendidas no período (não é receita).")

    meses = _meses_de((com, "ym"), (prev, "ym"), (df_vendas, "Data_Real"))
    if not meses:
        return _vazio("Sem dados para o relatório por administradora.")
    yms, rotulo = _seletor_periodo("adm", meses)
    if not yms:
        return _vazio("Selecione ao menos um mês.")

    c = com[com["ym"].isin(yms)] if not com.empty else com
    p = prev[prev["ym"].isin(yms)] if not prev.empty else prev
    v = _filtra_vendas_por_mes(df_vendas, yms)

    admins = set()
    if not c.empty:
        admins |= set(c["administradora"])
    if not p.empty:
        admins |= set(p["admin"])
    if not v.empty:
        admins |= set(v["ADMINISTRADORA"].astype(str).str.strip().str.upper())
    admins.discard("")
    if not admins:
        return _vazio(f"Nada encontrado em {rotulo}.")

    linhas = []
    for a in sorted(admins):
        cc = c[c["administradora"] == a] if not c.empty else c
        pp = p[p["admin"] == a] if not p.empty else p
        vv = v[v["ADMINISTRADORA"].astype(str).str.strip().str.upper() == a] if not v.empty else v
        linhas.append({
            "Administradora": a,
            "Cotas vendidas": int(len(vv)) if not vv.empty else 0,
            "Volume vendido": vv["Valor_Numerico"].sum() if not vv.empty else 0.0,
            "Parcelas recebidas": int(len(cc)) if not cc.empty else 0,
            "Faturamento": cc["valor_nota"].sum() if not cc.empty else 0.0,
            "Líquido": cc["valor_liquido"].sum() if not cc.empty else 0.0,
            "Breno": cc["breno"].sum() if not cc.empty else 0.0,
            "Uriel": cc["uriel"].sum() if not cc.empty else 0.0,
            "Previsto": pp["bruto"].sum() if not pp.empty else 0.0,
        })
    res = pd.DataFrame(linhas)
    total_fat = res["Faturamento"].sum()
    res["% do faturamento"] = (res["Faturamento"] / total_fat * 100) if total_fat else 0.0
    res = res.sort_values("Faturamento", ascending=False)

    m1, m2, m3 = st.columns(3)
    m1.metric("💵 Faturamento", formatar_brl_puro(total_fat))
    m2.metric("📦 Volume vendido", formatar_brl_puro(res["Volume vendido"].sum()))
    m3.metric("🔮 Previsto", formatar_brl_puro(res["Previsto"].sum()))

    show = res.copy()
    show["% do faturamento"] = show["% do faturamento"].apply(lambda x: f"{x:.1f}%")
    st.dataframe(_tabela_brl(show, ["Volume vendido", "Faturamento", "Líquido",
                                    "Breno", "Uriel", "Previsto"]),
                 use_container_width=True, hide_index=True)

    graf = res[res["Faturamento"] > 0]
    if len(graf) > 1:
        st.altair_chart(
            alt.Chart(graf).mark_arc(innerRadius=55).encode(
                theta="Faturamento:Q", color=alt.Color("Administradora:N", title=None),
                tooltip=["Administradora", alt.Tooltip("Faturamento:Q", format=",.2f")],
            ).properties(height=280), use_container_width=True)
    st.caption(f"Período: **{rotulo}**.")


# ==========================================================
# ABA 3 — POR PRODUTO
# ==========================================================
def _aba_produto(com, df_vendas, prev):
    st.markdown("#### 📦 Por Produto")
    st.caption("O produto vem da cota cadastrada em Vendas (a NF da administradora não traz "
               "essa informação). Cotas ainda não cadastradas aparecem como “—”.")

    meses = _meses_de((com, "ym"), (prev, "ym"), (df_vendas, "Data_Real"))
    if not meses:
        return _vazio("Sem dados para o relatório por produto.")
    yms, rotulo = _seletor_periodo("prod", meses)
    if not yms:
        return _vazio("Selecione ao menos um mês.")

    c = com[com["ym"].isin(yms)] if not com.empty else com
    p = prev[prev["ym"].isin(yms)] if not prev.empty else prev
    v = _filtra_vendas_por_mes(df_vendas, yms)

    prods = set()
    if not c.empty:
        prods |= set(c["produto"].astype(str).str.strip())
    if not p.empty:
        prods |= set(p["produto"].astype(str).str.strip())
    if not v.empty:
        prods |= set(v["PRODUTO"].apply(lambda x: normalizar_produto(x) or "—"))
    prods.discard("")
    if not prods:
        return _vazio(f"Nada encontrado em {rotulo}.")

    linhas = []
    for pr in sorted(prods):
        cc = c[c["produto"].astype(str).str.strip() == pr] if not c.empty else c
        pp = p[p["produto"].astype(str).str.strip() == pr] if not p.empty else p
        vv = v[v["PRODUTO"].apply(lambda x: normalizar_produto(x) or "—") == pr] if not v.empty else v
        vol = vv["Valor_Numerico"].sum() if not vv.empty else 0.0
        linhas.append({
            "Produto": pr,
            "Cotas vendidas": int(len(vv)) if not vv.empty else 0,
            "Volume vendido": vol,
            "Ticket médio": (vol / len(vv)) if (not vv.empty and len(vv)) else 0.0,
            "Faturamento": cc["valor_nota"].sum() if not cc.empty else 0.0,
            "Líquido": cc["valor_liquido"].sum() if not cc.empty else 0.0,
            "Previsto": pp["bruto"].sum() if not pp.empty else 0.0,
        })
    res = pd.DataFrame(linhas).sort_values("Faturamento", ascending=False)

    m1, m2, m3 = st.columns(3)
    m1.metric("💵 Faturamento", formatar_brl_puro(res["Faturamento"].sum()))
    m2.metric("📦 Volume vendido", formatar_brl_puro(res["Volume vendido"].sum()))
    m3.metric("🔮 Previsto", formatar_brl_puro(res["Previsto"].sum()))

    st.dataframe(_tabela_brl(res, ["Volume vendido", "Ticket médio", "Faturamento",
                                   "Líquido", "Previsto"]),
                 use_container_width=True, hide_index=True)
    st.caption(f"Período: **{rotulo}**.")


# ==========================================================
# ABA 4 — POR VENDEDOR
# ==========================================================
def _aba_vendedor(com, df_vendas, prev, is_master):
    st.markdown("#### 👤 Por Vendedor")
    st.caption("**Faturamento gerado** = comissão que as cotas desse vendedor trouxeram. "
               "Breno/Uriel mostram como esse valor foi dividido entre os sócios.")

    meses = _meses_de((com, "ym"), (prev, "ym"), (df_vendas, "Data_Real"))
    if not meses:
        return _vazio("Sem dados para o relatório por vendedor.")
    yms, rotulo = _seletor_periodo("vend", meses)
    if not yms:
        return _vazio("Selecione ao menos um mês.")

    c = com[com["ym"].isin(yms)] if not com.empty else com
    p = prev[prev["ym"].isin(yms)] if not prev.empty else prev
    v = _filtra_vendas_por_mes(df_vendas, yms)

    vends = set()
    if not c.empty:
        vends |= set(c["vendedor"].astype(str).str.strip())
    if not p.empty:
        vends |= set(p["vendedor"].astype(str).str.strip())
    if not v.empty:
        vends |= set(v["VENDEDOR"].astype(str).str.strip())
    vends.discard("")
    if not vends:
        return _vazio(f"Nada encontrado em {rotulo}.")

    linhas = []
    for nome in sorted(vends):
        cc = c[c["vendedor"].astype(str).str.strip() == nome] if not c.empty else c
        pp = p[p["vendedor"].astype(str).str.strip() == nome] if not p.empty else p
        vv = v[v["VENDEDOR"].astype(str).str.strip() == nome] if not v.empty else v
        linha = {
            "Vendedor": nome,
            "Cotas vendidas": int(len(vv)) if not vv.empty else 0,
            "Volume vendido": vv["Valor_Numerico"].sum() if not vv.empty else 0.0,
            "Faturamento gerado": cc["valor_nota"].sum() if not cc.empty else 0.0,
            "Líquido": cc["valor_liquido"].sum() if not cc.empty else 0.0,
            "Previsto": pp["bruto"].sum() if not pp.empty else 0.0,
        }
        if is_master:
            linha["Breno"] = cc["breno"].sum() if not cc.empty else 0.0
            linha["Uriel"] = cc["uriel"].sum() if not cc.empty else 0.0
        linhas.append(linha)
    res = pd.DataFrame(linhas).sort_values("Faturamento gerado", ascending=False)

    cols = st.columns(4 if is_master else 3)
    cols[0].metric("💵 Faturamento gerado", formatar_brl_puro(res["Faturamento gerado"].sum()))
    cols[1].metric("📦 Volume vendido", formatar_brl_puro(res["Volume vendido"].sum()))
    cols[2].metric("🔮 Previsto", formatar_brl_puro(res["Previsto"].sum()))
    if is_master:
        cols[3].metric("👤 Breno / Uriel",
                       f"{formatar_brl_puro(res['Breno'].sum())} / "
                       f"{formatar_brl_puro(res['Uriel'].sum())}")

    moeda = ["Volume vendido", "Faturamento gerado", "Líquido", "Previsto"]
    if is_master:
        moeda += ["Breno", "Uriel"]
    st.dataframe(_tabela_brl(res, moeda), use_container_width=True, hide_index=True)
    st.caption(f"Período: **{rotulo}**.")


# ==========================================================
# ABA 5 — FATURAMENTO PREVISTO
# ==========================================================
def _aba_previsto(prev, site_prev):
    st.markdown("#### 🔮 Faturamento Previsto")
    st.caption("Comissões ainda **não recebidas** das cotas Em Andamento, projetadas pela "
               "regra de cada administradora, mais o ágio das cartas contempladas ainda "
               "em análise no Site.")

    sem_trad = prev is None or prev.empty
    sem_site = site_prev is None or site_prev.empty
    if sem_trad and sem_site:
        return _vazio("Nada previsto: não há cotas ativas com parcelas pendentes.")

    if not sem_trad:
        vencidas = prev[prev["atrasada"]]
        a_vencer = prev[~prev["atrasada"]]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔮 Total previsto", formatar_brl_puro(prev["bruto"].sum()))
        m2.metric("📅 A vencer", formatar_brl_puro(a_vencer["bruto"].sum()))
        m3.metric("⏰ Vencido s/ baixa", formatar_brl_puro(vencidas["bruto"].sum()))
        m4.metric("🧾 Parcelas", f"{len(prev)}")
        if not vencidas.empty:
            st.warning(f"⏰ {len(vencidas)} parcela(s) com data prevista já passada e ainda sem "
                       f"baixa ({formatar_brl_puro(vencidas['bruto'].sum())}). "
                       f"Pode ser NF ainda não importada — confira em Importar Comissões.")

        linhas = []
        for ym in sorted(prev["ym"].unique()):
            d = prev[prev["ym"] == ym]
            linhas.append({
                "Mês": _label_mes(ym), "Parcelas": int(len(d)),
                "Previsto": d["bruto"].sum(), "Líquido": d["liquido"].sum(),
                "Breno": d["breno"].sum(), "Uriel": d["uriel"].sum(),
                "Situação": "⏰ vencido" if d["atrasada"].all()
                            else ("parcial" if d["atrasada"].any() else "a vencer"),
            })
        res = pd.DataFrame(linhas)
        st.dataframe(_tabela_brl(res, ["Previsto", "Líquido", "Breno", "Uriel"]),
                     use_container_width=True, hide_index=True)

        st.altair_chart(
            alt.Chart(res).mark_bar().encode(
                x=alt.X("Mês:N", sort=list(res["Mês"]), title=None),
                y=alt.Y("Previsto:Q", title="R$"),
                tooltip=["Mês", "Parcelas", alt.Tooltip("Previsto:Q", format=",.2f")],
            ).properties(height=260), use_container_width=True)

        with st.expander("🔎 Detalhe parcela a parcela"):
            det = prev.sort_values(["ym", "data", "cliente"])
            st.dataframe(pd.DataFrame({
                "Mês": det["ym"].apply(_label_mes).values,
                "Vencimento": det["data"].values,
                "Cliente": det["cliente"].values,
                "Grupo/Cota": det["gc"].values,
                "Adm.": det["admin"].values,
                "Produto": det["produto"].values,
                "Parcela": det["parcela"].values,
                "Vendedor": det["vendedor"].values,
                "Previsto": det["bruto"].apply(formatar_brl_puro).values,
                "Breno": det["breno"].apply(formatar_brl_puro).values,
                "Uriel": det["uriel"].apply(formatar_brl_puro).values,
                "Situação": det["atrasada"].apply(
                    lambda x: "⏰ Vencida" if x else "A vencer").values,
            }), use_container_width=True, hide_index=True)

    if not sem_site:
        st.markdown("##### 🎯 Cartas Contempladas em análise (Site)")
        st.metric("Ágio previsto", formatar_brl_puro(site_prev["agio"].sum()))
        st.dataframe(pd.DataFrame({
            "Cliente": site_prev["cliente"].values,
            "Representante": site_prev["representante"].values,
            "Produto": site_prev["produto"].values,
            "Administradora": site_prev["administradora"].values,
            "Crédito": site_prev["credito_total"].apply(formatar_brl_puro).values,
            "Ágio previsto": site_prev["agio"].apply(formatar_brl_puro).values,
        }), use_container_width=True, hide_index=True)
        st.caption("Previsão — só vira faturamento quando a operação for concluída no Site.")


# ==========================================================
# ABA 6 — CARTAS CONTEMPLADAS (realizado)
# ==========================================================
def _aba_cartas(site_ok):
    st.markdown("#### 🎯 Cartas Contempladas")
    st.caption("Operações **concluídas** no admin do Site. A receita aqui é o **ágio** "
               "(valor ao cliente − valor ao cedente − custos + ajuste), dividido 50/50 "
               "entre os sócios. Hoje o ágio entra sem desconto de imposto.")
    if site_ok is None or site_ok.empty:
        return _vazio("Nenhuma operação de carta contemplada concluída "
                      "(ou a integração com o Site está desligada).")

    meses = _meses_de((site_ok, "ym"))
    if not meses:
        return _vazio("Operações concluídas sem data de conclusão registrada.")
    yms, rotulo = _seletor_periodo("cartas", meses)
    d = site_ok[site_ok["ym"].isin(yms)]
    if d.empty:
        return _vazio(f"Nenhuma carta concluída em {rotulo}.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎯 Ágio (receita)", formatar_brl_puro(d["agio"].sum()))
    m2.metric("💳 Crédito negociado", formatar_brl_puro(d["credito_total"].sum()))
    m3.metric("🧾 Operações", f"{len(d)}")
    m4.metric("📊 Ágio médio", formatar_brl_puro(d["agio"].mean() if len(d) else 0))

    por_mes = d.groupby("ym").agg(Operações=("agio", "count"), Ágio=("agio", "sum"),
                                  Crédito=("credito_total", "sum")).reset_index()
    por_mes["Mês"] = por_mes["ym"].apply(_label_mes)
    st.dataframe(_tabela_brl(por_mes, ["Ágio", "Crédito"],
                             ordem=["Mês", "Operações", "Crédito", "Ágio"]),
                 use_container_width=True, hide_index=True)

    with st.expander("🔎 Operações do período"):
        st.dataframe(pd.DataFrame({
            "Conclusão": d["data_conclusao"].values,
            "Cliente": d["cliente"].values,
            "Representante": d["representante"].values,
            "Produto": d["produto"].values,
            "Administradora": d["administradora"].values,
            "Crédito": d["credito_total"].apply(formatar_brl_puro).values,
            "Ágio": d["agio"].apply(formatar_brl_puro).values,
            "Breno": d["breno"].apply(formatar_brl_puro).values,
            "Uriel": d["uriel"].apply(formatar_brl_puro).values,
        }), use_container_width=True, hide_index=True)
    st.caption(f"Período: **{rotulo}**.")


# ==========================================================
# ABA 7 — PRODUÇÃO (volume vendido)
# ==========================================================
def _aba_producao(df_vendas):
    st.markdown("#### 📊 Produção (volume vendido)")
    st.caption("⚠️ Isto **não é faturamento** — é o crédito total das cotas vendidas, "
               "ou seja, o tamanho do negócio fechado no período.")
    if df_vendas is None or df_vendas.empty:
        return _vazio("Nenhuma venda cadastrada.")

    v = df_vendas[df_vendas["Data_Real"].notna()]
    if v.empty:
        return _vazio("Nenhuma venda com data válida.")

    meses = _meses_de((v, "Data_Real"))
    yms, rotulo = _seletor_periodo("prod_vol", meses)
    d = v[v["Data_Real"].dt.strftime("%Y-%m").isin(yms)]
    if d.empty:
        return _vazio(f"Nenhuma venda em {rotulo}.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📦 Volume vendido", formatar_brl_puro(d["Valor_Numerico"].sum()))
    m2.metric("🧾 Cotas", f"{len(d)}")
    m3.metric("📊 Ticket médio", formatar_brl_puro(d["Valor_Numerico"].mean()))
    m4.metric("👥 Clientes", f"{d['Nome do cliente'].nunique()}")

    por_mes = d.groupby(d["Data_Real"].dt.strftime("%Y-%m")).agg(
        Cotas=("Nome do cliente", "count"), Volume=("Valor_Numerico", "sum")).reset_index()
    por_mes.columns = ["ym", "Cotas", "Volume"]
    por_mes["Mês"] = por_mes["ym"].apply(_label_mes)
    st.dataframe(_tabela_brl(por_mes, ["Volume"], ordem=["Mês", "Cotas", "Volume"]),
                 use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Por status da cota**")
        s = d.groupby("STATUS").agg(Cotas=("Nome do cliente", "count"),
                                    Volume=("Valor_Numerico", "sum")).reset_index()
        st.dataframe(_tabela_brl(s, ["Volume"]), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Por produto**")
        pr = d.assign(PRODUTO=d["PRODUTO"].apply(lambda x: normalizar_produto(x) or "—")).groupby("PRODUTO").agg(Cotas=("Nome do cliente", "count"),
                                      Volume=("Valor_Numerico", "sum")).reset_index()
        st.dataframe(_tabela_brl(pr, ["Volume"]), use_container_width=True, hide_index=True)
    st.caption(f"Período: **{rotulo}**.")


# ==========================================================
# ABA 8 — COMISSIONAMENTO (fluxo de baixa, em tela cheia)
# ==========================================================
def _aba_comissionamento(df_vendas):
    st.markdown("#### 💰 Comissionamento detalhado")
    st.caption("Abre o relatório em tela cheia, onde dá para conferir parcela a parcela "
               "e dar baixa.")
    if df_vendas is None or df_vendas.empty:
        return _vazio("Nenhuma venda cadastrada.")
    periodo = st.selectbox("⏳ Período do relatório:",
                           ["Mês Atual", "Quinzena Atual", "Mês Anterior", "Ano Atual",
                            "Todas as Vendas", "Período Personalizado"], key="rel_com_per")
    ri = rf = None
    if periodo == "Período Personalizado":
        d1, d2 = st.columns(2)
        with d1:
            ri = st.date_input("Data Inicial", format="DD/MM/YYYY", key="rel_com_ini")
        with d2:
            rf = st.date_input("Data Final", format="DD/MM/YYYY", key="rel_com_fim")
    if st.button("Gerar Relatório Detalhado", type="primary"):
        st.session_state["tela_cheia_relatorio"] = True
        st.session_state["rel_periodo"] = periodo
        if periodo == "Período Personalizado":
            st.session_state["rel_dt_ini"], st.session_state["rel_dt_fim"] = ri, rf
        st.rerun()


# ==========================================================
# TELA PRINCIPAL
# ==========================================================
def render_relatorios(supabase, df_vendas_global, df_admin, cfg, status_dict):
    st.markdown("### 📑 Relatórios Gerenciais")

    is_master = (st.session_state.get("perfil_logado") == "Master") or \
                (st.session_state.get("usuario_logado") in ["breno", "uriel"])
    nome_vendedor = st.session_state.get("nome_vendedor", "")

    com = _enriquecer_com_venda(_carregar_comissoes(supabase), df_vendas_global)
    prev, avisos_prev = _previsto(df_vendas_global, df_admin, cfg, status_dict)
    site_ok, site_prev = _cartas_site()
    vendas = df_vendas_global

    if not is_master:
        # vendedor só enxerga o que é dele; não vê sócios nem cartas do Site
        if com is not None and not com.empty:
            com = com[com["vendedor"] == nome_vendedor]
        if not prev.empty:
            prev = prev[prev["vendedor"] == nome_vendedor]
        if vendas is not None and not vendas.empty:
            vendas = vendas[vendas["VENDEDOR"] == nome_vendedor]
        site_ok, site_prev = pd.DataFrame(), pd.DataFrame()
        st.info("🔒 Como Vendedor, você vê apenas os relatórios das suas próprias vendas.")

    if com is None:
        com = pd.DataFrame()

    # Problemas de cadastro que distorcem os números — mostrar, não esconder.
    for a in avisos_prev:
        st.warning(f"⚠️ {a}")
    dups = cotas_duplicadas(df_vendas_global)
    if dups and is_master:
        st.warning("⚠️ Cota(s) cadastrada(s) mais de uma vez em Vendas: "
                   + ", ".join(sorted(dups))
                   + ". A previsão conta cada uma só uma vez, mas convém apagar a repetida.")

    abas = ["💵 Faturamento por Mês", "🏢 Administradora", "📦 Produto", "👤 Vendedor",
            "🔮 Previsto", "🎯 Cartas Contempladas", "📊 Produção", "💰 Comissionamento"]
    t = st.tabs(abas)
    with t[0]:
        _aba_faturamento_mes(com, site_ok, prev)
    with t[1]:
        _aba_administradora(com, vendas, prev)
    with t[2]:
        _aba_produto(com, vendas, prev)
    with t[3]:
        _aba_vendedor(com, vendas, prev, is_master)
    with t[4]:
        _aba_previsto(prev, site_prev)
    with t[5]:
        _aba_cartas(site_ok)
    with t[6]:
        _aba_producao(vendas)
    with t[7]:
        _aba_comissionamento(vendas)
