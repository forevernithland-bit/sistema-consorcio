import streamlit as st
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro
from regras import gerar_tabela_parcelas

def render_baixas(supabase, df_vendas_global, df_admin, cfg, status_dict):
    st.markdown("### 💰 Baixar Parcelas de Comissão")
    
    if 'cart_baixas' not in st.session_state: 
        st.session_state['cart_baixas'] = []

    st.subheader("1. Buscar Cota")
    with st.form("b_b"):
        c1, c2 = st.columns(2)
        busca_g = c1.text_input("Grupo")
        busca_c = c2.text_input("Cota")
        
        if st.form_submit_button("Buscar Cliente", type="primary"):
            if busca_g and busca_c:
                alvo = df_vendas_global[(df_vendas_global['GRUPO'] == busca_g.strip()) & (df_vendas_global['COTA'] == busca_c.strip())]
                st.session_state['venda_baixa_atual'] = alvo.iloc[0].to_dict() if not alvo.empty else None
                if alvo.empty: 
                    st.error("❌ Cota não encontrada.")
            else: 
                st.warning("Preencha Grupo e Cota.")

    v_atual = st.session_state.get('venda_baixa_atual')
    if v_atual:
        st.divider()
        st.subheader("2. Configurar Parcela")
        df_p, _ = gerar_tabela_parcelas(pd.DataFrame([v_atual]), df_vendas_global, df_admin, cfg, status_dict)
        
        if not df_p.empty:
            st.markdown(f"**Cliente:** {v_atual.get('Nome do cliente', '')} | **Grupo:** {v_atual.get('GRUPO', '')} | **Cota:** {v_atual.get('COTA', '')}")
            pendentes = df_p[df_p['Status'] != 'PAGO']
            sug = pendentes.iloc[0]['Parcela'] if not pendentes.empty else df_p.iloc[-1]['Parcela']
            
            cp1, cp2 = st.columns(2)
            sel_parc = cp1.selectbox("Parcela a Baixar:", df_p['Parcela'].tolist(), index=df_p['Parcela'].tolist().index(sug) if sug in df_p['Parcela'].tolist() else 0)
            linha = df_p[df_p['Parcela'] == sel_parc].iloc[0]
            val_o = linha['Comissão (Bruta)']
            novo_val = cp2.number_input("Valor Recebido (R$):", value=float(val_o), step=10.0)

            rz = novo_val / val_o if val_o > 0 else 0
            n_liq = linha['Comissão (s/ Imposto)'] * rz
            n_vend = linha['Vendedor Recebe'] * rz
            n_breno = linha['Breno'] * rz
            n_uriel = linha['Uriel'] * rz
            
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Líquido Corretora", formatar_brl_puro(n_liq))
            s2.metric("Vendedor", formatar_brl_puro(n_vend))
            s3.metric("Breno", formatar_brl_puro(n_breno))
            s4.metric("Uriel", formatar_brl_puro(n_uriel))
            
            st.write("")
            if st.button("Adicionar à Lista", use_container_width=True):
                if any(i['Chave'] == linha['Chave'] for i in st.session_state['cart_baixas']): 
                    st.warning("Já está na lista.")
                else:
                    st.session_state['cart_baixas'].append({
                        "Chave": linha['Chave'], 
                        "Cliente": v_atual.get('Nome do cliente'), 
                        "Grupo": v_atual.get('GRUPO'), 
                        "Cota": v_atual.get('COTA'), 
                        "Parcela": sel_parc, 
                        "Valor Base": val_o, 
                        "Valor Pago": novo_val, 
                        "Líquido": n_liq, 
                        "Vendedor": n_vend, 
                        "Breno": n_breno, 
                        "Uriel": n_uriel, 
                        "Data Baixa": datetime.today().strftime("%d/%m/%Y")
                    })
                    st.success("Adicionado!")
                    st.rerun()

    st.divider()
    st.subheader("3. Lista de Baixas")
    if st.session_state['cart_baixas']:
        df_c = pd.DataFrame(st.session_state['cart_baixas'])
        df_show = df_c[['Cliente', 'Grupo', 'Cota', 'Parcela', 'Valor Pago', 'Líquido', 'Vendedor', 'Breno', 'Uriel']].copy()
        
        for col in ['Valor Pago', 'Líquido', 'Vendedor', 'Breno', 'Uriel']: 
            df_show[col] = df_show[col].apply(formatar_brl_puro)
            
        df_show.columns = ['Cliente', 'Grupo', 'Cota', 'Parcela', 'Valor Bruto', 'Líquido Corretora', 'Vendedor Recebe', 'Breno Recebe', 'Uriel Recebe']
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        
        st.markdown("#### 📊 Resumo dos Valores")
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Bruto", formatar_brl_puro(df_c['Valor Pago'].sum()))
        t2.metric("Líquido", formatar_brl_puro(df_c['Líquido'].sum()))
        t3.metric("Vendedores", formatar_brl_puro(df_c['Vendedor'].sum()))
        t4.metric("Sócios", formatar_brl_puro(df_c['Breno'].sum() + df_c['Uriel'].sum()))
        
        cb_a, cb_b = st.columns([3, 1])
        if cb_a.button("CONFIRMAR E DAR BAIXA", type="primary", use_container_width=True):
            for i in st.session_state['cart_baixas']:
                cv = i['Chave']
                ex = supabase.table("status_comissoes").select("id").eq("Chave_Unica", cv).execute()
                if ex.data: 
                    supabase.table("status_comissoes").update({"Status": "PAGO", "Valor_Pago": i['Valor Pago'], "Data_Pagamento": i['Data Baixa']}).eq("id", ex.data[0]['id']).execute()
                else: 
                    supabase.table("status_comissoes").insert({"Chave_Unica": cv, "Status": "PAGO", "Valor_Pago": i['Valor Pago'], "Data_Pagamento": i['Data Baixa']}).execute()
            st.session_state['cart_baixas'] = []
            st.success("Sucesso!")
            st.rerun()
            
        if cb_b.button("Limpar Lista", use_container_width=True): 
            st.session_state['cart_baixas'] = []
            st.rerun()
    else: 
        st.info("Lista vazia.")

    st.divider()
    st.subheader("Histórico")
    
    # Novo formato de leitura de Status Pagos
    c_p = []
    for k, v in status_dict.items():
        if isinstance(v, str) and v == 'PAGO':
            c_p.append(k)
        elif isinstance(v, dict) and v.get('Status') == 'PAGO':
            c_p.append(k)

    if c_p:
        h_l = []
        for ch in c_p:
            p = ch.split('_')
            if len(p) >= 5: 
                h_l.append({"Cliente": "_".join(p[:-4]), "Grupo": p[-4], "Cota": p[-3], "Administradora": p[-2], "Parcela": p[-1], "Status": "PAGO"})
        st.dataframe(pd.DataFrame(h_l), use_container_width=True, hide_index=True)
    else: 
        st.info("Sem pagamentos registrados.")
