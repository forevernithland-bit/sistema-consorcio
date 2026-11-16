import re
import streamlit as st
import pandas as pd
from datetime import datetime
from escopo import filtrar_por_vendedor, filtrar_fila, preencher_cliente
from utils import formatar_brl_puro, normalizar_string, normalizar_produto, dt_br
from modulos import regras_lance_yamaha as RL

# 16/11/2026: todas as modalidades que o grupo liberar + repetir nos próximos meses.
MODS_CURTOS = ["Fixo", "2º Fixo", "Livre", "Limitado", "Fidelidade"]
REPETIR_OPCOES = ["Só este mês", "2 meses", "3 meses", "4 meses", "6 meses", "12 meses", "Ilimitado"]
REDUZIR_OPCOES = ["Parcela", "Prazo"]

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


def _nome_curto(nome):
    """Só 1º nome + último sobrenome, pra não ocupar tanta largura na tabela.
    'DAVIDSON VINICIU LACERDA DA SILVA' -> 'DAVIDSON SILVA'. Tira apelido entre
    parênteses ('... (Nay)' -> '...') e ignora conectivos (da, de, do…) no fim."""
    limpo = re.sub(r"\s*\([^)]*\)", "", str(nome or "")).strip()
    partes = [p for p in limpo.split() if p]
    if len(partes) <= 2:
        return " ".join(partes)
    conectivos = {"da", "de", "do", "dos", "das", "e"}
    sobren = partes[-1]
    if sobren.lower() in conectivos and len(partes) >= 3:
        sobren = partes[-2]
    return f"{partes[0]} {sobren}"


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
        if vid is None:
            continue
        # como veio ordenado desc, o 1º é o mais recente. Uma SIMULAÇÃO (teste) não
        # esconde um pedido de verdade do mês.
        ant = mapa.get(vid)
        if ant is None or ((ant.get("status") or "").upper() == "SIMULADO"
                           and (r.get("status") or "").upper() != "SIMULADO"):
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
            dt = dt_br(dt, "%d/%m/%Y") or str(dt)[:10]
        except Exception:
            dt = str(dt)[:10]
        return f"✅ Ofertado {dt}"
    if status == "JA_OFERTADO":
        m = re.search(r"(\d{2}/\d{2}/\d{4})", pedido.get("mensagem") or "")
        return f"☑️ Já ofertado em {m.group(1)}" if m else "☑️ Já estava ofertado"
    if status == "SIMULADO":
        return "🧪 Simulado (teste)"
    return status or "—"


