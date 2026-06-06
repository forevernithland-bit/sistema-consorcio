import streamlit as st
import pandas as pd
from datetime import datetime
import unicodedata
import os
import streamlit.components.v1 as components
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# FUNÇÕES DE CARREGAMENTO DE HTML (SIMULADORES)
# ==========================================
def carregar_ferramenta(nome_arquivo, pasta_atual):
    caminho_completo = os.path.join(pasta_atual, nome_arquivo)
    try:
        with open(caminho_completo, 'r', encoding='utf-8') as f:
            html_code = f.read()
            components.html(html_code, height=900, scrolling=True)
    except FileNotFoundError:
        st.error(f"⚠️ O arquivo {nome_arquivo} não foi encontrado no servidor! Verifique se ele está no GitHub.")

# ==========================================
# MÁSCARAS E FORMATADORES
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

# ==========================================
# NORMALIZADORES DE TEXTO E PRODUTO
# ==========================================
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

# ==========================================
# CALLBACKS DE INPUT DO STREAMLIT
# ==========================================
def mascara_tel_nv(): 
    st.session_state['tel_nv'] = formatar_telefone(st.session_state.get('tel_nv', ''))

def mascara_aniv_nv(): 
    st.session_state['aniv_nv'] = formatar_data(st.session_state.get('aniv_nv', ''))

def mascara_renda_nv(): 
    st.session_state['renda_nv'] = formatar_moeda(st.session_state.get('renda_nv', ''))

# ==========================================
# INTEGRAÇÃO COM GOOGLE DRIVE
# ==========================================
@st.cache_resource
def get_drive_service():
    """Autentica com o Google Drive usando as credenciais do Streamlit Secrets"""
    try:
        if "gcp_service_account" not in st.secrets:
            return None
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
