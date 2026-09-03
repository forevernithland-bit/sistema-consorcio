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
import base64
import datetime

import streamlit as st
import streamlit.components.v1 as components


def _logo_data_uri(pasta_atual):
    """logo.png da raiz do projeto (a mesma logo Consorbens da sidebar do ERP)
    convertida em data URI base64, pra renderizar offline dentro do iframe."""
    caminho = os.path.join(pasta_atual, "logo.png")
    try:
        with open(caminho, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return "data:image/png;base64," + b64
    except Exception:
        return ""


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


_TIPOS_BEM = ["Auto", "Moto", "Imóvel", "Caminhão"]


def _quem():
    try:
        return "manual: " + str(st.session_state.get("usuario_logado") or "n/d")
    except Exception:
        return "manual"


def _parse_lista_pct(txt):
    """'25' -> [25] · '25, 35' -> [25,35] · '' -> None"""
    nums = [int(n) for n in _re_nums(txt)]
    return nums or None


def _re_nums(txt):
    import re
    return re.findall(r"\d+", str(txt or ""))


def _agora_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _form_editar_grupo(supabase, grupos):
    st.markdown("#### ➕ Adicionar / editar grupo")
    st.caption("Cadastre um grupo que não veio do robô, ou corrija os dados de "
               "um já existente. Fica salvo com a data de hoje e `fonte = manual`.")

    opcoes = ["— novo grupo —"] + [f"{g['grupo']} · {g.get('tipo_bem','?')}" for g in grupos]
    escolha = st.selectbox("Grupo", opcoes, key="ygrp_sel")
    atual = {}
    if escolha != "— novo grupo —":
        gsel = escolha.split(" · ")[0]
        atual = next((g for g in grupos if str(g["grupo"]) == gsel), {})

    with st.form("form_grupo_yamaha", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        grupo = c1.text_input("Nº do grupo *", value=str(atual.get("grupo", "")))
        tipo_bem = c2.selectbox(
            "Produto *", _TIPOS_BEM,
            index=_TIPOS_BEM.index(atual["tipo_bem"]) if atual.get("tipo_bem") in _TIPOS_BEM else 0)
        plano_codigo = c3.text_input("Plano (código)", value=str(atual.get("plano_codigo") or ""))

        c1, c2, c3 = st.columns(3)
        credito = c1.number_input("Crédito (R$)", min_value=0.0, step=1000.0,
                                  value=float(atual.get("credito") or 0))
        taxa = c2.number_input("Taxa de adm. (%)", min_value=0.0, step=0.1,
                               value=float(atual.get("taxa") or 0))
        vagas = c3.number_input("Vagas", min_value=0, step=1, value=int(atual.get("vagas") or 0))

        c1, c2, c3 = st.columns(3)
        prazo_restante = c1.number_input("Prazo restante (meses)", min_value=0, step=1,
                                         value=int(atual.get("prazo_restante") or 0))
        prazo_total = c2.number_input("Prazo total do grupo (meses)", min_value=0, step=1,
                                      value=int(atual.get("prazo_total") or 0))
        parcela = c3.number_input("Parcela base (R$)", min_value=0.0, step=10.0,
                                  value=float(atual.get("parcela") or 0))

        c1, c2, c3 = st.columns(3)
        prox_assembleia = c1.text_input("Próxima assembleia (DD/MM/AAAA)",
                                        value=str(atual.get("prox_assembleia") or ""))
        lance_medio = c2.number_input("Lance livre médio (%)", min_value=0.0, step=0.5,
                                      value=float(atual.get("lance_medio") or 0))
        bem = c3.text_input("Bem / descrição", value=str(atual.get("bem") or ""))

        c1, c2, c3 = st.columns(3)
        parcela_reduzida = c1.checkbox("É Parcela Reduzida?",
                                       value=bool(atual.get("parcela_reduzida")))
        embutido_max = c2.number_input("Lance embutido máx. (%)", min_value=0, step=1,
                                       value=int(atual.get("embutido_max_pct") or 0))
        lance_fixo_txt = c3.text_input("Lance fixo (%) — ex.: 25 ou 25, 35",
                                       value=", ".join(str(x) for x in (atual.get("lance_fixo_pct") or [])))

        salvar = st.form_submit_button("💾 Salvar grupo na base", type="primary")

    if salvar:
        if not grupo.strip():
            st.error("Informe o nº do grupo.")
            return
        payload = {
            "grupo": grupo.strip(), "tipo_bem": tipo_bem,
            "plano_codigo": plano_codigo.strip() or None,
            "bem": bem.strip() or None,
            "credito": credito or None, "taxa": taxa or None,
            "vagas": int(vagas), "parcela": parcela or None,
            "prazo_restante": int(prazo_restante) or None,
            "prazo_total": int(prazo_total) or None,
            "prox_assembleia": prox_assembleia.strip() or None,
            "lance_medio": lance_medio or None,
            "parcela_reduzida": bool(parcela_reduzida),
            "embutido_max_pct": int(embutido_max) or None,
            "lance_fixo_pct": _parse_lista_pct(lance_fixo_txt),
            "fonte": "manual",
            "consultado_em": _agora_iso(),
            "atualizado_em": _agora_iso(),
            "atualizado_por": _quem(),
        }
        try:
            supabase.table("grupos_yamaha").upsert(
                payload, on_conflict="grupo,tipo_bem").execute()
            st.success(f"Grupo {grupo} salvo ({payload['atualizado_por']}, "
                       f"{datetime.datetime.now():%d/%m/%Y %H:%M}).")
            st.rerun()
        except Exception as e:
            st.error(f"Não consegui gravar: {e}")


def _form_lancar_assembleia(supabase, grupos):
    st.markdown("#### ➕ Lançar resultado de assembleia (manual)")
    st.caption("Use quando o robô não coletou. A média de lance livre por grupo "
               "(view) se recalcula sozinha.")

    with st.form("form_assemb_yamaha", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        grupo = c1.text_input("Nº do grupo *")
        tipo_bem = c2.selectbox("Produto", _TIPOS_BEM, key="yass_tipo")
        num_ass = c3.number_input("Nº da assembleia *", min_value=1, step=1)

        c1, c2, c3 = st.columns(3)
        data_ass = c1.date_input("Data da assembleia *", value=datetime.date.today())
        n_total = c2.number_input("Total de contemplados", min_value=0, step=1)
        n_sorteio = c3.number_input("Por sorteio", min_value=0, step=1)

        c1, c2, c3 = st.columns(3)
        n_livre = c1.number_input("Por lance livre", min_value=0, step=1)
        n_fixo = c2.number_input("Por lance fixo", min_value=0, step=1)
        ll_med = c3.number_input("Lance livre — média (%)", min_value=0.0, step=0.5)

        c1, c2, c3 = st.columns(3)
        ll_min = c1.number_input("Lance livre — mínimo (%)", min_value=0.0, step=0.5)
        ll_max = c2.number_input("Lance livre — máximo (%)", min_value=0.0, step=0.5)
        lf_med = c3.number_input("Lance fixo — média (%)", min_value=0.0, step=0.5)

        salvar = st.form_submit_button("💾 Salvar assembleia", type="primary")

    if salvar:
        if not grupo.strip():
            st.error("Informe o nº do grupo.")
            return
        mods = []
        if n_sorteio: mods.append("Sorteio")
        if n_livre: mods.append("Lance Livre")
        if n_fixo: mods.append("Lance Fixo")
        payload = {
            "grupo": grupo.strip(), "tipo_bem": tipo_bem,
            "num_assembleia": int(num_ass),
            "data_assembleia": data_ass.isoformat(),
            "mes_competencia": data_ass.strftime("%Y-%m"),
            "n_total": int(n_total), "n_sorteio": int(n_sorteio),
            "n_lance_livre": int(n_livre), "n_lance_fixo": int(n_fixo),
            "lance_livre_medio": ll_med or None,
            "lance_livre_min": ll_min or None, "lance_livre_max": ll_max or None,
            "lance_fixo_medio": lf_med or None,
            "lance_medio": ll_med or lf_med or None,
            "modalidades_vistas": mods or None,
            "atualizado_em": _agora_iso(),
            "atualizado_por": _quem(),
        }
        try:
            supabase.table("yamaha_assembleias").upsert(
                payload, on_conflict="grupo,num_assembleia").execute()
            st.success(f"Assembleia {int(num_ass)} do grupo {grupo} salva "
                       f"({datetime.datetime.now():%d/%m/%Y %H:%M}).")
            st.rerun()
        except Exception as e:
            st.error(f"Não consegui gravar: {e}")


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

    # logo Consorbens (base64) — troca o marcador "__LOGO_CONSORBENS__"
    logo_uri = _logo_data_uri(pasta_atual)
    if logo_uri:
        if "__LOGO_CONSORBENS__" in html_code:
            html_code = html_code.replace("__LOGO_CONSORBENS__", logo_uri)
        else:
            html_code = html_code.replace(
                "</head>",
                f'<script>window.LOGO_CONSORBENS={json.dumps(logo_uri)};</script></head>',
                1,
            )

    # 1600 cobre a aba Simulador; a aba "Estruturada" (várias linhas + relatório
    # + fluxo) é mais alta — scrolling=True cobre o resto, mas dá um respiro.
    components.html(html_code, height=1900, scrolling=True)

    # ---- edição manual da Base de Dados (sem robô) ----
    st.divider()
    with st.expander("✍️ Editar a Base de Dados manualmente (sem robô)"):
        st.info("Cadastre/edite grupo ou lance o resultado de uma assembleia à "
                "mão. Tudo fica com a data de hoje e marcado como manual. "
                "Depois de salvar, a página recarrega e o simulador já usa o "
                "dado novo.")
        aba_g, aba_a = st.tabs(["Grupo", "Resultado de assembleia"])
        with aba_g:
            _form_editar_grupo(supabase, dados.get("grupos") or [])
        with aba_a:
            _form_lancar_assembleia(supabase, dados.get("grupos") or [])
