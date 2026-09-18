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
- [ ] `modulos/financeiro.py`
- [ ] `modulos/relatorios.py`
- [ ] `modulos/nova_venda.py`
- [ ] `modulos/baixas.py`
- [ ] `modulos/ofertar_lance.py`
- [ ] `modulos/emitir_boleto.py`
- [ ] `modulos/configuracoes.py`
- [ ] `modulos/assembleias.py`
- [ ] `modulos/robo_painel.py`
- [ ] `modulos/yamaha_sim.py`
- [ ] `modulos/itau_v2.py`
- [ ] `modulos/integracao_site.py`
- [ ] `modulos/importar_comissoes.py`
- [ ] `modulos/assistente.py`
- [ ] `modulos/midias.py`
- [ ] `modulos/senhas.py`
- [ ] `modulos/tema.py`

## Decisões de "não cachear" (revisar com calma depois)

(nenhuma ainda — será preenchido conforme avanço)
