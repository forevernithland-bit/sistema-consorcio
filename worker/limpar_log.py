"""
limpar_log.py — Limpeza do log de lances (fila_automacao).

O que faz:
  * Remove TODOS os registros com ERRO.
  * Remove DUPLICADOS: se a mesma cota (grupo+cota) tiver mais de um registro OK
    no mesmo mês, mantém só o mais recente.
  * Mantém PENDENTE/PROCESSANDO (trabalho em andamento) intactos.
Ou seja, fica só o "OK" (SUCESSO / JÁ OFERTADO), um por cota por mês.

    python limpar_log.py
"""

import os
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

OK = ("SUCESSO", "JA_OFERTADO")

res = sb.table("fila_automacao").select("*").eq("tipo", "LANCE").execute()
dados = res.data or []

apagar = set()

# 1) Todos os erros
for r in dados:
    if (r.get("status") or "").upper() == "ERRO":
        apagar.add(r["id"])

# 2) Duplicados de OK por (grupo, cota, mês) — mantém o mais recente
oks = defaultdict(list)
for r in dados:
    if (r.get("status") or "").upper() in OK:
        ym = (r.get("criado_em") or "")[:7]  # AAAA-MM
        oks[(r.get("grupo"), r.get("cota"), ym)].append(r)

for _, recs in oks.items():
    if len(recs) > 1:
        recs.sort(key=lambda r: r.get("criado_em") or "", reverse=True)
        for r in recs[1:]:
            apagar.add(r["id"])

print(f"Total de registros de LANCE: {len(dados)}")
print(f"A remover (erros + duplicados): {len(apagar)}")

for rid in apagar:
    sb.table("fila_automacao").delete().eq("id", rid).execute()

print(f"Removidos: {len(apagar)}. Mantidos: {len(dados) - len(apagar)}.")
print("Concluído.")
