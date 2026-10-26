"""
handlers_backup.py — backup diário de todas as tabelas do ERP (robô do escritório).

Grava em  G:\\Meu Drive\\CLODE\\BACKUP_ERP\\AAAA-MM-DD\\  (JSON + CSV por tabela +
manifesto), mantém 30 diários + 12 mensais e espelha os arquivos de Mídias.
A lógica fica em ../backup_erp.py (a mesma usada pelo botão do ERP).

Uso direto (teste no PC do escritório):
    python handlers_backup.py              # faz um backup agora
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ_ERP = os.path.dirname(_AQUI)
if _RAIZ_ERP not in sys.path:
    sys.path.insert(0, _RAIZ_ERP)

import backup_erp  # noqa: E402

_DEF_DESTINO = r"G:\Meu Drive\CLODE\BACKUP_ERP"


def fazer_backup(sb, cfg: dict, origem: str = "CRON") -> dict:
    cam = (cfg or {}).get("caminhos", {})
    bk = (cfg or {}).get("backup", {})
    destino = cam.get("backup_erp", _DEF_DESTINO)
    return backup_erp.fazer_backup(
        sb, destino, origem=origem,
        diarios=int(bk.get("diarios", 30)), mensais=int(bk.get("mensais", 12)),
        midias=bool(bk.get("midias", True)),
        incluir_senhas_sistema=bool(bk.get("incluir_senhas_sistema", False)))


if __name__ == "__main__":
    from dotenv import load_dotenv
    from supabase import create_client
    import tomllib
    load_dotenv(os.path.join(_AQUI, ".env"))
    with open(os.path.join(_AQUI, "robo_config.toml"), "rb") as f:
        cfg = tomllib.load(f)
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    r = fazer_backup(sb, cfg, origem="manual")
    print(("OK  " if r["ok"] else "ERRO ") + r["mensagem"])
