import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
import os
import base64  # Necessário para codificar imagens caso use futuramente

# ==========================================
# IMPORTAÇÃO DOS NOSSOS MÓDULOS LOCAIS
# ==========================================
from utils import carregar_ferramenta, formatar_brl_puro
from database import iniciar_conexao, carregar_dados_iniciais, salvar_status_comissoes, verificar_login_db, atualizar_senha_usuario
from regras import gerar_tabela_parcelas

from modulos.dashboard import render_dashboard
from modulos.nova_venda import render_nova_venda
from modulos.assembleias import render_assembleias
from modulos.relatorios import render_relatorios
from modulos.midias import render_midias
from modulos.baixas import render_baixas
from modulos.configuracoes import render_configuracoes
from modulos.senhas import render_senhas
from modulos.assistente import render_widget_ia, render_config_ia

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E SESSÕES
# ==========================================
st.set_page_config(page_title="Portal Consorbens", layout="wide", initial_sidebar_state="expanded")

PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))

# Inicialização de Variáveis de Sessão
for key, default in [('usuario_logado', None), ('perfil_logado', None), ('nome_vendedor', None), 
                     ('menu_lateral', "🔐 Login (Área Restrita)"), ('cliente_visualizado', None), 
                     ('key_tabela', 0), ('tela_cheia_relatorio', False)]:
    if key not in st.session_state:
        st.session_state[key] = default

is_logado = st.session_state['usuario_logado'] is not None
is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

# ==========================================
# 2. INICIAR BANCO DE DADOS
# ==========================================
try:
    supabase = iniciar_conexao()
    # Carrega as tabelas uma única vez e distribui para os módulos
    (df_vendas_global, df_cli, df_ass, df_admin_cad, 
     lista_admin_bd, df_admin, status_dict, cfg, cfg_id) = carregar_dados_iniciais(supabase)
except Exception as e:
    st.error(f"⚠️ Erro ao conectar com o Supabase. Detalhes: {e}")
    st.stop()

