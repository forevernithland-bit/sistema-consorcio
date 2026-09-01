"""
limpar_comissoes_duplicadas.py — acha e remove linhas 100% duplicadas em
`comissoes_pagas` (a mesma nota importada duas vezes pela tela
"Importar Comissoes", que faz insert cego, sem checar se ja existia).

Duas linhas sao a MESMA importacao quando batem, campo a campo, em:
  chave_unica, periodo_inicio, periodo_fim, grupo, cota, parcela,
  valor_nota, valor_liquido, breno, uriel, origem
Mantem a de MENOR id (a 1a importacao) e remove as copias. NAO mexe em
`status_comissoes` — a linha que fica ja sustenta a baixa PAGO.

USO:
    python limpar_comissoes_duplicadas.py                    # ANALISE (nao apaga)
    python limpar_comissoes_duplicadas.py --confirmar        # apaga de verdade
    python limpar_comissoes_duplicadas.py --periodo 31/08/2026   # so esse periodo_fim
"""

import sys
from pathlib import Path

CAMINHO_SECRETS = Path(r"G:\Meu Drive\CLODE\ERP_CONSORBENS\.streamlit\secrets.toml")


def _secrets():
    valores = {}
    for linha in CAMINHO_SECRETS.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or linha.startswith("["):
            continue
        if "=" in linha:
            k, _, v = linha.partition("=")
            valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


_SB = None


def sb():
    global _SB
    if _SB is None:
        from supabase import create_client
        s = _secrets()
        _SB = create_client(s["SUPABASE_URL"], s["SUPABASE_KEY"])
    return _SB


def brl(v):
    return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _n(v):
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def chave_linha(r):
    return (
        str(r.get("chave_unica") or ""),
        str(r.get("periodo_inicio") or ""),
        str(r.get("periodo_fim") or ""),
        str(r.get("grupo") or ""),
        str(r.get("cota") or ""),
        str(r.get("parcela") or ""),
        _n(r.get("valor_nota")),
        _n(r.get("valor_liquido")),
        _n(r.get("breno")),
        _n(r.get("uriel")),
        str(r.get("origem") or ""),
    )


def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return
    confirmar = "--confirmar" in args
    periodo = args[args.index("--periodo") + 1] if "--periodo" in args else None

    q = sb().table("comissoes_pagas").select("*")
    if periodo:
        q = q.eq("periodo_fim", periodo)
    linhas = q.execute().data or []
    print(f"\n{'='*92}")
    print(f"{'LIMPEZA DE COMISSOES DUPLICADAS':^92}")
    print(f"{('APAGANDO DE VERDADE' if confirmar else 'MODO ANALISE - nada sera apagado'):^92}")
    print(f"{'='*92}")
    print(f"\n{len(linhas)} linha(s) lida(s) de comissoes_pagas"
          + (f" (periodo_fim = {periodo})" if periodo else "") + "\n")

    grupos = {}
    for r in linhas:
        grupos.setdefault(chave_linha(r), []).append(r)

    dups = {k: v for k, v in grupos.items() if len(v) > 1}
    if not dups:
        print(">>> Nenhuma duplicata encontrada. Nada a fazer.")
        return

    apagar_ids = []
    tot_nota = tot_breno = tot_uriel = 0.0
    print(f"{'Grupo/Cota':<13} {'Parc':>4} {'Periodo fim':>12} {'Copias':>7} "
          f"{'Valor nota':>13}  IDs (mantem / apaga)")
    print("-" * 92)
    for k, rows in sorted(dups.items(), key=lambda x: (x[0][3], x[0][4], x[0][5])):
        rows.sort(key=lambda r: r["id"])
        manter, remover = rows[0], rows[1:]
        ids_rm = [r["id"] for r in remover]
        apagar_ids.extend(ids_rm)
        n_extra = len(remover)
        tot_nota += _n(manter.get("valor_nota")) * n_extra
        tot_breno += _n(manter.get("breno")) * n_extra
        tot_uriel += _n(manter.get("uriel")) * n_extra
        print(f"{(manter.get('grupo','?')+'/'+manter.get('cota','?')):<13} "
              f"{str(manter.get('parcela','')):>4} {str(manter.get('periodo_fim','')):>12} "
              f"{len(rows):>7} {brl(manter.get('valor_nota')):>13}  "
              f"{manter['id']} / {','.join(map(str, ids_rm))}")

    print("-" * 92)
    print(f"\n{len(dups)} chave(s) duplicada(s) | {len(apagar_ids)} linha(s) sobrando para apagar")
    print(f"Inflacao que sai do historico:  nota {brl(tot_nota)}  |  "
          f"Breno {brl(tot_breno)}  |  Uriel {brl(tot_uriel)}")

    if not confirmar:
        print(f"\n>>> MODO ANALISE - nada foi apagado.")
        print(f">>> Para apagar:  python limpar_comissoes_duplicadas.py --confirmar"
              + (f" --periodo {periodo}" if periodo else ""))
        return

    print(f"\nApagando {len(apagar_ids)} linha(s)...")
    apagados = 0
    for i in range(0, len(apagar_ids), 50):
        lote = apagar_ids[i:i + 50]
        sb().table("comissoes_pagas").delete().in_("id", lote).execute()
        apagados += len(lote)
        print(f"  {apagados}/{len(apagar_ids)}")
    print(f"\n>>> OK: {apagados} linha(s) duplicada(s) removida(s). "
          f"status_comissoes intacto (a linha original sustenta a baixa).")


if __name__ == "__main__":
    main()
