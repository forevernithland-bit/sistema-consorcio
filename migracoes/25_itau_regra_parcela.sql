-- 25_itau_regra_parcela.sql
-- Comissão do Itaú: 4% no total, diluído linearmente, com nº de parcelas
-- variando por PRODUTO x TIPO DE PARCELA (linear x reduzida):
--   Auto   linear   -> 4% em 4  parcelas  = 1,0%   cada
--   Auto   reduzida -> 4% em 8  parcelas  = 0,5%   cada
--   Imóvel linear   -> 4% em 8  parcelas  = 0,5%   cada
--   Imóvel reduzida -> 4% em 12 parcelas  = 0,3333% cada
--
-- Para isso o ERP passa a distinguir o tipo de parcela da cota:
--   * vendas."TIPO_PARCELA"          -> 'Linear' | 'Reduzida' (por cota)
--   * administradoras."Tipo_Parcela" -> 'Linear' | 'Reduzida' | NULL (regra genérica)
-- regras.py casa (Administradora + Produto + Tipo_Parcela); se não houver regra
-- com o tipo, cai na regra genérica (Tipo_Parcela NULL) — Yamaha etc. não muda.
--
-- IMPORTANTE: rode este SQL ANTES (ou junto) de subir o código novo — o app
-- passa a gravar vendas."TIPO_PARCELA" em toda venda/edição de cota.
-- Rodar no SQL Editor do Supabase mgvihpkqeazdxnjpuekt.

-- 0) Confira antes o que casa como "Itaú" (não deve pegar ITAPEVA etc.):
--    select distinct "Administradora" from administradoras where trim(upper("Administradora")) in ('ITAU','ITAÚ');
--    select distinct "ADMINISTRADORA" from vendas          where trim(upper("ADMINISTRADORA")) in ('ITAU','ITAÚ');

-- 1) Colunas novas
alter table vendas          add column if not exists "TIPO_PARCELA" text;
alter table administradoras add column if not exists "Tipo_Parcela" text;

-- 2) Normaliza a administradora "ITAU " (com espaço) / "ITAÚ" -> "ITAU"
update administradoras set "Administradora" = 'ITAU'
 where trim(upper("Administradora")) in ('ITAU', 'ITAÚ');
update vendas set "ADMINISTRADORA" = 'ITAU'
 where trim(upper("ADMINISTRADORA")) in ('ITAU', 'ITAÚ');

-- 3) A regra ITAU/Imóvel que já existia (P1..P8 = 0,5%) é a LINEAR
update administradoras
   set "Tipo_Parcela" = 'Linear'
 where "Administradora" = 'ITAU' and "Produto" = 'Imóvel' and "Tipo_Parcela" is null;

-- 4) Regras que faltavam do Itaú (idempotente: só insere se não existir)
insert into administradoras ("Administradora","Produto","Tipo_Parcela",
       "P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11","P12")
select v."Administradora", v."Produto", v."Tipo_Parcela",
       v.p1,v.p2,v.p3,v.p4,v.p5,v.p6,v.p7,v.p8,v.p9,v.p10,v.p11,v.p12
from (values
  ('ITAU','Auto','Linear',   '1.0%','1.0%','1.0%','1.0%', null,null,null,null, null,null,null,null),
  ('ITAU','Auto','Reduzida', '0.5%','0.5%','0.5%','0.5%','0.5%','0.5%','0.5%','0.5%', null,null,null,null),
  ('ITAU','Imóvel','Reduzida','0.3333%','0.3333%','0.3333%','0.3333%','0.3333%','0.3333%','0.3333%','0.3333%','0.3333%','0.3333%','0.3333%','0.3333%')
) as v("Administradora","Produto","Tipo_Parcela",p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12)
where not exists (
  select 1 from administradoras a
   where a."Administradora" = v."Administradora"
     and a."Produto" = v."Produto"
     and coalesce(a."Tipo_Parcela",'') = v."Tipo_Parcela"
);

-- 5) Tipo de parcela das cotas Itaú já existentes.
--    Warlei Oliveira Gomes (id 59, grupo 40215 / cota 999) é REDUZIDA — confirmado
--    pelo extrato do Itaú: 1ª parcela R$ 999,90 = 0,3333% de 300.000.
update vendas set "TIPO_PARCELA" = 'Reduzida' where id = 59;
--    As demais cotas do Itaú entram como LINEAR (revisar caso a caso na ficha:
--    id 2 Maria Lucia, id 8 Sergio Livio, id 30 Maria Auxiliadora).
update vendas set "TIPO_PARCELA" = 'Linear'
 where "ADMINISTRADORA" = 'ITAU' and ("TIPO_PARCELA" is null or "TIPO_PARCELA" = '');

-- 6) Confira o resultado:
--    select id,"NOME","GRUPO","COTA","PRODUTO","TIPO_PARCELA" from vendas where "ADMINISTRADORA"='ITAU' order by id;
--    select "Administradora","Produto","Tipo_Parcela","P1" from administradoras where "Administradora"='ITAU';
