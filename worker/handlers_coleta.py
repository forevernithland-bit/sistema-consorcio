"""
handlers_coleta.py — adaptadores finos entre o supervisor e as coletas do
Newcon que já existem (robo_yamaha.py, coletar_tabelas_yamaha.py).

Todos usam a MESMA sessão Newcon do supervisor (`ctx`) e um callback
`ceder_cb()` que devolve True quando entrou LANCE/BOLETO na fila — aí a
coleta pausa (com o progresso gravado) e retoma depois.

Contrato de retorno: dict {ok, mensagem, resultado?}.
  ok=True  -> tarefa concluiu (ou pausou pra ceder a vez)
  ok=False -> falhou de verdade
"""

import importlib
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import robo_yamaha as RY   # noqa: E402


def _sx_do_ctx(ctx: dict, reabrir_fn):
    """Monta o dicionário `sx` que robo_yamaha espera a partir do contexto
    Newcon do supervisor, com um `reabrir` que delega ao supervisor."""
    sx = {
        "page": ctx["page"],
        "browser": ctx.get("browser"),
        "pw": ctx.get("pw"),
        "ctx": ctx.get("context"),
    }

    def reabrir():
        nova_page = reabrir_fn()          # supervisor reabre o Newcon e devolve a page
        sx["page"] = nova_page
        return nova_page

    return sx, reabrir


def coleta_grupos(sb, ctx, reabrir_fn, *, produtos=None, prazo_pref="longo",
                  salvar=True, limite_planos=None, forcar=False, ceder_cb=None) -> dict:
    prog = RY._prog_ler()
    prods = produtos or list(RY.ORDEM_PRODUTOS)
    prods = [p for p in RY.ORDEM_PRODUTOS if p in prods] or list(RY.ORDEM_PRODUTOS)
    sx, reabrir = _sx_do_ctx(ctx, reabrir_fn)
    r = RY.fase_grupos(sx, sb, prog, prods, False, prazo_pref,
                       salvar, limite_planos, forcar, reabrir, ceder_cb=ceder_cb)
    if r == "CEDEU":
        return {"ok": True, "ceder": True,
                "mensagem": "coleta de grupos pausada (cede a vez) — retoma depois"}
    if not r:
        return {"ok": False, "mensagem": "coleta de grupos interrompida — progresso salvo, roda de novo"}
    return {"ok": True, "mensagem": f"grupos coletados ({len(prog.get('grupos_com_vaga', {}))} com vaga)"}


def coleta_assembleias(sb, ctx, reabrir_fn, *, n_ass=3, salvar=True,
                       forcar=False, ceder_cb=None) -> dict:
    prog = RY._prog_ler()
    if not prog.get("grupos_com_vaga"):
        # semeia do banco: todo grupo com vaga que ainda não tem a assembleia do mês
        try:
            for row in (sb.table("grupos_yamaha").select("grupo,tipo_bem,vagas")
                        .gt("vagas", 0).execute().data or []):
                prog["grupos_com_vaga"][str(row["grupo"])] = row.get("tipo_bem")
        except Exception as e:
            return {"ok": False, "mensagem": f"não li grupos_yamaha: {e}"}
    # Grupos cadastrados à mão pelo Simulador (fonte 'manual…', vagas desconhecidas):
    # sempre entram na fila, mesmo com o progresso do dia já semeado.
    try:
        for row in (sb.table("grupos_yamaha").select("grupo,tipo_bem")
                    .like("fonte", "manual%").is_("vagas", "null").execute().data or []):
            prog["grupos_com_vaga"].setdefault(str(row["grupo"]), row.get("tipo_bem"))
    except Exception as e:
        print(f"  !! não li os grupos manuais de grupos_yamaha: {str(e)[:90]}")
    sx, reabrir = _sx_do_ctx(ctx, reabrir_fn)
    r = RY.fase_assembleias(sx, sb, prog, n_ass, salvar, reabrir, forcar, ceder_cb=ceder_cb)
    if r == "CEDEU":
        return {"ok": True, "ceder": True, "mensagem": "coleta de assembleias pausada (cede a vez)"}
    if not r:
        return {"ok": False, "mensagem": "coleta de assembleias interrompida — progresso salvo"}
    feitas = len(prog.get("assembleias_feitas", []))
    return {"ok": True, "mensagem": f"assembleias coletadas ({feitas} grupo(s))"}


