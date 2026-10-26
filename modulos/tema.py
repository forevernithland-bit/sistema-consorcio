"""
Design System do Portal Consorbens.
Centraliza cores, tipografia e componentes visuais.
Permite ao usuário trocar a cor do sistema pelo seletor no topo.
"""
import os
import base64
import streamlit as st

# ==========================================
# PALETAS DISPONÍVEIS
# O tema padrão "Consorbens" usa o teal (verde-petróleo) da logo/site.
# ==========================================
TEMAS = {
    "teal":     {"nome": "Consorbens",  "emoji": "🟢", "brand": "#2c7a73", "dark": "#1f5b55", "glow": "44,122,115"},
    "azul":     {"nome": "Corporativo", "emoji": "🔵", "brand": "#2563eb", "dark": "#1d4ed8", "glow": "37,99,235"},
    "verde":    {"nome": "Esmeralda",   "emoji": "🟩", "brand": "#059669", "dark": "#047857", "glow": "5,150,105"},
    "roxo":     {"nome": "Violeta",     "emoji": "🟣", "brand": "#7c3aed", "dark": "#6d28d9", "glow": "124,58,237"},
    "laranja":  {"nome": "Âmbar",       "emoji": "🟠", "brand": "#ea580c", "dark": "#c2410c", "glow": "234,88,12"},
    "vermelho": {"nome": "Rubi",        "emoji": "🔴", "brand": "#e74c3c", "dark": "#c0392b", "glow": "231,76,60"},
    "grafite":  {"nome": "Grafite",     "emoji": "⚫", "brand": "#334155", "dark": "#1e293b", "glow": "51,65,85"},
}

TEMA_PADRAO = "teal"


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
    # Fica "flutuando" no canto superior direito (CSS .st-key-cb_tema_bar): não empurra o conteúdo para baixo
    with st.container(key="cb_tema_bar"):
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
# FUNDO ILUSTRADO DA TELA DE LOGIN
# ==========================================
@st.cache_data
def _svg_login_b64():
    """Lê a ilustração de fundo (assets/fundo_login.svg) e devolve em base64.
    Cacheado sem TTL: é um arquivo estático do projeto, só muda em deploy —
    evita reler e recodificar o SVG a cada render da tela de login."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    caminho = os.path.join(raiz, "assets", "fundo_login.svg")
    try:
        with open(caminho, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""


def css_fundo_login():
    """CSS aplicado só na tela de login: gradiente da marca + montagem ilustrada."""
    b64 = _svg_login_b64()
    camada_img = f'url("data:image/svg+xml;base64,{b64}"), ' if b64 else ""
    return f"""
