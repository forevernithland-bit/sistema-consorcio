import streamlit as st
import gspread
import pandas as pd
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="CRM Consórcios", layout="wide")

# Conexão com o Google Sheets usando a senha segura do Streamlit
@st.cache_resource
def conectar_planilha():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    # ATENÇÃO: O nome da sua planilha no Google Drive deve ser exatamente "Sistema CRM"
    planilha = gc.open("Sistema CRM") 
    return planilha

planilha = conectar_planilha()

# Menu Lateral
st.sidebar.title("Menu do Sistema")
menu = st.sidebar.radio("Escolha uma opção:", ["Dashboard", "Nova Venda", "Baixar Parcela"])

if menu == "Dashboard":
    st.title("📊 Painel Financeiro")
    st.write("Aqui em breve teremos os gráficos de previsão de recebimentos e vendas do mês!")
    
    # Exibir Vendas Rápidas
    aba_vendas = planilha.worksheet("Vendas")
    dados_vendas = aba_vendas.get_all_records()
    if dados_vendas:
        st.subheader("Últimas Vendas Cadastradas")
        df_vendas = pd.DataFrame(dados_vendas)
        st.dataframe(df_vendas.tail(5)) # Mostra as últimas 5
    else:
        st.info("Nenhuma venda cadastrada ainda.")

elif menu == "Nova Venda":
    st.title("📝 Cadastrar Nova Venda")
    
    with st.form("form_venda"):
        col1, col2 = st.columns(2)
        with col1:
            data = st.date_input("Data da Venda")
            cliente = st.text_input("Nome do Cliente *")
            telefone = st.text_input("Telefone (Opcional)")
            vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"])
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
                nova_linha = [
                    "", str(data.strftime("%d/%m/%Y")), cliente, telefone, "", "", "",
                    vendedor, admin, produto, grupo, cota, valor, status
                ]
                aba_vendas.append_row(nova_linha)
                st.success(f"Venda de {cliente} salva com sucesso!")
                st.info("No futuro, salvar uma venda aqui criará automaticamente as parcelas na aba Recebimentos.")
            else:
                st.error("Preencha todos os campos obrigatórios (*).")

elif menu == "Baixar Parcela":
    st.title("💰 Recebimento de Comissão (Baixa)")
    st.write("Simulador de conferência de pagamentos (Regra do Imposto de 7,16% e Divisão de Sócios).")
    
    col1, col2 = st.columns(2)
    with col1:
        grupo_busca = st.text_input("Digite o Grupo")
    with col2:
        cota_busca = st.text_input("Digite a Cota")
        
    valor_admin = st.number_input("Valor pago pela Administradora nesta parcela (R$):", min_value=0.0)
    vendedor_venda = st.selectbox("Quem fez a venda?", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Terceiro"])
    
    if st.button("Calcular Divisão para Conferência"):
        # Matemática
        imposto = valor_admin * 0.0716
        valor_pos_imposto = valor_admin - imposto
        
        comissao_vendedor = 0.0
        if vendedor_venda == "Terceiro":
            st.warning("⚠️ Vendedor Terceiro: Preenchendo a comissão manualmente para este teste (1% em 4x = 0.25% ao mês).")
            comissao_vendedor = valor_admin * 0.25 # Exemplo fixo para testar
            
        lucro_liquido = valor_pos_imposto - comissao_vendedor
        
        # Divisão
        if vendedor_venda == "BRENO LIMA":
            breno = lucro_liquido * 0.70
            uriel = lucro_liquido * 0.30
        elif vendedor_venda == "URIEL GOMES":
            uriel = lucro_liquido * 0.70
            breno = lucro_liquido * 0.30
        else: # Consorbens ou Terceiro
            breno = lucro_liquido * 0.50
            uriel = lucro_liquido * 0.50
            
        # Tela de Resumo
        st.divider()
        st.subheader("Resumo do Recebimento")
        st.write(f"**Valor Bruto Recebido:** R$ {valor_admin:.2f}")
        st.write(f"**(-) Imposto NF (7,16%):** R$ {imposto:.2f}")
        st.write(f"**(-) Comissão Vendedor:** R$ {comissao_vendedor:.2f}")
        st.write(f"**(=) Lucro Líquido:** R$ {lucro_liquido:.2f}")
        
        st.success(f"**Divisão Breno (Sócio 1):** R$ {breno:.2f}")
        st.success(f"**Divisão Uriel (Sócio 2):** R$ {uriel:.2f}")
        
        st.button("Confirmar Recebimento e dar Baixa na Planilha")
