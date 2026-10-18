-- ==========================================================================
-- Migração 26 — usuários com senha CRIPTOGRAFADA, perfis e permissões
-- Rodar uma vez no SQL Editor do Supabase do ERP (mgvihpkqeazdxnjpuekt).
-- É idempotente (pode rodar de novo sem estragar nada).
--
-- O que muda em `usuarios`:
--   senha_hash        senha criptografada (PBKDF2-SHA256, sal próprio por usuário)
--   email             e-mail do usuário (obrigatório para quem entra no admin do site)
--   ativo             desativar um usuário sem apagar o histórico
--   permissoes        telas que o vendedor pode ver (lista JSON); NULL = padrão do perfil
--   acesso_site_admin libera também o login do admin do site de cartas contempladas
--   site_user_id      id do mesmo usuário no Supabase Auth do SITE
--   trocar_senha      obriga trocar a senha no próximo acesso (senha temporária)
--   tentativas_falhas / bloqueado_ate   trava anti "chute de senha"
--   ultimo_login / atualizado_em / criado_por   trilha mínima de auditoria
--
-- Depois de rodar esta migração, o ERP converte sozinho as senhas antigas
-- (texto puro) para hash e apaga o texto puro, no primeiro login de cada um —
-- ou de uma vez só pelo script  migracoes/26b_converter_senhas.py.
-- ==========================================================================

alter table usuarios
    add column if not exists senha_hash        text,
    add column if not exists email             text,
    add column if not exists ativo             boolean     default true,
    add column if not exists permissoes        jsonb,
    add column if not exists acesso_site_admin boolean     default false,
    add column if not exists site_user_id      uuid,
    add column if not exists trocar_senha      boolean     default false,
    add column if not exists tentativas_falhas integer     default 0,
    add column if not exists bloqueado_ate     timestamptz,
    add column if not exists ultimo_login      timestamptz,
    add column if not exists atualizado_em     timestamptz default now(),
    add column if not exists criado_por        text;

-- a senha em texto puro deixa de ser obrigatória (vira vazia depois da conversão)
alter table usuarios alter column senha drop not null;

-- um login por pessoa, sem diferenciar maiúscula/minúscula
create unique index if not exists ux_usuarios_login_lower on usuarios (lower(login));

update usuarios set ativo = true where ativo is null;
update usuarios set acesso_site_admin = false where acesso_site_admin is null;

comment on column usuarios.senha_hash is
  'PBKDF2-SHA256: pbkdf2_sha256$<iteracoes>$<sal_b64>$<hash_b64>. Nunca guardar a senha em texto.';
comment on column usuarios.permissoes is
  'Lista JSON de telas liberadas ao vendedor (chaves em seguranca.py). NULL = padrão do perfil. Administrador ignora.';
