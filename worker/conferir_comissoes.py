"""
conferir_comissoes.py — Confere os PDFs de "Comissoes Pagas" da Yamaha.

O QUE FAZ (nao toca no Newcon, so le arquivos):
  1. Le todos os PDFs de uma pasta (padrao: pasta de download dos quinzenais).
  2. De cada PDF pega, do RODAPE do proprio relatorio: periodo de encerramento,
     nº de linhas de comissao (N), Base total (credito), $ Comissao total e
     $ Liquido total.
  3. Soma tudo e mostra a tabela do mais antigo para o mais recente.
     Avisa se algum periodo veio DUPLICADO ou se ha BURACO na sequencia quinzenal.
  4. Com --geral <arquivo.pdf> (o relatorio unico de 01/10/2024 ate hoje),
     compara: SOMA DOS QUINZENAIS  x  RELATORIO GERAL. Tem que bater (valor e Nº de linhas).
  5. Se houver .env com SUPABASE, mostra o que ja esta em comissoes_pagas no ERP.

USO:
    python conferir_comissoes.py
    python conferir_comissoes.py --pasta "C:\\Users\\desta\\Downloads\\Comissoes Yamaha"
    python conferir_comissoes.py --geral "C:\\Users\\desta\\Downloads\\GERAL.pdf"
"""

import os
import re
import sys
import glob
import datetime

PASTA_PADRAO = os.path.join(os.path.expanduser("~"), "Downloads", "Comissoes Yamaha")
TOLERANCIA = 0.05  # R$

RE_PERIODO = re.compile(r"Encerramento de:\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})", re.I)
RE_MOEDA = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}")
# Aceita os dois modelos de impressao:
#   Modelo Filial      -> "Total Geral:"            seguido da linha de totais
#   Modelo Comissionado -> "Total de Comissao do Periodo:  ( N )  <valores>"
RE_RODAPE = re.compile(
    r"Total\s+(?:Geral|de\s+Comiss.o\s+do\s+Per.odo|de\s+Comiss.o\s+do\s+Comissionado)"
    # o corpo pode ter valores NEGATIVOS (estorno/cancelamento de cota),
    # por isso o '-' entra na classe de caracteres.
    r"\s*:?\s*\(\s*(?P<n>\d+)\s*\)\s*(?P<corpo>[-\d.,\s]+)",
    re.I,
)


def _ler_texto(caminho):
    try:
        import pdfplumber
        with pdfplumber.open(caminho) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(caminho).pages)


def _brl(s):
    return float(str(s).replace(".", "").replace(",", "."))


def _fmt(v):
    if v is None:
        return "        --"
    return f"{v:>14,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _d(ddmmaaaa):
    return datetime.datetime.strptime(ddmmaaaa, "%d/%m/%Y").date()


def analisar_pdf(caminho):
    txt = _ler_texto(caminho)
    r = {"arquivo": os.path.basename(caminho), "periodo_ini": "", "periodo_fim": "",
         "n": None, "base": None, "comissao": None, "liquido": None}

    mp = RE_PERIODO.search(txt)
    if mp:
        r["periodo_ini"], r["periodo_fim"] = mp.group(1), mp.group(2)

    # Pega a ULTIMA ocorrencia de rodape (a mais "geral": Filial > Ponto de Venda > Comissionado)
    matches = list(RE_RODAPE.finditer(txt))
    if matches:
        m = matches[-1]
        r["n"] = int(m.group("n"))
        vals = [_brl(x) for x in RE_MOEDA.findall(m.group("corpo"))]
        if vals:
            # linha de totais: [Base, $Comissao, $Estorno, $Canc, $Reativ, $Atraso, $IR, $Base2, $Abat, $Liquido]
            r["base"] = vals[0]
            r["comissao"] = vals[1] if len(vals) >= 2 else None
            r["liquido"] = vals[-1]
    return r


