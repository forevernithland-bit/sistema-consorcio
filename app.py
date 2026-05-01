import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import streamlit.components.v1 as components
import altair as alt

# Configuração da página
st.set_page_config(page_title="Portal Consorbens", layout="wide", initial_sidebar_state="expanded")

# === 1. CONFIGURAÇÃO DE USUÁRIOS E SENHAS ===
USUARIOS = {
    "breno": {"senha": "123", "perfil": "Master", "nome": "BRENO LIMA"},
    "uriel": {"senha": "123", "perfil": "Master", "nome": "URIEL GOMES"},
    "vendedor1": {"senha": "123", "perfil": "Vendedor", "nome": "Vendedor Terceiro"},
    "consorbens": {"senha": "123", "perfil": "Vendedor", "nome": "Consorbens"}
}

# Controle de sessão
if 'usuario_logado' not in st.session_state:
    st.session_state['usuario_logado'] = None
    st.session_state['perfil_logado'] = None
    st.session_state['nome_vendedor'] = None

# Função auxiliar para ler os arquivos HTML
def carregar_ferramenta(nome_arquivo):
    try:
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            html_code = f.read()
            components.html(html_code, height=900, scrolling=True)
    except FileNotFoundError:
        st.error(f"⚠️ O arquivo {nome_arquivo} não foi encontrado. Certifique-se de ter criado ele no GitHub com este nome exato!")

# === 2. LÓGICA DO MENU LATERAL ===
menu_selecionado = ""
is_logado = st.session_state['usuario_logado'] is not None

st.sidebar.image("https://www.consorbens.com/assets/logo-consorbens-DZ8uSiSJ.png", use_column_width=True)
st.sidebar.write("") 

if not is_logado:
    menu_selecionado = st.sidebar.radio(
        " ", 
        [
            "🔐 Login (Área Restrita)",
            "🏍️ Simulador Yamaha",
            "🏦 Simulador Itaú",
            "🎯 Oportunidades Itaú",
            "⚖️ Financiamento x Consórcio"
        ],
        label_visibility="collapsed"
    )
    st.sidebar.divider()
    st.sidebar.caption("Portal Consorbens © 2026")
    
else:
    st.sidebar.write(f"👤 **{st.session_state['nome_vendedor']}**")
    st.sidebar.divider()

    ferramentas_logadas = [
        "🏍️ Simulador Yamaha", 
        "🏦 Simulador Itaú", 
        "🎯 Oportunidades Itaú", 
        "⚖️ Financiamento x Consórcio"
    ]

    if st.session_state['perfil_logado'] == "Master":
        opcoes_menu = ["Dashboard", "Nova Venda", "Gerenciar Vendas (Editar/Deletar)", "Relatórios", "Baixar Parcela"] + ferramentas_logadas
    else:
        opcoes_menu = ["Dashboard", "Nova Venda", "Relatórios"] + ferramentas_logadas

    menu_selecionado = st.sidebar.radio(
        " ", 
        opcoes_menu,
        label_visibility="collapsed"
    )
    
    st.sidebar.write("")
    if st.sidebar.button("Sair do Sistema"):
        st.session_state['usuario_logado'] = None
        st.session_state['perfil_logado'] = None
        st.session_state['nome_vendedor'] = None
        st.rerun()

