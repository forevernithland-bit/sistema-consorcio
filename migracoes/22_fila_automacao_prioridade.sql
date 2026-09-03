-- 22_fila_automacao_prioridade.sql
-- Suporte ao robô único (worker_consorbens.py): prioridade na fila + colunas
-- de payload/progresso pras tarefas novas (coleta, relatório, cron).
-- Roda no Supabase do ERP (mgvihpkqeazdxnjpuekt). Idempotente.

alter table fila_automacao
  add column if not exists prioridade int default 50,
  add column if not exists payload    jsonb  default '{}'::jsonb,
  add column if not exists resultado  jsonb,
  add column if not exists progresso  text;

-- LANCE/BOLETO já existentes: garante que fiquem à frente das coletas.
update fila_automacao
   set prioridade = 10
 where tipo in ('LANCE', 'BOLETO')
   and (prioridade is null or prioridade = 50);

-- Índice pra seleção "próximo pendente" (status + prioridade + antiguidade).
create index if not exists idx_fila_pendente_prio
  on fila_automacao (status, prioridade, criado_em);

-- OBS: o worker_consorbens.py também faz o "coalesce" de prioridade no lado do
-- Python (LANCE/BOLETO = 10 mesmo sem o campo), então o ERP NÃO precisa mudar
-- os inserts de modulos/ofertar_lance.py e modulos/emitir_boleto.py agora.
