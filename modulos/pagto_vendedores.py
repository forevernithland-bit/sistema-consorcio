"""Aba "Pagamento a Vendedores" (dentro de Baixar Parcelas) — só Master.

Fluxo: montar rascunho (itens vindos das baixas reais) → travar (gera relatório + código) → marcar enviado →
registrar pagamento (ou compensar saldo negativo) → histórico por vendedor. Regras e gravação em fechamento_vendedor.py."""
import calendar
from datetime import date, datetime

import pandas as pd
import streamlit as st

import comissao_vendedor as cv
import fechamento_vendedor as fv
from escopo import eh_master
from utils import formatar_brl_puro
from ui_valores import input_valor

_MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
_COR = {"RASCUNHO": "🟡", "GERADO": "🔵", "ENVIADO": "🟠", "PAGO": "🟢", "COMPENSADO": "⚪", "CANCELADO": "⚫"}
_ROT = {"RASCUNHO": "Rascunho", "GERADO": "Gerado (travado)", "ENVIADO": "Enviado — a pagar", "PAGO": "PAGO",
        "COMPENSADO": "Compensado", "CANCELADO": "Cancelado"}


def _brl(v):
    return formatar_brl_puro(v)


def _conf_vendedor(f):
    """Coluna do histórico: o vendedor confirmou que recebeu? (só faz sentido em fechamento PAGO)"""
    if f.get("confirmado_vendedor_em"):
        return "✅ " + fv.data_br(f["confirmado_vendedor_em"])
    return "⏳ aguardando" if f.get("status") == "PAGO" else ""


def _todas(sb, tabela, colunas="*", filtros=None):
    return fv._todas(sb, tabela, colunas, filtros)


def _usuarios_vendedores(sb):
    try:
        us = _todas(sb, "usuarios", "id,nome,perfil,ativo,cnpj,razao_social,pix,regime")
    except Exception:
        us = _todas(sb, "usuarios", "id,nome,perfil,ativo")
    return us


def _so_master():
    """Reconfere o perfil no instante da ação (além de a tela já esconder os botões de quem não é Master)."""
    if not eh_master():
        raise fv.ErroFechamento("Somente o administrador pode fazer esta ação.")


def _ator():
    return str(st.session_state.get("usuario_logado") or "?")


def _tabela_itens(itens):
    return pd.DataFrame({
        "Grupo": [str(i.get("grupo") or "") for i in itens], "Cota": [str(i.get("cota") or "") for i in itens],
        "Cliente": [i.get("cliente") or "" for i in itens], "Administradora": [i.get("administradora") or "" for i in itens],
        "Tipo": [i.get("tipo") for i in itens], "Parc. adm.": [i.get("parcela_adm") or "" for i in itens],
        "Parcela vend.": [i.get("parcela_vendedor") or "" for i in itens],
        "%": [("" if i.get("pct") is None else ("%.2f%%" % float(i["pct"])).replace(".", ",")) for i in itens],
        "Valor": [_brl(i["valor"]) for i in itens], "Referência": [i.get("referencia") or "" for i in itens],
    })


def _csv_seguro(df):
    """Planilha aberta no Excel executa texto que começa com = + - @ : prefixa com apóstrofo nos campos de texto livre."""
    df = df.copy()
    for c in ("Cliente", "Referência", "Administradora"):
        df[c] = df[c].apply(lambda v: ("'" + v) if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v)
    return df


