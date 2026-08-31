# -*- coding: utf-8 -*-
r"""
coletar_tabelas_yamaha.py — lê as tabelas de preço em PDF de
    G:\Meu Drive\CONSORBENS\Tabelas\YAMAHA
e extrai, por grupo:  lance embutido permitido, lance(s) fixo(s),
produto, prazo, participantes, próxima assembleia e faixas de crédito.

Grava/atualiza em `grupos_yamaha` (mesmo modelo da base do simulador):
  - preenche `embutido_max_pct` e `lance_fixo_pct` (migração 21)
  - se o grupo da tabela ainda não existe em `grupos_yamaha`, INSERE com os
    campos que a tabela fornece (fonte = 'tabela_pdf'); o robô de vagas
    (`coletar_grupos.py`) completa vagas/taxa/parcela depois.

Só reprocessa se houver arquivo mais novo que o último processado
(marca em `worker/tabelas_yamaha_estado.json`). Rode:

    python coletar_tabelas_yamaha.py --dry        # só imprime o que achou
    python coletar_tabelas_yamaha.py --salvar     # grava no Supabase
    python coletar_tabelas_yamaha.py --salvar --forcar   # ignora o "sem novidade"

Regras GERAIS (usadas quando NÃO há tabela do grupo na pasta) — as mesmas
que estão no botão "Lembretes" do simulador:

  Embutido:  Moto 15% · Auto 15% · Imóvel 25% · Caminhão 30%
  Lance fixo: Moto 35% ou 25% (com 15% de embutido)
              Auto 35% (com 15% de embutido)
              Imóvel 30% (com 25% de embutido)
              Caminhão 25%
"""
import os
import re
import json
import argparse
import subprocess
import datetime

PASTA_TABELAS = r"G:\Meu Drive\CONSORBENS\Tabelas\YAMAHA"
ESTADO = os.path.join(os.path.dirname(__file__), "tabelas_yamaha_estado.json")

# subpastas que são histórico / não vigentes
SKIP_DIRS = ("antigas", "] enc_", os.sep + "2026" + os.sep, "/2026/")

REGRAS_GERAIS = {
    "Moto":     {"embutido_max": 15, "lance_fixo": [25, 35]},
    "Auto":     {"embutido_max": 15, "lance_fixo": [35]},
    "Imóvel":   {"embutido_max": 25, "lance_fixo": [30]},
    "Caminhão": {"embutido_max": 30, "lance_fixo": [25]},
    "Náutica":  {"embutido_max": 15, "lance_fixo": [25]},
}


# ----------------------------------------------------------------------------
_LEITOR_OK = None   # None = ainda n\u00e3o sei; True/False depois do 1\u00ba PDF


def _via_pypdf(caminho):
    try:
        from pypdf import PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader  # nome antigo
        except Exception:
            return None
    try:
        r = PdfReader(caminho)
        return "\n".join((p.extract_text() or "") for p in r.pages)
    except Exception:
        return ""


def _via_pdfplumber(caminho):
    try:
        import pdfplumber
    except Exception:
        return None
    try:
        with pdfplumber.open(caminho) as pdf:
            return "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    except Exception:
        return ""


def _via_pdftotext(caminho):
    for enc in ("UTF-8", "Latin1"):
        try:
            out = subprocess.run(
                ["pdftotext", "-layout", "-enc", enc, caminho, "-"],
                capture_output=True, timeout=45,
            )
            s = out.stdout.decode("utf-8", "replace")
            if s.count("\ufffd") < 20:
                return s
        except FileNotFoundError:
            return None   # bin\u00e1rio n\u00e3o instalado
        except Exception:
            pass
    return ""


def _pdftotext(caminho):
    """Tenta pypdf \u2192 pdfplumber \u2192 bin\u00e1rio pdftotext (o que estiver dispon\u00edvel).
    N\u00e3o depende de programa externo no PATH (o pypdf \u00e9 Python puro)."""
    global _LEITOR_OK
    for fn in (_via_pypdf, _via_pdfplumber, _via_pdftotext):
        s = fn(caminho)
        if s is None:
            continue          # esse leitor n\u00e3o est\u00e1 instalado
        if s.strip():
            _LEITOR_OK = True
            return s
        _LEITOR_OK = True     # o leitor funciona, o PDF \u00e9 que veio vazio
        return s
    if _LEITOR_OK is None:
        _LEITOR_OK = False
    return ""


def _produto(nome, texto):
    n = (nome + " " + texto[:2000]).lower()
    if "imóve" in n or "imove" in n or "imóvei" in n:
        return "Imóvel"
    if "caminh" in n:
        return "Caminhão"
    if "motocicl" in n or re.search(r"\bmoto\b", n):
        return "Moto"
    if "náutic" in n or "nautic" in n:
        return "Náutica"
    if "autom" in n or "prime auto" in n or "auto ipca" in n:
        return "Auto"
    return None