def render_ofertar_lance(supabase, df_vendas_global):
    is_master = (st.session_state.get('perfil_logado') == "Master") or \
                (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    mes_atual = datetime.today().strftime("%m/%Y")
    from modulos.tema import cabecalho; cabecalho("Ofertar Lance (Yamaha)", "🎯", "Marque as cotas e o robô do escritório oferta no Newcon, uma a uma.",
              chips=[(f"Referência {mes_atual}", "plain"), ("Todas as modalidades", "brand")], eyebrow="Robô Yamaha")
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

    # Consórcio Contemplado não oferta lance — fica de fora da lista
    if 'TIPO_PRODUTO' in df.columns:
        df = df[df['TIPO_PRODUTO'].apply(normalizar_string) != "CONSORCIOCONTEMPLADO"]

    df = filtrar_por_vendedor(df, 'VENDEDOR', eh_adm=is_master)

    if df.empty:
        st.success("Nenhuma cota da Yamaha pendente de lance no momento. 🎉")
        _painel_status(supabase, is_master, df_vendas_global)
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
            _painel_status(supabase, is_master, df_vendas_global)
            return

    # ------------------------------------------------------------------
    # 2. Situação atual de cada cota (lida da fila)
    # ------------------------------------------------------------------
    venda_ids = [int(x) for x in df['id'].tolist() if pd.notna(x)]
    mapa_ultimo = _mapa_ultimo_lance(supabase, venda_ids)
    _resumo_situacoes(venda_ids, mapa_ultimo)

    # ------------------------------------------------------------------
    # 3. Regras do grupo (modalidades liberadas, % fixo, embutido) + médias
    # ------------------------------------------------------------------
    regras = RL.carregar_regras(supabase)

    linhas = []
    for _, r in df.iterrows():
        vid = int(r['id'])
        pedido = mapa_ultimo.get(vid)
        status_atual = (pedido.get("status") or "").upper() if pedido else ""
        # "Já tratado no mês": na fila, em processamento, ofertado ou já-ofertado.
        # (ERRO e SIMULADO ficam de fora: podem ser (re)ofertados.)
        na_fila = status_atual in ("PENDENTE", "PROCESSANDO", "SUCESSO", "JA_OFERTADO")
        rg = RL.regra_do_grupo(regras, r.get('GRUPO', ''), r.get('PRODUTO', ''))
        lance = float(rg["fixo_pct"] or _regra_lance(r.get('PRODUTO', ''))["lance"] or 0)
        embutido = min(float(rg["embutido_max_pct"] or 0), lance)
        linhas.append({
            "venda_id": vid,
            "Selecionar": False,
            "Cliente": _nome_curto(r.get('Nome do cliente', '')),
            "Situação": _rotulo_situacao(pedido),
            "Grupo/Cota": f"{r.get('GRUPO','')}/{r.get('COTA','')}",
            "Produto": r.get('PRODUTO', ''),
            "Vendedor": r.get('VENDEDOR', ''),
            "Valor": formatar_brl_puro(r.get('Valor_Numerico', 0)),
            "Modalidade": "Fixo",
            "Lance (%)": lance,
            "Embutido (%)": embutido,
            "Próprios (%)": max(0.0, lance - embutido),
            "Reduzir": "Parcela",
            "Repetir": "Só este mês",
            "Regras do grupo": RL.resumo_txt(rg),
            "Média de lance (últ. assembleias)": RL.medias_txt(rg),
            "_na_fila": na_fila,
            "_grupo": str(r.get('GRUPO', '')).strip(),
        })
    df_edit = pd.DataFrame(linhas)

    c_top1, c_top2 = st.columns([1, 3])
    with c_top1:
        marcar_todos = st.checkbox("Marcar todos", value=False, key="lance_marcar_todos")
    with c_top2:
        st.caption(
            "💡 Escolha a **Modalidade** que o grupo libera (coluna *Regras do grupo*). "
            "**Fixo / 2º Fixo**: o % do lance é o do grupo (o Newcon preenche sozinho). "
            "**Livre / Limitado / Fidelidade**: digite o **Lance (%)** total; o **Embutido (%)** sai do "
            "crédito (até o permitido no grupo) e o resto são **recursos próprios**. "
            "**Repetir**: deixa o mesmo lance programado para os próximos meses."
        )

    if marcar_todos:
        # Só marca os que ainda não estão na fila (evita repetir pedido)
        df_edit['Selecionar'] = ~df_edit['_na_fila']

    col_config = {
        "venda_id": None,
        "_na_fila": None,
        "_grupo": None,
        "Selecionar": st.column_config.CheckboxColumn("✔️", help="Marque para ofertar o lance"),
        "Cliente": st.column_config.TextColumn("Cliente", disabled=True, width="small"),
        "Situação": st.column_config.TextColumn("Situação", disabled=True, width="medium"),
        "Grupo/Cota": st.column_config.TextColumn("Grupo/Cota", disabled=True, width="small"),
        "Produto": st.column_config.TextColumn("Produto", disabled=True, width="small"),
        "Vendedor": st.column_config.TextColumn("Vendedor", disabled=True, width="small"),
        "Valor": st.column_config.TextColumn("Valor da Carta", disabled=True, width="small"),
        "Modalidade": st.column_config.SelectboxColumn("Modalidade", options=MODS_CURTOS, required=True,
                                                       help="Só vale a que o grupo libera (ver Regras do grupo)"),
        "Lance (%)": st.column_config.NumberColumn("Lance (%)", min_value=0.0, max_value=100.0, step=0.5, format="%.2f%%",
                                                   help="% TOTAL do lance (embutido + próprios). No Fixo/2º Fixo vale o % do grupo."),
        "Embutido (%)": st.column_config.NumberColumn("Embutido (%)", min_value=0.0, max_value=100.0, step=0.5, format="%.2f%%",
                                                      help="% que sai do próprio crédito — até o permitido no grupo"),
        "Próprios (%)": st.column_config.NumberColumn("Próprios (%)", format="%.2f%%", help="Lance − Embutido (recalcula no resumo abaixo)"),
        "Reduzir": st.column_config.SelectboxColumn("Reduzir", options=REDUZIR_OPCOES, required=True,
                                                    help="Depois de contemplar: reduzir o valor da parcela ou o prazo"),
        "Repetir": st.column_config.SelectboxColumn("Repetir", options=REPETIR_OPCOES, required=True,
                                                    help="Oferta o mesmo lance nos próximos meses (até contemplar)"),
        "Regras do grupo": st.column_config.TextColumn("Regras do grupo", disabled=True, width="medium"),
        "Média de lance (últ. assembleias)": st.column_config.TextColumn("Média de lance (últ. assembleias)", disabled=True, width="medium"),
    }

    # A key muda junto com "marcar todos" para o editor refletir a marcação em massa
    editor_key = f"editor_lance_{marcar_todos}"
    df_result = st.data_editor(
        df_edit,
        column_config=col_config,
        disabled=["Cliente", "Vendedor", "Produto", "Grupo/Cota", "Valor", "Próprios (%)", "Situação",
                  "Regras do grupo", "Média de lance (últ. assembleias)"],
        hide_index=True,
        use_container_width=True,
        key=editor_key,
    )

    selecionados = df_result[df_result['Selecionar'] == True]  # noqa: E712
    qtd = len(selecionados)

    # Resumo + conferência de cada linha contra as regras do grupo
    pedidos, problemas = [], []
    for _, r in selecionados.iterrows():
        rg = RL.regra_do_grupo(regras, r["_grupo"], r.get("Produto"))
        ok, msg, ped = _validar_linha(r, rg)
        (pedidos if ok else problemas).append((r, msg, ped))
    if qtd:
        from modulos.tema import secao
        secao("Conferência antes de enviar", "🔎", "Como cada lance vai para o robô, já conferido com as regras do grupo.")
        conf = []
        for r, msg, ped in pedidos + problemas:
            conf.append({
                "Cliente": r["Cliente"], "Grupo/Cota": r["Grupo/Cota"],
                "Modalidade": ped["tipo_lance"] if ped else r["Modalidade"],
                "Lance": RL.pct_txt(ped["pct_lance"]) if ped else "—",
                "Embutido": RL.pct_txt(ped["pct_embutido"]) if ped else "—",
                "Próprios": RL.pct_txt(ped["pct_proprio"]) if ped else "—",
                "Reduzir": r["Reduzir"], "Repetir": r["Repetir"],
                "Conferência": ("✅ " + msg) if ped else ("⛔ " + msg),
            })
        st.dataframe(pd.DataFrame(conf), hide_index=True, use_container_width=True)

    st.write("")
    c_bt1, c_bt2, c_bt3 = st.columns([1, 1.2, 2])
    with c_bt1:
        ofertar = st.button(
            f"🚀 Ofertar Lance ({len(pedidos)})" if pedidos else "🚀 Ofertar Lance",
            type="primary", use_container_width=True, disabled=(len(pedidos) == 0),
        )
    with c_bt2:
        simular = False
        if is_master:
            simular = st.checkbox("🧪 Só simular no Newcon", value=False, key="lance_so_simular",
                                  help="Teste: o robô preenche a oferta e clica em 'Simular...', "
                                       "SEM confirmar. Nada é enviado à Yamaha.")
    with c_bt3:
        if qtd:
            st.caption(f"{len(pedidos)} de {qtd} cota(s) prontas para a fila do robô"
                       + (f" · {len(problemas)} com problema (não vão)" if problemas else "") + ".")

    if ofertar and pedidos:
        _enfileirar(supabase, pedidos, mapa_ultimo, simular=simular)

    _painel_regras(regras, df)
    _painel_programados(supabase, is_master, df_vendas_global)
    st.divider()
    _painel_status(supabase, is_master, df_vendas_global)


def _validar_linha(r, rg):
    """Confere a linha com as regras do grupo. Devolve (ok, mensagem, pedido|None)."""
    mod = RL.DO_CURTO.get(r.get("Modalidade") or "Fixo", "Lance Fixo")
    if not rg["liberadas"].get(mod):
        lib = ", ".join(RL.CURTO[m] for m in RL.MODALIDADES if rg["liberadas"].get(m))
        return False, f"o grupo {rg['grupo']} não libera {RL.CURTO[mod]} (libera: {lib})", None
    emb = float(r.get("Embutido (%)") or 0)
    if mod == "Lance Fixo":
        lance = float(rg["fixo_pct"] or r.get("Lance (%)") or 0)
    elif mod == "2º Lance Fixo":
        lance = float(rg["fixo2_pct"] or 0)
        if not lance:
            return False, f"não sei o % do 2º fixo do grupo {rg['grupo']} — o robô ainda não leu", None
    else:
        lance = float(r.get("Lance (%)") or 0)
        if lance <= 0:
            return False, "digite o Lance (%)", None
        # (Lance Mínimo/Máximo da tela são DA COTA lida — dependem do saldo —, não do grupo;
        #  por isso não travam aqui. Limitado/Fidelidade máximos são do grupo.)
        lim_max = {"Lance Limitado": rg.get("limitado_max_pct"),
                   "Lance Fidelidade": rg.get("fidelidade_max_pct")}.get(mod)
        lim_min = {"Lance Limitado": rg.get("limitado_min_pct")}.get(mod)
        if lim_max and lance > lim_max:
            return False, f"{RL.CURTO[mod]} do grupo vai até {RL.pct_txt(lim_max)}", None
        if lim_min and lance < lim_min:
            return False, f"{RL.CURTO[mod]} do grupo começa em {RL.pct_txt(lim_min)}", None
    emb_max = float(rg["embutido_max_pct"] or 0)
    if mod in ("Lance Fixo", "2º Lance Fixo"):
        emb = min(emb, emb_max, lance)     # fixo: % do grupo; embutido cabe nele
    if mod == "Lance Limitado" and emb > 0:
        # testado no Newcon em 16/11/2026 (9047, 9538): no Limitado o campo de embutido fica travado
        return False, "o Limitado não aceita embutido no Newcon — use Embutido 0% (tudo recursos próprios)", None
    if emb > emb_max + 1e-9:
        return False, f"embutido acima do permitido no grupo ({RL.pct_txt(emb_max)}, {rg['embutido_fonte']})", None
    if emb > lance + 1e-9:
        return False, "embutido maior que o lance", None
    rep = r.get("Repetir") or "Só este mês"
    meses = None if rep == "Ilimitado" else int(rep.split()[0]) if rep[0].isdigit() else 1
    ped = {"tipo_lance": mod, "pct_lance": round(lance, 4), "pct_embutido": round(emb, 4),
           "pct_proprio": round(max(0.0, lance - emb), 4),
           "tipo_reducao": "Reduzir Prazo" if r.get("Reduzir") == "Prazo" else "Reduzir Parcela",
           "meses": meses}
    media = (rg["medias"].get(mod) or {}).get("media")
    extra = f" · média do grupo {RL.pct_txt(media)}" if media else ""
    return True, f"ok{extra}", ped


def _resumo_situacoes(venda_ids, mapa_ultimo):
    """Pílulas com a situação do mês das cotas listadas (só leitura do que já foi carregado)."""
    from modulos.tema import linha_chips
    st_ = [((mapa_ultimo.get(v) or {}).get("status") or "").upper() for v in venda_ids]
    disp = sum(1 for s in st_ if s in ("", "ERRO"))
    fila = sum(1 for s in st_ if s in ("PENDENTE", "PROCESSANDO"))
    feito = sum(1 for s in st_ if s in ("SUCESSO", "JA_OFERTADO"))
    erro = sum(1 for s in st_ if s == "ERRO")
    chips = [(f"{len(venda_ids)} cota(s) na lista", "plain"), (f"{disp} disponível(is) para ofertar", "brand"),
             (f"{fila} na fila do robô", "info" if fila else "plain"), (f"{feito} já ofertada(s) no mês", "ok" if feito else "plain")]
    if erro:
        chips.append((f"{erro} com erro — pode reofertar", "danger"))
    linha_chips(chips)


def _enfileirar(supabase, pedidos, mapa_ultimo, simular=False):
    """Grava os pedidos conferidos na fila_automacao (status PENDENTE).
    Se 'Repetir' > 1 mês (ou Ilimitado), cria também a programação em
    lances_programados — o robô põe o pedido dos meses seguintes sozinho."""
    usuario = st.session_state.get('usuario_logado', 'desconhecido')
    inseridos, pulados, programados = 0, 0, 0

    for r, _msg, ped in pedidos:
        vid = int(r['venda_id'])

        # Evita duplicar no mês: se a cota já está na fila, em processamento,
        # ofertada ou já-ofertada NESTE mês, pula (a conferência é mensal).
        pedido_ant = mapa_ultimo.get(vid)
        if not simular and pedido_ant and (pedido_ant.get("status") or "").upper() in (
                "PENDENTE", "PROCESSANDO", "SUCESSO", "JA_OFERTADO"):
            pulados += 1
            continue

        grupo, cota = "", ""
        gc = str(r.get('Grupo/Cota', ''))
        if "/" in gc:
            grupo, cota = gc.split("/", 1)
        grupo, cota = grupo.strip(), cota.strip()

        prog_id = None
        if not simular and ped["meses"] != 1:
            try:
                res = supabase.table("lances_programados").insert({
                    "venda_id": vid, "cliente": r.get('Cliente'), "vendedor": r.get('Vendedor'),
                    "produto": r.get('Produto'), "grupo": grupo, "cota": cota,
                    "tipo_lance": ped["tipo_lance"], "pct_lance": ped["pct_lance"],
                    "pct_embutido": ped["pct_embutido"], "pct_proprio": ped["pct_proprio"],
                    "tipo_reducao": ped["tipo_reducao"], "meses_total": ped["meses"],
                    "criado_por": usuario,
                }).execute()
                prog_id = (res.data or [{}])[0].get("id")
                programados += 1
            except Exception as e:
                st.error(f"Não consegui programar a repetição de {r.get('Cliente')} ({gc}): {e}. "
                         f"O lance deste mês vai assim mesmo.")

        payload = {
            "tipo": "LANCE",
            "venda_id": vid,
            "cliente": r.get('Cliente'),
            "vendedor": r.get('Vendedor'),
            "produto": r.get('Produto'),
            "administradora": "Yamaha",
            "grupo": grupo,
            "cota": cota,
            "tipo_lance": ped["tipo_lance"],
            "pct_lance": ped["pct_lance"],
            "pct_embutido": ped["pct_embutido"],
            "pct_proprio": ped["pct_proprio"],
            "tipo_reducao": ped["tipo_reducao"],
            "status": "PENDENTE",
            "solicitado_por": usuario + (" (teste)" if simular else ""),
        }
        if prog_id:
            payload["programado_id"] = prog_id
        if simular:
            payload["payload"] = {"simular": True}
        try:
            supabase.table("fila_automacao").insert(payload).execute()
            inseridos += 1
        except Exception as e:
            # banco sem a migração 34 (colunas novas): só aceita o Fixo com Reduzir Parcela
            if ("tipo_reducao" in str(e) or "programado_id" in str(e)) and \
                    ped["tipo_reducao"] == "Reduzir Parcela" and not prog_id:
                payload.pop("tipo_reducao", None)
                try:
                    supabase.table("fila_automacao").insert(payload).execute()
                    inseridos += 1
                    continue
                except Exception as e2:
                    e = e2
            st.error(f"Erro ao enfileirar {r.get('Cliente')} ({gc}): {e}")

    if inseridos:
        st.success(f"✅ {inseridos} lance(s) enviados para a fila"
                   + (" em MODO TESTE (só simular)" if simular else "")
                   + (f" · {programados} programado(s) para os próximos meses" if programados else "")
                   + ". O robô vai processar em seguida.")
    if pulados:
        st.warning(f"⚠️ {pulados} cota(s) já tratada(s) neste mês (na fila ou ofertada) foram ignoradas.")
    if inseridos:
        st.rerun()


def _painel_regras(regras, df):
    """Tabela com as regras e as médias de lance dos grupos da lista."""
    grupos = sorted({str(g).strip() for g in df['GRUPO'].tolist() if str(g).strip()},
                    key=lambda x: (len(x), x))
    prod_por_grupo = {str(a).strip(): b for a, b in zip(df['GRUPO'], df['PRODUTO'])}
    with st.expander(f"📊 Regras e médias de lance dos grupos ({len(grupos)})", expanded=False):
        linhas = []
        for g in grupos:
            rg = RL.regra_do_grupo(regras, g, prod_por_grupo.get(g))
            md = rg["medias"]
            linhas.append({
                "Grupo": g, "Produto": rg["produto"].title(),
                "Modalidades liberadas": ", ".join(RL.CURTO[m] for m in RL.MODALIDADES if rg["liberadas"].get(m)),
                "Fixo": RL.pct_txt(rg["fixo_pct"]),
                "2º Fixo": RL.pct_txt(rg["fixo2_pct"]) if rg["liberadas"].get("2º Lance Fixo") else "—",
                "Limitado até": RL.pct_txt(rg["limitado_max_pct"]) if rg["liberadas"].get("Lance Limitado") else "—",
                "Fidelidade até": RL.pct_txt(rg["fidelidade_max_pct"]) if rg["liberadas"].get("Lance Fidelidade") else "—",
                "Embutido permitido": f"{RL.pct_txt(rg['embutido_max_pct'])} ({rg['embutido_fonte']})",
                **{f"Média {RL.CURTO[m]}": (f"{RL.pct_txt(md[m]['media'])} ({md[m]['n']})" if m in md else "—")
                   for m in RL.MODALIDADES},
                "Fonte": rg["fonte_modalidades"],
            })
        st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)
        st.caption(f"Médias = % de lance dos contemplados nas últimas {RL.N_ASSEMBLEIAS_MEDIA} assembleias de cada "
                   "grupo (entre parênteses, quantos contemplados). Modalidades e limites: lidos pelo robô na tela "
                   "'Oferta de Lance' do Newcon; sem leitura, vale o que já apareceu nas contemplações do grupo + "
                   "regra geral. Embutido: tabela do grupo > regra geral do produto.")


