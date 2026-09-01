# Projeto — Robô único Consorbens + integração da skill com o Simulador

> **Status:** documento de projeto (rascunho para alinhamento). Nada aqui está
> implementado. Serve de base para o acordo entre **TI / Arquitetura** e
> **Analista de Dados** antes de escrever código na próxima rodada.
>
> Contexto imediato: nesta rodada o `yamaha.html` ganhou o fluxo
> **produto → grupo (Base de Dados injetada) → autofill de crédito/prazo/taxa →
> média de lance livre → proposta do cliente com logo Consorbens**. O passo
> seguinte é o robô fazer essa cadeia sozinho a partir de um comando em
> português.

---

## 1. Visão (o que o Uriel/Breno pediram)

1. **Um robô só.** Toda a inteligência que já ensinamos à Consorbens vive num
   **único processo** no PC do escritório:

   *Precisam do navegador Newcon:*
   - **Lance** (Ofertar Lance → Newcon) — já funciona (`worker_lances.py` / `newcon.py`).
   - **Boletos** (Emissão de Cobrança → PDF + código de barras) — já funciona.
   - **Busca de grupos / planos / faixas de crédito / vagas** (`coletar_grupos.py`).
   - **Resultado de assembleias / média de lance real** (`coletar_assembleias.py`).
   - **Relatórios de comissão** (download no Newcon, leitura de PDF).
   - **Planejamento de simulação** (`planejar.py` / `robo_yamaha.py`) + **driver do `yamaha.html`** (novo).

   *Não precisam de navegador (só HTTP / API) — hoje são robôs SEPARADOS que o
   Uriel quer trazer pra cá (ver 7.9):*
   - **Importar cartas da Anglo** → `IMPORTA_ANGLO_CONSORCIO/atualizar_cartas.py`:
     baixa da API JSON da Anglo, aplica ágio + termômetro, grava no **Supabase
     do SITE** (projeto `gvgwphsmdbmzifpwrevp`, não o do ERP), substituindo só o
     fornecedor "Anglo Consórcios". Sem navegador, ~2 s. Hoje roda 23h/dia via
     Agendador. É o que alimenta a skill `cartas-contempladas-consorbens`.
   - **Baixar tabelas do Gmail** → dois scripts iguais
     (`ATUALIZA_YAMAHA_TABELAS/scripts/download_attachments.py` e
     `GUIA_DE_OPORTUNIDADES_ITAU/scripts/download_attachments.py`): Gmail API
     (readonly), baixam os anexos pra `G:\Meu Drive\CONSORBENS\Tabelas\{YAMAHA,ITAU}`.
     Yamaha: busca "Tabelas Yamaha", quarta 12h. Itaú: `subject:"GUIA DE
     OPORTUNIDADES" "Itaú"`, terça 12h. É o que alimenta o `coletar_tabelas_yamaha.py`
     e o simulador "Oportunidades Itaú".
2. **Sempre ligado, na escuta.** O robô fica de pé o tempo todo, ouvindo uma
   fila de pedidos, e executa assim que chega tarefa — sem alguém rodar script
   na mão.
3. **Comando em linguagem natural.** O usuário fala com o Clode:
   > "Gera um simulado para um cliente que quer R$ 100.000 de crédito para
   > veículos, prazo longo."
   e o robô resolve a cadeia inteira: checar base → atualizar o que estiver
   vencido → escolher os melhores grupos → rodar o simulador → devolver a
   proposta pronta no modelo do cliente.
4. **Fica mais inteligente com o tempo:** cada coleta alimenta o histórico
   (`yamaha_contemplacoes`, `yamaha_assembleias`), e as decisões de ranking
   passam a usar mais dados reais.

---

## 2. Arquitetura — consolidar no que já existe

Já temos o esqueleto certo; falta unificar:

| Peça existente | Papel | O que muda |
|---|---|---|
| Tabela `fila_automacao` (Supabase) | pedidos PENDENTE → PROCESSANDO → OK/ERRO | **passa a aceitar mais tipos** (hoje: LANCE, BOLETO) |
| `worker/worker_lances.py` (loop) | lê a fila, executa LANCE/BOLETO, escreve resultado | vira **supervisor único** `worker_consorbens.py` |
| `worker/newcon.py` | miolo Newcon (login, navegação, ler comprovante) | reusado por todas as tarefas |
| `coletar_grupos.py` / `coletar_assembleias.py` / `planejar.py` | hoje scripts avulsos | viram **handlers** chamados pelo supervisor (mantêm o `if __name__=='__main__'` pra rodar solto também) |
| `robo_status` (heartbeat) + bolinha 🟢 SERVER | mostra se o robô está vivo | já serve pro "sempre ligado" |
| `senhas_sistema` (cofre) | credencial Newcon num lugar só | reusado |

