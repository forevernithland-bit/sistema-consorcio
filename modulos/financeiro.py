import streamlit as st
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro, parse_float_safe, normalizar_string
from regras import gerar_tabela_parcelas
from modulos.importar_comissoes import dividir_socios

# Brecha para imposto sobre o ÁGIO (Consórcio Contemplado).
# Por enquanto 0 (ágio entra líquido). Quando a contabilidade definir, mude aqui.
AGIO_IMPOSTO_PCT = 0.0

# Recebimento da carta contemplada ocorre ~10 dias APÓS a data da venda.
PRAZO_RECEBIMENTO_CONTEMPLADO_DIAS = 10


# ==========================================================
# HELPERS DE DATA
# ==========================================================
def _ym(data_str):
    """Data (dd/mm/aaaa ou texto) -> 'AAAA-MM'. None se inválida."""
    try:
        d = pd.to_datetime(data_str, dayfirst=True, errors="coerce")
        return None if pd.isna(d) else d.strftime("%Y-%m")
    except Exception:
        return None


def _label_mes(ym):
    try:
        return datetime.strptime(ym, "%Y-%m").strftime("%m/%Y")
    except Exception:
        return ym


def _ddmmaaaa(valor):
    """Converte qualquer data (timestamp/str) para 'dd/mm/aaaa' ('' se inválida)."""
    try:
        d = pd.to_datetime(valor, dayfirst=True, errors="coerce")
        return "" if pd.isna(d) else d.strftime("%d/%m/%Y")
    except Exception:
        return ""


def _mais_dias(data_str, dias):
    """Soma 'dias' a uma data dd/mm/aaaa e devolve dd/mm/aaaa ('' se inválida)."""
    try:
        d = pd.to_datetime(data_str, dayfirst=True, errors="coerce")
        if pd.isna(d):
            return ""
        return (d + pd.Timedelta(days=dias)).strftime("%d/%m/%Y")
    except Exception:
        return ""


def _carregar_datas_financeiro(supabase):
    """Datas exclusivas do Financeiro (tabela financeiro_datas). {chave: 'dd/mm/aaaa'}."""
    try:
        rows = supabase.table("financeiro_datas").select("*").execute().data or []
        return {r["chave_unica"]: r.get("data") for r in rows if r.get("data")}
    except Exception:
        return {}


def _salvar_data_financeiro(supabase, chave, data):
    """Grava a data SÓ no Financeiro (não mexe em nenhum outro módulo)."""
    supabase.table("financeiro_datas").upsert(
        {"chave_unica": chave, "data": data}, on_conflict="chave_unica"
    ).execute()


# ==========================================================
# FONTES DE DADOS (sem duplicidade)
# ==========================================================
def _recebidos_tradicional(supabase, df_vendas_global, df_admin, cfg, status_dict, datas_fin):
    """Comissões recebidas do Consórcio Tradicional.
    Fonte 1: comissoes_pagas (NF). Fonte 2: baixas manuais (PAGO fora do NF).
    Data usada = data do Financeiro (financeiro_datas) OU, por padrão, a data em que
    foi LANÇADO no sistema (data_importacao da NF / data de recebimento da baixa)."""
    regs = []
    chaves_nf = set()

    # Fonte 1 — histórico NF
    try:
        cp = supabase.table("comissoes_pagas").select("*").execute().data or []
    except Exception:
        cp = []
    for r in cp:
        ch = r.get("chave_unica")
        if ch:
            chaves_nf.add(ch)
        # padrão = data em que lançamos no sistema (import); reserva = data de pagamento
        padrao = _ddmmaaaa(r.get("data_importacao")) or (r.get("data_pagamento") or "")
        data_fin = datas_fin.get(ch) or padrao
        regs.append({
            "key": ch, "origem": "NF",
            "cliente": r.get("cliente", "") or "—",
            "grupo_cota": f"{r.get('grupo','')}/{r.get('cota','')}",
            "data": data_fin, "ym": _ym(data_fin),
            "bruto": parse_float_safe(r.get("valor_nota", 0)),
            "liquido": parse_float_safe(r.get("valor_liquido", 0)),
            "breno": parse_float_safe(r.get("breno", 0)),
            "uriel": parse_float_safe(r.get("uriel", 0)),
        })

    # Fonte 2 — baixas manuais (PAGO) fora do NF
    if df_vendas_global is not None and not df_vendas_global.empty:
        df_parc, _ = gerar_tabela_parcelas(df_vendas_global, df_vendas_global, df_admin, cfg, status_dict)
        if not df_parc.empty:
            for _, p in df_parc[df_parc["Status"] == "PAGO"].iterrows():
                if p["Chave"] in chaves_nf:
                    continue
                padrao = str(p["Data Recebimento"])
                data_fin = datas_fin.get(p["Chave"]) or padrao
                regs.append({
                    "key": p["Chave"], "origem": "Manual",
                    "cliente": p["Cliente"],
                    "grupo_cota": f"{p['Grupo']}/{p['Cota']}",
                    "data": data_fin, "ym": _ym(data_fin),
                    "bruto": parse_float_safe(p["Comissão (Bruta)"]),
                    "liquido": parse_float_safe(p["Comissão (s/ Imposto)"]),
                    "breno": parse_float_safe(p["Breno"]),
                    "uriel": parse_float_safe(p["Uriel"]),
                })
    return pd.DataFrame(regs)


