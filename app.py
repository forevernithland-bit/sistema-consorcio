import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import calendar
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

# === MÁSCARAS INTELIGENTES E NORMALIZADORES ===
def formatar_telefone(tel):
    if not tel: return ""
    nums = ''.join(filter(str.isdigit, str(tel)))
    if len(nums) == 11: return f"({nums[:2]}) {nums[2:7]}-{nums[7:]}"
    elif len(nums) == 10: return f"({nums[:2]}) {nums[2:6]}-{nums[6:]}"
    return tel

def formatar_data(data_str):
    if not data_str: return ""
    nums = ''.join(filter(str.isdigit, str(data_str)))
    if len(nums) >= 8: return f"{nums[:2]}/{nums[2:4]}/{nums[4:8]}"
    elif len(nums) >= 4: return f"{nums[:2]}/{nums[2:4]}/{nums[4:]}"
    elif len(nums) >= 2: return f"{nums[:2]}/{nums[2:]}"
    return nums

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
    s = s.replace(" ", "")
    return s

def normalizar_produto(p):
    p = normalizar_string(p)
    if p in ["AUTO", "AUTOMOVEL", "VEICULO"]: return "AUTO"
    if p in ["IMOVEL", "IMOVEIS"]: return "IMOVEL"
    if p in ["MOTO", "MOTOS", "MOTOCICLETA"]: return "MOTO"
    if p in ["CAMINHAO", "CAMINHOES"]: return "CAMINHAO"
    if p in ["SERVICO", "SERVICOS"]: return "SERVICOS"
    return p

def obter_index_produto(p_str):
    norm = normalizar_produto(p_str)
    mapping = {"AUTO": 0, "IMOVEL": 1, "MOTO": 2, "CAMINHAO": 3, "SERVICOS": 4}
    return mapping.get(norm, 0)

def parse_float_safe(v):
    try:
        v_str = str(v).replace('%', '').replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.').strip()
        if not v_str: return 0.0
        return float(v_str)
    except:
        return 0.0

