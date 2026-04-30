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
        opcoes_menu = ["Dashboard", "Nova Venda", "Gerenciar Vendas (Editar/Deletar)", "Baixar Parcela"] + ferramentas_logadas
    else:
        opcoes_menu = ["Dashboard", "Nova Venda"] + ferramentas_logadas

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
    # Trocamos para get_all_values() para ler como uma matriz bruta, ignorando cabeçalhos!
    dados_brutos = aba_vendas.get_all_values()
    
    if len(dados_brutos) > 1:
        # Pula a linha 0 (cabeçalho) e transforma em DataFrame garantindo as posições numéricas
        df_vendas = pd.DataFrame(dados_brutos[1:])
        
        # Garante que a matriz tem pelo menos 14 colunas para não dar erro
        for i in range(len(df_vendas.columns), 14):
            df_vendas[i] = ""
            
        # Nomenclatura fixa baseada nas POSIÇÕES que o código salva as vendas
        df_vendas = df_vendas.rename(columns={
            1: 'Data_Venda',
            2: 'Nome_Cliente',
            3: 'Telefone_Cliente',
            7: 'Vendedor_Nome',
            8: 'Admin_Nome',
            9: 'Tipo_Produto',
            10: 'Grupo_Num',
            11: 'Cota_Num',
            12: 'Valor_Financeiro',
            13: 'Status_Venda'
        })
        
        # Converte Data de forma segura
        df_vendas['Data_Real'] = pd.to_datetime(df_vendas['Data_Venda'], format="%d/%m/%Y", errors='coerce')

        # Limpa o Valor Financeiro (transforma texto em número para somar)
        df_vendas['Valor_Numerico'] = df_vendas['Valor_Financeiro'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip()
        df_vendas['Valor_Numerico'] = pd.to_numeric(df_vendas['Valor_Numerico'], errors='coerce').fillna(0.0)

        # Filtro de vendedor
        if st.session_state['perfil_logado'] == "Vendedor":
            df_vendas = df_vendas[df_vendas['Vendedor_Nome'] == st.session_state['nome_vendedor']]
            
        # =========================================================
        # PARTE 1: GESTÃO E BUSCA DE CLIENTES
        # =========================================================
        st.subheader("👥 Ficha de Clientes")
        
        c_filtro1, c_filtro2 = st.columns([1, 2])
        with c_filtro1:
            filtro_cli = st.selectbox("⏳ Período de Cadastro:", ["Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual"])
        with c_filtro2:
            busca_nome = st.text_input("🔍 Buscar Cliente por Nome:")
            
        hoje = datetime.today()
        df_clientes = df_vendas.copy()
        
        # Aplicando Filtro de Tempo
        if not df_clientes['Data_Real'].isna().all():
            if filtro_cli == "Mês Atual":
                df_clientes = df_clientes[(df_clientes['Data_Real'].dt.month == hoje.month) & (df_clientes['Data_Real'].dt.year == hoje.year)]
            elif filtro_cli == "Mês Anterior":
                mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                df_clientes = df_clientes[(df_clientes['Data_Real'].dt.month == mes_ant) & (df_clientes['Data_Real'].dt.year == ano_ant)]
            elif filtro_cli == "Ano Atual":
                df_clientes = df_clientes[df_clientes['Data_Real'].dt.year == hoje.year]
            
        # Filtro de Busca
        if busca_nome:
            df_clientes = df_clientes[df_clientes['Nome_Cliente'].astype(str).str.contains(busca_nome, case=False, na=False)]
            
        if not df_clientes.empty:
            df_display = df_clientes.copy()
            
            # Formata Grupo e Cota (mesmo se vazios)
            df_display['Grupo e Cota'] = df_display['Grupo_Num'].astype(str) + " / " + df_display['Cota_Num'].astype(str)
            df_display['Grupo e Cota'] = df_display['Grupo e Cota'].replace(" / ", "N/A") # Limpa se os dois forem vazios
            
            # Ordenação exata solicitada
            colunas_desejadas = ['Nome_Cliente', 'Grupo e Cota', 'Tipo_Produto', 'Admin_Nome', 'Valor_Financeiro', 'Vendedor_Nome', 'Data_Venda']
            
            nomes_bonitos = {
                'Nome_Cliente': 'Nome',
                'Grupo e Cota': 'Grupo e Cota',
                'Tipo_Produto': 'Tipo de Produto',
                'Admin_Nome': 'Administradora',
                'Valor_Financeiro': 'Valor da Venda',
                'Vendedor_Nome': 'Vendedor',
                'Data_Venda': 'Data da Venda'
            }
            df_display = df_display[colunas_desejadas].rename(columns=nomes_bonitos)
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # --- ÁREA DO PERFIL DO CLIENTE ---
            st.write("")
            st.markdown("### 📄 Entrar no Perfil do Cliente")
            
            lista_clientes_filtrados = [""] + sorted(df_clientes['Nome_Cliente'].astype(str).unique().tolist())
            cliente_selecionado = st.selectbox("Selecione um cliente para abrir a Ficha Completa:", lista_clientes_filtrados)

            if cliente_selecionado != "":
                cotas_do_cliente = df_vendas[df_vendas['Nome_Cliente'].astype(str) == cliente_selecionado]

                st.success(f"**Perfil do Cliente:** {cliente_selecionado}")
                
                info1, info2, info3 = st.columns(3)
                info1.metric("Total de Cotas Adquiridas", len(cotas_do_cliente))
                
                total_investido = cotas_do_cliente['Valor_Numerico'].sum()
                info2.metric("Volume Total Investido", f"R$ {total_investido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                telefone = cotas_do_cliente.iloc[0].get('Telefone_Cliente', 'Não informado')
                info3.metric("Telefone de Contato", telefone if telefone.strip() != "" else 'Não informado')

                st.markdown(f"#### 📦 Cotas do Cliente ({len(cotas_do_cliente)})")
                
                colunas_ficha = ['Data_Venda', 'Admin_Nome', 'Tipo_Produto', 'Grupo_Num', 'Cota_Num', 'Valor_Financeiro']
                tabela_cotas = cotas_do_cliente[colunas_ficha].rename(columns={
                    'Data_Venda': 'Data', 'Admin_Nome': 'Administradora', 'Tipo_Produto': 'Produto', 'Grupo_Num': 'Grupo', 'Cota_Num': 'Cota', 'Valor_Financeiro': 'Valor (R$)'
                })
                
                st.dataframe(tabela_cotas, use_container_width=True, hide_index=True)
                
        else:
            st.warning("Nenhum cliente encontrado com esses filtros/busca.")

        st.divider()

        # =========================================================
        # PARTE 2: GRÁFICOS E SOMAS FINANCEIRAS
        # =========================================================
        st.subheader("📊 Gráficos de Vendas")
        
        g_filtro1, g_filtro2 = st.columns(2)
        with g_filtro1:
            filtro_tempo_grafico = st.selectbox("⏳ Período para o Gráfico:", ["Mês Atual", "Mês Anterior", "Anual", "Todas as Vendas"])
        with g_filtro2:
            filtro_produto_grafico = st.selectbox("📦 Produto:", ["Todos", "Auto", "Imovel", "Moto", "Caminhao"])
            
        df_grafico_filtrado = df_vendas.copy()
        
        if not df_grafico_filtrado['Data_Real'].isna().all():
            if filtro_tempo_grafico == "Mês Atual":
                df_grafico_filtrado = df_grafico_filtrado[(df_grafico_filtrado['Data_Real'].dt.month == hoje.month) & (df_grafico_filtrado['Data_Real'].dt.year == hoje.year)]
            elif filtro_tempo_grafico == "Mês Anterior":
                mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                df_grafico_filtrado = df_grafico_filtrado[(df_grafico_filtrado['Data_Real'].dt.month == mes_ant) & (df_grafico_filtrado['Data_Real'].dt.year == ano_ant)]
            elif filtro_tempo_grafico == "Anual":
                df_grafico_filtrado = df_grafico_filtrado[df_grafico_filtrado['Data_Real'].dt.year == hoje.year]
            
        if filtro_produto_grafico != "Todos":
            df_grafico_filtrado = df_grafico_filtrado[df_grafico_filtrado['Tipo_Produto'].astype(str).str.contains(filtro_produto_grafico, case=False, na=False)]
            
        if not df_grafico_filtrado.empty:
            total_cotas_graf = len(df_grafico_filtrado)
            soma_financeira = df_grafico_filtrado['Valor_Numerico'].sum()
            
            met_col1, met_col2 = st.columns(2)
            met_col1.metric(label="Volume Total Vendido (R$)", value=f"R$ {soma_financeira:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            met_col2.metric(label="Total de Cotas Vendidas", value=total_cotas_graf)
            st.write("")
            
            agrupar_por = 'Tipo_Produto' if filtro_produto_grafico == "Todos" else 'Admin_Nome'
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
            telefone = st.text_input("Telefone (Opcional)")
            
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
                    "", str(data.strftime("%d/%m/%Y")), cliente, telefone, "", "", "",
                    vendedor, admin, produto, grupo, cota, valor, status
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
        for i in range(len(df_vendas.columns), 14):
            df_vendas[i] = ""
            
        df_vendas = df_vendas.rename(columns={
            2: 'Nome_Cliente', 10: 'Grupo_Num', 11: 'Cota_Num', 12: 'Valor_Financeiro', 13: 'Status_Venda'
        })
        
        opcoes_busca = df_vendas.apply(lambda row: f"Linha {row.name + 2} | Cliente: {row.get('Nome_Cliente', 'S/N')} - Grupo/Cota: {row.get('Grupo_Num', '')}/{row.get('Cota_Num', '')}", axis=1).tolist()
        venda_selecionada = st.selectbox("Selecione a venda que deseja alterar ou excluir:", [""] + opcoes_busca)
        
        if venda_selecionada:
            linha_planilha = int(venda_selecionada.split(" | ")[0].replace("Linha ", ""))
            idx_dataframe = linha_planilha - 2
            venda_atual = df_vendas.iloc[idx_dataframe]
            
            st.divider()
            st.subheader(f"Editando Venda: {venda_atual.get('Nome_Cliente', '')}")
            
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome do Cliente", value=str(venda_atual.get('Nome_Cliente', '')))
                novo_status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"], index=["Vendido", "Contemplado", "Cancelado"].index(venda_atual.get('Status_Venda', 'Vendido') if venda_atual.get('Status_Venda') in ["Vendido", "Contemplado", "Cancelado"] else "Vendido"))
            with col2:
                val_atual = str(venda_atual.get('Valor_Financeiro', '0')).replace('R$', '').replace('.','').replace(',', '.').strip()
                try:
                    val_float = float(val_atual)
                except:
                    val_float = 0.0
                novo_valor = st.number_input("Valor da Venda (R$)", value=val_float)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Salvar Alterações"):
                    # Aqui usamos a posição cravada da planilha para não ter erro
                    aba_vendas.update_cell(linha_planilha, 3, novo_nome) # Coluna 3 = Cliente
                    aba_vendas.update_cell(linha_planilha, 13, novo_valor) # Coluna 13 = Valor
                    aba_vendas.update_cell(linha_planilha, 14, novo_status) # Coluna 14 = Status
                    st.success("Alterações salvas na planilha!")
                    st.rerun()
            with col_btn2:
                if st.button("🚨 DELETAR ESTA VENDA", type="primary"):
                    aba_vendas.delete_rows(linha_planilha)
                    st.error("Venda apagada permanentemente!")
                    st.rerun()
    else:
        st.info("Nenhuma venda para gerenciar.")

elif menu_selecionado == "Baixar Parcela":
    st.title("💰 Recebimento de Comissão (Baixa)")
    st.info("Esta tela calculará a divisão exata quando as parcelas forem geradas automaticamente.")

# --- TELAS DAS FERRAMENTAS ---
elif menu_selecionado == "🏍️ Simulador Yamaha": carregar_ferramenta("yamaha.html")
elif menu_selecionado == "🏦 Simulador Itaú": carregar_ferramenta("itau.html")
elif menu_selecionado == "🎯 Oportunidades Itaú": carregar_ferramenta("guia.html")
elif menu_selecionado == "⚖️ Financiamento x Consórcio": carregar_ferramenta("comparador.html")
