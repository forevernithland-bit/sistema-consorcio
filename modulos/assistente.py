import streamlit as st
import pandas as pd
import google.generativeai as genai

# ==========================================
# 1. WIDGET DO CHAT (Fica fixo no Menu Lateral)
# ==========================================
def render_widget_ia(supabase):
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    if "GEMINI_API_KEY" not in st.secrets:
        st.sidebar.warning("⚠️ Chave API da IA não configurada.")
        return

    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

    if "mensagens_ia" not in st.session_state:
        st.session_state["mensagens_ia"] = [{"role": "assistant", "content": "Olá! Sou a IA da Consorbens. Qual a sua dúvida sobre as administradoras?"}]

    st.sidebar.divider()
    
    # O Popover atua como o nosso "Bonequinho Flutuante" nativo!
    with st.sidebar.popover("🤖 Falar com a IA", use_container_width=True):
        st.markdown("### 💬 Assistente Consorbens")
        
        # O processamento da pergunta precisa vir ANTES de desenhar o chat na tela
        with st.form("chat_form", clear_on_submit=True):
            c1, c2 = st.columns([4, 1])
            pergunta = c1.text_input("Digite sua dúvida:", label_visibility="collapsed", placeholder="Ex: Qual a taxa da Yamaha?")
            enviou = c2.form_submit_button("➤")
            
            if enviou and pergunta:
                st.session_state["mensagens_ia"].append({"role": "user", "content": pergunta})
                
                with st.spinner("Pensando..."):
                    try:
                        res = supabase.table("base_conhecimento_ia").select("*").execute()
                        df_base = pd.DataFrame(res.data)
                        
                        contexto_geral = ""
                        if not df_base.empty:
                            for _, row in df_base.iterrows():
                                contexto_geral += f"\n\n--- ADMINISTRADORA: {row['administradora']} ---\n"
                                contexto_geral += f"Regras Operacionais: {row['regras_operacionais']}\n"
                                if is_master:
                                    contexto_geral += f"Comissões (SIGILOSO): {row['regras_comissionamento']}\n"
                        
                        if not contexto_geral:
                            contexto_geral = "Ainda não há regras cadastradas no banco de dados."

                        model = genai.GenerativeModel('gemini-1.5-flash')
                        prompt_sistema = f"""Você é o assistente virtual da Consorbens, especializado em consórcios.
                        Responda APENAS com base neste contexto (se não souber, diga que não tem a informação):
                        {contexto_geral}
                        
                        PERGUNTA DO USUÁRIO: {pergunta}
                        """
                        
                        resposta = model.generate_content(prompt_sistema)
                        st.session_state["mensagens_ia"].append({"role": "assistant", "content": resposta.text})
                    except Exception as e:
                        st.error(f"Erro ao consultar a IA: {e}")

        # Caixa de exibição do histórico de mensagens (Com barra de rolagem)
        chat_container = st.container(height=350)
        with chat_container:
            for msg in st.session_state["mensagens_ia"]:
                st.chat_message(msg["role"]).write(msg["content"])

# ==========================================
# 2. TELA DE CADASTRO DE REGRAS (Só para Masters)
# ==========================================
def render_config_ia(supabase):
    st.markdown("### ⚙️ Base de Conhecimento da IA")
    st.markdown("Aqui você escreve tudo o que a IA precisa saber para responder à equipe com precisão.")
    
    try:
        res = supabase.table("base_conhecimento_ia").select("*").execute()
        df_bd = pd.DataFrame(res.data)
    except:
        df_bd = pd.DataFrame(columns=["id", "administradora", "regras_operacionais", "regras_comissionamento"])
        
    with st.expander("➕ Cadastrar Regras de uma Administradora", expanded=False):
        with st.form("form_ia_cadastro"):
            admin_nome = st.text_input("Nome da Administradora *")
            reg_op = st.text_area("Regras Operacionais (Visível para todos)", placeholder="Idade do veículo, lances embutidos, prazos...", height=150)
            reg_com = st.text_area("Regras de Comissionamento (SIGILOSO - Só Masters)", placeholder="Taxas da corretora, parcelamento de bônus...", height=150)
            
            if st.form_submit_button("Salvar na Base da IA", type="primary"):
                if admin_nome:
                    supabase.table("base_conhecimento_ia").insert({
                        "administradora": admin_nome,
                        "regras_operacionais": reg_op,
                        "regras_comissionamento": reg_com
                    }).execute()
                    st.success("Salvo com sucesso!")
                    st.rerun()
                else:
                    st.error("Preencha o nome da administradora.")
                    
    if not df_bd.empty:
        st.markdown("#### 📚 Base Atual de Conhecimento")
        for _, row in df_bd.iterrows():
            with st.expander(f"Administradora: {row['administradora']}"):
                st.markdown("**Regras Operacionais:**")
                st.write(row['regras_operacionais'])
                st.markdown("**Regras de Comissionamento:**")
                st.write(row['regras_comissionamento'])
                if st.button(f"🚨 Apagar Regras da {row['administradora']}", key=f"del_{row['id']}"):
                    supabase.table("base_conhecimento_ia").delete().eq("id", row['id']).execute()
                    st.rerun()
