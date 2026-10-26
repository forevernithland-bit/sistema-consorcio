"""Produção mensal, nível de comissão e extrato (com estorno) de UM vendedor.

Usada no Dashboard do vendedor e, para o administrador, no relatório "Por Vendedor".
Toda linha de cota mostra GRUPO e COTA. A regra está em comissao_vendedor.py."""
from datetime import datetime

import pandas as pd
import streamlit as st

import comissao_vendedor as cv
from regras import gerar_tabela_parcelas, _gc
from utils import formatar_brl_puro

_NOMES_NIVEL = ["Base", "Bônus 1", "Bônus 2"]


def _brl(v):
    return formatar_brl_puro(v)


def _pct(x):
    return f"{x:.2f}%".replace(".", ",")


def _vendas_do_vendedor(df_vendas, vendedor):
    if df_vendas is None or df_vendas.empty or cv.norm(vendedor) in ("", "NAN", "NONE"):
        return pd.DataFrame()           # vendedor sem nome nunca herda as vendas "sem vendedor"
    d = df_vendas[df_vendas["VENDEDOR"].apply(cv.norm) == cv.norm(vendedor)]
    return d[d["Data_Real"].notna()] if not d.empty else d


def resumo_meses(df_vendas, vendedor, cfg):
    """Uma linha por mês com venda: Mês (aaaa-mm), Cotas, Produção, Nível, % total."""
    d = _vendas_do_vendedor(df_vendas, vendedor)
    if d.empty:
        return pd.DataFrame(columns=["ym", "Cotas", "Produção", "Nível", "% total"])
    r = cv.regra(cfg)
    linhas = []
    for (a, m), _ in d.groupby([d["Data_Real"].dt.year, d["Data_Real"].dt.month]):
        dm = cv.vendas_do_mes(df_vendas, vendedor, a, m)
        vol = float(dm["Valor_Numerico"].sum()) if not dm.empty else 0.0
        n = cv.nivel(vol, r)
        linhas.append({"ym": f"{int(a):04d}-{int(m):02d}", "Cotas": len(dm), "Produção": vol,
                       "Nível": _NOMES_NIVEL[n], "% total": sum(cv.percentuais_por_posicao(vol, cfg))})
    return pd.DataFrame(linhas).sort_values("ym", ascending=False).reset_index(drop=True)


def _sem_cota_duplicada(d):
    """Mesma cota (grupo/cota) cadastrada duas vezes: fica uma só (a mais recente, igual à previsão do Financeiro),
    senão o extrato do vendedor dobraria a comissão e o estorno dessa cota."""
    if d.empty or "GRUPO" not in d.columns or "COTA" not in d.columns:
        return d
    gc = pd.Series([f"{_gc(g)}/{_gc(c)}" for g, c in zip(d["GRUPO"], d["COTA"])], index=d.index)
    ordenado = d.assign(_gc=gc).sort_values("Data_Real", na_position="first", kind="stable")
    dup = ordenado["_gc"].duplicated(keep="last") & (ordenado["_gc"] != "/")
    return ordenado[~dup].drop(columns="_gc").sort_index()


def extrato(df_vendas, df_admin, cfg, status_dict, vendedor):
    """Parcelas de comissão do vendedor (inclui linhas de estorno, negativas)."""
    d = _vendas_do_vendedor(df_vendas, vendedor)
    if d.empty:
        return pd.DataFrame(), []
    d = _sem_cota_duplicada(d)
    t, _ = gerar_tabela_parcelas(d, df_vendas, df_admin, cfg, status_dict)
    if t.empty:
        return t, []
    t = t[t["Vendedor Recebe"] != 0].copy()
    sem_data_canc = [f"{r['GRUPO']}/{r['COTA']}" for _, r in d.iterrows()
                     if str(r.get("STATUS", "")).strip() == "Cancelada"
                     and pd.isna(cv.data_cancelamento(r.get("DATA_CANCELAMENTO")))]
    return t, sem_data_canc


