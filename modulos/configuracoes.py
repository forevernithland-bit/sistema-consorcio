import streamlit as st
from utils import parse_float_safe, obter_index_produto
from database import carregar_dados_iniciais
import comissao_vendedor as cv
from ui_valores import input_valor

def render_configuracoes(supabase, df_admin_cad, df_admin, lista_admin_bd, cfg, cfg_id):
    from modulos.tema import secao; secao("Administradoras e regras", "🏢", "Cadastro das administradoras, regras de comissão e regras internas.")
    t_cad_adm, t_regras, t_reg_int = st.tabs(["🏢 Cadastrar Admin", "📋 Regras", "👥 Regras Internas"])
    
    with t_cad_adm:
        with st.form("f_c_adm"):
            c1, c2 = st.columns([2, 1])
            n_adm = c1.text_input("Nome da Administradora *")
            cn_adm = c2.text_input("CNPJ")
            en_adm = st.text_input("Endereço Completo")
            if st.form_submit_button("Salvar Administradora", type="primary") and n_adm:
                supabase.table("cad_administradoras").insert({"Administradora": n_adm.upper(), "CNPJ": cn_adm, "Endereço": en_adm}).execute()
                carregar_dados_iniciais.clear()
                st.success("Cadastrada!")
                st.rerun()
                
        if not df_admin_cad.empty: 
            st.dataframe(df_admin_cad.drop(columns=['id'], errors='ignore'), use_container_width=True, hide_index=True)
    
    with t_regras:
        if not df_admin.empty:
            df_m = df_admin.drop(columns=['Admin_Norm', 'Prod_Norm', 'Tipo_Norm', 'id'], errors='ignore').copy()

            # "Tipo de Parcela" logo depois do Produto, pra ficar claro qual
            # linha é a linear e qual é a reduzida (ex.: Itaú imóvel).
            _tp = df_m.pop('Tipo_Parcela') if 'Tipo_Parcela' in df_m.columns else None
            df_m.insert(2, 'Tipo de Parcela',
                        (_tp.fillna('').replace('', 'Linear/Reduzida (todas)')
                         if _tp is not None else 'Linear/Reduzida (todas)'))

            # Cálculo seguro da comissão usando a nossa função parse_float_safe
            df_m.insert(3, 'Total Comissão', df_m.apply(lambda r: f"{sum([parse_float_safe(r.get(f'P{i}', 0)) for i in range(1, 26)]):.2f}%".replace('.', ','), axis=1))

            # Quantidade de parcelas (nº de Pn preenchidos) — ajuda a bater o "4% em N"
            df_m.insert(4, 'Nº Parcelas', df_m.apply(lambda r: sum(1 for i in range(1, 26) if parse_float_safe(r.get(f'P{i}', 0)) > 0), axis=1))

            st.dataframe(df_m.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
            st.caption("**Tipo de Parcela** — *Linear*: parcela cheia. *Reduzida*: parcela reduzida (o Itaú "
                       "dilui os mesmos 4% em mais parcelas). *Linear/Reduzida (todas)*: a regra vale para "
                       "os dois casos (Yamaha e demais).")
        
        with st.expander("➕ Nova Regra", expanded=False):
            with st.form("f_a_n"):
                c1, c2, c3 = st.columns(3)
                na = c1.selectbox("Admin *", lista_admin_bd)
                pa = c2.selectbox("Produto *", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
                tp = c3.selectbox("Tipo de Parcela", ["— (todas)", "Linear", "Reduzida"],
                                  help="Use Linear/Reduzida quando a administradora tem "
                                       "percentuais diferentes por tipo de parcela (ex.: Itaú).")
                i_p = []
                for l in range(5):
                    cp = st.columns(5)
                    for c in range(5):
                        np = (l * 5) + c + 1
                        i_p.append(cp[c].number_input(f"Parcela {np}", min_value=0.0, step=0.05, format="%.4f", key=f"n_p{np}"))
                if st.form_submit_button("Salvar", type="primary") and na != "Nenhuma administradora cadastrada":
                    nr = {"Administradora": na.upper(), "Produto": pa,
                          "Tipo_Parcela": (tp if tp in ("Linear", "Reduzida") else None)}
                    for i, v in enumerate(i_p):
                        nr[f"P{i+1}"] = f"{v}%" if v > 0 else ""
                    supabase.table("administradoras").insert(nr).execute()
                    carregar_dados_iniciais.clear()
                    st.rerun()
                
        with st.expander("✏️ Editar/Excluir Regra", expanded=False):
            if not df_admin.empty:
                opts = df_admin.apply(lambda x: f"ID:{x['id']} | {x['Administradora']} - {x['Produto']}", axis=1).tolist()
                sel = st.selectbox("Selecione:", [""] + opts)
                if sel:
                    id_r = int(sel.split(" | ")[0].replace("ID:", ""))
                    r_at = df_admin[df_admin['id'] == id_r].iloc[0]
                    c1, c2, c3 = st.columns(3)
                    e_n = c1.selectbox("Admin", lista_admin_bd, index=lista_admin_bd.index(r_at['Administradora']) if r_at['Administradora'] in lista_admin_bd else 0)
                    e_p = c2.selectbox("Produto", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"], index=obter_index_produto(r_at['Produto']))
                    _tp_op = ["— (todas)", "Linear", "Reduzida"]
                    _tp_cur = str(r_at.get('Tipo_Parcela') or "").strip().capitalize()
                    e_tp = c3.selectbox("Tipo de Parcela", _tp_op,
                                        index=_tp_op.index(_tp_cur) if _tp_cur in _tp_op else 0)
                    e_ip = []
                    for l in range(5):
                        cp = st.columns(5)
                        for c in range(5):
                            np = (l * 5) + c + 1
                            v_f = float(str(r_at.get(f'P{np}', '')).replace('%', '').strip() or 0.0)
                            e_ip.append(cp[c].number_input(f"P {np}", min_value=0.0, step=0.05, format="%.4f", value=v_f, key=f"e_p{np}"))
                    b1, b2 = st.columns(2)
                    if b1.button("Salvar Alterações", type="primary"):
                        r_u = {"Administradora": e_n.upper(), "Produto": e_p,
                               "Tipo_Parcela": (e_tp if e_tp in ("Linear", "Reduzida") else None)}
                        for i, v in enumerate(e_ip):
                            r_u[f"P{i+1}"] = f"{v}%" if v > 0 else ""
                        supabase.table("administradoras").update(r_u).eq("id", id_r).execute()
                        carregar_dados_iniciais.clear()
                        st.rerun()
                    _conf_regra = b2.checkbox("Confirmo excluir esta regra", key=f"conf_del_regra_{id_r}")
                    if b2.button("🚨 EXCLUIR", disabled=not _conf_regra):
                        try:
                            from auditoria import apagar_com_lixeira
                            _n, _av = apagar_com_lixeira(supabase, "administradoras", [id_r],
                                                         f"Configurações: excluir regra {r_at['Administradora']} - {r_at['Produto']}")
                            carregar_dados_iniciais.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ A regra NÃO foi excluída: {e}")

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
        st.caption("Percentuais sobre o **valor da carta**, pagos por posição: 1º, 2º, 3º e 4º pagamento de comissão da administradora. "
                   "A produção é a soma das cartas vendidas pelo vendedor no mês; vale \"acima de\" (acima, não igual).")
        rv = cv.regra(cfg)
        ct1, ct2, ct3 = st.columns(3)
        with ct1:
            st.markdown("**Base (sempre)**")
            vd_p1 = st.number_input("1º pagamento (%)", value=rv["VD_P1"], min_value=0.0, step=0.05, format="%.2f")
            vd_p2 = st.number_input("2º pagamento (%)", value=rv["VD_P2"], min_value=0.0, step=0.05, format="%.2f")
        with ct2:
            st.markdown("**Bônus 1**")
            vd_m1 = input_valor("Produção do mês acima de (R$)", value=rv["VD_M1"], key="vd_m1", casas=0)
            vd_m1p3 = st.number_input("Mais no 3º pagamento (%)", value=rv["VD_M1_P3"], min_value=0.0, step=0.05, format="%.2f")
        with ct3:
            st.markdown("**Bônus 2** (soma ao bônus 1)")
            vd_m2 = input_valor("Produção do mês acima de (R$) ", value=rv["VD_M2"], key="vd_m2", casas=0)
            vd_m2p4 = st.number_input("Mais no 4º pagamento (%)", value=rv["VD_M2_P4"], min_value=0.0, step=0.05, format="%.2f")
        ce1, ce2, ce3 = st.columns(3)
        with ce1:
            vd_est = st.number_input("Estorno se cancelar (% do crédito)", value=rv["VD_EST_PCT"], min_value=0.0, step=0.05, format="%.2f")
        with ce2:
            vd_estm = st.number_input("Estorno vale até (meses da venda)", value=int(rv["VD_EST_MESES"]), step=1, min_value=0)
        with ce3:
            vd_estp = st.number_input("Estorno abatido em (parcelas)", value=int(rv["VD_EST_PARCELAS"]), step=1, min_value=1,
                                      help="O estorno é dividido em parcelas iguais, abatidas nos próximos pagamentos de comissão do vendedor.")
        _limites_ok = 0 < vd_m1 < vd_m2
        if not _limites_ok:
            st.error("Limites inválidos: o valor do bônus 2 precisa ser maior que o do bônus 1, e os dois maiores que zero.")
        _tot = vd_p1 + vd_p2
        st.caption(f"Total ao vendedor: **{_tot:.2f}%** (base) · **{_tot + vd_m1p3:.2f}%** (acima de R$ {vd_m1:,.0f}) · "
                   f"**{_tot + vd_m1p3 + vd_m2p4:.2f}%** (acima de R$ {vd_m2:,.0f}).".replace(",", ".").replace("$", "\\$"))   # '$' cru vira LaTeX

        st.divider()
        imp_in = st.number_input("Imposto Nota (%)", value=parse_float_safe(cfg.get("Imposto", 7.16)), step=0.01)

        if st.button("Salvar Regras", type="primary", use_container_width=True):
            if not _limites_ok:
                st.error("Corrija os limites do vendedor antes de salvar.")
                st.stop()
            # Converte tudo para tipos nativos do Python (evita numpy.int64/float64,
            # que o banco pode rejeitar). Percentuais/valores = float; qtd parcelas = int.
            n_c = {
                "Breno_Breno": float(b_b), "Breno_Uriel": float(b_u),
                "Uriel_Uriel": float(u_u), "Uriel_Breno": float(u_b),
                "Cons_Breno": float(c_b), "Cons_Uriel": float(c_u),
                "Imposto": float(imp_in)
            }
            n_vd = {"VD_P1": float(vd_p1), "VD_P2": float(vd_p2), "VD_M1": float(vd_m1), "VD_M1_P3": float(vd_m1p3),
                    "VD_M2": float(vd_m2), "VD_M2_P4": float(vd_m2p4), "VD_EST_PCT": float(vd_est), "VD_EST_MESES": int(vd_estm), "VD_EST_PARCELAS": int(vd_estp)}
            try:
                try:
                    if cfg_id:
                        supabase.table("config_interna").update({**n_c, **n_vd}).eq("id", int(cfg_id)).execute()
                    else:
                        supabase.table("config_interna").insert({**n_c, **n_vd}).execute()
                except Exception:
                    # colunas da regra do vendedor ainda não existem (migração 29): salva o resto e avisa
                    if cfg_id:
                        supabase.table("config_interna").update(n_c).eq("id", int(cfg_id)).execute()
                    else:
                        supabase.table("config_interna").insert(n_c).execute()
                    st.warning("A regra do vendedor não foi salva: rode a migração 29 no Supabase.")
                    carregar_dados_iniciais.clear()
                    st.stop()
                carregar_dados_iniciais.clear()
                st.success("✅ Regras atualizadas!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao salvar as regras: {e}")
