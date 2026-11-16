# -*- coding: utf-8 -*-
r"""
regras_lance.py — parte do ROBÔ YAMAHA (chamado por robo_yamaha.py --regras-lance).

Lê, SÓ LENDO, a tela "Oferta de Lance" de uma cota nossa em cada grupo e guarda as
regras de lance do grupo (16/11/2026):
  * modalidades liberadas no grupo (Livre / Fixo / 2º Fixo / Limitado / Fidelidade)
  * lance mínimo e máximo (%), % do lance fixo e do 2º fixo,
    limitado mínimo/máximo, fidelidade máximo
  * embutido já usado nas ofertas do histórico da cota (% Embutido)
  * plano, bem, prazo e a assembleia em que a oferta vale
Nunca marca nada nem clica em Confirmar. Usa o NAVEGADOR ÚNICO (mesma janela logada).
Grava: conhecimento_newcon/regras_lance.json (sempre) e grupos_yamaha (se --salvar).
Retoma: pula grupo já lido hoje (regras_lance.json guarda a data).
"""
import os
import re
import sys
import json
import datetime

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)
ARQ = os.path.join(PASTA, "conhecimento_newcon", "regras_lance.json")
# igual ao REGRAS_GERAIS do coletar_tabelas_yamaha.py / yamaha.html / modulos/regras_lance_yamaha.py
REGRA_GERAL_EMBUTIDO = {"MOTO": 15.0, "AUTO": 15.0, "IMOVEL": 25.0, "CAMINHAO": 30.0}


def _pct(s):
    if not s:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", s)
    if not m or "---" in s:
        return None
    return float(m.group(1).replace(".", "").replace(",", ".")) if "," in m.group(1) else float(m.group(1))


def _depois(txt, rotulo):
    """valor da linha seguinte ao rótulo (o Newcon põe rótulo e valor em células separadas)."""
    m = re.search(re.escape(rotulo) + r"\s*\n\s*([^\n]+)", txt)
    return m.group(1).strip() if m else None


_JS_RADIOS = """() => [...document.querySelectorAll('input[type=radio]')].map(r => {
   const l = r.id && document.querySelector('label[for="'+r.id+'"]');
   return {label:(l?l.innerText:r.value||'').trim(), marcado:r.checked, desligado:r.disabled}; })"""


def ler_regras(page, grupo, cota):
    import newcon
    newcon._ir_para_atendimento(page)
    page.locator("#ctl00_Conteudo_edtGrupo").fill(str(grupo))
    page.locator("#ctl00_Conteudo_edtCota").fill(str(cota))
    page.get_by_role("button", name="Localizar").click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name="Oferta de Lance").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)
    txt = "\n".join(fr.inner_text("body") for fr in page.frames if fr.url)
    radios = page.evaluate(_JS_RADIOS)
    mod_nomes = {"Livre", "Fixo", "2º Fixo", "Limitado", "Fidelidade"}
    mods = {r["label"]: (not r["desligado"]) for r in radios if r["label"] in mod_nomes}
    r = {"grupo": str(grupo), "cota_lida": str(cota), "lido_em": datetime.date.today().isoformat(),
         "formulario_aberto": bool(mods),
         "modalidades": mods,
         "lance_min_pct": _pct(_depois(txt, "Lance Mínimo:")),
         "lance_max_pct": _pct(_depois(txt, "Lance Máximo:")),
         "lance_fixo_pct": _pct(_depois(txt, "Lance Fixo:")),
         "lance_2fixo_pct": _pct(_depois(txt, "2º Lance Fixo:")),
         "limitado_min_pct": _pct(_depois(txt, "Lance Limitado Mínimo:")),
         "limitado_max_pct": _pct(_depois(txt, "Lance Limitado Máximo:")),
         "fidelidade_max_pct": _pct(_depois(txt, "Lance Fidelidade Máximo:")),
         "plano": _depois(txt, "Tipo de Venda:"), "bem": _depois(txt, "Bem:"),
         "assembleia_oferta": None, "historico": []}
    m = re.search(r"Assembleia:\s*\n?\s*(\d{2}/\d{2}/\d{4})", txt)
    if m:
        r["assembleia_oferta"] = m.group(1)
    # histórico de ofertas: Protocolo | Assembleia | Credenciamento | Modalidade | ... | % Lance | Pc | % Embutido | ...
    for lin in re.findall(r"^\d{6,8}\t.*$", txt, re.M):
        c = [x.strip() for x in lin.split("\t")]
        if len(c) >= 12:
            r["historico"].append({"assembleia": c[1], "modalidade": c[3], "pct_lance": _pct(c[8]),
                                   "pct_embutido": _pct(c[10]), "status": c[15] if len(c) > 15 else ""})
    embs = [h["pct_embutido"] for h in r["historico"] if h["pct_embutido"]]
    r["embutido_usado_max_pct"] = max(embs) if embs else None
    r["modalidades_no_historico"] = sorted({h["modalidade"] for h in r["historico"]})
    return r


