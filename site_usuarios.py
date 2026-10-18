"""
Sincroniza usuários do ERP com o login do ADMIN do site de cartas contempladas.

O site (Supabase Auth, projeto do site) decide quem é admin pela tabela
`user_roles` (user_id, role='admin'). Esta função cria/atualiza o usuário no
Auth do site com o MESMO e-mail e senha do ERP e liga/desliga o papel de admin.

Exige a conexão do site com chave service_role (`SITE_SUPABASE_URL` /
`SITE_SUPABASE_KEY` nos secrets do Streamlit — a mesma que a integração de
cartas já usa). Sem ela, o ERP continua funcionando e avisa que o site não foi
sincronizado.
"""


def _achar_por_email(cli, email):
    """Procura o usuário no Auth do site pelo e-mail (varre as páginas)."""
    alvo = str(email or "").strip().lower()
    pagina = 1
    while pagina <= 20:
        lote = cli.auth.admin.list_users(page=pagina, per_page=200)
        usuarios = lote if isinstance(lote, list) else getattr(lote, "users", []) or []
        for u in usuarios:
            if str(getattr(u, "email", "") or "").strip().lower() == alvo:
                return u
        if len(usuarios) < 200:
            return None
        pagina += 1
    return None


def _id_de(resp):
    u = getattr(resp, "user", resp)
    return str(getattr(u, "id", "") or "") or None


def sincronizar_site(cli, email, senha, liberar, site_user_id=None):
    """Liga (`liberar=True`) ou desliga o acesso de admin do site.

    `senha` pode ser None quando só se está desligando ou quando a senha não
    mudou. Devolve (ok, mensagem, site_user_id).
    """
    if cli is None:
        return False, ("O ERP ainda não tem a chave do site (SITE_SUPABASE_URL / SITE_SUPABASE_KEY "
                       "nos secrets). O usuário foi salvo no ERP, mas o login do admin do site "
                       "não foi criado."), site_user_id
    email = str(email or "").strip().lower()
    try:
        if liberar:
            if not email:
                return False, "Informe o e-mail: o login do site é por e-mail.", site_user_id
            uid = str(site_user_id) if site_user_id else None
            if not uid:
                achado = _achar_por_email(cli, email)
                uid = str(achado.id) if achado else None
            if uid:
                dados = {"email": email, "email_confirm": True, "ban_duration": "none"}
                if senha:
                    dados["password"] = senha
                cli.auth.admin.update_user_by_id(uid, dados)
            else:
                if not senha:
                    return False, ("Para criar o login no site é preciso definir uma senha "
                                   "(use \"Gerar senha temporária\")."), None
                uid = _id_de(cli.auth.admin.create_user(
                    {"email": email, "password": senha, "email_confirm": True}))
                if not uid:
                    return False, "O site não devolveu o id do usuário criado.", None
            ja = (cli.table("user_roles").select("user_id").eq("user_id", uid)
                  .eq("role", "admin").execute().data or [])
            if not ja:
                cli.table("user_roles").insert({"user_id": uid, "role": "admin"}).execute()
            return True, "Acesso ao admin do site liberado (mesmo e-mail e senha do ERP).", uid
        # desligar
        uid = str(site_user_id) if site_user_id else None
        if not uid and email:
            achado = _achar_por_email(cli, email)
            uid = str(achado.id) if achado else None
        if not uid:
            return True, "Não havia login desse usuário no site.", None
        cli.table("user_roles").delete().eq("user_id", uid).eq("role", "admin").execute()
        try:   # bloqueia o login de vez (reversível ao liberar de novo)
            cli.auth.admin.update_user_by_id(uid, {"ban_duration": "876000h"})
        except Exception:
            pass
        return True, "Acesso ao admin do site removido.", uid
    except Exception as e:
        return False, f"Não consegui sincronizar com o site: {str(e)[:200]}", site_user_id
