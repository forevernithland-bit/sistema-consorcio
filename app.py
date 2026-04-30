import streamlit as st
import gspread
import pandas as pd
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="CRM Consórcios", layout="wide")

# === 1. CONFIGURAÇÃO DE USUÁRIOS E SENHAS ===
# Aqui você pode mudar o login e a senha da sua equipe. 
# Mantenha o "perfil" como "Master" para os sócios e "Vendedor" para a equipe.
USUARIOS = {
    "breno": {"senha": "123", "perfil": "Master", "nome": "BRENO LIMA"},
    "uriel": {"senha": "123", "perfil": "Master", "nome": "URIEL GOMES"},
    "vendedor1": {"senha": "123", "perfil": "Vendedor", "nome": "Vendedor Terceiro"},
    "consorbens": {"senha": "123", "perfil": "Vendedor", "nome": "Consorbens"}
}

# === 2. SISTEMA DE LOGIN ===
# Verifica se alguém já está logado
if 'usuario_logado' not in st.session_state:
    st.session_state['usuario_logado'] = None
    st.session_state['perfil_logado'] = None
    st.session_state['nome_vendedor'] = None

# Se não tiver logado, mostra a tela de login e PARA o código aqui
if st.session_state['usuario_logado'] is None:
    st.title("🔒 Login - CRM Consórcios")
    st.write("Digite suas credenciais para acessar o sistema.")
    
    with st.form("form_login"):
        usuario_input = st.text_input("Usuário (Login)").lower() # Transforma em minúsculo
        senha_input = st.text_input("Senha", type="password")
        btn_login = st.form_submit_button("Entrar")
        
        if btn_login:
            if usuario_input in USUARIOS and USUARIOS[usuario_input]["senha"] == senha_input:
                # Login com sucesso!
                st.session_state['usuario_logado'] = usuario_input
                st.session_state['perfil_logado'] = USUARIOS[usuario_input]["perfil"]
                st.session_state['nome_vendedor'] = USUARIOS[usuario_input]["nome"]
                st.rerun() # Atualiza a página para carregar o sistema
            else:
                st.error("❌ Usuário ou senha incorretos.")
    st.stop() # Bloqueia o resto do site até fazer o login

# === 3. CONEXÃO COM O GOOGLE SHEETS ===
@st.cache_resource
def conectar_planilha():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    planilha = gc.open("Sistema CRM") 
    return planilha

planilha = conectar_planilha()

# === 4. MENU LATERAL (DE ACORDO COM O PERFIL) ===
st.sidebar.title(f"Olá, {st.session_state['nome_vendedor']}")
st.sidebar.write(f"Perfil: **{st.session_state['perfil_logado']}**")
st.sidebar.divider()

# Libera os menus dependendo de quem logou
if st.session_state['perfil_logado'] == "Master":
    opcoes_menu = ["Dashboard", "Nova Venda", "Gerenciar Vendas (Editar/Deletar)", "Baixar Parcela"]
else:
    # Vendedor só vê o Dashboard (suas comissões) e pode lançar Nova Venda
    opcoes_menu = ["Dashboard", "Nova Venda"]

menu = st.sidebar.radio("Navegação:", opcoes_menu)

st.sidebar.divider()
if st.sidebar.button("Sair (Logout)"):
    st.session_state['usuario_logado'] = None
    st.session_state['perfil_logado'] = None
    st.session_state['nome_vendedor'] = None
    st.rerun()

# === 5. TELAS DO SISTEMA ===

if menu == "Dashboard":
    st.title("📊 Painel de Vendas")
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_vendas = aba_vendas.get_all_records()
    
    if dados_vendas:
        df_vendas = pd.DataFrame(dados_vendas)
        
        # O SEGREDO DOS VENDEDORES: Se for vendedor, filtra a planilha e mostra SÓ as vendas dele!
        if st.session_state['perfil_logado'] == "Vendedor":
            st.write("Aqui estão as vendas registradas por você:")
            df_vendas = df_vendas[df_vendas['Vendedor'] == st.session_state['nome_vendedor']]
        else:
            st.write("Visão Geral do Sistema (Todas as Vendas):")
            
        if not df_vendas.empty:
            st.dataframe(df_vendas.tail(10)) # Mostra as últimas 10
        else:
            st.info("Nenhuma venda encontrada para o seu usuário.")
    else:
        st.info("O sistema ainda não possui vendas cadastradas.")

