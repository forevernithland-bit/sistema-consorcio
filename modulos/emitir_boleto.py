import io
import re
import zipfile
import unicodedata
import urllib.parse
import streamlit as st
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro, normalizar_string, listar_arquivos_drive, get_drive_service


def _nome_arquivo_boleto(cliente, grupo, cota):
    """Mesmo padrão que o robô usa para salvar: primeiroNome_grupo_cota.pdf (minúsculo)."""
    prim = str(cliente or "").strip().split(" ")[0]
    prim = unicodedata.normalize("NFKD", prim).encode("ascii", "ignore").decode()
    prim = re.sub(r"[^A-Za-z0-9]", "", prim) or "cliente"
    return f"{prim}_{grupo}_{cota}.pdf".lower()


def _mapa_boletos_drive():
    """{'arquivo.pdf' (minúsculo): {'link':..., 'id':...}}. Vazio se o Drive não estiver configurado."""
    try:
        folder = st.secrets.get("BOLETOS_DRIVE_FOLDER_ID", "")
        if not folder:
            return {}
        arquivos = listar_arquivos_drive(folder)
        return {str(a.get("name", "")).lower():
                {"link": (a.get("webContentLink") or a.get("webViewLink") or ""), "id": a.get("id")}
                for a in arquivos}
    except Exception:
        return {}


def _gerar_zip(itens):
    """itens = [(nome_arquivo, file_id)]. Baixa os PDFs do Drive e devolve um .zip em bytes."""
    service = get_drive_service()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, fid in itens:
            if not fid:
                continue
            try:
                dados = service.files().get_media(fileId=fid).execute()
                z.writestr(nome, dados)
            except Exception:
                pass
    buf.seek(0)
    return buf.getvalue()


def _tel_wa(tel):
    """Telefone -> formato do wa.me (só dígitos, com 55 na frente)."""
    d = ''.join(filter(str.isdigit, str(tel or "")))
    if not d:
        return ""
    if not d.startswith("55"):
        d = "55" + d
    return d


def _limpar_boletos_antigos(supabase):
    """Ao virar o mês, apaga os boletos dos meses anteriores (housekeeping)."""
    try:
        supabase.table("fila_automacao").delete() \
            .eq("tipo", "BOLETO").lt("criado_em", _inicio_mes_atual()).execute()
    except Exception:
        pass

# Administradoras com automação de boleto configurada (por enquanto Yamaha/Newcon)
ADMINS_COM_BOLETO = ["YAMAHA"]

# Boletos são para cotas que ainda pagam parcelas: Em Andamento e Em Atraso.
STATUS_MOSTRAR = ["EMANDAMENTO", "EMATRASO"]


def _inicio_mes_atual():
    hoje = datetime.today()
    return f"{hoje.year}-{hoje.month:02d}-01"


def _mapa_ultimo_boleto(supabase, venda_ids):
    """{venda_id: último pedido de BOLETO do mês atual}."""
    if not venda_ids:
        return {}
    try:
        res = (supabase.table("fila_automacao").select("*")
               .eq("tipo", "BOLETO").in_("venda_id", list(venda_ids))
               .gte("criado_em", _inicio_mes_atual())
               .order("criado_em", desc=True).execute())
    except Exception:
        return {}
    mapa = {}
    for r in (res.data or []):
        vid = r.get("venda_id")
        if vid is not None and vid not in mapa:
            mapa[vid] = r
    return mapa


def _rotulo_situacao(pedido):
    if not pedido:
        return "—"
    s = (pedido.get("status") or "").upper()
    if s == "PENDENTE":
        return "⏳ Na fila"
    if s == "PROCESSANDO":
        return "🔄 Gerando"
    if s == "ERRO":
        return "❌ Erro"
    if s == "SUCESSO":
        dt = pedido.get("concluido_em") or pedido.get("criado_em") or ""
        try:
            dt = pd.to_datetime(dt).strftime("%d/%m/%Y")
        except Exception:
            dt = str(dt)[:10]
        return f"🧾 Gerado {dt}"
    if s == "JA_PAGO":
        return "✅ Já pago"
    if s == "SEM_BOLETO":
        return "📭 Sem boleto no mês"
    return s or "—"


