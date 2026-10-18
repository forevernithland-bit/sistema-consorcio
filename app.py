import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import calendar
import os
import html
import base64  # Necessário para codificar imagens caso use futuramente

# ==========================================
# IMPORTAÇÃO DOS NOSSOS MÓDULOS LOCAIS
# ==========================================
from utils import carregar_ferramenta, formatar_brl_puro
from database import (iniciar_conexao, iniciar_conexao_site, carregar_dados_iniciais, salvar_status_comissoes,
                      verificar_login_db, autenticar, atualizar_senha_usuario, carregar_sessao_usuario)
from seguranca import permissoes_efetivas, MENU_PARA_PERMISSAO, validar_forca
from site_usuarios import sincronizar_site
from regras import gerar_tabela_parcelas
from escopo import filtrar_por_vendedor

from modulos.dashboard import render_dashboard
from modulos.nova_venda import render_nova_venda
from modulos.assembleias import render_assembleias
from modulos.relatorios import render_relatorios
from modulos.midias import render_midias
from modulos.baixas import render_baixas
from modulos.configuracoes import render_configuracoes
from modulos.senhas import render_senhas
from modulos.assistente import render_widget_ia, render_config_ia
from modulos.tema import montar_css, render_seletor_tema, css_fundo_login
from modulos.ofertar_lance import render_ofertar_lance
from modulos.emitir_boleto import render_emitir_boleto
from modulos.financeiro import render_financeiro
from modulos.robo_painel import render_robo_painel
from modulos.usuarios import render_usuarios

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

# Deep-link: ...?pg=robo (atalho na área de trabalho OU clique no "SERVER" da
# barra lateral) abre o Painel do Robô. Depois de aplicar, limpa o parâmetro
# para que um novo clique no "SERVER" torne a acionar.
_PG_MAP = {"robo": "🤖 Robô"}
try:
    _pg = (st.query_params.get("pg") or "").lower()
except Exception:
    _pg = ""
