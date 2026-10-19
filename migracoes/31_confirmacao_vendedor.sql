-- Migração 31 — o vendedor confirma o recebimento do fechamento pago (rodar depois da 30). Idempotente.
alter table public.pagamentos_vendedor
    add column if not exists confirmado_vendedor_em  timestamptz,
    add column if not exists confirmado_vendedor_por text;

-- A confirmação só pode ser feita uma vez, num fechamento PAGO, com quem confirmou, e nunca desfeita.
-- Um fechamento novo também não pode nascer já "confirmado" (senão travaria o PAGO depois).
-- (Não mexe nos demais campos: o pv_cabecalho_guard da migração 30 continua congelando total, hash, pagamento etc.)
create or replace function public.pv_confirmacao_guard() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.confirmado_vendedor_em is not null or new.confirmado_vendedor_por is not null then
            raise exception 'Fechamento novo não pode nascer com recebimento confirmado';
        end if;
        return new;
    end if;
    if new.confirmado_vendedor_em is distinct from old.confirmado_vendedor_em
       or new.confirmado_vendedor_por is distinct from old.confirmado_vendedor_por then
        if old.status <> 'PAGO' then
            raise exception 'Só se confirma recebimento de fechamento PAGO';
        end if;
        if old.confirmado_vendedor_em is not null then
            raise exception 'Recebimento já confirmado (não muda)';
        end if;
        if new.confirmado_vendedor_em is null then
            raise exception 'Confirmação não pode ser apagada';
        end if;
        if coalesce(trim(new.confirmado_vendedor_por), '') = '' then
            raise exception 'Informe quem confirmou o recebimento';
        end if;
    end if;
    return new;
end $$;
drop trigger if exists trg_pv_confirmacao_guard on public.pagamentos_vendedor;
create trigger trg_pv_confirmacao_guard before insert or update on public.pagamentos_vendedor
    for each row execute function public.pv_confirmacao_guard();

notify pgrst, 'reload schema';