elif menu == "Nova Venda":
    st.title("📝 Cadastrar Nova Venda")
    
    with st.form("form_venda"):
        col1, col2 = st.columns(2)
        with col1:
            # Data agora no formato DIA / MÊS / ANO
            data = st.date_input("Data da Venda", format="DD/MM/YYYY")
            cliente = st.text_input("Nome do Cliente *")
            telefone = st.text_input("Telefone (Opcional)")
            
            # Se for Master, pode escolher o vendedor. Se for Vendedor, trava no nome dele.
            if st.session_state['perfil_logado'] == "Master":
                vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"])
            else:
                st.write(f"**Vendedor:** {st.session_state['nome_vendedor']}")
                vendedor = st.session_state['nome_vendedor']
                
        with col2:
            admin = st.selectbox("Administradora *", ["YAMAHA", "ITAÚ", "ROMA", "EMBRACON"])
            produto = st.selectbox("Produto *", ["Auto", "Imovel", "Moto"])
            grupo = st.text_input("Grupo *")
            cota = st.text_input("Cota *")
            valor = st.number_input("Valor da Venda (R$) *", min_value=0.0, step=1000.0)
            status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"])
        
        salvar = st.form_submit_button("Salvar Venda")
        
        if salvar:
            if cliente and grupo and cota and valor > 0:
                aba_vendas = planilha.worksheet("Vendas")
                # Formata a data para salvar bonitinho na planilha
                nova_linha = [
                    "", str(data.strftime("%d/%m/%Y")), cliente, telefone, "", "", "",
                    vendedor, admin, produto, grupo, cota, valor, status
                ]
                aba_vendas.append_row(nova_linha)
                st.success(f"Venda de {cliente} salva com sucesso!")
            else:
                st.error("Preencha todos os campos obrigatórios (*).")

elif menu == "Gerenciar Vendas (Editar/Deletar)":
    st.title("🛠️ Gerenciar e Editar Vendas")
    st.warning("Área Restrita (Apenas Sócios). Muito cuidado ao deletar informações!")
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_vendas = aba_vendas.get_all_records()
    
    if dados_vendas:
        df_vendas = pd.DataFrame(dados_vendas)
        
        # Cria uma lista de opções para encontrar a venda facilmente
        opcoes_busca = df_vendas.apply(lambda row: f"Linha {row.name + 2} | Cliente: {row['Nome_Cliente']} - Grupo/Cota: {row['Grupo']}/{row['Cota']}", axis=1).tolist()
        venda_selecionada = st.selectbox("Selecione a venda que deseja alterar ou excluir:", [""] + opcoes_busca)
        
        if venda_selecionada:
            # Puxa o número exato da linha lá do Google Sheets
            linha_planilha = int(venda_selecionada.split(" | ")[0].replace("Linha ", ""))
            idx_dataframe = linha_planilha - 2
            venda_atual = df_vendas.iloc[idx_dataframe]
            
            st.divider()
            st.subheader(f"Editando Venda: {venda_atual['Nome_Cliente']}")
            
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome do Cliente", value=str(venda_atual['Nome_Cliente']))
                novo_status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"], index=["Vendido", "Contemplado", "Cancelado"].index(venda_atual.get('Status_Cliente', 'Vendido') if venda_atual.get('Status_Cliente') in ["Vendido", "Contemplado", "Cancelado"] else "Vendido"))
            with col2:
                novo_valor = st.number_input("Valor da Venda (R$)", value=float(venda_atual['Valor_Venda'] if str(venda_atual['Valor_Venda']).replace('.','',1).isdigit() else 0.0))

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Salvar Alterações"):
                    # Atualiza células específicas (linha, coluna, valor)
                    aba_vendas.update_cell(linha_planilha, 3, novo_nome)   # Coluna C é a 3 (Nome)
                    aba_vendas.update_cell(linha_planilha, 13, novo_valor) # Coluna M é a 13 (Valor)
                    aba_vendas.update_cell(linha_planilha, 14, novo_status) # Coluna N é a 14 (Status)
                    st.success("Alterações salvas na planilha!")
                    st.rerun()
            with col_btn2:
                if st.button("🚨 DELETAR ESTA VENDA", type="primary"):
                    aba_vendas.delete_rows(linha_planilha)
                    st.error("Venda apagada permanentemente!")
                    st.rerun()

elif menu == "Baixar Parcela":
    st.title("💰 Recebimento de Comissão (Baixa)")
    st.write("A lógica da matemática do imposto fica aqui...")
    # (Mantive a tela resumida para focar nas atualizações que você pediu)
    st.info("Esta tela calculará a divisão exata quando as parcelas forem geradas automaticamente.")
