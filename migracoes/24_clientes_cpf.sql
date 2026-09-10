-- 24_clientes_cpf.sql
-- Adiciona o campo CPF na ficha do cliente (antes não existia coluna nenhuma
-- de documento em `clientes`). Texto livre, guardado formatado
-- (ex.: 636.419.416-87). Rodar no SQL Editor do Supabase mgvihpkqeazdxnjpuekt.

alter table clientes add column if not exists "CPF" text;
