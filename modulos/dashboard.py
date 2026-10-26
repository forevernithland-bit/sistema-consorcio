from ui_valores import input_valor
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import altair as alt
from utils import (formatar_telefone, formatar_data, formatar_data_br,
                   formatar_moeda, formatar_brl_puro, normalizar_produto, formatar_cpf)
from regras import gerar_tabela_parcelas
from database import salvar_status_comissoes, carregar_dados_iniciais
from modulos.integracao_site import carregar_operacoes_site
from modulos.financeiro import calcular_resumo_mes_atual
from escopo import filtrar_por_vendedor, eh_master as _eh_master
import comissao_vendedor as cv


def _render_resumo_mes(supabase, df_vendas_global, df_admin, cfg, status_dict):
    """Quadrinho 'Resumo do mês' no topo do Dashboard — faturamento
    Tradicional + Cotas Contempladas (realizado e previsto), reaproveitando
    a mesma lógica do Financeiro. Só para Master (valores sensíveis)."""
    try:
        r = calcular_resumo_mes_atual(supabase, df_vendas_global, df_admin, cfg, status_dict)
    except Exception:
        return
    mes_lbl = datetime.today().strftime("%m/%Y")
    st.markdown(f"##### 📊 Resumo do mês ({mes_lbl})")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏦 Consórcio Tradicional", formatar_brl_puro(r["tradicional"]))
    c2.metric("🎯 Cotas Contempladas", formatar_brl_puro(r["contemplado_realizado"]))
    c3.metric("🔮 Previsto (em andamento)", formatar_brl_puro(r["contemplado_previsto"]))
    c4.metric("💰 Faturamento Total", formatar_brl_puro(r["total"]))
    st.caption("Tradicional e Cotas Contempladas = recebido/concluído até agora no mês. "
               "Previsto = ágio das Cotas Contempladas ainda Em análise no Site.")
    st.divider()


def _render_cartas_site(busca_nome=""):
    """Lista (só leitura) as operações de carta contemplada vindas do SITE.
    A edição continua no admin do Site — aqui é apenas visão."""
    try:
        site = carregar_operacoes_site()
    except Exception:
        site = None
    if site is None or site.empty:
        return
    # Vendedor só enxerga as operações em que ELE é o representante
    site = filtrar_por_vendedor(site, "representante")
    if site is None or site.empty:
        return

    st.divider()
    from modulos.tema import secao
    secao("Cartas Contempladas — Clientes do Site", "🌐")
    st.caption("Operações cadastradas no admin do Site (consorbensmg.com.br/admin). "
               "Visão somente leitura — para editar, use o painel do Site.")

    df = site.copy()
    if busca_nome:
        df = df[df['cliente'].astype(str).str.contains(busca_nome.strip(), case=False, na=False)]
    if df.empty:
        st.info("Nenhum cliente do Site para essa busca.")
        return

    view = pd.DataFrame({
        "Cliente": df['cliente'].values,
        "Vendedor": df['representante'].values,
        "Produto": df['produto'].values,
        "Administradora": df['administradora'].values,
        "Crédito": df['credito_total'].apply(formatar_brl_puro).values,
        "Status": df['status_label'].values,
        "Ágio": df['agio'].apply(formatar_brl_puro).values,
    })
    if not _eh_master():
        view = view.drop(columns=["Ágio"])      # a margem da Consorbens não é do vendedor
    st.dataframe(view, use_container_width=True, hide_index=True)


def _aniversariantes(df_cli, nomes_ok=None, dias=7):
    """[(nome, 'dd/mm', telefone, em_quantos_dias)] dos próximos `dias` dias (só leitura)."""
    if df_cli is None or df_cli.empty or 'Aniversario' not in df_cli.columns or 'Nome' not in df_cli.columns:
        return []
    hoje = datetime.today().date()
    c = df_cli
    if nomes_ok is not None:
        c = c[c['Nome'].astype(str).str.strip().isin(nomes_ok)]
    # filtro vetorizado: só datas 'dd/mm' que caem nos próximos `dias` dias (sem laço em todos os clientes)
    alvos = {(hoje + timedelta(days=k)).strftime("%d/%m"): k for k in range(dias + 1)}
    dm = c['Aniversario'].astype(str).str.strip().str[:5]
    c = c[dm.isin(alvos.keys())]
    out = []
    for _, r in c.iterrows():
        nome = str(r.get('Nome') or '').strip()
        s = str(r.get('Aniversario')).strip()[:5]
        if nome:
            out.append((nome, s, str(r.get('Telefone') or ''), alvos[s]))
    return sorted(out, key=lambda x: x[3])


def _render_hero_dashboard(df, df_ass, is_master):
    """Saudação + chips do dia. Só apresentação: usa os dados já carregados e o
    mesmo escopo do vendedor (filtrar_por_vendedor)."""
    from modulos.tema import cabecalho, saudacao, data_extenso
    nome = str(st.session_state.get('nome_vendedor') or st.session_state.get('usuario_logado') or '').strip()
    primeiro = nome.split()[0].capitalize() if nome else ""
    chips = []
    if df is not None and not df.empty and 'Data_Real' in df.columns:
        hoje = datetime.today()
        mes = df[df['Data_Real'].notna() & (df['Data_Real'].dt.month == hoje.month) & (df['Data_Real'].dt.year == hoje.year)]
        chips.append((f"{len(mes)} venda(s) neste mês", "ok" if len(mes) else ""))
        atraso = int((df['STATUS'].astype(str).str.strip() == "Em Atraso").sum()) if 'STATUS' in df.columns else 0
        if atraso:
            chips.append((f"{atraso} cota(s) em atraso", "warn"))
    if df_ass is not None and not df_ass.empty and 'data_dt' in df_ass.columns:
        hd = datetime.today().date()
        prox = df_ass[(df_ass['data_dt'].dt.date >= hd) & (df_ass['data_dt'].dt.date <= hd + timedelta(days=7))]
        if not prox.empty:
            chips.append((f"{len(prox)} assembleia(s) em até 7 dias", "info"))
    cabecalho(f"{saudacao()}, {primeiro} 👋" if primeiro else "Dashboard", icone="📊",
              subtitulo="Seu painel de vendas, clientes e pendências — tudo num lugar só.",
              chips=chips, eyebrow=data_extenso())