def conferir_grupos(sb, ctx, reabrir_fn, *, vagas=None, assembleias=None, ceder_cb=None) -> dict:
    """CONFERIR_GRUPOS (16/11/2026) — pedido pelo Simulador Consorbens na hora do simulado.
    Confere SÓ os grupos pedidos, na mesma janela do Newcon:
      vagas       = grupos cuja vaga está velha (>6 dias) ou com poucas vagas (<10)
                    → busca só o(s) plano(s) de venda desses grupos;
      assembleias = grupos sem resultado de assembleia recente → lê as últimas.
    Usa um progresso próprio (não mexe na varredura semanal do robo_yamaha)."""
    import datetime
    import conferir_vagas as CV
    vagas = [str(g) for g in (vagas or [])]
    assembleias = [str(g) for g in (assembleias or [])]
    sx, reabrir = _sx_do_ctx(ctx, reabrir_fn)
    prog_orig = RY.PROG
    RY.PROG = os.path.join(_AQUI, "conferir_grupos_progresso.json")
    prog = {"data": datetime.date.today().isoformat(), "fase": "grupos", "planos_feitos": {},
            "grupos_com_vaga": {}, "assembleias_feitas": []}
    msgs, ok = [], True
    try:
        if vagas:
            sit = CV.situacao(sb, vagas)
            so_planos = CV.planos_alvo([s for s in sit if s.get("atual")])
            antes = {s["grupo"]: str((s.get("atual") or {}).get("consultado_em")) for s in sit}
            if so_planos:
                r = RY.fase_grupos(sx, sb, prog, list(so_planos), True, "longo", True, None, True,
                                   reabrir, ceder_cb=ceder_cb, so_planos=so_planos)
                if r == "CEDEU":
                    return {"ok": True, "ceder": True, "mensagem": "conferência pausada (cede a vez)"}
                ok = ok and bool(r)
            depois = {s["grupo"]: s for s in CV.situacao(sb, vagas)}
            novos = [g for g in vagas if str((depois.get(g) or {}).get("atual", {}).get("consultado_em")) != antes.get(g)]
            falhou = [g for g in vagas if g not in novos]
            msgs.append(f"vagas conferidas: {', '.join(novos) or 'nenhum'}"
                        + (f"; sem conferir (plano não abriu): {', '.join(falhou)}" if falhou else ""))
        if assembleias:
            tipos = {}
            poucas = False
            for g in assembleias:
                try:
                    rows = sb.table("grupos_yamaha").select("tipo_bem").eq("grupo", g).limit(1).execute().data or []
                    tipos[g] = (rows[0].get("tipo_bem") if rows else None) or "Auto"
                    n = (sb.table("yamaha_assembleias").select("grupo", count="exact")
                         .eq("grupo", g).execute().count or 0)
                    poucas = poucas or n < 3
                except Exception:
                    tipos[g] = "Auto"
            prog["grupos_com_vaga"] = tipos
            prog["assembleias_feitas"] = []
            r = RY.fase_assembleias(sx, sb, prog, 6 if poucas else 3, True, reabrir, False, ceder_cb=ceder_cb)
            if r == "CEDEU":
                return {"ok": True, "ceder": True, "mensagem": "conferência pausada (cede a vez)"}
            ok = ok and bool(r)
            msgs.append(f"assembleias lidas: {', '.join(prog.get('assembleias_feitas') or []) or 'nenhuma'}")
    finally:
        RY.PROG = prog_orig
        try:
            os.remove(os.path.join(_AQUI, "conferir_grupos_progresso.json"))
        except Exception:
            pass
    return {"ok": ok, "mensagem": " | ".join(msgs) or "nada a conferir"}


def coleta_tabelas(*, salvar=True, forcar=False) -> dict:
    """Lê os PDFs de tabela da pasta da Yamaha e atualiza embutido/lance-fixo.
    Não usa o Newcon. No-op quando não há PDF novo."""
    argv0 = list(sys.argv)
    try:
        sys.argv = ["coletar_tabelas_yamaha.py"]
        if salvar:
            sys.argv.append("--salvar")
        else:
            sys.argv.append("--dry")
        if forcar:
            sys.argv.append("--forcar")
        mod = importlib.import_module("coletar_tabelas_yamaha")
        importlib.reload(mod)
        mod.main()
        return {"ok": True, "mensagem": "tabelas Yamaha processadas" + (" (dry)" if not salvar else "")}
    except SystemExit as e:                       # main() pode chamar sys.exit
        return {"ok": (e.code in (None, 0)), "mensagem": f"coletar_tabelas saiu com code={e.code}"}
    finally:
        sys.argv[:] = argv0
