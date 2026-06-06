import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
from utils import formatar_brl_puro

def render_relatorios(df_vendas_global):
    st.markdown("### 📑 Relatórios Gerenciais")
    
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])
    
    if not df_vendas_global.empty:
        df_f = df_vendas_global.copy()
        c1, c2 = st.columns([1, 2])
        with c1:
            ft_rel = st.selectbox("⏳ Período:", ["Mês Atual", "Quinzena Atual", "Mês Anterior", "Ano Atual", "Todas as Vendas", "Período Personalizado"])
            if ft_rel == "Período Personalizado":
                rd1, rd2 = st.columns(2)
                with rd1: ri = st.date_input("Data Inicial", format="DD/MM/YYYY")
                with rd2: rf = st.date_input("Data Final", format="DD/MM/YYYY")
        
        hoje = datetime.today()
        if ft_rel != "Todas as Vendas":
            mask = df_f['Data_Real'].notna()
            if ft_rel == "Mês Atual": 
                df_f = df_f[mask & (df_f['Data_Real'].dt.month == hoje.month) & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Quinzena Atual":
                q_ini, q_fim = (hoje.replace(day=1), hoje.replace(day=15)) if hoje.day <= 15 else (hoje.replace(day=16), hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1]))
                df_f = df_f[mask & (df_f['Data_Real'].dt.date >= q_ini.date()) & (df_f['Data_Real'].dt.date <= q_fim.date())]
            elif ft_rel == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_f = df_f[mask & (df_f['Data_Real'].dt.month == ma) & (df_f['Data_Real'].dt.year == aa)]
            elif ft_rel == "Ano Atual": 
                df_f = df_f[mask & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Período Personalizado": 
                df_f = df_f[mask & (df_f['Data_Real'].dt.date >= ri) & (df_f['Data_Real'].dt.date <= rf)]
                
        if not is_master: 
            df_f = df_f[df_f['VENDEDOR'] == st.session_state['nome_vendedor']]
            
        st.divider()

        if df_f.empty: 
            st.warning("Nenhuma venda neste período.")
        else:
            t1, t2, t3 = st.tabs(["👤 Vendas Por Usuário", "🏢 Por Administradora", "💰 Comissionamento (Gerar)"])
            
            with t1:
                rv = df_f.groupby('VENDEDOR').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                rv['Vol'] = rv['Vol'].apply(formatar_brl_puro)
                st.dataframe(rv.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
                
            with t2:
                ra = df_f.groupby('ADMINISTRADORA').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                ra['Vol'] = ra['Vol'].apply(formatar_brl_puro)
                st.dataframe(ra.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
                
            with t3:
                st.info("Para dar baixa, expanda o relatório clicando no botão abaixo.")
                if st.button("Gerar Relatório Detalhado", type="primary"):
                    st.session_state['tela_cheia_relatorio'] = True
                    st.session_state['rel_periodo'] = ft_rel
                    if ft_rel == "Período Personalizado": 
                        st.session_state['rel_dt_ini'], st.session_state['rel_dt_fim'] = ri, rf
                    st.rerun()
    else: 
        st.info("Não possui vendas.")
