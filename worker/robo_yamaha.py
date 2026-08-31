# -*- coding: utf-8 -*-
r"""
robo_yamaha.py — ROBÔ ÚNICO da Yamaha para alimentar o simulador.

Faz as DUAS coisas numa sessão só (abre o navegador e LOGA UMA VEZ):

  FASE 1 — GRUPOS        (menu Venda -> Venda de Proposta)
     varre os planos de cada produto (Auto, Moto, Imóvel, Caminhão),
     prioriza os MAIS RECENTES (metade da lista pra frente — os antigos
     quase nunca têm vaga) e entra na grade de cada faixa de crédito,
     trazendo: nº do grupo, vagas, créditos, taxa, parcela, prazo,
     próxima assembleia, se é parcela reduzida e o lance médio da grade.

  FASE 2 — ASSEMBLEIAS   (menu Contemplação -> Resultado de Assembleia)
     para cada grupo COM VAGA achado na fase 1 (que ainda não tem a
     assembleia do mês no banco), lê as últimas N assembleias e calcula
     a MÉDIA DE LANCE LIVRE real.

Inteligente:
  * uma sessão só — não fica logando/deslogando (recupera a navegação sem
    relogar; só reabre o navegador se a sessão travar de vez);
  * grava o progresso em `robo_yamaha_progresso.json` a cada plano/grupo —
    se parar no meio (timeout, queda), rodar o MESMO comando de novo
    continua exatamente de onde parou;
  * tudo o que coleta é gravado no Supabase à medida que anda (com --salvar).

USO (PC do escritório):
    python robo_yamaha.py --teste                 # curto, NÃO grava (confere)
    python robo_yamaha.py --teste --salvar        # curto e grava
    python robo_yamaha.py --completo --salvar      # tudo, grava
  Opções:
    --produtos auto,moto        limita os produtos (padrão: os 4)
    --incluir-antigos           varre também os planos antigos do início
    --prazo longo|todos         longo = só o prazo máximo (rápido; padrão)
    --assembleias 3             nº de assembleias por grupo na fase 2 (padrão 3)
    --so-grupos | --so-assembleias   roda só uma das fases
    --headless                  navegador invisível
    --refazer                   ignora o progresso e recomeça do zero

Precisa das migrações 17, 18, 19 (e 20) rodadas no Supabase, e do
worker/.env com SUPABASE_URL/KEY e SIMULACAO_CPF.
"""
import os
import re
import sys
import json
import datetime

sys.path.insert(0, os.path.dirname(__file__))

from coletar_grupos import (                      # noqa: E402
    _abrir, _conectar_sb, _ir_para_form, _preambulo, _opcoes, S,
    _plano_valido, _cod, _coletar_plano,
    _salvar as _salvar_grupos, _registrar_busca, PRODUTOS,
)
import coletar_grupos as CG                        # noqa: E402
from coletar_assembleias import (                  # noqa: E402
    _ir_para_resultado, _nav_grupo, _coletar_um,
    _salvar as _salvar_assemb, _vale_a_pena,
)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

PASTA = os.path.dirname(__file__)
PROG = os.path.join(PASTA, "robo_yamaha_progresso.json")
ORDEM_PRODUTOS = ["auto", "moto", "imovel", "caminhao"]


# ------------------------------------------------------------------- progresso
def _prog_ler():
    hoje = datetime.date.today().isoformat()
    try:
        d = json.load(open(PROG, encoding="utf-8"))
        if d.get("data") == hoje:
            return d
    except Exception:
        pass
    return {"data": hoje, "fase": "grupos", "planos_feitos": {},
            "grupos_com_vaga": {}, "assembleias_feitas": []}


