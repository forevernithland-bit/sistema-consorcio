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
   - **Lance** (Ofertar Lance → Newcon) — já funciona (`worker_lances.py` / `newcon.py`).
   - **Boletos** (Emissão de Cobrança → PDF + código de barras) — já funciona.
   - **Busca de grupos / planos / faixas de crédito / vagas** (`coletar_grupos.py`).
   - **Resultado de assembleias / média de lance real** (`coletar_assembleias.py`).
   - **Relatórios de comissão** (download no Newcon, leitura de PDF).
   - **Planejamento de simulação** (`planejar.py`) + **driver do `yamaha.html`** (novo).
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
| `PLANEJAR_SIMULACAO` | produto, credito, prazo, lance_cliente, parcela_alvo, n_grupos | orquestra as duas de cima + driver do simulador + monta proposta |

O supervisor: 1 loop, pega o próximo PENDENTE (prioridade: LANCE/BOLETO na
frente das coletas, que são mais lentas), abre **um** navegador Playwright,
loga **uma vez**, roda o handler, grava resultado + `bater_heartbeat` a cada
ciclo. Erro técnico → reabre navegador; erro de negócio → não repete.

### 2.2 "Sempre ligado"

- **Agora (barato):** `iniciar_robo.bat` na pasta **Inicializar** do Windows
  (`shell:startup`) + o loop com `while True` e reconexão. Já dá "liga sozinho
  quando o PC liga".
- **Depois (robusto):** empacotar como **serviço do Windows** (NSSM ou
  `pywin32`), com restart automático e log rotativo. O heartbeat em
  `robo_status` continua sendo a fonte da verdade pro ERP (🟢/🔴).
- **Fila como "escuta":** o robô não precisa de porta aberta nem webhook — ele
  faz *poll* na `fila_automacao` (a cada ~15–30 s). Quem "fala" com ele é
  qualquer cliente que saiba gravar uma linha na fila: o ERP (botões), um cron,
  ou a **skill do Clode**.

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
