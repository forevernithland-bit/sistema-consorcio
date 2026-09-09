"""
testar_boleto.py — testa SÓ o passo de emitir + baixar o PDF do boleto,
sem passar pela fila. Use no PC do escritório, com o Newcon acessível.

    python testar_boleto.py 10015 107
    python testar_boleto.py 10015 107 --cliente "Diego Teste"
    python testar_boleto.py 10015 107 --visivel     # abre a janela do Chrome

O que ele faz:
  1. conecta no Supabase (pega a credencial do Newcon do cofre, igual o robô),
  2. abre o navegador e loga,
  3. roda newcon.gerar_boleto para a cota informada,
  4. diz o status, o código de barras e SE/ONDE o PDF foi salvo
     (PASTA_BOLETOS = G:\\Meu Drive\\CONSORBENS\\IMAGENS\\Boletos por padrão).

Nada é gravado na fila nem no ERP — é só um teste isolado.
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import newcon
from worker_consorbens import conectar_supabase, preparar_newcon, _fechar_navegador


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grupo")
    ap.add_argument("cota")
    ap.add_argument("--cliente", default="Teste Boleto")
    ap.add_argument("--visivel", action="store_true", help="abre a janela do Chrome")
    ap.add_argument("--timeout", type=int, default=int(os.getenv("TIMEOUT_CONFIRMACAO", "180")))
    a = ap.parse_args()

    pasta = newcon.PASTA_BOLETOS
    print(f"PASTA_BOLETOS = {pasta}")
    antes = set(os.listdir(pasta)) if os.path.isdir(pasta) else set()

    sb = conectar_supabase()
    ctx = preparar_newcon(sb, visivel=a.visivel)
    try:
        pedido = {"grupo": a.grupo, "cota": a.cota, "cliente": a.cliente}
        print(f"\n→ Emitindo boleto de {a.grupo}/{a.cota} ...")
        status, mensagem, extras = newcon.gerar_boleto(ctx["page"], pedido, a.timeout)
        print(f"\nSTATUS   : {status}")
        print(f"MENSAGEM : {mensagem}")
        print(f"EXTRAS   : {extras}")

        depois = set(os.listdir(pasta)) if os.path.isdir(pasta) else set()
        novos = sorted(depois - antes)
        if novos:
            for n in novos:
                p = os.path.join(pasta, n)
                print(f"\n✅ PDF NOVO: {p}  ({os.path.getsize(p)} bytes)")
        else:
            print("\n❌ Nenhum PDF novo na pasta. Veja os prints em worker/comprovantes/ "
                  "(boleto_sem_pdf_* / erro_emitir_boleto_*).")
    finally:
        _fechar_navegador(ctx)


if __name__ == "__main__":
    main()
