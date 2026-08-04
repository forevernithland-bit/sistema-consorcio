"""
Design System do Portal Consorbens.
Centraliza cores, tipografia e componentes visuais.
Permite ao usuário trocar a cor do sistema pelo seletor no topo.
"""
import streamlit as st

# ==========================================
# PALETAS DISPONÍVEIS
# ==========================================
TEMAS = {
    "vermelho": {"nome": "Consorbens",  "emoji": "🔴", "brand": "#e74c3c", "dark": "#c0392b", "glow": "231,76,60"},
    "azul":     {"nome": "Corporativo", "emoji": "🔵", "brand": "#2563eb", "dark": "#1d4ed8", "glow": "37,99,235"},
    "verde":    {"nome": "Esmeralda",   "emoji": "🟢", "brand": "#059669", "dark": "#047857", "glow": "5,150,105"},
    "roxo":     {"nome": "Violeta",     "emoji": "🟣", "brand": "#7c3aed", "dark": "#6d28d9", "glow": "124,58,237"},
    "laranja":  {"nome": "Âmbar",       "emoji": "🟠", "brand": "#ea580c", "dark": "#c2410c", "glow": "234,88,12"},
    "grafite":  {"nome": "Grafite",     "emoji": "⚫", "brand": "#334155", "dark": "#1e293b", "glow": "51,65,85"},
}

TEMA_PADRAO = "vermelho"


def tema_atual():
    """Retorna o dicionário do tema escolhido pelo usuário."""
    chave = st.session_state.get("tema_cor", TEMA_PADRAO)
    return TEMAS.get(chave, TEMAS[TEMA_PADRAO])


# ==========================================
# SELETOR DE COR (fica no topo da tela)
# ==========================================
def render_seletor_tema():
    """Barra superior com o seletor de cor do sistema."""
    t = tema_atual()
    _, col_sel = st.columns([6, 1.15])
    with col_sel:
        with st.popover(f"🎨 Tema", use_container_width=True):
            st.markdown("##### Cor do sistema")
            st.caption("Escolha a identidade visual do painel.")
            for chave, cfg in TEMAS.items():
                marcado = "  ✓" if chave == st.session_state.get("tema_cor", TEMA_PADRAO) else ""
                if st.button(f"{cfg['emoji']}  {cfg['nome']}{marcado}",
                             key=f"tema_{chave}", use_container_width=True):
                    st.session_state["tema_cor"] = chave
                    st.rerun()


