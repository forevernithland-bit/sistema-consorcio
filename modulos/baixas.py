import streamlit as st
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro, parse_float_safe
from regras import gerar_tabela_parcelas
from modulos.importar_comissoes import (
    render_importar_comissoes, render_historico_comissoes, dividir_socios
)

def render_baixas(supabase, df_vendas_global, df_admin, cfg, status_dict, lista_admin_bd=None):
    st.markdown("### 💰 Baixar Parcelas de Comissão")

    aba_import, aba_manual, aba_hist = st.tabs(
        ["📥 Importar Resumo (NF)", "✍️ Baixa Manual", "📚 Histórico"]
    )

    with aba_import:
        render_importar_comissoes(supabase, df_vendas_global, cfg, lista_admin_bd or [])

    with aba_hist:
        render_historico_comissoes(supabase)

    with aba_manual:
        _render_baixa_manual(supabase, df_vendas_global, df_admin, cfg, status_dict)


def _mes_competencia(data_ddmmaaaa):
    """'13/08/2026' -> '2026-08'."""
    try:
        return datetime.strptime(str(data_ddmmaaaa), "%d/%m/%Y").strftime("%Y-%m")
    except (ValueError, TypeError):
        return datetime.today().strftime("%Y-%m")


def _parcela_num(chave):
    """Extrai o nº da parcela do fim da Chave (cliente_grupo_cota_admin_PARCELA)."""
    try:
        return str(chave).rsplit("_", 1)[-1]
    except Exception:
        return ""


def _render_baixa_manual(supabase, df_vendas_global, df_admin, cfg, status_dict):
    """Baixa manual, cota por cota, com o MESMO relatório e registro da importação
    de NF: calcula imposto + divisão de sócios (dividir_socios) e grava no histórico
    (comissoes_pagas), além de marcar a parcela como PAGO (status_comissoes).
    Feito para administradoras sem lote de PDF ainda (ex.: Itaú)."""
    if 'cart_baixas' not in st.session_state:
        st.session_state['cart_baixas'] = []

    imp_pct = parse_float_safe(cfg.get("Imposto", 7.16))

    st.subheader("1. Buscar Cota")
    st.caption("Digite Grupo e Cota (uma de cada vez). O sistema calcula imposto e "
               "divisão de sócios igual à importação de NF e monta a lista de baixas.")
    with st.form("b_b"):
        c1, c2 = st.columns(2)
        busca_g = c1.text_input("Grupo")
        busca_c = c2.text_input("Cota")

        if st.form_submit_button("Buscar Cliente", type="primary"):
            if busca_g and busca_c:
                alvo = df_vendas_global[(df_vendas_global['GRUPO'] == busca_g.strip()) & (df_vendas_global['COTA'] == busca_c.strip())]
                st.session_state['venda_baixa_atual'] = alvo.iloc[0].to_dict() if not alvo.empty else None
                if alvo.empty:
                    st.error("❌ Cota não encontrada. Cadastre a venda em 'Nova Venda' antes de dar baixa.")
            else:
                st.warning("Preencha Grupo e Cota.")

    v_atual = st.session_state.get('venda_baixa_atual')
    if v_atual:
        st.divider()
        st.subheader("2. Configurar Parcela")
        df_p, _ = gerar_tabela_parcelas(pd.DataFrame([v_atual]), df_vendas_global, df_admin, cfg, status_dict)

        if df_p.empty:
            st.warning("Não há parcelas de comissão previstas para esta cota "
                       "(confira administradora/produto e a data da venda).")
        else:
            admin = str(v_atual.get('ADMINISTRADORA', '') or '')
            st.markdown(
                f"**Cliente:** {v_atual.get('Nome do cliente', '')} &nbsp;|&nbsp; "
                f"**Grupo/Cota:** {v_atual.get('GRUPO', '')}/{v_atual.get('COTA', '')} &nbsp;|&nbsp; "
                f"**Administradora:** {admin or '—'} &nbsp;|&nbsp; "
                f"**Vendedor:** {v_atual.get('VENDEDOR', '') or '—'}"
            )
            pendentes = df_p[df_p['Status'] != 'PAGO']
            sug = pendentes.iloc[0]['Parcela'] if not pendentes.empty else df_p.iloc[-1]['Parcela']

            cp1, cp2, cp3 = st.columns([2, 1.4, 1.4])
            sel_parc = cp1.selectbox(
                "Parcela a Baixar:", df_p['Parcela'].tolist(),
                index=df_p['Parcela'].tolist().index(sug) if sug in df_p['Parcela'].tolist() else 0
            )
            linha = df_p[df_p['Parcela'] == sel_parc].iloc[0]
            val_bruto = float(linha['Comissão (Bruta)'])
            # Valor da nota (comissão) — vem sugerido pela regra, mas é editável (ex.: Itaú)
            vn = cp2.number_input("Valor da Nota (R$):", value=round(val_bruto, 2), step=10.0,
                                  help="Valor bruto da comissão recebida desta parcela.")
            data_baixa = cp3.date_input("Data da baixa:", value=datetime.today(), format="DD/MM/YYYY")

            # MESMO cálculo da importação de NF: imposto + dividir_socios
            vimp = round(vn * imp_pct / 100.0, 2)
            vliq = round(vn - vimp, 2)
            vendedor = str(v_atual.get('VENDEDOR', '') or '')
            n_breno, n_uriel = dividir_socios(vendedor, vliq, cfg)

            s1, s2, s3, s4 = st.columns(4)
            s1.metric(f"Imposto ({imp_pct:.2f}%)", formatar_brl_puro(vimp))
            s2.metric("Líquido Corretora", formatar_brl_puro(vliq))
            s3.metric("Breno", formatar_brl_puro(n_breno))
            s4.metric("Uriel", formatar_brl_puro(n_uriel))

            st.write("")
            if st.button("➕ Adicionar à Lista", use_container_width=True):
                if any(i['Chave'] == linha['Chave'] for i in st.session_state['cart_baixas']):
                    st.warning("Essa parcela já está na lista.")
                else:
                    st.session_state['cart_baixas'].append({
                        "Chave": linha['Chave'],
                        "Cliente": v_atual.get('Nome do cliente'),
                        "Vendedor": vendedor,
                        "Grupo": str(v_atual.get('GRUPO', '')),
                        "Cota": str(v_atual.get('COTA', '')),
                        "Admin": admin,
                        "Parcela": sel_parc,
                        "ParcelaNum": _parcela_num(linha['Chave']),
                        "Credito": float(linha.get('Valor da Venda', 0) or 0),
                        "Valor Nota": float(vn),
                        "Imposto": vimp,
                        "Líquido": vliq,
                        "Breno": n_breno,
                        "Uriel": n_uriel,
                        "Data Baixa": data_baixa.strftime("%d/%m/%Y"),
                    })
                    st.success("Adicionado à lista!")
                    st.rerun()

    st.divider()
    st.subheader("3. Lista de Baixas (relatório)")
    if st.session_state['cart_baixas']:
        df_c = pd.DataFrame(st.session_state['cart_baixas'])

        # Relatório no MESMO formato da importação de NF
        df_show = pd.DataFrame({
            "Grupo/Cota": df_c['Grupo'].astype(str) + "/" + df_c['Cota'].astype(str),
            "Cliente": df_c['Cliente'],
            "Vendedor": df_c['Vendedor'],
            "Valor Nota": df_c['Valor Nota'].apply(formatar_brl_puro),
            f"Imposto ({imp_pct:.2f}%)": df_c['Imposto'].apply(formatar_brl_puro),
            "Líquido": df_c['Líquido'].apply(formatar_brl_puro),
            "Breno": df_c['Breno'].apply(formatar_brl_puro),
            "Uriel": df_c['Uriel'].apply(formatar_brl_puro),
        })
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.markdown("#### 📊 Resumo dos Valores")
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Total Notas", formatar_brl_puro(df_c['Valor Nota'].sum()))
        t2.metric("Líquido", formatar_brl_puro(df_c['Líquido'].sum()))
        t3.metric("Breno", formatar_brl_puro(df_c['Breno'].sum()))
        t4.metric("Uriel", formatar_brl_puro(df_c['Uriel'].sum()))

        cb_a, cb_b = st.columns([3, 1])
        if cb_a.button("✅ Confirmar e Registrar Pagamentos", type="primary", use_container_width=True):
            _salvar_baixas_manuais(supabase, st.session_state['cart_baixas'])

        if cb_b.button("Limpar Lista", use_container_width=True):
            st.session_state['cart_baixas'] = []
            st.rerun()
    else:
        st.info("Lista vazia. Busque uma cota acima e adicione as parcelas a baixar.")


