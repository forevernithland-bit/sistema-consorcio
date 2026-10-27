import streamlit as st
import pandas as pd
from supabase import create_client, Client
from utils import parse_float_safe, limpar_str_nan, normalizar_string, normalizar_produto

# ==========================================
# CONEXÃO COM O BANCO DE DADOS
# ==========================================
@st.cache_resource
def iniciar_conexao() -> Client:
    """Inicia a conexão com o Supabase usando as chaves configuradas nos Secrets"""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


@st.cache_resource
def iniciar_conexao_site():
    """Conexão de LEITURA com o Supabase do SITE (cartas contempladas).
    Projeto/banco diferente do ERP. Usa SITE_SUPABASE_URL / SITE_SUPABASE_KEY
    (chave service_role, só nos secrets do servidor). Retorna None se não
    configurado — a integração fica desligada e o ERP segue normal."""
    try:
        url = st.secrets["SITE_SUPABASE_URL"]
        key = st.secrets["SITE_SUPABASE_KEY"]
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None

PAGINA = 1000   # o PostgREST do Supabase devolve no máximo 1000 linhas por consulta


def ler_tudo(supabase: Client, nome_tabela: str, colunas: str = "*", ordem: str = "id", desc: bool = False,
             filtros=None) -> list:
    """Lê a tabela INTEIRA, de 1000 em 1000 (o Supabase corta em 1000 linhas
    sem avisar — sem isto, vendas/comissões acima de 1000 sumiam das telas e da
    checagem de duplicidade). Ordenado por `ordem` para a paginação ser estável.
    `filtros` = lista de (metodo, coluna, valor), ex.: [("eq", "tipo", "BOLETO")].
    Erro de rede/banco SOBE (não vira tabela vazia)."""
    try:
        return _ler_paginas(supabase, nome_tabela, colunas, ordem, desc, filtros)
    except Exception as e:
        # tabela sem a coluna de ordenação (ex.: financeiro_datas, resultado_socios_mensal não têm `id`):
        # lê de novo sem ordenar, em vez de derrubar a tela
        if ordem and ("42703" in str(e) or "does not exist" in str(e)):
            return _ler_paginas(supabase, nome_tabela, colunas, None, desc, filtros)
        raise


def _ler_paginas(supabase, nome_tabela, colunas, ordem, desc, filtros):
    linhas, ini = [], 0
    while True:
        q = supabase.table(nome_tabela).select(colunas)
        for metodo, col, val in (filtros or []):
            q = getattr(q, metodo)(col, val)
        if ordem:
            q = q.order(ordem, desc=desc)
        if not hasattr(q, "range"):          # cliente simplificado (testes): sem paginação
            return list(q.execute().data or [])
        lote = q.range(ini, ini + PAGINA - 1).execute().data or []
        linhas.extend(lote)
        if len(lote) < PAGINA:
            return linhas
        ini += PAGINA


def carregar_tabela(supabase: Client, nome_tabela: str, tolerante: bool = True) -> pd.DataFrame:
    """Busca todos os dados de uma tabela específica (todas as páginas).
    tolerante=True: erro vira tabela vazia (comportamento antigo);
    tolerante=False: o erro sobe — usado nas tabelas essenciais, para uma falha
    de rede não ser confundida com "não há dados" (nem ficar 60 s no cache)."""
    try:
        return pd.DataFrame(ler_tudo(supabase, nome_tabela))
    except Exception:
        if not tolerante:
            raise
        return pd.DataFrame()

