import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta
import calendar
import requests 
import streamlit.components.v1 as components
import altair as alt
import unicodedata
import os 
import urllib.parse

# Configuração da página
st.set_page_config(page_title="Portal Consorbens", layout="wide", initial_sidebar_state="expanded")

# --- SEGURANÇA DE CAMINHOS DE ARQUIVOS ---
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))

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
if 'tela_cheia_relatorio' not in st.session_state:
    st.session_state['tela_cheia_relatorio'] = False

is_logado = st.session_state['usuario_logado'] is not None
is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

def carregar_ferramenta(nome_arquivo):
    caminho_completo = os.path.join(PASTA_ATUAL, nome_arquivo)
    try:
        with open(caminho_completo, 'r', encoding='utf-8') as f:
            components.html(f.read(), height=900, scrolling=True)
    except FileNotFoundError:
        st.error(f"⚠️ O arquivo {nome_arquivo} não foi encontrado no servidor! Verifique se ele está no GitHub.")

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
    return f"R$ {float(nums)/100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_brl_puro(val):
    if pd.isna(val): return "R$ 0,00"
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
    if p in ["SERVICO", "SERVICOS"]: return "SERVICOS"
    return p

def obter_index_produto(p_str):
    mapping = {"AUTO": 0, "IMOVEL": 1, "MOTO": 2, "CAMINHAO": 3, "SERVICOS": 4}
    return mapping.get(normalizar_produto(p_str), 0)

def parse_float_safe(v):
    if isinstance(v, (int, float)): return float(v)
    try:
        v_str = str(v).replace('%', '').replace('R$', '').strip()
        if not v_str: return 0.0
        if '.' in v_str and ',' in v_str:
            if v_str.rfind(',') > v_str.rfind('.'): v_str = v_str.replace('.', '').replace(',', '.')
            else: v_str = v_str.replace(',', '')
        elif ',' in v_str: v_str = v_str.replace(',', '.')
        return float(v_str)
    except: return 0.0

def limpar_str_nan(val):
    s = str(val).strip()
    if s.lower() in ['nan', 'none', '<na>', 'nat']: return ""
    return s[:-2] if s.endswith('.0') else s

def mascara_tel_nv(): st.session_state['tel_nv'] = formatar_telefone(st.session_state.get('tel_nv', ''))
def mascara_aniv_nv(): st.session_state['aniv_nv'] = formatar_data(st.session_state.get('aniv_nv', ''))
def mascara_renda_nv(): st.session_state['renda_nv'] = formatar_moeda(st.session_state.get('renda_nv', ''))

# === MOTORES DE CÁLCULO DE COMISSÃO ===
def calcular_comissao_vendedor(df_vendas_global, vendedor_nome, data_venda_dt, cfg):
    if pd.isna(data_venda_dt): return cfg.get('T1_Pct', 1.0), int(cfg.get('T1_Parc', 4))
    mes, ano = data_venda_dt.month, data_venda_dt.year
    df_mes = df_vendas_global[(df_vendas_global['VENDEDOR'] == vendedor_nome) & (df_vendas_global['Data_Real'].dt.month == mes) & (df_vendas_global['Data_Real'].dt.year == ano)]
    vol_total = df_mes['Valor_Numerico'].sum()
    if vol_total <= cfg.get('T1_Max', 500000): return cfg.get('T1_Pct', 1.0), int(cfg.get('T1_Parc', 4))
    elif vol_total <= cfg.get('T2_Max', 1500000): return cfg.get('T2_Pct', 1.5), int(cfg.get('T2_Parc', 5))
    else: return cfg.get('T3_Pct', 2.0), int(cfg.get('T3_Parc', 5))

def gerar_tabela_parcelas(df_alvo, df_global, df_regras, cfg, status_dict):
    hoje = pd.Timestamp.today().normalize()
    parcelas_finais, vendas_sem_data = [], []
    for idx, r in df_alvo.iterrows():
        data_venda = r['Data_Real']
        cliente, grupo, cota = r.get('Nome do cliente', 'Desconhecido'), r.get('GRUPO', ''), r.get('COTA', '')
        if pd.isna(data_venda):
            vendas_sem_data.append(f"{cliente} (Gr: {grupo}/Cota: {cota})")
            continue 
            
        admin, prod, vendedor, val_venda = r['ADMINISTRADORA'], r['PRODUTO'], r['VENDEDOR'], r['Valor_Numerico']
        admin_norm, prod_norm = normalizar_string(admin), normalizar_produto(prod)
        status_cota = r.get('STATUS', 'Em Andamento')
        if status_cota in ["Vendido", ""]: status_cota = "Em Andamento"
        
        regra = df_regras[(df_regras['Admin_Norm'] == admin_norm) & (df_regras['Prod_Norm'] == prod_norm)]
        if regra.empty: continue
        regra = regra.iloc[0]
        
        tier_pct, tier_parc = calcular_comissao_vendedor(df_global, vendedor, data_venda, cfg)
        temp_parcels = []
        for i in range(1, 26):
            p_val = parse_float_safe(regra.get(f"P{i}", 0)) / 100.0
            if p_val <= 0: continue
            
            comissao_bruta = val_venda * p_val
            imposto_val = comissao_bruta * (parse_float_safe(cfg.get('Imposto', 7.16)) / 100.0)
            corretora_liq = comissao_bruta - imposto_val
            vend_rec = breno_rec = uriel_rec = 0.0
            
            if vendedor == "BRENO LIMA":
                breno_rec, uriel_rec = corretora_liq * (parse_float_safe(cfg.get('Breno_Breno', 70))/100.0), corretora_liq * (parse_float_safe(cfg.get('Breno_Uriel', 30))/100.0)
            elif vendedor == "URIEL GOMES":
                uriel_rec, breno_rec = corretora_liq * (parse_float_safe(cfg.get('Uriel_Uriel', 70))/100.0), corretora_liq * (parse_float_safe(cfg.get('Uriel_Breno', 30))/100.0)
            elif vendedor == "Consorbens":
                breno_rec, uriel_rec = corretora_liq * (parse_float_safe(cfg.get('Cons_Breno', 50))/100.0), corretora_liq * (parse_float_safe(cfg.get('Cons_Uriel', 50))/100.0)
            else:
                if i <= tier_parc: vend_rec = val_venda * (tier_pct/100.0) / tier_parc
                sobra = corretora_liq - vend_rec
                breno_rec, uriel_rec = sobra * 0.50, sobra * 0.50

            data_pagamento = data_venda + pd.Timedelta(days=7) + pd.DateOffset(months=i-1)
            temp_parcels.append({'parcela': i, 'data_pagamento': data_pagamento, 'bruto': comissao_bruta, 'liquido': corretora_liq, 'vend': vend_rec, 'breno': breno_rec, 'uriel': uriel_rec})
            
        if status_cota == 'Cancelada': temp_parcels = [p for p in temp_parcels if p['data_pagamento'] <= hoje]
        elif status_cota == 'Contemplada':
            past = [p for p in temp_parcels if p['data_pagamento'] <= hoje]
            future = [p for p in temp_parcels if p['data_pagamento'] > hoje]
            if future: past.append({'parcela': 'Antecipação', 'data_pagamento': hoje, 'bruto': sum(p['bruto'] for p in future), 'liquido': sum(p['liquido'] for p in future), 'vend': sum(p['vend'] for p in future), 'breno': sum(p['breno'] for p in future), 'uriel': sum(p['uriel'] for p in future)})
            temp_parcels = past
            
        for p in temp_parcels:
            chave_unica = f"{cliente}_{grupo}_{cota}_{admin}_{p['parcela']}"
            data_str = "⚠️ Travada (Atraso)" if status_cota == 'Em Atraso' else p['data_pagamento'].strftime("%d/%m/%Y")
            nome_parc = f"{p['parcela']}ª Parcela" if isinstance(p['parcela'], int) else "Antecip. (Contemplada)"
            
            parcelas_finais.append({
                "Chave": chave_unica, "Cliente": cliente, "Produto": prod, "Vendedor": vendedor, "Grupo": grupo, "Cota": cota,
                "Valor da Venda": val_venda, "Parcela": nome_parc, "data_pagamento_dt": p['data_pagamento'], "Comissão (Bruta)": p['bruto'],
                "Comissão (s/ Imposto)": p['liquido'], "Breno": p['breno'], "Uriel": p['uriel'], "Vendedor Recebe": p['vend'],
                "Status": status_dict.get(chave_unica, "Pendente"), "Data Prevista": data_str
            })
    return pd.DataFrame(parcelas_finais), vendas_sem_data