def _recebidos_contemplado(df_vendas_global, cfg, datas_fin):
    """Receita de Cartas Contempladas = ÁGIO. O RECEBIMENTO cai ~10 dias após a venda
    (configurável). A data pode ser sobrescrita no Financeiro (financeiro_datas)."""
    regs = []
    if (df_vendas_global is None or df_vendas_global.empty
            or 'TIPO_PRODUTO' not in df_vendas_global.columns):
        return pd.DataFrame(regs)

    df = df_vendas_global[df_vendas_global['TIPO_PRODUTO'].apply(normalizar_string) == "CONSORCIOCONTEMPLADO"]
    for _, r in df.iterrows():
        key = f"CONT_{r.get('id')}"
        data_venda = r.get("DATA", "") or ""
        recebimento_padrao = _mais_dias(data_venda, PRAZO_RECEBIMENTO_CONTEMPLADO_DIAS)
        data_fin = datas_fin.get(key) or recebimento_padrao or data_venda

        agio = parse_float_safe(r.get("AGIO", 0))
        imposto = agio * AGIO_IMPOSTO_PCT / 100.0
        liquido = agio - imposto
        breno, uriel = dividir_socios(r.get("VENDEDOR", ""), liquido, cfg)
        regs.append({
            "key": key,
            "cliente": r.get("Nome do cliente", "") or "—",
            "vendedor": r.get("VENDEDOR", "") or "—",
            "produto": r.get("PRODUTO", "") or "",
            "data_venda": data_venda,
            "data": data_fin, "ym": _ym(data_fin),
            "agio": agio, "liquido": liquido, "breno": breno, "uriel": uriel,
        })
    return pd.DataFrame(regs)


# ==========================================================
# TRAVA ANTI-DUPLICIDADE
# ==========================================================
def _alertas_duplicidade(trad, cont):
    alertas = []
    if trad is not None and not trad.empty and 'key' in trad.columns:
        dup = trad[trad['key'].notna()]
        for chave, n in dup.groupby('key').size().items():
            if n > 1:
                linha = dup[dup['key'] == chave].iloc[0]
                alertas.append(
                    f"🏦 Comissão lançada **{n}x** — {linha['cliente']} ({linha['grupo_cota']}). "
                    f"A mesma parcela aparece mais de uma vez."
                )
    if cont is not None and not cont.empty:
        for (cli, agio, dv), n in cont.groupby(['cliente', 'agio', 'data_venda']).size().items():
            if n > 1:
                alertas.append(
                    f"🎯 Carta contemplada possivelmente **duplicada ({n}x)** — {cli}, "
                    f"ágio {formatar_brl_puro(agio)}, venda em {dv}."
                )
    return alertas


