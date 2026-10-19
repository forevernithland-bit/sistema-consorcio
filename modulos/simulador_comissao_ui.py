"""Simulador de comissionamento do VENDEDOR — toda a camada visual/UX.

`render_simulador(df_admin, cfg, master=False)` mostra um painel escuro (verde-petróleo + dourado) com:
  - campo de valor + barra (st.slider) SINCRONIZADOS por callbacks (digitar move a barra, arrastar muda o campo);
  - cartão herói com a comissão total estimada e a mensagem do próximo prêmio;
  - trilha com os marcos dos bônus (🔒/✅);
  - SEMPRE os 4 próximos meses de recebimento (Mês 1..4), mesmo que algum seja R$ 0 (bônus travado);
  - simulação avançada (vários meses) dentro de um expander;
  - na versão master, o bloco do lado da Consorbens (a versão do vendedor nunca mostra nada da corretora).

A matemática vem toda de comissao_vendedor (regra/nivel/percentuais_por_posicao/simular); aqui só se apresenta.
Limites e percentuais dos prêmios são lidos de cv.regra(cfg) — nunca fixos no texto.

Todo "R$" em texto vai com o cifrão escapado (`&#36;` no HTML, `\\$` no markdown): dois "$" no mesmo
texto viram LaTeX no st.markdown.
"""
import math
import re
from datetime import datetime

import pandas as pd
import streamlit as st

import comissao_vendedor as cv
from ui_valores import fmt_valor, input_valor, parse_valor
from utils import parse_float_safe

_MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
          "Outubro", "Novembro", "Dezembro"]

PADRAO_INICIAL = 600_000.0      # valor com que a tela abre (mostra Bônus 1 liberado e o Bônus 2 por perto)
PASSO_BARRA = 10_000
BARRA_MIN_MAX = 3_000_000
TETO_VALOR = 1_000_000_000_000.0   # só para não estourar a tela com um zero a mais digitado sem querer


# ==========================================================================
# formatação (sempre com milhar; "$" escapado)
# ==========================================================================
def _num(v, forcar_centavos=False):
    """12500 -> '12.500' ; 12345.6 -> '12.345,60'."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = 0.0
    if not forcar_centavos and abs(v - round(v)) < 0.005:
        return fmt_valor(round(v), 0)
    return fmt_valor(v, 2)


def _h(v, centavos=False):
    """'R$ 1.000' para HTML (cifrão como entidade, espaço sem quebra)."""
    return "R&#36;&nbsp;" + _num(v, centavos)


def _t(v, centavos=False):
    """'R$ 1.000' para st.markdown/st.caption (cifrão escapado)."""
    return "R\\$ " + _num(v, centavos)


def _pct(x):
    """0.25 -> '0,25%' ; 1.5 -> '1,5%' ; 1.0 -> '1%'."""
    t = f"{float(x):.2f}"
    t = t[:-3] if t.endswith(".00") else (t[:-1] if t.endswith("0") else t)
    return t.replace(".", ",") + "%"


def _curto(v):
    """500000 -> '500 mil' ; 1000000 -> '1 milhão' ; 2500000 -> '2,5 milhões' (rótulos de marco)."""
    if v >= 1_000_000:
        m = v / 1_000_000
        s = f"{m:.1f}".replace(".", ",").replace(",0", "")
        return f"{s} milhão" if m < 2 else f"{s} milhões"
    if v >= 1000:
        return f"{v / 1000:.0f} mil"
    return _num(v)


def _curto_mi(v):
    """Versão compacta para a barra: 500 mil / 1 mi / 2,5 mi."""
    if v >= 1_000_000:
        s = f"{v / 1_000_000:.1f}".replace(".", ",").replace(",0", "")
        return f"{s} mi"
    return _curto(v)


def _rot_mes(ym):
    return f"{_MESES[int(ym[5:7])]}/{ym[:4]}"


def _rot_mes_curto(ym):
    return f"{_MESES[int(ym[5:7])][:3]}/{ym[2:4]}"


# ==========================================================================
# entrada de valor: campo de texto + barra sincronizados
# ==========================================================================
def _fmt_campo(v):
    return fmt_valor(v, 0) if abs(v - round(v)) < 0.005 else fmt_valor(v, 2)


def _snap(v, smax):
    return int(min(max(round(v / PASSO_BARRA) * PASSO_BARRA, 0), smax))


# ==========================================================================
# CSS (escopo: só dentro de .st-key-sim_comissao)
# ==========================================================================
_CSS = """
<style>
.st-key-sim_comissao{
  --g1:#f6d27a; --g2:#e3a93a; --t1:#2d6a65; --t2:#49b3a6; --ink:#eef7f5; --mut:rgba(238,247,245,.68);
  --line:rgba(255,255,255,.13); --card:rgba(255,255,255,.065);
  position:relative; color:var(--ink); gap:1.05rem !important;
  padding:28px 30px 26px; border-radius:26px; overflow:hidden;
  border:1px solid rgba(246,210,122,.22);
  background:
    radial-gradient(620px 300px at 104% -6%, rgba(246,210,122,.17), transparent 62%),
    radial-gradient(760px 420px at -8% 4%, rgba(73,179,166,.30), transparent 60%),
    linear-gradient(168deg,#071a19 0%,#0b2523 48%,#0f3532 100%);
  box-shadow:0 26px 60px rgba(7,26,25,.38), inset 0 1px 0 rgba(255,255,255,.08);
}
.st-key-sim_comissao p, .st-key-sim_comissao li{color:var(--ink);}
.st-key-sim_comissao [data-testid="stHtml"], .st-key-sim_comissao [data-testid="stMarkdownContainer"]{color:var(--ink);}

/* ---------- cabeçalho ---------- */
.sc-head .sc-eye{font-size:.72rem;letter-spacing:.16em;font-weight:700;color:var(--g1);text-transform:uppercase;}
.sc-head h3{margin:.25rem 0 .2rem !important;font-size:1.65rem !important;line-height:1.15 !important;color:#fff !important;
  font-family:'Plus Jakarta Sans','Inter',sans-serif;font-weight:800;letter-spacing:-.01em !important;padding:0 !important;}
.sc-head p{margin:0;color:var(--mut);font-size:.95rem;}
.sc-tagm{display:inline-block;margin-left:8px;padding:2px 9px;border-radius:99px;font-size:.66rem;letter-spacing:.08em;
  background:rgba(246,210,122,.16);color:var(--g1);border:1px solid rgba(246,210,122,.35);vertical-align:middle;font-weight:700;}

/* ---------- herói ---------- */
.sc-hero{position:relative;border-radius:22px;padding:22px 24px 20px;overflow:hidden;
  background:linear-gradient(135deg,rgba(255,255,255,.10),rgba(255,255,255,.035));
  border:1px solid rgba(246,210,122,.30);
  box-shadow:0 14px 40px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.12);}
.sc-hero::after{content:"";position:absolute;right:-70px;top:-70px;width:240px;height:240px;border-radius:50%;
  background:radial-gradient(circle,rgba(246,210,122,.28),transparent 68%);pointer-events:none;}
