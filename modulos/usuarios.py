"""
Configurações → 👥 Usuários e acessos  (só Administrador).

Cadastro fácil de vendedores (e administradores), com:
  • senha criptografada (hash) — a senha temporária aparece UMA vez, na hora;
  • escolha de quais telas/simuladores cada vendedor pode ver;
  • opção de liberar também o login do ADMIN do site de cartas contempladas
    (mesmo e-mail e senha do ERP).
"""
import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from database import (iniciar_conexao_site, carregar_sessao_usuario,
                      vendedores_cadastrados, carregar_dados_iniciais)
from seguranca import (PERMISSOES, MODELOS_PERMISSAO, PERMISSOES_PADRAO_VENDEDOR,
                       PERFIL_ADMIN, PERFIL_VENDEDOR, ROTULO_PERFIL,
                       hash_senha, gerar_senha_temporaria, validar_forca)
from site_usuarios import sincronizar_site
from cadastro import (so_digitos, validar_cnpj, validar_cpf, fmt_cnpj, fmt_cpf, fmt_tel, fmt_cep)

OPCAO_NOVO = "➕ Criar novo usuário"
LOGINS_SOCIOS = {"breno", "uriel"}
NOMES_RESERVADOS = {"BRENO LIMA", "URIEL GOMES", "CONSORBENS", "PARTICULAR BRENO",
                    "PARTICULAR URIEL", "VENDEDOR TERCEIRO"}
COLUNAS_NOVAS = "senha_hash,permissoes,ativo,acesso_site_admin,site_user_id,trocar_senha,email"
COLUNAS_DADOS = ("razao_social,cnpj,cpf,telefone,endereco,cidade,uf,cep,pix,regime,local_atuacao,"
                 "data_inicio,observacoes")
REGIMES = ["", "Simples Nacional (ME/EPP)", "MEI", "Lucro Presumido", "Outro"]
LOCAIS = ["", "Loja Santa Luzia", "Externo / home office"]
OBRIGATORIOS_PJ = {"razao_social": "razão social", "cnpj": "CNPJ", "telefone": "telefone",
                   "endereco": "endereço", "pix": "chave PIX"}


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _migracao_ok(supabase) -> bool:
    try:
        supabase.table("usuarios").select(COLUNAS_NOVAS).limit(1).execute()
        return True
    except Exception:
        return False


def _dados_ok(supabase) -> bool:
    """True se a migração 27 (dados cadastrais do vendedor) já foi aplicada."""
    try:
        supabase.table("usuarios").select(COLUNAS_DADOS).limit(1).execute()
        return True
    except Exception:
        return False


def _usuarios(supabase, com_dados=False):
    try:
        cols = "id,login,nome,perfil,email,ativo,permissoes,acesso_site_admin,site_user_id,ultimo_login,trocar_senha"
        if com_dados:
            cols += "," + COLUNAS_DADOS
        return supabase.table("usuarios").select(cols).order("id").execute().data or []
    except Exception:
        return []


def _faltantes(u):
    """Dados obrigatórios do vendedor PJ que ainda não foram preenchidos."""
    return [rot for k, rot in OBRIGATORIOS_PJ.items() if not str(u.get(k) or "").strip()]


