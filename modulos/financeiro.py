import streamlit as st
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro, parse_float_safe
from regras import gerar_tabela_parcelas
from modulos.integracao_site import carregar_operacoes_site


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
    """Converte qualquer data para 'dd/mm/aaaa' ('' se inválida).
    Detecta automaticamente ISO (2026-08-06T...) x brasileiro (dd/mm/aaaa):
    no ISO NÃO se usa dayfirst (senão o pandas troca dia/mês)."""
    if valor is None or str(valor).strip() == "":
        return ""
    s = str(valor).strip()
    iso = len(s) >= 10 and s[4] == "-" and s[7] == "-"   # 'AAAA-MM-DD...'
    try:
        d = pd.to_datetime(s, dayfirst=not iso, errors="coerce")
        return "" if pd.isna(d) else d.strftime("%d/%m/%Y")
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


# ==========================================================
# TRAVA ANTI-DUPLICIDADE
# ==========================================================
def _alertas_duplicidade(trad):
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
    return alertas


# ==========================================================
# RESUMO DO MÊS ATUAL (usado pelo card do Dashboard)
# ==========================================================
def calcular_resumo_mes_atual(supabase, df_vendas_global, df_admin, cfg, status_dict):
    """Faturamento do mês atual, para o quadrinho do Dashboard: Tradicional
    (recebido até agora), Cotas Contempladas concluídas até agora, previsto
    das Contempladas em andamento (Site), e o total. Reusa exatamente as
    mesmas fontes/fórmulas do quadro do Financeiro — evita números divergentes
    entre as duas telas."""
    hoje = datetime.today()
    ym_atual = f"{hoje.year:04d}-{hoje.month:02d}"

    datas_fin = _carregar_datas_financeiro(supabase)
    trad = _recebidos_tradicional(supabase, df_vendas_global, df_admin, cfg, status_dict, datas_fin)
    trad_calc = trad.drop_duplicates('key', keep='first') if not trad.empty else trad
    t_mes = trad_calc[trad_calc['ym'] == ym_atual] if not trad_calc.empty else trad_calc
    fat_tradicional = t_mes['bruto'].sum() if not t_mes.empty else 0.0

    try:
        site = carregar_operacoes_site()
    except Exception:
        site = pd.DataFrame()
    if site is None:
        site = pd.DataFrame()

    site_ok_mes = site[(site['status'] == 'concluido') & (site['ym'] == ym_atual)] if not site.empty else site
    fat_contemplado = site_ok_mes['agio'].sum() if not site_ok_mes.empty else 0.0

    site_prev = site[site['status'] == 'em_analise'] if not site.empty else site
    fat_previsto = site_prev['agio'].sum() if not site_prev.empty else 0.0

    fat_tradicional = float(fat_tradicional)
    fat_contemplado = float(fat_contemplado)
    fat_previsto = float(fat_previsto)
    return {
        "tradicional": round(fat_tradicional, 2),
        "contemplado_realizado": round(fat_contemplado, 2),
        "contemplado_previsto": round(fat_previsto, 2),
        "total": round(fat_tradicional + fat_contemplado + fat_previsto, 2),
    }


def _publicar_resultado_socios(supabase, ym, breno, uriel):
    """Grava o resultado do mês (Breno/Uriel) em resultado_socios_mensal, para o
    ERP_ECOCLIM ler (linha 'CONS INVESTIMENTOS' do Controle Financeiro) sem
    duplicar a lógica de comissionamento. Nunca deve travar a tela Financeiro."""
    try:
        ano, mes = ym.split("-")
        supabase.table("resultado_socios_mensal").upsert(
            {"ano": int(ano), "mes": int(mes), "breno": round(float(breno), 2), "uriel": round(float(uriel), 2)},
            on_conflict="ano,mes",
        ).execute()
    except Exception:
        pass


