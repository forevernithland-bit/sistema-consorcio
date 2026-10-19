"""
Fechamento de comissão do VENDEDOR (controle de pagamento) — lógica pura + gravação.

Princípios (revisão de controles de 19/10/2026):
  • o item NASCE de uma baixa real da administradora (comissoes_pagas, não-AJUSTE, valor > 0,
    recebimento até a data de corte) — a previsão só fornece o VALOR, que é congelado no item;
  • identidade do item = administradora|grupo|cota|parcela da administradora|tipo (sem nome do cliente,
    sem id interno) com UNIQUE no banco: não dá para pagar o mesmo item duas vezes;
  • fechamento congelado (hash) — diferenças posteriores viram ajuste no fechamento seguinte;
  • vínculo por usuarios.id (o nome só serve para achar o usuário);
  • estados: RASCUNHO → GERADO → ENVIADO → PAGO (ou COMPENSADO se o total for ≤ 0); CANCELADO.
    Cada passo é gravado com UPDATE condicional (só vale se o status ainda for o esperado) + log.
"""
import hashlib
import html as _html
import json
import re
from datetime import datetime, timezone

import pandas as pd

import comissao_vendedor as cv
from regras import gerar_tabela_parcelas, _gc

STATUS_ABERTOS = ("RASCUNHO", "GERADO", "ENVIADO")


def _dig(x):
    """Primeiro número do texto, sem zeros à esquerda: '01' -> '1', '1ª' -> '1', 'Antecip.' -> ''."""
    m = re.search(r"\d+", str(x if x is not None else ""))
    return str(int(m.group(0))) if m else ""


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _data(s):
    """Data da baixa (dd/mm/aaaa ou ISO) -> Timestamp SEM fuso, ou NaT.
    ISO (aaaa-mm-dd) não pode ser lido com dayfirst: o pandas 3 troca mês e dia."""
    try:
        t = str(s if s is not None else "").strip()
        if t in ("", "None", "nan", "NaT"):
            return pd.NaT
        if re.match(r"^\d{4}-\d{2}-\d{2}", t):
            r = pd.to_datetime(t[:10], format="%Y-%m-%d", errors="coerce")
        else:
            r = pd.to_datetime(t, dayfirst=True, errors="coerce")
        if not pd.isna(r) and r.tzinfo is not None:
            r = r.tz_localize(None)
        return r
    except Exception:
        return pd.NaT


def _txt(v):
    """Texto limpo para gravar no banco (None/NaN -> '')."""
    try:
        if v is None or pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v)


def chave_item(admin, grupo, cota, parcela, tipo):
    return f"{cv.norm(admin)}|{_gc(grupo)}|{_gc(cota)}|{_dig(parcela)}|{tipo}"


def vendedor_do_usuario(usuarios, nome):
    """usuarios (lista de dicts) -> dict do usuário cujo nome normalizado bate, ou None; None se houver 2+."""
    achados = [u for u in usuarios if cv.norm(u.get("nome")) == cv.norm(nome)]
    return achados[0] if len(achados) == 1 else None


def pendencias_bloqueantes(df_vendas, usuarios, vendedor_nome):
    """Coisas que precisam ser resolvidas ANTES de gerar o fechamento do vendedor."""
    out = []
    if df_vendas is None or df_vendas.empty:
        return out
    meu = df_vendas[df_vendas["VENDEDOR"].apply(cv.norm) == cv.norm(vendedor_nome)]
    for _, r in meu.iterrows():
        if str(r.get("STATUS") or "").strip() == "Cancelada" and pd.isna(cv.data_cancelamento(r.get("DATA_CANCELAMENTO"))):
            out.append(f"Cota cancelada sem data de cancelamento: {_gc(r.get('GRUPO'))}/{_gc(r.get('COTA'))} "
                       f"({r.get('Nome do cliente', '')}) — informe a data na ficha da cota (o estorno depende dela).")
    # cotas de vendedor que não é sócio e não tem usuário (ex.: 'Vendedor Terceiro') com baixa a pagar
    nomes_usuarios = {cv.norm(u.get("nome")) for u in usuarios}
    sem = {}
    for _, r in df_vendas.iterrows():
        v = r.get("VENDEDOR")
        if cv.eh_terceiro(v) and cv.norm(v) not in nomes_usuarios:
            sem[str(v)] = sem.get(str(v), 0) + 1
    for v, n in sem.items():
        out.append(f"{n} cota(s) com vendedor “{v}” sem usuário cadastrado — cadastre o vendedor em Configurações → Usuários.")
    homonimos = [u for u in usuarios if cv.norm(u.get("nome")) == cv.norm(vendedor_nome)]
    if len(homonimos) > 1:
        out.append(f"Há {len(homonimos)} usuários com o nome “{vendedor_nome}” — deixe só um (o pagamento é vinculado ao usuário).")
    dup = {}
    if "GRUPO" in meu.columns:
        for _, r in meu.iterrows():
            k = (cv.norm(r.get("ADMINISTRADORA")), _gc(r.get("GRUPO")), _gc(r.get("COTA")))
            dup[k] = dup.get(k, 0) + 1
    for k, n in dup.items():
        if n > 1 and k[1]:
            out.append(f"Cota {k[1]}/{k[2]} cadastrada {n} vezes em Vendas — apague a repetida.")
    return out


