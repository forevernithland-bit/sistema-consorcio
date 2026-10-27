"""
auditoria.py — lixeira e registro de exclusões do ERP.

Toda exclusão feita pelas telas passa por `apagar_com_lixeira`:
  1. lê as linhas que vão ser apagadas (pelo ID — nunca por nome);
  2. guarda uma cópia completa de cada uma em `auditoria_exclusoes`
     (tabela, id, JSON da linha, quem, quando, motivo);
  3. só então apaga.
Se a cópia não puder ser guardada, NADA é apagado (exceto se a migração 32
ainda não foi rodada — aí apaga como antes e avisa).

Além disso, a migração 32 instala gatilhos no banco que copiam para a mesma
tabela qualquer DELETE/UPDATE em vendas, clientes, comissoes_pagas e
status_comissoes — inclusive os feitos pelo robô ou direto no Supabase.
Com isso dá para restaurar (`restaurar`) o que foi apagado.
"""
import json
from datetime import datetime, timezone

import streamlit as st

TABELA = "auditoria_exclusoes"
LOTE = 200
# tabelas que podem ser restauradas pela tela (usuarios fica de fora: a cópia não guarda senha)
RESTAURAVEIS = {"vendas", "clientes", "comissoes_pagas", "status_comissoes", "administradoras",
                "cad_administradoras", "assembleias", "financeiro_datas", "base_conhecimento_ia", "midias"}
# nunca guardar estes campos na cópia
CAMPOS_SENSIVEIS = {"senha", "senha_hash"}


class AuditoriaIndisponivel(Exception):
    """A cópia de segurança não pôde ser gravada — a exclusão foi cancelada."""


def _tabela_ausente(e) -> bool:
    t = str(e)
    return "PGRST205" in t or "42P01" in t or (TABELA in t and ("does not exist" in t or "schema cache" in t))


def quem() -> str:
    try:
        return str(st.session_state.get("usuario_logado") or "desconhecido")
    except Exception:
        return "desconhecido"


def _limpa(linha: dict) -> dict:
    return {k: v for k, v in (linha or {}).items() if k not in CAMPOS_SENSIVEIS}


def registrar(supabase, tabela: str, linhas: list, motivo: str, operacao: str = "DELETE"):
    """Guarda a cópia das linhas. Devolve (True, aviso|None).
    Tabela de auditoria ausente (migração 32 não rodada) -> (False, aviso).
    Qualquer outro erro SOBE como AuditoriaIndisponivel."""
    if not linhas:
        return True, None
    agora = datetime.now(timezone.utc).isoformat()
    regs = [{"tabela": tabela, "operacao": operacao, "registro_id": str(l.get("id", "")),
             "dados": json.loads(json.dumps(_limpa(l), default=str)), "quem": quem(),
             "origem": "app", "motivo": motivo, "criado_em": agora} for l in linhas]
    try:
        for i in range(0, len(regs), LOTE):
            supabase.table(TABELA).insert(regs[i:i + LOTE]).execute()
        return True, None
    except Exception as e:
        if _tabela_ausente(e):
            return False, ("A lixeira ainda não está ativada (rode a migração 32 no Supabase): "
                           "esta exclusão não pôde ser guardada para restauração.")
        raise AuditoriaIndisponivel(f"Não consegui guardar a cópia de segurança antes de apagar: {e}")


def ler_por_ids(supabase, tabela: str, ids: list) -> list:
    out = []
    ids = [i for i in ids if i is not None]
    for i in range(0, len(ids), LOTE):
        out += supabase.table(tabela).select("*").in_("id", ids[i:i + LOTE]).execute().data or []
    return out


def apagar_com_lixeira(supabase, tabela: str, ids: list, motivo: str, permitir_sem_lixeira: bool = True):
    """Apaga as linhas de `tabela` com esses IDs, guardando cópia antes.
    Devolve (qtd_apagada, aviso|None). Se a cópia falhar, levanta
    AuditoriaIndisponivel e não apaga nada."""
    ids = [int(i) for i in ids if i is not None and str(i).strip() not in ("", "nan", "None")]
    if not ids:
        return 0, None
    linhas = ler_por_ids(supabase, tabela, ids)
    ok, aviso = registrar(supabase, tabela, linhas, motivo)
    if not ok and not permitir_sem_lixeira:
        raise AuditoriaIndisponivel(aviso)
    for i in range(0, len(ids), LOTE):
        supabase.table(tabela).delete().in_("id", ids[i:i + LOTE]).execute()
    return len(linhas), aviso


def listar(supabase, operacao: str = "DELETE", limite: int = 300) -> list:
    try:
        return (supabase.table(TABELA).select("*").eq("operacao", operacao)
                .order("criado_em", desc=True).limit(limite).execute().data or [])
    except Exception as e:
        if _tabela_ausente(e):
            return None
        raise


def restaurar(supabase, reg: dict):
    """Recoloca no banco a linha guardada em `reg` (registro de auditoria).
    Devolve (ok, mensagem). Não sobrescreve: se já existe uma linha com o
    mesmo ID, recusa."""
    tabela = reg.get("tabela")
    if tabela not in RESTAURAVEIS:
        return False, f"A tabela '{tabela}' não é restaurável por aqui."
    dados = reg.get("dados") or {}
    if isinstance(dados, str):
        dados = json.loads(dados)
    rid = dados.get("id")
    if rid is not None:
        ja = supabase.table(tabela).select("id").eq("id", rid).execute().data
        if ja:
            return False, f"Já existe uma linha com ID {rid} em {tabela} — nada foi alterado."
    try:
        supabase.table(tabela).insert(dados).execute()
    except Exception as e:
        if "23505" in str(e) or "duplicate" in str(e).lower():
            return False, f"Essa linha já existe de novo em {tabela} — nada foi alterado."
        raise
    try:
        supabase.table(TABELA).update({"restaurado_em": datetime.now(timezone.utc).isoformat(),
                                        "restaurado_por": quem()}).eq("id", reg["id"]).execute()
    except Exception:
        pass
    ident = rid if rid is not None else (dados.get("chave_unica") or dados.get("Chave_Unica") or "")
    return True, f"Linha {ident} restaurada em {tabela}.".replace("Linha  ", "Linha ")
