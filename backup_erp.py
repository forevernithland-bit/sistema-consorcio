"""
backup_erp.py — cópia de segurança de TODAS as tabelas do ERP.

Usado em dois lugares (sem depender do Streamlit):
  • robô do escritório (worker/handlers_backup.py): todo dia grava uma pasta
    datada no Google Drive local — G:\\Meu Drive\\CLODE\\BACKUP_ERP\\AAAA-MM-DD\\
    com um JSON e um CSV por tabela + manifesto (linhas e SHA-256 de cada
    arquivo). Retenção: últimos 30 dias + 1 por mês dos últimos 12 meses.
  • tela Configurações → Backup e Lixeira: botão "Baixar backup agora" (ZIP).

Senhas NUNCA entram no backup: usuarios sai sem senha/senha_hash e a tabela
senhas_sistema (senhas das administradoras, em texto) só entra se for pedido
explicitamente (incluir_senhas_sistema=True).
"""
import csv
import hashlib
import io
import json
import os
import re
import shutil
import zipfile
from datetime import date, datetime, timezone

PAGINA = 1000

# Tabelas do ERP (o que não existir no banco é registrado como "ausente" e o
# backup segue com as demais).
TABELAS = [
    "vendas", "clientes", "comissoes_pagas", "status_comissoes", "usuarios",
    "administradoras", "cad_administradoras", "config_interna", "assembleias",
    "financeiro_datas", "resultado_socios_mensal",
    "pagamentos_vendedor", "pagamentos_vendedor_itens", "pagamentos_vendedor_log",
    "fila_automacao", "midias", "base_conhecimento_ia", "robo_status",
    "planos_yamaha", "grupos_yamaha", "grupos_yamaha_consultas", "grupos_yamaha_lances",
    "yamaha_assembleias", "yamaha_contemplacoes", "yamaha_buscas",
    "auditoria_exclusoes", "backups_erp",
]
TABELA_SENHAS = "senhas_sistema"
CAMPOS_FORA = {"usuarios": {"senha", "senha_hash"}}
_PASTA_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ausente(e) -> bool:
    """A TABELA não existe (não confundir com coluna inexistente)."""
    t = str(e)
    return ("PGRST205" in t or "42P01" in t or "Could not find the table" in t
            or ("relation" in t and "does not exist" in t))


def _coluna_inexistente(e) -> bool:
    t = str(e)
    return "42703" in t or ("column" in t and "does not exist" in t) or "PGRST204" in t


# Ordem da paginação por tabela (chave primária). Várias tabelas NÃO têm `id`
# (financeiro_datas, resultado_socios_mensal, planos/grupos/assembleias/buscas da
# Yamaha) — ordenar por id nelas dá erro "column ... id does not exist".
ORDEM = {
    "financeiro_datas": ["chave_unica"],
    "resultado_socios_mensal": ["ano", "mes"],
    "planos_yamaha": ["codigo", "tipo_bem"],
    "grupos_yamaha": ["grupo", "tipo_bem"],
    "yamaha_assembleias": ["grupo", "num_assembleia"],
    "yamaha_buscas": ["tipo_bem", "plano_codigo", "credito", "prazo_label"],
}


def ler_tabela(sb, tabela: str) -> list:
    """Todas as linhas, de 1000 em 1000, ordenadas pela chave da tabela para a
    paginação ser estável. Se a coluna de ordem não existir, lê sem ordenar
    — essas tabelas são pequenas, cabem numa página só)."""
    linhas, ini, ordem = [], 0, list(ORDEM.get(tabela, ["id"]))
    while True:
        q = sb.table(tabela).select("*")
        for col in ordem:
            q = q.order(col)
        try:
            lote = q.range(ini, ini + PAGINA - 1).execute().data or []
        except Exception as e:
            if ordem and ini == 0 and _coluna_inexistente(e):
                ordem = []            # sem a coluna de ordem: pagina sem ordenar
                continue
            raise
        linhas.extend(lote)
        if len(lote) < PAGINA:
            return linhas
        ini += PAGINA