def _prog_gravar(d):
    d["atualizado_em"] = datetime.datetime.now().isoformat(timespec="seconds")
    json.dump(d, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _prog_limpar():
    try:
        os.remove(PROG)
    except Exception:
        pass


# ------------------------------------------------------------------- fase 1
def _planos_do_produto(page, prod_in, incluir_antigos, limite=None):
    prod_nome, prod_pal = PRODUTOS[prod_in]
    CG._PROD_PAL = prod_pal
    _ir_para_form(page)
    _preambulo(page, prod_pal)
    todos = _opcoes(page, S["tp_venda"])
    validos = [(v, t) for v, t in todos if _plano_valido(t)]
    if not validos:
        return prod_nome, prod_pal, []
    if incluir_antigos:
        escolhidos = validos
    else:
        cods = sorted(_cod(t) for _, t in validos)
        meio = cods[len(cods) // 2] if cods else ""
        recentes = [(v, t) for v, t in validos if _cod(t) >= meio]
        escolhidos = recentes or validos
    if limite:
        escolhidos = escolhidos[-limite:]          # os N mais recentes
    return prod_nome, prod_pal, escolhidos


def fase_grupos(page, sb, prog, produtos, incluir_antigos, prazo_pref,
                salvar, limite_planos):
    for prod_in in produtos:
        prod_nome, prod_pal, planos = _planos_do_produto(
            page, prod_in, incluir_antigos, limite_planos)
        feitos = set(prog["planos_feitos"].get(prod_in, []))
        fila = [(v, t) for v, t in planos if _cod(t) not in feitos]
        print(f"\n{'#'*72}\n# {prod_nome}: {len(planos)} plano(s) recente(s), "
              f"{len(feitos)} já feito(s) hoje, {len(fila)} na fila\n{'#'*72}")
        if not fila:
            continue

        CG._PROD_PAL = prod_pal
        for i, (pv, pt) in enumerate(fila, 1):
            cod = _cod(pt)
            print(f"\n[{prod_nome} {i}/{len(fila)}] plano {cod}", flush=True)
            ok = False
            for tent in (1, 2):
                try:
                    meta, grupos = _coletar_plano(
                        page, pv, pt, alvo=None, com_grupos=True,
                        prazo_pref=prazo_pref, max_faixas=1)
                    if salvar:
                        try:
                            _salvar_grupos(sb, prod_nome, [meta], grupos)
                            _registrar_busca(sb, prod_nome, meta["plano_cod"], None, grupos)
                        except Exception as e:
                            print(f"  ! não gravei plano {cod}: {str(e)[:110]}")
                    for g in grupos:
                        if (g.get("vagas") or 0) > 0:
                            prog["grupos_com_vaga"][str(g["grupo"])] = prod_nome
                    ok = True
                    break
                except Exception as e:
                    print(f"  ~ plano {cod} tentativa {tent}: {str(e)[:120]}")
                    try:
                        _ir_para_form(page); _preambulo(page, prod_pal)
                    except Exception:
                        pass
            prog["planos_feitos"].setdefault(prod_in, [])
            if ok:
                prog["planos_feitos"][prod_in].append(cod)
            _prog_gravar(prog)

            try:
                _ir_para_form(page); _preambulo(page, prod_pal)
            except Exception as e:
                print(f"\n  !! não consegui voltar ao formulário ({str(e)[:70]}).")
                print(f"  !! PAROU no plano {cod} de {prod_nome}. O que já foi coletado "
                      f"está salvo. Rode o MESMO comando de novo para continuar.")
                return False
    prog["fase"] = "assembleias"
    _prog_gravar(prog)
    return True


# ------------------------------------------------------------------- fase 2
def fase_assembleias(page, sb, prog, n_ass, salvar):
    pend = [g for g in sorted(prog["grupos_com_vaga"], key=lambda x: int(x))
            if g not in prog["assembleias_feitas"]]
    print(f"\n{'#'*72}\n# ASSEMBLEIAS: {len(prog['grupos_com_vaga'])} grupo(s) com vaga, "
          f"{len(prog['assembleias_feitas'])} já feito(s), {len(pend)} na fila\n{'#'*72}")
    if not pend:
        return True
    try:
        _ir_para_resultado(page)                    # navega (sem relogar)
    except Exception as e:
        print(f"  !! não abri Resultado de Assembleia ({str(e)[:80]}).")
        return False

    for n, grupo in enumerate(pend, 1):
        tb = prog["grupos_com_vaga"].get(grupo)
        print(f"\n[assembleia {n}/{len(pend)}] grupo {grupo} ({tb})", flush=True)
        ok_g, motivo = _vale_a_pena(sb, grupo, False)
        if not ok_g:
            print(f"  pula: {motivo}")
            prog["assembleias_feitas"].append(grupo); _prog_gravar(prog)
            continue
        resumos = contempls = None
        for tent in (1, 2):
            try:
                _nav_grupo(page, grupo)
                resumos, contempls = _coletar_um(page, sb, grupo, n_ass, tb, False)
                break
            except Exception as e:
                print(f"  ~ tentativa {tent}: {str(e)[:120]}")
                try:
                    _ir_para_resultado(page)
                except Exception:
                    print("  x sessão travada na fase 2 — progresso salvo, "
                          "rode o mesmo comando de novo.")
                    _prog_gravar(prog)
                    return False
        if resumos is None:
            print(f"  x grupo {grupo} FALHOU — fica pendente.")
            _prog_gravar(prog)
            continue
        if salvar and resumos:
            _salvar_assemb(sb, resumos, contempls)
            print(f"  [OK] {len(resumos)} assembleia(s) + {len(contempls)} contemplação(ões).")
        elif resumos:
            livres = [x["pct_lance"] for x in contempls
                      if x.get("situacao") == "ativo"
                      and "LIVRE" in (x.get("modalidade") or "").upper() and x.get("pct_lance")]
            if livres:
                print(f"  lance livre: méd {sum(livres)/len(livres):.2f}% "
                      f"(min {min(livres):.2f} / max {max(livres):.2f}) — {len(livres)} contempl.")
        prog["assembleias_feitas"].append(grupo); _prog_gravar(prog)
    prog["fase"] = "fim"
    _prog_gravar(prog)
    return True


# ------------------------------------------------------------------- main
def main():
    a = sys.argv[1:]
    if not a or "--help" in a or "-h" in a:
        print(__doc__); return

    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a else d

    teste = "--teste" in a
    completo = "--completo" in a
    if not (teste or completo):
        print("passe --teste (curto, confere) ou --completo (tudo).")
        return
    salvar = "--salvar" in a
    headless = "--headless" in a
    incluir_antigos = "--incluir-antigos" in a
    prazo_pref = (opt("--prazo") or "longo").lower()
    if prazo_pref in ("todos", "all"):
        prazo_pref = None
    n_ass = int(opt("--assembleias", "2" if teste else "3"))
    so_grupos = "--so-grupos" in a
    so_assemb = "--so-assembleias" in a
    prods = [p.strip().lower() for p in (opt("--produtos") or ",".join(ORDEM_PRODUTOS)).split(",")]
    prods = [p for p in ORDEM_PRODUTOS if p in prods] or ORDEM_PRODUTOS
    limite_planos = 2 if teste else None
    if teste:
        prods = prods[:2] if not opt("--produtos") else prods   # teste: 2 produtos

    if "--refazer" in a:
        _prog_limpar()
    prog = _prog_ler()

    modo = "TESTE CURTO" if teste else "COMPLETO"
    print(f">>> ROBÔ YAMAHA — {modo}{' (grava)' if salvar else ' (NÃO grava)'}")
    print(f"    produtos: {', '.join(prods)} | prazo: {prazo_pref or 'todos'} | "
          f"assembleias/grupo: {n_ass}")
    if prog.get("planos_feitos") or prog.get("assembleias_feitas"):
        print(f"    retomando progresso de hoje "
              f"({sum(len(v) for v in prog['planos_feitos'].values())} planos, "
              f"{len(prog['assembleias_feitas'])} assembleias já feitos)")

    sb = _conectar_sb()

    # --so-assembleias sem progresso: pega os grupos com vaga direto do banco
    if so_assemb and not prog["grupos_com_vaga"]:
        try:
            for r in (sb.table("grupos_yamaha").select("grupo,tipo_bem,vagas")
                      .gt("vagas", 0).execute().data or []):
                prog["grupos_com_vaga"][str(r["grupo"])] = r.get("tipo_bem") or "Auto"
            print(f"    (--so-assembleias: {len(prog['grupos_com_vaga'])} grupo(s) "
                  f"com vaga vindos do banco)")
        except Exception as e:
            print(f"    !! não li grupos_yamaha: {e}")

    fase = prog.get("fase", "grupos")
    pw, browser, ctx, page = _abrir(sb, visivel=not headless)
    fim_ok = True
    try:
        if not so_assemb and fase == "grupos":
            fim_ok = fase_grupos(page, sb, prog, prods, incluir_antigos,
                                 prazo_pref, salvar, limite_planos)
        if fim_ok and not so_grupos:
            # no teste, olha assembleia só dos 2 primeiros grupos por segurança
            if teste and prog["grupos_com_vaga"]:
                keep = dict(list(sorted(prog["grupos_com_vaga"].items(),
                                        key=lambda kv: int(kv[0])))[:2])
                prog["grupos_com_vaga"] = keep
            fim_ok = fase_assembleias(page, sb, prog, n_ass, salvar)
    finally:
        try:
            browser.close(); pw.stop()
        except Exception:
            pass

    print("\n" + "=" * 72)
    if fim_ok and prog.get("fase") == "fim":
        ncv = len(prog["grupos_com_vaga"])
        print(f"[OK] Terminou. {ncv} grupo(s) com vaga catalogado(s), "
              f"{len(prog['assembleias_feitas'])} com assembleia coletada.")
        if not teste:
            _prog_limpar()
        print("    Veja tudo na aba 'Base de Dados' do Simulador Yamaha.")
    else:
        print("[!] NÃO terminou — progresso salvo em robo_yamaha_progresso.json.")
        print("    Rode o MESMO comando de novo para continuar de onde parou.")


if __name__ == "__main__":
    main()