def carregar_df_admin_seguro(aba):
    try:
        dados = aba.get_all_values()
        cabecalho = ["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)]
        dados_validos = [r for r in dados if any(str(cell).strip() for cell in r)]
        if len(dados_validos) > 1:
            linhas_completas = [r + [""] * (27 - len(r)) for r in dados_validos[1:]]
            df = pd.DataFrame([r[:27] for r in linhas_completas], columns=cabecalho)
            df['Admin_Norm'] = df['Administradora'].apply(normalizar_string)
            df['Prod_Norm'] = df['Produto'].apply(normalizar_produto)
            return df
    except Exception as e:
        pass
    return pd.DataFrame(columns=["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)])

# Callbacks
def mascara_tel_nv(): st.session_state['tel_nv'] = formatar_telefone(st.session_state.get('tel_nv', ''))
def mascara_aniv_nv(): st.session_state['aniv_nv'] = formatar_data(st.session_state.get('aniv_nv', ''))
def mascara_renda_nv(): st.session_state['renda_nv'] = formatar_moeda(st.session_state.get('renda_nv', ''))

# === MOTOR DE CÁLCULO DE COMISSÃO ===
def calcular_comissao_vendedor(df_vendas_global, vendedor_nome, data_venda_dt, cfg):
    if pd.isna(data_venda_dt): 
        return cfg['T1_Pct'], int(cfg['T1_Parc'])
        
    mes = data_venda_dt.month
    ano = data_venda_dt.year
    df_mes = df_vendas_global[(df_vendas_global['VENDEDOR'] == vendedor_nome) &
                              (df_vendas_global['Data_Real'].dt.month == mes) &
                              (df_vendas_global['Data_Real'].dt.year == ano)]
    vol_total = df_mes['Valor_Numerico'].sum()

    if vol_total <= cfg['T1_Max']: return cfg['T1_Pct'], int(cfg['T1_Parc'])
    elif vol_total <= cfg['T2_Max']: return cfg['T2_Pct'], int(cfg['T2_Parc'])
    else: return cfg['T3_Pct'], int(cfg['T3_Parc'])

# === 2. LÓGICA DO MENU LATERAL ===
is_logado = st.session_state['usuario_logado'] is not None

if is_logado:
    st.sidebar.markdown(f"<div style='color: #0f172a; font-weight: bold; font-size: 14px; margin-bottom: 10px;'>👤 {st.session_state['nome_vendedor'].upper()}</div>", unsafe_allow_html=True)

st.sidebar.image("https://www.consorbens.com/assets/logo-consorbens-DZ8uSiSJ.png", use_column_width=True)

if not is_logado:
    st.sidebar.write("")
    opcoes_menu = ["🔐 Login (Área Restrita)", "🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
    try: idx_menu = opcoes_menu.index(st.session_state['menu_lateral'])
    except ValueError: idx_menu = 0
    selecao = st.sidebar.radio(" ", opcoes_menu, index=idx_menu, label_visibility="collapsed")
    if selecao != st.session_state['menu_lateral']:
        st.session_state['menu_lateral'] = selecao
        st.rerun()
else:
    st.sidebar.divider() 
    ferramentas_logadas = ["🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
    
    if st.session_state['perfil_logado'] == "Master":
        opcoes_principais = ["Dashboard", "Nova Venda", "Relatórios", "Regras de Comissão", "Baixar Parcela"]
    else:
        opcoes_principais = ["Dashboard", "Nova Venda", "Relatórios"]

    idx_principal = opcoes_principais.index(st.session_state['menu_lateral']) if st.session_state['menu_lateral'] in opcoes_principais else None
    selecao_principal = st.sidebar.radio(" ", opcoes_principais, index=idx_principal, label_visibility="collapsed")
    
    if selecao_principal != st.session_state.get('last_radio_selection'):
        if selecao_principal is not None:
            st.session_state['menu_lateral'] = selecao_principal
            st.session_state['cliente_visualizado'] = None
            st.session_state['last_radio_selection'] = selecao_principal
            st.rerun()
            
    st.session_state['last_radio_selection'] = selecao_principal
    st.sidebar.write("")
    is_sim_active = st.session_state['menu_lateral'] in ferramentas_logadas
    
    with st.sidebar.expander("🛠️ Simuladores", expanded=is_sim_active):
        for sim in ferramentas_logadas:
            btn_type = "primary" if st.session_state['menu_lateral'] == sim else "secondary"
            if st.button(sim, use_container_width=True, type=btn_type):
                st.session_state['menu_lateral'] = sim
                st.session_state['cliente_visualizado'] = None
                st.session_state['last_radio_selection'] = None
                st.rerun()

menu_selecionado = st.session_state['menu_lateral']

if is_logado:
    st.sidebar.write("")
    if menu_selecionado == "Dashboard" and st.session_state['cliente_visualizado'] is not None:
        if st.sidebar.button("⬅️ Voltar ao Dashboard", type="primary", use_container_width=True):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
            
    st.sidebar.write("")
    if st.sidebar.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

st.sidebar.markdown("""<div style="text-align: center; margin-top: 30px; padding-top: 15px; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 0.85rem;">Portal Consorbens &copy; 2026</div>""", unsafe_allow_html=True)

# === 3. ESTILIZAÇÃO CSS ===
css = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
    [data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 2px solid #e2e8f0 !important; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div { color: #0f172a !important; }
    [data-testid="stSidebar"] hr { border-bottom-color: #e2e8f0 !important; margin-top: 0.5rem !important; margin-bottom: 0.5rem !important; }
    [data-testid="stSidebar"] button { border: 1px solid #cbd5e1 !important; background-color: #f8fafc !important; }
    [data-testid="collapsedControl"] { background-color: #ff6600 !important; border-radius: 8px !important; box-shadow: 0px 4px 10px rgba(255, 102, 0, 0.6) !important; padding: 8px !important; margin-top: 15px !important; margin-left: 15px !important; opacity: 1 !important; z-index: 999999 !important; }
    [data-testid="collapsedControl"] svg { fill: #ffffff !important; color: #ffffff !important; stroke: #ffffff !important; width: 20px !important; height: 20px !important; }
    [data-testid="collapsedControl"]:hover { background-color: #cc5200 !important; transform: scale(1.1) !important; }
    [data-testid="stSidebarCollapseButton"] { background-color: #ff6600 !important; border-radius: 6px !important; }
    [data-testid="stSidebarCollapseButton"] svg { fill: #ffffff !important; color: #ffffff !important; }
    [data-testid="stSidebarCollapseButton"]:hover { background-color: #cc5200 !important; }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    button[data-baseweb="tab"] { font-size: 16px !important; font-weight: bold !important; }
    button[kind="primary"] { background-color: #239b56 !important; border-color: #239b56 !important; color: #ffffff !important; font-weight: bold !important; }
    button[kind="primary"]:hover { background-color: #1b7a43 !important; border-color: #1b7a43 !important; color: #ffffff !important; transform: scale(1.02); transition: all 0.2s; }
</style>
"""
simuladores_dict = {
    "🏍️ Simulador Yamaha": "yamaha.html",
    "🏦 Simulador Itaú": "itau.html",
    "🎯 Oportunidades Itaú": "guia.html",
    "⚖️ Financiamento x Consórcio": "comparador.html"
}
if menu_selecionado in simuladores_dict: css += """ <style>.stApp { background-color: #0f172a !important; }</style> """
else: css += """ <style>.stApp { background-color: #ffffff !important; }</style> """

st.markdown(css, unsafe_allow_html=True)

# === 4. CONEXÃO PLANILHA E CONFIGURAÇÕES OTIMIZADA ===
@st.cache_resource
def conectar_planilha():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    return gc.open("Sistema CRM")

try:
    planilha = conectar_planilha()
    todas_abas = [aba.title for aba in planilha.worksheets()]
    
    if "Vendas" not in todas_abas: planilha.add_worksheet("Vendas", 1000, 10)
    aba_vendas = planilha.worksheet("Vendas")

    if "Clientes" not in todas_abas:
        aba_clientes = planilha.add_worksheet("Clientes", 1000, 10)
        aba_clientes.append_row(["Nome", "Telefone", "Email", "Endereco", "Aniversario", "Profissao", "Renda", "Data_Cadastro"])
    else: aba_clientes = planilha.worksheet("Clientes")

    if "Cad_Administradoras" not in todas_abas:
        aba_admin_cad = planilha.add_worksheet("Cad_Administradoras", 100, 3)
        aba_admin_cad.append_row(["Administradora", "CNPJ", "Endereço"])
    else: aba_admin_cad = planilha.worksheet("Cad_Administradoras")

    lista_admin_bd_raw = aba_admin_cad.col_values(1)[1:]
    if not lista_admin_bd_raw: lista_admin_bd = ["Nenhuma administradora cadastrada"]
    else: lista_admin_bd = lista_admin_bd_raw

    if "Administradoras" not in todas_abas:
        aba_admin = planilha.add_worksheet("Administradoras", 100, 27)
        cabecalho_admin = ["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)]
        aba_admin.append_row(cabecalho_admin)
    else: aba_admin = planilha.worksheet("Administradoras")

    cols_cfg = ["Breno_Breno", "Breno_Uriel", "Uriel_Uriel", "Uriel_Breno", "Cons_Breno", "Cons_Uriel", "T1_Max", "T1_Pct", "T1_Parc", "T2_Max", "T2_Pct", "T2_Parc", "T3_Pct", "T3_Parc", "Imposto"]
    
    if "Config_Interna" not in todas_abas:
        aba_cfg = planilha.add_worksheet("Config_Interna", 10, 20)
        vals_cfg = [70, 30, 70, 30, 50, 50, 500000, 1.0, 4, 1500000, 1.5, 5, 2.0, 5, 7.16]
        aba_cfg.append_row(cols_cfg)
        aba_cfg.append_row(vals_cfg)
        cfg_data = [cols_cfg, vals_cfg]
    else:
        aba_cfg = planilha.worksheet("Config_Interna")
        cfg_data = aba_cfg.get_all_values()
        if len(cfg_data) < 2:
            aba_cfg.clear()
            vals_cfg = [70, 30, 70, 30, 50, 50, 500000, 1.0, 4, 1500000, 1.5, 5, 2.0, 5, 7.16]
            aba_cfg.append_row(cols_cfg)
            aba_cfg.append_row(vals_cfg)
            cfg_data = [cols_cfg, vals_cfg]

    # Prevenção: Caso a planilha antiga não tenha a coluna Imposto ainda
    cfg_dic = {}
    for i in range(min(len(cfg_data[0]), len(cfg_data[1]))):
        cfg_dic[cfg_data[0][i]] = parse_float_safe(cfg_data[1][i])
    if 'Imposto' not in cfg_dic: cfg_dic['Imposto'] = 7.16
    cfg = cfg_dic

    # Carrega Base Global só quando precisa
    if is_logado and menu_selecionado in ["Dashboard", "Relatórios"]:
        dados_brutos = aba_vendas.get_all_values()
        if len(dados_brutos) > 1:
            df_vendas_global = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
            df_vendas_global.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
            df_vendas_global['Data_Real'] = pd.to_datetime(df_vendas_global['DATA'], format="%d/%m/%Y", errors='coerce')
            df_vendas_global['Valor_Numerico'] = df_vendas_global['VALOR'].apply(parse_float_safe)
        else: df_vendas_global = pd.DataFrame()
    else: df_vendas_global = pd.DataFrame()

except gspread.exceptions.APIError as e:
    st.error("⚠️ O Google Sheets limitou o acesso temporariamente por excesso de requisições. Por favor, aguarde cerca de 1 minuto e recarregue a página.")
    st.stop()


# === RENDERIZAÇÃO DAS TELAS ===

# 1. ROTEADOR DE SIMULADORES (RODA SEMPRE)
if menu_selecionado in simuladores_dict:
    carregar_ferramenta(simuladores_dict[menu_selecionado])
    st.stop() 

# 2. TELA DE LOGIN
if not is_logado:
    if menu_selecionado == "🔐 Login (Área Restrita)":
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        _, col_meio, _ = st.columns([1, 1.2, 1])
        with col_meio:
            with st.form("form_login"):
                usuario_input = st.text_input("Usuário (Login)").lower()
                senha_input = st.text_input("Senha", type="password")
                st.write("") 
                _, c_btn2, _ = st.columns([1, 1.5, 1])
                with c_btn2:
                    if st.form_submit_button("ENTRAR", type="primary", use_container_width=True):
                        if usuario_input in USUARIOS and USUARIOS[usuario_input]["senha"] == senha_input:
                            st.session_state['usuario_logado'] = usuario_input
                            st.session_state['perfil_logado'] = USUARIOS[usuario_input]["perfil"]
                            st.session_state['nome_vendedor'] = USUARIOS[usuario_input]["nome"]
                            st.session_state['menu_lateral'] = "Dashboard" 
                            st.rerun() 
                        else: st.error("❌ Usuário ou senha incorretos.")
    st.stop() 

# 3. PÁGINAS DA ÁREA RESTRITA
if menu_selecionado == "Dashboard":
    
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        st.markdown(f"### {cliente_nome}")
        
        if st.button("⬅️ Voltar ao Dashboard", type="primary"):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
            
        dados_cli_brutos = aba_clientes.get_all_values()
        if len(dados_cli_brutos) > 1: df_cli = pd.DataFrame(dados_cli_brutos[1:], columns=dados_cli_brutos[0])
        else: df_cli = pd.DataFrame(columns=["Nome", "Telefone", "Email", "Endereco", "Aniversario", "Profissao", "Renda", "Data_Cadastro"])
        
        info_cliente = {}
        if not df_cli.empty and 'Nome' in df_cli.columns:
            busca_cli = df_cli[df_cli['Nome'] == cliente_nome]
            if not busca_cli.empty: info_cliente = busca_cli.iloc[0].to_dict()

        is_master = st.session_state['perfil_logado'] == "Master"
        if not is_master: st.info("🔒 Como Vendedor, você só pode visualizar estes dados. Para alterar, contate o Administrador.")
            
        key_nome = f"nome_ed_{cliente_nome}"
        key_tel = f"tel_ed_{cliente_nome}"
        key_email = f"email_ed_{cliente_nome}"
        key_end = f"end_ed_{cliente_nome}"
        key_aniv = f"aniv_ed_{cliente_nome}"
        key_prof = f"prof_ed_{cliente_nome}"
        key_renda = f"renda_ed_{cliente_nome}"
        
        if key_nome not in st.session_state: st.session_state[key_nome] = info_cliente.get("Nome", cliente_nome)
        if key_tel not in st.session_state: st.session_state[key_tel] = info_cliente.get("Telefone", "")
        if key_email not in st.session_state: st.session_state[key_email] = info_cliente.get("Email", "")
        if key_end not in st.session_state: st.session_state[key_end] = info_cliente.get("Endereco", "")
        if key_aniv not in st.session_state: st.session_state[key_aniv] = info_cliente.get("Aniversario", "")
        if key_prof not in st.session_state: st.session_state[key_prof] = info_cliente.get("Profissao", "")
        if key_renda not in st.session_state: st.session_state[key_renda] = info_cliente.get("Renda", "")
            
        def m_tel_ed(): st.session_state[key_tel] = formatar_telefone(st.session_state.get(key_tel, ''))
        def m_aniv_ed(): st.session_state[key_aniv] = formatar_data(st.session_state.get(key_aniv, ''))
        def m_renda_ed(): st.session_state[key_renda] = formatar_moeda(st.session_state.get(key_renda, ''))

        nome_edit = st.text_input("Nome Completo", key=key_nome, disabled=not is_master)
        
        c1, c2 = st.columns(2)
        with c1:
            endereco = st.text_input("Endereço Completo", key=key_end, disabled=not is_master)
            telefone_edit = st.text_input("Telefone", key=key_tel, on_change=m_tel_ed, disabled=not is_master, placeholder="(31) 99999-9999", max_chars=15)
            profissao_edit = st.text_input("Profissão", key=key_prof, disabled=not is_master)
        with c2:
            email = st.text_input("E-mail", key=key_email, disabled=not is_master)
            aniversario_edit = st.text_input("Data de Aniversário (DD/MM/AAAA)", key=key_aniv, on_change=m_aniv_ed, disabled=not is_master, placeholder="DD/MM/AAAA", max_chars=10)
            renda_edit = st.text_input("Renda Mensal (R$)", key=key_renda, on_change=m_renda_ed, disabled=not is_master, placeholder="R$ 0,00")
        
        if is_master:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Salvar Alterações Cadastrais", type="primary", use_container_width=True):
                    novo_nome_val = st.session_state[key_nome]
                    nomes_col = aba_clientes.col_values(1)
                    if cliente_nome in nomes_col:
                        row_idx = nomes_col.index(cliente_nome) + 1
                        aba_clientes.update_cell(row_idx, 1, novo_nome_val)
                        aba_clientes.update_cell(row_idx, 2, st.session_state[key_tel])
                        aba_clientes.update_cell(row_idx, 3, st.session_state[key_email])
                        aba_clientes.update_cell(row_idx, 4, st.session_state[key_end])
                        aba_clientes.update_cell(row_idx, 5, st.session_state[key_aniv])
                        aba_clientes.update_cell(row_idx, 6, st.session_state[key_prof])
                        aba_clientes.update_cell(row_idx, 7, st.session_state[key_renda])
                    else:
                        aba_clientes.append_row([novo_nome_val, st.session_state[key_tel], st.session_state[key_email], st.session_state[key_end], st.session_state[key_aniv], st.session_state[key_prof], st.session_state[key_renda], datetime.today().strftime("%d/%m/%Y")])
                    
                    if novo_nome_val != cliente_nome:
                        vendas_nomes = aba_vendas.col_values(2)
                        for i in range(len(vendas_nomes), 0, -1):
                            if vendas_nomes[i-1] == cliente_nome:
                                aba_vendas.update_cell(i, 2, novo_nome_val)
                        st.session_state['cliente_visualizado'] = novo_nome_val

                    st.success("Dados atualizados com sucesso!")
                    st.rerun()

            with col_b2:
                if st.button("🚨 Excluir Cliente (Apagar Todas as Cotas)", use_container_width=True):
                    nomes_col = aba_clientes.col_values(1)
                    if cliente_nome in nomes_col:
                        row_idx = nomes_col.index(cliente_nome) + 1
                        aba_clientes.delete_rows(row_idx)
                    
                    vendas_nomes = aba_vendas.col_values(2)
                    for i in range(len(vendas_nomes), 0, -1):
                        if vendas_nomes[i-1] == cliente_nome: aba_vendas.delete_rows(i)

                    st.session_state['cliente_visualizado'] = None
                    st.session_state['key_tabela'] += 1
                    st.rerun()

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        if not df_vendas_global.empty:
            cotas_cliente = df_vendas_global[df_vendas_global['Nome do cliente'] == cliente_nome].copy()
            if not cotas_cliente.empty:
                info_a, info_b = st.columns(2)
                info_a.metric("Total de Cotas Adquiridas", len(cotas_cliente))
                info_b.metric("Volume Total Investido", formatar_brl_puro(cotas_cliente['Valor_Numerico'].sum()))
                cotas_cliente['Valor Formatado'] = cotas_cliente['Valor_Numerico'].apply(formatar_brl_puro)
                
                ficha_display = cotas_cliente[['DATA', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'Valor Formatado', 'STATUS', 'VENDEDOR']].rename(columns={'DATA': 'Data da Venda', 'ADMINISTRADORA': 'Administradora', 'PRODUTO': 'Produto', 'GRUPO': 'Grupo', 'COTA': 'Cota', 'Valor Formatado': 'Valor (R$)', 'STATUS': 'Status', 'VENDEDOR': 'Vendedor'})
                estilo_ficha = ficha_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_ficha, use_container_width=True, hide_index=True)
                
                st.write("")
                with st.expander("⚙️ Atualizar Status e Gerenciar Cota", expanded=False):
                    st.info("Atualize o status da cota. Apenas usuários Master podem alterar o vendedor ou apagar a cota do sistema.")
                    opcoes_cotas = cotas_cliente.apply(lambda r: f"Linha {r.name + 2} | Grupo: {r['GRUPO']} / Cota: {r['COTA']} - Valor: {r['Valor Formatado']}", axis=1).tolist()
                    
                    c_sel, _ = st.columns([3, 1])
                    with c_sel: cota_selecionada = st.selectbox("Selecione a cota que deseja gerenciar:", [""] + opcoes_cotas)
                        
                    if cota_selecionada:
                        linha_planilha = int(cota_selecionada.split(" | ")[0].replace("Linha ", ""))
                        vendedor_atual = cotas_cliente.loc[linha_planilha - 2, 'VENDEDOR']
                        status_atual = cotas_cliente.loc[linha_planilha - 2, 'STATUS']
                        if status_atual == "Vendido" or not status_atual: status_atual = "Em Andamento"
                        
                        c_ed1, c_ed2 = st.columns(2)
                        with c_ed1:
                            status_list = ["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"]
                            idx_status = status_list.index(status_atual) if status_atual in status_list else 0
                            novo_status = st.selectbox("Status da Cota", status_list, index=idx_status)
                        with c_ed2:
                            vendedores_list = ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]
                            if is_master:
                                idx_vend = vendedores_list.index(vendedor_atual) if vendedor_atual in vendedores_list else 0
                                novo_vendedor = st.selectbox("Vendedor Realizador", vendedores_list, index=idx_vend)
                            else:
                                st.text_input("Vendedor Realizador", value=vendedor_atual, disabled=True)
                                novo_vendedor = vendedor_atual
                                
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.button("Salvar Alterações na Cota", type="primary", use_container_width=True):
                                aba_vendas.update_cell(linha_planilha, 5, novo_vendedor)
                                aba_vendas.update_cell(linha_planilha, 9, novo_status)
                                st.success("Cota atualizada com sucesso!")
                                st.rerun()
                        with col_b2:
                            if is_master:
                                if st.button("🚨 Apagar Esta Cota", use_container_width=True):
                                    aba_vendas.delete_rows(linha_planilha)
                                    st.success("Cota apagada com sucesso!")
                                    st.rerun()
                            else: st.button("🚨 Apagar Esta Cota", disabled=True, use_container_width=True, help="Apenas Masters podem excluir cotas.")

                st.write("")
                st.subheader("📈 Previsão de Comissionamento")
                df_admin = carregar_df_admin_seguro(aba_admin)
                hoje = pd.Timestamp.today().normalize()
                    
                previsoes = []
                for idx, r in cotas_cliente.iterrows():
                    admin_venda = normalizar_string(r['ADMINISTRADORA'])
                    prod_venda = normalizar_produto(r['PRODUTO'])
                    vendedor_nome = r['VENDEDOR']
                    
                    status_cota = r.get('STATUS', 'Em Andamento')
                    if status_cota in ["Vendido", ""]: status_cota = "Em Andamento"
                    
                    regra_encontrada = None
                    if not df_admin.empty:
                        for _, reg_row in df_admin.iterrows():
                            if reg_row['Admin_Norm'] == admin_venda and reg_row['Prod_Norm'] == prod_venda:
                                regra_encontrada = reg_row
                                break
                            
                    if regra_encontrada is not None:
                        data_venda = r['Data_Real']
                        if pd.notna(data_venda):
                            tier_pct, tier_parc = calcular_comissao_vendedor(df_vendas_global, vendedor_nome, data_venda, cfg)
                            parcelas_cota = []
                            for i in range(1, 26):
                                p_str = str(regra_encontrada.get(f"P{i}", "0")).replace('%', '').strip()
                                try: p_val_admin = float(p_str) / 100.0
                                except: p_val_admin = 0.0
                                
                                admin_recebe = r['Valor_Numerico'] * p_val_admin
                                imposto_val = admin_recebe * (cfg.get('Imposto', 7.16) / 100.0)
                                corretora_liq = admin_recebe - imposto_val

                                vend_recebe = 0.0
                                breno_recebe = 0.0
                                uriel_recebe = 0.0
                                
                                if vendedor_nome == "BRENO LIMA":
                                    breno_recebe = corretora_liq * (cfg['Breno_Breno']/100)
                                    uriel_recebe = corretora_liq * (cfg['Breno_Uriel']/100)
                                elif vendedor_nome == "URIEL GOMES":
                                    uriel_recebe = corretora_liq * (cfg['Uriel_Uriel']/100)
                                    breno_recebe = corretora_liq * (cfg['Uriel_Breno']/100)
                                elif vendedor_nome == "Consorbens":
                                    breno_recebe = corretora_liq * (cfg['Cons_Breno']/100)
                                    uriel_recebe = corretora_liq * (cfg['Cons_Uriel']/100)
                                else:
                                    if i <= tier_parc: vend_recebe = (r['Valor_Numerico'] * (tier_pct/100)) / tier_parc
                                    sobra = corretora_liq - vend_recebe
                                    breno_recebe = sobra * 0.50
                                    uriel_recebe = sobra * 0.50

                                if admin_recebe > 0 or vend_recebe > 0:
                                    data_pagamento = data_venda + pd.Timedelta(days=7) + pd.DateOffset(months=i-1)
                                    parcelas_cota.append({
                                        'i': i, 'data_pagamento': data_pagamento, 'admin_recebe': admin_recebe,
                                        'vend_recebe': vend_recebe, 'breno_recebe': breno_recebe, 'uriel_recebe': uriel_recebe
                                    })
                                    
                            if status_cota == 'Cancelada':
                                parcelas_cota = [p for p in parcelas_cota if p['data_pagamento'] <= hoje]
                            elif status_cota == 'Contemplada':
                                past_parcels = [p for p in parcelas_cota if p['data_pagamento'] <= hoje]
                                future_parcels = [p for p in parcelas_cota if p['data_pagamento'] > hoje]
                                if future_parcels:
                                    past_parcels.append({
                                        'i': 'Antecipação', 'data_pagamento': hoje,
                                        'admin_recebe': sum(p['admin_recebe'] for p in future_parcels),
                                        'vend_recebe': sum(p['vend_recebe'] for p in future_parcels),
                                        'breno_recebe': sum(p['breno_recebe'] for p in future_parcels),
                                        'uriel_recebe': sum(p['uriel_recebe'] for p in future_parcels)
                                    })
                                parcelas_cota = past_parcels

                            for p in parcelas_cota:
                                data_str = p['data_pagamento'].strftime("%d/%m/%Y")
                                if status_cota == 'Em Atraso': data_str = "⚠️ Travada (Atraso)"
                                nome_parcela = f"{p['i']}ª Parcela" if isinstance(p['i'], int) else "Antecipação (Contemplada)"
                                row_dict = {
                                    "Cota / Admin": f"{r['GRUPO']}/{r['COTA']} ({r['ADMINISTRADORA']})",
                                    "Mês/Parcela": nome_parcela,
                                    "Data Prevista": data_str,
                                }
                                if is_master:
                                    row_dict["Corretora Recebe"] = formatar_brl_puro(p['admin_recebe'])
                                    row_dict[f"Vendedor Recebe"] = formatar_brl_puro(p['vend_recebe'])
                                    row_dict["Breno Recebe"] = formatar_brl_puro(p['breno_recebe'])
                                    row_dict["Uriel Recebe"] = formatar_brl_puro(p['uriel_recebe'])
                                else: row_dict["Sua Comissão"] = formatar_brl_puro(p['vend_recebe'])
                                previsoes.append(row_dict)
                    else:
                        st.warning(f"⚠️ Regra não encontrada para a cota **{r['GRUPO']}/{r['COTA']}**.")
                        
                if previsoes:
                    df_prev = pd.DataFrame(previsoes)
                    if not is_master: df_prev = df_prev[df_prev['Sua Comissão'] != "R$ 0,00"]
                    if not df_prev.empty:
                        st.dataframe(df_prev.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
                else:
                    if len(df_admin) == 0: st.info("Aguardando configurações de regras para gerar a previsão.")
            else: st.warning("Nenhuma cota encontrada para este cliente.")

    else:
        if not df_vendas_global.empty:
            df_view = df_vendas_global.copy()
            if st.session_state['perfil_logado'] == "Vendedor":
                df_view = df_view[df_view['VENDEDOR'] == st.session_state['nome_vendedor']]

            col_t1, col_t2 = st.columns([4, 1])
            with col_t2:
                st.write("")
                if st.button("Nova Venda", use_container_width=True, type="primary"):
                    st.session_state['menu_lateral'] = "Nova Venda"
                    st.rerun()
            
            c_filtro1, c_filtro2 = st.columns([1, 2])
            with c_filtro1:
                filtro_cli = st.selectbox("⏳ Filtro da Tabela:", ["Últimos 5 Cadastros", "Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
                if filtro_cli == "Período Personalizado":
                    cd1, cd2 = st.columns(2)
                    with cd1: p_ini = st.date_input("Início", format="DD/MM/YYYY")
                    with cd2: p_fim = st.date_input("Fim", format="DD/MM/YYYY")
            with c_filtro2: busca = st.text_input("🔍 Buscar Cliente por Nome:")

            hoje = datetime.today()
            df_view = df_view.sort_values(by="Data_Real", ascending=False)
            
            if filtro_cli == "Últimos 5 Cadastros" and busca.strip() == "":
                df_view = df_view.head(5)
            elif filtro_cli != "Todos os Clientes" and filtro_cli != "Últimos 5 Cadastros":
                mask = df_view['Data_Real'].notna()
                if filtro_cli == "Mês Atual":
                    df_view = df_view[mask & (df_view['Data_Real'].dt.month == hoje.month) & (df_view['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Mês Anterior":
                    mes_ant, ano_ant = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                    df_view = df_view[mask & (df_view['Data_Real'].dt.month == mes_ant) & (df_view['Data_Real'].dt.year == ano_ant)]
                elif filtro_cli == "Ano Atual":
                    df_view = df_view[mask & (df_view['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Período Personalizado":
                    df_view = df_view[mask & (df_view['Data_Real'].dt.date >= p_ini) & (df_view['Data_Real'].dt.date <= p_fim)]

            if busca.strip() != "":
                df_view = df_view[df_view['Nome do cliente'].str.contains(busca.strip(), case=False, na=False)]

            if not df_view.empty:
                st.write("Clique em uma linha para ver os detalhes do cliente:")
                df_tab = df_view.copy()
                df_tab['Grupo e Cota'] = df_tab.apply(lambda x: f"{x['GRUPO']}/{x['COTA']}", axis=1)
                df_tab['Valor Formatado'] = df_tab['Valor_Numerico'].apply(formatar_brl_puro)
                
                df_tab = df_tab[['Nome do cliente', 'PRODUTO', 'ADMINISTRADORA', 'Grupo e Cota', 'VENDEDOR', 'Valor Formatado', 'DATA']]
                df_tab.columns = ['Cliente', 'Produto', 'Administradora', 'Grupo/Cota', 'Vendedor', 'Valor', 'Data da Venda']
                
                tabela = st.dataframe(df_tab, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                
                if hasattr(tabela, 'selection') and tabela.selection.rows:
                    st.session_state['cliente_visualizado'] = df_tab.iloc[tabela.selection.rows[0]]['Cliente']
                    st.rerun()

                st.divider()
                m1, m2, m3 = st.columns(3)
                vol_total = df_view['Valor_Numerico'].sum()
                m1.metric("Volume Total (Filtro)", formatar_brl_puro(vol_total))
                m2.metric("Qtd. Cotas (Filtro)", len(df_view))
                m3.metric("Ticket Médio", formatar_brl_puro(vol_total/len(df_view) if len(df_view)>0 else 0))

                st.write("")
                st.subheader("📊 Gráficos Globais (Filtro Independente)")
                g_filtro1, g_filtro2 = st.columns(2)
                with g_filtro1:
                    ft_graf = st.selectbox("⏳ Período para o Gráfico:", ["Mês Atual", "Mês Anterior", "Anual", "Todas as Vendas", "Período Personalizado"])
                    if ft_graf == "Período Personalizado":
                        cg1, cg2 = st.columns(2)
                        with cg1: gi = st.date_input("Data Inicial", format="DD/MM/YYYY", key="g_inicio")
                        with cg2: gf = st.date_input("Data Final", format="DD/MM/YYYY", key="g_fim")
                with g_filtro2: fp_graf = st.selectbox("📦 Produto:", ["Todos", "Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
                    
                df_g = df_vendas_global.copy()
                if st.session_state['perfil_logado'] == "Vendedor":
                    df_g = df_g[df_g['VENDEDOR'] == st.session_state['nome_vendedor']]
                    
                if ft_graf != "Todas as Vendas" and not df_g.empty:
                    mask = df_g['Data_Real'].notna()
                    if ft_graf == "Mês Atual": 
                        df_g = df_g[mask & (df_g['Data_Real'].dt.month == hoje.month) & (df_g['Data_Real'].dt.year == hoje.year)]
                    elif ft_graf == "Mês Anterior":
                        ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                        df_g = df_g[mask & (df_g['Data_Real'].dt.month == ma) & (df_g['Data_Real'].dt.year == aa)]
                    elif ft_graf == "Anual": 
                        df_g = df_g[mask & (df_g['Data_Real'].dt.year == hoje.year)]
                    elif ft_graf == "Período Personalizado": 
                        df_g = df_g[mask & (df_g['Data_Real'].dt.date >= gi) & (df_g['Data_Real'].dt.date <= gf)]
                    
                if fp_graf != "Todos" and not df_g.empty: 
                    df_g['Prod_Norm'] = df_g['PRODUTO'].apply(normalizar_produto)
                    df_g = df_g[df_g['Prod_Norm'] == normalizar_produto(fp_graf)]
                    
                if not df_g.empty:
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        st.markdown("#### Vendas por Produto")
                        df_p = df_g['PRODUTO'].value_counts().reset_index()
                        df_p.columns = ['Produto', 'Quantidade']
                        chart_p = alt.Chart(df_p).mark_arc(innerRadius=50).encode(theta='Quantidade', color='Produto', tooltip=['Produto', 'Quantidade'])
                        st.altair_chart(chart_p, use_container_width=True)
                    with col_g2:
                        st.markdown("#### Vendas por Administradora")
                        df_a = df_g['ADMINISTRADORA'].value_counts().reset_index()
                        df_a.columns = ['Administradora', 'Quantidade']
                        chart_a = alt.Chart(df_a).mark_arc(innerRadius=50).encode(theta='Quantidade', color='Administradora', tooltip=['Administradora', 'Quantidade'])
                        st.altair_chart(chart_a, use_container_width=True)
                else:
                    st.warning("📊 Não há vendas suficientes para gerar o gráfico com os filtros atuais.")
            else: st.info("Nenhuma venda encontrada para os filtros selecionados.")
        else: st.info("O sistema ainda não possui vendas cadastradas na planilha.")

elif menu_selecionado == "Nova Venda":
    st.markdown("### 📝 Cadastrar Nova Venda")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        if 'venda_cliente' not in st.session_state: st.session_state['venda_cliente'] = ""
        cliente = st.text_input("Nome do Cliente *", key="venda_cliente")
        if 'tel_nv' not in st.session_state: st.session_state['tel_nv'] = ""
        telefone = st.text_input("Telefone", key="tel_nv", on_change=mascara_tel_nv, placeholder="(31) 99999-9999", max_chars=15)
        if 'prof_nv' not in st.session_state: st.session_state['prof_nv'] = ""
        profissao = st.text_input("Profissão", key="prof_nv")
    with col_c2:
        if 'venda_email' not in st.session_state: st.session_state['venda_email'] = ""
        email = st.text_input("E-mail", key="venda_email")
        if 'aniv_nv' not in st.session_state: st.session_state['aniv_nv'] = ""
        aniversario = st.text_input("Data de Aniversário (DD/MM/AAAA)", key="aniv_nv", on_change=mascara_aniv_nv, placeholder="DD/MM/AAAA", max_chars=10)
        if 'renda_nv' not in st.session_state: st.session_state['renda_nv'] = ""
        renda = st.text_input("Renda Mensal (R$)", key="renda_nv", on_change=mascara_renda_nv, placeholder="R$ 0,00")
        
    st.markdown("##### Busca Rápida de Endereço")
    col_cep1, col_cep2 = st.columns([1, 3])
    with col_cep1:
        if 'venda_cep' not in st.session_state: st.session_state['venda_cep'] = ""
        cep = st.text_input("CEP (Digite e clique fora)", key="venda_cep", max_chars=9)
        
    if cep != st.session_state.get('last_cep', ''):
        cep_limpo = ''.join(filter(str.isdigit, cep))
        if len(cep_limpo) == 8:
            try:
                res = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
                if res.status_code == 200:
                    dados_cep = res.json()
                    if "erro" not in dados_cep:
                        st.session_state['venda_rua'] = dados_cep.get("logradouro", "")
                        st.session_state['venda_bairro'] = dados_cep.get("bairro", "")
                        st.session_state['venda_cidade'] = dados_cep.get("localidade", "")
                        st.session_state['venda_uf'] = dados_cep.get("uf", "")
                        st.success("✅ CEP Encontrado!")
            except: st.warning("⚠️ Serviço de CEP indisponível.")
        st.session_state['last_cep'] = cep

    ce1, ce2, ce3 = st.columns([2, 1, 1])
    with ce1: rua = st.text_input("Rua/Logradouro", key="venda_rua" if 'venda_rua' in st.session_state else None)
    with ce2: numero = st.text_input("Número", key="venda_numero" if 'venda_numero' in st.session_state else None)
    with ce3: complemento = st.text_input("Complemento", key="venda_complemento" if 'venda_complemento' in st.session_state else None)

    ce4, ce5, ce6 = st.columns([2, 2, 1])
    with ce4: bairro = st.text_input("Bairro", key="venda_bairro" if 'venda_bairro' in st.session_state else None)
    with ce5: cidade = st.text_input("Cidade", key="venda_cidade" if 'venda_cidade' in st.session_state else None)
    with ce6: uf = st.text_input("UF", max_chars=2, key="venda_uf" if 'venda_uf' in st.session_state else None)

    st.subheader("2. Dados da Venda")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        data = st.date_input("Data da Venda", format="DD/MM/YYYY")
        if st.session_state['perfil_logado'] == "Master": 
            vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"])
        else:
            st.write(f"**Vendedor:** {st.session_state['nome_vendedor']}")
            vendedor = st.session_state['nome_vendedor']
    with col_v2:
        if not lista_admin_bd or lista_admin_bd[0] == "Nenhuma administradora cadastrada":
            opcoes_admin = ["YAMAHA", "ITAÚ", "ROMA", "EMBRACON"]
        else: opcoes_admin = lista_admin_bd
        admin = st.selectbox("Administradora *", opcoes_admin)
        produto = st.selectbox("Produto *", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
        
    st.markdown("##### Cotas Adquiridas")
    if 'qtd_cotas' not in st.session_state: st.session_state['qtd_cotas'] = 1
    cotas_data = []
    for i in range(st.session_state['qtd_cotas']):
        st.markdown(f"**Cota {i+1}**")
        cq1, cq2, cq3 = st.columns(3)
        if f"g_{i}" not in st.session_state: st.session_state[f"g_{i}"] = ""
        if f"c_{i}" not in st.session_state: st.session_state[f"c_{i}"] = ""
        if f"v_in_{i}" not in st.session_state: st.session_state[f"v_in_{i}"] = ""
        with cq1: grupo = st.text_input(f"Grupo *", key=f"g_{i}")
        with cq2: cota = st.text_input(f"Cota *", key=f"c_{i}")
        with cq3:
            def m_moeda(idx=i): 
                val = st.session_state.get(f"v_in_{idx}", "")
                st.session_state[f"v_in_{idx}"] = formatar_moeda(val)
            valor_str = st.text_input(f"Valor (R$) *", key=f"v_in_{i}", on_change=m_moeda, placeholder="R$ 0,00")
        cotas_data.append({"grupo": grupo, "cota": cota, "valor_str": valor_str, "status": "Em Andamento"})

    if st.button("➕ Adicionar mais uma Cota"):
        st.session_state['qtd_cotas'] += 1
        st.rerun()
    st.markdown("---")
    if st.button("Salvar Venda(s)", type="primary", use_container_width=True):
        if not str(cliente).strip():
            st.error("❌ Preencha o Nome do Cliente!")
        else:
            erros_cotas = []
            for i, c in enumerate(cotas_data):
                val_limpo = ''.join(filter(str.isdigit, str(c['valor_str'])))
                v_float = float(val_limpo)/100 if val_limpo else 0.0
                if not str(c['grupo']).strip() or not str(c['cota']).strip() or v_float <= 0:
                    erros_cotas.append(str(i+1))
            if erros_cotas:
                st.error(f"❌ Atenção! Preencha o Grupo, Cota e Valor da(s) Cota(s): {', '.join(erros_cotas)}")
            else:
                aba_vendas = planilha.worksheet("Vendas")
                end_completo = ", ".join([p for p in [rua, numero, complemento, bairro, cidade, uf] if p])
                if cep: end_completo += f" (CEP: {cep})"
                for c in cotas_data:
                    val_float = float(''.join(filter(str.isdigit, str(c['valor_str']))))/100
                    aba_vendas.append_row(["", cliente, str(data.strftime("%d/%m/%Y")), produto, vendedor, c['grupo'], c['cota'], admin, c['status'], val_float])
                try:
                    nomes_cadastrados = aba_clientes.col_values(1)
                    if cliente not in nomes_cadastrados:
                        aba_clientes.append_row([cliente, telefone, email, end_completo, aniversario, profissao, renda, str(datetime.today().strftime("%d/%m/%Y"))])
                except: pass
                st.success(f"✅ {len(cotas_data)} Venda(s) salvas!")
                limpar = ['venda_cliente', 'tel_nv', 'venda_email', 'aniv_nv', 'prof_nv', 'renda_nv', 'venda_cep', 'last_cep', 'venda_rua', 'venda_numero', 'venda_complemento', 'venda_bairro', 'venda_cidade', 'venda_uf']
                for i in range(st.session_state['qtd_cotas']): limpar.extend([f"g_{i}", f"c_{i}", f"v_in_{i}"])
                for k in limpar:
                    if k in st.session_state: del st.session_state[k]
                st.session_state['qtd_cotas'] = 1 

elif menu_selecionado == "Relatórios":
    st.markdown("### 📑 Relatórios Gerenciais")
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
                if hoje.day <= 15: q_ini, q_fim = hoje.replace(day=1), hoje.replace(day=15)
                else: q_ini, q_fim = hoje.replace(day=16), hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])
                df_f = df_f[mask & (df_f['Data_Real'].dt.date >= q_ini.date()) & (df_f['Data_Real'].dt.date <= q_fim.date())]
            elif ft_rel == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_f = df_f[mask & (df_f['Data_Real'].dt.month == ma) & (df_f['Data_Real'].dt.year == aa)]
            elif ft_rel == "Ano Atual": 
                df_f = df_f[mask & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Período Personalizado": 
                df_f = df_f[mask & (df_f['Data_Real'].dt.date >= ri) & (df_f['Data_Real'].dt.date <= rf)]
                
        if st.session_state['perfil_logado'] == "Vendedor": df_f = df_f[df_f['VENDEDOR'] == st.session_state['nome_vendedor']]
        st.divider()

        if df_f.empty: st.warning("Nenhuma venda no período selecionado.")
        else:
            t1, t2, t3 = st.tabs(["👤 Por Usuário", "🏢 Por Administradora", "💰 Comissionamento"])
            with t1:
                rv = df_f.groupby('VENDEDOR').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                rv['Vol'] = rv['Vol'].apply(formatar_brl_puro)
                st.dataframe(rv.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
            with t2:
                ra = df_f.groupby('ADMINISTRADORA').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                ra['Vol'] = ra['Vol'].apply(formatar_brl_puro)
                st.dataframe(ra.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
            
            # --- NOVO RELATÓRIO DE COMISSIONAMENTO ---
            with t3:
                st.markdown("#### Detalhamento de Comissionamento das Vendas do Período")
                df_admin_regras = carregar_df_admin_seguro(aba_admin)
                rel_comissao = []
                
                sum_breno = 0.0
                sum_uriel = 0.0
                sum_vend = 0.0
                
                for _, r in df_f.iterrows():
                    admin_venda = normalizar_string(r['ADMINISTRADORA'])
                    prod_venda = normalizar_produto(r['PRODUTO'])
                    vend_nome = r['VENDEDOR']
                    
                    regra = df_admin_regras[(df_admin_regras['Admin_Norm'] == admin_venda) & (df_admin_regras['Prod_Norm'] == prod_venda)]
                    if not regra.empty:
                        regra = regra.iloc[0]
                        pct_admin_total = 0.0
                        for i in range(1, 26):
                            pct_admin_total += parse_float_safe(regra.get(f"P{i}", 0)) / 100.0
                            
                        val_venda = r['Valor_Numerico']
                        comissao_bruta = val_venda * pct_admin_total
                        imposto_val = comissao_bruta * (cfg.get('Imposto', 7.16) / 100.0)
                        comissao_liq = comissao_bruta - imposto_val
                        
                        tier_pct, tier_parc = calcular_comissao_vendedor(df_vendas_global, vend_nome, r['Data_Real'], cfg)
                        vend_recebe = 0.0
                        breno_recebe = 0.0
                        uriel_recebe = 0.0
                        
                        if vend_nome == "BRENO LIMA":
                            breno_recebe = comissao_liq * (cfg['Breno_Breno']/100.0)
                            uriel_recebe = comissao_liq * (cfg['Breno_Uriel']/100.0)
                        elif vend_nome == "URIEL GOMES":
                            uriel_recebe = comissao_liq * (cfg['Uriel_Uriel']/100.0)
                            breno_recebe = comissao_liq * (cfg['Uriel_Breno']/100.0)
                        elif vend_nome == "Consorbens":
                            breno_recebe = comissao_liq * (cfg['Cons_Breno']/100.0)
                            uriel_recebe = comissao_liq * (cfg['Cons_Uriel']/100.0)
                        else:
                            vend_recebe = val_venda * (tier_pct / 100.0)
                            sobra = comissao_liq - vend_recebe
                            breno_recebe = sobra * 0.50
                            uriel_recebe = sobra * 0.50
                            
                        sum_breno += breno_recebe
                        sum_uriel += uriel_recebe
                        sum_vend += vend_recebe
                            
                        rel_comissao.append({
                            "Cliente": r['Nome do cliente'],
                            "Produto": r['PRODUTO'],
                            "Vendedor": vend_nome,
                            "Grupo": r['GRUPO'],
                            "Cota": r['COTA'],
                            "Comissão (Bruta)": formatar_brl_puro(comissao_bruta),
                            "Comissão (s/ Imposto)": formatar_brl_puro(comissao_liq),
                            "Breno": formatar_brl_puro(breno_recebe),
                            "Uriel": formatar_brl_puro(uriel_recebe),
                            "Vendedor Recebe": formatar_brl_puro(vend_recebe)
                        })
                    else:
                        rel_comissao.append({
                            "Cliente": r['Nome do cliente'], "Produto": r['PRODUTO'], "Vendedor": vend_nome, "Grupo": r['GRUPO'], "Cota": r['COTA'],
                            "Comissão (Bruta)": "⚠️ Sem Regra", "Comissão (s/ Imposto)": "⚠️ Sem Regra", "Breno": "-", "Uriel": "-", "Vendedor Recebe": "-"
                        })
                
                df_rel_comissao = pd.DataFrame(rel_comissao)
                if not df_rel_comissao.empty:
                    if st.session_state['perfil_logado'] == "Vendedor": 
                        df_rel_comissao = df_rel_comissao.drop(columns=["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"])
                    
                    st.dataframe(df_rel_comissao.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
                    
                    if st.session_state['perfil_logado'] == "Master":
                        st.divider()
                        st.markdown("#### 💵 Fechamento do Período (Previsão Baseada em Vendas)")
                        mt1, mt2, mt3 = st.columns(3)
                        mt1.metric("Breno (Sócios)", formatar_brl_puro(sum_breno))
                        mt2.metric("Uriel (Sócios)", formatar_brl_puro(sum_uriel))
                        mt3.metric("Vendedores", formatar_brl_puro(sum_vend))
                else:
                    st.info("Nenhuma previsão financeira gerada para este período.")
    else: st.info("Não possui vendas.")

elif menu_selecionado == "Regras de Comissão":
    st.markdown("### 🏢 Regras de Comissão")
    df_admin = carregar_df_admin_seguro(aba_admin)
    
    t_cad_adm, t_regras, t_reg_int = st.tabs(["🏢 Cadastrar Admin", "📋 Regras", "👥 Regras Internas"])
    with t_cad_adm:
        st.subheader("Cadastrar Nova Administradora")
        with st.form("form_cad_admin"):
            c1, c2 = st.columns([2, 1])
            with c1: nome_adm = st.text_input("Nome da Administradora *")
            with c2: cnpj_adm = st.text_input("CNPJ")
            end_adm = st.text_input("Endereço Completo")
            if st.form_submit_button("Salvar Administradora", type="primary"):
                if nome_adm:
                    aba_admin_cad.append_row([nome_adm.upper(), cnpj_adm, end_adm])
                    st.success("Cadastrada com sucesso!")
                    st.rerun()
                else: st.error("Nome é obrigatório.")
        st.write("Administradoras Cadastradas")
        dados_cad = aba_admin_cad.get_all_values()
        if len(dados_cad) > 1: st.dataframe(pd.DataFrame(dados_cad[1:], columns=dados_cad[0]), use_container_width=True, hide_index=True)
    with t_regras:
        st.subheader("Regras Cadastradas")
        if not df_admin.empty:
            df_mostrar = df_admin.drop(columns=['Admin_Norm', 'Prod_Norm'], errors='ignore').copy()
            def calc_total(row):
                t = 0.0
                for i in range(1, 26):
                    v_str = str(row.get(f"P{i}", "0")).replace('%', '').strip()
                    try: t += float(v_str)
                    except: pass
                return f"{t:.2f}%".replace('.', ',')
            df_mostrar.insert(2, 'Total Comissão', df_mostrar.apply(calc_total, axis=1))
            st.dataframe(df_mostrar.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
        else: st.info("Nenhuma regra cadastrada.")
        with st.expander("➕ Adicionar Nova Regra", expanded=False):
            with st.form("f_adm_nova"):
                c1, c2 = st.columns(2)
                with c1: n = st.selectbox("Administradora *", lista_admin_bd)
                with c2: p = st.selectbox("Produto *", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
                st.write("Percentual de Comissão por Parcela (%)")
                inputs_p = []
                for linha in range(5):
                    cols_p = st.columns(5)
                    for col in range(5):
                        num_p = (linha * 5) + col + 1
                        with cols_p[col]:
                            v = st.number_input(f"Parcela {num_p}", min_value=0.0, step=0.1, key=f"nova_p{num_p}")
                            inputs_p.append(v)
                if st.form_submit_button("Salvar Regra da Administradora", type="primary"):
                    if n and p and n != "Nenhuma administradora cadastrada":
                        aba_admin.append_row([n.upper(), p] + [f"{v}%" if v > 0 else "" for v in inputs_p])
                        st.success("Regra cadastrada com sucesso!")
                        st.rerun()
                    else: st.error("Selecione uma Administradora.")
        with st.expander("✏️ Editar ou Excluir Regra", expanded=False):
            if not df_admin.empty:
                opts = df_admin.apply(lambda x: f"Linha {x.name + 2} | {x['Administradora']} - {x['Produto']}", axis=1).tolist()
                sel = st.selectbox("Selecione a regra para editar:", [""] + opts)
                if sel:
                    l_plan = int(sel.split(" | ")[0].replace("Linha ", ""))
                    reg_at = df_admin.iloc[l_plan - 2]
                    c1, c2 = st.columns(2)
                    with c1: 
                        idx_admin = lista_admin_bd.index(reg_at['Administradora']) if reg_at['Administradora'] in lista_admin_bd else 0
                        e_n = st.selectbox("Administradora", lista_admin_bd, index=idx_admin)
                    with c2: 
                        e_p = st.selectbox("Produto", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"], index=obter_index_produto(reg_at['Produto']))
                    st.write("Percentuais (%)")
                    edit_inputs_p = []
                    for linha in range(5):
                        cols_p = st.columns(5)
                        for col in range(5):
                            num_p = (linha * 5) + col + 1
                            val_str = str(reg_at[f'P{num_p}']).replace('%', '').strip()
                            try: val_float = float(val_str)
                            except: val_float = 0.0
                            with cols_p[col]:
                                v = st.number_input(f"P {num_p}", min_value=0.0, step=0.1, value=val_float, key=f"e_regra_p{num_p}")
                                edit_inputs_p.append(v)
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("Salvar Alterações", type="primary"):
                            aba_admin.update_cell(l_plan, 1, e_n.upper())
                            aba_admin.update_cell(l_plan, 2, e_p)
                            for i, v in enumerate(edit_inputs_p): aba_admin.update_cell(l_plan, i+3, f"{v}%" if v > 0 else "")
                            st.success("Regra alterada!")
                            st.rerun()
                    with b2:
                        if st.button("🚨 EXCLUIR REGRA"):
                            aba_admin.delete_rows(l_plan)
                            st.rerun()

    with t_reg_int:
        st.subheader("Configurações de Recebimento (Sócios e Vendedores)")
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            st.markdown("**Vendas do Breno Lima**")
            b_b = st.number_input("Para Breno (%)", value=cfg["Breno_Breno"], step=1.0)
            b_u = st.number_input("Para Uriel (%)", value=cfg["Breno_Uriel"], step=1.0)
        with cc2:
            st.markdown("**Vendas do Uriel Gomes**")
            u_u = st.number_input("Para Uriel (%) ", value=cfg["Uriel_Uriel"], step=1.0)
            u_b = st.number_input("Para Breno (%) ", value=cfg["Uriel_Breno"], step=1.0)
        with cc3:
            st.markdown("**Vendas da Consorbens (PJ)**")
            c_b = st.number_input("Para Breno (%)  ", value=cfg["Cons_Breno"], step=1.0)
            c_u = st.number_input("Para Uriel (%)  ", value=cfg["Cons_Uriel"], step=1.0)
            
        st.divider()
        st.markdown("#### Regra Vendedor Terceiro")
        ct1, ct2, ct3 = st.columns(3)
        with ct1:
            t1_max_str = st.text_input("Nível 1: Até (Volume R$)", value=str(int(cfg["T1_Max"])))
            t1_pct = st.number_input("Comissão (%)", value=cfg["T1_Pct"], step=0.1)
            t1_parc = st.number_input("Qtd. Parcelas", value=int(cfg["T1_Parc"]), step=1)
        with ct2:
            t2_max_str = st.text_input("Nível 2: Até (Volume R$) ", value=str(int(cfg["T2_Max"])))
            t2_pct = st.number_input("Comissão (%) ", value=cfg["T2_Pct"], step=0.1)
            t2_parc = st.number_input("Qtd. Parcelas ", value=int(cfg["T2_Parc"]), step=1)
        with ct3:
            st.markdown("**Teto (Nível 3)**")
            t3_pct = st.number_input("Comissão (%)  ", value=cfg["T3_Pct"], step=0.1)
            t3_parc = st.number_input("Qtd. Parcelas  ", value=int(cfg["T3_Parc"]), step=1)

        st.divider()
        st.markdown("#### Imposto sobre Nota Fiscal")
        st.caption("Este imposto é abatido apenas da parte que cabe à Corretora (Sócios), antes da divisão dos lucros.")
        imposto_in = st.number_input("Imposto (%)", value=cfg.get("Imposto", 7.16), step=0.01)

        st.write("")
        if st.button("Salvar Regras de Pagamento", type="primary", use_container_width=True):
            t1_val = parse_float_safe(t1_max_str)
            t2_val = parse_float_safe(t2_max_str)
            aba_cfg.clear()
            aba_cfg.append_row(cols_cfg)
            aba_cfg.append_row([b_b, b_u, u_u, u_b, c_b, c_u, t1_val, t1_pct, t1_parc, t2_val, t2_pct, t2_parc, t3_pct, t3_parc, imposto_in])
            st.success("Regras Internas atualizadas!")
            st.rerun()

elif menu_selecionado == "Baixar Parcela":
    st.markdown("### 💰 Baixa de Comissão")
    st.info("A integração de baixa com o sistema de previsão será habilitada na próxima etapa!")
