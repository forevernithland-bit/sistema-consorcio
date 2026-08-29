"""
importar_lote_comissoes.py — Importa em lote os PDFs de "Comissoes Pagas" da Yamaha.

Faz EXATAMENTE o que a tela "Importar Comissoes" do ERP faz, um PDF por vez:
  1. Le o PDF (parse_pdf_yamaha) -> cotas + periodo + total da nota
  2. Casa cada cota com a base `vendas` por GRUPO+COTA -> cliente, vendedor, admin
  3. Calcula imposto (config_interna.Imposto) e divide entre Breno/Uriel
     (mesma funcao dividir_socios do modulo da tela)
  4. Grava em `comissoes_pagas` (historico quinzenal detalhado)
  5. Da baixa da parcela em `status_comissoes` (Status=PAGO)

E IDEMPOTENTE: se a chave_unica ja existir em comissoes_pagas, a linha e pulada.
Assim da pra rodar de novo sem duplicar (os periodos ja importados sao ignorados).

USO:
    python importar_lote_comissoes.py                  # ANALISE (nao grava nada)
    python importar_lote_comissoes.py --confirmar      # grava de verdade
    python importar_lote_comissoes.py --so 2026-04     # so os PDFs desse mes
    python importar_lote_comissoes.py --pasta "C:\\..."

Antes de gravar, rode sem --confirmar e resolva o que aparecer em PROBLEMAS.
"""

import os
import re
import sys
import glob
import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "modulos"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PASTA_PDFS = os.path.join(os.path.expanduser("~"), "Downloads", "Comissoes Yamaha")
ADMIN_PADRAO = "YAMAHA"
CAMINHO_SECRETS = Path(r"G:\Meu Drive\CLODE\ERP_CONSORBENS\.streamlit\secrets.toml")


# --------------------------------------------------------------------------
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


def _norm_gc(v):
    """Normaliza grupo/cota (tira zeros a esquerda) — igual ao _norm da tela."""
    s = str(v or "").strip()
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s


def _mes_competencia(data_fim):
    try:
        return datetime.datetime.strptime(data_fim, "%d/%m/%Y").strftime("%Y-%m")
    except (ValueError, TypeError):
        return ""


def _dt(p):
    return datetime.datetime.strptime(p, "%d/%m/%Y").date()


# --------------------------------------------------------------------------
def carregar_contexto():
    """Le vendas, config e o que ja foi importado."""
    vendas = sb().table("vendas").select("*").execute().data or []
    idx = {}
    for v in vendas:
        idx[(_norm_gc(v.get("GRUPO")), _norm_gc(v.get("COTA")))] = v

    cfg = (sb().table("config_interna").select("*").execute().data or [{}])[0]

    ja = sb().table("comissoes_pagas").select("chave_unica").execute().data or []
    chaves = {r.get("chave_unica") for r in ja}
    return idx, cfg, chaves


def dividir_socios(vendedor, liquido, cfg):
    """Copia fiel de modulos/importar_comissoes.py::dividir_socios."""
    v = (vendedor or "").strip().upper()
    f = lambda k, d: float(cfg.get(k, d) or d)
    if v == "BRENO LIMA":
        b = liquido * f("Breno_Breno", 70.0) / 100.0
        u = liquido * f("Breno_Uriel", 30.0) / 100.0
    elif v == "URIEL GOMES":
        u = liquido * f("Uriel_Uriel", 70.0) / 100.0
        b = liquido * f("Uriel_Breno", 30.0) / 100.0
    elif v == "CONSORBENS":
        b = liquido * f("Cons_Breno", 50.0) / 100.0
        u = liquido * f("Cons_Uriel", 50.0) / 100.0
    elif v == "PARTICULAR BRENO":
        b, u = liquido, 0.0
    elif v == "PARTICULAR URIEL":
        b, u = 0.0, liquido
    else:  # Vendedor Terceiro / nao identificado -> 50/50 (igual a tela)
        b = liquido * 0.5
        u = liquido * 0.5
    return round(b, 2), round(u, 2)


