# Robô de Oferta de Lances (Worker)

> **Robô único (novo):** `worker_consorbens.py` substitui o `worker_lances.py`
> **e** os 3 robôs separados de Gmail/Anglo. Um processo só, um log só
> (`logs/robo.log`), uma bolinha 🟢 SERVER só. Config a quente em
> `robo_config.toml`. Instalação passo a passo: **`SETUP_SEMPRE_LIGADO.md`**.
>
> - lê a `fila_automacao` e roda `LANCE` / `BOLETO` / `RELATORIO_COMISSAO` /
>   `COLETA_GRUPOS` / `COLETA_ASSEMBLEIAS` / `COLETA_TABELAS`
>   (dispatch por `HANDLERS` — adicionar função nova = 1 linha);
> - **cron interno** dispara Gmail Yamaha (qua 12h), Gmail Itaú (ter 12h) e
>   Importar Anglo (23h/dia) — sem Agendador de Tarefas do Windows;
> - `watchdog_robo.py` (tarefa "a cada 2 min") re-sobe o robô se travar.
>
> O restante deste README descreve o `worker_lances.py` original, que continua
> como base (LANCE/BOLETO são o mesmo código).

---

Este robô roda **no PC do escritório** (não no Streamlit Cloud). Ele lê os
pedidos de lance que o CRM grava na fila (`fila_automacao` no Supabase),
executa no Newcon e escreve o resultado de volta.

```
CRM (Streamlit nuvem) → grava pedido → [fila_automacao / Supabase] → Robô (este PC) → Newcon
                                    ↖ escreve status/mensagem ↙
```

## Instalação (só na 1ª vez)

Precisa de **Python 3.10+** instalado no PC.

```bash
cd worker
pip install -r requirements.txt
playwright install chromium
```

Depois copie o arquivo de configuração e preencha:

```bash
copy .env.exemplo .env      # Windows
```

Abra o `.env` e preencha `SUPABASE_URL` e `SUPABASE_KEY`.

**Login do Newcon:** o robô lê login e senha do **Cofre de Senhas do CRM**
(menu "Senhas"), na linha cuja empresa é o valor de `NEWCON_EMPRESA_COFRE`
(padrão: `YAMAHA NEWCON`). Assim, quando a senha do Newcon expirar, basta
atualizá-la lá no CRM que o robô pega a nova sozinho — não precisa mexer no `.env`.
(Os campos `NEWCON_LOGIN`/`NEWCON_SENHA` no `.env` são só uma reserva opcional.)

> ⚠️ O `.env` guarda a chave do Supabase — **nunca** suba ele para o GitHub.

## Como testar SEM tocar no Newcon (recomendado começar por aqui)

No `.env`, deixe:

```
MODO_SIMULACAO=true
```

Rode:

```bash
python worker_lances.py
```

Agora, no CRM, oferte um lance. Você verá o pedido mudar de
**⏳ Na fila → 🔄 Processando → ✅ Ofertado** sozinho. Isso prova que todo o
circuito CRM ↔ fila ↔ robô está funcionando. (A mensagem virá marcada como
"SIMULAÇÃO".)

## Ligar o Newcon de verdade (depois da Fase 0)

1. **Gravar o fluxo manual** uma vez:
   ```bash
   playwright codegen "COLE_A_URL_DO_NEWCON_AQUI" -o roteiro_newcon.py
   ```
   Faça o processo completo: login → achar a cota → ofertar o lance → até
   aparecer a mensagem de confirmação. Feche a janela; o `roteiro_newcon.py`
   guarda todos os cliques/seletores.

2. Me mande o `roteiro_newcon.py`. Com ele eu preencho os seletores no
   arquivo `newcon.py` (as funções `esta_logado`, `fazer_login`, `ofertar_lance`).

3. No `.env`, troque para `MODO_SIMULACAO=false` e rode de novo. Pronto.

## Arquivos

| Arquivo | Função |
|---|---|
| `worker_lances.py` | Loop principal: lê a fila e processa os pedidos |
| `newcon.py` | Miolo do Newcon (login + oferta) — completado após a Fase 0 |
| `.env` | Configuração/senhas (você cria a partir do `.env.exemplo`) |
| `newcon_sessao.json` | Sessão salva do Newcon (criado automaticamente no 1º login) |
