"""
limpar_simulacao.py — Remove do log as linhas de TESTE (simulação).
Apaga apenas registros cuja mensagem contém 'SIMULA' ou protocolo 'SIMULACAO'.
Os lances reais NÃO são tocados.
    python limpar_simulacao.py
"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

res = sb.table("fila_automacao").select("id,cliente,grupo,cota,mensagem,protocolo").execute()

alvos = []
for r in (res.data or []):
    msg = (r.get("mensagem") or "").upper()
    prot = (r.get("protocolo") or "").upper()
    if "SIMULA" in msg or prot == "SIMULACAO":
        alvos.append(r)

print(f"{len(alvos)} linha(s) de simulacao encontrada(s):")
for r in alvos:
    print(f"  #{r['id']} {r.get('cliente')} - {r.get('grupo')}/{r.get('cota')}")

for r in alvos:
    sb.table("fila_automacao").delete().eq("id", r["id"]).execute()

print("Removidas com sucesso." if alvos else "Nada a remover.")