def _campos_dados(prefixo, d=None):
    """Bloco 'Dados do vendedor (PJ)'. Devolve os valores digitados (crus)."""
    d = d or {}
    st.markdown("**Dados do vendedor (PJ)** — para contrato, nota fiscal e pagamento")
    c1, c2 = st.columns(2)
    razao = c1.text_input("Razão social / nome empresarial", value=d.get("razao_social") or "", key=f"{prefixo}_razao")
    cnpj = c2.text_input("CNPJ", value=fmt_cnpj(d.get("cnpj")), key=f"{prefixo}_cnpj", placeholder="00.000.000/0000-00")
    c3, c4 = st.columns(2)
    cpf = c3.text_input("CPF do responsável", value=fmt_cpf(d.get("cpf")), key=f"{prefixo}_cpf", placeholder="000.000.000-00")
    tel = c4.text_input("Telefone / WhatsApp", value=fmt_tel(d.get("telefone")), key=f"{prefixo}_tel", placeholder="(31) 99999-9999")
    end = st.text_input("Endereço (rua, número, complemento, bairro)", value=d.get("endereco") or "", key=f"{prefixo}_end")
    c5, c6, c7 = st.columns([2, 1, 1])
    cidade = c5.text_input("Cidade", value=d.get("cidade") or "", key=f"{prefixo}_cidade")
    uf = c6.text_input("UF", value=d.get("uf") or "", key=f"{prefixo}_uf", max_chars=2)
    cep = c7.text_input("CEP", value=fmt_cep(d.get("cep")), key=f"{prefixo}_cep", placeholder="00000-000")
    c8, c9 = st.columns(2)
    pix = c8.text_input("Chave PIX (para o pagamento)", value=d.get("pix") or "", key=f"{prefixo}_pix")
    reg_atual = d.get("regime") or ""
    regime = c9.selectbox("Regime tributário do CNPJ", REGIMES, key=f"{prefixo}_regime",
                          index=REGIMES.index(reg_atual) if reg_atual in REGIMES else 0,
                          help="MEI tem teto anual de faturamento que um bom vendedor pode ultrapassar; "
                               "prefira Simples Nacional.")
    c10, c11 = st.columns(2)
    loc_atual = d.get("local_atuacao") or ""
    local = c10.selectbox("Local de atuação", LOCAIS, key=f"{prefixo}_local",
                          index=LOCAIS.index(loc_atual) if loc_atual in LOCAIS else 0)
    try:
        ini = pd.to_datetime(d.get("data_inicio")).date() if d.get("data_inicio") else None
    except Exception:
        ini = None
    inicio = c11.date_input("Início da parceria", value=ini, key=f"{prefixo}_inicio", format="DD/MM/YYYY")
    obs = st.text_area("Observações", value=d.get("observacoes") or "", key=f"{prefixo}_obs")
    return {"razao_social": razao, "cnpj": cnpj, "cpf": cpf, "telefone": tel, "endereco": end,
            "cidade": cidade, "uf": uf, "cep": cep, "pix": pix, "regime": regime,
            "local_atuacao": local, "data_inicio": inicio, "observacoes": obs}


def _normalizar_dados(raw, lista, ignorar_id=None):
    """(dados_para_gravar, erros). Guarda só dígitos em CNPJ/CPF/telefone/CEP."""
    erros = []
    out = {
        "razao_social": raw["razao_social"].strip() or None,
        "cnpj": so_digitos(raw["cnpj"]) or None,
        "cpf": so_digitos(raw["cpf"]) or None,
        "telefone": so_digitos(raw["telefone"]) or None,
        "endereco": raw["endereco"].strip() or None,
        "cidade": raw["cidade"].strip() or None,
        "uf": raw["uf"].strip().upper() or None,
        "cep": so_digitos(raw["cep"]) or None,
        "pix": raw["pix"].strip() or None,
        "regime": raw["regime"] or None,
        "local_atuacao": raw["local_atuacao"] or None,
        "data_inicio": raw["data_inicio"].isoformat() if raw.get("data_inicio") else None,
        "observacoes": raw["observacoes"].strip() or None,
    }
    if out["cnpj"]:
        if not validar_cnpj(out["cnpj"]):
            erros.append("CNPJ inválido (confira os dígitos).")
        elif any(so_digitos(u.get("cnpj")) == out["cnpj"] and u["id"] != ignorar_id for u in lista):
            erros.append("Já existe um usuário com esse CNPJ.")
    if out["cpf"] and not validar_cpf(out["cpf"]):
        erros.append("CPF inválido (confira os dígitos).")
    if out["telefone"]:
        t = out["telefone"][2:] if (out["telefone"].startswith("55") and len(out["telefone"]) in (12, 13)) else out["telefone"]
        if len(t) not in (10, 11):
            erros.append("Telefone inválido: informe DDD + número.")
    if out["cep"] and len(out["cep"]) != 8:
        erros.append("CEP inválido (8 dígitos).")
    if out["uf"] and not re.fullmatch(r"[A-Z]{2}", out["uf"]):
        erros.append("UF inválida (2 letras, ex.: MG).")
    return out, erros


def _limpar_caches():
    try:
        carregar_sessao_usuario.clear()
        vendedores_cadastrados.clear()
    except Exception:
        pass


