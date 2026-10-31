"""
Barra lateral (sidebar) do Portal Consorbens — design system.

Tudo aqui é só apresentação (CSS + pequenos helpers de texto). A lógica de
navegação, permissões e sessão continua em app.py / seguranca.py.

Princípios: hierarquia clara (marca > status > navegação agrupada > rodapé),
ícones Lucide (traço 1.75px) via CSS mask, tokens do tema (--brand*) e grade
de 4/8px. Sem JS: só Streamlit + CSS.
"""
import base64
import html as _html
from functools import lru_cache

# ------------------------------------------------------------------
# Ícones (Lucide, 24x24, traço aplicado via mask => herdam a cor do CSS)
# ------------------------------------------------------------------
_P = {
    "dashboard": "<rect width='7' height='9' x='3' y='3' rx='1'/><rect width='7' height='5' x='14' y='3' rx='1'/><rect width='7' height='9' x='14' y='12' rx='1'/><rect width='7' height='5' x='3' y='16' rx='1'/>",
    "file-plus": "<path d='M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z'/><path d='M14 2v4a2 2 0 0 0 2 2h4'/><path d='M12 18v-6'/><path d='M9 15h6'/>",
    "trending-up": "<polyline points='22 7 13.5 15.5 8.5 10.5 2 17'/><polyline points='16 7 22 7 22 13'/>",
    "barcode": "<path d='M3 5v14'/><path d='M8 5v14'/><path d='M12 5v14'/><path d='M17 5v14'/><path d='M21 5v14'/>",
    "wallet": "<path d='M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1'/><path d='M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4'/>",
    "check-circle": "<circle cx='12' cy='12' r='10'/><path d='m9 12 2 2 4-4'/>",
    "bar-chart": "<path d='M3 3v18h18'/><path d='M18 17V9'/><path d='M13 17V5'/><path d='M8 17v-3'/>",
    "image": "<rect width='18' height='18' x='3' y='3' rx='2'/><circle cx='9' cy='9' r='2'/><path d='m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21'/>",
    "sliders": "<path d='M21 4h-7'/><path d='M10 4H3'/><path d='M21 12h-9'/><path d='M8 12H3'/><path d='M21 20h-5'/><path d='M12 20H3'/><path d='M14 2v4'/><path d='M8 10v4'/><path d='M16 18v4'/>",
    "calculator": "<rect width='16' height='20' x='4' y='2' rx='2'/><line x1='8' x2='16' y1='6' y2='6'/><path d='M16 14v4'/><path d='M8 10h.01'/><path d='M12 10h.01'/><path d='M16 10h.01'/><path d='M8 14h.01'/><path d='M12 14h.01'/><path d='M8 18h.01'/><path d='M12 18h.01'/>",
    "bot": "<path d='M12 8V4H8'/><rect width='16' height='12' x='4' y='8' rx='2'/><path d='M2 14h2'/><path d='M20 14h2'/><path d='M15 13v2'/><path d='M9 13v2'/>",
    "sparkles": "<path d='M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z'/><path d='M20 3v4'/><path d='M22 5h-4'/><path d='M4 17v2'/><path d='M5 18H3'/>",
    "log-out": "<path d='M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4'/><path d='m16 17 5-5-5-5'/><path d='M21 12H9'/>",
    "lock": "<rect width='18' height='11' x='3' y='11' rx='2'/><path d='M7 11V7a5 5 0 0 1 10 0v4'/>",
    "chevron": "<path d='m9 18 6-6-6-6'/>",
    "bike": "<circle cx='18.5' cy='17.5' r='3.5'/><circle cx='5.5' cy='17.5' r='3.5'/><circle cx='15' cy='5' r='1'/><path d='M12 17.5V14l-3-3 4-3 2 3h2'/>",
    "zap": "<path d='M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z'/>",
    "landmark": "<line x1='3' x2='21' y1='22' y2='22'/><line x1='6' x2='6' y1='18' y2='11'/><line x1='10' x2='10' y1='18' y2='11'/><line x1='14' x2='14' y1='18' y2='11'/><line x1='18' x2='18' y1='18' y2='11'/><polygon points='12 2 20 7 4 7'/>",
    "target": "<circle cx='12' cy='12' r='10'/><circle cx='12' cy='12' r='6'/><circle cx='12' cy='12' r='2'/>",
    "scale": "<path d='m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z'/><path d='m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z'/><path d='M7 21h10'/><path d='M12 3v18'/><path d='M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2'/>",
    "file-text": "<path d='M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z'/><path d='M14 2v4a2 2 0 0 0 2 2h4'/><path d='M10 9H8'/><path d='M16 13H8'/><path d='M16 17H8'/>",
    "arrow-up-right": "<path d='M7 7h10v10'/><path d='M7 17 17 7'/>",
}


