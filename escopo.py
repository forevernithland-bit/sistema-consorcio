"""
Escopo de dados do usuário logado: o Administrador (Master) enxerga tudo; o
Vendedor enxerga SÓ o que é dele — as vendas/cotas em que ele é o vendedor.

Toda tela que lista dados de clientes, vendas, lances, boletos ou relatórios
passa os dados por aqui, em vez de repetir o filtro por nome em cada módulo
(foi assim que uma lista esquecia o filtro). A comparação ignora maiúscula,
acento e espaço sobrando.
"""
import unicodedata

import pandas as pd
import streamlit as st

from regras import _gc


def eh_master() -> bool:
    return (st.session_state.get("perfil_logado") == "Master") or \
           (st.session_state.get("usuario_logado") in ["breno", "uriel"])


def nome_logado() -> str:
    return str(st.session_state.get("nome_vendedor") or "")


def norm(s) -> str:
    """Nome comparável: sem acento, maiúsculo, espaços únicos."""
    t = unicodedata.normalize("NFD", str(s if s is not None else ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.upper().split())


def eh_meu(nome_vendedor_do_registro, nome=None) -> bool:
    return norm(nome_vendedor_do_registro) == norm(nome if nome is not None else nome_logado())


def filtrar_por_vendedor(df, coluna, eh_adm=None, nome=None):
    """DataFrame só com as linhas do vendedor logado (Master: tudo)."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    if (eh_master() if eh_adm is None else eh_adm):
        return df
    if coluna not in df.columns:
        return df.iloc[0:0]          # sem a coluna não dá para provar que é dele: não mostra
    alvo = norm(nome if nome is not None else nome_logado())
    return df[df[coluna].apply(norm) == alvo]


def cotas_do_vendedor(df_vendas, nome=None) -> set:
    """Conjunto 'grupo/cota' das cotas em que o vendedor é o dele."""
    if df_vendas is None or df_vendas.empty or "VENDEDOR" not in df_vendas.columns:
        return set()
    alvo = norm(nome if nome is not None else nome_logado())
    meu = df_vendas[df_vendas["VENDEDOR"].apply(norm) == alvo]
    return {f"{_gc(r.get('GRUPO'))}/{_gc(r.get('COTA'))}" for _, r in meu.iterrows()}


def filtrar_fila(df_fila, df_vendas, eh_adm=None, nome=None):
    """Pedidos de lance/boleto (fila_automacao) só das cotas do vendedor.
    Vale a COTA (grupo/cota) — não depende de o campo 'vendedor' do pedido estar
    escrito igual — ou o pedido ter sido feito em nome dele."""
    if df_fila is None or df_fila.empty:
        return df_fila
    if (eh_master() if eh_adm is None else eh_adm):
        return df_fila
    minhas = cotas_do_vendedor(df_vendas, nome)
    alvo = norm(nome if nome is not None else nome_logado())

    def meu(r):
        if f"{_gc(r.get('grupo'))}/{_gc(r.get('cota'))}" in minhas:
            return True
        return "vendedor" in r and norm(r.get("vendedor")) == alvo and alvo != ""
    return df_fila[df_fila.apply(meu, axis=1)]


def preencher_cliente(df_fila, df_vendas):
    """Pedidos sem nome de cliente (ex.: boletos mensais do robô) recebem o nome da venda."""
    if df_fila is None or df_fila.empty or df_vendas is None or df_vendas.empty:
        return df_fila
    if "Nome do cliente" not in df_vendas.columns:
        return df_fila
    mapa = {}
    for _, r in df_vendas.iterrows():
        mapa[f"{_gc(r.get('GRUPO'))}/{_gc(r.get('COTA'))}"] = r.get("Nome do cliente")
    df = df_fila.copy()
    if "cliente" not in df.columns:
        df["cliente"] = None

    def _nome(r):
        atual = r.get("cliente")
        if atual is not None and str(atual).strip() not in ("", "None", "nan"):
            return atual
        return mapa.get(f"{_gc(r.get('grupo'))}/{_gc(r.get('cota'))}", atual)
    df["cliente"] = df.apply(_nome, axis=1)
    return df
