"""
Regra de comissão do VENDEDOR (terceiro com login no ERP).

Todos os percentuais são sobre o VALOR DA CARTA (crédito) e pagos por POSIÇÃO de
pagamento da cota (1º, 2º, 3º, 4º pagamento de comissão da administradora):

    base ................................. 0,5% no 1º + 0,5% no 2º   (1,00% no total)
    produção do mês  > R$ 500 mil ........ + 0,25% no 3º              (1,25% no total)
    produção do mês  > R$ 1 milhão ....... + 0,25% no 4º              (1,50% no total)
                                           (o nível de 1 milhão inclui o de 500 mil)

Produção do mês = soma do crédito das cotas vendidas pelo vendedor naquele mês
(pela data da venda), de consórcio tradicional; "Consórcio Contemplado" não entra
(a renda dele é o ágio). Cotas canceladas continuam contando: o cancelamento é
tratado pelo estorno, não mexe no nível de quem já vendeu.

Estorno: cota CANCELADA em até 5 meses depois da venda devolve 0,5% do crédito
(limitado ao que o vendedor já tinha ganhado dessa cota até o cancelamento), em 2 parcelas
de 0,25%, abatidas nos PRÓXIMOS 2 pagamentos (meses) em que o vendedor tiver comissão a receber.

Os números podem ser mudados em Configurações (chaves VD_* da config_interna);
sem a chave, vale o padrão abaixo.
"""
import re
import unicodedata

import pandas as pd

REGRA_PADRAO = {
    "VD_P1": 0.5,            # % do crédito no 1º pagamento
    "VD_P2": 0.5,            # % no 2º
    "VD_M1": 500000.0,       # produção do mês ACIMA disso libera o bônus 1
    "VD_M1_P3": 0.25,        # bônus 1: % no 3º pagamento
    "VD_M2": 1000000.0,      # produção do mês ACIMA disso libera o bônus 2
    "VD_M2_P4": 0.25,        # bônus 2 (soma ao bônus 1): % no 4º pagamento
    "VD_EST_PCT": 0.5,       # estorno: % do crédito
    "VD_EST_MESES": 5,       # estorno vale se cancelar em até N meses da venda
    "VD_EST_PARCELAS": 2,    # o estorno é abatido em N parcelas iguais, nos próximos N pagamentos do vendedor
}


def _num(v, padrao):
    try:
        x = float(v)
        return padrao if pd.isna(x) else x
    except (TypeError, ValueError):
        return padrao


def regra(cfg):
    """Regra vigente: padrão + o que estiver na configuração."""
    cfg = cfg or {}
    r = {k: _num(cfg.get(k), v) for k, v in REGRA_PADRAO.items()}
    r["VD_EST_MESES"] = int(r["VD_EST_MESES"])
    r["VD_EST_PARCELAS"] = max(int(r["VD_EST_PARCELAS"]), 1)
    return r


