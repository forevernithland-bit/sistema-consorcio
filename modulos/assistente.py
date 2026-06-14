import streamlit as st
import pandas as pd
import google.generativeai as genai
import time

# ==========================================
# 1. TELA DE GERENCIAMENTO DA BASE (Para Administradores)
# ==========================================
def render_assistente_interativo(supabase):
    st.markdown("### ⚙️ Gerenciamento da Base de Conhecimento da IA")
    
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])
    if not is_master:
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()

    # Busca as regras existentes no banco de dados
    try:
        res = supabase.table("base_conhecimento_ia").select("*").execute()
        df_bd = pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Erro ao carregar a base de conhecimento. Detalhes: {e}")
        df_bd = pd.DataFrame(columns=["id", "administradora", "regras_operacionais"])
        
    # Formulário de Cadastro de Novas Regras
    with st.expander("➕ Adicionar Novas Regras de Administradora", expanded=False):
        with st.form("form_ia_regras"):
            c1, c2 = st.columns([2, 5])
            admin_nome = c1.text_input("Nome da Administradora *", placeholder="Ex: Yamaha")
            reg_op = c2.text_area("Regras Operacionais", placeholder="Idade do veículo, prazos, faturamento, observações...", height=150)
            
            if st.form_submit_button("Salvar na Base do Bento", type="primary"):
                if admin_nome and reg_op:
                    # Envia os dados para o Supabase
                    supabase.table("base_conhecimento_ia").insert({
                        "administradora": admin_nome,
                        "regras_operacionais": reg_op
                    }).execute()
                    st.success(f"✅ Regras da {admin_nome} salvas com sucesso!")
                    st.rerun()
                else:
                    st.error("Preencha o nome da administradora e as regras operacionais!")

    st.divider()

    # Exibição da Base Atual com Opção de Excluir
    if not df_bd.empty:
        st.markdown("#### 📚 Base de Regras Atual")
        for _, row in df_bd.iterrows():
            with st.expander(f"Administradora: {row['administradora']}"):
                st.write(row['regras_operacionais'])
                if st.button(f"🚨 Apagar Regras da {row['administradora']}", key=f"del_{row['id']}"):
                    # Exclui do Supabase
                    supabase.table("base_conhecimento_ia").delete().eq("id", row['id']).execute()
                    st.rerun()

# ==========================================
# 2. INTERFACE DO CHAT FLUTUANTE (Para Todos os Usuários)
# ==========================================
def render_falar_bento(supabase):
    # Trava de segurança extra: garante que só logados usem o Bento
    if st.session_state.get('usuario_logado') is None:
        return
        
    st.markdown("<h2 style='text-align: center;'>🤖 Olá, eu sou o Bento!</h2>", unsafe_allow_html=True)
    
    c_img, c_inst = st.columns([2, 5])
    
    # Imagem do Bento (Escalada para ficar agradável e não muito grande)
    c_img.image("logo_bento_ia.png", width=250, use_container_width=False)
    
    c_inst.markdown(f"""
    **Oi, {st.session_state.get('nome_vendedor', 'membro da equipe Consorbens')}!** Sou o assistente virtual exclusivo da Consorbens, especializado em te ajudar com dúvidas operacionais sobre as administradoras.

    Você pode me perguntar coisas como:
    * *Qual a idade máxima para comprar um veículo na Itaú?*
    * *Quais administradoras aceitam imóvel na planta?*
    * *Qual o prazo de faturamento da Yamaha para carros pesados?*

    Fique à vontade, estou aqui para agilizar o seu atendimento! 🚀
    """)
    
    st.divider()

    # Inicia o histórico do chat na sessão se não existir
    if "mensagens_ia_bento" not in st.session_state:
        st.session_state["mensagens_ia_bento"] = []

    # Configuração da Chave da API do Gemini
    if "GEMINI_API_KEY" not in st.secrets:
        st.error("⚠️ Chave da API do Gemini não configurada nos Secrets do Streamlit.")
        return
        
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    # Exibe o histórico de mensagens
    for msg in st.session_state["mensagens_ia_bento"]:
        st.chat_message(msg["role"]).write(msg["content"])

    # Campo de digitação de chat
    pergunta = st.chat_input("Digite sua dúvida operacionais sobre administradoras...")
    
    if pergunta:
        # Mostra a pergunta do usuário na tela
        st.session_state["mensagens_ia_bento"].append({"role": "user", "content": pergunta})
        st.chat_message("user").write(pergunta)
        
        with st.spinner("Pensando..."):
            try:
                # 1. Puxar o conhecimento do banco (regras operacionais apenas)
                res = supabase.table("base_conhecimento_ia").select("administradora, regras_operacionais").execute()
                df_base = pd.DataFrame(res.data)
                
                # 2. Montar o texto de contexto
                contexto_geral = ""
                if not df_base.empty:
                    for _, row in df_base.iterrows():
                        contexto_geral += f"\n\n--- ADMINISTRADORA: {row['administradora']} ---\n"
                        contexto_geral += f"Regras Operacionais: {row['regras_operacionais']}\n"
                
                if not contexto_geral:
                    contexto_geral = "Ainda não há regras cadastradas no banco de dados."

                # 3. Configurar a IA e o Prompt do Bento
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt_sistema = f"""Você é o Bento, o assistente virtual oficial e exclusivo do ERP da Consorbens, especializado em consórcios. Sua personalidade é prestativa, precisa e profissional.
                Sua missão é responder à pergunta do usuário baseando-se ÚNICA E EXCLUSIVAMENTE nas informações operacionais abaixo.
                
                CONTEXTO OPERACIONAL DO BANCO DE DADOS:
                {contexto_geral}
                
                REGRAS DE RESPOSTA DO BENTO:
                1. Se a resposta não estiver no contexto acima, diga educadamente: "Desculpe, não encontrei essa informação operacional na minha base de conhecimento."
                2. NUNCA invente regras, taxas ou observações que não estejam no texto fornecido.
                3. NUNCA mencione taxas de comissão da corretora ou vendedor. Você só fala de regras operacionais para a equipe.
                4. Seja direto, claro e amigável.
                
                PERGUNTA DO USUÁRIO: {pergunta}
                """
                
                # 4. Chamar a IA
                resposta = model.generate_content(prompt_sistema)
                texto_resposta = resposta.text
                
                # 5. Salvar e mostrar a resposta do Bento
                st.session_state["mensagens_ia_bento"].append({"role": "assistant", "content": texto_resposta})
                st.chat_message("assistant").write(texto_resposta)
                
            except Exception as e:
                st.error(f"Erro ao processar a resposta do Bento: {e}")
