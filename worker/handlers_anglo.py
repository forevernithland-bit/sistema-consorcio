"""
handlers_anglo.py — traz o robô "Importar Anglo" pra dentro do supervisor.

CLODE/IMPORTA_ANGLO_CONSORCIO/atualizar_cartas.py:
  API JSON da Anglo -> ágio/termômetro -> Supabase do SITE
  (substitui SÓ fornecedor "Anglo Consórcios"; os outros ficam intactos).
Credencial: %LOCALAPPDATA%/Consorbens/config.json (o próprio script acha).

Uso direto (debug):
    python handlers_anglo.py           # roda de verdade
    python handlers_anglo.py --dry     # só mostra
"""

import importlib
import os
import sys

_DEF_ANGLO = r"G:\Meu Drive\CLODE\IMPORTA_ANGLO_CONSORCIO"
_MODULOS_VOLATEIS = ("atualizar_cartas", "converter_anglo")


def importar_anglo(anglo_dir: str = _DEF_ANGLO, dry: bool = False) -> dict:
    """Roda o atualizar_cartas.main() daquela pasta. Levanta exceção em falha."""
    anglo_dir = os.path.abspath(anglo_dir)
    if not os.path.isdir(anglo_dir):
        raise RuntimeError(f"Pasta do robô Anglo não existe: {anglo_dir}")

    salvos = {m: sys.modules.pop(m, None) for m in _MODULOS_VOLATEIS}
    path0, argv0, cwd0 = list(sys.path), list(sys.argv), os.getcwd()
    try:
        sys.path.insert(0, anglo_dir)
        os.chdir(anglo_dir)
        sys.argv = ["atualizar_cartas.py"] + (["--dry-run"] if dry else [])
        mod = importlib.import_module("atualizar_cartas")
        importlib.reload(mod)
        mod.main()                       # sucesso = retorna None; falha = raise
        return {"ok": True, "fonte": "anglo",
                "mensagem": "Cartas Anglo atualizadas no site" + (" (dry)" if dry else "")}
    finally:
        os.chdir(cwd0)
        sys.path[:] = path0
        sys.argv[:] = argv0
        for m in _MODULOS_VOLATEIS:
            sys.modules.pop(m, None)
            if salvos.get(m) is not None:
                sys.modules[m] = salvos[m]


if __name__ == "__main__":
    print(importar_anglo(dry="--dry" in sys.argv))
