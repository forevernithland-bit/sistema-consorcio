# -*- coding: utf-8 -*-
"""
Simulador Itaú V 2.0 — módulo do ERP (Streamlit).

Lê a Guia de Oportunidades MAIS RECENTE direto da pasta do Google Drive
(via o mesmo service account que o ERP já usa), converte para JSON e injeta
no itau_v2.html. Sempre reflete a última Guia — sem git push, sem CORS.

Requer:
  - Secret `gcp_service_account` (já existe no ERP)
  - Secret `DRIVE_FOLDER_ITAU` = ID da pasta do Drive onde caem as Guias (Tabelas/ITAU)
    (a pasta precisa estar compartilhada com o e-mail do service account)
  - openpyxl no requirements.txt
"""
import os
import io
import re
import json
import datetime

import streamlit as st
import streamlit.components.v1 as components

from utils import get_drive_service  # reutiliza a autenticação já existente do ERP

# ------------------------------------------------------------------ #
# 1. Descobrir e baixar a Guia mais recente da pasta do Drive
# ------------------------------------------------------------------ #
_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def _mk(ano, mes, dia):
    if ano < 100:
        ano += 2000
    try:
        return datetime.date(ano, mes, dia)
    except (ValueError, TypeError):
        return None


def _data_do_nome(nome):
    """Extrai a data do nome do arquivo (mês por extenso, AAAAMMDD, AAAA-MM-DD, DD-MM-AAAA)."""
    m = re.search(r"(\d{1,2})[-_ .]+(?:de[-_ ]+)?([A-Za-zçÇãÃáàâéêíóôõúÁÉ]{3,})[-_ .]+(?:de[-_ ]+)?(\d{2,4})", nome)
    if m:
        mes = (m.group(2).lower()
               .replace("ç", "c").replace("ã", "a").replace("â", "a").replace("á", "a")
               .replace("à", "a").replace("é", "e").replace("ê", "e").replace("í", "i")
               .replace("ó", "o").replace("ô", "o").replace("õ", "o").replace("ú", "u"))
        if mes in _MESES:
            d = _mk(int(m.group(3)), _MESES[mes], int(m.group(1)))
            if d:
                return d
    for g in re.findall(r"(20\d{2})(\d{2})(\d{2})", nome):
        d = _mk(int(g[0]), int(g[1]), int(g[2]))
        if d:
            return d
    m = re.search(r"(20\d{2})[-_ ./](\d{1,2})[-_ ./](\d{1,2})", nome)
    if m:
        d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            return d
    m = re.search(r"(\d{1,2})[-_ ./](\d{1,2})[-_ ./](\d{2,4})", nome)
    if m:
        d = _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            return d
    return None


def _guia_mais_recente(service, folder_id):
    """Retorna (fileId, nome, modifiedTime) da Guia mais recente da pasta."""
    q = f"'{folder_id}' in parents and trashed=false"
    res = service.files().list(
        q=q, fields="files(id, name, mimeType, modifiedTime)", pageSize=200
    ).execute()
    arquivos = res.get("files", [])
    # só planilhas com "oportunidad" no nome
    guias = [a for a in arquivos
             if "oportunidad" in a["name"].lower()
             and a["name"].lower().endswith((".xlsx", ".xlsm"))
             and not a["name"].startswith("~$")]
    if not guias:
        return None
    guias.sort(key=lambda a: (_data_do_nome(a["name"]) or datetime.date.min,
                              a.get("modifiedTime", "")))
    return guias[-1]


# ------------------------------------------------------------------ #
# 2. Ler a planilha -> JSON (mesma lógica do atualizar_simulador.py)
# ------------------------------------------------------------------ #
def _num(v, d=0):
    try:
        if v is None or v == "":
            return d
        return float(v)
    except (TypeError, ValueError):
        return d


