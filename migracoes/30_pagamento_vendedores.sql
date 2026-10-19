-- ==========================================================================
-- Migração 30 — Controle de pagamento de comissão aos vendedores (fechamentos)
-- Rodar uma vez no SQL Editor do Supabase do ERP. Idempotente.
--
-- Três tabelas: pagamentos_vendedor (cabeçalho), pagamentos_vendedor_itens (itens congelados)
-- e pagamentos_vendedor_log (histórico que não se altera nem se apaga).
-- O banco impõe: estados permitidos, itens imutáveis depois de travados, unicidade do item
-- (não paga duas vezes), pagamento só com valor igual ao total, e log append-only.
-- ==========================================================================

create table if not exists public.pagamentos_vendedor (
    id                  bigint generated always as identity primary key,
    vendedor_id         bigint not null references public.usuarios(id),
    vendedor_nome       text   not null,
    competencia         text   not null,                       -- AAAA-MM da data de corte
    data_corte          date   not null,
    status              text   not null default 'RASCUNHO'
                        check (status in ('RASCUNHO','GERADO','ENVIADO','PAGO','COMPENSADO','CANCELADO')),
    total               numeric(14,2) not null default 0,
    qtd_itens           integer not null default 0,
    snapshot_vendedor   jsonb,                                 -- nome, CNPJ, PIX etc. no momento da geração
    regra_vigente       jsonb,                                 -- regra VD_* usada
    hash_conteudo       text,                                  -- SHA-256 dos itens, gravado ao travar
    gerado_em           timestamptz not null default now(),
    gerado_por          text,
    travado_em          timestamptz,
    travado_por         text,
    enviado_em          timestamptz,
    enviado_por         text,
    enviado_hash        text,
    pago_em             timestamptz,
    pago_por            text,
    data_pagamento      date,
    forma_pagamento     text,
    valor_pago          numeric(14,2),
    pix_e2e             text,
    comprovante         text,
    observacao          text,
    cancelado_em        timestamptz,
    cancelado_por       text,
    motivo_cancelamento text
);
create unique index if not exists ux_pv_um_rascunho on public.pagamentos_vendedor(vendedor_id) where status = 'RASCUNHO';
create unique index if not exists ux_pv_pix_e2e     on public.pagamentos_vendedor(pix_e2e) where pix_e2e is not null and pix_e2e <> '';
create index if not exists ix_pv_vendedor           on public.pagamentos_vendedor(vendedor_id, status);

create table if not exists public.pagamentos_vendedor_itens (
    id               bigint generated always as identity primary key,
    fechamento_id    bigint not null references public.pagamentos_vendedor(id) on delete restrict,
    vendedor_id      bigint not null,
    tipo             text   not null check (tipo in ('COMISSAO','BONUS','ESTORNO','AJUSTE','SALDO')),
    chave_item       text   not null,                          -- administradora|grupo|cota|parcela|tipo
    administradora   text,
    grupo            text,
    cota             text,
    parcela_adm      text,
    cliente          text,
    credito_base     numeric(14,2),
    pct              numeric(7,4),
    valor            numeric(14,2) not null,
    parcela_vendedor text,
    referencia       text,
    baixa_ref        bigint,                                   -- id da baixa em comissoes_pagas (informativo)
    baixa_snapshot   jsonb,
    anulado          boolean not null default false,
    criado_em        timestamptz not null default now(),
    check ( (tipo in ('COMISSAO','BONUS') and valor > 0) or (tipo = 'ESTORNO' and valor < 0) or tipo in ('AJUSTE','SALDO') )
);
-- o mesmo item nunca entra em dois fechamentos ativos
create unique index if not exists ux_pv_itens_chave on public.pagamentos_vendedor_itens(chave_item) where not anulado;
create index if not exists ix_pv_itens_fech on public.pagamentos_vendedor_itens(fechamento_id);

create table if not exists public.pagamentos_vendedor_log (
    id            bigint generated always as identity primary key,
    fechamento_id bigint,
    acao          text not null,
    status_de     text,
    status_para   text,
    ator          text,
    em            timestamptz not null default now(),
    detalhe       jsonb
);

-- ---------------------------------------------------------------- log: só inserir
create or replace function public.pv_log_imutavel() returns trigger language plpgsql as $$
begin
    raise exception 'pagamentos_vendedor_log é imutável (sem UPDATE/DELETE)';