def _fmt_dt(v):
    try:
        return pd.to_datetime(v, utc=True).tz_convert("America/Sao_Paulo").strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "—"


def _seletor_telas(prefixo, atuais):
    """Três grupos de caixas de seleção; devolve a lista de chaves marcadas."""
    atuais = set(atuais or [])
    marcadas = []
    grupos = {}
    for chave, (rotulo, grupo) in PERMISSOES.items():
        grupos.setdefault(grupo, []).append((chave, rotulo))
    cols = st.columns(len(grupos))
    for col, (grupo, itens) in zip(cols, grupos.items()):
        with col:
            st.markdown(f"**{grupo}**")
            for chave, rotulo in itens:
                if st.checkbox(rotulo, value=(chave in atuais), key=f"{prefixo}_{chave}"):
                    marcadas.append(chave)
    return marcadas


def _mostrar_senha_unica():
    """Mostra a senha temporária recém-gerada UMA vez (some ao fechar)."""
    info = st.session_state.get("_senha_temp_exibir")
    if not info:
        return
    st.success(f"Usuário **{info['login']}** — entregue estas credenciais agora (a senha não fica visível depois):")
    c1, c2 = st.columns(2)
    c1.code(f"Login: {info['login']}", language=None)
    c2.code(f"Senha temporária: {info['senha']}", language=None)
    st.caption("No primeiro acesso o sistema pede para a pessoa criar a própria senha.")
    if info.get("site_msg"):
        (st.success if info.get("site_ok") else st.warning)(info["site_msg"])
    if st.button("Já anotei — esconder", key="btn_esconder_senha"):
        st.session_state.pop("_senha_temp_exibir", None)
        st.rerun()


def render_usuarios(supabase):
    st.markdown("#### 👥 Usuários e acessos")

    if not _migracao_ok(supabase):
        st.error("A atualização do banco para senhas criptografadas ainda não foi aplicada.")
        st.markdown(
            "Rode **uma vez** o arquivo `migracoes/26_usuarios_seguros.sql` no **SQL Editor do Supabase** "
            "do ERP e depois recarregue esta página. Até lá o login continua funcionando como antes.")
        return

    eu = st.session_state.get("usuario_logado")
    com_dados = _dados_ok(supabase)
    lista = _usuarios(supabase, com_dados)
    _mostrar_senha_unica()
    if not com_dados:
        st.info("Para guardar CNPJ, telefone, endereço e PIX dos vendedores, rode uma vez o arquivo "
                "`migracoes/27_vendedores_dados.sql` no SQL Editor do Supabase e recarregue esta página.")

    # ---------- visão geral ----------
    if lista:
        linhas = []
        for u in lista:
            n_telas = "tudo" if u["perfil"] == PERFIL_ADMIN else (
                len(PERMISSOES_PADRAO_VENDEDOR) if u.get("permissoes") is None else len(u.get("permissoes") or []))
            linhas.append({
                "Login": u["login"], "Nome": u["nome"],
                "Perfil": ROTULO_PERFIL.get(u["perfil"], u["perfil"]),
                "E-mail": u.get("email") or "—",
                "Situação": "✅ Ativo" if u.get("ativo") is not False else "⛔ Desativado",
                "Admin do site": "✅" if u.get("acesso_site_admin") else "—",
                "Telas liberadas": str(n_telas),
                "Último acesso": _fmt_dt(u.get("ultimo_login")),
            })
            if com_dados:
                falt = _faltantes(u) if u["perfil"] == PERFIL_VENDEDOR else None
                linhas[-1].update({
                    "CNPJ": fmt_cnpj(u.get("cnpj")) if u.get("cnpj") else "—",
                    "Telefone": fmt_tel(u.get("telefone")) if u.get("telefone") else "—",
                    "Local": u.get("local_atuacao") or "—",
                    "Cadastro": "—" if falt is None else ("✅ Completo" if not falt else "⚠️ Falta: " + ", ".join(falt)),
                })
        st.dataframe(pd.DataFrame(linhas), use_container_width=True, hide_index=True)

    # ---------- um só lugar: criar OU editar ----------
    opcoes = {OPCAO_NOVO: None}
    for u in lista:
        opcoes[f"{u['login']} — {u['nome']} ({ROTULO_PERFIL.get(u['perfil'], u['perfil'])})"] = u
    escolha = st.selectbox("Usuário — escolha um para editar ou crie um novo", list(opcoes), key="usr_edit_sel")
    if opcoes[escolha] is None:
        _form_novo(supabase, lista, eu, com_dados)
    else:
        _form_editar(supabase, lista, opcoes[escolha], eu, com_dados)


