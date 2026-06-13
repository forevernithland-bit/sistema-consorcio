import streamlit as st
import pandas as pd
import google.generativeai as genai

def render_assistente(supabase):
    st.markdown("### 🤖 Assistente Virtual IA")
    
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    # Configuração da Chave da API
    if "GEMINI_API_KEY" not in st.secrets:
        st.warning("⚠️ Chave da API do Gemini não encontrada. Adicione 'GEMINI_API_KEY' nos Secrets do Streamlit.")
        return
        
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    # Abas do sistema
    if is_master:
        tab_chat, tab_bd = st.tabs(["💬 Bater Papo com a IA", "⚙️ Alimentar Base de Conhecimento"])
    else:
        tab_chat, tab_bd = st.tabs(["💬 Bater Papo com a IA", " "]) # Gambiarra visual para vendedores verem só o chat
    
    # ==========================================
    # ABA 1: CHAT COM A IA
    # ==========================================
    with tab_chat:
        st.caption("Pergunte sobre regras, prazos, faturamento ou idades de veículos das administradoras.")
        
        # Inicia o histórico do chat na sessão
        if "mensagens_ia" not in st.session_state:
            st.session_state["mensagens_ia"] = [{"role": "assistant", "content": f"Olá, {st.session_state.get('nome_vendedor', 'equipe')}! Sou o assistente da Consorbens. O que você deseja saber sobre as administradoras hoje?"}]

        # Exibe o histórico
        for msg in st.session_state["mensagens_ia"]:
            st.chat_message(msg["role"]).write(msg["content"])

        # Campo de digitação
        pergunta = st.chat_input("Ex: Qual o percentual de lance embutido da Yamaha?")
        
        if pergunta:
            # Mostra a pergunta do usuário
            st.session_state["mensagens_ia"].append({"role": "user", "content": pergunta})
            st.chat_message("user").write(pergunta)
            
            with st.spinner("Pensando..."):
                try:
                    # 1. Puxar o conhecimento do banco
                    res = supabase.table("base_conhecimento_ia").select("*").execute()
                    df_base = pd.DataFrame(res.data)
                    
                    # 2. Montar o texto de contexto (A Mágica da Segurança)
                    contexto_geral = ""
                    if not df_base.empty:
                        for _, row in df_base.iterrows():
                            contexto_geral += f"\n\n--- ADMINISTRADORA: {row['administradora']} ---\n"
                            contexto_geral += f"Regras Operacionais: {row['regras_operacionais']}\n"
                            # Se for Master, inclui as comissões. Se for Vendedor, a IA NUNCA fica sabendo.
                            if is_master:
                                contexto_geral += f"Regras de Comissionamento (SIGILOSO): {row['regras_comissionamento']}\n"
                    
                    if not contexto_geral:
                        contexto_geral = "Ainda não há regras cadastradas no banco de dados."

                    # 3. Configurar a IA e o Prompt
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    prompt_sistema = f"""Você é o assistente virtual exclusivo do ERP da Consorbens, especializado em consórcios.
                    Sua missão é responder à pergunta do usuário baseando-se ÚNICA E EXCLUSIVAMENTE nas informações abaixo.
                    
                    CONTEXTO DO BANCO DE DADOS:
                    {contexto_geral}
                    
                    REGRAS DE RESPOSTA:
                    1. Se a resposta não estiver no contexto acima, diga educadamente: "Desculpe, não encontrei essa informação na minha base de conhecimento."
                    2. NÃO invente regras, taxas ou comissões.
                    3. Seja direto, claro e profissional.
                    
                    PERGUNTA DO USUÁRIO: {pergunta}
                    """
                    
                    # 4. Chamar a IA
                    resposta = model.generate_content(prompt_sistema)
                    texto_resposta = resposta.text
                    
                    # 5. Salvar e mostrar a resposta
                    st.session_state["mensagens_ia"].append({"role": "assistant", "content": texto_resposta})
                    st.chat_message("assistant").write(texto_resposta)
                    
                except Exception as e:
                    st.error(f"Erro ao processar a resposta: {e}")

    # ==========================================
    # ABA 2: ALIMENTAR O BANCO (SÓ MASTERS)
    # ==========================================
    if is_master:
        with tab_bd:
            st.markdown("Aqui você escreve tudo o que a IA precisa saber para responder à equipe.")
            
            try:
                res = supabase.table("base_conhecimento_ia").select("*").execute()
                df_bd = pd.DataFrame(res.data)
            except:
                df_bd = pd.DataFrame(columns=["id", "administradora", "regras_operacionais", "regras_comissionamento"])
                
            with st.expander("➕ Cadastrar Regras de uma Administradora", expanded=False):
                with st.form("form_ia"):
                    admin_nome = st.text_input("Nome da Administradora *")
                    reg_op = st.text_area("Regras Operacionais (Visível para todos)", placeholder="Idade do veículo, lance embutido, faturamento...", height=150)
                    reg_com = st.text_area("Regras de Comissionamento (SIGILOSO - Só Masters)", placeholder="Taxas da corretora, bônus, estornos...", height=150)
                    
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
                st.markdown("#### 📚 Base Atual")
                for _, row in df_bd.iterrows():
                    with st.expander(f"Administradora: {row['administradora']}"):
                        st.markdown("**Regras Operacionais:**")
                        st.write(row['regras_operacionais'])
                        st.markdown("**Regras de Comissionamento:**")
                        st.write(row['regras_comissionamento'])
                        if st.button(f"🚨 Apagar Regras da {row['administradora']}", key=f"del_{row['id']}"):
                            supabase.table("base_conhecimento_ia").delete().eq("id", row['id']).execute()
                            st.rerun()
