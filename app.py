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
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E USUÁRIOS
# ==========================================
st.set_page_config(page_title="Portal Consorbens", layout="wide", initial_sidebar_state="expanded")

PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))

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

# ==========================================
# 2. MÁSCARAS E NORMALIZADORES
# ==========================================
def formatar_telefone(tel):
    if not tel: return ""
    nums = ''.join(filter(str.isdigit, str(tel)))
    if len(nums) == 11: return f"({nums[:2]}) {nums[2:7]}-{nums[7:]}"
    elif len(nums) == 10: return f"({nums[:2]}) {nums[2:6]}-{nums[6:]}"
    return tel

def formatar_data_br(dt):
    if pd.isna(dt) or dt is None: return ""
    if isinstance(dt, (datetime, pd.Timestamp)):
        return dt.strftime('%d/%m/%Y')
    return str(dt)

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

def limpar_str_nan(val):
    s = str(val).strip()
    if s.lower() in ['nan', 'none', '<na>', 'nat']: return ""
    if s.endswith('.0'): return s[:-2]
    return s

# Callbacks
def mascara_tel_nv(): st.session_state['tel_nv'] = formatar_telefone(st.session_state.get('tel_nv', ''))
def mascara_aniv_nv(): st.session_state['aniv_nv'] = formatar_data(st.session_state.get('aniv_nv', ''))
def mascara_renda_nv(): st.session_state['renda_nv'] = formatar_moeda(st.session_state.get('renda_nv', ''))

# ==========================================
# 3. INTEGRAÇÃO GOOGLE DRIVE (MÍDIAS)
# ==========================================
@st.cache_resource
def get_drive_service():
    """Autentica com o Google Drive usando as credenciais do Streamlit Secrets"""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        return None

@st.cache_data(ttl=300) # Cache de 5 minutos para não estourar limite da API
def listar_arquivos_drive(folder_ids):
    """Lista os arquivos das pastas do Google Drive especificadas"""
    service = get_drive_service()
    if not service: return []
    todos_arquivos = []
    if isinstance(folder_ids, str): folder_ids = [folder_ids]
    
    for folder_id in folder_ids:
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            results = service.files().list(
                q=query, 
                fields="files(id, name, mimeType, webViewLink, webContentLink, thumbnailLink)",
                pageSize=100
            ).execute()
            todos_arquivos.extend(results.get('files', []))
        except Exception as e:
            continue
    return todos_arquivos

# ==========================================
# 4. MOTORES DE CÁLCULO DE COMISSÃO
# ==========================================
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
# 5. CONEXÃO E CARREGAMENTO - SUPABASE
# ==========================================
@st.cache_resource
def iniciar_conexao() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = iniciar_conexao()

    def carregar_tabela(nome_tabela):
        try:
            res = supabase.table(nome_tabela).select("*").execute()
            return pd.DataFrame(res.data)
        except:
            return pd.DataFrame() # Caso a tabela não exista ainda

    df_vendas_bd = carregar_tabela("vendas")
    if not df_vendas_bd.empty:
        df_vendas_global = df_vendas_bd.copy()
        df_vendas_global.rename(columns={"NOME": "Nome do cliente"}, inplace=True)
        # Correção no parser de data para ser mais robusto com os formatos
        df_vendas_global['Data_Real'] = pd.to_datetime(df_vendas_global['DATA'], dayfirst=True, errors='coerce')
        df_vendas_global['Valor_Numerico'] = df_vendas_global['VALOR'].apply(parse_float_safe)
        
        # Filtro de nan e formatos incorretos
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
    st.error(f"⚠️ Erro ao conectar com o Supabase. Verifique a estrutura do banco. Detalhes: {e}")
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

# ==========================================
# 6. LÓGICA DE TELA CHEIA (RELATÓRIO DE COMISSÃO)
# ==========================================
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

