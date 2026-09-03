"""
Painel do Robô — botões pra disparar as tarefas pré-programadas do robô único
(worker_consorbens.py, que roda no PC do escritório). Cada botão grava uma
linha em `fila_automacao`; o robô pega e executa. A tabela embaixo mostra o
que já rodou (✅ / ❌ / 🔄 / ⏳) com a mensagem de retorno.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone

LIMITE_SERVER_SEG = 90

# botão -> (tipo na fila, descrição curta, prioridade, payload)
TAREFAS = [
    ("🃏 Atualizar grupos com vaga (+ assembleias)", "COLETA_GRUPOS", 50, {},
     "Varre os planos recentes no Newcon, pega os grupos com vaga e, ao terminar, "
     "encadeia sozinho a coleta das assembleias (lance médio)."),
    ("📊 Só atualizar média de lances", "COLETA_ASSEMBLEIAS", 50, {},
     "Relê o resultado das últimas assembleias dos grupos com vaga — atualiza o "
     "lance livre médio sem refazer a varredura de grupos."),
    ("🏢 Atualizar cartas Anglo (site)", "IMPORTA_ANGLO", 55, {},
     "Baixa o estoque da Anglo e substitui as cartas 'Anglo Consórcios' no site. "
     "Não toca em outros fornecedores."),
    ("📥 Baixar tabelas Yamaha (Gmail)", "BAIXAR_GMAIL_YAMAHA", 55, {},
     "Puxa o e-mail mais recente 'Tabelas Yamaha' e salva os anexos em "
     "CONSORBENS\\Tabelas\\YAMAHA."),
    ("📥 Baixar Guia de Oportunidades Itaú (Gmail)", "BAIXAR_GMAIL_ITAU", 55, {},
     "Puxa o e-mail 'GUIA DE OPORTUNIDADES' do Itaú e salva os anexos em "
     "CONSORBENS\\Tabelas\\ITAU."),
    ("💰 Baixar financeiro Yamaha (Comissões Pagas)", "RELATORIO_COMISSAO", 60, {},
     "Baixa no Newcon o relatório de Comissões Pagas da Yamaha do mês atual "
     "(PDF em Downloads\\Comissoes Yamaha)."),
]

_STATUS_EMOJI = {
    "PENDENTE": "⏳ Na fila", "PROCESSANDO": "🔄 Rodando",
    "SUCESSO": "✅ Concluído", "ERRO": "❌ Erro",
    "JA_OFERTADO": "☑️ Já feito", "JA_PAGO": "☑️ Já pago", "SEM_BOLETO": "—",
}
_TIPOS_PAINEL = [t[1] for t in TAREFAS]


def _robo_online(sb) -> bool:
    try:
        r = sb.table("robo_status").select("atualizado_em").eq("id", 1).execute()
        if not r.data:
            return False
        dt = pd.to_datetime(r.data[0]["atualizado_em"], utc=True)
        return (datetime.now(timezone.utc) - dt.to_pydatetime()).total_seconds() <= LIMITE_SERVER_SEG
    except Exception:
        return False


def _ja_na_fila(sb, tipo) -> bool:
    try:
        r = (sb.table("fila_automacao").select("id")
             .eq("tipo", tipo).in_("status", ["PENDENTE", "PROCESSANDO"])
             .limit(1).execute())
        return bool(r.data)
    except Exception:
        return False


def _enfileirar(sb, tipo, prioridade, payload, usuario):
    sb.table("fila_automacao").insert({
        "tipo": tipo, "status": "PENDENTE", "prioridade": prioridade,
        "payload": payload or {}, "solicitado_por": f"PAINEL:{usuario or 'ERP'}",
    }).execute()


def _dt(v):
    try:
        return pd.to_datetime(v).strftime("%d/%m %H:%M")
    except Exception:
        return ""


def render_robo_painel(supabase):
    st.markdown("### 🤖 Painel do Robô")
    online = _robo_online(supabase)
    cor, txt = ("#22c55e", "🟢 Robô ligado — as tarefas rodam em segundos") if online \
        else ("#ef4444", "🔴 Robô desligado — as tarefas ficam na fila até ele ligar")
    st.markdown(
        f"<div style='display:inline-block;padding:6px 14px;border-radius:999px;"
        f"background:{cor}22;color:{cor};font-weight:700;font-size:13px'>{txt}</div>",
        unsafe_allow_html=True,
    )
    st.caption("Clique num botão pra pedir a tarefa. O robô do escritório executa e "
               "o resultado aparece na tabela abaixo (atualize a página pra ver).")

    usuario = (st.session_state.get("usuario_logado") or {})
    usuario = usuario.get("nome") if isinstance(usuario, dict) else str(usuario or "")

    cols = st.columns(2)
    for i, (rotulo, tipo, prio, payload, ajuda) in enumerate(TAREFAS):
        with cols[i % 2]:
            na_fila = _ja_na_fila(supabase, tipo)
            if st.button(rotulo, use_container_width=True, disabled=na_fila,
                         help=ajuda, key=f"robo_bt_{tipo}"):
                try:
                    _enfileirar(supabase, tipo, prio, payload, usuario)
                    st.toast(f"Pedido enviado: {rotulo}", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Não consegui enfileirar: {e}")
            if na_fila:
                st.caption("⏳ já está na fila / rodando")

    st.divider()
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Atualizar", use_container_width=True):
            st.rerun()
    with c2:
        st.caption("Últimas execuções das tarefas do painel:")

    try:
        res = (supabase.table("fila_automacao")
               .select("tipo,status,mensagem,solicitado_por,criado_em,concluido_em")
               .in_("tipo", _TIPOS_PAINEL)
               .order("criado_em", desc=True).limit(20).execute())
        rows = res.data or []
    except Exception as e:
        st.error(f"Não consegui ler a fila: {e}")
        return

    if not rows:
        st.info("Nenhuma tarefa do painel foi disparada ainda.")
        return

    df = pd.DataFrame([{
        "Tarefa": r.get("tipo", ""),
        "Situação": _STATUS_EMOJI.get((r.get("status") or "").upper(), r.get("status") or "—"),
        "Mensagem / erro": r.get("mensagem") or "",
        "Pedido em": _dt(r.get("criado_em")),
        "Concluído": _dt(r.get("concluido_em")),
        "Por": (r.get("solicitado_por") or "").replace("PAINEL:", ""),
    } for r in rows])
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "Tarefa": st.column_config.TextColumn("Tarefa", width="medium"),
            "Situação": st.column_config.TextColumn("Situação", width="small"),
            "Mensagem / erro": st.column_config.TextColumn("Mensagem / erro", width="large"),
        },
    )