def _painel_programados(supabase, is_master, df_vendas_global=None):
    """Lances que se repetem nos próximos meses (com botão de parar)."""
    try:
        progs = (supabase.table("lances_programados").select("*").eq("ativo", True)
                 .order("criado_em", desc=True).execute().data or [])
    except Exception:
        return   # migração 34 ainda não rodada
    if not progs:
        return
    dfp = pd.DataFrame(progs)
    dfp = preencher_cliente(dfp, df_vendas_global) if df_vendas_global is not None else dfp
    dfp = filtrar_fila(dfp, df_vendas_global, eh_adm=is_master)
    if dfp is None or dfp.empty:
        return
    with st.expander(f"📆 Lances programados para os próximos meses ({len(dfp)})", expanded=False):
        dfp["Cliente"] = dfp["cliente"].apply(_nome_curto)
        dfp["Grupo/Cota"] = dfp["grupo"].astype(str) + "/" + dfp["cota"].astype(str)
        dfp["Lance"] = dfp.apply(lambda x: f"{RL.pct_txt(x.get('pct_lance'))} (emb {RL.pct_txt(x.get('pct_embutido'))})", axis=1)
        dfp["Meses"] = dfp.apply(lambda x: f"{int(x.get('meses_feitos') or 0)}/"
                                 + (str(int(x['meses_total'])) if pd.notna(x.get('meses_total')) else "∞"), axis=1)
        dfp["Parar"] = False
        res = st.data_editor(
            dfp[["id", "Parar", "Cliente", "Grupo/Cota", "tipo_lance", "Lance", "tipo_reducao", "Meses", "ultimo_mes"]]
            .rename(columns={"tipo_lance": "Modalidade", "tipo_reducao": "Reduzir", "ultimo_mes": "Último mês"}),
            column_config={"id": None, "Parar": st.column_config.CheckboxColumn("⏹️", help="Marque para parar de repetir")},
            disabled=["Cliente", "Grupo/Cota", "Modalidade", "Lance", "Reduzir", "Meses", "Último mês"],
            hide_index=True, use_container_width=True, key="editor_programados")
        parar = res[res["Parar"] == True]  # noqa: E712
        if len(parar) and st.button(f"⏹️ Parar {len(parar)} programação(ões)", key="bt_parar_prog"):
            for pid in parar["id"].tolist():
                supabase.table("lances_programados").update({"ativo": False}).eq("id", int(pid)).execute()
            st.success("Programação parada. Os lances já enviados não mudam.")
            st.rerun()
        st.caption("O robô põe o lance de cada mês na fila sozinho (se o Newcon recusar porque a oferta "
                   "ainda não abriu, tenta de novo no dia seguinte). Para quando completa os meses, "
                   "quando você para aqui, ou quando a cota é contemplada/cancelada.")