### 2.1 Tipos de tarefa na `fila_automacao` (proposta)

| `tipo` | payload | handler |
|---|---|---|
| `LANCE` | grupo, cota, pct_lance/embutido/proprio | `newcon.ofertar_lance` (existe) |
| `BOLETO` | grupo, cota | `newcon.gerar_boleto` (existe) |
| `RELATORIO_COMISSAO` | mês/ano | rotina de download+parse (existe, avulsa) |
| `COLETA_GRUPOS` | produto, credito, n_grupos, prazo | `coletar_grupos.py` |
| `COLETA_ASSEMBLEIAS` | grupos[], assembleias, tipo_bem | `coletar_assembleias.py` |
| `COLETA_TABELAS` | — | `coletar_tabelas_yamaha.py` — lê os PDFs de `CONSORBENS\Tabelas\YAMAHA`, grava embutido/lance-fixo por grupo; **no-op se não há PDF novo** |
| `PLANEJAR_SIMULACAO` | produto, credito, prazo, lance_cliente, parcela_alvo, n_grupos | orquestra as duas de cima + driver do simulador + monta proposta |
| `IMPORTA_ANGLO` | — | `atualizar_cartas.py` — API Anglo → Supabase do SITE. **Sem navegador.** (ver 7.9) |
| `BAIXAR_GMAIL` | fonte: `yamaha` \| `itau` | `download_attachments.py` — Gmail API → pasta `Tabelas\{YAMAHA,ITAU}`. **Sem navegador.** (ver 7.9) |

**Cadência automática** (o supervisor enfileira sozinho, prioridade baixa —
roda no "tempo ocioso", quando o robô já está aberto e sem LANCE/BOLETO na
fila; não é gatilho dedicado): `COLETA_TABELAS` **1×/semana** (as regras de
embutido/lance-fixo quase nunca mudam) · `COLETA_GRUPOS --sync` conforme regra
de validade do Uriel · `COLETA_ASSEMBLEIAS` para grupo candidato sem assembleia
do mês.

O supervisor: 1 loop, pega o próximo PENDENTE (prioridade: LANCE/BOLETO na
frente das coletas, que são mais lentas), abre **um** navegador Playwright,
loga **uma vez**, roda o handler, grava resultado + `bater_heartbeat` a cada
ciclo. Erro técnico → reabre navegador; erro de negócio → não repete.

### 2.2 "Sempre ligado" (resumo — detalhe na seção 7)

- **Fila como "escuta":** o robô não precisa de porta aberta nem webhook — ele
  faz *poll* na `fila_automacao` (a cada ~15–30 s). Quem "fala" com ele é
  qualquer cliente que saiba gravar uma linha na fila: o ERP (botões), um cron,
  ou a **skill do Clode**.
- **Arranque:** `.bat` na Inicialização do Windows + **logon automático** do
  Windows → PC liga, loga sozinho, robô sobe.
- **Keep-alive:** watchdog leve (script ou Agendador de Tarefas) que checa o
  heartbeat em `robo_status` e re-sobe o supervisor se ele morreu.
- **NÃO** dá pra ser Serviço do Windows (sessão 0 = só headless, e o Newcon
  precisa de navegador visível). Roda numa sessão logada, janela minimizada.
- Retomada: progresso em arquivo + fila durável → ao re-subir continua de onde
  parou. Heartbeat em `robo_status` = bolinha 🟢/🔴 no ERP.

---

## 3. A cadeia do comando em linguagem natural

