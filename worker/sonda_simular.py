# -*- coding: utf-8 -*-
"""sonda_simular.py — SÓ LEITURA. Abre a Posição do Consorciado e a Oferta de Lance de uma cota,
roda "Simular..." (nunca Confirmar/Cancelar) e despeja todos os campos (id, rótulo, valor)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coletar_grupos import _abrir, _conectar_sb
import newcon

JS = """() => [...document.querySelectorAll('input,select,span[id]')].filter(e => e.id).map(e => ({
  id: e.id, v: (e.tagName==='SELECT' ? (e.options[e.selectedIndex]||{}).text : (e.value ?? e.innerText)) }))
  .filter(x => x.v && String(x.v).trim())"""

g, c = sys.argv[1], sys.argv[2]
pw, aba, ctx, page = _abrir(_conectar_sb(), visivel=True)
out = {}
try:
    newcon._ir_para_atendimento(page)
    page.locator("#ctl00_Conteudo_edtGrupo").fill(g)
    page.locator("#ctl00_Conteudo_edtCota").fill(c)
    page.get_by_role("button", name="Localizar").click(); page.wait_for_load_state("networkidle")
    try:
        page.get_by_role("link", name="Posição do Consorciado").click(); page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        out["posicao_txt"] = newcon._texto_pagina(page)[:6000]
        out["posicao_campos"] = [x for fr in page.frames for x in fr.evaluate(JS)]
    except Exception as e:
        out["posicao_erro"] = str(e)[:200]
    page.get_by_role("link", name="Oferta de Lance").click(); page.wait_for_load_state("networkidle")
    page.locator("input[type=radio][value='LL']").check(); page.wait_for_load_state("networkidle")
    page.get_by_role("radio", name="Reduzir Parcela").check(); page.wait_for_load_state("networkidle")
    page.locator("#ctl00_Conteudo_rblTipoOferta").select_option(label="Percentual")
    page.locator("#ctl00_Conteudo_edtOferta").fill("50,0000"); page.locator("#ctl00_Conteudo_edtOferta").press("Tab")
    page.wait_for_load_state("networkidle")
    page.locator("#ctl00_Conteudo_btnSimula").click(); page.wait_for_load_state("networkidle"); page.wait_for_timeout(1500)
    out["sim_campos"] = [x for fr in page.frames for x in fr.evaluate(JS)]
    page.goto(newcon.HOME_URL)
finally:
    aba.close(); pw.stop()
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conhecimento_newcon", f"sonda_{g}_{c}.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("salvo", p)
