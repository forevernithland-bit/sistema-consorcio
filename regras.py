import re
import hashlib
import threading
import weakref
from collections import OrderedDict
import pandas as pd
from utils import parse_float_safe, normalizar_string, normalizar_produto, iter_linhas
import comissao_vendedor as cv

def total_parcelas_regra(admin, produto, tipo_parcela, df_regras):
    """Nº da ÚLTIMA parcela que paga comissão pra essa combinação de
    admin+produto(+tipo de parcela linear/reduzida) — é o "de N" do "X de N"
    mostrado nos relatórios de comissão.
    Atenção: NÃO é a contagem de parcelas com comissão. A Yamaha imóvel, por
    exemplo, paga nas parcelas 1, 2, 4 e 5 (a 3ª não paga): são 4 pagamentos,
    mas a última é a 5ª — o rótulo certo é "5 de 5" (igual ao "Pcl" da NF), e
    não "5 de 4". Mesmo casamento Admin_Norm/Prod_Norm/
    Tipo_Norm que `gerar_tabela_parcelas` usa, só que exposto à parte para quem
    não tem a venda inteira em mãos (ex.: histórico de NF já importado, que só
    guarda administradora/grupo/cota, não produto/tipo_parcela).
    Devolve None se não achar regra (não dá pra saber o total)."""
    if df_regras is None or df_regras.empty:
        return None
    # Desempenho: memória por TABELA DE REGRAS (o mesmo objeto, conferido por
    # referência fraca — se a tabela for outra, a memória é outra) e pelos 3 valores.
    try:
        chave = tuple((type(x).__name__, str(x)) for x in (admin, produto, tipo_parcela))
        with _MEMO_LOCK:
            ent = _MEMO_TOTAL.get(id(df_regras))
            if ent is None or ent[0]() is not df_regras:
                ent = (weakref.ref(df_regras), {})
                if len(_MEMO_TOTAL) > 50:
                    _MEMO_TOTAL.clear()
                _MEMO_TOTAL[id(df_regras)] = ent
            if chave in ent[1]:
                return ent[1][chave]
    except TypeError:
        return _total_parcelas_regra_impl(admin, produto, tipo_parcela, df_regras)
    v = _total_parcelas_regra_impl(admin, produto, tipo_parcela, df_regras)
    with _MEMO_LOCK:
        ent[1][chave] = v
    return v


def _total_parcelas_regra_impl(admin, produto, tipo_parcela, df_regras):
    df_regras = df_regras.copy()
    if 'Tipo_Norm' not in df_regras.columns:
        if 'Tipo_Parcela' in df_regras.columns:
            df_regras['Tipo_Norm'] = df_regras['Tipo_Parcela'].apply(normalizar_string)
        else:
            df_regras['Tipo_Norm'] = ""
    admin_norm = normalizar_string(admin)
    prod_norm = normalizar_produto(produto)
    base = df_regras[(df_regras['Admin_Norm'] == admin_norm) & (df_regras['Prod_Norm'] == prod_norm)]
    if base.empty:
        return None
    tipo_norm = normalizar_string(tipo_parcela or '')
    regra = base[base['Tipo_Norm'] == tipo_norm]
    if regra.empty:
        regra = base[base['Tipo_Norm'] == ""]
    if regra.empty:
        regra = base
    regra = regra.iloc[0]
    pagas = [i for i in range(1, 26) if parse_float_safe(regra.get(f"P{i}", 0)) > 0]
    return max(pagas) if pagas else None


def calcular_comissao_vendedor(df_vendas_global, vendedor_nome, data_venda_dt, cfg):
    """% do crédito por posição de pagamento para a venda do vendedor (regra em comissao_vendedor.py)."""
    return cv.percentuais_da_venda(df_vendas_global, vendedor_nome, data_venda_dt, cfg)


