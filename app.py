import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import requests 
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

def normalizar_produto(p):
    p = str(p).strip().upper()
    if p in ["AUTO", "AUTOMOVEL", "AUTOMÓVEL"]: return "AUTOMÓVEL"
    if p in ["IMOVEL", "IMÓVEL", "IMÓVEIS", "IMOVEIS"]: return "IMÓVEL"
    if p in ["MOTO", "MOTOS", "MOTOCICLETA"]: return "MOTO"
    if p in ["CAMINHAO", "CAMINHÃO", "CAMINHÕES"]: return "CAMINHÃO"
    if p in ["SERVIÇO", "SERVIÇOS", "SERVICO", "SERVICOS"]: return "SERVIÇOS"
    return p

def normalizar_admin(a):
    a = str(a).strip().upper()
    if a == "ITAU": return "ITAÚ"
    return a

def obter_index_produto(p_str):
    norm = normalizar_produto(p_str)
    mapping = {"AUTOMÓVEL": 0, "IMÓVEL": 1, "MOTO": 2, "CAMINHÃO": 3, "SERVIÇOS": 4}
    return mapping.get(norm, 0)

# Callbacks
def mascara_tel_nv(): st.session_state['tel_nv'] = formatar_telefone(st.session_state.get('tel_nv', ''))
def mascara_aniv_nv(): st.session_state['aniv_nv'] = formatar_data(st.session_state.get('aniv_nv', ''))
def mascara_renda_nv(): st.session_state['renda_nv'] = formatar_moeda(st.session_state.get('renda_nv', ''))

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
simuladores = ["🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
is_simulator = menu_selecionado in simuladores

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

if is_simulator: css += """ <style>.stApp { background-color: #0f172a !important; }</style> """
else: css += """ <style>.stApp { background-color: #ffffff !important; }</style> """

st.markdown(css, unsafe_allow_html=True)

# === 4. CONEXÃO PLANILHA ===
@st.cache_resource
def conectar_planilha():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    return gc.open("Sistema CRM")

planilha = conectar_planilha()
aba_vendas = planilha.worksheet("Vendas")
try: aba_clientes = planilha.worksheet("Clientes")
except: 
    aba_clientes = planilha.add_worksheet("Clientes", 1000, 10)
    aba_clientes.append_row(["Nome", "Telefone", "Email", "Endereco", "Aniversario", "Profissao", "Renda", "Data_Cadastro"])

try: 
    aba_admin = planilha.worksheet("Administradoras")
    d_admin_temp = aba_admin.get_all_values()
    if not d_admin_temp or len(d_admin_temp[0]) < 27:
        aba_admin.clear()
        cabecalho_admin = ["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)]
        aba_admin.append_row(cabecalho_admin)
except: 
    aba_admin = planilha.add_worksheet("Administradoras", 100, 27)
    cabecalho_admin = ["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)]
    aba_admin.append_row(cabecalho_admin)

# Criando a nova aba para Comissões dos Vendedores
try: 
    aba_com_int = planilha.worksheet("Comissoes_Internas")
except: 
    aba_com_int = planilha.add_worksheet("Comissoes_Internas", 100, 3)
    aba_com_int.append_row(["Alvo (Usuário/Perfil)", "Base de Cálculo", "Percentual (%)"])

# === RENDERIZAÇÃO ===
if not is_logado:
    if menu_selecionado == "🔐 Login (Área Restrita)":
        st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        col_esq, col_meio, col_dir = st.columns([1, 1.2, 1])
        with col_meio:
            with st.form("form_login"):
                usuario_input = st.text_input("Usuário (Login)").lower()
                senha_input = st.text_input("Senha", type="password")
                
                st.write("") 
                
                c_btn1, c_btn2, c_btn3 = st.columns([1, 1.5, 1])
                with c_btn2:
                    btn_login = st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True)
                
                if btn_login:
                    if usuario_input in USUARIOS and USUARIOS[usuario_input]["senha"] == senha_input:
                        st.session_state['usuario_logado'] = usuario_input
                        st.session_state['perfil_logado'] = USUARIOS[usuario_input]["perfil"]
                        st.session_state['nome_vendedor'] = USUARIOS[usuario_input]["nome"]
                        st.session_state['menu_lateral'] = "Dashboard" 
                        st.rerun() 
                    else: st.error("❌ Usuário ou senha incorretos.")
    elif menu_selecionado == "🏍️ Simulador Yamaha": carregar_ferramenta("yamaha.html")
    elif menu_selecionado == "🏦 Simulador Itaú": carregar_ferramenta("itau.html")
    elif menu_selecionado == "🎯 Oportunidades Itaú": carregar_ferramenta("guia.html")
    elif menu_selecionado == "⚖️ Financiamento x Consórcio": carregar_ferramenta("comparador.html")
    st.stop() 

if menu_selecionado == "Dashboard":
    dados_brutos = aba_vendas.get_all_values()
    
    # -------------------------------------------------------------
    # PERFIL DO CLIENTE
    # -------------------------------------------------------------
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        
        st.markdown(f"## 👤 Perfil: {cliente_nome}")
        
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
        st.subheader("📋 Dados Cadastrais")
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
        endereco = c1.text_input("Endereço Completo", key=key_end, disabled=not is_master)
        telefone_edit = c1.text_input("Telefone", key=key_tel, on_change=m_tel_ed, disabled=not is_master, placeholder="(31) 99999-9999", max_chars=15)
        profissao_edit = c1.text_input("Profissão", key=key_prof, disabled=not is_master)
        
        email = c2.text_input("E-mail", key=key_email, disabled=not is_master)
        aniversario_edit = c2.text_input("Data de Aniversário (DD/MM/AAAA)", key=key_aniv, on_change=m_aniv_ed, disabled=not is_master, placeholder="DD/MM/AAAA", max_chars=10)
        renda_edit = c2.text_input("Renda Mensal (R$)", key=key_renda, on_change=m_renda_ed, disabled=not is_master, placeholder="R$ 0,00")
        
        if is_master:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Salvar Alterações", type="primary", use_container_width=True):
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
                        if vendas_nomes[i-1] == cliente_nome:
                            aba_vendas.delete_rows(i)

                    st.session_state['cliente_visualizado'] = None
                    st.session_state['key_tabela'] += 1
                    st.rerun()

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        if len(dados_brutos) > 1:
            df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
            df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
            cotas_cliente = df_vendas[df_vendas['Nome do cliente'] == cliente_nome].copy()
            if not cotas_cliente.empty:
                cotas_cliente['Valor_Numerico'] = cotas_cliente['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip().apply(pd.to_numeric, errors='coerce').fillna(0.0)
                info_a, info_b = st.columns(2)
                info_a.metric("Total de Cotas Adquiridas", len(cotas_cliente))
                info_b.metric("Volume Total Investido", f"R$ {cotas_cliente['Valor_Numerico'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                cotas_cliente['Valor Formatado'] = cotas_cliente['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                ficha_display = cotas_cliente[['DATA', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'VENDEDOR', 'Valor Formatado']].rename(columns={'DATA': 'Data da Venda', 'ADMINISTRADORA': 'Administradora', 'PRODUTO': 'Produto', 'GRUPO': 'Grupo', 'COTA': 'Cota', 'VENDEDOR': 'Vendedor', 'Valor Formatado': 'Valor (R$)'})
                estilo_ficha = ficha_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_ficha, use_container_width=True, hide_index=True)
                
                # --- PREVISÃO DE COMISSIONAMENTO ---
                st.write("")
                st.subheader("📈 Previsão de Comissionamento")
                
                dados_admin = aba_admin.get_all_values()
                if len(dados_admin) > 1: df_admin = pd.DataFrame(dados_admin[1:], columns=dados_admin[0])
                else: df_admin = pd.DataFrame(columns=["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)])
                    
                previsoes = []
                for idx, r in cotas_cliente.iterrows():
                    admin_venda = normalizar_admin(r['ADMINISTRADORA'])
                    prod_venda = normalizar_produto(r['PRODUTO'])
                    
                    regra_encontrada = None
                    for _, regra_row in df_admin.iterrows():
                        if normalizar_admin(regra_row['Administradora']) == admin_venda and normalizar_produto(regra_row['Produto']) == prod_venda:
                            regra_encontrada = regra_row
                            break
                            
                    if regra_encontrada is not None:
                        data_venda = pd.to_datetime(r['DATA'], format="%d/%m/%Y", errors='coerce')
                        if pd.notna(data_venda):
                            for i in range(1, 26):
                                p_str = str(regra_encontrada[f"P{i}"]).replace('%', '').strip()
                                try: p_val = float(p_str)
                                except: p_val = 0.0
                                
                                if p_val > 0:
                                    data_pagamento = data_venda + pd.Timedelta(days=7) + pd.DateOffset(months=i-1)
                                    valor_pagamento = r['Valor_Numerico'] * (p_val / 100)
                                    previsoes.append({
                                        "Cota": f"{r['GRUPO']}/{r['COTA']} ({r['ADMINISTRADORA']})",
                                        "Vendedor": r['VENDEDOR'],
                                        "Parcela": f"{i}ª Parcela",
                                        "Data Prevista": data_pagamento.strftime("%d/%m/%Y"),
                                        "%": f"{p_val}%",
                                        "Valor Previsto": f"R$ {valor_pagamento:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                                    })
                    else:
                        st.warning(f"⚠️ Regra não cadastrada para: {r['ADMINISTRADORA']} - {r['PRODUTO']} (Cota {r['GRUPO']}/{r['COTA']})")
                        
                if previsoes:
                    df_prev = pd.DataFrame(previsoes)
                    if not is_master: df_prev = df_prev[df_prev['Vendedor'] == st.session_state['nome_vendedor']]
                        
                    if not df_prev.empty:
                        st.dataframe(df_prev.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
                    else: st.info("Nenhuma previsão de comissão vinculada a você para este cliente.")
                else:
                    if len(df_admin) == 0: st.info("Aguardando configurações de regras para gerar a previsão.")

                if is_master:
                    st.write("")
                    with st.expander("⚙️ Gerenciar / Excluir Cota Específica"):
                        st.info("Aqui você pode apagar apenas uma cota caso o cliente tenha cancelado, sem precisar excluir o cadastro inteiro.")
                        opcoes_cotas = cotas_cliente.apply(lambda r: f"Linha {r.name + 2} | Grupo: {r['GRUPO']} / Cota: {r['COTA']} - Valor: {r['Valor Formatado']}", axis=1).tolist()
                        c_del1, c_del2 = st.columns([3, 1])
                        with c_del1:
                            cota_del_selecionada = st.selectbox("Selecione a cota que deseja apagar:", [""] + opcoes_cotas)
                        with c_del2:
                            st.write("")
                            if st.button("🚨 Apagar Esta Cota", use_container_width=True):
                                if cota_del_selecionada:
                                    linha_del = int(cota_del_selecionada.split(" | ")[0].replace("Linha ", ""))
                                    aba_vendas.delete_rows(linha_del)
                                    st.success("Cota apagada com sucesso!")
                                    st.rerun()
                                else: st.error("Selecione a cota.")

            else: st.warning("Nenhuma cota encontrada para este cliente.")

    # -------------------------------------------------------------
    # DASHBOARD PADRÃO
    # -------------------------------------------------------------
    else:
        if len(dados_brutos) > 1:
            df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
            df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
            df_vendas['Data_Real'] = pd.to_datetime(df_vendas['DATA'], dayfirst=True, errors='coerce')
            df_vendas['Valor_Numerico'] = df_vendas['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip().apply(pd.to_numeric, errors='coerce').fillna(0.0)

            if st.session_state['perfil_logado'] == "Vendedor": df_vendas = df_vendas[df_vendas['VENDEDOR'] == st.session_state['nome_vendedor']]
                
            col_t1, col_t2 = st.columns([4, 1])
            with col_t2:
                st.write("")
                if st.button("Nova Venda", use_container_width=True, type="primary"):
                    st.session_state['menu_lateral'] = "Nova Venda"
                    st.rerun()
            
            c_filtro1, c_filtro2 = st.columns([1, 2])
            with c_filtro1:
                filtro_cli = st.selectbox("⏳ Filtro por Data da Venda:", ["Últimos 5 Cadastros", "Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
                if filtro_cli == "Período Personalizado":
                    cd1, cd2 = st.columns(2)
                    with cd1: data_inicio = st.date_input("Data Inicial", format="DD/MM/YYYY")
                    with cd2: data_fim = st.date_input("Data Final", format="DD/MM/YYYY")
            with c_filtro2: busca_nome = st.text_input("🔍 Buscar Cliente por Nome:")
                
            hoje = datetime.today()
            df_clientes = df_vendas.copy()
            
            if filtro_cli == "Últimos 5 Cadastros" and busca_nome.strip() == "": df_clientes = df_clientes.tail(5).iloc[::-1]
            elif filtro_cli != "Todos os Clientes" and filtro_cli != "Últimos 5 Cadastros":
                mask = df_clientes['Data_Real'].notna()
                if filtro_cli == "Mês Atual": df_clientes = df_clientes[mask & (df_clientes['Data_Real'].dt.month == hoje.month) & (df_clientes['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Mês Anterior":
                    mes_ant, ano_ant = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                    df_clientes = df_clientes[mask & (df_clientes['Data_Real'].dt.month == mes_ant) & (df_clientes['Data_Real'].dt.year == ano_ant)]
                elif filtro_cli == "Ano Atual": df_clientes = df_clientes[mask & (df_clientes['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Período Personalizado": df_clientes = df_clientes[mask & (df_clientes['Data_Real'].dt.date >= data_inicio) & (df_clientes['Data_Real'].dt.date <= data_fim)]
                
            if busca_nome.strip() != "": df_clientes = df_vendas[df_vendas['Nome do cliente'].astype(str).str.contains(busca_nome.strip(), case=False, na=False)]
                
            if not df_clientes.empty:
                df_display = df_clientes.copy()
                df_display['Grupo e cota'] = df_display.apply(lambda x: f"{x['GRUPO']} / {x['COTA']}" if str(x['GRUPO']).strip() or str(x['COTA']).strip() else "N/A", axis=1)
                df_display['valor da venda'] = df_display['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                df_display['Prod_Norm'] = df_display['PRODUTO'].apply(normalizar_produto)
                df_display = df_display[['Nome do cliente', 'Grupo e cota', 'Prod_Norm', 'ADMINISTRADORA', 'valor da venda', 'VENDEDOR', 'DATA']].rename(columns={ 'Nome do cliente': 'Nome', 'Prod_Norm': 'Tipo de Produto', 'ADMINISTRADORA': 'Administradora', 'VENDEDOR': 'Vendedor', 'DATA': 'Data da Venda' })
                
                estilo_tabela = df_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                tabela_interativa = st.dataframe(estilo_tabela, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key=f"tabela_clientes_{st.session_state['key_tabela']}")
                
                st.markdown(f"""<div style="text-align: right; padding-top: 10px;"><h4 style="color: #239b56; font-weight: bold; margin: 0;">TOTAL: R$ {df_clientes['Valor_Numerico'].sum():,.2f}</h4></div>""".replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
                
                sel = tabela_interativa.selection.rows
                if len(sel) > 0:
                    st.session_state['cliente_visualizado'] = df_display.iloc[sel[0]]['Nome']
                    st.rerun()
            else: st.warning("Nenhum cliente encontrado com esses filtros ou termos de busca.")

            st.divider()
            st.subheader("📊 Gráficos de Vendas Globais")
            g_filtro1, g_filtro2 = st.columns(2)
            with g_filtro1:
                ft_graf = st.selectbox("⏳ Período para o Gráfico:", ["Mês Atual", "Mês Anterior", "Anual", "Todas as Vendas", "Período Personalizado"])
                if ft_graf == "Período Personalizado":
                    cg1, cg2 = st.columns(2)
                    with cg1: gi = st.date_input("Data Inicial", format="DD/MM/YYYY", key="g_inicio")
                    with cg2: gf = st.date_input("Data Final", format="DD/MM/YYYY", key="g_fim")
            with g_filtro2: fp_graf = st.selectbox("📦 Produto:", ["Todos", "Automóvel", "Imóvel", "Moto", "Caminhão", "Serviços"])
                
            df_g = df_vendas.copy()
            if ft_graf != "Todas as Vendas" and not df_g['Data_Real'].isna().all():
                mask = df_g['Data_Real'].notna()
                if ft_graf == "Mês Atual": df_g = df_g[mask & (df_g['Data_Real'].dt.month == hoje.month) & (df_g['Data_Real'].dt.year == hoje.year)]
                elif ft_graf == "Mês Anterior":
                    ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                    df_g = df_g[mask & (df_g['Data_Real'].dt.month == ma) & (df_g['Data_Real'].dt.year == aa)]
                elif ft_graf == "Anual": df_g = df_g[mask & (df_g['Data_Real'].dt.year == hoje.year)]
                elif ft_graf == "Período Personalizado": df_g = df_g[mask & (df_g['Data_Real'].dt.date >= gi) & (df_g['Data_Real'].dt.date <= gf)]
                
            if fp_graf != "Todos": 
                df_g['Prod_Norm'] = df_g['PRODUTO'].apply(normalizar_produto)
                df_g = df_g[df_g['Prod_Norm'] == normalizar_produto(fp_graf)]
                
            if not df_g.empty:
                m1, m2 = st.columns(2)
                m1.metric("Volume Total Vendido", f"R$ {df_g['Valor_Numerico'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                m2.metric("Total de Cotas Vendidas", len(df_g))
                st.write("")
                agrupar = 'PRODUTO' if fp_graf == "Todos" else 'ADMINISTRADORA'
                df_pizza = df_g[agrupar].value_counts().reset_index()
                df_pizza.columns = ['Categoria', 'Quantidade']
                graf = alt.Chart(df_pizza).mark_arc(innerRadius=60).encode(theta=alt.Theta(field="Quantidade", type="quantitative"), color=alt.Color(field="Categoria", type="nominal"), tooltip=['Categoria', 'Quantidade']).properties(height=350)
                _, gc2, _ = st.columns([1, 2, 1])
                with gc2: st.altair_chart(graf, use_container_width=True)
            else: st.warning("📊 Não há vendas suficientes para gerar o gráfico com os filtros atuais.")
        else: st.info("O sistema ainda não possui vendas cadastradas na planilha.")

elif menu_selecionado == "Nova Venda":
    st.markdown("## 📝 Cadastrar Nova Venda")
    
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
        if st.session_state['perfil_logado'] == "Master": vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"])
        else:
            st.write(f"**Vendedor:** {st.session_state['nome_vendedor']}")
            vendedor = st.session_state['nome_vendedor']
    with col_v2:
        admin = st.selectbox("Administradora *", ["YAMAHA", "ITAÚ", "ROMA", "EMBRACON"])
        produto = st.selectbox("Produto *", ["Automóvel", "Imóvel", "Moto", "Caminhão", "Serviços"])
        
    st.markdown("##### Cotas Adquiridas")
    if 'qtd_cotas' not in st.session_state: st.session_state['qtd_cotas'] = 1

    cotas_data = []
    for i in range(st.session_state['qtd_cotas']):
        st.markdown(f"**Cota {i+1}**")
        cq1, cq2, cq3, cq4 = st.columns(4)
        if f"g_{i}" not in st.session_state: st.session_state[f"g_{i}"] = ""
        if f"c_{i}" not in st.session_state: st.session_state[f"c_{i}"] = ""
        if f"v_in_{i}" not in st.session_state: st.session_state[f"v_in_{i}"] = ""
        if f"s_{i}" not in st.session_state: st.session_state[f"s_{i}"] = "Vendido"
        
        with cq1: grupo = st.text_input(f"Grupo *", key=f"g_{i}")
        with cq2: cota = st.text_input(f"Cota *", key=f"c_{i}")
        with cq3:
            def m_moeda(idx=i): 
                val = st.session_state.get(f"v_in_{idx}", "")
                st.session_state[f"v_in_{idx}"] = formatar_moeda(val)
                
            valor_str = st.text_input(f"Valor (R$) *", key=f"v_in_{i}", on_change=m_moeda, placeholder="R$ 0,00")
        with cq4: status = st.selectbox(f"Status", ["Vendido", "Contemplado", "Cancelado"], key=f"s_{i}")
        
        cotas_data.append({"grupo": grupo, "cota": cota, "valor_str": valor_str, "status": status})

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
                st.error(f"❌ Atenção! Preencha o Grupo, Cota e um Valor maior que zero da(s) seguinte(s) Cota(s): {', '.join(erros_cotas)}")
            else:
                aba_vendas = planilha.worksheet("Vendas")
                end_completo = ", ".join([p for p in [rua, numero, complemento, bairro, cidade, uf] if p])
                if cep: end_completo += f" (CEP: {cep})"

                for c in cotas_data:
                    val_float = float(''.join(filter(str.isdigit, str(c['valor_str']))))/100
                    aba_vendas.append_row(["", cliente, str(data.strftime("%d/%m/%Y")), produto, vendedor, c['grupo'], c['cota'], admin, c['status'], val_float])

                try:
                    dados_cli_brutos = aba_clientes.get_all_values()
                    nomes_cadastrados = [row[0] for row in dados_cli_brutos] if len(dados_cli_brutos) > 0 else []
                except: nomes_cadastrados = []
                
                if cliente not in nomes_cadastrados:
                    aba_clientes.append_row([cliente, telefone, email, end_completo, aniversario, profissao, renda, str(datetime.today().strftime("%d/%m/%Y"))])

                st.success(f"✅ {len(cotas_data)} Venda(s) e Cadastro de {cliente} salvos com sucesso!")
                
                limpar = ['venda_cliente', 'tel_nv', 'venda_email', 'aniv_nv', 'prof_nv', 'renda_nv', 'venda_cep', 'last_cep', 'venda_rua', 'venda_numero', 'venda_complemento', 'venda_bairro', 'venda_cidade', 'venda_uf']
                for i in range(st.session_state['qtd_cotas']): limpar.extend([f"g_{i}", f"c_{i}", f"v_in_{i}", f"s_{i}"])
                for k in limpar:
                    if k in st.session_state: del st.session_state[k]
                st.session_state['qtd_cotas'] = 1 

elif menu_selecionado == "Gerenciar Vendas (Editar/Deletar)":
    st.markdown("## 🛠️ Gerenciar e Editar Vendas")
    st.warning("Área Restrita (Apenas Sócios). Muito cuidado ao deletar informações!")
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_brutos = aba_vendas.get_all_values()
    if len(dados_brutos) > 1:
        df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
        df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
        opcoes_busca = df_vendas.apply(lambda r: f"Linha {r.name + 2} | Cliente: {r['Nome do cliente']} - Grupo/Cota: {r['GRUPO']}/{r['COTA']}", axis=1).tolist()
        venda_selecionada = st.selectbox("Selecione a venda para alterar/excluir:", [""] + opcoes_busca)
        
        if venda_selecionada:
            linha_planilha = int(venda_selecionada.split(" | ")[0].replace("Linha ", ""))
            venda_atual = df_vendas.iloc[linha_planilha - 2]
            st.divider()
            st.subheader(f"Editando Venda: {venda_atual['Nome do cliente']}")
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome do Cliente", value=str(venda_atual['Nome do cliente']))
                novo_status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"], index=["Vendido", "Contemplado", "Cancelado"].index(venda_atual['STATUS'] if venda_atual['STATUS'] in ["Vendido", "Contemplado", "Cancelado"] else "Vendido"))
            with col2:
                val_float = pd.to_numeric(str(venda_atual['VALOR']).replace('R$', '').replace('.','').replace(',', '.').strip(), errors='coerce')
                novo_valor = st.number_input("Valor da Venda (R$)", value=float(val_float) if not pd.isna(val_float) else 0.0)

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
    else: st.info("Nenhuma venda para gerenciar.")

elif menu_selecionado == "Relatórios":
    st.markdown("## 📑 Relatórios Gerenciais")
    aba_vendas = planilha.worksheet("Vendas")
    dados_brutos = aba_vendas.get_all_values()
    if len(dados_brutos) > 1:
        df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
        df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
        df_vendas['Data_Real'] = pd.to_datetime(df_vendas['DATA'], dayfirst=True, errors='coerce')
        df_vendas['Valor_Numerico'] = df_vendas['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip().apply(pd.to_numeric, errors='coerce').fillna(0.0)

        c1, c2 = st.columns([1, 2])
        with c1:
            ft_rel = st.selectbox("⏳ Período:", ["Mês Atual", "Mês Anterior", "Ano Atual", "Todas as Vendas", "Período Personalizado"])
            if ft_rel == "Período Personalizado":
                rd1, rd2 = st.columns(2)
                with rd1: ri = st.date_input("Data Inicial", format="DD/MM/YYYY")
                with rd2: rf = st.date_input("Data Final", format="DD/MM/YYYY")
        
        hoje = datetime.today()
        df_f = df_vendas.copy()
        
        if ft_rel != "Todas as Vendas":
            m = df_f['Data_Real'].notna()
            if ft_rel == "Mês Atual": df_f = df_f[m & (df_f['Data_Real'].dt.month == hoje.month) & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_f = df_f[m & (df_f['Data_Real'].dt.month == ma) & (df_f['Data_Real'].dt.year == aa)]
            elif ft_rel == "Ano Atual": df_f = df_f[m & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Período Personalizado": df_f = df_f[m & (df_f['Data_Real'].dt.date >= ri) & (df_f['Data_Real'].dt.date <= rf)]
                
        if st.session_state['perfil_logado'] == "Vendedor": df_f = df_f[df_f['VENDEDOR'] == st.session_state['nome_vendedor']]
        st.divider()

        if df_f.empty: st.warning("Nenhuma venda no período selecionado.")
        else:
            t1, t2, t3 = st.tabs(["👤 Por Usuário", "🏢 Por Administradora", "💰 Comissões"])
            with t1:
                rv = df_f.groupby('VENDEDOR').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                rv['Vol'] = rv['Vol'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.dataframe(rv.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
            with t2:
                ra = df_f.groupby('ADMINISTRADORA').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                ra['Vol'] = ra['Vol'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.dataframe(ra.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
            with t3:
                pct = st.number_input("Comissão Média (%)", min_value=0.0, value=1.0, step=0.1)
                dc = df_f.groupby('VENDEDOR').agg(Vol=('Valor_Numerico', 'sum')).reset_index()
                dc['Comissão'] = dc['Vol'] * (pct / 100)
                st.metric("Comissão Total", f"R$ {dc['Comissão'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                dc['Vol'] = dc['Vol'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                dc['Comissão'] = dc['Comissão'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.dataframe(dc.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
    else: st.info("Não possui vendas.")

elif menu_selecionado == "Regras de Comissão":
    st.markdown("## 🏢 Regras de Comissão")
    
    # DF Administradoras
    dados_admin = aba_admin.get_all_values()
    if len(dados_admin) > 1:
        df_admin = pd.DataFrame(dados_admin[1:])
        df_admin = df_admin.iloc[:, :27]
        df_admin.columns = ["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)]
    else: 
        df_admin = pd.DataFrame(columns=["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)])

    # DF Comissões Internas
    dados_com_int = aba_com_int.get_all_values()
    if len(dados_com_int) > 1:
        df_com_int = pd.DataFrame(dados_com_int[1:], columns=dados_com_int[0])
    else:
        df_com_int = pd.DataFrame(columns=["Alvo (Usuário/Perfil)", "Base de Cálculo", "Percentual (%)"])

    t1, t2, t3, t4 = st.tabs(["📋 Adm Cadastradas", "➕ Nova Regra Adm", "✏️ Editar/Excluir Adm", "👥 Comissões Internas"])
    
    with t1:
        if not df_admin.empty:
            df_mostrar = df_admin.copy()
            st.dataframe(df_mostrar.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
        else: st.info("Nenhuma regra de comissionamento de administradora.")
        
    with t2:
        with st.form("f_adm"):
            st.subheader("Dados da Regra")
            c1, c2 = st.columns(2)
            with c1: n = st.text_input("Administradora *")
            with c2: p = st.selectbox("Produto *", ["Automóvel", "Imóvel", "Moto", "Caminhão", "Serviços"])
            
            st.divider()
            st.subheader("Percentual de Comissão por Parcela (%)")
            st.caption("Preencha apenas as parcelas que geram comissionamento. Deixe 0.0 nas demais.")
            
            inputs_p = []
            for linha in range(5):
                cols_p = st.columns(5)
                for col in range(5):
                    num_p = (linha * 5) + col + 1
                    with cols_p[col]:
                        v = st.number_input(f"Parcela {num_p}", min_value=0.0, step=0.1, key=f"nova_p{num_p}")
                        inputs_p.append(v)

            if st.form_submit_button("Salvar Regra da Administradora", type="primary"):
                if n and p:
                    nova_linha = [n.upper(), p] + [f"{v}%" if v > 0 else "" for v in inputs_p]
                    aba_admin.append_row(nova_linha)
                    st.success("Regra cadastrada com sucesso!")
                    st.rerun()
                else: st.error("Preencha a Administradora e o Produto.")
                
    with t3:
        if not df_admin.empty:
            opts = df_admin.apply(lambda x: f"Linha {x.name + 2} | {x['Administradora']} - {x['Produto']}", axis=1).tolist()
            sel = st.selectbox("Selecione a regra para editar:", [""] + opts)
            if sel:
                l_plan = int(sel.split(" | ")[0].replace("Linha ", ""))
                reg_at = df_admin.iloc[l_plan - 2]
                
                st.subheader("Editando Regra")
                c1, c2 = st.columns(2)
                with c1: e_n = st.text_input("Administradora", value=reg_at['Administradora'])
                with c2: e_p = st.selectbox("Produto", ["Automóvel", "Imóvel", "Moto", "Caminhão", "Serviços"], index=obter_index_produto(reg_at['Produto']))
                
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
                            v = st.number_input(f"Parcela {num_p}", min_value=0.0, step=0.1, value=val_float, key=f"edit_p{num_p}")
                            edit_inputs_p.append(v)
                            
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Salvar Alterações", type="primary"):
                        aba_admin.update_cell(l_plan, 1, e_n.upper())
                        aba_admin.update_cell(l_plan, 2, e_p)
                        for i, v in enumerate(edit_inputs_p):
                            aba_admin.update_cell(l_plan, i+3, f"{v}%" if v > 0 else "")
                        st.success("Regra alterada!")
                        st.rerun()
                with b2:
                    if st.button("🚨 EXCLUIR REGRA"):
                        aba_admin.delete_rows(l_plan)
                        st.error("Regra deletada!")
                        st.rerun()

    # --- ABA DE COMISSÕES INTERNAS ---
    with t4:
        st.subheader("Configurar Repasses (Vendedores e Masters)")
        if not df_com_int.empty:
            st.dataframe(df_com_int.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
        else: st.info("Nenhuma regra interna configurada.")
        
        with st.form("f_com_int"):
            st.write("Criar Nova Regra Interna")
            c_int1, c_int2, c_int3 = st.columns(3)
            with c_int1:
                opcoes_alvo = ["Perfil: Vendedor", "Perfil: Master"] + [u["nome"] for u in USUARIOS.values()]
                alvo = st.selectbox("Usuário ou Perfil Alvo *", list(dict.fromkeys(opcoes_alvo)))
            with c_int2:
                base_calc = st.selectbox("Base de Cálculo *", ["% sobre a Comissão da Corretora", "% sobre o Valor da Venda"])
            with c_int3:
                pct_int = st.number_input("Percentual de Repasse (%) *", min_value=0.0, step=0.1)
                
            if st.form_submit_button("Salvar Regra Interna", type="primary"):
                aba_com_int.append_row([alvo, base_calc, f"{pct_int}%"])
                st.success("Regra salva com sucesso!")
                st.rerun()

        if not df_com_int.empty:
            st.write("---")
            opts_del = df_com_int.apply(lambda x: f"Linha {x.name + 2} | {x['Alvo (Usuário/Perfil)']} - {x['Base de Cálculo']} - {x['Percentual (%)']}", axis=1).tolist()
            del_sel = st.selectbox("Selecione a Regra Interna para excluir:", [""] + opts_del)
            if st.button("🚨 Apagar Regra Interna Selecionada"):
                if del_sel:
                    l_del = int(del_sel.split(" | ")[0].replace("Linha ", ""))
                    aba_com_int.delete_rows(l_del)
                    st.success("Regra excluída!")
                    st.rerun()

elif menu_selecionado == "Baixar Parcela":
    st.markdown("## 💰 Baixa de Comissão")
    st.info("A integração de baixa com o sistema de previsão será habilitada na próxima etapa!")