# ==========================================
# CARREGAMENTO E LIMPEZA INICIAL DE DADOS
# ==========================================
@st.cache_data(ttl=60)
def carregar_dados_iniciais(_supabase: Client):
    """Carrega e padroniza todas as tabelas cruciais do sistema ao iniciar.

    Cacheado por até 60s (st.cache_data) para evitar refazer ~7 fetches completos
    do Supabase a cada rerun/clique de navegação. Toda escrita nas tabelas lidas
    aqui (vendas, clientes, assembleias, cad_administradoras, administradoras,
    status_comissoes, config_interna) DEVE chamar carregar_dados_iniciais.clear()
    logo após o insert/update/delete, para não mostrar dado desatualizado antes
    do TTL expirar. Parâmetro com "_" no nome (_supabase) para o Streamlit não
    tentar hashear o Client do Supabase.
    """
    supabase = _supabase

    # 1. Carregar Vendas
    df_vendas_bd = carregar_tabela(supabase, "vendas", tolerante=False)
    if not df_vendas_bd.empty:
        df_vendas_global = df_vendas_bd.copy()
        df_vendas_global.rename(columns={"NOME": "Nome do cliente"}, inplace=True)
        # Padroniza datas e números
        df_vendas_global['Data_Real'] = pd.to_datetime(df_vendas_global['DATA'], dayfirst=True, errors='coerce')
        df_vendas_global['Valor_Numerico'] = df_vendas_global['VALOR'].apply(parse_float_safe)
        df_vendas_global['GRUPO'] = df_vendas_global['GRUPO'].apply(limpar_str_nan)
        df_vendas_global['COTA'] = df_vendas_global['COTA'].apply(limpar_str_nan)
    else:
        df_vendas_global = pd.DataFrame()

    # 2. Carregar Clientes
    df_cli = carregar_tabela(supabase, "clientes", tolerante=False)
    
    # 3. Carregar Assembleias
    df_ass = carregar_tabela(supabase, "assembleias", tolerante=False)
    if not df_ass.empty:
        df_ass['data_dt'] = pd.to_datetime(df_ass['data_evento'], format="%d/%m/%Y", errors='coerce')

    # 4. Carregar Administradoras
    df_admin_cad = carregar_tabela(supabase, "cad_administradoras", tolerante=False)
    lista_admin_bd = df_admin_cad['Administradora'].tolist() if not df_admin_cad.empty else ["Nenhuma administradora cadastrada"]

    # 5. Carregar Regras de Comissionamento
    df_admin = carregar_tabela(supabase, "administradoras", tolerante=False)
    if not df_admin.empty:
        df_admin['Admin_Norm'] = df_admin['Administradora'].apply(normalizar_string)
        df_admin['Prod_Norm'] = df_admin['Produto'].apply(normalizar_produto)
        # Tipo de parcela da regra (linear x reduzida). Vazio = regra genérica.
        if 'Tipo_Parcela' in df_admin.columns:
            df_admin['Tipo_Norm'] = df_admin['Tipo_Parcela'].apply(normalizar_string)
        else:
            df_admin['Tipo_Parcela'] = ""
            df_admin['Tipo_Norm'] = ""

    # 6. Carregar Status das Comissões (Pagas ou Pendentes)
    df_status = carregar_tabela(supabase, "status_comissoes", tolerante=False)
    # Novo formato: armazena status e data de pagamento para permitir edição
    status_dict = df_status.set_index('Chave_Unica').to_dict('index') if not df_status.empty else {}

    # 7. Carregar Configurações Internas e Impostos
    cfg_padrao = {
        "Breno_Breno": 70.0, "Breno_Uriel": 30.0, "Uriel_Uriel": 70.0, "Uriel_Breno": 30.0,
        "Cons_Breno": 50.0, "Cons_Uriel": 50.0, "T1_Max": 500000.0, "T1_Pct": 1.0, "T1_Parc": 4,
        "T2_Max": 1500000.0, "T2_Pct": 1.5, "T2_Parc": 5, "T3_Pct": 2.0, "T3_Parc": 5, "Imposto": 7.16
    }
    
    df_cfg = carregar_tabela(supabase, "config_interna", tolerante=False)
    cfg_id = None
    if not df_cfg.empty:
        cfg = df_cfg.iloc[0].to_dict()
        cfg_id = cfg.get('id')
    else:
        # Se não houver configuração, insere o padrão. Só chega aqui se a LEITURA
        # deu certo e a tabela está mesmo vazia (erro de rede agora sobe — antes
        # uma falha momentânea gravava uma 2ª configuração com valores padrão).
        res = supabase.table("config_interna").insert(cfg_padrao).execute()
        cfg = cfg_padrao
        cfg_id = res.data[0]['id'] if res.data else None

    return df_vendas_global, df_cli, df_ass, df_admin_cad, lista_admin_bd, df_admin, status_dict, cfg, cfg_id

