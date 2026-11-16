# -*- coding: utf-8 -*-
"""analisar_calibracao.py — compara o MODELO do simulador com cada "Simular..." real do Newcon
(conhecimento_newcon/calibracao_simulador.json) e mostra a diferença de cada campo.
    py -V:3.14 analisar_calibracao.py
"""
import os
import json
import math

ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conhecimento_newcon", "calibracao_simulador.json")


def modelo(cred, tx, n, k, red, p, e, dif_pct, mod_fixo=None):
    """Mesmas regras do _calcLanceNewcon do yamaha.html (versão calibrada)."""
    C1 = cred * (1 + tx)
    redCred = cred * (1 - red)
    pura_paga = redCred * (1 + tx) / n
    sd = C1 - k * pura_paga
    if red > 0:
        B = redCred * (1 + tx)
        Bemb = B
    else:
        B = BASE_INTEGRAL(cred, tx, n, k)
        Bemb = cred
    L = p * B
    emb = e * Bemb
    dif = dif_pct * cred
    A = L - dif
    nPag = n - k
    return {"lance": L, "emb": emb, "rec": L - emb - dif, "sd": sd, "sd_novo": sd - A,
            "parc_lance": math.floor((L - dif_pct * B) / pura_paga + 1e-9), "pura": pura_paga, "B": B,
            "delta_parcela": A / nPag}


FATOR_INTEGRAL = 0.96191   # 16/11/2026: base do lance integral = 96,191% de C1 (9029, 9542, 9569, 9600/302;
                           # 9600/454 deu 0,96410) — independe de n e de pagas


def BASE_INTEGRAL(cred, tx, n, k):
    return FATOR_INTEGRAL * cred * (1 + tx)


def main():
    d = json.load(open(ARQ, encoding="utf-8"))
    for gc, r in d.items():
        p = r.get("posicao") or {}
        cs = [c for c in r["cenarios"].values() if c.get("lblVL_Lance")]
        if not cs or p.get("taxa_pct") is None:
            continue
        c0 = cs[0]
        cred = c0["lblVlCredito"]; tx = (p["taxa_pct"] + (p.get("fr_pct") or 0)) / 100
        k = int(p["pagas"]); nPag = int(c0["lblPclPagar"]); n = k + nPag
        red = (p.get("pct_cont") or 0) / 100
        dif = (p.get("dif_grupo_pct") or 0) / 100
        m0 = modelo(cred, tx, n, k, red, 0, 0, dif)
        seg = p["parcela"] - m0["pura"]
        print(f"\n== {gc} {p.get('plano_venda')} | cred {cred:,.0f} taxa {tx*100:.3f}% n {n} pagas {k} "
              f"{'PR '+str(int(red*100))+'%' if red else 'integral'} dif {dif*100:.4f}% | "
              f"sd Newcon {p['sd']:,.2f} modelo {m0['sd']:,.2f} | seguro implícito {seg:,.2f} "
              f"({seg/(cred*(1+tx))*100:.4f}% de C1)")
        # base do lance real (ajuste linear)
        pts = [(c["lblPE_Lance"] / 100, c["lblVL_Lance"]) for c in cs]
        if len({x for x, _ in pts}) >= 2:
            (x1, y1), (x2, y2) = sorted(set(pts))[0], sorted(set(pts))[-1]
            a = (y2 - y1) / (x2 - x1); b = y1 - a * x1
            print(f"   base real do lance: {a:,.2f} (+{b:,.2f}) | modelo {m0['B']:,.2f} | "
                  f"real/C1 {a/(cred*(1+tx)):.5f} real/cred {a/cred:.5f} real/pura {a/m0['pura']:.3f}")
        for ch, c in r["cenarios"].items():
            if not c.get("lblVL_Lance"):
                continue
            pp = c["lblPE_Lance"] / 100
            e = (cred - c["lblVlCreditoNovo"]) / (m0["B"] if red else cred) if c.get("lblVlCreditoNovo") else 0
            m = modelo(cred, tx, n, k, red, pp, e, dif)
            pos = c["lblPclPagar"] - c["lblPclPagarNovo"] if "Prazo" in ch else None
            parc = (p["parcela"] - m["delta_parcela"]) if "Parcela" in ch else None
            print(f"   {ch:<28} lance {c['lblVL_Lance']:>11,.2f} Δ{m['lance']-c['lblVL_Lance']:>9,.2f} | "
                  f"rec Δ{m['rec']-c['lblVlRecursos']:>8,.2f} | sdNovo Δ{m['sd_novo']-c['lblSdDevedorNovo']:>8,.2f} | "
                  + (f"parcela {c['lblVL_Parcela']:,.2f} Δ{parc-c['lblVL_Parcela']:+.2f}" if parc is not None and c.get('lblVL_Parcela') else "")
                  + (f"parcelas amortiz. {pos} modelo {m['parc_lance']}" if pos is not None else ""))


if __name__ == "__main__":
    main()
