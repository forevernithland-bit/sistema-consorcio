# ERP Consorbens — Entendimento do Sistema

> Documento gerado a partir da análise do código-fonte (`CONSORBENS.zip` → `sistema-consorcio-main`).
> É um **ERP interno de uma corretora de consórcios** (Consorbens), separado do site público `consorbensmg.com.br`.

## 1. Stack tecnológica

| Camada | Tecnologia |
|---|---|
| Frontend/App | **Streamlit** (Python) — app de página única com sidebar |
| Banco de dados | **Supabase** (PostgreSQL na nuvem) |
| IA | **Google Gemini** (`google-generativeai`) — assistente "Bento" |
| Integrações | **Google Drive** (mídias), **ViaCEP** (busca de endereço), **WhatsApp** (links `wa.me`) |
| Documentos | `python-docx` (import/export da base da IA), `openpyxl` |
| Gráficos | `altair` |

Dependências em `requirements.txt`. Segredos ficam em `st.secrets` (Streamlit): `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`, `gcp_service_account`, `DRIVE_FOLDER_IDS`.

## 2. Estrutura de arquivos

```
ERP_CONSORBENS/
├── app.py               # Ponto de entrada: config, login, roteador de menu, CSS
├── database.py          # Conexão Supabase + carga inicial de todas as tabelas
├── regras.py            # Motor de cálculo de comissões e parcelas (coração financeiro)
├── utils.py             # Formatadores (BRL, telefone, data), normalizadores, Google Drive
├── requirements.txt
├── logo.png
├── modulos/
│   ├── dashboard.py     # Lista de vendas, ficha do cliente, gráficos, edição de cotas
│   ├── nova_venda.py    # Cadastro de cliente + venda (multi-cotas, busca CEP)
│   ├── assembleias.py   # Calendário de assembleias + lembrete WhatsApp
│   ├── relatorios.py    # Relatórios por vendedor/administradora + gerar comissionamento
│   ├── baixas.py        # Baixa (pagamento) de parcelas de comissão
│   ├── configuracoes.py # Cadastro de administradoras, regras de comissão, regras internas
│   ├── senhas.py        # Cofre de senhas da empresa (import/export CSV)
│   ├── assistente.py    # Assistente IA "Bento" (Gemini) + base de conhecimento
│   ├── midias.py        # Galeria de mídias vinda do Google Drive
│   └── itau_v2.py       # Lógica do simulador Itaú V2
└── *.html               # Simuladores embutidos (yamaha, itau, itau_v2, guia, comparador)
```

## 3. Perfis de acesso

- **Master** (perfil "Master" ou login `breno`/`uriel`): acesso total — vê comissões, valores de sócios, edita tudo, aba Senhas e Base de Conhecimento.
- **Vendedor**: vê apenas suas próprias vendas e sua parte da comissão; não vê valores dos sócios nem edita cadastros.
- **Visitante (não logado)**: só acessa os simuladores públicos e o link de Cartas Contempladas.

Login validado em `database.verificar_login_db` (login case-insensitive, senha em texto puro na tabela `usuarios` — **ponto de atenção de segurança**).

## 4. Tabelas do Supabase (inferidas do código)

| Tabela | Uso |
|---|---|
| `vendas` | Cotas vendidas: NOME, DATA, PRODUTO, VENDEDOR, GRUPO, COTA, ADMINISTRADORA, STATUS, VALOR |
| `clientes` | Cadastro: Nome, Telefone, Email, Endereco, Aniversario, Profissao, Renda, Data_Cadastro |
| `assembleias` | data_evento, descricao |
| `cad_administradoras` | Administradora, CNPJ, Endereço |
| `administradoras` | Regras de comissão por Admin+Produto, colunas P1..P25 (% por parcela) |
| `status_comissoes` | Chave_Unica, Status (Pendente/PAGO), Valor_Pago, Data_Pagamento |
| `config_interna` | Percentuais de divisão sócios + faixas de comissão de terceiros + imposto |
| `usuarios` | login, senha, perfil, nome |
| `senhas_sistema` | Cofre: empresa, login, senha, link, descricao |
| `base_conhecimento_ia` | administradora, regras_operacionais, regras_comissionamento (p/ o Bento) |

## 5. Regra de negócio central — cálculo de comissão (`regras.py`)

1. Para cada venda, busca a regra `administradoras` (Admin + Produto) → percentuais P1..P25.
2. Cada parcela `i`: `comissão_bruta = valor_venda × P_i%`; desconta imposto (`config_interna.Imposto`, padrão 7,16%) → líquido.
3. **Divisão da comissão líquida** conforme o vendedor:
   - `BRENO LIMA` → 70% Breno / 30% Uriel (configurável)
   - `URIEL GOMES` → 70% Uriel / 30% Breno
   - `Consorbens` → 50% / 50%
   - `Vendedor Terceiro` → recebe % por faixa de volume mensal (N1/N2/N3 em `config_interna`); o resto é dividido 50/50 entre os sócios.
4. Data de pagamento prevista = data da venda + 7 dias + (i-1) meses.
5. Status da cota altera a projeção:
   - **Cancelada** → só mantém parcelas já vencidas.
   - **Contemplada** → antecipa todas as parcelas futuras em uma única linha "Antecipação".
   - **Em Atraso** → data "Travada".

## 6. Simuladores (HTML embutidos)

Carregados via `components.html` dentro do Streamlit: Yamaha, Itaú, Itaú V2 (com lógica Python em `itau_v2.py`), Guia de Oportunidades Itaú, e Comparador Financiamento×Consórcio.

## 7. Como rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```
Requer um arquivo `.streamlit/secrets.toml` com as chaves do Supabase, Gemini e Google Cloud. Sem isso, o app para na tela de erro de conexão com o Supabase.

## 8. Pontos de atenção observados

- **Senhas em texto puro** na tabela `usuarios` e no cofre `senhas_sistema` (sem hash/criptografia).
- Chaves/segredos dependem de `st.secrets` — não há `.streamlit/secrets.toml` no repositório (correto por segurança, mas precisa ser recriado para rodar).
- `WhatsApp` de lembrete de assembleia usa número placeholder `5531999999999`.
