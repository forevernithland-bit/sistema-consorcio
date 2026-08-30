# Assistente de Planejamento de Simulações — Yamaha

> Rascunho de projeto. Nada implementado ainda — este arquivo é o mapa para
> a gente alinhar antes de escrever código. Depois de pronto, todo o
> conhecimento entra na skill `erp-consorbens`.

## 1. O que é

Uma função que responde perguntas do tipo:

> "Tenho um cliente que precisa contemplar **R$ 100.000** e tem **R$ 40.000**
> de lance. O que dá pra fazer?"

e devolve as **melhores combinações de grupo + cota + lance**, já simuladas,
ordenadas por chance de contemplar e por parcela pós-contemplação —
aproveitando o robô que já temos.

## 2. As duas "máquinas" que ela precisa

### 2A. Coletor de inteligência de grupos (robô no Newcon)

Entra no Newcon e extrai, por grupo Yamaha:

| Dado | Provável origem no Newcon | Observação |
|---|---|---|
| Nº de grupos ativos | menu **Grupo** (lista) | base do resto |
| Vagas disponíveis no grupo | menu **Venda → Venda de Proposta** (ao simular, lista grupos com vaga) ou menu **Grupo** | "vaga" = cota livre pra vender |
| Créditos disponíveis no grupo | idem — cada grupo tem faixa/valores de crédito | ex.: grupo de moto R$ 16k–60k |
| Nº de assembleias do grupo | menu **Grupo** ou **Contemplação** | total (prazo) e/ou já realizadas |
| Média de lance do grupo | menu **Contemplação** (histórico de assembleias) | % médio vencedor das últimas N assembleias |