def _parse_guia(xls_bytes, nome_arquivo, modified_iso):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xls_bytes), data_only=True)
    grupos = []
    for aba in wb.sheetnames:
        ws = wb[aba]
        for r in range(3, ws.max_row + 1):
            n = ws.cell(r, 2).value
            if n is None:
                continue
            if str(ws.cell(r, 3).value or "").strip().lower() != "andamento":
                continue
            vagas = int(_num(ws.cell(r, 26).value))
            valores = []
            for x in str(ws.cell(r, 17).value or "").split(","):
                x = x.strip()
                if x:
                    try:
                        valores.append(int(round(float(x))))
                    except ValueError:
                        pass
            valores = sorted(set(valores))
            if not valores:
                continue
            e_raw = str(ws.cell(r, 5).value or "").strip().replace(",", ".")
            try:
                fixo_pct = float(e_raw)
                fixo_ok = fixo_pct > 0
            except ValueError:
                fixo_ok = False
                fixo_pct = None
            grupos.append({
                "grupo": int(n), "aba": aba,
                "prazo": int(_num(ws.cell(r, 11).value)),
                "fundo": _num(ws.cell(r, 14).value),
                "vagas": vagas,
                "fixoOk": fixo_ok, "fixoPct": fixo_pct,
                "valores": valores,
                "lances": [_num(ws.cell(r, 18).value), _num(ws.cell(r, 19).value),
                           _num(ws.cell(r, 22).value), _num(ws.cell(r, 23).value)],
                "contLivre": int(_num(ws.cell(r, 20).value)) + int(_num(ws.cell(r, 24).value)),
            })

    # data "baixado" a partir do nome do arquivo; senão, modifiedTime do Drive
    dt = _data_do_nome(nome_arquivo)
    if dt is None and modified_iso:
        try:
            dt = datetime.datetime.fromisoformat(modified_iso.replace("Z", "+00:00")).date()
        except Exception:
            dt = datetime.date.today()
    baixado = dt.strftime("%d/%m/%y") if dt else datetime.date.today().strftime("%d/%m/%y")

    return {
        "meta": {
            "gerado_em": datetime.date.today().isoformat(),
            "fonte": nome_arquivo,
            "baixado_em": baixado,
            "total": len(grupos),
        },
        "grupos": grupos,
    }


# ------------------------------------------------------------------ #
# 3. Buscar dados (com cache de 5 min) e renderizar
# ------------------------------------------------------------------ #
@st.cache_data(ttl=300, show_spinner=False)
def _carregar_dados_itau():
    folder_id = st.secrets.get("DRIVE_FOLDER_ITAU")
    if not folder_id:
        return None, "Secret DRIVE_FOLDER_ITAU não configurado."
    service = get_drive_service()
    if not service:
        return None, "Service account do Google Drive não configurado (gcp_service_account)."
    guia = _guia_mais_recente(service, folder_id)
    if not guia:
        return None, "Nenhuma Guia de Oportunidades encontrada na pasta do Drive."
    conteudo = service.files().get_media(fileId=guia["id"]).execute()
    dados = _parse_guia(conteudo, guia["name"], guia.get("modifiedTime"))
    return dados, None


def render_itau_v2(pasta_atual):
    """Renderiza o Simulador Itaú V 2.0 com os dados vivos da Guia (Google Drive)."""
    with st.spinner("Carregando a Guia de Oportunidades mais recente…"):
        dados, erro = _carregar_dados_itau()

    if erro:
        st.error(f"⚠️ Não foi possível carregar a Guia: {erro}")
        st.info("Verifique nos Secrets: `gcp_service_account` e `DRIVE_FOLDER_ITAU`, "
                "e se a pasta Tabelas/ITAU está compartilhada com o e-mail do service account.")
        return

    caminho = os.path.join(pasta_atual, "itau_v2.html")
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        st.error("⚠️ O arquivo itau_v2.html não foi encontrado no servidor (verifique se está no GitHub).")
        return

    html = html.replace("__DADOS__", json.dumps(dados, ensure_ascii=False))
    components.html(html, height=1300, scrolling=True)
