import re
import streamlit as st
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro, normalizar_string, normalizar_produto

# Administradoras que já têm automação de lance configurada no Worker.
# Por enquanto só a Yamaha (site newkey.cny.com.br).
ADMINS_COM_LANCE = ["YAMAHA"]

# Regras do LANCE FIXO por produto (Yamaha, out/2026).
#   lance    = % total do lance fixo
#   embutido = % que pode sair do próprio crédito (embutido)
#   próprios = lance - embutido  (o que o cliente paga de recurso próprio)
# O usuário pode ajustar linha a linha, pois alguns grupos têm ajuste.
LANCE_FIXO_DEFAULTS = {
    "IMOVEL":   {"lance": 30.0, "embutido": 25.0},  # -> 5% próprios
    "MOTO":     {"lance": 35.0, "embutido": 15.0},  # -> 20% próprios
    "AUTO":     {"lance": 25.0, "embutido": 15.0},  # -> 10% próprios
    "CAMINHAO": {"lance": 25.0, "embutido": 25.0},  # -> 0% próprios (grupo permite até 30%)
}
DEFAULT_LANCE = {"lance": 0.0, "embutido": 0.0}

# Canceladas e contempladas NÃO aparecem. Em Andamento e Em Atraso aparecem.
STATUS_OCULTAR = ["CANCELADA", "CONTEMPLADA"]


def _regra_lance(produto):
    """Retorna o dict de default (lance/embutido) para o produto da cota."""
    return LANCE_FIXO_DEFAULTS.get(normalizar_produto(produto), DEFAULT_LANCE)


def _inicio_mes_atual():
    """Primeiro dia do mês atual (ex: '2026-08-01') — a conferência é mensal."""
    hoje = datetime.today()
    return f"{hoje.year}-{hoje.month:02d}-01"


def _mapa_ultimo_lance(supabase, venda_ids):
    """Retorna {venda_id: dict_do_ultimo_pedido} DO MÊS ATUAL lendo a fila_automacao.
    Pedidos de meses anteriores são ignorados aqui (viram histórico), para que,
    ao virar o mês, as cotas não contempladas voltem a aparecer como disponíveis.
    Serve para mostrar a 'Situação' de cada cota e evitar pedidos duplicados no mês."""
    if not venda_ids:
        return {}
    try:
        res = (supabase.table("fila_automacao")
               .select("*")
               .eq("tipo", "LANCE")
               .in_("venda_id", list(venda_ids))
               .gte("criado_em", _inicio_mes_atual())
               .order("criado_em", desc=True)
               .execute())
    except Exception:
        return {}

    mapa = {}
    for r in (res.data or []):
        vid = r.get("venda_id")
        if vid is not None and vid not in mapa:  # como veio ordenado desc, o 1º é o mais recente
            mapa[vid] = r
    return mapa


def _rotulo_situacao(pedido):
    """Texto amigável da situação do último pedido daquela cota."""
    if not pedido:
        return "—"
    status = (pedido.get("status") or "").upper()
    if status == "PENDENTE":
        return "⏳ Na fila"
    if status == "PROCESSANDO":
        return "🔄 Processando"
    if status == "ERRO":
        return "❌ Erro"
    if status == "SUCESSO":
        dt = pedido.get("concluido_em") or pedido.get("criado_em") or ""
        try:
            dt = pd.to_datetime(dt).strftime("%d/%m/%Y")
        except Exception:
            dt = str(dt)[:10]
        return f"✅ Ofertado {dt}"
    if status == "JA_OFERTADO":
        m = re.search(r"(\d{2}/\d{2}/\d{4})", pedido.get("mensagem") or "")
        return f"☑️ Já ofertado em {m.group(1)}" if m else "☑️ Já estava ofertado"
    return status or "—"