# ===================================================================== NOVO
def _form_novo(supabase, lista, eu, com_dados=False):
    st.markdown("##### ➕ Criar novo usuário")
    modelo = st.selectbox("Modelo de acesso (pré-seleciona as telas)", list(MODELOS_PERMISSAO),
                          key="usr_modelo")
    with st.form("form_novo_usuario", clear_on_submit=False):
        c1, c2 = st.columns(2)
        perfil_rot = c1.radio("Perfil", ["Vendedor", "Administrador"], horizontal=True, key="usr_perfil")
        nome = c2.text_input("Nome completo *", help="É o nome que aparece como vendedor nas vendas e relatórios.")
        c3, c4 = st.columns(2)
        login = c3.text_input("Login *", help="3 a 30 caracteres: letras, números, ponto, hífen ou _").strip().lower()
        email = c4.text_input("E-mail", help="Obrigatório para liberar o login do admin do site.").strip().lower()
        raw_dados = _campos_dados("novo_dados") if com_dados else None
        modo_senha = st.radio("Senha inicial", ["Gerar senha temporária (recomendado)", "Eu defino a senha"],
                              horizontal=True)
        senha_manual = st.text_input("Senha (só se escolheu definir)", type="password")
        st.markdown("**O que este vendedor poderá ver** (Administrador sempre vê tudo)")
        # a chave muda com o modelo: assim, ao trocar o modelo, as caixas recebem as telas novas
        telas = _seletor_telas(f"novo{list(MODELOS_PERMISSAO).index(modelo)}", MODELOS_PERMISSAO[modelo])
        site_admin = st.checkbox("Também pode entrar no **admin do site** de cartas contempladas "
                                 "(mesmo e-mail e senha)", key="usr_novo_site")
        enviar = st.form_submit_button("Criar usuário", type="primary")

    if not enviar:
        return
    erros = []
    perfil = PERFIL_ADMIN if perfil_rot == "Administrador" else PERFIL_VENDEDOR
    if not nome.strip():
        erros.append("Informe o nome completo.")
    erros += _validar_login(login, lista)
    if perfil == PERFIL_VENDEDOR and nome.strip().upper() in NOMES_RESERVADOS:
        erros.append("Esse nome é de uso interno (sócios/categorias do ERP); use o nome da pessoa.")
    if site_admin and not email:
        erros.append("Para liberar o admin do site é preciso informar o e-mail.")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        erros.append("E-mail inválido.")
    gerada = modo_senha.startswith("Gerar")
    if gerada:
        senha = gerar_senha_temporaria()
    else:
        senha = senha_manual
        ok_f, msg_f = validar_forca(senha)
        if not ok_f:
            erros.append(msg_f)
    dados_db = {}
    if raw_dados is not None:
        dados_db, erros_d = _normalizar_dados(raw_dados, lista)
        erros += erros_d
    if erros:
        for e in erros:
            st.error(e)
        return
    nome_final = nome.strip().upper() if perfil == PERFIL_VENDEDOR else nome.strip()
    reg = {"login": login, "nome": nome_final, "perfil": perfil, "email": email or None,
           "senha": None, "senha_hash": hash_senha(senha), "ativo": True,
           "permissoes": (telas if perfil == PERFIL_VENDEDOR else None),
           "acesso_site_admin": bool(site_admin), "trocar_senha": bool(gerada),
           "criado_por": eu, "atualizado_em": _agora()}
    reg.update(dados_db)
    try:
        novo = supabase.table("usuarios").insert(reg).execute().data
        site_ok = site_msg = None
        if site_admin:
            site_ok, site_msg, uid = sincronizar_site(iniciar_conexao_site(), email, senha, True)
            if novo and uid:
                supabase.table("usuarios").update({"site_user_id": uid}).eq("id", novo[0]["id"]).execute()
        _limpar_caches()
        st.session_state["_senha_temp_exibir"] = {
            "login": login, "senha": senha if gerada else "(a que você definiu)",
            "site_msg": site_msg, "site_ok": site_ok}
        st.rerun()
    except Exception as e:
        st.error(f"Não consegui criar o usuário: {str(e)[:200]}")


