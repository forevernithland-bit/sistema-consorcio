-- ==========================================================
-- Migração 13 — Datas exclusivas do módulo Financeiro
-- Rode no Supabase (SQL Editor).
--
-- Guarda a data que o Financeiro usa para atribuir cada lançamento a um mês.
-- É SEPARADA das datas dos outros módulos: editar a data aqui NÃO altera
-- Baixar Parcelas, Relatórios, Dashboard, etc.
--   * Tradicional  -> chave_unica = a mesma chave da parcela de comissão
--   * Contemplado  -> chave_unica = 'CONT_<id da venda>'
-- ==========================================================

create table if not exists financeiro_datas (
    chave_unica text primary key,
    data        text          -- data no formato DD/MM/AAAA usada só no Financeiro
);
