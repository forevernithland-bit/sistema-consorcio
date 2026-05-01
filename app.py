import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import requests 
import streamlit.components.v1 as components
import altair as alt

# Configuração da página
st.set_page_config(page_title="Portal Consorbens", layout="wide", initial_sidebar_state="expanded")

# === 1. CONFIGURAÇÃO DE USUÁRIOS E SENHAS ===
USUARIOS = {
    "breno": {"senha": "123", "perfil": "Master", "nome": "BRENO LIMA"},
    "uriel": {"senha": "123", "perfil": "Master", "nome": "URIEL GOMES"},
    "vendedor1": {"senha": "123", "perfil": "Vendedor", "nome": "Vendedor Terceiro"},
    "consorbens": {"senha": "123", "perfil": "Vendedor", "nome": "Consorbens"}
}

# Controle de sessão geral
if 'usuario_logado' not in st.session_state:
    st.session_state['usuario_logado'] = None
    st.session_state['perfil_logado'] = None
    st.session_state['nome_vendedor'] = None
if 'menu_lateral' not in st.session_state:
    st.session_state['menu_lateral'] = "🔐 Login (Área Restrita)"
if 'cliente_visualizado' not in st.session_state:
    st.session_state['cliente_visualizado'] = None
if 'key_tabela' not in st.session_state:
    st.session_state['key_tabela'] = 0

def carregar_ferramenta(nome_arquivo):
    try:
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            html_code = f.read()
            components.html(html_code, height=900, scrolling=True)
    except FileNotFoundError:
        st.error(f"⚠️ O arquivo {nome_arquivo} não foi encontrado!")

# === MÁSCARAS INTELIGENTES ===
def formatar_telefone(tel):
    if not tel: return ""
    nums = ''.join(filter(str.isdigit, str(tel)))
    if len(nums) == 11: return f"({nums[:2]}) {nums[2:7]}-{nums[7:]}"
    elif len(nums) == 10: return f"({nums[:2]}) {nums[2:6]}-{nums[6:]}"
    return tel

def formatar_data(data_str):
    if not data_str: return ""
    nums = ''.join(filter(str.isdigit, str(data_str)))
    if len(nums) >= 8: return f"{nums[:2]}/{nums[2:4]}/{nums[4:8]}"
    elif len(nums) >= 4: return f"{nums[:2]}/{nums[2:4]}/{nums[4:]}"
    elif len(nums) >= 2: return f"{nums[:2]}/{nums[2:]}"
    return nums

def formatar_moeda(valor):
    if not valor: return "R$ 0,00"
    nums = ''.join(filter(str.isdigit, str(valor)))
    if not nums: return "R$ 0,00"
    val_float = float(nums) / 100
    return f"R$ {val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Callbacks
def mascara_tel_nv(): st.session_state['tel_nv'] = formatar_telefone(st.session_state.get('tel_nv', ''))
def mascara_aniv_nv(): st.session_state['aniv_nv'] = formatar_data(st.session_state.get('aniv_nv', ''))

# === 2. LÓGICA DO MENU LATERAL ===
is_logado = st.session_state['usuario_logado'] is not None
st.sidebar.image("https://www.consorbens.com/assets/logo-consorbens-DZ8uSiSJ.png", use_column_width=True)
st.sidebar.write("") 

