-- 23_robo_status_login_travado.sql
-- Trava de login do Newcon visível no ERP: quando o robô erra a senha do
-- Newcon, ele marca aqui; o ERP mostra um aviso + botão "liberar o robô".
-- Roda no Supabase do ERP (mgvihpkqeazdxnjpuekt). Idempotente.

alter table robo_status
  add column if not exists login_travado        boolean     default false,
  add column if not exists login_travado_desde  timestamptz,
  add column if not exists login_travado_msg    text,
  add column if not exists login_liberado_em    timestamptz;

update robo_status set login_travado = false where id = 1 and login_travado is null;
