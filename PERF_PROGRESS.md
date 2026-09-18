# Progresso — otimização de performance (branch `perf/otimizacao-paginas`)

Trabalho de performance pura (cache de leituras do Supabase + invalidação
correta nas escritas). Nenhuma lógica de negócio, cálculo, texto ou design
deve mudar — só velocidade. Ver instruções completas na tarefa original.

Regra geral aplicada: `database.carregar_dados_iniciais` agora é
`@st.cache_data(ttl=60)`. Toda tabela que ela lê (vendas, clientes,
assembleias, cad_administradoras, administradoras, status_comissoes,
config_interna) e que é escrita em algum módulo PRECISA de uma chamada
`carregar_dados_iniciais.clear()` logo após o insert/update/delete daquele
módulo — senão a tela pode mostrar dado desatualizado por até 60s. Isso é
rastreado abaixo, arquivo por arquivo, conforme vou mexendo em cada um.

## Checklist

- [x] `database.py` — `carregar_dados_iniciais` cacheada com `@st.cache_data(ttl=60)`
      (parâmetro renomeado para `_supabase` para não tentar hashear o Client).
      `salvar_status_comissoes` chama `.clear()` após salvar com sucesso.
      Testado contra o Supabase real: 2ª chamada com cache quente ~0.006s vs
      ~2s sem cache; dado idêntico (`.equals()`/comparação profunda) com e
      sem cache. **Ainda falta** adicionar `.clear()` nos outros módulos que
      escrevem nessas 7 tabelas (dashboard.py, nova_venda.py, baixas.py,
      configuracoes.py, assembleias.py, importar_comissoes.py) — será feito
      quando cada um for processado nesta lista, mas até isso ser concluído em
      TODOS eles, o cache tecnicamente pode servir dado com até 60s de atraso
      em algum fluxo ainda não coberto. Nunca fizemos `git push`, então isso
      não afeta produção.
- [x] `app.py` — `_status_robo` e `_trava_login_robo` (leem `robo_status`, chamadas
      em TODO rerun logado) cacheadas com `@st.cache_data(ttl=15)`. TTL curto
      porque o worker só atualiza a cada ~30s e o limite de "offline" já é
      90s, então 15s não muda a percepção do usuário. `.clear()` chamado nas
      duas logo após o único update que o próprio app faz em `robo_status`
      (botão "liberar robô"). Testado: leitura cacheada retorna valor
      idêntico e cai de ~0.87s para ~0.000s.
- [x] `modulos/dashboard.py` — adicionado `carregar_dados_iniciais.clear()` logo
      após cada escrita em `clientes`/`vendas` (editar/excluir cliente,
      adicionar cota, editar cota, apagar cota), para o cache de 60s de
      `database.py` nunca mostrar dado velho depois de uma escrita nesta tela.
      Nenhuma outra otimização aplicada aqui (os `.apply()` restantes rodam
      sobre recortes pequenos — por cliente — e vetorizá-los não traria ganho
      que justifique o risco).
- [x] `modulos/financeiro.py` — `_carregar_datas_financeiro` (tabela
      `financeiro_datas`) e a nova `_carregar_comissoes_pagas` (tabela
      `comissoes_pagas`, extraída de dentro de `_recebidos_tradicional`)
      cacheadas com `@st.cache_data(ttl=60)`. Achado importante: essas duas
      fetches completas rodavam a cada render do Financeiro **E** a cada
      Dashboard de usuário Master (via `calcular_resumo_mes_atual` no card
      "Resumo do mês") — ou seja, em uma das páginas mais visitadas.
      `_salvar_data_financeiro` chama `.clear()` de `_carregar_datas_financeiro`
      logo após o upsert. `_carregar_comissoes_pagas.clear()` ainda precisa ser
      chamado nas escritas de `comissoes_pagas` em `baixas.py` e
      `importar_comissoes.py` — será feito quando esses arquivos forem
      processados nesta lista (mesmo padrão do `carregar_dados_iniciais`).
      `carregar_operacoes_site()` (site) já estava cacheada (ttl=120) e não
      precisou de mudança — tabela só de leitura, nunca escrita por este ERP.
      Testado contra o Supabase real: dado idêntico com e sem cache, latência
      cai para ~0.000s na chamada cacheada.