# ---------------------------------------------------------------------------
# Leitor do PDF (Comissoes Pagas - Analitico)
#
# Cada linha de cota traz, DEPOIS do percentual (ex.: "1,0500"), exatamente 10
# colunas monetarias, nesta ordem:
#   0 Calc.Comis (credito)  1 $Comissao  2 $Estorno  3 $CancCota  4 $Reativ.
#   5 $Atraso    6 $IR      7 $Base      8 $Abat.    9 $Liquido
# O que a Ecoclim REALMENTE recebeu na linha e o $Liquido (col. 9) — e ele que
# pode vir negativo (cota cancelada) ou positivo sem comissao (reativacao).
# ---------------------------------------------------------------------------
RE_GRUPO_COTA = re.compile(r"(\d{6})-(\d{4})-\d{2}")
RE_PCT_TOKEN = re.compile(r"\b\d{1,2},\d{4}\b")
RE_MONEY = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}")
RE_INT_PEQ = re.compile(r"^\d{1,2}$")
RE_PERIODO = re.compile(r"Encerramento de:\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})")
RE_TOTAL = re.compile(
    r"Total (?:de Comiss.o do Per.odo|Geral):\s*\(\s*(\d+)\s*\)\s*(?P<corpo>[-\d.,\s]+)")


def _v(s):
    return float(str(s).replace(".", "").replace(",", "."))


def ler_pdf(caminho):
    """Retorna (cotas, info). cotas tem credito, comissao e liquido por linha."""
    import pdfplumber
    with pdfplumber.open(caminho) as pdf:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages)

    info = {"periodo_ini": "", "periodo_fim": "", "total_nf": None,
            "total_liquido": None, "qtd_nf": None}
    mp = RE_PERIODO.search(txt)
    if mp:
        info["periodo_ini"], info["periodo_fim"] = mp.group(1), mp.group(2)
    mts = list(RE_TOTAL.finditer(txt))
    if mts:
        m = mts[-1]                       # o ultimo rodape e o "Total Geral"
        info["qtd_nf"] = int(m.group(1))
        vals = [_v(x) for x in RE_MONEY.findall(m.group("corpo"))]
        if len(vals) >= 2:
            info["total_nf"] = vals[1]       # $ Comissao
            info["total_liquido"] = vals[-1]  # $ Liquido

    cotas = []
    for linha in txt.splitlines():
        m = RE_GRUPO_COTA.search(linha)
        if not m:
            continue
        grupo, cota = str(int(m.group(1))), str(int(m.group(2)))
        resto = linha[m.end():]
        parcela = next((t for t in resto.split() if RE_INT_PEQ.match(t)), "")
        mp2 = RE_PCT_TOKEN.search(resto)
        if not mp2:
            continue
        vals = [_v(x) for x in RE_MONEY.findall(resto[mp2.end():])]
        if len(vals) < 10:
            continue
        cotas.append({
            "grupo": grupo, "cota": cota, "parcela": str(parcela),
            "credito": vals[0], "comissao": vals[1], "estorno": vals[2],
            "canc_cota": vals[3], "reativ": vals[4], "atraso": vals[5],
            "ir": vals[6], "abatimento": vals[8],
            "valor_nota": vals[9],       # $ Liquido = o que entrou de fato
        })
    return cotas, info


def analisar_pdf(caminho, idx_vendas, cfg):
    """Le o PDF e monta as linhas prontas (com calculo), sem gravar."""
    cotas, info = ler_pdf(caminho)
    imp_pct = float(cfg.get("Imposto", 7.16) or 7.16)

    linhas, problemas = [], []
    for c in cotas:
        chave_gc = (_norm_gc(c["grupo"]), _norm_gc(c["cota"]))
        v = idx_vendas.get(chave_gc)
        if v:
            cliente = str(v.get("NOME") or "")
            vendedor = str(v.get("VENDEDOR") or "")
            admin = str(v.get("ADMINISTRADORA") or ADMIN_PADRAO)
        else:
            cliente, vendedor, admin = "", "", ADMIN_PADRAO
            problemas.append(f"cota {c['grupo']}/{c['cota']} (parc {c['parcela']}, "
                             f"nota {brl(c['valor_nota'])}) NAO existe em `vendas`")
        if v and not vendedor.strip():
            problemas.append(f"cota {c['grupo']}/{c['cota']} sem VENDEDOR cadastrado")
        if v and not cliente.strip():
            problemas.append(f"cota {c['grupo']}/{c['cota']} sem NOME de cliente")

        # Linha de AJUSTE = nao tem comissao propria; o valor veio de
        # cancelamento/reativacao/estorno da cota (pode ser negativo).
        ajuste = (c["comissao"] == 0.0 and c["valor_nota"] != 0.0)
        # Na linha de ajuste a 1a coluna nao e o credito da carta —
        # nesse caso pegamos o credito da propria venda cadastrada.
        credito = float(c["credito"])
        if ajuste and v:
            try:
                credito = float(str(v.get("VALOR") or credito).replace(",", "."))
            except (TypeError, ValueError):
                pass

        vn = float(c["valor_nota"])
        vimp = round(vn * imp_pct / 100.0, 2)
        vliq = round(vn - vimp, 2)
        breno, uriel = dividir_socios(vendedor, vliq, cfg)
        linhas.append({
            "grupo": c["grupo"], "cota": c["cota"], "parcela": c["parcela"],
            "cliente": cliente, "vendedor": vendedor, "admin": admin,
            "credito": credito, "valor_nota": vn,
            "imposto_pct": imp_pct, "imposto": vimp, "liquido": vliq,
            "breno": breno, "uriel": uriel,
            "encontrado": bool(v), "ajuste": ajuste,
            "motivo": ("Cancelamento de cota" if c["canc_cota"] else
                       "Reativacao de cota" if c["reativ"] else
                       "Estorno" if c["estorno"] else "") if ajuste else "",
            "chave": f"{cliente}_{c['grupo']}_{c['cota']}_{admin}_{c['parcela']}",
        })
    return linhas, info, problemas