def render_producao_vendedor(df_vendas, df_admin, cfg, status_dict, vendedor, chave="pv"):
    r = cv.regra(cfg)
    hoje = datetime.today()
    ym_atual = f"{hoje.year:04d}-{hoje.month:02d}"

    from modulos.tema import secao; secao(f"Produção mensal — {vendedor}", "🎯", "Seu volume do mês, nível de comissão e quanto falta para o próximo bônus.")
    hist = resumo_meses(df_vendas, vendedor, cfg)
    meses = [ym_atual] + [m for m in hist["ym"].tolist() if m != ym_atual]
    meses = sorted(set(meses), reverse=True)

    def _rot(ym):
        a, m = ym.split("-")
        return f"{m}/{a}" + ("  (mês atual)" if ym == ym_atual else "")

    sel = st.selectbox("Mês", meses, format_func=_rot, key=f"{chave}_mes")
    ano, mes = int(sel[:4]), int(sel[5:])
    dm = cv.vendas_do_mes(df_vendas, vendedor, ano, mes)
    vol = float(dm["Valor_Numerico"].sum()) if not dm.empty else 0.0
    n = cv.nivel(vol, r)
    pcts = cv.percentuais_por_posicao(vol, cfg)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📦 Produção do mês", _brl(vol))
    c2.metric("🧾 Cotas vendidas", f"{len(dm)}")
    c3.metric("🏅 Nível", _NOMES_NIVEL[n])
    c4.metric("💰 Comissão sobre a carta", _pct(sum(pcts)))

    if n == 0:
        alvo, bonus, rot = r["VD_M1"], r["VD_M1_P3"], "Bônus 1"
    elif n == 1:
        alvo, bonus, rot = r["VD_M2"], r["VD_M2_P4"], "Bônus 2"
    else:
        alvo = None
    if alvo:
        falta = max(alvo - vol, 0.0)
        st.progress(min(vol / alvo, 1.0))
        st.caption((f"Faltam **{_brl(falta + 0.01)}** para passar de {_brl(alvo)} e liberar o {rot} "
                    f"(+{_pct(bonus)} do crédito).").replace("$", "\\$"))   # '$' cru vira LaTeX no Markdown
    else:
        st.success("🏆 Nível máximo do mês atingido.")
    st.caption("Pagamento por posição: " + " · ".join(f"{i + 1}º pagamento {_pct(p)}" for i, p in enumerate(pcts))
               + ". A produção zera a cada mês — o nível vale para todas as cotas vendidas naquele mês.")

    if dm.empty:
        st.info("Nenhuma venda neste mês.")
    else:
        view = pd.DataFrame({
            "Grupo": dm["GRUPO"].astype(str).values, "Cota": dm["COTA"].astype(str).values,
            "Cliente": dm["Nome do cliente"].values,
            "Administradora": dm["ADMINISTRADORA"].values, "Produto": dm["PRODUTO"].values,
            "Valor": [_brl(x) for x in dm["Valor_Numerico"]],
            "Data": [x.strftime("%d/%m/%Y") for x in dm["Data_Real"]],
            "Status": dm["STATUS"].fillna("").values,
        })
        st.dataframe(view, use_container_width=True, hide_index=True)

    with st.expander("📅 Produção dos meses anteriores", expanded=False):
        if hist.empty:
            st.caption("Sem histórico.")
        else:
            h = pd.DataFrame({"Mês": [_rot(m).replace("  (mês atual)", "") for m in hist["ym"]],
                              "Cotas": hist["Cotas"], "Produção": [_brl(x) for x in hist["Produção"]],
                              "Nível": hist["Nível"], "% da carta": [_pct(x) for x in hist["% total"]]})
            st.dataframe(h, use_container_width=True, hide_index=True)

    with st.expander("💵 Extrato de comissão (parcelas e estornos)", expanded=False):
        t, sem_data = extrato(df_vendas, df_admin, cfg, status_dict, vendedor)
        if sem_data:
            st.warning("Cota(s) cancelada(s) sem data de cancelamento — o estorno só é calculado depois que o "
                       "administrador informar a data: " + ", ".join(sem_data))
        if t.empty:
            st.caption("Ainda não há parcelas de comissão.")
        else:
            t = t.sort_values(["data_pagamento_dt", "Grupo", "Cota"])
            eh_est = t["Tipo Vendedor"].astype(str) == "Estorno"
            pago = t["Status"].astype(str).str.upper() == "PAGO"
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Já pago", _brl(t[~eh_est & pago]["Vendedor Recebe"].sum()))
            m2.metric("A receber", _brl(t[~eh_est & ~pago]["Vendedor Recebe"].sum()))
            m3.metric("Estornos a abater", _brl(t[eh_est & ~pago]["Vendedor Recebe"].sum()))
            m4.metric("Saldo a receber", _brl(t[~pago]["Vendedor Recebe"].sum()))
            st.caption("Estorno: cota cancelada em até 5 meses da venda devolve 0,5% do crédito, em 2 parcelas de 0,25% "
                       "abatidas nos próximos 2 pagamentos de comissão do vendedor.")
            st.dataframe(pd.DataFrame({
                "Grupo": t["Grupo"].astype(str).values, "Cota": t["Cota"].astype(str).values,
                "Cliente": t["Cliente"].values,
                "Tipo": t["Tipo Vendedor"].values,
                "Parcela": t["Parcela Vendedor"].values,
                "%": [("" if pd.isna(x) or x is None else f"{x:.2f}%".replace(".", ",")) for x in t["% Vendedor"]],
                "Valor": [_brl(x) for x in t["Vendedor Recebe"]],
                "Parc. adm.": ["" if str(x).startswith("Estorno") else x for x in t["Parcela"]],
                "Referência": t["Referência"].values,
                "Data": t["Data Recebimento"].values, "Status": t["Status"].values,
                "Valor da carta": [_brl(x) for x in t["Valor da Venda"]],
            }), use_container_width=True, hide_index=True)