def _seq_quinzenas(dini, dfim):
    """Gera os pares (ini, fim) quinzenais esperados entre duas datas."""
    y, m = dini.year, dini.month
    out = []
    while datetime.date(y, m, 1) <= dfim:
        import calendar
        ult = calendar.monthrange(y, m)[1]
        for a, b in ((1, 15), (16, ult)):
            pi, pf = datetime.date(y, m, a), datetime.date(y, m, b)
            if pf >= dini and pi <= dfim:
                out.append((pi, pf))
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def conferir_pasta(pasta, geral=None):
    pdfs = sorted(glob.glob(os.path.join(pasta, "*.pdf")))
    if geral:
        pdfs = [p for p in pdfs if os.path.abspath(p) != os.path.abspath(geral)]
    if not pdfs:
        print(f"Nenhum PDF em {pasta}")
        return

    linhas = [analisar_pdf(p) for p in pdfs]
    com_per = [x for x in linhas if x["periodo_ini"]]
    sem_per = [x for x in linhas if not x["periodo_ini"]]
    com_per.sort(key=lambda x: _d(x["periodo_ini"]))

    print(f"\n=== {len(linhas)} relatorios em {pasta} ===\n")
    print(f"{'Periodo':<25} {'N':>4} {'Base (credito)':>16} {'$ Comissao':>16} {'$ Liquido':>16}")
    print("-" * 82)
    tot_n = 0
    tot_base = tot_com = tot_liq = 0.0
    vistos = {}
    for r in com_per:
        chave = (r["periodo_ini"], r["periodo_fim"])
        vistos[chave] = vistos.get(chave, 0) + 1
        per = f"{r['periodo_ini']} a {r['periodo_fim']}"
        print(f"{per:<25} {(r['n'] if r['n'] is not None else '?'):>4} "
              f"{_fmt(r['base'])} {_fmt(r['comissao'])} {_fmt(r['liquido'])}")
        tot_n += r["n"] or 0
        tot_base += r["base"] or 0.0
        tot_com += r["comissao"] or 0.0
        tot_liq += r["liquido"] or 0.0
    print("-" * 82)
    print(f"{'TOTAL':<25} {tot_n:>4} {_fmt(tot_base)} {_fmt(tot_com)} {_fmt(tot_liq)}")

    dups = {k: v for k, v in vistos.items() if v > 1}
    if dups:
        print("\n[!] Periodos DUPLICADOS na pasta:")
        for (i, f), v in dups.items():
            print(f"   - {i} a {f}  ({v} arquivos)")

    if sem_per:
        print("\n[!] PDFs sem periodo reconhecido (formato inesperado?):")
        for r in sem_per:
            print(f"   - {r['arquivo']}")

    # buraco na sequencia quinzenal
    if com_per:
        esperados = _seq_quinzenas(_d(com_per[0]["periodo_ini"]), _d(com_per[-1]["periodo_fim"]))
        tem = {(_d(x["periodo_ini"]), _d(x["periodo_fim"])) for x in com_per}
        faltando = [p for p in esperados if p not in tem]
        if faltando:
            print("\n[!] Quinzenas FALTANDO na sequencia:")
            for i, f in faltando:
                print(f"   - {i:%d/%m/%Y} a {f:%d/%m/%Y}")
        else:
            print("\n[ok] Sequencia quinzenal completa, sem buracos.")

    if geral:
        if not os.path.exists(geral):
            print(f"\n[--geral] arquivo nao encontrado: {geral}")
        else:
            g = analisar_pdf(geral)
            alvo = g["comissao"] if g["comissao"] is not None else g["liquido"]
            dif = abs((alvo or 0) - tot_com)
            print("\n=== CONFERENCIA CONTRA O RELATORIO GERAL ===")
            print(f"  Geral ({g['periodo_ini']} a {g['periodo_fim']}): $ comissao {_fmt(alvo)} | N {g['n']}")
            print(f"  Soma dos quinzenais:            $ comissao {_fmt(tot_com)} | N {tot_n}")
            ok_val = dif <= TOLERANCIA
            ok_n = (g["n"] or -1) == tot_n
            if ok_val and ok_n:
                print(f"  >>> BATEU 100%  (dif R$ {_fmt(dif).strip()})")
            else:
                print(f"  >>> NAO BATEU: dif de valor R$ {_fmt(dif).strip()} | dif de linhas {(g['n'] or 0) - tot_n}")

    _comparar_erp()


def _comparar_erp():
    try:
        from dotenv import load_dotenv
        from supabase import create_client
    except ImportError:
        return
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key or "xxxx" in url:
        return
    try:
        sb = create_client(url, key)
        rows = sb.table("comissoes_pagas").select("periodo_inicio,periodo_fim,administradora").execute().data or []
    except Exception as e:
        print(f"\n[ERP] nao consegui ler comissoes_pagas: {e}")
        return
    yam = sorted({(r.get("periodo_inicio"), r.get("periodo_fim")) for r in rows
                  if str(r.get("administradora", "")).upper() == "YAMAHA"})
    print("\n=== JA IMPORTADO NO ERP (comissoes_pagas, YAMAHA) — nao precisa rebaixar ===")
    for ini, fim in (yam or [("(nada ainda)", "")]):
        print(f"  {ini} a {fim}" if fim else f"  {ini}")


if __name__ == "__main__":
    args = sys.argv[1:]
    pasta, geral, i = PASTA_PADRAO, None, 0
    while i < len(args):
        if args[i] == "--pasta" and i + 1 < len(args):
            pasta = args[i + 1]; i += 2
        elif args[i] == "--geral" and i + 1 < len(args):
            geral = args[i + 1]; i += 2
        else:
            print(__doc__); sys.exit(0)
    conferir_pasta(pasta, geral)
