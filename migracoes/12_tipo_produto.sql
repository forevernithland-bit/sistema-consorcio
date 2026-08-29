-- ==========================================================
-- Migração 12 — Tipo de Produto (Tradicional / Contemplado)
-- Rode no Supabase (SQL Editor).
--
-- Adiciona o tipo de produto e os campos do Consórcio Contemplado.
-- Marca TODAS as vendas já existentes como "Consórcio Tradicional"
-- (nada muda para elas — continuam aparecendo no Ofertar Lance).
-- ==========================================================

alter table vendas add column if not exists "TIPO_PRODUTO"  text;
alter table vendas add column if not exists "VALOR_ENTRADA" numeric;  -- só Contemplado
alter table vendas add column if not exists "AGIO"          numeric;  -- só Contemplado (renda Consorbens)

-- Backfill: tudo que já existe vira Tradicional
update vendas
   set "TIPO_PRODUTO" = 'Consórcio Tradicional'
 where "TIPO_PRODUTO" is null or "TIPO_PRODUTO" = '';
