"""
planejar.py — Orquestrador do assistente de planejamento de simulações Yamaha.

Junta os dois robôs numa tacada só, do jeito que o Uriel/Breno pedem de boca:
"quero 5 grupos de auto em torno de 80 mil, prazo máximo".

O que ele faz, em ordem:
  1) coletar_grupos.py --credito ALVO --n-grupos N --prazo longo --salvar
     (prioriza planos da metade da lista pra frente; registra em yamaha_buscas;
      pula, no mesmo dia, plano que já buscou e não tinha vaga)
  2) lê no Supabase os grupos COM vaga perto do alvo (respeitando a validade
     por nº de vagas — só re-coleta assembleia de quem está "vencido")
  3) coletar_assembleias.py --grupo G --assembleias 3 --salvar   (um por grupo)
  4) apresenta os 2 cenários:
       * grupo que MAIS contemplou no último mês
       * grupo com a MENOR média de lance no último mês

USO (PC do escritório):
    python planejar.py --produto auto --credito 80000 --n-grupos 5 --prazo longo
    python planejar.py --produto auto --credito 80000 --n-grupos 5 --so-apresentar
        (não roda robô nenhum, só lê o que já está no banco e apresenta)
    + --incluir-antigos   varre também os planos antigos do início da lista
    + --assembleias 6     quantas assembleias olhar por grupo (padrão 3)
    + --headless          navegador invisível

Precisa das migrações 17, 18 e 19 rodadas no Supabase.
"""
import os
import re
import sys
import subprocess
import datetime

sys.path.insert(0, os.path.dirname(__file__))
from coletar_grupos import _conectar_sb, _perto_do_alvo, dias_de_validade, _idade_dias  # noqa

for _st in (sys.stdout, sys.stderr):
    try:
        _st.reconfigure(encoding="utf-8")
    except Exception:
        pass

PASTA = os.path.dirname(__file__)
PY = sys.executable


def _run(args):
    """Roda um script do worker e ecoa a saída. Devolve o returncode."""
    cmd = [PY, os.path.join(PASTA, args[0])] + args[1:]
    print(f"\n$ {' '.join(cmd[1:])}\n" + "-" * 70)
    p = subprocess.run(cmd, cwd=PASTA)
    return p.returncode


def _grupos_alvo(sb, prod_nome, alvo):
    """Grupos COM vaga perto do alvo, do banco. Marca quem precisa re-consultar."""
    try:
        rows = sb.table("grupos_yamaha").select("*").eq("tipo_bem", prod_nome).execute().data or []
    except Exception as e:
        print(f"[erro] lendo grupos_yamaha: {e}")
        return []
    # mês corrente 'AAAA-MM' — se já temos assembleia desse mês, não re-coleta
    mes_atual = datetime.date.today().strftime("%Y-%m")
    try:
        ja = sb.table("yamaha_assembleias").select("grupo,mes_competencia").execute().data or []
    except Exception:
        ja = []
    tem_mes_atual = {str(x["grupo"]) for x in ja if x.get("mes_competencia") == mes_atual}

    out = []
    for r in rows:
        if not _perto_do_alvo(r.get("credito") or 0, alvo):
            continue
        vagas = r.get("vagas") or 0
        if vagas <= 0:
            continue
        # precisa coletar assembleia se ainda não temos a do mês corrente
        r["_precisa_assembleia"] = str(r["grupo"]) not in tem_mes_atual
        out.append(r)
    return sorted(out, key=lambda x: -(x.get("vagas") or 0))


def _resumo_ultimo_mes(sb, grupos):
    """Por grupo: contemplados e média de lance da assembleia mais recente."""
    res = {}
    for g in grupos:
        gid = str(g["grupo"])
        try:
            aa = (sb.table("yamaha_assembleias").select("*")
                  .eq("grupo", gid).order("num_assembleia", desc=True)
                  .limit(1).execute().data or [])
        except Exception:
            aa = []
        if not aa:
            continue
        a = aa[0]
        media = a.get("lance_livre_medio") or a.get("lance_medio") or 0
        res[gid] = {
            "grupo": gid,
            "credito": g.get("credito"),
            "vagas": g.get("vagas"),
            "parcela": g.get("parcela"),
            "parcela_reduzida": g.get("parcela_reduzida"),
            "prox_assembleia": g.get("prox_assembleia"),
            "mes": a.get("mes_competencia"),
            "assembleia": a.get("num_assembleia"),
            "contemplados": a.get("n_total") or 0,
            "n_lance_livre": a.get("n_lance_livre") or 0,
            "n_lance_fixo": a.get("n_lance_fixo") or 0,
            "n_sorteio": a.get("n_sorteio") or 0,
            "lance_medio": round(float(media), 2) if media else None,
            "lance_min": a.get("lance_livre_min") or a.get("lance_min"),
            "lance_max": a.get("lance_livre_max") or a.get("lance_max"),
        }
    return res