def _grupos(nome, texto):
    g = set()
    base = os.path.splitext(nome)[0]
    # do NOME do arquivo — mais confiável
    for m in re.finditer(r"(?:grupo\s*n?[ºo°]?\s*|\bg\s*)((?:\d{1,2}\.\d{3})|\d{4,5})", base, re.I):
        g.add(m.group(1))
    for m in re.finditer(r"\b(\d{2}\.\d{3})\b", base):
        g.add(m.group(1))
    # nome do arquivo é só o número do grupo (ex.: "9036.pdf", "20.003.pdf")
    m = re.fullmatch(r"\s*((?:\d{1,2}\.\d{3})|\d{4,5})\s*", base)
    if m:
        g.add(m.group(1))
    # do CONTEÚDO
    for m in re.finditer(r"GRUPO(?:\s*N?[ºo°:]*)?\s+((?:\d{1,2}\.\d{3})|\d{4,5})", texto, re.I):
        g.add(m.group(1))
    return sorted({x.replace(".", "") for x in g if x.replace(".", "").isdigit()})


def _embutido(texto):
    pats = [
        r"LANCE\s+EMBUTIDO\s+DE\s+(?:AT[ÉE]\s+)?(\d{1,2})\s*%",
        r"utilizar\s+lance\s+embutido\s+de\s+(\d{1,2})\s*%",
        r"utilizar\s+(\d{1,2})\s*%\s+do\s+cr[ée]dito\s+como\s+parte\s+do\s+pagamento",
        r"embutido\s+de\s+at[ée]\s+(\d{1,2})\s*%",
        r"lance\s+embutido[^%\n]{0,20}?(\d{1,2})\s*%",
    ]
    for p in pats:
        m = re.search(p, texto, re.I)
        if m:
            return int(m.group(1))
    return None


def _lance_fixo(texto):
    out = []
    for m in re.finditer(r"LANCE\s+FIXO\s+(?:DE\s+|\()\s*([0-9%\s,eE/]+)", texto, re.I):
        for n in re.findall(r"(\d{1,2})\s*%", m.group(1)[:45]):
            out.append(int(n))
    for m in re.finditer(r"lance\s+fixo\b[^\n]{0,55}", texto, re.I):
        for n in re.findall(r"(\d{1,2})\s*%", m.group(0)):
            out.append(int(n))
    # lance fixo na Yamaha é sempre um "degrau" redondo (20/25/30/35/50);
    # descarta ruído (ex.: "70" vindo de "Parcela Reduzida 70%").
    out = sorted({v for v in out if v in (20, 25, 30, 35, 40, 45, 50)})
    return out or None


def _prazo(texto):
    m = re.search(r"Prazo\s+de\s+(\d{2,3})\s+meses", texto, re.I)
    if m:
        return int(m.group(1))
    ms = [int(x) for x in re.findall(r"\b(\d{2,3})\s+MESES\b", texto)]
    return max(ms) if ms else None


def _participantes(texto):
    for m in re.finditer(r"(?:com\s+|participantes[:\s]+|n[ºo°]\s*de\s*participantes[:\s]+)(\d{2,4})\s*(?:participantes)?", texto, re.I):
        v = int(m.group(1))
        if 50 <= v <= 5000 and not (2020 <= v <= 2035):
            return v
    m = re.search(r"(\d{2,4})\s+participantes", texto, re.I)
    if m:
        v = int(m.group(1))
        if 50 <= v <= 5000 and not (2020 <= v <= 2035):
            return v
    return None


def _assembleia(texto):
    m = re.search(r"Assembleia[:\s]+(\d{2}/\d{2}/\d{4})", texto, re.I)
    return m.group(1) if m else None


def _creditos(texto):
    v = set()
    for m in re.finditer(r"R\$\s?(\d{2,3}(?:\.\d{3})+),00", texto):
        n = int(m.group(1).replace(".", ""))
        if 8000 <= n <= 2_000_000:
            v.add(n)
    return sorted(v)


# ----------------------------------------------------------------------------
def _arquivos():
    achados = []
    for base, _dirs, files in os.walk(PASTA_TABELAS):
        low = (base.lower() + os.sep)
        if any(s in low for s in SKIP_DIRS):
            continue
        for fn in files:
            if fn.lower().endswith(".pdf"):
                achados.append(os.path.join(base, fn))
    return achados


