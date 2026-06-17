import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import altair as alt
from utils import (formatar_telefone, formatar_data, formatar_data_br, 
                   formatar_moeda, formatar_brl_puro, normalizar_produto)
from regras import gerar_tabela_parcelas
from database import salvar_status_comissoes

def render_dashboard(supabase, df_vendas_global, df_cli, df_ass, lista_admin_bd, df_admin, status_dict, cfg):
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    # Alerta de Assembleias
    hoje_date = datetime.today().date()
    if not df_ass.empty:
        df_prox = df_ass[(df_ass['data_dt'].dt.date >= hoje_date) & (df_ass['data_dt'].dt.date <= hoje_date + timedelta(days=3))]
        if not df_prox.empty:
            alertas = [f"**{r['descricao']}** ({r['data_dt'].strftime('%d/%m')})" for _, r in df_prox.iterrows()]
            st.warning(f"📅 **Atenção para as Assembleias nos próximos dias:** {' | '.join(alertas)}")

    # ==========================================
    # VISÃO DETALHADA DO CLIENTE
    # ==========================================
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        st.markdown(f"### {cliente_nome}")
        
        if st.button("⬅️ Voltar ao Dashboard", type="primary"):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
            
        info_cliente, id_cliente_db = {}, None
        if not df_cli.empty and 'Nome' in df_cli.columns:
            busca_cli = df_cli[df_cli['Nome'] == cliente_nome]
            if not busca_cli.empty: 
                info_cliente, id_cliente_db = busca_cli.iloc[0].to_dict(), busca_cli.iloc[0].get('id')

        if not is_master: 
            st.info("🔒 Como Vendedor, você só pode visualizar estes dados. Para alterar, contate o Administrador.")
            
        def safe_str(val, default=""):
            if pd.isna(val) or val is None or str(val).strip().lower() in ["nan", "nat", "none"]: return default
            return str(val)

        key_nome = f"n_{cliente_nome}"
        key_tel = f"t_{cliente_nome}"
        key_email = f"e_{cliente_nome}"
        key_end = f"en_{cliente_nome}"
        key_aniv = f"a_{cliente_nome}"
        key_prof = f"p_{cliente_nome}"
        key_renda = f"r_{cliente_nome}"

        if key_nome not in st.session_state: st.session_state[key_nome] = safe_str(info_cliente.get("Nome"), cliente_nome)
        if key_tel not in st.session_state: st.session_state[key_tel] = safe_str(info_cliente.get("Telefone"))
        if key_email not in st.session_state: st.session_state[key_email] = safe_str(info_cliente.get("Email"))
        if key_end not in st.session_state: st.session_state[key_end] = safe_str(info_cliente.get("Endereco"))
        if key_aniv not in st.session_state: st.session_state[key_aniv] = safe_str(info_cliente.get("Aniversario"))
        if key_prof not in st.session_state: st.session_state[key_prof] = safe_str(info_cliente.get("Profissao"))
        if key_renda not in st.session_state: st.session_state[key_renda] = safe_str(info_cliente.get("Renda"))
            
        nome_edit = st.text_input("Nome Completo", key=key_nome, disabled=not is_master)
        
        if is_master:
            col_cep_1, col_cep_2 = st.columns([1, 3])
            with col_cep_1:
                cep_busca = st.text_input("Buscar CEP p/ Endereço", key=f"cep_ed_{cliente_nome}", max_chars=9)
            if cep_busca and cep_busca != st.session_state.get(f'last_cep_ed_{cliente_nome}', ''):
                cep_limpo = ''.join(filter(str.isdigit, cep_busca))
                if len(cep_limpo) == 8:
                    try:
                        res = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
                        if res.status_code == 200 and "erro" not in res.json():
                            d_cep = res.json()
                            st.session_state[key_end] = f"{d_cep.get('logradouro','')}, Nº , {d_cep.get('bairro','')}, {d_cep.get('localidade','')}-{d_cep.get('uf','')} (CEP: {cep_busca})"
                            st.rerun()
                    except: pass
                st.session_state[f'last_cep_ed_{cliente_nome}'] = cep_busca
        
        c1, c2 = st.columns(2)
        with c1:
            endereco = st.text_input("Endereço Completo", key=key_end, disabled=not is_master)
            telefone_edit = st.text_input("Telefone", key=key_tel, on_change=lambda: st.session_state.update({key_tel: formatar_telefone(st.session_state[key_tel])}), disabled=not is_master)
            profissao_edit = st.text_input("Profissão", key=key_prof, disabled=not is_master)
        with c2:
            email = st.text_input("Email", key=key_email, disabled=not is_master)
            aniversario_edit = st.text_input("Data de Aniversário (DD/MM/AAAA)", key=key_aniv, on_change=lambda: st.session_state.update({key_aniv: formatar_data(st.session_state[key_aniv])}), disabled=not is_master, placeholder="DD/MM/AAAA")
            renda_edit = st.text_input("Renda Mensal (R$)", key=key_renda, on_change=lambda: st.session_state.update({key_renda: formatar_moeda(st.session_state[key_renda])}), disabled=not is_master)
        
        if is_master:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Salvar Alterações Cadastrais", type="primary", use_container_width=True):
                    dados_cli = {
                        "Nome": st.session_state[key_nome], "Telefone": st.session_state[key_tel], "Email": st.session_state[key_email],
                        "Endereco": st.session_state[key_end], "Aniversario": st.session_state[key_aniv], "Profissao": st.session_state[key_prof], "Renda": st.session_state[key_renda]
                    }
                    try:
                        if id_cliente_db: supabase.table("clientes").update(dados_cli).eq("id", int(id_cliente_db)).execute()
                        else:
                            dados_cli["Data_Cadastro"] = datetime.today().strftime("%d/%m/%Y")
                            supabase.table("clientes").insert([dados_cli]).execute()
                        
                        if st.session_state[key_nome] != cliente_nome:
                            supabase.table("vendas").update({"NOME": st.session_state[key_nome]}).eq("NOME", cliente_nome).execute()
                            st.session_state['cliente_visualizado'] = st.session_state[key_nome]
                        st.success("Dados atualizados com sucesso!"); st.rerun()
                    except Exception as e: st.error(f"❌ Erro ao salvar: {e}")

            with col_b2:
                if st.button("🚨 Excluir Cliente (Apagar Todas as Cotas)", use_container_width=True):
                    if id_cliente_db: supabase.table("clientes").delete().eq("id", int(id_cliente_db)).execute()
                    supabase.table("vendas").delete().eq("NOME", cliente_nome).execute()
                    st.session_state['cliente_visualizado'] = None; st.session_state['key_tabela'] += 1; st.rerun()

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        if not df_vendas_global.empty:
            cotas_cliente = df_vendas_global[df_vendas_global['Nome do cliente'] == cliente_nome].copy()
            if not cotas_cliente.empty:
                info_a, info_b = st.columns(2)
                info_a.metric("Total de Cotas Adquiridas", len(cotas_cliente))
                info_b.metric("Volume Total Investido", formatar_brl_puro(cotas_cliente['Valor_Numerico'].sum()))
                
                cotas_cliente['Valor Formatado'] = cotas_cliente['Valor_Numerico'].apply(formatar_brl_puro)
                cotas_cliente['Data da Venda'] = cotas_cliente['Data_Real'].apply(formatar_data_br)
                
                ficha_display = cotas_cliente[['Data da Venda', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'Valor Formatado', 'STATUS', 'VENDEDOR']].rename(columns={'ADMINISTRADORA': 'Administradora', 'PRODUTO': 'Produto', 'GRUPO': 'Grupo', 'COTA': 'Cota', 'Valor Formatado': 'Valor (R$)', 'STATUS': 'Status', 'VENDEDOR': 'Vendedor'})
                estilo_ficha = ficha_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_ficha, use_container_width=True, hide_index=True)
                
                with st.expander("⚙️ Atualizar Status, Data e Gerenciar Cota", expanded=False):
                    opcoes_cotas = cotas_cliente.apply(lambda r: f"ID:{r['id']} | Grupo: {r['GRUPO']} / Cota: {r['COTA']} - Valor: {r['Valor Formatado']}", axis=1).tolist()
                    c_sel, _ = st.columns([3, 1])
                    with c_sel: cota_selecionada = st.selectbox("Selecione a cota que deseja gerenciar:", [""] + opcoes_cotas)
                        
                    if cota_selecionada:
                        id_cota = int(cota_selecionada.split(" | ")[0].replace("ID:", ""))
                        cota_info = cotas_cliente[cotas_cliente['id'] == id_cota].iloc[0]
                        
                        vendedor_atual = cota_info['VENDEDOR']
                        status_atual = cota_info['STATUS']
                        data_atual_str = cota_info['DATA']
                        grupo_atual = cota_info['GRUPO']
                        cota_atual = cota_info['COTA']
                        valor_atual = cota_info['Valor_Numerico']
                        admin_atual = cota_info['ADMINISTRADORA']
                        produto_atual = cota_info['PRODUTO']
                        
                        opcoes_status = ["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"]
                        if status_atual not in opcoes_status:
                            status_atual = "Em Andamento"
                        
                        try:
                            data_atual_obj = pd.to_datetime(data_atual_str, format="%d/%m/%Y", errors='coerce').date()
                            if pd.isna(data_atual_obj): data_atual_obj = datetime.today().date()
                        except:
                            data_atual_obj = datetime.today().date()
                        
                        # --- LINHA 1 ---
                        c_ed1, c_ed2, c_ed3 = st.columns(3)
                        with c_ed1: novo_status = st.selectbox("Status", opcoes_status, index=opcoes_status.index(status_atual))
                        with c_ed2:
                            opts_v = ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]
                            novo_vendedor = st.selectbox("Vendedor", opts_v, index=opts_v.index(vendedor_atual) if vendedor_atual in opts_v else 0) if is_master else st.text_input("Vendedor", value=vendedor_atual, disabled=True)
                        with c_ed3: nova_data = st.date_input("Data da Venda", value=data_atual_obj, format="DD/MM/YYYY") if is_master else st.text_input("Data da Venda", value=formatar_data_br(cota_info['Data_Real']), disabled=True)

                        # --- LINHA 2 ---
                        c_ed4, c_ed5, c_ed6 = st.columns(3)
                        with c_ed4: novo_grupo = st.text_input("Grupo", value=grupo_atual, disabled=not is_master)
                        with c_ed5: nova_cota = st.text_input("Cota", value=cota_atual, disabled=not is_master)
                        with c_ed6: novo_valor = st.number_input("Valor da Carta (R$)", value=float(valor_atual) if pd.notna(valor_atual) else 0.0, step=1000.0, format="%.2f", disabled=not is_master)
                                
                        # --- LINHA 3 ---
                        c_ed7, c_ed8 = st.columns(2)
                        with c_ed7:
                            try: idx_admin = lista_admin_bd.index(admin_atual)
                            except ValueError: idx_admin = 0
                            nova_admin = st.selectbox("Administradora", options=lista_admin_bd, index=idx_admin, disabled=not is_master)
                            
                        with c_ed8:
                            lista_produtos = ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"]
                            try: idx_produto = lista_produtos.index(produto_atual)
                            except ValueError: idx_produto = 0
                            novo_produto = st.selectbox("Tipo do Bem", options=lista_produtos, index=idx_produto, disabled=not is_master)

                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.button("💾 Salvar Alterações na Cota", type="primary", use_container_width=True):
                                data_formatada = nova_data.strftime("%d/%m/%Y") if not isinstance(nova_data, str) else nova_data
                                
                                dados_atualizados = {
                                    "VENDEDOR": novo_vendedor, 
                                    "STATUS": novo_status, 
                                    "DATA": data_formatada, 
                                    "GRUPO": novo_grupo, 
                                    "COTA": nova_cota,
                                    "VALOR": novo_valor,
                                    "ADMINISTRADORA": nova_admin,
                                    "PRODUTO": novo_produto
                                }
                                
                                supabase.table("vendas").update(dados_atualizados).eq("id", id_cota).execute()
                                st.success("Cota atualizada com sucesso!"); st.rerun()
                        with col_b2:
                            if is_master and st.button("🚨 Apagar Esta Cota", use_container_width=True):
                                supabase.table("vendas").delete().eq("id", id_cota).execute()
                                st.success("Cota apagada com sucesso!"); st.rerun()

                st.subheader("📈 Previsão de Comissionamento")
                df_parcelas, vendas_sem_data = gerar_tabela_parcelas(cotas_cliente, df_vendas_global, df_admin, cfg, status_dict)
                if vendas_sem_data: st.warning(f"⚠️ Algumas vendas estão sem data: {', '.join(vendas_sem_data)}")

                if not df_parcelas.empty:
                    df_view_cli = df_parcelas[df_parcelas['Vendedor Recebe'] > 0].copy() if not is_master else df_parcelas.copy()
                    if not df_view_cli.empty:
                        for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']: df_view_cli[col] = df_view_cli[col].apply(formatar_brl_puro)
                        
                        c_conf = {
                            "Chave": None, 
                            "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True),
                            "Data Recebimento": st.column_config.TextColumn("Data Recebimento", disabled=not is_master)
                        }
                        c_hide = ['Cliente', 'Produto', 'Vendedor', 'data_pagamento_dt'] + (["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"] if not is_master else [])
                        df_final_cli = df_view_cli.drop(columns=c_hide).reset_index(drop=True)
                        
                        cols_editaveis_cli = ["Status", "Data Recebimento"] if is_master else []
                        
                        st.caption("Dica: Clique em 'Status' ou 'Data Recebimento' para alterar. Em seguida, salve no botão.")
                        edited_df_cli = st.data_editor(df_final_cli, disabled=[c for c in df_final_cli.columns if c not in cols_editaveis_cli], column_config=c_conf, use_container_width=True, hide_index=True)
                        
                        if is_master and st.button("💾 Salvar Status de Pagamento (Cliente)", type="primary"):
                            if salvar_status_comissoes(supabase, edited_df_cli, df_final_cli): 
                                st.success("Atualizados!")
                                st.rerun()
                else: st.info("Aguardando configurações de regras para gerar a previsão.")
            else: st.warning("Nenhuma cota encontrada.")

    # ==========================================
    # VISÃO GLOBAL (LISTA DE VENDAS E GRÁFICOS)
    # ==========================================
    else:
        df_view = df_vendas_global.copy()
        if not is_master: df_view = df_view[df_view['VENDEDOR'] == st.session_state['nome_vendedor']]

        col_t1, col_t2 = st.columns([4, 1])
        with col_t2:
            st.write("")
            if st.button("Nova Venda", use_container_width=True, type="primary"): 
                st.session_state['menu_lateral'] = "Nova Venda"
                st.rerun()
        
        c_f1, c_f2, c_f3, c_f4 = st.columns([1.5, 1.5, 1, 1])
        with c_f1:
            ft_cli = st.selectbox("⏳ Filtro:", ["Últimos 5 Cadastros", "Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
            if ft_cli == "Período Personalizado":
                cd1, cd2 = st.columns(2)
                with cd1: p_ini = st.date_input("Início", format="DD/MM/YYYY")
                with cd2: p_fim = st.date_input("Fim", format="DD/MM/YYYY")
        with c_f2: busca_nome = st.text_input("🔍 Buscar Cliente:")
        with c_f3: busca_grupo = st.text_input("📦 Grupo:")
        with c_f4: busca_cota = st.text_input("🔢 Cota:")

        hoje = datetime.today()
        df_view = df_view.sort_values(by="Data_Real", ascending=False)
        
        if ft_cli == "Últimos 5 Cadastros" and not (busca_nome or busca_grupo or busca_cota): df_view = df_view.head(5)
        elif ft_cli != "Todos os Clientes" and ft_cli != "Últimos 5 Cadastros":
            mask = df_view['Data_Real'].notna()
            if ft_cli == "Mês Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.month == hoje.month) & (df_view['Data_Real'].dt.year == hoje.year)]
            elif ft_cli == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_view = df_view[mask & (df_view['Data_Real'].dt.month == ma) & (df_view['Data_Real'].dt.year == aa)]
            elif ft_cli == "Ano Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.year == hoje.year)]
            elif ft_cli == "Período Personalizado": df_view = df_view[mask & (df_view['Data_Real'].dt.date >= p_ini) & (df_view['Data_Real'].dt.date <= p_fim)]

        if busca_nome: df_view = df_view[df_view['Nome do cliente'].astype(str).str.contains(busca_nome.strip(), case=False, na=False)]
        if busca_grupo: df_view = df_view[df_view['GRUPO'].astype(str).str.contains(busca_grupo.strip(), case=False, na=False)]
        if busca_cota: df_view = df_view[df_view['COTA'].astype(str).str.contains(busca_cota.strip(), case=False, na=False)]

        if not df_view.empty:
            st.write("Clique em uma linha para ver os detalhes do cliente:")
            df_tab = df_view.copy()
            df_tab['Grupo e Cota'] = df_tab.apply(lambda x: f"{x['GRUPO']}/{x['COTA']}", axis=1)
            df_tab['Valor Formatado'] = df_tab['Valor_Numerico'].apply(formatar_brl_puro)
            df_tab['Data da Venda'] = df_tab['Data_Real'].apply(formatar_data_br)
            
            df_tab = df_tab[['Nome do cliente', 'PRODUTO', 'ADMINISTRADORA', 'Grupo e Cota', 'VENDEDOR', 'Valor Formatado', 'Data da Venda']]
            df_tab.columns = ['Cliente', 'Produto', 'Administradora', 'Grupo/Cota', 'Vendedor', 'Valor', 'Data da Venda']
            
            tabela = st.dataframe(df_tab, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
            if hasattr(tabela, 'selection') and tabela.selection.rows:
                st.session_state['cliente_visualizado'] = df_tab.iloc[tabela.selection.rows[0]]['Cliente']; st.rerun()

            st.divider()
            m1, m2, m3 = st.columns(3)
            vol_total = df_view['Valor_Numerico'].sum()
            m1.metric("Volume Total (Filtro)", formatar_brl_puro(vol_total))
            m2.metric("Qtd. Cotas (Filtro)", len(df_view))
            m3.metric("Ticket Médio", formatar_brl_puro(vol_total/len(df_view) if len(df_view)>0 else 0))

            st.write("")
            st.subheader("📊 Gráficos Globais (Filtro Independente)")
            g_f1, g_f2 = st.columns(2)
            with g_f1:
                ft_graf = st.selectbox("⏳ Período para o Gráfico:", ["Mês Atual", "Mês Anterior", "Anual", "Todas as Vendas", "Período Personalizado"])
                if ft_graf == "Período Personalizado":
                    cg1, cg2 = st.columns(2)
                    with cg1: gi = st.date_input("Início", format="DD/MM/YYYY", key="g_ini")
                    with cg2: gf = st.date_input("Fim", format="DD/MM/YYYY", key="g_fim")
            with g_f2: fp_graf = st.selectbox("📦 Produto:", ["Todos", "Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
                
            df_g = df_vendas_global.copy()
            if not is_master: df_g = df_g[df_g['VENDEDOR'] == st.session_state['nome_vendedor']]
            if ft_graf != "Todas as Vendas" and not df_g.empty:
                mask = df_g['Data_Real'].notna()
                if ft_graf == "Mês Atual": df_g = df_g[mask & (df_g['Data_Real'].dt.month == hoje.month) & (df_g['Data_Real'].dt.year == hoje.year)]
                elif ft_graf == "Mês Anterior":
                    ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                    df_g = df_g[mask & (df_g['Data_Real'].dt.month == ma) & (df_g['Data_Real'].dt.year == aa)]
                elif ft_graf == "Anual": df_g = df_g[mask & (df_g['Data_Real'].dt.year == hoje.year)]
                elif ft_graf == "Período Personalizado": df_g = df_g[mask & (df_g['Data_Real'].dt.date >= gi) & (df_g['Data_Real'].dt.date <= gf)]
                
            if fp_graf != "Todos" and not df_g.empty: 
                df_g = df_g[df_g['PRODUTO'].apply(normalizar_produto) == normalizar_produto(fp_graf)]
                
            if not df_g.empty:
                cg1, cg2 = st.columns(2)
                with cg1:
                    st.markdown("#### Vendas por Produto")
                    df_p = df_g['PRODUTO'].value_counts().reset_index()
                    df_p.columns = ['Produto', 'Quantidade']
                    st.altair_chart(alt.Chart(df_p).mark_arc(innerRadius=50).encode(theta='Quantidade', color='Produto', tooltip=['Produto', 'Quantidade']), use_container_width=True)
                with cg2:
                    st.markdown("#### Vendas por Administradora")
                    df_a = df_g['ADMINISTRADORA'].value_counts().reset_index()
                    df_a.columns = ['Administradora', 'Quantidade']
                    st.altair_chart(alt.Chart(df_a).mark_arc(innerRadius=50).encode(theta='Quantidade', color='Administradora', tooltip=['Administradora', 'Quantidade']), use_container_width=True)
        else: st.info("Nenhuma venda encontrada.")