def _acoes(sb, f, vendedor_info):
    fid, status = f["id"], f["status"]
    itens = fv._itens(sb, fid)
    st.dataframe(_tabela_itens(itens), use_container_width=True, hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", _brl(f["total"]))
    c2.metric("Itens", len(itens))
    c3.metric("Código", (f.get("hash_conteudo") or "—")[:12])
    cab = {**f}
    integro = fv.verificar_integridade(sb, f, itens)
    if not integro:
        st.error("⛔ Os itens gravados NÃO conferem com o código (hash) do fechamento — não pague nem envie. "
                 "Avise o responsável pelo sistema.")
    # o relatório usa os dados do vendedor congelados na geração (não o cadastro de hoje)
    html = fv.relatorio_html(cab, itens, f.get("snapshot_vendedor") or vendedor_info)
    d1, d2, _ = st.columns([1, 1, 2])
    d1.download_button("📄 Relatório (HTML p/ imprimir/PDF)", html.encode("utf-8"), file_name=f"FV-{int(fid):04d}.html",
                       mime="text/html", key=f"pv_dl_h_{fid}", use_container_width=True)
    d2.download_button("📊 Planilha (CSV)", _csv_seguro(_tabela_itens(itens)).to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name=f"FV-{int(fid):04d}.csv", mime="text/csv", key=f"pv_dl_c_{fid}", use_container_width=True)
    if not eh_master():
        return
    st.divider()
    # a confirmação vale só para a etapa atual (chave inclui o status): cada passo pede a conferência de novo
    ok_ck = st.checkbox("Confirmo que conferi este fechamento", key=f"pv_ck_{fid}_{status}")
    if not integro:
        ok_ck = False
    try:
        if status == "RASCUNHO":
            b1, b2 = st.columns(2)
            if b1.button("🔒 Travar e gerar relatório", key=f"pv_tr_{fid}", type="primary", disabled=not ok_ck, use_container_width=True):
                _so_master(); fv.travar(sb, fid, _ator()); st.rerun()
            _cancelar_ui(sb, fid, b2)
        elif status == "GERADO":
            b1, b2 = st.columns(2)
            st.caption("Baixe o relatório acima e envie ao vendedor; depois clique em “Marcar como enviado”.")
            if b1.button("📨 Marcar como enviado", key=f"pv_en_{fid}", type="primary", disabled=not ok_ck, use_container_width=True):
                _so_master(); fv.enviar(sb, fid, _ator()); st.rerun()
            _cancelar_ui(sb, fid, b2)
        elif status == "ENVIADO":
            total = float(f["total"])
            if total > 0:
                st.markdown("**Registrar pagamento**")
                p1, p2 = st.columns(2)
                dpag = p1.date_input("Data do pagamento", value=date.today(), format="DD/MM/YYYY", key=f"pv_dp_{fid}")
                forma = p2.selectbox("Forma", ["Pix", "Transferência", "Outro"], key=f"pv_fm_{fid}")
                p3, p4 = st.columns(2)
                valor = input_valor("Valor pago (R$)", value=total, key=f"pv_vp_{fid}")
                e2e = p4.text_input("ID da transação Pix (E2E)", key=f"pv_e2e_{fid}", help="Opcional, mas evita reaproveitar o mesmo comprovante.")
                obs = st.text_input("Observação", key=f"pv_ob_{fid}")
                if st.button("✅ Marcar como PAGO", key=f"pv_pg_{fid}", type="primary", disabled=not ok_ck):
                    _so_master(); fv.pagar(sb, fid, _ator(), dpag, forma, valor, e2e, obs); st.rerun()
            else:
                st.info("Total zero ou negativo (estorno maior que a comissão): não há o que pagar. "
                        "Compense — o saldo negativo entra automaticamente no próximo fechamento.")
                if st.button("⚪ Compensar", key=f"pv_cp_{fid}", disabled=not ok_ck):
                    _so_master(); fv.compensar(sb, fid, _ator()); st.rerun()
            _cancelar_ui(sb, fid, st.container())
    except fv.ErroFechamento as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Não foi possível concluir: {str(e)[:200]}")


def _cancelar_ui(sb, fid, container):
    with container:
        with st.popover("Cancelar fechamento", use_container_width=True):
            mot = st.text_input("Motivo (obrigatório)", key=f"pv_mc_{fid}")
            if st.button("Confirmar cancelamento", key=f"pv_cc_{fid}"):
                try:
                    _so_master(); fv.cancelar(sb, fid, _ator(), mot); st.rerun()
                except fv.ErroFechamento as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Não foi possível cancelar: {str(e)[:200]}")


def render_pagamento_vendedores(supabase, df_vendas, df_admin, cfg, status_dict):
    st.markdown("#### 👥 Pagamento de comissão aos vendedores")
    if not eh_master():
        st.warning("Somente o administrador acessa esta área.")
        return
    diag, msg_diag = fv.diagnostico_tabelas(supabase)
    if diag == "ausente":
        st.info("Esta função ainda não foi ativada. Rode uma vez o arquivo `migracoes/30_pagamento_vendedores.sql` "
                "no SQL Editor do Supabase.")
        return
    if diag != "ok":
        st.error(f"Não consegui acessar as tabelas de fechamento (conexão/permissão?): {msg_diag}")
        return

    usuarios = _usuarios_vendedores(supabase)
    vendedores = sorted([u for u in usuarios if str(u.get("perfil")) == "Vendedor" and u.get("ativo") is not False
                         and cv.eh_terceiro(u.get("nome"))],      # sócios/Consorbens/Particular não recebem comissão de vendedor
                        key=lambda u: cv.norm(u.get("nome")))
    abas = st.tabs(["🧾 Gerar fechamento", "📂 Em aberto", "📚 Histórico por vendedor"])

    # ------------------------------------------------------------ 1. gerar
    with abas[0]:
        st.caption("A comissão entra aqui **depois** que a baixa da administradora (NF importada ou baixa manual) existe. "
                   "O fechamento fica congelado: se algo mudar depois, vira ajuste no próximo.")
        if not vendedores:
            st.info("Nenhum usuário com perfil Vendedor ativo.")
        else:
            c1, c2 = st.columns([2, 1])
            vend = c1.selectbox("Vendedor", vendedores, format_func=lambda u: u["nome"], key="pv_vend")
            hoje_d = date.today()
            meses_op = []
            for k in range(13):
                t = hoje_d.year * 12 + (hoje_d.month - 1) - k
                meses_op.append((t // 12, t % 12 + 1))
            mes_sel = c2.selectbox("Mês de recebimento", meses_op, index=0, key="pv_mes",
                                   format_func=lambda m: f"{_MESES[m[1]]}/{m[0]}",
                                   help="Fechamento mensal: entram todas as baixas da administradora recebidas até o fim deste mês "
                                        "(inclusive as de meses anteriores que ainda não foram pagas).")
            corte = date(mes_sel[0], mes_sel[1], calendar.monthrange(mes_sel[0], mes_sel[1])[1])
            if st.button("🔎 Montar rascunho", type="primary", key="pv_montar"):
                pend = fv.pendencias_bloqueantes(df_vendas, usuarios, vend["nome"])
                try:
                    cps = _todas(supabase, "comissoes_pagas")
                    chaves_todas = fv.chaves_ativas(supabase)               # de todos os vendedores
                    chaves = fv.chaves_ativas(supabase, vend["id"])
                    saldo = fv.saldos_a_carregar(supabase, vend["id"])
                    leitura_ok = True
                except Exception as e:
                    st.error(f"Não consegui ler os dados: {str(e)[:150]}"); cps, chaves, chaves_todas, saldo = [], set(), set(), []
                    leitura_ok = False
                if leitura_ok:
                    orfas = []
                    itens, aguard = fv.montar_itens(df_vendas, df_admin, cfg, status_dict, cps, vend["nome"], corte, chaves, saldo, orfas)
                    # item que já está no fechamento de OUTRO vendedor (cota trocou de vendedor): não entra, e avisa
                    de_outro = [i for i in itens if i["chave_item"] in (chaves_todas - chaves)]
                    itens = [i for i in itens if i not in de_outro]
                    avisos = ([f"{len(de_outro)} item(ns) já constam em fechamento de OUTRO vendedor e ficaram de fora "
                               f"({', '.join(sorted({str(i['grupo']) + '/' + str(i['cota']) for i in de_outro})[:5])}) — "
                               "confira o vendedor da cota."] if de_outro else [])
                    if orfas:
                        avisos.append(f"{len(orfas)} baixa(s) recebida(s) não geraram item (parcela fora da previsão): "
                                      + "; ".join(f"{o['grupo']}/{o['cota']} parc. {o['parcela'] or '?'}" for o in orfas[:6])
                                      + (" …" if len(orfas) > 6 else "") + " — confira a cota (cancelada? regra?).")
                    st.session_state["pv_prev"] = {"vend_id": vend["id"], "corte": str(corte), "itens": itens,
                                                   "aguard": aguard, "pend": pend, "avisos": avisos}
                else:
                    st.session_state.pop("pv_prev", None)
            prev = st.session_state.get("pv_prev")
            if prev and prev["vend_id"] == vend["id"] and prev["corte"] != str(corte):
                st.info("O mês mudou desde a última montagem — clique em “Montar rascunho” de novo.")
            elif prev and prev["vend_id"] == vend["id"]:
                for p in prev["pend"]:
                    st.error("⛔ " + p)
                for a in prev.get("avisos", []):
                    st.warning("⚠️ " + a)
                itens = prev["itens"]
                if not itens:
                    st.info("Nada novo para fechar neste mês.")
                else:
                    total = fv.total_itens(itens)
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Itens", len(itens)); m2.metric("Total do fechamento", _brl(total))
                    m3.metric("Estornos/abatimentos", _brl(sum(i["valor"] for i in itens if i["tipo"] in ("ESTORNO", "SALDO"))))
                    st.dataframe(_tabela_itens(itens), use_container_width=True, hide_index=True)
                    if total <= 0:
                        st.warning("Total zero ou negativo: o fechamento será “compensado” e o saldo passa para o próximo.")
                    if prev["pend"]:
                        st.warning("Resolva as pendências acima antes de salvar o rascunho.")
                    elif st.button("💾 Salvar rascunho", key="pv_salvar", type="primary"):
                        try:
                            snap = {k: vend.get(k) for k in ("nome", "cnpj", "razao_social", "pix", "regime")}
                            fid = fv.criar_rascunho(supabase, vend, itens, date.fromisoformat(prev["corte"]), _ator(), snap,
                                                    {k: v for k, v in cv.regra(cfg).items()})
                            st.session_state.pop("pv_prev", None)
                            st.success(f"Rascunho FV-{int(fid):04d} salvo. Confira na aba “Em aberto”.")
                        except fv.ErroFechamento as e:
                            st.error(str(e))
                if prev["aguard"]:
                    with st.expander(f"⏳ {len(prev['aguard'])} item(ns) ainda sem baixa até o fim do mês (não entram)"):
                        st.dataframe(pd.DataFrame({
                            "Grupo/Cota": [f"{a['grupo']}/{a['cota']}" for a in prev["aguard"]],
                            "Cliente": [a.get("cliente") for a in prev["aguard"]], "Tipo": [a["tipo"] for a in prev["aguard"]],
                            "Valor previsto": [_brl(a["valor"]) for a in prev["aguard"]], "Motivo": [a["motivo"] for a in prev["aguard"]]}),
                            use_container_width=True, hide_index=True)

    # ------------------------------------------------------------ 2. em aberto
    with abas[1]:
        try:
            abertos = [f for f in _todas(supabase, "pagamentos_vendedor") if f["status"] in fv.STATUS_ABERTOS]
        except Exception as e:
            st.error(f"Não consegui ler os fechamentos: {str(e)[:150]}"); abertos = []
        if not abertos:
            st.info("Nenhum fechamento em aberto.")
        for f in sorted(abertos, key=lambda x: x["id"], reverse=True):
            vinfo = next((u for u in usuarios if u["id"] == f["vendedor_id"]), {})
            with st.expander(f"{_COR[f['status']]} FV-{int(f['id']):04d} · {f['vendedor_nome']} · {f['competencia']} · "
                             f"{_brl(f['total'])} · {_ROT[f['status']]}"):
                _acoes(supabase, f, vinfo)

    # ------------------------------------------------------------ 3. histórico
    with abas[2]:
        opcoes = [None] + vendedores
        quem = st.selectbox("Vendedor", opcoes, format_func=lambda u: "Todos" if u is None else u["nome"], key="pv_hist_v")
        try:
            todos = _todas(supabase, "pagamentos_vendedor")
        except Exception as e:
            st.error(f"Não consegui ler o histórico: {str(e)[:150]}"); todos = []
        if quem is not None:
            todos = [f for f in todos if f["vendedor_id"] == quem["id"]]
        if not todos:
            st.info("Sem fechamentos.")
        else:
            pago = sum(float(f["valor_pago"] or 0) for f in todos if f["status"] == "PAGO")
            pendente = sum(float(f["total"]) for f in todos if f["status"] in ("GERADO", "ENVIADO"))
            m1, m2, m3 = st.columns(3)
            m1.metric("💚 Total pago", _brl(pago)); m2.metric("🟠 A pagar (gerado/enviado)", _brl(pendente))
            m3.metric("Fechamentos", len(todos))
            todos = sorted(todos, key=lambda x: x["id"], reverse=True)
            st.dataframe(pd.DataFrame({
                "Nº": [f"FV-{int(f['id']):04d}" for f in todos], "Vendedor": [f["vendedor_nome"] for f in todos],
                "Competência": [f["competencia"] for f in todos], "Status": [f"{_COR[f['status']]} {_ROT[f['status']]}" for f in todos],
                "Total": [_brl(f["total"]) for f in todos], "Gerado em": [str(f.get("gerado_em") or "")[:10] for f in todos],
                "Enviado em": [str(f.get("enviado_em") or "")[:10] for f in todos],
                "Pago em": [str(f.get("data_pagamento") or "") for f in todos],
                "Valor pago": [(_brl(f["valor_pago"]) if f.get("valor_pago") is not None else "") for f in todos],
                "Forma": [f.get("forma_pagamento") or "" for f in todos], "Por": [f.get("pago_por") or f.get("gerado_por") or "" for f in todos],
                "Confirmado pelo vendedor": [_conf_vendedor(f) for f in todos],
            }), use_container_width=True, hide_index=True)
            sel = st.selectbox("Ver detalhe do fechamento", [None] + todos,
                               format_func=lambda f: "—" if f is None else f"FV-{int(f['id']):04d} · {f['vendedor_nome']} · {f['competencia']}",
                               key="pv_hist_det")
            if sel is not None:
                itens = fv._itens(supabase, sel["id"], incluir_anulados=True)
                st.dataframe(_tabela_itens(itens), use_container_width=True, hide_index=True)
                logs = _todas(supabase, "pagamentos_vendedor_log", "*", {"fechamento_id": sel["id"]})
                if logs:
                    with st.expander("Histórico de ações (quem fez o quê)"):
                        st.dataframe(pd.DataFrame({"Quando": [str(l.get("em"))[:19].replace("T", " ") for l in logs],
                                                   "Ação": [l["acao"] for l in logs], "De": [l.get("status_de") or "" for l in logs],
                                                   "Para": [l.get("status_para") or "" for l in logs], "Quem": [l.get("ator") for l in logs]}),
                                     use_container_width=True, hide_index=True)