def _carregar():
    try:
        return json.load(open(ARQ, encoding="utf-8"))
    except Exception:
        return {}


def _gravar(d):
    os.makedirs(os.path.dirname(ARQ), exist_ok=True)
    tmp = ARQ + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, ARQ)


def _salvar_sb(sb, r):
    """Grava no grupos_yamaha o que cabe nas colunas atuais; o resto vai em lance_regras (se existir)."""
    upd = {"lance_regras_fonte": f"newcon-oferta-lance cota {r['cota_lida']}",
           "lance_regras_em": datetime.datetime.now().isoformat(timespec="seconds")}
    fixos = [x for x in (r["lance_fixo_pct"], r["lance_2fixo_pct"]) if x]
    if fixos:
        upd["lance_fixo_pct"] = fixos
    try:
        sb.table("grupos_yamaha").update(upd).eq("grupo", r["grupo"]).execute()
    except Exception as e:
        print(f"   !! grupos_yamaha {r['grupo']}: {str(e)[:100]}")
    # embutido permitido: tabela do grupo (grupos_yamaha) > regra geral do produto.
    # O Newcon não mostra o máximo de embutido na tela de oferta (só o já usado).
    emb, emb_f = None, None
    try:
        gy = (sb.table("grupos_yamaha").select("embutido_max_pct,tipo_bem").eq("grupo", r["grupo"])
              .execute().data or [{}])[0]
        if gy.get("embutido_max_pct") is not None:
            emb, emb_f = float(gy["embutido_max_pct"]), "tabela do grupo"
        else:
            t = (gy.get("tipo_bem") or r.get("bem") or "").upper()
            prod = ("MOTO" if "MOTO" in t else "IMOVEL" if "IM" in t[:3] else
                    "CAMINHAO" if "CAMIN" in t else "AUTO")
            emb = REGRA_GERAL_EMBUTIDO[prod]
            emb_f = f"regra geral ({prod.lower()})"
    except Exception:
        pass
    if r.get("embutido_usado_max_pct") and (emb is None or r["embutido_usado_max_pct"] > emb):
        emb, emb_f = r["embutido_usado_max_pct"], "já ofertado numa cota nossa (Newcon)"
    r["embutido_max_pct"], r["embutido_fonte"] = emb, emb_f
    try:   # tabela nova (migração 34) — se ainda não existir, só avisa
        linha = {k: r.get(k) for k in ("grupo", "cota_lida", "lido_em", "formulario_aberto", "modalidades",
                                       "lance_min_pct", "lance_max_pct", "lance_fixo_pct", "lance_2fixo_pct",
                                       "limitado_min_pct", "limitado_max_pct", "fidelidade_max_pct",
                                       "embutido_max_pct", "embutido_fonte",
                                       "embutido_usado_max_pct", "modalidades_no_historico", "plano",
                                       "assembleia_oferta")}
        sb.table("yamaha_regras_lance").upsert(linha, on_conflict="grupo").execute()
        return True
    except Exception as e:
        return str(e)[:80]