# ==========================================
# 7. CSS CUSTOMIZADO
# ==========================================
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
    
    /* Mídias Cards */
    .media-card { background: white; padding: 12px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .media-img { max-width: 100%; max-height: 120px; object-fit: contain; border-radius: 4px; margin-bottom: 10px; }
    .media-title { font-size: 13px; font-weight: 500; color: #334155; margin-bottom: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
"""

# ==========================================
# 8. ROTEADOR DE MENU LATERAL
# ==========================================
simuladores_dict = {
    "🏍️ Simulador Yamaha": "yamaha.html",
    "🏦 Simulador Itaú": "itau.html",
    "🎯 Oportunidades Itaú": "guia.html",
    "⚖️ Financiamento x Consórcio": "comparador.html"
}

logo_path = os.path.join(PASTA_ATUAL, "logo.png")
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)
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
    
    if is_master:
        opcoes_principais = ["Dashboard", "Nova Venda", "Assembleias", "Relatórios", "Mídias", "Baixar Parcelas", "Configurações de Sistema"] 
    else:
        opcoes_principais = ["Dashboard", "Nova Venda", "Assembleias", "Relatórios", "Mídias"]
        
    try:
        idx_principal = opcoes_principais.index(st.session_state['menu_lateral'])
    except ValueError:
        idx_principal = None 
        
    selecao_principal = st.sidebar.radio("Navegação", opcoes_principais, index=idx_principal, label_visibility="collapsed")
    
    if selecao_principal and selecao_principal != st.session_state.get('last_radio_selection') and selecao_principal in opcoes_principais:
        st.session_state['menu_lateral'] = selecao_principal
        st.session_state['cliente_visualizado'] = None
        st.session_state['last_radio_selection'] = selecao_principal
        st.rerun()
            
    if selecao_principal in opcoes_principais:
        st.session_state['last_radio_selection'] = selecao_principal
        
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

if menu_selecionado in simuladores_dict: 
    css += """ <style>.stApp { background-color: #0f172a !important; }</style> """
else: 
    css += """ <style>.stApp { background-color: #f8fafc !important; }</style> """
st.markdown(css, unsafe_allow_html=True)


# ==========================================
# 9. RENDERIZAÇÃO DAS TELAS
# ==========================================
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
                            st.session_state.update({
                                'usuario_logado': usuario_input,
                                'perfil_logado': USUARIOS[usuario_input]["perfil"],
                                'nome_vendedor': USUARIOS[usuario_input]["nome"],
                                'menu_lateral': "Dashboard"
                            })
                            st.rerun() 
                        else: st.error("❌ Usuário ou senha incorretos.")
    st.stop() 

# --- DASHBOARD ---
if menu_selecionado == "Dashboard":
    
    # Alerta de Assembleias
    hoje_date = datetime.today().date()
    if not df_ass.empty:
        df_prox = df_ass[(df_ass['data_dt'].dt.date >= hoje_date) & (df_ass['data_dt'].dt.date <= hoje_date + timedelta(days=3))]
        if not df_prox.empty:
            alertas = [f"**{r['descricao']}** ({r['data_dt'].strftime('%d/%m')})" for _, r in df_prox.iterrows()]
            st.warning(f"📅 **Atenção para as Assembleias nos próximos dias:** {' | '.join(alertas)}")

    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        st.markdown(f"### {cliente_nome}")
        
        if st.button("⬅️ Voltar ao Dashboard", type="primary"):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
            
        info_cliente, id_cliente_db = {}, None
        if not df_cli.empty and 'Nome' in df_cli.columns:
            busca_cli = df_cli[df_cli['Nome'] == cliente_nome]
            if not busca_cli.empty: 
                info_cliente, id_cliente_db = busca_cli.iloc[0].to_dict(), busca_cli.iloc[0].get('id')

        if not is_master: st.info("🔒 Como Vendedor, você só pode visualizar estes dados. Para alterar, contate o Administrador.")
            
        def safe_str(val, default=""):
            if pd.isna(val) or val is None or str(val).strip().lower() in ["nan", "nat", "none"]: return default
            return str(val)

        key_nome, key_tel, key_email, key_end, key_aniv, key_prof, key_renda = f"n_{cliente_nome}", f"t_{cliente_nome}", f"e_{cliente_nome}", f"en_{cliente_nome}", f"a_{cliente_nome}", f"p_{cliente_nome}", f"r_{cliente_nome}"

        if key_nome not in st.session_state: st.session_state[key_nome] = safe_str(info_cliente.get("Nome"), cliente_nome)
        if key_tel not in st.session_state: st.session_state[key_tel] = safe_str(info_cliente.get("Telefone"))
        if key_email not in st.session_state: st.session_state[key_email] = safe_str(info_cliente.get("Email"))
        if key_end not in st.session_state: st.session_state[key_end] = safe_str(info_cliente.get("Endereco"))
        if key_aniv not in st.session_state: st.session_state[key_aniv] = safe_str(info_cliente.get("Aniversario"))
        if key_prof not in st.session_state: st.session_state[key_prof] = safe_str(info_cliente.get("Profissao"))
        if key_renda not in st.session_state: st.session_state[key_renda] = safe_str(info_cliente.get("Renda"))
            
        nome_edit = st.text_input("Nome Completo", key=key_nome, disabled=not is_master)
        
        if is_master:
            col_cep_1, col_cep_2 = st.columns([1, 3])
            with col_cep_1:
                cep_busca = st.text_input("Buscar CEP p/ Endereço", key=f"cep_ed_{cliente_nome}", max_chars=9)
            if cep_busca and cep_busca != st.session_state.get(f'last_cep_ed_{cliente_nome}', ''):
                cep_limpo = ''.join(filter(str.isdigit, cep_busca))
                if len(cep_limpo) == 8:
                    try:
                        res = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
                        if res.status_code == 200 and "erro" not in res.json():
                            d_cep = res.json()
                            st.session_state[key_end] = f"{d_cep.get('logradouro','')}, Nº , {d_cep.get('bairro','')}, {d_cep.get('localidade','')}-{d_cep.get('uf','')} (CEP: {cep_busca})"
                            st.rerun()
                    except: pass
                st.session_state[f'last_cep_ed_{cliente_nome}'] = cep_busca
        
        c1, c2 = st.columns(2)
        with c1:
            endereco = st.text_input("Endereço Completo", key=key_end, disabled=not is_master)
            telefone_edit = st.text_input("Telefone", key=key_tel, on_change=lambda: st.session_state.update({key_tel: formatar_telefone(st.session_state[key_tel])}), disabled=not is_master)
            profissao_edit = st.text_input("Profissão", key=key_prof, disabled=not is_master)
        with c2:
            email = st.text_input("Email", key=key_email, disabled=not is_master)
            aniversario_edit = st.text_input("Data de Aniversário (DD/MM/AAAA)", key=key_aniv, on_change=lambda: st.session_state.update({key_aniv: formatar_data(st.session_state[key_aniv])}), disabled=not is_master, placeholder="DD/MM/AAAA")
            renda_edit = st.text_input("Renda Mensal (R$)", key=key_renda, on_change=lambda: st.session_state.update({key_renda: formatar_moeda(st.session_state[key_renda])}), disabled=not is_master)
        
        if is_master:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Salvar Alterações Cadastrais", type="primary", use_container_width=True):
                    dados_cli = {
                        "Nome": st.session_state[key_nome], "Telefone": st.session_state[key_tel], "Email": st.session_state[key_email],
                        "Endereco": st.session_state[key_end], "Aniversario": st.session_state[key_aniv], "Profissao": st.session_state[key_prof], "Renda": st.session_state[key_renda]
                    }
                    try:
                        if id_cliente_db: supabase.table("clientes").update(dados_cli).eq("id", int(id_cliente_db)).execute()
                        else:
                            dados_cli["Data_Cadastro"] = datetime.today().strftime("%d/%m/%Y")
                            supabase.table("clientes").insert([dados_cli]).execute()
                        
                        if st.session_state[key_nome] != cliente_nome:
                            supabase.table("vendas").update({"NOME": st.session_state[key_nome]}).eq("NOME", cliente_nome).execute()
                            st.session_state['cliente_visualizado'] = st.session_state[key_nome]
                        st.success("Dados atualizados com sucesso!"); st.rerun()
                    except Exception as e: st.error(f"❌ Erro ao salvar: {e}")

            with col_b2:
                if st.button("🚨 Excluir Cliente (Apagar Todas as Cotas)", use_container_width=True):
                    if id_cliente_db: supabase.table("clientes").delete().eq("id", int(id_cliente_db)).execute()
                    supabase.table("vendas").delete().eq("NOME", cliente_nome).execute()
                    st.session_state['cliente_visualizado'] = None; st.session_state['key_tabela'] += 1; st.rerun()

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        if not df_vendas_global.empty:
            cotas_cliente = df_vendas_global[df_vendas_global['Nome do cliente'] == cliente_nome].copy()
            if not cotas_cliente.empty:
                info_a, info_b = st.columns(2)
                info_a.metric("Total de Cotas Adquiridas", len(cotas_cliente))
                info_b.metric("Volume Total Investido", formatar_brl_puro(cotas_cliente['Valor_Numerico'].sum()))
                
                # Formatando a data antes de exibir na tabela
                cotas_cliente['Valor Formatado'] = cotas_cliente['Valor_Numerico'].apply(formatar_brl_puro)
                cotas_cliente['Data da Venda'] = cotas_cliente['Data_Real'].apply(formatar_data_br)
                
                ficha_display = cotas_cliente[['Data da Venda', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'Valor Formatado', 'STATUS', 'VENDEDOR']].rename(columns={'ADMINISTRADORA': 'Administradora', 'PRODUTO': 'Produto', 'GRUPO': 'Grupo', 'COTA': 'Cota', 'Valor Formatado': 'Valor (R$)', 'STATUS': 'Status', 'VENDEDOR': 'Vendedor'})
                estilo_ficha = ficha_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_ficha, use_container_width=True, hide_index=True)
                
                with st.expander("⚙️ Atualizar Status, Data e Gerenciar Cota", expanded=False):
                    opcoes_cotas = cotas_cliente.apply(lambda r: f"ID:{r['id']} | Grupo: {r['GRUPO']} / Cota: {r['COTA']} - Valor: {r['Valor Formatado']}", axis=1).tolist()
                    c_sel, _ = st.columns([3, 1])
                    with c_sel: cota_selecionada = st.selectbox("Selecione a cota que deseja gerenciar:", [""] + opcoes_cotas)
                        
                    if cota_selecionada:
                        id_cota = int(cota_selecionada.split(" | ")[0].replace("ID:", ""))
                        cota_info = cotas_cliente[cotas_cliente['id'] == id_cota].iloc[0]
                        vendedor_atual = cota_info['VENDEDOR']
                        status_atual = cota_info['STATUS']
                        data_atual_str = cota_info['DATA']
                        grupo_atual = cota_info['GRUPO']
                        cota_atual = cota_info['COTA']
                        
                        if status_atual == "Vendido" or not status_atual: status_atual = "Em Andamento"
                        
                        try:
                            data_atual_obj = pd.to_datetime(data_atual_str, format="%d/%m/%Y", errors='coerce').date()
                            if pd.isna(data_atual_obj): data_atual_obj = datetime.today().date()
                        except:
                            data_atual_obj = datetime.today().date()
                        
                        c_ed1, c_ed2, c_ed3 = st.columns(3)
                        with c_ed1: novo_status = st.selectbox("Status", ["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"], index=["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"].index(status_atual))
                        with c_ed2:
                            opts_v = ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]
                            novo_vendedor = st.selectbox("Vendedor", opts_v, index=opts_v.index(vendedor_atual) if vendedor_atual in opts_v else 0) if is_master else st.text_input("Vendedor", value=vendedor_atual, disabled=True)
                        with c_ed3: nova_data = st.date_input("Data da Venda", value=data_atual_obj, format="DD/MM/YYYY") if is_master else st.text_input("Data da Venda", value=formatar_data_br(cota_info['Data_Real']), disabled=True)

                        c_ed4, c_ed5 = st.columns(2)
                        with c_ed4: novo_grupo = st.text_input("Grupo", value=grupo_atual, disabled=not is_master)
                        with c_ed5: nova_cota = st.text_input("Cota", value=cota_atual, disabled=not is_master)
                                
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.button("💾 Salvar Alterações na Cota", type="primary", use_container_width=True):
                                data_formatada = nova_data.strftime("%d/%m/%Y") if not isinstance(nova_data, str) else nova_data
                                supabase.table("vendas").update({"VENDEDOR": novo_vendedor, "STATUS": novo_status, "DATA": data_formatada, "GRUPO": novo_grupo, "COTA": nova_cota}).eq("id", id_cota).execute()
                                st.success("Cota atualizada com sucesso!"); st.rerun()
                        with col_b2:
                            if is_master and st.button("🚨 Apagar Esta Cota", use_container_width=True):
                                supabase.table("vendas").delete().eq("id", id_cota).execute()
                                st.success("Cota apagada com sucesso!"); st.rerun()

                st.subheader("📈 Previsão de Comissionamento")
                df_parcelas, vendas_sem_data = gerar_tabela_parcelas(cotas_cliente, df_vendas_global, df_admin, cfg, status_dict)
                if vendas_sem_data: st.warning(f"⚠️ Algumas vendas estão sem data: {', '.join(vendas_sem_data)}")

                if not df_parcelas.empty:
                    df_view_cli = df_parcelas[df_parcelas['Vendedor Recebe'] > 0].copy() if not is_master else df_parcelas.copy()
                    if not df_view_cli.empty:
                        for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']: df_view_cli[col] = df_view_cli[col].apply(formatar_brl_puro)
                        c_conf = {"Chave": None, "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True)}
                        c_hide = ['Cliente', 'Produto', 'Vendedor', 'data_pagamento_dt'] + (["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"] if not is_master else [])
                        df_final_cli = df_view_cli.drop(columns=c_hide).reset_index(drop=True)
                        
                        edited_df_cli = st.data_editor(df_final_cli, disabled=[c for c in df_final_cli.columns if c != "Status"], column_config=c_conf, use_container_width=True, hide_index=True)
                        if is_master and st.button("💾 Salvar Status de Pagamento (Cliente)", type="primary"):
                            if salvar_status_comissoes(edited_df_cli, df_final_cli): st.success("Atualizados!"); st.rerun()
                else: st.info("Aguardando configurações de regras para gerar a previsão.")
            else: st.warning("Nenhuma cota encontrada.")

    else:
        df_view = df_vendas_global.copy()
        if not is_master: df_view = df_view[df_view['VENDEDOR'] == st.session_state['nome_vendedor']]

        col_t1, col_t2 = st.columns([4, 1])
        with col_t2:
            st.write("")
            if st.button("Nova Venda", use_container_width=True, type="primary"): st.session_state['menu_lateral'] = "Nova Venda"; st.rerun()
        
        c_f1, c_f2, c_f3, c_f4 = st.columns([1.5, 1.5, 1, 1])
        with c_f1:
            ft_cli = st.selectbox("⏳ Filtro:", ["Últimos 5 Cadastros", "Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
            if ft_cli == "Período Personalizado":
                cd1, cd2 = st.columns(2)
                with cd1: p_ini = st.date_input("Início", format="DD/MM/YYYY")
                with cd2: p_fim = st.date_input("Fim", format="DD/MM/YYYY")
        with c_f2: busca_nome = st.text_input("🔍 Buscar Cliente:")
        with c_f3: busca_grupo = st.text_input("📦 Grupo:")
        with c_f4: busca_cota = st.text_input("🔢 Cota:")

        hoje = datetime.today()
        df_view = df_view.sort_values(by="Data_Real", ascending=False)
        
        if ft_cli == "Últimos 5 Cadastros" and not (busca_nome or busca_grupo or busca_cota): df_view = df_view.head(5)
        elif ft_cli != "Todos os Clientes" and ft_cli != "Últimos 5 Cadastros":
            mask = df_view['Data_Real'].notna()
            if ft_cli == "Mês Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.month == hoje.month) & (df_view['Data_Real'].dt.year == hoje.year)]
            elif ft_cli == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_view = df_view[mask & (df_view['Data_Real'].dt.month == ma) & (df_view['Data_Real'].dt.year == aa)]
            elif ft_cli == "Ano Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.year == hoje.year)]
            elif ft_cli == "Período Personalizado": df_view = df_view[mask & (df_view['Data_Real'].dt.date >= p_ini) & (df_view['Data_Real'].dt.date <= p_fim)]

        if busca_nome: df_view = df_view[df_view['Nome do cliente'].astype(str).str.contains(busca_nome.strip(), case=False, na=False)]
        if busca_grupo: df_view = df_view[df_view['GRUPO'].astype(str).str.contains(busca_grupo.strip(), case=False, na=False)]
        if busca_cota: df_view = df_view[df_view['COTA'].astype(str).str.contains(busca_cota.strip(), case=False, na=False)]

        if not df_view.empty:
            st.write("Clique em uma linha para ver os detalhes do cliente:")
            df_tab = df_view.copy()
            df_tab['Grupo e Cota'] = df_tab.apply(lambda x: f"{x['GRUPO']}/{x['COTA']}", axis=1)
            df_tab['Valor Formatado'] = df_tab['Valor_Numerico'].apply(formatar_brl_puro)
            
            # Formatando a data da coluna Data_Real para ficar certinho DD/MM/YYYY
            df_tab['Data da Venda'] = df_tab['Data_Real'].apply(formatar_data_br)
            
            df_tab = df_tab[['Nome do cliente', 'PRODUTO', 'ADMINISTRADORA', 'Grupo e Cota', 'VENDEDOR', 'Valor Formatado', 'Data da Venda']]
            df_tab.columns = ['Cliente', 'Produto', 'Administradora', 'Grupo/Cota', 'Vendedor', 'Valor', 'Data da Venda']
            
            tabela = st.dataframe(df_tab, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
            if hasattr(tabela, 'selection') and tabela.selection.rows:
                st.session_state['cliente_visualizado'] = df_tab.iloc[tabela.selection.rows[0]]['Cliente']; st.rerun()

            st.divider()
            m1, m2, m3 = st.columns(3)
            vol_total = df_view['Valor_Numerico'].sum()
            m1.metric("Volume Total (Filtro)", formatar_brl_puro(vol_total))
            m2.metric("Qtd. Cotas (Filtro)", len(df_view))
            m3.metric("Ticket Médio", formatar_brl_puro(vol_total/len(df_view) if len(df_view)>0 else 0))

            st.write("")
            st.subheader("📊 Gráficos Globais (Filtro Independente)")
            g_f1, g_f2 = st.columns(2)
            with g_f1:
                ft_graf = st.selectbox("⏳ Período para o Gráfico:", ["Mês Atual", "Mês Anterior", "Anual", "Todas as Vendas", "Período Personalizado"])
                if ft_graf == "Período Personalizado":
                    cg1, cg2 = st.columns(2)
                    with cg1: gi = st.date_input("Início", format="DD/MM/YYYY", key="g_ini")
                    with cg2: gf = st.date_input("Fim", format="DD/MM/YYYY", key="g_fim")
            with g_f2: fp_graf = st.selectbox("📦 Produto:", ["Todos", "Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
                
            df_g = df_vendas_global.copy()
            if not is_master: df_g = df_g[df_g['VENDEDOR'] == st.session_state['nome_vendedor']]
            if ft_graf != "Todas as Vendas" and not df_g.empty:
                mask = df_g['Data_Real'].notna()
                if ft_graf == "Mês Atual": df_g = df_g[mask & (df_g['Data_Real'].dt.month == hoje.month) & (df_g['Data_Real'].dt.year == hoje.year)]
                elif ft_graf == "Mês Anterior":
                    ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                    df_g = df_g[mask & (df_g['Data_Real'].dt.month == ma) & (df_g['Data_Real'].dt.year == aa)]
                elif ft_graf == "Anual": df_g = df_g[mask & (df_g['Data_Real'].dt.year == hoje.year)]
                elif ft_graf == "Período Personalizado": df_g = df_g[mask & (df_g['Data_Real'].dt.date >= gi) & (df_g['Data_Real'].dt.date <= gf)]
                
            if fp_graf != "Todos" and not df_g.empty: df_g = df_g[df_g['PRODUTO'].apply(normalizar_produto) == normalizar_produto(fp_graf)]
                
            if not df_g.empty:
                cg1, cg2 = st.columns(2)
                with cg1:
                    st.markdown("#### Vendas por Produto")
                    df_p = df_g['PRODUTO'].value_counts().reset_index()
                    df_p.columns = ['Produto', 'Quantidade']
                    st.altair_chart(alt.Chart(df_p).mark_arc(innerRadius=50).encode(theta='Quantidade', color='Produto', tooltip=['Produto', 'Quantidade']), use_container_width=True)
                with cg2:
                    st.markdown("#### Vendas por Administradora")
                    df_a = df_g['ADMINISTRADORA'].value_counts().reset_index()
                    df_a.columns = ['Administradora', 'Quantidade']
                    st.altair_chart(alt.Chart(df_a).mark_arc(innerRadius=50).encode(theta='Quantidade', color='Administradora', tooltip=['Administradora', 'Quantidade']), use_container_width=True)
        else: st.info("Nenhuma venda encontrada.")

# --- NOVA VENDA ---
elif menu_selecionado == "Nova Venda":
    st.markdown("### 📝 Cadastrar Nova Venda")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        cliente = st.text_input("Nome do Cliente *", key="v_cli")
        telefone = st.text_input("Telefone", key="v_tel", on_change=lambda: st.session_state.update({'v_tel': formatar_telefone(st.session_state.get('v_tel',''))}), placeholder="(31) 99999-9999", max_chars=15)
        profissao = st.text_input("Profissão", key="v_prof")
    with col_c2:
        email = st.text_input("Email", key="v_email")
        aniversario = st.text_input("Data de Aniversário (DD/MM/AAAA)", key="v_ani", on_change=lambda: st.session_state.update({'v_ani': formatar_data(st.session_state.get('v_ani',''))}), placeholder="DD/MM/AAAA", max_chars=10)
        renda = st.text_input("Renda Mensal (R$)", key="v_ren", on_change=lambda: st.session_state.update({'v_ren': formatar_moeda(st.session_state.get('v_ren',''))}), placeholder="R$ 0,00")
        
    st.markdown("##### Busca Rápida de Endereço")
    col_cep1, col_cep2 = st.columns([1, 3])
    with col_cep1: cep = st.text_input("CEP (Digite e clique fora)", max_chars=9)
        
    if cep and cep != st.session_state.get('last_cep', ''):
        c_limpo = ''.join(filter(str.isdigit, cep))
        if len(c_limpo) == 8:
            try:
                res = requests.get(f"https://viacep.com.br/ws/{c_limpo}/json/", timeout=5)
                if res.status_code == 200 and "erro" not in res.json():
                    d_cep = res.json()
                    st.session_state.update({'v_rua': d_cep.get("logradouro", ""), 'v_bai': d_cep.get("bairro", ""), 'v_cid': d_cep.get("localidade", ""), 'v_uf': d_cep.get("uf", "")})
                    st.success("✅ CEP Encontrado!")
            except: st.warning("⚠️ Serviço de CEP indisponível.")
        st.session_state['last_cep'] = cep

    ce1, ce2, ce3 = st.columns([2, 1, 1])
    rua = ce1.text_input("Rua/Logradouro", key="v_rua" if 'v_rua' in st.session_state else None)
    numero = ce2.text_input("Número")
    complemento = ce3.text_input("Complemento")

    ce4, ce5, ce6 = st.columns([2, 2, 1])
    bairro = ce4.text_input("Bairro", key="v_bai" if 'v_bai' in st.session_state else None)
    cidade = ce5.text_input("Cidade", key="v_cid" if 'v_cid' in st.session_state else None)
    uf = ce6.text_input("UF", max_chars=2, key="v_uf" if 'v_uf' in st.session_state else None)

    st.subheader("2. Dados da Venda")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        data = st.date_input("Data da Venda", format="DD/MM/YYYY")
        vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]) if is_master else st.session_state['nome_vendedor']
    with col_v2:
        admin = st.selectbox("Administradora *", lista_admin_bd)
        produto = st.selectbox("Produto *", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
        
    st.markdown("##### Cotas Adquiridas")
    if 'qtd_cotas' not in st.session_state: st.session_state['qtd_cotas'] = 1
    cotas_data = []
    for i in range(st.session_state['qtd_cotas']):
        st.markdown(f"**Cota {i+1}**")
        cq1, cq2, cq3 = st.columns(3)
        with cq1: grp = st.text_input(f"Grupo *", key=f"g_{i}")
        with cq2: cta = st.text_input(f"Cota *", key=f"c_{i}")
        with cq3: val_str = st.text_input(f"Valor (R$) *", key=f"v_{i}", on_change=lambda idx=i: st.session_state.update({f'v_{idx}': formatar_moeda(st.session_state.get(f'v_{idx}',''))}), placeholder="R$ 0,00")
        cotas_data.append({"grupo": grp, "cota": cta, "valor_str": val_str})

    if st.button("➕ Adicionar mais uma Cota"): st.session_state['qtd_cotas'] += 1; st.rerun()
    st.markdown("---")
    if st.button("Salvar Venda(s)", type="primary", use_container_width=True):
        if not cliente.strip() or not cotas_data[0]['grupo'].strip() or not cotas_data[0]['cota'].strip():
            st.error("❌ Preencha os campos obrigatórios (*).")
        else:
            erros_cotas = []
            for i, c in enumerate(cotas_data):
                val_limpo = ''.join(filter(str.isdigit, str(c['valor_str'])))
                if not c['grupo'].strip() or not c['cota'].strip() or (float(val_limpo)/100 if val_limpo else 0) <= 0: erros_cotas.append(str(i+1))
            if erros_cotas: st.error(f"❌ Preencha os dados da Cota: {', '.join(erros_cotas)}")
            else:
                end_completo = ", ".join([p for p in [rua, numero, complemento, bairro, cidade, uf] if p]) + (f" (CEP: {cep})" if cep else "")
                vendas_insert = []
                for c in cotas_data:
                    vf = float(''.join(filter(str.isdigit, str(c['valor_str']))))/100
                    vendas_insert.append({"NOME": cliente, "DATA": data.strftime("%d/%m/%Y"), "PRODUTO": produto, "VENDEDOR": vendedor, "GRUPO": c['grupo'], "COTA": c['cota'], "ADMINISTRADORA": admin, "STATUS": "Em Andamento", "VALOR": vf})
                supabase.table("vendas").insert(vendas_insert).execute()
                
                try:
                    if df_cli.empty or cliente not in df_cli['Nome'].tolist():
                        supabase.table("clientes").insert([{
                            "Nome": cliente, "Telefone": telefone, "Email": email, "Endereco": end_completo,
                            "Aniversario": aniversario, "Profissao": profissao, "Renda": renda, "Data_Cadastro": datetime.today().strftime("%d/%m/%Y")
                        }]).execute()
                except Exception: pass
                st.success(f"✅ {len(cotas_data)} Venda(s) salvas!"); st.session_state['qtd_cotas'] = 1

# --- ASSEMBLEIAS ---
elif menu_selecionado == "Assembleias":
    st.markdown("### 📅 Cronograma de Assembleias")
    col_m, col_a, col_btn = st.columns([1, 1, 3])
    meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    hoje = datetime.today()
    
    with col_m: m_sel = st.selectbox("Mês", meses_pt, index=hoje.month - 1)
    with col_a: a_sel = st.selectbox("Ano", range(hoje.year - 1, hoje.year + 3), index=1)
    num_m = meses_pt.index(m_sel) + 1
    
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
        ev_amanha = df_ass[df_ass['data_dt'].dt.date == amanha]['descricao'].tolist() if not df_ass.empty else []
        if ev_amanha:
            msg = f"Olá Sócios! Segue lembrete das assembleias de amanhã ({amanha.strftime('%d/%m')}): " + ", ".join(ev_amanha)
            st.link_button("📲 Enviar Lembrete WhatsApp (Amanhã)", f"https://wa.me/5531999999999?text={urllib.parse.quote(msg)}", type="primary")
        else: st.caption(f"Sem assembleias para amanhã ({amanha.strftime('%d/%m')}).")

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
        if not eventos_mes: st.info("Nenhuma assembleia cadastrada neste mês.")
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
                if st.form_submit_button("Cadastrar Nova", type="primary") and desc_ass:
                    supabase.table("assembleias").insert({"data_evento": dt_ass.strftime("%d/%m/%Y"), "descricao": desc_ass}).execute()
                    st.success("Salvo!"); st.rerun()
        with c_del:
            if not df_ass.empty:
                opts_del = df_ass.apply(lambda x: f"ID:{x['id']} | {x['data_evento']} - {x['descricao']}", axis=1).tolist()
                sel_del = st.selectbox("Selecione para Apagar:", [""] + opts_del)
                if st.button("🚨 Apagar Selecionada", use_container_width=True) and sel_del:
                    supabase.table("assembleias").delete().eq("id", int(sel_del.split(" | ")[0].replace("ID:", ""))).execute()
                    st.rerun()

# --- RELATORIOS ---
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
            if ft_rel == "Mês Atual": df_f = df_f[mask & (df_f['Data_Real'].dt.month == hoje.month) & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Quinzena Atual":
                q_ini, q_fim = (hoje.replace(day=1), hoje.replace(day=15)) if hoje.day <= 15 else (hoje.replace(day=16), hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1]))
                df_f = df_f[mask & (df_f['Data_Real'].dt.date >= q_ini.date()) & (df_f['Data_Real'].dt.date <= q_fim.date())]
            elif ft_rel == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_f = df_f[mask & (df_f['Data_Real'].dt.month == ma) & (df_f['Data_Real'].dt.year == aa)]
            elif ft_rel == "Ano Atual": df_f = df_f[mask & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Período Personalizado": df_f = df_f[mask & (df_f['Data_Real'].dt.date >= ri) & (df_f['Data_Real'].dt.date <= rf)]
                
        if not is_master: df_f = df_f[df_f['VENDEDOR'] == st.session_state['nome_vendedor']]
        st.divider()

        if df_f.empty: st.warning("Nenhuma venda neste período.")
        else:
            t1, t2, t3 = st.tabs(["👤 Vendas Por Usuário", "🏢 Por Administradora", "💰 Comissionamento (Gerar)"])
            with t1:
                rv = df_f.groupby('VENDEDOR').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                rv['Vol'] = rv['Vol'].apply(formatar_brl_puro)
                st.dataframe(rv.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
            with t2:
                ra = df_f.groupby('ADMINISTRADORA').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                ra['Vol'] = ra['Vol'].apply(formatar_brl_puro)
                st.dataframe(ra.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
            with t3:
                st.info("Para dar baixa, expanda o relatório.")
                if st.button("Gerar Relatório Detalhado", type="primary"):
                    st.session_state['tela_cheia_relatorio'] = True
                    st.session_state['rel_periodo'] = ft_rel
                    if ft_rel == "Período Personalizado": st.session_state['rel_dt_ini'], st.session_state['rel_dt_fim'] = ri, rf
                    st.rerun()
    else: st.info("Não possui vendas.")

# --- MÍDIAS (GOOGLE DRIVE) ---
elif menu_selecionado == "Mídias":
    st.markdown("### 🖼️ Portal de Mídias (Google Drive)")
    if "gcp_service_account" not in st.secrets or "DRIVE_FOLDER_IDS" not in st.secrets:
        st.warning("⚠️ O sistema ainda não possui a configuração de acesso ao Google Drive nos Secrets.")
    else:
        folder_ids = st.secrets.get("DRIVE_FOLDER_IDS", [])
        with st.spinner("Buscando arquivos..."):
            arquivos = listar_arquivos_drive(folder_ids)
        if not arquivos: st.info("Nenhum arquivo encontrado nas pastas configuradas.")
        else:
            st.success(f"Foram encontrados {len(arquivos)} arquivos.")
            cols = st.columns(4)
            for i, f in enumerate(arquivos):
                with cols[i % 4]:
                    st.markdown("<div class='media-card'>", unsafe_allow_html=True)
                    if 'image' in f.get('mimeType', '') and 'thumbnailLink' in f:
                        st.markdown(f"<img src='{f['thumbnailLink']}' class='media-img'>", unsafe_allow_html=True)
                    else: st.markdown("📄 *(Documento/Vídeo)*")
                    st.markdown(f"<div class='media-title'>{f['name']}</div>", unsafe_allow_html=True)
                    if 'webContentLink' in f: st.link_button("📥 Baixar", f['webContentLink'], use_container_width=True)
                    elif 'webViewLink' in f: st.link_button("👁️ Abrir", f['webViewLink'], use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)

# --- BAIXAR PARCELAS ---
elif menu_selecionado == "Baixar Parcelas":
    st.markdown("### Baixar Parcelas de Comissão")
    if 'cart_baixas' not in st.session_state: st.session_state['cart_baixas'] = []

    st.subheader("1. Buscar Cota")
    with st.form("b_b"):
        c1, c2 = st.columns(2)
        busca_g, busca_c = c1.text_input("Grupo"), c2.text_input("Cota")
        if st.form_submit_button("Buscar Cliente", type="primary"):
            if busca_g and busca_c:
                alvo = df_vendas_global[(df_vendas_global['GRUPO'] == busca_g.strip()) & (df_vendas_global['COTA'] == busca_c.strip())]
                st.session_state['venda_baixa_atual'] = alvo.iloc[0].to_dict() if not alvo.empty else None
                if alvo.empty: st.error("❌ Cota não encontrada.")
            else: st.warning("Preencha Grupo e Cota.")

    v_atual = st.session_state.get('venda_baixa_atual')
    if v_atual:
        st.divider()
        st.subheader("2. Configurar Parcela")
        df_p, _ = gerar_tabela_parcelas(pd.DataFrame([v_atual]), df_vendas_global, df_admin, cfg, status_dict)
        if not df_p.empty:
            st.markdown(f"**Cliente:** {v_atual.get('Nome do cliente', '')} | **Grupo:** {v_atual.get('GRUPO', '')} | **Cota:** {v_atual.get('COTA', '')}")
            pendentes = df_p[df_p['Status'] != 'PAGO']
            sug = pendentes.iloc[0]['Parcela'] if not pendentes.empty else df_p.iloc[-1]['Parcela']
            
            cp1, cp2 = st.columns(2)
            sel_parc = cp1.selectbox("Parcela a Baixar:", df_p['Parcela'].tolist(), index=df_p['Parcela'].tolist().index(sug) if sug in df_p['Parcela'].tolist() else 0)
            linha = df_p[df_p['Parcela'] == sel_parc].iloc[0]
            val_o = linha['Comissão (Bruta)']
            novo_val = cp2.number_input("Valor Recebido (R$):", value=float(val_o), step=10.0)

            rz = novo_val / val_o if val_o > 0 else 0
            n_liq, n_vend, n_breno, n_uriel = linha['Comissão (s/ Imposto)']*rz, linha['Vendedor Recebe']*rz, linha['Breno']*rz, linha['Uriel']*rz
            
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Líquido Corretora", formatar_brl_puro(n_liq)); s2.metric("Vendedor", formatar_brl_puro(n_vend))
            s3.metric("Breno", formatar_brl_puro(n_breno)); s4.metric("Uriel", formatar_brl_puro(n_uriel))
            
            st.write("")
            if st.button("Adicionar à Lista", use_container_width=True):
                if any(i['Chave'] == linha['Chave'] for i in st.session_state['cart_baixas']): st.warning("Já está na lista.")
                else:
                    st.session_state['cart_baixas'].append({"Chave": linha['Chave'], "Cliente": v_atual.get('Nome do cliente'), "Grupo": v_atual.get('GRUPO'), "Cota": v_atual.get('COTA'), "Parcela": sel_parc, "Valor Base": val_o, "Valor Pago": novo_val, "Líquido": n_liq, "Vendedor": n_vend, "Breno": n_breno, "Uriel": n_uriel, "Data Baixa": datetime.today().strftime("%d/%m/%Y")})
                    st.success("Adicionado!"); st.rerun()

    st.divider()
    st.subheader("3. Lista de Baixas")
    if st.session_state['cart_baixas']:
        df_c = pd.DataFrame(st.session_state['cart_baixas'])
        df_show = df_c[['Cliente', 'Grupo', 'Cota', 'Parcela', 'Valor Pago', 'Líquido', 'Vendedor', 'Breno', 'Uriel']].copy()
        for col in ['Valor Pago', 'Líquido', 'Vendedor', 'Breno', 'Uriel']: df_show[col] = df_show[col].apply(formatar_brl_puro)
        df_show.columns = ['Cliente', 'Grupo', 'Cota', 'Parcela', 'Valor Bruto', 'Líquido Corretora', 'Vendedor Recebe', 'Breno Recebe', 'Uriel Recebe']
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        
        st.markdown("#### 📊 Resumo dos Valores")
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Bruto", formatar_brl_puro(df_c['Valor Pago'].sum()))
        t2.metric("Líquido", formatar_brl_puro(df_c['Líquido'].sum()))
        t3.metric("Vendedores", formatar_brl_puro(df_c['Vendedor'].sum()))
        t4.metric("Sócios", formatar_brl_puro(df_c['Breno'].sum() + df_c['Uriel'].sum()))
        
        cb_a, cb_b = st.columns([3, 1])
        if cb_a.button("CONFIRMAR E DAR BAIXA", type="primary", use_container_width=True):
            for i in st.session_state['cart_baixas']:
                cv = i['Chave']
                ex = supabase.table("status_comissoes").select("id").eq("Chave_Unica", cv).execute()
                if ex.data: supabase.table("status_comissoes").update({"Status": "PAGO", "Valor_Pago": i['Valor Pago'], "Data_Pagamento": i['Data Baixa']}).eq("id", ex.data[0]['id']).execute()
                else: supabase.table("status_comissoes").insert({"Chave_Unica": cv, "Status": "PAGO", "Valor_Pago": i['Valor Pago'], "Data_Pagamento": i['Data Baixa']}).execute()
            st.session_state['cart_baixas'] = []; st.success("Sucesso!"); st.rerun()
        if cb_b.button("Limpar Lista", use_container_width=True): st.session_state['cart_baixas'] = []; st.rerun()
    else: st.info("Lista vazia.")

    st.divider()
    st.subheader("Histórico")
    c_p = [k for k, v in status_dict.items() if v == 'PAGO']
    if c_p:
        h_l = []
        for ch in c_p:
            p = ch.split('_')
            if len(p) >= 5: h_l.append({"Cliente": "_".join(p[:-4]), "Grupo": p[-4], "Cota": p[-3], "Administradora": p[-2], "Parcela": p[-1], "Status": "PAGO"})
        st.dataframe(pd.DataFrame(h_l), use_container_width=True, hide_index=True)
    else: st.info("Sem pagamentos registrados.")

# --- CONFIGURACOES DE SISTEMA ---
elif menu_selecionado == "Configurações de Sistema":
    st.markdown("### 🏢 Configurações de Sistema")
    t_cad_adm, t_regras, t_reg_int = st.tabs(["🏢 Cadastrar Admin", "📋 Regras", "👥 Regras Internas"])
    with t_cad_adm:
        with st.form("f_c_adm"):
            c1, c2 = st.columns([2, 1])
            n_adm = c1.text_input("Nome da Administradora *")
            cn_adm = c2.text_input("CNPJ")
            en_adm = st.text_input("Endereço Completo")
            if st.form_submit_button("Salvar Administradora", type="primary") and n_adm:
                supabase.table("cad_administradoras").insert({"Administradora": n_adm.upper(), "CNPJ": cn_adm, "Endereço": en_adm}).execute()
                st.success("Cadastrada!"); st.rerun()
        if not df_admin_cad.empty: st.dataframe(df_admin_cad.drop(columns=['id'], errors='ignore'), use_container_width=True, hide_index=True)
    
    with t_regras:
        if not df_admin.empty:
            df_m = df_admin.drop(columns=['Admin_Norm', 'Prod_Norm', 'id'], errors='ignore').copy()
            df_m.insert(2, 'Total Comissão', df_m.apply(lambda r: f"{sum([float(str(r.get(f'P{i}', '0')).replace('%','').strip() or 0) for i in range(1,26)]):.2f}%".replace('.',','), axis=1))
            st.dataframe(df_m.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
        
        with st.expander("➕ Nova Regra", expanded=False):
            with st.form("f_a_n"):
                c1, c2 = st.columns(2)
                na = c1.selectbox("Admin *", lista_admin_bd)
                pa = c2.selectbox("Produto *", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
                i_p = []
                for l in range(5):
                    cp = st.columns(5)
                    for c in range(5):
                        np = (l * 5) + c + 1
                        i_p.append(cp[c].number_input(f"Parcela {np}", min_value=0.0, step=0.1, key=f"n_p{np}"))
                if st.form_submit_button("Salvar", type="primary") and na != "Nenhuma administradora cadastrada":
                    nr = {"Administradora": na.upper(), "Produto": pa}
                    for i, v in enumerate(i_p): nr[f"P{i+1}"] = f"{v}%" if v > 0 else ""
                    supabase.table("administradoras").insert(nr).execute(); st.rerun()
                
        with st.expander("✏️ Editar/Excluir Regra", expanded=False):
            if not df_admin.empty:
                opts = df_admin.apply(lambda x: f"ID:{x['id']} | {x['Administradora']} - {x['Produto']}", axis=1).tolist()
                sel = st.selectbox("Selecione:", [""] + opts)
                if sel:
                    id_r = int(sel.split(" | ")[0].replace("ID:", ""))
                    r_at = df_admin[df_admin['id'] == id_r].iloc[0]
                    c1, c2 = st.columns(2)
                    e_n = c1.selectbox("Admin", lista_admin_bd, index=lista_admin_bd.index(r_at['Administradora']) if r_at['Administradora'] in lista_admin_bd else 0)
                    e_p = c2.selectbox("Produto", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"], index=obter_index_produto(r_at['Produto']))
                    e_ip = []
                    for l in range(5):
                        cp = st.columns(5)
                        for c in range(5):
                            np = (l * 5) + c + 1
                            v_f = float(str(r_at.get(f'P{np}', '')).replace('%', '').strip() or 0.0)
                            e_ip.append(cp[c].number_input(f"P {np}", min_value=0.0, step=0.1, value=v_f, key=f"e_p{np}"))
                    b1, b2 = st.columns(2)
                    if b1.button("Salvar Alterações", type="primary"):
                        r_u = {"Administradora": e_n.upper(), "Produto": e_p}
                        for i, v in enumerate(e_ip): r_u[f"P{i+1}"] = f"{v}%" if v > 0 else ""
                        supabase.table("administradoras").update(r_u).eq("id", id_r).execute(); st.rerun()
                    if b2.button("🚨 EXCLUIR"):
                        supabase.table("administradoras").delete().eq("id", id_r).execute(); st.rerun()

    with t_reg_int:
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            st.markdown("**Breno**")
            b_b = st.number_input("Breno (%)", value=parse_float_safe(cfg.get("Breno_Breno", 70.0)), step=1.0)
            b_u = st.number_input("Uriel (%)", value=parse_float_safe(cfg.get("Breno_Uriel", 30.0)), step=1.0)
        with cc2:
            st.markdown("**Uriel**")
            u_u = st.number_input("Uriel (%) ", value=parse_float_safe(cfg.get("Uriel_Uriel", 70.0)), step=1.0)
            u_b = st.number_input("Breno (%) ", value=parse_float_safe(cfg.get("Uriel_Breno", 30.0)), step=1.0)
        with cc3:
            st.markdown("**Consorbens**")
            c_b = st.number_input("Breno (%)  ", value=parse_float_safe(cfg.get("Cons_Breno", 50.0)), step=1.0)
            c_u = st.number_input("Uriel (%)  ", value=parse_float_safe(cfg.get("Cons_Uriel", 50.0)), step=1.0)
            
        st.divider()
        st.markdown("#### Vendedor Terceiro")
        ct1, ct2, ct3 = st.columns(3)
        with ct1:
            t1_max = parse_float_safe(st.text_input("N1 Até (R$)", value=str(int(parse_float_safe(cfg.get("T1_Max", 500000))))))
            t1_pct = st.number_input("Comissão N1 (%)", value=parse_float_safe(cfg.get("T1_Pct", 1.0)), step=0.1)
            t1_parc = st.number_input("Qtd N1", value=int(parse_float_safe(cfg.get("T1_Parc", 4))), step=1)
        with ct2:
            t2_max = parse_float_safe(st.text_input("N2 Até (R$) ", value=str(int(parse_float_safe(cfg.get("T2_Max", 1500000))))))
            t2_pct = st.number_input("Comissão N2 (%)", value=parse_float_safe(cfg.get("T2_Pct", 1.5)), step=0.1)
            t2_parc = st.number_input("Qtd N2", value=int(parse_float_safe(cfg.get("T2_Parc", 5))), step=1)
        with ct3:
            st.markdown("**Teto N3**")
            t3_pct = st.number_input("Comissão N3 (%)", value=parse_float_safe(cfg.get("T3_Pct", 2.0)), step=0.1)
            t3_parc = st.number_input("Qtd N3", value=int(parse_float_safe(cfg.get("T3_Parc", 5))), step=1)

        st.divider()
        imp_in = st.number_input("Imposto Nota (%)", value=parse_float_safe(cfg.get("Imposto", 7.16)), step=0.01)

        if st.button("Salvar Regras", type="primary", use_container_width=True):
            n_c = {"Breno_Breno": b_b, "Breno_Uriel": b_u, "Uriel_Uriel": u_u, "Uriel_Breno": u_b, "Cons_Breno": c_b, "Cons_Uriel": c_u, "T1_Max": t1_max, "T1_Pct": t1_pct, "T1_Parc": t1_parc, "T2_Max": t2_max, "T2_Pct": t2_pct, "T2_Parc": t2_parc, "T3_Pct": t3_pct, "T3_Parc": t3_parc, "Imposto": imp_in}
            if cfg_id: supabase.table("config_interna").update(n_c).eq("id", cfg_id).execute()
            else: supabase.table("config_interna").insert(n_c).execute()
            st.success("Atualizado!"); st.rerun()
