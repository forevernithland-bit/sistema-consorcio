-- Portal de Mídias: arquivos enviados pelo Master (arrastar e soltar) no próprio ERP.
-- (A conta de serviço do Google Drive não tem cota para gravar, por isso o envio vai para o Supabase Storage.)
-- Rode uma vez no SQL Editor do Supabase.

insert into storage.buckets (id, name, public, file_size_limit)
values ('midias', 'midias', true, 52428800)           -- público para leitura (link), até 50 MB por arquivo
on conflict (id) do update set public = true, file_size_limit = 52428800;

drop policy if exists midias_ler on storage.objects;
drop policy if exists midias_enviar on storage.objects;
create policy midias_ler    on storage.objects for select to anon, authenticated using (bucket_id = 'midias');
create policy midias_enviar on storage.objects for insert to anon, authenticated with check (bucket_id = 'midias');

create table if not exists public.midias (
    id          bigserial primary key,
    nome        text not null,
    mime        text,
    tamanho     bigint,
    md5         text,
    caminho     text not null,
    enviado_por text,
    criado_em   timestamptz not null default now()
);
alter table public.midias enable row level security;
drop policy if exists midias_acesso on public.midias;
create policy midias_acesso on public.midias for all to anon, authenticated using (true) with check (true);
