"""Visão do VENDEDOR: os próprios fechamentos de comissão (somente leitura) e a confirmação de recebimento.

O id do vendedor vem SEMPRE da sessão (login → usuarios.id), nunca de widget ou URL; toda consulta filtra por ele.
O vendedor só enxerga fechamentos ENVIADO, PAGO ou COMPENSADO (rascunho, gerado e cancelado são internos)."""
import pandas as pd
import streamlit as st

import fechamento_vendedor as fv
from utils import formatar_brl_puro

_VISIVEIS = ("ENVIADO", "PAGO", "COMPENSADO")
_ROT = {"ENVIADO": "🟠 A receber", "PAGO": "🟢 Pago", "COMPENSADO": "⚪ Compensado (saldo para o próximo)"}
_ROT_ENV_NEG = "⚪ Sem valor a receber (saldo para o próximo)"      # ENVIADO com total <= 0: ainda não compensado, mas não há o que receber


def _rotulo(f):
    if f["status"] == "ENVIADO" and float(f.get("total") or 0) <= 0:
        return _ROT_ENV_NEG
    return _ROT[f["status"]]


def _brl(v):
    return formatar_brl_puro(v)


def _tabela(itens):
    return pd.DataFrame({
        "Grupo": [str(i.get("grupo") or "") for i in itens], "Cota": [str(i.get("cota") or "") for i in itens],
        "Cliente": [i.get("cliente") or "" for i in itens], "Tipo": [i.get("tipo") for i in itens],
        "Parcela": [i.get("parcela_vendedor") or "" for i in itens],
        "%": [("" if i.get("pct") is None else ("%.2f%%" % float(i["pct"])).replace(".", ",")) for i in itens],
        "Valor": [_brl(i["valor"]) for i in itens], "Referência": [i.get("referencia") or "" for i in itens]})


def render_meus_pagamentos(supabase):
    st.markdown("#### 💳 Meus pagamentos de comissão")
    if fv.diagnostico_tabelas(supabase)[0] != "ok":
        st.info("Seus fechamentos de comissão ainda não estão disponíveis.")
        return
    try:
        from database import _buscar_usuario
        u = _buscar_usuario(supabase, st.session_state.get("usuario_logado")) or {}
    except Exception:
        u = {}
    vid = u.get("id")
    if vid is None:
        st.info("Não encontrei o seu cadastro.")
        return
    try:
        todos = fv._todas(supabase, "pagamentos_vendedor", "*", {"vendedor_id": vid})
    except Exception:
        st.error("Não consegui carregar seus pagamentos agora. Tente de novo em instantes.")
        return
    todos = sorted([f for f in todos if f.get("status") in _VISIVEIS], key=lambda x: x["id"], reverse=True)
    if not todos:
        st.info("Ainda não há fechamento de comissão enviado para você.")
        return

    recebido = sum(float(f.get("valor_pago") or 0) for f in todos if f["status"] == "PAGO")
    a_receber = sum(float(f["total"]) for f in todos if f["status"] == "ENVIADO" and float(f["total"]) > 0)
    m1, m2, m3 = st.columns(3)
    m1.metric("💚 Já recebido", _brl(recebido))
    m2.metric("🟠 A receber", _brl(a_receber))
    m3.metric("Fechamentos", len(todos))
    st.caption("Cada fechamento reúne as comissões do mês, já com bônus e estornos. Confirme o recebimento depois de cair na sua conta.")

    # os itens vêm numa consulta só (do vendedor logado) e são agrupados por fechamento: o Streamlit executa o corpo de
    # TODOS os expanders a cada clique, então uma consulta por fechamento deixaria a tela lenta com o histórico crescendo
    try:
        todos_itens = fv._todas(supabase, "pagamentos_vendedor_itens", "*", {"vendedor_id": vid})
    except Exception:
        todos_itens = None
    por_fech = {}
    for i in todos_itens or []:
        if not i.get("anulado"):
            por_fech.setdefault(i.get("fechamento_id"), []).append(i)

    for f in todos:
        try:
            pago_txt = f" · pago em {pd.to_datetime(f['data_pagamento']).strftime('%d/%m/%Y')}" if f.get("data_pagamento") else ""
        except Exception:
            pago_txt = ""
        with st.expander(f"FV-{int(f['id']):04d} · {f['competencia']} · {_brl(f['total'])} · {_rotulo(f)}{pago_txt}"):
            if todos_itens is None:
                st.error("Não consegui carregar os itens."); continue
            itens = por_fech.get(f["id"], [])
            st.dataframe(_tabela(itens), use_container_width=True, hide_index=True)
            c1, c2 = st.columns(2)
            c1.metric("Total do fechamento", _brl(f["total"]))
            c2.metric("Código de autenticidade", (f.get("hash_conteudo") or "—")[:16])
            st.download_button("📄 Baixar relatório (HTML, imprimir/salvar em PDF)",
                               fv.relatorio_html(f, itens, f.get("snapshot_vendedor") or {}).encode("utf-8"),
                               file_name=f"FV-{int(f['id']):04d}.html", mime="text/html", key=f"mp_dl_{f['id']}")
            if f["status"] == "PAGO":
                if f.get("confirmado_vendedor_em"):
                    st.success(f"✅ Recebimento confirmado por você em {fv.data_br(f['confirmado_vendedor_em'])}.")
                else:
                    forma = f" via {f['forma_pagamento']}" if f.get("forma_pagamento") else ""
                    st.info(f"Pagamento de {_brl(f.get('valor_pago') or f['total'])}{forma} registrado pela Consorbens.")
                    ok = st.checkbox("Confirmo que recebi este valor", key=f"mp_ck_{f['id']}")
                    if st.button("Confirmar recebimento", key=f"mp_bt_{f['id']}", disabled=not ok):
                        try:
                            fv.confirmar_recebimento(supabase, f["id"], vid, str(st.session_state.get("usuario_logado")))
                            st.rerun()
                        except fv.ErroFechamento as e:
                            st.error(str(e))
                        except Exception:
                            st.error("Não consegui confirmar agora. Tente novamente.")