```
Usuário → Clode (skill erp-consorbens)
   │  "simulado: R$ 100k, veículo/auto, prazo longo, lance ~R$ 40k, parcela até R$ 1.500"
   │
   ├─ 1. Skill traduz para um pedido PLANEJAR_SIMULACAO e grava na fila_automacao.
   │
   ▼  (robô pega o pedido)
   ├─ 2. FRESCOR DA BASE  — para os grupos-alvo (produto + faixa de crédito):
   │       regra do Uriel por nº de vagas (ver simulacao-planejamento.md):
   │       <10 vagas → sempre; 10–25 → >1 dia; 25–40 → >2 dias; 50–80 → >4;
   │       80–120 → >7; 120–170 → >12.
   │       Catálogo de faixas: revalida a cada 30 dias ou se surgir plano novo.
   │       Assembleia: se já tenho a mais recente do grupo, não recoleta.
   │
   ├─ 3. ATUALIZA o que venceu:
   │       COLETA_GRUPOS (produto, credito) → grupos com vaga perto do alvo
   │       COLETA_ASSEMBLEIAS (esses grupos) → média de lance livre real
   │
   ├─ 4. RANKEIA os grupos pelo que o cliente quer (score explicável):
   │       • folga de lance = lance_cliente_% − média_lance_livre_grupo
   │           🟢 folga ≥ +5 pp  · 🟡 −2 a +5 · 🔴 < −2
   │       • assembleia mais próxima (prox_assembleia)
   │       • parcela pós ≤ parcela_alvo do cliente (do simulador)
   │       • crédito líquido entregue
   │       pesos ajustáveis; começa simples (folga > assembleia > parcela).
   │
   ├─ 5. RODA o simulador de verdade nos N melhores:
   │       driver abre o yamaha.html (a conta é toda em JS — não portar),
   │       preenche grupo/tipoPlano/cotas/credito/prazoGrupo/prazo/taxa/
   │       seguroTipo/embutido/recurso e lê parcelaAntes, lanceTotalPerc,
   │       lanceOf, lanceRecFooter, liberado, parcelasPos.
   │       Split do lance em R$ → % do crédito, embutido vs recurso próprio
   │       conforme o padrão do produto (LANCE_FIXO_DEFAULTS do ERP).
   │
   └─ 6. ENTREGA:
       • grava o resultado no pedido da fila (JSON: 3–5 cenários rankeados);
       • monta a PROPOSTA no modelo novo do cliente (o mesmo cartão
         .proposta do yamaha.html, com logo Consorbens) — 1 por cenário;
       • a skill devolve isso no chat + link/again pro PDF.
```

### 3.1 O que "melhores opções" quer dizer (critério do cliente)

O pedido carrega a intenção; o ranking responde a ela:

| Cliente quer… | Sinal no score |
|---|---|
| **lance menor** | menor `média_lance_livre` do grupo; folga positiva com o lance que ele tem |
| **parcela X** | `parcelasPos` (e `parcelaAntes`) do simulador ≤ alvo; senão sinaliza |
| **contemplar rápido / assertividade** | folga de lance alta **e** `prox_assembleia` perto **e** histórico de muitos contemplados por lance livre no grupo |
| **crédito na mão** | maior `liberado` (crédito líquido) para o mesmo desembolso |

Sempre mostrar também: **1 cenário "esticado"** (e se ele puser +R$ X de lance)
e **1 conservador** (menor parcela, mesmo que contemple mais devagar).

---

## 4. Pontos para TI + Analista de Dados fecharem

**TI / Arquitetura:**
1. Supervisor único vs. manter scripts separados chamados por subprocess? (proposta: um `worker_consorbens.py` que importa os handlers.)
2. Serialização de navegador: 1 navegador só, fila com prioridade — ok? Como evitar que uma coleta longa segure um LANCE urgente (timeslice? fila 2 faixas?).
3. Empacotar como serviço do Windows agora ou só `shell:startup` + loop? Log e restart.
4. A skill grava direto na `fila_automacao` (service key) ou passa por um endpoint fino? (hoje o ERP grava direto.)
5. Migração nova: colunas/tipos extras em `fila_automacao` (`tipo` novos, `resultado jsonb`, `prioridade int`).

**Analista de Dados:**
1. Janela da média de lance livre: últimas 3 assembleias? 6? mês corrente? (Maggi usa 3 meses.)
2. Fórmula e pesos do score de ranking — validar com casos reais já vividos.
3. Definição de "assertividade de contemplação": taxa histórica de contemplação por lance livre no grupo × folga do cliente. Precisa de quantos meses de histórico pra confiar?
4. Como tratar grupo novo (sem assembleia coletada) no ranking — excluir, ou entrar com aviso 🟡?
5. Split lance R$ → %: regra única por produto, ou deixar o robô otimizar embutido vs recurso próprio pelo maior `liberado`?
6. Métricas de acompanhamento: guardar cada simulado gerado (input do cliente + cenário escolhido + resultado real depois) pra medir acerto e ir calibrando.