def norm(s):
    t = unicodedata.normalize("NFD", str(s if s is not None else ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.upper().split())


SOCIOS_NORM = {"BRENO LIMA", "URIEL GOMES", "CONSORBENS", "PARTICULAR BRENO", "PARTICULAR URIEL"}


def eh_terceiro(vendedor):
    """Vendedor que recebe comissão de vendedor: não é sócio/corretora e tem nome."""
    n = norm(vendedor)
    return n != "" and n not in SOCIOS_NORM and n not in ("NAN", "NONE")


def _entra_na_producao(df):
    if "TIPO_PRODUTO" not in df.columns:
        return pd.Series(True, index=df.index)
    return df["TIPO_PRODUTO"].apply(norm).str.replace(" ", "") != "CONSORCIOCONTEMPLADO"


def vendas_do_mes(df_vendas, vendedor, ano, mes):
    """Cotas do vendedor vendidas no mês (as que contam para a produção)."""
    if df_vendas is None or df_vendas.empty or "Data_Real" not in df_vendas.columns:
        return pd.DataFrame() if df_vendas is None else df_vendas.iloc[0:0]
    d = df_vendas
    m = (d["VENDEDOR"].apply(norm) == norm(vendedor)) & d["Data_Real"].notna()
    d = d[m]
    d = d[(d["Data_Real"].dt.year == ano) & (d["Data_Real"].dt.month == mes)]
    return d[_entra_na_producao(d)] if not d.empty else d


def _sem_duplicata(d):
    """Mesma cota (grupo/cota) cadastrada duas vezes conta uma vez só na produção."""
    if d.empty or "GRUPO" not in d.columns or "COTA" not in d.columns:
        return d
    gc = d["GRUPO"].astype(str).str.strip().str.lstrip("0") + "/" + d["COTA"].astype(str).str.strip().str.lstrip("0")
    com_gc = gc.str.strip("/") != ""
    dup = gc.duplicated(keep="last") & com_gc
    return d[~dup]


def volume_mes(df_vendas, vendedor, ano, mes):
    d = _sem_duplicata(vendas_do_mes(df_vendas, vendedor, ano, mes))
    return round(float(d["Valor_Numerico"].sum()), 2) if not d.empty else 0.0


def indice_volumes(df_vendas):
    """{(vendedor normalizado, ano, mês): volume} de uma vez só — evita refiltrar o DataFrame a cada cota."""
    idx = {}
    if df_vendas is None or df_vendas.empty or "Data_Real" not in df_vendas.columns:
        return idx
    d = df_vendas[df_vendas["Data_Real"].notna()]
    d = d[_entra_na_producao(d)] if not d.empty else d
    if d.empty:
        return idx
    gc = (d["GRUPO"].astype(str).str.strip().str.lstrip("0") + "/" + d["COTA"].astype(str).str.strip().str.lstrip("0")
          if "GRUPO" in d.columns and "COTA" in d.columns else pd.Series("/", index=d.index))
    d = d.assign(_v=d["VENDEDOR"].map(norm), _a=d["Data_Real"].dt.year, _m=d["Data_Real"].dt.month, _gc=gc.values)
    tem_gc = d["_gc"].str.strip("/") != ""
    dup = d.duplicated(subset=["_v", "_a", "_m", "_gc"], keep="last") & tem_gc      # mesma cota duas vezes = uma
    d = d[~dup]
    soma = d.groupby(["_v", "_a", "_m"])["Valor_Numerico"].sum()
    return {(v, int(a), int(m)): round(float(x), 2) for (v, a, m), x in soma.items()}


def nivel(volume, r):
    """0 = base, 1 = acima de 500 mil, 2 = acima de 1 milhão (estritamente acima)."""
    if volume > r["VD_M2"]:
        return 2
    if volume > r["VD_M1"]:
        return 1
    return 0


def percentuais_por_posicao(volume, cfg):
    """Lista de % do crédito por posição de pagamento: [1º, 2º, (3º), (4º)]."""
    r = regra(cfg)
    lst = [r["VD_P1"], r["VD_P2"]]
    n = nivel(volume, r)
    if n >= 1:
        lst.append(r["VD_M1_P3"])
    if n >= 2:
        lst.append(r["VD_M2_P4"])
    return lst


def percentuais_da_venda(df_vendas, vendedor, data_venda, cfg, indice=None):
    """% por posição que valem para uma venda (depende da produção do mês dela).
    `indice` = indice_volumes(df_vendas) já calculado (rápido); sem ele, calcula direto."""
    if pd.isna(data_venda):
        return percentuais_por_posicao(0.0, cfg)
    if indice is not None:
        vol = indice.get((norm(vendedor), data_venda.year, data_venda.month), 0.0)
    else:
        vol = volume_mes(df_vendas, vendedor, data_venda.year, data_venda.month)
    return percentuais_por_posicao(vol, cfg)


def estorno(valor_carta, data_venda, data_cancel, ganho_ate_cancel, cfg):
    """Valor do estorno (positivo) ou 0. Só vale se cancelou em até N meses da venda."""
    r = regra(cfg)
    if pd.isna(data_venda) or pd.isna(data_cancel):
        return 0.0
    if data_cancel > data_venda + pd.DateOffset(months=r["VD_EST_MESES"]):
        return 0.0
    cheio = float(valor_carta) * r["VD_EST_PCT"] / 100.0
    return round(min(cheio, max(float(ganho_ate_cancel), 0.0)), 2)


def data_cancelamento(v):
    """Lê a DATA_CANCELAMENTO (dd/mm/aaaa ou ISO) -> Timestamp ou NaT."""
    if v is None or str(v).strip() in ("", "None", "nan", "NaT"):
        return pd.NaT
    t = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", t):            # ISO (aaaa-mm-dd): não pode ler como dia/mês
        return pd.to_datetime(t[:10], format="%Y-%m-%d", errors="coerce")
    return pd.to_datetime(v, dayfirst=True, errors="coerce")


def parse_brl(txt, padrao=0.0):
    """'1.000.000' / '1000000' / '1.000.000,50' / 'R$ 500 mil'(não) -> float. Texto inválido -> padrao."""
    t = re.sub(r"[^\d,.\-]", "", str(txt if txt is not None else ""))
    if t in ("", "-"):
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):          # só pontos de milhar
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return padrao
