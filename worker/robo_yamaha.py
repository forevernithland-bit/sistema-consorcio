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
  * LÊ O QUE JÁ TEMOS primeiro (planos_yamaha + grupos_yamaha) e SÓ BUSCA O
    QUE FALTA OU VENCEU: pula o plano cujo catálogo de faixas tem < 30 dias
    E cujos grupos já vistos ainda estão dentro da validade pela regra do
    Uriel (nº de vagas × dias: <10 vagas revalida sempre, grupo cheio vale
    até 20 dias). `--forcar-grupos` re-varre tudo;
  * uma sessão só — não fica logando/deslogando à toa. Se um passo do Newcon
    travar (timeout, "Invalid postback"), tenta recuperar a navegação; se nem
    assim, REABRE o navegador (novo login) e continua. Na fase de assembleias,
    se 3 grupos seguidos falharem, para (rode de novo mais tarde);
  * grava o progresso em `robo_yamaha_progresso.json` a cada plano/grupo —
    se parar no meio (timeout, queda), rodar o MESMO comando de novo
    continua exatamente de onde parou;
  * tudo o que coleta é gravado no Supabase à medida que anda (com --salvar).

USO (PC do escritório):
    python robo_yamaha.py --rapido                 # MÍNIMO: 1 produto, 1 plano,
                                                   # 1 grupo, 1 assembleia (só confere)
    python robo_yamaha.py --teste --salvar        # curto (2 prod, 2 planos) e grava
    python robo_yamaha.py --completo --salvar      # tudo, grava
  Opções:
    --produtos auto,moto        limita os produtos (padrão: os 4)
    --planos 6                  só os 6 planos MAIS RECENTES de cada produto
    --incluir-antigos           varre também os planos antigos do início
    --prazo longo|todos         longo = só o prazo máximo (rápido; padrão)
    --assembleias 3             nº de assembleias por grupo na fase 2 (padrão 3)
    --so-grupos | --so-assembleias   roda só uma das fases
    --forcar-grupos             re-varre até os planos que já estão em dia
    --headless                  navegador invisível
    --refazer                   ignora o progresso do dia e recomeça

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
    _carregar_catalogo, _idade_dias, precisa_reconsultar, CATALOGO_MAX_DIAS,
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


def _grupos_da_base(sb, prod_nome):
    """Grupos que JÁ temos de um produto, agrupados por plano.
    {plano_cod: [rows]} + set de grupos com vaga."""
    por_plano, com_vaga = {}, {}
    try:
        rows = (sb.table("grupos_yamaha").select("grupo,plano_codigo,vagas,consultado_em,tipo_bem")
                .eq("tipo_bem", prod_nome).execute().data or [])
    except Exception as e:
        print(f"  !! não li grupos_yamaha de {prod_nome}: {str(e)[:90]}")
        rows = []
    for r in rows:
        por_plano.setdefault(_cod(r.get("plano_codigo")), []).append(r)
        if (r.get("vagas") or 0) > 0:
            com_vaga[str(r["grupo"])] = prod_nome
    return por_plano, com_vaga


def _plano_ja_fresco(cod, catalogo, grupos_do_plano):
    """True = já temos esse plano e os dados estão dentro da validade → pular.
    Precisa: catálogo de faixas < 30 dias  E  já vimos grupo(s) desse plano
    E  nenhum deles venceu pela regra do Uriel (nº de vagas × dias)."""
    cat = catalogo.get(cod)
    if not cat or _idade_dias(cat.get("consultado_em")) >= CATALOGO_MAX_DIAS:
        return False
    if not grupos_do_plano:
        return False          # nunca vimos grupo desse plano → tem que varrer
    return not any(precisa_reconsultar(g.get("vagas"), g.get("consultado_em"))
                   for g in grupos_do_plano)


def _voltar_form(sx, prod_pal, reabrir):
    """Volta ao formulário de venda; se não der, reabre o navegador (relogin).
    SEMPRE lê a página atual de `sx` (que reabrir() atualiza)."""
    try:
        _ir_para_form(sx["page"]); _preambulo(sx["page"], prod_pal)
    except Exception:
        reabrir()                       # atualiza sx["page"]
        _ir_para_form(sx["page"]); _preambulo(sx["page"], prod_pal)


