"""
Simulador Yamaha + aba "Base de Dados".

A lógica de cálculo do simulador vive no yamaha.html e NÃO é tocada aqui.
Este módulo só:
  1) lê as tabelas que o robô do escritório alimenta (planos_yamaha,
     grupos_yamaha, yamaha_assembleias, yamaha_grupo_lance_resumo);
  2) injeta esses dados como JSON dentro do HTML (placeholder
     /*__BASE_DADOS__*/), pra aba "Base de Dados" renderizar tudo já
     atualizado, com a data da última coleta em evidência.
"""
import os
import json
import datetime

import streamlit as st
import streamlit.components.v1 as components


def _rows(supabase, tabela, colunas="*", ordem=None, desc=False):
    try:
        q = supabase.table(tabela).select(colunas)
        if ordem:
            q = q.order(ordem, desc=desc)
        return q.execute().data or []
    except Exception as e:
        st.warning(f"Não consegui ler `{tabela}`: {e}")
        return []


def _max_ts(rows, *campos):
    """Maior timestamp (ISO string) entre os campos dados, ou None."""
    vals = []
    for r in rows:
        for c in campos:
            v = r.get(c)
            if v:
                vals.append(str(v))
    return max(vals) if vals else None


def carregar_base_yamaha(supabase):
    planos = _rows(supabase, "planos_yamaha", ordem="codigo")
    grupos = _rows(supabase, "grupos_yamaha", ordem="grupo")
    assembleias = _rows(supabase, "yamaha_assembleias", ordem="data_assembleia", desc=True)
    resumo = _rows(supabase, "yamaha_grupo_lance_resumo", ordem="grupo")

    att = {
        "planos": _max_ts(planos, "consultado_em"),
        "grupos": _max_ts(grupos, "consultado_em"),
        "assembleias": _max_ts(assembleias, "atualizado_em"),
    }
    att["geral"] = _max_ts(
        [{"x": v} for v in att.values() if v], "x"
    )

    return {
        "planos": planos,
        "grupos": grupos,
        "assembleias": assembleias,
        "resumo": resumo,
        "atualizacao": att,
        "gerado_em": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "contagem": {
            "planos": len(planos),
            "faixas": sum(len(p.get("creditos") or []) for p in planos),
            "grupos": len(grupos),
            "assembleias": len(assembleias),
        },
    }


def render_yamaha_sim(supabase, pasta_atual):
    caminho = os.path.join(pasta_atual, "yamaha.html")
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            html_code = f.read()
    except FileNotFoundError:
        st.error("⚠️ yamaha.html não encontrado no servidor.")
        return

    dados = carregar_base_yamaha(supabase)
    payload = json.dumps(dados, ensure_ascii=False, default=str)

    # troca o objeto-marcador do HTML pelo JSON real (fallback: injeta no <head>)
    marcador = '{"__BASE_DADOS__":true,"planos":[],"grupos":[],"assembleias":[],"resumo":[],"atualizacao":{},"contagem":{}}'
    if marcador in html_code:
        html_code = html_code.replace(marcador, payload, 1)
    else:
        html_code = html_code.replace(
            "</head>", f"<script>window.BASE_DADOS={payload};</script></head>", 1
        )

    components.html(html_code, height=1200, scrolling=True)
