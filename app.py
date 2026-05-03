import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import calendar
import requests 
import streamlit.components.v1 as components
import altair as alt
import unicodedata
import os 

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
            html_code = f.read()
            components.html(html_code, height=900, scrolling=True)
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
    val_float = float(nums) / 100
    return f"R$ {val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_brl_puro(val):
    if pd.isna(val): return "R$ 0,00"
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
    if isinstance(v, (int, float)): return float(v)
    try:
        v_str = str(v).replace('%', '').replace('R$', '').strip()
        if not v_str: return 0.0
        if '.' in v_str and ',' in v_str:
            if v_str.rfind(',') > v_str.rfind('.'):
                v_str = v_str.replace('.', '').replace(',', '.')
            else:
                v_str = v_str.replace(',', '')
        elif ',' in v_str:
            v_str = v_str.replace(',', '.')
        return float(v_str)
    except:
        return 0.0

# Callbacks
def mascara_tel_nv(): st.session_state['tel_nv'] = formatar_telefone(st.session_state.get('tel_nv', ''))
def mascara_aniv_nv(): st.session_state['aniv_nv'] = formatar_data(st.session_state.get('aniv_nv', ''))
def mascara_renda_nv(): st.session_state['renda_nv'] = formatar_moeda(st.session_state.get('renda_nv', ''))

# === MOTORES DE CÁLCULO DE COMISSÃO ===
def calcular_comissao_vendedor(df_vendas_global, vendedor_nome, data_venda_dt, cfg):
    if pd.isna(data_venda_dt): return cfg.get('T1_Pct', 1.0), int(cfg.get('T1_Parc', 4))
    mes = data_venda_dt.month
    ano = data_venda_dt.year
    df_mes = df_vendas_global[(df_vendas_global['VENDEDOR'] == vendedor_nome) &
                              (df_vendas_global['Data_Real'].dt.month == mes) &
                              (df_vendas_global['Data_Real'].dt.year == ano)]
    vol_total = df_mes['Valor_Numerico'].sum()

    if vol_total <= cfg.get('T1_Max', 500000): return cfg.get('T1_Pct', 1.0), int(cfg.get('T1_Parc', 4))
    elif vol_total <= cfg.get('T2_Max', 1500000): return cfg.get('T2_Pct', 1.5), int(cfg.get('T2_Parc', 5))
    else: return cfg.get('T3_Pct', 2.0), int(cfg.get('T3_Parc', 5))

