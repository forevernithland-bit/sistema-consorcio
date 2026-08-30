-- Resultado de assembleias por grupo Yamaha (menu Contemplação → Resultado de
-- Assembleia). Base pra "média de lance de verdade", contemplados por modalidade,
-- maior/menor lance, mês a mês. Rodar uma vez no SQL editor do Supabase.

-- ============================================================
-- 1) UMA linha por contemplação (o dado bruto, tudo é guardado)
-- ============================================================
create table if not exists yamaha_contemplacoes (
    id              bigserial primary key,
    grupo           text not null,
    tipo_bem        text,                        -- Auto / Moto / Imóvel / Caminhão
    num_assembleia  int,
    data_assembleia date,
    mes_competencia text,                        -- 'AAAA-MM' da data da assembleia
    modalidade      text,                        -- Sorteio / Lance Livre / Lance Fixo /
                                                 -- 2º Lance Fixo / Lance Limitado /
                                                 -- Lance Fidelidade / (qualquer outra que aparecer)
    opcao           text,                        -- Red. Parc / Red. Prazo / (vazio)
    cota            text,
    bem             text,
    filial          text,
    dt_contemplacao date,
    dt_confirmacao  date,
    pct_lance       numeric,                     -- % do lance (0 no sorteio)
    situacao        text,                        -- ativo / cancelado / desclassificado
    atualizado_em   timestamptz not null default now(),
    unique (grupo, num_assembleia, cota, modalidade, dt_contemplacao, pct_lance)
);
create index if not exists ix_yc_grupo on yamaha_contemplacoes (grupo, data_assembleia desc);
create index if not exists ix_yc_mes on yamaha_contemplacoes (grupo, mes_competencia);

-- ============================================================
-- 2) UMA linha por assembleia (resumo + contadores por modalidade)
-- ============================================================
create table if not exists yamaha_assembleias (
    grupo                text not null,
    tipo_bem             text,
    num_assembleia       int not null,
    data_assembleia      date,
    mes_competencia      text,                   -- 'AAAA-MM'
    numero_sorteado      text,
    assembleias_realizadas int,
    assembleias_a_realizar int,
    prazo_grupo          int,
    -- contadores de contemplados por modalidade (o que o cabeçalho mostra)
    n_sorteio            int default 0,
    n_lance_livre        int default 0,
    n_lance_fixo         int default 0,
    n_2lance_fixo        int default 0,
    n_lance_limitado     int default 0,
    n_lance_fidelidade   int default 0,
    n_total              int default 0,
    -- estatística de lance dessa assembleia (só das modalidades de lance)
    lance_min            numeric,
    lance_max            numeric,
    lance_medio          numeric,                -- média geral (lances > 0)
    lance_livre_min      numeric,
    lance_livre_max      numeric,
    lance_livre_medio    numeric,
    lance_fixo_medio     numeric,
    modalidades_vistas   text[],                 -- todas as modalidades que apareceram
    atualizado_em        timestamptz not null default now(),
    primary key (grupo, num_assembleia)
);
create index if not exists ix_ya_grupo on yamaha_assembleias (grupo, data_assembleia desc);

-- ============================================================
-- 3) Resumo por grupo (janela das últimas assembleias coletadas) — view
-- ============================================================
create or replace view yamaha_grupo_lance_resumo as
select
    grupo,
    max(tipo_bem)                              as tipo_bem,
    count(*)                                   as assembleias_analisadas,
    min(data_assembleia)                       as de,
    max(data_assembleia)                       as ate,
    round(avg(lance_livre_medio) filter (where lance_livre_medio > 0), 4) as lance_livre_medio_periodo,
    min(lance_livre_min) filter (where lance_livre_min > 0)              as lance_livre_min_periodo,
    max(lance_livre_max)                                                 as lance_livre_max_periodo,
    round(avg(lance_fixo_medio) filter (where lance_fixo_medio > 0), 4)  as lance_fixo_medio_periodo,
    sum(n_lance_livre)                         as contempl_lance_livre,
    sum(n_lance_fixo)                          as contempl_lance_fixo,
    sum(n_lance_limitado)                      as contempl_lance_limitado,
    sum(n_lance_fidelidade)                    as contempl_lance_fidelidade,
    sum(n_sorteio)                             as contempl_sorteio,
    sum(n_total)                              as contempl_total,
    max(atualizado_em)                        as atualizado_em
from yamaha_assembleias
group by grupo;
