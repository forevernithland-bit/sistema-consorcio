-- Inteligência de planos e grupos Yamaha para o assistente de simulações.
-- Rodar uma vez no SQL editor do Supabase.

-- Cada PLANO (Tipo de Venda) e as faixas de crédito que ele oferece.
create table if not exists planos_yamaha (
    codigo        text        not null,             -- 073, 074, 069...
    tipo_bem      text        not null,             -- Moto / Auto / Imóvel / Caminhão
    nome          text,                             -- "S GRUPO PRIME IPCA + TX 11,6"
    creditos      jsonb,                            -- [{bem_cod, texto, credito}, ...]
    consultado_em timestamptz not null default now(),
    primary key (codigo, tipo_bem)
);

-- Foto mais recente de cada grupo (UPSERT por grupo+tipo_bem).
create table if not exists grupos_yamaha (
    grupo           text        not null,
    tipo_bem        text        not null,
    plano_codigo    text,
    bem             text,
    credito         numeric,
    taxa            numeric,                        -- taxa de administração (%)
    prox_assembleia text,                           -- DD/MM/AAAA
    prazo_restante  int,
    prazo_total     int,
    vagas           int,
    parcela         numeric,
    lance_medio     numeric,                        -- % lance médio (quando o Newcon traz)
    consultado_em   timestamptz not null default now(),
    fonte           text,
    primary key (grupo, tipo_bem)
);

-- Histórico de cada consulta (tendência de vagas; base pra "reconsultar se > N dias").
create table if not exists grupos_yamaha_consultas (
    id            bigserial primary key,
    grupo         text not null,
    tipo_bem      text not null,
    vagas         int,
    credito       numeric,
    consultado_em timestamptz not null default now()
);
create index if not exists ix_gyc_grupo on grupos_yamaha_consultas (grupo, consultado_em desc);

-- Resultado de assembleia por grupo (lances vencedores) — alimentado depois,
-- quando mapearmos a tela de Contemplação.
create table if not exists grupos_yamaha_lances (
    id                  bigserial primary key,
    grupo               text not null,
    tipo_bem            text,
    data_assembleia     text,
    num_assembleia      int,
    tipo_lance          text,                       -- livre / fixo
    lance_vencedor_pct  numeric,
    lance_vencedor_valor numeric,
    contemplacoes       int,
    atualizado_em       timestamptz not null default now()
);
create index if not exists ix_gyl_grupo on grupos_yamaha_lances (grupo, data_assembleia desc);