def _datas_comissao_vendedor(df_global, vendedor, df_regras, cfg, status_dict, indice=None, _norm_vend=None):
    """Datas (ordenadas) em que o vendedor tem comissão a receber, somando TODAS as cotas dele.
    Serve para decidir em quais pagamentos o estorno é abatido.
    `_norm_vend` = df_global['VENDEDOR'] já normalizado (só desempenho: não renormaliza a cada vendedor)."""
    if df_global is None or df_global.empty:
        return []
    nv_serie = _norm_vend if _norm_vend is not None else df_global['VENDEDOR'].apply(cv.norm)
    alvo = df_global[nv_serie == cv.norm(vendedor)]
    if alvo.empty:
        return []
    t, _ = _gerar_tabela_parcelas_impl(alvo, df_global, df_regras, cfg, status_dict, _estornos=False, _indice=indice)
    if t.empty:
        return []
    t = t[t['Vendedor Recebe'] > 0]
    return sorted(pd.to_datetime(t['data_pagamento_dt']).tolist())


def _meta_vendedor(pos, perc_pos, data_venda, cfg, _r=None):
    """Rótulos da comissão do vendedor na posição `pos` (0 = 1º pagamento): tipo, parcela k/n, %, referência."""
    r = _r if _r is not None else cv.regra(cfg)
    mes = data_venda.strftime("%m/%Y")
    if pos < 2:
        return ("Comissão", f"{pos + 1}/2", perc_pos[pos],
                f"Comissão base — {perc_pos[pos]:.2f}% do crédito ({pos + 1}º pagamento da administradora)".replace(".", ","))
    if pos == 2:
        return ("Bônus", "1/1", perc_pos[pos],
                f"Bônus produção acima de R$ {r['VD_M1']:,.0f} em {mes} — {perc_pos[pos]:.2f}% (3º pagamento)".replace(",", "X").replace(".", ",").replace("X", "."))
    return ("Bônus", "1/1", perc_pos[pos],
            f"Bônus produção acima de R$ {r['VD_M2']:,.0f} em {mes} — {perc_pos[pos]:.2f}% (4º pagamento)".replace(",", "X").replace(".", ",").replace("X", "."))


# --------------------------------------------------------------------------
# DESEMPENHO — memória dos resultados.
# A mesma tabela (todas as vendas) é pedida várias vezes por clique (Financeiro,
# card do Dashboard, previsão, relatórios) e de novo a cada rerun. O resultado só
# depende do CONTEÚDO das entradas e do dia de hoje; guardamos pela "impressão
# digital" delas e devolvemos sempre uma CÓPIA. Se a impressão digital falhar,
# calcula normalmente (nunca devolve resultado de outra entrada).
# --------------------------------------------------------------------------
_MEMO_TABELA = OrderedDict()
_MEMO_TOTAL = {}
_MEMO_MAX = 24
_MEMO_LOCK = threading.RLock()
_OFFSETS_MES = [pd.DateOffset(months=i - 1) for i in range(1, 26)]
_SETE_DIAS = pd.Timedelta(days=7)


