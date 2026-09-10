"""
handlers_fraga_bitello.py — traz o "Importar Fraga e Bitello" pra dentro do supervisor.

Lê a API pública da F&B (https://fragaebitelloconsorcios.com.br/api/json/contemplados),
aplica o nosso ágio (fornecedor "Fraga e Bitello": autos 5% / imóveis 4%) e
sincroniza a base de cartas do SITE — insere/atualiza/apaga só o que é do
fornecedor "Fraga e Bitello", o resto fica intacto.

O script de verdade vive na skill:
  C:/Users/<user>/.claude/skills/cartas-contempladas-consorbens/scripts/importar_fraga_bitello.py
Credencial de escrita: o `.secrets.toml` daquela mesma pasta (login admin do site).

Uso direto (debug):
    python handlers_fraga_bitello.py           # roda de verdade (--confirmar)
    python handlers_fraga_bitello.py --dry      # só mostra a prévia
"""

import importlib
import os
import sys

# Caminho padrão da pasta de scripts da skill (mesmo PC do escritório).
_DEF_FB = os.path.expandvars(
    r"%USERPROFILE%\.claude\skills\cartas-contempladas-consorbens\scripts")
_MODULOS_VOLATEIS = ("importar_fraga_bitello", "consorbens_db")


def importar_fb(scripts_dir: str = _DEF_FB, dry: bool = False) -> dict:
    """Roda o importar_fraga_bitello.main() daquela pasta. Levanta exceção em falha."""
    scripts_dir = os.path.abspath(scripts_dir)
    if not os.path.isdir(scripts_dir):
        raise RuntimeError(f"Pasta de scripts da F&B não existe: {scripts_dir}")

    salvos = {m: sys.modules.pop(m, None) for m in _MODULOS_VOLATEIS}
    path0, argv0, cwd0 = list(sys.path), list(sys.argv), os.getcwd()
    try:
        sys.path.insert(0, scripts_dir)
        os.chdir(scripts_dir)
        sys.argv = ["importar_fraga_bitello.py"] + ([] if dry else ["--confirmar"])
        mod = importlib.import_module("importar_fraga_bitello")
        importlib.reload(mod)
        try:
            mod.main()                   # sucesso = retorna None
        except SystemExit as se:         # o script usa sys.exit(1) em falha de API
            if se.code:
                raise RuntimeError(f"importar_fraga_bitello saiu com código {se.code}") from se
        return {"ok": True, "fonte": "fraga_bitello",
                "mensagem": "Cartas Fraga e Bitello sincronizadas no site" + (" (dry)" if dry else "")}
    finally:
        os.chdir(cwd0)
        sys.path[:] = path0
        sys.argv[:] = argv0
        for m in _MODULOS_VOLATEIS:
            sys.modules.pop(m, None)
            if salvos.get(m) is not None:
                sys.modules[m] = salvos[m]


if __name__ == "__main__":
    print(importar_fb(dry="--dry" in sys.argv))
