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
                      vendedores_cadastrados)
from seguranca import (PERMISSOES, MODELOS_PERMISSAO, PERMISSOES_PADRAO_VENDEDOR,
                       PERFIL_ADMIN, PERFIL_VENDEDOR, ROTULO_PERFIL,
                       hash_senha, gerar_senha_temporaria, validar_forca)
from site_usuarios import sincronizar_site

NOMES_RESERVADOS = {"BRENO LIMA", "URIEL GOMES", "CONSORBENS", "PARTICULAR BRENO",
                    "PARTICULAR URIEL", "VENDEDOR TERCEIRO"}
COLUNAS_NOVAS = "senha_hash,permissoes,ativo,acesso_site_admin,site_user_id,trocar_senha,email"


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _migracao_ok(supabase) -> bool:
    try:
        supabase.table("usuarios").select(COLUNAS_NOVAS).limit(1).execute()
        return True
    except Exception:
        return False


def _usuarios(supabase):
    try:
        cols = "id,login,nome,perfil,email,ativo,permissoes,acesso_site_admin,site_user_id,ultimo_login,trocar_senha"
        return supabase.table("usuarios").select(cols).order("id").execute().data or []
    except Exception:
        return []


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
    lista = _usuarios(supabase)
    _mostrar_senha_unica()

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
        st.dataframe(pd.DataFrame(linhas), use_container_width=True, hide_index=True)

    t_novo, t_edit = st.tabs(["➕ Novo usuário", "✏️ Editar · senha · acessos"])

    # ================= NOVO =================
    with t_novo:
        modelo = st.selectbox("Modelo de acesso (pré-seleciona as telas)", list(MODELOS_PERMISSAO),
                              key="usr_modelo")
        with st.form("form_novo_usuario", clear_on_submit=False):
            c1, c2 = st.columns(2)
            perfil_rot = c1.radio("Perfil", ["Vendedor", "Administrador"], horizontal=True, key="usr_perfil")
            nome = c2.text_input("Nome completo *", help="É o nome que aparece como vendedor nas vendas e relatórios.")
            c3, c4 = st.columns(2)
            login = c3.text_input("Login *", help="3 a 30 caracteres: letras, números, ponto, hífen ou _").strip().lower()
            email = c4.text_input("E-mail", help="Obrigatório para liberar o login do admin do site.").strip().lower()
            modo_senha = st.radio("Senha inicial", ["Gerar senha temporária (recomendado)", "Eu defino a senha"],
                                  horizontal=True)
            senha_manual = st.text_input("Senha (só se escolheu definir)", type="password")
            st.markdown("**O que este vendedor poderá ver** (Administrador sempre vê tudo)")
            # a chave muda com o modelo: assim, ao trocar o modelo, as caixas recebem as telas novas
            telas = _seletor_telas(f"novo{list(MODELOS_PERMISSAO).index(modelo)}", MODELOS_PERMISSAO[modelo])
            site_admin = st.checkbox("Também pode entrar no **admin do site** de cartas contempladas "
                                     "(mesmo e-mail e senha)", key="usr_novo_site")
            enviar = st.form_submit_button("Criar usuário", type="primary")

        if enviar:
            erros = []
            if not nome.strip():
                erros.append("Informe o nome completo.")
            if not re.fullmatch(r"[a-z0-9._-]{3,30}", login or ""):
                erros.append("Login inválido: use 3 a 30 caracteres (letras minúsculas, números, . - _).")
            if any(str(u["login"]).lower() == login for u in lista):
                erros.append("Já existe um usuário com esse login.")
            perfil = PERFIL_ADMIN if perfil_rot == "Administrador" else PERFIL_VENDEDOR
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
            if erros:
                for e in erros:
                    st.error(e)
            else:
                nome_final = nome.strip().upper() if perfil == PERFIL_VENDEDOR else nome.strip()
                reg = {"login": login, "nome": nome_final, "perfil": perfil, "email": email or None,
                       "senha": None, "senha_hash": hash_senha(senha), "ativo": True,
                       "permissoes": (telas if perfil == PERFIL_VENDEDOR else None),
                       "acesso_site_admin": bool(site_admin), "trocar_senha": bool(gerada),
                       "criado_por": eu, "atualizado_em": _agora()}
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

    # ================= EDITAR =================
    with t_edit:
        if not lista:
            st.info("Nenhum usuário cadastrado.")
            return
        opcoes = {f"{u['login']} — {u['nome']} ({ROTULO_PERFIL.get(u['perfil'], u['perfil'])})": u for u in lista}
        escolha = st.selectbox("Usuário", list(opcoes), key="usr_edit_sel")
        u = opcoes[escolha]
        eh_admin = u["perfil"] == PERFIL_ADMIN
        sou_eu = str(u["login"]).lower() == str(eu or "").lower()
        k = f"usr_{u['id']}"

        c1, c2 = st.columns(2)
        nome_e = c1.text_input("Nome", value=u["nome"], key=k + "_nome", disabled=eh_admin,
                               help="Nome dos sócios é fixo: ele liga as vendas ao vendedor.")
        email_e = c2.text_input("E-mail", value=u.get("email") or "", key=k + "_email").strip().lower()
        ativo_e = st.checkbox("Usuário ativo (pode entrar no sistema)", value=(u.get("ativo") is not False),
                              key=k + "_ativo", disabled=sou_eu)
        if sou_eu:
            st.caption("Você não pode desativar o próprio usuário.")
        if eh_admin:
            st.info("Administrador vê todas as telas — não há o que escolher aqui.")
            telas_e = None
        else:
            st.markdown("**O que este vendedor pode ver**")
            atuais = PERMISSOES_PADRAO_VENDEDOR if u.get("permissoes") is None else u.get("permissoes")
            telas_e = _seletor_telas(k, atuais)
        site_e = st.checkbox("Pode entrar no **admin do site** de cartas contempladas (mesmo e-mail e senha)",
                             value=bool(u.get("acesso_site_admin")), key=k + "_site")

        b1, b2 = st.columns(2)
        if b1.button("💾 Salvar alterações", type="primary", key=k + "_salvar"):
            if site_e and not email_e:
                st.error("Para liberar o admin do site é preciso informar o e-mail.")
            elif email_e and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_e):
                st.error("E-mail inválido.")
            else:
                campos = {"email": email_e or None, "ativo": bool(ativo_e) if not sou_eu else True,
                          "acesso_site_admin": bool(site_e), "atualizado_em": _agora()}
                if not eh_admin:
                    campos["nome"] = nome_e.strip().upper()
                    campos["permissoes"] = telas_e
                msgs = []
                site_antes = bool(u.get("acesso_site_admin"))
                precisa_site = (site_e != site_antes) or (site_e and (email_e != (u.get("email") or "")))
                # se o usuário foi desativado, o login do site também é removido
                liberar_site = bool(site_e) and bool(campos["ativo"])
                try:
                    if precisa_site or (not campos["ativo"] and site_antes):
                        ok_s, msg_s, uid = sincronizar_site(iniciar_conexao_site(), email_e, None,
                                                            liberar_site, u.get("site_user_id"))
                        if uid:
                            campos["site_user_id"] = uid
                        msgs.append((ok_s, msg_s))
                    supabase.table("usuarios").update(campos).eq("id", u["id"]).execute()
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
