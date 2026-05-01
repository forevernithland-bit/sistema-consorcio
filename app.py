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

# Controle de sessão geral
if 'usuario_logado' not in st.session_state:
    st.session_state['usuario_logado'] = None
    st.session_state['perfil_logado'] = None
    st.session_state['nome_vendedor'] = None
if 'menu_lateral' not in st.session_state:
    st.session_state['menu_lateral'] = "🔐 Login (Área Restrita)"
if 'cliente_visualizado' not in st.session_state:
    st.session_state['cliente_visualizado'] = None
if 'key_tabela' not in st.session_state:
    st.session_state['key_tabela'] = 0

def carregar_ferramenta(nome_arquivo):
    try:
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            html_code = f.read()
            components.html(html_code, height=900, scrolling=True)
    except FileNotFoundError:
        st.error(f"⚠️ O arquivo {nome_arquivo} não foi encontrado. Certifique-se de ter criado ele no GitHub com este nome exato!")

# === 2. LÓGICA DO MENU LATERAL (Navegação Segura) ===
is_logado = st.session_state['usuario_logado'] is not None

st.sidebar.image("https://www.consorbens.com/assets/logo-consorbens-DZ8uSiSJ.png", use_column_width=True)
st.sidebar.write("") 

if not is_logado:
    opcoes_menu = ["🔐 Login (Área Restrita)", "🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
    st.sidebar.divider()
    st.sidebar.caption("Portal Consorbens © 2026")
else:
    st.sidebar.write(f"👤 **{st.session_state['nome_vendedor']}**")
    st.sidebar.divider()

    ferramentas_logadas = ["🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]

    if st.session_state['perfil_logado'] == "Master":
        opcoes_menu = ["Dashboard", "Nova Venda", "Gerenciar Vendas (Editar/Deletar)", "Relatórios", "Administradoras", "Baixar Parcela"] + ferramentas_logadas
    else:
        opcoes_menu = ["Dashboard", "Nova Venda", "Relatórios"] + ferramentas_logadas

# Acha a posição da página atual para não dar erro
try:
    idx_menu = opcoes_menu.index(st.session_state['menu_lateral'])
except ValueError:
    idx_menu = 0

menu_selecionado = st.sidebar.radio(
    " ", 
    opcoes_menu,
    index=idx_menu,
    label_visibility="collapsed"
)

# Atualiza silenciosamente a navegação
st.session_state['menu_lateral'] = menu_selecionado

if is_logado:
    st.sidebar.write("")
    if st.sidebar.button("Sair do Sistema"):
        st.session_state['usuario_logado'] = None
        st.session_state['perfil_logado'] = None
        st.session_state['nome_vendedor'] = None
        st.session_state['cliente_visualizado'] = None
        st.session_state['menu_lateral'] = "🔐 Login (Área Restrita)"
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
    button[kind="primary"] { background-color: #2b615e !important; border-color: #2b615e !important; color: #ffffff !important; font-weight: bold !important; }
    button[kind="primary"]:hover { background-color: #1a3c3a !important; border-color: #1a3c3a !important; color: #ffffff !important; transform: scale(1.02); transition: all 0.2s ease-in-out; }
"""

if is_simulator: css += """ .stApp { background-color: #0f172a !important; } """
else: css += """ .stApp { background-color: #ffffff !important; } """

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
                btn_login = st.form_submit_button("Entrar no Sistema", type="primary")
                
                if btn_login:
                    if usuario_input in USUARIOS and USUARIOS[usuario_input]["senha"] == senha_input:
                        st.session_state['usuario_logado'] = usuario_input
                        st.session_state['perfil_logado'] = USUARIOS[usuario_input]["perfil"]
                        st.session_state['nome_vendedor'] = USUARIOS[usuario_input]["nome"]
                        st.session_state['menu_lateral'] = "Dashboard" # Navegação super segura
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

try: aba_clientes = planilha.worksheet("Clientes")
except:
    aba_clientes = planilha.add_worksheet("Clientes", 1000, 6)
    aba_clientes.append_row(["Nome", "Telefone", "Email", "Endereco", "Aniversario", "Data_Cadastro"])

if menu_selecionado == "Dashboard":
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_brutos = aba_vendas.get_all_values()
    
    # -------------------------------------------------------------
    # SE O USUÁRIO CLICOU EM UM CLIENTE: MOSTRA A PÁGINA DO CLIENTE
    # -------------------------------------------------------------
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        
        # Botão voltar com reset de cache da tabela (Adeus Loop Infinito!)
        if st.button("⬅️ Voltar ao Dashboard"):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
            
        st.title(f"👤 Perfil do Cliente: {cliente_nome}")
        
        dados_cli = aba_clientes.get_all_records()
        df_cli = pd.DataFrame(dados_cli)
        
        info_cliente = {}
        if not df_cli.empty and 'Nome' in df_cli.columns:
            busca_cli = df_cli[df_cli['Nome'] == cliente_nome]
            if not busca_cli.empty:
                info_cliente = busca_cli.iloc[0].to_dict()

        is_master = st.session_state['perfil_logado'] == "Master"
        
        st.subheader("📋 Dados Cadastrais")
        if not is_master:
            st.info("🔒 Como Vendedor, você só pode visualizar estes dados. Para alterar, contate o Administrador.")
            
        with st.form("form_dados_cli"):
            c1, c2 = st.columns(2)
            endereco = c1.text_input("Endereço Completo", value=info_cliente.get("Endereco", ""), disabled=not is_master)
            telefone = c1.text_input("Telefone", value=info_cliente.get("Telefone", ""), disabled=not is_master)
            email = c2.text_input("E-mail", value=info_cliente.get("Email", ""), disabled=not is_master)
            aniversario = c2.text_input("Data de Aniversário (DD/MM)", value=info_cliente.get("Aniversario", ""), disabled=not is_master)
            
            if is_master:
                if st.form_submit_button("Salvar Alterações", type="primary"):
                    nomes_col = aba_clientes.col_values(1)
                    if cliente_nome in nomes_col:
                        row_idx = nomes_col.index(cliente_nome) + 1
                        aba_clientes.update_cell(row_idx, 2, telefone)
                        aba_clientes.update_cell(row_idx, 3, email)
                        aba_clientes.update_cell(row_idx, 4, endereco)
                        aba_clientes.update_cell(row_idx, 5, aniversario)
                    else:
                        aba_clientes.append_row([cliente_nome, telefone, email, endereco, aniversario, datetime.today().strftime("%d/%m/%Y")])
                    st.success("Dados do cliente atualizados com sucesso!")
                    st.rerun()
            else:
                st.form_submit_button("Salvar Alterações", disabled=True)

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        
        if len(dados_brutos) > 1:
            df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
            df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
            cotas_cliente = df_vendas[df_vendas['Nome do cliente'] == cliente_nome].copy()
            
            if not cotas_cliente.empty:
                cotas_cliente['Valor_Numerico'] = cotas_cliente['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip()
                cotas_cliente['Valor_Numerico'] = pd.to_numeric(cotas_cliente['Valor_Numerico'], errors='coerce').fillna(0.0)
                
                info_a, info_b = st.columns(2)
                info_a.metric("Total de Cotas Adquiridas", len(cotas_cliente))
                info_b.metric("Volume Total Investido", f"R$ {cotas_cliente['Valor_Numerico'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                cotas_cliente['Valor Formatado'] = cotas_cliente['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                colunas_ficha = ['DATA', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'Valor Formatado']
                
                ficha_display = cotas_cliente[colunas_ficha].rename(columns={'DATA': 'Data', 'ADMINISTRADORA': 'Administradora', 'PRODUTO': 'Produto', 'GRUPO': 'Grupo', 'COTA': 'Cota', 'Valor Formatado': 'Valor (R$)'})
                estilo_ficha = ficha_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_ficha, use_container_width=True, hide_index=True)
            else:
                st.warning("Nenhuma cota encontrada para este cliente.")

    # -------------------------------------------------------------
    # SE NÃO CLICOU EM NINGUÉM: MOSTRA O DASHBOARD NORMAL
    # -------------------------------------------------------------
    else:
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
            col_t1, col_t2 = st.columns([4, 1])
            with col_t1:
                st.subheader("👥 Ficha de Clientes")
            with col_t2:
                st.write("") 
                # Botão Nova Venda (Navegação Segura)
                if st.button("➕ Nova Venda", use_container_width=True, type="primary"):
                    st.session_state['menu_lateral'] = "Nova Venda"
                    st.rerun()
            
            c_filtro1, c_filtro2 = st.columns([1, 2])
            with c_filtro1:
                filtro_cli = st.selectbox("⏳ Filtro por Data da Venda:", ["Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
                if filtro_cli == "Período Personalizado":
                    col_d1, col_d2 = st.columns(2)
                    with col_d1: data_inicio = st.date_input("Data Inicial", format="DD/MM/YYYY")
                    with col_d2: data_fim = st.date_input("Data Final", format="DD/MM/YYYY")
            with c_filtro2:
                busca_nome = st.text_input("🔍 Buscar Cliente por Nome:")
                
            hoje = datetime.today()
            df_clientes = df_vendas.copy()
            
            if filtro_cli != "Todos os Clientes":
                mask_datas_validas = df_clientes['Data_Real'].notna()
                if filtro_cli == "Mês Atual": df_clientes = df_clientes[mask_datas_validas & (df_clientes['Data_Real'].dt.month == hoje.month) & (df_clientes['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Mês Anterior":
                    mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                    ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                    df_clientes = df_clientes[mask_datas_validas & (df_clientes['Data_Real'].dt.month == mes_ant) & (df_clientes['Data_Real'].dt.year == ano_ant)]
                elif filtro_cli == "Ano Atual": df_clientes = df_clientes[mask_datas_validas & (df_clientes['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Período Personalizado": df_clientes = df_clientes[mask_datas_validas & (df_clientes['Data_Real'].dt.date >= data_inicio) & (df_clientes['Data_Real'].dt.date <= data_fim)]
                
            if busca_nome.strip() != "":
                df_clientes = df_clientes[df_clientes['Nome do cliente'].astype(str).str.contains(busca_nome.strip(), case=False, na=False)]
                
            if not df_clientes.empty:
                df_display = df_clientes.copy()
                df_display['Grupo e cota'] = df_display.apply(lambda x: f"{x['GRUPO']} / {x['COTA']}" if str(x['GRUPO']).strip() or str(x['COTA']).strip() else "N/A", axis=1)
                df_display['valor da venda'] = df_display['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                colunas_desejadas = ['Nome do cliente', 'Grupo e cota', 'PRODUTO', 'ADMINISTRADORA', 'valor da venda', 'VENDEDOR', 'DATA']
                nomes_bonitos = { 'Nome do cliente': 'Nome', 'PRODUTO': 'Tipo de Produto', 'ADMINISTRADORA': 'Administradora', 'VENDEDOR': 'Vendedor', 'DATA': 'Data da Venda' }
                df_display = df_display[colunas_desejadas].rename(columns=nomes_bonitos)
                
                estilo_tabela = df_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                
                # A mágica do Reset da Tabela para não dar Loop no clique
                tabela_interativa = st.dataframe(
                    estilo_tabela, 
                    use_container_width=True, 
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"tabela_clientes_{st.session_state['key_tabela']}" 
                )
                
                total_vendas_tabela = df_clientes['Valor_Numerico'].sum()
                valor_formatado_total = f"R$ {total_vendas_tabela:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.markdown(f"""<div style="text-align: right; padding-top: 10px;"><h4 style="color: #2b615e; font-weight: bold; margin: 0;">TOTAL: {valor_formatado_total}</h4></div>""", unsafe_allow_html=True)
                
                linhas_selecionadas = tabela_interativa.selection.rows
                if len(linhas_selecionadas) > 0:
                    idx_linha = linhas_selecionadas[0]
                    cliente_clicado = df_display.iloc[idx_linha]['Nome']
                    st.session_state['cliente_visualizado'] = cliente_clicado
                    st.rerun()
                    
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
                    with col_g1: g_data_inicio = st.date_input("Data Inicial do Gráfico", format="DD/MM/YYYY", key="g_inicio")
                    with col_g2: g_data_fim = st.date_input("Data Final do Gráfico", format="DD/MM/YYYY", key="g_fim")
                        
            with g_filtro2:
                filtro_produto_grafico = st.selectbox("📦 Produto:", ["Todos", "Auto", "Imovel", "Moto", "Caminhao"])
                
            df_grafico_filtrado = df_vendas.copy()
            
            if filtro_tempo_grafico != "Todas as Vendas" and not df_grafico_filtrado['Data_Real'].isna().all():
                mask_datas_validas = df_grafico_filtrado['Data_Real'].notna()
                if filtro_tempo_grafico == "Mês Atual": df_grafico_filtrado = df_grafico_filtrado[mask_datas_validas & (df_grafico_filtrado['Data_Real'].dt.month == hoje.month) & (df_grafico_filtrado['Data_Real'].dt.year == hoje.year)]
                elif filtro_tempo_grafico == "Mês Anterior":
                    mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                    ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                    df_grafico_filtrado = df_grafico_filtrado[mask_datas_validas & (df_grafico_filtrado['Data_Real'].dt.month == mes_ant) & (df_grafico_filtrado['Data_Real'].dt.year == ano_ant)]
                elif filtro_tempo_grafico == "Anual": df_grafico_filtrado = df_grafico_filtrado[mask_datas_validas & (df_grafico_filtrado['Data_Real'].dt.year == hoje.year)]
                elif filtro_tempo_grafico == "Período Personalizado": df_grafico_filtrado = df_grafico_filtrado[mask_datas_validas & (df_grafico_filtrado['Data_Real'].dt.date >= g_data_inicio) & (df_grafico_filtrado['Data_Real'].dt.date <= g_data_fim)]
                
            if filtro_produto_grafico != "Todos":
                df_grafico_filtrado = df_grafico_filtrado[df_grafico_filtrado['PRODUTO'].astype(str).str.contains(filtro_produto_grafico, case=False, na=False)]
                
            if not df_grafico_filtrado.empty:
                soma_financeira = df_grafico_filtrado['Valor_Numerico'].sum()
                
                met_col1, met_col2 = st.columns(2)
                met_col1.metric(label="Volume Total Vendido (R$)", value=f"R$ {soma_financeira:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                met_col2.metric(label="Total de Cotas Vendidas", value=len(df_grafico_filtrado))
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
                with gp_col2: st.altair_chart(grafico_pizza, use_container_width=True)
            else:
                st.warning("📊 Não há vendas suficientes para gerar o gráfico com os filtros atuais.")
                
        else:
            st.info("O sistema ainda não possui vendas cadastradas na planilha.")

elif menu_selecionado == "Nova Venda":
    st.title("📝 Cadastrar Nova Venda")
    
    with st.form("form_venda"):
        st.subheader("1. Dados do Cliente")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            cliente = st.text_input("Nome do Cliente *")
            telefone = st.text_input("Telefone")
            endereco = st.text_input("Endereço Completo")
        with col_c2:
            email = st.text_input("E-mail")
            aniversario = st.text_input("Data de Aniversário (DD/MM)")
            
        st.subheader("2. Dados da Venda")
        col1, col2 = st.columns(2)
        with col1:
            data = st.date_input("Data da Venda", format="DD/MM/YYYY")
            if st.session_state['perfil_logado'] == "Master":
                vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"])
            else:
                st.write(f"**Vendedor:** {st.session_state['nome_vendedor']}")
                vendedor = st.session_state['nome_vendedor']
                
        with col2:
            admin = st.selectbox("Administradora *", ["YAMAHA", "ITAÚ", "ROMA", "EMBRACON"])
            produto = st.selectbox("Produto *", ["Auto", "Imovel", "Moto", "Caminhão", "Serviços"])
            grupo = st.text_input("Grupo *")
            cota = st.text_input("Cota *")
            valor = st.number_input("Valor da Venda (R$) *", min_value=0.0, step=1000.0)
            status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"])
        
        salvar = st.form_submit_button("Salvar Venda", type="primary")
        
        if salvar:
            if cliente and grupo and cota and valor > 0:
                aba_vendas = planilha.worksheet("Vendas")
                nova_linha = ["", cliente, str(data.strftime("%d/%m/%Y")), produto, vendedor, grupo, cota, admin, status, valor]
                aba_vendas.append_row(nova_linha)
                
                try: nomes_cadastrados = aba_clientes.col_values(1)
                except: nomes_cadastrados = []
                
                if cliente not in nomes_cadastrados:
                    aba_clientes.append_row([cliente, telefone, email, endereco, aniversario, str(datetime.today().strftime("%d/%m/%Y"))])
                
                st.success(f"Venda e Cadastro de {cliente} salvos com sucesso!")
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
                if st.button("Salvar Alterações", type="primary"):
                    aba_vendas.update_cell(linha_planilha, 2, novo_nome)   
                    aba_vendas.update_cell(linha_planilha, 10, novo_valor) 
                    aba_vendas.update_cell(linha_planilha, 9, novo_status) 
                    st.success("Alterações salvas na planilha!")
                    st.rerun()
            with col_btn2:
                if st.button("🚨 DELETAR ESTA VENDA"):
                    aba_vendas.delete_rows(linha_planilha)
                    st.error("Venda apagada permanentemente!")
                    st.rerun()
    else:
        st.info("Nenhuma venda para gerenciar.")

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

        col_rel_1, col_rel_2 = st.columns([1, 2])
        with col_rel_1:
            filtro_tempo_rel = st.selectbox("⏳ Selecione o Período dos Relatórios:", ["Mês Atual", "Mês Anterior", "Ano Atual", "Todas as Vendas", "Período Personalizado"])
            if filtro_tempo_rel == "Período Personalizado":
                r_d1, r_d2 = st.columns(2)
                with r_d1: r_data_inicio = st.date_input("Data Inicial", format="DD/MM/YYYY", key="r_inicio")
                with r_d2: r_data_fim = st.date_input("Data Final", format="DD/MM/YYYY", key="r_fim")
        
        hoje = datetime.today()
        df_filtrado = df_vendas.copy()
        
        if filtro_tempo_rel != "Todas as Vendas":
            mask_datas_validas = df_filtrado['Data_Real'].notna()
            if filtro_tempo_rel == "Mês Atual": df_filtrado = df_filtrado[mask_datas_validas & (df_filtrado['Data_Real'].dt.month == hoje.month) & (df_filtrado['Data_Real'].dt.year == hoje.year)]
            elif filtro_tempo_rel == "Mês Anterior":
                mes_ant = hoje.month - 1 if hoje.month > 1 else 12
                ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
                df_filtrado = df_filtrado[mask_datas_validas & (df_filtrado['Data_Real'].dt.month == mes_ant) & (df_filtrado['Data_Real'].dt.year == ano_ant)]
            elif filtro_tempo_rel == "Ano Atual": df_filtrado = df_filtrado[mask_datas_validas & (df_filtrado['Data_Real'].dt.year == hoje.year)]
            elif filtro_tempo_rel == "Período Personalizado": df_filtrado = df_filtrado[mask_datas_validas & (df_filtrado['Data_Real'].dt.date >= r_data_inicio) & (df_filtrado['Data_Real'].dt.date <= r_data_fim)]
                
        if st.session_state['perfil_logado'] == "Vendedor":
            df_filtrado = df_filtrado[df_filtrado['VENDEDOR'] == st.session_state['nome_vendedor']]
            
        st.divider()

        if df_filtrado.empty:
            st.warning("Nenhuma venda registrada no período selecionado.")
        else:
            tab1, tab2, tab3 = st.tabs(["👤 Vendas por Usuário", "🏢 Vendas por Administradora", "💰 Comissões por Vendedor"])
            
            with tab1:
                st.subheader("Vendas por Usuário (Vendedor)")
                resumo_vendedor = df_filtrado.groupby('VENDEDOR').agg(Quantidade=('Nome do cliente', 'count'), Volume_Total=('Valor_Numerico', 'sum')).reset_index()
                resumo_vendedor['Volume Formatado'] = resumo_vendedor['Volume_Total'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                estilo_vendedor = resumo_vendedor[['VENDEDOR', 'Quantidade', 'Volume Formatado']].style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_vendedor, use_container_width=True, hide_index=True)
                
            with tab2:
                st.subheader("Vendas por Administradora")
                resumo_admin = df_filtrado.groupby('ADMINISTRADORA').agg(Quantidade=('Nome do cliente', 'count'), Volume_Total=('Valor_Numerico', 'sum')).reset_index()
                resumo_admin['Volume Formatado'] = resumo_admin['Volume_Total'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                estilo_admin = resumo_admin[['ADMINISTRADORA', 'Quantidade', 'Volume Formatado']].style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_admin, use_container_width=True, hide_index=True)
                
            with tab3:
                st.subheader("Relatório de Comissões Estimadas")
                pct_comissao = st.number_input("Porcentagem Média de Comissão (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1)
                df_comissoes = df_filtrado.groupby('VENDEDOR').agg(Volume_Total=('Valor_Numerico', 'sum')).reset_index()
                df_comissoes['Comissão a Receber'] = df_comissoes['Volume_Total'] * (pct_comissao / 100)
                st.metric("Comissão Total do Período", f"R$ {df_comissoes['Comissão a Receber'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                df_comissoes['Volume Total Vendido'] = df_comissoes['Volume_Total'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                df_comissoes['Comissão a Receber'] = df_comissoes['Comissão a Receber'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                estilo_comissao = df_comissoes[['VENDEDOR', 'Volume Total Vendido', 'Comissão a Receber']].style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_comissao, use_container_width=True, hide_index=True)
    else:
        st.info("O sistema ainda não possui vendas cadastradas na planilha.")

elif menu_selecionado == "Administradoras":
    st.title("🏢 Gestão de Administradoras e Regras de Comissionamento")
    try: aba_admin = planilha.worksheet("Administradoras")
    except gspread.exceptions.WorksheetNotFound:
        aba_admin = planilha.add_worksheet(title="Administradoras", rows=100, cols=10)
        aba_admin.append_row(["Administradora", "Produto", "Comissão Total (%)", "Regra de Pagamento (Parcelas)"])
        st.rerun()

    dados_admin = aba_admin.get_all_values()
    if len(dados_admin) <= 1: df_admin = pd.DataFrame(columns=["Administradora", "Produto", "Comissão Total (%)", "Regra de Pagamento (Parcelas)"])
    else: df_admin = pd.DataFrame(dados_admin[1:], columns=dados_admin[0])

    tab_lista, tab_cadastro, tab_edicao = st.tabs(["📋 Regras Cadastradas", "➕ Nova Regra", "✏️ Editar ou Excluir"])

    with tab_lista:
        st.subheader("Lista de Regras Atuais")
        if not df_admin.empty:
            estilo_admin = df_admin.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
            st.dataframe(estilo_admin, use_container_width=True, hide_index=True)
        else: st.info("Nenhuma administradora cadastrada.")

    with tab_cadastro:
        st.subheader("Cadastrar Administradora e Comissão")
        with st.form("form_nova_admin"):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                nome_admin = st.text_input("Nome da Administradora *")
                produto_admin = st.selectbox("Produto *", ["Automóvel", "Caminhão", "Serviços", "Motos", "Imóveis"])
            with col_a2:
                comissao_total = st.number_input("Comissão Total (%) *", min_value=0.0, step=0.1, format="%.2f")
                regra_parcelas = st.text_area("Regras de Pagamento *")
            if st.form_submit_button("Salvar Regra", type="primary"):
                if nome_admin and produto_admin and comissao_total >= 0 and regra_parcelas:
                    aba_admin.append_row([nome_admin.upper(), produto_admin, f"{comissao_total}%", regra_parcelas])
                    st.success(f"Regra cadastrada com sucesso!")
                    st.rerun()
                else: st.error("Preencha todos os campos obrigatórios.")
                    
    with tab_edicao:
        st.subheader("Editar ou Excluir Regras")
        if not df_admin.empty:
            opcoes_admin = df_admin.apply(lambda row: f"Linha {row.name + 2} | {row['Administradora']} - {row['Produto']}", axis=1).tolist()
            regra_selecionada = st.selectbox("Selecione a regra para editar:", [""] + opcoes_admin)
            if regra_selecionada:
                linha_planilha_admin = int(regra_selecionada.split(" | ")[0].replace("Linha ", ""))
                idx_df = linha_planilha_admin - 2
                regra_atual = df_admin.iloc[idx_df]
                st.divider()
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    edit_nome = st.text_input("Administradora", value=regra_atual['Administradora'])
                    edit_prod = st.selectbox("Produto", ["Automóvel", "Caminhão", "Serviços", "Motos", "Imóveis"], index=["Automóvel", "Caminhão", "Serviços", "Motos", "Imóveis"].index(regra_atual['Produto']) if regra_atual['Produto'] in ["Automóvel", "Caminhão", "Serviços", "Motos", "Imóveis"] else 0)
                with col_e2:
                    val_comissao_atual = str(regra_atual['Comissão Total (%)']).replace('%', '').strip()
                    try: val_comissao_float = float(val_comissao_atual)
                    except: val_comissao_float = 0.0
                    edit_comissao = st.number_input("Comissão Total (%)", value=val_comissao_float)
                    edit_parcelas = st.text_area("Regra de Pagamento", value=regra_atual['Regra de Pagamento (Parcelas)'])
                col_btn_e1, col_btn_e2 = st.columns(2)
                with col_btn_e1:
                    if st.button("Salvar Alterações", type="primary"):
                        aba_admin.update_cell(linha_planilha_admin, 1, edit_nome.upper())
                        aba_admin.update_cell(linha_planilha_admin, 2, edit_prod)
                        aba_admin.update_cell(linha_planilha_admin, 3, f"{edit_comissao}%")
                        aba_admin.update_cell(linha_planilha_admin, 4, edit_parcelas)
                        st.success("Regra alterada com sucesso!")
                        st.rerun()
                with col_btn_e2:
                    if st.button("🚨 EXCLUIR REGRA PERMANENTEMENTE"):
                        aba_admin.delete_rows(linha_planilha_admin)
                        st.error("Regra deletada!")
                        st.rerun()

elif menu_selecionado == "Baixar Parcela":
    st.title("💰 Recebimento de Comissão (Baixa)")
    st.info("Esta tela calculará a divisão exata quando as parcelas forem geradas automaticamente.")