**Só liberamos a implementação da próxima rodada quando os dois assinarem
embaixo deste documento com os itens acima resolvidos.**

---

## 5. Fora de escopo agora (mas no radar)

- Itaú / outros simuladores (só Yamaha por enquanto).
- Envio automático da proposta por WhatsApp API (hoje: link `wa.me` + PDF).
- Tela "Planejador de Contemplação" no ERP (a resposta pode viver só no chat + PDF no começo).

---

## 6. Pareceres TI + Dados (2026-08-30) e lista conjunta

Rodada 1 rodou os dois pareceres. **Ambos aprovaram a direção**, condicionados a
fechar uma lista conjunta antes de codar.

- **TI / Arquitetura:** *ARQUITETURA OK PARA A PRÓXIMA RODADA (após acordo com Dados).*
  Direção aprovada: estender o `worker_lances.py` num **supervisor único** com
  handlers; **2 navegadores por função** (um Newcon serializado + um só para o
  `yamaha.html`); **"cede a vez" cooperativo** (coleta em blocos suspende se
  entrar LANCE/BOLETO); coluna `prioridade`; **poll na `fila_automacao`**, sem
  HTTP; **migração 21** com `payload`/`resultado` jsonb + `chave_idempotencia`;
  extrair um **`core/fila_contrato.py`** único (hoje as regras de lance/dedup
  estão duplicadas ERP↔skill). "Sempre ligado": **Task Scheduler headful +
  auto-logon + watchdog**, NÃO Windows Service (sessão 0 = só headless, e o
  Newcon headless não foi validado).
- **Analista de Dados:** *DADOS OK PARA A PRÓXIMA RODADA (após acordo com TI).*
  Definições fechadas: média de lance = **mediana (p50) do `pct_lance`** direto
  de `yamaha_contemplacoes` (não a média-de-médias da view), janela de **3
  assembleias** (expande p/ 6 se < 6 contemplações); **assembleia normal ×
  mega** separadas; referência de folga = **percentil que depende de quantas
  cotas de lance livre o grupo contempla** (p50 se ≥5, p75 se 2–4, p90 se 1);
  **score 0–100** com 5 componentes (folga .40 / assembleia .20 / parcela .20 /
  liberado .15 / confiança .05), re-pesados pelo critério do cliente, guardados
  em tabela `score_config` versionada; **assertividade** = `p_ll × ECDF(lance)`
  como faixa, só exibe % com ≥ 8 contemplações; grupo novo entra 🟡 e nunca em
  1º; **4 tabelas novas** de histórico de simulados + job de calibração mensal.

### Lista conjunta — resolver antes de codar (dono do item entre colchetes)

**A. Contrato de dados / schema (trava a migração 21 e o `fila_contrato.py`)**
1. **Schema exato de `payload` e `resultado` por `tipo`**, principalmente o de
   `PLANEJAR_SIMULACAO` = espelho de `simulados_yamaha_cenarios`. [TI + Dados]
2. **Migração 21** (`fila_automacao`): `prioridade`, `payload/resultado jsonb`,
   `chave_idempotencia`, `origem`, `progresso`, `heartbeat_em` + índices. [TI]
3. **4 tabelas de histórico** (`simulados_yamaha`, `_cenarios`, `_resultado`,
   `score_config`): quem grava (handler direto ou via `resultado` da fila?),
   FKs. [TI + Dados]
4. **PII:** `cliente_ref` = **CPF hasheado**, nunca cru. Formato do hash. [TI]

**B. Chave de junção simulado → venda → contemplação (o mais crítico p/ Dados)**
5. Sem um campo "originou-se do simulado #" no cadastro de venda, **não há
   calibração**. Definir a chave (cota? lead_id? CPF hash?) e onde ela entra no
   fluxo de venda do ERP. [Dados + TI + decisão de produto]

**C. Atributos de grupo que hoje não coletamos (travam score de custo/split/assertividade)**
6. `fundo_reserva` por grupo — está na proposta antiga, **não** na migração 17
   aplicada (só `taxa`). [mapear tela Newcon]
7. **Teto de lance embutido** por grupo e se aceita embutido. [mapear tela Newcon]
8. **`prox_assembleia` como `date`** (hoje text `DD/MM/AAAA`) + flag
   `prox_assembleia_mega`. [TI, migração]