def rodar(page, sb, cotas_por_grupo, salvar=False, forcar=False):
    dados = _carregar()
    hoje = datetime.date.today().isoformat()
    aviso_tabela = None
    for g, cotas in cotas_por_grupo.items():
        # Só atualiza o que precisa (Breno, 16/11/2026): regra de lance do grupo não muda
        # dentro do mês → lida com o formulário aberto neste mês = em dia, pula.
        if (not forcar and dados.get(g, {}).get("formulario_aberto")
                and str(dados[g].get("lido_em") or "")[:7] == hoje[:7]):
            print(f"  = {g}: regras já lidas este mês ({dados[g].get('lido_em')}) — em dia"); continue
        melhor = None
        for c in cotas[:3]:                       # tenta até 3 cotas do grupo (1ª com formulário aberto vence)
            try:
                r = ler_regras(page, g, c)
            except Exception as e:
                print(f"  x {g}/{c}: {str(e)[:90]}"); continue
            if melhor is None or (r["formulario_aberto"] and not melhor["formulario_aberto"]):
                melhor = r
            if r["formulario_aberto"]:
                break
        if not melhor:
            continue
        ant = dados.get(g) or {}
        if not melhor["formulario_aberto"] and ant.get("formulario_aberto"):
            # hoje o formulário está fechado: mantém as regras lidas quando estava aberto,
            # só soma o histórico novo
            ant = dict(ant)
            ant["historico"] = melhor["historico"] or ant.get("historico", [])
            ant["modalidades_no_historico"] = sorted(set(ant.get("modalidades_no_historico") or [])
                                                     | set(melhor["modalidades_no_historico"]))
            ant["embutido_usado_max_pct"] = max([x for x in (ant.get("embutido_usado_max_pct"),
                                                 melhor["embutido_usado_max_pct"]) if x] or [None]) \
                if (ant.get("embutido_usado_max_pct") or melhor["embutido_usado_max_pct"]) else None
            melhor = ant
        dados[g] = melhor; _gravar(dados)
        mods = ", ".join(k for k, v in melhor["modalidades"].items() if v) or "(formulário fechado agora)"
        print(f"  + {g}: {mods} | fixo {melhor['lance_fixo_pct']} | 2ºfixo {melhor['lance_2fixo_pct']} | "
              f"limit {melhor['limitado_min_pct']}-{melhor['limitado_max_pct']} | fidel {melhor['fidelidade_max_pct']} | "
              f"emb usado {melhor['embutido_usado_max_pct']} | hist {melhor['modalidades_no_historico']}")
        if salvar:
            ok = _salvar_sb(sb, melhor)
            if ok is not True:
                aviso_tabela = ok
    if aviso_tabela:
        print(f"  (tabela yamaha_regras_lance ainda não existe — rode a migração 34. Detalhe: {aviso_tabela})")
    return dados


def main_robo(a):
    from coletar_grupos import _abrir, _conectar_sb
    sb = _conectar_sb()
    if "--so-salvar" in a:            # grava no banco o que já foi lido (sem abrir o Newcon)
        dados = _carregar()
        ok = 0
        for g, r in sorted(dados.items()):
            res = _salvar_sb(sb, r)
            ok += res is True
            if res is not True:
                print(f"  !! {g}: {res}")
        print(f">>> regras de lance gravadas no banco: {ok}/{len(dados)} grupo(s)")
        return
    v = (sb.table("vendas").select("GRUPO,COTA,STATUS,ADMINISTRADORA").ilike("ADMINISTRADORA", "%yamaha%")
         .in_("STATUS", ["Em Andamento", "Em Atraso"]).execute().data or [])
    por = {}
    for x in v:
        por.setdefault(str(x["GRUPO"]).strip(), []).append(str(x["COTA"]).strip())
    if "--grupos" in a:
        quer = set(a[a.index("--grupos") + 1].split(","))
        por = {g: c for g, c in por.items() if g in quer}
    print(f">>> ROBÔ YAMAHA — REGRAS DE LANCE de {len(por)} grupo(s) (só leitura, navegador único)")
    pw, aba, ctx, page = _abrir(sb, visivel=True)
    try:
        rodar(page, sb, dict(sorted(por.items())), salvar="--salvar" in a, forcar="--forcar" in a)
    finally:
        aba.close(); pw.stop()
