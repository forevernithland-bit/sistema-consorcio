"""
corrigir_log.py — Correção pontual do log de lances no CRM.

Use quando um lance foi REALMENTE ofertado no Newcon (tem protocolo), mas o CRM
registrou como ERRO por causa de falha antiga na leitura do comprovante.

Preencha a lista CORRECOES com grupo, cota e protocolo (confira no Newcon) e rode:
    python corrigir_log.py
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Lances que já foram ofertados de verdade (protocolo conferido no Newcon):
CORRECOES = [
    {"grupo": "9048", "cota": "332", "protocolo": "5439150"},
]

for c in CORRECOES:
    res = (sb.table("fila_automacao")
           .update({
               "status": "SUCESSO",
               "protocolo": c["protocolo"],
               "mensagem": f"Corrigido manualmente — lance confirmado no Newcon (protocolo {c['protocolo']}).",
               "concluido_em": datetime.now(timezone.utc).isoformat(),
           })
           .eq("tipo", "LANCE").eq("grupo", c["grupo"]).eq("cota", c["cota"]).eq("status", "ERRO")
           .execute())
    n = len(res.data or [])
    print(f"Grupo {c['grupo']}/Cota {c['cota']} -> {n} registro(s) corrigido(s) "
          f"para SUCESSO (protocolo {c['protocolo']}).")

print("Concluído.")
