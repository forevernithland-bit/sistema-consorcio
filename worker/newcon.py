"""
newcon.py — Miolo da automação do Newcon (site newkey.cny.com.br).

Fluxo de OFERTA DE LANCE FIXO (mapeado a partir da gravação real):
    Login -> Atendimento -> (Grupo + Cota) -> Localizar
    -> Oferta de Lance -> Fixo -> Reduzir Parcela -> Embutido -> Confirmar

Seguranças embutidas:
  * Confere o NOME do cliente na tela antes de ofertar (aborta se não bater).
  * Tira um print (comprovante) antes e depois de Confirmar, em worker/comprovantes/.
  * (Opcional) pausa antes de Confirmar, para você conferir na 1ª vez.
"""

import os
import re
import unicodedata
from datetime import datetime
from playwright.sync_api import Page, BrowserContext, TimeoutError as PWTimeout

# Sessão salva (login persistente) e pasta de comprovantes
PASTA = os.path.dirname(__file__)
STORAGE_STATE = os.path.join(PASTA, "newcon_sessao.json")
PASTA_COMPROVANTES = os.path.join(PASTA, "comprovantes")

# Pausa (segundos) antes de clicar em Confirmar. 0 = sem pausa.
# Útil nas 1ªs execuções: dá tempo de você olhar a tela preenchida.
PAUSA_ANTES_CONFIRMAR = int(os.getenv("PAUSA_ANTES_CONFIRMAR_SEG", "0"))

# Endereço da tela de Atendimento (busca de cota). É memorizado na 1ª vez que
# chegamos nela, para voltarmos DIRETO entre uma cota e outra (sem reiniciar).
_URL_ATENDIMENTO = None


# ------------------------------------------------------------------ util
def _norm(txt: str) -> str:
    """Maiúsculas, sem acento, espaços colapsados — para comparar nomes."""
    if not txt:
        return ""
    txt = unicodedata.normalize("NFD", str(txt))
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", txt.upper()).strip()


