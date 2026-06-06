import streamlit as st
import requests
from datetime import datetime
from utils import formatar_telefone, formatar_data, formatar_moeda

def render_nova_venda(supabase, df_cli, lista_admin_bd):
    st.markdown("### 📝 Cadastrar Nova Venda")
    
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        cliente = st.text_input("Nome do Cliente *", key="v_cli")
        telefone = st.text_input("Telefone", key="v_tel", on_change=lambda: st.session_state.update({'v_tel': formatar_telefone(st.session_state.get('v_tel',''))}), placeholder="(31) 99999-9999", max_chars=15)
        profissao = st.text_input("Profissão", key="v_prof")
    with col_c2:
        email = st.text_input("Email", key="v_email")
        aniversario = st.text_input("Data de Aniversário (DD/MM/AAAA)", key="v_ani", on_change=lambda: st.session_state.update({'v_ani': formatar_data(st.session_state.get('v_ani',''))}), placeholder="DD/MM/AAAA", max_chars=10)
        renda = st.text_input("Renda Mensal (R$)", key="v_ren", on_change=lambda: st.session_state.update({'v_ren': formatar_moeda(st.session_state.get('v_ren',''))}), placeholder="R$ 0,00")
        
    st.markdown("##### Busca Rápida de Endereço")
    col_cep1, col_cep2 = st.columns([1, 3])
    with col_cep1: 
        cep = st.text_input("CEP (Digite e clique fora)", max_chars=9)
        
    if cep and cep != st.session_state.get('last_cep', ''):
        c_limpo = ''.join(filter(str.isdigit, cep))
        if len(c_limpo) == 8:
            try:
                res = requests.get(f"https://viacep.com.br/ws/{c_limpo}/json/", timeout=5)
                if res.status_code == 200 and "erro" not in res.json():
                    d_cep = res.json()
                    st.session_state.update({'v_rua': d_cep.get("logradouro", ""), 'v_bai': d_cep.get("bairro", ""), 'v_cid': d_cep.get("localidade", ""), 'v_uf': d_cep.get("uf", "")})
                    st.success("✅ CEP Encontrado!")
            except: 
                st.warning("⚠️ Serviço de CEP indisponível.")
        st.session_state['last_cep'] = cep

    ce1, ce2, ce3 = st.columns([2, 1, 1])
    rua = ce1.text_input("Rua/Logradouro", key="v_rua" if 'v_rua' in st.session_state else None)
    numero = ce2.text_input("Número")
    complemento = ce3.text_input("Complemento")

    ce4, ce5, ce6 = st.columns([2, 2, 1])
    bairro = ce4.text_input("Bairro", key="v_bai" if 'v_bai' in st.session_state else None)
    cidade = ce5.text_input("Cidade", key="v_cid" if 'v_cid' in st.session_state else None)
    uf = ce6.text_input("UF", max_chars=2, key="v_uf" if 'v_uf' in st.session_state else None)

    st.subheader("2. Dados da Venda")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        data = st.date_input("Data da Venda", format="DD/MM/YYYY")
        vendedor = st.selectbox("Vendedor *", ["BRENO LIMA", "URIEL GOMES", "Consorbens", "Vendedor Terceiro"]) if is_master else st.session_state['nome_vendedor']
    with col_v2:
        admin = st.selectbox("Administradora *", lista_admin_bd)
        produto = st.selectbox("Produto *", ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])
        
    st.markdown("##### Cotas Adquiridas")
    if 'qtd_cotas' not in st.session_state: 
        st.session_state['qtd_cotas'] = 1
        
    cotas_data = []
    for i in range(st.session_state['qtd_cotas']):
        st.markdown(f"**Cota {i+1}**")
        cq1, cq2, cq3 = st.columns(3)
        with cq1: grp = st.text_input(f"Grupo *", key=f"g_{i}")
        with cq2: cta = st.text_input(f"Cota *", key=f"c_{i}")
        with cq3: val_str = st.text_input(f"Valor (R$) *", key=f"v_{i}", on_change=lambda idx=i: st.session_state.update({f'v_{idx}': formatar_moeda(st.session_state.get(f'v_{idx}',''))}), placeholder="R$ 0,00")
        cotas_data.append({"grupo": grp, "cota": cta, "valor_str": val_str})

    if st.button("➕ Adicionar mais uma Cota"): 
        st.session_state['qtd_cotas'] += 1
        st.rerun()
        
    st.markdown("---")
    if st.button("Salvar Venda(s)", type="primary", use_container_width=True):
        if not cliente.strip() or not cotas_data[0]['grupo'].strip() or not cotas_data[0]['cota'].strip():
            st.error("❌ Preencha os campos obrigatórios (*).")
        else:
            erros_cotas = []
            for i, c in enumerate(cotas_data):
                val_limpo = ''.join(filter(str.isdigit, str(c['valor_str'])))
                if not c['grupo'].strip() or not c['cota'].strip() or (float(val_limpo)/100 if val_limpo else 0) <= 0: 
                    erros_cotas.append(str(i+1))
            
            if erros_cotas: 
                st.error(f"❌ Preencha os dados da Cota: {', '.join(erros_cotas)}")
            else:
                end_completo = ", ".join([p for p in [rua, numero, complemento, bairro, cidade, uf] if p]) + (f" (CEP: {cep})" if cep else "")
                vendas_insert = []
                for c in cotas_data:
                    vf = float(''.join(filter(str.isdigit, str(c['valor_str']))))/100
                    vendas_insert.append({
                        "NOME": cliente, 
                        "DATA": data.strftime("%d/%m/%Y"), 
                        "PRODUTO": produto, 
                        "VENDEDOR": vendedor, 
                        "GRUPO": c['grupo'], 
                        "COTA": c['cota'], 
                        "ADMINISTRADORA": admin, 
                        "STATUS": "Em Andamento", 
                        "VALOR": vf
                    })
                
                supabase.table("vendas").insert(vendas_insert).execute()
                
                try:
                    if df_cli.empty or cliente not in df_cli['Nome'].tolist():
                        supabase.table("clientes").insert([{
                            "Nome": cliente, "Telefone": telefone, "Email": email, "Endereco": end_completo,
                            "Aniversario": aniversario, "Profissao": profissao, "Renda": renda, "Data_Cadastro": datetime.today().strftime("%d/%m/%Y")
                        }]).execute()
                except Exception: 
                    pass
                    
                st.success(f"✅ {len(cotas_data)} Venda(s) salvas!")
                st.session_state['qtd_cotas'] = 1