def _apresenta(resumo, alvo):
    if not resumo:
        print("\n[!] Nenhum grupo com assembleia coletada. Rode sem --so-apresentar.")
        return
    linhas = list(resumo.values())
    print(f"\n{'='*78}\nGRUPOS ANALISADOS  (crédito ~ R$ {alvo:,.0f})\n{'='*78}")
    print(f"{'Grupo':>7} {'Crédito':>11} {'Vagas':>6} {'Parcela':>11} {'PR':>3} "
          f"{'Mês':>8} {'Contempl':>9} {'LanceMéd%':>10} {'Prox.Assemb':>12}")
    print("-" * 78)
    for x in sorted(linhas, key=lambda y: -(y["contemplados"] or 0)):
        print(f"{x['grupo']:>7} {(x['credito'] or 0):>11,.0f} {x['vagas']:>6} "
              f"{(x['parcela'] or 0):>11,.2f} {'sim' if x['parcela_reduzida'] else '  -':>3} "
              f"{str(x['mes'] or '?'):>8} {x['contemplados']:>9} "
              f"{(str(x['lance_medio']) if x['lance_medio'] is not None else '?'):>10} "
              f"{str(x['prox_assembleia'] or '?'):>12}")

    mais = max(linhas, key=lambda y: (y["contemplados"] or 0))
    com_lance = [y for y in linhas if y["lance_medio"] is not None and y["lance_medio"] > 0]
    menor = min(com_lance, key=lambda y: y["lance_medio"]) if com_lance else None

    print(f"\n{'='*78}\nCENÁRIOS\n{'='*78}")
    print(f"\n1) GRUPO QUE MAIS CONTEMPLOU no último mês ({mais['mes']}):")
    print(f"   Grupo {mais['grupo']} — {mais['contemplados']} contemplados "
          f"({mais['n_lance_livre']} lance livre, {mais['n_lance_fixo']} lance fixo, "
          f"{mais['n_sorteio']} sorteio)")
    print(f"   Crédito R$ {(mais['credito'] or 0):,.0f} | parcela R$ {(mais['parcela'] or 0):,.2f}"
          f"{' (reduzida)' if mais['parcela_reduzida'] else ''} | "
          f"lance médio {mais['lance_medio']}% | próx. assembleia {mais['prox_assembleia']}")

    if menor:
        print(f"\n2) GRUPO COM A MENOR MÉDIA DE LANCE no último mês ({menor['mes']}):")
        print(f"   Grupo {menor['grupo']} — lance médio {menor['lance_medio']}% "
              f"(mín {menor['lance_min']} / máx {menor['lance_max']})")
        print(f"   {menor['contemplados']} contemplados | crédito R$ {(menor['credito'] or 0):,.0f} | "
              f"parcela R$ {(menor['parcela'] or 0):,.2f}"
              f"{' (reduzida)' if menor['parcela_reduzida'] else ''} | "
              f"próx. assembleia {menor['prox_assembleia']}")
    else:
        print("\n2) Sem média de lance livre nos grupos analisados "
              "(só sorteio/lance fixo no último mês).")


def main():
    a = sys.argv[1:]
    if not a or "--help" in a or "-h" in a:
        print(__doc__); return

    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a else d

    prod_in = (opt("--produto", "auto") or "auto").lower()
    prod_map = {"auto": "Auto", "automovel": "Auto", "carro": "Auto", "moto": "Moto",
                "imovel": "Imóvel", "imóvel": "Imóvel", "caminhao": "Caminhão",
                "caminhão": "Caminhão"}
    prod_nome = prod_map.get(prod_in, "Auto")
    alvo = float(re.sub(r"[^\d]", "", opt("--credito", "0")) or 0)
    if not alvo:
        print("informe --credito VALOR"); return
    n_grupos = int(opt("--n-grupos", "5"))
    prazo = (opt("--prazo") or "longo").lower()
    n_ass = opt("--assembleias", "3")
    so_apresentar = "--so-apresentar" in a
    headless = ["--headless"] if "--headless" in a else []

    sb = _conectar_sb()

    # ---------- 1) coleta de grupos ----------
    if not so_apresentar:
        args = ["coletar_grupos.py", "--produto", prod_in, "--credito", str(int(alvo)),
                "--n-grupos", str(n_grupos), "--prazo", prazo, "--salvar"]
        if "--incluir-antigos" in a:
            args.append("--incluir-antigos")
        args += headless
        if _run(args) != 0:
            print("\n[!] coletar_grupos saiu com erro — sigo com o que já estiver no banco.")

    grupos = _grupos_alvo(sb, prod_nome, alvo)
    if not grupos:
        print(f"\n[!] Nenhum grupo COM vaga perto de R$ {alvo:,.0f} no banco.")
        print("    (veja yamaha_buscas — pode ser que nenhum plano tenha vaga hoje.)")
        return
    grupos = grupos[:n_grupos]
    print(f"\n>>> {len(grupos)} grupo(s) com vaga perto do alvo: "
          + ", ".join(f"{g['grupo']}({g['vagas']}v)" for g in grupos))

    # ---------- 2) assembleias (UMA sessão pra todos os grupos) ----------
    if not so_apresentar:
        pendentes = [str(g["grupo"]) for g in grupos if g.get("_precisa_assembleia")]
        ja_tem = [str(g["grupo"]) for g in grupos if not g.get("_precisa_assembleia")]
        if ja_tem:
            print(f"  já temos a assembleia deste mês de: {', '.join(ja_tem)}")
        if pendentes:
            _run(["coletar_assembleias.py", "--grupos", ",".join(pendentes),
                  "--assembleias", str(n_ass), "--tipo-bem", prod_in,
                  "--salvar"] + headless)

    # ---------- 3) apresenta ----------
    resumo = _resumo_ultimo_mes(sb, grupos)
    _apresenta(resumo, alvo)


if __name__ == "__main__":
    main()