def coletar():
    arqs = _arquivos()
    por_grupo = {}
    for p in arqs:
        t = _pdftotext(p)
        if not t.strip():
            continue
        nome = os.path.basename(p)
        gs = _grupos(nome, t)
        if not gs:
            continue
        rec = dict(
            produto=_produto(nome, t),
            embutido_max=_embutido(t),
            lance_fixo=_lance_fixo(t),
            prazo=_prazo(t),
            participantes=_participantes(t),
            prox_assembleia=_assembleia(t),
            creditos=_creditos(t),
            arquivo=nome,
            mtime=os.path.getmtime(p),
        )
        for g in gs:
            cur = por_grupo.get(g)
            if cur is None or rec["mtime"] > cur["mtime"]:
                if cur:  # herda o que o mais novo não achou
                    for k in ("produto", "embutido_max", "lance_fixo", "prazo",
                              "participantes", "prox_assembleia", "creditos"):
                        if not rec[k] and cur.get(k):
                            rec[k] = cur[k]
                por_grupo[g] = dict(rec, grupo=g)

    # completa embutido/lance_fixo pela regra geral do produto quando faltou
    for g, r in por_grupo.items():
        reg = REGRAS_GERAIS.get(r.get("produto") or "", {})
        if r.get("embutido_max") is None and reg.get("embutido_max") is not None:
            r["embutido_max"] = reg["embutido_max"]
            r["embutido_fonte"] = "regra_geral"
        else:
            r["embutido_fonte"] = "tabela"
        if not r.get("lance_fixo") and reg.get("lance_fixo"):
            r["lance_fixo"] = reg["lance_fixo"]
            r["lance_fixo_fonte"] = "regra_geral"
        else:
            r["lance_fixo_fonte"] = "tabela"

    return sorted(por_grupo.values(), key=lambda r: r["grupo"]), arqs


# ----------------------------------------------------------------------------
def _mtime_max(arqs):
    return max((os.path.getmtime(a) for a in arqs), default=0)


