# -*- coding: utf-8 -*-
"""testar_lance_simulado.py (16/11/2026) — testa o robô de lance SEM ENVIAR NADA.
Usa o navegador único (mesma janela logada), abre a Oferta de Lance da cota,
preenche a modalidade/percentuais e clica em "Simular..." — NUNCA em Confirmar.

    py -V:3.14 testar_lance_simulado.py 9538 644 "Lance Livre" 60 15 [Prazo]
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from coletar_grupos import _abrir, _conectar_sb
import newcon

g, c, tipo = sys.argv[1], sys.argv[2], sys.argv[3]
pct = float(sys.argv[4]) if len(sys.argv) > 4 else None
emb = float(sys.argv[5]) if len(sys.argv) > 5 else 0
red = "Reduzir Prazo" if len(sys.argv) > 6 and "prazo" in sys.argv[6].lower() else "Reduzir Parcela"
pedido = {"grupo": g, "cota": c, "cliente": "", "tipo_lance": tipo, "pct_lance": pct,
          "pct_embutido": emb, "tipo_reducao": red, "simular": True}
pw, aba, ctx, page = _abrir(_conectar_sb(), visivel=True)
try:
    st, msg, prot = newcon.ofertar_lance(page, pedido, 60)
    print("STATUS:", st)
    print("MSG:", msg)
    assert st != "OK", "não era para confirmar!"
finally:
    aba.close(); pw.stop()
