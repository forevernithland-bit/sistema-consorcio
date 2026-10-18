import re
from datetime import datetime

import pandas as pd
import streamlit as st
from utils import listar_arquivos_drive

# Ordem em que os tipos aparecem (tudo já vem organizado por tipo, para todos os usuários)
TIPOS = ["📁 Pastas", "🖼️ Imagens", "🎬 Vídeos", "📄 Documentos", "📦 Outros"]
VISOES = ["📋 Lista + prévia", "🖼️ Grade", "📑 Tabela"]   # a primeira é a padrão

_DOCS = ("pdf", "word", "document", "sheet", "excel", "presentation", "powerpoint", "text", "csv", "msword")


def _tipo(f):
    m = (f.get("mimeType") or "").lower()
    if m == "application/vnd.google-apps.folder":
        return TIPOS[0]
    if m.startswith("image/"):
        return TIPOS[1]
    if m.startswith("video/"):
        return TIPOS[2]
    if any(k in m for k in _DOCS):
        return TIPOS[3]
    return TIPOS[4]


def _tamanho(f):
    try:
        n = float(f.get("size"))
    except (TypeError, ValueError):
        return ""
    for un in ("B", "KB", "MB", "GB"):
        if n < 1024 or un == "GB":
            return f"{n:.0f} {un}" if un == "B" else f"{n:.1f} {un}"
        n /= 1024


def _data(f):
    try:
        return datetime.fromisoformat(str(f.get("modifiedTime")).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except Exception:
        return ""


def _miniatura(f, grande=False):
    link = f.get("thumbnailLink")
    if not link:
        return None
    return re.sub(r"=s\d+$", "=s900" if grande else "=s400", link)


def _botao(f, key):
    if "webContentLink" in f:
        st.link_button("📥 Baixar", f["webContentLink"], use_container_width=True, key=key)
    elif "webViewLink" in f:
        st.link_button("👁️ Abrir", f["webViewLink"], use_container_width=True, key=key)


def _previa(f):
    """Painel da direita: imagem grande (ou ícone) + dados + botões."""
    st.markdown(f"**{f['name']}**")
    img = _miniatura(f, grande=True)
    if img:
        st.markdown(f"<img src='{img}' style='max-width:100%;max-height:520px;border-radius:12px'>",
                    unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='font-size:64px;text-align:center;padding:40px 0'>{f['_tipo'].split()[0]}</div>",
                    unsafe_allow_html=True)
    st.caption(" · ".join(x for x in (f["_tipo"], f["_tam"], f["_data"]) if x))
    _botao(f, "midia_previa_btn")
    if "webViewLink" in f and "webContentLink" in f:
        st.link_button("👁️ Abrir no Drive", f["webViewLink"], use_container_width=True, key="midia_previa_abrir")


def _grade(arqs):
    cols = st.columns(4)
    for i, f in enumerate(arqs):
        with cols[i % 4]:
            st.markdown("<div class='media-card'>", unsafe_allow_html=True)
            img = _miniatura(f)
            if img:
                st.markdown(f"<img src='{img}' class='media-img'>", unsafe_allow_html=True)
            else:
                st.markdown(f"{f['_tipo'].split()[0]} *{f['_tipo'].split(' ', 1)[1]}*")
            st.markdown(f"<div class='media-title'>{f['name']}</div>", unsafe_allow_html=True)
            _botao(f, f"midia_g_{i}")
            st.markdown("</div>", unsafe_allow_html=True)


def _tabela_df(arqs):
    return pd.DataFrame({
        "Tipo": [f["_tipo"] for f in arqs],
        "Nome": [f["name"] for f in arqs],
        "Modificado": [f["_data"] for f in arqs],
        "Tamanho": [f["_tam"] for f in arqs],
    })


def render_midias():
    st.markdown("### 🖼️ Portal de Mídias (Google Drive)")

    if "gcp_service_account" not in st.secrets or "DRIVE_FOLDER_IDS" not in st.secrets:
        st.warning("⚠️ O sistema ainda não possui a configuração de acesso ao Google Drive nos Secrets.")
        return

    folder_ids = st.secrets.get("DRIVE_FOLDER_IDS", [])
    with st.spinner("Buscando arquivos..."):
        arquivos = listar_arquivos_drive(folder_ids)

    if not arquivos:
        st.info("Nenhum arquivo encontrado nas pastas configuradas.")
        return

    arquivos = [dict(f, _tipo=_tipo(f), _tam=_tamanho(f), _data=_data(f)) for f in arquivos]
    # organizado por TIPO e, dentro do tipo, por nome
    arquivos.sort(key=lambda f: (TIPOS.index(f["_tipo"]), str(f.get("name", "")).lower()))

    c1, c2 = st.columns([3, 2], gap="large", vertical_alignment="bottom")
    with c1:
        visao = st.segmented_control("Visualização", VISOES, default=VISOES[0], key="midias_visao") or VISOES[0]
    with c2:
        busca = st.text_input("🔍 Buscar pelo nome", key="midias_busca", placeholder="Digite parte do nome…")
    presentes = [t for t in TIPOS if any(f["_tipo"] == t for f in arquivos)]
    st.write("")
    tipos_sel = st.pills("Tipo", presentes, selection_mode="multi", default=presentes, key="midias_tipos") or []
    st.write("")

    vis = [f for f in arquivos if f["_tipo"] in tipos_sel
           and (not busca.strip() or busca.strip().lower() in str(f.get("name", "")).lower())]
    resumo = " · ".join(f"{t} {sum(1 for f in vis if f['_tipo'] == t)}" for t in TIPOS
                        if any(f["_tipo"] == t for f in vis))
    st.caption(f"{len(vis)} de {len(arquivos)} arquivos" + (f"  —  {resumo}" if resumo else ""))
    if not vis:
        st.info("Nenhum arquivo com esse filtro.")
        return

    if visao == VISOES[1]:
        _grade(vis)
    elif visao == VISOES[2]:
        st.dataframe(_tabela_df(vis), use_container_width=True, hide_index=True)
    else:
        esq, dir_ = st.columns([1.1, 1])
        with esq:
            sel = st.dataframe(_tabela_df(vis), use_container_width=True, hide_index=True, height=560,
                               on_select="rerun", selection_mode="single-row", key="midias_lista")
            linhas = sel.selection.rows if hasattr(sel, "selection") else []
        idx = linhas[0] if linhas and linhas[0] < len(vis) else 0     # sem clique: mostra o primeiro
        with dir_:
            _previa(vis[idx])
