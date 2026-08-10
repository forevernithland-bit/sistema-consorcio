import streamlit as st
import pandas as pd
from datetime import datetime
from utils import formatar_brl_puro, normalizar_string

# Administradoras que já têm automação de lance configurada no Worker.
# Por enquanto só a Yamaha (site newkey.cny.com.br).
ADMINS_COM_LANCE = ["YAMAHA"]

OPCOES_TIPO_LANCE = ["Lance Fixo", "Lance Livre"]

# Status da cota que NÃO deve aparecer para ofertar lance
STATUS_OCULTAR = ["CONTEMPLADA"]


def _mapa_ultimo_lance(supabase, venda_ids):
    """Retorna {venda_id: dict_do_ultimo_pedido} lendo a fila_automacao.
    Serve para mostrar a 'Situação' de cada cota e evitar pedidos duplicados."""
    if not venda_ids:
        return {}
    try:
        res = (supabase.table("fila_automacao")
               .select("*")
               .eq("tipo", "LANCE")
               .in_("venda_id", list(venda_ids))
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
    return status or "—"


def render_ofertar_lance(supabase, df_vendas_global):
    is_master = (st.session_state.get('perfil_logado') == "Master") or \
                (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    st.markdown("### 🎯 Ofertar Lance (Yamaha)")
    st.caption(
        "Marque as cotas, escolha o tipo de lance e clique em **Ofertar Lance**. "
        "O sistema envia os pedidos para a fila e o robô do escritório oferta cota a cota no Newcon, "
        "aguardando a confirmação de cada uma antes de seguir. Cotas **Contempladas** não aparecem."
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
        na_fila = status_atual in ("PENDENTE", "PROCESSANDO")
        linhas.append({
            "venda_id": vid,
            "Selecionar": False,
            "Cliente": r.get('Nome do cliente', ''),
            "Vendedor": r.get('VENDEDOR', ''),
            "Produto": r.get('PRODUTO', ''),
            "Grupo/Cota": f"{r.get('GRUPO','')}/{r.get('COTA','')}",
            "Valor": formatar_brl_puro(r.get('Valor_Numerico', 0)),
            "Tipo de Lance": "Lance Fixo",
            "Lance Livre (%)": 0.0,
            "Situação": _rotulo_situacao(pedido),
            "_na_fila": na_fila,
        })
    df_edit = pd.DataFrame(linhas)

    c_top1, c_top2 = st.columns([1, 3])
    with c_top1:
        marcar_todos = st.checkbox("Marcar todos", value=False, key="lance_marcar_todos")
    with c_top2:
        st.caption("💡 O campo **Lance Livre (%)** só é usado quando o tipo for *Lance Livre*.")

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
        "Tipo de Lance": st.column_config.SelectboxColumn("Tipo de Lance", options=OPCOES_TIPO_LANCE, required=True),
        "Lance Livre (%)": st.column_config.NumberColumn("Lance Livre (%)", min_value=0.0, max_value=100.0, step=0.5, format="%.2f%%"),
        "Situação": st.column_config.TextColumn("Situação", disabled=True),
    }

    # A key muda junto com "marcar todos" para o editor refletir a marcação em massa
    editor_key = f"editor_lance_{marcar_todos}"
    df_result = st.data_editor(
        df_edit,
        column_config=col_config,
        disabled=["Cliente", "Vendedor", "Produto", "Grupo/Cota", "Valor", "Situação"],
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

        # Evita duplicar: se já tem um pedido PENDENTE/PROCESSANDO, pula
        pedido_ant = mapa_ultimo.get(vid)
        if pedido_ant and (pedido_ant.get("status") or "").upper() in ("PENDENTE", "PROCESSANDO"):
            pulados += 1
            continue

        tipo_lance = r['Tipo de Lance']
        valor_lance = float(r['Lance Livre (%)']) if tipo_lance == "Lance Livre" else None

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
            "tipo_lance": tipo_lance,
            "valor_lance": valor_lance,
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
        st.warning(f"⚠️ {pulados} cota(s) já estavam na fila e foram ignoradas.")
    if inseridos:
        st.rerun()


def _painel_status(supabase, is_master):
    """Mostra os últimos pedidos da fila e como está cada um."""
    cab1, cab2 = st.columns([3, 1])
    with cab1:
        st.subheader("📋 Andamento dos Lances")
    with cab2:
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True):
            st.rerun()

    try:
        res = (supabase.table("fila_automacao")
               .select("*")
               .eq("tipo", "LANCE")
               .order("criado_em", desc=True)
               .limit(50)
               .execute())
        dados = res.data or []
    except Exception as e:
        st.error(f"Não foi possível ler a fila: {e}")
        return

    if not dados:
        st.info("Nenhum lance na fila ainda.")
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

    cols = ['cliente', 'Grupo/Cota', 'tipo_lance', 'Situação', 'mensagem', 'Solicitado em']
    ren = {'cliente': 'Cliente', 'tipo_lance': 'Tipo', 'mensagem': 'Mensagem'}
    df_show = df_f[cols].rename(columns=ren)
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    st.caption(
        "ℹ️ Os lances só são efetivados quando o **robô do escritório** está ligado. "
        "Enquanto ele não roda, os pedidos ficam com a situação **⏳ Na fila**."
    )
