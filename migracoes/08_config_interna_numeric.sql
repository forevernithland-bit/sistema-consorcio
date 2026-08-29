-- ==========================================================
-- Migração 08 — Corrige os tipos da config_interna
-- As colunas estavam misturadas: umas bigint (70), outra texto
-- com vírgula ("1,5"). Converte TODAS para numeric, trocando
-- vírgula por ponto e tratando vazios como nulo.
-- Rode no Supabase → SQL Editor.
-- ==========================================================

alter table config_interna
    alter column "Breno_Breno" type numeric using nullif(replace("Breno_Breno"::text, ',', '.'), '')::numeric,
    alter column "Breno_Uriel" type numeric using nullif(replace("Breno_Uriel"::text, ',', '.'), '')::numeric,
    alter column "Uriel_Uriel" type numeric using nullif(replace("Uriel_Uriel"::text, ',', '.'), '')::numeric,
    alter column "Uriel_Breno" type numeric using nullif(replace("Uriel_Breno"::text, ',', '.'), '')::numeric,
    alter column "Cons_Breno"  type numeric using nullif(replace("Cons_Breno"::text,  ',', '.'), '')::numeric,
    alter column "Cons_Uriel"  type numeric using nullif(replace("Cons_Uriel"::text,  ',', '.'), '')::numeric,
    alter column "T1_Max"      type numeric using nullif(replace("T1_Max"::text,      ',', '.'), '')::numeric,
    alter column "T1_Pct"      type numeric using nullif(replace("T1_Pct"::text,      ',', '.'), '')::numeric,
    alter column "T1_Parc"     type numeric using nullif(replace("T1_Parc"::text,     ',', '.'), '')::numeric,
    alter column "T2_Max"      type numeric using nullif(replace("T2_Max"::text,      ',', '.'), '')::numeric,
    alter column "T2_Pct"      type numeric using nullif(replace("T2_Pct"::text,      ',', '.'), '')::numeric,
    alter column "T2_Parc"     type numeric using nullif(replace("T2_Parc"::text,     ',', '.'), '')::numeric,
    alter column "T3_Pct"      type numeric using nullif(replace("T3_Pct"::text,      ',', '.'), '')::numeric,
    alter column "T3_Parc"     type numeric using nullif(replace("T3_Parc"::text,     ',', '.'), '')::numeric,
    alter column "Imposto"     type numeric using nullif(replace("Imposto"::text,     ',', '.'), '')::numeric;
