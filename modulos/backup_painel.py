"""Configurações → 🛟 Backup e Lixeira (só administrador).

- Último backup feito pelo robô do escritório (tabela backups_erp).
- "Pedir backup ao robô agora": enfileira BACKUP_ERP (o robô grava a pasta
  datada em G:\\Meu Drive\\CLODE\\BACKUP_ERP).
- "Baixar backup agora (.zip)": gera na hora, direto do banco, um ZIP com
  JSON + CSV de todas as tabelas (sem senhas).
- Lixeira: o que foi apagado (cópia guardada pela migração 32) com botão
  Restaurar; e as últimas alterações registradas.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

import auditoria
import backup_erp
from utils import dt_br


def _ultimo(sb):
    try:
        return backup_erp.ultimo_backup(sb), None
    except Exception as e:
        return None, e


def _pedido_pendente(sb):
    try:
        r = (sb.table("fila_automacao").select("id,status,criado_em").eq("tipo", "BACKUP_ERP")
             .in_("status", ["PENDENTE", "PROCESSANDO"]).limit(1).execute().data or [])
        return r[0] if r else None
    except Exception:
        return None


def render_backup_lixeira(supabase):
    st.markdown("#### 🛟 Backup dos dados")
    ult, erro = _ultimo(supabase)
    if erro is not None:
        st.info("O registro de backups ainda não está ativado — rode a **migração 32** "
                "(`migracoes/32_auditoria_backup.sql`) no SQL Editor do Supabase.")
    elif not ult:
        st.warning("Nenhum backup registrado ainda. O robô do escritório faz um por dia (01:30); "
                   "use o botão abaixo para pedir um agora.")
    else:
        quando = dt_br(ult.get("criado_em")) or str(ult.get("criado_em"))
        (st.success if ult.get("ok") else st.error)(
            f"**Último backup:** {quando} — {'OK' if ult.get('ok') else 'COM ERRO'} · "
            f"{ult.get('total_linhas') or 0} linhas · origem {ult.get('origem') or '—'}")
        try:
            idade_h = (pd.Timestamp.now(tz="UTC") - pd.to_datetime(ult.get("criado_em"), utc=True)).total_seconds() / 3600
            if idade_h > 36:
                st.warning(f"⚠️ O último backup tem {idade_h / 24:.1f} dia(s). Confira se o robô do escritório está ligado.")
        except Exception:
            pass
        with st.expander("Detalhes do último backup"):
            st.caption(ult.get("mensagem") or "")
            tabs = ult.get("tabelas") or {}
            if tabs:
                st.dataframe(pd.DataFrame(sorted(tabs.items()), columns=["Tabela", "Linhas"]),
                             hide_index=True, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        pend = _pedido_pendente(supabase)
        if st.button("🤖 Pedir backup ao robô agora", use_container_width=True, disabled=bool(pend),
                     help="O robô do escritório grava a cópia na pasta BACKUP_ERP do Google Drive."):
            try:
                if _pedido_pendente(supabase):          # alguém já pediu (outra aba/usuário): não duplica
                    raise RuntimeError("já há um backup na fila")
                supabase.table("fila_automacao").insert({
                    "tipo": "BACKUP_ERP", "status": "PENDENTE", "prioridade": 20,
                    "solicitado_por": st.session_state.get("usuario_logado") or "erp", "payload": {}}).execute()
                st.success("Pedido enviado! Com o robô ligado, o backup fica pronto em instantes.")
            except Exception as e:
                st.error(f"Não consegui enviar o pedido ao robô: {e}")
        if pend:
            st.caption(f"⏳ Já há um backup na fila ({pend.get('status')}).")
    with c2:
        if st.button("⬇️ Baixar backup agora (.zip)", use_container_width=True,
                     help="Gera agora, direto do banco, um ZIP com todas as tabelas (JSON + CSV, sem senhas)."):
            with st.spinner("Lendo todas as tabelas e montando o ZIP…"):
                try:
                    dados, man = backup_erp.gerar_zip(supabase, origem=f"ERP:{st.session_state.get('usuario_logado')}")
                    st.session_state["_bk_zip"] = (dados, man, datetime.now().strftime("%Y-%m-%d_%H%M"))
                except Exception as e:
                    st.error(f"Não consegui gerar o backup: {e}")
        if st.session_state.get("_bk_zip"):
            dados, man, carimbo = st.session_state["_bk_zip"]
            st.download_button(f"💾 Salvar backup_erp_{carimbo}.zip ({man.get('total_linhas', 0)} linhas)",
                               dados, file_name=f"backup_erp_{carimbo}.zip", mime="application/zip",
                               use_container_width=True, key="bk_zip_dl")
            if man.get("erros"):
                faltou = {t: e for t, e in man["erros"].items() if e != "ausente"}
                if faltou:
                    st.error(f"Algumas tabelas não puderam ser lidas: {faltou}")

    st.divider()
    st.markdown("#### 🗑️ Lixeira (o que foi apagado)")
    st.caption("Toda linha apagada de vendas, clientes, comissões, status, regras etc. fica guardada aqui "
               "(migração 32) — inclusive o que o robô ou alguém apagar direto no banco. Dá para restaurar.")
    exp = st.expander("Abrir a lixeira", key="bk_lixeira_exp", on_change="rerun")
    if exp.open is not False:
        with exp:
            _render_lixeira(supabase)
    exp2 = st.expander("Últimas alterações registradas", key="bk_alter_exp", on_change="rerun")
    if exp2.open is not False:
        with exp2:
            _render_alteracoes(supabase)


def _resumo(d):
    d = d or {}
    for campos in (("NOME", "GRUPO", "COTA"), ("Nome",), ("cliente", "grupo", "cota", "parcela"),
                   ("Chave_Unica", "Status"), ("Administradora", "Produto"), ("descricao",), ("tipo", "cliente")):
        partes = [str(d.get(c)) for c in campos if d.get(c) not in (None, "")]
        if partes:
            return " · ".join(partes)
    return ", ".join(f"{k}={v}" for k, v in list(d.items())[:4])


def _render_lixeira(sb):
    try:
        regs = auditoria.listar(sb, "DELETE")
    except Exception as e:
        st.error(f"Não consegui ler a lixeira: {e}")
        return
    if regs is None:
        st.info("A lixeira ainda não está ativada — rode a **migração 32** no Supabase.")
        return
    if not regs:
        st.success("Lixeira vazia — nada foi apagado.")
        return
    # o gatilho do banco (origem db) e a tela (origem app, com quem/motivo) registram a mesma
    # exclusão: mostra uma linha só, com o motivo quando houver
    motivos = {}
    for r in regs:
        if r.get("origem") == "app":
            motivos[(r.get("tabela"), str(r.get("registro_id")))] = (r.get("quem"), r.get("motivo"))
    vistos, linhas = set(), []
    for r in regs:
        k = (r.get("tabela"), str(r.get("registro_id")), r.get("origem"))
        chave = (r.get("tabela"), str(r.get("registro_id")))
        if r.get("origem") == "app" and any(x.get("origem") == "db" and (x.get("tabela"), str(x.get("registro_id"))) == chave for x in regs):
            continue
        if k in vistos:
            continue
        vistos.add(k)
        quem, motivo = motivos.get(chave, (r.get("quem"), r.get("motivo")))
        linhas.append({"_id": r["id"], "Apagado em": dt_br(r.get("criado_em")), "Tabela": r.get("tabela"),
                       "ID": r.get("registro_id"), "O quê": _resumo(r.get("dados")), "Quem": quem or "",
                       "Motivo": motivo or "", "Restaurado": dt_br(r.get("restaurado_em")) if r.get("restaurado_em") else ""})
    df = pd.DataFrame(linhas)
    st.dataframe(df.drop(columns=["_id"]), hide_index=True, use_container_width=True)
    restauraveis = [l for l in linhas if not l["Restaurado"] and l["Tabela"] in auditoria.RESTAURAVEIS]
    if not restauraveis:
        return
    opcoes = {f"#{l['_id']} · {l['Tabela']} {l['ID']} · {l['O quê']} ({l['Apagado em']})": l["_id"] for l in restauraveis}
    sel = st.selectbox("Restaurar qual?", [""] + list(opcoes), key="bk_rest_sel")
    if sel:
        conf = st.checkbox("Confirmo recolocar esta linha no sistema", key="bk_rest_conf")
        if st.button("♻️ Restaurar", type="primary", disabled=not conf, key="bk_rest_btn"):
            reg = next(r for r in regs if r["id"] == opcoes[sel])
            try:
                ok, msg = auditoria.restaurar(sb, reg)
                if ok:
                    from database import carregar_dados_iniciais
                    carregar_dados_iniciais.clear()
                    try:
                        from modulos.importar_comissoes import _invalidar_caches_comissoes
                        _invalidar_caches_comissoes()
                    except Exception:
                        pass
                    st.success(msg)
                else:
                    st.warning(msg)
            except Exception as e:
                st.error(f"Não consegui restaurar: {e}")


def _render_alteracoes(sb):
    try:
        regs = auditoria.listar(sb, "UPDATE", limite=200)
    except Exception as e:
        st.error(f"Não consegui ler as alterações: {e}")
        return
    if regs is None:
        st.info("Ainda não ativado — rode a **migração 32** no Supabase.")
        return
    if not regs:
        st.caption("Nenhuma alteração registrada ainda.")
        return
    linhas = []
    for r in regs:
        antes, depois = r.get("dados") or {}, r.get("dados_novos") or {}
        mud = [f"{k}: {antes.get(k)} → {depois.get(k)}" for k in depois if antes.get(k) != depois.get(k)]
        linhas.append({"Quando": dt_br(r.get("criado_em")), "Tabela": r.get("tabela"), "ID": r.get("registro_id"),
                       "O quê": _resumo(antes), "Mudou": "; ".join(mud)[:300]})
    st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)
