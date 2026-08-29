-- ==========================================================
-- Migração 15 — Status do Robô (heartbeat) + agenda mensal
-- Rode no Supabase (SQL Editor).
--
-- Para quê:
--   * robo_status: o Worker "bate o ponto" (atualiza atualizado_em) a
--     cada ciclo. O CRM lê essa data para acender a bolinha SERVER
--     (🟢 ligado / 🔴 desligado) em cima da logo.
--   * ultimo_mensal: guarda o mês (AAAA-MM) em que o robô já disparou
--     os boletos mensais automáticos — evita disparar duas vezes.
-- ==========================================================

create table if not exists robo_status (
    id            int primary key default 1,
    atualizado_em timestamptz not null default now(),
    ultimo_mensal text,                                  -- 'AAAA-MM' já processado
    constraint robo_status_singleton check (id = 1)
);

-- Garante a linha única (id = 1). Semeia com data ANTIGA de propósito: assim,
-- enquanto o robô não bater o ponto de verdade, a bolinha SERVER fica VERMELHA
-- (não queremos que só rodar esta migração já acenda verde).
insert into robo_status (id, atualizado_em)
values (1, timestamptz '2000-01-01')
on conflict (id) do nothing;
