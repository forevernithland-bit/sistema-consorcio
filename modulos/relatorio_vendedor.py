"""Relatórios simplificados do VENDEDOR + simulação de comissionamento (vendedor e master).

Vendedor: (1) comissionamento previsto do mês, com grupo/cota, cliente, parcela e percentual,
e as vendas de Carta Contemplada em seção separada; (2) simulação do que vai receber.
Master: a mesma simulação, com o lado da Consorbens (o que fica após pagar o vendedor)."""
from datetime import datetime

import pandas as pd
import streamlit as st

import comissao_vendedor as cv
from escopo import norm
from modulos.producao_vendedor import extrato
from utils import formatar_brl_puro, parse_float_safe

_MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
          "Outubro", "Novembro", "Dezembro"]


def _brl(v):
    return formatar_brl_puro(v)


def _pct(x):
    return "" if x is None or pd.isna(x) else f"{x:.2f}%".replace(".", ",")


def _rot_mes(ym):
    return f"{_MESES[int(ym[5:7])]}/{ym[:4]}"


def _contempladas_do_mes(df_vendas, nome, ym):
    """Vendas de Carta Contemplada do vendedor no mês (ERP + operações do Site em que ele é o representante)."""
    linhas = []
    if df_vendas is not None and not df_vendas.empty and "TIPO_PRODUTO" in df_vendas.columns:
        d = df_vendas[(df_vendas["VENDEDOR"].apply(norm) == norm(nome)) & df_vendas["Data_Real"].notna()]
        d = d[d["TIPO_PRODUTO"].apply(norm).str.replace(" ", "") == "CONSORCIOCONTEMPLADO"]
        d = d[d["Data_Real"].dt.strftime("%Y-%m") == ym]
        for _, r in d.iterrows():
            linhas.append({"Tipo": "🎯 CARTA CONTEMPLADA", "Cliente": r.get("Nome do cliente", ""),
                           "Grupo/Cota": f"{r.get('GRUPO', '')}/{r.get('COTA', '')}",
                           "Administradora": r.get("ADMINISTRADORA", ""), "Crédito": _brl(r.get("Valor_Numerico", 0)),
                           "Situação": r.get("STATUS", ""), "Data": r["Data_Real"].strftime("%d/%m/%Y")})
    try:
        from modulos.integracao_site import carregar_operacoes_site
        s = carregar_operacoes_site()
    except Exception:
        s = None
    if s is not None and not s.empty and "representante" in s.columns:
        s = s[s["representante"].apply(norm) == norm(nome)]
        for _, r in s.iterrows():
            dv = str(r.get("data_venda") or r.get("data_conclusao") or "")[:7]
            if dv != ym:
                continue
            data = str(r.get("data_venda") or r.get("data_conclusao") or "")[:10]
            try:
                data = datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m/%Y")
            except ValueError:
                pass
            linhas.append({"Tipo": "🎯 CARTA CONTEMPLADA", "Cliente": r.get("cliente", ""),
                           "Grupo/Cota": r.get("grupo_cota", "—"), "Administradora": r.get("administradora", ""),
                           "Crédito": _brl(r.get("credito_total", 0)), "Situação": r.get("status_label", ""),
                           "Data": data})
    return pd.DataFrame(linhas)


