-- ============================================================
--  CONSORBENS — Resultado mensal dos sócios (Breno/Uriel).
--  Publicado automaticamente pela tela Financeiro (modulos/financeiro.py)
--  toda vez que ela é renderizada, para o ERP_ECOCLIM ler (linha
--  "CONS INVESTIMENTOS" do Controle Financeiro) sem duplicar a lógica
--  de comissionamento. Chave por ano+mês — funciona na virada de ano
--  sem regra especial.
--  Rode no SQL Editor do Supabase do Consorbens.
-- ============================================================

create table if not exists public.resultado_socios_mensal (
  ano integer not null,
  mes integer not null,
  breno numeric not null default 0,
  uriel numeric not null default 0,
  atualizado_em timestamptz not null default now(),
  primary key (ano, mes)
);
