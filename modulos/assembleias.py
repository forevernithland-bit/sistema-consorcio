import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
import urllib.parse

def render_assembleias(supabase, df_ass):
    st.markdown("### 📅 Cronograma de Assembleias")
    
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    col_m, col_a, col_btn = st.columns([1, 1, 3])
    meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    hoje = datetime.today()
    
    with col_m: m_sel = st.selectbox("Mês", meses_pt, index=hoje.month - 1)
    with col_a: a_sel = st.selectbox("Ano", range(hoje.year - 1, hoje.year + 3), index=1)
    num_m = meses_pt.index(m_sel) + 1
    
    eventos_mes = {}
    if not df_ass.empty:
        df_mes_atual = df_ass[(df_ass['data_dt'].dt.month == num_m) & (df_ass['data_dt'].dt.year == a_sel)]
        for _, r in df_mes_atual.iterrows():
            dia = r['data_dt'].day
            if dia not in eventos_mes: eventos_mes[dia] = []
            eventos_mes[dia].append(r['descricao'])

    with col_btn:
        st.write("")
        amanha = (hoje + timedelta(days=1)).date()
        ev_amanha = df_ass[df_ass['data_dt'].dt.date == amanha]['descricao'].tolist() if not df_ass.empty else []
        if ev_amanha:
            msg = f"Olá Sócios! Segue lembrete das assembleias de amanhã ({amanha.strftime('%d/%m')}): " + ", ".join(ev_amanha)
            st.link_button("📲 Enviar Lembrete WhatsApp (Amanhã)", f"https://wa.me/5531999999999?text={urllib.parse.quote(msg)}", type="primary")
        else: 
            st.caption(f"Sem assembleias para amanhã ({amanha.strftime('%d/%m')}).")

    st.divider()
    cal_matriz = calendar.monthcalendar(a_sel, num_m)
    cal_col, list_col = st.columns([1.2, 1])
    
    with cal_col:
        html_cal = "<table class='cal-table'><tr><th>Seg</th><th>Ter</th><th>Qua</th><th>Qui</th><th>Sex</th><th>Sáb</th><th>Dom</th></tr>"
        for sem in cal_matriz:
            html_cal += "<tr>"
            for d in sem:
                if d == 0: 
                    html_cal += "<td class='cal-empty'></td>"
                else:
                    classe = "cal-day cal-event" if d in eventos_mes else "cal-day"
                    html_cal += f"<td><span class='{classe}'>{d}</span></td>"
            html_cal += "</tr>"
        st.markdown(html_cal + "</table>", unsafe_allow_html=True)
        
    with list_col:
        if not eventos_mes: 
            st.info("Nenhuma assembleia cadastrada neste mês.")
        else:
            for d in sorted(eventos_mes.keys()):
                st.markdown(f"<div class='event-desc'><b>Dia {d:02d}:</b> {', '.join(eventos_mes[d])}</div>", unsafe_allow_html=True)

    if is_master:
        st.divider()
        st.markdown("#### ⚙️ Gerenciar Assembleias")
        c_add, c_del = st.columns(2)
        with c_add:
            with st.form("add_ass"):
                dt_ass = st.date_input("Data da Assembleia", format="DD/MM/YYYY")
                desc_ass = st.text_input("Descrição (Ex: Assembleia Auto Itaú)")
                if st.form_submit_button("Cadastrar Nova", type="primary") and desc_ass:
                    supabase.table("assembleias").insert({"data_evento": dt_ass.strftime("%d/%m/%Y"), "descricao": desc_ass}).execute()
                    st.success("Salvo!"); st.rerun()
        with c_del:
            if not df_ass.empty:
                opts_del = df_ass.apply(lambda x: f"ID:{x['id']} | {x['data_evento']} - {x['descricao']}", axis=1).tolist()
                sel_del = st.selectbox("Selecione para Apagar:", [""] + opts_del)
                if st.button("🚨 Apagar Selecionada", use_container_width=True) and sel_del:
                    id_apagar = int(sel_del.split(" | ")[0].replace("ID:", ""))
                    supabase.table("assembleias").delete().eq("id", id_apagar).execute()
                    st.rerun()
