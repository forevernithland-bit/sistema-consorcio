-- ==========================================================
-- Migração 10 — Percentuais do Lance Fixo na fila
-- Rode este SQL no Supabase (SQL Editor) DEPOIS da migração 09.
--
-- Guarda, por pedido, os 3 percentuais que o robô vai usar no Newcon:
--   pct_lance    = % total do Lance Fixo
--   pct_embutido = % que sai do próprio crédito (embutido)
--   pct_proprio  = % de recursos próprios (= pct_lance - pct_embutido)
-- ==========================================================

alter table fila_automacao add column if not exists pct_lance    numeric;
alter table fila_automacao add column if not exists pct_embutido numeric;
alter table fila_automacao add column if not exists pct_proprio  numeric;