def _render_previsao_site(site_prev):
    """Bloco de PREVISÃO: operações do Site ainda EM ANÁLISE (não entram no
    resultado do mês; entram quando concluídas). Independente do seletor de mês."""
    if site_prev is None or site_prev.empty:
        return
    st.divider()
    st.markdown("#### 🔮 Previsão — operações em andamento (Site)")
    st.caption("Cartas contempladas ainda **Em análise** no admin do Site. Não entram no resultado do mês — "
               "entram quando a operação for **concluída**.")
    p1, p2, p3 = st.columns(3)
    p1.metric("Ágio previsto (total)", formatar_brl_puro(site_prev['agio'].sum()))
    p2.metric("Breno (50%)", formatar_brl_puro(site_prev['breno'].sum()))
    p3.metric("Uriel (50%)", formatar_brl_puro(site_prev['uriel'].sum()))
    view = pd.DataFrame({
        "Cliente": site_prev['cliente'].values,
        "Vendedor": site_prev['representante'].values,
        "Produto": site_prev['produto'].values,
        "Ágio previsto": site_prev['agio'].apply(formatar_brl_puro).values,
    })
    st.dataframe(view, use_container_width=True, hide_index=True)


# ==========================================================
# TELA PRINCIPAL
# ==========================================================
def render_financeiro(supabase, df_vendas_global, df_admin, cfg, status_dict):
    st.markdown("### 💰 Financeiro")
    st.caption("Faturamento da Consorbens por mês: comissões recebidas (Consórcio Tradicional) "
               "+ ágio das Cartas Contempladas. Selecione o ano e um ou mais meses para comparar.")

    datas_fin = _carregar_datas_financeiro(supabase)
    trad = _recebidos_tradicional(supabase, df_vendas_global, df_admin, cfg, status_dict, datas_fin)

    # Cartas contempladas: fonte única é o SITE (só leitura). concluído = realizado
    # no mês da conclusão; em análise = previsão.
    try:
        site = carregar_operacoes_site()
    except Exception:
        site = pd.DataFrame()
    if site is None:
        site = pd.DataFrame()
    site_ok = site[site['status'] == 'concluido'] if not site.empty else site      # realizado
    site_prev = site[site['status'] == 'em_analise'] if not site.empty else site    # previsão

    # TRAVA ANTI-DUPLICIDADE
    alertas = _alertas_duplicidade(trad)
    if alertas:
        st.error("⚠️ **Possível duplicidade detectada — confira e corrija:**")
        for a in alertas:
            st.markdown(f"- {a}")
        st.caption("Nos totais, cada comissão repetida conta uma vez só; nas contempladas, confira "
                   "se não cadastrou a mesma venda duas vezes.")

    trad_calc = trad.drop_duplicates('key', keep='first') if not trad.empty else trad

    # Anos disponíveis
    anos = set()
    for d in (trad, site_ok):
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
    linhas = ["💵 Faturamento Total", "   • Consórcio Tradicional", "   • Cartas Contempladas — Site",
              "🧾 Receita Líquida", "👤 Breno", "👤 Uriel"]
    dados = {}
    for lbl, ym in zip(sel_meses, yms):
        t = trad_calc[trad_calc['ym'] == ym] if not trad_calc.empty else trad_calc
        s = site_ok[site_ok['ym'] == ym] if not site_ok.empty else site_ok
        fat_t = t['bruto'].sum() if not t.empty else 0.0
        fat_s = s['agio'].sum() if not s.empty else 0.0        # ágio do Site (concluído no mês)
        liq = (t['liquido'].sum() if not t.empty else 0.0) + fat_s
        breno = (t['breno'].sum() if not t.empty else 0.0) + (s['breno'].sum() if not s.empty else 0.0)
        uriel = (t['uriel'].sum() if not t.empty else 0.0) + (s['uriel'].sum() if not s.empty else 0.0)
        dados[lbl] = [fat_t + fat_s, fat_t, fat_s, liq, breno, uriel]
        _publicar_resultado_socios(supabase, ym, breno, uriel)

    df_sum = pd.DataFrame(dados, index=linhas)
    if len(sel_meses) > 1:
        df_sum["TOTAL"] = df_sum.sum(axis=1)
    df_fmt = df_sum.copy()
    for col in df_fmt.columns:
        df_fmt[col] = df_fmt[col].apply(formatar_brl_puro)
    st.dataframe(df_fmt, use_container_width=True)

    st.caption("ℹ️ Tradicional entra no mês em que foi **lançado no sistema**. "
               "“Cartas Contempladas — Site” são as operações **concluídas** no admin do Site, "
               "no mês da conclusão. Ágio hoje sem imposto.")

    # ---- PREVISÃO (operações do Site ainda EM ANÁLISE) ----
    _render_previsao_site(site_prev)

    # DETALHAMENTO POR MÊS (em popup)
    st.divider()
    st.markdown("#### 🔎 Detalhar")
    mes_det = st.selectbox("Mês para detalhar:", sel_meses, key="fin_det_mes")
    ym_det = f"{ano}-{mes_det[:2]}"
    t_det = trad_calc[trad_calc['ym'] == ym_det] if not trad_calc.empty else pd.DataFrame()
    s_det = site_ok[site_ok['ym'] == ym_det] if not site_ok.empty else pd.DataFrame()

    @st.dialog(f"🏦 Consórcio Tradicional — {mes_det}", width="large")
    def _pop_trad():
        _detalhe_tradicional(supabase, t_det, mes_det)

    @st.dialog(f"🌐 Cartas Contempladas — Site — {mes_det}", width="large")
    def _pop_site():
        _detalhe_site(s_det, mes_det)

    @st.dialog(f"👤 Breno — {mes_det}", width="large")
    def _pop_breno():
        _detalhe_socio("Breno", "breno", t_det, s_det, mes_det)

    @st.dialog(f"👤 Uriel — {mes_det}", width="large")
    def _pop_uriel():
        _detalhe_socio("Uriel", "uriel", t_det, s_det, mes_det)

    st.caption("Clique para conferir/editar em uma janela:")
    bt1, bt2, bt3, bt4 = st.columns(4)
    if bt1.button("🏦 Consórcio Tradicional", use_container_width=True):
        _pop_trad()
    if bt2.button("🌐 Cartas Contempladas — Site", use_container_width=True):
        _pop_site()
    if bt3.button("👤 Breno recebe", use_container_width=True):
        _pop_breno()
    if bt4.button("👤 Uriel recebe", use_container_width=True):
        _pop_uriel()


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
# DETALHAMENTO — CARTAS CONTEMPLADAS (SITE, só leitura)
# ==========================================================
def _detalhe_site(df, mes_lbl):
    """Operações CONCLUÍDAS no admin do Site, neste mês. Só leitura — a edição
    (status, data de conclusão, valores) é feita no próprio admin do Site."""
    if df is None or df.empty:
        st.info(f"Nenhuma Carta Contemplada concluída (no Site) em {mes_lbl}.")
        return

    st.caption("Operações **concluídas** no admin do Site neste mês. Para editar, use o painel do Site.")
    view = pd.DataFrame({
        "Cliente": df["cliente"].values,
        "Vendedor": df["representante"].values,
        "Produto": df["produto"].values,
        "Ágio": df["agio"].apply(formatar_brl_puro).values,
        "Breno": df["breno"].apply(formatar_brl_puro).values,
        "Uriel": df["uriel"].apply(formatar_brl_puro).values,
        "Data Conclusão": df["data_conclusao"].astype(str).values,
    })
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.markdown(f"**Total Ágio em {mes_lbl}:** {formatar_brl_puro(df['agio'].sum())}")


# ==========================================================
# DETALHAMENTO — SÓCIO (Breno / Uriel): o que cada um recebe no mês
# ==========================================================
def _detalhe_socio(nome, col, t_det, s_det, mes_lbl):
    linhas = []
    if t_det is not None and not t_det.empty:
        for _, r in t_det.iterrows():
            linhas.append({"Origem": "Consórcio Tradicional", "Cliente": r["cliente"],
                           "_v": parse_float_safe(r[col])})
    if s_det is not None and not s_det.empty:
        for _, r in s_det.iterrows():
            linhas.append({"Origem": "Carta Contemplada — Site", "Cliente": r["cliente"],
                           "_v": parse_float_safe(r[col])})

    if not linhas:
        st.info(f"{nome} não recebeu nada em {mes_lbl}.")
        return

    df = pd.DataFrame(linhas)
    total = df["_v"].sum()
    df["Recebe"] = df["_v"].apply(formatar_brl_puro)
    st.caption(f"O que **{nome}** recebe em {mes_lbl}, por venda:")
    st.dataframe(df[["Origem", "Cliente", "Recebe"]], use_container_width=True, hide_index=True)
    st.markdown(f"### 💰 Total {nome} em {mes_lbl}: {formatar_brl_puro(total)}")
