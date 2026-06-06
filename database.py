import streamlit as st
import pandas as pd
from supabase import create_client, Client
from utils import parse_float_safe, limpar_str_nan, normalizar_string, normalizar_produto

# ==========================================
# CONEXÃO COM O BANCO DE DADOS
# ==========================================
@st.cache_resource
def iniciar_conexao() -> Client:
    """Inicia a conexão com o Supabase usando as chaves configuradas nos Secrets"""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def carregar_tabela(supabase: Client, nome_tabela: str) -> pd.DataFrame:
    """Busca todos os dados de uma tabela específica"""
    try:
        res = supabase.table(nome_tabela).select("*").execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame()

# ==========================================
# CARREGAMENTO E LIMPEZA INICIAL DE DADOS
# ==========================================
def carregar_dados_iniciais(supabase: Client):
    """Carrega e padroniza todas as tabelas cruciais do sistema ao iniciar"""
    
    # 1. Carregar Vendas
    df_vendas_bd = carregar_tabela(supabase, "vendas")
    if not df_vendas_bd.empty:
        df_vendas_global = df_vendas_bd.copy()
        df_vendas_global.rename(columns={"NOME": "Nome do cliente"}, inplace=True)
        # Padroniza datas e números
        df_vendas_global['Data_Real'] = pd.to_datetime(df_vendas_global['DATA'], dayfirst=True, errors='coerce')
        df_vendas_global['Valor_Numerico'] = df_vendas_global['VALOR'].apply(parse_float_safe)
        df_vendas_global['GRUPO'] = df_vendas_global['GRUPO'].apply(limpar_str_nan)
        df_vendas_global['COTA'] = df_vendas_global['COTA'].apply(limpar_str_nan)
    else:
        df_vendas_global = pd.DataFrame()

    # 2. Carregar Clientes
    df_cli = carregar_tabela(supabase, "clientes")
    
    # 3. Carregar Assembleias
    df_ass = carregar_tabela(supabase, "assembleias")
    if not df_ass.empty:
        df_ass['data_dt'] = pd.to_datetime(df_ass['data_evento'], format="%d/%m/%Y", errors='coerce')

    # 4. Carregar Administradoras
    df_admin_cad = carregar_tabela(supabase, "cad_administradoras")
    lista_admin_bd = df_admin_cad['Administradora'].tolist() if not df_admin_cad.empty else ["Nenhuma administradora cadastrada"]

    # 5. Carregar Regras de Comissionamento
    df_admin = carregar_tabela(supabase, "administradoras")
    if not df_admin.empty:
        df_admin['Admin_Norm'] = df_admin['Administradora'].apply(normalizar_string)
        df_admin['Prod_Norm'] = df_admin['Produto'].apply(normalizar_produto)

    # 6. Carregar Status das Comissões (Pagas ou Pendentes)
    df_status = carregar_tabela(supabase, "status_comissoes")
    status_dict = dict(zip(df_status['Chave_Unica'], df_status['Status'])) if not df_status.empty else {}

    # 7. Carregar Configurações Internas e Impostos
    cfg_padrao = {
        "Breno_Breno": 70.0, "Breno_Uriel": 30.0, "Uriel_Uriel": 70.0, "Uriel_Breno": 30.0,
        "Cons_Breno": 50.0, "Cons_Uriel": 50.0, "T1_Max": 500000.0, "T1_Pct": 1.0, "T1_Parc": 4,
        "T2_Max": 1500000.0, "T2_Pct": 1.5, "T2_Parc": 5, "T3_Pct": 2.0, "T3_Parc": 5, "Imposto": 7.16
    }
    
    df_cfg = carregar_tabela(supabase, "config_interna")
    cfg_id = None
    if not df_cfg.empty:
        cfg = df_cfg.iloc[0].to_dict()
        cfg_id = cfg.get('id')
    else:
        # Se não houver configuração, insere o padrão
        res = supabase.table("config_interna").insert(cfg_padrao).execute()
        cfg = cfg_padrao
        cfg_id = res.data[0]['id'] if res.data else None

    return df_vendas_global, df_cli, df_ass, df_admin_cad, lista_admin_bd, df_admin, status_dict, cfg, cfg_id

# ==========================================
# FUNÇÕES DE ATUALIZAÇÃO NO BANCO
# ==========================================
def salvar_status_comissoes(supabase: Client, df_editado: pd.DataFrame, df_original: pd.DataFrame) -> bool:
    """Verifica quais linhas mudaram de status na tabela e salva no Supabase"""
    mudancas = df_editado[df_editado['Status'] != df_original['Status']]
    if not mudancas.empty:
        for _, row in mudancas.iterrows():
            chave = row['Chave']
            novo_status = row['Status']
            
            # Verifica se já existe um registro para esta parcela
            existe = supabase.table("status_comissoes").select("id").eq("Chave_Unica", chave).execute()
            
            if existe.data:
                # Atualiza o existente
                supabase.table("status_comissoes").update({"Status": novo_status}).eq("id", existe.data[0]['id']).execute()
            else:
                # Cria um novo registro
                supabase.table("status_comissoes").insert({"Chave_Unica": chave, "Status": novo_status}).execute()
        return True
    return False