<style>
    .stApp {{
        background-color: #e6f1ef !important;
        background-image: {camada_img}
            radial-gradient(1100px 460px at 85% -10%, rgba(44,122,115,0.14), transparent 60%),
            linear-gradient(180deg, #f1f7f6 0%, #dfeeeb 100%) !important;
        background-position: bottom center, center, center !important;
        background-size: 100% auto, cover, cover !important;
        background-repeat: no-repeat, no-repeat, no-repeat !important;
        background-attachment: fixed, fixed, fixed !important;
    }}
    /* Cartão do login com mais destaque sobre o fundo */
    [data-testid="stMain"] [data-testid="stForm"] {{
        box-shadow: 0 24px 55px rgba(15,23,42,0.16) !important;
        border-radius: 20px !important;
    }}
</style>
"""


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

    /* SIDEBAR: ver modulos/sidebar.py (css_sidebar) */
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
""" + _CSS_V2


# ==========================================================
# DESIGN SYSTEM v2 — componentes de apresentação (só visual)
# Tudo em CSS puro: transform/opacity, sem JS. Respeita
# prefers-reduced-motion. Os números "contam" com @property.
# ==========================================================
_CSS_V2 = """
<style>
    :root {
        --ok: #16a34a; --ok-soft: #dcfce7; --warn: #d97706; --warn-soft: #fef3c7;
        --danger: #dc2626; --danger-soft: #fee2e2; --info: #2563eb; --info-soft: #dbeafe;
        --radius-lg: 20px; --radius-sm: 10px;
    }
    @property --cbn { syntax: '<integer>'; inherits: false; initial-value: 0; }
    @counter-style cbpad3 { system: extends decimal; pad: 3 "0"; }
    @counter-style cbpad2 { system: extends decimal; pad: 2 "0"; }
    @keyframes cbCount { from { --cbn: 0; } }
    @keyframes cbGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
    @keyframes cbRise { from { opacity: 0; transform: translateY(60%); } to { opacity: 1; transform: none; } }
    @keyframes cbFade { from { opacity: 0; } to { opacity: 1; } }
    @keyframes cbPulse { 0%,100% { box-shadow: 0 0 0 0 rgba(255,255,255,.55); } 50% { box-shadow: 0 0 0 5px rgba(255,255,255,0); } }

    /* ---------- números que contam ---------- */
    .cb-c { --cbn: var(--to); counter-reset: cbn var(--cbn); animation: cbCount 1.15s var(--ease) both; font-variant-numeric: tabular-nums; }
    .cb-c::after { content: counter(cbn); }
    .cb-c.p3::after { content: counter(cbn, cbpad3); }
    .cb-c.p2::after { content: counter(cbn, cbpad2); }
    .cb-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

    /* ---------- cabeçalho de página (hero) ---------- */
    .cb-hero { position: relative; overflow: hidden; border-radius: var(--radius-lg); padding: 22px 26px 20px; margin: 2px 0 18px;
        color: #fff; isolation: isolate;
        background: radial-gradient(700px 260px at 92% -30%, rgba(255,255,255,.20), transparent 60%),
                    linear-gradient(135deg, var(--brand) 0%, var(--brand-dark) 100%);
        box-shadow: 0 14px 34px -14px var(--brand-glow), 0 2px 6px rgba(15,23,42,.06);
        animation: cbUp .5s var(--ease) both; }
    .cb-hero::before { content: ""; position: absolute; inset: 0; z-index: -1; pointer-events: none;
        background-image: radial-gradient(rgba(255,255,255,.16) 1px, transparent 1.4px); background-size: 22px 22px;
        -webkit-mask-image: linear-gradient(100deg, transparent 35%, #000 100%); mask-image: linear-gradient(100deg, transparent 35%, #000 100%); }
    .cb-hero::after { content: ""; position: absolute; width: 260px; height: 260px; right: -70px; bottom: -150px; border-radius: 50%;
        background: rgba(255,255,255,.10); z-index: -1; }
    .cb-hero-row { display: flex; align-items: center; gap: 16px; }
    .cb-hero-ico { flex: 0 0 auto; width: 52px; height: 52px; border-radius: 15px; display: grid; place-items: center; font-size: 26px;
        background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.25); box-shadow: inset 0 1px 0 rgba(255,255,255,.25); }
    .cb-hero-ico.cb-av { font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 800; font-size: 19px; letter-spacing: .02em; }
    .cb-hero-txt { min-width: 0; }
    .cb-eyebrow { display: inline-flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 800; letter-spacing: .14em;
        text-transform: uppercase; color: rgba(255,255,255,.82); }
    .cb-eyebrow::before { content: ""; width: 22px; height: 3px; border-radius: 3px; background: rgba(255,255,255,.75);
        transform-origin: left; animation: cbGrow .9s .25s var(--ease) both; }
    .cb-hero-t { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 800; font-size: 1.62rem; line-height: 1.15;
        letter-spacing: -.025em; margin: 3px 0 2px; color: #fff; overflow-wrap: anywhere; }
    .cb-hero-s { font-size: 14px; color: rgba(255,255,255,.86); margin: 0; max-width: 78ch; }
    .cb-chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
    .cb-hero .cb-chip { background: rgba(255,255,255,.14); border-color: rgba(255,255,255,.26); color: #fff; }
    .cb-hero .cb-chip.ok::before { background: #86efac; animation: cbPulse 2.4s ease-in-out 3; }
    .cb-hero .cb-chip.warn::before { background: #fde68a; } .cb-hero .cb-chip.danger::before { background: #fca5a5; }

    /* ---------- chips / pílulas ---------- */
    .cb-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 11px; border-radius: 999px; font-size: 12.5px; font-weight: 700;
        line-height: 1.5; border: 1px solid var(--line); background: #fff; color: #334155; white-space: nowrap; }
    .cb-chip::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #94a3b8; }
    .cb-chip.plain::before { display: none; }
    .cb-chip.brand { background: var(--brand-soft); border-color: var(--brand-mid); color: var(--brand-dark); } .cb-chip.brand::before { background: var(--brand); }
    .cb-chip.ok { background: var(--ok-soft); border-color: #bbf7d0; color: #166534; } .cb-chip.ok::before { background: var(--ok); }
    .cb-chip.warn { background: var(--warn-soft); border-color: #fde68a; color: #92400e; } .cb-chip.warn::before { background: var(--warn); }
    .cb-chip.danger { background: var(--danger-soft); border-color: #fecaca; color: #991b1b; } .cb-chip.danger::before { background: var(--danger); }
    .cb-chip.info { background: var(--info-soft); border-color: #bfdbfe; color: #1e40af; } .cb-chip.info::before { background: var(--info); }
    .cb-chiprow { display: flex; flex-wrap: wrap; gap: 7px; margin: 2px 0 12px; }
    .cb-hero .cb-chip.brand, .cb-hero .cb-chip.plain { background: rgba(255,255,255,.16); border-color: rgba(255,255,255,.30); color: #fff; }
    .cb-hero .cb-chip.brand::before { background: #fff; }
    a.cb-chip { text-decoration: none !important; transition: transform .18s var(--ease), box-shadow .18s var(--ease); }
    a.cb-chip:hover { transform: translateY(-1px); box-shadow: var(--shadow-sm); }

    /* ---------- login ---------- */
    .cb-login-hd { text-align: center; margin: 0 0 14px; animation: cbUp .55s var(--ease) both; }
    .cb-login-hd .cb-eyebrow { color: var(--brand); }
    .cb-login-hd .cb-eyebrow::before { background: var(--brand); }
    .cb-login-t { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 800; font-size: 1.9rem; letter-spacing: -.03em; color: var(--ink); margin-top: 4px; }
    .cb-login-s { color: var(--muted); font-size: 14.5px; margin-top: 2px; }

    /* ---------- cartões de KPI ---------- */
    .cb-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 4px 0 18px; }
    .cb-kpi { position: relative; overflow: hidden; background: var(--card); border: 1px solid var(--line); border-radius: 18px;
        padding: 16px 18px 15px; box-shadow: var(--shadow-sm); animation: cbPop .45s var(--ease) both;
        transition: transform .24s var(--ease), box-shadow .24s var(--ease), border-color .24s var(--ease); }
    .cb-kpi:nth-child(2) { animation-delay: .05s; } .cb-kpi:nth-child(3) { animation-delay: .1s; } .cb-kpi:nth-child(4) { animation-delay: .15s; }
    .cb-kpi:hover { transform: translateY(-3px); box-shadow: var(--shadow-lg); border-color: var(--brand-mid); }
    .cb-kpi::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: linear-gradient(90deg, var(--brand), var(--brand-dark)); }
    .cb-kpi.ok::before { background: linear-gradient(90deg, #22c55e, #15803d); } .cb-kpi.warn::before { background: linear-gradient(90deg, #f59e0b, #d97706); }
    .cb-kpi.danger::before { background: linear-gradient(90deg, #f87171, #dc2626); } .cb-kpi.info::before { background: linear-gradient(90deg, #60a5fa, #2563eb); }
    .cb-kpi-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .cb-kpi-l { font-size: 12.5px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
    .cb-kpi-i { width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center; font-size: 17px; background: var(--brand-soft); }
    .cb-kpi.ok .cb-kpi-i { background: var(--ok-soft); } .cb-kpi.warn .cb-kpi-i { background: var(--warn-soft); }
    .cb-kpi.danger .cb-kpi-i { background: var(--danger-soft); } .cb-kpi.info .cb-kpi-i { background: var(--info-soft); }
    .cb-kpi-v { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.7rem; font-weight: 800; letter-spacing: -.03em;
        color: var(--ink); line-height: 1.15; margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .cb-kpi-v small { font-size: .62em; font-weight: 700; color: var(--muted); margin-right: 2px; }
    .cb-kpi-s { font-size: 12.5px; color: var(--muted); margin-top: 3px; min-height: 1.2em; }
    .cb-kpi-s b.up { color: var(--ok); } .cb-kpi-s b.down { color: var(--danger); }
    .cb-bar { height: 7px; border-radius: 99px; background: #eef2f7; overflow: hidden; margin-top: 10px; }
    .cb-bar > i { display: block; height: 100%; width: var(--w); border-radius: 99px; transform-origin: left;
        background: linear-gradient(90deg, var(--brand), var(--brand-dark)); animation: cbGrow 1.1s .15s var(--ease) both; }
    .cb-kpi.warn .cb-bar > i { background: linear-gradient(90deg, #fbbf24, #d97706); } .cb-kpi.danger .cb-bar > i { background: linear-gradient(90deg, #f87171, #dc2626); }
    .cb-kpi.ok .cb-bar > i { background: linear-gradient(90deg, #4ade80, #16a34a); }

    /* ---------- painel de pendências / listas ---------- */
    .cb-panel { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 15px 17px; box-shadow: var(--shadow-sm);
        height: 100%; animation: cbUp .45s var(--ease) both; }
    .cb-panel-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-weight: 800; color: var(--ink);
        font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 15px; margin-bottom: 8px; }
    .cb-li { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 2px; border-top: 1px dashed var(--line); font-size: 13.5px; color: #334155; }
    .cb-li:first-of-type { border-top: 0; }
    .cb-li span.n { font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .cb-li a { color: var(--brand); font-weight: 700; text-decoration: none; white-space: nowrap; }
    .cb-li a:hover { text-decoration: underline; }
    .cb-ok-msg { font-size: 13.5px; color: var(--muted); padding: 6px 2px; }

    /* ---------- estado vazio ---------- */
    .cb-empty { text-align: center; padding: 30px 18px 26px; border: 1.5px dashed #d5dde8; border-radius: 18px; margin: 8px 0 14px;
        background: linear-gradient(180deg, #fff, #f8fafc); animation: cbPop .4s var(--ease) both; }
    .cb-empty-i { width: 58px; height: 58px; margin: 0 auto 10px; border-radius: 18px; display: grid; place-items: center; font-size: 28px;
        background: var(--brand-soft); box-shadow: 0 0 0 7px rgba(255,255,255,.9), 0 0 0 8px var(--brand-soft); }
    .cb-empty-t { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 800; color: var(--ink); font-size: 16px; }
    .cb-empty-s { color: var(--muted); font-size: 13.5px; margin-top: 3px; }

    /* ---------- dica contextual ---------- */
    .cb-tip { display: flex; gap: 10px; align-items: flex-start; padding: 10px 14px; border-radius: 13px; margin: 2px 0 12px;
        background: var(--brand-soft); border: 1px solid var(--brand-mid); color: #334155; font-size: 13.5px; }
    .cb-tip b { color: var(--brand-dark); }

    /* ---------- seção ---------- */
    .cb-sec { display: flex; align-items: center; gap: 10px; margin: 18px 0 8px; }
    .cb-sec-i { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; background: var(--brand-soft); font-size: 16px; }
    .cb-sec-t { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 800; font-size: 17px; color: var(--ink); letter-spacing: -.02em; }
    .cb-sec-s { font-size: 12.5px; color: var(--muted); }

    /* ---------- refinamentos globais ---------- */
    [data-testid="stMain"] h3 { position: relative; }
    [data-testid="stMain"] hr { border: 0 !important; height: 1px !important; margin: 1.3rem 0 !important;
        background: linear-gradient(90deg, transparent, #d5dde8 18%, #d5dde8 82%, transparent) !important; }
    [data-testid="stCaptionContainer"] { color: #64748b !important; line-height: 1.55; }
    [data-testid="stMetricValue"] > div { animation: cbRise .55s var(--ease) both; font-variant-numeric: tabular-nums; }
    [data-testid="stMetric"]::after { content: ""; position: absolute; right: -40px; top: -40px; width: 110px; height: 110px; border-radius: 50%;
        background: var(--brand-soft); opacity: .7; pointer-events: none; transition: transform .35s var(--ease); }
    [data-testid="stMetric"]:hover::after { transform: scale(1.25); }
    /* abas como pílulas */
    [data-baseweb="tab-list"] { gap: 4px !important; background: #fff; border: 1px solid var(--line) !important; border-radius: 14px;
        padding: 4px !important; box-shadow: var(--shadow-sm); overflow-x: auto; scrollbar-width: thin; }
    button[data-baseweb="tab"] { border-radius: 10px !important; padding: 8px 15px !important; white-space: nowrap; }
    button[data-baseweb="tab"][aria-selected="true"] { background: linear-gradient(135deg, var(--brand), var(--brand-dark)) !important; color: #fff !important;
        box-shadow: 0 6px 16px -6px var(--brand-glow); }
    button[data-baseweb="tab"][aria-selected="true"] p { color: #fff !important; }
    [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none !important; }
    /* Streamlit novo (react-aria): mesmas pílulas */
    [data-testid="stTabs"] [role="tablist"] { gap: 4px !important; background: #fff; border: 1px solid var(--line) !important; border-radius: 14px;
        padding: 4px !important; box-shadow: var(--shadow-sm); overflow-x: auto; scrollbar-width: thin; width: fit-content; max-width: 100%; }
    [data-testid="stTab"] { border-radius: 10px !important; padding: 7px 15px !important; white-space: nowrap; cursor: pointer;
        transition: background-color .2s var(--ease), color .2s var(--ease), box-shadow .2s var(--ease) !important; }
    [data-testid="stTab"] p { font-weight: 600 !important; color: var(--muted); font-size: 14.5px !important; }
    [data-testid="stTab"]:hover { background: #f1f5f9; } [data-testid="stTab"]:hover p { color: var(--brand) !important; }
    [data-testid="stTab"][aria-selected="true"] { background: linear-gradient(135deg, var(--brand), var(--brand-dark)) !important;
        box-shadow: 0 6px 16px -6px var(--brand-glow); }
    [data-testid="stTab"][aria-selected="true"] p { color: #fff !important; }
    [data-testid="stTabs"] .react-aria-SelectionIndicator { display: none !important; }
    [data-testid="stTabs"] [role="tablist"] + div, [data-testid="stTabs"] > div > div:has(> [role="tablist"])::after { border: 0 !important; }
    /* alertas com faixa lateral por tipo */
    [data-testid="stAlert"] { border-radius: 14px !important; animation: cbPop .35s var(--ease) both; }
    [data-testid="stAlert"] > div { border-left: 4px solid transparent; border-radius: 14px !important; }
    [data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) > div { border-left-color: #3b82f6; }
    [data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) > div { border-left-color: #22c55e; }
    [data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) > div { border-left-color: #f59e0b; }
    [data-testid="stAlert"]:has([data-testid="stAlertContentError"]) > div { border-left-color: #ef4444; }
    /* tabelas */
    [data-testid="stDataFrame"] { transition: box-shadow .24s var(--ease), border-color .24s var(--ease); background: #fff; }
    [data-testid="stDataFrame"]:hover { box-shadow: var(--shadow-md); border-color: var(--brand-mid) !important; }
    /* progresso */
    [data-testid="stProgress"] div[role="progressbar"] > div > div { border-radius: 99px !important; }
    [data-testid="stProgress"] div[role="progressbar"] > div > div > div { background: linear-gradient(90deg, var(--brand), var(--brand-dark)) !important;
        border-radius: 99px !important; transform-origin: left; animation: cbGrow 1s var(--ease) both; }
    /* caixas com borda (st.container(border=True)) */
    [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 18px !important; background: var(--card);
        border-color: var(--line) !important; box-shadow: var(--shadow-sm); transition: box-shadow .24s var(--ease), border-color .24s var(--ease); }
    [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]:hover { box-shadow: var(--shadow-md); border-color: var(--brand-mid) !important; }
    .st-key-cb_tema_bar { position: fixed; top: 12px; right: 136px; z-index: 999991; width: 116px !important; }
    .st-key-cb_tema_bar [data-testid="stPopover"] button { padding: .3rem .8rem !important; min-height: 0 !important; background: rgba(255,255,255,.85);
        backdrop-filter: blur(6px); font-size: 13.5px !important; }
    [class*="st-key-dash_atr_"] button { padding: .2rem .7rem !important; min-height: 0 !important; font-size: 13px !important; border-radius: 9px !important; }
    /* diálogos, popovers e toasts */
    div[role="dialog"] { border-radius: 22px !important; box-shadow: 0 30px 80px -24px rgba(15,23,42,.45) !important; }
    [data-testid="stToast"] { border-radius: 14px !important; box-shadow: var(--shadow-lg) !important; border: 1px solid var(--line); }
    [data-testid="stPopoverBody"] { border-radius: 16px !important; box-shadow: var(--shadow-lg) !important; }
    /* checkbox/radio/pílulas na cor da marca */
    [data-testid="stMain"] [data-baseweb="checkbox"] input:checked + div, [data-testid="stMain"] label[data-baseweb="checkbox"] > span[aria-checked="true"] { background-color: var(--brand) !important; border-color: var(--brand) !important; }
    [data-testid="stMain"] button[kind="pillsActive"], [data-testid="stMain"] button[kind="segmented_controlActive"] { background: var(--brand-soft) !important;
        border-color: var(--brand) !important; color: var(--brand-dark) !important; }
    /* acessibilidade: foco visível */
    [data-testid="stMain"] button:focus-visible, [data-testid="stMain"] a:focus-visible { outline: 3px solid var(--brand-mid) !important; outline-offset: 2px; }

    /* scroll-reveal leve (só onde o navegador suporta; opacity/transform no compositor) */
    @supports (animation-timeline: view()) {
        .cb-reveal, [data-testid="stMain"] [data-testid="stExpander"] {
            animation: cbUp linear both; animation-timeline: view(); animation-range: entry 0% entry 28%; }
    }

    /* ---------- celular ---------- */
    @media (max-width: 640px) {
        .block-container { padding: 1rem 1rem 2rem !important; }
        .cb-hero { padding: 17px 17px 15px; border-radius: 18px; }
        .cb-hero-ico { width: 42px; height: 42px; font-size: 21px; border-radius: 13px; }
        .cb-hero-t { font-size: 1.28rem; }
        .cb-hero-s { font-size: 13px; }
        .cb-kpis { grid-template-columns: 1fr 1fr; gap: 10px; }
        .cb-kpi { padding: 13px 13px 12px; border-radius: 15px; }
        .cb-kpi-v { font-size: 1.22rem; }
        .cb-kpi-l { font-size: 11px; }
        .cb-kpi-i { width: 28px; height: 28px; font-size: 14px; }
        [data-testid="stMetricValue"] { font-size: 1.35rem !important; }
    }

    /* ---------- menos movimento ---------- */
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { animation-duration: .001ms !important; animation-delay: 0s !important; animation-iteration-count: 1 !important;
            transition-duration: .001ms !important; scroll-behavior: auto !important; }
        .cb-reveal, [data-testid="stMain"] [data-testid="stExpander"] { animation: none !important; }
    }
</style>
"""


def _esc(txt):
    """Escapa HTML e o '$' (que o Markdown do Streamlit trataria como LaTeX)."""
    import html as _h
    return _h.escape(str(txt if txt is not None else "")).replace("$", "&#36;")


def _brl_txt(v):
    s = f"{abs(float(v)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if float(v) < 0 else "") + "R&#36;&nbsp;" + s


def numero_animado(valor, tipo="int"):
    """HTML de um número que 'conta' de 0 até o valor (CSS puro, @property).
    tipo: 'int' | 'brl'. O valor exato fica num texto para leitores de tela."""
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        return _esc(valor)
    if tipo == "brl":
        real = _brl_txt(v)
        cent_total = int(round(abs(v) * 100))
        inteiro, cent = divmod(cent_total, 100)
        grupos = []
        while True:
            inteiro, g = divmod(inteiro, 1000)
            grupos.insert(0, g)
            if inteiro == 0:
                break
        partes = [f'<span class="cb-c" style="--to:{grupos[0]}"></span>']
        partes += [f'.<span class="cb-c p3" style="--to:{g}"></span>' for g in grupos[1:]]
        partes.append(f',<span class="cb-c p2" style="--to:{cent}"></span>')
        sinal = "-" if v < 0 else ""
        return (f'<span class="cb-sr">{real}</span><span aria-hidden="true"><small>{sinal}R&#36;</small>'
                + "".join(partes) + "</span>")
    n = int(round(v))
    return f'<span class="cb-sr">{n}</span><span aria-hidden="true">{"-" if n < 0 else ""}<span class="cb-c" style="--to:{abs(n)}"></span></span>'


def chips_html(chips):
    """chips: lista de (texto, tom) — tom: brand|ok|warn|danger|info|plain|''."""
    out = []
    for c in chips or []:
        txt, tom = (c, "") if isinstance(c, str) else (c[0], c[1] if len(c) > 1 else "")
        out.append(f'<span class="cb-chip {tom}">{_esc(txt)}</span>')
    return "".join(out)


def cabecalho(titulo, icone="", subtitulo="", chips=None, eyebrow="Consorbens", avatar=None):
    """Cabeçalho padrão de página (hero com gradiente da cor do tema)."""
    ico = (f'<div class="cb-hero-ico cb-av">{_esc(avatar)}</div>' if avatar
           else (f'<div class="cb-hero-ico">{_esc(icone)}</div>' if icone else ""))
    sub = f'<p class="cb-hero-s">{_esc(subtitulo)}</p>' if subtitulo else ""
    ch = f'<div class="cb-chips">{chips_html(chips)}</div>' if chips else ""
    eb = f'<div class="cb-eyebrow">{_esc(eyebrow)}</div>' if eyebrow else ""
    st.markdown(f'<div class="cb-hero"><div class="cb-hero-row">{ico}<div class="cb-hero-txt">{eb}'
                f'<div class="cb-hero-t">{_esc(titulo)}</div>{sub}</div></div>{ch}</div>', unsafe_allow_html=True)


def linha_chips(chips):
    if chips:
        st.markdown(f'<div class="cb-chiprow">{chips_html(chips)}</div>', unsafe_allow_html=True)


def kpis(itens):
    """Cartões de KPI com número animado e barra opcional.
    item: dict(rotulo, valor, tipo='int'|'brl'|'txt', icone, tom, sub (html já escapado ou texto), barra (0..1))."""
    cards = []
    for it in itens:
        tipo = it.get("tipo", "int")
        val = _esc(it.get("valor")) if tipo == "txt" else numero_animado(it.get("valor"), tipo)
        barra = it.get("barra")
        bar = (f'<div class="cb-bar"><i style="--w:{max(0.0, min(float(barra), 1.0)) * 100:.1f}%"></i></div>'
               if barra is not None else "")
        sub = it.get("sub_html") or _esc(it.get("sub", ""))
        cards.append(f'<div class="cb-kpi {it.get("tom", "")}"><div class="cb-kpi-top"><span class="cb-kpi-l">{_esc(it.get("rotulo"))}</span>'
                     f'<span class="cb-kpi-i">{_esc(it.get("icone", ""))}</span></div><div class="cb-kpi-v">{val}</div>'
                     f'<div class="cb-kpi-s">{sub}</div>{bar}</div>')
    st.markdown(f'<div class="cb-kpis">{"".join(cards)}</div>', unsafe_allow_html=True)


def estado_vazio(titulo, texto="", icone="✨"):
    """Estado vazio amigável (substitui o 'st.info' seco quando não há nada a mostrar)."""
    s = f'<div class="cb-empty-s">{_esc(texto)}</div>' if texto else ""
    st.markdown(f'<div class="cb-empty"><div class="cb-empty-i">{_esc(icone)}</div>'
                f'<div class="cb-empty-t">{_esc(titulo)}</div>{s}</div>', unsafe_allow_html=True)


def dica(texto_html):
    """Dica contextual discreta. Recebe HTML simples já seguro (use <b>)."""
    st.markdown(f'<div class="cb-tip"><span>💡</span><div>{texto_html}</div></div>', unsafe_allow_html=True)


def secao(titulo, icone="", subtitulo=""):
    s = f'<div class="cb-sec-s">{_esc(subtitulo)}</div>' if subtitulo else ""
    i = f'<div class="cb-sec-i">{_esc(icone)}</div>' if icone else ""
    st.markdown(f'<div class="cb-sec">{i}<div><div class="cb-sec-t">{_esc(titulo)}</div>{s}</div></div>', unsafe_allow_html=True)


def iniciais(nome):
    p = [x for x in str(nome or "").replace("(", " ").split() if x[:1].isalpha() and x.lower() not in ("da", "de", "do", "dos", "das", "e")]
    if not p:
        return "?"
    return (p[0][0] + (p[-1][0] if len(p) > 1 else "")).upper()


def saudacao():
    from datetime import datetime as _dt
    h = _dt.now().hour
    return "Bom dia" if 5 <= h < 12 else ("Boa tarde" if 12 <= h < 18 else "Boa noite")


def data_extenso():
    from datetime import datetime as _dt
    d = _dt.now()
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return f"{dias[d.weekday()]}, {d.day} de {meses[d.month - 1]} de {d.year}"
