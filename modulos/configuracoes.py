import streamlit as st
from utils import parse_float_safe, obter_index_produto

def render_configuracoes(supabase, df_admin_cad, df_admin, lista_admin_bd, cfg, cfg_id):
    st.markdown("### 🏢 Configurações de Sistema")
    t_cad_adm, t_regras, t_reg_int = st.tabs(["🏢 Cadastrar Admin", "📋 Regras", "👥 Regras Internas"])
    
    with t_cad_adm:
        with st.form("f_c_adm"):
            c1, c2 = st.columns([2, 1])
            n_adm = c1.text_input("Nome da Administradora *")
            cn_adm = c2.text_input("CNPJ")
            en_adm = st.text_input("Endereço Completo")
            if st.form_submit_button("Salvar Administradora", type="primary") and n_adm:
                supabase.table("cad_administradoras").insert({"Administradora": n_adm.upper(), "CNPJ": cn_adm, "Endereço": en_adm}).execute()
                st.success("Cadastrada!")
                st.rerun()
                
        if not df_admin_cad.empty: 
            st.dataframe(df_admin_cad.drop(columns=['id'], errors='ignore'), use_container_width=True, hide_index=True)
    
    with t_regras:
        if not df_admin.empty:
            df_m = df_admin.drop(columns=['Admin_Norm', 'Prod_Norm', 'id'], errors='ignore').copy()
            
            # Cálculo seguro da comissão usando a nossa função parse_float_safe
            df_m.insert(2, 'Total Comissão', df_m.apply(lambda r: f"{sum([parse_float_safe(r.get(f'P{i}', 0)) for i in range(1, 26)]):.2f}%".replace('.', ','), axis=1))
            
            st.dataframe(df_m.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
        
        with st.expander("➕ Nova Regra", expanded=False):
            with st.form("f_a_n"):
                c1, c2 = st.columns(2)
                na = c1.selectbox("Admin *", lista_admin_bd)
                pa = c2.selectbox("Produto *", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
                i_p = []
                for l in range(5):
                    cp = st.columns(5)
                    for c in range(5):
                        np = (l * 5) + c + 1
                        i_p.append(cp[c].number_input(f"Parcela {np}", min_value=0.0, step=0.1, key=f"n_p{np}"))
                if st.form_submit_button("Salvar", type="primary") and na != "Nenhuma administradora cadastrada":
                    nr = {"Administradora": na.upper(), "Produto": pa}
                    for i, v in enumerate(i_p): 
                        nr[f"P{i+1}"] = f"{v}%" if v > 0 else ""
                    supabase.table("administradoras").insert(nr).execute()
                    st.rerun()
                
        with st.expander("✏️ Editar/Excluir Regra", expanded=False):
            if not df_admin.empty:
                opts = df_admin.apply(lambda x: f"ID:{x['id']} | {x['Administradora']} - {x['Produto']}", axis=1).tolist()
                sel = st.selectbox("Selecione:", [""] + opts)
                if sel:
                    id_r = int(sel.split(" | ")[0].replace("ID:", ""))
                    r_at = df_admin[df_admin['id'] == id_r].iloc[0]
                    c1, c2 = st.columns(2)
                    e_n = c1.selectbox("Admin", lista_admin_bd, index=lista_admin_bd.index(r_at['Administradora']) if r_at['Administradora'] in lista_admin_bd else 0)
                    e_p = c2.selectbox("Produto", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"], index=obter_index_produto(r_at['Produto']))
                    e_ip = []
                    for l in range(5):
                        cp = st.columns(5)
                        for c in range(5):
                            np = (l * 5) + c + 1
                            v_f = float(str(r_at.get(f'P{np}', '')).replace('%', '').strip() or 0.0)
                            e_ip.append(cp[c].number_input(f"P {np}", min_value=0.0, step=0.1, value=v_f, key=f"e_p{np}"))
                    b1, b2 = st.columns(2)
                    if b1.button("Salvar Alterações", type="primary"):
                        r_u = {"Administradora": e_n.upper(), "Produto": e_p}
                        for i, v in enumerate(e_ip): 
                            r_u[f"P{i+1}"] = f"{v}%" if v > 0 else ""
                        supabase.table("administradoras").update(r_u).eq("id", id_r).execute()
                        st.rerun()
                    if b2.button("🚨 EXCLUIR"):
                        supabase.table("administradoras").delete().eq("id", id_r).execute()
                        st.rerun()

    with t_reg_int:
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            st.markdown("**Breno**")
            b_b = st.number_input("Breno (%)", value=parse_float_safe(cfg.get("Breno_Breno", 70.0)), step=1.0)
            b_u = st.number_input("Uriel (%)", value=parse_float_safe(cfg.get("Breno_Uriel", 30.0)), step=1.0)
        with cc2:
            st.markdown("**Uriel**")
            u_u = st.number_input("Uriel (%) ", value=parse_float_safe(cfg.get("Uriel_Uriel", 70.0)), step=1.0)
            u_b = st.number_input("Breno (%) ", value=parse_float_safe(cfg.get("Uriel_Breno", 30.0)), step=1.0)
        with cc3:
            st.markdown("**Consorbens**")
            c_b = st.number_input("Breno (%)  ", value=parse_float_safe(cfg.get("Cons_Breno", 50.0)), step=1.0)
            c_u = st.number_input("Uriel (%)  ", value=parse_float_safe(cfg.get("Cons_Uriel", 50.0)), step=1.0)
            
        st.divider()
        st.markdown("#### Vendedor Terceiro")
        ct1, ct2, ct3 = st.columns(3)
        with ct1:
            t1_max = parse_float_safe(st.text_input("N1 Até (R$)", value=str(int(parse_float_safe(cfg.get("T1_Max", 500000))))))
            t1_pct = st.number_input("Comissão N1 (%)", value=parse_float_safe(cfg.get("T1_Pct", 1.0)), step=0.1)
            t1_parc = st.number_input("Qtd N1", value=int(parse_float_safe(cfg.get("T1_Parc", 4))), step=1)
        with ct2:
            t2_max = parse_float_safe(st.text_input("N2 Até (R$) ", value=str(int(parse_float_safe(cfg.get("T2_Max", 1500000))))))
            t2_pct = st.number_input("Comissão N2 (%)", value=parse_float_safe(cfg.get("T2_Pct", 1.5)), step=0.1)
            t2_parc = st.number_input("Qtd N2", value=int(parse_float_safe(cfg.get("T2_Parc", 5))), step=1)
        with ct3:
            st.markdown("**Teto N3**")
            t3_pct = st.number_input("Comissão N3 (%)", value=parse_float_safe(cfg.get("T3_Pct", 2.0)), step=0.1)
            t3_parc = st.number_input("Qtd N3", value=int(parse_float_safe(cfg.get("T3_Parc", 5))), step=1)

        st.divider()
        imp_in = st.number_input("Imposto Nota (%)", value=parse_float_safe(cfg.get("Imposto", 7.16)), step=0.01)

        if st.button("Salvar Regras", type="primary", use_container_width=True):
            n_c = {
                "Breno_Breno": b_b, "Breno_Uriel": b_u, "Uriel_Uriel": u_u, "Uriel_Breno": u_b, 
                "Cons_Breno": c_b, "Cons_Uriel": c_u, "T1_Max": t1_max, "T1_Pct": t1_pct, "T1_Parc": t1_parc, 
                "T2_Max": t2_max, "T2_Pct": t2_pct, "T2_Parc": t2_parc, "T3_Pct": t3_pct, "T3_Parc": t3_parc, 
                "Imposto": imp_in
            }
            if cfg_id: 
                supabase.table("config_interna").update(n_c).eq("id", cfg_id).execute()
            else: 
                supabase.table("config_interna").insert(n_c).execute()
            st.success("Atualizado!")
            st.rerun()
