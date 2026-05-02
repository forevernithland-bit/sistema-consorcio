import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import requests 
import streamlit.components.v1 as components
import altair as alt
import unicodedata

# Configuração da página
st.set_page_config(page_title="Portal Consorbens", layout="wide", initial_sidebar_state="expanded")

# === 1. CONFIGURAÇÃO DE USUÁRIOS E SENHAS ===
USUARIOS = {
    "breno": {"senha": "123", "perfil": "Master", "nome": "BRENO LIMA"},
    "uriel": {"senha": "123", "perfil": "Master", "nome": "URIEL GOMES"},
    "vendedor1": {"senha": "123", "perfil": "Vendedor", "nome": "Vendedor Terceiro"},
    "consorbens": {"senha": "123", "perfil": "Vendedor", "nome": "Consorbens"}
}

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
        st.error(f"⚠️ O arquivo {nome_arquivo} não foi encontrado!")

# === MÁSCARAS E NORMALIZADORES ===
def formatar_telefone(tel):
    if not tel: return ""
    nums = ''.join(filter(str.isdigit, str(tel)))
    if len(nums) == 11: return f"({nums[:2]}) {nums[2:7]}-{nums[7:]}"
    elif len(nums) == 10: return f"({nums[:2]}) {nums[2:6]}-{nums[6:]}"
    return tel

def formatar_moeda(valor):
    if not valor: return "R$ 0,00"
    nums = ''.join(filter(str.isdigit, str(valor)))
    if not nums: return "R$ 0,00"
    val_float = float(nums) / 100
    return f"R$ {val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_brl_puro(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def normalizar_string(s):
    if pd.isna(s): return ""
    s = str(s).strip().upper()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s.replace(" ", "")

def normalizar_produto(p):
    p = normalizar_string(p)
    if p in ["AUTO", "AUTOMOVEL", "VEICULO"]: return "AUTO"
    if p in ["IMOVEL", "IMOVEIS"]: return "IMOVEL"
    if p in ["MOTO", "MOTOS", "MOTOCICLETA"]: return "MOTO"
    if p in ["CAMINHAO", "CAMINHOES"]: return "CAMINHAO"
    if p in ["SERVICO", "SERVICOS"]: return "SERVICO"
    return p

def parse_float_safe(v):
    try:
        v_str = str(v).replace('%', '').replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.').strip()
        if not v_str: return 0.0
        return float(v_str)
    except: return 0.0

