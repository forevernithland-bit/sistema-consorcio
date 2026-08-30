-- Registro de cada tentativa de busca de grupo (plano + crédito), com ou sem
-- resultado. Serve pra NÃO repetir busca que já foi feita hoje e não achou vaga.
create table if not exists yamaha_buscas (
    tipo_bem          text not null,          -- Auto / Moto / Imóvel / Caminhão
    plano_codigo      text not null,
    credito           numeric not null,       -- valor-alvo dessa busca
    prazo_label       text,                   -- prazo usado ('84', '(único)', ...)
    grupos_encontrados int default 0,
    vagas_total       int default 0,          -- soma de vagas dos grupos achados
    grupos            text[],                 -- nº dos grupos achados
    consultado_em     timestamptz not null default now(),
    primary key (tipo_bem, plano_codigo, credito, prazo_label)
);
create index if not exists ix_yb on yamaha_buscas (tipo_bem, credito, consultado_em desc);
