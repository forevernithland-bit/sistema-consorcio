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
    st.markdown("#### 🧮 Simulação de comissionamento")
    st.caption("Informe quanto será vendido por mês e veja a comissão prevista, mês a mês, já com os prêmios de "
               "superação (bônus de produção) definidos no sistema.")
    r = cv.regra(cfg)
    hoje = datetime.today()
    ym0 = f"{hoje.year:04d}-{hoje.month:02d}"

    c1, c2 = st.columns([2, 1])
    with c1:
        txt = st.text_input("Valor vendido por mês (R$)", value="600.000", key="sim_valor")
        valor = cv.parse_brl(txt, None)
        if valor is None or valor < 0:
            st.error("Digite um valor válido, por exemplo 600.000.")
            return
    with c2:
        n_meses = int(st.number_input("Meses de venda", min_value=1, max_value=12, value=1, step=1, key="sim_meses"))
    meses_venda = [cv._soma_meses(ym0, i) for i in range(n_meses)]
    vendas = [(m, valor) for m in meses_venda]
    if n_meses > 1 and st.checkbox("Informar um valor diferente em cada mês", key="sim_difere"):
        ed = st.data_editor(pd.DataFrame({"Mês": [_rot_mes(m) for m in meses_venda], "Vendido (R$)": [float(valor)] * n_meses}),
                            hide_index=True, disabled=["Mês"], use_container_width=True, key="sim_editor")
        vendas = [(m, (0.0 if v is None or pd.isna(v) else max(float(v), 0.0))) for m, v in zip(meses_venda, ed["Vendido (R$)"])]   # célula em branco = 0

    regra_adm, imposto = None, parse_float_safe(cfg.get("Imposto", 7.16))
    if master:
        if df_admin is not None and not df_admin.empty:
            a1, a2, a3 = st.columns(3)
            adm = a1.selectbox("Administradora", sorted(df_admin["Administradora"].dropna().unique()), key="sim_adm")
            prods = sorted(df_admin[df_admin["Administradora"] == adm]["Produto"].dropna().unique())
            prod = a2.selectbox("Produto", prods, key="sim_prod")
            sub = df_admin[(df_admin["Administradora"] == adm) & (df_admin["Produto"] == prod)]
            tipos = sorted(sub["Tipo_Parcela"].fillna("").astype(str).unique()) if "Tipo_Parcela" in sub.columns else [""]
            tipo = a3.selectbox("Tipo de parcela", tipos, format_func=lambda x: x or "(padrão)", key="sim_tipo") if len(tipos) > 1 else tipos[0]
            regra_adm = _regra_admin(df_admin, adm, prod, tipo)
            if not regra_adm:
                st.warning("Esta combinação não tem comissão cadastrada na administradora; só o lado do vendedor será simulado.")
        else:
            st.info("Sem regras de administradora cadastradas: só o lado do vendedor será simulado.")

    por_mes, niveis = cv.simular(vendas, cfg, regra_adm, imposto)
    if por_mes.empty:
        st.info("Informe um valor de venda maior que zero.")
        return

    total_vend = por_mes["Total vendedor"].sum()
    m = st.columns(4 if master and regra_adm else 3)
    m[0].metric("💰 Comissão total do vendedor", _brl(total_vend))
    m[1].metric("📦 Vendido no período", _brl(sum(v for _, v in vendas)))
    m[2].metric("🏅 % sobre o vendido", _pct(total_vend / max(sum(v for _, v in vendas), 1) * 100))
    if master and regra_adm:
        m[3].metric("🏢 Consorbens recebe (após vendedor)", _brl(por_mes["Consorbens (após vendedor)"].sum()))

    # --- prêmios de superação por mês de venda
    st.markdown("##### 🏆 Prêmios de superação")
    st.caption(f"Bônus 1: produção do mês acima de {_brl(r['VD_M1'])} (+{_pct(r['VD_M1_P3'])} no 3º pagamento). "
               f"Bônus 2: acima de {_brl(r['VD_M2'])} (+{_pct(r['VD_M2_P4'])} no 4º pagamento, somando ao Bônus 1).")
    nv = niveis.copy()
    nv["Mês de venda"] = nv["ym"].apply(_rot_mes)
    st.dataframe(pd.DataFrame({
        "Mês de venda": nv["Mês de venda"], "Vendido": [_brl(x) for x in nv["Vendido"]], "Nível": nv["Nível"],
        "% total": [_pct(x) for x in nv["% total"]],
        "Para o próximo prêmio": [("—" if f == 0 else f"vender mais {_brl(f)} → {p}") for f, p in zip(nv["Falta p/ próximo"], nv["Próximo"])],
    }), use_container_width=True, hide_index=True)

    # --- mês a mês
    st.markdown("##### 📅 Comissão prevista mês a mês")
    pm = por_mes.copy()
    pm["Acumulado"] = pm["Total vendedor"].cumsum()
    cols = {"Mês": pm["ym"].apply(_rot_mes), "Comissão base": [_brl(x) for x in pm["Comissão base"]],
            "Prêmio (bônus)": [_brl(x) for x in pm["Bônus"]], "Total do mês": [_brl(x) for x in pm["Total vendedor"]],
            "Acumulado": [_brl(x) for x in pm["Acumulado"]]}
    if master and regra_adm:
        cols.update({"Comissão bruta (adm.)": [_brl(x) for x in pm["Comissão bruta (adm.)"]],
                     "Imposto": [_brl(x) for x in pm["Imposto"]],
                     "Líquido corretora": [_brl(x) for x in pm["Líquido corretora"]],
                     "Consorbens (após vendedor)": [_brl(x) for x in pm["Consorbens (após vendedor)"]]})
    st.dataframe(pd.DataFrame(cols), use_container_width=True, hide_index=True)
    st.bar_chart(pd.DataFrame({"Comissão base": pm["Comissão base"].values, "Prêmio (bônus)": pm["Bônus"].values},
                              index=pm["ym"].apply(_rot_mes).values))

    if master and regra_adm:
        liq = por_mes["Líquido corretora"].sum()
        sobra = por_mes["Consorbens (após vendedor)"].sum()
        st.markdown("##### 🏢 O que a Consorbens recebe com essa produção")
        k = st.columns(5)
        k[0].metric("Comissão bruta (adm.)", _brl(por_mes["Comissão bruta (adm.)"].sum()))
        k[1].metric("Imposto", _brl(por_mes["Imposto"].sum()))
        k[2].metric("Líquido da corretora", _brl(liq))
        k[3].metric("Pago ao vendedor", _brl(total_vend))
        k[4].metric("Fica com a Consorbens", _brl(sobra))
        st.caption(f"A Consorbens fica com {_brl(sobra)} após pagar o vendedor "
                   f"(Breno {_brl(sobra / 2)} e Uriel {_brl(sobra / 2)}, divisão 50/50 da sobra).")
    st.caption("Premissas: a parcela i da administradora é paga no mês da venda + (i − 1) meses; o vendedor recebe nos "
               "pagamentos 1º, 2º, 3º e 4º da administradora. Sem a regra da administradora, o 1º pagamento do vendedor "
               "cai no mês da venda e os demais um por mês. Valores previstos, sem estornos.")


def render_relatorio_vendedor(df_vendas, df_admin, cfg, status_dict, nome):
    t1, t2 = st.tabs(["💵 Comissionamento previsto do mês", "🧮 Simulação de comissionamento"])
    with t1:
        _aba_comissionamento_mes(df_vendas, df_admin, cfg, status_dict, nome)
    with t2:
        render_simulacao(df_admin, cfg, master=False)
