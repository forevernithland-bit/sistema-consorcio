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
            if p_val <= 0: continue
            
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
            status_pagamento = status_dict.get(chave_unica, "Pendente")
            
            data_str = p['data_pagamento'].strftime("%d/%m/%Y")
            if status_cota == 'Em Atraso': data_str = "⚠️ Travada (Atraso)"
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
                "Data Prevista": data_str
            })
            
    return pd.DataFrame(parcelas_finais), vendas_sem_data