- [x] `modulos/relatorios.py` — `_carregar_comissoes` fazia fetch completo de
      `comissoes_pagas` a cada render da tela (8 abas todas dependem dela).
      Extraída a leitura crua para `_fetch_comissoes_pagas_raw`, cacheada com
      `@st.cache_data(ttl=60)`; o try/except com `st.error` de
      `_carregar_comissoes` foi mantido por fora, para não mudar o
      comportamento de erro. Cache próprio (separado do de financeiro.py) de
      propósito — evita que uma exceção engolida silenciosamente dentro do
      cache compartilhado faça o aviso de erro do usuário parar de aparecer.
      `.clear()` ainda precisa ser adicionado nas escritas de
      `comissoes_pagas` em `baixas.py`/`importar_comissoes.py` (junto com o de
      financeiro.py). Testado: dado idêntico (`.equals()`) com e sem cache.
- [x] `modulos/nova_venda.py` — adicionado `carregar_dados_iniciais.clear()`
      após os dois pontos que gravam em `vendas`/`clientes` (venda tradicional
      e venda contemplada), para não deixar o cache de 60s do
      `database.py` mostrar dado velho na próxima navegação.
- [x] `modulos/baixas.py` — `_salvar_baixas_manuais` grava em `comissoes_pagas`
      e `status_comissoes` num loop. Adicionado `carregar_dados_iniciais.clear()`
      (database.py) + `_carregar_comissoes_pagas.clear()` (financeiro.py) +
      `_fetch_comissoes_pagas_raw.clear()` (relatorios.py) uma vez, após o
      loop, dentro do `if ok:`. Com isso os caches de `comissoes_pagas`
      ficam totalmente cobertos entre financeiro.py/relatorios.py/baixas.py.
      Testado import isolado do módulo (sem import circular).
- [x] `modulos/ofertar_lance.py` — nenhuma mudança. `_mapa_ultimo_lance` e
      `_painel_status` leem `fila_automacao`, que é escrita tanto pelo app
      (aqui mesmo, `_enfileirar`) quanto pelo WORKER externo do robô
      (`worker/worker_lances.py` etc.), em ciclos de segundos, e a própria
      razão de existir desta tela é mostrar o status **ao vivo** da fila
      (inclui um botão "🔄 Atualizar"). Cachear aqui esconderia justamente a
      informação que o usuário está checando. Decisão: não cachear (ver
      seção "Decisões de não cachear" abaixo). `fila_automacao` não é uma das
      7 tabelas do `carregar_dados_iniciais`, então nenhuma invalidação foi
      necessária.
- [x] `modulos/emitir_boleto.py` — `_salvar_flags_mensais` grava
      `BOLETO_MENSAL` em `vendas`; adicionado `carregar_dados_iniciais.clear()`
      logo após salvar. `_mapa_ultimo_boleto`/`_painel_status` (leem
      `fila_automacao`) NÃO foram cacheadas, mesmo motivo do
      `ofertar_lance.py`: status ao vivo do robô, escrito por um processo
      externo. `listar_arquivos_drive` já estava cacheada (utils.py) e já
      tinha `.clear()` correto no botão "Atualizar" — nada a mudar.
- [x] `modulos/configuracoes.py` — adicionado `carregar_dados_iniciais.clear()`
      após todas as escritas em `cad_administradoras`, `administradoras` e
      `config_interna` (cadastrar admin, nova regra, editar/excluir regra,
      salvar regras internas).
- [x] `modulos/assembleias.py` — adicionado `carregar_dados_iniciais.clear()`
      após cadastrar/apagar assembleia. Com isso, TODAS as 7 tabelas do
      `carregar_dados_iniciais` (vendas, clientes, assembleias,
      cad_administradoras, administradoras, status_comissoes,
      config_interna) já têm `.clear()` cobrindo suas escritas conhecidas no
      app (falta só `importar_comissoes.py`, que também mexe em
      vendas/clientes/status_comissoes e será feito mais adiante).