# ==========================================
# 4. CONEXÃO E CARREGAMENTO - SUPABASE
# ==========================================
@st.cache_resource
def iniciar_conexao() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

try:
    supabase = iniciar_conexao()

    def carregar_tabela(nome_tabela):
        try:
            return pd.DataFrame(supabase.table(nome_tabela).select("*").execute().data)
        except:
            return pd.DataFrame() # Tabela pode não existir ainda

    df_vendas_bd = carregar_tabela("vendas")
    if not df_vendas_bd.empty:
        df_vendas_global = df_vendas_bd.copy()
        df_vendas_global.rename(columns={"NOME": "Nome do cliente"}, inplace=True)
        df_vendas_global['Data_Real'] = pd.to_datetime(df_vendas_global['DATA'], dayfirst=True, errors='coerce')
        df_vendas_global['Valor_Numerico'] = df_vendas_global['VALOR'].apply(parse_float_safe)
        df_vendas_global['GRUPO'] = df_vendas_global['GRUPO'].apply(limpar_str_nan)
        df_vendas_global['COTA'] = df_vendas_global['COTA'].apply(limpar_str_nan)
    else:
        df_vendas_global = pd.DataFrame()

    df_cli = carregar_tabela("clientes")
    
    # Carregar Assembleias
    df_ass = carregar_tabela("assembleias")
    if not df_ass.empty:
        df_ass['data_dt'] = pd.to_datetime(df_ass['data_evento'], format="%d/%m/%Y", errors='coerce')
    
    df_admin_cad = carregar_tabela("cad_administradoras")
    lista_admin_bd = df_admin_cad['Administradora'].tolist() if not df_admin_cad.empty else ["Nenhuma administradora cadastrada"]

    df_admin = carregar_tabela("administradoras")
    if not df_admin.empty:
        df_admin['Admin_Norm'] = df_admin['Administradora'].apply(normalizar_string)
        df_admin['Prod_Norm'] = df_admin['Produto'].apply(normalizar_produto)

    df_status = carregar_tabela("status_comissoes")
    status_dict = dict(zip(df_status['Chave_Unica'], df_status['Status'])) if not df_status.empty else {}

    cfg_padrao = {"Breno_Breno": 70.0, "Breno_Uriel": 30.0, "Uriel_Uriel": 70.0, "Uriel_Breno": 30.0, "Cons_Breno": 50.0, "Cons_Uriel": 50.0, "T1_Max": 500000.0, "T1_Pct": 1.0, "T1_Parc": 4, "T2_Max": 1500000.0, "T2_Pct": 1.5, "T2_Parc": 5, "T3_Pct": 2.0, "T3_Parc": 5, "Imposto": 7.16}
    df_cfg = carregar_tabela("config_interna")
    cfg_id = None
    if not df_cfg.empty:
        cfg = df_cfg.iloc[0].to_dict()
        cfg_id = cfg.get('id')
    else:
        res = supabase.table("config_interna").insert(cfg_padrao).execute()
        cfg = cfg_padrao
        cfg_id = res.data[0]['id'] if res.data else None

except Exception as e:
    st.error(f"⚠️ Erro ao conectar com o Supabase. Verifique se as tabelas existem. Detalhes: {e}")
    st.stop()

def salvar_status_comissoes(df_editado, df_original):
    mudancas = df_editado[df_editado['Status'] != df_original['Status']]
    if not mudancas.empty:
        for _, row in mudancas.iterrows():
            chave, novo_status = row['Chave'], row['Status']
            existe = supabase.table("status_comissoes").select("id").eq("Chave_Unica", chave).execute()
            if existe.data: supabase.table("status_comissoes").update({"Status": novo_status}).eq("id", existe.data[0]['id']).execute()
            else: supabase.table("status_comissoes").insert({"Chave_Unica": chave, "Status": novo_status}).execute()
        return True
    return False