def gerar_tabela_parcelas(df_alvo, df_global, df_regras, cfg, status_dict):
    hoje = pd.Timestamp.today().normalize()
    parcelas_finais = []
    vendas_sem_data = [] 
    
    for idx, r in df_alvo.iterrows():
        data_venda = r['Data_Real']
        cliente = r.get('Nome do cliente', 'Desconhecido')
        grupo = r.get('GRUPO', '')
        cota = r.get('COTA', '')
        
        if pd.isna(data_venda):
            vendas_sem_data.append(f"{cliente} (Gr: {grupo}/Cota: {cota})")
            continue 
            
        admin = r['ADMINISTRADORA']
        admin_norm = normalizar_string(admin)
        prod = r['PRODUTO']
        prod_norm = normalizar_produto(prod)
        vendedor = r['VENDEDOR']
        val_venda = r['Valor_Numerico']
        
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
            
            vend_rec = 0.0
            breno_rec = 0.0
            uriel_rec = 0.0
            
            if vendedor == "BRENO LIMA":
                breno_rec = corretora_liq * (parse_float_safe(cfg.get('Breno_Breno', 70))/100.0)
                uriel_rec = corretora_liq * (parse_float_safe(cfg.get('Breno_Uriel', 30))/100.0)
            elif vendedor == "URIEL GOMES":
                uriel_rec = corretora_liq * (parse_float_safe(cfg.get('Uriel_Uriel', 70))/100.0)
                breno_rec = corretora_liq * (parse_float_safe(cfg.get('Uriel_Breno', 30))/100.0)
            elif vendedor == "Consorbens":
                breno_rec = corretora_liq * (parse_float_safe(cfg.get('Cons_Breno', 50))/100.0)
                uriel_rec = corretora_liq * (parse_float_safe(cfg.get('Cons_Uriel', 50))/100.0)
            else:
                if i <= tier_parc: vend_rec = val_venda * (tier_pct/100.0) / tier_parc
                sobra = corretora_liq - vend_rec
                breno_rec = sobra * 0.50
                uriel_rec = sobra * 0.50

            data_pagamento = data_venda + pd.Timedelta(days=7) + pd.DateOffset(months=i-1)
            temp_parcels.append({
                'parcela': i, 'data_pagamento': data_pagamento, 'bruto': comissao_bruta,
                'liquido': corretora_liq, 'vend': vend_rec, 'breno': breno_rec, 'uriel': uriel_rec
            })
            
        if status_cota == 'Cancelada':
            temp_parcels = [p for p in temp_parcels if p['data_pagamento'] <= hoje]
        elif status_cota == 'Contemplada':
            past = [p for p in temp_parcels if p['data_pagamento'] <= hoje]
            future = [p for p in temp_parcels if p['data_pagamento'] > hoje]
            if future:
                past.append({
                    'parcela': 'Antecipação', 'data_pagamento': hoje,
                    'bruto': sum(p['bruto'] for p in future), 'liquido': sum(p['liquido'] for p in future),
                    'vend': sum(p['vend'] for p in future), 'breno': sum(p['breno'] for p in future), 'uriel': sum(p['uriel'] for p in future)
                })
            temp_parcels = past
            
        for p in temp_parcels:
            chave_unica = f"{cliente}_{grupo}_{cota}_{admin}_{p['parcela']}"
            status_pagamento = status_dict.get(chave_unica, "Pendente")
            
            data_str = p['data_pagamento'].strftime("%d/%m/%Y")
            if status_cota == 'Em Atraso': data_str = "⚠️ Travada (Atraso)"
            nome_parcela = f"{p['parcela']}ª Parcela" if isinstance(p['parcela'], int) else "Antecip. (Contemplada)"
            
            parcelas_finais.append({
                "Chave": chave_unica,
                "Cliente": cliente,
                "Produto": prod,
                "Vendedor": vendedor,
                "Grupo": grupo,
                "Cota": cota,
                "Valor da Venda": val_venda,
                "Parcela": nome_parcela,
                "data_pagamento_dt": p['data_pagamento'], 
                "Comissão (Bruta)": p['bruto'],
                "Comissão (s/ Imposto)": p['liquido'],
                "Breno": p['breno'],
                "Uriel": p['uriel'],
                "Vendedor Recebe": p['vend'],
                "Status": status_pagamento,
                "Data Prevista": data_str
            })
            
    return pd.DataFrame(parcelas_finais), vendas_sem_data

# ==========================================
# 4. CONEXÃO E CARREGAMENTO - SUPABASE
# ==========================================
@st.cache_resource
def iniciar_conexao() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = iniciar_conexao()

    def carregar_tabela(nome_tabela):
        res = supabase.table(nome_tabela).select("*").execute()
        return pd.DataFrame(res.data)

    df_vendas_bd = carregar_tabela("vendas")
    if not df_vendas_bd.empty:
        df_vendas_global = df_vendas_bd.copy()
        df_vendas_global.rename(columns={"NOME": "Nome do cliente"}, inplace=True)
        # Correção no parser de data para ser mais robusto com os formatos
        df_vendas_global['Data_Real'] = pd.to_datetime(df_vendas_global['DATA'], dayfirst=True, errors='coerce')
        df_vendas_global['Valor_Numerico'] = df_vendas_global['VALOR'].apply(parse_float_safe)
        
        df_vendas_global['GRUPO'] = df_vendas_global['GRUPO'].apply(lambda x: str(x)[:-2] if str(x).endswith('.0') else str(x).strip())
        df_vendas_global['COTA'] = df_vendas_global['COTA'].apply(lambda x: str(x)[:-2] if str(x).endswith('.0') else str(x).strip())
    else:
        df_vendas_global = pd.DataFrame()

    df_cli = carregar_tabela("clientes")
    
    df_admin_cad = carregar_tabela("cad_administradoras")
    lista_admin_bd = df_admin_cad['Administradora'].tolist() if not df_admin_cad.empty else ["Nenhuma administradora cadastrada"]

    df_admin = carregar_tabela("administradoras")
    if not df_admin.empty:
        df_admin['Admin_Norm'] = df_admin['Administradora'].apply(normalizar_string)
        df_admin['Prod_Norm'] = df_admin['Produto'].apply(normalizar_produto)

    df_status = carregar_tabela("status_comissoes")
    status_dict = dict(zip(df_status['Chave_Unica'], df_status['Status'])) if not df_status.empty else {}

    cfg_padrao = {
        "Breno_Breno": 70.0, "Breno_Uriel": 30.0, "Uriel_Uriel": 70.0, "Uriel_Breno": 30.0,
        "Cons_Breno": 50.0, "Cons_Uriel": 50.0, "T1_Max": 500000.0, "T1_Pct": 1.0, "T1_Parc": 4,
        "T2_Max": 1500000.0, "T2_Pct": 1.5, "T2_Parc": 5, "T3_Pct": 2.0, "T3_Parc": 5, "Imposto": 7.16
    }
    
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
    st.error(f"⚠️ Erro ao conectar com o Supabase. Detalhes: {e}")
    st.stop()