@lru_cache(maxsize=None)
def _uri(nome: str) -> str:
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' "
           "stroke='#000' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'>" + _P[nome] + "</svg>")
    return 'url("data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode() + '")'


# ------------------------------------------------------------------
# Estrutura do menu (só rótulos visuais — os VALORES do roteador não mudam)
# ------------------------------------------------------------------
GRUPOS_NAV = [
    ("Operação", ["Dashboard", "Nova Venda", "Ofertar Lance", "Emissão de Boletos"]),
    ("Gestão", ["Financeiro", "Baixar Parcelas", "Relatórios"]),
    ("Ferramentas", ["Mídias", "Configurações de Sistema"]),
]

ICONE_NAV = {
    "Dashboard": "dashboard", "Nova Venda": "file-plus", "Ofertar Lance": "trending-up",
    "Emissão de Boletos": "barcode", "Financeiro": "wallet", "Baixar Parcelas": "check-circle",
    "Relatórios": "bar-chart", "Mídias": "image", "Configurações de Sistema": "sliders",
    "🔐 Login (Área Restrita)": "lock",
}

# chave do simulador (valor do roteador) -> (ícone, nome exibido, slug da key do botão)
SIMULADORES_UI = {
    "🧮 Simuladores": ("calculator", "Simuladores", "hub"),
    "🏍️ Simulador Yamaha": ("bike", "Simulador Yamaha", "yamaha"),
    "🚀 Simulador Itaú V 2.0": ("zap", "Simulador Itaú V 2.0", "itau_v2"),
    "🏦 Simulador Itaú": ("landmark", "Simulador Itaú", "itau"),
    "🎯 Oportunidades Itaú": ("target", "Oportunidades Itaú", "oport"),
    "⚖️ Financiamento x Consórcio": ("scale", "Financiamento x Consórcio", "comp"),
}


def nome_simulador(chave: str) -> str:
    return SIMULADORES_UI.get(chave, ("", chave.split(" ", 1)[-1], ""))[1]


def key_simulador(chave: str) -> str:
    return "sim_" + SIMULADORES_UI.get(chave, ("", "", chave))[2]


