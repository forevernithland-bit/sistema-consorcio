import pandas as pd
from utils import parse_float_safe, normalizar_string, normalizar_produto

def calcular_comissao_vendedor(df_vendas_global, vendedor_nome, data_venda_dt, cfg):
    """Calcula a taxa e a quantidade de parcelas que o vendedor tem direito com base no volume do mês"""
    if pd.isna(data_venda_dt): return cfg.get('T1_Pct', 1.0), int(cfg.get('T1_Parc', 4))
    
    mes = data_venda_dt.month
    ano = data_venda_dt.year
    df_mes = df_vendas_global[(df_vendas_global['VENDEDOR'] == vendedor_nome) &
                              (df_vendas_global['Data_Real'].dt.month == mes) &
                              (df_vendas_global['Data_Real'].dt.year == ano)]
    vol_total = df_mes['Valor_Numerico'].sum()

    if vol_total <= cfg.get('T1_Max', 500000): 
        return cfg.get('T1_Pct', 1.0), int(cfg.get('T1_Parc', 4))
    elif vol_total <= cfg.get('T2_Max', 1500000): 
        return cfg.get('T2_Pct', 1.5), int(cfg.get('T2_Parc', 5))
    else: 
        return cfg.get('T3_Pct', 2.0), int(cfg.get('T3_Parc', 5))

