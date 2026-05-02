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
    if p in ["SERVICO", "SERVICOS"]: return "SERVICO"
    return p

def obter_index_produto(p_str):
    norm = normalizar_produto(p_str)
    mapping = {"AUTO": 0, "IMOVEL": 1, "MOTO": 2, "CAMINHAO": 3, "SERVICO": 4}
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
    except:
        pass
    return pd.DataFrame(columns=["Administradora", "Produto"] + [f"P{i}" for i in range(1, 26)])

# === MOTOR DE CÁLCULO DE COMISSÃO ===
def calcular_comissao_vendedor(df_vendas_global, vendedor_nome, data_venda_dt, cfg):
    if pd.isna(data_venda_dt): return cfg['T1_Pct'], int(cfg['T1_Parc'])
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
    if st.session_state['perfil_logado'] == "Master":
        opcoes_principais = ["Dashboard", "Nova Venda", "Relatórios", "Regras de Comissão", "Baixar Parcela"]
    else:
        opcoes_principais = ["Dashboard", "Nova Venda", "Relatórios"]
    idx_principal = opcoes_principais.index(st.session_state['menu_lateral']) if st.session_state['menu_lateral'] in opcoes_principais else 0
    selecao_principal = st.sidebar.radio(" ", opcoes_principais, index=idx_principal, label_visibility="collapsed")
    if selecao_principal != st.session_state.get('last_radio_selection'):
        st.session_state['menu_lateral'] = selecao_principal
        st.session_state['cliente_visualizado'] = None
        st.session_state['last_radio_selection'] = selecao_principal
        st.rerun()

    with st.sidebar.expander("🛠️ Simuladores"):
        f_log = ["🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
        for sim in f_log:
            if st.button(sim, use_container_width=True):
                st.session_state['menu_lateral'] = sim
                st.rerun()

menu_selecionado = st.session_state['menu_lateral']

if is_logado:
    st.sidebar.write("")
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
if not is_logado:
    if menu_selecionado == "🔐 Login (Área Restrita)":
        st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        col_esq, col_meio, col_dir = st.columns([1, 1.2, 1])
        with col_meio:
            with st.form("form_login"):
                usuario_input = st.text_input("Usuário (Login)").lower()
                senha_input = st.text_input("Senha", type="password")
                
                st.write("") 
                
                # Botão centralizado e com texto simplificado ENTRAR
                c_btn1, c_btn2, c_btn3 = st.columns([1, 1.5, 1])
                with c_btn2:
                    btn_login = st.form_submit_button("ENTRAR", type="primary", use_container_width=True)
                
                if btn_login:
                    if usuario_input in USUARIOS and USUARIOS[usuario_input]["senha"] == senha_input:
                        st.session_state['usuario_logado'] = usuario_input
                        st.session_state['perfil_logado'] = USUARIOS[usuario_input]["perfil"]
                        st.session_state['nome_vendedor'] = USUARIOS[usuario_input]["nome"]
                        st.session_state['menu_lateral'] = "Dashboard" 
                        st.rerun() 
                    else: st.error("❌ Usuário ou senha incorretos.")
    else:
        if "Yamaha" in menu_selecionado: carregar_ferramenta("yamaha.html")
        elif "Itaú" in menu_selecionado: carregar_ferramenta("itau.html")
        elif "Oportunidades" in menu_selecionado: carregar_ferramenta("guia.html")
        elif "Financiamento" in menu_selecionado: carregar_ferramenta("comparador.html")
    st.stop()

# --- Restante do código (Dashboard, Nova Venda, etc) segue a mesma lógica já implementada ---
if menu_selecionado == "Dashboard":
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        
        if st.button("⬅️ Voltar ao Dashboard", type="primary"):
            st.session_state['cliente_visualizado'] = None
            st.rerun()
            
        dados_cli_brutos = aba_clientes.get_all_values()
        df_cli = pd.DataFrame(dados_cli_brutos[1:], columns=dados_cli_brutos[0])
        info_cliente = df_cli[df_cli['Nome'] == cliente_nome].iloc[0].to_dict() if not df_cli[df_cli['Nome'] == cliente_nome].empty else {}

        is_master = st.session_state['perfil_logado'] == "Master"
        
        c1, c2 = st.columns(2)
        with c1:
            nome_ed = st.text_input("Nome Completo", value=info_cliente.get("Nome", cliente_nome), disabled=not is_master)
            tel_ed = st.text_input("Telefone", value=info_cliente.get("Telefone", ""), disabled=not is_master)
        with c2:
            email_ed = st.text_input("E-mail", value=info_cliente.get("Email", ""), disabled=not is_master)
            renda_ed = st.text_input("Renda Mensal", value=info_cliente.get("Renda", ""), disabled=not is_master)
        
        if is_master and st.button("Salvar Alterações Cadastrais"):
            idx = df_cli[df_cli['Nome'] == cliente_nome].index[0] + 2
            aba_clientes.update_cell(idx, 1, nome_ed)
            aba_clientes.update_cell(idx, 2, tel_ed)
            aba_clientes.update_cell(idx, 3, email_ed)
            aba_clientes.update_cell(idx, 7, renda_ed)
            st.success("Dados atualizados!")
            st.rerun()

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        cotas_cliente = df_vendas_global[df_vendas_global['Nome do cliente'] == cliente_nome].copy()
        if not cotas_cliente.empty:
            st.dataframe(cotas_cliente[['DATA', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'VENDEDOR', 'VALOR']], use_container_width=True, hide_index=True)
            
            st.subheader("📈 Previsão de Comissionamento")
            df_admin_regras = carregar_df_admin_seguro(aba_admin)
            previsoes = []
            for _, r in cotas_cliente.iterrows():
                admin_v = normalizar_string(r['ADMINISTRADORA'])
                prod_v = normalizar_produto(r['PRODUTO'])
                regra = df_admin_regras[(df_admin_regras['Admin_Norm'] == admin_v) & (df_admin_regras['Prod_Norm'] == prod_v)]
                
                if not regra.empty:
                    regra = regra.iloc[0]
                    tier_pct, tier_parc = calcular_comissao_vendedor(df_vendas_global, r['VENDEDOR'], r['Data_Real'], cfg)
                    for i in range(1, 26):
                        p_val = parse_float_safe(regra.get(f"P{i}", 0)) / 100
                        if p_val > 0:
                            v_corr = r['Valor_Numerico'] * p_val
                            v_vend, v_breno, v_uriel = 0.0, 0.0, 0.0
                            
                            vendedor = r['VENDEDOR']
                            if vendedor == "BRENO LIMA":
                                v_breno, v_uriel = v_corr * (cfg['Breno_Breno']/100), v_corr * (cfg['Breno_Uriel']/100)
                            elif vendedor == "URIEL GOMES":
                                v_uriel, v_breno = v_corr * (cfg['Uriel_Uriel']/100), v_corr * (cfg['Uriel_Breno']/100)
                            elif vendedor == "Consorbens":
                                v_breno, v_uriel = v_corr * 0.5, v_corr * 0.5
                            else:
                                if i <= tier_parc: v_vend = (r['Valor_Numerico'] * (tier_pct/100)) / tier_parc
                                sobra = v_corr - v_vend
                                v_breno, v_uriel = sobra * 0.5, sobra * 0.5
                            
                            previsoes.append({
                                "Cota": f"{r['GRUPO']}/{r['COTA']}",
                                "Parcela": f"{i}ª",
                                "Data": (r['Data_Real'] + pd.Timedelta(days=7) + pd.DateOffset(months=i-1)).strftime("%d/%m/%Y"),
                                "Corretora": formatar_brl_puro(v_corr),
                                "Vendedor": formatar_brl_puro(v_vend),
                                "Breno": formatar_brl_puro(v_breno),
                                "Uriel": formatar_brl_puro(v_uriel),
                                "Vendedor_Raw": vendedor
                            })
            
            if previsoes:
                df_p = pd.DataFrame(previsoes)
                if not is_master: df_p = df_p[df_p['Vendedor_Raw'] == st.session_state['nome_vendedor']]
                st.dataframe(df_p.drop(columns=['Vendedor_Raw']), use_container_width=True, hide_index=True)

            if is_master:
                with st.expander("⚙️ Gerenciar / Excluir Cota Específica"):
                    cota_sel = st.selectbox("Selecione a cota:", cotas_cliente.apply(lambda x: f"Linha {x.name + 2} | {x['GRUPO']}/{x['COTA']}", axis=1))
                    if cota_sel:
                        ln = int(cota_sel.split(" | ")[0].replace("Linha ", ""))
                        vendedores_list = ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]
                        vendedor_atual = cotas_cliente.loc[ln-2, 'VENDEDOR']
                        novo_vendedor = st.selectbox("Alterar Vendedor Realizador:", vendedores_list, index=vendedores_list.index(vendedor_atual) if vendedor_atual in vendedores_list else 0)
                        
                        col_b1, col_b2 = st.columns(2)
                        if col_b1.button("Atualizar Vendedor", use_container_width=True):
                            aba_vendas.update_cell(ln, 5, novo_vendedor)
                            st.success("Vendedor alterado!")
                            st.rerun()
                        if col_b2.button("🚨 Apagar Cota", use_container_width=True):
                            aba_vendas.delete_rows(ln)
                            st.rerun()
    else:
        if not df_vendas_global.empty:
            df_v = df_vendas_global.copy()
            if st.session_state['perfil_logado'] == "Vendedor": df_v = df_v[df_v['VENDEDOR'] == st.session_state['nome_vendedor']]
            st.dataframe(df_v[['Nome do cliente', 'PRODUTO', 'VENDEDOR', 'VALOR']], on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
            sel = st.context.selection.get("rows", [])
            if sel:
                st.session_state['cliente_visualizado'] = df_v.iloc[sel[0]]['Nome do cliente']
                st.rerun()

# Demais abas (Nova Venda, Regras, etc) permanecem as mesmas
