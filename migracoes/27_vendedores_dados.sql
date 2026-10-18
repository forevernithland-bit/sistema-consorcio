-- ==========================================================================
-- Migração 27 — dados cadastrais do vendedor (PJ) em `usuarios`
-- Rodar uma vez no SQL Editor do Supabase do ERP (depois da 26). Idempotente.
--
-- Guarda, junto do usuário, o que o contrato e o pagamento precisam:
-- razão social, CNPJ, CPF do responsável, telefone, endereço, chave PIX,
-- regime tributário, local de atuação (loja ou externo), início da parceria.
-- ==========================================================================

alter table usuarios
    add column if not exists razao_social text,
    add column if not exists cnpj         text,
    add column if not exists cpf          text,
    add column if not exists telefone     text,
    add column if not exists endereco     text,
    add column if not exists cidade       text,
    add column if not exists uf           text,
    add column if not exists cep          text,
    add column if not exists pix          text,
    add column if not exists regime       text,
    add column if not exists local_atuacao text,
    add column if not exists data_inicio  date,
    add column if not exists observacoes  text;

-- um CNPJ por vendedor (só dígitos; vazio não conta)
create unique index if not exists ux_usuarios_cnpj
    on usuarios (cnpj) where cnpj is not null and cnpj <> '';

comment on column usuarios.cnpj is 'Só dígitos (14). Formatado na tela.';