def salvar_status_comissoes(df_editado, df_original):
    mudancas = df_editado[df_editado['Status'] != df_original['Status']]
    if not mudancas.empty:
        for _, row in mudancas.iterrows():
            chave = row['Chave']
            novo_status = row['Status']
            existe = supabase.table("status_comissoes").select("id").eq("Chave_Unica", chave).execute()
            if existe.data:
                supabase.table("status_comissoes").update({"Status": novo_status}).eq("id", existe.data[0]['id']).execute()
            else:
                supabase.table("status_comissoes").insert({"Chave_Unica": chave, "Status": novo_status}).execute()
        return True
    return False

if st.session_state['tela_cheia_relatorio']:
    st.markdown("## 💰 Relatório de Comissionamento Detalhado")
    
    col_bt, col_chk = st.columns([1, 3])
    with col_bt:
        if st.button("⬅️ Voltar aos Filtros", type="secondary"):
            st.session_state['tela_cheia_relatorio'] = False
            st.rerun()
    with col_chk:
        mostrar_pagos = st.checkbox("Mostrar parcelas já pagas (PAGO)", value=False)
        
    df_parcelas_todas, vendas_sem_data = gerar_tabela_parcelas(df_vendas_global, df_vendas_global, df_admin, cfg, status_dict)
    
    if vendas_sem_data:
        st.warning(f"⚠️ **Atenção:** As seguintes vendas estão sem data preenchida ou em formato incorreto: **{', '.join(vendas_sem_data)}**.")

    if not df_parcelas_todas.empty:
        hoje = pd.Timestamp.today().normalize()
        mask = df_parcelas_todas['data_pagamento_dt'].notna()
        df_view = df_parcelas_todas.copy()
        
        if st.session_state['perfil_logado'] == "Vendedor" and not is_master:
            df_view = df_view[df_view['Vendedor'] == st.session_state['nome_vendedor']]
        
        ft_rel = st.session_state.get('rel_periodo', 'Todas as Vendas')
        
        if ft_rel == "Mês Atual":
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.month == hoje.month) & (df_view['data_pagamento_dt'].dt.year == hoje.year)]
        elif ft_rel == "Quinzena Atual":
            if hoje.day <= 15: 
                q_ini, q_fim = hoje.replace(day=1), hoje.replace(day=15)
            else: 
                q_ini, q_fim = hoje.replace(day=16), hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.date >= q_ini.date()) & (df_view['data_pagamento_dt'].dt.date <= q_fim.date())]
        elif ft_rel == "Mês Anterior":
            ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.month == ma) & (df_view['data_pagamento_dt'].dt.year == aa)]
        elif ft_rel == "Ano Atual":
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.year == hoje.year)]
        elif ft_rel == "Período Personalizado":
            ri = st.session_state['rel_dt_ini']
            rf = st.session_state['rel_dt_fim']
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.date >= ri) & (df_view['data_pagamento_dt'].dt.date <= rf)]
            
        if not mostrar_pagos:
            df_view = df_view[df_view['Status'] != 'PAGO']
            
        if not df_view.empty:
            df_view = df_view[['Chave', 'Cliente', 'Produto', 'Vendedor', 'Grupo', 'Cota', 'Valor da Venda', 'Parcela', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe', 'Status', 'Data Prevista']]
            
            total_breno = df_view['Breno'].sum()
            total_uriel = df_view['Uriel'].sum()
            total_vend = df_view['Vendedor Recebe'].sum()
            
            for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']:
                df_view[col] = df_view[col].apply(formatar_brl_puro)
            
            col_config = {
                "Chave": None, 
                "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True)
            }
            
            cols_to_hide = []
            if not is_master: cols_to_hide = ["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"]
            
            df_final = df_view.drop(columns=cols_to_hide).reset_index(drop=True)
            disabled_cols = [c for c in df_final.columns if c != "Status"]
            
            st.caption("Dica: Clique na coluna 'Status' para alterar. Em seguida, salve as alterações no botão vermelho.")
            edited_df = st.data_editor(
                df_final,
                disabled=disabled_cols,
                column_config=col_config,
                use_container_width=True,
                hide_index=True,
                key="editor_relatorio_full"
            )
            
            if is_master:
                if st.button("💾 Salvar Status de Pagamento", type="primary"):
                    if salvar_status_comissoes(edited_df, df_final):
                        st.success("Status atualizados no banco de dados!")
                        st.rerun()
                    else: st.info("Nenhuma alteração detectada.")
                        
                st.divider()
                st.markdown("#### 💵 Total do Período (Apenas o visualizado acima)")
                mt1, mt2, mt3 = st.columns(3)
                mt1.metric("Breno (Sócios)", formatar_brl_puro(total_breno))
                mt2.metric("Uriel (Sócios)", formatar_brl_puro(total_uriel))
                mt3.metric("Vendedores", formatar_brl_puro(total_vend))
        else:
            st.success("Nenhuma comissão pendente (ou com os filtros atuais) para exibir!")
    else:
        st.info("O sistema ainda não possui vendas para calcular a comissão.")
        
    st.stop() 

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
</style>
"""

simuladores_dict = {
    "🏍️ Simulador Yamaha": "yamaha.html",
    "🏦 Simulador Itaú": "itau.html",
    "🎯 Oportunidades Itaú": "guia.html",
    "⚖️ Financiamento x Consórcio": "comparador.html"
}

logo_path = os.path.join(PASTA_ATUAL, "logo.png")
if os.path.exists(logo_path): st.sidebar.image(logo_path, use_container_width=True)
st.sidebar.markdown("<br>", unsafe_allow_html=True) 

if not is_logado:
    opcoes_menu = ["🔐 Login (Área Restrita)"] + list(simuladores_dict.keys())
    try: idx_menu = opcoes_menu.index(st.session_state['menu_lateral'])
    except ValueError: idx_menu = 0
    selecao = st.sidebar.radio(" ", opcoes_menu, index=idx_menu, label_visibility="collapsed")
    if selecao != st.session_state['menu_lateral']:
        st.session_state['menu_lateral'] = selecao
        st.rerun()
else:
    st.sidebar.divider() 
    if is_master: opcoes_principais = ["Dashboard", "Nova Venda", "Relatórios", "Baixar Parcelas", "Configurações de Sistema"] 
    else: opcoes_principais = ["Dashboard", "Nova Venda", "Relatórios"]
    
    try: idx_principal = opcoes_principais.index(st.session_state['menu_lateral'])
    except ValueError: idx_principal = None 
        
    selecao_principal = st.sidebar.radio(" ", opcoes_principais, index=idx_principal, label_visibility="collapsed")
    
    if selecao_principal and selecao_principal != st.session_state.get('last_radio_selection') and selecao_principal in opcoes_principais:
        st.session_state['menu_lateral'] = selecao_principal
        st.session_state['cliente_visualizado'] = None
        st.session_state['last_radio_selection'] = selecao_principal
        st.rerun()
            
    if selecao_principal in opcoes_principais: st.session_state['last_radio_selection'] = selecao_principal
        
    st.sidebar.write("")
    
    with st.sidebar.expander("🛠️ Simuladores", expanded=(st.session_state['menu_lateral'] in simuladores_dict)):
        for sim in simuladores_dict.keys():
            btn_type = "primary" if st.session_state['menu_lateral'] == sim else "secondary"
            if st.button(sim, use_container_width=True, type=btn_type):
                st.session_state['menu_lateral'] = sim
                st.session_state['cliente_visualizado'] = None
                st.session_state['last_radio_selection'] = None
                st.rerun()
                
    st.sidebar.write("")
    if st.sidebar.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

menu_selecionado = st.session_state['menu_lateral']

if menu_selecionado in simuladores_dict: css += """ <style>.stApp { background-color: #0f172a !important; }</style> """
else: css += """ <style>.stApp { background-color: #ffffff !important; }</style> """
st.markdown(css, unsafe_allow_html=True)


if menu_selecionado in simuladores_dict:
    carregar_ferramenta(simuladores_dict[menu_selecionado])
    st.stop() 

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

# --- DASHBOARD ---
if menu_selecionado == "Dashboard":
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        st.markdown(f"### {cliente_nome}")
        
        if st.button("⬅️ Voltar ao Dashboard", type="primary"):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
            
        info_cliente = {}
        id_cliente_db = None
        if not df_cli.empty and 'Nome' in df_cli.columns:
            busca_cli = df_cli[df_cli['Nome'] == cliente_nome]
            if not busca_cli.empty: 
                info_cliente = busca_cli.iloc[0].to_dict()
                id_cliente_db = info_cliente.get('id')

        if not is_master: st.info("🔒 Como Vendedor, você só pode visualizar estes dados. Para alterar, contate o Administrador.")
            
        key_nome = f"nome_ed_{cliente_nome}"
        key_tel = f"tel_ed_{cliente_nome}"
        key_email = f"email_ed_{cliente_nome}"
        key_end = f"end_ed_{cliente_nome}"
        key_aniv = f"aniv_ed_{cliente_nome}"
        key_prof = f"prof_ed_{cliente_nome}"
        key_renda = f"renda_ed_{cliente_nome}"
        
        def safe_str(val, default=""):
            if pd.isna(val) or val is None or str(val).strip().lower() in ["nan", "nat", "none"]:
                return default
            return str(val)

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
        
        c1, c2 = st.columns(2)
        with c1:
            endereco = st.text_input("Endereço Completo", key=key_end, disabled=not is_master)
            telefone_edit = st.text_input("Telefone", key=key_tel, on_change=m_tel_ed, disabled=not is_master)
            profissao_edit = st.text_input("Profissão", key=key_prof, disabled=not is_master)
        with c2:
            email = st.text_input("E-mail", key=key_email, disabled=not is_master)
            aniversario_edit = st.text_input("Data de Aniversário (DD/MM/AAAA)", key=key_aniv, on_change=m_aniv_ed, disabled=not is_master)
            renda_edit = st.text_input("Renda Mensal (R$)", key=key_renda, on_change=m_renda_ed, disabled=not is_master)
        
        if is_master:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Salvar Alterações Cadastrais", type="primary", use_container_width=True):
                    novo_nome_val = st.session_state[key_nome]
                    dados_cli = {
                        "Nome": novo_nome_val, "Telefone": st.session_state[key_tel], "Email": st.session_state[key_email],
                        "Endereco": st.session_state[key_end], "Aniversario": st.session_state[key_aniv],
                        "Profissao": st.session_state[key_prof], "Renda": st.session_state[key_renda]
                    }
                    if id_cliente_db: supabase.table("clientes").update(dados_cli).eq("id", id_cliente_db).execute()
                    else:
                        dados_cli["Data_Cadastro"] = datetime.today().strftime("%d/%m/%Y")
                        supabase.table("clientes").insert(dados_cli).execute()
                    
                    if novo_nome_val != cliente_nome:
                        supabase.table("vendas").update({"NOME": novo_nome_val}).eq("NOME", cliente_nome).execute()
                        st.session_state['cliente_visualizado'] = novo_nome_val
                        
                    st.success("Dados atualizados com sucesso!")
                    st.rerun()

            with col_b2:
                if st.button("🚨 Excluir Cliente", use_container_width=True):
                    if id_cliente_db: supabase.table("clientes").delete().eq("id", id_cliente_db).execute()
                    supabase.table("vendas").delete().eq("NOME", cliente_nome).execute()
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
                st.dataframe(ficha_display, use_container_width=True, hide_index=True)
                
                st.write("")
                with st.expander("⚙️ Atualizar Status, Data e Gerenciar Cota", expanded=False):
                    opcoes_cotas = cotas_cliente.apply(lambda r: f"ID:{r['id']} | Grupo: {r['GRUPO']} / Cota: {r['COTA']} - Valor: {r['Valor Formatado']}", axis=1).tolist()
                    c_sel, _ = st.columns([3, 1])
                    with c_sel: cota_selecionada = st.selectbox("Selecione a cota:", [""] + opcoes_cotas)
                        
                    if cota_selecionada:
                        id_cota = int(cota_selecionada.split(" | ")[0].replace("ID:", ""))
                        cota_info = cotas_cliente[cotas_cliente['id'] == id_cota].iloc[0]
                        vendedor_atual = cota_info['VENDEDOR']
                        status_atual = cota_info['STATUS']
                        data_atual_str = cota_info['DATA']
                        if status_atual == "Vendido" or not status_atual: status_atual = "Em Andamento"
                        try: data_atual_obj = datetime.strptime(str(data_atual_str), "%d/%m/%Y").date()
                        except: data_atual_obj = datetime.today().date()
                        
                        c_ed1, c_ed2, c_ed3 = st.columns(3)
                        with c_ed1:
                            status_list = ["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"]
                            idx_status = status_list.index(status_atual) if status_atual in status_list else 0
                            novo_status = st.selectbox("Status da Cota", status_list, index=idx_status, key=f"edit_status_{id_cota}")
                        with c_ed2:
                            vendedores_list = ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]
                            if is_master:
                                idx_vend = vendedores_list.index(vendedor_atual) if vendedor_atual in vendedores_list else 0
                                novo_vendedor = st.selectbox("Vendedor Realizador", vendedores_list, index=idx_vend, key=f"edit_vend_{id_cota}")
                            else:
                                st.text_input("Vendedor Realizador", value=vendedor_atual, disabled=True, key=f"edit_vend_block_{id_cota}")
                                novo_vendedor = vendedor_atual
                        with c_ed3:
                            if is_master:
                                nova_data = st.date_input("Nova Data (DD/MM/AAAA)", value=data_atual_obj, format="DD/MM/YYYY", key=f"edit_data_{id_cota}")
                            else:
                                st.text_input("Data da Venda", value=data_atual_str, disabled=True, key=f"edit_data_block_{id_cota}")
                                nova_data = data_atual_obj
                                
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.button("💾 Salvar Alterações na Cota", type="primary", use_container_width=True):
                                nova_data_formatada = nova_data.strftime("%d/%m/%Y") if not isinstance(nova_data, str) else nova_data
                                supabase.table("vendas").update({"VENDEDOR": novo_vendedor, "STATUS": novo_status, "DATA": nova_data_formatada}).eq("id", id_cota).execute()
                                st.success("Cota atualizada!")
                                st.rerun()
                        with col_b2:
                            if is_master:
                                if st.button("🚨 Apagar Cota", use_container_width=True):
                                    supabase.table("vendas").delete().eq("id", id_cota).execute()
                                    st.rerun()

                st.write("")
                st.subheader("📈 Previsão de Comissionamento")
                df_parcelas, vendas_sem_data = gerar_tabela_parcelas(cotas_cliente, df_vendas_global, df_admin, cfg, status_dict)
                
                if vendas_sem_data:
                    st.warning(f"⚠️ **Atenção:** As seguintes vendas estão sem data ou com formatação incorreta: **{', '.join(vendas_sem_data)}**.")

                if not df_parcelas.empty:
                    df_view_cli = df_parcelas.copy()
                    if not is_master: df_view_cli = df_view_cli[df_view_cli['Vendedor Recebe'] > 0]
                        
                    if not df_view_cli.empty:
                        for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']:
                            if col in df_view_cli.columns: df_view_cli[col] = df_view_cli[col].apply(formatar_brl_puro)
                            
                        col_config = {
                            "Chave": None, 
                            "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True)
                        }
                        
                        cols_to_hide = ['Cliente', 'Produto', 'Vendedor', 'data_pagamento_dt']
                        if not is_master: cols_to_hide += ["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"]
                        
                        df_final_cli = df_view_cli.drop(columns=cols_to_hide).reset_index(drop=True)
                        disabled_cols = [c for c in df_final_cli.columns if c != "Status"]
                        
                        edited_df_cli = st.data_editor(
                            df_final_cli, disabled=disabled_cols, column_config=col_config, use_container_width=True, hide_index=True, key="editor_cli"
                        )
                        
                        if is_master and st.button("💾 Salvar Status de Pagamento", type="primary"):
                            if salvar_status_comissoes(edited_df_cli, df_final_cli):
                                st.success("Status atualizados!")
                                st.rerun()
                else: st.info("Aguardando configurações para gerar a previsão.")
            else: st.warning("Nenhuma cota encontrada.")

    else:
        if not df_vendas_global.empty:
            df_view = df_vendas_global.copy()
            if st.session_state['perfil_logado'] == "Vendedor" and not is_master:
                df_view = df_view[df_view['VENDEDOR'] == st.session_state['nome_vendedor']]

            col_t1, col_t2 = st.columns([4, 1])
            with col_t2:
                st.write("")
                if st.button("Nova Venda", use_container_width=True, type="primary"):
                    st.session_state['menu_lateral'] = "Nova Venda"
                    st.rerun()
            
            c_filtro1, c_filtro2, c_filtro3, c_filtro4 = st.columns([1.5, 1.5, 1, 1])
            with c_filtro1:
                filtro_cli = st.selectbox("⏳ Filtro da Tabela:", ["Últimos 5 Cadastros", "Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
                if filtro_cli == "Período Personalizado":
                    cd1, cd2 = st.columns(2)
                    with cd1: p_ini = st.date_input("Início", format="DD/MM/YYYY")
                    with cd2: p_fim = st.date_input("Fim", format="DD/MM/YYYY")
            with c_filtro2: busca_nome = st.text_input("🔍 Buscar Cliente:")
            with c_filtro3: busca_grupo = st.text_input("📦 Grupo:")
            with c_filtro4: busca_cota = st.text_input("🔢 Cota:")

            hoje = datetime.today()
            df_view = df_view.sort_values(by="Data_Real", ascending=False)
            
            if filtro_cli == "Últimos 5 Cadastros" and not (busca_nome or busca_grupo or busca_cota):
                df_view = df_view.head(5)
            elif filtro_cli not in ["Todos os Clientes", "Últimos 5 Cadastros"]:
                mask = df_view['Data_Real'].notna()
                if filtro_cli == "Mês Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.month == hoje.month) & (df_view['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Mês Anterior":
                    mes_ant, ano_ant = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                    df_view = df_view[mask & (df_view['Data_Real'].dt.month == mes_ant) & (df_view['Data_Real'].dt.year == ano_ant)]
                elif filtro_cli == "Ano Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Período Personalizado": df_view = df_view[mask & (df_view['Data_Real'].dt.date >= p_ini) & (df_view['Data_Real'].dt.date <= p_fim)]

            if busca_nome.strip(): df_view = df_view[df_view['Nome do cliente'].astype(str).str.contains(busca_nome.strip(), case=False, na=False)]
            if busca_grupo.strip(): df_view = df_view[df_view['GRUPO'].astype(str).str.strip() == busca_grupo.strip()]
            if busca_cota.strip(): df_view = df_view[df_view['COTA'].astype(str).str.strip() == busca_cota.strip()]

            if not df_view.empty:
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
            else: st.info("Nenhuma venda encontrada.")
        else: st.info("O sistema ainda não possui vendas cadastradas.")

elif menu_selecionado == "Baixar Parcelas":
    st.markdown("### Baixar Parcelas de Comissão")
    
    if 'cart_baixas' not in st.session_state: st.session_state['cart_baixas'] = []

    st.subheader("1. Buscar Cota")
    with st.form("busca_baixa_form"):
        cb1, cb2 = st.columns(2)
        with cb1: busca_g = st.text_input("Grupo")
        with cb2: busca_c = st.text_input("Cota")
        btn_busca = st.form_submit_button("Buscar Cliente", type="primary")

    if btn_busca:
        if busca_g and busca_c:
            alvo = df_vendas_global[(df_vendas_global['GRUPO'].astype(str).str.strip() == busca_g.strip()) & (df_vendas_global['COTA'].astype(str).str.strip() == busca_c.strip())]
            if not alvo.empty:
                st.session_state['venda_baixa_atual'] = alvo.iloc[0].to_dict()
            else:
                st.error("❌ Cota não encontrada.")
                st.session_state['venda_baixa_atual'] = None
        else:
            st.warning("Preencha Grupo e Cota.")
            st.session_state['venda_baixa_atual'] = None

    v_atual = st.session_state.get('venda_baixa_atual')
    if v_atual:
        st.divider()
        st.subheader("2. Configurar Parcela")
        
        df_alvo = pd.DataFrame([v_atual])
        df_parc_alvo, _ = gerar_tabela_parcelas(df_alvo, df_vendas_global, df_admin, cfg, status_dict)
        
        if not df_parc_alvo.empty:
            st.markdown(f"**Cliente:** {v_atual.get('Nome do cliente', '')} | **Grupo:** {v_atual.get('GRUPO', '')} | **Cota:** {v_atual.get('COTA', '')}")
            st.markdown(f"**Crédito:** {formatar_brl_puro(v_atual.get('Valor_Numerico', 0))}")
            st.write("")
            
            pendentes = df_parc_alvo[df_parc_alvo['Status'] != 'PAGO']
            parc_sugerida = pendentes.iloc[0]['Parcela'] if not pendentes.empty else df_parc_alvo.iloc[-1]['Parcela']
            
            opcoes_parc = df_parc_alvo['Parcela'].tolist()
            try: idx_sug = opcoes_parc.index(parc_sugerida)
            except: idx_sug = 0
            
            cp1, cp2 = st.columns(2)
            with cp1: sel_parc = st.selectbox("Parcela a Baixar:", opcoes_parc, index=idx_sug)
            
            linha_parc = df_parc_alvo[df_parc_alvo['Parcela'] == sel_parc].iloc[0]
            val_original = linha_parc['Comissão (Bruta)']
            
            with cp2: novo_valor_bruto = st.number_input("Valor Recebido (R$):", value=float(val_original), step=10.0)

            if val_original > 0:
                razao = novo_valor_bruto / val_original
                novo_imp = (val_original - linha_parc['Comissão (s/ Imposto)']) * razao
                novo_liq = linha_parc['Comissão (s/ Imposto)'] * razao
                novo_vend = linha_parc['Vendedor Recebe'] * razao
                novo_breno = linha_parc['Breno'] * razao
                novo_uriel = linha_parc['Uriel'] * razao
            else:
                novo_imp = novo_liq = novo_vend = novo_breno = novo_uriel = 0.0
            
            sd1, sd2, sd3, sd4 = st.columns(4)
            sd1.metric("Líquido Corretora", formatar_brl_puro(novo_liq))
            sd2.metric("Vendedor", formatar_brl_puro(novo_vend))
            sd3.metric("Breno", formatar_brl_puro(novo_breno))
            sd4.metric("Uriel", formatar_brl_puro(novo_uriel))
            
            st.write("")
            if st.button("Adicionar à Lista", use_container_width=True):
                chave_item = linha_parc['Chave']
                if any(item['Chave'] == chave_item for item in st.session_state['cart_baixas']):
                    st.warning("Esta parcela já está na lista.")
                else:
                    st.session_state['cart_baixas'].append({
                        "Chave": chave_item, "Cliente": v_atual.get('Nome do cliente'), "Grupo": v_atual.get('GRUPO'),
                        "Cota": v_atual.get('COTA'), "Parcela": sel_parc, "Valor Base": val_original,
                        "Valor Pago": novo_valor_bruto, "Líquido": novo_liq, "Vendedor": novo_vend,
                        "Breno": novo_breno, "Uriel": novo_uriel, "Data Baixa": datetime.today().strftime("%d/%m/%Y")
                    })
                    st.success("Adicionado!")
                    st.rerun()
        else: st.warning("Não há parcelas geradas para esta cota.")

    st.divider()
    st.subheader("3. Lista de Baixas")
    if st.session_state['cart_baixas']:
        df_cart = pd.DataFrame(st.session_state['cart_baixas'])
        df_cart_display = df_cart[['Cliente', 'Grupo', 'Cota', 'Parcela', 'Valor Pago']].copy()
        df_cart_display['Valor Pago'] = df_cart_display['Valor Pago'].apply(formatar_brl_puro)
        st.dataframe(df_cart_display, use_container_width=True, hide_index=True)
        
        c_btn_a, c_btn_b = st.columns([3, 1])
        with c_btn_a:
            if st.button("CONFIRMAR E DAR BAIXA", type="primary", use_container_width=True):
                for item in st.session_state['cart_baixas']:
                    c = item['Chave']
                    try:
                        existe = supabase.table("status_comissoes").select("id").eq("Chave_Unica", c).execute()
                        if existe.data:
                            supabase.table("status_comissoes").update({"Status": "PAGO", "Valor_Pago": item['Valor Pago'], "Data_Pagamento": item['Data Baixa']}).eq("id", existe.data[0]['id']).execute()
                        else:
                            res_in = supabase.table("status_comissoes").insert({"Chave_Unica": c, "Status": "PAGO"}).execute()
                            try: supabase.table("status_comissoes").update({"Valor_Pago": item['Valor Pago'], "Data_Pagamento": item['Data Baixa']}).eq("id", res_in.data[0]['id']).execute()
                            except: pass
                    except Exception as e: st.error(f"Erro: {e}")
                
                st.success("Parcelas baixadas.")
                st.session_state['cart_baixas'] = []
                st.rerun()
        with c_btn_b:
            if st.button("Limpar", use_container_width=True):
                st.session_state['cart_baixas'] = []
                st.rerun()
    else: st.info("A lista está vazia.")

    st.divider()
    st.subheader("Histórico")
    chaves_pagas = [k for k, v in status_dict.items() if v == 'PAGO']
    if chaves_pagas:
        historico_lista = []
        for ch in chaves_pagas:
            partes = ch.split('_')
            if len(partes) >= 5:
                historico_lista.append({
                    "Cliente": "_".join(partes[:-4]), "Grupo": partes[-4], "Cota": partes[-3],
                    "Administradora": partes[-2], "Parcela": partes[-1], "Status": "PAGO"
                })
        if historico_lista: st.dataframe(pd.DataFrame(historico_lista), use_container_width=True, hide_index=True)
    else: st.info("Sem pagamentos registrados.")

# --- OUTROS MENUS ---
# Nova Venda, Relatórios, e Configurações continuam como antes.