def montar_itens(df_vendas, df_admin, cfg, status_dict, comissoes_pagas, vendedor_nome, data_corte, chaves_existentes=(), saldo_anterior=None,
                 orfas=None):
    """Itens candidatos ao fechamento do vendedor.
    Devolve (itens, aguardando) — `aguardando` = linhas previstas que ainda não têm baixa real até o corte.
    `orfas` (lista opcional, preenchida aqui): baixas reais das cotas do vendedor, até o corte, cuja parcela NÃO existe na
    previsão (ex.: cota cancelada antes do vencimento, parcela fora da regra) — hoje não geram item e ninguém veria."""
    itens, aguardando = [], []
    if df_vendas is None or df_vendas.empty:
        return itens, aguardando
    meu = df_vendas[df_vendas["VENDEDOR"].apply(cv.norm) == cv.norm(vendedor_nome)]
    if "TIPO_PRODUTO" in meu.columns:
        meu = meu[meu["TIPO_PRODUTO"].apply(cv.norm).str.replace(" ", "") != "CONSORCIOCONTEMPLADO"]
    if meu.empty:
        return itens, aguardando
    corte = pd.Timestamp(data_corte).normalize()

    # baixas reais (NF ou manual), uma por (admin, grupo, cota, parcela)
    baixas = {}
    for b in comissoes_pagas or []:
        if str(b.get("origem") or "").upper().startswith("AJUSTE"):
            continue
        try:
            vn = float(b.get("valor_nota") or 0)
        except (TypeError, ValueError):
            vn = 0.0
        if vn <= 0:
            continue
        k = (cv.norm(b.get("administradora")), _gc(b.get("grupo")), _gc(b.get("cota")), _dig(b.get("parcela")))
        dt = _data(b.get("data_pagamento"))
        if k not in baixas or (not pd.isna(dt) and (pd.isna(baixas[k][1]) or dt < baixas[k][1])):
            baixas[k] = (b, dt)

    # uma chamada por administradora: grupo/cota iguais em administradoras diferentes são cotas diferentes
    # (a tabela de parcelas não devolve a administradora, então marcamos aqui)
    partes = []
    indice = cv.indice_volumes(df_vendas)
    for adm_n, sub in meu.groupby(meu["ADMINISTRADORA"].apply(cv.norm), sort=False):
        t, _ = gerar_tabela_parcelas(sub, df_vendas, df_admin, cfg, status_dict, _indice=indice)
        if not t.empty:
            partes.append(t.assign(_adm=sub["ADMINISTRADORA"].iloc[0]))
    if not partes:
        return itens, aguardando
    tab = pd.concat(partes, ignore_index=True)
    if orfas is not None:
        previstas = {(cv.norm(r["_adm"]), _gc(r["Grupo"]), _gc(r["Cota"]), _dig(r["Parcela"])) for _, r in tab.iterrows()
                     if str(r.get("Tipo Vendedor") or "") != "Estorno"}
        cotas_meu = {(cv.norm(r.get("ADMINISTRADORA")), _gc(r.get("GRUPO")), _gc(r.get("COTA"))) for _, r in meu.iterrows()}
        for k, (b, dt) in baixas.items():
            if k[:3] in cotas_meu and k not in previstas and not pd.isna(dt) and dt.normalize() <= corte:
                orfas.append({"grupo": k[1], "cota": k[2], "parcela": k[3], "valor_nota": b.get("valor_nota"),
                              "data": b.get("data_pagamento"), "cliente": _txt(b.get("cliente")),
                              "motivo": "baixa recebida de parcela que não está na previsão desta cota (cota cancelada antes do vencimento? parcela fora da regra?)"})
    tab = tab[tab["Vendedor Recebe"] != 0]
    existentes = set(chaves_existentes or ())
    for _, r in tab.iterrows():
        g, c = _gc(r["Grupo"]), _gc(r["Cota"])
        adm = r["_adm"]
        tipo_vd = str(r.get("Tipo Vendedor") or "")
        valor = round(float(r["Vendedor Recebe"]), 2)
        base = {"administradora": cv.norm(adm), "grupo": g, "cota": c, "cliente": _txt(r.get("Cliente")),
                "credito_base": (None if pd.isna(r.get("Valor da Venda")) else round(float(r.get("Valor da Venda") or 0), 2)), "valor": valor,
                "pct": (None if pd.isna(r.get("% Vendedor")) else round(float(r["% Vendedor"]), 4)),
                "parcela_vendedor": str(r.get("Parcela Vendedor") or ""), "referencia": str(r.get("Referência") or "")}
        if tipo_vd == "Estorno":
            ref = str(r.get("Referência") or "")
            dt = pd.Timestamp(r["data_pagamento_dt"]).normalize()
            if "próxima comissão" in ref or dt > corte:
                aguardando.append({**base, "tipo": "ESTORNO", "motivo": "abatimento ainda sem comissão/mês de abate até o corte"})
                continue
            j = _dig(r.get("Parcela Vendedor"))
            ck = f"{cv.norm(adm)}|{g}|{c}|E{j}|ESTORNO"
            if ck in existentes:
                continue
            itens.append({**base, "tipo": "ESTORNO", "chave_item": ck, "parcela_adm": f"E{j}", "baixa_ref": None, "baixa_snapshot": None})
            continue
        if tipo_vd not in ("Comissão", "Bônus") or valor <= 0:
            continue                       # Antecipação etc.: não entra sem baixa específica
        if str(r.get("Parcela Vendedor") or "") == "Antecipação":
            # cota contemplada: a previsão soma as parcelas futuras numa linha só, que não tem nº de parcela
            # da administradora — não casa com baixa nenhuma e não entra sozinha
            aguardando.append({**base, "tipo": "COMISSAO", "parcela_adm": "",
                               "motivo": "antecipação (cota contemplada): não entra automaticamente — acerte por ajuste"})
            continue
        padm = _dig(r.get("Parcela"))
        tipo = "BONUS" if tipo_vd == "Bônus" else "COMISSAO"
        k = (cv.norm(adm), g, c, padm)
        b = baixas.get(k)
        if not b or pd.isna(b[1]) or b[1].normalize() > corte:
            aguardando.append({**base, "tipo": tipo, "parcela_adm": padm,
                               "motivo": "sem baixa da administradora até o corte" if not b else "recebimento depois do corte"})
            continue
        ck = f"{cv.norm(adm)}|{g}|{c}|{padm}|{tipo}"
        if ck in existentes:
            continue
        brow = b[0]
        itens.append({**base, "tipo": tipo, "chave_item": ck, "parcela_adm": padm, "baixa_ref": brow.get("id"),
                      "baixa_snapshot": {"valor_nota": brow.get("valor_nota"), "valor_liquido": brow.get("valor_liquido"),
                                         "data_pagamento": brow.get("data_pagamento"), "origem": brow.get("origem"),
                                         "credito": brow.get("credito")}})
    if saldo_anterior and itens:        # saldo sozinho não vira fechamento (ficaria compensando a si mesmo)
        for sid, val in saldo_anterior:
            ck = f"SALDO|{sid}"
            if ck not in existentes:
                itens.append({"tipo": "SALDO", "chave_item": ck, "administradora": "", "grupo": "", "cota": "", "parcela_adm": "",
                              "cliente": "", "credito_base": None, "pct": None, "valor": round(float(val), 2),
                              "parcela_vendedor": "", "referencia": f"Saldo negativo do fechamento FV-{int(sid):04d} (estorno maior que a comissão)",
                              "baixa_ref": None, "baixa_snapshot": None})
    itens.sort(key=lambda x: (x["grupo"], x["cota"], x["parcela_adm"], x["tipo"]))
    return itens, aguardando