def render_emitir_boleto(supabase, df_vendas_global, df_cli=None):
    is_master = (st.session_state.get('perfil_logado') == "Master") or \
                (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    _limpar_boletos_antigos(supabase)  # ao virar o mês, some com os boletos antigos

    # mapa nome do cliente -> telefone (para o link do WhatsApp)
    tel_por_cliente = {}
    if df_cli is not None and not df_cli.empty and 'Nome' in df_cli.columns:
        for _, c in df_cli.iterrows():
            tel_por_cliente[str(c.get('Nome', ''))] = c.get('Telefone', '')
    st.session_state['_bol_tel'] = tel_por_cliente

    mes_atual = datetime.today().strftime("%m/%Y")
    st.markdown("### 🧾 Emissão de Boletos (Yamaha)")
    st.caption(
        f"Marque as cotas e clique em **Gerar Boletos**. O robô do escritório entra no Newcon, "
        f"gera o boleto e o **código de barras** de cada cota (para envio ao cliente). Aparecem cotas "
        f"**Em Andamento e Em Atraso** (as em atraso são sinalizadas). Marque **Envio Mensal** para "
        f"gerar o boleto da cota **automaticamente todo dia 05** (o robô do escritório precisa estar "
        f"ligado). Referência: **{mes_atual}**."
    )

    if df_vendas_global is None or df_vendas_global.empty:
        st.info("Ainda não há cotas cadastradas.")
        return

    # ---------------- FILTRO ----------------
    df = df_vendas_global.copy()
    df['_admin_norm'] = df['ADMINISTRADORA'].apply(normalizar_string)
    df['_status_norm'] = df['STATUS'].apply(normalizar_string)
    df = df[df['_admin_norm'].isin(ADMINS_COM_BOLETO)]
    df = df[df['_status_norm'].isin(STATUS_MOSTRAR)]
    if 'TIPO_PRODUTO' in df.columns:
        df = df[df['TIPO_PRODUTO'].apply(normalizar_string) != "CONSORCIOCONTEMPLADO"]
    if not is_master:
        df = df[df['VENDEDOR'] == st.session_state.get('nome_vendedor')]

    if df.empty:
        st.success("Nenhuma cota da Yamaha para emitir boleto no momento. 🎉")
        _painel_status(supabase, is_master)
        return

    df = df.sort_values(by="Data_Real", ascending=False)

    busca = st.text_input("🔍 Buscar cliente, grupo ou cota", key="busca_boleto",
                          placeholder="Digite parte do nome, o grupo ou a cota…")
    if busca and busca.strip():
        b = busca.strip()
        df = df[
            df['Nome do cliente'].astype(str).str.contains(b, case=False, na=False) |
            df['GRUPO'].astype(str).str.contains(b, case=False, na=False) |
            df['COTA'].astype(str).str.contains(b, case=False, na=False)
        ]
        if df.empty:
            st.info(f"Nenhuma cota encontrada para “{b}”.")
            _painel_status(supabase, is_master)
            return

    venda_ids = [int(x) for x in df['id'].tolist() if pd.notna(x)]
    mapa_ultimo = _mapa_ultimo_boleto(supabase, venda_ids)

    # ---------------- TABELA EDITÁVEL ----------------
    linhas = []
    for _, r in df.iterrows():
        vid = int(r['id'])
        pedido = mapa_ultimo.get(vid)
        status_atual = (pedido.get("status") or "").upper() if pedido else ""
        ja_tratado = status_atual in ("PENDENTE", "PROCESSANDO", "SUCESSO", "JA_PAGO", "SEM_BOLETO")
        mensal = bool(r.get('BOLETO_MENSAL', False)) if 'BOLETO_MENSAL' in df.columns else False
        atraso = r.get('_status_norm') == "EMATRASO"
        linhas.append({
            "venda_id": vid,
            "Selecionar": False,
            "Cliente": r.get('Nome do cliente', ''),
            "Vendedor": r.get('VENDEDOR', ''),
            "Produto": r.get('PRODUTO', ''),
            "Grupo/Cota": f"{r.get('GRUPO','')}/{r.get('COTA','')}",
            "Situação Cota": "⚠️ Em Atraso" if atraso else "Em Andamento",
            "Envio Mensal": mensal,
            "Situação": _rotulo_situacao(pedido),
            "_ja_tratado": ja_tratado,
        })
    df_edit = pd.DataFrame(linhas)

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        marcar_todos = st.checkbox("Marcar todos", value=False, key="bol_marcar_todos")
    with c2:
        marcar_mensais = st.checkbox("Marcar os mensais", value=False, key="bol_marcar_mensais")

    if marcar_todos:
        df_edit['Selecionar'] = ~df_edit['_ja_tratado']
    elif marcar_mensais:
        df_edit['Selecionar'] = df_edit['Envio Mensal'] & (~df_edit['_ja_tratado'])

    col_config = {
        "venda_id": None,
        "_ja_tratado": None,
        "Selecionar": st.column_config.CheckboxColumn("✔️", help="Marque para gerar o boleto"),
        "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
        "Vendedor": st.column_config.TextColumn("Vendedor", disabled=True),
        "Produto": st.column_config.TextColumn("Produto", disabled=True),
        "Grupo/Cota": st.column_config.TextColumn("Grupo/Cota", disabled=True),
        "Situação Cota": st.column_config.TextColumn("Situação Cota", disabled=True),
        "Envio Mensal": st.column_config.CheckboxColumn("Envio Mensal", help="Incluir esta cota todo mês"),
        "Situação": st.column_config.TextColumn("Boleto (mês)", disabled=True),
    }

    editor_key = f"editor_boleto_{marcar_todos}_{marcar_mensais}"
    df_result = st.data_editor(
        df_edit, column_config=col_config,
        disabled=["Cliente", "Vendedor", "Produto", "Grupo/Cota", "Situação Cota", "Situação"],
        hide_index=True, use_container_width=True, key=editor_key,
    )

    selecionados = df_result[df_result['Selecionar'] == True]  # noqa: E712
    qtd = len(selecionados)

    st.write("")
    cbt1, cbt2, cbt3 = st.columns([1.2, 1.2, 2])
    with cbt1:
        gerar = st.button(f"🧾 Gerar Boletos ({qtd})" if qtd else "🧾 Gerar Boletos",
                          type="primary", use_container_width=True, disabled=(qtd == 0))
    with cbt2:
        salvar_mensal = st.button("💾 Salvar 'Envio Mensal'", use_container_width=True)

    if gerar and qtd:
        _enfileirar(supabase, selecionados, mapa_ultimo)
    if salvar_mensal:
        _salvar_flags_mensais(supabase, df_edit, df_result)

    st.divider()
    _painel_status(supabase, is_master)


def _enfileirar(supabase, selecionados, mapa_ultimo):
    usuario = st.session_state.get('usuario_logado', 'desconhecido')
    inseridos, pulados = 0, 0
    for _, r in selecionados.iterrows():
        vid = int(r['venda_id'])
        pedido_ant = mapa_ultimo.get(vid)
        if pedido_ant and (pedido_ant.get("status") or "").upper() in (
                "PENDENTE", "PROCESSANDO", "SUCESSO", "JA_PAGO", "SEM_BOLETO"):
            pulados += 1
            continue
        grupo, cota = "", ""
        gc = str(r.get('Grupo/Cota', ''))
        if "/" in gc:
            grupo, cota = gc.split("/", 1)
        payload = {
            "tipo": "BOLETO", "venda_id": vid,
            "cliente": r.get('Cliente'), "vendedor": r.get('Vendedor'),
            "produto": r.get('Produto'), "administradora": "Yamaha",
            "grupo": grupo.strip(), "cota": cota.strip(),
            "status": "PENDENTE", "solicitado_por": usuario,
        }
        try:
            supabase.table("fila_automacao").insert(payload).execute()
            inseridos += 1
        except Exception as e:
            st.error(f"Erro ao enfileirar {r.get('Cliente')} ({gc}): {e}")
    if inseridos:
        st.success(f"✅ {inseridos} boleto(s) enviados para a fila! O robô vai gerar em seguida.")
    if pulados:
        st.warning(f"⚠️ {pulados} cota(s) já gerada(s)/na fila neste mês foram ignoradas.")
    if inseridos:
        st.rerun()


def _salvar_flags_mensais(supabase, df_antes, df_depois):
    """Persiste a coluna 'Envio Mensal' na tabela vendas (BOLETO_MENSAL)."""
    n = 0
    for i in range(len(df_depois)):
        antes = bool(df_antes.iloc[i]['Envio Mensal'])
        depois = bool(df_depois.iloc[i]['Envio Mensal'])
        if antes != depois:
            vid = int(df_depois.iloc[i]['venda_id'])
            try:
                supabase.table("vendas").update({"BOLETO_MENSAL": depois}).eq("id", vid).execute()
                n += 1
            except Exception as e:
                st.error(f"Erro ao salvar {df_depois.iloc[i]['Cliente']}: {e}")
    if n:
        st.success(f"✅ {n} marcação(ões) de Envio Mensal salva(s).")
        st.rerun()
    else:
        st.info("Nenhuma marcação alterada.")


def _painel_status(supabase, is_master):
    st.subheader("📋 Andamento dos Boletos")
    hoje = datetime.today()
    meses = []
    y, m = hoje.year, hoje.month
    for _ in range(12):
        meses.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    labels = [f"{mm:02d}/{yy}" for (yy, mm) in meses]

    cab1, cab2 = st.columns([3, 1])
    with cab1:
        sel = st.selectbox("📅 Mês", labels, index=0, key="bol_hist_mes")
    with cab2:
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True, key="bol_refresh"):
            try:
                listar_arquivos_drive.clear()  # busca os PDFs novos do Drive na hora
            except Exception:
                pass
            st.rerun()

    y_sel, m_sel = meses[labels.index(sel)]
    ini = f"{y_sel}-{m_sel:02d}-01"
    ny, nm = (y_sel + 1, 1) if m_sel == 12 else (y_sel, m_sel + 1)
    fim = f"{ny}-{nm:02d}-01"

    try:
        res = (supabase.table("fila_automacao").select("*")
               .eq("tipo", "BOLETO").gte("criado_em", ini).lt("criado_em", fim)
               .order("criado_em", desc=True).limit(1000).execute())
        dados = res.data or []
    except Exception as e:
        st.error(f"Não foi possível ler a fila: {e}")
        return

    if not dados:
        st.info(f"Nenhum boleto registrado em {sel}.")
        return

    df_f = pd.DataFrame(dados)
    df_f['Situação'] = df_f.apply(lambda x: _rotulo_situacao(x.to_dict()), axis=1)
    df_f['Grupo/Cota'] = df_f['grupo'].fillna('').astype(str) + "/" + df_f['cota'].fillna('').astype(str)
    if 'codigo_barras' not in df_f.columns:
        df_f['codigo_barras'] = ""
    if 'vencimento' not in df_f.columns:
        df_f['vencimento'] = ""
    if 'em_atraso' not in df_f.columns:
        df_f['em_atraso'] = None
    # Link para baixar o PDF do boleto (Google Drive) e coleta dos itens p/ ZIP em lote
    mapa_pdf = _mapa_boletos_drive()
    itens_zip = []  # (label, nome_arquivo, file_id)

    def _link_pdf(row):
        if (row.get('status') or '').upper() != "SUCESSO":
            return ""
        nome = _nome_arquivo_boleto(row.get('cliente'), row.get('grupo'), row.get('cota'))
        info = mapa_pdf.get(nome)
        if info and info.get("id"):
            itens_zip.append((f"{row.get('cliente')} — {row.get('grupo')}/{row.get('cota')}", nome, info["id"]))
        return (info or {}).get("link", "")
    df_f['Baixar'] = df_f.apply(_link_pdf, axis=1)

    cols = ['cliente', 'Grupo/Cota', 'Situação', 'vencimento', 'codigo_barras', 'Baixar']
    df_show = df_f[cols].rename(columns={'cliente': 'Cliente', 'vencimento': 'Vencimento',
                                         'codigo_barras': 'Código de Barras'})

    busca_h = st.text_input("🔍 Buscar no andamento (cliente, grupo/cota, código…)",
                            key="busca_boleto_hist", placeholder="Digite parte do nome, grupo/cota ou código…")
    if busca_h and busca_h.strip():
        b = busca_h.strip()
        mask = False
        for c in ['Cliente', 'Grupo/Cota', 'Código de Barras', 'Situação']:
            mask = mask | df_show[c].astype(str).str.contains(b, case=False, na=False)
        df_show = df_show[mask]

    if df_show.empty:
        st.info(f"Nenhum boleto encontrado para “{busca_h}”.")
        return
    st.dataframe(
        df_show, use_container_width=True, hide_index=True,
        column_config={
            "Código de Barras": st.column_config.TextColumn("Código de Barras", width="large"),
            "Baixar": st.column_config.LinkColumn("Baixar", display_text="📥 PDF"),
        },
    )
    st.caption("ℹ️ Os boletos são gerados quando o **robô do escritório** está ligado. "
               "Clique em **📥 PDF** para baixar. Os boletos deste mês somem sozinhos ao virar o mês.")

    # --- Baixar vários boletos de uma vez (ZIP) ---
    if itens_zip:
        st.markdown("##### 📦 Baixar vários boletos de uma vez")
        labels = [it[0] for it in itens_zip]
        sel_zip = st.multiselect("Selecione (deixe vazio = baixar TODOS):", labels, key="bol_sel_zip")
        escolhidos = [it for it in itens_zip if it[0] in sel_zip] or itens_zip
        if st.button(f"📦 Preparar ZIP ({len(escolhidos)} boleto(s))", key="bol_zip_btn"):
            with st.spinner("Baixando os PDFs do Drive e montando o ZIP…"):
                st.session_state['bol_zip_bytes'] = _gerar_zip([(n, fid) for (_, n, fid) in escolhidos])
        if st.session_state.get('bol_zip_bytes'):
            st.download_button("⬇️ Baixar ZIP", st.session_state['bol_zip_bytes'],
                               file_name=f"boletos_{sel.replace('/', '-')}.zip",
                               mime="application/zip", key="bol_zip_dl")
