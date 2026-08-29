-- ==========================================================
-- Migração 14 — Emissão de Boletos
-- Rode no Supabase (SQL Editor).
-- ==========================================================

-- Flag: cota marcada para envio MENSAL de boleto
alter table vendas add column if not exists "BOLETO_MENSAL" boolean default false;

-- Campos do boleto na fila de automação (tipo = 'BOLETO')
alter table fila_automacao add column if not exists codigo_barras text;    -- linha digitável
alter table fila_automacao add column if not exists vencimento    text;    -- data de vencimento
alter table fila_automacao add column if not exists em_atraso      boolean; -- cliente em atraso?