def _ler_estado():
    try:
        with open(ESTADO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _grava_estado(mtime_max, n):
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump({"ultimo_mtime": mtime_max, "grupos": n,
                   "rodou_em": datetime.datetime.now().isoformat()}, f, indent=1)


def _supabase():
    """Mesma conexão dos outros scripts do worker (worker/.env)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    except Exception:
        pass
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key or "xxxx" in url:
        raise RuntimeError("Configure SUPABASE_URL/KEY no worker/.env")
    return create_client(url, key)


def _faixas_do_pdf(r):
    """creditos do PDF no MESMO formato de planos_yamaha.creditos
    (o simulador lê c.credito / c.prazo / c.reducao_pct)."""
    prazo = r.get("prazo")
    reduz = 30 if (r.get("produto") == "Imóvel" and "reduzida" in (r.get("arquivo") or "").lower()) else None
    out = []
    for v in (r.get("creditos") or []):
        out.append({
            "credito": v,
            "prazo": prazo,
            "texto": f"{r.get('produto') or 'CRÉDITO'} R$ {v:,.0f}".replace(",", "."),
            "reducao_pct": reduz,
            "parcela_reduzida": bool(reduz),
            "bem_cod": None,
            "fonte": "tabela_pdf",
        })
    return out


def salvar(supabase, grupos):
    ins, upd, plan = 0, 0, 0
    existentes = {}   # grupo -> {tipo_bem: {plano_codigo,...}}
    try:
        cols = "grupo,tipo_bem,plano_codigo,credito"
        for row in (supabase.table("grupos_yamaha").select(cols).execute().data or []):
            existentes.setdefault(str(row["grupo"]), {})[row.get("tipo_bem")] = row
    except Exception as e:
        print("!! não consegui listar grupos_yamaha:", e)

    planos_cod = set()
    try:
        for row in (supabase.table("planos_yamaha").select("codigo,tipo_bem").execute().data or []):
            planos_cod.add((str(row["codigo"]), row.get("tipo_bem")))
    except Exception as e:
        print("!! não consegui listar planos_yamaha:", e)

    agora = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for r in grupos:
        tipo = r.get("produto") or "Auto"
        faixas = _faixas_do_pdf(r)
        cod_tab = f"TAB-{r['grupo']}"   # plano sintético da tabela do grupo

        regras = {
            "embutido_max_pct": r["embutido_max"],
            "lance_fixo_pct": r["lance_fixo"],
            "lance_regras_fonte": {
                "embutido": r["embutido_fonte"], "lance_fixo": r["lance_fixo_fonte"],
                "arquivo": r["arquivo"],
            },
            "lance_regras_em": agora,
        }

        ja = existentes.get(r["grupo"], {})
        row_atual = ja.get(tipo) or (next(iter(ja.values())) if ja else None)

        # ---- plano sintético com as faixas de crédito da tabela (modelo exato) ----
        if faixas:
            plano_row = {
                "codigo": cod_tab, "tipo_bem": tipo,
                "nome": f"Tabela do grupo {r['grupo']} ({r['arquivo']})",
                "creditos": faixas, "consultado_em": agora,
            }
            supabase.table("planos_yamaha").upsert(plano_row, on_conflict="codigo,tipo_bem").execute()
            plan += 1

        if row_atual is not None:
            # grupo já existe: atualiza regras de lance; só amarra o plano
            # sintético se o grupo ainda não tem plano de verdade do Newcon.
            payload = dict(regras)
            pc = (row_atual.get("plano_codigo") or "")
            if faixas and (not pc or pc.startswith("TAB-")):
                payload["plano_codigo"] = cod_tab
            if faixas and row_atual.get("credito") in (None, 0):
                payload["credito"] = faixas[len(faixas) // 2]["credito"]
            tb = tipo if tipo in ja else next(iter(ja))
            supabase.table("grupos_yamaha").update(payload).eq("grupo", r["grupo"]).eq("tipo_bem", tb).execute()
            upd += 1
        else:
            novo = dict(regras)
            novo.update({
                "grupo": r["grupo"], "tipo_bem": tipo,
                "plano_codigo": cod_tab if faixas else None,
                "bem": (tipo or "").upper(),
                "credito": (faixas[len(faixas) // 2]["credito"] if faixas else None),
                "prox_assembleia": r.get("prox_assembleia"),
                "prazo_total": r.get("prazo"),
                "consultado_em": agora,
                "fonte": "tabela_pdf",
            })
            supabase.table("grupos_yamaha").insert(novo).execute()
            ins += 1
            print(f"  + grupo {r['grupo']} ({tipo}) INSERIDO — {len(faixas)} faixas de crédito, "
                  f"embutido {r['embutido_max']}%, lance fixo {r['lance_fixo']}")

    print(f"  (planos sintéticos TAB-* gravados/atualizados: {plan})")
    return ins, upd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="só imprime o que achou")
    ap.add_argument("--salvar", action="store_true", help="grava no Supabase")
    ap.add_argument("--forcar", action="store_true", help="ignora o 'sem arquivo novo'")
    ap.add_argument("--json", action="store_true", help="saída JSON crua")
    args = ap.parse_args()

    arqs = _arquivos()
    mtmax = _mtime_max(arqs)
    estado = _ler_estado()
    # só considera "em dia" se a última rodada REALMENTE achou grupos
    em_dia = (estado.get("ultimo_mtime", 0) >= mtmax) and (estado.get("grupos", 0) > 0)
    if not args.forcar and not args.dry and em_dia:
        print("Sem arquivo novo na pasta desde a última coleta — nada a atualizar.")
        print(f"(última: {estado.get('rodou_em','?')}, {estado.get('grupos','?')} grupos)")
        return

    grupos, arqs = coletar()

    if _LEITOR_OK is False:
        print("!! Não consegui LER nenhum PDF — falta uma biblioteca de PDF.")
        print("   Instale uma destas (Python puro, não precisa de admin):")
        print("       pip install pypdf")
        print("       pip install pdfplumber")
        print("   (ou tenha o 'pdftotext'/poppler no PATH). NADA foi gravado.")
        return
    if not grupos:
        print(f"!! {len(arqs)} PDFs varridos, mas 0 grupo reconhecido — algo está errado.")
        print("   NADA foi gravado e o estado NÃO foi tocado (a próxima rodada tenta de novo).")
        return

    if args.json:
        print(json.dumps({"arquivos": len(arqs), "grupos": grupos}, ensure_ascii=False, indent=1))
    else:
        print(f"{len(arqs)} PDFs varridos · {len(grupos)} grupos com tabela\n")
        print(f"{'GRUPO':<8}{'PRODUTO':<10}{'EMB%':<7}{'L.FIXO':<12}{'PRAZO':<7}{'PART':<7}{'ASSEMB':<12}{'FONTE'}")
        for r in grupos:
            lf = ",".join(map(str, r["lance_fixo"])) if r["lance_fixo"] else "-"
            fonte = f"{r['embutido_fonte']}/{r['lance_fixo_fonte']}"
            print(f"{r['grupo']:<8}{str(r['produto'] or '-'):<10}"
                  f"{str(r['embutido_max']) if r['embutido_max'] is not None else '-':<7}"
                  f"{lf:<12}{str(r['prazo'] or '-'):<7}{str(r['participantes'] or '-'):<7}"
                  f"{str(r['prox_assembleia'] or '-'):<12}{fonte}")

    if args.salvar:
        sb = _supabase()
        ins, upd = salvar(sb, grupos)
        _grava_estado(mtmax, len(grupos))
        print(f"\nSupabase: {ins} inseridos, {upd} atualizados. Estado salvo em {os.path.basename(ESTADO)}.")
    elif not args.dry and not args.json:
        print("\n(nada gravado — rode com --salvar para escrever no Supabase)")


if __name__ == "__main__":
    main()
