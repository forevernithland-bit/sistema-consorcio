-- 34_regras_lance_e_programados.sql  (16/11/2026)
-- 1) yamaha_regras_lance: regras de lance de CADA GRUPO lidas pelo robô na tela
--    "Oferta de Lance" do Newcon (modalidades liberadas, % do fixo/2º fixo,
--    limitado mín/máx, fidelidade máx, embutido permitido).
-- 2) lances_programados: lance que se REPETE nos próximos meses (N meses ou ilimitado).
-- Roda no Supabase do ERP (mgvihpkqeazdxnjpuekt) -> SQL Editor. Idempotente.

create table if not exists public.yamaha_regras_lance (
  grupo                    text primary key,
  cota_lida                text,
  lido_em                  date,
  formulario_aberto        boolean,
  modalidades              jsonb,          -- {"Livre":true,"Fixo":true,"2º Fixo":false,...}
  modalidades_no_historico jsonb,          -- ["Lance Livre","Lance Limitado",...]
  lance_min_pct            numeric,
  lance_max_pct            numeric,
  lance_fixo_pct           numeric,
  lance_2fixo_pct          numeric,
  limitado_min_pct         numeric,
  limitado_max_pct         numeric,
  fidelidade_max_pct       numeric,
  embutido_max_pct         numeric,        -- % de embutido que o grupo permite (tabela de preço / histórico)
  embutido_fonte           text,
  embutido_usado_max_pct   numeric,        -- maior % de embutido já ofertado numa cota nossa do grupo
  plano                    text,
  assembleia_oferta        text,
  atualizado_em            timestamptz default now()
);
alter table public.yamaha_regras_lance enable row level security;
drop policy if exists yamaha_regras_lance_acesso on public.yamaha_regras_lance;
create policy yamaha_regras_lance_acesso on public.yamaha_regras_lance
  for all to anon, authenticated using (true) with check (true);

create table if not exists public.lances_programados (
  id             bigserial primary key,
  venda_id       bigint,
  cliente        text,
  vendedor       text,
  produto        text,
  grupo          text not null,
  cota           text not null,
  tipo_lance     text not null,             -- Lance Livre | Lance Fixo | 2º Lance Fixo | Lance Limitado | Lance Fidelidade
  pct_lance      numeric,
  pct_embutido   numeric default 0,
  pct_proprio    numeric default 0,
  tipo_reducao   text default 'Reduzir Parcela',
  meses_total    integer,                   -- null = ILIMITADO
  meses_feitos   integer default 0,
  ultimo_mes     text,                      -- 'AAAA-MM' do último pedido gerado
  ativo          boolean default true,
  criado_por     text,
  criado_em      timestamptz default now(),
  atualizado_em  timestamptz default now()
);
create index if not exists lances_programados_ativos on public.lances_programados (ativo, grupo, cota);
alter table public.lances_programados enable row level security;
drop policy if exists lances_programados_acesso on public.lances_programados;
create policy lances_programados_acesso on public.lances_programados
  for all to anon, authenticated using (true) with check (true);

-- fila: guarda a forma de redução e de qual programação o pedido veio
alter table public.fila_automacao add column if not exists tipo_reducao text;
alter table public.fila_automacao add column if not exists programado_id bigint;

-- 3) TAXA POR PLANO (16/11/2026): no Newcon a taxa de adm. (e a parcela) depende do PLANO
--    de venda (ex.: 9538 tem plano com 16,5% e plano "40% DESC" com 9,9%). A coluna taxa
--    guardava só o último plano lido. Agora: planos = {"<cod plano>": {nome, taxa, parcela,
--    prazo_total, prazo_restante, credito, parcela_reduzida, visto_em}, ...}
alter table public.grupos_yamaha add column if not exists planos jsonb;
