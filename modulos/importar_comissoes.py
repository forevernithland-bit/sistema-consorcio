import streamlit as st
import pandas as pd
import re
from datetime import datetime
import pdfplumber
from utils import parse_float_safe, formatar_brl_puro, limpar_str_nan

# ==========================================
# EXPRESSÕES REGULARES DO PDF DA YAMAHA
# (Relatório "Comissões Pagas - Analítico - Modelo Comissionado")
# ==========================================
RE_GRUPO_COTA = re.compile(r"(\d{6})-(\d{4})-\d{2}")          # 009045-0105-00
RE_PCT        = re.compile(r"^\d{1,2},\d{4}$")                # 1,0000 / 0,7000
RE_MOEDA      = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")    # 60.070,00 / 600,70
RE_INT_PEQ    = re.compile(r"^\d{1,2}$")                      # nº da parcela (Pcl)
RE_TOTAL      = re.compile(r"Total de Comiss.o do Per.odo:\s*\(\s*(\d+)\s*\)\s*([\d\.]+,\d{2})\s+([\d\.]+,\d{2})")
RE_PERIODO    = re.compile(r"Encerramento de:\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})")

VENDEDORES = ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]
PRODUTOS = ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"]


def _brl(s):
    return float(str(s).replace(".", "").replace(",", "."))


def _norm(v):
    """Normaliza grupo/cota para comparação (tira zeros à esquerda e '.0')."""
    s = limpar_str_nan(v)
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s.strip()


def _mes_competencia(data_fim_str):
    """'31/07/2026' -> '2026-07'."""
    try:
        d = datetime.strptime(data_fim_str, "%d/%m/%Y")
        return d.strftime("%Y-%m")
    except (ValueError, TypeError):
        return ""


# ==========================================
# 1. LEITOR DO PDF
# ==========================================
def parse_pdf_yamaha(arquivo):
    """Lê o PDF de comissões da Yamaha (todas as páginas).
    Retorna (lista_de_cotas, info_da_nota)."""
    with pdfplumber.open(arquivo) as pdf:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages)

    info = {"periodo_ini": "", "periodo_fim": "", "total_nf": None, "qtd_nf": None}
    mp = RE_PERIODO.search(txt)
    if mp:
        info["periodo_ini"], info["periodo_fim"] = mp.group(1), mp.group(2)
    mt = RE_TOTAL.search(txt)
    if mt:
        info["qtd_nf"] = int(mt.group(1))
        info["total_nf"] = _brl(mt.group(3))

    cotas = []
    for linha in txt.splitlines():
        m = RE_GRUPO_COTA.search(linha)
        if not m:
            continue
        grupo, cota = str(int(m.group(1))), str(int(m.group(2)))
        resto = linha[m.end():].split()
        parcela = next((t for t in resto if RE_INT_PEQ.match(t)), "")
        idx_pct = next((i for i, t in enumerate(resto) if RE_PCT.match(t)), None)
        nums = [t for t in resto[idx_pct + 1:] if RE_MOEDA.match(t)] if idx_pct is not None else []
        if len(nums) < 2:
            continue
        cotas.append({
            "grupo": grupo,
            "cota": cota,
            "parcela": str(parcela),
            "credito": _brl(nums[0]),      # valor da carta / crédito
            "valor_nota": _brl(nums[1]),   # comissão $ (valor da nota)
        })
    return cotas, info


# ==========================================
# 2. REGRAS DE CÁLCULO (imposto + divisão de sócios)
# ==========================================
def dividir_socios(vendedor, liquido, cfg):
    """Divide o valor líquido entre Breno e Uriel conforme o vendedor da cota."""
    v = (vendedor or "").strip().upper()
    if v == "BRENO LIMA":
        b = liquido * parse_float_safe(cfg.get("Breno_Breno", 70.0)) / 100.0
        u = liquido * parse_float_safe(cfg.get("Breno_Uriel", 30.0)) / 100.0
    elif v == "URIEL GOMES":
        u = liquido * parse_float_safe(cfg.get("Uriel_Uriel", 70.0)) / 100.0
        b = liquido * parse_float_safe(cfg.get("Uriel_Breno", 30.0)) / 100.0
    elif v == "CONSORBENS":
        b = liquido * parse_float_safe(cfg.get("Cons_Breno", 50.0)) / 100.0
        u = liquido * parse_float_safe(cfg.get("Cons_Uriel", 50.0)) / 100.0
    else:  # Vendedor Terceiro ou não identificado -> revisar manualmente (50/50 por padrão)
        b = liquido * 0.5
        u = liquido * 0.5
    return round(b, 2), round(u, 2)