# ==========================================
# FUNÇÕES DE ATUALIZAÇÃO NO BANCO
# ==========================================
def salvar_status_comissoes(supabase: Client, df_editado: pd.DataFrame, df_original: pd.DataFrame) -> bool:
    """Verifica quais linhas mudaram de status ou data na tabela e salva no Supabase"""
    
    # Preenchemos valores nulos/NaN com strings vazias temporariamente apenas para a comparação matemática não falhar
    df_ed_cmp = df_editado.fillna("")
    df_or_cmp = df_original.fillna("")
    
    # Detecta mudança no Status OU na Data Recebimento de forma segura
    mudancas = df_editado[(df_ed_cmp['Status'] != df_or_cmp['Status']) | (df_ed_cmp['Data Recebimento'] != df_or_cmp['Data Recebimento'])]
    
    if not mudancas.empty:
        for _, row in mudancas.iterrows():
            chave = str(row['Chave'])
            novo_status = str(row['Status'])
            
            # Sanitiza a data: Se for nula (NaN), enviamos None (nulo no banco), senão enviamos o texto exato
            nova_data = row['Data Recebimento']
            if pd.isna(nova_data):
                nova_data = None
            else:
                nova_data = str(nova_data).strip()
                # "⏳ Próxima comissão" / "⚠️ Travada (Atraso)" são avisos da tela, não datas: gravar isso trava a linha sem data
                if nova_data.startswith(("⏳", "⚠")):
                    nova_data = None
            
            payload = {
                "Chave_Unica": chave, 
                "Status": novo_status, 
                "Data_Pagamento": nova_data
            }
            
            try:
                # Verifica se já existe um registro para esta parcela
                existe = supabase.table("status_comissoes").select("id").eq("Chave_Unica", chave).execute()
                if existe.data:
                    # Atualiza o existente
                    supabase.table("status_comissoes").update(payload).eq("id", existe.data[0]['id']).execute()
                else:
                    # Cria um novo registro
                    supabase.table("status_comissoes").insert(payload).execute()
            except Exception as e:
                # as parcelas anteriores JÁ foram gravadas: limpa o cache para a tela
                # mostrar o que de fato ficou no banco, e diz claramente onde parou.
                carregar_dados_iniciais.clear()
                st.error(f"Erro ao salvar a parcela {chave}: {e}. As parcelas antes dela já foram salvas; "
                         "confira e salve de novo as que faltaram.")
                return False

        carregar_dados_iniciais.clear()
        return True
    return False

# ==========================================
# FUNÇÕES DE AUTENTICAÇÃO E GESTÃO DE USUÁRIOS
# ==========================================
def _escapar_like(txt: str) -> str:
    """Escapa %, _ e a barra invertida para o ilike tratar o login como texto literal."""
    barra = chr(92)
    return str(txt).replace(barra, barra + barra).replace("%", barra + "%").replace("_", barra + "_")


def _buscar_usuario(supabase: Client, login_input: str):
    """Usuário pelo login (sem diferenciar maiúscula/minúscula), ou None."""
    login = str(login_input or "").strip()
    if not login:
        return None
    res = supabase.table("usuarios").select("*").ilike("login", _escapar_like(login)).execute()
    for u in (res.data or []):
        if str(u.get("login", "")).strip().lower() == login.lower():
            return u
    return None


def _atualizar_usuario(supabase: Client, user_id, campos: dict):
    """update tolerante: se a migração 26 ainda não rodou (colunas novas
    ausentes) o update inteiro falha e NADA é gravado — em especial a senha
    em texto puro continua intacta (nunca se apaga a senha sem antes ter o
    hash gravado na mesma operação)."""
    try:
        supabase.table("usuarios").update(campos).eq("id", user_id).execute()
        return True
    except Exception:
        return False


@st.cache_data(ttl=30)
def carregar_sessao_usuario(_supabase, login):
    """Situação ATUAL do usuário logado (ativo? perfil? telas liberadas?).
    Reconsultada a cada 30 s: desativar um usuário ou mudar as telas dele no
    cadastro vale rápido, sem esperar ele sair e entrar."""
    try:
        u = _buscar_usuario(_supabase, login)
    except Exception:
        return None
    if not u:
        return None
    return {"login": u.get("login"), "nome": u.get("nome"), "perfil": u.get("perfil"),
            "ativo": u.get("ativo") is not False, "permissoes": u.get("permissoes"),
            "trocar_senha": bool(u.get("trocar_senha"))}


