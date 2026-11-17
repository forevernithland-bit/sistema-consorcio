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
import base64
import unicodedata
from datetime import datetime, date
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
class NewconBloqueado(RuntimeError):
    """O firewall (Imperva) do Newcon barrou o navegador — não é problema de senha/sessão."""


def _checar_bloqueio(page: Page) -> None:
    try:
        txt = (page.inner_text("body", timeout=3000) or "").lower()
    except Exception:
        return
    if "this request was blocked by our security service" in txt or "access denied" in txt[:200]:
        raise NewconBloqueado("Newcon bloqueou o acesso (firewall Imperva, 'Access denied / Error 15'). "
                              "Costuma ser navegador headless ou IP bloqueado.")


def esta_logado(page: Page) -> bool:
    """Logado = a tela de login (campo de usuário) NÃO está visível."""
    _checar_bloqueio(page)   # página de bloqueio não tem campo de login e enganaria o teste abaixo
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


HOME_URL = "https://newkey.cny.com.br/Intranet/frmMain.aspx"


def garantir_sessao(page: Page, context: BrowserContext, login: str = None, senha: str = None) -> str:
    """Reaproveita a JANELA que já está aberta: volta pra home e, se a sessão
    caiu, loga de novo ALI MESMO (sem fechar/abrir navegador).
    Retorna 'ok' (já estava logado) | 'relogado' | levanta exceção se o navegador morreu
    ou se o login falhou (quem chama decide se trava)."""
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    # fecha abas/popups que sobraram de tarefas anteriores (relatórios, boletos)
    for p in list(context.pages):
        if p is not page:
            try:
                p.close()
            except Exception:
                pass
    page.goto(HOME_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    if esta_logado(page):
        return "ok"
    if not page.locator("#edtUsuario").count():
        page.goto(os.getenv("NEWCON_URL", HOME_URL), wait_until="domcontentloaded")
        if esta_logado(page):
            return "ok"
    if not (login and senha):
        raise RuntimeError("sessão do Newcon caiu e não tenho credencial para relogar")
    fazer_login(page, context, login, senha)
    try:
        import newcon_navegador
        newcon_navegador.registrar_login("garantir_sessao (sessão tinha caído)")
    except Exception:
        pass
    try:
        context.storage_state(path=STORAGE_STATE)
    except Exception:
        pass
    return "relogado"


# ------------------------------------------------------------------ oferta
# Modalidades da tela "Oferta de Lance" (radios ctl00_Conteudo_rgLance_N, value = sigla).
MODALIDADE_RADIO = {"Lance Livre": "LL", "Lance Fixo": "LF", "2º Lance Fixo": "LS",
                    "Lance Limitado": "LM", "Lance Fidelidade": "LI"}
MODALIDADE_ROTULO = {"Lance Livre": "Livre", "Lance Fixo": "Fixo", "2º Lance Fixo": "2º Fixo",
                     "Lance Limitado": "Limitado", "Lance Fidelidade": "Fidelidade"}


def _modalidade_canonica(t) -> str:
    s = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    if "2" in s and "fix" in s:
        return "2º Lance Fixo"
    if "fix" in s or not s.strip():
        return "Lance Fixo"          # padrão histórico do robô
    if "livre" in s:
        return "Lance Livre"
    if "limit" in s:
        return "Lance Limitado"
    if "fidel" in s:
        return "Lance Fidelidade"
    raise ValueError(f"modalidade de lance desconhecida: {t!r}")


def _pct_br(v) -> str:
    return f"{float(v):.4f}".replace(".", ",")


def ofertar_lance(page: Page, pedido: dict, timeout_confirmacao: int):
    """Retorna (status, mensagem, protocolo), onde status é:
       'OK'          -> lance ofertado agora com sucesso
       'JA_OFERTADO' -> a cota já tinha lance; não ofertamos de novo (traz protocolo/data)
       'FALHA'       -> falha de negócio (nome não confere, sem opção de lance, etc.)
       'SIMULADO'    -> pedido['simular'] = True: preencheu e clicou em "Simular...", NADA enviado
       pedido: grupo, cota, cliente, tipo_lance (Livre/Fixo/2º Fixo/Limitado/Fidelidade),
               pct_lance (Livre/Limitado/Fidelidade), pct_embutido, tipo_reducao, simular"""
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
    if m_data and not pedido.get("simular"):   # no teste (simular) segue para preencher
        data_lance = m_data.group(1)
        cam = _print_tela(page, f"ja_ofertado_{grupo}_{cota}")
        return "JA_OFERTADO", (f"Já estava ofertado em {data_lance}. "
                               f"Print: {os.path.basename(cam)}"), None

    # 5) Modalidade + forma de redução + % do lance + embutido (16/11/2026: todas as modalidades)
    #    Se a tela NÃO tem a modalidade pedida (formulário fechado — fora do prazo, cota
    #    já com lance ativo — ou o grupo não permite), é FALHA DE NEGÓCIO: não repete sozinho.
    tipo = _modalidade_canonica(pedido.get("tipo_lance"))
    valor_radio = MODALIDADE_RADIO[tipo]
    nome_curto = MODALIDADE_ROTULO[tipo]
    sel_radio = f"input[type=radio][id^='ctl00_Conteudo_rgLance'][value='{valor_radio}']"
    radio = page.locator(sel_radio)
    try:
        radio.first.wait_for(state="attached", timeout=12000)
        desligado = radio.first.is_disabled()
    except PWTimeout:
        desligado = None
    if desligado is None or desligado:
        try:
            opcoes = page.evaluate("""() => [...document.querySelectorAll('input[type=radio]')]
                .filter(r => (r.id||'').includes('rgLance'))
                .map(r => { const l = r.id && document.querySelector('label[for="'+r.id+'"]');
                            return (l ? l.innerText : r.value).trim() + (r.disabled ? ' (bloqueado)' : ''); })""")
        except Exception:
            opcoes = []
        aviso = ""
        m_av = re.search(r"([^\n]{0,80}(n[ãa]o (é )?permitid|n[ãa]o (est[áa] )?apt|encerrad|fora do per[íi]odo|"
                         r"inadimpl|n[ãa]o h[áa] assembleia|bloquead)[^\n]{0,80})", txt_oferta, re.I)
        if m_av:
            aviso = f" Aviso na tela: \"{m_av.group(1).strip()[:150]}\"."
        motivo = ("o grupo não libera essa modalidade" if desligado else
                  "o formulário de oferta está fechado (fora do prazo ou a cota já tem lance ativo)")
        cam = _print_tela(page, f"sem_opcao_{valor_radio}_{grupo}_{cota}")
        return "FALHA", (f"Sem a opção '{nome_curto}' na Oferta de Lance de {grupo}/{cota}: {motivo} "
                         f"(opções na tela: {', '.join(opcoes) or 'nenhuma'}).{aviso} "
                         f"Não repito sozinho — conferir a cota. Print: {os.path.basename(cam)}"), None
    radio.first.check()
    page.wait_for_load_state("networkidle")

    reducao = str(pedido.get("tipo_reducao") or "Reduzir Parcela")
    nome_red = "Reduzir Prazo" if "prazo" in reducao.lower() else "Reduzir Parcela"
    try:
        page.get_by_role("radio", name=nome_red).check()
    except Exception:   # fallback pelo id (0 = Prazo, 1 = Parcela)
        page.locator("#ctl00_Conteudo_rblFormasLance_" + ("0" if nome_red == "Reduzir Prazo" else "1")).check()
    page.wait_for_load_state("networkidle")

    # % do lance: no Fixo/2º Fixo o Newcon preenche sozinho; nas outras a gente digita.
    pct_lance = pedido.get("pct_lance")
    if valor_radio in ("LL", "LM", "LI"):
        if not pct_lance:
            return "FALHA", f"Pedido de {nome_curto} sem % de lance ({grupo}/{cota}).", None
        try:
            page.locator("#ctl00_Conteudo_rblTipoOferta").select_option(label="Percentual")
        except Exception:
            pass
        campo = page.locator("#ctl00_Conteudo_edtOferta")
        if not campo.is_enabled():
            cam = _print_tela(page, f"oferta_bloqueada_{valor_radio}_{grupo}_{cota}")
            return "FALHA", (f"No {nome_curto} de {grupo}/{cota} o campo do % do lance está bloqueado no "
                             f"Newcon. Print: {os.path.basename(cam)}"), None
        campo.fill(_pct_br(pct_lance))
        try:
            campo.press("Tab")
            page.wait_for_load_state("networkidle")
        except Exception:
            pass

    emb_txt = _pct_br(pct_embutido)  # ex: 15.0 -> "15,0000"
    try:
        page.locator("#ctl00_Conteudo_cbxLanceEmbutido").select_option(label="Percentual")
    except Exception:
        pass
    campo_emb = page.locator("#ctl00_Conteudo_edtEmbutido")
    if campo_emb.count() and not campo_emb.is_enabled():
        # nessa modalidade o grupo NÃO aceita embutido (campo travado no Newcon)
        if pct_embutido > 0:
            cam = _print_tela(page, f"sem_embutido_{valor_radio}_{grupo}_{cota}")
            return "FALHA", (f"No {nome_curto} do grupo {grupo} o Newcon não aceita lance embutido "
                             f"(campo travado). Refaça com embutido 0% (tudo com recursos próprios). "
                             f"Print: {os.path.basename(cam)}"), None
    else:
        campo_emb.fill(emb_txt)
        try:
            campo_emb.press("Tab")
            page.wait_for_load_state("networkidle")
        except Exception:
            pass

    # 5.1) MODO SIMULAR (teste / conferência): clica em "Simular..." e PARA. Nunca confirma.
    # anota os alertas do Newcon (quem aceita/recusa é outro handler). Um ouvinte só por página.
    avisos = getattr(page, "_avisos_newcon", None)
    if avisos is None:
        avisos = []
        page.on("dialog", lambda d: avisos.append(d.message))
        try:
            page._avisos_newcon = avisos
        except Exception:
            pass
    avisos.clear()
    if pedido.get("simular"):
        antes = _texto_pagina(page)
        # lê o % ANTES do clique: depois do "Simular..." o campo some da tela (dava "lance ?%")
        try:
            oferta = page.locator("#ctl00_Conteudo_edtOferta").first.input_value(timeout=3000) or "?"
        except Exception:
            oferta = "?"
        try:
            page.locator("#ctl00_Conteudo_btnSimula").click(timeout=20000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
            if avisos:
                cam = _print_tela(page, f"simulado_aviso_{valor_radio}_{grupo}_{cota}")
                try:
                    page.goto(HOME_URL, wait_until="domcontentloaded")
                except Exception:
                    pass
                return "FALHA", (f"SIMULAÇÃO recusada pelo Newcon ({nome_curto} {grupo}/{cota}): "
                                 f"\"{' / '.join(avisos)[:300]}\". Print: {os.path.basename(cam)}"), None
        except Exception as e:
            cam = _print_tela(page, f"simular_erro_{grupo}_{cota}")
            return "FALHA", f"Simular não respondeu: {str(e)[:120]}. Print: {os.path.basename(cam)}", None
        depois = _texto_pagina(page)
        novas = [l.strip() for l in depois.splitlines() if l.strip() and l.strip() not in antes][:25]
        cam = _print_tela(page, f"simulado_{valor_radio}_{grupo}_{cota}")
        if oferta == "?":
            m_pe = re.search(r"%\s*do\s*Lance[:\s]*([\d.,]+)", depois, re.I)
            if m_pe:
                oferta = m_pe.group(1)
        # sai sem gravar nada. NÃO clica em "Cancelar" (nessa tela ele pode cancelar
        # uma oferta já registrada) — só volta para a home.
        try:
            page.goto(HOME_URL, wait_until="domcontentloaded")
        except Exception:
            pass
        return "SIMULADO", (f"SIMULAÇÃO (nada enviado): {nome_curto}, lance {oferta}%, embutido {emb_txt}%, "
                            f"{nome_red}. Tela: {' | '.join(novas)[:600]}. Print: {os.path.basename(cam)}"), None

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
        return "OK", (f"{tipo} ofertado ({nome_red}, embutido {emb_txt}%). Protocolo {prot_txt}. "
                      f"Comprovante: {os.path.basename(cam)}"), prot_log

    if avisos:   # o Newcon recusou com um alerta (ex.: "Cota não está apta para ... fidelidade")
        return "FALHA", (f"O Newcon recusou o {nome_curto} de {grupo}/{cota}: \"{' / '.join(avisos)[:300]}\". "
                         f"Confira no Newcon. Print: {os.path.basename(cam)}"), None
    # ZONA SENSÍVEL: não vimos o comprovante — o lance PODE ter ido. Não repetir sozinho.
    return "FALHA", (f"Cliquei em Confirmar, mas não confirmei o comprovante em {timeout_confirmacao}s. "
                     f"CONFIRA MANUALMENTE no Newcon antes de repetir — o lance pode ter sido "
                     f"registrado. Print: {os.path.basename(cam)}"), None


# ------------------------------------------------------------------ boleto
# Onde salvar os PDFs dos boletos (no PC do escritório). Configurável no .env.
PASTA_BOLETOS = os.getenv("PASTA_BOLETOS", r"G:\Meu Drive\CONSORBENS\IMAGENS\Boletos")

# JS que lê o conteúdo da própria aba (serve para blob: e data:) e devolve base64.
_JS_ABA_PARA_B64 = """async (u) => {
    const r = await fetch(u); const b = await r.blob();
    const buf = await b.arrayBuffer(); const bytes = new Uint8Array(buf);
    let s = ''; for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
}"""


def _extrair_pdf_da_aba(pg, cap, so_se_pdf_url=False):
    """Tenta extrair os bytes de um PDF de uma aba, seja a URL http(s), blob: ou data:.
    Guarda o resultado em cap['pdf']. Best-effort — nunca levanta erro."""
    if cap.get("pdf"):
        return
    try:
        u = pg.url or ""
    except Exception:
        return
    if not u or u.startswith("about:"):
        return
    low = u.lower()
    if so_se_pdf_url and not (low.endswith(".pdf") or low.startswith("blob:")
                              or low.startswith("data:") or "pdf" in low):
        return
    try:
        if u.startswith("blob:") or u.startswith("data:"):
            try:
                pg.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            b64 = pg.evaluate(_JS_ABA_PARA_B64, u)
            if b64:
                raw = base64.b64decode(b64)
                if raw[:4] == b"%PDF":
                    cap["pdf"] = raw
            return
        # http(s): usa a APIRequestContext do contexto (herda os cookies da sessão)
        resp = pg.context.request.get(u)
        body = resp.body()
        if body[:4] == b"%PDF":
            cap["pdf"] = body
    except Exception:
        pass


def _linha_digitavel_do_pdf(caminho_pdf):
    """Lê a linha digitável (e o vencimento impresso) direto do texto do PDF do boleto.
    É o jeito mais confiável: não depende de clipboard nem de botão da tela.
    Retorna (codigo, vencimento) — '' quando não achar."""
    try:
        try:
            import fitz
            txt = "".join(pg.get_text() for pg in fitz.open(caminho_pdf))
        except ImportError:
            from PyPDF2 import PdfReader
            txt = "\n".join((pg.extract_text() or "") for pg in PdfReader(caminho_pdf).pages)
    except Exception:
        return "", ""
    m = re.search(r"(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14})", txt)
    cod = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    venc = ""
    try:       # a data do cantinho "Vencimento" (canto superior direito) — não a do documento
        import fitz
        pg0 = fitz.open(caminho_pdf)[0]
        datas = [w for w in pg0.get_text("words")
                 if re.fullmatch(r"\d{2}/\d{2}/\d{4}", w[4]) and w[0] > pg0.rect.width * 0.7 and w[1] < pg0.rect.height * 0.25]
        if datas:
            venc = sorted(datas, key=lambda w: w[1])[0][4]
    except Exception:
        pass
    if not venc:
        mv = re.search(r"Vencimento\s*(\d{2}/\d{2}/\d{4})", txt)
        venc = mv.group(1) if mv else ""
    return cod, venc


def _valor_positivo(txt: str) -> bool:
    # respeita o sinal: "-3,40" NÃO conta como positivo
    for m in re.finditer(r"-?\s*\d[\d.]*,\d{2}", txt):
        try:
            if float(m.group(0).replace(" ", "").replace(".", "").replace(",", ".")) > 0:
                return True
        except ValueError:
            pass
    return False


def _classificar_pendencias(page: Page):
    """Lê o grid de pendências da 'Emissão Boleto Avulso' e separa por vencimento:
       'mes'    -> parcelas que vencem NO MÊS VIGENTE (boleto do mês);
       'atraso' -> parcelas com vencimento ANTES do 1º dia do mês (boleto em atraso);
       parcelas futuras são ignoradas; 'RECBTO. DIFERENÇA' nunca entra.
    Retorna {'mes': [linhas], 'atraso': [linhas]}; cada linha = {i, venc(date|None), txt}."""
    hoje = date.today()
    ini_mes = hoje.replace(day=1)
    fim_mes = (date(hoje.year + 1, 1, 1) if hoje.month == 12 else date(hoje.year, hoje.month + 1, 1))
    controles = page.locator("[id*='imgEmite_Boleto']")
    res = {"mes": [], "atraso": []}
    for i in range(controles.count()):
        try:
            txt = controles.nth(i).locator("xpath=ancestor::tr[1]").inner_text()
        except Exception:
            txt = ""
        up = txt.upper()
        if "DIFEREN" in up:                          # RECBTO. DIFERENÇA -> nunca
            continue
        if "PARCELA" not in up and not _valor_positivo(txt):
            continue
        md = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
        venc = None
        if md:
            try:
                venc = date(int(md.group(3)), int(md.group(2)), int(md.group(1)))
            except ValueError:
                venc = None
        lin = {"i": i, "venc": venc, "txt": txt}
        if venc is None or ini_mes <= venc < fim_mes:
            res["mes"].append(lin)
        elif venc < ini_mes:
            res["atraso"].append(lin)
        # venc >= fim_mes: parcela futura, não emite
    return res


def _emitir_e_baixar(page: Page, grupo: str, cota: str, nome_arquivo: str):
    """Com as parcelas JÁ marcadas na tela: 'Emitir Cobrança', baixa o PDF e lê o código.
    Retorna (caminho_pdf|'', codigo, vencimento_do_pdf)."""
    arquivo = ""
    ctx = page.context
    _antes = set(ctx.pages)      # só mexe nas abas abertas durante esta emissão (nunca nas do navegador único)

    def _novas():
        return [p for p in ctx.pages if p is not page and p not in _antes]
    _cap = {"pdf": None}

    def _on_download(dl):
        try:
            tmp = dl.path()            # bloqueia até o download terminar
            if tmp and os.path.exists(tmp):
                with open(tmp, "rb") as fh:
                    b = fh.read()
                if b[:4] == b"%PDF":
                    _cap["pdf"] = b
        except Exception:
            pass

    def _clicar_baixar_em(alvo):
        """Procura 'Baixar'/'Download'/'Imprimir' no alvo e em qualquer iframe dele."""
        try:
            frames = [alvo] + list(getattr(alvo, "frames", []) or [])
        except Exception:
            frames = [alvo]
        for fr in frames:
            for papel in ("button", "link"):
                for nome in ("Baixar", "Download", "Imprimir", "Salvar"):
                    try:
                        el = fr.get_by_role(papel, name=nome)
                        if el.count():
                            el.first.click(timeout=4000)
                            return True
                    except Exception:
                        pass
        return False

    ctx.on("download", _on_download)
    try:
        os.makedirs(PASTA_BOLETOS, exist_ok=True)
        caminho_pdf = os.path.join(PASTA_BOLETOS, nome_arquivo)

        # 5.1 "Emitir Cobrança" — clica UMA vez; se abrir popup de confirmação, ok
        try:
            with ctx.expect_page(timeout=8000):
                page.get_by_role("button", name="Emitir Cobrança", exact=True).click()
        except PWTimeout:
            pass                       # clicou, só não abriu popup — segue
        except Exception:
            _print_tela(page, f"erro_emitir_boleto_{grupo}_{cota}")
        page.wait_for_timeout(1500)

        # 5.2 abre a tela de relatório do boleto (nova aba) e clica "Baixar"
        rel_url = ("https://newkey.cny.com.br/Intranet/CONCO/frmConCoRelBoletoAvulso.aspx")
        if "/Intranet/" in (page.url or ""):
            rel_url = re.sub(r"(https?://[^/]+/Intranet/).*", r"\1CONCO/frmConCoRelBoletoAvulso.aspx",
                             page.url)
        rel = None
        try:
            with ctx.expect_page(timeout=8000) as pinfo:
                page.evaluate("u => window.open(u, '_blank')", rel_url)
            rel = pinfo.value
        except Exception:
            rel = None
        clicou_baixar = False
        for alvo in ([rel] if rel else []) + _novas():
            try:
                alvo.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            if _clicar_baixar_em(alvo):
                clicou_baixar = True
                break
        # fallback: popup bloqueado -> navega a própria página para o relatório,
        # clica "Baixar" e volta (para o passo do código de barras).
        if not clicou_baixar and not _cap["pdf"]:
            try:
                page.goto(rel_url)
                page.wait_for_load_state("networkidle", timeout=8000)
                _clicar_baixar_em(page)
                page.wait_for_timeout(2500)
                page.go_back()
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

        # 5.3 espera o PDF (download OU aba com PDF/blob/data) por até ~40s
        for _ in range(20):
            if _cap["pdf"]:
                break
            page.wait_for_timeout(2000)
            for pg in _novas():
                _extrair_pdf_da_aba(pg, _cap)
                if _cap["pdf"]:
                    break
            if not _cap["pdf"]:            # o PDF pode ter substituído a própria página
                _extrair_pdf_da_aba(page, _cap, so_se_pdf_url=True)

        if _cap["pdf"]:
            with open(caminho_pdf, "wb") as f:
                f.write(_cap["pdf"])
            arquivo = caminho_pdf
        else:                             # não veio PDF — diagnóstico
            for i, pg in enumerate(_novas()):
                try:
                    _print_tela(pg, f"boleto_sem_pdf_{grupo}_{cota}_pop{i}")
                except Exception:
                    pass
            _print_tela(page, f"boleto_sem_pdf_{grupo}_{cota}_principal")
    except Exception:
        _print_tela(page, f"erro_emitir_boleto_{grupo}_{cota}")
        # segue mesmo assim para tentar pegar o código de barras
    finally:
        try:
            ctx.remove_listener("download", _on_download)
        except Exception:
            pass
        # fecha os popups, deixando só a página principal (p/ o passo do código)
        for p in _novas():
            if True:
                try:
                    p.close()
                except Exception:
                    pass


    # 6) Código de barras: 1º do próprio PDF; senão pelos botões da tela (clipboard)
    codigo, venc_pdf = "", ""
    if arquivo:
        codigo, venc_pdf = _linha_digitavel_do_pdf(arquivo)
    if not codigo:
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


    return arquivo, codigo, venc_pdf


def _tela_pendencias(page: Page):
    """(Re)abre 'Emissão de Cobrança' da cota que está na tela."""
    page.get_by_role("link", name="Emissão de Cobrança").click()
    page.wait_for_load_state("networkidle")


def _marcar_linhas(page: Page, linhas):
    """Marca no grid as linhas dadas (1 postback por clique) e confere se ficaram marcadas."""
    for lin in linhas:
        ctrl = page.locator("[id*='imgEmite_Boleto']").nth(lin["i"])
        ctrl.click()
        page.wait_for_load_state("networkidle")
        try:
            if not ctrl.is_checked():
                ctrl.click()
                page.wait_for_load_state("networkidle")
        except Exception:
            pass


def gerar_boleto(page: Page, pedido: dict, timeout: int):
    """Emite o(s) boleto(s) de uma cota no Newcon, baixa o PDF e lê o código de barras.

    REGRA (Breno, 17/11/2026): o boleto é SEMPRE o do mês vigente. Se a cota tiver parcela
    em atraso, emite DOIS boletos separados: o do mês e o de atraso (todas as parcelas
    atrasadas juntas num só, com multa/juros do Newcon). Parcela futura nunca é emitida.

    Arquivos: primeiroNome_grupo_cota.pdf (mês) e primeiroNome_grupo_cota_atraso.pdf (atraso).

    Retorna (status, mensagem, extras). extras = {codigo_barras, vencimento, em_atraso} do boleto
    principal (o do mês; se só houver atraso, o de atraso) + extras['adicionais'] = lista de
    {codigo_barras, vencimento, em_atraso, arquivo, mensagem} dos demais boletos."""
    grupo = str(pedido.get("grupo", "")).strip()
    cota = str(pedido.get("cota", "")).strip()

    # Nome do arquivo do PDF: primeiroNome_grupo_cota.pdf (sem acento/caractere inválido)
    _prim = str(pedido.get("cliente", "")).strip().split(" ")[0]
    _prim = unicodedata.normalize("NFKD", _prim).encode("ascii", "ignore").decode()
    _prim = re.sub(r"[^A-Za-z0-9]", "", _prim) or "cliente"
    nome_mes = f"{_prim}_{grupo}_{cota}.pdf"
    nome_atraso = f"{_prim}_{grupo}_{cota}_atraso.pdf"

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

    texto = _texto_pagina(page)

    # 3) Sem nenhuma pendência para emitir: pago ou sem boleto no mês
    if page.locator("[id*='imgEmite_Boleto']").count() == 0:
        cam = _print_tela(page, f"sem_emitir_{grupo}_{cota}")
        if re.search(r"\bpag[oa]\b|quitad|liquidad|baixad", texto, re.I):
            mes = datetime.now().strftime("%m")
            return "JA_PAGO", (f"Boleto do mês {mes} já está pago para {grupo}/{cota}. "
                               f"Print: {os.path.basename(cam)}"), {"em_atraso": False}
        return "SEM_BOLETO", (f"Não há boleto para emitir neste mês para {grupo}/{cota}. "
                              f"Print: {os.path.basename(cam)}"), {"em_atraso": False}

    pend = _classificar_pendencias(page)
    if not pend["mes"] and not pend["atraso"]:
        cam = _print_tela(page, f"sem_parcela_mes_{grupo}_{cota}")
        return "SEM_BOLETO", (f"Nenhuma parcela do mês nem em atraso para {grupo}/{cota} "
                              f"(só parcelas futuras ou diferença). Print: {os.path.basename(cam)}"), {"em_atraso": False}

    # 4) Quais boletos emitir (ordem: mês primeiro, depois atraso)
    plano = []
    if pend["mes"]:
        plano.append(("mes", nome_mes))
    if pend["atraso"]:
        plano.append(("atraso", nome_atraso))

    resultados = []   # {tipo, arquivo, codigo, vencimento, em_atraso}
    falhas = []
    for n, (tipo, nome_arq) in enumerate(plano):
        try:
            if n > 0:
                _tela_pendencias(page)                       # volta ao grid limpo
                pend = _classificar_pendencias(page)
            linhas = pend[tipo]
            if not linhas:
                falhas.append(f"{tipo}: sumiu do grid depois da 1ª emissão")
                continue
            _marcar_linhas(page, linhas)

            # Guarda: não emitir se o "Total a receber" da tela não for positivo
            try:
                _mtot = re.search(r"Total a receber\D{0,20}?(-?\s*[\d.]+,\d{2})", _texto_pagina(page), re.I)
                if _mtot:
                    _val = float(_mtot.group(1).replace(" ", "").replace(".", "").replace(",", "."))
                    if _val <= 0:
                        cam = _print_tela(page, f"boleto_total_invalido_{tipo}_{grupo}_{cota}")
                        falhas.append(f"{tipo}: Total a receber {_mtot.group(1).strip()} (não emiti). "
                                      f"Print: {os.path.basename(cam)}")
                        continue
            except Exception:
                pass

            arquivo, codigo, venc_pdf = _emitir_e_baixar(page, grupo, cota, nome_arq)
            venc_linha = min((l["venc"] for l in linhas if l["venc"]), default=None)
            venc = venc_pdf or (venc_linha.strftime("%d/%m/%Y") if venc_linha else "")
            if codigo and any(r["codigo"] == codigo for r in resultados):
                falhas.append(f"{tipo}: o PDF veio igual ao boleto anterior (mesmo código) — não gravei")
                continue
            if codigo or arquivo:
                resultados.append({"tipo": tipo, "arquivo": arquivo, "codigo": codigo,
                                   "vencimento": venc, "em_atraso": tipo == "atraso"})
            else:
                falhas.append(f"{tipo}: emiti mas não li o código nem baixei o PDF")
        except Exception as e:
            _print_tela(page, f"erro_boleto_{tipo}_{grupo}_{cota}")
            falhas.append(f"{tipo}: {type(e).__name__}: {str(e)[:100]}")

    # sem boleto de atraso nesta rodada: remove PDF de atraso velho (evita mandar boleto vencido)
    if not pend["atraso"]:
        try:
            velho = os.path.join(PASTA_BOLETOS, nome_atraso)
            if os.path.exists(velho):
                os.remove(velho)
        except Exception:
            pass

    if not resultados:
        return "FALHA", (f"Não consegui emitir o boleto de {grupo}/{cota}. "
                         f"{' | '.join(falhas)} Confira manualmente."), {}

    prim = resultados[0]
    extras = {"codigo_barras": prim["codigo"] or None, "vencimento": prim["vencimento"] or None,
              "em_atraso": prim["em_atraso"]}
    adicionais = []
    for r in resultados[1:]:
        adicionais.append({"codigo_barras": r["codigo"] or None, "vencimento": r["vencimento"] or None,
                           "em_atraso": r["em_atraso"],
                           "mensagem": ("Boleto EM ATRASO emitido." if r["em_atraso"] else "Boleto do mês emitido.")
                                       + (f" Código: {r['codigo']}." if r["codigo"] else "")
                                       + (f" PDF salvo: {os.path.basename(r['arquivo'])}." if r["arquivo"] else "")})
    if adicionais:
        extras["adicionais"] = adicionais

    partes = []
    for r in resultados:
        rot = "EM ATRASO" if r["em_atraso"] else "do mês"
        t = f"Boleto {rot} (venc. {r['vencimento'] or '?'})"
        if r["codigo"]:
            t += f" código {r['codigo']}"
        if r["arquivo"]:
            t += f", PDF {os.path.basename(r['arquivo'])}"
        partes.append(t)
    msg = "Boleto emitido: " + " + ".join(partes) + "."
    if falhas:
        msg += " ATENÇÃO, faltou: " + " | ".join(falhas) + "."
    return "OK", msg, extras
