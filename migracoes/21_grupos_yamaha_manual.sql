-- ==========================================================================
-- Migração 21 — edição manual da Base de Dados Yamaha (sem robô)
-- Rodar uma vez no SQL editor do Supabase (depois da 20).
--
-- Permite o vendedor cadastrar/editar grupo e lançar resultado de assembleia
-- direto na aba "Base de Dados" do Simulador Yamaha. Marca fonte='manual' e
-- guarda quem editou e quando.
-- ==========================================================================

alter table grupos_yamaha
    add column if not exists parcela_reduzida boolean,      -- grupo de Parcela Reduzida?
    add column if not exists atualizado_por   text,         -- ex.: 'manual: uriel'
    add column if not exists atualizado_em    timestamptz;  -- quando foi editado (robô ou manual)

alter table yamaha_assembleias
    add column if not exists atualizado_por   text;         -- ex.: 'manual: uriel'

comment on column grupos_yamaha.atualizado_em is
  'Data da última atualização (robô ou edição manual na tela). consultado_em = última checagem de vagas.';
comment on column grupos_yamaha.parcela_reduzida is
  'Marcado quando o grupo é de plano Parcela Reduzida (o simulador mostra o selo e pré-seleciona Parcela Reduzida).';