@st.cache_data(ttl=60)
def vendedores_cadastrados(_supabase):
    """Nomes dos usuários Vendedor ATIVOS (entram nas listas de vendedor das telas)."""
    try:
        res = _supabase.table("usuarios").select("nome,perfil,ativo").execute().data or []
        return sorted({str(r["nome"]).strip() for r in res
                       if r.get("perfil") == "Vendedor" and r.get("ativo") is not False and r.get("nome")})
    except Exception:
        return []


def autenticar(supabase: Client, login_input: str, senha_input: str):
    """Valida login+senha. Devolve (usuario|None, mensagem_de_erro).

    - senha conferida contra o HASH (PBKDF2); usuário antigo ainda com senha em
      texto é aceito UMA vez e já convertido para hash (o texto é apagado);
    - usuário desativado não entra;
    - 5 erros seguidos bloqueiam o login por 10 minutos.
    """
    from datetime import datetime, timezone, timedelta
    import hmac
    from seguranca import (verificar_senha, hash_senha, precisa_rehash,
                           MAX_TENTATIVAS, BLOQUEIO_MIN)
    try:
        u = _buscar_usuario(supabase, login_input)
    except Exception:
        return None, "Não consegui consultar o banco agora. Tente de novo."
    if not u:
        return None, "Usuário ou senha incorretos."

    agora = datetime.now(timezone.utc)
    if u.get("ativo") is False:
        return None, "Este usuário está desativado. Fale com o administrador."
    bloq = u.get("bloqueado_ate")
    if bloq:
        try:
            ate = datetime.fromisoformat(str(bloq).replace("Z", "+00:00"))
            if ate > agora:
                faltam = max(1, int((ate - agora).total_seconds() // 60) + 1)
                return None, f"Muitas tentativas erradas. Tente de novo em {faltam} min."
        except Exception:
            pass

    senha_input = str(senha_input or "")
    h = (u.get("senha_hash") or "").strip()
    plano = (u.get("senha") or "")
    ok = False
    migrar = False
    if h:
        ok = verificar_senha(senha_input, h)
        if ok and precisa_rehash(h):
            migrar = True
    elif plano:                                    # legado: texto puro (case sensitive)
        ok = hmac.compare_digest(str(plano), senha_input)
        migrar = ok

    if not ok:
        falhas = int(u.get("tentativas_falhas") or 0) + 1
        campos = {"tentativas_falhas": falhas}
        if falhas >= MAX_TENTATIVAS:
            campos = {"tentativas_falhas": 0,
                      "bloqueado_ate": (agora + timedelta(minutes=BLOQUEIO_MIN)).isoformat()}
        _atualizar_usuario(supabase, u["id"], campos)
        return None, "Usuário ou senha incorretos."

    campos = {"tentativas_falhas": 0, "bloqueado_ate": None, "ultimo_login": agora.isoformat()}
    if migrar:
        campos.update({"senha_hash": hash_senha(senha_input), "senha": None})
    _atualizar_usuario(supabase, u["id"], campos)
    return u, ""


def verificar_login_db(supabase: Client, login_input: str, senha_input: str):
    """Compatível com o código antigo: devolve o usuário ou None."""
    usuario, _ = autenticar(supabase, login_input, senha_input)
    return usuario


def atualizar_senha_usuario(supabase: Client, login_input: str, nova_senha: str, trocar_no_proximo_login: bool = False):
    """Grava a nova senha CRIPTOGRAFADA (e apaga qualquer texto puro antigo)."""
    from seguranca import hash_senha
    from datetime import datetime, timezone
    try:
        u = _buscar_usuario(supabase, login_input)
        if not u:
            return False
        campos = {"senha_hash": hash_senha(nova_senha), "senha": None,
                  "trocar_senha": bool(trocar_no_proximo_login),
                  "tentativas_falhas": 0, "bloqueado_ate": None,
                  "atualizado_em": datetime.now(timezone.utc).isoformat()}
        try:
            supabase.table("usuarios").update(campos).eq("id", u["id"]).execute()
            return True
        except Exception:
            # migração 26 ainda não rodou: sem coluna de hash não há como criptografar
            return False
    except Exception as e:
        return False
