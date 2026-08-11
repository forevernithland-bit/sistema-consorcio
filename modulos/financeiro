import streamlit as st
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro, parse_float_safe, normalizar_string
from regras import gerar_tabela_parcelas
from modulos.importar_comissoes import dividir_socios

# Brecha para imposto sobre o ÁGIO (Consórcio Contemplado).
# Por enquanto 0 (ágio entra líquido). Quando a contabilidade definir, é só mudar aqui.
AGIO_IMPOSTO_PCT = 0.0


# ==========================================================
# HELPERS DE DATA
# ==========================================================
def _ym(data_str):
    """Converte uma data (dd/mm/aaaa ou texto) em 'AAAA-MM'. Retorna None se inválida."""
    try:
        d = pd.to_datetime(data_str, dayfirst=True, errors="coerce")
        if pd.isna(d):
            return None
        return d.strftime("%Y-%m")
    except Exception:
        return None


def _label_mes(ym):
    """'2026-08' -> '08/2026'."""
    try:
        return datetime.strptime(ym, "%Y-%m").strftime("%m/%Y")
    except Exception:
        return ym


# ==========================================================
# FONTES DE DADOS (sem duplicidade)
# ==========================================================
def _recebidos_tradicional(supabase, df_vendas_global, df_admin, cfg, status_dict):
    """Comissões efetivamente RECEBIDAS do Consórcio Tradicional.
    Fonte 1: comissoes_pagas (Importar Resumo NF) — detalhe real.
    Fonte 2: baixas manuais (parcelas PAGAS que NÃO vieram por NF), via motor de regras.
    Dedup por chave_unica (uma parcela conta uma vez só)."""
    regs = []
    chaves_nf = set()

    # Fonte 1 — histórico detalhado das NFs
    try:
        cp = supabase.table("comissoes_pagas").select("*").execute().data or []
    except Exception:
        cp = []
    for r in cp:
        ch = r.get("chave_unica")
        if ch:
            chaves_nf.add(ch)
        regs.append({
            "origem": "NF", "id": r.get("id"), "chave": ch,
            "cliente": r.get("cliente", "") or "—",
            "grupo_cota": f"{r.get('grupo','')}/{r.get('cota','')}",
            "data": r.get("data_pagamento", "") or "",
            "ym": _ym(r.get("data_pagamento", "")),
            "bruto": parse_float_safe(r.get("valor_nota", 0)),
            "liquido": parse_float_safe(r.get("valor_liquido", 0)),
            "breno": parse_float_safe(r.get("breno", 0)),
            "uriel": parse_float_safe(r.get("uriel", 0)),
        })

    # Fonte 2 — baixas manuais (PAGO) que não estão no histórico NF
    if df_vendas_global is not None and not df_vendas_global.empty:
        df_parc, _ = gerar_tabela_parcelas(df_vendas_global, df_vendas_global, df_admin, cfg, status_dict)
        if not df_parc.empty:
            pagos = df_parc[df_parc["Status"] == "PAGO"]
            for _, p in pagos.iterrows():
                if p["Chave"] in chaves_nf:
                    continue  # já contado pela NF
                regs.append({
                    "origem": "Manual", "id": None, "chave": p["Chave"],
                    "cliente": p["Cliente"],
                    "grupo_cota": f"{p['Grupo']}/{p['Cota']}",
                    "data": p["Data Recebimento"],
                    "ym": _ym(p["Data Recebimento"]),
                    "bruto": parse_float_safe(p["Comissão (Bruta)"]),
                    "liquido": parse_float_safe(p["Comissão (s/ Imposto)"]),
                    "breno": parse_float_safe(p["Breno"]),
                    "uriel": parse_float_safe(p["Uriel"]),
                })
    return pd.DataFrame(regs)


