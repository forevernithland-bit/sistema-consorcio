-- ==========================================================
-- Migração 11 — Protocolo do lance (comprovante)
-- Rode no Supabase (SQL Editor) depois da migração 10.
--
-- Guarda o Nº de Protocolo que o Newcon devolve ao ofertar o lance.
-- É o comprovante oficial de que o lance foi registrado.
-- ==========================================================

alter table fila_automacao add column if not exists protocolo text;
