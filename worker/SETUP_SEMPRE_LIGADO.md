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

## 2b. Trava de segurança do login do Newcon (importante)

Se o robô tentar logar no Newcon e a **senha estiver errada/expirada**, ele
**para de tentar na hora** — só 1 tentativa. Isso evita bloquear a conta do
Newcon com tentativas repetidas (o que travaria o Breno/Uriel também).

Quando isso acontece:

- Ele cria `worker\robo_login_travado.json` (fica lá **mesmo se o robô
  reiniciar** — ele lembra que a última senha estava errada).
- **Lance / boleto / coleta ficam parados** (as tarefas esperam na fila).
- **Gmail Yamaha / Gmail Itaú / Anglo continuam rodando** (não usam o Newcon).
- O `robo.log` repete o aviso a cada ~15 min.

**Pra voltar ao normal** (só quando você tiver CERTEZA que a senha nova está
certa):

1. Atualize a senha do Newcon na aba **Senhas** do CRM (empresa `YAMAHA NEWCON`).
2. Rode:
   ```bash
   python worker_consorbens.py --destravar-login
   ```
   (pode rodar numa janela separada, com o robô ligado — ele pega no próximo ciclo)

O robô **nunca** destrava sozinho — é sempre você que dá o OK.

---

## 3. Subir sozinho quando o PC liga — SEM JANELA

**Jeito fácil:** botão direito em **`INSTALAR_ROBO.bat`** → *Executar como
administrador*. Ele cria o atalho de inicialização **e** a tarefa do watchdog
de uma vez. Pronto — pula pro passo 5.

**Na mão** (se o `.bat` não rolar):

1. `Win+R` → `shell:startup` → Enter (abre a pasta de Inicializar).
2. Crie ali um **atalho** para
   `G:\Meu Drive\CLODE\ERP_CONSORBENS\worker\iniciar_robo_oculto.vbs`
   (o `.vbs`, não o `.bat`). Ele sobe o robô **sem nenhuma janela** — não tem
   o que fechar sem querer. Os logs continuam em `worker\logs\robo.log`.
3. **Pra espiar o robô** quando bater a ansiedade: dá 2 cliques em
   `worker\ver_robo.bat`. Abre uma janelinha azul que mostra o log **ao vivo**;
   pode fechar essa janela à vontade que **não para o robô** (é só leitura).
5. (Opcional, se o PC reinicia sozinho e ninguém loga) **logon automático do
   Windows**: `Win+R` → `netplwiz` → desmarque "Os usuários precisam digitar
   um nome…" → confirme com a senha. (Ou `AutoAdminLogon=1` no registro em
   `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`.)
6. **Regra de ouro:** ao sair, **bloqueie a tela** (`Win+L`) — **não faça
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
atalho novo (`Robo Consorbens.lnk`, criado pelo `INSTALAR_ROBO.bat`).

### ⚠️ NÃO apague as pastas dos robôs antigos

O robô único **importa o código deles**. Devem continuar existindo:
- `CLODE\ATUALIZA_YAMAHA_TABELAS\scripts\` (com `download_attachments.py`,
  `config.py`, `credentials.json`, `token.pickle`)
- `CLODE\GUIA_DE_OPORTUNIDADES_ITAU\scripts\` (idem)
- `CLODE\IMPORTA_ANGLO_CONSORCIO\` (`atualizar_cartas.py` + a credencial em
  `%LOCALAPPDATA%\Consorbens\config.json`)

O que dá pra apagar sem dó: os **atalhos do desktop** ("Atualizar-Site",
"ATUALIZAR_...") e os `.bat` de execução manual (`ATUALIZAR_*_AGORA.bat`) —
são só lançadores. Se quiser manter 1 pra debug, mantenha; o robô não usa.

---

## Comandos úteis (rodar numa janela à parte, com o robô ligado)

```bash
# ver o log ao vivo (ou 2 cliques em ver_robo.bat)
powershell Get-Content logs\robo.log -Wait -Tail 40

# forçar um timer agora (Gmail é read-only, seguro)
python worker_consorbens.py --rodar-agora gmail_itau
python worker_consorbens.py --rodar-agora anglo --dry

# FURAR A FILA: pausa a coleta atual (salva progresso), roda isto primeiro, retoma
python worker_consorbens.py --fazer-agora COLETA_ASSEMBLEIAS
python worker_consorbens.py --fazer-agora RELATORIO_COMISSAO --payload "{\"mes\":\"2026-08\"}"

# senha do Newcon travou? corrija na aba Senhas do CRM e:
python worker_consorbens.py --destravar-login
```

---

## Onde está cada coisa

| | |
|---|---|
| Supervisor | `worker/worker_consorbens.py` |
| Config (a quente) | `worker/robo_config.toml` |
| Subir sem janela | `worker/iniciar_robo_oculto.vbs` (atalho no startup) |
| Ver o log ao vivo | `worker/ver_robo.bat` (fechar não para o robô) |
| Instalar startup+watchdog | `worker/INSTALAR_ROBO.bat` (como admin) |
| Log | `worker/logs/robo.log` · console: `worker/logs/console.log` |
| Estado do cron | `worker/robo_cron_estado.json` |
| Estado da coleta | `worker/robo_yamaha_progresso.json` (já existia) |
| Trava de login do Newcon | `worker/robo_login_travado.json` (persiste; some com `--destravar-login`) |
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