.sc-hero .sc-lbl{font-size:.78rem;letter-spacing:.1em;font-weight:700;color:var(--mut);text-transform:uppercase;}
.sc-big{font-family:'Plus Jakarta Sans','Inter',sans-serif;font-weight:800;letter-spacing:-.035em;line-height:1.02;
  font-size:clamp(2.7rem,8.6vw,4.7rem);margin:.28rem 0 .35rem;
  background:linear-gradient(180deg,#fff3c9 0%,var(--g1) 38%,var(--g2) 100%);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;
  filter:drop-shadow(0 4px 18px rgba(227,169,58,.28));word-break:break-word;}
.sc-big .cur{font-size:.42em;letter-spacing:0;margin-right:.18em;font-weight:700;vertical-align:.52em;}
.sc-big .cts{font-size:.42em;letter-spacing:0;vertical-align:.52em;}
.sc-hero .sc-sub{font-size:1.02rem;line-height:1.5;color:var(--ink);max-width:62ch;}
.sc-hero .sc-sub b{color:#fff;}
.sc-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;}
.sc-chip{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:99px;font-size:.82rem;font-weight:600;
  background:rgba(255,255,255,.08);border:1px solid var(--line);color:var(--ink);}
.sc-chip.gold{background:rgba(246,210,122,.15);border-color:rgba(246,210,122,.45);color:var(--g1);}

/* ---------- controles ---------- */
.st-key-sim_ctrl{gap:.35rem !important;}
.st-key-sim_ctrl [data-testid="stWidgetLabel"] p, .st-key-sim_ctrl label p{color:var(--mut) !important;font-size:.8rem !important;
  font-weight:700 !important;letter-spacing:.08em;text-transform:uppercase;}
.st-key-sim_ctrl [data-testid="stTextInputRootElement"], .st-key-sim_ctrl .stTextInput div[data-baseweb="input"],
.st-key-sim_ctrl .stTextInput div[data-baseweb="base-input"]{
  background:rgba(255,255,255,.075) !important;border:1.5px solid rgba(246,210,122,.45) !important;border-radius:16px !important;
  box-shadow:none !important;min-height:64px;align-items:center;}
.st-key-sim_ctrl [data-testid="stTextInputRootElement"]::before, .st-key-sim_ctrl .stTextInput div[data-baseweb="input"]::before{
  content:"R\\0024";padding:0 2px 0 18px;font-weight:800;font-size:1.3rem;color:var(--g1);align-self:center;
  font-family:'Plus Jakarta Sans','Inter',sans-serif;}
.st-key-sim_ctrl [data-testid="stTextInputRootElement"]:focus-within, .st-key-sim_ctrl .stTextInput div[data-baseweb="input"]:focus-within{
  border-color:var(--g1) !important;box-shadow:0 0 0 4px rgba(246,210,122,.2) !important;background:rgba(255,255,255,.11) !important;}
.st-key-sim_ctrl .stTextInput input{background:transparent !important;border:none !important;color:#fff !important;-webkit-text-fill-color:#fff !important;
  font-size:2rem !important;font-weight:800 !important;font-family:'Plus Jakarta Sans','Inter',sans-serif;letter-spacing:-.02em;
  padding:10px 16px 10px 6px !important;caret-color:var(--g1);height:62px;}
.st-key-sim_ctrl .stTextInput input::placeholder{color:rgba(255,255,255,.35) !important;-webkit-text-fill-color:rgba(255,255,255,.35) !important;}
.sc-warn{margin:2px 2px 0;font-size:.85rem;color:#ffd7a1;background:rgba(255,160,60,.12);border:1px solid rgba(255,160,60,.35);
  padding:7px 12px;border-radius:10px;}

/* barra (slider) */
.st-key-sim_ctrl [data-testid="stSlider"]{padding:0 12px;}
.st-key-sim_ctrl [data-testid="stSliderThumbValue"], .st-key-sim_ctrl [data-testid="stSliderTickBar"]{display:none !important;}
.st-key-sim_ctrl [data-testid="stSlider"] [data-orientation="horizontal"] > div:first-child{height:9px !important;border-radius:9px !important;
  filter:brightness(1.28) saturate(1.1);}
.st-key-sim_ctrl [data-testid="stSlider"] div[style*="translate(-50%"], .st-key-sim_ctrl [data-testid="stSlider"] [role="slider"]{
  width:30px !important;height:30px !important;background:linear-gradient(180deg,#fff3c9,var(--g2)) !important;border-radius:50% !important;
  border:3px solid #0b2523 !important;box-shadow:0 0 0 3px rgba(246,210,122,.55),0 6px 16px rgba(0,0,0,.45) !important;}
.st-key-sim_ctrl [data-testid="stSlider"] div[style*="translate(-50%"]:focus-within{box-shadow:0 0 0 5px rgba(246,210,122,.75),0 6px 16px rgba(0,0,0,.45) !important;}

/* marcos sob a barra */
.sc-marks{position:relative;height:56px;margin:-10px 18px 6px;}
.sc-mk{position:absolute;top:0;transform:translateX(-50%);display:flex;flex-direction:column;align-items:center;text-align:center;}
.sc-mk i{display:block;width:2px;height:12px;background:rgba(255,255,255,.35);border-radius:2px;margin-bottom:3px;}
.sc-mk .ic{font-size:1rem;line-height:1;}
.sc-mk .tx{font-size:.74rem;font-weight:700;color:var(--mut);white-space:nowrap;}
.sc-mk.on i{background:var(--g1);box-shadow:0 0 10px rgba(246,210,122,.8);}
.sc-mk.on .tx{color:var(--g1);}
.sc-mk.edge{transform:none;}
.sc-mk.edge.l{left:0 !important;align-items:flex-start;} .sc-mk.edge.r{right:0;left:auto !important;align-items:flex-end;}
.sc-mk.edge i{opacity:.0;}

/* prêmios */
.sc-prizes{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.sc-pz{border-radius:16px;padding:12px 14px;background:var(--card);border:1px solid var(--line);display:flex;gap:11px;align-items:flex-start;}
.sc-pz .ic{font-size:1.4rem;line-height:1.1;}
.sc-pz b{display:block;font-size:.95rem;color:#fff;}
.sc-pz span{display:block;font-size:.8rem;color:var(--mut);line-height:1.35;margin-top:2px;}
.sc-pz.on{background:linear-gradient(135deg,rgba(246,210,122,.20),rgba(246,210,122,.06));border-color:rgba(246,210,122,.55);}
.sc-pz.on b{color:var(--g1);}

/* meta / próximo prêmio */
.sc-goal{border-radius:16px;padding:14px 18px;font-size:1.02rem;line-height:1.5;
  background:linear-gradient(90deg,rgba(73,179,166,.24),rgba(73,179,166,.08));border:1px solid rgba(73,179,166,.55);color:var(--ink);}
.sc-goal b{color:#fff;} .sc-goal .gd{color:var(--g1);font-weight:800;}
.sc-goal.max{background:linear-gradient(90deg,rgba(246,210,122,.24),rgba(246,210,122,.07));border-color:rgba(246,210,122,.6);}

/* seções */
.sc-sec{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:.35rem 0 .1rem;}
.sc-sec h4{letter-spacing:-.01em !important;margin:0 !important;padding:0 !important;color:#fff !important;font-size:1.12rem !important;font-weight:800;font-family:'Plus Jakarta Sans','Inter',sans-serif;}
.sc-sec small{color:var(--mut);font-size:.82rem;}

/* 4 meses */
.sc-meses{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;}
.sc-m{position:relative;border-radius:18px;padding:14px 15px 14px;min-width:0;background:var(--card);border:1px solid var(--line);
  display:flex;flex-direction:column;gap:3px;}
.sc-m .top{display:flex;justify-content:space-between;align-items:center;gap:6px;}
.sc-m .n{font-size:.7rem;letter-spacing:.14em;font-weight:800;color:var(--g1);}
.sc-m .tag{font-size:.68rem;font-weight:700;padding:2px 8px;border-radius:99px;background:rgba(255,255,255,.1);color:var(--mut);white-space:nowrap;}
.sc-m .nome{font-size:.9rem;font-weight:600;color:var(--ink);}
.sc-m .val{font-family:'Plus Jakarta Sans','Inter',sans-serif;font-weight:800;font-size:1.45rem;letter-spacing:-.02em;color:#fff;
  line-height:1.15;margin:2px 0 4px;word-break:break-word;}
.sc-m .det{font-size:.78rem;line-height:1.4;color:var(--mut);}
.sc-m .det b{color:var(--ink);font-weight:700;}
.sc-m.ok{border-color:rgba(246,210,122,.4);background:linear-gradient(160deg,rgba(246,210,122,.13),rgba(255,255,255,.04));}
.sc-m.ok .tag{background:rgba(246,210,122,.2);color:var(--g1);}
.sc-m.ok .val{color:var(--g1);}
.sc-m.lock{border-style:dashed;border-color:rgba(255,255,255,.28);background:rgba(255,255,255,.03);}
.sc-m.lock .val{color:rgba(255,255,255,.42);}
.sc-m.lock .tag{background:rgba(255,160,60,.16);color:#ffd7a1;}
.sc-m.lock .det{color:rgba(255,224,178,.92);}
.sc-m.zero .val{color:rgba(255,255,255,.5);}
.sc-soma{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px 18px;margin-top:2px;padding:12px 16px;border-radius:14px;
  background:rgba(255,255,255,.05);border:1px solid var(--line);font-size:.92rem;color:var(--mut);}
.sc-soma b{color:var(--g1);font-size:1.12rem;font-family:'Plus Jakarta Sans','Inter',sans-serif;}

/* gestão: cascata */
.sc-wf{border-radius:20px;padding:18px 20px;background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.025));
  border:1px solid rgba(246,210,122,.3);display:flex;flex-direction:column;gap:12px;}
.sc-wr{display:grid;grid-template-columns:230px minmax(0,1fr) 168px;gap:6px 14px;align-items:center;}
.sc-wr .lb{font-size:.9rem;line-height:1.3;color:var(--ink);font-weight:600;min-width:0;grid-column:1;grid-row:1;}
.sc-wr .lb small{display:block;font-weight:500;color:var(--mut);font-size:.76rem;margin-top:1px;}
.sc-wr .op{display:inline-block;min-width:1.3em;color:var(--g1);font-weight:800;}
.sc-wr .tk{position:relative;height:20px;border-radius:7px;background:rgba(255,255,255,.07);overflow:hidden;grid-column:2;grid-row:1;}
.sc-wr .bar{position:absolute;top:0;bottom:0;border-radius:6px;background:linear-gradient(90deg,#2d6a65,#49b3a6);}
.sc-wr .bar.neg{background:linear-gradient(90deg,#8b3a3a,#e0706a);}
.sc-wr .bar.gold{background:linear-gradient(90deg,#e3a93a,#f6d27a);}
.sc-wr .vl{font-family:'Plus Jakarta Sans','Inter',sans-serif;font-weight:800;font-size:1.05rem;color:#fff;text-align:right;white-space:nowrap;grid-column:3;grid-row:1;}
.sc-wr.res .lb{font-size:1rem;color:#fff;font-weight:800;}
.sc-wr.res .vl{font-size:1.5rem;color:var(--g1);}
.sc-wr.res .bar{background:linear-gradient(90deg,#e3a93a,#f6d27a);box-shadow:0 0 14px rgba(246,210,122,.55);}
.sc-wr.res .tk{height:26px;}
.sc-wr.bad .vl{color:#ff9d96;}
.sc-split{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.sc-t{border-radius:14px;padding:12px 14px;background:var(--card);border:1px solid var(--line);min-width:0;}
.sc-t span{display:block;font-size:.74rem;letter-spacing:.05em;text-transform:uppercase;font-weight:700;color:var(--mut);line-height:1.3;}
.sc-t b{display:block;margin-top:4px;font-size:1.2rem;color:#fff;font-family:'Plus Jakarta Sans','Inter',sans-serif;word-break:break-word;}
.sc-regra{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:.8rem;color:var(--mut);}
.sc-regra span.p{padding:3px 9px;border-radius:99px;background:rgba(255,255,255,.07);border:1px solid var(--line);color:var(--ink);font-weight:600;}
/* gestão: mês a mês */
.sc-tb{border-radius:16px;border:1px solid var(--line);overflow:hidden;background:rgba(255,255,255,.03);}
.sc-tb .sc-sc{max-height:340px;overflow-y:auto;}
.sc-tr{display:grid;grid-template-columns:1.15fr 1fr 1fr 1fr 1.25fr 1.1fr;gap:8px;padding:9px 14px;align-items:center;font-size:.86rem;border-top:1px solid rgba(255,255,255,.07);}
.sc-tr.hd{font-size:.7rem;letter-spacing:.05em;text-transform:uppercase;font-weight:800;color:var(--mut);background:rgba(255,255,255,.06);border-top:none;line-height:1.25;}
.sc-tb.n8 .sc-tr{grid-template-columns:1.05fr repeat(7,minmax(0,1fr));gap:6px;padding:9px 12px;font-size:.82rem;}
.sc-tb.n8 .sc-tr.hd{font-size:.66rem;}
.sc-tr > div{min-width:0;}
.sc-tr small{display:block;color:var(--mut);font-size:.7rem;font-weight:500;}
.sc-tr .m{font-weight:700;color:#fff;}
.sc-tr .fi{font-weight:800;color:var(--g1);}
.sc-tr.tt{background:linear-gradient(90deg,rgba(246,210,122,.16),rgba(246,210,122,.05));font-weight:800;}
.sc-tr.tt .m{color:var(--g1);}
.sc-tr .ng{color:#ff9d96 !important;}

/* selects do master (painel escuro) */
.st-key-sim_master [data-testid="stWidgetLabel"] p{color:var(--mut) !important;font-size:.8rem !important;font-weight:700 !important;}
.st-key-sim_master div[data-baseweb="select"] > div{background:rgba(255,255,255,.08) !important;border:1.5px solid var(--line) !important;color:#fff !important;}
.st-key-sim_master div[data-baseweb="select"] *{color:#fff !important;}
.st-key-sim_master div[data-baseweb="select"] svg{fill:#fff !important;}
.st-key-sim_master .react-aria-ComboBox > div[role="group"]{background:rgba(255,255,255,.08) !important;border:1.5px solid var(--line) !important;
  border-radius:12px !important;box-shadow:none !important;}
.st-key-sim_master .react-aria-ComboBox input{color:#fff !important;-webkit-text-fill-color:#fff !important;background:transparent !important;}
.st-key-sim_master .react-aria-ComboBox button, .st-key-sim_master .react-aria-ComboBox svg{color:#fff !important;fill:#fff !important;}

/* tipo de simulação (radio em pílulas) */
.st-key-sim_master [data-testid="stRadioGroup"]{gap:8px !important;flex-wrap:wrap;}
.st-key-sim_master [data-testid="stRadioOption"]{margin:0 !important;padding:10px 16px !important;border-radius:14px;cursor:pointer;
  border:1.5px solid var(--line);background:rgba(255,255,255,.06);transition:background .18s,border-color .18s,transform .18s;}
.st-key-sim_master [data-testid="stRadioOption"]:hover{border-color:rgba(246,210,122,.6);transform:translateY(-1px);}
.st-key-sim_master [data-testid="stRadioOption"] > div > div > div:first-child{display:none !important;}
.st-key-sim_master [data-testid="stRadioOption"] p{color:var(--ink) !important;font-weight:700 !important;font-size:.92rem !important;line-height:1.25;}
.st-key-sim_master [data-testid="stRadioOption"][data-selected="true"]{background:linear-gradient(135deg,rgba(246,210,122,.30),rgba(246,210,122,.10));
  border-color:var(--g1);box-shadow:0 0 0 3px rgba(246,210,122,.16);}
.st-key-sim_master [data-testid="stRadioOption"][data-selected="true"] p{color:var(--g1) !important;}
.st-key-sim_master [data-testid="stRadioOption"]:has(input:focus-visible){outline:2px solid var(--g1);outline-offset:2px;}

/* expander avançado = gaveta clara */
.st-key-sim_comissao [data-testid="stExpander"]{background:#f6faf9 !important;border:1px solid rgba(246,210,122,.4) !important;border-radius:16px !important;}
.st-key-sim_comissao [data-testid="stExpander"] summary, .st-key-sim_comissao [data-testid="stExpander"] summary *{color:#0f2f2c !important;}
.st-key-sim_comissao [data-testid="stExpander"] input{color:#0f2f2c !important;-webkit-text-fill-color:#0f2f2c !important;}
.st-key-sim_comissao [data-testid="stExpander"] label p,.st-key-sim_comissao [data-testid="stExpander"] p,
.st-key-sim_comissao [data-testid="stExpander"] [data-testid="stCaptionContainer"] *{color:#0f2f2c !important;}

.sc-foot{font-size:.78rem;line-height:1.5;color:rgba(238,247,245,.58);margin-top:4px;}

/* ---------- celular ---------- */
@media (max-width:760px){
  .st-key-sim_comissao{padding:20px 16px 18px;border-radius:20px;margin-left:-19px;margin-right:-19px;width:calc(100% + 38px) !important;max-width:none !important;}
  .sc-chip{font-size:.76rem;padding:5px 10px;}
  .sc-soma{flex-direction:column;align-items:flex-start;}
  .sc-head h3{font-size:1.38rem !important;}
  .sc-hero{padding:18px 16px 16px;}
  .sc-meses{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}
  .sc-m{padding:12px 12px;}
  .sc-m .val{font-size:1.3rem;}
  .sc-mk.edge.l{display:none;}
  .st-key-sim_master [data-testid="stRadioOption"]{width:100%;}
  .sc-wf{padding:14px 14px;}
  .sc-wr{grid-template-columns:minmax(0,1fr) auto;}
  .sc-wr .tk{grid-column:1 / -1;grid-row:2;}
  .sc-wr .vl{grid-column:2;grid-row:1;font-size:1rem;}
  .sc-wr.res .vl{font-size:1.3rem;}
  .sc-tr.hd{display:none;}
  .sc-tb.n8 .sc-tr{grid-template-columns:1fr 1fr;padding:11px 14px;gap:6px 12px;font-size:.86rem;}
  .sc-tr{grid-template-columns:1fr 1fr;padding:11px 14px;gap:6px 12px;}
  .sc-tr > div:first-child{grid-column:1 / -1;font-size:.95rem;}
  .sc-tr > div[data-l]::before{content:attr(data-l);display:block;font-size:.66rem;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);font-weight:700;margin-bottom:1px;}
  .sc-split .sc-t b{font-size:1.05rem;}
  .sc-prizes{grid-template-columns:1fr;}
  .st-key-sim_ctrl .stTextInput input{font-size:1.6rem !important;}
}
@media (prefers-reduced-motion:no-preference){
  .sc-m,.sc-pz,.sc-goal{animation:scUp .5s cubic-bezier(.22,1,.36,1) both;}
  .sc-m:nth-child(2){animation-delay:.05s}.sc-m:nth-child(3){animation-delay:.1s}.sc-m:nth-child(4){animation-delay:.15s}
  @keyframes scUp{from{opacity:.0;transform:translateY(8px)}to{opacity:1;transform:none}}
}
</style>
"""


# ==========================================================================
# blocos de HTML (uma linha só: linhas em branco/indentadas quebrariam o markdown)
# ==========================================================================
def _html(s):
    st.markdown(re.sub(r"\n\s*", "", s), unsafe_allow_html=True)


def _bloco_hero(valor, total, n_meses, nivel, pct_total, base, premio, diferente, master=False):
    quem = "o vendedor leva" if master else "você leva"
    if total <= 0:
        return ('<div class="sc-hero"><div class="sc-lbl">Sua comissão estimada</div>'
                '<div class="sc-big"><span class="cur">R&#36;</span>0</div>'
                '<div class="sc-sub">Digite um valor ou arraste a barra: a comissão estimada aparece aqui na hora. '
                'Quanto mais você vende no mês, maiores ficam os prêmios.</div></div>')
    inteiro, _, cts = _num(total, True).partition(",")
    cts_html = "" if cts == "00" else f'<span class="cts">,{cts}</span>'
    if n_meses > 1:
        if diferente:
            sub = f"Vendendo nos <b>{n_meses} meses</b> do período {quem} para casa, ao todo, <b>{_h(total)}</b>."
        else:
            sub = (f"Com <b>{_h(valor)}</b> vendidos por mês, durante <b>{n_meses} meses</b>, {quem} para casa, "
                   f"ao todo, <b>{_h(total)}</b>.")
    else:
        sub = f"Com <b>{_h(valor)}</b> vendidos no mês {quem} para casa <b>{_h(total)}</b>."
    nome_n = ["Base", "Bônus 1 liberado", "Bônus 2 liberado"][nivel]
    chips = [f'<span class="sc-chip{" gold" if nivel else ""}">{"🏆" if nivel else "🎯"} Nível: {nome_n}</span>'] if n_meses == 1 or not diferente else []
    if n_meses == 1 or not diferente:
        chips.append(f'<span class="sc-chip">📈 {_pct(pct_total)} do valor vendido</span>')
    chips.append(f'<span class="sc-chip">💵 Base {_h(base)}</span>')
    chips.append(f'<span class="sc-chip{" gold" if premio > 0 else ""}">⭐ Prêmios {_h(premio)}</span>')
    return (f'<div class="sc-hero"><div class="sc-lbl">{"Estimativa: comissão do vendedor" if master else "Estimativa: você leva para casa"}</div>'
            f'<div class="sc-big"><span class="cur">R&#36;</span>{inteiro}{cts_html}</div>'
            f'<div class="sc-sub">{sub}</div><div class="sc-chips">{"".join(chips)}</div></div>')


def _bloco_marcos(nivel, r, smax):
    def pos(v):
        return max(0.0, min(100.0, v / smax * 100.0))
    on1, on2 = nivel >= 1, nivel >= 2
    m = [
        f'<div class="sc-mk edge l"><i></i><span class="ic">🚀</span><span class="tx">R&#36; 0</span></div>',
        f'<div class="sc-mk{" on" if on1 else ""}" style="left:{pos(r["VD_M1"]):.2f}%"><i></i><span class="ic">{"✅" if on1 else "🔒"}</span>'
        f'<span class="tx">{_curto_mi(r["VD_M1"]).replace(" ", "&nbsp;")}</span></div>',
        f'<div class="sc-mk{" on" if on2 else ""}" style="left:{pos(r["VD_M2"]):.2f}%"><i></i><span class="ic">{"✅" if on2 else "🔒"}</span>'
        f'<span class="tx">{_curto_mi(r["VD_M2"]).replace(" ", "&nbsp;")}</span></div>',
        f'<div class="sc-mk edge r"><i></i><span class="ic">🏁</span><span class="tx">{_curto_mi(smax)}</span></div>',
    ]
    return f'<div class="sc-marks">{"".join(m)}</div>'


def _bloco_premios(nivel, r):
    def card(on, ic, nome, regra_txt, pct_txt):
        return (f'<div class="sc-pz{" on" if on else ""}"><span class="ic">{ic}</span><div><b>{nome} · {"liberado" if on else "travado"}</b>'
                f'<span>{regra_txt}</span><span>{pct_txt}</span></div></div>')
    return ('<div class="sc-prizes">'
            + card(nivel >= 1, "✅" if nivel >= 1 else "🔒", "Bônus 1", f'Mês acima de {_h(r["VD_M1"])} vendidos',
                   f'+{_pct(r["VD_M1_P3"])} do crédito no 3º recebimento')
            + card(nivel >= 2, "✅" if nivel >= 2 else "🔒", "Bônus 2", f'Mês acima de {_h(r["VD_M2"])} vendidos',
                   f'+{_pct(r["VD_M2_P4"])} do crédito no 4º recebimento')
            + '</div>')


# ==========================================================================
# cálculo dos 4 cartões
# ==========================================================================
def _linha(por_mes, ym):
    if por_mes is None or por_mes.empty:
        return 0.0, 0.0
    x = por_mes[por_mes["ym"] == ym]
    if x.empty:
        return 0.0, 0.0
    return float(x["Comissão base"].iloc[0]), float(x["Bônus"].iloc[0])


def _posicao_do_mes(j, pagantes):
    """Posição (0=1º pagamento do vendedor ... 3=4º) paga no mês j (0-based), ou None se não há pagamento."""
    if pagantes:
        return pagantes.index(j + 1) if (j + 1) in pagantes else None
    return j


def _cartoes(vendas_mes_unico, por_mes, ym0, nivel, r, cfg, regra_adm, imposto, valor, travas):
    """Lista de 4 dicts {n, nome, total, classe, tag, detalhe}. `travas` = mostrar estado de bônus travado
    (só quando a simulação é de um único valor mensal)."""
    pagantes = sorted(i for i, p in (regra_adm or {}).items() if p and p > 0)
    cache = {}

    def destravado(alvo):
        if alvo not in cache:
            cache[alvo] = cv.simular([(ym0, alvo)], cfg, regra_adm, imposto)[0]
        return cache[alvo]

    out = []
    for j in range(4):
        ym = cv._soma_meses(ym0, j)
        base, prem = _linha(por_mes, ym)
        tot = base + prem
        k = _posicao_do_mes(j, pagantes)
        c = {"n": j + 1, "nome": _rot_mes(ym), "total": tot}
        if tot > 0:
            c["classe"] = "ok"
            partes = []
            if base > 0:
                partes.append(f"Base <b>{_h(base)}</b>")
            if prem > 0:
                partes.append(f"Prêmio <b>{_h(prem)}</b>")
            if k is not None and k >= 2 and valor > 0 and travas:
                pc = r["VD_M1_P3"] if k == 2 else r["VD_M2_P4"]
                partes.append(f"{_pct(pc)} do vendido")
            elif k is not None and k < 2 and valor > 0 and travas:
                pc = r["VD_P1"] if k == 0 else r["VD_P2"]
                partes.append(f"{_pct(pc)} do vendido")
            c["tag"] = "Prêmio" if (prem > 0 and base == 0) else "Base"
            c["detalhe"] = "<br>".join(partes)
        elif travas and k in (2, 3) and nivel < (1 if k == 2 else 2):
            alvo_lim = r["VD_M1"] if k == 2 else r["VD_M2"]
            ganho = _linha(destravado(alvo_lim + 0.01), ym)
            c["classe"] = "lock"
            c["tag"] = "🔒 Bônus 1" if k == 2 else "🔒 Bônus 2"
            c["detalhe"] = (f"Destrava com mês acima de <b>{_h(alvo_lim)}</b> ({_falta_txt(alvo_lim, valor)}): "
                            f"este mês passaria a render <b>{_h(sum(ganho))}</b>.")
        elif travas and valor > 0 and k in (2, 3):
            c["classe"] = "zero"
            c["tag"] = "Bônus"
            c["detalhe"] = "Sem prêmio neste mês."
        elif k is None and valor > 0:
            c["classe"] = "zero"
            c["tag"] = "—"
            c["detalhe"] = "A administradora não paga comissão neste mês."
        elif valor <= 0 or not travas:
            c["classe"] = "zero"
            c["tag"] = "Aguardando"
            c["detalhe"] = ("Ainda sem venda: informe um valor acima." if valor <= 0 else "Sem recebimento neste mês.")
        else:
            c["classe"] = "zero"
            c["tag"] = "—"
            c["detalhe"] = "Sem recebimento neste mês."
        out.append(c)
    return out


def _cartoes_html(cards):
    h = []
    for c in cards:
        val = _h(c["total"]) if c["total"] > 0 else "R&#36;&nbsp;0"
        h.append(f'<div class="sc-m {c["classe"]}"><div class="top"><span class="n">MÊS {c["n"]}</span><span class="tag">{c["tag"]}</span></div>'
                 f'<div class="nome">{c["nome"]}</div><div class="val">{val}</div><div class="det">{c["detalhe"]}</div></div>')
    return f'<div class="sc-meses">{"".join(h)}</div>'


def _hs(v, centavos=False):
    """Valor com sinal para HTML: negativo vira '-R$ 1.000'."""
    return ("&minus;" + _h(-v, centavos)) if v < -0.004 else _h(v, centavos)


def _bloco_corretora(por_mes, regra_adm, imposto, desc=False):
    """Modo vendedor (master): entrada real da administradora -> imposto -> líquido -> vendedor -> Consorbens -> Breno/Uriel."""
    bruta = float(por_mes["Comissão bruta (adm.)"].sum())
    imp = float(por_mes["Imposto"].sum())
    liq = float(por_mes["Líquido corretora"].sum())
    vend = float(por_mes["Total vendedor"].sum())
    base = float(por_mes["Comissão base"].sum())
    prem = float(por_mes["Bônus"].sum())
    sobra = float(por_mes["Consorbens (após vendedor)"].sum())
    esc = max(bruta, liq, vend, abs(sobra), 0.01)
    neg = sobra < -0.004

    def pc(x):
        return max(0.0, min(100.0, x / esc * 100.0))

    def linha(op, rot, sub, valor_txt, ini, fim, cls="", barcls=""):
        return (f'<div class="sc-wr {cls}"><div class="lb"><span class="op">{op}</span>{rot}'
                + (f'<small>{sub}</small>' if sub else '') + '</div>'
                f'<div class="vl">{valor_txt}</div>'
                f'<div class="tk"><div class="bar {barcls}" style="left:{pc(ini):.2f}%;width:{max(pc(fim) - pc(ini), 0.6):.2f}%"></div></div></div>')

    if desc:
        linha_vend = linha("&minus;", "Vendedor recebe", f"base {_h(base)} + prêmios {_h(prem)} · descontado da Consorbens", _hs(-vend),
                           0 if neg else liq - vend, liq, barcls="gold")
        sub_fica = "depois de pagar o vendedor"
        rot_v, op_v = "&minus; Vendedor recebe", "&minus; "
    else:   # custo do vendedor fica com a Ecoclim: aparece só como informação, não desconta da Consorbens
        linha_vend = linha("&nbsp;", "Vendedor recebe (custo da Ecoclim)",
                           f"base {_h(base)} + prêmios {_h(prem)} · não é descontado da Consorbens", _h(vend), 0, vend, barcls="gold")
        sub_fica = "o líquido inteiro; o custo do vendedor é da Ecoclim"
        rot_v, op_v = "Vendedor recebe (Ecoclim)", ""
    rows = (linha("&nbsp;", "Entrada bruta da administradora", "comissão que a administradora nos paga, pela regra cadastrada", _h(bruta), 0, bruta)
            + linha("&minus;", "Imposto", f"{_pct(imposto)} sobre a bruta", _hs(-imp), liq, bruta, barcls="neg")
            + linha("=", "Líquido que entra na corretora", "", _h(liq), 0, liq)
            + linha_vend
            + linha("=", "Consorbens recebe", sub_fica, _hs(sobra), 0, abs(sobra),
                    cls="res" + (" bad" if neg else ""), barcls="neg" if neg else ""))
    split = (f'<div class="sc-split"><div class="sc-t"><span>Breno · 50% da Consorbens</span><b>{_hs(sobra / 2)}</b></div>'
             f'<div class="sc-t"><span>Uriel · 50% da Consorbens</span><b>{_hs(sobra / 2)}</b></div></div>')

    cab = ('<div class="sc-tr hd"><div>Mês</div><div>Entrada bruta (adm.)</div><div>&minus; Imposto</div><div>= Líquido que entra</div>'
           f'<div>{rot_v}</div><div>Consorbens recebe</div><div>Breno 50%</div><div>Uriel 50%</div></div>')
    lin = []
    for _, x in por_mes.iterrows():
        sb = float(x["Consorbens (após vendedor)"])
        lin.append(f'<div class="sc-tr"><div class="m">{_rot_mes(x["ym"])}</div>'
                   f'<div data-l="Entrada bruta (adm.)">{_h(x["Comissão bruta (adm.)"])}</div>'
                   f'<div data-l="&minus; Imposto">{_h(x["Imposto"])}</div>'
                   f'<div data-l="= Líquido que entra">{_h(x["Líquido corretora"])}</div>'
                   f'<div data-l="{op_v}Vendedor recebe">{_h(x["Total vendedor"])}{("<small>base " + _h(x["Comissão base"]) + " · prêmio " + _h(x["Bônus"]) + "</small>") if x["Total vendedor"] > 0 else ""}</div>'
                   f'<div data-l="Consorbens recebe" class="fi{" ng" if sb < -0.004 else ""}">{_hs(sb)}</div>'
                   f'<div data-l="Breno 50%">{_hs(sb / 2)}</div><div data-l="Uriel 50%">{_hs(sb / 2)}</div></div>')
    tot = (f'<div class="sc-tr tt"><div class="m">TOTAL</div><div data-l="Entrada bruta (adm.)">{_h(bruta)}</div>'
           f'<div data-l="&minus; Imposto">{_h(imp)}</div><div data-l="= Líquido que entra">{_h(liq)}</div>'
           f'<div data-l="{op_v}Vendedor recebe">{_h(vend)}</div>'
           f'<div data-l="Consorbens recebe" class="fi{" ng" if neg else ""}">{_hs(sobra)}</div>'
           f'<div data-l="Breno 50%">{_hs(sobra / 2)}</div><div data-l="Uriel 50%">{_hs(sobra / 2)}</div></div>')
    tabela = f'<div class="sc-tb n8">{cab}<div class="sc-sc">{"".join(lin)}</div>{tot}</div>'
    return ('<div class="sc-sec"><h4>🏢 Entrada real da administradora e divisão</h4>'
            '<small>Seguindo a regra de comissão da administradora escolhida</small></div>'
            + _chips_regra(regra_adm) + f'<div class="sc-wf">{rows}</div>' + split
            + '<div class="sc-sec"><h4>📆 Mês a mês: entrada, vendedor, Consorbens e sócios</h4></div>' + tabela)


def _chips_regra(regra_adm):
    pg = sorted((i, p) for i, p in regra_adm.items() if p and p > 0)
    return ('<div class="sc-regra">Regra da administradora: '
            + "".join(f'<span class="p">{i}ª parcela {_pct(p)}</span>' for i, p in pg) + '</div>')


def _rot_div(modo):
    """Rótulos dos dois sócios: Consorbens = Breno/Uriel; Sócios = quem vendeu / outro sócio (colunas Breno/Uriel de
    simular_corretora com quem='BRENO': Breno_Breno e Breno_Uriel do cfg, simétrico ao par do Uriel)."""
    return ("Breno", "Uriel") if modo == "consorbens" else ("Sócio que vendeu", "Outro sócio")


def _bloco_socios(df, regra_adm, imposto, modo, quem, pb, pu):
    """Modos Consorbens (50/50) e Sócios (70/30): bruta -> imposto -> líquido -> Breno / Uriel, mês a mês e total."""
    bruta = float(df["Comissão bruta (adm.)"].sum())
    imp = float(df["Imposto"].sum())
    liq = float(df["Líquido corretora"].sum())
    br = float(df["Breno"].sum())
    ur = float(df["Uriel"].sum())
    esc = max(bruta, 0.01)

    def pc(x):
        return max(0.0, min(100.0, x / esc * 100.0))

    def linha(op, rot, sub, valor_txt, ini, fim, cls="", barcls=""):
        return (f'<div class="sc-wr {cls}"><div class="lb"><span class="op">{op}</span>{rot}'
                + (f'<small>{sub}</small>' if sub else '') + '</div>'
                f'<div class="vl">{valor_txt}</div>'
                f'<div class="tk"><div class="bar {barcls}" style="left:{pc(ini):.2f}%;width:{max(pc(fim) - pc(ini), 0.6):.2f}%"></div></div></div>')
    l1, l2 = _rot_div(modo)
    rows = (linha("&nbsp;", "Entrada bruta da administradora", "comissão que a administradora nos paga, pela regra cadastrada", _h(bruta), 0, bruta)
            + linha("&minus;", "Imposto", f"{_pct(imposto)} sobre a bruta", _hs(-imp), liq, bruta, barcls="neg")
            + linha("=", "Líquido que entra na corretora", "", _h(liq), 0, liq)
            + linha("&rarr;", l1, f"{_pct(pb)} do líquido", _h(br), 0, br, barcls="gold")
            + linha("&rarr;", l2, f"{_pct(pu)} do líquido", _h(ur), 0, ur, barcls="gold"))
    cab = ('<div class="sc-tr hd"><div>Mês</div><div>Entrada bruta (adm.)</div><div>&minus; Imposto</div><div>= Líquido que entra</div>'
           f'<div>{l1} {_pct(pb)}</div><div>{l2} {_pct(pu)}</div></div>')
    lin = []
    for _, x in df.iterrows():
        lin.append(f'<div class="sc-tr"><div class="m">{_rot_mes(x["ym"])}</div>'
                   f'<div data-l="Entrada bruta (adm.)">{_h(x["Comissão bruta (adm.)"])}</div>'
                   f'<div data-l="&minus; Imposto">{_h(x["Imposto"])}</div>'
                   f'<div data-l="= Líquido que entra" class="fi">{_h(x["Líquido corretora"])}</div>'
                   f'<div data-l="{l1} {_pct(pb)}">{_h(x["Breno"])}</div><div data-l="{l2} {_pct(pu)}">{_h(x["Uriel"])}</div></div>')
    tot = (f'<div class="sc-tr tt"><div class="m">TOTAL</div><div data-l="Entrada bruta (adm.)">{_h(bruta)}</div>'
           f'<div data-l="&minus; Imposto">{_h(imp)}</div><div data-l="= Líquido que entra" class="fi">{_h(liq)}</div>'
           f'<div data-l="{l1} {_pct(pb)}">{_h(br)}</div><div data-l="{l2} {_pct(pu)}">{_h(ur)}</div></div>')
    tabela = f'<div class="sc-tb">{cab}<div class="sc-sc">{"".join(lin)}</div>{tot}</div>'
    titulo = "Venda da própria Consorbens" if modo == "consorbens" else "Venda de um sócio"
    return (f'<div class="sc-sec"><h4>🏢 {titulo}: da administradora até cada sócio</h4>'
            '<small>Sem vendedor e sem bônus. Divisão conforme as Configurações</small></div>'
            + _chips_regra(regra_adm) + f'<div class="sc-wf">{rows}</div>'
            + '<div class="sc-sec"><h4>📆 Mês a mês</h4></div>' + tabela)


def _bloco_hero_corr(valor, df, n_meses, modo, quem, pb, pu, imposto):
    liq = float(df["Líquido corretora"].sum()) if not df.empty else 0.0
    if liq <= 0:
        return ('<div class="sc-hero"><div class="sc-lbl">Estimativa: entrada líquida da corretora</div>'
                '<div class="sc-big"><span class="cur">R&#36;</span>0</div>'
                '<div class="sc-sub">Digite um valor ou arraste a barra: a entrada estimada da administradora aparece aqui na hora. '
                'Se nada aparecer, confira se a administradora escolhida tem comissão cadastrada.</div></div>')
    bruta = float(df["Comissão bruta (adm.)"].sum())
    br, ur = float(df["Breno"].sum()), float(df["Uriel"].sum())
    inteiro, _, cts = _num(liq, True).partition(",")
    cts_html = "" if cts == "00" else f'<span class="cts">,{cts}</span>'
    quem_txt = "a Consorbens" if modo == "consorbens" else "um sócio"
    l1, l2 = _rot_div(modo)
    if n_meses > 1:
        sub = (f"Em <b>{n_meses} meses</b> de vendas de {quem_txt}, a administradora paga <b>{_h(bruta)}</b>; "
               f"descontado o imposto ({_pct(imposto)}), entram <b>{_h(liq)}</b> na corretora.")
    else:
        sub = (f"Com <b>{_h(valor)}</b> vendidos no mês por {quem_txt}, a administradora paga <b>{_h(bruta)}</b> ao todo; "
               f"descontado o imposto ({_pct(imposto)}), entram <b>{_h(liq)}</b> na corretora.")
    chips = (f'<span class="sc-chip gold">👤 {l1} {_pct(pb)}: {_h(br)}</span>'
             f'<span class="sc-chip gold">👤 {l2} {_pct(pu)}: {_h(ur)}</span>'
             f'<span class="sc-chip">🏦 Bruta {_h(bruta)}</span>'
             f'<span class="sc-chip">🧾 Imposto {_h(float(df["Imposto"].sum()))}</span>')
    return (f'<div class="sc-hero"><div class="sc-lbl">Estimativa: entrada líquida da corretora</div>'
            f'<div class="sc-big"><span class="cur">R&#36;</span>{inteiro}{cts_html}</div>'
            f'<div class="sc-sub">{sub}</div><div class="sc-chips">{chips}</div></div>')


def _cartoes_corr(df, ym0, valor, modo="consorbens"):
    l1, l2 = _rot_div(modo)
    out = []
    for j in range(4):
        ym = cv._soma_meses(ym0, j)
        x = df[df["ym"] == ym] if not df.empty else df
        c = {"n": j + 1, "nome": _rot_mes(ym)}
        if not x.empty and float(x["Líquido corretora"].iloc[0]) > 0:
            liq = float(x["Líquido corretora"].iloc[0])
            c.update(total=liq, classe="ok", tag="Entrada",
                     detalhe=f'{l1} <b>{_h(float(x["Breno"].iloc[0]))}</b><br>{l2} <b>{_h(float(x["Uriel"].iloc[0]))}</b>')
        else:
            c.update(total=0.0, classe="zero", tag="Aguardando" if valor <= 0 else "—",
                     detalhe="Ainda sem venda: informe um valor acima." if valor <= 0 else "A administradora não paga comissão neste mês.")
        out.append(c)
    return out


def _falta_txt(lim, valor):
    """'faltam mais de R$ 400.000' (o bônus exige produção ESTRITAMENTE acima do limite)."""
    dist = round(lim - valor, 2)
    return "falta só 1 centavo" if dist <= 0 else f"faltam mais de {_h(dist)}"


def _pagantes(regra_adm):
    return sorted(i for i, p in (regra_adm or {}).items() if p and p > 0)


# ==========================================================================
# tela
# ==========================================================================
MODOS = ["vendedor", "consorbens", "socios"]


def _rotulo_modo(m, cfg):
    cb, cu = cv.divisao_socios(cfg, "consorbens")
    sb, su = cv.divisao_socios(cfg, "socios", "BRENO")
    return {"vendedor": "Comissionamento vendedor",
            "consorbens": f"Comissionamento Consorbens ({_pct(cb)}/{_pct(cu)})",
            "socios": f"Comissionamento Sócios ({_pct(sb)}/{_pct(su)})"}[m]


def render_simulador(df_admin, cfg, master=False):
    from modulos.relatorio_vendedor import _regra_admin      # import tardio: evita ciclo (relatorio_vendedor delega para cá)

    r = cv.regra(cfg)
    imposto = parse_float_safe((cfg or {}).get("Imposto", 7.16))
    hoje = datetime.today()
    ym0 = f"{hoje.year:04d}-{hoje.month:02d}"
    px = "sim_m_" if master else "sim_v_"
    k_val, k_txt, k_sl = px + "valor", px + "txt", px + "barra"
    ss = st.session_state
    smax = max(BARRA_MIN_MAX, int(math.ceil(r["VD_M2"] * 3 / 500_000.0) * 500_000))

    # --- sincronia campo <-> barra ---------------------------------------------------------------------
    # k_val = valor "oficial". Arrastar a barra: o callback atualiza k_val e o texto do campo (antes do script).
    # Digitar: input_valor (máscara de milhar) devolve o número; se mudou, k_val e a barra são atualizados
    # logo abaixo, antes de a barra ser criada.
    if k_val not in ss:
        ss[k_val] = PADRAO_INICIAL

    def _ao_arrastar():
        v = float(ss[k_sl])
        ss[k_val] = v
        ss[k_txt] = _fmt_campo(v)                         # arrastar atualiza o campo

    valor = float(ss[k_val])
    nivel = cv.nivel(valor, r)
    modo, quem, corr = "vendedor", None, False

    with st.container(key="sim_comissao"):
        st.markdown(_CSS, unsafe_allow_html=True)
        s_head = st.container()

        # ---- master: 1º tipo de simulação, 2º administradora/produto/tipo de parcela
        regra_adm = None
        if master:
            with st.container(key="sim_master"):
                modo = st.radio("Tipo de simulação", MODOS, format_func=lambda m: _rotulo_modo(m, cfg), key="sim_modo", horizontal=True)
                if modo == "socios":
                    quem = "BRENO"          # só rotula: o par Breno_* do cfg vale para "sócio que vendeu" / "outro sócio"
                if df_admin is not None and not df_admin.empty:
                    a1, a2, a3 = st.columns(3)
                    adm = a1.selectbox("Administradora", sorted(df_admin["Administradora"].dropna().unique()), key="sim_adm")
                    prods = sorted(df_admin[df_admin["Administradora"] == adm]["Produto"].dropna().unique())
                    prod = a2.selectbox("Produto", prods, key="sim_prod")
                    sub = df_admin[(df_admin["Administradora"] == adm) & (df_admin["Produto"] == prod)]
                    tipos = sorted(sub["Tipo_Parcela"].fillna("").astype(str).unique()) if "Tipo_Parcela" in sub.columns else [""]
                    tipo = (a3.selectbox("Tipo de parcela", tipos, format_func=lambda x: x or "(padrão)", key="sim_tipo")
                            if len(tipos) > 1 else tipos[0])
                    regra_adm = _regra_admin(df_admin, adm, prod, tipo)
                    if not regra_adm:
                        st.warning("Esta combinação não tem comissão cadastrada na administradora; "
                                   + ("não há o que simular." if modo != "vendedor" else "só o lado do vendedor será simulado."))
                else:
                    st.info("Sem regras de administradora cadastradas: "
                            + ("não há o que simular." if modo != "vendedor" else "só o lado do vendedor será simulado."))
            corr = modo != "vendedor"
        s_hero = st.container()

        # ---- controles: campo + barra (+ marcos e prêmios do vendedor)
        with st.container(key="sim_ctrl"):
            v_campo = input_valor("Valor vendido no mês (R\\$)", value=valor, key=k_txt, casas=0, placeholder="Ex.: 600.000")
            v_campo = min(max(v_campo, 0.0), TETO_VALOR)
            if abs(v_campo - ss[k_val]) > 0.004:          # o campo mudou (digitado): vale o que está no campo
                ss[k_val] = v_campo
            valor = float(ss[k_val])
            nivel = cv.nivel(valor, r)
            ss[k_sl] = _snap(valor, smax)                 # digitar move a barra (valor grande só encosta no fim)
            st.slider("Arraste para simular", min_value=0, max_value=smax, step=PASSO_BARRA, key=k_sl,
                      on_change=_ao_arrastar, label_visibility="collapsed")
            if not corr:
                _html(_bloco_marcos(nivel, r, smax))
                _html(_bloco_premios(nivel, r))
        s_meta = st.container()

        if corr:
            _html('<div class="sc-sec"><h4>📅 Próximos 4 meses de entrada</h4>'
                  '<small>A parcela i da administradora cai no mês da venda + (i &minus; 1).</small></div>')
        else:
            _html(f'<div class="sc-sec"><h4>📅 {"Próximos 4 meses de recebimento do vendedor" if master else "Seus próximos 4 meses de recebimento"}</h4>'
                  '<small>Acima de ' + _h(r["VD_M2"]) + ' no mês, o pagamento se estende por 4 meses.</small></div>')
        s_cards = st.container()
        if master:
            s_master = st.container()

        # ---- avançado: vários meses de venda
        n_meses, diferente, vendas = 1, False, [(ym0, valor)]
        with st.expander("Simulação avançada (vários meses)", expanded=False):
            st.caption("Quer projetar um período maior? Escolha quantos meses vai vender o valor acima, ou informe um valor diferente em cada mês.")
            n_meses = int(st.number_input("Meses de venda", min_value=1, max_value=12, value=1, step=1, key=px + "meses"))
            meses_venda = [cv._soma_meses(ym0, i) for i in range(n_meses)]
            vendas = [(m, valor) for m in meses_venda]
            if n_meses > 1:
                diferente = st.checkbox("Informar um valor diferente em cada mês", key=px + "difere")
                if diferente:
                    ed = st.data_editor(
                        pd.DataFrame({"Mês": [_rot_mes(m) for m in meses_venda], "Vendido (R$)": [float(valor)] * n_meses}),
                        hide_index=True, disabled=["Mês"], use_container_width=True,
                        column_config={"Vendido (R$)": st.column_config.NumberColumn("Vendido (R$)", min_value=0, format="localized")},
                        key=f"{px}editor_{n_meses}_{int(valor)}")
                    vendas = [(m, (0.0 if v is None or pd.isna(v) else max(float(v), 0.0)))
                              for m, v in zip(meses_venda, ed["Vendido (R$)"])]       # célula em branco = 0

        unico = (n_meses == 1)                                  # estados de bônus travado só fazem sentido com 1 valor mensal
        with s_head:
            if master:
                titulo = {"vendedor": "Quanto será vendido neste mês?", "consorbens": "Quanto a Consorbens vai vender neste mês?",
                          "socios": "Quanto o sócio vai vender neste mês?"}[modo]
                sub_t = ("Digite o valor ou arraste a barra: tudo muda na hora, seguindo a regra da administradora escolhida.")
            else:
                titulo, sub_t = ("Quanto você quer vender neste mês?",
                                 "Digite o valor ou arraste a barra: a sua comissão estimada muda na hora.")
            _html('<div class="sc-head"><div class="sc-eye">✨ Simulador de comissionamento'
                  + ('<span class="sc-tagm">VISÃO DA GESTÃO</span>' if master else '') + f'</div><h3>{titulo}</h3><p>{sub_t}</p></div>')

        # ================= modos Consorbens / Sócios =================
        if corr:
            pb, pu = cv.divisao_socios(cfg, modo, quem)
            df_c = cv.simular_corretora(vendas, cfg, regra_adm, imposto, modo, quem)
            tem = not df_c.empty
            with s_hero:
                _html(_bloco_hero_corr(valor, df_c, n_meses, modo, quem, pb, pu, imposto))
            with s_cards:
                cards = _cartoes_corr(df_c, ym0, valor, modo)
                _html(_cartoes_html(cards))
                liq_t = float(df_c["Líquido corretora"].sum()) if tem else 0.0
                resto = liq_t - sum(c["total"] for c in cards)
                extra = f' · mais <b>{_h(resto)}</b> depois do Mês 4' if resto > 0.005 else ""
                _html(f'<div class="sc-soma"><span>Entrada líquida total estimada{extra}</span><b>{_h(liq_t)}</b></div>')
            with s_master:
                if tem:
                    _html(_bloco_socios(df_c, regra_adm, imposto, modo, quem, pb, pu))
                elif regra_adm:
                    _html('<div class="sc-goal">Informe um valor de venda acima de zero para ver a entrada da administradora, mês a mês.</div>')
            st.markdown(
                '<div class="sc-foot">Estimativa para planejamento, não garantia de ganho. A parcela i da administradora cai no mês da venda + (i &minus; 1) '
                'e depende de a administradora receber a parcela do cliente. Sem vendedor e sem bônus; a divisão entre os sócios segue '
                'as Configurações.</div>', unsafe_allow_html=True)
            return

        # ================= modo vendedor =================
        por_mes, _niveis = cv.simular(vendas, cfg, regra_adm, imposto)
        tem = not por_mes.empty
        total = float(por_mes["Total vendedor"].sum()) if tem else 0.0
        base = float(por_mes["Comissão base"].sum()) if tem else 0.0
        premio = float(por_mes["Bônus"].sum()) if tem else 0.0
        pct_total = sum(cv.percentuais_por_posicao(valor, cfg))

        with s_hero:
            _html(_bloco_hero(valor, total, n_meses, nivel, pct_total, base, premio, diferente, master))

        # ---- meta / próximo prêmio
        com_de = "na comissão do vendedor" if master else "na sua comissão"
        with s_meta:
            if valor > 0 and not diferente:
                if nivel < 2:
                    lim, pc, nome, k_novo = ((r["VD_M1"], r["VD_M1_P3"], "Bônus 1", 2) if nivel == 0
                                             else (r["VD_M2"], r["VD_M2_P4"], "Bônus 2", 3))
                    alvo = cv.simular([(ym0, lim + 0.01)], cfg, regra_adm, imposto)[0]
                    pg_ = _pagantes(regra_adm)
                    off = (pg_[k_novo] - 1) if (pg_ and k_novo < len(pg_)) else (None if pg_ else k_novo)
                    ganho = sum(_linha(alvo, cv._soma_meses(ym0, off))) if off is not None else 0.0
                    dist = round(lim - valor, 2)
                    quanto = "Falta só <b>1 centavo</b>" if dist <= 0 else f"Venda mais de <b>{_h(dist)}</b>"
                    mais = f': <span class="gd">+{_h(ganho)}</span> {com_de}' if ganho > 0 else ""
                    _html(f'<div class="sc-goal">🚀 {quanto} neste mês para destravar o <b>{nome}</b>{mais} '
                          f'(+{_pct(pc)} do crédito, no {k_novo + 1}º recebimento).</div>')
                else:
                    por100 = 100_000 * pct_total / 100.0
                    _html(f'<div class="sc-goal max">🏆 <b>{"Todos os prêmios do mês estão destravados!" if master else "Você destravou todos os prêmios do mês!"}</b> '
                          f'Daqui para frente, cada <b>{_h(100000)}</b> a mais em vendas rende cerca de '
                          f'<span class="gd">{_h(por100)}</span> de comissão ({_pct(pct_total)} do crédito).</div>')
            elif valor <= 0:
                _html(f'<div class="sc-goal">💡 Passando de <b>{_h(r["VD_M1"])}</b> no mês libera o Bônus 1 '
                      f'e, passando de <b>{_h(r["VD_M2"])}</b>, o Bônus 2. Arraste a barra e veja.</div>')

        # ---- 4 cartões
        with s_cards:
            cards = _cartoes(vendas, por_mes, ym0, nivel, r, cfg, regra_adm, imposto, valor, unico)
            _html(_cartoes_html(cards))
            soma4 = sum(c["total"] for c in cards)
            resto = total - soma4
            extra = f' · mais <b>{_h(resto)}</b> depois do Mês 4' if resto > 0.005 else ""
            _html(f'<div class="sc-soma"><span>Comissão total estimada{extra}</span><b>{_h(total)}</b></div>')

        # ---- master: entrada real, vendedor, Consorbens e sócios (cascata + mês a mês)
        if master and regra_adm and tem:
            with s_master:
                _html(_bloco_corretora(por_mes, regra_adm, imposto, cv.desconta_dos_socios(cfg)))
        elif master and regra_adm:
            with s_master:
                _html('<div class="sc-goal">Informe um valor de venda acima de zero para ver a entrada da administradora, mês a mês.</div>')

        # ---- rodapé honesto
        pg = _pagantes(regra_adm)
        premissa = ("Os recebimentos seguem as parcelas pagas pela administradora." if pg else
                    "Considera o 1º recebimento no mês da venda e os demais, um por mês.")
        st.markdown(
            f'<div class="sc-foot">Estimativa para planejamento, não garantia de ganho. {premissa} Cada pagamento depende de a administradora '
            f'receber a parcela do cliente, e cota cancelada em até {r["VD_EST_MESES"]} meses pode gerar estorno de '
            f'{_pct(r["VD_EST_PCT"])} do crédito. Prêmios valem sobre a produção do mês de venda.</div>'.replace("$", "&#36;"),
            unsafe_allow_html=True)