def exportar(sb, tabelas=None, incluir_senhas_sistema=False):
    """{tabela: linhas}, {tabela: erro}. Tabela ausente vira erro 'ausente'."""
    dados, erros = {}, {}
    lista = list(tabelas or TABELAS) + ([TABELA_SENHAS] if incluir_senhas_sistema else [])
    for t in lista:
        try:
            linhas = ler_tabela(sb, t)
            fora = CAMPOS_FORA.get(t)
            if fora:
                linhas = [{k: v for k, v in r.items() if k not in fora} for r in linhas]
            dados[t] = linhas
        except Exception as e:
            erros[t] = "ausente" if _ausente(e) else f"{type(e).__name__}: {e}"
    return dados, erros


def _csv_bytes(linhas: list) -> bytes:
    cols = []
    for r in linhas:
        for k in r:
            if k not in cols:
                cols.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in linhas:
        w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in r.items()})
    return ("\ufeff" + buf.getvalue()).encode("utf-8")       # BOM: o Excel abre com acento certo


def _json_bytes(linhas: list) -> bytes:
    return json.dumps(linhas, ensure_ascii=False, indent=1, default=str).encode("utf-8")


def montar_arquivos(dados: dict, erros: dict, origem: str = "") -> dict:
    """{nome_arquivo: bytes} — JSON + CSV por tabela + manifesto.json."""
    arqs, manifesto = {}, {"gerado_em": datetime.now(timezone.utc).isoformat(), "origem": origem,
                           "tabelas": {}, "erros": erros, "observacao":
                           "usuarios sem senha/senha_hash; senhas_sistema só se pedido."}
    for t, linhas in dados.items():
        j, c = _json_bytes(linhas), _csv_bytes(linhas)
        arqs[f"{t}.json"], arqs[f"{t}.csv"] = j, c
        manifesto["tabelas"][t] = {"linhas": len(linhas), "sha256_json": hashlib.sha256(j).hexdigest()}
    manifesto["total_linhas"] = sum(v["linhas"] for v in manifesto["tabelas"].values())
    arqs["manifesto.json"] = json.dumps(manifesto, ensure_ascii=False, indent=1).encode("utf-8")
    return arqs


def gerar_zip(sb, origem="ERP", incluir_senhas_sistema=False):
    """(bytes_do_zip, manifesto) — usado pelo botão de download."""
    dados, erros = exportar(sb, incluir_senhas_sistema=incluir_senhas_sistema)
    arqs = montar_arquivos(dados, erros, origem)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, b in arqs.items():
            z.writestr(nome, b)
    return buf.getvalue(), json.loads(arqs["manifesto.json"])


def gravar_pasta(arqs: dict, raiz: str, dia: date = None) -> str:
    """Grava em raiz/AAAA-MM-DD/. Escreve numa pasta temporária, confere e só
    então troca — um backup interrompido nunca estraga o do dia anterior."""
    dia = dia or date.today()
    os.makedirs(raiz, exist_ok=True)
    final = os.path.join(raiz, dia.isoformat())
    tmp = final + ".tmp"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    for nome, b in arqs.items():
        with open(os.path.join(tmp, nome), "wb") as f:
            f.write(b)
    # conferência: o que está no disco bate com o manifesto
    man = json.loads(arqs["manifesto.json"])
    for t, info in man["tabelas"].items():
        with open(os.path.join(tmp, f"{t}.json"), "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != info["sha256_json"]:
                raise RuntimeError(f"conferência falhou em {t}.json")
    if os.path.exists(final):
        antigo = final + ".antigo"
        if os.path.exists(antigo):
            shutil.rmtree(antigo)
        os.rename(final, antigo)
        os.rename(tmp, final)
        shutil.rmtree(antigo, ignore_errors=True)
    else:
        os.rename(tmp, final)
    return final


def aplicar_retencao(raiz: str, diarios: int = 30, mensais: int = 12, hoje: date = None) -> list:
    """Mantém as pastas dos últimos `diarios` dias + a mais antiga de cada um dos
    últimos `mensais` meses. Só mexe em pastas com nome AAAA-MM-DD. Nunca apaga
    a mais recente. Devolve a lista do que foi removido."""
    hoje = hoje or date.today()
    if not os.path.isdir(raiz):
        return []
    dias = []
    for n in os.listdir(raiz):
        if _PASTA_DIA.match(n) and os.path.isdir(os.path.join(raiz, n)):
            try:
                dias.append(date.fromisoformat(n))
            except ValueError:
                pass
    if not dias:
        return []
    dias.sort()
    manter = {dias[-1]}
    manter |= {d for d in dias if (hoje - d).days < diarios}
    meses = {}
    for d in dias:                                   # 1ª pasta de cada mês
        meses.setdefault((d.year, d.month), d)
    ult_meses = sorted(meses)[-mensais:] if mensais > 0 else []
    manter |= {meses[m] for m in ult_meses}
    removidas = []
    for d in dias:
        if d not in manter:
            shutil.rmtree(os.path.join(raiz, d.isoformat()), ignore_errors=True)
            removidas.append(d.isoformat())
    return removidas


def espelhar_midias(sb, linhas_midias: list, raiz: str, bucket: str = "midias") -> dict:
    """Copia para raiz/_midias_arquivos/ os arquivos do Storage que ainda não
    estão lá (incremental: só baixa o que é novo)."""
    destino = os.path.join(raiz, "_midias_arquivos")
    os.makedirs(destino, exist_ok=True)
    novos, erros = 0, 0
    for r in linhas_midias or []:
        cam = str(r.get("caminho") or "").strip()
        if not cam:
            continue
        local = os.path.join(destino, *cam.replace("\\", "/").split("/"))
        if os.path.exists(local):
            continue
        try:
            dados = sb.storage.from_(bucket).download(cam)
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "wb") as f:
                f.write(dados)
            novos += 1
        except Exception:
            erros += 1
    return {"novos": novos, "erros": erros}