def _render_painel_do_dia(df, df_cli, is_master):
    """KPIs animados + pendências (cotas em atraso, aniversariantes) + atalhos.
    Só leitura dos dados já carregados; respeita o escopo do vendedor."""
    from modulos.tema import kpis, _esc
    from seguranca import MENU_PARA_PERMISSAO
    hoje = datetime.today()
    vol_mes = vol_ant = 0.0
    n_mes = ativas = atraso = 0
    df_atraso = pd.DataFrame()
    if df is not None and not df.empty and 'Data_Real' in df.columns:
        ok_d = df['Data_Real'].notna()
        mes = df[ok_d & (df['Data_Real'].dt.month == hoje.month) & (df['Data_Real'].dt.year == hoje.year)]
        ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
        ant = df[ok_d & (df['Data_Real'].dt.month == ma) & (df['Data_Real'].dt.year == aa)]
        n_mes, vol_mes, vol_ant = len(mes), float(mes['Valor_Numerico'].sum()), float(ant['Valor_Numerico'].sum())
        stt = df['STATUS'].astype(str).str.strip() if 'STATUS' in df.columns else pd.Series(dtype=str)
        ativas = int(stt.isin(["Em Andamento", "Em Atraso"]).sum())
        atraso = int((stt == "Em Atraso").sum())
        df_atraso = df[stt == "Em Atraso"]
    if vol_ant > 0:
        dv = (vol_mes - vol_ant) / vol_ant * 100
        sub_vol = f'<b class="{"up" if dv >= 0 else "down"}">{"▲" if dv >= 0 else "▼"} {abs(dv):.0f}%</b> vs. mês anterior'
    else:
        sub_vol = _esc(f"{n_mes} cota(s) vendida(s) no mês")
    nomes_ok = None if is_master else set(df['Nome do cliente'].astype(str)) if (df is not None and not df.empty and 'Nome do cliente' in df.columns) else set()
    aniv = _aniversariantes(df_cli, nomes_ok)
    kpis([
        {"rotulo": "Vendido no mês", "valor": vol_mes, "tipo": "brl", "icone": "💼", "sub_html": sub_vol,
         "barra": (vol_mes / vol_ant) if vol_ant > 0 else None},
        {"rotulo": "Cotas no mês", "valor": n_mes, "icone": "🧾", "tom": "info", "sub": "vendas registradas neste mês"},
        {"rotulo": "Carteira ativa", "valor": ativas, "icone": "📦", "tom": "ok", "sub": "cotas em andamento ou em atraso"},
        {"rotulo": "Em atraso", "valor": atraso, "icone": "⏰", "tom": "danger" if atraso else "ok",
         "sub": "precisam de atenção" if atraso else "nenhuma pendência 🎉",
         "barra": (atraso / ativas) if (ativas and atraso) else None},
    ])

    # ---- atalhos rápidos (só telas liberadas para o usuário) ----
    perms = set(st.session_state.get('permissoes') or [])
    atalhos = [("➕ Nova Venda", "Nova Venda"), ("🎯 Ofertar Lance", "Ofertar Lance"),
               ("🧾 Emitir Boletos", "Emissão de Boletos"), ("📑 Relatórios", "Relatórios")]
    atalhos = [a for a in atalhos if is_master or MENU_PARA_PERMISSAO.get(a[1]) in perms]
    if atalhos:
        cols = st.columns(len(atalhos))
        for col, (rot, destino) in zip(cols, atalhos):
            with col:
                if st.button(rot if destino != "Nova Venda" else "Nova Venda", key=f"dash_atalho_{destino}",
                             use_container_width=True, type="primary" if destino == "Nova Venda" else "secondary"):
                    st.session_state['menu_lateral'] = destino
                    st.rerun()

    # ---- pendências: cotas em atraso + aniversariantes ----
    p1, p2 = st.columns(2)
    with p1:
        with st.container(border=True):
            st.markdown(f'<div class="cb-panel-h"><span>⏰ Cotas em atraso</span><span class="cb-chip {"danger" if atraso else "ok"}">{atraso}</span></div>',
                        unsafe_allow_html=True)
            if df_atraso.empty:
                st.markdown('<div class="cb-ok-msg">Tudo em dia por aqui. ✅</div>', unsafe_allow_html=True)
            else:
                for i, (_, r) in enumerate(df_atraso.sort_values('Data_Real', ascending=False).head(4).iterrows()):
                    a, b = st.columns([4, 1.3], vertical_alignment="center")
                    a.markdown(f'<div class="cb-li"><span class="n">{_esc(r.get("Nome do cliente"))}</span>'
                               f'<span class="cb-chip warn">{_esc(r.get("GRUPO"))}/{_esc(r.get("COTA"))}</span></div>', unsafe_allow_html=True)
                    if b.button("Abrir", key=f"dash_atr_{i}", use_container_width=True):
                        st.session_state['cliente_visualizado'] = r.get("Nome do cliente")
                        st.rerun()
                if atraso > 4:
                    st.caption(f"+ {atraso - 4} outra(s) — use a busca abaixo.")
    with p2:
        with st.container(border=True):
            st.markdown(f'<div class="cb-panel-h"><span>🎂 Aniversariantes (7 dias)</span><span class="cb-chip brand">{len(aniv)}</span></div>',
                        unsafe_allow_html=True)
            if not aniv:
                st.markdown('<div class="cb-ok-msg">Nenhum aniversário nos próximos dias.</div>', unsafe_allow_html=True)
            else:
                linhas = []
                for nome, dm, tel, falta in aniv[:5]:
                    quando = "hoje 🎉" if falta == 0 else ("amanhã" if falta == 1 else f"em {falta} dias")
                    dig = "".join(ch for ch in tel if ch.isdigit())
                    zap = (f'<a href="https://wa.me/55{dig}" target="_blank" rel="noopener">WhatsApp ↗</a>'
                           if len(dig) >= 10 else "")
                    linhas.append(f'<div class="cb-li"><span class="n">{_esc(nome)}</span>'
                                  f'<span class="cb-chip {"ok" if falta == 0 else "plain"}">{dm} · {quando}</span>{zap}</div>')
                st.markdown("".join(linhas), unsafe_allow_html=True)