def _aba_comissionamento_mes(df_vendas, df_admin, cfg, status_dict, nome):
    hoje = datetime.today()
    ym_atual = f"{hoje.year:04d}-{hoje.month:02d}"
    t, sem_data = extrato(df_vendas, df_admin, cfg, status_dict, nome)
    meses = {ym_atual}
    if not t.empty:
        meses |= set(pd.to_datetime(t["data_pagamento_dt"]).dt.strftime("%Y-%m"))
    meses = sorted(meses, reverse=True)
    ym = st.selectbox("Mês", meses, index=meses.index(ym_atual),      # abre no mês atual
                      format_func=lambda m: _rot_mes(m) + ("  (mês atual)" if m == ym_atual else ""),
                      key="rv_mes")

    st.markdown(f"#### 💵 Comissionamento previsto — {_rot_mes(ym)}")
    st.caption("Cotas vendidas por você que entram no seu comissionamento neste mês, com a parcela da comissão e o percentual.")
    if sem_data:
        st.warning("Cota(s) cancelada(s) sem data de cancelamento (o estorno só é calculado depois que o "
                   "administrador informar a data): " + ", ".join(sem_data))

    dm = t[pd.to_datetime(t["data_pagamento_dt"]).dt.strftime("%Y-%m") == ym] if not t.empty else t
    if dm is None or dm.empty:
        st.info("Nenhuma comissão prevista para este mês.")
    else:
        dm = dm.sort_values(["Data Recebimento", "Grupo", "Cota"])
        eh_est = dm["Tipo Vendedor"].astype(str) == "Estorno"
        pago = dm["Status"].astype(str).str.upper() == "PAGO"
        c1, c2, c3 = st.columns(3)
        c1.metric("Comissão do mês", _brl(dm[~eh_est]["Vendedor Recebe"].sum()))
        c2.metric("Estornos do mês", _brl(dm[eh_est]["Vendedor Recebe"].sum()))
        c3.metric("Total a receber no mês", _brl(dm["Vendedor Recebe"].sum()))
        st.dataframe(pd.DataFrame({
            "Grupo": dm["Grupo"].astype(str).values, "Cota": dm["Cota"].astype(str).values,
            "Cliente": dm["Cliente"].values,
            "Tipo": dm["Tipo Vendedor"].values,
            "Parcela": dm["Parcela Vendedor"].values,
            "%": [_pct(x) for x in dm["% Vendedor"]],
            "Valor": [_brl(x) for x in dm["Vendedor Recebe"]],
            "Parc. adm.": ["" if str(x).startswith("Estorno") else x for x in dm["Parcela"]],
            "Referência": dm["Referência"].values,
            "Data": dm["Data Recebimento"].values,
            "Situação": ["Pago" if p else "Previsto" for p in pago],
        }), use_container_width=True, hide_index=True)

    # ---- Cartas Contempladas: seção separada ----
    st.markdown(
        "<div style='margin-top:26px;padding:10px 16px;border-radius:10px;background:#fff4d6;"
        "border-left:6px solid #e0a100;font-weight:800;font-size:1.05rem'>🎯 CARTA CONTEMPLADA — vendas do mês</div>",
        unsafe_allow_html=True)
    cc = _contempladas_do_mes(df_vendas, nome, ym)
    if cc.empty:
        st.caption("Nenhuma venda de Carta Contemplada neste mês.")
    else:
        st.dataframe(cc, use_container_width=True, hide_index=True)
        st.caption("Vendas de Carta Contemplada não entram na regra de comissionamento acima.")


# ==========================================================================
# SIMULAÇÃO
# ==========================================================================
def _regra_admin(df_admin, adm, prod, tipo):
    if df_admin is None or df_admin.empty:
        return None
    d = df_admin[(df_admin["Administradora"] == adm) & (df_admin["Produto"] == prod)]
    if "Tipo_Parcela" in d.columns and tipo is not None:
        d2 = d[d["Tipo_Parcela"].fillna("").astype(str) == tipo]
        d = d2 if not d2.empty else d
    if d.empty:
        return None
    row = d.iloc[0]
    return {i: parse_float_safe(row.get(f"P{i}", 0)) for i in range(1, 26) if parse_float_safe(row.get(f"P{i}", 0)) > 0}


def render_simulacao(df_admin, cfg, master=False):
    """Simulador de comissionamento: todo o visual/UX vive em modulos/simulador_comissao_ui.py."""
    from modulos.simulador_comissao_ui import render_simulador
    render_simulador(df_admin, cfg, master=master)


