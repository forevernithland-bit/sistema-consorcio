"""
coletar_assembleias.py — Resultado das assembleias de um grupo Yamaha.

Menu Contemplação → Resultado de Assembleia → filtro por grupo → detalhe.
A tela mostra, por assembleia, a tabela de CONTEMPLAÇÕES:
    Cota | Modalidade | Opção | Bem | Filial | Dt. Contempl. | Dt. Confirm. | % Lance
com os botões « Retorna uma Assembleia / Avança uma Assembleia » pra navegar.

O robô anota TUDO (yamaha_contemplacoes) e resume por assembleia
(yamaha_assembleias): nº de contemplados por modalidade (Sorteio, Lance Livre,
Lance Fixo, 2º Lance Fixo, Lance Limitado, Lance Fidelidade e QUALQUER outra
que apareça), maior/menor lance, média por modalidade, mês de competência.
A view yamaha_grupo_lance_resumo consolida o período.
Também atualiza grupos_yamaha.lance_medio com a média real (lance livre).

USO (PC do escritório):
    python coletar_assembleias.py --grupo 10011 --assembleias 3
    python coletar_assembleias.py --grupos 9564,9598,9045 --assembleias 3 --tipo-bem auto --salvar
    python coletar_assembleias.py --grupo 10011 --assembleias 6 --tipo-bem imovel --salvar

VÁRIOS grupos numa tacada (--grupos): abre o navegador e LOGA UMA VEZ SÓ; pra
cada grupo só troca o número no filtro e lê. Só reloga se a sessão travar/der
timeout. Grava o progresso em assembleias_progresso.json — se parar no meio,
rodar o MESMO comando de novo continua de onde parou (não refaz o que já fez
hoje). --refazer ignora o progresso.  Sem --salvar: só imprime.
Precisa das tabelas do migracoes/18_assembleias_yamaha.sql.
"""
import os
import re
import sys
import json
import time
import datetime

sys.path.insert(0, os.path.dirname(__file__))
from coletar_grupos import (_abrir, _conectar_sb, _clic, _num, _sel_por_texto,   # noqa
                            _opcoes, _esperar_opcoes, S as _S)

for _st in (sys.stdout, sys.stderr):
    try:
        _st.reconfigure(encoding="utf-8")
    except Exception:
        pass

PASTA = os.path.dirname(__file__)

F = {
    "grupo":    "#ctl00_Conteudo_edtCD_Grupo",
    "buscar":   "#ctl00_Conteudo_btnOK",
    "buscar2":  "#ctl00_Conteudo_btnBuscarGrupos",
    "retorna":  "#ctl00_Conteudo_btnRetornaAssembleia",
    "avanca":   "#ctl00_Conteudo_btnAvancaAssembleia",
    "grd_conf": "ctl00_Conteudo_grdContemplacoes_Confirmadas",
    "grd_canc": "ctl00_Conteudo_grdContemplacoes_Confirmadas_Canceladas",
    "grd_desc": "ctl00_Conteudo_grdContemplacoes_Desclassificadas",
}

# rótulo da modalidade -> coluna do contador em yamaha_assembleias
MOD_COL = {
    "SORTEIO": "n_sorteio",
    "LANCE LIVRE": "n_lance_livre",
    "LANCE FIXO": "n_lance_fixo",
    "2 LANCE FIXO": "n_2lance_fixo",
    "2º LANCE FIXO": "n_2lance_fixo",
    "LANCE LIMITADO": "n_lance_limitado",
    "LANCE FIDELIDADE": "n_lance_fidelidade",
}


def _pct(s):
    """% do lance. Essa tela usa ponto como DECIMAL ('67.0299' = 67,0299).
    Também aceita formato BR ('67,0299')."""
    t = re.sub(r"[^\d.,\-]", "", str(s or ""))
    if not t:
        return 0.0
    if "," in t:                       # BR: vírgula é o decimal
        t = t.replace(".", "").replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return 0.0
    return round(v, 4)


def _dt(s):
    s = (s or "").strip()
    return s if re.match(r"\d{2}/\d{2}/\d{4}", s) else None


def _iso(s):
    try:
        return datetime.datetime.strptime(s, "%d/%m/%Y").date().isoformat()
    except Exception:
        return None


def _mes(s):
    try:
        return datetime.datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m")
    except Exception:
        return None


HOME_URL = "https://newkey.cny.com.br/Intranet/frmMain.aspx"


