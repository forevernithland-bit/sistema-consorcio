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
    
    try:
        aba_vendas = planilha.worksheet("Vendas")
        dados_vendas = aba_vendas.get_all_records() # Lê a planilha com os títulos exatos
        df_vendas = pd.DataFrame(dados_vendas)
    except Exception as e:
        st.error("Erro ao ler a planilha. Verifique se o cabeçalho está correto.")
        df_vendas = pd.DataFrame()
    
    if not df_vendas.empty:
        # A MÁGICA: Caçador de Colunas inteligente
        def achar_col(keywords, excluir=[]):
            for col in df_vendas.columns:
                c_low = str(col).lower().strip()
                if any(kw in c_low for kw in keywords) and not any(ex in c_low for ex in excluir):
                    return col
            return None

        # Identifica as colunas independente do nome que estejam na sua planilha
        c_data = achar_col(['data'])
        c_cliente = achar_col(['cliente', 'nome'], excluir=['vendedor', 'consultor'])
        c_telefone = achar_col(['tel', 'cel'])
        c_vendedor = achar_col(['vendedor', 'consultor', 'corretor'])
        c_admin = achar_col(['admin', 'banco', 'consórcio', 'consorcio'])
        c_produto = achar_col(['prod', 'tipo'])
        c_grupo = achar_col(['grupo'])
        c_cota = achar_col(['cota'])
        c_valor = achar_col(['valor', 'venda', 'crédito', 'credito'])
        c_status = achar_col(['status', 'situ'])

        # Padroniza tudo internamente para não dar erro
        mapeamento = {}
        if c_data: mapeamento[c_data] = 'Data'
        if c_cliente: mapeamento[c_cliente] = 'Cliente'
        if c_telefone: mapeamento[c_telefone] = 'Telefone'
        if c_vendedor: mapeamento[c_vendedor] = 'Vendedor'
        if c_admin: mapeamento[c_admin] = 'Administradora'
        if c_produto: mapeamento[c_produto] = 'Produto'
        if c_grupo: mapeamento[c_grupo] = 'Grupo'
        if c_cota: mapeamento[c_cota] = 'Cota'
        if c_valor: mapeamento[c_valor] = 'Valor'
        if c_status: mapeamento[c_status] = 'Status'

        df_vendas = df_vendas.rename(columns=mapeamento)

        # Garante que as colunas padrão existam, mesmo vazias, para evitar bugs
        for padrao in ['Data', 'Cliente', 'Telefone', 'Vendedor', 'Administradora', 'Produto', 'Grupo', 'Cota', 'Valor', 'Status']:
            if padrao not in df_vendas.columns:
                df_vendas[padrao] = ""

        # LIMPEZA DOS DADOS (Converte Data e Dinheiro)
        df_vendas['Data_Real'] = pd.to_datetime(df_vendas['Data'], format="%d/%m/%Y", errors='coerce')
        
        df_vendas['Valor_Numerico'] = df_vendas['Valor'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip()
        df_vendas['Valor_Numerico'] = pd.to_numeric(df_vendas['Valor_Numerico'], errors='coerce').fillna(0.0)

        # Filtro Master x Vendedor
        if st.session_state['perfil_logado'] == "Vendedor":
            df_vendas = df_vendas[df_vendas['Vendedor'] == st.session_state['nome_vendedor']]
            
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
        
        # Filtros de Tempo (Clientes)
        if not df_clientes['Data_Real'].isna().all():
            if filtro_cli == "Mês Atual":
                df_clientes = df_clientes[(df_clientes['Data_Real'].dt.month == hoje.month) & (df_clientes['Data_Real'].dt.year == hoje.year)]
            elif filtro_cli == "Mês Anterior":
                mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                df_clientes = df_clientes[(df_clientes['Data_Real'].dt.month == mes_ant) & (df_clientes['Data_Real'].dt.year == ano_ant)]
            elif filtro_cli == "Ano Atual":
                df_clientes = df_clientes[df_clientes['Data_Real'].dt.year == hoje.year]
            
        # Filtro de Busca (Campo de Pesquisa Rápida)
        if busca_nome:
            df_clientes = df_clientes[df_clientes['Cliente'].astype(str).str.contains(busca_nome, case=False, na=False)]
            
        if not df_clientes.empty:
            df_display = df_clientes.copy()
            
            # Arrumando a visualização de Grupo e Cota
            df_display['Grupo'] = df_display['Grupo'].astype(str).str.replace('.0', '', regex=False).replace('nan', '').str.strip()
            df_display['Cota'] = df_display['Cota'].astype(str).str.replace('.0', '', regex=False).replace('nan', '').str.strip()
            df_display['Grupo e Cota'] = df_display.apply(
                lambda x: f"{x['Grupo']} / {x['Cota']}" if x['Grupo'] or x['Cota'] else "N/A", axis=1
            )
            
            # Formata o Dinheiro bonitinho para a tabela
            df_display['Valor Formatado'] = df_display['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            # ORDEM EXATA QUE VOCÊ PEDIU
            colunas_desejadas = ['Cliente', 'Grupo e Cota', 'Produto', 'Administradora', 'Valor Formatado', 'Vendedor', 'Data']
            
            nomes_bonitos = {
                'Cliente': 'Nome',
                'Grupo e Cota': 'Grupo e Cota',
                'Produto': 'Tipo de Produto',
                'Administradora': 'Administradora',
                'Valor Formatado': 'Valor da Venda',
                'Vendedor': 'Vendedor',
                'Data': 'Data da Venda'
            }
            
            df_display = df_display[colunas_desejadas].rename(columns=nomes_bonitos)
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # --- ÁREA DO PERFIL DO CLIENTE ---
            st.write("")
            st.markdown("### 📄 Entrar no Perfil do Cliente")
            
            # Limpa nomes vazios da lista
            lista_nomes = sorted([n for n in df_clientes['Cliente'].astype(str).unique() if n.strip() != ""])
            cliente_selecionado = st.selectbox("Selecione um cliente para abrir a Ficha Completa:", [""] + lista_nomes)

            if cliente_selecionado != "":
                cotas_do_cliente = df_vendas[df_vendas['Cliente'].astype(str) == cliente_selecionado].copy()

                st.success(f"**Perfil do Cliente:** {cliente_selecionado}")
                
                info1, info2, info3 = st.columns(3)
                info1.metric("Total de Cotas Adquiridas", len(cotas_do_cliente))
                
                total_investido = cotas_do_cliente['Valor_Numerico'].sum()
                info2.metric("Volume Total Investido", f"R$ {total_investido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                telefone = str(cotas_do_cliente.iloc[0]['Telefone']).strip()
                info3.metric("Telefone de Contato", telefone if telefone != "" else 'Não informado')

                st.markdown(f"#### 📦 Cotas do Cliente ({len(cotas_do_cliente)})")
                
                cotas_do_cliente['Valor (R$)'] = cotas_do_cliente['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                colunas_ficha = ['Data', 'Administradora', 'Produto', 'Grupo', 'Cota', 'Valor (R$)']
                st.dataframe(cotas_do_cliente[colunas_ficha], use_container_width=True, hide_index=True)
                
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
        
        # Filtros de Tempo (Gráficos)
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
            df_grafico_filtrado = df_grafico_filtrado[df_grafico_filtrado['Produto'].astype(str).str.contains(filtro_produto_grafico, case=False, na=False)]
            
        if not df_grafico_filtrado.empty:
            total_cotas_graf = len(df_grafico_filtrado)
            soma_financeira = df_grafico_filtrado['Valor_Numerico'].sum()
            
            met_col1, met_col2 = st.columns(2)
            met_col1.metric(label="Volume Total Vendido (R$)", value=f"R$ {soma_financeira:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            met_col2.metric(label="Total de Cotas Vendidas", value=total_cotas_graf)
            st.write("")
            
            agrupar_por = 'Produto' if filtro_produto_grafico == "Todos" else 'Administradora'
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
                cabecalhos_planilha = aba_vendas.row_values(1)
                
                if not cabecalhos_planilha:
                    # Se a planilha tiver zerada sem título, cria os títulos!
                    cabecalhos_planilha = ['Data', 'Cliente', 'Telefone', 'Vendedor', 'Administradora', 'Produto', 'Grupo', 'Cota', 'Valor', 'Status']
                    aba_vendas.append_row(cabecalhos_planilha)
                
                # Monta a nova venda Mapeando para os Títulos Exatos da sua Planilha Google
                nova_linha = [""] * len(cabecalhos_planilha)
                for i, cabecalho in enumerate(cabecalhos_planilha):
                    cb_low = str(cabecalho).lower().strip()
                    if 'data' in cb_low: nova_linha[i] = str(data.strftime("%d/%m/%Y"))
                    elif 'cliente' in cb_low or ('nome' in cb_low and 'vend' not in cb_low): nova_linha[i] = cliente
                    elif 'tel' in cb_low or 'cel' in cb_low: nova_linha[i] = telefone
                    elif 'vend' in cb_low or 'consultor' in cb_low: nova_linha[i] = vendedor
                    elif 'admin' in cb_low or 'banco' in cb_low: nova_linha[i] = admin
                    elif 'prod' in cb_low or 'tipo' in cb_low: nova_linha[i] = produto
                    elif 'grupo' in cb_low: nova_linha[i] = grupo
                    elif 'cota' in cb_low: nova_linha[i] = cota
                    elif 'valor' in cb_low or 'credito' in cb_low: nova_linha[i] = valor
                    elif 'status' in cb_low or 'situ' in cb_low: nova_linha[i] = status
                    
                aba_vendas.append_row(nova_linha)
                st.success(f"Venda de {cliente} salva com sucesso!")
            else:
                st.error("Preencha todos os campos obrigatórios (*).")

elif menu_selecionado == "Gerenciar Vendas (Editar/Deletar)":
    st.title("🛠️ Gerenciar e Editar Vendas")
    st.warning("Área Restrita (Apenas Sócios). Muito cuidado ao deletar informações!")
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_vendas = aba_vendas.get_all_records()
    
    if dados_vendas:
        df_vendas = pd.DataFrame(dados_vendas)
        cabecalhos = aba_vendas.row_values(1)
        
        # Puxa o número EXATO da coluna no Google Sheets para não editar a célula errada
        col_idx = {}
        for i, cabecalho in enumerate(cabecalhos):
            cb_low = str(cabecalho).lower().strip()
            if 'cliente' in cb_low or ('nome' in cb_low and 'vend' not in cb_low): 
                col_idx['Cliente'] = i + 1
                col_nome_real = cabecalho
            elif 'valor' in cb_low or 'credito' in cb_low: 
                col_idx['Valor'] = i + 1
                col_valor_real = cabecalho
            elif 'status' in cb_low or 'situ' in cb_low: 
                col_idx['Status'] = i + 1
                col_status_real = cabecalho
            elif 'grupo' in cb_low: col_grupo_real = cabecalho
            elif 'cota' in cb_low: col_cota_real = cabecalho

        opcoes_busca = df_vendas.apply(lambda row: f"Linha {row.name + 2} | Cliente: {row.get(col_nome_real, 'S/N')} - Grupo/Cota: {row.get(col_grupo_real, '')}/{row.get(col_cota_real, '')}", axis=1).tolist()
        venda_selecionada = st.selectbox("Selecione a venda que deseja alterar ou excluir:", [""] + opcoes_busca)
        
        if venda_selecionada:
            linha_planilha = int(venda_selecionada.split(" | ")[0].replace("Linha ", ""))
            idx_dataframe = linha_planilha - 2
            venda_atual = df_vendas.iloc[idx_dataframe]
            
            st.divider()
            st.subheader(f"Editando Venda: {venda_atual.get(col_nome_real, '')}")
            
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome do Cliente", value=str(venda_atual.get(col_nome_real, '')))
                novo_status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"], index=["Vendido", "Contemplado", "Cancelado"].index(venda_atual.get(col_status_real, 'Vendido') if venda_atual.get(col_status_real) in ["Vendido", "Contemplado", "Cancelado"] else "Vendido"))
            with col2:
                val_atual = str(venda_atual.get(col_valor_real, '0')).replace('R$', '').replace('.','').replace(',', '.').strip()
                try: val_float = float(val_atual)
                except: val_float = 0.0
                novo_valor = st.number_input("Valor da Venda (R$)", value=val_float)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Salvar Alterações"):
                    if 'Cliente' in col_idx: aba_vendas.update_cell(linha_planilha, col_idx['Cliente'], novo_nome)
                    if 'Valor' in col_idx: aba_vendas.update_cell(linha_planilha, col_idx['Valor'], novo_valor) 
                    if 'Status' in col_idx: aba_vendas.update_cell(linha_planilha, col_idx['Status'], novo_status)
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