def _render_hero_ficha(cliente_nome, df_cli, df_vendas_global, is_master):
    """Cabeçalho da ficha: iniciais, resumo das cotas (escopo do vendedor) e
    contatos rápidos (WhatsApp / e-mail). Só leitura."""
    from modulos.tema import cabecalho, iniciais, _esc
    chips = []
    if df_vendas_global is not None and not df_vendas_global.empty:
        cc = filtrar_por_vendedor(df_vendas_global[df_vendas_global['Nome do cliente'] == cliente_nome], 'VENDEDOR', eh_adm=is_master)
        if not cc.empty:
            chips.append((f"{len(cc)} cota(s)", "brand"))
            chips.append((formatar_brl_puro(cc['Valor_Numerico'].sum()) + " em cartas", "plain"))
            for stt, tom in (("Em Andamento", "ok"), ("Em Atraso", "warn"), ("Contemplada", "info"), ("Cancelada", "danger")):
                n = int((cc['STATUS'].astype(str).str.strip() == stt).sum())
                if n:
                    chips.append((f"{n} {stt.lower()}", tom))
    tel = email = ""
    if df_cli is not None and not df_cli.empty and 'Nome' in df_cli.columns:
        b = df_cli[df_cli['Nome'] == cliente_nome]
        if not b.empty:
            tel = str(b.iloc[0].get('Telefone') or "")
            email = str(b.iloc[0].get('Email') or "")
    cabecalho(cliente_nome, avatar=iniciais(cliente_nome), eyebrow="Ficha do cliente", chips=chips)
    dig = "".join(ch for ch in tel if ch.isdigit())
    links = []
    if len(dig) >= 10:
        links.append(f'<a class="cb-chip ok" href="https://wa.me/55{dig}" target="_blank" rel="noopener">WhatsApp · {_esc(tel)}</a>')
    if email and "@" in email and email.lower() not in ("nan", "none"):
        links.append(f'<a class="cb-chip info" href="mailto:{_esc(email)}">{_esc(email)}</a>')
    if links:
        st.markdown(f'<div class="cb-chiprow">{"".join(links)}</div>', unsafe_allow_html=True)