- [x] `modulos/robo_painel.py` — nenhuma mudança. `_robo_online` e
      `_ja_na_fila` (uma consulta por botão de tarefa, 7 no total) leem
      `robo_status`/`fila_automacao` — status ao vivo do robô, escrito por
      processo externo, e a página existe para o usuário decidir se dispara
      uma tarefa com base no estado atual (cachear arriscaria deixar um botão
      habilitado quando a tarefa já está na fila, gerando pedido duplicado).
      Mesma decisão do `ofertar_lance.py`/`emitir_boleto.py`. Nenhuma escrita
      nas 7 tabelas de `carregar_dados_iniciais` — só em `fila_automacao`.
- [x] `modulos/yamaha_sim.py` — 3 caches: `_logo_data_uri` e a nova
      `_ler_html_yamaha` (arquivo estático `yamaha.html`, ~100KB, relido do
      disco em TODO render do simulador) cacheadas sem TTL (`@st.cache_data`
      simples — só mudam em deploy); `carregar_base_yamaha` (4 tabelas:
      planos_yamaha, grupos_yamaha, yamaha_assembleias,
      yamaha_grupo_lance_resumo) cacheada com `ttl=60` + `.clear()` nos dois
      formulários manuais que escrevem aqui (editar grupo, lançar
      assembleia). Cuidado tomado: o campo `gerado_em` do payload (timestamp
      "agora") foi tirado de dentro da função cacheada e recalculado a cada
      render em `render_yamaha_sim`, pra não passar a mostrar um horário
      congelado do momento em que os dados foram buscados (ele não é
      exibido no yamaha.html hoje, mas preservei o valor exato mesmo assim).
      As mesmas 4 tabelas também são escritas pelo worker de coleta externo
      (`worker/coletar_grupos.py`, `coletar_tabelas_yamaha.py`,
      `coletar_assembleias.py`) — o ttl=60 é a rede de segurança para essas.
      Testado contra o Supabase real: dado idêntico (exceto `gerado_em`, que
      já era esperado variar) e arquivo idêntico com e sem cache; latência
      cai de ~1.4s/~0.03s/~0.12s para ~0.007s/~0.0005s/~0.0007s.
- [x] `modulos/itau_v2.py` — `_carregar_dados_itau` (Google Drive, ttl=300) já
      estava cacheada corretamente, com `.clear()` no botão "🔄 Recarregar
      Guia" — nada a mudar aí. Adicionado só o cache do arquivo estático
      `itau_v2.html` (~86KB, relido do disco a cada render), na nova
      `_ler_html_itau_v2` (`@st.cache_data` sem TTL, mesmo padrão do
      `yamaha_sim.py`). Testado: conteúdo idêntico, latência cai de ~0.10s
      para ~0.0004s.
- [ ] `modulos/integracao_site.py`
- [ ] `modulos/importar_comissoes.py`
- [ ] `modulos/assistente.py`
- [ ] `modulos/midias.py`
- [ ] `modulos/senhas.py`
- [ ] `modulos/tema.py`

## Decisões de "não cachear" (revisar com calma depois)

- `modulos/ofertar_lance.py` (`_mapa_ultimo_lance`, `_painel_status`): leem
  `fila_automacao`, que é escrita em tempo real pelo worker externo do robô
  (fora do processo do Streamlit, então `.clear()` local não alcançaria essas
  escritas) e a tela existe justamente para mostrar o andamento ao vivo.
  Não cacheado — segue lendo direto do banco a cada rerun, como já era.
- `modulos/emitir_boleto.py` (`_mapa_ultimo_boleto`, `_painel_status`): mesmo
  motivo acima (fila_automacao ao vivo).
- `modulos/robo_painel.py` (`_robo_online`, `_ja_na_fila`): mesmo motivo —
  além disso, cachear `_ja_na_fila` poderia deixar um botão de tarefa
  clicável mesmo com a tarefa já na fila, gerando pedido duplicado ao robô.