def hash_itens(itens):
    canon = json.dumps(sorted(({k: it.get(k) for k in ("chave_item", "tipo", "valor", "credito_base", "pct")} for it in itens),
                              key=lambda d: d["chave_item"]), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def total_itens(itens):
    return round(sum(round(float(i["valor"]), 2) for i in itens), 2)


# ------------------------------------------------------------------ gravação
class ErroFechamento(Exception):
    pass


def _log(sb, fid, acao, de, para, ator, detalhe=None):
    sb.table("pagamentos_vendedor_log").insert({"fechamento_id": fid, "acao": acao, "status_de": de, "status_para": para,
                                                "ator": ator, "detalhe": detalhe or {}}).execute()


def diagnostico_tabelas(sb):
    """('ok'|'ausente'|'erro', mensagem). 'ausente' = migração 30 ainda não rodada; 'erro' = falha de rede/permissão."""
    try:
        for t in ("pagamentos_vendedor", "pagamentos_vendedor_itens", "pagamentos_vendedor_log"):
            sb.table(t).select("id").limit(1).execute()
        return "ok", ""
    except Exception as e:
        m = str(e)
        if any(x in m for x in ("PGRST205", "42P01", "does not exist", "schema cache", "Could not find the table")):
            return "ausente", m[:200]
        return "erro", m[:200]


def tabelas_ok(sb):
    return diagnostico_tabelas(sb)[0] == "ok"


def _todas(sb, tabela, colunas="*", filtros=None, ordem="id"):
    """Lê a tabela inteira em páginas de 1000 (o PostgREST corta em 1000 linhas sem aviso)."""
    out, i = [], 0
    while True:
        q = sb.table(tabela).select(colunas)
        for c, v in (filtros or {}).items():
            q = q.eq(c, v)
        if ordem:
            q = q.order(ordem)
        r = q.range(i, i + 999).execute().data or []
        out += r
        if len(r) < 1000:
            return out
        i += 1000


def chaves_ativas(sb, vendedor_id=None):
    """Chaves de itens que estão em fechamento ativo. Sem vendedor_id: de TODOS os vendedores."""
    rows = _todas(sb, "pagamentos_vendedor_itens", "chave_item,anulado", {"vendedor_id": vendedor_id} if vendedor_id is not None else None)
    return {r["chave_item"] for r in rows if not r.get("anulado")}


def saldos_a_carregar(sb, vendedor_id):
    """[(id do fechamento COMPENSADO, total negativo)] ainda não levados para outro fechamento."""
    fs = _todas(sb, "pagamentos_vendedor", "id,total,status", {"vendedor_id": vendedor_id, "status": "COMPENSADO"})
    usados = chaves_ativas(sb, vendedor_id)
    return [(f["id"], f["total"]) for f in fs if f"SALDO|{f['id']}" not in usados and float(f["total"]) < 0]


def criar_rascunho(sb, vendedor, itens, data_corte, ator, snapshot_vendedor=None, regra=None):
    if not itens:
        raise ErroFechamento("Nenhum item para fechar.")
    dup = (sb.table("pagamentos_vendedor").select("id").eq("vendedor_id", vendedor["id"]).eq("status", "RASCUNHO").execute().data) or []
    if dup:
        raise ErroFechamento(f"Já existe um rascunho aberto (FV-{int(dup[0]['id']):04d}) para este vendedor. Trave ou cancele antes.")
    corte = pd.Timestamp(data_corte)
    # fechamento MENSAL: um por vendedor e mês (cancelado não conta) — baixa que chegar depois vai para o mês seguinte
    mesmo_mes = (sb.table("pagamentos_vendedor").select("id,status").eq("vendedor_id", vendedor["id"])
                 .eq("competencia", corte.strftime("%Y-%m")).execute().data) or []
    mesmo_mes = [f for f in mesmo_mes if f.get("status") != "CANCELADO"]
    if mesmo_mes:
        raise ErroFechamento(f"Já existe o fechamento FV-{int(mesmo_mes[0]['id']):04d} de {corte.strftime('%m/%Y')} para este vendedor "
                             f"({mesmo_mes[0]['status']}). Cancele-o para refazer, ou deixe as baixas novas para o fechamento do mês seguinte.")
    cab = {"vendedor_id": vendedor["id"], "vendedor_nome": vendedor.get("nome"), "competencia": corte.strftime("%Y-%m"),
           "data_corte": corte.strftime("%Y-%m-%d"), "status": "RASCUNHO", "total": total_itens(itens), "qtd_itens": len(itens),
           "snapshot_vendedor": snapshot_vendedor or {}, "regra_vigente": regra or {}, "gerado_por": ator}
    try:
        res = sb.table("pagamentos_vendedor").insert(cab).execute()
    except Exception as e:                 # outra sessão criou o rascunho/fechamento do mês no mesmo instante (índice único)
        if "ux_pv_um" in str(e):
            raise ErroFechamento("Já existe um fechamento aberto deste vendedor neste mês (outra sessão acabou de criar). Atualize a tela.")
        raise ErroFechamento(f"Não consegui criar o rascunho: {str(e)[:160]}")
    fid = res.data[0]["id"]
    try:
        linhas = [{**{k: v for k, v in it.items()}, "fechamento_id": fid, "vendedor_id": vendedor["id"]} for it in itens]
        sb.table("pagamentos_vendedor_itens").insert(linhas).execute()
    except Exception as e:                 # UNIQUE (item já em outro fechamento) ou falha de rede: desfaz o cabeçalho
        try:
            sb.table("pagamentos_vendedor").delete().eq("id", fid).execute()
        except Exception:
            pass
        raise ErroFechamento(f"Não consegui gravar os itens (algum já está em outro fechamento?): {str(e)[:160]}")
    _log(sb, fid, "RASCUNHO_CRIADO", None, "RASCUNHO", ator, {"itens": len(itens), "total": cab["total"]})
    return fid


def _itens(sb, fid, incluir_anulados=False):
    filtros = {"fechamento_id": fid} if incluir_anulados else {"fechamento_id": fid, "anulado": False}
    return _todas(sb, "pagamentos_vendedor_itens", "*", filtros)


def verificar_integridade(sb, cab, itens=None):
    """True se os itens gravados ainda geram o hash gravado ao travar (e o total confere). Rascunho: sempre True."""
    if cab.get("status") == "RASCUNHO" or not cab.get("hash_conteudo"):
        return True
    itens = _itens(sb, cab["id"]) if itens is None else itens
    return hash_itens(itens) == cab["hash_conteudo"] and abs(total_itens(itens) - float(cab.get("total") or 0)) < 0.005


def _transicao(sb, fid, de, para, campos, ator, acao, detalhe=None):
    """UPDATE condicional: só muda se o status ainda for `de` (protege de duplo clique e de duas sessões)."""
    try:
        res = sb.table("pagamentos_vendedor").update({"status": para, **campos}).eq("id", fid).eq("status", de).execute()
    except Exception as e:
        if "ux_pv_pix_e2e" in str(e):
            raise ErroFechamento("Este ID de transação Pix já foi usado em outro fechamento.")
        raise
    if not res.data:
        raise ErroFechamento(f"O fechamento FV-{int(fid):04d} não está mais em {de} (outra sessão já mexeu). Atualize a tela.")
    _log(sb, fid, acao, de, para, ator, detalhe)


def travar(sb, fid, ator):
    itens = _itens(sb, fid)
    if not itens:
        raise ErroFechamento("Fechamento sem itens.")
    total = total_itens(itens)
    h = hash_itens(itens)
    _transicao(sb, fid, "RASCUNHO", "GERADO", {"total": total, "qtd_itens": len(itens), "hash_conteudo": h,
                                               "travado_em": _agora(), "travado_por": ator},
               ator, "TRAVADO", {"hash": h, "total": total})
    return h


def enviar(sb, fid, ator):
    cab = (sb.table("pagamentos_vendedor").select("hash_conteudo").eq("id", fid).execute().data or [{}])[0]
    _transicao(sb, fid, "GERADO", "ENVIADO", {"enviado_em": _agora(), "enviado_por": ator,
                                              "enviado_hash": cab.get("hash_conteudo")}, ator, "ENVIADO")


def pagar(sb, fid, ator, data_pagamento, forma, valor_pago, pix_e2e=None, obs=None):
    cab = (sb.table("pagamentos_vendedor").select("total,status").eq("id", fid).execute().data or [{}])[0]
    total = round(float(cab.get("total") or 0), 2)
    if total <= 0:
        raise ErroFechamento("Total ≤ 0: use “Compensar” (o saldo passa para o próximo fechamento).")
    if round(float(valor_pago), 2) != total:
        raise ErroFechamento(f"O valor pago (R$ {valor_pago:,.2f}) precisa ser igual ao total do fechamento (R$ {total:,.2f}). "
                             "Diferença deve virar ajuste no próximo fechamento.")
    if not data_pagamento:
        raise ErroFechamento("Informe a data do pagamento.")
    _transicao(sb, fid, "ENVIADO", "PAGO", {"pago_em": _agora(), "pago_por": ator,
                                            "data_pagamento": pd.Timestamp(data_pagamento).strftime("%Y-%m-%d"),
                                            "forma_pagamento": forma, "valor_pago": round(float(valor_pago), 2),
                                            "pix_e2e": ((pix_e2e or "").strip() or None), "observacao": (obs or "").strip() or None},
               ator, "PAGO", {"valor": total, "forma": forma, "e2e": (pix_e2e or "").strip() or None})


def compensar(sb, fid, ator):
    cab = (sb.table("pagamentos_vendedor").select("total").eq("id", fid).execute().data or [{}])[0]
    if round(float(cab.get("total") or 0), 2) > 0:
        raise ErroFechamento("Só dá para compensar fechamento com total ≤ 0.")
    _transicao(sb, fid, "ENVIADO", "COMPENSADO", {"pago_em": _agora(), "pago_por": ator}, ator, "COMPENSADO")


def cancelar(sb, fid, ator, motivo):
    if not (motivo or "").strip() or len(motivo.strip()) < 5:
        raise ErroFechamento("Informe o motivo do cancelamento.")
    cab = (sb.table("pagamentos_vendedor").select("status").eq("id", fid).execute().data or [{}])[0]
    de = cab.get("status")
    if de not in STATUS_ABERTOS:
        raise ErroFechamento("Só dá para cancelar fechamento aberto (rascunho, gerado ou enviado).")
    _transicao(sb, fid, de, "CANCELADO", {"cancelado_em": _agora(), "cancelado_por": ator,
                                          "motivo_cancelamento": motivo.strip()}, ator, "CANCELADO", {"motivo": motivo.strip()})
    # libera as chaves (o banco também faz isso por trigger ao cancelar; aqui só cobre o que ainda estiver ativo)
    sb.table("pagamentos_vendedor_itens").update({"anulado": True}).eq("fechamento_id", fid).eq("anulado", False).execute()


def relatorio_html(cab, itens, vendedor=None):
    """Relatório do fechamento, gerado SÓ do que está gravado (itens + cabeçalho). Todo texto vindo do banco é escapado."""
    def e(v):
        return _html.escape(str(v if v is not None else ""), quote=True)
    def brl(v):
        return ("-" if float(v) < 0 else "") + "R$ " + f"{abs(float(v)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    def pct(x):
        return "" if x is None else ("%.2f%%" % float(x)).replace(".", ",")
    linhas = "".join(
        f"<tr><td>{e(i.get('grupo',''))}/{e(i.get('cota',''))}</td><td>{e(i.get('cliente'))}</td><td>{e(i.get('administradora'))}</td>"
        f"<td>{e(i.get('tipo'))}</td><td>{e(i.get('parcela_vendedor'))}</td>"
        f"<td style='text-align:right'>{pct(i.get('pct'))}</td>"
        f"<td style='text-align:right'>{brl(i['valor'])}</td><td>{e(i.get('referencia'))}</td></tr>" for i in itens)
    ven = vendedor or {}
    cnpj = ('— CNPJ ' + e(ven.get('cnpj'))) if ven.get('cnpj') else ''
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Fechamento FV-{int(cab['id']):04d}</title>
<style>body{{font-family:Arial,sans-serif;color:#1a2a2a;margin:32px}}h1{{color:#2d6a65}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #ccd;padding:6px 8px}}th{{background:#e6f0ef;text-align:left}}.t{{font-size:18px;font-weight:700;margin:16px 0}}
small{{color:#667}}</style></head><body>
<h1>Consorbens — Fechamento de comissão FV-{int(cab['id']):04d}</h1>
<p><b>Vendedor:</b> {e(cab.get('vendedor_nome',''))} {cnpj}<br>
<b>Competência:</b> {e(cab.get('competencia',''))} &nbsp; <b>Data de corte:</b> {e(cab.get('data_corte',''))} &nbsp; <b>Status:</b> {e(cab.get('status',''))}</p>
<table><tr><th>Grupo/Cota</th><th>Cliente</th><th>Administradora</th><th>Tipo</th><th>Parcela</th><th>%</th><th>Valor</th><th>Referência</th></tr>{linhas}</table>
<p class="t">Total do fechamento: {brl(cab.get('total', 0))}</p>
<p><small>Código de autenticidade (SHA-256): {e(cab.get('hash_conteudo')) or '(rascunho — ainda não travado)'}<br>
Documento gerado pelo ERP Consorbens a partir do fechamento gravado. Confira o número e o código com a Consorbens.</small></p></body></html>"""
