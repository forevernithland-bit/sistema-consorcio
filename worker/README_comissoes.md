# Baixar histórico de Comissões Pagas da Yamaha (tarefa avulsa)

Puxa do Newcon **todos os relatórios "Comissões Pagas" quinzenais** de
`01/10/2024` até `15/07/2026` (o resto já está em `comissoes_pagas` no ERP),
salva cada um em PDF nomeado por período e no fim confere se bateu tudo.

Roda **no PC do escritório** (é onde tem acesso ao Newcon), reaproveitando o
login/sessão do robô de lances (`newcon.py`). **Não entra na fila** do robô —
é script solto, roda quando você quiser.

## Arquivos

| Arquivo | O quê |
|---|---|
| `periodos_comissao.json` | Os 43 períodos quinzenais + nome de cada PDF. Já pronto. |
| `baixar_comissoes.py` | Abre o Newcon, faz Venda → Comissão, gera e salva os 43 PDFs. |
| `conferir_comissoes.py` | Lê os PDFs baixados, soma e confere contra o relatório geral. **Já funciona.** |

## Passo a passo

### 1. Descobrir os campos da tela (1ª vez só)

O robô ainda **não conhecia** a tela de Comissão. Os seletores no
`baixar_comissoes.py` (dict `SELETORES`) são um chute pelo padrão do Newcon.
Para acertar:

```bash
cd worker
python baixar_comissoes.py --descobrir
```

Ele loga, abre **Venda → Comissão** e imprime todos os `id`/nome de campo e
botão da tela. Copie essa saída e me mande (ou ajuste o dict `SELETORES` você
mesmo). Enquanto os seletores não estiverem certos, o passo 2 vai falhar.

### 2. Testar com 1 período

```bash
python baixar_comissoes.py --so 01/10/2024
```

Confere no `Downloads\Comissoes Yamaha\` se saiu o PDF certo (Analítico,
Quebra de Página, 2ª linha de detalhes). A tela de opções é uma só: marca
**Analítico + Quebra de Página + Demonstrar 2ª linha** e clica **Imprimir**.

### 3. Rodar tudo

```bash
python baixar_comissoes.py
```

Baixa os 43 (pula os que já existirem — dá pra parar e continuar). Modelo de
impressão: **Filial** (igual aos PDFs que você já tinha). Para o modelo
"Comissionado", rode com `set MODELO_COMISSAO=Comissionado` antes. O
importador do ERP lê os dois.

### 4. Conferir ("bater 100%")

```bash
python baixar_comissoes.py --geral          # 1 relatório 01/10/2024 → hoje
python conferir_comissoes.py --geral "C:\Users\desta\Downloads\Comissoes Yamaha\GERAL ....pdf"
```

Mostra a tabela período a período, aponta **quinzena faltando** ou
**duplicada**, e no fim compara **soma dos quinzenais × relatório geral**
(valor de comissão e nº de linhas). Também lista o que já está no ERP.

> ⚠️ **Valor de venda ≠ valor de comissão.** O relatório soma comissão paga
> por parcela, não o crédito das cartas. A conferência que fecha é
> *soma dos quinzenais = relatório geral do período inteiro*.

### 5. Importar no ERP (opcional, depois)

ERP → **Importar Comissões** → sobe cada PDF. Já pula período repetido.

## Config (`worker/.env`)

Usa o mesmo `.env` do robô de lances (`SUPABASE_URL/KEY`, `NEWCON_URL`,
`NEWCON_EMPRESA_COFRE`). Opcional:

```
PASTA_COMISSOES=C:\Users\desta\Downloads\Comissoes Yamaha
MODELO_COMISSAO=Filial
```