def _voltar_resultado(sx, reabrir):
    """Volta pra tela de Resultado de Assembleia (caminho fixo); reabre se travar.
    SEMPRE lê/atualiza `sx["page"]`."""
    try:
        _ir_para_resultado(sx["page"], forcar=True)
    except Exception:
        reabrir()                       # atualiza sx["page"]
        _ir_para_resultado(sx["page"], forcar=True)


def fase_grupos(sx, sb, prog, produtos, incluir_antigos, prazo_pref,
                salvar, limite_planos, forcar, reabrir, ceder_cb=None):
    for prod_in in produtos:
        prod_nome, prod_pal, planos = _planos_do_produto(
            sx["page"], prod_in, incluir_antigos, limite_planos)

        # >>> LÊ O QUE JÁ TEMOS antes de sair varrendo <<<
        catalogo = _carregar_catalogo(sb, prod_nome)
        por_plano, com_vaga_db = _grupos_da_base(sb, prod_nome)
        prog["grupos_com_vaga"].update(com_vaga_db)   # fase 2 cobre até os planos pulados

        feitos = set(prog["planos_feitos"].get(prod_in, []))
        fila, pulados = [], 0
        for v, t in planos:
            c = _cod(t)
            if c in feitos:
                continue
            if not forcar and _plano_ja_fresco(c, catalogo, por_plano.get(c, [])):
                pulados += 1
                prog["planos_feitos"].setdefault(prod_in, []).append(c)
                continue
            fila.append((v, t))
        print(f"\n{'#'*72}\n# {prod_nome}: {len(planos)} plano(s) recente(s) | "
              f"{len(feitos)} feito(s) hoje | {pulados} já em dia (pulados) | "
              f"{len(fila)} a buscar\n{'#'*72}")
        if pulados:
            _prog_gravar(prog)
        if not fila:
            continue

        CG._PROD_PAL = prod_pal
        for i, (pv, pt) in enumerate(fila, 1):
            # "cede a vez": se o supervisor sinalizar que entrou tarefa urgente
            # (LANCE/BOLETO), grava o progresso e sai — retoma no próximo ciclo.
            if ceder_cb and ceder_cb():
                print("  [cede a vez] tarefa urgente na fila — pausando a coleta de grupos.")
                _prog_gravar(prog)
                return "CEDEU"
            cod = _cod(pt)
            print(f"\n[{prod_nome} {i}/{len(fila)}] plano {cod}", flush=True)
            ok = False
            for tent in (1, 2):
                try:
                    meta, grupos = _coletar_plano(
                        sx["page"], pv, pt, alvo=None, com_grupos=True,
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
                        _voltar_form(sx, prod_pal, reabrir)
                    except Exception:
                        pass
            prog["planos_feitos"].setdefault(prod_in, [])
            if ok:
                prog["planos_feitos"][prod_in].append(cod)
            _prog_gravar(prog)

            try:
                _voltar_form(sx, prod_pal, reabrir)
            except Exception as e:
                print(f"\n  !! não consegui voltar ao formulário nem reabrindo ({str(e)[:70]}).")
                print(f"  !! PAROU no plano {cod} de {prod_nome}. O que já foi coletado "
                      f"está salvo. Rode o MESMO comando de novo para continuar.")
                return False
    prog["fase"] = "assembleias"
    _prog_gravar(prog)
    return True


# ------------------------------------------------------------------- fase 2
def fase_assembleias(sx, sb, prog, n_ass, salvar, reabrir, forcar=False, ceder_cb=None):
    pend = [g for g in sorted(prog["grupos_com_vaga"], key=lambda x: int(x))
            if g not in prog["assembleias_feitas"]]
    print(f"\n{'#'*72}\n# ASSEMBLEIAS: {len(prog['grupos_com_vaga'])} grupo(s) com vaga, "
          f"{len(prog['assembleias_feitas'])} já feito(s), {len(pend)} na fila\n{'#'*72}")
    if not pend:
        return True
    try:
        _voltar_resultado(sx, reabrir)     # navega (reabre se travar)
    except Exception as e:
        print(f"  !! não abri Resultado de Assembleia nem reabrindo ({str(e)[:80]}).")
        return False

    falhas_seguidas = 0
    for n, grupo in enumerate(pend, 1):
        if ceder_cb and ceder_cb():
            print("  [cede a vez] tarefa urgente na fila — pausando a coleta de assembleias.")
            _prog_gravar(prog)
            return "CEDEU"
        tb = prog["grupos_com_vaga"].get(grupo)
        print(f"\n[assembleia {n}/{len(pend)}] grupo {grupo} ({tb})", flush=True)
        ok_g, motivo = _vale_a_pena(sb, grupo, forcar)
        if not ok_g:
            print(f"  pula: {motivo}")
            prog["assembleias_feitas"].append(grupo); _prog_gravar(prog)
            continue
        resumos = contempls = None
        for tent in (1, 2, 3):
            try:
                # SEMPRE re-abre a tela limpa (Contemplação → Contemplação →
                # Resultado) antes de digitar o grupo — é o que resolve o
                # "não sabe onde clicar" ao trocar de grupo.
                _voltar_resultado(sx, reabrir)
                _nav_grupo(sx["page"], grupo)
                resumos, contempls = _coletar_um(sx["page"], sb, grupo, n_ass, tb, forcar)
                break
            except Exception as e:
                print(f"  ~ tentativa {tent}: {str(e)[:120]}")
                try:
                    _voltar_resultado(sx, reabrir)   # recupera; reabre se preciso
                except Exception:
                    print("  x não recuperei a sessão nem reabrindo — progresso salvo, "
                          "rode o mesmo comando de novo.")
                    _prog_gravar(prog)
                    return False
        if resumos is None:
            print(f"  x grupo {grupo} FALHOU (fica pendente; segue pro próximo).")
            falhas_seguidas += 1
            _prog_gravar(prog)
            if falhas_seguidas >= 3:
                print("  x 3 grupos seguidos falharam — parando. Rode de novo mais tarde.")
                return False
            continue
        falhas_seguidas = 0
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

    rapido = "--rapido" in a
    teste = "--teste" in a or rapido
    completo = "--completo" in a
    so_grupos = "--so-grupos" in a
    so_assemb = "--so-assembleias" in a
    if not (teste or completo or so_grupos or so_assemb):
        print("passe --rapido | --teste | --completo  (ou --so-grupos / --so-assembleias)")
        return
    salvar = "--salvar" in a
    headless = "--headless" in a
    incluir_antigos = "--incluir-antigos" in a
    prazo_pref = (opt("--prazo") or "longo").lower()
    if prazo_pref in ("todos", "all"):
        prazo_pref = None
    n_ass = int(opt("--assembleias", "1" if rapido else "2" if teste else "3"))
    n_grupos = int(opt("--n-grupos")) if opt("--n-grupos") else None   # teto de grupos na fase 2
    forcar_ass = "--forcar" in a            # relê assembleia mesmo já tendo a do mês
    forcar_grupos = "--forcar-grupos" in a   # re-varre até os planos já em dia
    prods = [p.strip().lower() for p in (opt("--produtos") or ",".join(ORDEM_PRODUTOS)).split(",")]
    prods = [p for p in ORDEM_PRODUTOS if p in prods] or ORDEM_PRODUTOS
    # --planos N = pega só os N planos MAIS RECENTES de cada produto
    limite_planos = (int(opt("--planos")) if opt("--planos")
                     else 1 if rapido else 2 if teste else None)
    if rapido and not opt("--produtos"):
        prods = ["auto"]                       # rápido: 1 produto só
    elif teste and not opt("--produtos"):
        prods = prods[:2]                      # teste: 2 produtos

    if "--refazer" in a:
        _prog_limpar()
    prog = _prog_ler()

    # se um run menor (--rapido/--teste) "terminou" hoje, um run maior deve
    # voltar a varrer os grupos — mas aproveita o que já foi feito.
    if prog.get("fase") == "fim" and (completo or (teste and not rapido)):
        prog["fase"] = "grupos"
        prog["grupos_com_vaga"] = {}          # re-semeia do banco na fase_grupos

    modo = "RÁPIDO" if rapido else "TESTE CURTO" if teste else "COMPLETO"
    print(f">>> ROBÔ YAMAHA — {modo}{' (grava)' if salvar else ' (NÃO grava)'}")
    print(f"    produtos: {', '.join(prods)} | prazo: {prazo_pref or 'todos'} | "
          f"assembleias/grupo: {n_ass}")
    if prog.get("planos_feitos") or prog.get("assembleias_feitas"):
        print(f"    retomando progresso de hoje "
              f"({sum(len(v) for v in prog['planos_feitos'].values())} planos, "
              f"{len(prog['assembleias_feitas'])} assembleias já feitos)")

    sb = _conectar_sb()

    # --so-assembleias sem progresso: pega os grupos com vaga direto do banco
    # (respeitando --produtos)
    if so_assemb and not prog["grupos_com_vaga"]:
        _nomes = {"auto": "Auto", "moto": "Moto", "imovel": "Imóvel", "caminhao": "Caminhão"}
        _quer = {_nomes[p] for p in prods}
        try:
            for r in (sb.table("grupos_yamaha").select("grupo,tipo_bem,vagas")
                      .gt("vagas", 0).execute().data or []):
                if r.get("tipo_bem") in _quer:
                    prog["grupos_com_vaga"][str(r["grupo"])] = r["tipo_bem"]
            print(f"    (--so-assembleias: {len(prog['grupos_com_vaga'])} grupo(s) "
                  f"com vaga de {', '.join(sorted(_quer))} vindos do banco)")
        except Exception as e:
            print(f"    !! não li grupos_yamaha: {e}")

    fase = prog.get("fase", "grupos")
    pw, browser, ctx, page = _abrir(sb, visivel=not headless)
    sessao = {"pw": pw, "browser": browser, "ctx": ctx, "page": page}
    n_reaberturas = [0]

    def reabrir():
        """Fecha e reabre o navegador (novo login). Atualiza sessao['page']."""
        n_reaberturas[0] += 1
        if n_reaberturas[0] > 4:
            raise RuntimeError("reabri o navegador vezes demais — abortando")
        try:
            sessao["browser"].close(); sessao["pw"].stop()
        except Exception:
            pass
        print(f"   [sessão] reabrindo o navegador / novo login "
              f"(reabertura {n_reaberturas[0]})...", flush=True)
        p2, b2, c2, pg2 = _abrir(sb, visivel=not headless)
        sessao.update(pw=p2, browser=b2, ctx=c2, page=pg2)
        return pg2

    fim_ok = True
    try:
        # SEMPRE tenta a fase de grupos (a não ser --so-assembleias). O
        # fase_grupos pula sozinho o produto/plano que já foi feito hoje —
        # então isso resume um run interrompido E acrescenta produtos novos
        # a um progresso que já passou pra fase de assembleias.
        if not so_assemb:
            fim_ok = fase_grupos(sessao, sb, prog, prods, incluir_antigos,
                                 prazo_pref, salvar, limite_planos, forcar_grupos,
                                 reabrir)
        if fim_ok and not so_grupos:
            # rápido: 1 grupo · teste: 2 grupos · --n-grupos N: N (por tempo)
            corte = n_grupos or (1 if rapido else 2 if teste else None)
            if corte and prog["grupos_com_vaga"]:
                keep = dict(list(sorted(prog["grupos_com_vaga"].items(),
                                        key=lambda kv: int(kv[0])))[:corte])
                prog["grupos_com_vaga"] = keep
            fim_ok = fase_assembleias(sessao, sb, prog, n_ass, salvar, reabrir, forcar_ass)
    finally:
        try:
            sessao["browser"].close(); sessao["pw"].stop()
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
