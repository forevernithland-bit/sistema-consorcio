"""Integração ERP ← SITE (cartas contempladas).

O SITE (consorbensmg.com.br/admin) tem seu PRÓPRIO Supabase, onde ficam as
operações de carta contemplada (tabelas vendas/clientes/venda_cotas/pagamentos).
Aqui o ERP LÊ essas operações (só leitura) e normaliza num DataFrame usado pelo
Dashboard e pelo Financeiro. Nada é gravado no Site.

Requer os secrets SITE_SUPABASE_URL / SITE_SUPABASE_KEY no ERP. Sem eles, a
integração fica desligada (retorna DataFrame vazio) e o ERP funciona normal.

Ágio da operação = valor_total − valor_cedente − outros_custos + lucro_ajuste
(mesma fórmula do 'lucroFinal' do painel de operações do Site).

Divisão do ágio entre os sócios = coluna vendas.vendedor_comissao do Site
(migração sql/16_divisao_comissao.sql do Site, regra do Breno de 17/11/2026):
  consorbens -> 50% Breno / 50% Uriel   (padrão; também se a coluna não existir)
  breno      -> 70% Breno / 30% Uriel   (Vendedor Breno)
  uriel      -> 30% Breno / 70% Uriel   (Vendedor Uriel)
É a mesma proporção usada nas comissões das administradoras (regras.py /
importar_comissoes.dividir_socios). O Site usa a mesma tabela (operacoes.js).
"""
import pandas as pd
import streamlit as st
from utils import parse_float_safe
from database import iniciar_conexao_site

STATUS_LABEL = {
    "em_analise": "Em análise",
    "concluido": "Concluído",
    "nao_aprovado": "Não aprovado",
    "cancelado": "Cancelado",
}

# vendedor_comissao -> (rótulo, % Breno, % Uriel)
DIVISAO_SITE = {
    "consorbens": ("Consorbens", 50.0, 50.0),
    "breno": ("Vendedor Breno", 70.0, 30.0),
    "uriel": ("Vendedor Uriel", 30.0, 70.0),
}


def dividir_agio_site(agio, vendedor_comissao):
    """Ágio de carta contemplada -> (rótulo, parte Breno, parte Uriel)."""
    rot, pb, pu = DIVISAO_SITE.get((vendedor_comissao or "consorbens").strip().lower(),
                                   DIVISAO_SITE["consorbens"])
    return rot, round(agio * pb / 100.0, 2), round(agio * pu / 100.0, 2)


def _ym(data_str):
    """Data ISO/br -> 'AAAA-MM' (None se inválida)."""
    if not data_str:
        return None
    try:
        d = pd.to_datetime(str(data_str)[:10], errors="coerce")
        return None if pd.isna(d) else d.strftime("%Y-%m")
    except Exception:
        return None


@st.cache_data(ttl=120, show_spinner=False)
def carregar_operacoes_site():
    """Lê as operações do Site e devolve um DataFrame normalizado (uma linha por
    operação/venda). Cache de 2 min para não bater no banco a cada rerun.
    DataFrame vazio se a integração não estiver configurada ou der erro."""
    sb = iniciar_conexao_site()
    if sb is None:
        return pd.DataFrame()
    try:
        rows = sb.table("vendas").select("*, clientes(nome), venda_cotas(*)").execute().data or []
    except Exception:
        return pd.DataFrame()

    regs = []
    for v in rows:
        status = (v.get("status") or "em_analise").strip()
        cotas = v.get("venda_cotas") or []
        tipos = [c.get("tipo") for c in cotas if c.get("tipo")]
        admins = [c.get("administradora") for c in cotas if c.get("administradora")]
        credito_total = sum(parse_float_safe(c.get("valor_carta", 0)) for c in cotas)

        valor_total = parse_float_safe(v.get("valor_total", 0))
        valor_cedente = parse_float_safe(v.get("valor_cedente", 0))
        outros = parse_float_safe(v.get("outros_custos", 0))
        ajuste = parse_float_safe(v.get("lucro_ajuste", 0))
        agio = round(valor_total - valor_cedente - outros + ajuste, 2)
        divisao, breno, uriel = dividir_agio_site(agio, v.get("vendedor_comissao"))

        data_venda = v.get("data_venda") or ""
        data_conclusao = v.get("data_conclusao") or ""
        # mês do REALIZADO só existe para concluído (conclusão, ou venda como reserva)
        ym = _ym(data_conclusao or data_venda) if status == "concluido" else None

        regs.append({
            "id": v.get("id"),
            "cliente": (v.get("clientes") or {}).get("nome") if isinstance(v.get("clientes"), dict) else None,
            "representante": v.get("representante") or "—",
            "status": status,
            "status_label": STATUS_LABEL.get(status, status),
            "produto": " / ".join(sorted(set(tipos))) if tipos else "—",
            "administradora": admins[0] if admins else "—",
            "credito_total": credito_total,
            "valor_total": valor_total,
            "valor_cedente": valor_cedente,
            "agio": agio,
            "divisao": divisao,
            "breno": breno,
            "uriel": uriel,
            "data_venda": str(data_venda)[:10],
            "data_conclusao": str(data_conclusao)[:10],
            "ym": ym,
            "n_cotas": len(cotas),
            "grupo_cota": ", ".join(f"{c.get('grupo') or '—'}/{c.get('cota') or '—'}" for c in cotas
                                    if c.get('grupo') or c.get('cota')) or "—",
        })

    df = pd.DataFrame(regs)
    if not df.empty:
        df["cliente"] = df["cliente"].fillna("(sem cliente)")
    return df