def _aba_proximos_meses(df_vendas, df_admin, cfg, status_dict, nome):
    """Comissionamento previsto dos próximos meses (cotas já vendidas), com estornos/abatimentos e o cliente de cada linha."""
    hoje = datetime.today()
    ym_atual = f"{hoje.year:04d}-{hoje.month:02d}"
    st.markdown("#### 📆 Comissionamento previsto — próximos meses")
    n = st.radio("Período", [3, 6, 12], index=1, horizontal=True, key="rv_horizonte",
                 format_func=lambda x: f"{x} meses (a partir deste mês)")
    meses = [cv._soma_meses(ym_atual, i) for i in range(n)]

    t, sem_data = extrato(df_vendas, df_admin, cfg, status_dict, nome)
    if sem_data:
        st.warning("Cota(s) cancelada(s) sem data de cancelamento (o estorno só é calculado depois que o "
                   "administrador informar a data): " + ", ".join(sem_data))
    if t.empty:
        st.info("Ainda não há comissões previstas.")
        return
    t = t.assign(_ym=pd.to_datetime(t["data_pagamento_dt"]).dt.strftime("%Y-%m"))
    d = t[t["_ym"].isin(meses) & (t["Status"].astype(str).str.upper() != "PAGO")].copy()
    if d.empty:
        st.info("Nenhuma comissão prevista para este período.")
        return
    d["_tipo"] = d["Tipo Vendedor"].astype(str)

    resumo = []
    for ym in meses:
        x = d[d["_ym"] == ym]
        resumo.append({
            "Mês": _rot_mes(ym),
            "Comissão": _brl(x[x["_tipo"] == "Comissão"]["Vendedor Recebe"].sum()),
            "Bônus": _brl(x[x["_tipo"] == "Bônus"]["Vendedor Recebe"].sum()),
            "Estornos (abatimento)": _brl(x[x["_tipo"] == "Estorno"]["Vendedor Recebe"].sum()),
            "Total do mês": _brl(x["Vendedor Recebe"].sum()),
            "Lançamentos": len(x),
        })
    c1, c2, c3 = st.columns(3)
    c1.metric("Comissão + bônus previstos", _brl(d[d["_tipo"] != "Estorno"]["Vendedor Recebe"].sum()))
    c2.metric("Estornos previstos", _brl(d[d["_tipo"] == "Estorno"]["Vendedor Recebe"].sum()))
    c3.metric("Total líquido previsto", _brl(d["Vendedor Recebe"].sum()))
    st.dataframe(pd.DataFrame(resumo), use_container_width=True, hide_index=True)

    est = d[d["_tipo"] == "Estorno"].sort_values(["_ym", "Cliente"])
    if not est.empty:
        st.markdown(
            "<div style='margin-top:14px;padding:10px 16px;border-radius:10px;background:#fde8e8;"
            "border-left:6px solid #d93025;font-weight:800'>🔻 ESTORNOS / ABATIMENTOS PREVISTOS</div>",
            unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({
            "Mês": [_rot_mes(m) for m in est["_ym"]], "Cliente": est["Cliente"].values,
            "Grupo": est["Grupo"].astype(str).values, "Cota": est["Cota"].astype(str).values,
            "Parcela do estorno": est["Parcela Vendedor"].values, "%": [_pct(x) for x in est["% Vendedor"]],
            "Valor": [_brl(x) for x in est["Vendedor Recebe"]],
            "Motivo": est["Referência"].values,
        }), use_container_width=True, hide_index=True)

    st.markdown("##### 🔎 Detalhe mês a mês")
    d = d.sort_values(["_ym", "Cliente", "Grupo", "Cota"])
    st.dataframe(pd.DataFrame({
        "Mês": [_rot_mes(m) for m in d["_ym"]],
        "Cliente": d["Cliente"].values,
        "Grupo": d["Grupo"].astype(str).values, "Cota": d["Cota"].astype(str).values,
        "Tipo": ["🔻 Estorno" if x == "Estorno" else x for x in d["_tipo"]],
        "Parcela": d["Parcela Vendedor"].values,
        "%": [_pct(x) for x in d["% Vendedor"]],
        "Valor": [_brl(x) for x in d["Vendedor Recebe"]],
        "Parc. adm.": ["" if str(x).startswith("Estorno") else x for x in d["Parcela"]],
        "Referência": d["Referência"].values,
        "Data": d["Data Recebimento"].values,
    }), use_container_width=True, hide_index=True)
    st.caption("Previsão das cotas que você já vendeu. Vendas novas e bônus de produção que ainda não aconteceram "
               "não entram aqui — use a aba de Simulação para isso.")


def render_relatorio_vendedor(df_vendas, df_admin, cfg, status_dict, nome):
    t1, t3, t4, t2 = st.tabs(["💵 Comissionamento previsto do mês", "📆 Próximos meses", "💳 Meus pagamentos",
                              "🧮 Simulação de comissionamento"])
    with t4:
        try:        # um problema nesta aba não pode derrubar as demais abas do vendedor
            from database import iniciar_conexao
            from modulos.meus_pagamentos import render_meus_pagamentos
            render_meus_pagamentos(iniciar_conexao())
        except Exception:
            st.error("Não consegui carregar seus pagamentos agora. Tente de novo em instantes.")
    with t1:
        _aba_comissionamento_mes(df_vendas, df_admin, cfg, status_dict, nome)
    with t3:
        _aba_proximos_meses(df_vendas, df_admin, cfg, status_dict, nome)
    with t2:
        render_simulacao(df_admin, cfg, master=False)