def _salvar_baixas_manuais(supabase, itens):
    """Grava cada baixa manual no histórico (comissoes_pagas, origem='MANUAL') e marca
    a parcela como PAGO (status_comissoes). Usa a MESMA chave_unica do gerar_tabela_parcelas,
    então o Financeiro não duplica (ele já prioriza comissoes_pagas)."""
    ok, erros = 0, 0
    for i in itens:
        chave = i['Chave']
        data_pgto = i['Data Baixa']
        try:
            registro = {
                "administradora": i['Admin'],
                "periodo_inicio": "",
                "periodo_fim": data_pgto,
                "mes_competencia": _mes_competencia(data_pgto),
                "grupo": i['Grupo'],
                "cota": i['Cota'],
                "parcela": i['ParcelaNum'],
                "cliente": i['Cliente'],
                "vendedor": i['Vendedor'],
                "credito": i['Credito'],
                "valor_nota": i['Valor Nota'],
                "imposto_pct": None,
                "valor_imposto": i['Imposto'],
                "valor_liquido": i['Líquido'],
                "breno": i['Breno'],
                "uriel": i['Uriel'],
                "data_pagamento": data_pgto,
                "origem": "MANUAL",
                "chave_unica": chave,
            }
            # 1) Histórico (comissoes_pagas) — atualiza se a chave já existir, senão insere
            ex_cp = supabase.table("comissoes_pagas").select("id").eq("chave_unica", chave).execute()
            if ex_cp.data:
                supabase.table("comissoes_pagas").update(registro).eq("id", ex_cp.data[0]["id"]).execute()
            else:
                supabase.table("comissoes_pagas").insert(registro).execute()

            # 2) Marca a parcela como PAGA (status_comissoes)
            ex_sc = supabase.table("status_comissoes").select("id").eq("Chave_Unica", chave).execute()
            payload = {"Chave_Unica": chave, "Status": "PAGO",
                       "Valor_Pago": i['Valor Nota'], "Data_Pagamento": data_pgto}
            if ex_sc.data:
                supabase.table("status_comissoes").update(payload).eq("id", ex_sc.data[0]["id"]).execute()
            else:
                supabase.table("status_comissoes").insert(payload).execute()
            ok += 1
        except Exception as e:
            erros += 1
            st.error(f"Erro na cota {i.get('Grupo')}/{i.get('Cota')}: {e}")

    if ok:
        st.session_state['cart_baixas'] = []
        st.success(f"✅ {ok} baixa(s) registrada(s) no histórico e marcada(s) como PAGO. "
                   f"Aparecem no 'Histórico' e no Financeiro.")
        st.rerun()
    elif erros:
        st.error("Nenhuma baixa foi salva. Verifique a conexão/tabelas no Supabase.")