def gravar(linhas, info, chaves_existentes):
    """Grava comissoes_pagas + status_comissoes.

    Idempotencia por (chave_unica, periodo_fim): a MESMA parcela pode aparecer
    em varios periodos (pagamento, depois estorno, depois reativacao) — cada
    ocorrencia e um evento distinto e deve virar uma linha do historico.
    Linhas de AJUSTE nao mexem em `status_comissoes` (a baixa da parcela
    continua sendo a do pagamento original)."""
    data_pgto = info.get("periodo_fim") or ""
    mes = _mes_competencia(data_pgto)
    ok = pulado = erro = 0
    for c in linhas:
        marca = (c["chave"], data_pgto)
        if marca in chaves_existentes:
            pulado += 1
            continue
        try:
            sb().table("comissoes_pagas").insert({
                "administradora": c["admin"],
                "periodo_inicio": info.get("periodo_ini", ""),
                "periodo_fim": data_pgto,
                "mes_competencia": mes,
                "grupo": c["grupo"], "cota": c["cota"], "parcela": c["parcela"],
                "cliente": c["cliente"], "vendedor": c["vendedor"],
                "credito": c["credito"], "valor_nota": c["valor_nota"],
                "imposto_pct": c["imposto_pct"], "valor_imposto": c["imposto"],
                "valor_liquido": c["liquido"], "breno": c["breno"], "uriel": c["uriel"],
                "data_pagamento": data_pgto, "origem": "NF", "chave_unica": c["chave"],
            }).execute()

            ex = sb().table("status_comissoes").select("id").eq("Chave_Unica", c["chave"]).execute()
            payload = {"Chave_Unica": c["chave"], "Status": "PAGO",
                       "Valor_Pago": c["valor_nota"], "Data_Pagamento": data_pgto}
            if ex.data:
                sb().table("status_comissoes").update(payload).eq("id", ex.data[0]["id"]).execute()
            else:
                sb().table("status_comissoes").insert(payload).execute()

            chaves_existentes.add(c["chave"])
            ok += 1
        except Exception as e:
            erro += 1
            print(f"      ERRO {c['grupo']}/{c['cota']} parc {c['parcela']}: {str(e)[:120]}")
    return ok, pulado, erro