def gerar_tabela_parcelas(df_alvo, df_global, df_regras, cfg, status_dict):
    """Gera a tabela completa de previsão de comissionamento e parcelas"""
    hoje = pd.Timestamp.today().normalize()
    parcelas_finais = []
    vendas_sem_data = [] 
    
    for idx, r in df_alvo.iterrows():
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
        
        regra = df_regras[(df_regras['Admin_Norm'] == admin_norm) & (df_regras['Prod_Norm'] == prod_norm)]
        if regra.empty: continue
        regra = regra.iloc[0]
        
        tier_pct, tier_parc = calcular_comissao_vendedor(df_global, vendedor, data_venda, cfg)
        temp_parcels = []
        
        for i in range(1, 26):
            p_val = parse_float_safe(regra.get(f"P{i}", 0)) / 100.0
            # `not (p_val > 0)` cobre 0, negativo E NaN (célula vazia na regra).
            # Sem isso a cota gerava as 25 parcelas, e as não definidas pela
            # administradora vinham com comissão NaN.
            if not (p_val > 0): continue
            
            comissao_bruta = val_venda * p_val
            imposto_val = comissao_bruta * (parse_float_safe(cfg.get('Imposto', 7.16)) / 100.0)
            corretora_liq = comissao_bruta - imposto_val
            
            vend_rec = 0.0
            breno_rec = 0.0
            uriel_rec = 0.0
            
            # Divisão societária e de vendedores
            if vendedor == "BRENO LIMA":
                breno_rec = corretora_liq * (parse_float_safe(cfg.get('Breno_Breno', 70))/100.0)
                uriel_rec = corretora_liq * (parse_float_safe(cfg.get('Breno_Uriel', 30))/100.0)
            elif vendedor == "URIEL GOMES":
                uriel_rec = corretora_liq * (parse_float_safe(cfg.get('Uriel_Uriel', 70))/100.0)
                breno_rec = corretora_liq * (parse_float_safe(cfg.get('Uriel_Breno', 30))/100.0)
            elif vendedor == "Consorbens":
                breno_rec = corretora_liq * (parse_float_safe(cfg.get('Cons_Breno', 50))/100.0)
                uriel_rec = corretora_liq * (parse_float_safe(cfg.get('Cons_Uriel', 50))/100.0)
            elif vendedor == "Particular Breno":
                breno_rec = corretora_liq  # 100% Breno
                uriel_rec = 0.0
            elif vendedor == "Particular Uriel":
                uriel_rec = corretora_liq  # 100% Uriel
                breno_rec = 0.0
            else:
                if i <= tier_parc: vend_rec = val_venda * (tier_pct/100.0) / tier_parc
                sobra = corretora_liq - vend_rec
                breno_rec = sobra * 0.50
                uriel_rec = sobra * 0.50

            data_pagamento = data_venda + pd.Timedelta(days=7) + pd.DateOffset(months=i-1)
            temp_parcels.append({
                'parcela': i, 'data_pagamento': data_pagamento, 'bruto': comissao_bruta,
                'liquido': corretora_liq, 'vend': vend_rec, 'breno': breno_rec, 'uriel': uriel_rec
            })
            
        # Lógica de cotas Canceladas e Contempladas
        if status_cota == 'Cancelada':
            temp_parcels = [p for p in temp_parcels if p['data_pagamento'] <= hoje]
        elif status_cota == 'Contemplada':
            past = [p for p in temp_parcels if p['data_pagamento'] <= hoje]
            future = [p for p in temp_parcels if p['data_pagamento'] > hoje]
            if future:
                past.append({
                    'parcela': 'Antecipação', 'data_pagamento': hoje,
                    'bruto': sum(p['bruto'] for p in future), 'liquido': sum(p['liquido'] for p in future),
                    'vend': sum(p['vend'] for p in future), 'breno': sum(p['breno'] for p in future), 'uriel': sum(p['uriel'] for p in future)
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
            
            # Se tivermos uma data editada manualmente no banco, sobrescrevemos a calculada
            if data_custom and pd.notna(data_custom) and str(data_custom).strip() != "":
                data_str = str(data_custom)
            
            nome_parcela = f"{p['parcela']}ª Parcela" if isinstance(p['parcela'], int) else "Antecip. (Contemplada)"
            
            parcelas_finais.append({
                "Chave": chave_unica,
                "Cliente": cliente,
                "Produto": prod,
                "Vendedor": vendedor,
                "Grupo": grupo,
                "Cota": cota,
                "Valor da Venda": val_venda,
                "Parcela": nome_parcela,
                "data_pagamento_dt": p['data_pagamento'], 
                "Comissão (Bruta)": p['bruto'],
                "Comissão (s/ Imposto)": p['liquido'],
                "Breno": p['breno'],
                "Uriel": p['uriel'],
                "Vendedor Recebe": p['vend'],
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
    vistos = {}
    for _, v in df_vendas.iterrows():
        gc = f"{_gc(v.get('GRUPO'))}/{_gc(v.get('COTA'))}"
        if gc == "/":
            continue          # Consórcio Contemplado não tem grupo/cota
        vistos.setdefault(gc, []).append(v)
    return {k: v for k, v in vistos.items() if len(v) > 1}


def gerar_previsao_pendente(df_vendas, df_admin, cfg, status_dict):
    """Comissões que ainda NÃO entraram, das cotas vivas.

    Fonte única da previsão — Financeiro e Relatórios chamam esta função para
    não divergirem. Regras aplicadas:
      • só cotas com status ativo (STATUS_ATIVOS), pois Cancelada/Contemplada
        não geram parcela futura;
      • cada grupo/cota entra UMA vez (cota cadastrada em duplicidade contaria
        a comissão duas vezes);
      • só parcelas ainda não baixadas (status_comissoes ≠ PAGO);
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

    st_norm = df_vendas["STATUS"].astype(str).str.strip().str.lower()
    ativas = df_vendas[st_norm.isin(STATUS_ATIVOS)].copy()
    if ativas.empty:
        return vazio, avisos

    # uma linha por grupo/cota (a mais recente vence)
    dups = cotas_duplicadas(ativas)
    if dups:
        avisos.append(
            f"{len(dups)} cota(s) cadastrada(s) em duplicidade — contei uma vez só: "
            + ", ".join(sorted(dups)))
        ativas["_gc"] = [f"{_gc(r.get('GRUPO'))}/{_gc(r.get('COTA'))}"
                         for _, r in ativas.iterrows()]
        ativas = ativas.sort_values("Data_Real").drop_duplicates("_gc", keep="last")
        ativas = ativas.drop(columns=["_gc"])

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
    for _, v in ativas.iterrows():
        info[f"{_gc(v.get('GRUPO'))}/{_gc(v.get('COTA'))}"] = (
            str(v.get("ADMINISTRADORA") or "—").strip().upper(),
            normalizar_produto(v.get("PRODUTO")) or "—")

    hoje = pd.Timestamp.today().normalize()
    regs = []
    for _, p in pend.iterrows():
        gc = f"{_gc(p['Grupo'])}/{_gc(p['Cota'])}"
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
    return pd.DataFrame(regs, columns=colunas), avisos
