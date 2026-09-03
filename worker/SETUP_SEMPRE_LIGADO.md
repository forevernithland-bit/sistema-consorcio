# Robô único "sempre-ligado" — instalação no PC do escritório

O `worker_consorbens.py` substitui o `worker_lances.py` **e** os 3 robôs de
Gmail/Anglo. Um processo só, um log só (`worker/logs/robo.log`), uma bolinha
🟢 SERVER só.

Faça na ordem. Tudo é no **PC do escritório** (é lá que tem o login do Newcon,
o OAuth do Gmail e o Drive `G:\` montado).

---

## 0. Pré-requisitos (uma vez)

```bat
cd /d "G:\Meu Drive\CLODE\ERP_CONSORBENS\worker"
pip install -r requirements.txt
pip install google-api-python-client google-auth google-auth-oauthlib schedule
playwright install chromium
```

`worker\.env` já existe (SUPABASE_URL/KEY, NEWCON_URL…). Confirme que está lá.

---

## 1. Testar em SIMULAÇÃO (sem tocar no Newcon)

`robo_config.toml` já vem com `modo_simulacao = true`.

```bat
python worker_consorbens.py
```

- No ERP, a bolinha **SERVER** deve ficar 🟢 em segundos.
- Peça um **Lance** de teste pelo ERP → a fila deve virar `SUCESSO (SIMULAÇÃO)`.
- `worker\logs\robo.log` mostra o ciclo. `Ctrl+C` para parar.

Rodar um robô de API na hora (é seguro — Gmail é read-only):

```bat
python worker_consorbens.py --rodar-agora gmail_itau
python worker_consorbens.py --rodar-agora gmail_yamaha
python worker_consorbens.py --rodar-agora anglo --dry
```

---

## 2. Ligar de verdade

Edite `robo_config.toml`: `modo_simulacao = false`.
Opcional: `navegador_visivel = false` (janela do Chrome minimizada = "segundo
plano"). Suba de novo com `python worker_consorbens.py` e confira um **boleto**
real.

---

## 3. Subir sozinho quando o PC liga

1. `Win+R` → `shell:startup` → Enter (abre a pasta de Inicializar).
2. Crie ali um **atalho** para
   `G:\Meu Drive\CLODE\ERP_CONSORBENS\worker\iniciar_robo.bat`.
   (Botão direito na pasta → Novo → Atalho → aponte pro `.bat`.)
3. (Opcional, se o PC reinicia sozinho e ninguém loga) **logon automático do
   Windows**: `Win+R` → `netplwiz` → desmarque "Os usuários precisam digitar
   um nome…" → confirme com a senha. (Ou `AutoAdminLogon=1` no registro em
   `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`.)
4. **Regra de ouro:** ao sair, **bloqueie a tela** (`Win+L`) — **não faça
   logoff**. Logoff derruba o navegador headful e o robô para.

---

## 4. Watchdog (re-sobe se travar)

Agendador de Tarefas do Windows:

1. **Criar Tarefa** (não "básica").
2. Guia *Geral*: "Executar estando o usuário conectado ou não" **NÃO** — deixe
   "Executar somente quando o usuário estiver conectado".
3. Guia *Disparadores*: Novo → "Em uma agenda" → Diariamente → repetir a tarefa
   a cada **2 minutos** por **1 dia** (indefinidamente).
4. Guia *Ações*: Novo → Iniciar um programa
   - Programa: `python`
   - Argumentos: `watchdog_robo.py`
   - Iniciar em: `G:\Meu Drive\CLODE\ERP_CONSORBENS\worker`
5. Guia *Configurações*: "Se a tarefa já estiver em execução… **Não iniciar uma
   nova instância**".

O `watchdog_robo.py` lê `robo_status.atualizado_em`; se estiver > 3 min parado
(ou o `robo.pid` não estiver vivo), mata e re-executa o `iniciar_robo.bat`.
Log: `worker\logs\watchdog.log`.

---

## 5. Aposentar os 3 robôs antigos  ← FAZER DEPOIS QUE O ÚNICO ESTIVER OK

O robô único já faz o que eles faziam (timers no `robo_config.toml`).

**Agendador de Tarefas** → *Desativar* (não apagar, por segurança) as tarefas:

| Tarefa | Vinha de |
|---|---|
| download de "Tabelas Yamaha" | `CLODE\ATUALIZA_YAMAHA_TABELAS` (`run_yamaha.bat` / `ATUALIZAR_YAMAHA_AGORA.bat`) |
| download "Guia de Oportunidades Itaú" | `CLODE\GUIA_DE_OPORTUNIDADES_ITAU` |
| "Atualizar site Anglo" | `CLODE\IMPORTA_ANGLO_CONSORCIO` (`Atualizar-Site-Agora.bat`) |

**Inicializar** (`shell:startup`): apague os atalhos `Atualizar-Site.lnk` /
`ATUALIZAR_TUDO_AGORA` / `iniciar_robo - Atalho.lnk` **antigos** — fica só o
atalho novo do `iniciar_robo.bat`.

As pastas `credentials.json` / `token.pickle` / `config.json` **ficam onde
estão** — o robô único aponta pra elas (`robo_config.toml` → `[caminhos]`).

---

## Onde está cada coisa

| | |
|---|---|
| Supervisor | `worker/worker_consorbens.py` |
| Config (a quente) | `worker/robo_config.toml` |
| Log | `worker/logs/robo.log` · console: `worker/logs/console.log` |
| Estado do cron | `worker/robo_cron_estado.json` |
| Estado da coleta | `worker/robo_yamaha_progresso.json` (já existia) |
| PID | `worker/robo.pid` |
| Watchdog | `worker/watchdog_robo.py` → `worker/logs/watchdog.log` |
| Migração | `migracoes/22_fila_automacao_prioridade.sql` (rodar no Supabase do ERP) |

## Adicionar uma função nova ao robô

1. Escreva `h_minha_funcao(sb, pedido, ctx, cfg)` em `worker_consorbens.py`
   (ou um handler à parte e importe).
2. Uma linha em `HANDLERS = {... "MEU_TIPO": h_minha_funcao}`.
3. Se precisa do Newcon aberto, acrescente `"MEU_TIPO"` em `PRECISA_NEWCON`.
4. Se é tarefa agendada de API, ponha em `[timers]` no `robo_config.toml` e um
   ramo em `_rodar_timer()`.