9. **`is_mega`** por linha em `yamaha_assembleias` (hoje só dá p/ inferir por
   contagem) — idealmente calendário oficial de megas. [mapear + Uriel]
10. Nº de cotas de lance livre / sorteados **por regra do grupo** (regulamento),
    separado do observado `n_lance_livre`. [mapear + Uriel]

**D. Regras / política**
11. **Split lance R$ → %:** o robô otimiza embutido × recurso próprio (dentro
    dos tetos) pelo objetivo do cliente; regra fixa `LANCE_FIXO_DEFAULTS` só
    como default. Colar os valores reais por produto. [Uriel + Dados]
12. **Fonte única de frescor:** a "regra do Uriel por nº de vagas" + catálogo 30
    dias + "não recoletar assembleia já no banco" numa função só
    (`precisa_reconsultar` já existe) chamada pelo handler. [TI]
13. **Coleta de fundo:** quem dispara `COLETA_ASSEMBLEIAS` de 6 assembleias p/
    todos os grupos ativos — cron? primeira vez que o grupo entra num ranking?
    (casa com a serialização de navegador). [TI + Dados]
14. **Qual `yamaha.html` o driver abre** — arquivo local ou app publicado (taxa
    sempre atual)? Define se o driver precisa de sessão logada no ERP. [TI]
15. **Newcon aceita 2 logins simultâneos?** Resposta define se há qualquer
    paralelismo possível. [Uriel]
16. **Onde vivem pesos/versão do modelo:** `score_config` lida a cada run
    (recalibra sem deploy) — confirmado pelos dois. [fechado]
17. **View/função `yamaha_grupo_lance_stats`** (p25/p50/p75/p90 + n) para HTML e
    handler usarem a mesma fonte — hoje a view só dá média. [TI + Dados]

**Gate:** codar a rodada 2 **só** depois desta lista fechada num spec assinado
por TI e Dados, com prioridade para os itens **5** (chave simulado→resultado) e
**6–10** (atributos de grupo, dependem de mapear telas novas do Newcon).

---

## 7. Arquitetura "sempre-ligado" (robô de prontidão)

> Objetivo: o robô fica de pé o tempo todo no PC do escritório e atua sozinho
> assim que chega tarefa — igual já rola com LANCE e BOLETO. Nada de rodar
> script na mão.

### 7.1 O processo — supervisor único

`worker/worker_consorbens.py` (estende o `worker_lances.py` de hoje):

```
loop infinito:
  1. lê fila_automacao  (status=PENDENTE, order by prioridade, criado_em)
  2. se não há nada: bate heartbeat em robo_status, dorme 15-30 s, repete
  3. pega o próximo pedido, marca PROCESSANDO
  4. chama o handler do `tipo`:
        LANCE / BOLETO              -> newcon.py (já existe)
        RELATORIO_COMISSAO         -> baixar_comissoes.py
        COLETA_GRUPOS              -> coletar_grupos.py  (como função)
        COLETA_ASSEMBLEIAS        -> coletar_assembleias.py
        COLETA_TABELAS            -> coletar_tabelas_yamaha.py
        PLANEJAR_SIMULACAO       -> planejar/robo_yamaha  + driver do yamaha.html
  5. grava resultado (SUCESSO/ERRO + resultado jsonb) e bate heartbeat
  6. erro técnico  -> recupera navegação -> se falhar, reabre navegador (relogin)
     erro de negócio -> marca ERRO, NÃO repete
```

- **1 navegador Playwright + 1 login** no Newcon, reusado por todos os
  handlers (o `robo_yamaha.py` já tem essa lógica: sessão única, retomada,
  `_reset_para_resultado` pra re-navegar sem relogar, `reabrir()` como último
  recurso).
- **2º contexto de navegador** só para o `yamaha.html` (o driver do simulado),
  isolado do Newcon — crash do driver não derruba a sessão de venda.

### 7.2 Como ele fica ligado — 3 camadas

| Camada | Implementação | Cobre |
|---|---|---|
| **Arranque** | `iniciar_robo.bat` em `shell:startup` + **logon automático do Windows** (netplwiz / registro `AutoAdminLogon`) | PC liga/reinicia → loga sozinho → robô sobe |
| **Keep-alive (watchdog)** | Tarefa no Agendador ("a cada 2 min") ou `watchdog_robo.py`: lê `robo_status.atualizado_em`; se > 3 min parado → `taskkill` no python + re-executa o `.bat` | crash, deadlock, Newcon matou a sessão de vez |
| **Retomada** | progresso em `*_progresso.json` + a própria `fila_automacao` (durável) | ao re-subir: pedido que estava PROCESSANDO volta pra PENDENTE (`reenfileirar_interrompidos`); coleta continua do bloco onde parou |