def _validar_login(login, lista, ignorar_id=None):
    erros = []
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", login or ""):
        erros.append("Login inválido: use 3 a 30 caracteres (letras minúsculas, números, . - _).")
    elif any(str(u["login"]).lower() == login and u["id"] != ignorar_id for u in lista):
        erros.append("Já existe um usuário com esse login.")
    return erros


# ==================================================================== EDITAR
def _contar_vendas(supabase, nome):
    try:
        r = supabase.table("vendas").select("id", count="exact").eq("VENDEDOR", nome).execute()
        return int(getattr(r, "count", None) if getattr(r, "count", None) is not None else len(r.data or []))
    except Exception:
        return 0


def _form_editar(supabase, lista, u, eu, com_dados=False):
    socio = str(u["login"]).lower() in LOGINS_SOCIOS         # Breno e Uriel: perfil/login/nome fixos
    sou_eu = str(u["login"]).lower() == str(eu or "").lower()
    k = f"usr_{u['id']}"
    st.markdown(f"##### ✏️ Editar **{u['login']}**")

    c1, c2 = st.columns(2)
    login_e = c1.text_input("Login", value=u["login"], key=k + "_login", disabled=(socio or sou_eu)).strip().lower()
    nome_e = c2.text_input("Nome", value=u["nome"], key=k + "_nome", disabled=socio,
                           help="É o nome que liga as vendas ao vendedor. Mudar o nome pode atualizar também as vendas já feitas.")
    c3, c4 = st.columns(2)
    perfil_rot = c3.radio("Perfil", ["Vendedor", "Administrador"], horizontal=True, key=k + "_perfil",
                          index=(1 if u["perfil"] == PERFIL_ADMIN else 0), disabled=(socio or sou_eu))
    email_e = c4.text_input("E-mail", value=u.get("email") or "", key=k + "_email").strip().lower()
    ativo_e = st.checkbox("Usuário ativo (pode entrar no sistema)", value=(u.get("ativo") is not False),
                          key=k + "_ativo", disabled=sou_eu)
    if sou_eu:
        st.caption("Você não pode mudar o próprio login, perfil nem desativar o próprio usuário.")
    perfil_e = PERFIL_ADMIN if perfil_rot == "Administrador" else PERFIL_VENDEDOR

    telas_e = None
    if perfil_e == PERFIL_ADMIN:
        st.info("Administrador vê todas as telas — não há o que escolher aqui.")
    else:
        st.markdown("**O que este vendedor pode ver**")
        atuais = PERMISSOES_PADRAO_VENDEDOR if u.get("permissoes") is None else u.get("permissoes")
        telas_e = _seletor_telas(k, atuais)

    raw_dados = None
    if com_dados:
        st.divider()
        raw_dados = _campos_dados(k + "_d", u)
        if perfil_e == PERFIL_VENDEDOR and _faltantes(u):
            st.caption("Cadastro incompleto — falta: " + ", ".join(_faltantes(u)) + ".")

    atualizar_vendas = False
    nome_mudou = (not socio) and nome_e.strip().upper() != str(u["nome"]).strip().upper()
    if nome_mudou and perfil_e == PERFIL_VENDEDOR:
        n_v = _contar_vendas(supabase, u["nome"])
        if n_v:
            atualizar_vendas = st.checkbox(
                f"Atualizar também as {n_v} venda(s) já registradas em nome de **{u['nome']}** "
                f"para o nome novo (recomendado)", value=True, key=k + "_vendas")
        else:
            st.caption("Nenhuma venda registrada com o nome antigo.")

    site_e = st.checkbox("Pode entrar no **admin do site** de cartas contempladas (mesmo e-mail e senha)",
                         value=bool(u.get("acesso_site_admin")), key=k + "_site")

    b1, b2 = st.columns(2)
    if b1.button("💾 Salvar alterações", type="primary", key=k + "_salvar"):
        erros = []
        if not (socio or sou_eu):
            erros += _validar_login(login_e, lista, ignorar_id=u["id"])
        if site_e and not email_e:
            erros.append("Para liberar o admin do site é preciso informar o e-mail.")
        if email_e and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_e):
            erros.append("E-mail inválido.")
        if not socio and not nome_e.strip():
            erros.append("O nome não pode ficar vazio.")
        if (not socio) and perfil_e == PERFIL_VENDEDOR and nome_e.strip().upper() in NOMES_RESERVADOS:
            erros.append("Esse nome é de uso interno (sócios/categorias do ERP); use o nome da pessoa.")
        # sempre sobra pelo menos um administrador ativo
        if u["perfil"] == PERFIL_ADMIN and (perfil_e != PERFIL_ADMIN or not ativo_e):
            outros = [x for x in lista if x["id"] != u["id"] and x["perfil"] == PERFIL_ADMIN and x.get("ativo") is not False]
            if not outros:
                erros.append("Precisa existir pelo menos um administrador ativo.")
        dados_db = {}
        if raw_dados is not None:
            dados_db, erros_d = _normalizar_dados(raw_dados, lista, ignorar_id=u["id"])
            erros += erros_d
        if erros:
            for e in erros:
                st.error(e)
        else:
            campos = {"email": email_e or None, "ativo": bool(ativo_e) if not sou_eu else True,
                      "acesso_site_admin": bool(site_e), "atualizado_em": _agora()}
            if not (socio or sou_eu):
                campos["login"] = login_e
                campos["perfil"] = perfil_e
            if not socio:
                campos["nome"] = nome_e.strip().upper() if perfil_e == PERFIL_VENDEDOR else nome_e.strip()
            campos["permissoes"] = telas_e if perfil_e == PERFIL_VENDEDOR else None
            campos.update(dados_db)
            msgs = []
            site_antes = bool(u.get("acesso_site_admin"))
            precisa_site = (site_e != site_antes) or (site_e and (email_e != (u.get("email") or "")))
            liberar_site = bool(site_e) and bool(campos["ativo"])
            try:
                if precisa_site or (not campos["ativo"] and site_antes):
                    ok_s, msg_s, uid = sincronizar_site(iniciar_conexao_site(), email_e, None,
                                                        liberar_site, u.get("site_user_id"))
                    if uid:
                        campos["site_user_id"] = uid
                    msgs.append((ok_s, msg_s))
                supabase.table("usuarios").update(campos).eq("id", u["id"]).execute()
                if atualizar_vendas and campos.get("nome") and campos["nome"] != u["nome"]:
                    supabase.table("vendas").update({"VENDEDOR": campos["nome"]}).eq("VENDEDOR", u["nome"]).execute()
                    try:
                        carregar_dados_iniciais.clear()
                    except Exception:
                        pass
                    msgs.append((True, "Vendas antigas atualizadas para o nome novo."))
                _limpar_caches()
                st.success("Alterações salvas. Valem para o usuário em até 30 segundos.")
                for ok_s, msg_s in msgs:
                    (st.success if ok_s else st.warning)(msg_s)
            except Exception as e:
                st.error(f"Não consegui salvar: {str(e)[:200]}")

    if b2.button("🔑 Gerar nova senha temporária", key=k + "_reset"):
        senha = gerar_senha_temporaria()
        try:
            supabase.table("usuarios").update({
                "senha_hash": hash_senha(senha), "senha": None, "trocar_senha": True,
                "tentativas_falhas": 0, "bloqueado_ate": None, "atualizado_em": _agora()}).eq("id", u["id"]).execute()
            site_ok = site_msg = None
            if u.get("acesso_site_admin") or site_e:
                site_ok, site_msg, uid = sincronizar_site(iniciar_conexao_site(), email_e or u.get("email"),
                                                          senha, True, u.get("site_user_id"))
                if uid:
                    supabase.table("usuarios").update({"site_user_id": uid, "acesso_site_admin": True}).eq("id", u["id"]).execute()
            _limpar_caches()
            st.session_state["_senha_temp_exibir"] = {"login": u["login"], "senha": senha,
                                                      "site_msg": site_msg, "site_ok": site_ok}
            st.rerun()
        except Exception as e:
            st.error(f"Não consegui gerar a senha: {str(e)[:200]}")
    st.caption("Usuários nunca são apagados — desative para impedir o acesso e manter o histórico das vendas.")
