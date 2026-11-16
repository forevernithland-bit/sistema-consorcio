# -*- coding: utf-8 -*-
r"""
calibrar_simulador.py — parte do ROBÔ YAMAHA (16/11/2026). SÓ LEITURA + "Simular...".

Junta casos REAIS do Newcon para deixar o Simulador Yamaha fiel ao centavo:
para cada cota: lê a Posição do Consorciado (taxa da cota, fundo de reserva, % a cobrar
na contemplação, parcelas pagas, valor da parcela, saldo devedor, dif. grupo) e roda
"Simular..." na Oferta de Lance com vários lances (livre/fixo, com e sem embutido,
reduzir parcela e prazo). NUNCA clica em Confirmar nem em Cancelar.

Saída: conhecimento_newcon/calibracao_simulador.json (retoma: pula cenário já feito hoje).
    py -V:3.14 calibrar_simulador.py 9538/369 9600/302 10015/156 ...
"""
import os
import re
import sys
import json
import datetime

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)
ARQ = os.path.join(PASTA, "conhecimento_newcon", "calibracao_simulador.json")

JS = """() => [...document.querySelectorAll('input,select,span[id]')].filter(e => e.id).map(e => ({
  id: e.id, v: (e.tagName==='SELECT' ? (e.options[e.selectedIndex]||{}).text : (e.value ?? e.innerText)) }))
  .filter(x => x.v && String(x.v).trim() && !x.id.startsWith('__'))"""


def _num(s):
    if s is None:
        return None
    t = re.sub(r"[^\d,.\-]", "", str(s))
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except Exception:
        return None


def _campos(page):
    d = {}
    for fr in page.frames:
        try:
            for x in fr.evaluate(JS):
                d[x["id"].replace("ctl00_Conteudo_", "")] = str(x["v"]).strip()
        except Exception:
            pass
    return d


def _depois(txt, rot, n=1):
    m = re.search(re.escape(rot) + r"\s*\n((?:[^\n]*\n){%d})" % n, txt)
    return [l.strip() for l in m.group(1).splitlines()] if m else []


def _abrir_cota(page, g, c):
    import newcon
    newcon._ir_para_atendimento(page)
    page.locator("#ctl00_Conteudo_edtGrupo").fill(g)
    page.locator("#ctl00_Conteudo_edtCota").fill(c)
    page.get_by_role("button", name="Localizar").click()
    page.wait_for_load_state("networkidle")


def ler_posicao(page, g, c):
    import newcon
    _abrir_cota(page, g, c)
    page.get_by_role("link", name="Posição do Consorciado").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(700)
    t = newcon._texto_pagina(page)
    p = {"txt": t[:5000]}
    for rot, k in [("Taxa Adm.:", "taxa_pct"), ("Fnd. Reserva:", "fr_pct"), ("% Cont.:", "pct_cont"),
                   ("Taxa Adesão:", "adesao_pct"), ("Prazo Plano:", "prazo_plano"),
                   ("Qtd. Pcls. Pagas:", "pagas"), ("Qtd. Pcls. Furo:", "furo")]:
        v = _depois(t, rot)
        p[k] = _num(v[0]) if v else None
    for rot, k in [("Valores Pagos:", "pagos"), ("Saldo Devedor:", "sd"), ("Vl. da Parcela:", "parcela")]:
        v = _depois(t, rot, 2)
        if rot == "Vl. da Parcela:":
            v = _depois(t, rot, 3)[1:]
        p[k] = _num(v[0]) if v else None
        p[k + "_pct"] = _num(v[1]) if len(v) > 1 else None
    v = _depois(t, "Dif. Grupo:", 2)
    p["dif_grupo_pct"] = _num(v[1]) if len(v) > 1 else None
    v = _depois(t, "Bem Objeto:", 3)
    p["bem"] = v[1] if len(v) > 1 else None
    p["valor_bem"] = _num(v[2]) if len(v) > 2 else None
    v = _depois(t, "Plano Venda:")
    p["plano_venda"] = v[0] if v else None
    v = _depois(t, "Seguros:")
    p["seguros"] = v[0] if v else None
    return p