def _recebidos_contemplado(df_vendas_global, cfg):
    """Receita de Cartas Contempladas = ÁGIO. Dividido pela regra do vendedor."""
    regs = []
    if (df_vendas_global is None or df_vendas_global.empty
            or 'TIPO_PRODUTO' not in df_vendas_global.columns):
        return pd.DataFrame(regs)

    df = df_vendas_global[df_vendas_global['TIPO_PRODUTO'].apply(normalizar_string) == "CONSORCIOCONTEMPLADO"]
    for _, r in df.iterrows():
        agio = parse_float_safe(r.get("AGIO", 0))
        imposto = agio * AGIO_IMPOSTO_PCT / 100.0
        liquido = agio - imposto
        breno, uriel = dividir_socios(r.get("VENDEDOR", ""), liquido, cfg)
        data_str = r.get("DATA", "") or ""
        regs.append({
            "id": r.get("id"),
            "cliente": r.get("Nome do cliente", "") or "—",
            "vendedor": r.get("VENDEDOR", "") or "—",
            "produto": r.get("PRODUTO", "") or "",
            "data": data_str, "ym": _ym(data_str),
            "agio": agio, "liquido": liquido, "breno": breno, "uriel": uriel,
            "valor_consorcio": parse_float_safe(r.get("Valor_Numerico", 0)),
            "entrada": parse_float_safe(r.get("VALOR_ENTRADA", 0)),
        })
    return pd.DataFrame(regs)


# ==========================================================
# TRAVA ANTI-DUPLICIDADE
# ==========================================================
def _alertas_duplicidade(trad, cont):
    """Procura valores contabilizados mais de uma vez e devolve uma lista de alertas."""
    alertas = []

    # Tradicional: a MESMA parcela (mesma chave) lançada mais de uma vez
    if trad is not None and not trad.empty and 'chave' in trad.columns:
        dup = trad[trad['chave'].notna()]
        contagem = dup.groupby('chave').size()
        for chave, n in contagem[contagem > 1].items():
            linha = dup[dup['chave'] == chave].iloc[0]
            alertas.append(
                f"🏦 Comissão lançada **{n}x** — {linha['cliente']} ({linha['grupo_cota']}). "
                f"A mesma parcela aparece mais de uma vez."
            )

    # Contemplado: a MESMA venda (cliente + ágio + data) aparece mais de uma vez
    if cont is not None and not cont.empty:
        for (cli, agio, data), n in cont.groupby(['cliente', 'agio', 'data']).size().items():
            if n > 1:
                alertas.append(
                    f"🎯 Carta contemplada possivelmente **duplicada ({n}x)** — {cli}, "
                    f"ágio {formatar_brl_puro(agio)}, em {data}."
                )
    return alertas