# === LÓGICA DE TELA CHEIA (RELATÓRIO DE COMISSÃO) ===
if st.session_state['tela_cheia_relatorio']:
    st.markdown("## 💰 Relatório de Comissionamento Detalhado")
    col_bt, col_chk = st.columns([1, 3])
    with col_bt:
        if st.button("⬅️ Voltar aos Filtros", type="secondary"):
            st.session_state['tela_cheia_relatorio'] = False
            st.rerun()
    with col_chk: mostrar_pagos = st.checkbox("Mostrar parcelas já pagas (PAGO)", value=False)
        
    df_parcelas_todas, vendas_sem_data = gerar_tabela_parcelas(df_vendas_global, df_vendas_global, df_admin, cfg, status_dict)
    if vendas_sem_data: st.warning(f"⚠️ **Atenção:** Vendas sem data preenchida: **{', '.join(vendas_sem_data)}**.")

    if not df_parcelas_todas.empty:
        hoje = pd.Timestamp.today().normalize()
        df_view = df_parcelas_todas[df_parcelas_todas['data_pagamento_dt'].notna()].copy()
        if st.session_state['perfil_logado'] == "Vendedor" and not is_master: df_view = df_view[df_view['Vendedor'] == st.session_state['nome_vendedor']]
        
        ft_rel = st.session_state.get('rel_periodo', 'Todas as Vendas')
        if ft_rel == "Mês Atual": df_view = df_view[(df_view['data_pagamento_dt'].dt.month == hoje.month) & (df_view['data_pagamento_dt'].dt.year == hoje.year)]
        elif ft_rel == "Quinzena Atual":
            q_ini, q_fim = (hoje.replace(day=1), hoje.replace(day=15)) if hoje.day <= 15 else (hoje.replace(day=16), hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1]))
            df_view = df_view[(df_view['data_pagamento_dt'].dt.date >= q_ini.date()) & (df_view['data_pagamento_dt'].dt.date <= q_fim.date())]
        elif ft_rel == "Mês Anterior":
            ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
            df_view = df_view[(df_view['data_pagamento_dt'].dt.month == ma) & (df_view['data_pagamento_dt'].dt.year == aa)]
        elif ft_rel == "Ano Atual": df_view = df_view[df_view['data_pagamento_dt'].dt.year == hoje.year]
        elif ft_rel == "Período Personalizado": df_view = df_view[(df_view['data_pagamento_dt'].dt.date >= st.session_state['rel_dt_ini']) & (df_view['data_pagamento_dt'].dt.date <= st.session_state['rel_dt_fim'])]
            
        if not mostrar_pagos: df_view = df_view[df_view['Status'] != 'PAGO']
            
        if not df_view.empty:
            df_view = df_view[['Chave', 'Cliente', 'Produto', 'Vendedor', 'Grupo', 'Cota', 'Valor da Venda', 'Parcela', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe', 'Status', 'Data Prevista']]
            total_breno, total_uriel, total_vend = df_view['Breno'].sum(), df_view['Uriel'].sum(), df_view['Vendedor Recebe'].sum()
            for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']: df_view[col] = df_view[col].apply(formatar_brl_puro)
            
            df_final = df_view.drop(columns=[] if is_master else ["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"]).reset_index(drop=True)
            edited_df = st.data_editor(
                df_final, disabled=[c for c in df_final.columns if c != "Status"],
                column_config={"Chave": None, "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True)},
                use_container_width=True, hide_index=True, key="editor_relatorio_full"
            )
            if is_master and st.button("💾 Salvar Status de Pagamento", type="primary"):
                if salvar_status_comissoes(edited_df, df_final): st.success("Status atualizados!"); st.rerun()
            st.divider()
            mt1, mt2, mt3 = st.columns(3)
            mt1.metric("Breno (Sócios)", formatar_brl_puro(total_breno))
            mt2.metric("Uriel (Sócios)", formatar_brl_puro(total_uriel))
            mt3.metric("Vendedores", formatar_brl_puro(total_vend))
        else: st.success("Nenhuma comissão pendente!")
    else: st.info("Sem vendas cadastradas.")
    st.stop() 

# === CSS CUSTOMIZADO ===
css = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
    [data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 2px solid #e2e8f0 !important; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div { color: #0f172a !important; }
    [data-testid="stSidebar"] hr { border-bottom-color: #e2e8f0 !important; margin-top: 0.5rem !important; margin-bottom: 0.5rem !important; }
    [data-testid="stSidebar"] button { border: 1px solid #cbd5e1 !important; background-color: #f8fafc !important; }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    button[data-baseweb="tab"] { font-size: 16px !important; font-weight: bold !important; }
    button[kind="primary"] { background-color: #239b56 !important; border-color: #239b56 !important; color: #ffffff !important; font-weight: bold !important; }
    button[kind="primary"]:hover { background-color: #1b7a43 !important; border-color: #1b7a43 !important; color: #ffffff !important; transform: scale(1.02); transition: all 0.2s; }
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    h3 { margin-bottom: 0.5rem !important; margin-top: 0.5rem !important; }
    
    /* Calendário Customizado Menor */
    .cal-table { width: 100%; border-collapse: collapse; text-align: center; font-family: sans-serif; background-color: white; border-radius: 6px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.05); font-size: 14px; }
    .cal-table th { background-color: #f8fafc; padding: 8px; font-weight: bold; color: #475569; border-bottom: 1px solid #e2e8f0; }
    .cal-table td { padding: 8px; border: 1px solid #e2e8f0; color: #334155; }
    .cal-day { border-radius: 50%; display: inline-block; width: 28px; height: 28px; line-height: 28px; }
    .cal-event { background-color: #e74c3c; color: white; font-weight: bold; box-shadow: 0 2px 4px rgba(231, 76, 60, 0.4); }
    .cal-empty { background-color: #f8fafc; }
    .event-desc { font-size: 14px; margin-bottom: 4px; border-left: 3px solid #e74c3c; padding-left: 8px; background: #fdf2f2; padding: 4px; border-radius: 0 4px 4px 0; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# === ROTEADOR DE MENU LATERAL ===
simuladores_dict = {"🏍️ Simulador Yamaha": "yamaha.html", "🏦 Simulador Itaú": "itau.html", "🎯 Oportunidades Itaú": "guia.html", "⚖️ Financiamento x Consórcio": "comparador.html"}

logo_path = os.path.join(PASTA_ATUAL, "logo.png")
if os.path.exists(logo_path): st.sidebar.image(logo_path, use_container_width=True)
st.sidebar.markdown("<br>", unsafe_allow_html=True) 

if not is_logado:
    opcoes_menu = ["🔐 Login (Área Restrita)"] + list(simuladores_dict.keys())
    selecao = st.sidebar.radio(" ", opcoes_menu, index=opcoes_menu.index(st.session_state['menu_lateral']) if st.session_state['menu_lateral'] in opcoes_menu else 0, label_visibility="collapsed")
    if selecao != st.session_state['menu_lateral']: st.session_state['menu_lateral'] = selecao; st.rerun()
else:
    st.sidebar.divider() 
    opcoes_principais = ["Dashboard", "Nova Venda", "Assembleias", "Relatórios", "Baixar Parcelas", "Configurações de Sistema"] if is_master else ["Dashboard", "Nova Venda", "Assembleias", "Relatórios"]
    selecao_principal = st.sidebar.radio(" ", opcoes_principais, index=opcoes_principais.index(st.session_state['menu_lateral']) if st.session_state['menu_lateral'] in opcoes_principais else None, label_visibility="collapsed")
    if selecao_principal and selecao_principal != st.session_state.get('last_radio_selection'):
        st.session_state['menu_lateral'] = selecao_principal
        st.session_state['cliente_visualizado'] = None
        st.session_state['last_radio_selection'] = selecao_principal
        st.rerun()
    st.sidebar.write("")
    with st.sidebar.expander("🛠️ Simuladores", expanded=(st.session_state['menu_lateral'] in simuladores_dict)):
        for sim in simuladores_dict.keys():
            if st.button(sim, use_container_width=True, type="primary" if st.session_state['menu_lateral'] == sim else "secondary"):
                st.session_state['menu_lateral'] = sim; st.session_state['cliente_visualizado'] = None; st.rerun()
    st.sidebar.write("")
    if st.sidebar.button("Sair do Sistema"): st.session_state.clear(); st.rerun()

menu_selecionado = st.session_state['menu_lateral']
if menu_selecionado in simuladores_dict: carregar_ferramenta(simuladores_dict[menu_selecionado]); st.stop() 

# === LOGIN ===
if not is_logado:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    _, col_meio, _ = st.columns([1, 1.2, 1])
    with col_meio:
        with st.form("form_login"):
            usuario_input, senha_input = st.text_input("Usuário (Login)").lower(), st.text_input("Senha", type="password")
            _, c_btn2, _ = st.columns([1, 1.5, 1])
            with c_btn2:
                if st.form_submit_button("ENTRAR", type="primary", use_container_width=True):
                    if usuario_input in USUARIOS and USUARIOS[usuario_input]["senha"] == senha_input:
                        st.session_state.update({'usuario_logado': usuario_input, 'perfil_logado': USUARIOS[usuario_input]["perfil"], 'nome_vendedor': USUARIOS[usuario_input]["nome"], 'menu_lateral': "Dashboard"})
                        st.rerun() 
                    else: st.error("❌ Usuário ou senha incorretos.")
    st.stop() 

# === DASHBOARD ===
if menu_selecionado == "Dashboard":
    
    # LÓGICA DE LEMBRETE DE ASSEMBLEIAS
    hoje = datetime.today().date()
    limite = hoje + timedelta(days=3)
    eventos_proximos = []
    
    if not df_ass.empty:
        df_futuro = df_ass[(df_ass['data_dt'].dt.date >= hoje) & (df_ass['data_dt'].dt.date <= limite)]
        for _, r in df_futuro.iterrows():
            d_fmt = r['data_dt'].strftime("%d/%m")
            eventos_proximos.append(f"**{r['descricao']}** ({d_fmt})")
            
    if eventos_proximos:
        st.warning(f"📅 **Atenção para as Assembleias nos próximos dias:** {' | '.join(eventos_proximos)}")

    # GESTÃO DO CLIENTE
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        st.markdown(f"### {cliente_nome}")
        if st.button("⬅️ Voltar ao Dashboard", type="primary"): st.session_state['cliente_visualizado'] = None; st.rerun()
            
        info_cliente, id_cliente_db = {}, None
        if not df_cli.empty and 'Nome' in df_cli.columns:
            busca_cli = df_cli[df_cli['Nome'] == cliente_nome]
            if not busca_cli.empty: info_cliente, id_cliente_db = busca_cli.iloc[0].to_dict(), busca_cli.iloc[0].get('id')

        if not is_master: st.info("🔒 Como Vendedor, você só pode visualizar estes dados.")
        def safe_str(val, default=""): return default if pd.isna(val) or val is None or str(val).strip().lower() in ["nan", "nat", "none"] else str(val)

        key_nome, key_tel, key_email, key_end, key_aniv, key_prof, key_renda = f"n_{cliente_nome}", f"t_{cliente_nome}", f"e_{cliente_nome}", f"en_{cliente_nome}", f"a_{cliente_nome}", f"p_{cliente_nome}", f"r_{cliente_nome}"

        if key_nome not in st.session_state: st.session_state[key_nome] = safe_str(info_cliente.get("Nome"), cliente_nome)
        if key_tel not in st.session_state: st.session_state[key_tel] = safe_str(info_cliente.get("Telefone"))
        if key_email not in st.session_state: st.session_state[key_email] = safe_str(info_cliente.get("Email"))
        if key_end not in st.session_state: st.session_state[key_end] = safe_str(info_cliente.get("Endereco"))
        if key_aniv not in st.session_state: st.session_state[key_aniv] = safe_str(info_cliente.get("Aniversario"))
        if key_prof not in st.session_state: st.session_state[key_prof] = safe_str(info_cliente.get("Profissao"))
        if key_renda not in st.session_state: st.session_state[key_renda] = safe_str(info_cliente.get("Renda"))
            
        def m_tel_ed(): st.session_state[key_tel] = formatar_telefone(st.session_state.get(key_tel, ''))
        def m_aniv_ed(): st.session_state[key_aniv] = formatar_data(st.session_state.get(key_aniv, ''))
        def m_renda_ed(): st.session_state[key_renda] = formatar_moeda(st.session_state.get(key_renda, ''))

        nome_edit = st.text_input("Nome Completo", key=key_nome, disabled=not is_master)
        
        if is_master:
            c_cep1, c_cep2 = st.columns([1, 3])
            with c_cep1: cep_busca = st.text_input("Buscar CEP", key=f"cep_{cliente_nome}", max_chars=9)
            if cep_busca and cep_busca != st.session_state.get(f'last_cep_{cliente_nome}', ''):
                cep_limpo = ''.join(filter(str.isdigit, cep_busca))
                if len(cep_limpo) == 8:
                    try:
                        res = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
                        if res.status_code == 200 and "erro" not in res.json():
                            d_cep = res.json()
                            st.session_state[key_end] = f"{d_cep.get('logradouro','')}, Nº , {d_cep.get('bairro','')}, {d_cep.get('localidade','')}-{d_cep.get('uf','')} (CEP: {cep_busca})"
                            st.rerun()
                    except: pass
                st.session_state[f'last_cep_{cliente_nome}'] = cep_busca
        
        c1, c2 = st.columns(2)
        with c1:
            endereco = st.text_input("Endereço Completo", key=key_end, disabled=not is_master)
            telefone_edit = st.text_input("Telefone", key=key_tel, on_change=m_tel_ed, disabled=not is_master)
            profissao_edit = st.text_input("Profissão", key=key_prof, disabled=not is_master)
        with c2:
            email = st.text_input("Email", key=key_email, disabled=not is_master)
            aniversario_edit = st.text_input("Aniversário (DD/MM/AAAA)", key=key_aniv, on_change=m_aniv_ed, disabled=not is_master)
            renda_edit = st.text_input("Renda Mensal", key=key_renda, on_change=m_renda_ed, disabled=not is_master)
        
        if is_master:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Salvar Alterações Cadastrais", type="primary", use_container_width=True):
                    dados_cli = {"Nome": st.session_state[key_nome], "Telefone": st.session_state[key_tel], "Email": st.session_state[key_email], "Endereco": st.session_state[key_end], "Aniversario": st.session_state[key_aniv], "Profissao": st.session_state[key_prof], "Renda": st.session_state[key_renda]}
                    try:
                        if id_cliente_db: supabase.table("clientes").update(dados_cli).eq("id", int(id_cliente_db)).execute()
                        else:
                            dados_cli["Data_Cadastro"] = datetime.today().strftime("%d/%m/%Y")
                            supabase.table("clientes").insert([dados_cli]).execute()
                        if st.session_state[key_nome] != cliente_nome:
                            supabase.table("vendas").update({"NOME": st.session_state[key_nome]}).eq("NOME", cliente_nome).execute()
                            st.session_state['cliente_visualizado'] = st.session_state[key_nome]
                        st.success("Salvo com sucesso!"); st.rerun()
                    except Exception as e: st.error(f"Erro ao salvar: {e}")
            with col_b2:
                if st.button("🚨 Excluir Cliente (Apagar Todas as Cotas)", use_container_width=True):
                    if id_cliente_db: supabase.table("clientes").delete().eq("id", int(id_cliente_db)).execute()
                    supabase.table("vendas").delete().eq("NOME", cliente_nome).execute()
                    st.session_state['cliente_visualizado'] = None; st.rerun()

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        if not df_vendas_global.empty:
            cotas_cliente = df_vendas_global[df_vendas_global['Nome do cliente'] == cliente_nome].copy()
            if not cotas_cliente.empty:
                i1, i2 = st.columns(2)
                i1.metric("Cotas", len(cotas_cliente))
                i2.metric("Volume Investido", formatar_brl_puro(cotas_cliente['Valor_Numerico'].sum()))
                cotas_cliente['Valor Formatado'] = cotas_cliente['Valor_Numerico'].apply(formatar_brl_puro)
                st.dataframe(cotas_cliente[['DATA', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'Valor Formatado', 'STATUS', 'VENDEDOR']].rename(columns={'DATA': 'Data da Venda', 'Valor Formatado': 'Valor (R$)'}), use_container_width=True, hide_index=True)
                
                with st.expander("⚙️ Gerenciar Cota", expanded=False):
                    cota_selecionada = st.selectbox("Selecione a cota:", [""] + cotas_cliente.apply(lambda r: f"ID:{r['id']} | G: {r['GRUPO']} / C: {r['COTA']} - Val: {r['Valor Formatado']}", axis=1).tolist())
                    if cota_selecionada:
                        id_cota = int(cota_selecionada.split(" | ")[0].replace("ID:", ""))
                        c_info = cotas_cliente[cotas_cliente['id'] == id_cota].iloc[0]
                        st_atu = c_info['STATUS'] if c_info['STATUS'] in ["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"] else "Em Andamento"
                        try: dt_obj = datetime.strptime(str(c_info['DATA']), "%d/%m/%Y").date()
                        except: dt_obj = datetime.today().date()
                        
                        c_ed1, c_ed2, c_ed3 = st.columns(3)
                        with c_ed1: n_st = st.selectbox("Status", ["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"], index=["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"].index(st_atu), key=f"s_{id_cota}")
                        with c_ed2: n_vd = st.selectbox("Vendedor", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"], index=["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"].index(c_info['VENDEDOR']) if c_info['VENDEDOR'] in ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"] else 0) if is_master else st.text_input("Vend", value=c_info['VENDEDOR'], disabled=True)
                        with c_ed3: n_dt = st.date_input("Data", value=dt_obj) if is_master else st.text_input("Data", value=c_info['DATA'], disabled=True)

                        c_ed4, c_ed5 = st.columns(2)
                        with c_ed4: n_gp = st.text_input("Grupo", value=c_info['GRUPO'], disabled=not is_master)
                        with c_ed5: n_ct = st.text_input("Cota", value=c_info['COTA'], disabled=not is_master)
                                
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("💾 Salvar Cota", type="primary", use_container_width=True):
                                supabase.table("vendas").update({"VENDEDOR": n_vd, "STATUS": n_st, "DATA": n_dt.strftime("%d/%m/%Y") if not isinstance(n_dt, str) else n_dt, "GRUPO": n_gp, "COTA": n_ct}).eq("id", id_cota).execute()
                                st.success("Atualizada!"); st.rerun()
                        with b2:
                            if is_master and st.button("🚨 Apagar Cota", use_container_width=True):
                                supabase.table("vendas").delete().eq("id", id_cota).execute()
                                st.success("Apagada!"); st.rerun()

                st.subheader("📈 Previsão de Comissionamento")
                df_parcelas, v_sem_data = gerar_tabela_parcelas(cotas_cliente, df_vendas_global, df_admin, cfg, status_dict)
                if v_sem_data: st.warning(f"Vendas sem data: {', '.join(v_sem_data)}")
                if not df_parcelas.empty:
                    df_view_cli = df_parcelas[df_parcelas['Vendedor Recebe'] > 0].copy() if not is_master else df_parcelas.copy()
                    if not df_view_cli.empty:
                        for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']: df_view_cli[col] = df_view_cli[col].apply(formatar_brl_puro)
                        c_conf = {"Chave": None, "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True)}
                        c_hide = ['Cliente', 'Produto', 'Vendedor', 'data_pagamento_dt'] + (["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"] if not is_master else [])
                        df_fc = df_view_cli.drop(columns=c_hide).reset_index(drop=True)
                        ed_cli = st.data_editor(df_fc, disabled=[c for c in df_fc.columns if c != "Status"], column_config=c_conf, use_container_width=True, hide_index=True, key="ed_cli")
                        if is_master and st.button("💾 Salvar Status", type="primary"):
                            if salvar_status_comissoes(ed_cli, df_fc): st.success("Atualizados!"); st.rerun()
                else: st.info("Aguardando configurações de regras.")
            else: st.warning("Nenhuma cota.")
    else:
        df_view = df_vendas_global.copy()
        if not is_master: df_view = df_view[df_view['VENDEDOR'] == st.session_state['nome_vendedor']]
        c_f1, c_f2, c_f3, c_f4 = st.columns([1.5, 1.5, 1, 1])
        with c_f1: ft_cli = st.selectbox("⏳ Filtro:", ["Últimos 5 Cadastros", "Todos", "Mês Atual", "Mês Anterior", "Ano Atual"])
        with c_f2: b_nome = st.text_input("🔍 Nome:")
        with c_f3: b_grupo = st.text_input("📦 Grupo:")
        with c_f4: b_cota = st.text_input("🔢 Cota:")

        hoje = datetime.today()
        df_view = df_view.sort_values(by="Data_Real", ascending=False)
        if ft_cli == "Últimos 5 Cadastros" and not (b_nome or b_grupo or b_cota): df_view = df_view.head(5)
        elif ft_cli != "Todos":
            mask = df_view['Data_Real'].notna()
            if ft_cli == "Mês Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.month == hoje.month) & (df_view['Data_Real'].dt.year == hoje.year)]
            elif ft_cli == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_view = df_view[mask & (df_view['Data_Real'].dt.month == ma) & (df_view['Data_Real'].dt.year == aa)]
            elif ft_cli == "Ano Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.year == hoje.year)]

        if b_nome: df_view = df_view[df_view['Nome do cliente'].str.contains(b_nome, case=False, na=False)]
        if b_grupo: df_view = df_view[df_view['GRUPO'].str.contains(b_grupo, case=False, na=False)]
        if b_cota: df_view = df_view[df_view['COTA'].str.contains(b_cota, case=False, na=False)]

        if not df_view.empty:
            df_tab = df_view.copy()
            df_tab['G/C'] = df_tab.apply(lambda x: f"{x['GRUPO']}/{x['COTA']}", axis=1)
            df_tab['Val'] = df_tab['Valor_Numerico'].apply(formatar_brl_puro)
            df_tab = df_tab[['Nome do cliente', 'PRODUTO', 'ADMINISTRADORA', 'G/C', 'VENDEDOR', 'Val', 'DATA']]
            tab = st.dataframe(df_tab, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
            if hasattr(tab, 'selection') and tab.selection.rows:
                st.session_state['cliente_visualizado'] = df_tab.iloc[tab.selection.rows[0]]['Nome do cliente']; st.rerun()
            m1, m2 = st.columns(2)
            m1.metric("Volume", formatar_brl_puro(df_view['Valor_Numerico'].sum()))
            m2.metric("Qtd", len(df_view))
        else: st.info("Sem vendas.")

# --- ASSEMBLEIAS ---
elif menu_selecionado == "Assembleias":
    st.markdown("### 📅 Cronograma de Assembleias")
    
    col_m, col_a, col_btn = st.columns([1, 1, 3])
    meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    hoje = datetime.today()
    
    with col_m: m_sel = st.selectbox("Mês", meses_pt, index=hoje.month - 1)
    with col_a: a_sel = st.selectbox("Ano", range(hoje.year - 1, hoje.year + 3), index=1)
    
    num_m = meses_pt.index(m_sel) + 1
    
    # Prepara eventos do mes
    eventos_mes = {}
    if not df_ass.empty:
        df_mes_atual = df_ass[(df_ass['data_dt'].dt.month == num_m) & (df_ass['data_dt'].dt.year == a_sel)]
        for _, r in df_mes_atual.iterrows():
            dia = r['data_dt'].day
            if dia not in eventos_mes: eventos_mes[dia] = []
            eventos_mes[dia].append(r['descricao'])

    with col_btn:
        st.write("")
        amanha = (hoje + timedelta(days=1)).date()
        ev_amanha = []
        if not df_ass.empty:
            df_am = df_ass[df_ass['data_dt'].dt.date == amanha]
            ev_amanha = df_am['descricao'].tolist()
            
        if ev_amanha:
            msg = f"Olá Sócios! Segue lembrete das assembleias de amanhã ({amanha.strftime('%d/%m')}): " + ", ".join(ev_amanha)
            st.link_button("📲 Enviar Lembrete WhatsApp (Amanhã)", f"https://wa.me/5531999999999?text={urllib.parse.quote(msg)}", type="primary")
        else:
            st.caption(f"Sem assembleias marcadas para amanhã ({amanha.strftime('%d/%m')}).")

    st.divider()
    
    cal_matriz = calendar.monthcalendar(a_sel, num_m)
    cal_col, list_col = st.columns([1.2, 1])
    
    with cal_col:
        html_cal = "<table class='cal-table'><tr><th>Seg</th><th>Ter</th><th>Qua</th><th>Qui</th><th>Sex</th><th>Sáb</th><th>Dom</th></tr>"
        for sem in cal_matriz:
            html_cal += "<tr>"
            for d in sem:
                if d == 0: html_cal += "<td class='cal-empty'></td>"
                else:
                    classe = "cal-day cal-event" if d in eventos_mes else "cal-day"
                    html_cal += f"<td><span class='{classe}'>{d}</span></td>"
            html_cal += "</tr>"
        st.markdown(html_cal + "</table>", unsafe_allow_html=True)
        
    with list_col:
        if not eventos_mes:
            st.info("Nenhuma assembleia cadastrada neste mês.")
        else:
            for d in sorted(eventos_mes.keys()):
                st.markdown(f"<div class='event-desc'><b>Dia {d:02d}:</b> {', '.join(eventos_mes[d])}</div>", unsafe_allow_html=True)

    if is_master:
        st.divider()
        st.markdown("#### ⚙️ Gerenciar Assembleias")
        c_add, c_del = st.columns(2)
        with c_add:
            with st.form("add_ass"):
                dt_ass = st.date_input("Data da Assembleia", format="DD/MM/YYYY")
                desc_ass = st.text_input("Descrição (Ex: Assembleia Auto Itaú)")
                if st.form_submit_button("Cadastrar Nova"):
                    if desc_ass:
                        supabase.table("assembleias").insert({"data_evento": dt_ass.strftime("%d/%m/%Y"), "descricao": desc_ass}).execute()
                        st.success("Salvo!"); st.rerun()
                    else: st.warning("Preencha a descrição.")
        with c_del:
            if not df_ass.empty:
                opts_del = df_ass.apply(lambda x: f"ID:{x['id']} | {x['data_evento']} - {x['descricao']}", axis=1).tolist()
                sel_del = st.selectbox("Selecione para Apagar:", [""] + opts_del)
                if st.button("🚨 Apagar Assembleia Selecionada", use_container_width=True) and sel_del:
                    id_del = int(sel_del.split(" | ")[0].replace("ID:", ""))
                    supabase.table("assembleias").delete().eq("id", id_del).execute()
                    st.rerun()

# --- NOVA VENDA ---
elif menu_selecionado == "Nova Venda":
    st.markdown("### 📝 Cadastrar Nova Venda")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        cliente = st.text_input("Nome do Cliente *", key="v_cli")
        telefone = st.text_input("Telefone", key="v_tel", on_change=lambda: st.session_state.update({'v_tel': formatar_telefone(st.session_state['v_tel'])}), placeholder="(31) 99999-9999", max_chars=15)
        profissao = st.text_input("Profissão")
    with col_c2:
        email = st.text_input("Email")
        aniversario = st.text_input("Aniversário (DD/MM/AAAA)", key="v_ani", on_change=lambda: st.session_state.update({'v_ani': formatar_data(st.session_state['v_ani'])}), max_chars=10)
        renda = st.text_input("Renda Mensal", key="v_ren", on_change=lambda: st.session_state.update({'v_ren': formatar_moeda(st.session_state['v_ren'])}), placeholder="R$ 0,00")
        
    cep = st.text_input("CEP Rápido", max_chars=9)
    if cep and cep != st.session_state.get('l_cep', ''):
        c_limpo = ''.join(filter(str.isdigit, cep))
        if len(c_limpo) == 8:
            try:
                res = requests.get(f"https://viacep.com.br/ws/{c_limpo}/json/", timeout=5)
                if res.status_code == 200 and "erro" not in res.json():
                    d = res.json()
                    st.session_state.update({'v_rua': d.get('logradouro',''), 'v_bai': d.get('bairro',''), 'v_cid': d.get('localidade',''), 'v_uf': d.get('uf','')})
            except: pass
        st.session_state['l_cep'] = cep

    c1, c2, c3 = st.columns([2, 1, 1])
    rua = c1.text_input("Rua", key="v_rua" if 'v_rua' in st.session_state else None)
    num = c2.text_input("Número")
    comp = c3.text_input("Complemento")

    c4, c5, c6 = st.columns([2, 2, 1])
    bairro = c4.text_input("Bairro", key="v_bai" if 'v_bai' in st.session_state else None)
    cidade = c5.text_input("Cidade", key="v_cid" if 'v_cid' in st.session_state else None)
    uf = c6.text_input("UF", max_chars=2, key="v_uf" if 'v_uf' in st.session_state else None)

    col_v1, col_v2 = st.columns(2)
    with col_v1:
        data = st.date_input("Data da Venda", format="DD/MM/YYYY")
        vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]) if is_master else st.session_state['nome_vendedor']
    with col_v2:
        admin = st.selectbox("Administradora *", lista_admin_bd)
        produto = st.selectbox("Produto *", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
        
    st.markdown("##### Cotas")
    if 'q_cotas' not in st.session_state: st.session_state['q_cotas'] = 1
    cotas_data = []
    for i in range(st.session_state['q_cotas']):
        g1, g2, g3 = st.columns(3)
        g = g1.text_input(f"Grupo *", key=f"g_{i}")
        c = g2.text_input(f"Cota *", key=f"c_{i}")
        v = g3.text_input(f"Valor *", key=f"v_{i}", on_change=lambda idx=i: st.session_state.update({f'v_{idx}': formatar_moeda(st.session_state[f'v_{idx}'])}), placeholder="R$ 0,00")
        cotas_data.append({"g": g, "c": c, "v": v})

    if st.button("➕ Mais uma Cota"): st.session_state['q_cotas'] += 1; st.rerun()
    st.markdown("---")
    if st.button("Salvar Venda(s)", type="primary", use_container_width=True):
        if not cliente or not cotas_data[0]['g'] or not cotas_data[0]['c']: st.error("Preencha os obrigatórios (*).")
        else:
            end_c = f"{rua}, {num} {comp} - {bairro}, {cidade}-{uf}"
            v_ins = []
            for ct in cotas_data:
                vf = float(''.join(filter(str.isdigit, str(ct['v']))))/100 if ''.join(filter(str.isdigit, str(ct['v']))) else 0.0
                v_ins.append({"NOME": cliente, "DATA": data.strftime("%d/%m/%Y"), "PRODUTO": produto, "VENDEDOR": vendedor, "GRUPO": ct['g'], "COTA": ct['c'], "ADMINISTRADORA": admin, "STATUS": "Em Andamento", "VALOR": vf})
            supabase.table("vendas").insert(v_ins).execute()
            try:
                if df_cli.empty or cliente not in df_cli['Nome'].tolist():
                    supabase.table("clientes").insert([{"Nome": cliente, "Telefone": telefone, "Email": email, "Endereco": end_c, "Aniversario": aniversario, "Profissao": profissao, "Renda": renda, "Data_Cadastro": datetime.today().strftime("%d/%m/%Y")}]).execute()
            except: pass
            st.success("Salvo!"); st.session_state['q_cotas'] = 1

# --- RELATORIOS ---
elif menu_selecionado == "Relatórios":
    st.markdown("### 📑 Relatórios Gerenciais")
    if not df_vendas_global.empty:
        df_f = df_vendas_global.copy()
        c1, c2 = st.columns([1, 2])
        with c1:
            ft_rel = st.selectbox("Período:", ["Mês Atual", "Mês Anterior", "Ano Atual", "Todas as Vendas"])
        hoje = datetime.today()
        mask = df_f['Data_Real'].notna()
        if ft_rel == "Mês Atual": df_f = df_f[mask & (df_f['Data_Real'].dt.month == hoje.month) & (df_f['Data_Real'].dt.year == hoje.year)]
        elif ft_rel == "Mês Anterior": df_f = df_f[mask & (df_f['Data_Real'].dt.month == (hoje.month-1 if hoje.month>1 else 12)) & (df_f['Data_Real'].dt.year == (hoje.year if hoje.month>1 else hoje.year-1))]
        elif ft_rel == "Ano Atual": df_f = df_f[mask & (df_f['Data_Real'].dt.year == hoje.year)]
        if not is_master: df_f = df_f[df_f['VENDEDOR'] == st.session_state['nome_vendedor']]
        st.divider()

        t1, t2, t3 = st.tabs(["Vendas Por Usuário", "Por Administradora", "Gerar Comissões"])
        with t1:
            rv = df_f.groupby('VENDEDOR').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
            rv['Vol'] = rv['Vol'].apply(formatar_brl_puro)
            st.dataframe(rv, use_container_width=True, hide_index=True)
        with t2:
            ra = df_f.groupby('ADMINISTRADORA').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
            ra['Vol'] = ra['Vol'].apply(formatar_brl_puro)
            st.dataframe(ra, use_container_width=True, hide_index=True)
        with t3:
            st.info("Para dar baixa, expanda o relatório.")
            if st.button("Gerar Relatório Detalhado", type="primary"): st.session_state['tela_cheia_relatorio'] = True; st.rerun()
    else: st.info("Sem vendas.")

# --- BAIXAR PARCELAS ---
elif menu_selecionado == "Baixar Parcelas":
    st.markdown("### Baixar Parcelas")
    if 'cart_baixas' not in st.session_state: st.session_state['cart_baixas'] = []

    with st.form("b_b"):
        c1, c2 = st.columns(2)
        bg = c1.text_input("Grupo")
        bc = c2.text_input("Cota")
        if st.form_submit_button("Buscar", type="primary") and bg and bc:
            alvo = df_vendas_global[(df_vendas_global['GRUPO'] == bg.strip()) & (df_vendas_global['COTA'] == bc.strip())]
            st.session_state['venda_baixa_atual'] = alvo.iloc[0].to_dict() if not alvo.empty else None
            if alvo.empty: st.error("Não encontrada.")

    v = st.session_state.get('venda_baixa_atual')
    if v:
        st.divider()
        df_p, _ = gerar_tabela_parcelas(pd.DataFrame([v]), df_vendas_global, df_admin, cfg, status_dict)
        if not df_p.empty:
            st.write(f"**Cliente:** {v['Nome do cliente']} | **G:** {v['GRUPO']} | **C:** {v['COTA']}")
            pend = df_p[df_p['Status'] != 'PAGO']
            sug = pend.iloc[0]['Parcela'] if not pend.empty else df_p.iloc[-1]['Parcela']
            
            c1, c2 = st.columns(2)
            parc = c1.selectbox("Parcela:", df_p['Parcela'].tolist(), index=df_p['Parcela'].tolist().index(sug) if sug in df_p['Parcela'].tolist() else 0)
            linha = df_p[df_p['Parcela'] == parc].iloc[0]
            val_r = c2.number_input("Valor Recebido:", value=float(linha['Comissão (Bruta)']))

            rz = val_r / linha['Comissão (Bruta)'] if linha['Comissão (Bruta)'] > 0 else 0
            nl, nv, nb, nu = linha['Comissão (s/ Imposto)']*rz, linha['Vendedor Recebe']*rz, linha['Breno']*rz, linha['Uriel']*rz
            
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Líquido", formatar_brl_puro(nl)); s2.metric("Vend", formatar_brl_puro(nv))
            s3.metric("Breno", formatar_brl_puro(nb)); s4.metric("Uriel", formatar_brl_puro(nu))
            
            if st.button("Adicionar", use_container_width=True):
                st.session_state['cart_baixas'].append({"Chave": linha['Chave'], "Cliente": v['Nome do cliente'], "Grupo": v['GRUPO'], "Cota": v['COTA'], "Parcela": parc, "Valor Pago": val_r, "Líquido": nl, "Vendedor": nv, "Breno": nb, "Uriel": nu, "Data Baixa": datetime.today().strftime("%d/%m/%Y")})
                st.rerun()

    if st.session_state['cart_baixas']:
        st.subheader("Lista")
        df_c = pd.DataFrame(st.session_state['cart_baixas'])
        df_show = df_c[['Cliente', 'Grupo', 'Cota', 'Parcela', 'Valor Pago', 'Líquido', 'Vendedor', 'Breno', 'Uriel']].copy()
        for col in ['Valor Pago', 'Líquido', 'Vendedor', 'Breno', 'Uriel']: df_show[col] = df_show[col].apply(formatar_brl_puro)
        st.dataframe(df_show, hide_index=True)
        
        c1, c2 = st.columns([3,1])
        if c1.button("CONFIRMAR E BAIXAR", type="primary", use_container_width=True):
            for i in st.session_state['cart_baixas']:
                cv = i['Chave']
                ex = supabase.table("status_comissoes").select("id").eq("Chave_Unica", cv).execute()
                if ex.data: supabase.table("status_comissoes").update({"Status": "PAGO", "Valor_Pago": i['Valor Pago'], "Data_Pagamento": i['Data Baixa']}).eq("id", ex.data[0]['id']).execute()
                else: supabase.table("status_comissoes").insert({"Chave_Unica": cv, "Status": "PAGO", "Valor_Pago": i['Valor Pago'], "Data_Pagamento": i['Data Baixa']}).execute()
            st.session_state['cart_baixas'] = []; st.rerun()
        if c2.button("Limpar", use_container_width=True): st.session_state['cart_baixas'] = []; st.rerun()

# --- CONFIGURACOES ---
elif menu_selecionado == "Configurações de Sistema":
    st.markdown("### 🏢 Configurações")
    t1, t2, t3 = st.tabs(["Cadastrar Admin", "Regras", "Internas"])
    with t1:
        with st.form("cad_adm"):
            n, cn, en = st.text_input("Nome *"), st.text_input("CNPJ"), st.text_input("Endereço")
            if st.form_submit_button("Salvar", type="primary") and n:
                supabase.table("cad_administradoras").insert({"Administradora": n.upper(), "CNPJ": cn, "Endereço": en}).execute(); st.rerun()
        if not df_admin_cad.empty: st.dataframe(df_admin_cad.drop(columns=['id'], errors='ignore'), hide_index=True)
    with t2:
        if not df_admin.empty: st.dataframe(df_admin.drop(columns=['Admin_Norm', 'Prod_Norm', 'id'], errors='ignore'), hide_index=True)
        with st.expander("Nova Regra"):
            with st.form("n_reg"):
                a = st.selectbox("Admin", lista_admin_bd)
                p = st.selectbox("Produto", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
                i_p = [st.number_input(f"P{i+1}", min_value=0.0, step=0.1) for i in range(25)]
                if st.form_submit_button("Salvar", type="primary") and a != "Nenhuma administradora cadastrada":
                    r = {"Administradora": a.upper(), "Produto": p}
                    for i, v in enumerate(i_p): r[f"P{i+1}"] = f"{v}%" if v>0 else ""
                    supabase.table("administradoras").insert(r).execute(); st.rerun()
    with t3:
        st.write("Configurações Financeiras")
        i_n = st.number_input("Imposto (%)", value=parse_float_safe(cfg.get("Imposto", 7.16)))
        if st.button("Salvar Imposto", type="primary"):
            if cfg_id: supabase.table("config_interna").update({"Imposto": i_n}).eq("id", cfg_id).execute()
            else: supabase.table("config_interna").insert({"Imposto": i_n}).execute()
            st.rerun()