def render_ofertar_lance(supabase, df_vendas_global):
    is_master = (st.session_state.get('perfil_logado') == "Master") or \
                (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    mes_atual = datetime.today().strftime("%m/%Y")
    st.markdown("### 🎯 Ofertar Lance (Yamaha)")
    st.caption(
        f"Marque as cotas e clique em **Ofertar Lance**. O robô do escritório oferta cota a cota "
        f"no Newcon, aguardando a confirmação de cada uma. **Canceladas e contempladas não aparecem** "
        f"(Em Andamento e Em Atraso aparecem). "
        f"A conferência é **mensal** (referência: **{mes_atual}**): ao virar o mês, as cotas não "
        f"contempladas voltam a aparecer como disponíveis, e os lances dos meses anteriores ficam "
        f"guardados no histórico abaixo."
    )

    if df_vendas_global is None or df_vendas_global.empty:
        st.info("Ainda não há cotas cadastradas.")
        return

    # ------------------------------------------------------------------
    # 1. FILTRO: Yamaha + não contemplados (+ apenas do vendedor, se não for master)
    # ------------------------------------------------------------------
    df = df_vendas_global.copy()
    df['_admin_norm'] = df['ADMINISTRADORA'].apply(normalizar_string)
    df['_status_norm'] = df['STATUS'].apply(normalizar_string)

    df = df[df['_admin_norm'].isin(ADMINS_COM_LANCE)]
    df = df[~df['_status_norm'].isin(STATUS_OCULTAR)]

    if not is_master:
        df = df[df['VENDEDOR'] == st.session_state.get('nome_vendedor')]

    if df.empty:
        st.success("Nenhuma cota da Yamaha pendente de lance no momento. 🎉")
        _painel_status(supabase, is_master)
        return

    df = df.sort_values(by="Data_Real", ascending=False)

    # Campo de busca (cliente, grupo ou cota)
    busca = st.text_input("🔍 Buscar cliente, grupo ou cota", key="busca_ofertar",
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

    # ------------------------------------------------------------------
    # 2. Situação atual de cada cota (lida da fila)
    # ------------------------------------------------------------------
    venda_ids = [int(x) for x in df['id'].tolist() if pd.notna(x)]
    mapa_ultimo = _mapa_ultimo_lance(supabase, venda_ids)

    # ------------------------------------------------------------------
    # 3. Monta a tabela editável
    # ------------------------------------------------------------------
    linhas = []
    for _, r in df.iterrows():
        vid = int(r['id'])
        pedido = mapa_ultimo.get(vid)
        status_atual = (pedido.get("status") or "").upper() if pedido else ""
        # "Já tratado no mês": na fila, em processamento, ofertado ou já-ofertado.
        # (ERRO fica de fora, pois precisa de atenção / pode ser reofertado.)
        na_fila = status_atual in ("PENDENTE", "PROCESSANDO", "SUCESSO", "JA_OFERTADO")
        regra = _regra_lance(r.get('PRODUTO', ''))
        lance = regra["lance"]
        embutido = regra["embutido"]
        linhas.append({
            "venda_id": vid,
            "Selecionar": False,
            "Cliente": r.get('Nome do cliente', ''),
            "Vendedor": r.get('VENDEDOR', ''),
            "Produto": r.get('PRODUTO', ''),
            "Grupo/Cota": f"{r.get('GRUPO','')}/{r.get('COTA','')}",
            "Valor": formatar_brl_puro(r.get('Valor_Numerico', 0)),
            "Lance Fixo (%)": lance,
            "Embutido (%)": embutido,
            "Próprios (%)": max(0.0, lance - embutido),
            "Situação": _rotulo_situacao(pedido),
            "_na_fila": na_fila,
        })
    df_edit = pd.DataFrame(linhas)

    c_top1, c_top2 = st.columns([1, 3])
    with c_top1:
        marcar_todos = st.checkbox("Marcar todos", value=False, key="lance_marcar_todos")
    with c_top2:
        st.caption(
            "💡 Só **Lance Fixo** por enquanto. Os percentuais já vêm pré-preenchidos por produto; "
            "você pode ajustar **Lance Fixo (%)** e **Embutido (%)** por linha se o grupo exigir. "
            "**Próprios (%) = Lance Fixo − Embutido** (recalcula ao atualizar a tela)."
        )

    if marcar_todos:
        # Só marca os que ainda não estão na fila (evita repetir pedido)
        df_edit['Selecionar'] = ~df_edit['_na_fila']

    col_config = {
        "venda_id": None,
        "_na_fila": None,
        "Selecionar": st.column_config.CheckboxColumn("✔️", help="Marque para ofertar o lance"),
        "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
        "Vendedor": st.column_config.TextColumn("Vendedor", disabled=True),
        "Produto": st.column_config.TextColumn("Produto", disabled=True),
        "Grupo/Cota": st.column_config.TextColumn("Grupo/Cota", disabled=True),
        "Valor": st.column_config.TextColumn("Valor da Carta", disabled=True),
        "Lance Fixo (%)": st.column_config.NumberColumn("Lance Fixo (%)", min_value=0.0, max_value=100.0, step=0.5, format="%.2f%%", help="% total do lance fixo"),
        "Embutido (%)": st.column_config.NumberColumn("Embutido (%)", min_value=0.0, max_value=100.0, step=0.5, format="%.2f%%", help="% que sai do próprio crédito"),
        "Próprios (%)": st.column_config.NumberColumn("Próprios (%)", format="%.2f%%", help="Recursos próprios = Lance Fixo − Embutido (calculado)"),
        "Situação": st.column_config.TextColumn("Situação", disabled=True),
    }

    # A key muda junto com "marcar todos" para o editor refletir a marcação em massa
    editor_key = f"editor_lance_{marcar_todos}"
    df_result = st.data_editor(
        df_edit,
        column_config=col_config,
        disabled=["Cliente", "Vendedor", "Produto", "Grupo/Cota", "Valor", "Próprios (%)", "Situação"],
        hide_index=True,
        use_container_width=True,
        key=editor_key,
    )

    selecionados = df_result[df_result['Selecionar'] == True]  # noqa: E712
    qtd = len(selecionados)

    st.write("")
    c_bt1, c_bt2 = st.columns([1, 3])
    with c_bt1:
        ofertar = st.button(
            f"🚀 Ofertar Lance ({qtd})" if qtd else "🚀 Ofertar Lance",
            type="primary", use_container_width=True, disabled=(qtd == 0),
        )
    with c_bt2:
        if qtd:
            st.caption(f"{qtd} cota(s) selecionada(s) serão enviadas para a fila do robô.")

    if ofertar and qtd:
        _enfileirar(supabase, selecionados, mapa_ultimo)

    st.divider()
    _painel_status(supabase, is_master)


def _enfileirar(supabase, selecionados, mapa_ultimo):
    """Grava os pedidos selecionados na fila_automacao (status PENDENTE)."""
    usuario = st.session_state.get('usuario_logado', 'desconhecido')
    inseridos, pulados, erros = 0, 0, 0

    for _, r in selecionados.iterrows():
        vid = int(r['venda_id'])

        # Evita duplicar no mês: se a cota já está na fila, em processamento,
        # ofertada ou já-ofertada NESTE mês, pula (a conferência é mensal).
        pedido_ant = mapa_ultimo.get(vid)
        if pedido_ant and (pedido_ant.get("status") or "").upper() in (
                "PENDENTE", "PROCESSANDO", "SUCESSO", "JA_OFERTADO"):
            pulados += 1
            continue

        pct_lance = float(r['Lance Fixo (%)'])
        pct_embutido = float(r['Embutido (%)'])
        pct_proprio = max(0.0, pct_lance - pct_embutido)

        grupo, cota = "", ""
        gc = str(r.get('Grupo/Cota', ''))
        if "/" in gc:
            grupo, cota = gc.split("/", 1)

        payload = {
            "tipo": "LANCE",
            "venda_id": vid,
            "cliente": r.get('Cliente'),
            "vendedor": r.get('Vendedor'),
            "produto": r.get('Produto'),
            "administradora": "Yamaha",
            "grupo": grupo.strip(),
            "cota": cota.strip(),
            "tipo_lance": "Lance Fixo",
            "pct_lance": pct_lance,
            "pct_embutido": pct_embutido,
            "pct_proprio": pct_proprio,
            "status": "PENDENTE",
            "solicitado_por": usuario,
        }
        try:
            supabase.table("fila_automacao").insert(payload).execute()
            inseridos += 1
        except Exception as e:
            erros += 1
            st.error(f"Erro ao enfileirar {r.get('Cliente')} ({gc}): {e}")

    if inseridos:
        st.success(f"✅ {inseridos} lance(s) enviados para a fila! O robô vai processar em seguida.")
    if pulados:
        st.warning(f"⚠️ {pulados} cota(s) já tratada(s) neste mês (na fila ou ofertada) foram ignoradas.")
    if inseridos:
        st.rerun()


def _painel_status(supabase, is_master):
    """Mostra os pedidos da fila do mês escolhido (padrão: mês atual)."""
    st.subheader("📋 Andamento dos Lances")

    # Seletor de mês (mês atual + históricos dos meses anteriores)
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
        sel = st.selectbox("📅 Mês", labels, index=0, key="lance_hist_mes")
    with cab2:
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True):
            st.rerun()

    y_sel, m_sel = meses[labels.index(sel)]
    ini = f"{y_sel}-{m_sel:02d}-01"
    ny, nm = (y_sel + 1, 1) if m_sel == 12 else (y_sel, m_sel + 1)
    fim = f"{ny}-{nm:02d}-01"

    try:
        res = (supabase.table("fila_automacao")
               .select("*")
               .eq("tipo", "LANCE")
               .gte("criado_em", ini)
               .lt("criado_em", fim)
               .order("criado_em", desc=True)
               .limit(1000)
               .execute())
        dados = res.data or []
    except Exception as e:
        st.error(f"Não foi possível ler a fila: {e}")
        return

    if not dados:
        st.info(f"Nenhum lance registrado em {sel}.")
        return

    df_f = pd.DataFrame(dados)
    df_f['Situação'] = df_f.apply(lambda x: _rotulo_situacao(x.to_dict()), axis=1)

    def _dt(v):
        try:
            return pd.to_datetime(v).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return ""
    df_f['Solicitado em'] = df_f['criado_em'].apply(_dt)
    df_f['Grupo/Cota'] = df_f['grupo'].fillna('').astype(str) + "/" + df_f['cota'].fillna('').astype(str)

    def _pct(v):
        try:
            return f"{float(v):g}%"
        except Exception:
            return "—"
    df_f['Lance (E/P)'] = df_f.apply(
        lambda x: f"{_pct(x.get('pct_lance'))} (emb {_pct(x.get('pct_embutido'))} / próp {_pct(x.get('pct_proprio'))})",
        axis=1,
    )

    if 'protocolo' not in df_f.columns:
        df_f['protocolo'] = ""
    df_f['Comprovante'] = df_f['protocolo'].apply(
        lambda p: f"📄 {p}" if p and str(p) not in ("None", "nan", "SIMULACAO") else ""
    )

    cols = ['cliente', 'Grupo/Cota', 'tipo_lance', 'Lance (E/P)', 'Situação', 'Comprovante', 'mensagem', 'Solicitado em']
    ren = {'cliente': 'Cliente', 'tipo_lance': 'Tipo', 'mensagem': 'Mensagem'}
    df_show = df_f[cols].rename(columns=ren)

    # Campo de busca (cliente, grupo/cota, protocolo ou situação)
    busca_h = st.text_input("🔍 Buscar no andamento (cliente, grupo/cota, protocolo…)",
                            key="busca_andamento", placeholder="Digite parte do nome, grupo/cota ou protocolo…")
    if busca_h and busca_h.strip():
        b = busca_h.strip()
        mask = False
        for c in ['Cliente', 'Grupo/Cota', 'Comprovante', 'Situação', 'Mensagem']:
            mask = mask | df_show[c].astype(str).str.contains(b, case=False, na=False)
        df_show = df_show[mask]

    if df_show.empty:
        st.info(f"Nenhum lance encontrado para “{busca_h}”.")
        return
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    st.caption(
        "ℹ️ Os lances só são efetivados quando o **robô do escritório** está ligado. "
        "Enquanto ele não roda, os pedidos ficam com a situação **⏳ Na fila**."
    )
