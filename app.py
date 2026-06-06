import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
import os

# ==========================================
# IMPORTAÇÃO DOS NOSSOS MÓDULOS LOCAIS
# ==========================================
from utils import carregar_ferramenta, formatar_brl_puro
from database import iniciar_conexao, carregar_dados_iniciais, salvar_status_comissoes
from regras import gerar_tabela_parcelas

from modulos.dashboard import render_dashboard
from modulos.nova_venda import render_nova_venda
from modulos.assembleias import render_assembleias
from modulos.relatorios import render_relatorios
from modulos.midias import render_midias
from modulos.baixas import render_baixas
from modulos.configuracoes import render_configuracoes

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
# Esta tela sobrepõe tudo quando ativada no módulo de Relatórios
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
            df_view = df_view[['Chave', 'Cliente', 'Produto', 'Vendedor', 'Grupo', 'Cota', 'Valor da Venda', 'Parcela', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe', 'Status', 'Data Prevista']]
            total_breno, total_uriel, total_vend = df_view['Breno'].sum(), df_view['Uriel'].sum(), df_view['Vendedor Recebe'].sum()
            
            for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']:
                df_view[col] = df_view[col].apply(formatar_brl_puro)
            
            col_config = {"Chave": None, "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True)}
            cols_to_hide = [] if is_master else ["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"]
            df_final = df_view.drop(columns=cols_to_hide).reset_index(drop=True)
            
            st.caption("Dica: Clique na coluna 'Status' para alterar. Em seguida, salve as alterações no botão vermelho.")
            edited_df = st.data_editor(df_final, disabled=[c for c in df_final.columns if c != "Status"], column_config=col_config, use_container_width=True, hide_index=True)
            
            if is_master:
                if st.button("💾 Salvar Status de Pagamento", type="primary"):
                    if salvar_status_comissoes(supabase, edited_df, df_final):
                        st.success("Status atualizados no banco de dados!")
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
# 5. ROTEADOR DE MENU LATERAL E RENDERIZAÇÃO
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

# Aplicando cor de fundo dependendo da área
if menu_selecionado in simuladores_dict: 
    css += """ <style>.stApp { background-color: #0f172a !important; }</style> """
else: 
    css += """ <style>.stApp { background-color: #f8fafc !important; }</style> """
st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 6. DISTRIBUIÇÃO DAS TELAS
# ==========================================
if menu_selecionado in simuladores_dict:
    carregar_ferramenta(simuladores_dict[menu_selecionado], PASTA_ATUAL)
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
    render_baixas(supabase, df_vendas_global, df_admin, cfg, status_dict)
elif menu_selecionado == "Configurações de Sistema":
    render_configuracoes(supabase, df_admin_cad, df_admin, lista_admin_bd, cfg, cfg_id)