**Por que não Serviço do Windows:** serviço roda na **sessão 0**, sem desktop
→ Playwright só funciona headless. O Newcon **não foi validado headless** (tem
tela pesada de postback, "Invalid postback", etc.). Então: sessão logada,
janela do Chrome **minimizada** ("segundo plano" = minimizado, não invisível).
Se um dia validarmos o Newcon headless, aí vira serviço de verdade e resolve.

**Alternativa (se o PC do escritório não puder ficar logado):** um mini-PC
dedicado só pro robô, ou uma VM Windows com auto-logon — mesmo desenho.

### 7.3 A fila é a caixa de entrada

Ninguém "chama" o robô por HTTP. Quem quer que ele faça algo **grava uma linha
em `fila_automacao`**:
- **ERP** — botões (Ofertar Lance, Emitir Boleto) já fazem isso hoje
- **Skill do Clode** — traduz "gera um simulado pra cliente que quer 100k em
  veículo" num pedido `PLANEJAR_SIMULACAO`
- **Cron interno** (7.4) — o próprio supervisor se agenda

Vantagem: sem porta aberta, sem firewall, sem TLS, sem 2º serviço no ar. A
latência (poll de 15-30 s) é irrelevante pra tudo aqui.

### 7.4 Cron interno (o robô se auto-agenda)

No tempo ocioso (fila sem LANCE/BOLETO), o supervisor enfileira sozinho, com
`prioridade` baixa:

| Tarefa | Quando |
|---|---|
| `COLETA_GRUPOS --sync` | conforme a regra de validade do Uriel (nº de vagas × dias) — na prática ~1×/dia varre só os planos vencidos |
| `COLETA_ASSEMBLEIAS` | grupo candidato com vaga que ainda não tem a assembleia do mês |
| `COLETA_TABELAS` | 1×/semana (regras de embutido/lance-fixo quase não mudam) |

### 7.5 Prioridade + "cede a vez"

- Coluna `prioridade int` (menor = mais urgente): LANCE/BOLETO=10 ·
  PLANEJAR=40 · COLETA_*=50 · RELATORIO=60
- Seleção: `order by prioridade, criado_em`
- **Cede a vez:** a coleta roda em **blocos** (um plano / um grupo por vez).
  Entre blocos re-olha a fila; se surgiu PENDENTE de prioridade < a dela,
  **suspende** (volta a PENDENTE com o progresso gravado), executa o urgente,
  e retoma. Latência do LANCE = "1 bloco" (segundos a ~1-2 min), sem
  paralelismo real no Newcon.

### 7.6 Observabilidade

- **Heartbeat** em `robo_status` a cada ciclo → bolinha 🟢/🔴 **SERVER** no ERP
  (já existe: `_status_robo` em `app.py`, `LIMITE_SERVER_SEG=90`)
- **Log rotativo** `worker/logs/robo.log` (RotatingFileHandler, ~5 MB × 5) +
  eco no console; o `.bat` também redireciona stdout/stderr pra `logs/console.log`
- **Painel da fila no ERP** — reaproveita o que `_mapa_ultimo_lance` já faz:
  lista `fila_automacao` filtrando `tipo in (COLETA_*, PLANEJAR_*)` com
  `status` / `progresso` ("coletando 3/12") / `mensagem`
- Opcional: alerta (e-mail/registro) se ficar 🔴 por > X min em horário comercial

### 7.7 Modos de falha