def _enriquecer(cotas, df_vendas, admin_padrao):
    """Preenche cliente/vendedor a partir da base de vendas (por grupo+cota)."""
    for c in cotas:
        c.setdefault("cliente", "")
        c.setdefault("vendedor", "")
        c["encontrado"] = False
        c["admin"] = admin_padrao
        c["produto"] = ""
        c["valor_venda"] = c.get("credito", 0.0)
        if df_vendas is not None and not df_vendas.empty:
            match = df_vendas[
                (df_vendas["GRUPO"].apply(_norm) == _norm(c["grupo"])) &
                (df_vendas["COTA"].apply(_norm) == _norm(c["cota"]))
            ]
            if not match.empty:
                r = match.iloc[0]
                c["cliente"] = str(r.get("Nome do cliente", "") or "")
                c["vendedor"] = str(r.get("VENDEDOR", "") or "")
                c["admin"] = str(r.get("ADMINISTRADORA", "") or admin_padrao)
                c["produto"] = str(r.get("PRODUTO", "") or "")
                c["valor_venda"] = parse_float_safe(r.get("Valor_Numerico", c.get("credito", 0.0)))
                c["encontrado"] = True
    return cotas


# ==========================================
# 3. TELA DE IMPORTAÇÃO
# ==========================================
def render_importar_comissoes(supabase, df_vendas_global, cfg, lista_admin_bd):
    st.subheader("📥 Importar Resumo de Comissionamento")
    st.caption("Importe o PDF do relatório de comissões pagas da administradora. "
               "O sistema busca as cotas, calcula imposto e divisão de sócios e prepara a baixa.")

    imp_pct = parse_float_safe(cfg.get("Imposto", 7.16))

    col_a, col_b = st.columns([1, 2])
    with col_a:
        admin_sel = st.selectbox("1️⃣ Administradora", ["Yamaha"],
                                 help="No momento apenas a Yamaha está configurada.")
    with col_b:
        arquivo = st.file_uploader(
            "2️⃣ Envie o arquivo (PDF) do resumo de comissões",
            type=["pdf"], key="upl_comissao"
        )

    if arquivo is not None:
        if st.button("🔍 Processar Arquivo", type="primary"):
            try:
                cotas, info = parse_pdf_yamaha(arquivo)
                if not cotas:
                    st.error("❌ Não consegui identificar nenhuma cota no arquivo. "
                             "Confirme que é o relatório 'Comissões Pagas - Analítico' da Yamaha.")
                else:
                    _enriquecer(cotas, df_vendas_global, admin_sel)
                    st.session_state["import_cotas"] = cotas
                    st.session_state["import_info"] = info
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao ler o PDF: {e}")

    # ---------- PREVIEW / CONFERÊNCIA ----------
    cotas = st.session_state.get("import_cotas")
    if not cotas:
        return

    info = st.session_state.get("import_info", {})
    st.divider()

    ci1, ci2, ci3 = st.columns(3)
    ci1.metric("Cotas no arquivo", len(cotas))
    if info.get("periodo_ini"):
        ci2.metric("Período de encerramento", f"{info['periodo_ini']} → {info['periodo_fim']}")
    if info.get("total_nf") is not None:
        ci3.metric("Total da nota (PDF)", formatar_brl_puro(info["total_nf"]))

    # Tabela editável de entrada
    st.markdown("#### 📝 Confira e ajuste os dados")
    st.caption("Você pode editar Cliente, Vendedor e Valor da Nota. As colunas de cálculo abaixo "
               "atualizam automaticamente. Cotas ⚠️ não foram encontradas — cadastre-as no bloco abaixo.")

    df_in = pd.DataFrame(cotas)
    df_edit = pd.DataFrame({
        "Grupo": df_in["grupo"],
        "Cota": df_in["cota"],
        "Parc.": df_in["parcela"],
        "Cliente": df_in["cliente"],
        "Vendedor": df_in["vendedor"],
        "Valor Nota": df_in["valor_nota"].astype(float),
        "Situação": df_in["encontrado"].apply(lambda x: "✅ No sistema" if x else "⚠️ Cadastrar"),
    })

    edited = st.data_editor(
        df_edit,
        key="editor_import",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Grupo": st.column_config.TextColumn("Grupo", disabled=True),
            "Cota": st.column_config.TextColumn("Cota", disabled=True),
            "Parc.": st.column_config.TextColumn("Parc.", disabled=True, help="Nº da parcela da comissão (Pcl no PDF)"),
            "Cliente": st.column_config.TextColumn("Cliente"),
            "Vendedor": st.column_config.SelectboxColumn("Vendedor", options=VENDEDORES),
            "Valor Nota": st.column_config.NumberColumn("Valor Nota", format="R$ %.2f"),
            "Situação": st.column_config.TextColumn("Situação", disabled=True),
        },
    )

    # Grava as edições de volta na sessão (mesma ordem das linhas)
    for i, c in enumerate(cotas):
        c["cliente"] = str(edited.iloc[i]["Cliente"] or "")
        c["vendedor"] = str(edited.iloc[i]["Vendedor"] or "")
        c["valor_nota"] = float(edited.iloc[i]["Valor Nota"] or 0.0)

    # ---------- CÁLCULO (imposto + divisão) ----------
    linhas_calc = []
    soma_nota = soma_liq = soma_breno = soma_uriel = 0.0
    for c in cotas:
        vn = c["valor_nota"]
        vimp = round(vn * imp_pct / 100.0, 2)
        vliq = round(vn - vimp, 2)
        breno, uriel = dividir_socios(c["vendedor"], vliq, cfg)
        c["imposto_pct"] = imp_pct
        c["imposto"], c["liquido"], c["breno"], c["uriel"] = vimp, vliq, breno, uriel
        soma_nota += vn; soma_liq += vliq; soma_breno += breno; soma_uriel += uriel
        linhas_calc.append({
            "Grupo/Cota": f"{c['grupo']}/{c['cota']}",
            "Cliente": c["cliente"] or "—",
            "Vendedor": c["vendedor"] or "—",
            "Valor Nota": formatar_brl_puro(vn),
            f"Imposto ({imp_pct:.2f}%)": formatar_brl_puro(vimp),
            "Líquido": formatar_brl_puro(vliq),
            "Breno": formatar_brl_puro(breno),
            "Uriel": formatar_brl_puro(uriel),
        })

    st.markdown("#### 💵 Cálculo (imposto e divisão de sócios)")
    st.dataframe(pd.DataFrame(linhas_calc), use_container_width=True, hide_index=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Notas", formatar_brl_puro(soma_nota))
    m2.metric("Total Líquido", formatar_brl_puro(soma_liq))
    m3.metric("Breno", formatar_brl_puro(soma_breno))
    m4.metric("Uriel", formatar_brl_puro(soma_uriel))

    # ---------- CONFERÊNCIA COM O TOTAL DA NOTA ----------
    total_nf = info.get("total_nf")
    nao_encontradas = [c for c in cotas if not c["encontrado"]]
    sem_vendedor = [c for c in cotas if not (c["vendedor"] or "").strip()]
    sem_cliente = [c for c in cotas if not (c["cliente"] or "").strip()]

    if total_nf is not None:
        diff = round(soma_nota - total_nf, 2)
        if abs(diff) < 0.01:
            st.success(f"✅ Conferência OK: a soma das cotas (R$ {soma_nota:,.2f}) bate com o total da nota.")
        else:
            motivos = []
            if nao_encontradas:
                motivos.append(f"{len(nao_encontradas)} cota(s) não encontrada(s) no sistema")
            if abs(diff) > 0.01:
                motivos.append(f"diferença de {formatar_brl_puro(abs(diff))} "
                               f"({'a mais' if diff > 0 else 'a menos'} que a nota)")
            st.warning("⚠️ **Os valores não batem com a nota.** Motivo(s): " +
                       "; ".join(motivos) + ".")

    if nao_encontradas:
        _render_cadastro_faltantes(supabase, cotas, admin_sel)

    # ---------- CONFIRMAÇÃO ----------
    st.divider()
    bloqueios = []
    if sem_cliente:
        bloqueios.append(f"{len(sem_cliente)} cota(s) sem cliente")
    if sem_vendedor:
        bloqueios.append(f"{len(sem_vendedor)} cota(s) sem vendedor")

    if bloqueios:
        st.info("Preencha antes de confirmar: " + "; ".join(bloqueios) + ".")

    cbtn1, cbtn2 = st.columns([3, 1])
    with cbtn1:
        confirmar = st.button("✅ Confirmar e Registrar Pagamentos", type="primary",
                              use_container_width=True, disabled=bool(bloqueios))
    with cbtn2:
        if st.button("🗑️ Cancelar", use_container_width=True):
            _limpar_import()
            st.rerun()

    if confirmar:
        _salvar_pagamentos(supabase, cotas, info, admin_sel)


# ==========================================
# 4. CADASTRO DE COTAS NÃO ENCONTRADAS
# ==========================================
def _render_cadastro_faltantes(supabase, cotas, admin_padrao):
    faltantes = [c for c in cotas if not c["encontrado"]]
    with st.expander(f"⚠️ Cadastrar {len(faltantes)} cota(s) não encontrada(s) no sistema", expanded=True):
        st.caption("Grupo, Cota, Valor da Venda (crédito) e Administradora já vêm do arquivo. "
                   "Complete o restante e cadastre a venda.")
        for c in faltantes:
            st.markdown(f"**Grupo {c['grupo']} / Cota {c['cota']}** — crédito {formatar_brl_puro(c['credito'])}")
            with st.form(f"form_cad_{c['grupo']}_{c['cota']}"):
                cc1, cc2, cc3 = st.columns(3)
                nome = cc1.text_input("Nome do Cliente *", value=c.get("cliente", ""))
                vendedor = cc2.selectbox("Vendedor *", VENDEDORES,
                                         index=VENDEDORES.index(c["vendedor"]) if c.get("vendedor") in VENDEDORES else 0)
                produto = cc3.selectbox("Produto *", PRODUTOS, index=2)  # Moto por padrão (Yamaha)
                cc4, cc5 = st.columns(2)
                valor_venda = cc4.number_input("Valor da Venda (R$) *", value=float(c["credito"]), step=1000.0)
                admin_v = cc5.text_input("Administradora *", value=admin_padrao.upper())

                if st.form_submit_button("💾 Cadastrar Venda", type="primary"):
                    if not nome.strip():
                        st.error("Informe o nome do cliente.")
                    else:
                        try:
                            supabase.table("vendas").insert([{
                                "NOME": nome.strip(),
                                "DATA": datetime.today().strftime("%d/%m/%Y"),
                                "PRODUTO": produto,
                                "VENDEDOR": vendedor,
                                "GRUPO": c["grupo"],
                                "COTA": c["cota"],
                                "ADMINISTRADORA": admin_v.strip(),
                                "STATUS": "Em Andamento",
                                "VALOR": valor_venda,
                            }]).execute()
                            # cadastra o cliente se ainda não existir
                            try:
                                ex = supabase.table("clientes").select("id").eq("Nome", nome.strip()).execute()
                                if not ex.data:
                                    supabase.table("clientes").insert([{
                                        "Nome": nome.strip(),
                                        "Data_Cadastro": datetime.today().strftime("%d/%m/%Y"),
                                    }]).execute()
                            except Exception:
                                pass
                            # atualiza a cota na sessão
                            c["cliente"] = nome.strip()
                            c["vendedor"] = vendedor
                            c["produto"] = produto
                            c["admin"] = admin_v.strip()
                            c["valor_venda"] = valor_venda
                            c["encontrado"] = True
                            st.success(f"✅ Venda cadastrada (Grupo {c['grupo']} / Cota {c['cota']}).")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao cadastrar: {e}")
            st.divider()


# ==========================================
# 5. GRAVAÇÃO (histórico + baixa das parcelas)
# ==========================================
def _salvar_pagamentos(supabase, cotas, info, admin_sel):
    data_pgto = info.get("periodo_fim") or datetime.today().strftime("%d/%m/%Y")
    mes_comp = _mes_competencia(data_pgto)
    ok, erros = 0, 0
    for c in cotas:
        chave = f"{c['cliente']}_{c['grupo']}_{c['cota']}_{c['admin']}_{c['parcela']}"
        try:
            # 1) Histórico detalhado (tabela comissoes_pagas)
            supabase.table("comissoes_pagas").insert({
                "administradora": c["admin"],
                "periodo_inicio": info.get("periodo_ini", ""),
                "periodo_fim": data_pgto,
                "mes_competencia": mes_comp,
                "grupo": c["grupo"],
                "cota": c["cota"],
                "parcela": c["parcela"],
                "cliente": c["cliente"],
                "vendedor": c["vendedor"],
                "credito": c["credito"],
                "valor_nota": c["valor_nota"],
                "imposto_pct": c.get("imposto_pct"),
                "valor_imposto": c["imposto"],
                "valor_liquido": c["liquido"],
                "breno": c["breno"],
                "uriel": c["uriel"],
                "data_pagamento": data_pgto,
                "origem": "NF",
                "chave_unica": chave,
            }).execute()

            # 2) Marca a parcela como PAGA no fluxo existente (status_comissoes)
            ex = supabase.table("status_comissoes").select("id").eq("Chave_Unica", chave).execute()
            payload = {"Chave_Unica": chave, "Status": "PAGO",
                       "Valor_Pago": c["valor_nota"], "Data_Pagamento": data_pgto}
            if ex.data:
                supabase.table("status_comissoes").update(payload).eq("id", ex.data[0]["id"]).execute()
            else:
                supabase.table("status_comissoes").insert(payload).execute()
            ok += 1
        except Exception as e:
            erros += 1
            st.error(f"Erro na cota {c['grupo']}/{c['cota']}: {e}")

    if ok:
        st.success(f"✅ {ok} pagamento(s) registrado(s) no histórico e marcados como PAGO "
                   f"(competência {mes_comp}).")
        _limpar_import()
        st.rerun()
    elif erros:
        st.error("Nenhum pagamento foi salvo. Verifique se a tabela 'comissoes_pagas' existe no Supabase.")


def _limpar_import():
    for k in ["import_cotas", "import_info", "editor_import", "upl_comissao"]:
        st.session_state.pop(k, None)


# ==========================================
# 6. HISTÓRICO MÊS A MÊS
# ==========================================
def render_historico_comissoes(supabase):
    st.subheader("📚 Histórico de Pagamentos (mês a mês)")
    try:
        res = supabase.table("comissoes_pagas").select("*").order("mes_competencia", desc=True).execute()
        df = pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Não foi possível ler o histórico. A tabela 'comissoes_pagas' existe? Detalhes: {e}")
        return

    if df.empty:
        st.info("Ainda não há pagamentos importados.")
        return

    meses = sorted(df["mes_competencia"].dropna().unique(), reverse=True)
    for mes in meses:
        dfm = df[df["mes_competencia"] == mes].copy()
        tot_nota = dfm["valor_nota"].sum()
        tot_breno = dfm["breno"].sum()
        tot_uriel = dfm["uriel"].sum()
        try:
            titulo = datetime.strptime(mes, "%Y-%m").strftime("%m/%Y")
        except (ValueError, TypeError):
            titulo = mes
        # Escapa o "$" para o Streamlit não interpretar como fórmula (LaTeX)
        def _rs(v):
            return formatar_brl_puro(v).replace("$", "\\$")
        titulo_exp = (
            f"📅 {titulo}  —  {len(dfm)} cota(s)  |  "
            f"**Nota Total:** {_rs(tot_nota)}  |  "
            f"**Breno:** {_rs(tot_breno)}  |  "
            f"**Uriel:** {_rs(tot_uriel)}"
        )
        with st.expander(titulo_exp):
            show = pd.DataFrame({
                "Grupo/Cota": dfm["grupo"].astype(str) + "/" + dfm["cota"].astype(str),
                "Parc.": dfm["parcela"],
                "Cliente": dfm["cliente"],
                "Vendedor": dfm["vendedor"],
                "Valor Nota": dfm["valor_nota"].apply(formatar_brl_puro),
                "Líquido": dfm["valor_liquido"].apply(formatar_brl_puro),
                "Breno": dfm["breno"].apply(formatar_brl_puro),
                "Uriel": dfm["uriel"].apply(formatar_brl_puro),
                "Pago em": dfm["data_pagamento"],
            })
            st.dataframe(show, use_container_width=True, hide_index=True)

            opts = dfm.apply(lambda r: f"ID:{r['id']} | {r['grupo']}/{r['cota']} - {r['cliente']}", axis=1).tolist()
            sel = st.selectbox("Remover um lançamento (desfaz a baixa):", [""] + opts, key=f"del_hist_{mes}")
            if sel and st.button("🚨 Remover lançamento", key=f"btn_del_{mes}"):
                rid = int(sel.split(" | ")[0].replace("ID:", ""))
                linha = dfm[dfm["id"] == rid].iloc[0]
                try:
                    supabase.table("comissoes_pagas").delete().eq("id", rid).execute()
                    # reverte o status para Pendente no fluxo de parcelas
                    chave = linha.get("chave_unica")
                    if chave:
                        supabase.table("status_comissoes").update(
                            {"Status": "Pendente"}).eq("Chave_Unica", chave).execute()
                    st.success("Lançamento removido e parcela revertida para Pendente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao remover: {e}")