def registrar(sb, origem, ok, pasta, manifesto, mensagem, duracao):
    try:
        sb.table("backups_erp").insert({
            "origem": origem, "ok": bool(ok), "pasta": pasta,
            "total_linhas": (manifesto or {}).get("total_linhas"),
            "tabelas": {t: v["linhas"] for t, v in ((manifesto or {}).get("tabelas") or {}).items()},
            "mensagem": (mensagem or "")[:1000], "duracao_s": round(float(duracao), 1),
        }).execute()
    except Exception:
        pass                      # migração 32 ainda não rodada: o backup em disco vale igual


def fazer_backup(sb, raiz: str, origem: str = "CRON", diarios: int = 30, mensais: int = 12,
                 midias: bool = True, incluir_senhas_sistema: bool = False) -> dict:
    """Backup completo em disco + retenção + registro. Devolve {ok, mensagem, pasta}."""
    import time
    t0 = time.time()
    try:
        dados, erros = exportar(sb, incluir_senhas_sistema=incluir_senhas_sistema)
        criticos = [t for t in ("vendas", "clientes", "comissoes_pagas", "status_comissoes") if t in erros]
        if criticos:
            # não grava um backup "furado" por cima de um bom do mesmo dia
            raise RuntimeError(f"não consegui ler {', '.join(criticos)}: {[erros[t] for t in criticos]}")
        arqs = montar_arquivos(dados, erros, origem)
        man = json.loads(arqs["manifesto.json"])
        pasta = gravar_pasta(arqs, raiz)
        removidas = aplicar_retencao(raiz, diarios, mensais)
        extra = ""
        if midias and dados.get("midias"):
            m = espelhar_midias(sb, dados["midias"], raiz)
            extra = f" · mídias: {m['novos']} arquivo(s) novo(s)" + (f", {m['erros']} erro(s)" if m["erros"] else "")
        falhas = {t: e for t, e in erros.items() if e != "ausente"}
        ok = not criticos and not falhas
        msg = (f"{man['total_linhas']} linhas de {len(dados)} tabelas em {pasta}"
               + (f" · removidas pela retenção: {', '.join(removidas)}" if removidas else "") + extra
               + (f" · ERROS: {falhas}" if falhas else ""))
        registrar(sb, origem, ok, pasta, man, msg, time.time() - t0)
        return {"ok": ok, "mensagem": msg, "pasta": pasta}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        registrar(sb, origem, False, raiz, None, msg, time.time() - t0)
        return {"ok": False, "mensagem": msg, "pasta": None}


def ultimo_backup(sb):
    """Última linha de backups_erp (ou None). Levanta se a tabela não existir."""
    r = sb.table("backups_erp").select("*").order("criado_em", desc=True).limit(1).execute().data or []
    return r[0] if r else None