# ==========================================
# CSS COMPLETO DO SISTEMA
# ==========================================
def montar_css(chave_tema=None):
    """Gera todo o CSS do ERP já com as cores do tema escolhido."""
    cfg = TEMAS.get(chave_tema or st.session_state.get("tema_cor", TEMA_PADRAO), TEMAS[TEMA_PADRAO])
    brand, dark, glow = cfg["brand"], cfg["dark"], cfg["glow"]

    return f"""
<style>
    /* ==========================================================
       DESIGN SYSTEM — Portal Consorbens
       Tema ativo: {cfg['nome']}
       ========================================================== */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

    :root {{
        --brand: {brand};
        --brand-dark: {dark};
        --brand-soft: rgba({glow}, 0.10);
        --brand-mid: rgba({glow}, 0.22);
        --brand-glow: rgba({glow}, 0.30);
        --green: #22a559;
        --green-dark: #178a47;
        --ink: #0f172a;
        --muted: #64748b;
        --line: #e9eef5;
        /* Borda dos campos: cinza mais nítido, levemente tingido pela cor do tema.
           A 1ª linha é o fallback (navegadores sem color-mix); a 2ª tinge pelo tema. */
        --field-line: #aeb9c9;
        --field-line: color-mix(in srgb, var(--brand) 22%, #94a3b8);
        --field-line-hover: #8b98ab;
        --field-line-hover: color-mix(in srgb, var(--brand) 45%, #7c8a9e);
        --card: #ffffff;
        --shadow-sm: 0 1px 2px rgba(15,23,42,0.04), 0 4px 14px rgba(15,23,42,0.04);
        --shadow-md: 0 6px 24px rgba(15,23,42,0.07), 0 1px 2px rgba(15,23,42,0.04);
        --shadow-lg: 0 18px 45px rgba(15,23,42,0.13);
        --radius: 14px;
        --ease: cubic-bezier(0.22, 1, 0.36, 1);
    }}

    /* ---- Tipografia ---- */
    html, body, .stApp, [data-testid="stSidebar"], input, textarea, button, select, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }}
    h1, h2, h3, h4, h5, [data-testid="stMetricValue"] {{
        font-family: 'Plus Jakarta Sans', 'Inter', sans-serif !important;
        color: var(--ink); letter-spacing: -0.025em;
    }}
    [data-testid="stMain"] h1 {{ font-weight: 800 !important; font-size: 2rem !important; }}
    [data-testid="stMain"] h2 {{ font-weight: 800 !important; }}
    [data-testid="stMain"] h3 {{ font-weight: 700 !important; margin: 0.5rem 0 !important; }}
    .block-container {{ padding: 1.4rem 2.2rem 2.5rem !important; max-width: 1480px; }}

    /* ---- Entrada suave e escalonada do conteúdo ---- */
    [data-testid="stMain"] .block-container > div > div > div {{ animation: cbUp 0.45s var(--ease) both; }}
    @keyframes cbUp {{ from {{ opacity: 0; transform: translateY(14px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes cbPop {{ from {{ opacity: 0; transform: scale(0.97); }} to {{ opacity: 1; transform: scale(1); }} }}

    /* ---- Botões ---- */
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button,
    [data-testid="stLinkButton"] a, [data-testid="stPopover"] button {{
        border-radius: 11px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.05rem !important;
        transition: transform 0.18s var(--ease), box-shadow 0.18s var(--ease),
                    background-color 0.18s var(--ease), border-color 0.18s var(--ease), color 0.18s var(--ease) !important;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stPopover"] button:hover {{
        transform: translateY(-2px);
        box-shadow: var(--shadow-md);
        border-color: var(--brand) !important;
        color: var(--brand) !important;
    }}
    .stButton > button:active {{ transform: translateY(0) scale(0.98); }}
    button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
        background: linear-gradient(135deg, var(--green), var(--green-dark)) !important;
        border: none !important; color: #fff !important; font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(34,165,89,0.30) !important;
    }}
    button[kind="primary"]:hover {{
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 26px rgba(34,165,89,0.45) !important;
        color: #fff !important;
    }}

    /* ---- Inputs: fundo branco + contorno nítido ----
       Mira em TODOS os invólucros usados pelas várias versões do Streamlit. */
    .stTextInput div[data-baseweb="input"],
    .stNumberInput div[data-baseweb="input"],
    .stDateInput div[data-baseweb="input"],
    .stTextInput div[data-baseweb="base-input"],
    .stNumberInput div[data-baseweb="base-input"],
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"],
    div[data-baseweb="base-input"],
    .stTextArea textarea,
    .stDateInput > div > div {{
        background-color: #ffffff !important;
        border: 1.5px solid var(--field-line) !important;
        border-radius: 11px !important;
        box-shadow: 0 1px 2px rgba(15,23,42,0.05) !important;
        transition: border-color 0.16s var(--ease), box-shadow 0.16s var(--ease) !important;
    }}
    /* Campos internos SEM borda/fundo próprios (evita retângulo cinza duplo) */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    div[data-baseweb="input"] input, div[data-baseweb="base-input"] input,
    div[data-baseweb="select"] input {{
        background-color: transparent !important;
        border: none !important;
        color: var(--ink) !important;
    }}
    .stTextArea textarea {{ color: var(--ink) !important; }}
    /* Hover */
    .stTextInput div[data-baseweb="input"]:hover,
    .stNumberInput div[data-baseweb="input"]:hover,
    .stDateInput div[data-baseweb="input"]:hover,
    div[data-baseweb="select"] > div:hover,
    div[data-baseweb="base-input"]:hover,
    .stTextArea textarea:hover {{
        border-color: var(--field-line-hover) !important;
    }}
    /* Foco: contorno na cor do tema + anel suave */
    .stTextInput div[data-baseweb="input"]:focus-within,
    .stNumberInput div[data-baseweb="input"]:focus-within,
    .stDateInput div[data-baseweb="input"]:focus-within,
    div[data-baseweb="select"] > div:focus-within,
    div[data-baseweb="base-input"]:focus-within,
    .stTextArea textarea:focus {{
        border-color: var(--brand) !important;
        box-shadow: 0 0 0 3.5px var(--brand-soft) !important;
    }}
    /* Botões +/- do number input acompanham a borda */
    .stNumberInput button {{ border: 1.5px solid var(--field-line) !important; background: #fff !important; }}
    .stNumberInput button:hover {{ border-color: var(--brand) !important; color: var(--brand) !important; }}
    /* Placeholder mais legível */
    input::placeholder, textarea::placeholder {{ color: #94a3b8 !important; opacity: 1 !important; }}
    [data-testid="stFileUploader"] section {{
        border-radius: 14px !important; border: 1.5px dashed #cbd5e1 !important;
        transition: border-color 0.2s var(--ease), background-color 0.2s var(--ease);
    }}
    [data-testid="stFileUploader"] section:hover {{ border-color: var(--brand) !important; background: var(--brand-soft); }}

    /* ---- Métricas como cards ---- */
    [data-testid="stMetric"] {{
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 17px 19px;
        box-shadow: var(--shadow-sm);
        position: relative; overflow: hidden;
        transition: transform 0.24s var(--ease), box-shadow 0.24s var(--ease), border-color 0.24s var(--ease);
        animation: cbPop 0.4s var(--ease) both;
    }}
    [data-testid="stMetric"]::before {{
        content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
        background: linear-gradient(180deg, var(--brand), var(--brand-dark));
        opacity: 0; transition: opacity 0.24s var(--ease);
    }}
    [data-testid="stMetric"]:hover {{ transform: translateY(-4px); box-shadow: var(--shadow-lg); border-color: var(--brand-mid); }}
    [data-testid="stMetric"]:hover::before {{ opacity: 1; }}
    [data-testid="stMetricValue"] {{ font-size: 1.65rem !important; font-weight: 800 !important; }}
    [data-testid="stMetricLabel"] {{ color: var(--muted) !important; font-weight: 600 !important; }}

    /* ---- Abas ---- */
    [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid var(--line); padding-bottom: 2px; }}
    button[data-baseweb="tab"] {{
        font-size: 15px !important; font-weight: 600 !important; color: var(--muted) !important;
        border-radius: 11px 11px 0 0 !important; padding: 9px 17px !important;
        transition: background-color 0.2s var(--ease), color 0.2s var(--ease) !important;
    }}
    button[data-baseweb="tab"]:hover {{ background: #f1f5f9; color: var(--brand) !important; }}
    button[data-baseweb="tab"][aria-selected="true"] {{ background: var(--brand-soft) !important; color: var(--brand) !important; }}
    [data-baseweb="tab-highlight"] {{ background: var(--brand) !important; height: 3px !important; border-radius: 3px; }}
    [data-testid="stTabPanel"] {{ animation: cbUp 0.35s var(--ease) both; }}

    /* ---- Expanders e formulários ---- */
    [data-testid="stExpander"] {{
        border: 1px solid var(--line) !important; border-radius: 16px !important;
        box-shadow: var(--shadow-sm); background: var(--card); overflow: hidden;
        transition: box-shadow 0.24s var(--ease), border-color 0.24s var(--ease);
    }}
    [data-testid="stExpander"]:hover {{ box-shadow: var(--shadow-md); border-color: var(--brand-mid) !important; }}
    [data-testid="stExpander"] summary {{ font-weight: 600 !important; transition: color 0.18s var(--ease); }}
    [data-testid="stExpander"] summary:hover {{ color: var(--brand) !important; }}
    [data-testid="stForm"] {{
        border: 1px solid var(--line) !important; border-radius: 18px !important;
        padding: 24px !important; box-shadow: var(--shadow-md); background: var(--card);
    }}

    /* ---- Tabelas ---- */
    [data-testid="stDataFrame"], [data-testid="stTable"] {{
        border-radius: 14px !important; overflow: hidden;
        border: 1px solid var(--line) !important; box-shadow: var(--shadow-sm);
    }}

    /* ---- Alertas ---- */
    [data-testid="stAlert"] {{ border-radius: 13px !important; border: none !important; box-shadow: var(--shadow-sm); }}

    /* ---- Barra de rolagem ---- */
    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 10px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--brand); }}

    /* ==========================================================
       SIDEBAR
       ========================================================== */
    [data-testid="stSidebar"] {{ border-right: 1px solid var(--line) !important; box-shadow: 6px 0 28px rgba(15,23,42,0.04); }}
    [data-testid="stSidebar"] > div:first-child {{ background: linear-gradient(180deg, #ffffff 0%, #fafbfd 100%) !important; }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div {{ color: #0f172a !important; }}
    [data-testid="stSidebar"] hr {{ border-bottom-color: var(--line) !important; margin: 0.5rem 0 !important; }}
    [data-testid="stSidebar"] button {{ border: 1px solid #cbd5e1 !important; background-color: #f8fafc !important; }}

    /* Navegação em pílulas com barra de destaque animada */
    [data-testid="stSidebar"] div[role="radiogroup"] label {{
        padding: 5px 12px !important; border-radius: 10px !important; margin: 1.5px 0 !important;
        position: relative; overflow: hidden;
        transition: background-color 0.2s var(--ease), color 0.2s var(--ease), transform 0.2s var(--ease) !important;
    }}
    [data-testid="stSidebar"] div[role="radiogroup"] label::before {{
        content: ""; position: absolute; left: 0; top: 18%; bottom: 18%; width: 3px; border-radius: 3px;
        background: var(--brand); transform: scaleY(0); transition: transform 0.25s var(--ease);
    }}
    [data-testid="stSidebar"] div[role="radiogroup"] label:hover {{ background-color: #f1f5f9 !important; transform: translateX(2px); }}
    [data-testid="stSidebar"] div[role="radiogroup"] label:hover p {{ color: var(--brand) !important; }}
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{ background-color: var(--brand-soft) !important; }}
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked)::before {{ transform: scaleY(1); }}
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {{ color: var(--brand) !important; font-weight: 700 !important; }}

    /* Links externos no menu (ex: Cartas Contempladas) com o mesmo visual dos botões */
    [data-testid="stSidebar"] [data-testid="stLinkButton"] a, [data-testid="stSidebar"] a[kind="secondary"] {{ border: 1px solid #cbd5e1 !important; background-color: #f8fafc !important; color: #0f172a !important; text-decoration: none !important; }}
    [data-testid="stSidebar"] [data-testid="stLinkButton"] a:hover, [data-testid="stSidebar"] a[kind="secondary"]:hover {{ border-color: var(--brand) !important; color: var(--brand) !important; }}
    /* Link externo no menu de visitante, com o mesmo visual das opções (bolinha + texto).
       As margens negativas encostam o link nas opções de cima e de baixo. */
    [data-testid="stSidebar"] .st-key-cartas_link {{ margin-top: -2.1rem !important; }}
    [data-testid="stSidebar"] .st-key-menu_sim {{ margin-top: -1.7rem !important; }}
    [data-testid="stSidebar"] .menu-link-externo {{ display: flex !important; align-items: center; gap: 9px; text-decoration: none !important; padding: 0 0 0 1px; height: 22.4px; }}
    [data-testid="stSidebar"] .menu-link-bolinha {{ width: 14px; height: 14px; border-radius: 50%; background-color: #f0f2f6; flex: 0 0 auto; box-sizing: border-box; }}
    [data-testid="stSidebar"] .menu-link-texto {{ color: #0f172a !important; font-size: 14px; line-height: 22.4px; }}
    [data-testid="stSidebar"] .menu-link-externo:hover .menu-link-bolinha {{ background-color: var(--brand-soft); }}
    [data-testid="stSidebar"] .menu-link-externo:hover .menu-link-texto {{ color: var(--brand) !important; }}
    header[data-testid="stHeader"] {{ background-color: transparent !important; }}

    /* ==========================================================
       CALENDÁRIO (Assembleias)
       ========================================================== */
    .cal-table {{ width: 100%; border-collapse: collapse; text-align: center; background-color: white; border-radius: 14px; overflow: hidden; box-shadow: var(--shadow-sm); font-size: 14px; }}
    .cal-table th {{ background-color: #f8fafc; padding: 9px; font-weight: 700; color: #475569; border-bottom: 1px solid var(--line); }}
    .cal-table td {{ padding: 8px; border: 1px solid var(--line); color: #334155; }}
    .cal-day {{ border-radius: 50%; display: inline-block; width: 28px; height: 28px; line-height: 28px; transition: background-color 0.18s var(--ease); }}
    .cal-event {{ background: linear-gradient(135deg, var(--brand), var(--brand-dark)); color: white; font-weight: bold; box-shadow: 0 3px 10px var(--brand-glow); }}
    .cal-empty {{ background-color: #f8fafc; }}
    .event-desc {{ font-size: 14px; margin-bottom: 5px; border-left: 3px solid var(--brand); padding: 6px 9px; background: var(--brand-soft); border-radius: 0 8px 8px 0; }}

    /* ==========================================================
       CARDS DE MÍDIA
       ========================================================== */
    .media-card {{ background: white; padding: 14px; border-radius: 14px; border: 1px solid var(--line); text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: space-between; box-shadow: var(--shadow-sm); transition: transform 0.24s var(--ease), box-shadow 0.24s var(--ease); }}
    .media-card:hover {{ transform: translateY(-4px); box-shadow: var(--shadow-lg); }}
    .media-img {{ max-width: 100%; max-height: 120px; object-fit: contain; border-radius: 8px; margin-bottom: 10px; }}
    .media-title {{ font-size: 13px; font-weight: 500; color: #334155; margin-bottom: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
</style>
"""
