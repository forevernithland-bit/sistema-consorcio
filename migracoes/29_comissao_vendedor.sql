-- Comissão do vendedor (regra nova) + data de cancelamento (para o estorno).
-- Rode uma vez no SQL Editor do Supabase.

-- 1) Data em que a cota foi cancelada (texto dd/mm/aaaa, igual à coluna DATA).
alter table public.vendas add column if not exists "DATA_CANCELAMENTO" text;

-- 2) Regra do vendedor editável em Configurações (valores padrão = regra combinada).
alter table public.config_interna
    add column if not exists "VD_P1"        numeric default 0.5,
    add column if not exists "VD_P2"        numeric default 0.5,
    add column if not exists "VD_M1"        numeric default 500000,
    add column if not exists "VD_M1_P3"     numeric default 0.25,
    add column if not exists "VD_M2"        numeric default 1000000,
    add column if not exists "VD_M2_P4"     numeric default 0.25,
    add column if not exists "VD_EST_PCT"   numeric default 0.5,
    add column if not exists "VD_EST_MESES" integer default 5,
    add column if not exists "VD_EST_PARCELAS" integer default 2;

update public.config_interna set
    "VD_P1" = coalesce("VD_P1", 0.5), "VD_P2" = coalesce("VD_P2", 0.5),
    "VD_M1" = coalesce("VD_M1", 500000), "VD_M1_P3" = coalesce("VD_M1_P3", 0.25),
    "VD_M2" = coalesce("VD_M2", 1000000), "VD_M2_P4" = coalesce("VD_M2_P4", 0.25),
    "VD_EST_PCT" = coalesce("VD_EST_PCT", 0.5), "VD_EST_MESES" = coalesce("VD_EST_MESES", 5), "VD_EST_PARCELAS" = coalesce("VD_EST_PARCELAS", 2);

notify pgrst, 'reload schema';

-- 3) Cotas JÁ canceladas ficam sem data: o estorno só é calculado depois que a data for informada
--    (na ficha da cota, status Cancelada -> "Data do cancelamento").
