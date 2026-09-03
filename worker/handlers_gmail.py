"""
handlers_gmail.py — traz os 2 robôs de Gmail (Tabelas Yamaha / Guia Itaú) pra
dentro do supervisor, sem mudar as credenciais deles.

Cada robô vive em `.../scripts/` com seu próprio `config.py`,
`credentials.json` e `token.pickle`. Como os dois módulos se chamam igual
(`config`, `download_attachments`), a importação é ISOLADA: antes de cada
execução limpo esses nomes de `sys.modules` e ponho o `scripts/` certo na
frente do `sys.path`. Assim um não contamina o outro.

Uso direto (debug):
    python handlers_gmail.py yamaha
    python handlers_gmail.py itau
"""

import importlib
import os
import sys

_DEF_YAMAHA = r"G:\Meu Drive\CLODE\ATUALIZA_YAMAHA_TABELAS\scripts"
_DEF_ITAU = r"G:\Meu Drive\CLODE\GUIA_DE_OPORTUNIDADES_ITAU\scripts"

# nomes que os dois pacotes usam e que precisam ser recarregados a cada run
_MODULOS_VOLATEIS = ("config", "download_attachments")


def _run_isolado(scripts_dir: str) -> bool:
    """Importa o download_attachments daquele scripts_dir do zero e roda
    `GmailDownloader().run_download()`. Devolve True/False (baixou ou não)."""
    scripts_dir = os.path.abspath(scripts_dir)
    if not os.path.isdir(scripts_dir):
        raise RuntimeError(f"Pasta do robô Gmail não existe: {scripts_dir}")

    salvos = {m: sys.modules.pop(m, None) for m in _MODULOS_VOLATEIS}
    path0 = list(sys.path)
    cwd0 = os.getcwd()
    try:
        sys.path.insert(0, scripts_dir)
        os.chdir(scripts_dir)                       # os scripts esperam CWD = scripts/
        da = importlib.import_module("download_attachments")
        importlib.reload(da)
        ok = da.GmailDownloader().run_download()
        return bool(ok)
    finally:
        os.chdir(cwd0)
        sys.path[:] = path0
        for m in _MODULOS_VOLATEIS:
            sys.modules.pop(m, None)
            if salvos.get(m) is not None:
                sys.modules[m] = salvos[m]


def baixar_yamaha(scripts_dir: str = _DEF_YAMAHA) -> dict:
    ok = _run_isolado(scripts_dir)
    return {"ok": ok, "fonte": "gmail_yamaha",
            "mensagem": "Tabelas Yamaha baixadas" if ok else "Nada novo / falhou"}


def baixar_itau(scripts_dir: str = _DEF_ITAU) -> dict:
    ok = _run_isolado(scripts_dir)
    return {"ok": ok, "fonte": "gmail_itau",
            "mensagem": "Guia de Oportunidades Itaú baixado" if ok else "Nada novo / falhou"}


if __name__ == "__main__":
    alvo = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if alvo == "yamaha":
        print(baixar_yamaha())
    elif alvo == "itau":
        print(baixar_itau())
    else:
        print("uso: python handlers_gmail.py [yamaha|itau]")
        sys.exit(2)