# ==========================================
# 3. LÓGICA DE TELA CHEIA (RELATÓRIO)
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
        st.warning(f"⚠️ **Atenção:** As seguintes vendas estão sem data preenchida: **{', '.join(vendas_sem_data)}**.")

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
            if hoje.day <= 15: q_ini, q_fim = hoje.replace(day=1), hoje.replace(day=15)
            else: q_ini, q_fim = hoje.replace(day=16), hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.date >= q_ini.date()) & (df_view['data_pagamento_dt'].dt.date <= q_fim.date())]
        elif ft_rel == "Mês Anterior":
            ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.month == ma) & (df_view['data_pagamento_dt'].dt.year == aa)]
        elif ft_rel == "Ano Atual":
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.year == hoje.year)]
        elif ft_rel == "Período Personalizado":
            ri, rf = st.session_state['rel_dt_ini'], st.session_state['rel_dt_fim']
            df_view = df_view[mask & (df_view['data_pagamento_dt'].dt.date >= ri) & (df_view['data_pagamento_dt'].dt.date <= rf)]
            
        if not mostrar_pagos:
            df_view = df_view[df_view['Status'] != 'PAGO']
            
        if not df_view.empty:
            df_view = df_view[['Chave', 'Cliente', 'Produto', 'Vendedor', 'Grupo', 'Cota', 'Valor da Venda', 'Parcela', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe', 'Status', 'Data Recebimento']]
            total_breno, total_uriel, total_vend = df_view['Breno'].sum(), df_view['Uriel'].sum(), df_view['Vendedor Recebe'].sum()
            
            for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']:
                df_view[col] = df_view[col].apply(formatar_brl_puro)
            
            col_config = {
                "Chave": None, 
                "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True),
                "Data Recebimento": st.column_config.TextColumn("Data Recebimento", disabled=not is_master)
            }
            cols_to_hide = [] if is_master else ["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"]
            df_final = df_view.drop(columns=cols_to_hide).reset_index(drop=True)
            
            st.caption("Dica: Clique em 'Status' ou 'Data Recebimento' para alterar. Em seguida, salve as alterações no botão vermelho.")
            
            cols_editaveis = ["Status", "Data Recebimento"] if is_master else []
            edited_df = st.data_editor(df_final, disabled=[c for c in df_final.columns if c not in cols_editaveis], column_config=col_config, use_container_width=True, hide_index=True)
            
            if is_master:
                if st.button("💾 Salvar Status de Pagamento", type="primary"):
                    if salvar_status_comissoes(supabase, edited_df, df_final):
                        st.success("Status e Datas atualizados no banco de dados!")
                        st.rerun()
                    else: 
                        st.info("Nenhuma alteração detectada.")
                        
                st.divider()
                st.markdown("#### 💵 Total do Período (Apenas o visualizado acima)")
                mt1, mt2, mt3 = st.columns(3)
                mt1.metric("Breno (Sócios)", formatar_brl_puro(total_breno))
                mt2.metric("Uriel (Sócios)", formatar_brl_puro(total_uriel))
                mt3.metric("Vendedores", formatar_brl_puro(total_vend))
        else:
            st.success("Nenhuma comissão pendente para exibir!")
    else:
        st.info("O sistema ainda não possui vendas para calcular a comissão.")
    st.stop() 

# ==========================================
# 4. CSS CUSTOMIZADO
# ==========================================
css = """
<style>
    /* ==========================================================
       DESIGN SYSTEM — Portal Consorbens (apenas visual)
       Fonte, cores, sombras, transições e componentes premium.
       ========================================================== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --brand: #e74c3c;
        --brand-dark: #c0392b;
        --brand-soft: rgba(231, 76, 60, 0.12);
        --green: #22a559;
        --green-dark: #178a47;
        --ink: #0f172a;
        --muted: #64748b;
        --line: #eef2f7;
        --card: #ffffff;
        --shadow-sm: 0 1px 3px rgba(15,23,42,0.04);
        --shadow-md: 0 4px 20px rgba(15,23,42,0.06);
        --shadow-lg: 0 12px 34px rgba(15,23,42,0.10);
        --radius: 14px;
    }

    /* ---- Tipografia global ---- */
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    input, textarea, button, select, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }
    .block-container { padding-top: 1.6rem; padding-bottom: 2rem; padding-left: 2rem; padding-right: 2rem; max-width: 1400px; }
    h1, h2, h3, h4, h5 { font-family: 'Inter', sans-serif !important; color: var(--ink); letter-spacing: -0.015em; font-weight: 700 !important; }
    h3 { margin-bottom: 0.5rem !important; margin-top: 0.5rem !important; }

    /* ---- Suave fade-in no conteúdo principal ---- */
    [data-testid="stMain"] .block-container { animation: cbFade 0.35s ease; }
    @keyframes cbFade { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

    /* ---- Botões (transição + arredondado + elevação no hover) ---- */
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button,
    [data-testid="stLinkButton"] a {
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: transform 0.16s ease, box-shadow 0.16s ease, background-color 0.16s ease, border-color 0.16s ease, color 0.16s ease !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        transform: translateY(-1px);
        box-shadow: var(--shadow-md);
        border-color: var(--brand) !important;
        color: var(--brand) !important;
    }
    button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--green), var(--green-dark)) !important;
        border: none !important; color: #fff !important; font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(34,165,89,0.30) !important;
    }
    button[kind="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 22px rgba(34,165,89,0.42) !important;
        color: #fff !important;
    }

    /* ---- Inputs / Selects / Datas (foco na cor da marca) ---- */
    .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
    [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="base-input"] {
        border-radius: 10px !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
    }
    [data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within,
    .stTextArea textarea:focus, [data-baseweb="base-input"]:focus-within {
        border-color: var(--brand) !important;
        box-shadow: 0 0 0 3px var(--brand-soft) !important;
    }

    /* ---- Métricas viram cards elegantes ---- */
    [data-testid="stMetric"] {
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 16px 18px;
        box-shadow: var(--shadow-sm);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    [data-testid="stMetric"]:hover { transform: translateY(-3px); box-shadow: var(--shadow-lg); }
    [data-testid="stMetricValue"] { font-size: 1.7rem !important; font-weight: 800 !important; color: var(--ink); }
    [data-testid="stMetricLabel"] { color: var(--muted) !important; font-weight: 600 !important; }

    /* ---- Abas (tabs) modernas ---- */
    [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--line); }
    button[data-baseweb="tab"] {
        font-size: 15px !important; font-weight: 600 !important;
        border-radius: 10px 10px 0 0 !important; padding: 8px 16px !important;
        transition: background-color 0.18s ease, color 0.18s ease !important;
    }
    button[data-baseweb="tab"]:hover { background: #f1f5f9; color: var(--brand) !important; }
    button[data-baseweb="tab"][aria-selected="true"] { color: var(--brand) !important; }
    [data-baseweb="tab-highlight"] { background: var(--brand) !important; height: 3px !important; border-radius: 3px; }

    /* ---- Expanders viram cards ---- */
    [data-testid="stExpander"] {
        border: 1px solid var(--line) !important;
        border-radius: var(--radius) !important;
        box-shadow: var(--shadow-sm);
        background: var(--card);
        overflow: hidden;
        transition: box-shadow 0.2s ease;
    }
    [data-testid="stExpander"]:hover { box-shadow: var(--shadow-md); }
    [data-testid="stExpander"] summary { font-weight: 600 !important; }
    [data-testid="stExpander"] summary:hover { color: var(--brand) !important; }

    /* ---- Formulários viram cards ---- */
    [data-testid="stForm"] {
        border: 1px solid var(--line) !important;
        border-radius: 16px !important;
        padding: 22px !important;
        box-shadow: var(--shadow-md);
        background: var(--card);
    }

    /* ---- Tabelas / DataFrames arredondados ---- */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border-radius: 12px !important;
        overflow: hidden;
        border: 1px solid var(--line) !important;
        box-shadow: var(--shadow-sm);
    }

    /* ---- Alertas (success/info/warning/error) ---- */
    [data-testid="stAlert"] {
        border-radius: 12px !important;
        border: none !important;
        box-shadow: var(--shadow-sm);
    }

    /* ---- Barra de rolagem premium ---- */
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

    /* ==========================================================
       SIDEBAR
       ========================================================== */
    [data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid var(--line) !important; box-shadow: 4px 0 24px rgba(15,23,42,0.03); }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div { color: #0f172a !important; }
    [data-testid="stSidebar"] hr { border-bottom-color: #e2e8f0 !important; margin-top: 0.5rem !important; margin-bottom: 0.5rem !important; }
    [data-testid="stSidebar"] button { border: 1px solid #cbd5e1 !important; background-color: #f8fafc !important; }
    [data-testid="stSidebar"] [role="radiogroup"] label { transition: color 0.15s ease; border-radius: 8px; }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover { color: var(--brand) !important; }
    /* Links externos no menu (ex: Cartas Contempladas) com o mesmo visual dos botões */
    [data-testid="stSidebar"] [data-testid="stLinkButton"] a, [data-testid="stSidebar"] a[kind="secondary"] { border: 1px solid #cbd5e1 !important; background-color: #f8fafc !important; color: #0f172a !important; text-decoration: none !important; }
    [data-testid="stSidebar"] [data-testid="stLinkButton"] a:hover, [data-testid="stSidebar"] a[kind="secondary"]:hover { border-color: #e74c3c !important; color: #e74c3c !important; }
    /* Link externo no menu de visitante, com o mesmo visual das opções (bolinha + texto).
       As margens negativas encostam o link nas opções de cima e de baixo. */
    [data-testid="stSidebar"] .st-key-cartas_link { margin-top: -2.1rem !important; }
    [data-testid="stSidebar"] .st-key-menu_sim { margin-top: -1.7rem !important; }
    [data-testid="stSidebar"] .menu-link-externo { display: flex !important; align-items: center; gap: 9px; text-decoration: none !important; padding: 0 0 0 1px; height: 22.4px; }
    [data-testid="stSidebar"] .menu-link-bolinha { width: 14px; height: 14px; border-radius: 50%; background-color: #f0f2f6; flex: 0 0 auto; box-sizing: border-box; }
    [data-testid="stSidebar"] .menu-link-texto { color: #0f172a !important; font-size: 14px; line-height: 22.4px; }
    [data-testid="stSidebar"] .menu-link-externo:hover .menu-link-bolinha { background-color: #e2e8f0; }
    [data-testid="stSidebar"] .menu-link-externo:hover .menu-link-texto { color: #e74c3c !important; }
    header[data-testid="stHeader"] { background-color: transparent !important; }

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

    /* ==========================================================
       CAMADA PREMIUM v2 — mais profundidade e identidade
       ========================================================== */
    /* Sidebar com leve gradiente e respiro */
    [data-testid="stSidebar"] > div:first-child { background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%) !important; }
    [data-testid="stSidebar"] [data-testid="stImage"] { padding: 4px 6px 2px; }

    /* Menu lateral em PÍLULAS com item ativo destacado (marca) */
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        padding: 3px 12px !important;
        border-radius: 10px !important;
        margin: 1px 0 !important;
        transition: background-color 0.15s ease, color 0.15s ease !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:hover { background-color: #f1f5f9 !important; }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) { background-color: var(--brand-soft) !important; }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p { color: var(--brand) !important; font-weight: 700 !important; }

    /* Cards com sombra mais rica */
    [data-testid="stMetric"] { border-radius: 16px !important; box-shadow: 0 6px 22px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04) !important; }
    [data-testid="stMetric"]:hover { box-shadow: 0 16px 40px rgba(15,23,42,0.12) !important; }
    [data-testid="stExpander"] { border-radius: 16px !important; box-shadow: 0 6px 22px rgba(15,23,42,0.05) !important; }
    [data-testid="stForm"] { border-radius: 18px !important; box-shadow: 0 10px 30px rgba(15,23,42,0.07) !important; }
    [data-testid="stDataFrame"] { box-shadow: 0 6px 22px rgba(15,23,42,0.05) !important; }

    /* Abas com destaque de fundo no item ativo */
    button[data-baseweb="tab"] { color: #64748b !important; }
    button[data-baseweb="tab"][aria-selected="true"] { background: var(--brand-soft) !important; color: var(--brand) !important; }

    /* Títulos das telas com mais presença */
    [data-testid="stMain"] h1, [data-testid="stMain"] h2 { font-weight: 800 !important; letter-spacing: -0.025em !important; }
    [data-testid="stMain"] h3 { font-weight: 700 !important; }

    /* Divider mais suave */
    [data-testid="stMain"] hr { border-color: var(--line) !important; margin: 1.1rem 0 !important; }
</style>
"""

# ==========================================
# 5. ROTEADOR DE MENU LATERAL E RENDERIZAÇÃO
# ==========================================
simuladores_dict = {
    "🏍️ Simulador Yamaha": "yamaha.html",
    "🚀 Simulador Itaú V 2.0": "itau_v2.html",
    "🏦 Simulador Itaú": "itau.html",
    "🎯 Oportunidades Itaú": "guia.html",
    "⚖️ Financiamento x Consórcio": "comparador.html"
}

logo_path = os.path.join(PASTA_ATUAL, "logo.png")
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)
st.sidebar.markdown("<br>", unsafe_allow_html=True) 

if not is_logado:
    OPC_LOGIN = "🔐 Login (Área Restrita)"
    opcoes_sim = list(simuladores_dict.keys())

    if st.session_state['menu_lateral'] not in [OPC_LOGIN] + opcoes_sim:
        st.session_state['menu_lateral'] = OPC_LOGIN
    menu_atual = st.session_state['menu_lateral']

    # O menu é dividido em dois blocos para encaixar o link externo entre eles.
    # Só um dos dois fica marcado por vez (o outro é zerado no on_change).
    if 'menu_login' not in st.session_state:
        st.session_state['menu_login'] = OPC_LOGIN if menu_atual == OPC_LOGIN else None
    if 'menu_sim' not in st.session_state:
        st.session_state['menu_sim'] = menu_atual if menu_atual in opcoes_sim else None

    def _selecionou_login():
        st.session_state['menu_lateral'] = OPC_LOGIN
        st.session_state['menu_sim'] = None

    def _selecionou_simulador():
        st.session_state['menu_lateral'] = st.session_state['menu_sim']
        st.session_state['menu_login'] = None

    link_cartas = """
    <div class="menu-link-wrap">
        <a href="https://consorbensmg.com.br/admin/" target="_blank" class="menu-link-externo">
            <span class="menu-link-bolinha"></span><span class="menu-link-texto">📄 Cartas Contempladas</span>
        </a>
    </div>
    """

    st.sidebar.radio(" ", [OPC_LOGIN], key="menu_login", label_visibility="collapsed", on_change=_selecionou_login)
    with st.sidebar.container(key="cartas_link"):
        st.markdown(link_cartas, unsafe_allow_html=True)
    st.sidebar.radio(" ", opcoes_sim, key="menu_sim", label_visibility="collapsed", on_change=_selecionou_simulador)
else:
    st.sidebar.divider() 
    
    # Condicional que adiciona a aba "Senhas" e "Base de Conhecimento" dependendo do perfil
    if is_master:
        opcoes_principais = ["Dashboard", "Nova Venda", "Assembleias", "Relatórios", "Mídias", "Baixar Parcelas", "Configurações de Sistema", "Senhas", "Base de Conhecimento"] 
    else:
        opcoes_principais = ["Dashboard", "Nova Venda", "Assembleias", "Relatórios", "Mídias"]
        
    try: idx_principal = opcoes_principais.index(st.session_state['menu_lateral'])
    except ValueError: idx_principal = None 
        
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
        st.link_button("📄 Cartas Contempladas", "https://consorbensmg.com.br/admin/", use_container_width=True)
        for sim in simuladores_dict.keys():
            btn_type = "primary" if st.session_state['menu_lateral'] == sim else "secondary"
            if st.button(sim, use_container_width=True, type=btn_type):
                st.session_state['menu_lateral'] = sim
                st.session_state['cliente_visualizado'] = None
                st.session_state['last_radio_selection'] = None
                st.rerun()
                
    st.sidebar.write("")
    
    # --- CHAMA O WIDGET FLUTUANTE DA IA AQUI ---
    render_widget_ia(supabase)
    
    if st.sidebar.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

menu_selecionado = st.session_state['menu_lateral']

# Aplicando cor de fundo dependendo da área
if menu_selecionado in simuladores_dict: 
    css += """ <style>.stApp { background-color: #0f172a !important; }</style> """
else:
    css += """ <style>.stApp { background: radial-gradient(1100px 480px at 100% -6%, rgba(231,76,60,0.06), transparent 55%), linear-gradient(180deg, #f7f9fc 0%, #eaeef4 100%) !important; background-attachment: fixed !important; }</style> """
st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 6. DISTRIBUIÇÃO DAS TELAS
# ==========================================
if menu_selecionado in simuladores_dict:
    if menu_selecionado == "🚀 Simulador Itaú V 2.0":
        from modulos.itau_v2 import render_itau_v2
        render_itau_v2(PASTA_ATUAL)
    else:
        carregar_ferramenta(simuladores_dict[menu_selecionado], PASTA_ATUAL)
    st.stop()

if not is_logado:
    if menu_selecionado == "🔐 Login (Área Restrita)":
        st.markdown("<br><br>", unsafe_allow_html=True)
        _, col_meio, _ = st.columns([1, 1.3, 1])
        
        with col_meio:
            t_login, t_senha = st.tabs(["🔐 Entrar no Sistema", "🔄 Alterar Minha Senha"])
            
            with t_login:
                with st.form("form_login"):
                    st.markdown("##### Selecione ou digite as suas credenciais")
                    opcoes_usuarios = ["Breno", "Uriel", "Outro (Digitar Manualmente / Novo Usuário)"]
                    usuario_sel = st.selectbox("Utilizador", opcoes_usuarios, index=0)
                    
                    if usuario_sel == "Outro (Digitar Manualmente / Novo Usuário)":
                        usuario_input = st.text_input("Introduza o Login do Utilizador").strip()
                    else:
                        usuario_input = usuario_sel.lower()
                        
                    senha_input = st.text_input("Palavra-passe (Senha)", type="password")
                    st.write("") 
                    
                    if st.form_submit_button("ENTRAR", type="primary", use_container_width=True):
                        if not usuario_input:
                            st.error("❌ Por favor, introduza o nome do utilizador.")
                        else:
                            user_valido = verificar_login_db(supabase, usuario_input, senha_input)
                            
                            if user_valido:
                                st.session_state.update({
                                    'usuario_logado': user_valido["login"],
                                    'perfil_logado': user_valido["perfil"],
                                    'nome_vendedor': user_valido["nome"],
                                    'menu_lateral': "Dashboard"
                                })
                                st.rerun() 
                            else: 
                                st.error("❌ Utilizador ou senha incorretos.")
                                
            with t_senha:
                with st.form("form_alterar_senha"):
                    st.markdown("##### Atualizar Palavra-passe")
                    alt_usuario = st.text_input("Confirme o seu Usuário (Login)").strip()
                    alt_senha_antiga = st.text_input("Senha Atual", type="password")
                    alt_senha_nova = st.text_input("Nova Senha", type="password")
                    alt_senha_conf = st.text_input("Confirmar Nova Senha", type="password")
                    
                    if st.form_submit_button("SALVAR NOVA SENHA", type="primary", use_container_width=True):
                        if not alt_usuario or not alt_senha_antiga or not alt_senha_nova:
                            st.error("❌ Preencha todos os campos obrigatórios.")
                        elif alt_senha_nova != alt_senha_conf:
                            st.error("❌ A nova senha e a confirmação não coincidem.")
                        else:
                            checar_atual = verificar_login_db(supabase, alt_usuario, alt_senha_antiga)
                            if checar_atual:
                                if atualizar_senha_usuario(supabase, alt_usuario, alt_senha_nova):
                                    st.success("✅ Senha atualizada com sucesso! Já pode iniciar sessão.")
                                else:
                                    st.error("❌ Erro técnico ao atualizar no banco de dados.")
                            else:
                                st.error("❌ Usuário ou Senha Atual incorretos. Operação recusada.")
    st.stop() 

# --- ROTEAMENTO PARA OS MÓDULOS ---
if menu_selecionado == "Dashboard":
    render_dashboard(supabase, df_vendas_global, df_cli, df_ass, lista_admin_bd, df_admin, status_dict, cfg)
elif menu_selecionado == "Nova Venda":
    render_nova_venda(supabase, df_cli, lista_admin_bd)
elif menu_selecionado == "Assembleias":
    render_assembleias(supabase, df_ass)
elif menu_selecionado == "Relatórios":
    render_relatorios(df_vendas_global)
elif menu_selecionado == "Mídias":
    render_midias()
elif menu_selecionado == "Baixar Parcelas":
    render_baixas(supabase, df_vendas_global, df_admin, cfg, status_dict, lista_admin_bd)
elif menu_selecionado == "Configurações de Sistema":
    render_configuracoes(supabase, df_admin_cad, df_admin, lista_admin_bd, cfg, cfg_id)
elif menu_selecionado == "Senhas":
    render_senhas(supabase)
elif menu_selecionado == "Base de Conhecimento":
    render_config_ia(supabase)