def render_dashboard(supabase, df_vendas_global, df_cli, df_ass, lista_admin_bd, df_admin, status_dict, cfg):
    is_master = (st.session_state.get('perfil_logado') == "Master") or (st.session_state.get('usuario_logado') in ['breno', 'uriel'])
    if st.session_state.get('_aviso_lixeira'):
        st.warning(st.session_state.pop('_aviso_lixeira'))

    # Cabeçalho com saudação + pulso do dia (só na visão geral; a ficha tem o próprio)
    _df_escopo = None
    if st.session_state.get('cliente_visualizado') is None:
        # mesmo escopo da lista (vendedor só vê o que é dele); calculado 1x e reaproveitado no painel do dia
        _df_escopo = filtrar_por_vendedor(df_vendas_global, 'VENDEDOR', eh_adm=is_master) if not df_vendas_global.empty else df_vendas_global
        _render_hero_dashboard(_df_escopo, df_ass, is_master)

    # Resumo do mês (Tradicional + Cotas Contempladas) — só Master, valores sensíveis
    if is_master:
        _render_resumo_mes(supabase, df_vendas_global, df_admin, cfg, status_dict)

    # Alerta de Assembleias
    hoje_date = datetime.today().date()
    if not df_ass.empty:
        df_prox = df_ass[(df_ass['data_dt'].dt.date >= hoje_date) & (df_ass['data_dt'].dt.date <= hoje_date + timedelta(days=3))]
        if not df_prox.empty:
            alertas = [f"**{r['descricao']}** ({r['data_dt'].strftime('%d/%m')})" for _, r in df_prox.iterrows()]
            st.warning(f"📅 **Atenção para as Assembleias nos próximos dias:** {' | '.join(alertas)}")

    # ==========================================
    # VISÃO DETALHADA DO CLIENTE
    # ==========================================
    if st.session_state['cliente_visualizado'] is not None:
        cliente_nome = st.session_state['cliente_visualizado']
        _render_hero_ficha(cliente_nome, df_cli, df_vendas_global, is_master)

        if st.button("⬅️ Voltar ao Dashboard", type="primary"):
            st.session_state['cliente_visualizado'] = None
            st.session_state['key_tabela'] += 1
            st.rerun()
            
        info_cliente, id_cliente_db = {}, None
        if not df_cli.empty and 'Nome' in df_cli.columns:
            busca_cli = df_cli[df_cli['Nome'] == cliente_nome]
            if not busca_cli.empty: 
                info_cliente, id_cliente_db = busca_cli.iloc[0].to_dict(), busca_cli.iloc[0].get('id')

        if not is_master: 
            st.info("🔒 Como Vendedor, você só pode visualizar estes dados. Para alterar, contate o Administrador.")
            
        def safe_str(val, default=""):
            if pd.isna(val) or val is None or str(val).strip().lower() in ["nan", "nat", "none"]: return default
            return str(val)

        key_nome = f"n_{cliente_nome}"
        key_tel = f"t_{cliente_nome}"
        key_email = f"e_{cliente_nome}"
        key_end = f"en_{cliente_nome}"
        key_aniv = f"a_{cliente_nome}"
        key_prof = f"p_{cliente_nome}"
        key_renda = f"r_{cliente_nome}"
        key_cpf = f"cpf_{cliente_nome}"

        if key_nome not in st.session_state: st.session_state[key_nome] = safe_str(info_cliente.get("Nome"), cliente_nome)
        if key_cpf not in st.session_state: st.session_state[key_cpf] = safe_str(info_cliente.get("CPF"))
        if key_tel not in st.session_state: st.session_state[key_tel] = safe_str(info_cliente.get("Telefone"))
        if key_email not in st.session_state: st.session_state[key_email] = safe_str(info_cliente.get("Email"))
        if key_end not in st.session_state: st.session_state[key_end] = safe_str(info_cliente.get("Endereco"))
        if key_aniv not in st.session_state: st.session_state[key_aniv] = safe_str(info_cliente.get("Aniversario"))
        if key_prof not in st.session_state: st.session_state[key_prof] = safe_str(info_cliente.get("Profissao"))
        if key_renda not in st.session_state: st.session_state[key_renda] = safe_str(info_cliente.get("Renda"))
            
        nome_edit = st.text_input("Nome Completo", key=key_nome, disabled=not is_master)
        
        if is_master:
            col_cep_1, col_cep_2 = st.columns([1, 3])
            with col_cep_1:
                cep_busca = st.text_input("Buscar CEP p/ Endereço", key=f"cep_ed_{cliente_nome}", max_chars=9)
            if cep_busca and cep_busca != st.session_state.get(f'last_cep_ed_{cliente_nome}', ''):
                cep_limpo = ''.join(filter(str.isdigit, cep_busca))
                if len(cep_limpo) == 8:
                    try:
                        res = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
                        if res.status_code == 200 and "erro" not in res.json():
                            d_cep = res.json()
                            st.session_state[key_end] = f"{d_cep.get('logradouro','')}, Nº , {d_cep.get('bairro','')}, {d_cep.get('localidade','')}-{d_cep.get('uf','')} (CEP: {cep_busca})"
                            st.rerun()
                    except: pass
                st.session_state[f'last_cep_ed_{cliente_nome}'] = cep_busca
        
        c1, c2 = st.columns(2)
        with c1:
            cpf_edit = st.text_input("CPF", key=key_cpf, on_change=lambda: st.session_state.update({key_cpf: formatar_cpf(st.session_state[key_cpf])}), disabled=not is_master, placeholder="000.000.000-00", max_chars=14)
            endereco = st.text_input("Endereço Completo", key=key_end, disabled=not is_master)
            telefone_edit = st.text_input("Telefone", key=key_tel, on_change=lambda: st.session_state.update({key_tel: formatar_telefone(st.session_state[key_tel])}), disabled=not is_master)
            profissao_edit = st.text_input("Profissão", key=key_prof, disabled=not is_master)
        with c2:
            email = st.text_input("Email", key=key_email, disabled=not is_master)
            aniversario_edit = st.text_input("Data de Aniversário (DD/MM/AAAA)", key=key_aniv, on_change=lambda: st.session_state.update({key_aniv: formatar_data(st.session_state[key_aniv])}), disabled=not is_master, placeholder="DD/MM/AAAA")
            renda_edit = st.text_input("Renda Mensal (R$)‍", key=key_renda, on_change=lambda: st.session_state.update({key_renda: formatar_moeda(st.session_state[key_renda])}), disabled=not is_master)
        
        if is_master:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Salvar Alterações Cadastrais", type="primary", use_container_width=True):
                    dados_cli = {
                        "Nome": st.session_state[key_nome], "CPF": st.session_state[key_cpf], "Telefone": st.session_state[key_tel], "Email": st.session_state[key_email],
                        "Endereco": st.session_state[key_end], "Aniversario": st.session_state[key_aniv], "Profissao": st.session_state[key_prof], "Renda": st.session_state[key_renda]
                    }
                    try:
                        if id_cliente_db: supabase.table("clientes").update(dados_cli).eq("id", int(id_cliente_db)).execute()
                        else:
                            dados_cli["Data_Cadastro"] = datetime.today().strftime("%d/%m/%Y")
                            supabase.table("clientes").insert([dados_cli]).execute()
                        
                        if st.session_state[key_nome] != cliente_nome:
                            supabase.table("vendas").update({"NOME": st.session_state[key_nome]}).eq("NOME", cliente_nome).execute()
                            st.session_state['cliente_visualizado'] = st.session_state[key_nome]
                        carregar_dados_iniciais.clear()
                        st.success("Dados atualizados com sucesso!"); st.rerun()
                    except Exception as e: st.error(f"❌ Erro ao salvar: {e}")

            with col_b2:
                # Proteção: confirmação explícita, apaga as cotas pelo ID (não pelo nome)
                # e guarda cópia de tudo na lixeira (Configurações → Backup e Lixeira).
                _ids_cotas_cli = (df_vendas_global.loc[df_vendas_global['Nome do cliente'] == cliente_nome, 'id'].tolist()
                                  if (not df_vendas_global.empty and 'id' in df_vendas_global.columns) else [])
                _conf_cli = st.checkbox(f"Confirmo apagar o cliente e as {len(_ids_cotas_cli)} cota(s) dele",
                                        key=f"conf_del_cli_{cliente_nome}")
                if st.button("🚨 Excluir Cliente (Apagar Todas as Cotas)", use_container_width=True, disabled=not _conf_cli):
                    try:
                        from auditoria import apagar_com_lixeira
                        _motivo = f"Dashboard: excluir cliente {cliente_nome}"
                        _nv, _av1 = apagar_com_lixeira(supabase, "vendas", _ids_cotas_cli, _motivo)
                        _av2 = None
                        if id_cliente_db:
                            _nc, _av2 = apagar_com_lixeira(supabase, "clientes", [id_cliente_db], _motivo)
                        carregar_dados_iniciais.clear()
                        if _av1 or _av2:
                            st.session_state['_aviso_lixeira'] = _av1 or _av2
                        st.session_state['cliente_visualizado'] = None; st.session_state['key_tabela'] += 1; st.rerun()
                    except Exception as e:
                        carregar_dados_iniciais.clear()
                        st.error(f"❌ Não apaguei o cliente: {e}")

        st.divider()
        st.subheader("📦 Cotas do Cliente")
        if not df_vendas_global.empty:
            cotas_cliente = df_vendas_global[df_vendas_global['Nome do cliente'] == cliente_nome].copy()
            cotas_cliente = filtrar_por_vendedor(cotas_cliente, 'VENDEDOR', eh_adm=is_master)   # só as cotas dele
            if not cotas_cliente.empty:
                info_a, info_b = st.columns(2)
                info_a.metric("Total de Cotas Adquiridas", len(cotas_cliente))
                info_b.metric("Volume Total Investido", formatar_brl_puro(cotas_cliente['Valor_Numerico'].sum()))
                
                cotas_cliente['Valor Formatado'] = cotas_cliente['Valor_Numerico'].apply(formatar_brl_puro)
                cotas_cliente['Data da Venda'] = cotas_cliente['Data_Real'].apply(formatar_data_br)
                
                ficha_display = cotas_cliente[['Data da Venda', 'ADMINISTRADORA', 'PRODUTO', 'GRUPO', 'COTA', 'Valor Formatado', 'STATUS', 'VENDEDOR']].rename(columns={'ADMINISTRADORA': 'Administradora', 'PRODUTO': 'Produto', 'GRUPO': 'Grupo', 'COTA': 'Cota', 'Valor Formatado': 'Valor (R$)', 'STATUS': 'Status', 'VENDEDOR': 'Vendedor'})
                estilo_ficha = ficha_display.style.set_properties(**{'text-align': 'center'}).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                st.dataframe(estilo_ficha, use_container_width=True, hide_index=True)

                # --- Adicionar nova cota a ESTE cliente (reaproveita o cadastro) ---
                if is_master:
                    with st.expander("➕ Adicionar Nova Cota a este Cliente", expanded=False):
                        st.caption("Inclui só a cota — o cadastro do cliente já existe e é reaproveitado. "
                                   "A cota entra automaticamente neste mesmo perfil.")
                        kp = f"addcota_{cliente_nome}_"
                        opts_v_add = ["BRENO LIMA", "URIEL GOMES", "Particular Breno", "Particular Uriel", "Consorbens", "Vendedor Terceiro"]
                        from database import vendedores_cadastrados as _vc
                        opts_v_add += [v for v in _vc(supabase) if v not in opts_v_add]
                        lista_prod_add = ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"]
                        ca1, ca2, ca3 = st.columns(3)
                        with ca1:
                            add_data = st.date_input("Data da Venda", format="DD/MM/YYYY", key=kp + "data")
                            add_grupo = st.text_input("Grupo *", key=kp + "grupo")
                        with ca2:
                            add_vend = st.selectbox("Vendedor *", opts_v_add, key=kp + "vend")
                            add_cota = st.text_input("Cota *", key=kp + "cota")
                        with ca3:
                            add_admin = st.selectbox("Administradora *", lista_admin_bd, key=kp + "admin")
                            add_valor = input_valor("Valor da Carta (R$) *", key=kp + "valor")
                        add_produto = st.selectbox("Tipo do Bem *", lista_prod_add, key=kp + "prod")

                        if st.button("➕ Salvar Nova Cota", type="primary", use_container_width=True, key=kp + "btn"):
                            g, c = str(add_grupo).strip(), str(add_cota).strip()
                            if not g or not c or add_valor <= 0:
                                st.error("❌ Preencha Grupo, Cota e um Valor maior que zero.")
                            elif ((df_vendas_global['GRUPO'].astype(str).str.strip() == g) &
                                  (df_vendas_global['COTA'].astype(str).str.strip() == c)).any():
                                dono = df_vendas_global[(df_vendas_global['GRUPO'].astype(str).str.strip() == g) &
                                                        (df_vendas_global['COTA'].astype(str).str.strip() == c)].iloc[0]['Nome do cliente']
                                st.error(f"❌ Já existe a cota {g}/{c} (cadastrada em '{dono}'). "
                                         "Para mudar algo nela, use '⚙️ Atualizar Status, Data e Gerenciar Cota'.")
                            else:
                                try:
                                    supabase.table("vendas").insert([{
                                        "NOME": cliente_nome,   # texto idêntico ao do perfil → cota cai neste cliente
                                        "DATA": add_data.strftime("%d/%m/%Y"),
                                        "PRODUTO": add_produto,
                                        "VENDEDOR": add_vend,
                                        "GRUPO": g,
                                        "COTA": c,
                                        "ADMINISTRADORA": add_admin,
                                        "STATUS": "Em Andamento",
                                        "TIPO_PRODUTO": "Consórcio Tradicional",
                                        "VALOR": float(add_valor),
                                    }]).execute()
                                    carregar_dados_iniciais.clear()
                                    st.success(f"✅ Cota {g}/{c} adicionada ao perfil de {cliente_nome}!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Erro ao salvar a cota: {e}")

                with st.expander("⚙️ Atualizar Status, Data e Gerenciar Cota", expanded=False):
                    opcoes_cotas = cotas_cliente.apply(lambda r: f"ID:{r['id']} | Grupo: {r['GRUPO']} / Cota: {r['COTA']} - Valor: {r['Valor Formatado']}", axis=1).tolist()
                    c_sel, _ = st.columns([3, 1])
                    with c_sel: cota_selecionada = st.selectbox("Selecione a cota que deseja gerenciar:", [""] + opcoes_cotas)
                        
                    if cota_selecionada:
                        id_cota = int(cota_selecionada.split(" | ")[0].replace("ID:", ""))
                        cota_info = cotas_cliente[cotas_cliente['id'] == id_cota].iloc[0]
                        
                        vendedor_atual = cota_info['VENDEDOR']
                        status_atual = cota_info['STATUS']
                        data_atual_str = cota_info['DATA']
                        grupo_atual = cota_info['GRUPO']
                        cota_atual = cota_info['COTA']
                        valor_atual = cota_info['Valor_Numerico']
                        admin_atual = cota_info['ADMINISTRADORA']
                        produto_atual = cota_info['PRODUTO']
                        
                        opcoes_status = ["Em Andamento", "Em Atraso", "Cancelada", "Contemplada"]
                        if status_atual not in opcoes_status:
                            status_atual = "Em Andamento"
                        
                        try:
                            data_atual_obj = pd.to_datetime(data_atual_str, format="%d/%m/%Y", errors='coerce').date()
                            if pd.isna(data_atual_obj): data_atual_obj = datetime.today().date()
                        except:
                            data_atual_obj = datetime.today().date()
                        
                        # --- LINHA 1 ---
                        c_ed1, c_ed2, c_ed3 = st.columns(3)
                        with c_ed1: novo_status = st.selectbox("Status", opcoes_status, index=opcoes_status.index(status_atual), disabled=not is_master)
                        with c_ed2:
                            from database import vendedores_cadastrados as _vc_ed
                            opts_v = ["BRENO LIMA", "URIEL GOMES", "Particular Breno", "Particular Uriel", "Consorbens", "Vendedor Terceiro"]
                            opts_v += [v for v in _vc_ed(supabase) if v not in opts_v]
                            _sem_vend = (vendedor_atual is None) or (str(vendedor_atual).strip() in ("", "None", "nan"))
                            if _sem_vend: opts_v.insert(0, "")                     # cota sem vendedor continua sem vendedor
                            elif vendedor_atual not in opts_v: opts_v.append(vendedor_atual)   # nunca troca o vendedor sem querer
                            novo_vendedor = st.selectbox("Vendedor", opts_v, index=(0 if _sem_vend else (opts_v.index(vendedor_atual) if vendedor_atual in opts_v else 0)), format_func=lambda x: x or "(sem vendedor)") if is_master else st.text_input("Vendedor", value=vendedor_atual, disabled=True)
                        with c_ed3: nova_data = st.date_input("Data da Venda", value=data_atual_obj, format="DD/MM/YYYY") if is_master else st.text_input("Data da Venda", value=formatar_data_br(cota_info['Data_Real']), disabled=True)

                        # --- LINHA 2 ---
                        c_ed4, c_ed5, c_ed6 = st.columns(3)
                        with c_ed4: novo_grupo = st.text_input("Grupo", value=grupo_atual, disabled=not is_master)
                        with c_ed5: nova_cota = st.text_input("Cota", value=cota_atual, disabled=not is_master)
                        with c_ed6: novo_valor = input_valor("Valor da Carta (R$)", value=float(valor_atual) if pd.notna(valor_atual) else 0.0, key=f"vc_cota_{id_cota}", disabled=not is_master)
                                
                        # --- LINHA 3 ---
                        c_ed7, c_ed8 = st.columns(2)
                        with c_ed7:
                            try: idx_admin = lista_admin_bd.index(admin_atual)
                            except ValueError: idx_admin = 0
                            nova_admin = st.selectbox("Administradora", options=lista_admin_bd, index=idx_admin, disabled=not is_master)
                            
                        with c_ed8:
                            lista_produtos = ["Auto", "Imóvel", "Moto", "Caminhão", "Serviços"]
                            try: idx_produto = lista_produtos.index(produto_atual)
                            except ValueError: idx_produto = 0
                            novo_produto = st.selectbox("Tipo do Bem", options=lista_produtos, index=idx_produto, disabled=not is_master)

                        # Cancelada: a data do cancelamento define se o vendedor é estornado (até 5 meses da venda)
                        nova_data_canc = ""
                        if novo_status == "Cancelada":
                            _dc_atual = cv.data_cancelamento(cota_info.get('DATA_CANCELAMENTO'))
                            if is_master:
                                # sem data cadastrada o campo vem vazio: nada é inventado ao salvar
                                _dc_val = st.date_input("Data do cancelamento", value=(_dc_atual.date() if not pd.isna(_dc_atual) else None),
                                    format="DD/MM/YYYY",
                                    help="Se foi até 5 meses depois da venda, o vendedor é estornado em 0,5% do crédito, em 2 parcelas.")
                                nova_data_canc = _dc_val.strftime("%d/%m/%Y") if _dc_val else ""
                                if not _dc_val:
                                    st.caption("⚠️ Informe a data do cancelamento para calcular o estorno do vendedor.")
                            elif not pd.isna(_dc_atual):
                                nova_data_canc = _dc_atual.strftime("%d/%m/%Y")
                            if pd.isna(_dc_atual) and not is_master:
                                st.caption("Cota cancelada — a data do cancelamento é informada pelo administrador.")

                        _tp_opts = ["Linear", "Reduzida"]
                        _tp_atual = str(cota_info.get('TIPO_PARCELA') or "Linear").strip().capitalize()
                        if _tp_atual not in _tp_opts: _tp_atual = "Linear"
                        novo_tipo_parcela = st.selectbox(
                            "Tipo de Parcela", options=_tp_opts, index=_tp_opts.index(_tp_atual),
                            disabled=not is_master,
                            help="Muda a regra de comissão em administradoras com percentual "
                                 "diferente por tipo de parcela (ex.: Itaú imóvel linear = 4% "
                                 "em 8; reduzida = 4% em 12).")

                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if is_master and st.button("💾 Salvar Alterações na Cota", type="primary", use_container_width=True):   # vendedor não grava nada na cota (campos já vêm desabilitados)
                                data_formatada = nova_data.strftime("%d/%m/%Y") if not isinstance(nova_data, str) else nova_data
                                
                                dados_atualizados = {
                                    "VENDEDOR": novo_vendedor,
                                    "STATUS": novo_status,
                                    "DATA": data_formatada,
                                    "GRUPO": novo_grupo,
                                    "COTA": nova_cota,
                                    "VALOR": novo_valor,
                                    "ADMINISTRADORA": nova_admin,
                                    "PRODUTO": novo_produto,
                                    "TIPO_PARCELA": novo_tipo_parcela
                                }
                                if is_master:
                                    dados_atualizados["DATA_CANCELAMENTO"] = (nova_data_canc or None) if novo_status == "Cancelada" else None
                                try:
                                    try:
                                        supabase.table("vendas").update(dados_atualizados).eq("id", id_cota).execute()
                                    except Exception:
                                        if "DATA_CANCELAMENTO" not in dados_atualizados: raise
                                        dados_atualizados.pop("DATA_CANCELAMENTO")
                                        supabase.table("vendas").update(dados_atualizados).eq("id", id_cota).execute()
                                        st.warning("A data do cancelamento não foi salva: rode a migração 29 no Supabase.")
                                    carregar_dados_iniciais.clear()
                                    st.success("Cota atualizada com sucesso!"); st.rerun()
                                except Exception as e:
                                    st.error(f"❌ A cota NÃO foi salva: {e}")
                        with col_b2:
                            _conf_cota = is_master and st.checkbox(f"Confirmo apagar a cota {grupo_atual}/{cota_atual}",
                                                                   key=f"conf_del_cota_{id_cota}")
                            if is_master and st.button("🚨 Apagar Esta Cota", use_container_width=True, disabled=not _conf_cota):
                                try:
                                    from auditoria import apagar_com_lixeira
                                    _n, _av = apagar_com_lixeira(supabase, "vendas", [id_cota],
                                                                 f"Dashboard: apagar cota {grupo_atual}/{cota_atual} de {cliente_nome}")
                                    carregar_dados_iniciais.clear()
                                    if _av:
                                        st.session_state['_aviso_lixeira'] = _av
                                    st.success("Cota apagada com sucesso!"); st.rerun()
                                except Exception as e:
                                    carregar_dados_iniciais.clear()
                                    st.error(f"❌ Não apaguei a cota: {e}")

                st.subheader("📈 Previsão de Comissionamento")
                df_parcelas, vendas_sem_data = gerar_tabela_parcelas(cotas_cliente, df_vendas_global, df_admin, cfg, status_dict)
                if vendas_sem_data: st.warning(f"⚠️ Algumas vendas estão sem data: {', '.join(vendas_sem_data)}")

                if not df_parcelas.empty:
                    df_view_cli = df_parcelas[df_parcelas['Vendedor Recebe'] != 0].copy() if not is_master else df_parcelas.copy()
                    if not df_view_cli.empty:
                        for col in ['Valor da Venda', 'Comissão (Bruta)', 'Comissão (s/ Imposto)', 'Breno', 'Uriel', 'Vendedor Recebe']: df_view_cli[col] = df_view_cli[col].apply(formatar_brl_puro)
                        df_view_cli['% Vendedor'] = df_view_cli['% Vendedor'].apply(lambda x: "" if pd.isna(x) else f"{x:.2f}%".replace(".", ","))
                        df_view_cli = df_view_cli.rename(columns={'Tipo Vendedor': 'Tipo (vendedor)', 'Parcela Vendedor': 'Parc. vendedor', '% Vendedor': '% vend.'})
                        
                        c_conf = {
                            "Chave": None, 
                            "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "PAGO"], required=True) if is_master else st.column_config.TextColumn("Status", disabled=True),
                            "Data Recebimento": st.column_config.TextColumn("Data Recebimento", disabled=not is_master)
                        }
                        c_hide = ['Cliente', 'Produto', 'Vendedor', 'data_pagamento_dt'] + (["Comissão (Bruta)", "Comissão (s/ Imposto)", "Breno", "Uriel"] if not is_master else [])
                        df_final_cli = df_view_cli.drop(columns=c_hide).reset_index(drop=True)
                        
                        cols_editaveis_cli = ["Status", "Data Recebimento"] if is_master else []
                        
                        st.caption("Dica: Clique em 'Status' ou 'Data Recebimento' para alterar. Em seguida, salve no botão.")
                        edited_df_cli = st.data_editor(df_final_cli, disabled=[c for c in df_final_cli.columns if c not in cols_editaveis_cli], column_config=c_conf, use_container_width=True, hide_index=True)
                        
                        if is_master and st.button("💾 Salvar Status de Pagamento (Cliente)", type="primary"):
                            if salvar_status_comissoes(supabase, edited_df_cli, df_final_cli): 
                                st.success("Atualizados!")
                                st.rerun()
                else: st.info("Aguardando configurações de regras para gerar a previsão.")
            else: st.warning("Nenhuma cota encontrada.")

    # ==========================================
    # VISÃO GLOBAL (LISTA DE VENDAS E GRÁFICOS)
    # ==========================================
    else:
        # Controle de produção mensal, nível de comissão e extrato — do próprio vendedor
        if not is_master:
            from modulos.producao_vendedor import render_producao_vendedor
            render_producao_vendedor(df_vendas_global, df_admin, cfg, status_dict,
                                     st.session_state.get('nome_vendedor') or "", chave="pv_dash")
            st.divider()
        df_view = df_vendas_global.copy()
        df_view = filtrar_por_vendedor(df_view, 'VENDEDOR', eh_adm=is_master)

        # Painel do dia: KPIs animados, atalhos (inclui o botão "Nova Venda") e pendências
        _render_painel_do_dia(_df_escopo, df_cli, is_master)

        from modulos.tema import secao
        secao("Clientes e vendas", "🔎", "Filtre, busque e clique numa linha para abrir a ficha do cliente.")

        c_f1, c_f2, c_f3, c_f4, c_f5 = st.columns([1.3, 1.3, 0.9, 0.9, 1.3])
        with c_f1:
            ft_cli = st.selectbox("⏳ Filtro:", ["Últimos 5 Cadastros", "Todos os Clientes", "Mês Atual", "Mês Anterior", "Ano Atual", "Período Personalizado"])
            if ft_cli == "Período Personalizado":
                cd1, cd2 = st.columns(2)
                with cd1: p_ini = st.date_input("Início", format="DD/MM/YYYY")
                with cd2: p_fim = st.date_input("Fim", format="DD/MM/YYYY")
        with c_f2: busca_nome = st.text_input("🔍 Buscar Cliente:")
        with c_f3: busca_grupo = st.text_input("📦 Grupo:")
        with c_f4: busca_cota = st.text_input("🔢 Cota:")
        with c_f5: ft_tipo = st.selectbox("🏷️ Tipo:", ["Todos", "Consórcio Tradicional", "Consórcio Contemplado"])

        hoje = datetime.today()
        df_view = df_view.sort_values(by="Data_Real", ascending=False)
        
        if ft_cli == "Últimos 5 Cadastros" and not (busca_nome or busca_grupo or busca_cota): df_view = df_view.head(5)
        elif ft_cli != "Todos os Clientes" and ft_cli != "Últimos 5 Cadastros":
            mask = df_view['Data_Real'].notna()
            if ft_cli == "Mês Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.month == hoje.month) & (df_view['Data_Real'].dt.year == hoje.year)]
            elif ft_cli == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_view = df_view[mask & (df_view['Data_Real'].dt.month == ma) & (df_view['Data_Real'].dt.year == aa)]
            elif ft_cli == "Ano Atual": df_view = df_view[mask & (df_view['Data_Real'].dt.year == hoje.year)]
            elif ft_cli == "Período Personalizado": df_view = df_view[mask & (df_view['Data_Real'].dt.date >= p_ini) & (df_view['Data_Real'].dt.date <= p_fim)]

        if busca_nome: df_view = df_view[df_view['Nome do cliente'].astype(str).str.contains(busca_nome.strip(), case=False, na=False)]
        if busca_grupo: df_view = df_view[df_view['GRUPO'].astype(str).str.contains(busca_grupo.strip(), case=False, na=False)]
        if busca_cota: df_view = df_view[df_view['COTA'].astype(str).str.contains(busca_cota.strip(), case=False, na=False)]
        if ft_tipo != "Todos": df_view = df_view[df_view['TIPO_PRODUTO'] == ft_tipo]

        if not df_view.empty:
            st.write("Clique em uma linha para ver os detalhes do cliente:")
            df_tab = df_view.copy()
            df_tab['Grupo e Cota'] = df_tab.apply(lambda x: f"{x['GRUPO']}/{x['COTA']}", axis=1)
            df_tab['Valor Formatado'] = df_tab['Valor_Numerico'].apply(formatar_brl_puro)
            df_tab['Data da Venda'] = df_tab['Data_Real'].apply(formatar_data_br)

            df_tab = df_tab[['Nome do cliente', 'PRODUTO', 'ADMINISTRADORA', 'Grupo e Cota', 'VENDEDOR', 'Valor Formatado', 'Data da Venda']]
            df_tab.columns = ['Cliente', 'Produto', 'Administradora', 'Grupo/Cota', 'Vendedor', 'Valor', 'Data da Venda']

            tabela = st.dataframe(df_tab, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
            if hasattr(tabela, 'selection') and tabela.selection.rows:
                st.session_state['cliente_visualizado'] = df_tab.iloc[tabela.selection.rows[0]]['Cliente']; st.rerun()

            st.divider()
            m1, m2, m3 = st.columns(3)
            vol_total = df_view['Valor_Numerico'].sum()
            m1.metric("Volume Total (Filtro)", formatar_brl_puro(vol_total))
            m2.metric("Qtd. Cotas (Filtro)", len(df_view))
            m3.metric("Ticket Médio", formatar_brl_puro(vol_total/len(df_view) if len(df_view)>0 else 0))
        else:
            from modulos.tema import estado_vazio
            estado_vazio("Nenhuma venda encontrada.", "Tente outro período no filtro ou limpe a busca para ver todos os clientes.", "🔍")

        # ---- Cartas Contempladas vindas do SITE (só leitura) ----
        # Fora do "if not df_view.empty" de propósito: o filtro de Tipo/Grupo/Cota
        # acima é só da tabela de VENDAS do ERP — as cartas contempladas do site
        # têm vida própria e sempre têm que aparecer, mesmo com 0 vendas no filtro.
        _render_cartas_site(busca_nome)

        st.write("")
        from modulos.tema import secao, tema_atual
        secao("Gráficos Globais (Filtro Independente)", "📊", "Distribuição das vendas por produto e por administradora.")
        _pal = [tema_atual()["brand"], "#f59e0b", "#6366f1", "#0ea5e9", "#ef4444", "#a855f7", "#14b8a6", "#64748b"]
        g_f1, g_f2 = st.columns(2)
        with g_f1:
            ft_graf = st.selectbox("⏳ Período para o Gráfico:", ["Mês Atual", "Mês Anterior", "Anual", "Todas as Vendas", "Período Personalizado"])
            if ft_graf == "Período Personalizado":
                cg1, cg2 = st.columns(2)
                with cg1: gi = st.date_input("Início", format="DD/MM/YYYY", key="g_ini")
                with cg2: gf = st.date_input("Fim", format="DD/MM/YYYY", key="g_fim")
        with g_f2: fp_graf = st.selectbox("📦 Produto:", ["Todos", "Auto", "Imóvel", "Moto", "Caminhão", "Serviços"])

        df_g = df_vendas_global.copy()
        df_g = filtrar_por_vendedor(df_g, 'VENDEDOR', eh_adm=is_master)
        if ft_graf != "Todas as Vendas" and not df_g.empty:
            mask = df_g['Data_Real'].notna()
            if ft_graf == "Mês Atual": df_g = df_g[mask & (df_g['Data_Real'].dt.month == hoje.month) & (df_g['Data_Real'].dt.year == hoje.year)]
            elif ft_graf == "Mês Anterior":
                ma, aa = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
                df_g = df_g[mask & (df_g['Data_Real'].dt.month == ma) & (df_g['Data_Real'].dt.year == aa)]
            elif ft_graf == "Anual": df_g = df_g[mask & (df_g['Data_Real'].dt.year == hoje.year)]
            elif ft_graf == "Período Personalizado": df_g = df_g[mask & (df_g['Data_Real'].dt.date >= gi) & (df_g['Data_Real'].dt.date <= gf)]

        if fp_graf != "Todos" and not df_g.empty:
            df_g = df_g[df_g['PRODUTO'].apply(normalizar_produto) == normalizar_produto(fp_graf)]

        if not df_g.empty:
            cg1, cg2 = st.columns(2)
            with cg1:
                st.markdown("#### Vendas por Produto")
                df_p = df_g['PRODUTO'].value_counts().reset_index()
                df_p.columns = ['Produto', 'Quantidade']
                st.altair_chart(alt.Chart(df_p).mark_arc(innerRadius=62, cornerRadius=6, padAngle=0.02).encode(theta='Quantidade', color=alt.Color('Produto', scale=alt.Scale(range=_pal)), tooltip=['Produto', 'Quantidade']).configure_view(strokeWidth=0), use_container_width=True)
            with cg2:
                st.markdown("#### Vendas por Administradora")
                df_a = df_g['ADMINISTRADORA'].value_counts().reset_index()
                df_a.columns = ['Administradora', 'Quantidade']
                st.altair_chart(alt.Chart(df_a).mark_arc(innerRadius=62, cornerRadius=6, padAngle=0.02).encode(theta='Quantidade', color=alt.Color('Administradora', scale=alt.Scale(range=_pal)), tooltip=['Administradora', 'Quantidade']).configure_view(strokeWidth=0), use_container_width=True)
