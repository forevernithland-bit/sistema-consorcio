import io
import re
import zipfile
import unicodedata
import urllib.parse
import streamlit as st
from utils import iter_linhas
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro, normalizar_string, listar_arquivos_drive, get_drive_service, dt_br
from database import carregar_dados_iniciais
from escopo import filtrar_por_vendedor, filtrar_fila, preencher_cliente


def _nome_arquivo_boleto(cliente, grupo, cota, atraso=False):
    """Mesmo padrão que o robô usa para salvar: primeiroNome_grupo_cota.pdf (minúsculo);
    o boleto EM ATRASO sai como primeiroNome_grupo_cota_atraso.pdf."""
    prim = str(cliente or "").strip().split(" ")[0]
    prim = unicodedata.normalize("NFKD", prim).encode("ascii", "ignore").decode()
    prim = re.sub(r"[^A-Za-z0-9]", "", prim) or "cliente"
    return f"{prim}_{grupo}_{cota}{'_atraso' if atraso else ''}.pdf".lower()


def _mapa_boletos_drive():
    """{'arquivo.pdf' (minúsculo): {'link':..., 'id':...}}. Vazio se o Drive não estiver configurado."""
    try:
        folder = st.secrets.get("BOLETOS_DRIVE_FOLDER_ID", "")
        if not folder:
            return {}
        arquivos = listar_arquivos_drive(folder)
        return {str(a.get("name", "")).lower():
                {"link": (a.get("webContentLink") or a.get("webViewLink") or ""), "id": a.get("id"),
                 "mod": a.get("modifiedTime") or ""}
                for a in arquivos}
    except Exception:
        return {}


def _achar_pdf_boleto(mapa, row):
    """Acha o PDF do boleto desta linha da fila. O nome padrão é primeiroNome_grupo_cota.pdf,
    mas boletos antigos saíram como None_grupo_cota.pdf (sem nome do cliente) e a mesma cota
    pode ter PDFs de meses diferentes: escolhe o PDF gravado logo depois do pedido."""
    atraso = bool(row.get('em_atraso'))
    suf = f"_{row.get('grupo')}_{row.get('cota')}{'_atraso' if atraso else ''}.pdf".lower()
    cands = [(n, i) for n, i in mapa.items()
             if n.endswith(suf) and (atraso or not n.endswith("_atraso.pdf"))
             and n.count("_") == suf.count("_")]
    if not cands:
        return None, None
    ref = pd.to_datetime(row.get('criado_em'), utc=True, errors='coerce')
    if pd.notna(ref):
        depois = []
        for n, i in cands:
            mod = pd.to_datetime(i.get("mod"), utc=True, errors='coerce')
            if pd.notna(mod) and mod >= ref - pd.Timedelta(minutes=10):
                depois.append((mod, n, i))
        if depois:
            _, n, i = min(depois, key=lambda t: t[0])
            return n, i
    nome = _nome_arquivo_boleto(row.get('cliente'), row.get('grupo'), row.get('cota'), atraso=atraso)
    if nome in mapa:
        return nome, mapa[nome]
    return None, None


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _ler_boleto_pdf(file_id, modificado=""):
    """Baixa o PDF do Drive e lê o que está IMPRESSO no boleto: linha digitável, vencimento e valor.
    {'codigo': '', 'venc': '', 'valor': None} quando não der para ler."""
    vazio = {"codigo": "", "venc": "", "valor": None}
    try:
        import pdfplumber
        dados = get_drive_service().files().get_media(fileId=file_id).execute()
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
            p0 = pdf.pages[0]
            palavras = p0.extract_words()
            larg, alt = p0.width, p0.height
    except Exception:
        return vazio
    m = re.search(r"(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14})", txt)
    cod = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    # vencimento = a data do cantinho "Vencimento" (canto superior direito), não a do documento
    datas = [w for w in palavras if re.fullmatch(r"\d{2}/\d{2}/\d{4}", w["text"])
             and w["x0"] > larg * 0.7 and w["top"] < alt * 0.25]
    venc = sorted(datas, key=lambda w: w["top"])[0]["text"] if datas else ""
    if not venc:
        mv = re.search(r"Vencimento\s*(\d{2}/\d{2}/\d{4})", txt)
        venc = mv.group(1) if mv else ""
    valor = None
    if cod:
        try:
            valor = int(cod.split(" ")[-1][-10:]) / 100   # últimos 10 dígitos da linha = valor
        except Exception:
            valor = None
    return {"codigo": cod, "venc": venc, "valor": valor}


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


_LIMPEZA_FEITA = {"mes": None}


