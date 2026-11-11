-- 33_robo_sob_demanda.sql
-- Robô sob demanda: o CRM marca aqui "tem alguém usando o sistema agora"; o watchdog
-- do notebook servidor liga o robô quando isso é recente (< 60 min) e desliga depois.
-- Roda no Supabase do ERP (mgvihpkqeazdxnjpuekt). Idempotente.

alter table robo_status
  add column if not exists crm_ativo_em timestamptz;
