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

# Função inteligente para achar a coluna certa na planilha, não importa a ordem
def encontra_coluna(df, palavras_chave):
    for palavra in palavras_chave:
        for col in df.columns:
            if palavra.lower() in str(col).lower() and str(col).strip() != "":
                return col
    return None

if menu_selecionado == "Dashboard":
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_vendas = aba_vendas.get_all_records()
    
    if dados_vendas:
        df_vendas = pd.DataFrame(dados_vendas)
        colunas = df_vendas.columns
        
        # Mapeamento Inteligente
        col_data = encontra_coluna(df_vendas, ['data']) or (colunas[1] if len(colunas) > 1 else colunas[0])
        col_cliente = encontra_coluna(df_vendas, ['cliente', 'nome']) or (colunas[2] if len(colunas) > 2 else colunas[0])
        col_vend = encontra_coluna(df_vendas, ['vendedor', 'corretor']) or (colunas[7] if len(colunas) > 7 else colunas[0])
        col_admin = encontra_coluna(df_vendas, ['admin', 'administradora']) or (colunas[8] if len(colunas) > 8 else colunas[0])
        col_prod = encontra_coluna(df_vendas, ['produto', 'tipo']) or (colunas[9] if len(colunas) > 9 else colunas[0])
        col_grupo = encontra_coluna(df_vendas, ['grupo']) or (colunas[10] if len(colunas) > 10 else colunas[0])
        col_cota = encontra_coluna(df_vendas, ['cota']) or (colunas[11] if len(colunas) > 11 else colunas[0])
        col_valor = encontra_coluna(df_vendas, ['valor', 'venda', 'preço']) or (colunas[12] if len(colunas) > 12 else colunas[0])
        col_status = encontra_coluna(df_vendas, ['status']) or (colunas[13] if len(colunas) > 13 else colunas[0])
        
        # Converte Datas
        if col_data in df_vendas.columns:
            df_vendas['Data_Real'] = pd.to_datetime(df_vendas[col_data], format="%d/%m/%Y", errors='coerce')
        else:
            df_vendas['Data_Real'] = pd.NaT

        # Limpa o dinheiro ("R$ 26.143,00" vira 26143.00 para o computador conseguir somar)
        if col_valor in df_vendas.columns:
            df_vendas['Valor_Numerico'] = df_vendas[col_valor].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip()
            df_vendas['Valor_Numerico'] = pd.to_numeric(df_vendas['Valor_Numerico'], errors='coerce').fillna(0.0)
        else:
            df_vendas['Valor_Numerico'] = 0.0

        # Filtro de vendedor
        if st.session_state['perfil_logado'] == "Vendedor" and col_vend in df_vendas.columns:
            df_vendas = df_vendas[df_vendas[col_vend] == st.session_state['nome_vendedor']]
            
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
        
        if not df_clientes['Data_Real'].isna().all():
            if filtro_cli == "Mês Atual":
                df_clientes = df_clientes[(df_clientes['Data_Real'].dt.month == hoje.month) & (df_clientes['Data_Real'].dt.year == hoje.year)]
            elif filtro_cli == "Mês Anterior":
                mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                df_clientes = df_clientes[(df_clientes['Data_Real'].dt.month == mes_ant) & (df_clientes['Data_Real'].dt.year == ano_ant)]
            elif filtro_cli == "Ano Atual":
                df_clientes = df_clientes[df_clientes['Data_Real'].dt.year == hoje.year]
            
        if busca_nome and col_cliente in df_clientes.columns:
            df_clientes = df_clientes[df_clientes[col_cliente].astype(str).str.contains(busca_nome, case=False, na=False)]
            
        if not df_clientes.empty:
            df_display = df_clientes.copy()
            
            # Formata Grupo e Cota
            if col_grupo in df_display.columns and col_cota in df_display.columns:
                df_display['Grupo e Cota'] = df_display[col_grupo].astype(str) + " / " + df_display[col_cota].astype(str)
            elif col_grupo in df_display.columns:
                df_display['Grupo e Cota'] = df_display[col_grupo].astype(str)
            else:
                df_display['Grupo e Cota'] = "N/A"
            
            # Ordena e renomeia as colunas do jeito que você pediu
            colunas_desejadas = [col_cliente, 'Grupo e Cota', col_prod, col_admin, col_valor, col_vend, col_data]
            colunas_mostrar = [c for c in colunas_desejadas if c in df_display.columns]
            
            nomes_bonitos = {
                col_cliente: 'Nome',
                'Grupo e Cota': 'Grupo e Cota',
                col_prod: 'Tipo de Produto',
                col_admin: 'Administradora',
                col_valor: 'Valor da Venda',
                col_vend: 'Vendedor',
                col_data: 'Data da Venda'
            }
            df_display = df_display[colunas_mostrar].rename(columns=nomes_bonitos)
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # --- ÁREA DO PERFIL DO CLIENTE ---
            st.write("")
            st.markdown("### 📄 Entrar no Perfil do Cliente")
            
            if col_cliente in df_clientes.columns:
                lista_clientes_filtrados = [""] + sorted(df_clientes[col_cliente].astype(str).unique().tolist())
                cliente_selecionado = st.selectbox("Selecione um cliente para abrir a Ficha Completa:", lista_clientes_filtrados)

                if cliente_selecionado != "":
                    cotas_do_cliente = df_vendas[df_vendas[col_cliente].astype(str) == cliente_selecionado]

                    st.success(f"**Perfil do Cliente:** {cliente_selecionado}")
                    
                    info1, info2, info3 = st.columns(3)
                    info1.metric("Total de Cotas Adquiridas", len(cotas_do_cliente))
                    
                    total_investido = cotas_do_cliente['Valor_Numerico'].sum()
                    info2.metric("Volume Total Investido", f"R$ {total_investido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    
                    telefone_col = encontra_coluna(cotas_do_cliente, ['telefone', 'tel'])
                    telefone = cotas_do_cliente.iloc[0].get(telefone_col, 'Não informado') if telefone_col else 'Não informado'
                    info3.metric("Telefone de Contato", telefone)

                    st.markdown(f"#### 📦 Cotas do Cliente ({len(cotas_do_cliente)})")
                    
                    colunas_ficha = [c for c in [col_data, col_admin, col_prod, col_grupo, col_cota, col_valor] if c in cotas_do_cliente.columns]
                    tabela_cotas = cotas_do_cliente[colunas_ficha].rename(columns={
                        col_data: 'Data', col_admin: 'Administradora', col_prod: 'Produto', col_grupo: 'Grupo', col_cota: 'Cota', col_valor: 'Valor (R$)'
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
            
        if filtro_produto_grafico != "Todos" and col_prod in df_grafico_filtrado.columns:
            df_grafico_filtrado = df_grafico_filtrado[df_grafico_filtrado[col_prod].astype(str).str.contains(filtro_produto_grafico, case=False, na=False)]
            
        if not df_grafico_filtrado.empty:
            
            total_cotas_graf = len(df_grafico_filtrado)
            soma_financeira = df_grafico_filtrado['Valor_Numerico'].sum()
            
            met_col1, met_col2 = st.columns(2)
            met_col1.metric(label="Volume Total Vendido (R$)", value=f"R$ {soma_financeira:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            met_col2.metric(label="Total de Cotas Vendidas", value=total_cotas_graf)
            st.write("")
            
            agrupar_por = col_prod if filtro_produto_grafico == "Todos" else col_admin
            if agrupar_por in df_grafico_filtrado.columns:
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
                st.warning("Faltam colunas na planilha para gerar este gráfico.")
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
    dados_vendas = aba_vendas.get_all_records()
    
    # Função segura copiada do Dashboard para evitar quebrar esta tela também
    def encontra_coluna(df, palavras_chave):
        for palavra in palavras_chave:
            for col in df.columns:
                if palavra.lower() in str(col).lower() and str(col).strip() != "":
                    return col
        return None

    if dados_vendas:
        df_vendas = pd.DataFrame(dados_vendas)
        col_cliente = encontra_coluna(df_vendas, ['cliente', 'nome']) or df_vendas.columns[2]
        col_grupo = encontra_coluna(df_vendas, ['grupo']) or df_vendas.columns[10]
        col_cota = encontra_coluna(df_vendas, ['cota']) or df_vendas.columns[11]
        col_valor = encontra_coluna(df_vendas, ['valor']) or df_vendas.columns[12]
        col_status = encontra_coluna(df_vendas, ['status']) or df_vendas.columns[13]

        opcoes_busca = df_vendas.apply(lambda row: f"Linha {row.name + 2} | Cliente: {row.get(col_cliente, 'S/N')} - Grupo/Cota: {row.get(col_grupo, '')}/{row.get(col_cota, '')}", axis=1).tolist()
        venda_selecionada = st.selectbox("Selecione a venda que deseja alterar ou excluir:", [""] + opcoes_busca)
        
        if venda_selecionada:
            linha_planilha = int(venda_selecionada.split(" | ")[0].replace("Linha ", ""))
            idx_dataframe = linha_planilha - 2
            venda_atual = df_vendas.iloc[idx_dataframe]
            
            st.divider()
            st.subheader(f"Editando Venda: {venda_atual.get(col_cliente, '')}")
            
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome do Cliente", value=str(venda_atual.get(col_cliente, '')))
                novo_status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"], index=["Vendido", "Contemplado", "Cancelado"].index(venda_atual.get(col_status, 'Vendido') if venda_atual.get(col_status) in ["Vendido", "Contemplado", "Cancelado"] else "Vendido"))
            with col2:
                # Trata o valor monetário caso tenha vindo como string com "R$"
                val_atual = str(venda_atual.get(col_valor, '0')).replace('R$', '').replace('.','').replace(',', '.').strip()
                try:
                    val_float = float(val_atual)
                except:
                    val_float = 0.0
                novo_valor = st.number_input("Valor da Venda (R$)", value=val_float)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Salvar Alterações"):
                    # Precisamos descobrir a letra exata da coluna ou atualizar a linha inteira.
                    # Para simplificar e evitar erros de coluna, vamos deixar essa parte pendente de refatoração futura, 
                    # mas atualizando via índice padrão por agora (como estava antes).
                    aba_vendas.update_cell(linha_planilha, df_vendas.columns.get_loc(col_cliente) + 1, novo_nome)
                    aba_vendas.update_cell(linha_planilha, df_vendas.columns.get_loc(col_valor) + 1, novo_valor) 
                    aba_vendas.update_cell(linha_planilha, df_vendas.columns.get_loc(col_status) + 1, novo_status)
                    st.success("Alterações salvas na planilha!")
                    st.rerun()
            with col_btn2:
                if st.button("🚨 DELETAR ESTA VENDA", type="primary"):
                    aba_vendas.delete_rows(linha_planilha)
                    st.error("Venda apagada permanentemente!")
                    st.rerun()

elif menu_selecionado == "Baixar Parcela":
    st.title("💰 Recebimento de Comissão (Baixa)")
    st.info("Esta tela calculará a divisão exata quando as parcelas forem geradas automaticamente.")

# --- TELAS DAS FERRAMENTAS ---
elif menu_selecionado == "🏍️ Simulador Yamaha": carregar_ferramenta("yamaha.html")
elif menu_selecionado == "🏦 Simulador Itaú": carregar_ferramenta("itau.html")
elif menu_selecionado == "🎯 Oportunidades Itaú": carregar_ferramenta("guia.html")
elif menu_selecionado == "⚖️ Financiamento x Consórcio": carregar_ferramenta("comparador.html")