def _ir_para_resultado(page, tentativas=4):
    """Contemplação (topo) → Contemplação (submenu) → 'Resultado de Assembleia'."""
    for i in range(tentativas):
        try:
            if page.locator(F["grupo"]).count() and \
               page.locator(F["grupo"]).first.is_visible():
                return True
            if i:
                page.goto(HOME_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
            _clic(page, "Contemplação")          # menu do topo
            page.wait_for_timeout(500)

            def _achou_resultado():
                try:
                    return (page.locator("#ctl00_Conteudo_ctl00_tvwMenut1").count() > 0
                            or page.get_by_text("Resultado de Assembleia", exact=False).count() > 0)
                except Exception:
                    return False

            # o submenu tem 'Pré-Contemplação' E 'Contemplação'. Testa cada
            # link/aba "Contemplação" até um deles abrir 'Resultado de Assembleia'.
            if not _achou_resultado():
                cands = page.get_by_text("Contemplação", exact=True)
                for k in range(min(cands.count(), 6)):
                    try:
                        cands.nth(k).click(timeout=6000)
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(600)
                    except Exception:
                        continue
                    if _achou_resultado():
                        break
                    _clic(page, "Contemplação")   # reabre o submenu p/ o próximo

            for tent in (lambda: page.locator("#ctl00_Conteudo_ctl00_tvwMenut1"),
                         lambda: page.get_by_text("Resultado de Assembleia", exact=True),
                         lambda: page.get_by_text("Resultado da Assembleia", exact=False)):
                try:
                    loc = tent().first
                    if loc.count():
                        loc.click(timeout=8000)
                        page.wait_for_load_state("networkidle")
                        break
                except Exception:
                    continue
            page.wait_for_selector(F["grupo"], state="visible", timeout=15000)
            return True
        except Exception as e:
            print(f"   [nav] tentativa {i+1}/{tentativas}: {str(e)[:70]}")
            page.wait_for_timeout(1500)
    raise RuntimeError("não cheguei em 'Resultado de Assembleia'")


def _texto_pagina(page):
    partes = []
    try:
        partes.append(page.evaluate("() => document.body.innerText"))
    except Exception:
        pass
    for fr in page.frames:
        if fr is page.main_frame:
            continue
        try:
            partes.append(fr.evaluate("() => document.body.innerText"))
        except Exception:
            pass
    return "\n".join(partes)


def _grade(page, grid_id):
    """Linhas (lista de listas de células) de uma grade por id — com fallback."""
    js = """(gid) => {
      const tb = document.getElementById(gid)
        || [...document.querySelectorAll('table')].find(t => (t.id||'').includes(gid));
      if (!tb) return [];
      return [...tb.querySelectorAll('tr')].map(tr =>
        [...tr.querySelectorAll('td,th')].map(td => (td.innerText||'').replace(/\\s+/g,' ').trim()));
    }"""
    try:
        rows = page.evaluate(js, grid_id)
    except Exception:
        rows = []
    return [r for r in rows if any(c for c in r)]


def _ler_assembleia(page, grupo, tipo_bem):
    """Lê o cabeçalho + as 3 grades (confirmadas ativas/canceladas/desclassificadas)."""
    txt = _texto_pagina(page)

    def _b(rx, d=None):
        m = re.search(rx, txt, re.I)
        return m.group(1).strip() if m else d

    cab = {
        "grupo": str(int(re.sub(r"\D", "", grupo) or grupo)),
        "tipo_bem": tipo_bem,
        "num_assembleia": _b(r"Assembleia:\s*0*(\d+)\s*-\s*\d{2}/\d{2}/\d{4}"),
        "data_assembleia": _b(r"Assembleia:\s*\d+\s*-\s*(\d{2}/\d{2}/\d{4})"),
        "numero_sorteado": _b(r"N[úu]mero sorteado:\s*([\d.]+)"),
        "assembleias_realizadas": _b(r"Assembleias realizadas:\s*0*(\d+)"),
        "assembleias_a_realizar": _b(r"Assembleias [àa] realizar:\s*0*(\d+)"),
        "prazo_grupo": _b(r"Prazo:\s*0*(\d+)"),
    }

    linhas = []
    for gid, sit in ((F["grd_conf"], "ativo"), (F["grd_canc"], "cancelado"),
                     (F["grd_desc"], "desclassificado")):
        rows = _grade(page, gid)
        if not rows:
            continue
        head = [h.lower() for h in rows[0]]
        for r in rows[1:]:
            d = dict(zip(head, r))
            mod = (d.get("modalidade") or "").strip()
            if not mod:
                continue
            linhas.append({
                "grupo": cab["grupo"], "tipo_bem": tipo_bem,
                "num_assembleia": int(cab["num_assembleia"]) if cab["num_assembleia"] else None,
                "data_assembleia": _iso(cab["data_assembleia"]),
                "mes_competencia": _mes(cab["data_assembleia"]),
                "modalidade": mod,
                "opcao": (d.get("opção") or d.get("opcao") or "").strip() or None,
                "cota": (d.get("cota") or "").strip() or None,
                "bem": (d.get("bem") or "").strip() or None,
                "filial": (d.get("filial") or "").strip() or None,
                "dt_contemplacao": _iso(_dt(d.get("dt. contemplação") or d.get("dt. contemplacao"))),
                "dt_confirmacao": _iso(_dt(d.get("dt. confirmação") or d.get("dt. confirmacao"))),
                "pct_lance": _pct(d.get("% lance")),
                "situacao": sit,
            })
    return cab, linhas


def _resumo_assembleia(cab, linhas):
    lance = [x for x in linhas if x["situacao"] == "ativo"
             and (x["modalidade"] or "").upper() != "SORTEIO"]
    livres = [x["pct_lance"] for x in lance
              if "LIVRE" in (x["modalidade"] or "").upper() and x["pct_lance"]]
    fixos = [x["pct_lance"] for x in lance
             if "FIXO" in (x["modalidade"] or "").upper() and x["pct_lance"]]
    todos = [x["pct_lance"] for x in lance if x["pct_lance"]]

    r = {
        "grupo": cab["grupo"], "tipo_bem": cab["tipo_bem"],
        "num_assembleia": int(cab["num_assembleia"]) if cab["num_assembleia"] else None,
        "data_assembleia": _iso(cab["data_assembleia"]),
        "mes_competencia": _mes(cab["data_assembleia"]),
        "numero_sorteado": cab["numero_sorteado"],
        "assembleias_realizadas": int(cab["assembleias_realizadas"] or 0) or None,
        "assembleias_a_realizar": int(cab["assembleias_a_realizar"] or 0) or None,
        "prazo_grupo": int(cab["prazo_grupo"] or 0) or None,
        "n_total": len([x for x in linhas if x["situacao"] == "ativo"]),
        "lance_min": min(todos) if todos else None,
        "lance_max": max(todos) if todos else None,
        "lance_medio": round(sum(todos) / len(todos), 4) if todos else None,
        "lance_livre_min": min(livres) if livres else None,
        "lance_livre_max": max(livres) if livres else None,
        "lance_livre_medio": round(sum(livres) / len(livres), 4) if livres else None,
        "lance_fixo_medio": round(sum(fixos) / len(fixos), 4) if fixos else None,
        "modalidades_vistas": sorted({x["modalidade"] for x in linhas if x["modalidade"]}),
    }
    for col in set(MOD_COL.values()):
        r[col] = 0
    for x in linhas:
        if x["situacao"] != "ativo":
            continue
        col = MOD_COL.get((x["modalidade"] or "").upper())
        if col:
            r[col] = r.get(col, 0) + 1
    return r


def _salvar(sb, resumos, contempls):
    for c in contempls:
        try:
            sb.table("yamaha_contemplacoes").upsert(
                c, on_conflict="grupo,num_assembleia,cota,modalidade,dt_contemplacao,pct_lance"
            ).execute()
        except Exception as e:
            print(f"  ! contemplacao {c['grupo']}/{c['num_assembleia']}: {str(e)[:100]}")
    for r in resumos:
        try:
            sb.table("yamaha_assembleias").upsert(
                r, on_conflict="grupo,num_assembleia").execute()
        except Exception as e:
            print(f"  ! assembleia {r['grupo']}/{r['num_assembleia']}: {str(e)[:100]}")

    # atualiza a média real no catálogo de grupos (lance livre do período)
    livres = [r["lance_livre_medio"] for r in resumos if r.get("lance_livre_medio")]
    if livres and resumos:
        media = round(sum(livres) / len(livres), 4)
        try:
            sb.table("grupos_yamaha").update({
                "lance_medio": media,
                "consultado_em": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }).eq("grupo", resumos[0]["grupo"]).execute()
            print(f"  → grupos_yamaha.lance_medio do grupo {resumos[0]['grupo']} = {media}")
        except Exception as e:
            print(f"  ! não atualizei grupos_yamaha: {str(e)[:100]}")


PROGRESSO = os.path.join(PASTA, "assembleias_progresso.json")


def _prog_ler():
    """{'data': 'AAAA-MM-DD', 'feitos': [...]} de HOJE, ou vazio."""
    try:
        d = json.load(open(PROGRESSO, encoding="utf-8"))
        if d.get("data") == datetime.date.today().isoformat():
            return d
    except Exception:
        pass
    return {"data": datetime.date.today().isoformat(), "feitos": []}


def _prog_gravar(d):
    try:
        json.dump(d, open(PROGRESSO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass


def _prog_limpar():
    try:
        os.remove(PROGRESSO)
    except Exception:
        pass


def _vale_a_pena(sb, grupo, forcar):
    """(ok, motivo). Regra do Uriel: não coletar assembleia se o grupo não tem
    vaga, ou se a assembleia atual já está no banco."""
    if forcar:
        return True, ""
    try:
        gr = sb.table("grupos_yamaha").select("*").eq("grupo", grupo).execute().data or []
        gr = gr[0] if gr else None
    except Exception:
        gr = None
    if gr is not None and (gr.get("vagas") or 0) <= 0:
        return False, "SEM VAGA no catálogo"
    realiz_estim = None
    if gr and gr.get("prazo_total") and gr.get("prazo_restante") is not None:
        realiz_estim = int(gr["prazo_total"]) - int(gr["prazo_restante"])
    try:
        ja = sb.table("yamaha_assembleias").select("num_assembleia") \
            .eq("grupo", grupo).order("num_assembleia", desc=True).limit(1).execute().data or []
        ja_max = ja[0]["num_assembleia"] if ja else None
    except Exception:
        ja_max = None
    if realiz_estim and ja_max and ja_max >= realiz_estim:
        return False, f"assembleia atual (nº {realiz_estim}) já está no banco (temos até {ja_max})"
    return True, ""


def _nav_grupo(page, grupo):
    """Já na tela 'Resultado de Assembleia': troca o filtro para outro grupo.
    NÃO reabre o navegador — só muda o número e busca de novo."""
    _ir_para_resultado(page)              # garante que o campo do grupo está visível
    campo = page.locator(F["grupo"]).first
    for g in (grupo, grupo.zfill(6), grupo.lstrip("0")):
        try:
            campo.fill("")
            campo.fill(g)
            break
        except Exception:
            continue
    for bt in (F["buscar"], F["buscar2"]):
        try:
            if page.locator(bt).count():
                page.locator(bt).first.click(timeout=10000, no_wait_after=True)
                break
        except Exception:
            pass
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(f"#{F['grd_conf']}, table", timeout=30000)


def _coletar_um(page, sb, grupo, n_ass, tipo_bem, forcar):
    """Lê até n_ass assembleias do grupo já filtrado. Devolve (resumos, contempls)."""
    try:
        js = {x["num_assembleia"] for x in (sb.table("yamaha_assembleias")
              .select("num_assembleia").eq("grupo", grupo).execute().data or [])}
    except Exception:
        js = set()

    resumos, contempls = [], []
    for i in range(n_ass):
        cab, linhas = _ler_assembleia(page, grupo, tipo_bem)
        if not cab["num_assembleia"]:
            print(f"  [{i+1}] não li o cabeçalho da assembleia — parando")
            break
        num = int(cab["num_assembleia"])
        if num in js and not forcar:
            print(f"  [{i+1}] Assembleia {num}: já está no banco — parando.")
            break
        r = _resumo_assembleia(cab, linhas)
        resumos.append(r); contempls += linhas
        mods = ", ".join(f"{m}:{r.get(MOD_COL.get(m.upper(), ''), 0)}"
                         for m in r["modalidades_vistas"]) or "—"
        print(f"  [{i+1}] Assembleia {r['num_assembleia']} ({r['data_assembleia']}): "
              f"{r['n_total']} contempl. | livre méd {r['lance_livre_medio']} "
              f"(min {r['lance_livre_min']} / max {r['lance_livre_max']}) | "
              f"fixo méd {r['lance_fixo_medio']} | {mods}")
        if i < n_ass - 1:
            try:
                page.locator(F["retorna"]).first.click(timeout=10000, no_wait_after=True)
                page.wait_for_timeout(2500); page.wait_for_load_state("networkidle")
            except Exception as e:
                print(f"  [!] não consegui « Retornar uma Assembleia: {str(e)[:70]}")
                break
    return resumos, contempls


def main():
    a = sys.argv[1:]
    if not a or "--help" in a:
        print(__doc__); return

    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a else d

    brutos = opt("--grupos") or opt("--grupo") or ""
    grupos = [str(int(x)) for x in re.findall(r"\d+", brutos)]
    if not grupos:
        print("informe --grupo NNNNN  ou  --grupos 9564,9598,9045"); return
    n_ass = int(opt("--assembleias", "3"))
    tipo_bem = (opt("--tipo-bem") or "").capitalize() or None
    salvar = "--salvar" in a
    forcar = "--forcar" in a
    refazer = "--refazer" in a
    headless = "--headless" in a

    sb = _conectar_sb()

    # ------- retomada: pula o que já foi feito hoje (a não ser --refazer) -------
    prog = {"data": datetime.date.today().isoformat(), "feitos": []} if refazer else _prog_ler()
    feitos = set(prog["feitos"])
    fila = [g for g in grupos if g not in feitos]
    if feitos:
        print(f">>> retomada: {len(feitos)} grupo(s) já feito(s) hoje "
              f"({', '.join(sorted(feitos))}) — pulando. Faltam {len(fila)}.")
    if not fila:
        print(">>> nada a fazer — todos os grupos já foram coletados hoje. "
              "(use --refazer pra rever)")
        _prog_limpar()
        return

    pw, browser, ctx, page = _abrir(sb, visivel=not headless)

    def _reabrir():
        nonlocal pw, browser, ctx, page
        print("   [sessão] reabrindo o navegador (login)...")
        try:
            browser.close(); pw.stop()
        except Exception:
            pass
        pw, browser, ctx, page = _abrir(sb, visivel=not headless)
        _ir_para_resultado(page)

    total_resumos = total_contempls = 0
    try:
        _ir_para_resultado(page)               # login + navegação UMA vez
        for n, grupo in enumerate(fila, 1):
            print(f"\n[{n}/{len(fila)}] grupo {grupo}")
            ok, motivo = _vale_a_pena(sb, grupo, forcar)
            if not ok:
                print(f"  pulando: {motivo}. (use --forcar)")
                feitos.add(grupo); prog["feitos"] = sorted(feitos); _prog_gravar(prog)
                continue

            resumos = contempls = None
            for tent in (1, 2):
                try:
                    _nav_grupo(page, grupo)
                    resumos, contempls = _coletar_um(page, sb, grupo, n_ass, tipo_bem, forcar)
                    break
                except Exception as e:
                    print(f"  ~ tentativa {tent}: {str(e)[:110]}")
                    try:
                        _ir_para_resultado(page)          # recupera sem relogar
                    except Exception:
                        try:
                            _reabrir()                   # só reloga se travou de vez
                        except Exception as e2:
                            print(f"  x não reabri a sessão: {str(e2)[:90]}")
                            break
            if resumos is None:
                print(f"  x grupo {grupo} FALHOU — fica pendente. Rode o mesmo comando "
                      f"de novo que ele continua daqui.")
                _prog_gravar(prog)                        # feitos até agora ficam salvos
                continue

            if resumos:
                todos_livres = [x["pct_lance"] for x in contempls
                                if x["situacao"] == "ativo"
                                and "LIVRE" in (x["modalidade"] or "").upper() and x["pct_lance"]]
                print(f"  === {len(resumos)} assembleia(s) ===")
                if todos_livres:
                    print(f"  Lance LIVRE no período: méd {sum(todos_livres)/len(todos_livres):.4f} "
                          f"| min {min(todos_livres):.4f} | max {max(todos_livres):.4f} "
                          f"| {len(todos_livres)} contemplações")

            if salvar:
                _salvar(sb, resumos, contempls)
                print(f"  [OK] {len(resumos)} assembleia(s) + {len(contempls)} "
                      f"contemplação(ões) gravadas.")
            else:
                out = os.path.join(PASTA, f"assembleias_{grupo}.json")
                open(out, "w", encoding="utf-8").write(
                    json.dumps({"resumos": resumos, "contemplacoes": contempls},
                               ensure_ascii=False, indent=1, default=str))
                print(f"  (teste — nada gravado. JSON: {out})")

            total_resumos += len(resumos); total_contempls += len(contempls)
            feitos.add(grupo); prog["feitos"] = sorted(feitos); _prog_gravar(prog)

        pendentes = [g for g in grupos if g not in feitos]
        print(f"\n{'='*70}")
        if pendentes:
            print(f"[!] {len(pendentes)} grupo(s) pendente(s): {', '.join(pendentes)}. "
                  f"Rode o mesmo comando de novo para continuar.")
        else:
            print(f"[OK] Todos os {len(grupos)} grupo(s) coletados "
                  f"({total_resumos} assembleias, {total_contempls} contemplações).")
            _prog_limpar()
    finally:
        try:
            browser.close(); pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
