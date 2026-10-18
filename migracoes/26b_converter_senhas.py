"""
26b — converte as senhas em TEXTO PURO da tabela `usuarios` para HASH (PBKDF2).

Rode DEPOIS da migração 26 (26_usuarios_seguros.sql). Idempotente: quem já
tem hash é ignorado. Depois da conversão a coluna `senha` fica vazia (NULL) —
nenhuma senha em texto permanece no banco. Não imprime nenhuma senha.

    python migracoes/26b_converter_senhas.py            # prévia (não grava)
    python migracoes/26b_converter_senhas.py --confirmar
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from seguranca import hash_senha  # noqa: E402


def _cliente():
    import tomllib
    from supabase import create_client
    with open(os.path.join(os.path.dirname(AQUI), ".streamlit", "secrets.toml"), "rb") as f:
        sec = tomllib.load(f)
    return create_client(sec["SUPABASE_URL"], sec["SUPABASE_KEY"])


def main():
    confirmar = "--confirmar" in sys.argv
    sb = _cliente()
    try:
        rows = sb.table("usuarios").select("id,login,senha,senha_hash").execute().data or []
    except Exception as e:
        print("Não consegui ler `usuarios` com as colunas novas — rode antes a migração 26 no SQL Editor.\n", str(e)[:200])
        sys.exit(1)
    pend = [r for r in rows if (r.get("senha") or "") and not (r.get("senha_hash") or "")]
    ja = [r for r in rows if (r.get("senha_hash") or "")]
    vazios = [r for r in rows if not (r.get("senha") or "") and not (r.get("senha_hash") or "")]
    print(f"{len(rows)} usuário(s): {len(pend)} com senha em texto a converter, {len(ja)} já com hash, "
          f"{len(vazios)} sem senha nenhuma.")
    for r in pend:
        print(f"  - {r['login']}: converter")
    if vazios:
        print("  ATENÇÃO: sem senha nenhuma (precisam de senha nova):", ", ".join(r["login"] for r in vazios))
    if not confirmar:
        print("\n>>> PRÉVIA. Rode de novo com --confirmar para gravar.")
        return
    for r in pend:
        sb.table("usuarios").update({"senha_hash": hash_senha(r["senha"]), "senha": None}).eq("id", r["id"]).execute()
    # limpa texto puro que sobrou ao lado de um hash válido
    for r in ja:
        if (r.get("senha") or ""):
            sb.table("usuarios").update({"senha": None}).eq("id", r["id"]).execute()
    print(f">>> OK: {len(pend)} senha(s) convertida(s); nenhuma senha em texto puro permanece.")


if __name__ == "__main__":
    main()