def carregar_df_admin_seguro(aba):
    try:
        dados = aba.get_all_values()
        cabecalho = ["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)]
        if len(dados) > 1:
            linhas_completas = [r + [""] * (27 - len(r)) for r in dados[1:]]
            df = pd.DataFrame([r[:27] for r in linhas_completas], columns=cabecalho)
            df['Admin_Norm'] = df['Administradora'].apply(normalizar_string)
            df['Prod_Norm'] = df['Produto'].apply(normalizar_produto)
            return df
    except: pass
    return pd.DataFrame(columns=["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)])

# === 2. LÓGICA DO MENU LATERAL ===
is_logado = st.session_state['usuario_logado'] is not None

if is_logado:
    st.sidebar.markdown(f"<div style='color: #0f172a; font-weight: bold; font-size: 14px; margin-bottom: 10px;'>👤 {st.session_state['nome_vendedor'].upper()}</div>", unsafe_allow_html=True)
st.sidebar.image("https://www.consorbens.com/assets/logo-consorbens-DZ8uSiSJ.png", use_column_width=True)

if not is_logado:
    opcoes_menu = ["🔐 Login (Área Restrita)", "🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
    selecao = st.sidebar.radio(" ", opcoes_menu, label_visibility="collapsed")
    if selecao != st.session_state['menu_lateral']:
        st.session_state['menu_lateral'] = selecao
        st.rerun()
else:
    st.sidebar.divider() 
    opcoes_principais = ["Dashboard", "Nova Venda", "Relatórios", "Regras de Comissão", "Baixar Parcela"] if st.session_state['perfil_logado'] == "Master" else ["Dashboard", "Nova Venda", "Relatórios"]
    selecao_principal = st.sidebar.radio(" ", opcoes_principais, label_visibility="collapsed")
    if selecao_principal != st.session_state['menu_lateral']:
        st.session_state['menu_lateral'] = selecao_principal
        st.session_state['cliente_visualizado'] = None
        st.rerun()
    if st.sidebar.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

# === 4. CONEXÃO PLANILHA ===
@st.cache_resource
def conectar_planilha():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    return gc.open("Sistema CRM")

planilha = conectar_planilha()
aba_vendas = planilha.worksheet("Vendas")
aba_clientes = planilha.worksheet("Clientes")
aba_admin = planilha.worksheet("Administradoras")
aba_admin_cad = planilha.worksheet("Cad_Administradoras")
aba_cfg = planilha.worksheet("Config_Interna")

cfg_data = aba_cfg.get_all_values()
cfg = {k: parse_float_safe(v) for k, v in zip(cfg_data[0], cfg_data[1])}

dados_brutos = aba_vendas.get_all_values()
if len(dados_brutos) > 1:
    df_vendas_global = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
    df_vendas_global.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
    df_vendas_global['Data_Real'] = pd.to_datetime(df_vendas_global['DATA'], format="%d/%m/%Y", errors='coerce')
    df_vendas_global['Valor_Numerico'] = df_vendas_global['VALOR'].apply(parse_float_safe)
else:
    df_vendas_global = pd.DataFrame()

# === RENDERIZAÇÃO ===
menu_selecionado = st.session_state['menu_lateral']

if not is_logado:
    if menu_selecionado == "🔐 Login (Área Restrita)":
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        _, col_meio, _ = st.columns([1, 1.2, 1])
        with col_meio:
            with st.form("form_login"):
                u_in = st.text_input("Usuário").lower()
                s_in = st.text_input("Senha", type="password")
                _, btn_col, _ = st.columns([1, 1.5, 1])
                with btn_col:
                    if st.form_submit_button("ENTRAR", type="primary", use_container_width=True):
                        if u_in in USUARIOS and USUARIOS[u_in]["senha"] == s_in:
                            st.session_state['usuario_logado'], st.session_state['perfil_logado'], st.session_state['nome_vendedor'] = u_in, USUARIOS[u_in]["perfil"], USUARIOS[u_in]["nome"]
                            st.session_state['menu_lateral'] = "Dashboard"
                            st.rerun()
                        else: st.error("❌ Acesso negado.")
    else: carregar_ferramenta("yamaha.html") if "Yamaha" in menu_selecionado else None
    st.stop()

if menu_selecionado == "Dashboard":
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        if st.button("⬅️ Voltar"): st.session_state['cliente_visualizado'] = None; st.rerun()
        
        # Visão simplificada (Cotas e Previsão)
        st.subheader("📦 Cotas do Cliente")
        cotas_cliente = df_vendas_global[df_vendas_global['Nome do cliente'] == cliente_nome].copy()
        st.dataframe(cotas_cliente[['DATA', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'VENDEDOR', 'VALOR']], use_container_width=True, hide_index=True)
        
        st.subheader("📈 Previsão de Comissionamento")
        df_admin_regras = carregar_df_admin_seguro(aba_admin)
        # ... lógica de cálculo de comissão aqui ...
        
        if st.session_state['perfil_logado'] == "Master":
            with st.expander("⚙️ Gerenciar Vendedor / Cota"):
                cota_sel = st.selectbox("Selecione a cota:", cotas_cliente.apply(lambda x: f"Linha {x.name + 2} | {x['GRUPO']}/{x['COTA']}", axis=1))
                v_list = ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]
                novo_v = st.selectbox("Alterar Vendedor:", v_list)
                if st.button("Salvar Alteração"):
                    ln = int(cota_sel.split(" | ")[0].replace("Linha ", ""))
                    aba_vendas.update_cell(ln, 5, novo_v)
                    st.success("Alterado!"); st.rerun()

    else:
        st.markdown("### 📊 Dashboard de Vendas")
        if not df_vendas_global.empty:
            df_v = df_vendas_global.copy()
            if st.session_state['perfil_logado'] == "Vendedor": df_v = df_v[df_v['VENDEDOR'] == st.session_state['nome_vendedor']]
            
            # CORREÇÃO DO ERRO: Usando método de seleção padrão do st.dataframe
            tabela_seletor = st.dataframe(df_v[['Nome do cliente', 'PRODUTO', 'VENDEDOR', 'VALOR']], 
                                          on_select="rerun", 
                                          selection_mode="single-row", 
                                          use_container_width=True, 
                                          hide_index=True)
            
            # Pega a linha selecionada de forma segura
            if hasattr(tabela_seletor, 'selection') and tabela_seletor.selection.rows:
                idx_sel = tabela_seletor.selection.rows[0]
                st.session_state['cliente_visualizado'] = df_v.iloc[idx_sel]['Nome do cliente']
                st.rerun()