def simular(page, g, c, mod, pct, emb, reducao):
    """Abre a Oferta de Lance e simula. Devolve dict com os campos do resultado."""
    _abrir_cota(page, g, c)
    page.get_by_role("link", name="Oferta de Lance").click()
    page.wait_for_load_state("networkidle")
    r = page.locator(f"input[type=radio][id^='ctl00_Conteudo_rgLance'][value='{mod}']")
    if not r.count() or r.first.is_disabled():
        return {"erro": f"modalidade {mod} indisponível"}
    r.first.check(); page.wait_for_load_state("networkidle")
    page.get_by_role("radio", name=reducao).check(); page.wait_for_load_state("networkidle")
    if mod in ("LL", "LM", "LI"):
        page.locator("#ctl00_Conteudo_rblTipoOferta").select_option(label="Percentual")
        page.locator("#ctl00_Conteudo_edtOferta").fill(f"{pct:.4f}".replace(".", ","))
        page.locator("#ctl00_Conteudo_edtOferta").press("Tab"); page.wait_for_load_state("networkidle")
    e = page.locator("#ctl00_Conteudo_edtEmbutido")
    if emb and e.count() and e.is_enabled():
        page.locator("#ctl00_Conteudo_cbxLanceEmbutido").select_option(label="Percentual")
        e.fill(f"{emb:.4f}".replace(".", ",")); e.press("Tab"); page.wait_for_load_state("networkidle")
    avisos = []
    page.on("dialog", lambda d: avisos.append(d.message))
    page.locator("#ctl00_Conteudo_btnSimula").click()
    page.wait_for_load_state("networkidle"); page.wait_for_timeout(1200)
    d = _campos(page)
    import newcon
    page.goto(newcon.HOME_URL, wait_until="domcontentloaded")     # sai sem gravar (nunca Cancelar)
    out = {k: d.get(k) for k in ("lblVL_Lance", "lblPE_Lance", "lblPC_Lance", "lblVlRecursos", "lblQtFuro",
                                 "lblQtProrrogada", "lblVlCredito", "lblSdDevedor", "lblPclPagar",
                                 "lblVlCreditoNovo", "lblSdDevedorNovo", "lblPclPagarNovo", "lblVL_Parcela",
                                 "lblVA_Lance_Minimo", "lblVL_Lance_Minimo", "lblVA_Lance_Maximo",
                                 "lblVL_Lance_Maximo", "lblVA_Lance_Fixo", "lblVA_Lance_Fixo_2", "lblVL_Bem",
                                 "lblPZ_Comercializacao", "lblNM_Plano_Venda", "lblNM_Bem")}
    out = {k: (_num(v) if k not in ("lblNM_Plano_Venda", "lblNM_Bem") else v) for k, v in out.items()}
    out["avisos"] = avisos
    return out


CENARIOS = [  # (modalidade, % lance, % embutido, redução)
    ("LL", 20, 0, "Reduzir Parcela"),
    ("LL", 50, 0, "Reduzir Parcela"),
    ("LL", 50, "EMB", "Reduzir Parcela"),
    ("LL", 50, 0, "Reduzir Prazo"),
    ("LL", 50, "EMB", "Reduzir Prazo"),
    ("LF", None, 0, "Reduzir Parcela"),
    ("LF", None, "EMB", "Reduzir Prazo"),
]
EMB_PADRAO = {"IMOVEL": 25.0, "CAMINHAO": 30.0}


def main(cotas):
    from coletar_grupos import _abrir, _conectar_sb
    try:
        dados = json.load(open(ARQ, encoding="utf-8"))
    except Exception:
        dados = {}
    hoje = datetime.date.today().isoformat()
    pw, aba, ctx, page = _abrir(_conectar_sb(), visivel=True)
    try:
        for gc in cotas:
            g, c = gc.split("/")
            reg = dados.setdefault(gc, {"cenarios": {}})
            if reg.get("posicao_em") != hoje:
                try:
                    reg["posicao"] = ler_posicao(page, g, c); reg["posicao_em"] = hoje
                except Exception as e:
                    print(f"  x posição {gc}: {str(e)[:100]}"); continue
            pos = reg["posicao"]
            bem = (pos.get("bem") or "").upper()
            emb = EMB_PADRAO["IMOVEL"] if "IM" in bem[:4] else EMB_PADRAO["CAMINHAO"] if "CAMIN" in bem else 15.0
            print(f"== {gc}: taxa {pos.get('taxa_pct')} FR {pos.get('fr_pct')} cont {pos.get('pct_cont')} "
                  f"pagas {pos.get('pagas')} parcela {pos.get('parcela')} sd {pos.get('sd')} | {pos.get('plano_venda')}")
            for mod, pct, e, red in CENARIOS:
                ee = emb if e == "EMB" else e
                chave = f"{mod}|{pct}|{ee}|{red}"
                if reg["cenarios"].get(chave, {}).get("em") == hoje:
                    continue
                r = {}
                for _t in range(2):          # 2ª tentativa se o Newcon "não viu" o percentual digitado
                    try:
                        r = simular(page, g, c, mod, pct or 0, ee, red)
                    except Exception as ex:
                        r = {"erro": str(ex)[:150]}
                    if not any("não foi informado" in a for a in r.get("avisos") or []):
                        break
                r["em"] = hoje
                reg["cenarios"][chave] = r
                os.makedirs(os.path.dirname(ARQ), exist_ok=True)
                tmp = ARQ + ".tmp"
                json.dump(dados, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                os.replace(tmp, ARQ)
                print(f"   {chave}: lance {r.get('lblVL_Lance')} ({r.get('lblPE_Lance')}%) rec {r.get('lblVlRecursos')} "
                      f"cred novo {r.get('lblVlCreditoNovo')} sd novo {r.get('lblSdDevedorNovo')} "
                      f"pcl {r.get('lblPclPagar')}->{r.get('lblPclPagarNovo')} parcela {r.get('lblVL_Parcela')} "
                      f"{r.get('erro') or ''} {r.get('avisos') or ''}")
    finally:
        aba.close(); pw.stop()


if __name__ == "__main__":
    main(sys.argv[1:])