end $$;
drop trigger if exists trg_pv_log_imutavel on public.pagamentos_vendedor_log;
create trigger trg_pv_log_imutavel before update or delete on public.pagamentos_vendedor_log
    for each row execute function public.pv_log_imutavel();

-- ---------------------------------------------------------------- cabeçalho: estados e campos congelados
create or replace function public.pv_cabecalho_guard() returns trigger language plpgsql as $$
declare soma numeric(14,2); n integer;
begin
    if tg_op = 'DELETE' then
        if old.status <> 'RASCUNHO' then
            raise exception 'Só rascunho pode ser apagado';
        end if;
        return old;
    end if;

    if new.vendedor_id <> old.vendedor_id then
        raise exception 'vendedor_id não pode mudar';
    end if;
    if old.status in ('PAGO','COMPENSADO','CANCELADO') and new.status <> old.status then
        raise exception 'Fechamento % é final (%): não muda de status', old.id, old.status;
    end if;
    if new.status <> old.status then
        if not ( (old.status = 'RASCUNHO' and new.status in ('GERADO','CANCELADO'))
              or (old.status = 'GERADO'   and new.status in ('ENVIADO','CANCELADO'))
              or (old.status = 'ENVIADO'  and new.status in ('PAGO','COMPENSADO','CANCELADO')) ) then
            raise exception 'Transição inválida: % -> %', old.status, new.status;
        end if;
        if new.status = 'GERADO' then
            select coalesce(sum(valor),0), count(*) into soma, n
              from public.pagamentos_vendedor_itens where fechamento_id = new.id and not anulado;
            if n = 0 or new.hash_conteudo is null or new.total <> soma then
                raise exception 'Para travar: precisa de itens, hash e total igual à soma dos itens (total=%, soma=%)', new.total, soma;
            end if;
        end if;
        if new.status = 'PAGO' then
            if new.total <= 0 or new.valor_pago is distinct from new.total or new.data_pagamento is null then
                raise exception 'Para pagar: total > 0, valor pago igual ao total e data do pagamento';
            end if;
        end if;
        if new.status = 'COMPENSADO' and new.total > 0 then
            raise exception 'Compensar só com total <= 0';
        end if;
        if new.status = 'CANCELADO' and coalesce(trim(new.motivo_cancelamento),'') = '' then
            raise exception 'Cancelar exige motivo';
        end if;
    else
        -- sem mudança de status: depois de travado, os campos financeiros são imutáveis
        if old.status <> 'RASCUNHO' and (
               new.total is distinct from old.total or new.hash_conteudo is distinct from old.hash_conteudo
            or new.data_corte is distinct from old.data_corte or new.qtd_itens is distinct from old.qtd_itens) then
            raise exception 'Fechamento travado: total, hash e itens não mudam';
        end if;
    end if;
    return new;
end $$;
drop trigger if exists trg_pv_cabecalho_guard on public.pagamentos_vendedor;
create trigger trg_pv_cabecalho_guard before update or delete on public.pagamentos_vendedor
    for each row execute function public.pv_cabecalho_guard();

-- ---------------------------------------------------------------- itens: só mexe em rascunho
create or replace function public.pv_itens_guard() returns trigger language plpgsql as $$
declare st text;
begin
    if tg_op = 'INSERT' then
        select status into st from public.pagamentos_vendedor where id = new.fechamento_id;
        if st is distinct from 'RASCUNHO' then
            raise exception 'Só dá para incluir itens em rascunho';
        end if;
        return new;
    end if;
    select status into st from public.pagamentos_vendedor where id = old.fechamento_id;
    if tg_op = 'DELETE' then
        if st is distinct from 'RASCUNHO' then
            raise exception 'Item de fechamento travado não se apaga';
        end if;
        return old;
    end if;
    -- UPDATE: só anular (liberar a chave) quando o fechamento está cancelado ou ainda é rascunho
    if st in ('CANCELADO','RASCUNHO') and new.anulado = true and old.anulado = false
       and new.valor = old.valor and new.chave_item = old.chave_item and new.fechamento_id = old.fechamento_id then
        return new;
    end if;
    raise exception 'Item de fechamento travado é imutável';
end $$;
drop trigger if exists trg_pv_itens_guard on public.pagamentos_vendedor_itens;
create trigger trg_pv_itens_guard before insert or update or delete on public.pagamentos_vendedor_itens
    for each row execute function public.pv_itens_guard();

notify pgrst, 'reload schema';