# ==========================================================
# TELA PRINCIPAL
# ==========================================================
def render_financeiro(supabase, df_vendas_global, df_admin, cfg, status_dict):
    st.markdown("### 💰 Financeiro")
    st.caption("Faturamento da Consorbens por mês: comissões recebidas (Consórcio Tradicional) "
               "+ ágio das Cartas Contempladas. Selecione o ano e um ou mais meses para comparar.")

    trad = _recebidos_tradicional(supabase, df_vendas_global, df_admin, cfg, status_dict)
    cont = _recebidos_contemplado(df_vendas_global, cfg)

    # TRAVA ANTI-DUPLICIDADE — avisa se algo está contabilizado mais de uma vez
    alertas = _alertas_duplicidade(trad, cont)
    if alertas:
        st.error("⚠️ **Possível duplicidade detectada — confira e corrija os lançamentos:**")
        for a in alertas:
            st.markdown(f"- {a}")
        st.caption("Nas comissões (Tradicional), cada parcela repetida é contada **uma vez só** nos "
                   "totais — mas vale corrigir na origem. Nas cartas contempladas, confira se não "
                   "cadastrou a mesma venda duas vezes (apague a repetida em Nova Venda/Dashboard).")

    # Para os cálculos, cada parcela de comissão conta uma única vez (dedup por chave)
    trad_calc = trad.drop_duplicates('chave', keep='first') if not trad.empty else trad

    # Anos disponíveis (dos dados) + ano atual
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

    # Ordena os meses selecionados cronologicamente
    sel_meses = [lbl for lbl in labels_mes if lbl in sel_meses]
    yms = [f"{ano}-{lbl[:2]}" for lbl in sel_meses]

    # ------------------------------------------------------------------
    # QUADRO COMPARATIVO (meses nas colunas)
    # ------------------------------------------------------------------
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

    st.caption("ℹ️ Ágio hoje entra **sem imposto** (a definir com a contabilidade). "
               "Receita Líquida = comissões líquidas (após imposto) + ágio.")

    # ------------------------------------------------------------------
    # DETALHAMENTO POR MÊS (clique para ver as vendas e corrigir datas)
    # ------------------------------------------------------------------
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
# DETALHAMENTO — TRADICIONAL (edita data de pagamento)
# ==========================================================
def _detalhe_tradicional(supabase, df, mes_lbl):
    if df is None or df.empty:
        st.info(f"Nenhuma comissão de Consórcio Tradicional recebida em {mes_lbl}.")
        return

    st.caption("Comissões recebidas neste mês. Você pode **corrigir a Data** e salvar "
               "(o valor vai para o mês certo).")
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

    tot = df["bruto"].sum()
    st.markdown(f"**Total Tradicional em {mes_lbl}:** {formatar_brl_puro(tot)}")

    if st.button("💾 Salvar datas (Tradicional)", key=f"fin_save_trad_{mes_lbl}"):
        alterados = 0
        for i in range(len(df)):
            nova_data = str(edit.iloc[i]["Data"]).strip()
            antiga = str(df.iloc[i]["data"]).strip()
            if nova_data and nova_data != antiga:
                origem = df.iloc[i]["origem"]
                try:
                    if origem == "NF" and pd.notna(df.iloc[i]["id"]):
                        supabase.table("comissoes_pagas").update(
                            {"data_pagamento": nova_data}).eq("id", int(df.iloc[i]["id"])).execute()
                    else:  # Manual -> status_comissoes pela chave
                        supabase.table("status_comissoes").update(
                            {"Data_Pagamento": nova_data}).eq("Chave_Unica", df.iloc[i]["chave"]).execute()
                    alterados += 1
                except Exception as e:
                    st.error(f"Erro ao salvar {df.iloc[i]['cliente']}: {e}")
        if alterados:
            st.success(f"✅ {alterados} data(s) atualizada(s).")
            st.rerun()
        else:
            st.info("Nenhuma data alterada.")


# ==========================================================
# DETALHAMENTO — CONTEMPLADO (edita data da venda)
# ==========================================================
def _detalhe_contemplado(supabase, df, mes_lbl):
    if df is None or df.empty:
        st.info(f"Nenhuma Carta Contemplada vendida em {mes_lbl}.")
        return

    st.caption("Cartas contempladas vendidas neste mês. Você pode **corrigir a Data** e salvar.")
    view = pd.DataFrame({
        "Cliente": df["cliente"].values,
        "Vendedor": df["vendedor"].values,
        "Produto": df["produto"].values,
        "Ágio": df["agio"].apply(formatar_brl_puro).values,
        "Breno": df["breno"].apply(formatar_brl_puro).values,
        "Uriel": df["uriel"].apply(formatar_brl_puro).values,
        "Data": df["data"].astype(str).values,
    })
    edit = st.data_editor(
        view, key=f"fin_edit_cont_{mes_lbl}", hide_index=True, use_container_width=True,
        column_config={c: st.column_config.TextColumn(c, disabled=True)
                       for c in ["Cliente", "Vendedor", "Produto", "Ágio", "Breno", "Uriel"]}
        | {"Data": st.column_config.TextColumn("Data (DD/MM/AAAA)")},
    )

    tot = df["agio"].sum()
    st.markdown(f"**Total Ágio em {mes_lbl}:** {formatar_brl_puro(tot)}")

    if st.button("💾 Salvar datas (Contemplado)", key=f"fin_save_cont_{mes_lbl}"):
        alterados = 0
        for i in range(len(df)):
            nova_data = str(edit.iloc[i]["Data"]).strip()
            antiga = str(df.iloc[i]["data"]).strip()
            if nova_data and nova_data != antiga and pd.notna(df.iloc[i]["id"]):
                try:
                    supabase.table("vendas").update(
                        {"DATA": nova_data}).eq("id", int(df.iloc[i]["id"])).execute()
                    alterados += 1
                except Exception as e:
                    st.error(f"Erro ao salvar {df.iloc[i]['cliente']}: {e}")
        if alterados:
            st.success(f"✅ {alterados} data(s) atualizada(s).")
            st.rerun()
        else:
            st.info("Nenhuma data alterada.")