if _pg in _PG_MAP:
    st.session_state['menu_lateral'] = _PG_MAP[_pg]
    st.session_state['last_radio_selection'] = None
    try:
        st.query_params.clear()
    except Exception:
        pass

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
    st.markdown(montar_css(), unsafe_allow_html=True)
    st.markdown("## 💰 Relatório de Comissionamento Detalhado")
    
    col_bt, col_chk = st.columns([1, 3])
    with col_bt:
        if st.button("⬅️ Voltar aos Filtros", type="secondary"):
            st.session_state['tela_cheia_relatorio'] = False
            st.rerun()
    with col_chk:
        mostrar_pagos = st.checkbox("Mostrar parcelas já pagas (PAGO)", value=False)
        
    df_parcelas_todas, vendas_sem_data = gerar_tabela_parcelas(df_vendas_global, df_vendas_global, df_admin, cfg, status_dict)
    
    if vendas_sem_data and is_master:
        st.warning(f"⚠️ **Atenção:** As seguintes vendas estão sem data preenchida: **{', '.join(vendas_sem_data)}**.")

    if not df_parcelas_todas.empty:
        hoje = pd.Timestamp.today().normalize()
        mask = df_parcelas_todas['data_pagamento_dt'].notna()
        df_view = df_parcelas_todas.copy()
        
        df_view = filtrar_por_vendedor(df_view, 'Vendedor', eh_adm=is_master)
        
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
            df_view = df_view[['Chave', 'Cliente', 'Produto', 'Vendedor', 'Grupo', 'Cota', 'Valor da Venda', 'Parcela', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe', 'Tipo Vendedor', 'Parcela Vendedor', '% Vendedor', 'Referência', 'Status', 'Data Recebimento']]
            total_breno, total_uriel, total_vend = df_view['Breno'].sum(), df_view['Uriel'].sum(), df_view['Vendedor Recebe'].sum()
            
            for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']:
                df_view[col] = df_view[col].apply(formatar_brl_puro)
            df_view['% Vendedor'] = df_view['% Vendedor'].apply(lambda x: "" if pd.isna(x) else f"{x:.2f}%".replace(".", ","))
            df_view = df_view.rename(columns={'Tipo Vendedor': 'Tipo (vendedor)', 'Parcela Vendedor': 'Parc. vendedor', '% Vendedor': '% vend.'})
            
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
css = montar_css()   # CSS completo do design system (modulos/tema.py)

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

# ---- Bolinha "SERVER" (status do robô do escritório) ----
# O worker bate o ponto em robo_status.atualizado_em a cada ciclo (~30s).
# Verde se o último ponto foi há pouco; vermelho se está sem sinal.
LIMITE_SERVER_SEG = 90  # sem sinal por mais que isso => robô desligado (vermelho)


@st.cache_data(ttl=15)
def _status_robo(_sb):
    # ttl=15: o worker só bate o ponto a cada ~30s, então 15s de cache não
    # atrasa a percepção do status (limite de "desligado" é 90s) e evita bater
    # no Supabase a cada clique de navegação/rerun.
    try:
        res = _sb.table("robo_status").select("atualizado_em").eq("id", 1).execute()
        if not res.data:
            return False
        dt = pd.to_datetime(res.data[0]["atualizado_em"], utc=True)
        idade = (datetime.now(timezone.utc) - dt.to_pydatetime()).total_seconds()
        return idade <= LIMITE_SERVER_SEG
    except Exception:
        return False


@st.cache_data(ttl=15)
def _trava_login_robo(_sb):
    """(travado, desde_texto) — o robô marca isso quando erra a senha do Newcon."""
    try:
        r = (_sb.table("robo_status")
             .select("login_travado,login_travado_desde").eq("id", 1).execute())
        row = (r.data or [{}])[0]
    except Exception:
        return (False, "")
    if not row.get("login_travado"):
        return (False, "")
    try:
        desde = pd.to_datetime(row.get("login_travado_desde")).strftime("%d/%m %H:%M")
    except Exception:
        desde = str(row.get("login_travado_desde") or "")
    return (True, desde)


_online = _status_robo(supabase)
_cor = "#22c55e" if _online else "#ef4444"          # verde / vermelho
_titulo = "Robô ligado" if _online else "Robô desligado"
# "SERVER" é um botão (não um <a href>): link real recarregaria a página inteira
# e derrubaria a sessão de login. Estilizado via container com key p/ parecer selo.
st.sidebar.markdown(
    f"""
    <style>
      /* Encosta o conteúdo da sidebar no topo (sobe a bolinha SERVER o máximo possível) */
      [data-testid="stSidebarUserContent"] {{ padding-top: 0.6rem !important; }}
      section[data-testid="stSidebar"] > div:first-child {{ padding-top: 0.6rem !important; }}
      div.st-key-server_badge {{ margin: -6px 0 2px 2px; }}
      div.st-key-server_badge button {{
        background: transparent !important; border: none !important;
        box-shadow: none !important; padding: 0 !important;
        min-height: 0 !important; height: auto !important; width: auto !important;
        line-height: 1 !important;
      }}
      div.st-key-server_badge button:hover {{ opacity: .7; }}
      div.st-key-server_badge button p {{
        color: {_cor} !important; font-size: 12px !important;
        font-weight: 700 !important; letter-spacing: 1px !important; margin: 0 !important;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)
# Nome de quem está logado, no topo, na mesma linha do SERVER
_nome_topo = ""
if st.session_state.get('usuario_logado'):
    _nome_topo = str(st.session_state.get('nome_vendedor') or "").strip()
    if not _nome_topo:   # 1ª tela logo após o login: busca o nome (cache de 30 s)
        try:
            _nome_topo = str((carregar_sessao_usuario(supabase, st.session_state['usuario_logado']) or {}).get("nome") or "").strip()
        except Exception:
            _nome_topo = ""
    _nome_topo = _nome_topo or str(st.session_state['usuario_logado'])
with st.sidebar.container(key="server_badge"):
    _cb, _cn = st.columns([1, 1.7], vertical_alignment="center") if _nome_topo else (st.container(), None)
    with _cb:
        if st.button("● SERVER", key="btn_server_robo",
                     help=f"{_titulo} — abrir Painel do Robô"):
            st.session_state['menu_lateral'] = "🤖 Robô"
            st.session_state['last_radio_selection'] = None
            st.session_state['cliente_visualizado'] = None
            st.rerun()
    if _cn is not None:
        with _cn:
            st.markdown(
                f"<div title='{html.escape(_nome_topo)}' style='text-align:right;font-size:12px;font-weight:700;"
                f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.85'>👤 {html.escape(_nome_topo)}</div>",
                unsafe_allow_html=True)

logo_path = os.path.join(PASTA_ATUAL, "logo.png")
# ---- Revalida o usuário logado a cada carregamento (cache de 30 s) ----
# Desativar alguém, mudar o perfil ou as telas dele passa a valer rápido,
# sem esperar ele sair e entrar de novo.
_perm_usuario = set()
if is_logado:
    _info_usr = carregar_sessao_usuario(supabase, st.session_state['usuario_logado'])
    if (not _info_usr) or (not _info_usr.get("ativo")):
        st.session_state.clear()
        st.rerun()
    st.session_state['perfil_logado'] = _info_usr.get("perfil")
    st.session_state['nome_vendedor'] = _info_usr.get("nome")
    is_master = (_info_usr.get("perfil") == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])
    _perm_usuario = permissoes_efetivas(_info_usr.get("perfil"), _info_usr.get("permissoes"), is_master)
    st.session_state['permissoes'] = sorted(_perm_usuario)

    # Senha temporária: a pessoa precisa criar a própria antes de usar o sistema
    if _info_usr.get("trocar_senha"):
        st.markdown("### 🔐 Crie a sua senha")
        st.info("Você entrou com uma senha temporária. Defina uma senha só sua para continuar "
                "(mínimo 8 caracteres, com letras e números).")
        with st.form("form_troca_obrigatoria"):
            _n1 = st.text_input("Nova senha", type="password")
            _n2 = st.text_input("Confirmar nova senha", type="password")
            if st.form_submit_button("Salvar e continuar", type="primary"):
                _ok_f, _msg_f = validar_forca(_n1)
                if not _ok_f:
                    st.error("❌ " + _msg_f)
                elif _n1 != _n2:
                    st.error("❌ A nova senha e a confirmação não coincidem.")
                elif atualizar_senha_usuario(supabase, st.session_state['usuario_logado'], _n1):
                    from database import _buscar_usuario
                    _u = _buscar_usuario(supabase, st.session_state['usuario_logado']) or {}
                    if _u.get("acesso_site_admin"):
                        sincronizar_site(iniciar_conexao_site(), _u.get("email"), _n1, True, _u.get("site_user_id"))
                    carregar_sessao_usuario.clear()
                    st.success("Senha criada!")
                    st.rerun()
                else:
                    st.error("❌ Não consegui salvar a senha agora.")
        st.stop()

if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)
st.sidebar.markdown("<br>", unsafe_allow_html=True)

if not is_logado:
    OPC_LOGIN = "🔐 Login (Área Restrita)"

    # Sem login, o ÚNICO destino é a tela de login. Os simuladores só aparecem
    # para usuário autenticado (regra definida pelo Breno/Uriel, ago/2026).
    st.session_state['menu_lateral'] = OPC_LOGIN

    link_cartas = """
    <div class="menu-link-wrap">
        <a href="https://consorbensmg.com.br/admin/" target="_blank" class="menu-link-externo">
            <span class="menu-link-bolinha"></span><span class="menu-link-texto">📄 Cartas Contempladas</span>
        </a>
    </div>
    """

    st.sidebar.radio(" ", [OPC_LOGIN], key="menu_login", label_visibility="collapsed")
    with st.sidebar.container(key="cartas_link"):
        st.markdown(link_cartas, unsafe_allow_html=True)
else:
    st.sidebar.divider()
    
    # Menu principal. Senhas e Base de Conhecimento agora ficam DENTRO de
    # "Configurações de Sistema" (abas). Assembleias está oculto por enquanto.
    if is_master:
        opcoes_principais = ["Dashboard", "Nova Venda", "Ofertar Lance", "Emissão de Boletos", "Financeiro", "Baixar Parcelas", "Relatórios", "Mídias", "Configurações de Sistema"]
    else:
        _todas_vend = ["Dashboard", "Nova Venda", "Ofertar Lance", "Emissão de Boletos", "Relatórios", "Mídias"]
        opcoes_principais = [o for o in _todas_vend if MENU_PARA_PERMISSAO[o] in _perm_usuario]
        # a tela inicial padrão pode não estar liberada para este vendedor
        if st.session_state.get('menu_lateral') not in opcoes_principais + list(simuladores_dict) and opcoes_principais:
            st.session_state['menu_lateral'] = opcoes_principais[0]
        if not opcoes_principais and not any(MENU_PARA_PERMISSAO[x] in _perm_usuario for x in simuladores_dict):
            st.warning("Seu usuário ainda não tem nenhuma tela liberada. Fale com o administrador.")
        
    try: idx_principal = opcoes_principais.index(st.session_state['menu_lateral'])
    except ValueError: idx_principal = None 
        
    selecao_principal = st.sidebar.radio("Navegação", opcoes_principais, index=idx_principal, label_visibility="collapsed") if opcoes_principais else None
    
    if selecao_principal and selecao_principal != st.session_state.get('last_radio_selection') and selecao_principal in opcoes_principais:
        st.session_state['menu_lateral'] = selecao_principal
        st.session_state['cliente_visualizado'] = None
        st.session_state['last_radio_selection'] = selecao_principal
        st.rerun()
            
    if selecao_principal in opcoes_principais:
        st.session_state['last_radio_selection'] = selecao_principal
        
    st.sidebar.write("")
    _sims_liberados = [x for x in simuladores_dict if is_master or MENU_PARA_PERMISSAO[x] in _perm_usuario]
    _atalho_site = is_master or ("cartas_site" in _perm_usuario)
    with st.sidebar.expander("🛠️ Simuladores", expanded=(st.session_state['menu_lateral'] in simuladores_dict)) if (_sims_liberados or _atalho_site) else st.sidebar.container():
        if _atalho_site:
            st.link_button("📄 Cartas Contempladas", "https://consorbensmg.com.br/admin/", use_container_width=True)
        for sim in _sims_liberados:
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

if is_logado and not is_master:
    _chave_perm = MENU_PARA_PERMISSAO.get(menu_selecionado)
    _so_admin = menu_selecionado in ("Financeiro", "Baixar Parcelas", "Configurações de Sistema", "Assembleias", "🤖 Robô")
    if _so_admin or (_chave_perm is None) or (_chave_perm not in _perm_usuario):
        st.warning("🔒 Você não tem acesso a esta tela. Escolha uma opção do menu.")
        st.stop()

# Trava de segurança: simulador só com login. Se cair aqui sem estar logado
# (sessão antiga, link direto), volta para a tela de login.
if (menu_selecionado in simuladores_dict) and not is_logado:
    menu_selecionado = "🔐 Login (Área Restrita)"
    st.session_state['menu_lateral'] = menu_selecionado

# Aplicando cor de fundo dependendo da área
if menu_selecionado in simuladores_dict:
    css += """ <style>.stApp { background-color: #0f172a !important; }</style> """
elif (not is_logado) and menu_selecionado == "🔐 Login (Área Restrita)":
    # Tela de login: fundo ilustrado com os produtos da Consorbens
    css += css_fundo_login()
else:
    # O brilho superior usa a cor do tema escolhido pelo usuário
    css += """ <style>.stApp { background: radial-gradient(1150px 500px at 100% -8%, var(--brand-soft), transparent 58%), linear-gradient(180deg, #f7f9fc 0%, #eaeef4 100%) !important; background-attachment: fixed !important; }</style> """
st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 6. DISTRIBUIÇÃO DAS TELAS
# ==========================================
if menu_selecionado in simuladores_dict:
    if menu_selecionado == "🚀 Simulador Itaú V 2.0":
        from modulos.itau_v2 import render_itau_v2
        render_itau_v2(PASTA_ATUAL)
    elif menu_selecionado == "🏍️ Simulador Yamaha":
        from modulos.yamaha_sim import render_yamaha_sim
        render_yamaha_sim(supabase, PASTA_ATUAL)
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
                    st.markdown("##### Acesse o sistema")
                    usuario_input = st.text_input("Usuário (login)", placeholder="ex.: breno ou o login que você recebeu").strip()
                    senha_input = st.text_input("Senha", type="password")
                    st.write("")
                    
                    if st.form_submit_button("ENTRAR", type="primary", use_container_width=True):
                        if not usuario_input:
                            st.error("❌ Digite o seu usuário (login).")
                        else:
                            user_valido, erro_login = autenticar(supabase, usuario_input, senha_input)

                            if user_valido:
                                st.session_state.update({
                                    'usuario_logado': user_valido["login"],
                                    'perfil_logado': user_valido["perfil"],
                                    'nome_vendedor': user_valido["nome"],
                                    'menu_lateral': "Dashboard"
                                })
                                st.rerun()
                            else:
                                st.error("❌ " + (erro_login or "Usuário ou senha incorretos."))
                                
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
                            _ok_forca, _msg_forca = validar_forca(alt_senha_nova)
                            if checar_atual and not _ok_forca:
                                st.error("❌ " + _msg_forca)
                            elif checar_atual:
                                if atualizar_senha_usuario(supabase, alt_usuario, alt_senha_nova):
                                    st.success("✅ Senha atualizada com sucesso! Já pode iniciar sessão.")
                                    if checar_atual.get("acesso_site_admin"):
                                        _ok_s, _msg_s, _uid = sincronizar_site(
                                            iniciar_conexao_site(), checar_atual.get("email"), alt_senha_nova,
                                            True, checar_atual.get("site_user_id"))
                                        (st.success if _ok_s else st.warning)(_msg_s)
                                else:
                                    st.error("❌ Erro técnico ao atualizar no banco de dados "
                                             "(a atualização de segurança do banco pode estar pendente).")
                            else:
                                st.error("❌ Usuário ou Senha Atual incorretos. Operação recusada.")
    st.stop() 

# --- BARRA SUPERIOR: SELETOR DE COR DO SISTEMA ---
render_seletor_tema()

# --- AVISO: robô não está entrando no Newcon (senha errada/expirada) ---
_trava_on, _trava_desde = _trava_login_robo(supabase)
if _trava_on:
    if not st.session_state.get("_trava_toast"):
        st.toast("🔒 O robô não está entrando no Newcon — senha errada/expirada!", icon="⚠️")
        st.session_state["_trava_toast"] = True
    st.error(
        f"🔒 **O robô parou de entrar no Newcon** (desde {_trava_desde}). A senha do Newcon "
        f"está **errada ou expirada** — ele fez 1 tentativa e travou de propósito, pra não "
        f"bloquear a conta.\n\n"
        f"**Como resolver:** abra a aba **Senhas**, atualize a senha da empresa "
        f"*YAMAHA NEWCON*, e clique no botão abaixo. Enquanto isso, **lance / boleto / coletas "
        f"ficam parados** (o resto do robô — Gmail, Anglo — segue normal)."
    )
    _bt1, _bt2 = st.columns([1, 2])
    with _bt1:
        if st.button("✅ Já atualizei a senha — liberar o robô", type="primary",
                     use_container_width=True, key="btn_liberar_robo"):
            try:
                supabase.table("robo_status").update({
                    "login_travado": False, "login_travado_msg": None,
                    "login_liberado_em": datetime.now(timezone.utc).isoformat(),
                }).eq("id", 1).execute()
                _status_robo.clear()
                _trava_login_robo.clear()
                st.session_state.pop("_trava_toast", None)
                st.success("Liberado! O robô vai tentar entrar de novo no próximo ciclo (~30s).")
                st.rerun()
            except Exception as e:
                st.error(f"Não consegui liberar agora: {e}")
    st.divider()
else:
    st.session_state.pop("_trava_toast", None)

# --- ROTEAMENTO PARA OS MÓDULOS ---
if menu_selecionado == "Dashboard":
    render_dashboard(supabase, df_vendas_global, df_cli, df_ass, lista_admin_bd, df_admin, status_dict, cfg)
elif menu_selecionado == "Ofertar Lance":
    render_ofertar_lance(supabase, df_vendas_global)
elif menu_selecionado == "Emissão de Boletos":
    render_emitir_boleto(supabase, df_vendas_global, df_cli)
elif menu_selecionado == "Nova Venda":
    render_nova_venda(supabase, df_cli, lista_admin_bd)
elif menu_selecionado == "Financeiro":
    render_financeiro(supabase, df_vendas_global, df_admin, cfg, status_dict)
elif menu_selecionado == "Assembleias":
    render_assembleias(supabase, df_ass)
elif menu_selecionado == "Relatórios":
    render_relatorios(supabase, df_vendas_global, df_admin, cfg, status_dict)
elif menu_selecionado == "Mídias":
    render_midias(supabase)
elif menu_selecionado == "Baixar Parcelas":
    render_baixas(supabase, df_vendas_global, df_admin, cfg, status_dict, lista_admin_bd)
elif menu_selecionado == "🤖 Robô":
    if is_master:
        render_robo_painel(supabase)
    else:
        st.session_state['menu_lateral'] = "Dashboard"
        st.rerun()
elif menu_selecionado == "Configurações de Sistema":
    # Senhas e Base de Conhecimento agora vivem aqui dentro, como abas.
    tab_sis, tab_usr, tab_senhas, tab_ia = st.tabs(["⚙️ Sistema", "👥 Usuários e acessos", "🔐 Senhas", "🧠 Base de Conhecimento"])
    with tab_sis:
        render_configuracoes(supabase, df_admin_cad, df_admin, lista_admin_bd, cfg, cfg_id)
    with tab_usr:
        render_usuarios(supabase)
    with tab_senhas:
        render_senhas(supabase)
    with tab_ia:
        render_config_ia(supabase)