# --------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return
    confirmar = "--confirmar" in args
    pasta = PASTA_PDFS
    if "--pasta" in args:
        pasta = args[args.index("--pasta") + 1]
    filtro = args[args.index("--so") + 1] if "--so" in args else None

    pdfs = [p for p in sorted(glob.glob(os.path.join(pasta, "*.pdf")))
            if "GERAL" not in os.path.basename(p).upper()]
    if filtro:
        pdfs = [p for p in pdfs if filtro in os.path.basename(p)]
    if not pdfs:
        print(f"Nenhum PDF quinzenal em {pasta}")
        return

    print(f"\n{'='*94}")
    print(f"{'IMPORTACAO DE COMISSOES YAMAHA':^94}")
    print(f"{('GRAVANDO NO BANCO' if confirmar else 'MODO ANALISE — nada sera gravado'):^94}")
    print(f"{'='*94}\n")

    idx_vendas, cfg, chaves = carregar_contexto()
    print(f"base: {len(idx_vendas)} cotas em `vendas` | imposto {cfg.get('Imposto')}% | "
          f"{len(chaves)} comissao(oes) ja importada(s)\n")

    print(f"{'Periodo':<25} {'N':>3} {'Nota (PDF)':>13} {'Soma cotas':>13} "
          f"{'Breno':>11} {'Uriel':>11}  Situacao")
    print("-" * 94)

    tot = {"n": 0, "nota": 0.0, "liq": 0.0, "breno": 0.0, "uriel": 0.0,
           "ok": 0, "pulado": 0, "erro": 0}
    problemas_geral = []
    faltantes = {}

    for p in pdfs:
        linhas, info, probs = analisar_pdf(p, idx_vendas, cfg)
        per = f"{info.get('periodo_ini','?')} a {info.get('periodo_fim','?')}"
        soma = sum(l["valor_nota"] for l in linhas)
        sb_, su_ = sum(l["breno"] for l in linhas), sum(l["uriel"] for l in linhas)
        nf = info.get("total_nf")

        marcas = []
        if nf is not None and abs(soma - nf) > 0.01:
            marcas.append(f"nota difere {brl(abs(soma-nf))}")
        nao_ach = [l for l in linhas if not l["encontrado"]]
        if nao_ach:
            marcas.append(f"{len(nao_ach)} cota(s) fora do sistema")
        ja_imp = sum(1 for l in linhas if l["chave"] in chaves)
        if ja_imp:
            marcas.append(f"{ja_imp} ja importada(s)")

        for l in nao_ach:
            faltantes.setdefault((l["grupo"], l["cota"]), {"cred": l["credito"], "per": [], "n": 0})
            faltantes[(l["grupo"], l["cota"])]["per"].append(per)
            faltantes[(l["grupo"], l["cota"])]["n"] += 1

        status = "OK" if not marcas else " | ".join(marcas)
        print(f"{per:<25} {len(linhas):>3} "
              f"{(brl(nf) if nf is not None else '--'):>13} {brl(soma):>13} "
              f"{brl(sb_):>11} {brl(su_):>11}  {status}")

        problemas_geral.extend(f"[{per}] {x}" for x in probs)
        tot["n"] += len(linhas); tot["nota"] += soma
        tot["liq"] += sum(l["liquido"] for l in linhas)
        tot["breno"] += sb_; tot["uriel"] += su_

        if confirmar:
            o, pu, er = gravar(linhas, info, chaves)
            tot["ok"] += o; tot["pulado"] += pu; tot["erro"] += er

    print("-" * 94)
    print(f"{'TOTAL':<25} {tot['n']:>3} {'':>13} {brl(tot['nota']):>13} "
          f"{brl(tot['breno']):>11} {brl(tot['uriel']):>11}")
    print(f"\n  Liquido (apos imposto): {brl(tot['liq'])}   "
          f"[Breno {brl(tot['breno'])} + Uriel {brl(tot['uriel'])}]")

    if faltantes:
        print(f"\n{'='*94}")
        print(f"PROBLEMAS — {len(faltantes)} cota(s) NAO cadastrada(s) em `vendas`:")
        print(f"{'='*94}")
        print(f"  {'Grupo/Cota':<14} {'Credito':>16} {'Parcelas':>9}   Periodos")
        for (g, c), d in sorted(faltantes.items(), key=lambda x: (int(x[0][0]), int(x[0][1]))):
            pers = ", ".join(d["per"][:3]) + (f" (+{len(d['per'])-3})" if len(d["per"]) > 3 else "")
            print(f"  {g+'/'+c:<14} {brl(d['cred']):>16} {d['n']:>9}   {pers}")
        print("\n  -> Cadastre essas cotas (vendas.py cadastrar / adicionar-cota) e rode de novo.")

    outros = [x for x in problemas_geral if "NAO existe em" not in x]
    if outros:
        print(f"\nOUTROS AVISOS ({len(outros)}):")
        for x in outros[:40]:
            print("  -", x)

    if confirmar:
        print(f"\n{'='*94}")
        print(f"GRAVADO: {tot['ok']} nova(s) | {tot['pulado']} ja existia(m) | {tot['erro']} erro(s)")
        print(f"{'='*94}")
    else:
        print(f"\n>>> MODO ANALISE — nada foi gravado.")
        print(f">>> Para gravar:  python importar_lote_comissoes.py --confirmar")


if __name__ == "__main__":
    main()