def _digital_df(df):
    if df is None:
        return ("None",)
    h = hashlib.sha1(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()
    return (h, tuple(map(str, df.columns)), tuple(map(str, df.dtypes)), len(df))


def _digital_obj(o):
    if isinstance(o, dict):
        itens = sorted(o.items(), key=lambda kv: str(kv[0]))
        return hashlib.sha1(repr(itens).encode("utf-8", "replace")).hexdigest()
    return hashlib.sha1(repr(o).encode("utf-8", "replace")).hexdigest()


def limpar_memoria_calculos():
    """Esquece os resultados guardados (usado em testes)."""
    with _MEMO_LOCK:
        _MEMO_TABELA.clear()
        _MEMO_TOTAL.clear()


def _memo(nome, partes, calcular):
    try:
        chave = (nome,) + tuple(partes()) + (str(pd.Timestamp.today().normalize().date()),)
        hash(chave)
    except Exception:
        return calcular()
    with _MEMO_LOCK:
        if chave in _MEMO_TABELA:
            _MEMO_TABELA.move_to_end(chave)
            return _MEMO_TABELA[chave]
    res = calcular()
    with _MEMO_LOCK:
        _MEMO_TABELA[chave] = res
        while len(_MEMO_TABELA) > _MEMO_MAX:
            _MEMO_TABELA.popitem(last=False)
    return res


def gerar_tabela_parcelas(df_alvo, df_global, df_regras, cfg, status_dict, _estornos=True, _indice=None):
    """Gera a tabela completa de previsão de comissionamento e parcelas"""
    if _indice is not None:
        return _gerar_tabela_parcelas_impl(df_alvo, df_global, df_regras, cfg, status_dict, _estornos, _indice)

    def _partes():
        return (_digital_df(df_alvo), ("mesmo",) if df_global is df_alvo else _digital_df(df_global),
                _digital_df(df_regras), _digital_obj(cfg or {}), _digital_obj(status_dict or {}), bool(_estornos))

    df, sem_data = _memo("tabela", _partes, lambda: _gerar_tabela_parcelas_impl(
        df_alvo, df_global, df_regras, cfg, status_dict, _estornos, None))
    return df.copy(), list(sem_data)


def _gerar_tabela_parcelas_impl(df_alvo, df_global, df_regras, cfg, status_dict, _estornos=True, _indice=None):
    """Cálculo de verdade (sem memória). Mesma regra de sempre; só não refaz contas
    repetidas por linha (regra da administradora, % de cada parcela, parâmetros
    da configuração, nome normalizado do vendedor)."""
    hoje = pd.Timestamp.today().normalize()
    _cache_datas_vd = {}
    _cache_regra = {}
    _cache_pvals = {}
    _cache_nv = {}
    _norm_vend = {}
    # parâmetros da configuração lidos uma vez (mesmos valores de antes)
    _imp = parse_float_safe(cfg.get('Imposto', 7.16)) / 100.0
    _bb = parse_float_safe(cfg.get('Breno_Breno', 70)) / 100.0
    _bu = parse_float_safe(cfg.get('Breno_Uriel', 30)) / 100.0
    _uu = parse_float_safe(cfg.get('Uriel_Uriel', 70)) / 100.0
    _ub = parse_float_safe(cfg.get('Uriel_Breno', 30)) / 100.0
    _cb = parse_float_safe(cfg.get('Cons_Breno', 50)) / 100.0
    _cu = parse_float_safe(cfg.get('Cons_Uriel', 50)) / 100.0
    _modo_desc = cv.desconta_dos_socios(cfg)
    _r_cfg = cv.regra(cfg)
    _indice_vol = _indice if _indice is not None else cv.indice_volumes(df_global)      # produção por vendedor/mês, calculada uma vez
    parcelas_finais = []
    vendas_sem_data = []

    # A regra de comissão pode variar pelo TIPO DE PARCELA da cota
    # (linear x reduzida) — ex.: Itaú imóvel reduzida = 4% em 12 parcelas.
    # Se a coluna ainda não existe (antes da migração 25), tudo cai na
    # regra genérica e nada muda para as outras administradoras.
    if df_regras is None or df_regras.empty:
        # sem regras cadastradas: nenhuma cota casa regra (antes dava KeyError 'Admin_Norm' em todas as telas)
        df_regras = pd.DataFrame(columns=['Admin_Norm', 'Prod_Norm', 'Tipo_Norm'])
    if not df_regras.empty and 'Tipo_Norm' not in df_regras.columns:
        df_regras = df_regras.copy()
        if 'Tipo_Parcela' in df_regras.columns:
            df_regras['Tipo_Norm'] = df_regras['Tipo_Parcela'].apply(normalizar_string)
        else:
            df_regras['Tipo_Norm'] = ""

    for r in iter_linhas(df_alvo):
        data_venda = r['Data_Real']
        cliente = r.get('Nome do cliente', 'Desconhecido')
        grupo = r.get('GRUPO', '')
        cota = r.get('COTA', '')

        # Consórcio Contemplado não gera comissão por parcela — a renda é o ágio.
        if normalizar_string(r.get('TIPO_PRODUTO', '')) == "CONSORCIOCONTEMPLADO":
            continue

        if pd.isna(data_venda):
            vendas_sem_data.append(f"{cliente} (Gr: {grupo}/Cota: {cota})")
            continue 
            
        admin = r['ADMINISTRADORA']
        admin_norm = normalizar_string(admin)
        prod = r['PRODUTO']
        prod_norm = normalizar_produto(prod)
        vendedor = r['VENDEDOR']
        val_venda = r['Valor_Numerico']
        
        status_cota = r.get('STATUS', 'Em Andamento')
        if status_cota in ["Vendido", ""]: status_cota = "Em Andamento"

        tipo_norm = normalizar_string(r.get('TIPO_PARCELA', '') or '')
        chave_regra = (admin_norm, prod_norm, tipo_norm)
        if chave_regra not in _cache_regra:
            base = df_regras[(df_regras['Admin_Norm'] == admin_norm) & (df_regras['Prod_Norm'] == prod_norm)]
            if base.empty:
                _cache_regra[chave_regra] = None
            else:
                # 1º: regra específica do tipo de parcela da cota; 2º: regra genérica
                # (Tipo_Norm vazio); 3º: qualquer uma que casou admin+produto.
                regra = base[base['Tipo_Norm'] == tipo_norm]
                if regra.empty:
                    regra = base[base['Tipo_Norm'] == ""]
                if regra.empty:
                    regra = base
                _cache_regra[chave_regra] = regra.iloc[0]
                _cache_pvals[chave_regra] = [parse_float_safe(regra.iloc[0].get(f"P{i}", 0)) / 100.0 for i in range(1, 26)]
        regra = _cache_regra[chave_regra]
        if regra is None: continue
        pvals = _cache_pvals[chave_regra]

        if vendedor not in _cache_nv:
            _cache_nv[vendedor] = (cv.norm(vendedor), cv.eh_terceiro(vendedor))
        nv, eh_terceiro = _cache_nv[vendedor]
        perc_pos = cv.percentuais_da_venda(df_global, vendedor, data_venda, cfg, indice=_indice_vol) if eh_terceiro else []
        temp_parcels = []
        base_pgto = data_venda + _SETE_DIAS

        for i in range(1, 26):
            p_val = pvals[i - 1]
            # `not (p_val > 0)` cobre 0, negativo E NaN (célula vazia na regra).
            # Sem isso a cota gerava as 25 parcelas, e as não definidas pela
            # administradora vinham com comissão NaN.
            if not (p_val > 0): continue
            
            comissao_bruta = val_venda * p_val
            imposto_val = comissao_bruta * _imp
            corretora_liq = comissao_bruta - imposto_val
            
            vend_rec = 0.0
            vend_desc = 0.0
            breno_rec = 0.0
            uriel_rec = 0.0
            
            # Divisão societária e de vendedores
            if nv == "BRENO LIMA":
                breno_rec = corretora_liq * _bb
                uriel_rec = corretora_liq * _bu
            elif nv == "URIEL GOMES":
                uriel_rec = corretora_liq * _uu
                breno_rec = corretora_liq * _ub
            elif nv == "CONSORBENS":
                breno_rec = corretora_liq * _cb
                uriel_rec = corretora_liq * _cu
            elif nv == "PARTICULAR BRENO":
                breno_rec = corretora_liq  # 100% Breno
                uriel_rec = 0.0
            elif nv == "PARTICULAR URIEL":
                uriel_rec = corretora_liq  # 100% Uriel
                breno_rec = 0.0
            else:
                # posição do PAGAMENTO (não o nº da parcela): regra com "buraco" (Yamaha imóvel
                # paga 1,2,4,5) senão deixava o vendedor sem receber a última fatia.
                pos = len(temp_parcels)
                if eh_terceiro and pos < len(perc_pos): vend_rec = val_venda * (perc_pos[pos] / 100.0)
                # o que sai da corretora: por padrão TUDO (base + bônus do vendedor);
                # cfg VD_DESCONTA_SOCIOS: 0 nada, 1 tudo, 2 só o bônus
                vend_desc = cv.parte_descontada(_modo_desc, vend_rec if pos < 2 else 0.0, vend_rec if pos >= 2 else 0.0)
                sobra = corretora_liq - vend_desc
                breno_rec = sobra * 0.50
                uriel_rec = sobra * 0.50

            data_pagamento = base_pgto + _OFFSETS_MES[i - 1]
            item = {
                'parcela': i, 'data_pagamento': data_pagamento, 'bruto': comissao_bruta,
                'liquido': corretora_liq, 'vend': vend_rec, 'breno': breno_rec, 'uriel': uriel_rec,
                'vend_desc': vend_desc
            }
            if eh_terceiro and vend_rec > 0:
                item['tipo_vd'], item['parc_vd'], item['pct_vd'], item['ref_vd'] = _meta_vendedor(
                    len(temp_parcels), perc_pos, data_venda, cfg, _r_cfg)
            temp_parcels.append(item)

        # "de N" do "X de N": nº da ÚLTIMA parcela com comissão na regra (antes de
        # Cancelada/Contemplada cortarem a lista). Não é a contagem: regra com
        # "buraco" (ex.: Yamaha imóvel paga 1,2,4,5) tem N=5, senão saía "5 de 4".
        total_parc = max((p['parcela'] for p in temp_parcels), default=0)

        # Lógica de cotas Canceladas e Contempladas
        if status_cota == 'Cancelada':
            # com a data do cancelamento cadastrada, nada vence depois dela
            dt_canc = cv.data_cancelamento(r.get('DATA_CANCELAMENTO'))
            corte = hoje if pd.isna(dt_canc) else min(hoje, dt_canc)
            def _ja_paga(p):
                inf = status_dict.get(f"{cliente}_{grupo}_{cota}_{admin}_{p['parcela']}", {})
                st_p = inf if isinstance(inf, str) else (inf or {}).get('Status', '')
                return str(st_p).upper() == 'PAGO'
            temp_parcels = [p for p in temp_parcels if p['data_pagamento'] <= corte or _ja_paga(p)]
            # estorno do vendedor: cancelou em até N meses da venda -> devolve parte do que recebeu
            if _estornos and eh_terceiro and not pd.isna(dt_canc):
                ganho = sum(p['vend'] for p in temp_parcels)
                est = cv.estorno(val_venda, data_venda, dt_canc, ganho, cfg)
                if est > 0:
                    k = cv.regra(cfg)['VD_EST_PARCELAS']
                    chave_vd = cv.norm(vendedor)
                    if chave_vd not in _cache_datas_vd:
                        if "s" not in _norm_vend:
                            _norm_vend["s"] = df_global['VENDEDOR'].apply(cv.norm) if (df_global is not None and not df_global.empty) else None
                        _cache_datas_vd[chave_vd] = _datas_comissao_vendedor(df_global, vendedor, df_regras, cfg, status_dict, _indice_vol,
                                                                            _norm_vend=_norm_vend["s"])
                    # próximos K "relatórios" (meses) em que o vendedor tem comissão a receber depois do cancelamento
                    meses_dt = {}
                    for d in _cache_datas_vd[chave_vd]:
                        if d >= dt_canc.normalize():
                            meses_dt.setdefault((d.year, d.month), d)
                    datas_est = [meses_dt[m] for m in sorted(meses_dt)][:k]
                    base = round(est / k, 2)
                    ref_base = (f"Estorno de {cliente} ({grupo}/{cota}) — cota cancelada em {dt_canc.strftime('%d/%m/%Y')}, "
                                f"venda de {data_venda.strftime('%d/%m/%Y')}")
                    for j in range(1, k + 1):
                        val_j = base if j < k else round(est - base * (k - 1), 2)
                        aguarda = j > len(datas_est)
                        dt_j = datas_est[j - 1] if not aguarda else (max([dt_canc] + datas_est) + pd.DateOffset(months=j - len(datas_est)))
                        _volta = val_j / 2.0 if cv.desconta_dos_socios(cfg) == 1 else 0.0   # só volta aos sócios se a base do vendedor saiu do bolso deles
                        temp_parcels.append({
                            'parcela': f'Estorno{j}', 'data_pagamento': dt_j, 'bruto': 0.0, 'liquido': 0.0,
                            'vend': -val_j, 'breno': _volta, 'uriel': _volta,
                            'tipo_vd': 'Estorno', 'parc_vd': f"{j}/{k}", 'pct_vd': -cv.regra(cfg)['VD_EST_PCT'] / k,
                            'ref_vd': ref_base + (" — a abater na próxima comissão do vendedor" if aguarda else ""),
                            'aguarda': aguarda})
        elif status_cota == 'Contemplada':
            past = [p for p in temp_parcels if p['data_pagamento'] <= hoje]
            future = [p for p in temp_parcels if p['data_pagamento'] > hoje]
            if future:
                past.append({
                    'parcela': 'Antecipação', 'data_pagamento': hoje,
                    'bruto': sum(p['bruto'] for p in future), 'liquido': sum(p['liquido'] for p in future),
                    'vend': sum(p['vend'] for p in future), 'breno': sum(p['breno'] for p in future), 'uriel': sum(p['uriel'] for p in future),
                    'tipo_vd': 'Comissão' if eh_terceiro else '', 'parc_vd': 'Antecipação' if eh_terceiro else '',
                    'pct_vd': sum(p.get('pct_vd', 0) for p in future) if eh_terceiro else None,
                    'ref_vd': 'Antecipação das parcelas restantes (cota contemplada)' if eh_terceiro else ''
                })
            temp_parcels = past
            
        for p in temp_parcels:
            chave_unica = f"{cliente}_{grupo}_{cota}_{admin}_{p['parcela']}"
            
            # Puxa o status e a data customizada (se houver no banco)
            info_status = status_dict.get(chave_unica, {})
            if isinstance(info_status, str): 
                status_pagamento = info_status
                data_custom = None
            else:
                status_pagamento = info_status.get('Status', 'Pendente')
                data_custom = info_status.get('Data_Pagamento')
            
            data_str = p['data_pagamento'].strftime("%d/%m/%Y")
            if status_cota == 'Em Atraso': data_str = "⚠️ Travada (Atraso)"
            if p.get('aguarda') and str(status_pagamento).upper() != 'PAGO': data_str = "⏳ Próxima comissão"
            
            # Se tivermos uma data editada manualmente no banco, sobrescrevemos a calculada
            if data_custom and pd.notna(data_custom) and str(data_custom).strip() != "":
                data_str = str(data_custom)
            
            if isinstance(p['parcela'], int): nome_parcela = f"{p['parcela']} de {total_parc}"
            elif str(p['parcela']).startswith('Estorno'): nome_parcela = f"Estorno {p['parc_vd']}"
            else: nome_parcela = "Antecip. (Contemplada)"

            parcelas_finais.append({
                "Chave": chave_unica,
                "Cliente": cliente,
                "Produto": prod,
                "Vendedor": vendedor,
                "Grupo": grupo,
                "Cota": cota,
                "Valor da Venda": val_venda,
                "Parcela": nome_parcela,
                "Total Parcelas": total_parc,
                "data_pagamento_dt": p['data_pagamento'],
                "Comissão (Bruta)": p['bruto'],
                "Comissão (s/ Imposto)": p['liquido'],
                "Breno": p['breno'],
                "Uriel": p['uriel'],
                "Vendedor Recebe": p['vend'],
                "Tipo Vendedor": p.get('tipo_vd', ''),
                "Parcela Vendedor": p.get('parc_vd', ''),
                "% Vendedor": p.get('pct_vd'),
                "Referência": p.get('ref_vd', ''),
                "Status": status_pagamento,
                "Data Recebimento": data_str
            })

    return pd.DataFrame(parcelas_finais), vendas_sem_data


# ==========================================================
# PREVISÃO DE RECEBIMENTO (usada pelo Financeiro e pelos Relatórios)
# ==========================================================
# Status que significam "cota viva, ainda vai gerar comissão". O banco tem
# formas legadas em caixa alta ("VENDIDO") que precisam entrar aqui, senão a
# cota some da previsão sem ninguém perceber.
STATUS_ATIVOS = {"em andamento", "vendido", ""}


def _gc(v):
    """Grupo/cota comparável: '009045', '9045', 9045.0 -> '9045'."""
    s = str(v if v is not None else "").strip()
    if s.lower() in ("nan", "none", "<na>", "nat"):
        return ""
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s


def cotas_duplicadas(df_vendas):
    """Grupo/cota cadastrado mais de uma vez em `vendas`.
    Duplicata infla a previsão (a mesma cota projeta duas vezes), por isso as
    telas avisam em vez de somar em silêncio. Retorna {'grupo/cota': [linhas]}."""
    if df_vendas is None or df_vendas.empty:
        return {}
    grupos = df_vendas['GRUPO'].tolist() if 'GRUPO' in df_vendas.columns else [None] * len(df_vendas)
    cotas = df_vendas['COTA'].tolist() if 'COTA' in df_vendas.columns else [None] * len(df_vendas)
    vistos = {}
    for pos, (g, c) in enumerate(zip(grupos, cotas)):
        gc = f"{_gc(g)}/{_gc(c)}"
        if gc == "/":
            continue          # Consórcio Contemplado não tem grupo/cota
        vistos.setdefault(gc, []).append(pos)
    return {k: [df_vendas.iloc[p] for p in v] for k, v in vistos.items() if len(v) > 1}


def _parc_num(p):
    """'3ª Parcela' / 3 / 'Antecip...' -> '3' ou '' (não numérica)."""
    m = re.search(r"\d+", str(p))
    return m.group(0) if m else ""


def _pagas_por_gc_parcela(status_dict):
    """Conjunto de (grupo, cota, parcela) já pagas, IGNORANDO o nome do cliente.

    A `chave_unica` do status inclui o nome do cliente; quando a mesma cota foi
    cadastrada com o nome em grafias diferentes (ex.: 'Uriel Gomes Junior' x
    'URIEL GOMES JUNIOR'), a parcela paga sob uma grafia não é reconhecida pela
    outra e a previsão a conta como pendente. Aqui reduzimos a chave a
    grupo/cota/parcela para não deixar isso passar."""
    pagas = set()
    for chave, info in (status_dict or {}).items():
        status = info if isinstance(info, str) else (info or {}).get("Status", "")
        if str(status).upper() != "PAGO":
            continue
        partes = str(chave).split("_")
        if len(partes) >= 3:
            g, c, parc = _gc(partes[-4]) if len(partes) >= 4 else "", _gc(partes[-3]), _gc(partes[-1])
            # formato: Cliente_GRUPO_COTA_ADMIN_PARCELA  -> índices -4,-3,-1
            pagas.add((_gc(partes[-4]), _gc(partes[-3]), _gc(partes[-1])))
    return pagas


def gerar_previsao_pendente(df_vendas, df_admin, cfg, status_dict):
    """Mesma função de sempre, com memória do resultado (ver `_memo`)."""
    if df_vendas is None or df_vendas.empty:
        return _gerar_previsao_pendente_impl(df_vendas, df_admin, cfg, status_dict)

    def _partes():
        return (_digital_df(df_vendas), _digital_df(df_admin), _digital_obj(cfg or {}), _digital_obj(status_dict or {}))

    df, avisos = _memo("previsao", _partes, lambda: _gerar_previsao_pendente_impl(df_vendas, df_admin, cfg, status_dict))
    return df.copy(), list(avisos)


def _gerar_previsao_pendente_impl(df_vendas, df_admin, cfg, status_dict):
    """Comissões que ainda NÃO entraram, das cotas vivas.

    Fonte única da previsão — Financeiro e Relatórios chamam esta função para
    não divergirem. Regras aplicadas:
      • só cotas com status ativo (STATUS_ATIVOS), pois Cancelada/Contemplada
        não geram parcela futura;
      • cada grupo/cota entra UMA vez (cota cadastrada em duplicidade contaria
        a comissão duas vezes);
      • só parcelas ainda não baixadas — checando por grupo/cota/parcela, sem
        depender do nome do cliente na chave;
      • valor e data vêm de `gerar_tabela_parcelas`, ou seja, da regra da
        administradora + produto.

    Retorna (DataFrame, avisos). Colunas: ym, cliente, gc, admin, produto,
    vendedor, parcela, data, bruto, liquido, breno, uriel, atrasada.
    """
    colunas = ["ym", "cliente", "gc", "admin", "produto", "vendedor", "parcela",
               "data", "bruto", "liquido", "breno", "uriel", "atrasada"]
    vazio = pd.DataFrame(columns=colunas)
    avisos = []
    if df_vendas is None or df_vendas.empty:
        return vazio, avisos

    pagas_gcp = _pagas_por_gc_parcela(status_dict)

    st_norm = df_vendas["STATUS"].fillna("").astype(str).str.strip().str.lower()
    ativas = df_vendas[st_norm.isin(STATUS_ATIVOS)].copy()
    if ativas.empty:
        return vazio, avisos

    # uma linha por grupo/cota (a mais recente vence)
    dups = cotas_duplicadas(ativas)
    if dups:
        avisos.append(
            f"{len(dups)} cota(s) cadastrada(s) em duplicidade — contei uma vez só: "
            + ", ".join(sorted(dups)))
        ativas["_gc"] = [f"{_gc(g)}/{_gc(c)}"
                         for g, c in zip(ativas['GRUPO'].tolist(), ativas['COTA'].tolist())]
        # NaT (sem data) primeiro: a duplicata COM data é a que fica (antes a sem data vencia e a cota sumia)
        ativas = ativas.sort_values("Data_Real", na_position="first").drop_duplicates("_gc", keep="last")
        ativas = ativas.drop(columns=["_gc"])

    # cota cuja administradora/produto não casa com nenhuma regra cadastrada sairia da
    # previsão em silêncio — avisa para o cadastro ser corrigido.
    sem_regra = []
    for v in iter_linhas(ativas):
        if normalizar_string(v.get("TIPO_PRODUTO", "")) == "CONSORCIOCONTEMPLADO":
            continue
        if total_parcelas_regra(v.get("ADMINISTRADORA"), v.get("PRODUTO"), v.get("TIPO_PARCELA"), df_admin) is None:
            sem_regra.append(f"{_gc(v.get('GRUPO'))}/{_gc(v.get('COTA'))} ({str(v.get('ADMINISTRADORA') or '—').strip()}/{v.get('PRODUTO') or '—'})")
    if sem_regra:
        avisos.append(f"{len(sem_regra)} cota(s) SEM regra de comissão cadastrada ficaram fora da previsão "
                      "(confira Administradoras): " + ", ".join(sem_regra[:6]) + ("…" if len(sem_regra) > 6 else ""))

    df_parc, sem_data = gerar_tabela_parcelas(ativas, df_vendas, df_admin, cfg, status_dict)
    if sem_data:
        avisos.append(f"{len(sem_data)} venda(s) sem data ficaram fora da previsão: "
                      + ", ".join(sem_data[:5]) + ("…" if len(sem_data) > 5 else ""))
    if df_parc.empty:
        return vazio, avisos

    pend = df_parc[df_parc["Status"].astype(str).str.upper() != "PAGO"].copy()
    if pend.empty:
        return vazio, avisos
    pend["dt"] = pd.to_datetime(pend["data_pagamento_dt"], errors="coerce")
    pend = pend[pend["dt"].notna()]
    if pend.empty:
        return vazio, avisos

    info = {}
    for v in iter_linhas(ativas):
        info[f"{_gc(v.get('GRUPO'))}/{_gc(v.get('COTA'))}"] = (
            str(v.get("ADMINISTRADORA") or "—").strip().upper(),
            normalizar_produto(v.get("PRODUTO")) or "—")

    hoje = pd.Timestamp.today().normalize()
    regs = []
    puladas_pagas = 0
    for p in iter_linhas(pend):
        gc = f"{_gc(p['Grupo'])}/{_gc(p['Cota'])}"
        # já paga sob outra grafia do nome do cliente? não é previsão.
        if (_gc(p["Grupo"]), _gc(p["Cota"]), _parc_num(p["Parcela"])) in pagas_gcp:
            puladas_pagas += 1
            continue
        adm, prod = info.get(gc, ("—", "—"))
        regs.append({
            "ym": p["dt"].strftime("%Y-%m"), "cliente": p["Cliente"], "gc": gc,
            "admin": adm, "produto": prod, "vendedor": p["Vendedor"],
            "parcela": p["Parcela"], "data": p["dt"].strftime("%d/%m/%Y"),
            "bruto": parse_float_safe(p["Comissão (Bruta)"]),
            "liquido": parse_float_safe(p["Comissão (s/ Imposto)"]),
            "breno": parse_float_safe(p["Breno"]), "uriel": parse_float_safe(p["Uriel"]),
            "atrasada": bool(p["dt"] < hoje),
        })
    if puladas_pagas:
        avisos.append(f"{puladas_pagas} parcela(s) já paga(s) sob outra grafia do nome "
                      f"do cliente foram excluídas da previsão.")
    return pd.DataFrame(regs, columns=colunas), avisos