def _limpar_boletos_antigos(supabase):
    """Ao virar o mês, apaga os boletos dos meses anteriores (housekeeping).
    Desempenho: roda UMA vez por mês por servidor (antes era um DELETE no banco a
    cada clique da tela). Com a migração 32, cada linha apagada fica na lixeira."""
    mes = _inicio_mes_atual()
    if _LIMPEZA_FEITA["mes"] == mes:
        return
    try:
        supabase.table("fila_automacao").delete() \
            .eq("tipo", "BOLETO").lt("criado_em", mes).execute()
        _LIMPEZA_FEITA["mes"] = mes
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
            dt = dt_br(dt, "%d/%m/%Y") or str(dt)[:10]
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
        for c in iter_linhas(df_cli):
            tel_por_cliente[str(c.get('Nome', ''))] = c.get('Telefone', '')
    st.session_state['_bol_tel'] = tel_por_cliente

    mes_atual = datetime.today().strftime("%m/%Y")
    from modulos.tema import cabecalho; cabecalho("Emissão de Boletos (Yamaha)", "🧾", "Boleto e código de barras de cada cota, prontos para enviar ao cliente.",
              chips=[(f"Referência {mes_atual}", "plain"), ("Envio mensal: todo dia 05", "brand")], eyebrow="Robô Yamaha")
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
    df = filtrar_por_vendedor(df, 'VENDEDOR', eh_adm=is_master)

    if df.empty:
        st.success("Nenhuma cota da Yamaha para emitir boleto no momento. 🎉")
        _painel_status(supabase, is_master, df_vendas_global)
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
            _painel_status(supabase, is_master, df_vendas_global)
            return

    venda_ids = [int(x) for x in df['id'].tolist() if pd.notna(x)]
    mapa_ultimo = _mapa_ultimo_boleto(supabase, venda_ids)
    _resumo_situacoes(venda_ids, mapa_ultimo, df)

    # ---------------- TABELA EDITÁVEL ----------------
    linhas = []
    for r in iter_linhas(df):
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
    _painel_status(supabase, is_master, df_vendas_global)


def _resumo_situacoes(venda_ids, mapa_ultimo, df):
    """Pílulas com a situação dos boletos do mês (só leitura do que já foi carregado)."""
    from modulos.tema import linha_chips
    st_ = [((mapa_ultimo.get(v) or {}).get("status") or "").upper() for v in venda_ids]
    gerados = sum(1 for s in st_ if s in ("SUCESSO", "JA_PAGO", "SEM_BOLETO"))
    fila = sum(1 for s in st_ if s in ("PENDENTE", "PROCESSANDO"))
    erro = sum(1 for s in st_ if s == "ERRO")
    atraso = int((df["_status_norm"] == "EMATRASO").sum()) if "_status_norm" in df.columns else 0
    mensais = int(df["BOLETO_MENSAL"].fillna(False).astype(bool).sum()) if "BOLETO_MENSAL" in df.columns else 0
    chips = [(f"{len(venda_ids)} cota(s) na lista", "plain"), (f"{len(venda_ids) - gerados - fila} sem boleto no mês", "brand"),
             (f"{fila} na fila do robô", "info" if fila else "plain"), (f"{gerados} resolvido(s) no mês", "ok" if gerados else "plain"),
             (f"{mensais} com envio mensal", "plain")]
    if atraso:
        chips.append((f"{atraso} cota(s) em atraso", "warn"))
    if erro:
        chips.append((f"{erro} com erro", "danger"))
    linha_chips(chips)


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
        carregar_dados_iniciais.clear()
        st.success(f"✅ {n} marcação(ões) de Envio Mensal salva(s).")
        st.rerun()
    else:
        st.info("Nenhuma marcação alterada.")