| Situação | O que acontece |
|---|---|
| PC reinicia | logon automático → `.bat` → robô sobe, `reenfileirar_interrompidos`, segue |
| Robô trava / deadlock | watchdog mata e re-sobe em ~2-3 min |
| Sessão Newcon expira no meio | handler recupera navegação; se travar, `reabrir()` (relogin), sem intervenção |
| `G:\` (Drive) não montado | robô **recusa subir** com log claro (não roda cego — boleto e `yamaha.html` vivem no `G:\`) |
| Sessão do Windows deslogada (não bloqueada) | Playwright headful para de funcionar — documentar: "não fazer logoff, só bloquear"; watchdog detecta pelo heartbeat parado |
| PC desligado / sem energia | bolinha 🔴 no ERP; nada a fazer no software |
| Uma coleta longa pendurada | teto de tempo por tarefa (ex.: PLANEJAR = 15 min) aborta e marca ERRO_TECNICO |

### 7.8 O que já está pronto pra isso

- `robo_yamaha.py` — sessão única, retomada por arquivo de progresso,
  recuperação em camadas (navegação → reabrir navegador), "lê o que já temos
  antes de buscar". É o handler de `COLETA_GRUPOS` + `COLETA_ASSEMBLEIAS`
  praticamente pronto.
- `coletar_tabelas_yamaha.py` — handler de `COLETA_TABELAS` (no-op se não há
  PDF novo).
- `worker_lances.py` — o esqueleto do loop (heartbeat, classificação
  técnico×negócio, reenfileiramento). É a base do `worker_consorbens.py`.
- `robo_status` + bolinha 🟢 SERVER — observabilidade mínima já no ar.

**Falta:** o `worker_consorbens.py` (juntar os handlers num loop só), a
migração da `fila_automacao` (`prioridade`, `payload/resultado jsonb`,
`chave_idempotencia`), o watchdog, e o auto-logon do Windows. Codar depois do
gate da seção 6.

### 7.9 Funções API-only (sem navegador) — as mais fáceis de trazer

Hoje são **3 robôs separados**, cada um com seu `.bat` e sua tarefa no
Agendador. Todos são **puro HTTP/API, sem navegador** — então entram no
supervisor como tarefas rápidas que **não encostam na sessão Newcon** (rodam
inline ou numa thread à parte, sem disputar prioridade com LANCE/BOLETO).

| Robô hoje | Pasta | O que faz | Vira |
|---|---|---|---|
| Importar Anglo | `CLODE\IMPORTA_ANGLO_CONSORCIO` (`atualizar_cartas.py`) | API JSON da Anglo → ágio + termômetro → **Supabase do SITE** (`gvgwphsmdbmzifpwrevp`), substitui só fornecedor "Anglo Consórcios" | tipo `IMPORTA_ANGLO` |
| Baixar tabelas Yamaha | `CLODE\ATUALIZA_YAMAHA_TABELAS\scripts` (`download_attachments.py`) | Gmail API (readonly), busca "Tabelas Yamaha" → `CONSORBENS\Tabelas\YAMAHA` | tipo `BAIXAR_GMAIL` (fonte=yamaha) |
| Baixar guia Itaú | `CLODE\GUIA_DE_OPORTUNIDADES_ITAU\scripts` (`download_attachments.py`) | Gmail API, `subject:"GUIA DE OPORTUNIDADES" "Itaú"` → `CONSORBENS\Tabelas\ITAU` | tipo `BAIXAR_GMAIL` (fonte=itau) |

**Como consolidar:**
- Os 3 scripts já rodam standalone — viram **handlers** do supervisor
  (import + chamada de função), mantendo o `__main__` pra debug.
- **Credenciais** (não mexer, só apontar):
  - Anglo: `config.json` em `%LOCALAPPDATA%\Consorbens\` (fora do Drive, não
    sincroniza) — o script já procura em vários caminhos alternativos.
  - Gmail (Yamaha e Itaú): `credentials.json` + `token.pickle` dentro de cada
    `scripts/` (OAuth já autorizado, escopo `gmail.readonly`). Dois tokens
    separados — dá pra unificar num só depois, não é urgente.
- **Supabase:** o Anglo grava no projeto do **SITE**, os outros no do **ERP** ou
  em pasta. O supervisor só precisa das duas URLs/keys no `.env`.
- **Cadência automática** (cron interno, 7.4): `BAIXAR_GMAIL` yamaha quarta 12h
  · `BAIXAR_GMAIL` itau terça 12h · `IMPORTA_ANGLO` 23h/dia. E **encadear**:
  depois do `BAIXAR_GMAIL` yamaha, enfileira `COLETA_TABELAS` (que lê os PDFs
  novos e atualiza os grupos no simulador).
- **Aposentar:** os `.bat` e as tarefas do Agendador desses 3 saem de cena — o
  supervisor passa a ser o único ponto que roda tudo (menos coisa pra dar
  errado, um log só, uma bolinha só).

Essas 3 são as **primeiras a migrar** quando começar a rodada 2 — são simples,
sem risco de navegador, e já tiram 3 tarefas do Agendador.
