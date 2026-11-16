# -*- coding: utf-8 -*-
"""backfill_2fixo.py (16/11/2026) — corrige yamaha_assembleias já gravadas:
n_2lance_fixo e n_lance_fixo / lance_fixo_medio, recalculados a partir de
yamaha_contemplacoes (o Newcon escreve '2o Lance Fixo', que antes não era contado).
    py -V:3.14 backfill_2fixo.py            # só mostra
    py -V:3.14 backfill_2fixo.py --salvar   # grava
"""
import sys
import os
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coletar_grupos import _conectar_sb
from coletar_assembleias import _col_mod, _eh_2fixo

sb = _conectar_sb()
linhas, ini = [], 0
while True:
    d = (sb.table("yamaha_contemplacoes").select("*").range(ini, ini + 999).execute().data or [])
    linhas += d
    if len(d) < 1000:
        break
    ini += 1000
print("contemplações lidas:", len(linhas))
if linhas:
    print("colunas:", sorted(linhas[0].keys()))

chave_ass = "num_assembleia" if "num_assembleia" in linhas[0] else "data_assembleia"
por = defaultdict(list)
for x in linhas:
    if (x.get("situacao") or "ativo") != "ativo":
        continue
    por[(str(x["grupo"]), x.get(chave_ass))].append(x)

ass = sb.table("yamaha_assembleias").select("grupo,num_assembleia,data_assembleia,n_lance_fixo,n_2lance_fixo,lance_fixo_medio") \
    .range(0, 4999).execute().data or []
mud = 0
for a in ass:
    ls = por.get((str(a["grupo"]), a.get(chave_ass)))
    if not ls:
        continue
    n2 = sum(1 for x in ls if _eh_2fixo(x.get("modalidade")))
    n1 = sum(1 for x in ls if _col_mod(x.get("modalidade")) == "n_lance_fixo")
    fx = [float(x["pct_lance"]) for x in ls if _col_mod(x.get("modalidade")) == "n_lance_fixo" and x.get("pct_lance")]
    med = round(sum(fx) / len(fx), 4) if fx else None
    # só mexe onde achou 2º fixo que não foi contado (a tabela de contemplações pode
    # não ter todas as linhas antigas; o resto da assembleia fica como estava)
    if n2 <= (a.get("n_2lance_fixo") or 0):
        continue
    # o contador antigo de "Lance Fixo" já NÃO incluía o 2º fixo (só a média misturava)
    novo = {"n_2lance_fixo": n2, "n_lance_fixo": a.get("n_lance_fixo") or n1, "lance_fixo_medio": med}
    velho = {k: a.get(k) for k in novo}
    if any((velho[k] or 0) != (novo[k] or 0) for k in novo):
        mud += 1
        print(f"  {a['grupo']} ass {a.get('num_assembleia')}: {velho} -> {novo}")
        if "--salvar" in sys.argv:
            sb.table("yamaha_assembleias").update(novo).eq("grupo", a["grupo"]).eq("num_assembleia", a["num_assembleia"]).execute()
print(f"assembleias corrigidas: {mud}" + ("" if "--salvar" in sys.argv else " (prévia; --salvar grava)"))