if not is_logado:
    opcoes_menu = ["🔐 Login (Área Restrita)", "🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
else:
    st.sidebar.write(f"👤 **{st.session_state['nome_vendedor']}**")
    st.sidebar.divider()
    ferramentas_logadas = ["🏍️ Simulador Yamaha", "🏦 Simulador Itaú", "🎯 Oportunidades Itaú", "⚖️ Financiamento x Consórcio"]
    if st.session_state['perfil_logado'] == "Master":
        opcoes_menu = ["Dashboard", "Nova Venda", "Gerenciar Vendas (Editar/Deletar)", "Relatórios", "Administradoras", "Baixar Parcela"] + ferramentas_logadas
    else:
        opcoes_menu = ["Dashboard", "Nova Venda", "Relatórios"] + ferramentas_logadas

try: idx_menu = opcoes_menu.index(st.session_state['menu_lateral'])
except ValueError: idx_menu = 0

menu_selecionado = st.sidebar.radio(" ", opcoes_menu, index=idx_menu, label_visibility="collapsed")
if menu_selecionado != "Dashboard": st.session_state['cliente_visualizado'] = None
st.session_state['menu_lateral'] = menu_selecionado

if is_logado:
    st.sidebar.write("")
    if menu_selecionado == "Dashboard" and st.session_state['cliente_visualizado'] is not None:
        if st.sidebar.button("⬅️ Voltar ao Dashboard", type="primary", use_container_width=True):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
    st.sidebar.write("")
    if st.sidebar.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

st.sidebar.markdown("""<div style="text-align: center; margin-top: 30px; padding-top: 15px; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 0.85rem;">Portal Consorbens &copy; 2026</div>""", unsafe_allow_html=True)

# === 3. ESTILIZAÇÃO CSS ===
css = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
    [data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 2px solid #e2e8f0 !important; }
    button[kind="primary"] { background-color: #239b56 !important; border-color: #239b56 !important; color: #ffffff !important; font-weight: bold !important; }
    button[kind="primary"]:hover { background-color: #1b7a43 !important; border-color: #1b7a43 !important; color: #ffffff !important; transform: scale(1.02); transition: all 0.2s; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# === 4. CONEXÃO PLANILHA ===
@st.cache_resource
def conectar_planilha():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    return gc.open("Sistema CRM")

planilha = conectar_planilha()
aba_vendas = planilha.worksheet("Vendas")
try: aba_clientes = planilha.worksheet("Clientes")
except: aba_clientes = planilha.add_worksheet("Clientes", 1000, 6)

# === RENDERIZAÇÃO ===
if not is_logado:
    if menu_selecionado == "🔐 Login (Área Restrita)":
        st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        col_esq, col_meio, col_dir = st.columns([1, 1.2, 1])
        with col_meio:
            with st.form("form_login"):
                usuario_input = st.text_input("Usuário (Login)").lower()
                senha_input = st.text_input("Senha", type="password")
                btn_login = st.form_submit_button("Entrar no Sistema", type="primary")
                if btn_login:
                    if usuario_input in USUARIOS and USUARIOS[usuario_input]["senha"] == senha_input:
                        st.session_state['usuario_logado'] = usuario_input
                        st.session_state['perfil_logado'] = USUARIOS[usuario_input]["perfil"]
                        st.session_state['nome_vendedor'] = USUARIOS[usuario_input]["nome"]
                        st.session_state['menu_lateral'] = "Dashboard" 
                        st.rerun() 
                    else: st.error("❌ Usuário ou senha incorretos.")
    elif menu_selecionado == "🏍️ Simulador Yamaha": carregar_ferramenta("yamaha.html")
    elif menu_selecionado == "🏦 Simulador Itaú": carregar_ferramenta("itau.html")
    elif menu_selecionado == "🎯 Oportunidades Itaú": carregar_ferramenta("guia.html")
    elif menu_selecionado == "⚖️ Financiamento x Consórcio": carregar_ferramenta("comparador.html")
    st.stop() 

if menu_selecionado == "Dashboard":
    dados_brutos = aba_vendas.get_all_values()
    
    # -------------------------------------------------------------
    # PERFIL DO CLIENTE - AGORA DINÂMICO E SEM FORMULÁRIO (ST.FORM)
    # -------------------------------------------------------------
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        st.title(f"👤 Perfil do Cliente: {cliente_nome}")
        if st.button("⬅️ Voltar ao Dashboard", type="primary"):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
            
        dados_cli = aba_clientes.get_all_records()
        df_cli = pd.DataFrame(dados_cli)
        
        info_cliente = {}
        if not df_cli.empty and 'Nome' in df_cli.columns:
            busca_cli = df_cli[df_cli['Nome'] == cliente_nome]
            if not busca_cli.empty: info_cliente = busca_cli.iloc[0].to_dict()

        is_master = st.session_state['perfil_logado'] == "Master"
        st.subheader("📋 Dados Cadastrais")
        if not is_master: st.info("🔒 Como Vendedor, você só pode visualizar estes dados. Para alterar, contate o Administrador.")
            
        # Chaves de sessão seguras para não perder dados ao atualizar
        key_tel = f"tel_ed_{cliente_nome}"
        key_aniv = f"aniv_ed_{cliente_nome}"
        key_end = f"end_ed_{cliente_nome}"
        key_email = f"email_ed_{cliente_nome}"
        
        if key_tel not in st.session_state: st.session_state[key_tel] = info_cliente.get("Telefone", "")
        if key_aniv not in st.session_state: st.session_state[key_aniv] = info_cliente.get("Aniversario", "")
        if key_end not in st.session_state: st.session_state[key_end] = info_cliente.get("Endereco", "")
        if key_email not in st.session_state: st.session_state[key_email] = info_cliente.get("Email", "")
            
        def m_tel_ed(): st.session_state[key_tel] = formatar_telefone(st.session_state[key_tel])
        def m_aniv_ed(): st.session_state[key_aniv] = formatar_data(st.session_state[key_aniv])

        # Elementos Livres (Sem st.form)
        c1, c2 = st.columns(2)
        endereco = c1.text_input("Endereço Completo", key=key_end, disabled=not is_master)
        telefone_edit = c1.text_input("Telefone", key=key_tel, on_change=m_tel_ed, disabled=not is_master, placeholder="(31) 99999-9999", max_chars=15)
        email = c2.text_input("E-mail", key=key_email, disabled=not is_master)
        aniversario_edit = c2.text_input("Data de Aniversário (DD/MM/AAAA)", key=key_aniv, on_change=m_aniv_ed, disabled=not is_master, placeholder="DD/MM/AAAA", max_chars=10)
        
        if is_master:
            if st.button("Salvar Alterações", type="primary", key="btn_salvar_cli"):
                nomes_col = aba_clientes.col_values(1)
                if cliente_nome in nomes_col:
                    row_idx = nomes_col.index(cliente_nome) + 1
                    aba_clientes.update_cell(row_idx, 2, st.session_state[key_tel])
                    aba_clientes.update_cell(row_idx, 3, st.session_state[key_email])
                    aba_clientes.update_cell(row_idx, 4, st.session_state[key_end])
                    aba_clientes.update_cell(row_idx, 5, st.session_state[key_aniv])
                else:
                    aba_clientes.append_row([cliente_nome, st.session_state[key_tel], st.session_state[key_email], st.session_state[key_end], st.session_state[key_aniv], datetime.today().strftime("%d/%m/%Y")])
                st.success("Dados do cliente atualizados com sucesso!")
        else:
            st.button("Salvar Alterações", disabled=True, key="btn_salvar_cli")

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        if len(dados_brutos) > 1:
            df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
            df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
            cotas_cliente = df_vendas[df_vendas['Nome do cliente'] == cliente_nome].copy()
            if not cotas_cliente.empty:
                cotas_cliente['Valor_Numerico'] = cotas_cliente['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip().apply(pd.to_numeric, errors='coerce').fillna(0.0)
                info_a, info_b = st.columns(2)
                info_a.metric("Total de Cotas Adquiridas", len(cotas_cliente))
                info_b.metric("Volume Total Investido", f"R$ {cotas_cliente['Valor_Numerico'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                cotas_cliente['Valor Formatado'] = cotas_cliente['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                ficha_display = cotas_cliente[['DATA', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'Valor Formatado']].rename(columns={'DATA': 'Data', 'ADMINISTRADORA': 'Administradora', 'PRODUTO': 'Produto', 'GRUPO': 'Grupo', 'COTA': 'Cota', 'Valor Formatado': 'Valor (R$)'})
                estilo_ficha = ficha_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_ficha, use_container_width=True, hide_index=True)
            else: st.warning("Nenhuma cota encontrada para este cliente.")

    # -------------------------------------------------------------
    # DASHBOARD PADRÃO
    # -------------------------------------------------------------
    else:
        if len(dados_brutos) > 1:
            df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
            df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
            df_vendas['Data_Real'] = pd.to_datetime(df_vendas['DATA'], dayfirst=True, errors='coerce')
            df_vendas['Valor_Numerico'] = df_vendas['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip().apply(pd.to_numeric, errors='coerce').fillna(0.0)

            if st.session_state['perfil_logado'] == "Vendedor": df_vendas = df_vendas[df_vendas['VENDEDOR'] == st.session_state['nome_vendedor']]
                
            col_t1, col_t2 = st.columns([4, 1])
            with col_t2:
                st.write("")
                if st.button("Nova Venda", use_container_width=True, type="primary"):
                    st.session_state['menu_lateral'] = "Nova Venda"
                    st.rerun()
            
            c_filtro1, c_filtro2 = st.columns([1, 2])
            with c_filtro1:
                filtro_cli = st.selectbox("⏳ Filtro por Data da Venda:", ["Últimos 5 Cadastros", "Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
                if filtro_cli == "Período Personalizado":
                    cd1, cd2 = st.columns(2)
                    with cd1: data_inicio = st.date_input("Data Inicial", format="DD/MM/YYYY")
                    with cd2: data_fim = st.date_input("Data Final", format="DD/MM/YYYY")
            with c_filtro2: busca_nome = st.text_input("🔍 Buscar Cliente por Nome:")
                
            hoje = datetime.today()
            df_clientes = df_vendas.copy()
            
            if filtro_cli == "Últimos 5 Cadastros" and busca_nome.strip() == "": df_clientes = df_clientes.tail(5).iloc[::-1]
            elif filtro_cli != "Todos os Clientes" and filtro_cli != "Últimos 5 Cadastros":
                mask = df_clientes['Data_Real'].notna()
                if filtro_cli == "Mês Atual": df_clientes = df_clientes[mask & (df_clientes['Data_Real'].dt.month == hoje.month) & (df_clientes['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Mês Anterior":
                    mes_ant, ano_ant = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                    df_clientes = df_clientes[mask & (df_clientes['Data_Real'].dt.month == mes_ant) & (df_clientes['Data_Real'].dt.year == ano_ant)]
                elif filtro_cli == "Ano Atual": df_clientes = df_clientes[mask & (df_clientes['Data_Real'].dt.year == hoje.year)]
                elif filtro_cli == "Período Personalizado": df_clientes = df_clientes[mask & (df_clientes['Data_Real'].dt.date >= data_inicio) & (df_clientes['Data_Real'].dt.date <= data_fim)]
                
            if busca_nome.strip() != "": df_clientes = df_vendas[df_vendas['Nome do cliente'].astype(str).str.contains(busca_nome.strip(), case=False, na=False)]
                
            if not df_clientes.empty:
                df_display = df_clientes.copy()
                df_display['Grupo e cota'] = df_display.apply(lambda x: f"{x['GRUPO']} / {x['COTA']}" if str(x['GRUPO']).strip() or str(x['COTA']).strip() else "N/A", axis=1)
                df_display['valor da venda'] = df_display['Valor_Numerico'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                df_display = df_display[['Nome do cliente', 'Grupo e cota', 'PRODUTO', 'ADMINISTRADORA', 'valor da venda', 'VENDEDOR', 'DATA']].rename(columns={ 'Nome do cliente': 'Nome', 'PRODUTO': 'Tipo de Produto', 'ADMINISTRADORA': 'Administradora', 'VENDEDOR': 'Vendedor', 'DATA': 'Data da Venda' })
                
                estilo_tabela = df_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                tabela_interativa = st.dataframe(estilo_tabela, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key=f"tabela_clientes_{st.session_state['key_tabela']}")
                
                st.markdown(f"""<div style="text-align: right; padding-top: 10px;"><h4 style="color: #239b56; font-weight: bold; margin: 0;">TOTAL: R$ {df_clientes['Valor_Numerico'].sum():,.2f}</h4></div>""".replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
                
                sel = tabela_interativa.selection.rows
                if len(sel) > 0:
                    st.session_state['cliente_visualizado'] = df_display.iloc[sel[0]]['Nome']
                    st.rerun()
            else: st.warning("Nenhum cliente encontrado com esses filtros ou termos de busca.")

            st.divider()
            st.subheader("📊 Gráficos de Vendas Globais")
            g_filtro1, g_filtro2 = st.columns(2)
            with g_filtro1:
                ft_graf = st.selectbox("⏳ Período para o Gráfico:", ["Mês Atual", "Mês Anterior", "Anual", "Todas as Vendas", "Período Personalizado"])
                if ft_graf == "Período Personalizado":
                    cg1, cg2 = st.columns(2)
                    with cg1: gi = st.date_input("Data Inicial", format="DD/MM/YYYY", key="g_inicio")
                    with cg2: gf = st.date_input("Data Final", format="DD/MM/YYYY", key="g_fim")
            with g_filtro2: fp_graf = st.selectbox("📦 Produto:", ["Todos", "Auto", "Imovel", "Moto", "Caminhao"])
                
            df_g = df_vendas.copy()
            if ft_graf != "Todas as Vendas" and not df_g['Data_Real'].isna().all():
                mask = df_g['Data_Real'].notna()
                if ft_graf == "Mês Atual": df_g = df_g[mask & (df_g['Data_Real'].dt.month == hoje.month) & (df_g['Data_Real'].dt.year == hoje.year)]
                elif ft_graf == "Mês Anterior":
                    ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                    df_g = df_g[mask & (df_g['Data_Real'].dt.month == ma) & (df_g['Data_Real'].dt.year == aa)]
                elif ft_graf == "Anual": df_g = df_g[mask & (df_g['Data_Real'].dt.year == hoje.year)]
                elif ft_graf == "Período Personalizado": df_g = df_g[mask & (df_g['Data_Real'].dt.date >= gi) & (df_g['Data_Real'].dt.date <= gf)]
                
            if fp_graf != "Todos": df_g = df_g[df_g['PRODUTO'].astype(str).str.contains(fp_graf, case=False, na=False)]
                
            if not df_g.empty:
                m1, m2 = st.columns(2)
                m1.metric("Volume Total Vendido", f"R$ {df_g['Valor_Numerico'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                m2.metric("Total de Cotas Vendidas", len(df_g))
                st.write("")
                agrupar = 'PRODUTO' if fp_graf == "Todos" else 'ADMINISTRADORA'
                df_pizza = df_g[agrupar].value_counts().reset_index()
                df_pizza.columns = ['Categoria', 'Quantidade']
                graf = alt.Chart(df_pizza).mark_arc(innerRadius=60).encode(theta=alt.Theta(field="Quantidade", type="quantitative"), color=alt.Color(field="Categoria", type="nominal"), tooltip=['Categoria', 'Quantidade']).properties(height=350)
                _, gc2, _ = st.columns([1, 2, 1])
                with gc2: st.altair_chart(graf, use_container_width=True)
            else: st.warning("📊 Não há vendas suficientes para gerar o gráfico com os filtros atuais.")
        else: st.info("O sistema ainda não possui vendas cadastradas na planilha.")

elif menu_selecionado == "Nova Venda":
    st.title("📝 Cadastrar Nova Venda")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        if 'venda_cliente' not in st.session_state: st.session_state['venda_cliente'] = ""
        cliente = st.text_input("Nome do Cliente *", key="venda_cliente")
        if 'tel_nv' not in st.session_state: st.session_state['tel_nv'] = ""
        telefone = st.text_input("Telefone", key="tel_nv", on_change=mascara_tel_nv, placeholder="(31) 99999-9999", max_chars=15)
    with col_c2:
        if 'venda_email' not in st.session_state: st.session_state['venda_email'] = ""
        email = st.text_input("E-mail", key="venda_email")
        if 'aniv_nv' not in st.session_state: st.session_state['aniv_nv'] = ""
        aniversario = st.text_input("Data de Aniversário (DD/MM/AAAA)", key="aniv_nv", on_change=mascara_aniv_nv, placeholder="DD/MM/AAAA", max_chars=10)
        
    st.markdown("##### Busca Rápida de Endereço")
    col_cep1, col_cep2 = st.columns([1, 3])
    with col_cep1:
        if 'venda_cep' not in st.session_state: st.session_state['venda_cep'] = ""
        cep = st.text_input("CEP (Digite e clique fora)", key="venda_cep", max_chars=9)
        
    if cep != st.session_state.get('last_cep', ''):
        cep_limpo = ''.join(filter(str.isdigit, cep))
        if len(cep_limpo) == 8:
            try:
                res = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
                if res.status_code == 200:
                    dados_cep = res.json()
                    if "erro" not in dados_cep:
                        st.session_state['venda_rua'] = dados_cep.get("logradouro", "")
                        st.session_state['venda_bairro'] = dados_cep.get("bairro", "")
                        st.session_state['venda_cidade'] = dados_cep.get("localidade", "")
                        st.session_state['venda_uf'] = dados_cep.get("uf", "")
                        st.success("✅ CEP Encontrado!")
            except: st.warning("⚠️ Serviço de CEP indisponível.")
        st.session_state['last_cep'] = cep

    ce1, ce2, ce3 = st.columns([2, 1, 1])
    with ce1: rua = st.text_input("Rua/Logradouro", key="venda_rua" if 'venda_rua' in st.session_state else None)
    with ce2: numero = st.text_input("Número", key="venda_numero" if 'venda_numero' in st.session_state else None)
    with ce3: complemento = st.text_input("Complemento", key="venda_complemento" if 'venda_complemento' in st.session_state else None)

    ce4, ce5, ce6 = st.columns([2, 2, 1])
    with ce4: bairro = st.text_input("Bairro", key="venda_bairro" if 'venda_bairro' in st.session_state else None)
    with ce5: cidade = st.text_input("Cidade", key="venda_cidade" if 'venda_cidade' in st.session_state else None)
    with ce6: uf = st.text_input("UF", max_chars=2, key="venda_uf" if 'venda_uf' in st.session_state else None)

    st.subheader("2. Dados da Venda")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        data = st.date_input("Data da Venda", format="DD/MM/YYYY")
        if st.session_state['perfil_logado'] == "Master": vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"])
        else:
            st.write(f"**Vendedor:** {st.session_state['nome_vendedor']}")
            vendedor = st.session_state['nome_vendedor']
    with col_v2:
        admin = st.selectbox("Administradora *", ["YAMAHA", "ITAÚ", "ROMA", "EMBRACON"])
        produto = st.selectbox("Produto *", ["Auto", "Imovel", "Moto", "Caminhão", "Serviços"])
        
    st.markdown("##### Cotas Adquiridas")
    if 'qtd_cotas' not in st.session_state: st.session_state['qtd_cotas'] = 1

    cotas_data = []
    for i in range(st.session_state['qtd_cotas']):
        st.markdown(f"**Cota {i+1}**")
        cq1, cq2, cq3, cq4 = st.columns(4)
        if f"g_{i}" not in st.session_state: st.session_state[f"g_{i}"] = ""
        if f"c_{i}" not in st.session_state: st.session_state[f"c_{i}"] = ""
        if f"v_in_{i}" not in st.session_state: st.session_state[f"v_in_{i}"] = ""
        if f"s_{i}" not in st.session_state: st.session_state[f"s_{i}"] = "Vendido"
        
        with cq1: grupo = st.text_input(f"Grupo *", key=f"g_{i}")
        with cq2: cota = st.text_input(f"Cota *", key=f"c_{i}")
        with cq3:
            def m_moeda(idx=i): st.session_state[f"v_in_{idx}"] = formatar_moeda(st.session_state[f"v_in_{idx}"])
            valor_str = st.text_input(f"Valor (R$) *", key=f"v_in_{i}", on_change=m_moeda, placeholder="R$ 0,00")
        with cq4: status = st.selectbox(f"Status", ["Vendido", "Contemplado", "Cancelado"], key=f"s_{i}")
        
        cotas_data.append({"grupo": grupo, "cota": cota, "valor_str": valor_str, "status": status})

    if st.button("➕ Adicionar mais uma Cota"):
        st.session_state['qtd_cotas'] += 1
        st.rerun()
    st.markdown("---")
    
    if st.button("Salvar Venda(s)", type="primary", use_container_width=True):
        if not str(cliente).strip():
            st.error("❌ Preencha o Nome do Cliente!")
        else:
            erros_cotas = []
            for i, c in enumerate(cotas_data):
                val_limpo = ''.join(filter(str.isdigit, str(c['valor_str'])))
                v_float = float(val_limpo)/100 if val_limpo else 0.0
                if not str(c['grupo']).strip() or not str(c['cota']).strip() or v_float <= 0:
                    erros_cotas.append(str(i+1))
                    
            if erros_cotas:
                st.error(f"❌ Atenção! Preencha o Grupo, Cota e um Valor maior que zero da(s) seguinte(s) Cota(s): {', '.join(erros_cotas)}")
            else:
                aba_vendas = planilha.worksheet("Vendas")
                end_completo = ", ".join([p for p in [rua, numero, complemento, bairro, cidade, uf] if p])
                if cep: end_completo += f" (CEP: {cep})"

                for c in cotas_data:
                    val_float = float(''.join(filter(str.isdigit, str(c['valor_str']))))/100
                    aba_vendas.append_row(["", cliente, str(data.strftime("%d/%m/%Y")), produto, vendedor, c['grupo'], c['cota'], admin, c['status'], val_float])

                try: nomes_cadastrados = aba_clientes.col_values(1)
                except: nomes_cadastrados = []
                if cliente not in nomes_cadastrados:
                    aba_clientes.append_row([cliente, telefone, email, end_completo, aniversario, str(datetime.today().strftime("%d/%m/%Y"))])

                st.success(f"✅ {len(cotas_data)} Venda(s) e Cadastro de {cliente} salvos com sucesso!")
                
                # Limpa TELA
                limpar = ['venda_cliente', 'tel_nv', 'venda_email', 'aniv_nv', 'venda_cep', 'last_cep', 'venda_rua', 'venda_numero', 'venda_complemento', 'venda_bairro', 'venda_cidade', 'venda_uf']
                for i in range(st.session_state['qtd_cotas']): limpar.extend([f"g_{i}", f"c_{i}", f"v_in_{i}", f"s_{i}"])
                for k in limpar:
                    if k in st.session_state: del st.session_state[k]
                st.session_state['qtd_cotas'] = 1 

elif menu_selecionado == "Gerenciar Vendas (Editar/Deletar)":
    st.title("🛠️ Gerenciar e Editar Vendas")
    st.warning("Área Restrita (Apenas Sócios). Muito cuidado ao deletar informações!")
    
    aba_vendas = planilha.worksheet("Vendas")
    dados_brutos = aba_vendas.get_all_values()
    if len(dados_brutos) > 1:
        df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
        df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
        opcoes_busca = df_vendas.apply(lambda r: f"Linha {r.name + 2} | Cliente: {r['Nome do cliente']} - Grupo/Cota: {r['GRUPO']}/{r['COTA']}", axis=1).tolist()
        venda_selecionada = st.selectbox("Selecione a venda para alterar/excluir:", [""] + opcoes_busca)
        
        if venda_selecionada:
            linha_planilha = int(venda_selecionada.split(" | ")[0].replace("Linha ", ""))
            venda_atual = df_vendas.iloc[linha_planilha - 2]
            st.divider()
            st.subheader(f"Editando Venda: {venda_atual['Nome do cliente']}")
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome do Cliente", value=str(venda_atual['Nome do cliente']))
                novo_status = st.selectbox("Status", ["Vendido", "Contemplado", "Cancelado"], index=["Vendido", "Contemplado", "Cancelado"].index(venda_atual['STATUS'] if venda_atual['STATUS'] in ["Vendido", "Contemplado", "Cancelado"] else "Vendido"))
            with col2:
                val_float = pd.to_numeric(str(venda_atual['VALOR']).replace('R$', '').replace('.','').replace(',', '.').strip(), errors='coerce')
                novo_valor = st.number_input("Valor da Venda (R$)", value=float(val_float) if not pd.isna(val_float) else 0.0)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Salvar Alterações", type="primary"):
                    aba_vendas.update_cell(linha_planilha, 2, novo_nome)   
                    aba_vendas.update_cell(linha_planilha, 10, novo_valor) 
                    aba_vendas.update_cell(linha_planilha, 9, novo_status) 
                    st.success("Alterações salvas na planilha!")
                    st.rerun()
            with col_btn2:
                if st.button("🚨 DELETAR ESTA VENDA"):
                    aba_vendas.delete_rows(linha_planilha)
                    st.error("Venda apagada permanentemente!")
                    st.rerun()
    else: st.info("Nenhuma venda para gerenciar.")

elif menu_selecionado == "Relatórios":
    st.title("📑 Relatórios Gerenciais")
    aba_vendas = planilha.worksheet("Vendas")
    dados_brutos = aba_vendas.get_all_values()
    if len(dados_brutos) > 1:
        df_vendas = pd.DataFrame(dados_brutos[1:]).iloc[:, :10]
        df_vendas.columns = ["ID_cliente", "Nome do cliente", "DATA", "PRODUTO", "VENDEDOR", "GRUPO", "COTA", "ADMINISTRADORA", "STATUS", "VALOR"]
        df_vendas['Data_Real'] = pd.to_datetime(df_vendas['DATA'], dayfirst=True, errors='coerce')
        df_vendas['Valor_Numerico'] = df_vendas['VALOR'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip().apply(pd.to_numeric, errors='coerce').fillna(0.0)

        c1, c2 = st.columns([1, 2])
        with c1:
            ft_rel = st.selectbox("⏳ Período:", ["Mês Atual", "Mês Anterior", "Ano Atual", "Todas as Vendas", "Período Personalizado"])
            if ft_rel == "Período Personalizado":
                rd1, rd2 = st.columns(2)
                with rd1: ri = st.date_input("Data Inicial", format="DD/MM/YYYY")
                with rd2: rf = st.date_input("Data Final", format="DD/MM/YYYY")
        
        hoje = datetime.today()
        df_f = df_vendas.copy()
        
        if ft_rel != "Todas as Vendas":
            m = df_f['Data_Real'].notna()
            if ft_rel == "Mês Atual": df_f = df_f[m & (df_f['Data_Real'].dt.month == hoje.month) & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_f = df_f[m & (df_f['Data_Real'].dt.month == ma) & (df_f['Data_Real'].dt.year == aa)]
            elif ft_rel == "Ano Atual": df_f = df_f[m & (df_f['Data_Real'].dt.year == hoje.year)]
            elif ft_rel == "Período Personalizado": df_f = df_f[m & (df_f['Data_Real'].dt.date >= ri) & (df_f['Data_Real'].dt.date <= rf)]
                
        if st.session_state['perfil_logado'] == "Vendedor": df_f = df_f[df_f['VENDEDOR'] == st.session_state['nome_vendedor']]
        st.divider()

        if df_f.empty: st.warning("Nenhuma venda no período selecionado.")
        else:
            t1, t2, t3 = st.tabs(["👤 Por Usuário", "🏢 Por Administradora", "💰 Comissões"])
            with t1:
                rv = df_f.groupby('VENDEDOR').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                rv['Vol'] = rv['Vol'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.dataframe(rv.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
            with t2:
                ra = df_f.groupby('ADMINISTRADORA').agg(Qtde=('Nome do cliente', 'count'), Vol=('Valor_Numerico', 'sum')).reset_index()
                ra['Vol'] = ra['Vol'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.dataframe(ra.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
            with t3:
                pct = st.number_input("Comissão Média (%)", min_value=0.0, value=1.0, step=0.1)
                dc = df_f.groupby('VENDEDOR').agg(Vol=('Valor_Numerico', 'sum')).reset_index()
                dc['Comissão'] = dc['Vol'] * (pct / 100)
                st.metric("Comissão Total", f"R$ {dc['Comissão'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                dc['Vol'] = dc['Vol'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                dc['Comissão'] = dc['Comissão'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.dataframe(dc.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
    else: st.info("Não possui vendas.")

elif menu_selecionado == "Administradoras":
    st.title("🏢 Gestão de Administradoras")
    try: aba_admin = planilha.worksheet("Administradoras")
    except:
        aba_admin = planilha.add_worksheet("Administradoras", 100, 10)
        aba_admin.append_row(["Administradora", "Produto", "Comissão Total (%)", "Regra de Pagamento (Parcelas)"])
        st.rerun()

    dados_admin = aba_admin.get_all_values()
    df_admin = pd.DataFrame(dados_admin[1:], columns=dados_admin[0]) if len(dados_admin) > 1 else pd.DataFrame(columns=["Administradora", "Produto", "Comissão Total (%)", "Regra de Pagamento (Parcelas)"])

    t1, t2, t3 = st.tabs(["📋 Regras", "➕ Nova", "✏️ Editar/Excluir"])
    with t1:
        if not df_admin.empty: st.dataframe(df_admin.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}]), use_container_width=True, hide_index=True)
        else: st.info("Nenhuma regra.")
    with t2:
        with st.form("f_adm"):
            c1, c2 = st.columns(2)
            with c1:
                n = st.text_input("Administradora *")
                p = st.selectbox("Produto *", ["Automóvel", "Caminhão", "Serviços", "Motos", "Imóveis"])
            with c2:
                com = st.number_input("Comissão (%) *", min_value=0.0, step=0.1)
                r = st.text_area("Regras *")
            if st.form_submit_button("Salvar", type="primary"):
                if n and p and r:
                    aba_admin.append_row([n.upper(), p, f"{com}%", r])
                    st.success("Salvo!")
                    st.rerun()
                else: st.error("Preencha tudo.")
    with t3:
        if not df_admin.empty:
            opts = df_admin.apply(lambda x: f"Linha {x.name + 2} | {x['Administradora']} - {x['Produto']}", axis=1).tolist()
            sel = st.selectbox("Editar:", [""] + opts)
            if sel:
                l_plan = int(sel.split(" | ")[0].replace("Linha ", ""))
                reg_at = df_admin.iloc[l_plan - 2]
                c1, c2 = st.columns(2)
                with c1:
                    e_n = st.text_input("Administradora", value=reg_at['Administradora'])
                    e_p = st.selectbox("Produto", ["Automóvel", "Caminhão", "Serviços", "Motos", "Imóveis"], index=["Automóvel", "Caminhão", "Serviços", "Motos", "Imóveis"].index(reg_at['Produto']) if reg_at['Produto'] in ["Automóvel", "Caminhão", "Serviços", "Motos", "Imóveis"] else 0)
                with c2:
                    vc = float(str(reg_at['Comissão Total (%)']).replace('%', '').strip() or 0)
                    e_c = st.number_input("Comissão (%)", value=vc)
                    e_r = st.text_area("Regras", value=reg_at['Regra de Pagamento (Parcelas)'])
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Salvar", type="primary"):
                        aba_admin.update_cell(l_plan, 1, e_n.upper())
                        aba_admin.update_cell(l_plan, 2, e_p)
                        aba_admin.update_cell(l_plan, 3, f"{e_c}%")
                        aba_admin.update_cell(l_plan, 4, e_r)
                        st.success("Alterado!")
                        st.rerun()
                with b2:
                    if st.button("🚨 EXCLUIR"):
                        aba_admin.delete_rows(l_plan)
                        st.error("Deletado!")
                        st.rerun()

elif menu_selecionado == "Baixar Parcela":
    st.title("💰 Baixa de Comissão")
    st.info("Em breve...")