# ==========================================================
# TELA PRINCIPAL
# ==========================================================
def render_financeiro(supabase, df_vendas_global, df_admin, cfg, status_dict):
    st.markdown("### 💰 Financeiro")
    st.caption("Faturamento da Consorbens por mês: comissões recebidas (Consórcio Tradicional) "
               "+ ágio das Cartas Contempladas. Selecione o ano e um ou mais meses para comparar.")

    datas_fin = _carregar_datas_financeiro(supabase)
    trad = _recebidos_tradicional(supabase, df_vendas_global, df_admin, cfg, status_dict, datas_fin)
    cont = _recebidos_contemplado(df_vendas_global, cfg, datas_fin)

    # TRAVA ANTI-DUPLICIDADE
    alertas = _alertas_duplicidade(trad, cont)
    if alertas:
        st.error("⚠️ **Possível duplicidade detectada — confira e corrija:**")
        for a in alertas:
            st.markdown(f"- {a}")
        st.caption("Nos totais, cada comissão repetida conta uma vez só; nas contempladas, confira "
                   "se não cadastrou a mesma venda duas vezes.")

    trad_calc = trad.drop_duplicates('key', keep='first') if not trad.empty else trad

    # Anos disponíveis
    anos = set()
    for d in (trad, cont):
        if not d.empty:
            anos |= {ym[:4] for ym in d['ym'].dropna().tolist()}
    anos.add(str(datetime.today().year))
    anos = sorted(anos, reverse=True)

    c_ano, c_mes = st.columns([1, 3])
    with c_ano:
        ano = st.selectbox("📅 Ano", anos, index=0, key="fin_ano")
    labels_mes = [f"{m:02d}/{ano}" for m in range(1, 13)]
    mes_atual_lbl = f"{datetime.today().month:02d}/{ano}"
    default_mes = [mes_atual_lbl] if mes_atual_lbl in labels_mes else [labels_mes[-1]]
    with c_mes:
        sel_meses = st.multiselect("📆 Meses (pode escolher vários para comparar)", labels_mes,
                                   default=default_mes, key="fin_meses")

    if not sel_meses:
        st.info("Selecione ao menos um mês.")
        return

    sel_meses = [lbl for lbl in labels_mes if lbl in sel_meses]
    yms = [f"{ano}-{lbl[:2]}" for lbl in sel_meses]

    # QUADRO COMPARATIVO (soma tudo do mês — inclusive várias notas)
    linhas = ["💵 Faturamento Total", "   • Consórcio Tradicional", "   • Cartas Contempladas (ágio)",
              "🧾 Receita Líquida", "👤 Breno", "👤 Uriel"]
    dados = {}
    for lbl, ym in zip(sel_meses, yms):
        t = trad_calc[trad_calc['ym'] == ym] if not trad_calc.empty else trad_calc
        c = cont[cont['ym'] == ym] if not cont.empty else cont
        fat_t = t['bruto'].sum() if not t.empty else 0.0
        fat_c = c['agio'].sum() if not c.empty else 0.0
        liq = (t['liquido'].sum() if not t.empty else 0.0) + (c['liquido'].sum() if not c.empty else 0.0)
        breno = (t['breno'].sum() if not t.empty else 0.0) + (c['breno'].sum() if not c.empty else 0.0)
        uriel = (t['uriel'].sum() if not t.empty else 0.0) + (c['uriel'].sum() if not c.empty else 0.0)
        dados[lbl] = [fat_t + fat_c, fat_t, fat_c, liq, breno, uriel]

    df_sum = pd.DataFrame(dados, index=linhas)
    if len(sel_meses) > 1:
        df_sum["TOTAL"] = df_sum.sum(axis=1)
    df_fmt = df_sum.copy()
    for col in df_fmt.columns:
        df_fmt[col] = df_fmt[col].apply(formatar_brl_puro)
    st.dataframe(df_fmt, use_container_width=True)

    st.caption(f"ℹ️ Tradicional entra no mês em que foi **lançado no sistema**. Contemplado entra "
               f"**{PRAZO_RECEBIMENTO_CONTEMPLADO_DIAS} dias após a venda** (recebimento). Ágio hoje "
               f"sem imposto. Você pode corrigir qualquer data no detalhamento abaixo — isso só afeta "
               f"o Financeiro.")

    # DETALHAMENTO POR MÊS
    st.divider()
    st.markdown("#### 🔎 Detalhar um mês")
    mes_det = st.selectbox("Escolha o mês para ver as vendas que compõem o valor:", sel_meses, key="fin_det_mes")
    ym_det = f"{ano}-{mes_det[:2]}"

    aba_t, aba_c = st.tabs(["🏦 Consórcio Tradicional", "🎯 Cartas Contempladas"])
    with aba_t:
        _detalhe_tradicional(supabase, trad[trad['ym'] == ym_det] if not trad.empty else pd.DataFrame(), mes_det)
    with aba_c:
        _detalhe_contemplado(supabase, cont[cont['ym'] == ym_det] if not cont.empty else pd.DataFrame(), mes_det)


