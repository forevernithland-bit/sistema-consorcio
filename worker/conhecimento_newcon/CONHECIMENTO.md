# Conhecimento do robô Yamaha sobre o Newcon (atualizado 16/11/2026)

Memória do ROBÔ (o mesmo `robo_yamaha.py` / `worker_consorbens.py` — não é robô novo).
Mapa completo das telas: `MAPA_NEWCON.md` e `ONDE_ACHAR.md` (gerados pelo explorador).

## 1. Uma janela só (desde 16/11/2026)
- `newcon_navegador.py`: um Chromium do robô, porta local 9333, perfil `~/.newcon_navegador_robo`.
- Todo script conecta nele e abre/fecha SÓ uma aba (`newcon_navegador.abrir_aba`). Loga 1 vez
  (senha do cofre `senhas_sistema`), com trava `newcon_login.lock` para só um logar por vez.
- Worker: recupera a sessão na mesma janela (`newcon.garantir_sessao`), ping na home a cada 10 min ocioso.
- `NEWCON_NAVEGADOR_UNICO=0` volta ao jeito antigo (cada script com seu navegador).

## 2. Onde achar cada dado
| Dado | Onde |
|---|---|
| grupos por produto, vagas, crédito, prazo | Venda → Venda de Propostas: Produto → Tipo de Venda (plano) → Prazo → Bem (`coletar_grupos.py`) |
| média de lance / contemplados por modalidade | Contemplação → Resultado de Assembleia (`coletar_assembleias.py`) — exige Ponto de Venda `010852 - ECOCLIM` para "Buscar grupos" |
| regras de lance do grupo | Atendimento → grupo/cota → Localizar → **Oferta de Lance** → bloco "Dados do Lance" (`regras_lance.py`) |
| taxa | já vem na coleta de grupos (47 grupos) |
| seguro | NÃO achado em tela de consulta. Possível: Venda → "Impressão de PAC" (não testado — perguntar ao Breno antes) |
| consulta de grupo | nosso usuário NÃO tem tela de consulta de grupo |
| calendário de assembleias | Calendário: "Imprimir" só habilita com o período preenchido |

## 3. Tela "Oferta de Lance" (Credenciamento de Lance)
- Radios `ctl00_Conteudo_rgLance_N`, value: **LL** Livre · **LF** Fixo · **LS** 2º Fixo · **LM** Limitado · **LI** Fidelidade.
  Radio desabilitado = o grupo não libera a modalidade.
- Redução: "Reduzir Prazo" (`rblFormasLance_0`) / "Reduzir Parcela" (`rblFormasLance_1`).
- % do lance: `rblTipoOferta` = **"Percentual"** + `edtOferta` (Fixo/2º Fixo o Newcon preenche sozinho).
- Embutido: `cbxLanceEmbutido` = "Percentual" + `edtEmbutido`. **No Limitado o embutido fica TRAVADO**
  (testado 9047 e 9538) → Limitado é 100% recursos próprios.
- **Fidelidade** depende da COTA: alerta "Cota não está apta para credenciamento de lance fidelidade."
- "Lance Mínimo/Máximo" do bloco são DA COTA (dependem do saldo), não do grupo.
- "Último lance ofertado em: DD/MM/AAAA" em vermelho = já tem lance no mês (o formulário continua aberto).
- Formulário fechado (fora do prazo) = sem radios, só a tabela "Ofertas" (histórico).
- Botões: Histórico · **Simular...** (só calcula, não grava) · Confirmar · **Cancelar (NUNCA clicar:
  pode cancelar a oferta registrada)**.
- Simular mostra: Valor do Lance, % do Lance, Recursos Próprios, Crédito Novo, Saldo Devedor Novo,
  Parcelas a Pagar Novo, Valor da Parcela após o lance.

## 4. Regras lidas por grupo (regras_lance.json → yamaha_regras_lance)
- Imóvel 10010–10022: Livre + Fixo 30%.
- 9021/9029/9047/9048: Livre, Fixo 35, 2º Fixo 25, Limitado (até 100).
- 9538/9542/9551/9569/9582: todas; Fixo 35, 2º Fixo 10, Limitado e Fidelidade até 100.
- 9600: Livre, Fixo 25, Limitado, Fidelidade.
- Embutido permitido: tabela do grupo (grupos_yamaha) > regra geral (Moto/Auto 15, Imóvel 25, Caminhão 30).

## 5. Como o robô oferta (newcon.ofertar_lance)
pedido: grupo, cota, tipo_lance, pct_lance, pct_embutido, tipo_reducao, simular.
Status: OK · JA_OFERTADO · FALHA (negócio, não repete) · SIMULADO (teste, nada enviado).
Alertas do Newcon viram FALHA com o texto do alerta.
Teste sem enviar: `py -V:3.14 testar_lance_simulado.py <grupo> <cota> "Lance Livre" 60 15 [Prazo]`.

## 6. Lances programados
ERP grava `lances_programados` (N meses ou ilimitado). O worker (a cada 30 min) põe o LANCE do mês
na fila; se o Newcon recusar, tenta no dia seguinte; conta o mês com SUCESSO/JA_OFERTADO; encerra
quando completa, quando a cota é contemplada/cancelada ou quando param no ERP.

## 7. Comandos
- `robo_yamaha.py --explorar [--limite N] [--so GR/AA]` · `--mapa` — explorador (retoma de onde parou).
- `robo_yamaha.py --regras-lance [--grupos X,Y] [--salvar] [--forcar] [--so-salvar]`.
- `backfill_2fixo.py [--salvar]` — corrige contadores de 2º fixo antigos ("2o Lance Fixo").
