import hashlib
import re
import unicodedata
import urllib.parse
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
from utils import listar_arquivos_drive
from escopo import eh_master

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


def _grupos_repetidos(arquivos):
    """Arquivos de mesmo conteúdo (mesmo md5 do Drive) já guardados no portal: [[f, f, ...], ...]."""
    por_md5 = {}
    for f in arquivos:
        if f.get("md5Checksum"):
            por_md5.setdefault(f["md5Checksum"], []).append(f)
    return [g for g in por_md5.values() if len(g) > 1]


def _analisar_envio(novos, arquivos):
    """Para cada arquivo escolhido: 'novo', 'identico' (mesmo conteúdo) ou 'mesmo_nome'."""
    md5_exist = {f["md5Checksum"]: f["name"] for f in arquivos if f.get("md5Checksum")}
    nomes_exist = {str(f.get("name", "")).strip().lower(): f["name"] for f in arquivos}
    vistos_md5, vistos_nome, res = {}, {}, []
    for u in novos:
        dados = u.getvalue()
        h = hashlib.md5(dados).hexdigest()
        nome = u.name
        if h in md5_exist:
            res.append((u, dados, "identico", f"já existe com o mesmo conteúdo: {md5_exist[h]}"))
        elif h in vistos_md5:
            res.append((u, dados, "identico", f"repetido na seleção (igual a {vistos_md5[h]})"))
        elif nome.strip().lower() in nomes_exist or nome.strip().lower() in vistos_nome:
            res.append((u, dados, "mesmo_nome", "já existe um arquivo com este nome (conteúdo diferente)"))
        else:
            res.append((u, dados, "novo", "novo"))
        vistos_md5.setdefault(h, nome)
        vistos_nome.setdefault(nome.strip().lower(), nome)
    return res


BUCKET = "midias"


def _midias_enviadas(supabase):
    """Arquivos enviados pelo Master (Supabase Storage), no mesmo formato dos arquivos do Drive.
    Devolve (lista, tabela_ok). tabela_ok=False => falta rodar a migração 28."""
    try:
        rows = supabase.table("midias").select("*").order("criado_em", desc=True).limit(2000).execute().data or []
    except Exception:
        return [], False
    out = []
    for r in rows:
        url = supabase.storage.from_(BUCKET).get_public_url(r["caminho"])
        mime = r.get("mime") or ""
        out.append({
            "id": f"up_{r['id']}", "name": r["nome"], "mimeType": mime,
            "webViewLink": url, "webContentLink": url + ("&" if "?" in url else "?") + "download=" + urllib.parse.quote(r["nome"]),
            "thumbnailLink": url if mime.startswith("image/") else None,
            "size": r.get("tamanho"), "modifiedTime": r.get("criado_em"), "md5Checksum": r.get("md5"),
        })
    for f in out:
        if not f["thumbnailLink"]:
            f.pop("thumbnailLink")
    return out, True


def _nome_seguro(nome):
    t = unicodedata.normalize("NFD", nome)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", t).strip("._") or "arquivo"


def _enviar_midias(supabase, arquivos, tabela_ok):
    """Só Master: arrastar e soltar arquivos, avisando os repetidos."""
    with st.expander("⬆️ Enviar arquivos para o portal (arrastar e soltar)", expanded=False):
        if not tabela_ok:
            st.warning("O envio ainda não foi ativado. Rode uma vez o arquivo "
                       "`migracoes/28_midias_envio.sql` no SQL Editor do Supabase.")
            return
        gen = st.session_state.get("midias_up_gen", 0)
        novos = st.file_uploader("Arraste aqui as imagens, vídeos e documentos (até 50 MB cada)",
                                 accept_multiple_files=True, key=f"midias_up_{gen}")
        if not novos:
            return
        analise = _analisar_envio(novos, arquivos)
        reps = [a for a in analise if a[2] != "novo"]
        if reps:
            st.warning(f"⚠️ {len(reps)} de {len(analise)} arquivo(s) parecem repetidos:")
            for u, _, tipo, msg in reps:
                st.markdown(f"- **{u.name}** — {msg}")
        enviar_rep = st.checkbox("Enviar também os repetidos", value=False, key=f"midias_rep_{gen}") if reps else False
        a_enviar = [a for a in analise if a[2] == "novo" or enviar_rep]
        if st.button(f"Enviar {len(a_enviar)} arquivo(s)", type="primary", disabled=not a_enviar, key=f"midias_go_{gen}"):
            falhas = 0
            quem = st.session_state.get("nome_vendedor") or st.session_state.get("usuario_logado")
            with st.spinner("Enviando..."):
                for u, dados, _, _ in a_enviar:
                    caminho = f"{uuid.uuid4().hex[:12]}/{_nome_seguro(u.name)}"
                    try:
                        supabase.storage.from_(BUCKET).upload(caminho, dados, {"content-type": u.type or "application/octet-stream"})
                        supabase.table("midias").insert({
                            "nome": u.name, "mime": u.type, "tamanho": len(dados),
                            "md5": hashlib.md5(dados).hexdigest(), "caminho": caminho, "enviado_por": quem}).execute()
                    except Exception as e:
                        falhas += 1
                        st.error(f"❌ {u.name}: {str(e)[:140]}")
            if falhas < len(a_enviar):
                st.session_state["midias_aviso"] = f"✅ {len(a_enviar) - falhas} arquivo(s) enviado(s)." + (
                    f" {falhas} falharam." if falhas else "")
                st.session_state["midias_up_gen"] = gen + 1
                st.rerun()


def render_midias(supabase):
    from modulos.tema import cabecalho; cabecalho("Portal de Mídias (Google Drive)", "🖼️", "Cards, tabelas, vídeos e apresentações prontos para enviar ao cliente.", eyebrow="Ferramentas")

    drive_ok = "gcp_service_account" in st.secrets and "DRIVE_FOLDER_IDS" in st.secrets
    arquivos = []
    if drive_ok:
        with st.spinner("Buscando arquivos..."):
            arquivos = list(listar_arquivos_drive(st.secrets.get("DRIVE_FOLDER_IDS", [])))
    enviados, tabela_ok = _midias_enviadas(supabase)
    arquivos += enviados

    master = eh_master()
    if master:
        if st.session_state.get("midias_aviso"):
            st.success(st.session_state.pop("midias_aviso"))
        _enviar_midias(supabase, arquivos, tabela_ok)

    if not arquivos:
        st.info("Nenhum arquivo encontrado." if drive_ok else
                "⚠️ O acesso ao Google Drive ainda não está configurado nos Secrets e nenhum arquivo foi enviado.")
        return

    if master:
        reps_lib = _grupos_repetidos(arquivos)
        if reps_lib:
            with st.expander(f"⚠️ {len(reps_lib)} grupo(s) de arquivos repetidos no portal"):
                st.caption("Mesmo conteúdo guardado mais de uma vez. Apague as cópias que não precisa mais.")
                for g in reps_lib:
                    st.markdown("- " + " · ".join(f"`{f['name']}`" for f in g))

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
