import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import streamlit.components.v1 as components

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

# Logo isolada no topo
st.sidebar.image("https://www.consorbens.com/assets/logo-consorbens-DZ8uSiSJ.png", use_column_width=True)
st.sidebar.write("") # Espaço para desgrudar os links da logo

if not is_logado:
    # Apenas os links, sem nenhum texto adicional
    menu_selecionado = st.sidebar.radio(
        "Menu Principal", 
        [
            "🔐 Login (Área Restrita)",
            "🏍️ Simulador Yamaha",
            "🏦 Simulador Itaú",
            "🎯 Oportunidades Itaú",
            "⚖️ Financiamento x Consórcio"
        ],
        label_visibility="collapsed"
    )
    
    # Rodapé
    st.sidebar.divider()
    st.sidebar.caption("Portal Consorbens © 2026")
    
else:
    # Mostra quem está logado rapidamente e os links
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
        "Menu Principal", 
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
    /* Margens da tela */
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
    
    /* Menu Lateral Branco e Textos Escuros */
    [data-testid="stSidebar"] { background-color: #ffffff !important; }
    [data-testid="stSidebar"] * { color: #0f172a !important; }
    [data-testid="stSidebar"] hr { border-bottom-color: #e2e8f0 !important; }
    
    /* Esconde a palavra "Navegação" caso o label_visibility falhe */
    [data-testid="stSidebar"] .stRadio label { display: none !important; }
    
    /* Estilo do Botão de Sair */
    [data-testid="stSidebar"] button { border: 1px solid #cbd5e1 !important; background-color: #f8fafc !important; }

    /* ====== BOTÃO PARA REEXIBIR O MENU (A SETINHA QUE SUMIA) ====== */
    [data-testid="collapsedControl"] {
        background-color: #ff6600 !important; /* Laranja Consorbens */
        border-radius: 8px !important;
        box-shadow: 0px 4px 10px rgba(255, 102, 0, 0.6) !important;
        padding: 8px !important;
        margin-top: 15px !important;
        margin-left: 15px !important;
        opacity: 1 !important; 
        z-index: 999999 !important; /* Força ficar por cima do preto */
    }
    
    /* Garante que o ícone da setinha seja BRANCO e grande */
    [data-testid="collapsedControl"] svg {
        fill: #ffffff !important;
        color: #ffffff !important;
        stroke: #ffffff !important;
        width: 20px !important;
        height: 20px !important;
    }

    [data-testid="collapsedControl"]:hover {
        background-color: #cc5200 !important;
        transform: scale(1.1) !important;
    }
    
    /* ====== BOTÃO PARA ESCONDER O MENU (DENTRO DA BARRA BRANCA) ====== */
    [data-testid="stSidebarCollapseButton"] {
        background-color: #ff6600 !important;
        border-radius: 6px !important;
    }
    [data-testid="stSidebarCollapseButton"] svg {
        fill: #ffffff !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebarCollapseButton"]:hover {
        background-color: #cc5200 !important;
    }
    
    /* Esconde a barra branca inútil do topo do Streamlit */
    header[data-testid="stHeader"] { background-color: transparent !important; }
"""

if is_simulator:
    css += """
    /* Fundo PRETO apenas nos simuladores */
    .stApp { background-color: #0f172a !important; }
    """
else:
    css += """
    /* Fundo CLARO no CRM e Login */
    .stApp { background-color: #f8fafc !important; }
    """

css += "</style>"
st.markdown(css, unsafe_allow_html=True)

# === 4. RENDERIZAÇÃO DAS TELAS ===
if not is_logado:
    if menu_selecionado == "🔐 Login (Área Restrita)":
        
        # Cria um espaçamento no topo para empurrar o formulário para o meio
        st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        
        # Usa colunas invisíveis para espremer o formulário no centro (menor)
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
                    
    elif menu_selecionado == "🏍️ Simulador Yamaha":
        carregar_ferramenta("yamaha.html")
    elif menu_selecionado == "🏦 Simulador Itaú":
        carregar_ferramenta("itau.html")
    elif menu_selecionado == "🎯 Oportunidades Itaú":
        carregar_ferramenta("guia.html")
    elif menu_selecionado == "⚖️ Financiamento x Consórcio":
        carregar_ferramenta("comparador.html")
        
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
    st.title("📊 Painel de Vendas")
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_vendas = aba_vendas.get_all_records()
    
    if dados_vendas:
        df_vendas = pd.DataFrame(dados_vendas)
        if st.session_state['perfil_logado'] == "Vendedor":
            st.write("Aqui estão as vendas registradas por você:")
            df_vendas = df_vendas[df_vendas['Vendedor'] == st.session_state['nome_vendedor']]
        else:
            st.write("Visão Geral do Sistema (Todas as Vendas):")
            
        if not df_vendas.empty:
            st.dataframe(df_vendas.tail(10))
        else:
            st.info("Nenhuma venda encontrada para o seu usuário.")
    else:
        st.info("O sistema ainda não possui vendas cadastradas.")

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
    
    if dados_vendas:
        df_vendas = pd.DataFrame(dados_vendas)
        opcoes_busca = df_vendas.apply(lambda row: f"Linha {row.name + 2} | Cliente: {row['Nome_Cliente']} - Grupo/Cota: {row['Grupo']}/{row['Cota']}", axis=1).tolist()
        venda_selecionada = st.selectbox("Selecione a venda que deseja alterar ou excluir:", [""] + opcoes_busca)
        
        if venda_selecionada:
            linha_planilha = int(venda_selecionada.split(" | ")[0].replace("Linha ", ""))
            idx_dataframe = linha_planilha - 2
            venda_atual = df_vendas.iloc[idx_dataframe]
            
            st.divider()
            st.subheader(f"Editando Venda: {venda_atual['Nome_Cliente']}")
            
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome do Cliente", value=str(venda_atual['Nome_Cliente']))
                novo_status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"], index=["Vendido", "Contemplado", "Cancelado"].index(venda_atual.get('Status_Cliente', 'Vendido') if venda_atual.get('Status_Cliente') in ["Vendido", "Contemplado", "Cancelado"] else "Vendido"))
            with col2:
                novo_valor = st.number_input("Valor da Venda (R$)", value=float(venda_atual['Valor_Venda'] if str(venda_atual['Valor_Venda']).replace('.','',1).isdigit() else 0.0))

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Salvar Alterações"):
                    aba_vendas.update_cell(linha_planilha, 3, novo_nome)
                    aba_vendas.update_cell(linha_planilha, 13, novo_valor) 
                    aba_vendas.update_cell(linha_planilha, 14, novo_status)
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
elif menu_selecionado == "🏍️ Simulador Yamaha":
    carregar_ferramenta("yamaha.html")
elif menu_selecionado == "🏦 Simulador Itaú":
    carregar_ferramenta("itau.html")
elif menu_selecionado == "🎯 Oportunidades Itaú":
    carregar_ferramenta("guia.html")
elif menu_selecionado == "⚖️ Financiamento x Consórcio":
    carregar_ferramenta("comparador.html")