def _painel_status(supabase, is_master, df_vendas_global=None):
    from modulos.tema import secao; secao("Andamento dos Boletos", "📋", "Boletos pedidos no mês escolhido — baixe o PDF ou copie o código.")
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
    # Vendedor só vê os boletos das cotas dele; boletos sem nome de cliente recebem o nome da venda
    df_f = preencher_cliente(df_f, df_vendas_global)
    df_f = filtrar_fila(df_f, df_vendas_global, eh_adm=is_master)
    if df_f is None or df_f.empty:
        st.info(f"Nenhum boleto seu registrado em {sel}.")
        return
    df_f['Situação'] = df_f.apply(lambda x: _rotulo_situacao(x.to_dict()), axis=1)
    df_f['Grupo/Cota'] = df_f['grupo'].fillna('').astype(str) + "/" + df_f['cota'].fillna('').astype(str)
    if 'codigo_barras' not in df_f.columns:
        df_f['codigo_barras'] = ""
    if 'vencimento' not in df_f.columns:
        df_f['vencimento'] = ""
    if 'em_atraso' not in df_f.columns:
        df_f['em_atraso'] = None
    # PDF de cada boleto (Google Drive) + o que está impresso nele (código, vencimento, valor)
    mapa_pdf = _mapa_boletos_drive()
    itens_zip = []  # (label, nome_arquivo, file_id)
    df_f['Boleto'] = df_f['em_atraso'].apply(lambda x: "⚠️ Em atraso" if x is True or x == True else "Do mês")  # noqa: E712

    busca_h = st.text_input("🔍 Buscar no andamento (cliente, grupo/cota, código…)",
                            key="busca_boleto_hist", placeholder="Digite parte do nome, grupo/cota ou código…")
    if busca_h and busca_h.strip():
        b = busca_h.strip()
        mask = False
        for c in ['cliente', 'Grupo/Cota', 'codigo_barras', 'Situação']:
            mask = mask | df_f[c].astype(str).str.contains(b, case=False, na=False)
        df_f = df_f[mask]
        if df_f.empty:
            st.info(f"Nenhum boleto encontrado para “{busca_h}”.")
            return

    def _txt(v):
        v = "" if v is None else str(v).strip()
        return "" if v.lower() in ("", "none", "nan", "nat") else v

    def _data_br(v):
        v = _txt(v)
        if not v:
            return ""
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", v):
            return v
        try:
            return pd.to_datetime(v).strftime("%d/%m/%Y")
        except Exception:
            return v

    linhas = df_f.to_dict("records")
    POR_PAG = 20
    if len(linhas) > POR_PAG:
        paginas = (len(linhas) + POR_PAG - 1) // POR_PAG
        pag = st.selectbox("Página", list(range(1, paginas + 1)), key="bol_hist_pag",
                           format_func=lambda n: f"{n} de {paginas}")
        linhas_pag = linhas[(pag - 1) * POR_PAG: pag * POR_PAG]
    else:
        linhas_pag = linhas

    hoje_d = datetime.today().date()
    with st.spinner("Conferindo código e vencimento nos PDFs…"):
        for row in linhas_pag:
            ok = (row.get('status') or '').upper() == "SUCESSO"
            nome, info = _achar_pdf_boleto(mapa_pdf, row) if ok else (None, None)
            lido = _ler_boleto_pdf(info["id"], info.get("mod", "")) if (info and info.get("id")) else {}
            row['_link'] = (info or {}).get("link", "")
            row['_nome'], row['_fid'] = nome, (info or {}).get("id")
            cod_db, venc_db = _txt(row.get('codigo_barras')), _data_br(row.get('vencimento'))
            row['_cod'] = lido.get("codigo") or cod_db
            row['_venc'] = lido.get("venc") or venc_db
            row['_venc_pdf'] = bool(lido.get("venc"))
            row['_venc_db'] = venc_db
            row['_valor'] = lido.get("valor")
            # guarda no banco o que foi lido do PDF (busca por código e próximas aberturas)
            if row.get('id') and lido.get("codigo") and (cod_db != lido["codigo"]
                                                         or (lido.get("venc") and venc_db != lido["venc"])):
                try:
                    upd = {"codigo_barras": lido["codigo"]}
                    if lido.get("venc"):
                        upd["vencimento"] = lido["venc"]
                    supabase.table("fila_automacao").update(upd).eq("id", row['id']).execute()
                except Exception:
                    pass

    # itens do ZIP: todos os boletos do mês com PDF (não só a página aberta)
    for row in linhas:
        if (row.get('status') or '').upper() != "SUCESSO":
            continue
        nome, info = _achar_pdf_boleto(mapa_pdf, row)
        if info and info.get("id"):
            itens_zip.append((f"{row.get('cliente')} — {row.get('grupo')}/{row.get('cota')}"
                              + (" (atraso)" if row.get('em_atraso') else ""), nome, info["id"]))

    for row in linhas_pag:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3.2, 1.8, 2.6, 1.2], vertical_alignment="center")
            with c1:
                st.markdown(f"**{_txt(row.get('cliente')) or '—'}**")
                st.caption(f"Grupo/Cota **{row['Grupo/Cota']}** · {row['Boleto']}")
            with c2:
                st.markdown(row['Situação'])
            with c3:
                venc = row['_venc']
                if venc:
                    try:
                        vencido = datetime.strptime(venc, "%d/%m/%Y").date() < hoje_d
                    except Exception:
                        vencido = False
                    st.markdown(f"📅 Vence **{venc}**" + (" · :red[**já venceu**]" if vencido else ""))
                    extra = []
                    if row['_valor']:
                        extra.append(formatar_brl_puro(row['_valor']))
                    if row['_venc_pdf']:
                        extra.append("✅ conferido no PDF")
                        if row['_venc_db'] and row['_venc_db'] != venc:
                            extra.append(f"(sistema dizia {row['_venc_db']})")
                    st.caption(" · ".join(extra) if extra else "vencimento do sistema (PDF não lido)")
                else:
                    st.markdown("📅 —")
            with c4:
                if row['_link']:
                    st.link_button("📥 PDF", row['_link'], use_container_width=True)
            if row['_cod']:
                st.caption("Código de barras deste boleto (clique no ícone à direita para copiar):")
                st.code(row['_cod'], language=None)
            elif (row.get('status') or '').upper() == "SUCESSO":
                st.caption("Código de barras não encontrado no PDF.")

    st.caption("ℹ️ Os boletos são gerados quando o **robô do escritório** está ligado. "
               "Código e vencimento são lidos do próprio PDF de cada boleto. "
               "Os boletos deste mês somem sozinhos ao virar o mês.")

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