Cada varredura **grava numa tabela** (proposta no item 3) com data/hora, pra:
- não ter que re-raspar tudo a cada pergunta;
- ir formando um histórico de lances vencedores por grupo (a "inteligência
  interna" que você pediu).

### 2B. Driver do simulador Yamaha (`yamaha.html`)

O robô abre o `yamaha.html` (a conta é toda em JS — não dá pra portar pra
Python sem risco) no próprio navegador dele, preenche e lê o resultado, um
grupo por vez. Campos do simulador hoje: `grupo, tipoPlano, cotas, credito,
prazoGrupo, prazo, taxa, seguroTipo, embutido, recurso`. Saídas:
`parcelaAntes, lanceTotalPerc, lanceOf, lanceRecFooter, liberado,
parcelasPos, resultado`.

## 3. Tabela de conhecimento (proposta)

Nova tabela no Supabase do ERP: **`grupos_yamaha`**

| coluna | tipo | o que guarda |
|---|---|---|
| `grupo` | text (PK) | nº do grupo |
| `tipo_bem` | text | Moto / Auto / Imóvel / Caminhão |
| `prazo_grupo` | int | nº total de meses/assembleias |
| `assembleias_realizadas` | int | quantas já rodaram |
| `assembleias_restantes` | int | prazo − realizadas |
| `vagas` | int | cotas livres pra vender agora |
| `credito_min` / `credito_max` | numeric | faixa de crédito do grupo |
| `taxa_adm` | numeric | taxa de administração do grupo |
| `fundo_reserva` | numeric | % fundo de reserva |
| `media_lance_pct` | numeric | média % lance vencedor (últimas N assembleias) |
| `menor_lance_pct` / `maior_lance_pct` | numeric | faixa observada |
| `qtd_contemplacoes_lance` | int | nº de contemplações por lance na janela |
| `atualizado_em` | timestamptz | quando o robô raspou |
| `fonte` | text | "newcon" / "manual" |

E uma tabela filha **`grupos_yamaha_lances`** (1 linha por assembleia
observada) pra guardar o histórico bruto e recalcular a média quando quiser:
`grupo, data_assembleia, num_assembleia, lance_vencedor_pct,
lance_vencedor_valor, tipo_lance (livre/fixo), atualizado_em`.

## 4. Fluxo da pergunta de exemplo (ponta a ponta)

```
Pergunta: crédito-alvo R$ 100.000, lance disponível R$ 40.000 (= 40%)
  │
  ├─ 1. Consulta `grupos_yamaha`: grupos do tipo certo, com VAGA,
  │      cujo credito_min..max cobre R$ 100.000.
  │      Se os dados estiverem velhos (> X dias) → robô re-raspa antes.
  │
  ├─ 2. Para cada grupo candidato, calcula a "folga de lance":
  │      folga = lance_cliente_% − media_lance_pct do grupo
  │      folga alta  → contempla fácil / sobra pra reduzir parcela
  │      folga baixa/negativa → arriscado, mostra mas sinaliza
  │
  ├─ 3. Roda o `yamaha.html` para os N melhores grupos, com:
  │      credito = 100.000, lance embutido/recurso conforme o padrão do
  │      produto (ver LANCE_FIXO_DEFAULTS no erp.py) + o lance de R$ 40.000.
  │      Lê parcela antes, parcela depois da contemplação, crédito liberado.
  │
  └─ 4. Devolve um ranking curto (3 a 5 linhas):
        grupo | crédito | sua chance (folga) | parcela hoje | parcela pós |
        crédito liberado | assembleia mais próxima
```

## 5. "Situações mais relevantes e inteligentes" — critério de ordenação

Proposta de score (ajustável): ordena por **maior folga de lance** (chance de
contemplar) e, em empate, **menor parcela pós-contemplação**. Marca:
- 🟢 folga ≥ +5 p.p. → "contempla com folga"
- 🟡 folga entre −2 e +5 → "linha de corte, depende da assembleia"
- 🔴 folga < −2 → "difícil com esse lance"

Mostrar também 1 cenário "esticado": e se o cliente puser mais R$ X de lance,
qual grupo abre. E 1 cenário "conservador": grupo com menor parcela mesmo que
contemple mais devagar.

## 6. Caminho mais rápido pra ficar pronto (fases)

1. **Mapear as telas** (`--descobrir` nas telas Grupo / Venda de Proposta /
   Contemplação do Newcon) — 1 rodada, manda o dump.
2. **Criar as tabelas** `grupos_yamaha` (+ `_lances`) e um script
   `worker/coletar_grupos.py` que raspa e grava.
3. **Driver do simulador** `worker/simular_yamaha.py` (abre `yamaha.html`,
   roda uma lista de cenários, devolve JSON).
4. **Orquestrador** `worker/planejar_simulacao.py` que junta 1+2+3 e responde
   a pergunta (recebe crédito-alvo + lance, devolve o ranking).
5. **Skill**: nova referência `references/planejamento-simulacao.md` + linha no
   mapa do `SKILL.md`.

Fases 2–4 só depois de 1 (sem os seletores reais, é chute).

## 7. Dúvidas que preciso resolver antes de codar

**Sobre o Newcon (telas):**
1. Em qual menu se vê a **lista de grupos com vaga e a faixa de crédito**?
   "Venda de Proposta" (simulação de venda), "Grupo", ou outro?
2. "**Vagas**" de um grupo — é cota livre pra vender? O Newcon mostra esse
   número numa tela só, ou tem que contar cota a cota?
3. "**Créditos disponíveis no grupo**" — é a faixa de crédito que o grupo
   oferece (min/máx), ou é lista de cotas já contempladas à venda? Qual dos
   dois você quer?
4. "**Média de lance**" — de onde tiro? Tem um relatório de resultado de
   assembleia no menu **Contemplação**? Quantas assembleias pra trás a média
   deve considerar (últimas 6? 12? todas)?
5. "**Quantidade de assembleias**" — você quer o total do grupo (prazo),
   quantas já rodaram, ou quantas faltam? (proponho guardar os três)

**Sobre o simulador:**
6. Rodo o `yamaha.html` do arquivo local, ou preciso rodar dentro do app
   publicado (pra pegar taxa/tabela sempre atualizada)?
7. Quando o cliente dá um lance em **R$** (ex.: R$ 40.000), no simulador isso
   entra como **% do crédito** (40%) dividido entre embutido + recurso
   próprio? Qual a regra de split que você usa hoje na mão?
8. "Precisa contemplar R$ 100.000" = **crédito da carta** = R$ 100.000, certo?
   Ou é o valor que ele quer na mão depois do lance embutido?

**Sobre o resultado:**
9. Quantos grupos no ranking final (3? 5?) e o que **não pode faltar** em cada
   linha (parcela hoje, parcela pós, prazo restante, chance…)?
10. A resposta vem **só no chat**, ou você quer também uma tela no ERP
    ("Planejador de Contemplação")?

**Sobre os dados:**
11. De quanto em quanto tempo os dados de grupo "vencem" e o robô deve
    re-raspar sozinho? (proponho: 7 dias, ou sempre que você pedir "atualiza
    os grupos")
12. Isso é só Yamaha por enquanto, certo? (Itaú fica pra depois)