# ==========================================================
# DETALHAMENTO — TRADICIONAL (edita a data SÓ do Financeiro)
# ==========================================================
def _detalhe_tradicional(supabase, df, mes_lbl):
    if df is None or df.empty:
        st.info(f"Nenhuma comissão de Consórcio Tradicional recebida em {mes_lbl}.")
        return

    st.caption("Comissões recebidas neste mês. Você pode **corrigir a Data** (só afeta o Financeiro).")
    view = pd.DataFrame({
        "Cliente": df["cliente"].values,
        "Grupo/Cota": df["grupo_cota"].values,
        "Origem": df["origem"].values,
        "Bruto": df["bruto"].apply(formatar_brl_puro).values,
        "Líquido": df["liquido"].apply(formatar_brl_puro).values,
        "Breno": df["breno"].apply(formatar_brl_puro).values,
        "Uriel": df["uriel"].apply(formatar_brl_puro).values,
        "Data": df["data"].astype(str).values,
    })
    edit = st.data_editor(
        view, key=f"fin_edit_trad_{mes_lbl}", hide_index=True, use_container_width=True,
        column_config={c: st.column_config.TextColumn(c, disabled=True)
                       for c in ["Cliente", "Grupo/Cota", "Origem", "Bruto", "Líquido", "Breno", "Uriel"]}
        | {"Data": st.column_config.TextColumn("Data (DD/MM/AAAA)")},
    )
    st.markdown(f"**Total Tradicional em {mes_lbl}:** {formatar_brl_puro(df['bruto'].sum())}")

    if st.button("💾 Salvar datas (Tradicional)", key=f"fin_save_trad_{mes_lbl}"):
        n = 0
        for i in range(len(df)):
            nova = str(edit.iloc[i]["Data"]).strip()
            if nova and nova != str(df.iloc[i]["data"]).strip():
                try:
                    _salvar_data_financeiro(supabase, df.iloc[i]["key"], nova)
                    n += 1
                except Exception as e:
                    st.error(f"Erro ao salvar {df.iloc[i]['cliente']}: {e}")
        if n:
            st.success(f"✅ {n} data(s) atualizada(s) no Financeiro.")
            st.rerun()
        else:
            st.info("Nenhuma data alterada.")


# ==========================================================
# DETALHAMENTO — CONTEMPLADO (edita a data de recebimento SÓ do Financeiro)
# ==========================================================
def _detalhe_contemplado(supabase, df, mes_lbl):
    if df is None or df.empty:
        st.info(f"Nenhuma Carta Contemplada com recebimento em {mes_lbl}.")
        return

    st.caption("Cartas contempladas com **recebimento** neste mês (≈10 dias após a venda). "
               "Você pode corrigir a Data de Recebimento (só afeta o Financeiro).")
    view = pd.DataFrame({
        "Cliente": df["cliente"].values,
        "Vendedor": df["vendedor"].values,
        "Produto": df["produto"].values,
        "Ágio": df["agio"].apply(formatar_brl_puro).values,
        "Breno": df["breno"].apply(formatar_brl_puro).values,
        "Uriel": df["uriel"].apply(formatar_brl_puro).values,
        "Data Venda": df["data_venda"].astype(str).values,
        "Data Recebimento": df["data"].astype(str).values,
    })
    edit = st.data_editor(
        view, key=f"fin_edit_cont_{mes_lbl}", hide_index=True, use_container_width=True,
        column_config={c: st.column_config.TextColumn(c, disabled=True)
                       for c in ["Cliente", "Vendedor", "Produto", "Ágio", "Breno", "Uriel", "Data Venda"]}
        | {"Data Recebimento": st.column_config.TextColumn("Data Recebimento (DD/MM/AAAA)")},
    )
    st.markdown(f"**Total Ágio em {mes_lbl}:** {formatar_brl_puro(df['agio'].sum())}")

    if st.button("💾 Salvar datas (Contemplado)", key=f"fin_save_cont_{mes_lbl}"):
        n = 0
        for i in range(len(df)):
            nova = str(edit.iloc[i]["Data Recebimento"]).strip()
            if nova and nova != str(df.iloc[i]["data"]).strip():
                try:
                    _salvar_data_financeiro(supabase, df.iloc[i]["key"], nova)
                    n += 1
                except Exception as e:
                    st.error(f"Erro ao salvar {df.iloc[i]['cliente']}: {e}")
        if n:
            st.success(f"✅ {n} data(s) atualizada(s) no Financeiro.")
            st.rerun()
        else:
            st.info("Nenhuma data alterada.")