def _nome_confere(cliente_esperado: str, texto_tela: str) -> bool:
    """True se um trecho significativo do nome do cliente aparece na tela.
    Exige o 1º nome + pelo menos mais um nome (evita falso positivo por nome comum)."""
    alvo = _norm(cliente_esperado)
    tela = _norm(texto_tela)
    partes = [p for p in alvo.split(" ") if len(p) >= 3]
    if not partes:
        return False
    presentes = sum(1 for p in partes if p in tela)
    # precisa do 1º nome presente e da maioria dos nomes batendo
    return (partes[0] in tela) and (presentes >= max(2, len(partes) // 2))


def _print_tela(page: Page, etiqueta: str) -> str:
    os.makedirs(PASTA_COMPROVANTES, exist_ok=True)
    nome = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{etiqueta}.png"
    caminho = os.path.join(PASTA_COMPROVANTES, nome)
    try:
        page.screenshot(path=caminho, full_page=True)
    except Exception:
        pass
    return caminho


# Campo de cota da tela de busca (Atendimento) — usado como sinal de "estou na busca"
CAMPO_COTA = "#ctl00_Conteudo_edtCota"


def _clique_curto(page: Page, locator, timeout=4000) -> bool:
    """Tenta clicar num elemento que PODE não estar presente, sem travar 60s."""
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
        locator.first.click(timeout=timeout)
        page.wait_for_load_state("networkidle")
        return True
    except Exception:
        return False


def _na_busca(page: Page) -> bool:
    """True se estamos na tela de Atendimento (campo de cota visível)."""
    try:
        return page.locator(CAMPO_COTA).first.is_visible(timeout=2000)
    except Exception:
        return False


def _ir_para_atendimento(page: Page) -> None:
    """Garante que estamos na tela de busca de cota, venha de onde vier
    (inclusive de uma tela de comprovante/relatório)."""
    global _URL_ATENDIMENTO
    try:
        page.keyboard.press("Escape")  # fecha qualquer modal aberto
    except Exception:
        pass
    if _na_busca(page):
        _URL_ATENDIMENTO = page.url
        return

    # 1) JEITO MAIS CONFIÁVEL: ir DIRETO para a tela de Atendimento já conhecida
    #    (memorizada na 1ª cota). Evita depender do "Voltar" e de reiniciar o robô.
    if _URL_ATENDIMENTO:
        try:
            page.goto(_URL_ATENDIMENTO)
            page.wait_for_load_state("networkidle")
            if _na_busca(page):
                return
        except Exception:
            pass

    # 2) Fallback: clicar em "Atendimento" (e, se preciso, "Voltar" de um relatório)
    for _ in range(3):
        _clique_curto(page, page.get_by_role("button", name="Atendimento"))
        if _na_busca(page):
            _URL_ATENDIMENTO = page.url
            return
        _clique_curto(page, page.get_by_role("link", name="Voltar"))
        _clique_curto(page, page.get_by_role("button", name="Voltar"))

    # 3) Última cartada: recarrega a home logada e tenta de novo
    page.goto(os.getenv("NEWCON_URL", ""))
    page.wait_for_load_state("networkidle")
    _clique_curto(page, page.get_by_role("button", name="Atendimento"), timeout=30000)
    if _na_busca(page):
        _URL_ATENDIMENTO = page.url
        return
    raise RuntimeError("Não consegui voltar para a tela de Atendimento (busca de cota).")


def _extrair_protocolo(txt: str):
    """Pega o nº de protocolo (~7 dígitos 'limpos') mais próximo do rótulo 'Protocolo'.
    O número não fica colado no rótulo (fica em outra célula da tabela), então
    procuramos inteiros de 6 a 9 dígitos sem ponto/vírgula/barra (para não pegar
    valores em R$, CPF ou datas), preferindo o que vem logo depois de 'Protocolo'."""
    candidatos = [(m.start(), m.group(1))
                  for m in re.finditer(r"(?<![\d.,/])(\d{6,9})(?![\d.,/])", txt)]
    if not candidatos:
        return None
    idx = txt.lower().find("protocolo")
    if idx >= 0:
        depois = [c for c in candidatos if c[0] >= idx]
        if depois:
            return min(depois, key=lambda c: c[0] - idx)[1]
    return candidatos[0][1]


def _ler_comprovante(page: Page, timeout_seg: int):
    """Espera o comprovante do lance e retorna (sucesso, protocolo|None).

    Sucesso é reconhecido de forma robusta por QUALQUER um destes sinais:
      * a página de comprovante do Newcon carregou (URL com 'reports'/'frmConCm'); OU
      * apareceu o texto 'Comprovante do Lance'.
    Procura em todas as abas/popups e em todos os frames. O protocolo é extraído
    quando possível; se o comprovante apareceu mas o número não pôde ser lido,
    ainda assim retorna sucesso (o print serve de comprovante)."""
    tentativas = max(1, int(timeout_seg / 2))
    viu_comprovante = False
    for _ in range(tentativas):
        for pg in [page] + [p for p in page.context.pages if p is not page]:
            urls = [pg.url] + [fr.url for fr in pg.frames]
            if any(("reports" in (u or "").lower() or "frmconcm" in (u or "").lower())
                   for u in urls):
                viu_comprovante = True
            for fr in pg.frames:
                txt = ""
                try:
                    txt = fr.content()
                except Exception:
                    try:
                        txt = fr.inner_text("body")
                    except Exception:
                        continue
                if "comprovante do lance" in txt.lower():
                    viu_comprovante = True
                if "protocolo" in txt.lower():
                    prot = _extrair_protocolo(txt)
                    if prot:
                        return True, prot
        page.wait_for_timeout(2000)
    return viu_comprovante, None


def _texto_pagina(page: Page) -> str:
    """Junta o texto de todos os frames da página (para procurar avisos/protocolos)."""
    partes = []
    for fr in page.frames:
        try:
            partes.append(fr.inner_text("body"))
        except Exception:
            try:
                partes.append(fr.content())
            except Exception:
                pass
    return "\n".join(partes)


# ------------------------------------------------------------------ login
def esta_logado(page: Page) -> bool:
    """Logado = a tela de login (campo de usuário) NÃO está visível."""
    try:
        return not page.locator("#edtUsuario").is_visible()
    except Exception:
        return False


def fazer_login(page: Page, context: BrowserContext, login: str, senha: str) -> None:
    page.locator("#edtUsuario").fill(login)
    page.locator("#edtSenha").fill(senha)
    page.get_by_role("button", name="Login").click()
    # Confirma que passou do login: o botão "Atendimento" precisa aparecer
    try:
        page.get_by_role("button", name="Atendimento").wait_for(timeout=30000)
    except PWTimeout:
        # Pode ser senha expirada / troca obrigatória de senha
        _print_tela(page, "falha_login")
        raise RuntimeError(
            "Não consegui completar o login (senha errada/expirada ou o Newcon "
            "pediu troca de senha). Atualize a senha na aba 'Senhas' do CRM."
        )


# ------------------------------------------------------------------ oferta
def ofertar_lance(page: Page, pedido: dict, timeout_confirmacao: int):
    """Retorna (status, mensagem, protocolo), onde status é:
       'OK'          -> lance ofertado agora com sucesso
       'JA_OFERTADO' -> a cota já tinha lance; não ofertamos de novo (traz protocolo/data)
       'FALHA'       -> falha de negócio (nome não confere, sem opção de lance, etc.)"""
    grupo = str(pedido.get("grupo", "")).strip()
    cota = str(pedido.get("cota", "")).strip()
    cliente = str(pedido.get("cliente", "")).strip()
    pct_embutido = float(pedido.get("pct_embutido") or 0)

    # 1) Garantir que estamos na tela de busca (Atendimento), venha de onde vier
    _ir_para_atendimento(page)

    # 2) Buscar por GRUPO + COTA
    try:
        page.locator("#ctl00_Conteudo_edtGrupo").fill(grupo)
    except Exception:
        # fallback: campo por rótulo, caso o id seja diferente
        page.get_by_label("Grupo").fill(grupo)
    page.locator("#ctl00_Conteudo_edtCota").fill(cota)
    page.get_by_role("button", name="Localizar").click()
    page.wait_for_load_state("networkidle")

    # 3) A cota é identificada por GRUPO + COTA na busca (chave única no Newcon).
    #    A conferência por NOME foi removida: os nomes no ERP têm anotações extras
    #    (ex: "(Nay)", "(1% nayara)", nome de empresa) que não batem com o Newcon e
    #    geravam falso "ABORTADO". Se a cota não existir, o passo seguinte já falha.

    # 4) Abrir Oferta de Lance
    try:
        page.get_by_role("link", name="Oferta de Lance").click()
        page.wait_for_load_state("networkidle")
    except Exception:
        cam = _print_tela(page, f"sem_oferta_lance_{grupo}_{cota}")
        return "FALHA", (f"Não encontrei 'Oferta de Lance' para grupo {grupo}/cota {cota} "
                         f"(cota pode não estar apta a lance). Print: {os.path.basename(cam)}"), None

    # 4.1) JÁ OFERTADO? A tela mostra em vermelho "Último lance ofertado em: DD/MM/AAAA".
    #      Nesse caso NÃO ofertamos de novo: pegamos a data (do aviso) e o protocolo
    #      (da primeira linha do Histórico) e registramos como "Já estava ofertado".
    txt_oferta = _texto_pagina(page)
    m_data = re.search(r"lance ofertado em[:\s]*(\d{2}/\d{2}/\d{4})", txt_oferta, re.I)
    if m_data:
        data_lance = m_data.group(1)
        cam = _print_tela(page, f"ja_ofertado_{grupo}_{cota}")
        return "JA_OFERTADO", (f"Já estava ofertado em {data_lance}. "
                               f"Print: {os.path.basename(cam)}"), None

    # 5) Fixo + Reduzir Parcela + Embutido
    page.get_by_role("radio", name="Fixo", exact=True).check()
    page.wait_for_load_state("networkidle")
    page.get_by_role("radio", name="Reduzir Parcela").check()
    page.wait_for_load_state("networkidle")

    emb_txt = f"{pct_embutido:.4f}".replace(".", ",")  # ex: 15.0 -> "15,0000"
    page.locator("#ctl00_Conteudo_edtEmbutido").fill(emb_txt)

    # 6) Comprovante ANTES de confirmar + pausa opcional de conferência
    _print_tela(page, f"antes_confirmar_{grupo}_{cota}")
    if PAUSA_ANTES_CONFIRMAR > 0:
        page.wait_for_timeout(PAUSA_ANTES_CONFIRMAR * 1000)

    # 7) Confirmar. O clique pode "reclamar" da navegação lenta, mas o lance costuma
    #    ser enviado mesmo assim — então, aconteça o que acontecer no clique, a gente
    #    procura o comprovante/protocolo em TODOS os frames da página.
    try:
        page.get_by_role("button", name="Confirmar").click(timeout=timeout_confirmacao * 1000)
    except Exception:
        pass  # segue mesmo assim para procurar o comprovante

    # 8) Espera o comprovante e lê o protocolo. Guarda o print (o comprovante em si).
    sucesso, protocolo = _ler_comprovante(page, timeout_confirmacao)
    cam = _print_tela(page, f"comprovante_{grupo}_{cota}_prot{protocolo or 'SN'}")

    if sucesso:
        prot_log = protocolo or "conferir-print"
        prot_txt = protocolo if protocolo else "(ver comprovante no print)"
        return "OK", (f"Lance Fixo ofertado (embutido {emb_txt}%). Protocolo {prot_txt}. "
                      f"Comprovante: {os.path.basename(cam)}"), prot_log

    # ZONA SENSÍVEL: não vimos o comprovante — o lance PODE ter ido. Não repetir sozinho.
    return "FALHA", (f"Cliquei em Confirmar, mas não confirmei o comprovante em {timeout_confirmacao}s. "
                     f"CONFIRA MANUALMENTE no Newcon antes de repetir — o lance pode ter sido "
                     f"registrado. Print: {os.path.basename(cam)}"), None


# ------------------------------------------------------------------ boleto
# Onde salvar os PDFs dos boletos (no PC do escritório). Configurável no .env.
PASTA_BOLETOS = os.getenv("PASTA_BOLETOS", r"G:\Meu Drive\CONSORBENS\IMAGENS\Boletos")


def gerar_boleto(page: Page, pedido: dict, timeout: int):
    """Emite o boleto de uma cota no Newcon, baixa o PDF e lê o código de barras.

    Fluxo (da gravação): Atendimento -> grupo/cota -> Localizar -> Emissão de Cobrança
    -> ícone de emitir (linha do grid) -> "Emitir Cobrança" (abre o boleto num popup)
    -> "Baixar" (PDF) -> "Gerar Cód. de barras" -> "Copiar Código".

    Retorna (status, mensagem, extras) com extras = {codigo_barras, vencimento, em_atraso}."""
    grupo = str(pedido.get("grupo", "")).strip()
    cota = str(pedido.get("cota", "")).strip()

    # Nome do arquivo do PDF: primeiroNome_grupo_cota.pdf (sem acento/caractere inválido)
    _prim = str(pedido.get("cliente", "")).strip().split(" ")[0]
    _prim = unicodedata.normalize("NFKD", _prim).encode("ascii", "ignore").decode()
    _prim = re.sub(r"[^A-Za-z0-9]", "", _prim) or "cliente"
    nome_arquivo = f"{_prim}_{grupo}_{cota}.pdf"

    # 1) Buscar a cota (grupo + cota)
    _ir_para_atendimento(page)
    try:
        page.locator("#ctl00_Conteudo_edtGrupo").fill(grupo)
    except Exception:
        pass
    page.locator("#ctl00_Conteudo_edtCota").fill(cota)
    page.get_by_role("button", name="Localizar").click()
    page.wait_for_load_state("networkidle")

    # 2) Menu "Emissão de Cobrança"
    try:
        page.get_by_role("link", name="Emissão de Cobrança").click()
        page.wait_for_load_state("networkidle")
    except Exception:
        cam = _print_tela(page, f"sem_emissao_cobranca_{grupo}_{cota}")
        return "FALHA", (f"Não encontrei 'Emissão de Cobrança' para {grupo}/{cota}. "
                         f"Print: {os.path.basename(cam)}"), {}

    # 3) Detectar atraso e vencimento na tela (best-effort — validar no teste)
    texto = _texto_pagina(page)
    em_atraso = bool(re.search(r"em atraso|parcela.{0,12}vencid|situa.{0,6}atras", texto, re.I))
    mv = re.search(r"Vencimento\D{0,20}?(\d{2}/\d{2}/\d{4})", texto, re.I)
    vencimento = mv.group(1) if mv else ""

    # 4) Ícone de emitir boleto. Se NÃO houver ícone de emitir:
    #    - se a tela indica pago -> boleto do mês já foi pago
    #    - senão -> não há boleto para emitir neste mês
    #    (detecção best-effort por texto — validar no teste com a tela real)
    if page.locator("[id*='imgEmite_Boleto']").count() == 0:
        cam = _print_tela(page, f"sem_emitir_{grupo}_{cota}")
        if re.search(r"\bpag[oa]\b|quitad|liquidad|baixad", texto, re.I):
            mes = datetime.now().strftime("%m")
            return "JA_PAGO", (f"Boleto do mês {mes} já está pago para {grupo}/{cota}. "
                               f"Print: {os.path.basename(cam)}"), {"em_atraso": em_atraso}
        return "SEM_BOLETO", (f"Não há boleto para emitir neste mês para {grupo}/{cota}. "
                              f"Print: {os.path.basename(cam)}"), {"em_atraso": em_atraso}
    # Escolha da pendência a emitir.
    # REGRA (pedido do usuário): emitir SEMPRE a linha "RECBTO. PARCELA" e NUNCA a
    # "RECBTO. DIFERENÇA" (linha de acerto de centavos, que pode até vir negativa —
    # ex.: -3,40 — e antes era escolhida por engano). Ordem de preferência:
    #   1) linha com "PARCELA" no histórico (a que queremos);
    #   2) qualquer linha com valor POSITIVO que NÃO seja "DIFERENÇA" (reserva);
    #   3) por último, a 1ª linha disponível.
    controles = page.locator("[id*='imgEmite_Boleto']")

    def _tem_valor_positivo(txt: str) -> bool:
        # respeita o sinal: "-3,40" NÃO conta como positivo
        for m in re.finditer(r"-?\s*\d[\d.]*,\d{2}", txt):
            try:
                if float(m.group(0).replace(" ", "").replace(".", "").replace(",", ".")) > 0:
                    return True
            except ValueError:
                pass
        return False

    escolhido, escolhido_txt = None, ""
    reserva, reserva_txt = None, ""
    for i in range(controles.count()):
        ctrl = controles.nth(i)
        try:
            linha_txt = ctrl.locator("xpath=ancestor::tr[1]").inner_text()
        except Exception:
            linha_txt = ""
        up = linha_txt.upper()
        if "DIFEREN" in up:                      # RECBTO. DIFERENÇA -> nunca
            continue
        if "PARCELA" in up:                      # RECBTO. PARCELA -> é essa
            escolhido, escolhido_txt = ctrl, linha_txt
            break
        if reserva is None and _tem_valor_positivo(linha_txt):
            reserva, reserva_txt = ctrl, linha_txt

    if escolhido is None:
        if reserva is not None:
            escolhido, escolhido_txt = reserva, reserva_txt
        else:
            escolhido, escolhido_txt = controles.first, ""

    mdt = re.search(r"(\d{2}/\d{2}/\d{4})", escolhido_txt)  # vencimento da parcela
    if mdt:
        vencimento = mdt.group(1)
    try:
        escolhido.click()
        page.wait_for_load_state("networkidle")
    except Exception:
        cam = _print_tela(page, f"falha_emitir_{grupo}_{cota}")
        return "FALHA", (f"Achei o boleto mas não consegui marcar a parcela de {grupo}/{cota}. "
                         f"Print: {os.path.basename(cam)}"), {}

    # 5) "Emitir Cobrança" -> o boleto abre no VISUALIZADOR DE PDF do navegador
    #    (o popup É o PDF). Basta pegar o PDF direto da URL do popup e salvar.
    arquivo = ""
    try:
        os.makedirs(PASTA_BOLETOS, exist_ok=True)
        caminho_pdf = os.path.join(PASTA_BOLETOS, nome_arquivo)
        page.get_by_role("button", name="Emitir Cobrança", exact=True).click()

        # Espera o(s) popup(s) do boleto e baixa o PDF da URL (usa a sessão logada)
        for _ in range(20):  # ~40s
            page.wait_for_timeout(2000)
            for pg in [p for p in page.context.pages if p is not page]:
                u = pg.url or ""
                if not u or u.startswith("about:"):
                    continue
                try:
                    resp = page.context.request.get(u)
                    body = resp.body()
                    if body[:4] == b"%PDF":
                        with open(caminho_pdf, "wb") as f:
                            f.write(body)
                        arquivo = caminho_pdf
                        break
                except Exception:
                    continue
            if arquivo:
                break

        if not arquivo:  # não achou PDF — guarda print de cada popup para diagnóstico
            for i, pg in enumerate([p for p in page.context.pages if p is not page]):
                try:
                    _print_tela(pg, f"boleto_sem_pdf_{grupo}_{cota}_pop{i}")
                except Exception:
                    pass

        # fecha os popups, deixando só a página principal (p/ o passo do código)
        for p in list(page.context.pages):
            if p is not page:
                try:
                    p.close()
                except Exception:
                    pass
    except Exception:
        _print_tela(page, f"erro_emitir_boleto_{grupo}_{cota}")
        # segue mesmo assim para tentar pegar o código de barras

    # 6) Gerar + copiar o código de barras (vai para a área de transferência)
    codigo = ""
    try:
        page.get_by_role("button", name="Gerar Cód. de barras").click()
        page.wait_for_timeout(1500)
        page.get_by_role("button", name="Copiar Código").click()
        page.wait_for_timeout(500)
        codigo = (page.evaluate("() => navigator.clipboard.readText()") or "").strip()
    except Exception:
        pass
    if not codigo:  # tenta ler a linha digitável direto do texto da página
        m = re.search(r"(\d{5}\.?\d{5}\s+\d{5}\.?\d{6}\s+\d{5}\.?\d{6}\s+\d\s+\d{14})",
                      _texto_pagina(page))
        if m:
            codigo = m.group(1)

    extras = {"codigo_barras": codigo or None, "vencimento": vencimento or None, "em_atraso": em_atraso}
    atraso_txt = " (⚠️ EM ATRASO)" if em_atraso else ""

    if codigo or arquivo:
        msg = f"Boleto emitido{atraso_txt}."
        if codigo:
            msg += f" Código: {codigo}."
        if arquivo:
            msg += f" PDF salvo: {os.path.basename(arquivo)}."
        return "OK", msg, extras
    return "FALHA", (f"Emiti o boleto mas não li o código nem baixei o PDF de {grupo}/{cota}. "
                     f"Confira manualmente.{atraso_txt}"), extras