# === 3. ESTILIZAÇÃO FORÇADA (CSS BRUTO) ===
simuladores = ["🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
is_simulator = menu_selecionado in simuladores

css = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
    
    [data-testid="stSidebar"] { background-color: #ffffff !important; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div { color: #0f172a !important; }
    [data-testid="stSidebar"] hr { border-bottom-color: #e2e8f0 !important; }
    [data-testid="stSidebar"] button { border: 1px solid #cbd5e1 !important; background-color: #f8fafc !important; }

    [data-testid="collapsedControl"] { background-color: #ff6600 !important; border-radius: 8px !important; box-shadow: 0px 4px 10px rgba(255, 102, 0, 0.6) !important; padding: 8px !important; margin-top: 15px !important; margin-left: 15px !important; opacity: 1 !important; z-index: 999999 !important; }
    [data-testid="collapsedControl"] svg { fill: #ffffff !important; color: #ffffff !important; stroke: #ffffff !important; width: 20px !important; height: 20px !important; }
    [data-testid="collapsedControl"]:hover { background-color: #cc5200 !important; transform: scale(1.1) !important; }
    
    [data-testid="stSidebarCollapseButton"] { background-color: #ff6600 !important; border-radius: 6px !important; }
    [data-testid="stSidebarCollapseButton"] svg { fill: #ffffff !important; color: #ffffff !important; }
    [data-testid="stSidebarCollapseButton"]:hover { background-color: #cc5200 !important; }
    
    header[data-testid="stHeader"] { background-color: transparent !important; }
    
    button[data-baseweb="tab"] { font-size: 16px !important; font-weight: bold !important; }
"""

if is_simulator:
    css += """ .stApp { background-color: #0f172a !important; } """
else:
    css += """ .stApp { background-color: #ffffff !important; } """

css += "</style>"
st.markdown(css, unsafe_allow_html=True)

# === 4. RENDERIZAÇÃO DAS TELAS ===
if not is_logado:
    if menu_selecionado == "🔐 Login (Área Restrita)":
        st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        col_esq, col_meio, col_dir = st.columns([1, 1.2, 1])
        with col_meio:
            with st.form("form_login"):
                usuario_input = st.text_input("Usuário (Login)").lower()
                senha_input = st.text_input("Senha", type="password")
                btn_login = st.form_submit_button("Entrar no Sistema")
                
                if btn_login:
                    if usuario_input in USUARIOS and USUARIOS[usuario_input]["senha"] == senha_input:
                        st.session_state['usuario_logado'] = usuario_input
                        st.session_state['perfil_logado'] = USUARIOS[usuario_input]["perfil"]
                        st.session_state['nome_vendedor'] = USUARIOS[usuario_input]["nome"]
                        st.rerun() 
                    else:
                        st.error("❌ Usuário ou senha incorretos.")
                        
    elif menu_selecionado == "🏍️ Simulador Yamaha": carregar_ferramenta("yamaha.html")
    elif menu_selecionado == "🏦 Simulador Itaú": carregar_ferramenta("itau.html")
    elif menu_selecionado == "🎯 Oportunidades Itaú": carregar_ferramenta("guia.html")
    elif menu_selecionado == "⚖️ Financiamento x Consórcio": carregar_ferramenta("comparador.html")
        
    st.stop() 

# --- ÁREA RESTRITA (Logado) ---
@st.cache_resource
def conectar_planilha():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    planilha = gc.open("Sistema CRM") 
    return planilha

planilha = conectar_planilha()

if menu_selecionado == "Dashboard":
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_brutos = aba_vendas.get_all_values()
    
    if len(dados_brutos) > 1:
        df_vendas = pd.DataFrame(dados_brutos[1:])
        col_count = len(df_vendas.columns)
        if col_count < 10:
            for i in range(col_count, 10): df_vendas[i] = ""
        df_vendas = df_vendas.iloc[:, :10]
        
        df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
        
        df_vendas['Data_Real'] = pd.to_datetime(df_vendas['DATA'], dayfirst=True, errors='coerce')
        df_vendas['Valor_Numerico'] = df_vendas['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip()
        df_vendas['Valor_Numerico'] = pd.to_numeric(df_vendas['Valor_Numerico'], errors='coerce').fillna(0.0)

        if st.session_state['perfil_logado'] == "Vendedor":
            df_vendas = df_vendas[df_vendas['VENDEDOR'] == st.session_state['nome_vendedor']]
            
        # =========================================================
        # PARTE 1: GESTÃO E BUSCA DE CLIENTES
        # =========================================================
        st.subheader("👥 Ficha de Clientes")
        
        c_filtro1, c_filtro2 = st.columns([1, 2])
        with c_filtro1:
            filtro_cli = st.selectbox("⏳ Filtro por Data da Venda:", ["Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
            
            # Calendário customizado
            if filtro_cli == "Período Personalizado":
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    data_inicio = st.date_input("Data Inicial", format="DD/MM/YYYY")
                with col_d2:
                    data_fim = st.date_input("Data Final", format="DD/MM/YYYY")
                    
        with c_filtro2:
            busca_nome = st.text_input("🔍 Buscar Cliente por Nome:")
            
        hoje = datetime.today()
        df_clientes = df_vendas.copy()
        
        if filtro_cli != "Todos os Clientes":
            mask_datas_validas = df_clientes['Data_Real'].notna()
            if filtro_cli == "Mês Atual":
                df_clientes = df_clientes[mask_datas_validas & (df_clientes['Data_Real'].dt.month == hoje.month) & (df_clientes['Data_Real'].dt.year == hoje.year)]
            elif filtro_cli == "Mês Anterior":
                mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                df_clientes = df_clientes[mask_datas_validas & (df_clientes['Data_Real'].dt.month == mes_ant) & (df_clientes['Data_Real'].dt.year == ano_ant)]
            elif filtro_cli == "Ano Atual":
                df_clientes = df_clientes[mask_datas_validas & (df_clientes['Data_Real'].dt.year == hoje.year)]
            elif filtro_cli == "Período Personalizado":
                df_clientes = df_clientes[mask_datas_validas & (df_clientes['Data_Real'].dt.date >= data_inicio) & (df_clientes['Data_Real'].dt.date <= data_fim)]
            
        if busca_nome.strip() != "":
            termo = busca_nome.strip()
            df_clientes = df_clientes[df_clientes['Nome do cliente'].astype(str).str.contains(termo, case=False, na=False)]
            
        if not df_clientes.empty:
            df_display = df_clientes.copy()
            df_display['Grupo e cota'] = df_display.apply(lambda x: f"{x['GRUPO']} / {x['COTA']}" if str(x['GRUPO']).strip() or str(x['COTA']).strip() else "N/A", axis=1)
            df_display['valor da venda'] = df_display['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            colunas_desejadas = ['Nome do cliente', 'Grupo e cota', 'PRODUTO', 'ADMINISTRADORA', 'valor da venda', 'VENDEDOR', 'DATA']
            nomes_bonitos = { 'Nome do cliente': 'Nome', 'PRODUTO': 'Tipo de Produto', 'ADMINISTRADORA': 'Administradora', 'VENDEDOR': 'Vendedor', 'DATA': 'Data da Venda' }
            df_display = df_display[colunas_desejadas].rename(columns=nomes_bonitos)
            
            # Força o alinhamento centralizado
            estilo_tabela = df_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
            st.dataframe(estilo_tabela, use_container_width=True, hide_index=True)
            
            total_vendas_tabela = df_clientes['Valor_Numerico'].sum()
            valor_formatado_total = f"R$ {total_vendas_tabela:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            st.markdown(f"""<div style="text-align: right; padding-top: 10px;"><h4 style="color: #ff6600; font-weight: bold; margin: 0;">TOTAL: {valor_formatado_total}</h4></div>""", unsafe_allow_html=True)
            
            # --- ÁREA DO PERFIL DO CLIENTE ---
            st.write("")
            st.markdown("### 📄 Entrar no Perfil do Cliente")
            
            lista_nomes = sorted([n for n in df_clientes['Nome do cliente'].astype(str).unique() if n.strip() != ""])
            cliente_selecionado = st.selectbox("Selecione um cliente para abrir a Ficha Completa:", [""] + lista_nomes)

            if cliente_selecionado != "":
                cotas_do_cliente = df_vendas[df_vendas['Nome do cliente'].astype(str) == cliente_selecionado].copy()

                st.success(f"**Perfil do Cliente:** {cliente_selecionado}")
                
                info1, info2 = st.columns(2)
                info1.metric("Total de Cotas Adquiridas", len(cotas_do_cliente))
                
                total_investido = cotas_do_cliente['Valor_Numerico'].sum()
                info2.metric("Volume Total Investido", f"R$ {total_investido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

                st.markdown(f"#### 📦 Cotas do Cliente ({len(cotas_do_cliente)})")
                cotas_do_cliente['Valor Formatado'] = cotas_do_cliente['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                colunas_ficha = ['DATA', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'Valor Formatado']
                
                ficha_display = cotas_do_cliente[colunas_ficha].rename(columns={'DATA': 'Data', 'ADMINISTRADORA': 'Administradora', 'PRODUTO': 'Produto', 'GRUPO': 'Grupo', 'COTA': 'Cota', 'Valor Formatado': 'Valor (R$)'})
                estilo_ficha = ficha_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                
                st.dataframe(estilo_ficha, use_container_width=True, hide_index=True)
                
        else:
            st.warning("Nenhum cliente encontrado com esses filtros ou termos de busca.")

        st.divider()

        # =========================================================
        # PARTE 2: GRÁFICOS
        # =========================================================
        st.subheader("📊 Gráficos de Vendas Globais")
        
        g_filtro1, g_filtro2 = st.columns(2)
        with g_filtro1:
            filtro_tempo_grafico = st.selectbox("⏳ Período para o Gráfico:", ["Mês Atual", "Mês Anterior", "Anual", "Todas as Vendas", "Período Personalizado"])
            
            if filtro_tempo_grafico == "Período Personalizado":
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    g_data_inicio = st.date_input("Data Inicial do Gráfico", format="DD/MM/YYYY", key="g_inicio")
                with col_g2:
                    g_data_fim = st.date_input("Data Final do Gráfico", format="DD/MM/YYYY", key="g_fim")
                    
        with g_filtro2:
            filtro_produto_grafico = st.selectbox("📦 Produto:", ["Todos", "Auto", "Imovel", "Moto", "Caminhao"])
            
        df_grafico_filtrado = df_vendas.copy()
        
        if filtro_tempo_grafico != "Todas as Vendas" and not df_grafico_filtrado['Data_Real'].isna().all():
            mask_datas_validas = df_grafico_filtrado['Data_Real'].notna()
            if filtro_tempo_grafico == "Mês Atual":
                df_grafico_filtrado = df_grafico_filtrado[mask_datas_validas & (df_grafico_filtrado['Data_Real'].dt.month == hoje.month) & (df_grafico_filtrado['Data_Real'].dt.year == hoje.year)]
            elif filtro_tempo_grafico == "Mês Anterior":
                mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                df_grafico_filtrado = df_grafico_filtrado[mask_datas_validas & (df_grafico_filtrado['Data_Real'].dt.month == mes_ant) & (df_grafico_filtrado['Data_Real'].dt.year == ano_ant)]
            elif filtro_tempo_grafico == "Anual":
                df_grafico_filtrado = df_grafico_filtrado[mask_datas_validas & (df_grafico_filtrado['Data_Real'].dt.year == hoje.year)]
            elif filtro_tempo_grafico == "Período Personalizado":
                df_grafico_filtrado = df_grafico_filtrado[mask_datas_validas & (df_grafico_filtrado['Data_Real'].dt.date >= g_data_inicio) & (df_grafico_filtrado['Data_Real'].dt.date <= g_data_fim)]
            
        if filtro_produto_grafico != "Todos":
            df_grafico_filtrado = df_grafico_filtrado[df_grafico_filtrado['PRODUTO'].astype(str).str.contains(filtro_produto_grafico, case=False, na=False)]
            
        if not df_grafico_filtrado.empty:
            total_cotas_graf = len(df_grafico_filtrado)
            soma_financeira = df_grafico_filtrado['Valor_Numerico'].sum()
            
            met_col1, met_col2 = st.columns(2)
            met_col1.metric(label="Volume Total Vendido (R$)", value=f"R$ {soma_financeira:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            met_col2.metric(label="Total de Cotas Vendidas", value=total_cotas_graf)
            st.write("")
            
            agrupar_por = 'PRODUTO' if filtro_produto_grafico == "Todos" else 'ADMINISTRADORA'
            df_pizza = df_grafico_filtrado[agrupar_por].value_counts().reset_index()
            df_pizza.columns = ['Categoria', 'Quantidade']
            
            grafico_pizza = alt.Chart(df_pizza).mark_arc(innerRadius=60).encode(
                theta=alt.Theta(field="Quantidade", type="quantitative"),
                color=alt.Color(field="Categoria", type="nominal"),
                tooltip=['Categoria', 'Quantidade']
            ).properties(height=350)
            
            gp_col1, gp_col2, gp_col3 = st.columns([1, 2, 1])
            with gp_col2:
                st.altair_chart(grafico_pizza, use_container_width=True)
        else:
            st.warning("📊 Não há vendas suficientes para gerar o gráfico com os filtros atuais.")
            
    else:
        st.info("O sistema ainda não possui vendas cadastradas na planilha.")

elif menu_selecionado == "Nova Venda":
    st.title("📝 Cadastrar Nova Venda")
    
    with st.form("form_venda"):
        col1, col2 = st.columns(2)
        with col1:
            data = st.date_input("Data da Venda", format="DD/MM/YYYY")
            cliente = st.text_input("Nome do Cliente *")
            telefone = st.text_input("Telefone (Opcional - só informativo, não vai para a planilha)")
            
            if st.session_state['perfil_logado'] == "Master":
                vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"])
            else:
                st.write(f"**Vendedor:** {st.session_state['nome_vendedor']}")
                vendedor = st.session_state['nome_vendedor']
                
        with col2:
            admin = st.selectbox("Administradora *", ["YAMAHA", "ITAÚ", "ROMA", "EMBRACON"])
            produto = st.selectbox("Produto *", ["Auto", "Imovel", "Moto"])
            grupo = st.text_input("Grupo *")
            cota = st.text_input("Cota *")
            valor = st.number_input("Valor da Venda (R$) *", min_value=0.0, step=1000.0)
            status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"])
        
        salvar = st.form_submit_button("Salvar Venda")
        
        if salvar:
            if cliente and grupo and cota and valor > 0:
                aba_vendas = planilha.worksheet("Vendas")
                nova_linha = [
                    "", # Coluna 1: ID_cliente 
                    cliente, # Coluna 2: Nome do cliente
                    str(data.strftime("%d/%m/%Y")), # Coluna 3: DATA
                    produto, # Coluna 4: PRODUTO
                    vendedor, # Coluna 5: VENDEDOR
                    grupo, # Coluna 6: GRUPO
                    cota, # Coluna 7: COTA
                    admin, # Coluna 8: ADMINISTRADORA
                    status, # Coluna 9: STATUS
                    valor # Coluna 10: VALOR
                ]
                aba_vendas.append_row(nova_linha)
                st.success(f"Venda de {cliente} salva com sucesso!")
            else:
                st.error("Preencha todos os campos obrigatórios (*).")

elif menu_selecionado == "Gerenciar Vendas (Editar/Deletar)":
    st.title("🛠️ Gerenciar e Editar Vendas")
    st.warning("Área Restrita (Apenas Sócios). Muito cuidado ao deletar informações!")
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_brutos = aba_vendas.get_all_values()
    
    if len(dados_brutos) > 1:
        df_vendas = pd.DataFrame(dados_brutos[1:])
        col_count = len(df_vendas.columns)
        if col_count < 10:
            for i in range(col_count, 10): df_vendas[i] = ""
        df_vendas = df_vendas.iloc[:, :10]
        
        df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
        
        opcoes_busca = df_vendas.apply(lambda row: f"Linha {row.name + 2} | Cliente: {row['Nome do cliente']} - Grupo/Cota: {row['GRUPO']}/{row['COTA']}", axis=1).tolist()
        venda_selecionada = st.selectbox("Selecione a venda que deseja alterar ou excluir:", [""] + opcoes_busca)
        
        if venda_selecionada:
            linha_planilha = int(venda_selecionada.split(" | ")[0].replace("Linha ", ""))
            idx_dataframe = linha_planilha - 2
            venda_atual = df_vendas.iloc[idx_dataframe]
            
            st.divider()
            st.subheader(f"Editando Venda: {venda_atual['Nome do cliente']}")
            
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome do Cliente", value=str(venda_atual['Nome do cliente']))
                novo_status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"], index=["Vendido", "Contemplado", "Cancelado"].index(venda_atual['STATUS'] if venda_atual['STATUS'] in ["Vendido", "Contemplado", "Cancelado"] else "Vendido"))
            with col2:
                val_atual = str(venda_atual['VALOR']).replace('R$', '').replace('.','').replace(',', '.').strip()
                try: val_float = float(val_atual)
                except: val_float = 0.0
                novo_valor = st.number_input("Valor da Venda (R$)", value=val_float)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Salvar Alterações"):
                    aba_vendas.update_cell(linha_planilha, 2, novo_nome)   
                    aba_vendas.update_cell(linha_planilha, 10, novo_valor) 
                    aba_vendas.update_cell(linha_planilha, 9, novo_status) 
                    st.success("Alterações salvas na planilha!")
                    st.rerun()
            with col_btn2:
                if st.button("🚨 DELETAR ESTA VENDA", type="primary"):
                    aba_vendas.delete_rows(linha_planilha)
                    st.error("Venda apagada permanentemente!")
                    st.rerun()
    else:
        st.info("Nenhuma venda para gerenciar.")

# =========================================================
# TELA DE RELATÓRIOS
# =========================================================
elif menu_selecionado == "Relatórios":
    st.title("📑 Relatórios Gerenciais")
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_brutos = aba_vendas.get_all_values()
    
    if len(dados_brutos) > 1:
        df_vendas = pd.DataFrame(dados_brutos[1:])
        col_count = len(df_vendas.columns)
        if col_count < 10:
            for i in range(col_count, 10): df_vendas[i] = ""
        df_vendas = df_vendas.iloc[:, :10]
        
        df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
        
        df_vendas['Data_Real'] = pd.to_datetime(df_vendas['DATA'], dayfirst=True, errors='coerce')
        df_vendas['Valor_Numerico'] = df_vendas['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip()
        df_vendas['Valor_Numerico'] = pd.to_numeric(df_vendas['Valor_Numerico'], errors='coerce').fillna(0.0)

        # Filtro Global de Tempo para os Relatórios
        col_rel_1, col_rel_2 = st.columns([1, 2])
        with col_rel_1:
            filtro_tempo_rel = st.selectbox("⏳ Selecione o Período dos Relatórios:", ["Mês Atual", "Mês Anterior", "Ano Atual", "Todas as Vendas", "Período Personalizado"])
            
            if filtro_tempo_rel == "Período Personalizado":
                r_d1, r_d2 = st.columns(2)
                with r_d1:
                    r_data_inicio = st.date_input("Data Inicial", format="DD/MM/YYYY", key="r_inicio")
                with r_d2:
                    r_data_fim = st.date_input("Data Final", format="DD/MM/YYYY", key="r_fim")
        
        hoje = datetime.today()
        df_filtrado = df_vendas.copy()
        
        if filtro_tempo_rel != "Todas as Vendas":
            mask_datas_validas = df_filtrado['Data_Real'].notna()
            if filtro_tempo_rel == "Mês Atual":
                df_filtrado = df_filtrado[mask_datas_validas & (df_filtrado['Data_Real'].dt.month == hoje.month) & (df_filtrado['Data_Real'].dt.year == hoje.year)]
            elif filtro_tempo_rel == "Mês Anterior":
                mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                df_filtrado = df_filtrado[mask_datas_validas & (df_filtrado['Data_Real'].dt.month == mes_ant) & (df_filtrado['Data_Real'].dt.year == ano_ant)]
            elif filtro_tempo_rel == "Ano Atual":
                df_filtrado = df_filtrado[mask_datas_validas & (df_filtrado['Data_Real'].dt.year == hoje.year)]
            elif filtro_tempo_rel == "Período Personalizado":
                df_filtrado = df_filtrado[mask_datas_validas & (df_filtrado['Data_Real'].dt.date >= r_data_inicio) & (df_filtrado['Data_Real'].dt.date <= r_data_fim)]
                
        # Filtro Master/Vendedor
        if st.session_state['perfil_logado'] == "Vendedor":
            df_filtrado = df_filtrado[df_filtrado['VENDEDOR'] == st.session_state['nome_vendedor']]
            
        st.divider()

        if df_filtrado.empty:
            st.warning("Nenhuma venda registrada no período selecionado.")
        else:
            # Criando o sistema de abas
            tab1, tab2, tab3 = st.tabs(["👤 Vendas por Usuário", "🏢 Vendas por Administradora", "💰 Comissões por Vendedor"])
            
            with tab1:
                st.subheader("Vendas por Usuário (Vendedor)")
                resumo_vendedor = df_filtrado.groupby('VENDEDOR').agg(
                    Quantidade=('Nome do cliente', 'count'),
                    Volume_Total=('Valor_Numerico', 'sum')
                ).reset_index()
                
                resumo_vendedor['Volume Formatado'] = resumo_vendedor['Volume_Total'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                # Força centralização nas tabelas de Relatório
                estilo_vendedor = resumo_vendedor[['VENDEDOR', 'Quantidade', 'Volume Formatado']].style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_vendedor, use_container_width=True, hide_index=True)
                
                grafico_vend = alt.Chart(resumo_vendedor).mark_bar(color='#ff6600').encode(
                    x=alt.X('VENDEDOR:N', title='Vendedor', sort='-y'),
                    y=alt.Y('Volume_Total:Q', title='Volume de Vendas (R$)'),
                    tooltip=['VENDEDOR', 'Quantidade', 'Volume_Total']
                ).properties(height=300)
                st.altair_chart(grafico_vend, use_container_width=True)

            with tab2:
                st.subheader("Vendas por Administradora")
                resumo_admin = df_filtrado.groupby('ADMINISTRADORA').agg(
                    Quantidade=('Nome do cliente', 'count'),
                    Volume_Total=('Valor_Numerico', 'sum')
                ).reset_index()
                
                resumo_admin['Volume Formatado'] = resumo_admin['Volume_Total'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                estilo_admin = resumo_admin[['ADMINISTRADORA', 'Quantidade', 'Volume Formatado']].style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_admin, use_container_width=True, hide_index=True)
                
                grafico_admin = alt.Chart(resumo_admin).mark_bar(color='#0f172a').encode(
                    x=alt.X('ADMINISTRADORA:N', title='Administradora', sort='-y'),
                    y=alt.Y('Volume_Total:Q', title='Volume de Vendas (R$)'),
                    tooltip=['ADMINISTRADORA', 'Quantidade', 'Volume_Total']
                ).properties(height=300)
                st.altair_chart(grafico_admin, use_container_width=True)

            with tab3:
                st.subheader("Relatório de Comissões Estimadas")
                st.info("💡 Como a planilha não tem uma coluna de % de comissão de cada vendedor, informe a comissão média abaixo para calcular a projeção financeira.")
                
                pct_comissao = st.number_input("Porcentagem Média de Comissão (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1)
                
                df_comissoes = df_filtrado.groupby('VENDEDOR').agg(Volume_Total=('Valor_Numerico', 'sum')).reset_index()
                df_comissoes['Comissão a Receber'] = df_comissoes['Volume_Total'] * (pct_comissao / 100)
                
                total_geral_comissao = df_comissoes['Comissão a Receber'].sum()
                
                st.metric("Comissão Total do Período (Todos os Vendedores)", f"R$ {total_geral_comissao:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                df_comissoes['Volume Total Vendido'] = df_comissoes['Volume_Total'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                df_comissoes['Comissão a Receber'] = df_comissoes['Comissão a Receber'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                estilo_comissao = df_comissoes[['VENDEDOR', 'Volume Total Vendido', 'Comissão a Receber']].style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_comissao, use_container_width=True, hide_index=True)

    else:
        st.info("O sistema ainda não possui vendas cadastradas na planilha.")

elif menu_selecionado == "Baixar Parcela":
    st.title("💰 Recebimento de Comissão (Baixa)")
    st.info("Esta tela calculará a divisão exata quando as parcelas forem geradas automaticamente.")

# --- TELAS DAS FERRAMENTAS ---
elif menu_selecionado == "🏍️ Simulador Yamaha": carregar_ferramenta("yamaha.html")
elif menu_selecionado == "🏦 Simulador Itaú": carregar_ferramenta("itau.html")
elif menu_selecionado == "🎯 Oportunidades Itaú": carregar_ferramenta("guia.html")
elif menu_selecionado == "⚖️ Financiamento x Consórcio": carregar_ferramenta("comparador.html")
