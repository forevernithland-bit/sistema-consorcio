import streamlit as st
import pandas as pd

def render_senhas(supabase):
    st.markdown("### 🔐 Gestão de Senhas e Acessos")
    
    # Trava de segurança extra: garante que só os Masters vejam o conteúdo
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])
    if not is_master:
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()

    # Busca as senhas no banco de dados
    try:
        res = supabase.table("senhas_sistema").select("*").execute()
        df = pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Erro ao conectar com a tabela de senhas. Verifique se criou a tabela 'senhas_sistema'. Detalhes: {e}")
        df = pd.DataFrame(columns=["id", "empresa", "login", "senha", "link", "descricao"])

    if df.empty:
        df = pd.DataFrame(columns=["id", "empresa", "login", "senha", "link", "descricao"])

    # 1. FORMULÁRIO DE CADASTRO
    with st.expander("➕ Adicionar Novo Acesso", expanded=False):
        with st.form("form_nova_senha"):
            c1, c2 = st.columns(2)
            empresa = c1.text_input("Empresa *")
            login = c2.text_input("Login *")
            senha = c1.text_input("Senha *")
            link = c2.text_input("Link (URL)")
            descricao = st.text_input("Descrição / Observações")
            
            if st.form_submit_button("Salvar Acesso", type="primary"):
                if empresa and login and senha:
                    novo_dado = {
                        "empresa": empresa, "login": login, 
                        "senha": senha, "link": link, "descricao": descricao
                    }
                    supabase.table("senhas_sistema").insert(novo_dado).execute()
                    st.success("✅ Acesso salvo com sucesso!")
                    st.rerun()
                else:
                    st.error("Preencha Empresa, Login e Senha!")

    st.divider()

    # 2. TABELA DE EDIÇÃO RÁPIDA E PESQUISA
    st.markdown("#### 📋 Seus Acessos")
    
    # --- NOVO: Campo de pesquisa dinâmico ---
    busca = st.text_input("🔍 Pesquisar por Empresa, Login ou Descrição:", placeholder="Digite o termo que deseja localizar...")

    df_display = df.drop(columns=['id'], errors='ignore')
    df_display = df_display.fillna("")
    
    # Lógica de filtragem com base no que foi digitado
    if busca:
        df_display = df_display[
            df_display['empresa'].astype(str).str.contains(busca, case=False, na=False) |
            df_display['login'].astype(str).str.contains(busca, case=False, na=False) |
            df_display['descricao'].astype(str).str.contains(busca, case=False, na=False)
        ]

    st.caption("Dica: Você pode dar um duplo-clique em qualquer célula da tabela para editar. Se preencher novas linhas em branco, preencha Empresa, Login e Senha!")

    # Exibição do editor de dados com botão limpo para link
    edited_df = st.data_editor(
        df_display,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "empresa": st.column_config.TextColumn("Empresa", required=True),
            "login": st.column_config.TextColumn("Login", required=True),
            "senha": st.column_config.TextColumn("Senha", required=True),
            "link": st.column_config.LinkColumn(
                "Link", 
                help="Dê um duplo-clique para colar ou editar a URL.",
                display_text="🔗 Acessar"
            ),
            "descricao": st.column_config.TextColumn("Descrição")
        },
        key="editor_senhas"
    )

    if st.button("💾 Salvar Alterações da Tabela", type="primary"):
        mudancas = st.session_state["editor_senhas"]
        try:
            # 1. Salva as edições em linhas existentes (mapeando pelo índice real)
            for idx, cols in mudancas.get("edited_rows", {}).items():
                real_idx = df_display.index[idx]
                row_id = df.iloc[real_idx]["id"]
                supabase.table("senhas_sistema").update(cols).eq("id", int(row_id)).execute()
                
            # 2. Salva exclusões de linhas
            for idx in mudancas.get("deleted_rows", []):
                real_idx = df_display.index[idx]
                row_id = df.iloc[real_idx]["id"]
                supabase.table("senhas_sistema").delete().eq("id", int(row_id)).execute()
                
            # 3. Salva novas linhas adicionadas direto pela grade
            valid_added = []
            for row in mudancas.get("added_rows", []):
                emp = row.get("empresa", "")
                log = row.get("login", "")
                sen = row.get("senha", "")
                if emp and log and sen:
                    valid_added.append({
                        "empresa": emp,
                        "login": log,
                        "senha": sen,
                        "link": row.get("link", ""),
                        "descricao": row.get("descricao", "")
                    })
                    
            if valid_added:
                supabase.table("senhas_sistema").insert(valid_added).execute()
                
            st.success("✅ Alterações salvas com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro ao salvar as modificações: {e}")

    st.divider()

    # 3. IMPORTAÇÃO E EXPORTAÇÃO
    st.markdown("#### 📥 Importar / 📤 Exportar Backup")
    c_imp, c_exp = st.columns(2)
    
    with c_imp:
        st.write("**Importar CSV**")
        st.caption("O arquivo CSV deve ter as colunas exatas: empresa, login, senha, link, descricao")
        uploaded_file = st.file_uploader("Subir arquivo", type=['csv'], label_visibility="collapsed")
        if uploaded_file is not None:
            if st.button("Processar Importação"):
                try:
                    df_import = pd.read_csv(uploaded_file)
                    df_import = df_import.fillna("")
                    records = df_import.to_dict(orient="records")
                    supabase.table("senhas_sistema").insert(records).execute()
                    st.success("✅ Senhas importadas com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro na importação. Detalhes: {e}")
    
    with c_exp:
        st.write("**Exportar para Excel (CSV)**")
        st.caption("Baixe uma cópia de segurança de todos os acessos cadastrados.")
        csv_data = df_display.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Baixar Backup em CSV",
            data=csv_data,
            file_name=f"backup_senhas_consorbens_{pd.Timestamp.today().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            type="secondary",
            use_container_width=True
        )
