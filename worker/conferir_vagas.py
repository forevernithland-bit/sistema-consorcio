# -*- coding: utf-8 -*-
"""conferir_vagas.py — confere as VAGAS de grupos na hora do simulado / cadastro.

Regra do Breno (16/11/2026): vaga se pega 1x por semana na varredura do robô. Na hora
de um simulado ou cadastro, olha a base primeiro e SÓ vai no Newcon quando precisa:
  * dado com mais de 6 dias (base de mais de uma semana), ou
  * grupo com poucas vagas (< 10) da última vez, ou
  * grupo que nunca foi visto / sem nº de vagas.
Quando vai, busca SÓ o plano de venda daquele grupo (não varre tudo), na MESMA janela
do Newcon (navegador único), e grava em grupos_yamaha.

    py -V:3.14 conferir_vagas.py 9538 9600 10015          # olha a base; confere o que precisar
    py -V:3.14 conferir_vagas.py 9538 --so-ver            # só mostra a situação, não abre o Newcon
    py -V:3.14 conferir_vagas.py 9538 --forcar            # confere no Newcon mesmo estando em dia
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

import coletar_grupos as CG          # noqa: E402
import robo_yamaha as RY             # noqa: E402

PROD_IN = {"Auto": "auto", "Moto": "moto", "Imóvel": "imovel", "Caminhão": "caminhao"}


def _idade(consultado_em):
    try:
        d = datetime.datetime.fromisoformat(str(consultado_em).replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds() / 86400
    except Exception:
        return None


def situacao(sb, grupos):
    """[{grupo, linhas:[...], precisa, motivo}] — lê só a base, não abre o Newcon."""
    out = []
    for g in grupos:
        try:
            rows = (sb.table("grupos_yamaha")
                    .select("grupo,plano_codigo,tipo_bem,vagas,consultado_em,fonte,planos")
                    .eq("grupo", str(g)).execute().data or [])
        except Exception as e:
            rows = []
            print(f"  !! não li grupos_yamaha {g}: {str(e)[:90]}")
        if not rows:
            out.append({"grupo": g, "linhas": [], "precisa": True, "motivo": "grupo não está na base"})
            continue
        r = max(rows, key=lambda x: str(x.get("consultado_em") or ""))
        idade = _idade(r.get("consultado_em"))
        vagas = r.get("vagas")
        if vagas is None:
            precisa, motivo = True, "sem nº de vagas na base"
        elif int(vagas) < CG.POUCAS_VAGAS:
            precisa, motivo = True, f"poucas vagas da última vez ({vagas})"
        elif idade is None or idade > CG.VALIDADE_VAGAS_DIAS:
            precisa, motivo = True, f"base com {idade:.0f} dias" if idade is not None else "sem data"
        else:
            precisa, motivo = False, f"em dia ({vagas} vagas, visto há {idade:.1f} dia(s))"
        out.append({"grupo": g, "linhas": rows, "atual": r, "precisa": precisa, "motivo": motivo})
    return out


def conferir(sb, grupos, forcar=False, so_ver=False, visivel=True, planos_extra=None):
    """planos_extra = códigos de plano a tentar além dos da base (ex.: '184,185')."""
    sit = situacao(sb, grupos)
    for s in sit:
        print(f"  grupo {s['grupo']}: {'CONFERIR' if (s['precisa'] or forcar) else 'ok'} — {s['motivo']}")
    alvo = [s for s in sit if (s["precisa"] or forcar) and s.get("atual")]
    sem_base = [s["grupo"] for s in sit if not s.get("atual")]
    if sem_base:
        print(f"  ! sem base (não sei o plano): {', '.join(map(str, sem_base))} — rode a varredura "
              f"`robo_yamaha.py --so-grupos --salvar` ou cadastre o grupo pelo Simulador.")
    if so_ver or not alvo:
        return sit
    so_planos = {}
    for s in alvo:
        for r in s["linhas"]:
            p = PROD_IN.get(r.get("tipo_bem"))
            if not p:
                continue
            # o grupo pode vender por mais de um plano (e o plano antigo pode sair de venda):
            # tenta o plano da base + todos os planos já vistos (grupos_yamaha.planos) + os extras
            cods = [r.get("plano_codigo")] + list((r.get("planos") or {}).keys()) + list(planos_extra or [])
            for c in cods:
                if c:
                    so_planos.setdefault(p, set()).add(CG._cod(c))
    if not so_planos:
        print("  ! nenhum plano de venda conhecido para os grupos a conferir.")
        return sit
    print(f"  → indo no Newcon (só os planos {dict((k, sorted(v)) for k, v in so_planos.items())})")
    # progresso separado: não mistura com a varredura semanal do robo_yamaha
    RY.PROG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conferir_vagas_progresso.json")
    prog = {"data": datetime.date.today().isoformat(), "fase": "grupos", "planos_feitos": {},
            "grupos_com_vaga": {}, "assembleias_feitas": []}
    pw, browser, ctx, page = CG._abrir(sb, visivel=visivel)
    sx = {"pw": pw, "browser": browser, "ctx": ctx, "page": page}

    def reabrir():
        try:
            sx["browser"].close(); sx["pw"].stop()
        except Exception:
            pass
        p2, b2, c2, pg2 = CG._abrir(sb, visivel=visivel)
        sx.update(pw=p2, browser=b2, ctx=c2, page=pg2)
        return pg2

    try:
        RY.fase_grupos(sx, sb, prog, list(so_planos), True, "longo", True, None, True,
                       reabrir, so_planos=so_planos)
    finally:
        try:
            sx["browser"].close(); sx["pw"].stop()
        except Exception:
            pass
        try:
            os.remove(RY.PROG)
        except Exception:
            pass
    antes = {s["grupo"]: str((s.get("atual") or {}).get("consultado_em")) for s in alvo}
    depois = situacao(sb, [s["grupo"] for s in alvo])
    print("\n  DEPOIS DA CONFERÊNCIA:")
    for s in depois:
        r = s.get("atual") or {}
        novo = str(r.get("consultado_em")) != antes.get(s["grupo"])
        s["conferido_agora"] = novo
        if novo:
            print(f"  grupo {s['grupo']}: {r.get('vagas')} vagas — CONFERIDO AGORA no Newcon")
        else:
            print(f"  grupo {s['grupo']}: NÃO consegui conferir agora (plano não abriu no Newcon). "
                  f"Vale a base: {r.get('vagas')} vagas de {str(r.get('consultado_em'))[:10]} — avisar no simulado. "
                  f"Dica: --planos <códigos atuais do grupo>")
    return depois


def main():
    a = sys.argv[1:]
    planos_extra = []
    if "--planos" in a:
        i = a.index("--planos")
        planos_extra = [x.strip() for x in a[i + 1].split(",") if x.strip()]
        a = a[:i] + a[i + 2:]
    grupos = [x for x in a if not x.startswith("--")]
    if not grupos:
        print(__doc__); return
    sb = CG._conectar_sb()
    conferir(sb, grupos, forcar="--forcar" in a, so_ver="--so-ver" in a,
             visivel="--headless" not in a, planos_extra=planos_extra)


if __name__ == "__main__":
    main()