def _painel_status(supabase, is_master, df_vendas_global=None):
    """Mostra os pedidos da fila do mês escolhido (padrão: mês atual)."""
    from modulos.tema import secao; secao("Andamento dos Lances", "📋", "Tudo o que foi pedido ao robô no mês escolhido.")

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
    # Vendedor só vê os pedidos das cotas dele (os dos outros clientes ficam de fora)
    df_f = preencher_cliente(df_f, df_vendas_global)
    df_f = filtrar_fila(df_f, df_vendas_global, eh_adm=is_master)
    if df_f is None or df_f.empty:
        st.info(f"Nenhum lance seu registrado em {sel}.")
        return
    if 'cliente' in df_f.columns:
        df_f['cliente'] = df_f['cliente'].apply(_nome_curto)
    df_f['Situação'] = df_f.apply(lambda x: _rotulo_situacao(x.to_dict()), axis=1)

    def _dt(v):
        return dt_br(v)
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
    st.dataframe(
        df_show, use_container_width=True, hide_index=True,
        column_config={
            "Cliente": st.column_config.TextColumn("Cliente", width="small"),
            "Grupo/Cota": st.column_config.TextColumn("Grupo/Cota", width="small"),
            "Tipo": st.column_config.TextColumn("Tipo", width="small"),
            "Situação": st.column_config.TextColumn("Situação", width="medium"),
            "Mensagem": st.column_config.TextColumn("Mensagem", width="large"),
        },
    )

    st.caption(
        "ℹ️ Os lances só são efetivados quando o **robô do escritório** está ligado. "
        "Enquanto ele não roda, os pedidos ficam com a situação **⏳ Na fila**."
    )