def iniciais(nome: str) -> str:
    partes = [p for p in str(nome or "").replace("-", " ").split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def rotulo_perfil(perfil, is_master) -> str:
    if is_master:
        return "Administrador"
    return str(perfil or "Usuário")


def html_cartao_usuario(nome: str, perfil: str) -> str:
    n = _html.escape(str(nome or ""))
    return (
        "<div class='sb-user'>"
        f"<div class='sb-av' aria-hidden='true'>{_html.escape(iniciais(nome))}</div>"
        f"<div class='sb-ui'><div class='sb-nm' title='{n}'>{n}</div>"
        f"<div class='sb-rl'>{_html.escape(perfil)}</div></div>"
        "</div>"
    )


# ------------------------------------------------------------------
# CSS
# ------------------------------------------------------------------
_RADIO = '[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"]'


def _css_nav_dinamico(itens_nav, mostrar_secoes: bool) -> str:
    """nth-child por item (ícone) + rótulo de seção no 1º item de cada grupo
    presente. Gerado a partir da lista REAL de itens => vendedor nunca recebe
    rótulo de seção vazio."""
    regras = []
    for i, it in enumerate(itens_nav, start=1):
        ic = ICONE_NAV.get(it)
        if ic:
            regras.append(f"{_RADIO} > label:nth-child({i})::before{{-webkit-mask-image:{_uri(ic)};mask-image:{_uri(ic)};}}")
    if mostrar_secoes:
        primeira = True
        for titulo, membros in GRUPOS_NAV:
            presentes = [m for m in membros if m in itens_nav]
            if not presentes:
                continue
            i = itens_nav.index(presentes[0]) + 1
            topo = 28
            regras.append(
                f"{_RADIO} > label:nth-child({i}){{margin-top:{topo}px !important;}}"
                f"{_RADIO} > label:nth-child({i})::after{{content:'{titulo.upper()}';}}"
            )
            primeira = False
    else:
        regras.append(f"{_RADIO} > label:nth-child(1){{margin-top:20px !important;}}")
    return "\n".join(regras)


def _css_icones(nomes) -> str:
    return "\n".join(f"--ic-{n}:{_uri(n)};" for n in sorted(set(nomes)))


def css_sidebar(itens_nav, simuladores, *, logado: bool, online: bool = True) -> str:
    """CSS completo da sidebar. `itens_nav`: opções do radio na ordem em que
    aparecem; `simuladores`: chaves dos simuladores liberados."""
    icones_usados = {"chevron", "log-out", "sparkles", "file-text", "arrow-up-right", "calculator", "lock"}
    icones_usados |= {ICONE_NAV[i] for i in itens_nav if i in ICONE_NAV}
    icones_usados |= {SIMULADORES_UI[s][0] for s in simuladores if s in SIMULADORES_UI}
    cor_on = "22,163,74"      # green-600
    cor_off = "220,38,38"     # red-600
    c_rgb = cor_on if online else cor_off
    c_txt = "#15803d" if online else "#b91c1c"
    pulso = "animation:sbPulse 2.2s ease-out infinite;" if online else ""

    # Simuladores pertencem a "Ferramentas": se nenhum item desse grupo está no menu
    # (ex.: vendedor), o próprio grupo recolhível leva o rótulo da seção.
    _tem_ferr = any(m in itens_nav for m in GRUPOS_NAV[2][1])
    css_exp_label = "" if (_tem_ferr or not logado) else (
        '[data-testid="stSidebar"] [data-testid="stExpander"] {margin-top:30px !important;}'
        '[data-testid="stSidebar"] [data-testid="stExpander"]::before {content:"FERRAMENTAS";position:absolute;left:10px;top:-22px;'
        'font-size:10.5px;font-weight:600;line-height:16px;letter-spacing:.09em;color:var(--sb-muted);pointer-events:none;}')
    return f"""<style>
/* =====================================================================
   SIDEBAR — Portal Consorbens (tokens + componentes)
   ===================================================================== */
[data-testid="stSidebar"] {{
  --sb-text:#334155; --sb-strong:#0f172a; --sb-muted:#64748b;
  --sb-line:#e6ebf2; --sb-hover:rgba(15,23,42,.05);
  --sb-act-bg:var(--brand-soft); --sb-act-fg:var(--brand-dark,#1f5b55);
  --sb-r:8px; --sb-h:34px; --sb-ease:cubic-bezier(.22,1,.36,1);
  {_css_icones(icones_usados)}
  border-right:1px solid var(--sb-line) !important; box-shadow:none !important;
}}
[data-testid="stSidebar"] > div:first-child {{ background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%) !important; }}

/* ---- Estrutura: cabeçalho nativo sobreposto (só o botão de recolher), conteúdo em coluna ---- */
[data-testid="stSidebarHeader"] {{ position:absolute !important; top:0; right:0; left:auto; width:auto !important;
  height:40px !important; padding:8px 10px 0 0 !important; z-index:5; background:transparent !important; }}
[data-testid="stSidebarHeader"] [data-testid="stLogoSpacer"] {{ display:none !important; }}
[data-testid="stSidebarContent"] {{ display:flex !important; flex-direction:column; min-height:100%; padding:0 !important; scrollbar-gutter:auto !important; }}
[class*="st-key-sb_"] {{ flex:0 0 auto !important; }}
[data-testid="stSidebarUserContent"] {{ margin:0 !important; width:100% !important; flex:1 1 auto; display:flex; flex-direction:column; padding:20px 12px 0 12px !important; }}
[data-testid="stSidebarUserContent"] > div {{ flex:1 1 auto; display:flex; flex-direction:column; }}
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {{ flex:1 1 auto; gap:0 !important; }}
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"],
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] {{ width:100%; }}
[data-testid="stSidebar"] hr {{ display:none !important; }}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style:only-child) {{ display:none; }}

/* ---- Marca ---- */
[data-testid="stSidebar"] .st-key-sb_brand {{ align-items:center !important; gap:0 !important; padding:0 0 4px; }}
[data-testid="stSidebar"] .st-key-sb_brand [data-testid="stElementToolbar"] {{ display:none !important; }}
[data-testid="stSidebar"] .st-key-sb_brand [data-testid="stFullScreenFrame"] > div,
[data-testid="stSidebar"] .st-key-sb_brand [data-testid="stImage"],
[data-testid="stSidebar"] .st-key-sb_brand [data-testid="stImageContainer"] {{ display:flex; justify-content:center !important; align-items:center !important; width:100% !important; }}
[data-testid="stSidebar"] .st-key-sb_brand img {{ width:140px !important; max-width:100% !important; height:auto !important; }}

/* ---- Status do robô (pill) ---- */
[data-testid="stSidebar"] .st-key-sb_robo {{ align-items:center !important; margin-top:10px; width:100%; }}
[data-testid="stSidebar"] .st-key-sb_robo [data-testid="stButton"],
[data-testid="stSidebar"] .st-key-sb_robo [data-testid="stTooltipIcon"],
[data-testid="stSidebar"] .st-key-sb_robo [data-testid="stTooltipHoverTarget"] {{ display:flex; justify-content:center !important; width:100%; }}
[data-testid="stSidebar"] .st-key-sb_robo button {{
  height:24px !important; min-height:24px !important; padding:0 10px 0 8px !important; gap:6px;
  border:1px solid rgba({c_rgb},.28) !important; background:rgba({c_rgb},.07) !important;
  border-radius:999px !important; box-shadow:none !important; transform:none !important; width:auto !important;
  transition:background-color .15s var(--sb-ease), border-color .15s var(--sb-ease) !important;
}}
[data-testid="stSidebar"] .st-key-sb_robo button::before {{
  content:""; width:7px; height:7px; border-radius:50%; background:rgb({c_rgb}); flex:none; {pulso}
}}
[data-testid="stSidebar"] .st-key-sb_robo button p {{
  color:{c_txt} !important; font-size:11.5px !important; font-weight:600 !important; letter-spacing:.01em; margin:0 !important; line-height:1 !important;
}}
[data-testid="stSidebar"] .st-key-sb_robo button:hover:not(:disabled) {{ background:rgba({c_rgb},.13) !important; border-color:rgba({c_rgb},.5) !important; }}
[data-testid="stSidebar"] .st-key-sb_robo button:disabled {{ opacity:1 !important; cursor:default; }}
@keyframes sbPulse {{ 0% {{ box-shadow:0 0 0 0 rgba({c_rgb},.45); }} 70%,100% {{ box-shadow:0 0 0 6px rgba({c_rgb},0); }} }}

/* ---- Navegação (radio => lista de itens com ícone) ---- */
[data-testid="stSidebar"] [data-testid="stRadio"] {{ margin:0; }}
{_RADIO} {{ gap:0 !important; align-items:stretch !important; width:100%; }}
{_RADIO} > label {{
  position:relative; display:flex !important; align-items:center; gap:10px;
  width:100%; box-sizing:border-box; height:var(--sb-h); min-height:var(--sb-h); padding:0 10px !important; margin:1px 0 !important;
  border-radius:var(--sb-r) !important; cursor:pointer; overflow:visible !important; background:transparent !important;
  transition:background-color .15s var(--sb-ease), color .15s var(--sb-ease) !important;
}}
/* ícone do item */
{_RADIO} > label::before {{
  content:""; flex:none; width:18px; height:18px; background-color:var(--sb-muted);
  -webkit-mask:center/18px 18px no-repeat; mask:center/18px 18px no-repeat;
  transition:background-color .15s var(--sb-ease);
}}
/* rótulo de seção (aparece só no 1º item de cada grupo — ver regras geradas) */
{_RADIO} > label::after {{
  position:absolute; left:10px; top:-22px; font-size:10.5px; font-weight:600; line-height:16px;
  letter-spacing:.09em; color:var(--sb-muted); pointer-events:none;
}}
/* bolinha nativa do radio vira a barra de destaque */
{_RADIO} > label > div > div > div:first-child {{
  position:absolute; left:0; top:7px; bottom:7px; width:3px; border-radius:0 3px 3px 0; padding:0 !important; margin:0 !important;
  background:var(--brand) !important; border:none !important; box-shadow:none !important; transform:scaleY(0); transition:transform .2s var(--sb-ease);
}}
{_RADIO} > label > div > div > div:first-child * {{ display:none !important; }}
{_RADIO} > label > div, {_RADIO} > label > div > div {{ margin:0 !important; padding:0 !important; min-width:0; }}
{_RADIO} > label p {{ margin:0 !important; font-size:14px !important; font-weight:500 !important; line-height:20px !important; color:var(--sb-text) !important;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; transition:color .15s var(--sb-ease); }}
{_RADIO} > label:hover {{ background:var(--sb-hover) !important; }}
{_RADIO} > label:hover p {{ color:var(--sb-strong) !important; }}
{_RADIO} > label:hover::before {{ background-color:var(--sb-strong); }}
{_RADIO} > label:has(input:checked) {{ background:var(--sb-act-bg) !important; }}
{_RADIO} > label:has(input:checked) > div > div > div:first-child {{ transform:scaleY(1); }}
{_RADIO} > label:has(input:checked) p {{ color:var(--sb-act-fg) !important; font-weight:600 !important; }}
{_RADIO} > label:has(input:checked)::before {{ background-color:var(--brand); }}
{_RADIO} > label:has(input:focus-visible) {{ outline:2px solid var(--brand); outline-offset:1px; }}
{_css_nav_dinamico(itens_nav, mostrar_secoes=logado)}

/* ---- Simuladores (grupo recolhível, mesma linguagem dos itens) ---- */
{css_exp_label}
[data-testid="stSidebar"] [data-testid="stExpander"] {{
  border:none !important; background:transparent !important; box-shadow:none !important; border-radius:var(--sb-r) !important;
  overflow:visible !important; margin:1px 0 0; transform:none !important;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ border:none !important; background:transparent !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary {{ background:transparent; border:none !important; box-shadow:none !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary:hover {{ background:var(--sb-hover) !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {{
  display:flex; align-items:center; height:var(--sb-h); min-height:var(--sb-h); padding:0 10px !important; gap:0;
  border-radius:var(--sb-r) !important; cursor:pointer; list-style:none; position:relative;
  transition:background-color .15s var(--sb-ease) !important;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] summary::-webkit-details-marker {{ display:none; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {{ background:var(--sb-hover) !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:focus-visible {{ outline:2px solid var(--brand); outline-offset:1px; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary [data-testid="stIconMaterial"], [data-testid="stSidebar"] [data-testid="stExpander"] summary span:has(> [data-testid="stIconMaterial"]) {{ display:none !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary span {{ display:flex; align-items:center; gap:0; min-width:0; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p {{
  margin:0 !important; display:flex; align-items:center; gap:10px; font-size:14px !important; font-weight:500 !important;
  line-height:20px !important; color:var(--sb-text) !important;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover p {{ color:var(--sb-strong) !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p::before {{
  content:""; flex:none; width:18px; height:18px; background-color:var(--sb-muted);
  -webkit-mask:var(--ic-calculator) center/18px 18px no-repeat; mask:var(--ic-calculator) center/18px 18px no-repeat;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] summary::after {{
  content:""; position:absolute; right:10px; top:50%; width:16px; height:16px; margin-top:-8px; background-color:var(--sb-muted);
  -webkit-mask:var(--ic-chevron) center/16px 16px no-repeat; mask:var(--ic-chevron) center/16px 16px no-repeat;
  transition:transform .2s var(--sb-ease);
}}
[data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary::after {{ transform:rotate(90deg); }}
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] {{ padding:2px 0 4px !important; border:none !important; }}
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] [data-testid="stVerticalBlock"] {{ gap:1px !important; }}

/* subitens: botões dos simuladores + link Cartas Contempladas */
[data-testid="stSidebar"] .st-key-sb_sims button,
[data-testid="stSidebar"] .st-key-sb_sims a,
[data-testid="stSidebar"] .st-key-sb_cartas a {{
  position:relative; width:100% !important; height:32px !important; min-height:32px !important; padding:0 28px 0 38px !important;
  justify-content:flex-start !important; text-align:left; gap:0;
  border:none !important; background:transparent !important; box-shadow:none !important; transform:none !important;
  border-radius:var(--sb-r) !important; text-decoration:none !important; color:var(--sb-text) !important;
  transition:background-color .15s var(--sb-ease), color .15s var(--sb-ease) !important;
}}
[data-testid="stSidebar"] .st-key-sb_sims button > div, [data-testid="stSidebar"] .st-key-sb_sims a > div,
[data-testid="stSidebar"] .st-key-sb_cartas a > div {{ justify-content:flex-start !important; width:100%; }}
[data-testid="stSidebar"] .st-key-sb_sims button p, [data-testid="stSidebar"] .st-key-sb_sims a p,
[data-testid="stSidebar"] .st-key-sb_cartas a p {{
  margin:0 !important; font-size:13.5px !important; font-weight:500 !important; line-height:20px !important; color:inherit !important;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:left;
}}
[data-testid="stSidebar"] .st-key-sb_sims button::before, [data-testid="stSidebar"] .st-key-sb_sims a::before,
[data-testid="stSidebar"] .st-key-sb_cartas a::before {{
  content:""; position:absolute; left:11px; top:50%; width:16px; height:16px; margin-top:-8px; background-color:var(--sb-muted);
  -webkit-mask:center/16px 16px no-repeat; mask:center/16px 16px no-repeat; transition:background-color .15s var(--sb-ease);
}}
[data-testid="stSidebar"] .st-key-sb_sims a::after, [data-testid="stSidebar"] .st-key-sb_cartas a::after {{
  content:""; position:absolute; right:10px; top:50%; width:14px; height:14px; margin-top:-7px; background-color:var(--sb-muted); opacity:.7;
  -webkit-mask:var(--ic-arrow-up-right) center/14px 14px no-repeat; mask:var(--ic-arrow-up-right) center/14px 14px no-repeat;
}}
[data-testid="stSidebar"] .st-key-sb_sims a::before, [data-testid="stSidebar"] .st-key-sb_cartas a::before {{
  -webkit-mask-image:var(--ic-file-text); mask-image:var(--ic-file-text);
}}
[data-testid="stSidebar"] .st-key-sb_sims button:hover, [data-testid="stSidebar"] .st-key-sb_sims a:hover,
[data-testid="stSidebar"] .st-key-sb_cartas a:hover {{ background:var(--sb-hover) !important; color:var(--sb-strong) !important; }}
[data-testid="stSidebar"] .st-key-sb_sims button:hover::before, [data-testid="stSidebar"] .st-key-sb_sims a:hover::before,
[data-testid="stSidebar"] .st-key-sb_cartas a:hover::before {{ background-color:var(--sb-strong); }}
[data-testid="stSidebar"] .st-key-sb_sims button[kind="primary"] {{
  background:var(--sb-act-bg) !important; color:var(--sb-act-fg) !important; font-weight:600 !important; box-shadow:none !important;
}}
[data-testid="stSidebar"] .st-key-sb_sims button[kind="primary"] p {{ font-weight:600 !important; }}
[data-testid="stSidebar"] .st-key-sb_sims button[kind="primary"]::before {{ background-color:var(--brand); }}
[data-testid="stSidebar"] .st-key-sb_sims button:focus-visible, [data-testid="stSidebar"] .st-key-sb_cartas a:focus-visible,
[data-testid="stSidebar"] .st-key-sb_sims a:focus-visible {{ outline:2px solid var(--brand) !important; outline-offset:1px; }}
{"".join(f'[data-testid="stSidebar"] .st-key-{key_simulador(s)} button::before{{-webkit-mask-image:var(--ic-{SIMULADORES_UI[s][0]});mask-image:var(--ic-{SIMULADORES_UI[s][0]});}}' for s in simuladores if s in SIMULADORES_UI)}

/* ---- Link "Cartas Contempladas" do visitante (e do usuário sem simuladores) ---- */
[data-testid="stSidebar"] .st-key-sb_cartas {{ margin-top:1px; }}
[data-testid="stSidebar"] .st-key-sb_cartas a {{ padding-left:38px !important; height:var(--sb-h) !important; min-height:var(--sb-h) !important; }}

/* ---- Rodapé ancorado: Bento + cartão do usuário ---- */
[data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has(> .st-key-sb_footer) {{
  margin:auto -12px 0 !important; position:sticky; bottom:0; z-index:3; width:calc(100% + 24px) !important; max-width:none !important;
}}
[data-testid="stSidebar"] .st-key-sb_footer {{
  padding:12px 12px 16px; gap:8px !important; border-top:1px solid var(--sb-line); background:linear-gradient(180deg,#fbfcfd,#f8fafc);
}}
/* Bento: popover com cara de item (ícone na cor da marca + selo IA) */
[data-testid="stSidebar"] [data-testid="stPopoverButton"] {{
  position:relative; height:38px !important; min-height:38px !important; padding:0 38px 0 38px !important; width:100% !important;
  justify-content:flex-start !important; background:#fff !important; border:1px solid var(--sb-line) !important;
  border-radius:10px !important; box-shadow:0 1px 2px rgba(15,23,42,.04) !important; transform:none !important;
  transition:border-color .15s var(--sb-ease), box-shadow .15s var(--sb-ease), background-color .15s var(--sb-ease) !important;
}}
[data-testid="stSidebar"] [data-testid="stPopoverButton"]:hover {{ border-color:var(--brand-mid) !important; background:#fff !important; box-shadow:0 2px 8px rgba(15,23,42,.07) !important; transform:none !important; }}
[data-testid="stSidebar"] [data-testid="stPopoverButton"]:focus-visible {{ outline:2px solid var(--brand); outline-offset:1px; }}
[data-testid="stSidebar"] [data-testid="stPopoverButton"] > div, [data-testid="stSidebar"] [data-testid="stPopoverButton"] > div > div:first-child,
[data-testid="stSidebar"] [data-testid="stPopoverButton"] span {{ justify-content:flex-start !important; text-align:left !important; width:100%; margin:0 !important; }}
[data-testid="stSidebar"] [data-testid="stPopoverButton"] > div > div:last-child {{ display:none !important; }}
[data-testid="stSidebar"] [data-testid="stPopoverButton"] p {{ margin:0 !important; font-size:13.5px !important; font-weight:600 !important; color:var(--sb-strong) !important; line-height:20px !important; }}
[data-testid="stSidebar"] [data-testid="stPopoverButton"]::before {{
  content:""; position:absolute; left:11px; top:50%; width:18px; height:18px; margin-top:-9px; background-color:var(--brand);
  -webkit-mask:var(--ic-sparkles) center/18px 18px no-repeat; mask:var(--ic-sparkles) center/18px 18px no-repeat;
}}
[data-testid="stSidebar"] [data-testid="stPopoverButton"]::after {{
  content:"IA"; position:absolute; right:10px; top:50%; margin-top:-8px; height:16px; line-height:16px; padding:0 6px; border-radius:999px;
  font-size:9.5px; font-weight:700; letter-spacing:.06em; color:var(--sb-act-fg); background:var(--brand-soft);
}}

/* Cartão do usuário + sair */
[data-testid="stSidebar"] .st-key-sb_user {{
  position:relative; border:1px solid var(--sb-line); border-radius:12px; background:#fff; padding:8px 44px 8px 8px; box-shadow:0 1px 2px rgba(15,23,42,.04);
}}
[data-testid="stSidebar"] .st-key-sb_user [data-testid="stVerticalBlock"] {{ gap:0 !important; }}
[data-testid="stSidebar"] .st-key-sb_user [data-testid="stElementContainer"]:has(.sb-user),
[data-testid="stSidebar"] .st-key-sb_user [data-testid="stElementContainer"]:has(.sb-user) *:not(.sb-user):not(.sb-user *) {{ height:auto !important; min-height:34px; }}
[data-testid="stSidebar"] .st-key-sb_user .sb-user {{ height:34px !important; min-height:0; }}
[data-testid="stSidebar"] .sb-user {{ display:flex; align-items:center; gap:10px; min-width:0; }}
[data-testid="stSidebar"] .sb-av {{
  flex:none; width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center;
  font-size:12.5px; font-weight:700; letter-spacing:.02em; color:#fff;
  background:linear-gradient(135deg,var(--brand),var(--brand-dark,var(--brand))); box-shadow:inset 0 0 0 1px rgba(255,255,255,.18);
}}
[data-testid="stSidebar"] .sb-ui {{ min-width:0; line-height:1.25; }}
[data-testid="stSidebar"] .sb-nm {{ font-size:13px; font-weight:600; color:var(--sb-strong); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
[data-testid="stSidebar"] .sb-rl {{ font-size:11.5px; font-weight:500; color:var(--sb-muted); white-space:nowrap; }}
[data-testid="stSidebar"] .st-key-sb_logout {{ position:absolute !important; right:8px; top:50%; margin:-16px 0 0 !important; width:32px !important; height:32px !important; }}
[data-testid="stSidebar"] .st-key-sb_user [data-testid="stMarkdownContainer"] {{ margin:0 !important; }}
[data-testid="stSidebar"] .st-key-sb_logout button {{
  width:32px !important; height:32px !important; min-height:32px !important; padding:0 !important; border:none !important; background:transparent !important;
  box-shadow:none !important; border-radius:8px !important; transform:none !important; position:relative; font-size:0 !important;
  transition:background-color .15s var(--sb-ease) !important;
}}
[data-testid="stSidebar"] .st-key-sb_logout button * {{ font-size:0 !important; }}
[data-testid="stSidebar"] .st-key-sb_logout button::before {{
  content:""; position:absolute; inset:0; margin:auto; width:18px; height:18px; background-color:var(--sb-muted);
  -webkit-mask:var(--ic-log-out) center/18px 18px no-repeat; mask:var(--ic-log-out) center/18px 18px no-repeat; transition:background-color .15s var(--sb-ease);
}}
[data-testid="stSidebar"] .st-key-sb_logout button:hover {{ background:rgba(220,38,38,.09) !important; }}
[data-testid="stSidebar"] .st-key-sb_logout button:hover::before {{ background-color:#dc2626; }}
[data-testid="stSidebar"] .st-key-sb_logout button:focus-visible {{ outline:2px solid #dc2626 !important; outline-offset:1px; }}

@media (prefers-reduced-motion: reduce) {{
  [data-testid="stSidebar"] * {{ transition:none !important; animation:none !important; }}
}}
</style>"""
