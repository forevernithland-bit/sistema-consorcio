-- ==========================================================================
-- Migração 20 — regras de lance por grupo Yamaha (embutido / lance fixo)
-- Rodar uma vez no SQL editor do Supabase (depois da 19).
--
-- Origem dos dados: worker/coletar_tabelas_yamaha.py lê as tabelas de preço
-- em PDF de  G:\Meu Drive\CONSORBENS\Tabelas\YAMAHA  e grava aqui o embutido
-- máximo e o(s) lance(s) fixo(s) de cada grupo. Quando não há tabela do
-- grupo na pasta, vale a REGRA GERAL por produto (está no botão "Lembretes"
-- do simulador e em references/regras-lance-yamaha.md):
--   Embutido:  Moto 15% · Auto 15% · Imóvel 25% · Caminhão 30%
--   Lance fixo: Moto 35%/25% (emb 15%) · Auto 35% (emb 15%)
--               Imóvel 30% (emb 25%) · Caminhão 25%
-- ==========================================================================

alter table grupos_yamaha
    add column if not exists embutido_max_pct   int,        -- % máx. de lance embutido do grupo
    add column if not exists lance_fixo_pct     jsonb,      -- ex.: [25] ou [25,35]
    add column if not exists lance_regras_fonte jsonb,      -- {embutido:'tabela'|'regra_geral', lance_fixo:..., arquivo:'...'}
    add column if not exists lance_regras_em    timestamptz;

comment on column grupos_yamaha.embutido_max_pct is
  'Lance embutido máximo do grupo (da tabela de preço em PDF). NULL = usar regra geral por produto.';
comment on column grupos_yamaha.lance_fixo_pct is
  'Lista de % de lance fixo do grupo, ex.: [25] ou [25,35]. NULL = usar regra geral por produto.';

-- grupos inseridos só a partir da tabela de preço (sem passar pelo robô de
-- vagas ainda) ficam com fonte = 'tabela_pdf'; o coletar_grupos.py depois
-- completa vagas / parcela / taxa e muda a fonte para 'newcon'.
