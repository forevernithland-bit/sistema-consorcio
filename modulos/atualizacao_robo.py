# -*- coding: utf-8 -*-
"""
Atualização preliminar ao logar (16/11/2026, pedido do Breno).

Quando alguém loga no ERP, o sistema olha a base e vê o que está PENDENTE de atualizar
nos grupos Yamaha com vaga:
  * vaga velha: conferida há mais de 6 dias, ou grupo com poucas vagas (< 10);
  * assembleia sem resultado: a próxima assembleia já passou e o resultado não está na base,
    ou o último resultado tem mais de 35 dias.
E pede ao robô (fila_automacao, CONFERIR_GRUPOS) com PRIORIDADE BAIXA (60). Se alguém
pedir lance/boleto (10) ou conferir um simulado (30), o robô PAUSA esta tarefa, faz o
pedido e depois CONTINUA de onde parou (handlers_coleta.conferir_grupos guarda o progresso).

Para não repetir à toa: no máximo 1 pedido destes a cada 6 h, e nunca se já houver
coleta de grupos/assembleias ou outra conferência na fila.
"""
import datetime

PRIORIDADE_LOGIN = 60
INTERVALO_HORAS = 6
EXPIRA_PENDENTE_HORAS = 6           # pedido de login parado na fila há mais que isso → expira
MAX_GRUPOS = 60
POUCAS_VAGAS = 10
VALIDADE_VAGAS_DIAS = 6
VALIDADE_ASSEMB_DIAS = 35
FORA_DE_VENDA_DIAS = 30             # grupo que a varredura não vê há 30+ dias saiu de venda: não conferir
TIPOS_COLETA = ["COLETA_GRUPOS", "COLETA_ASSEMBLEIAS", "CONFERIR_GRUPOS"]


def _agora():
    return datetime.datetime.now(datetime.timezone.utc)


def _dt(ts):
    try:
        d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def _data_br(s):
    """'19/11/2026' → date (ou None)."""
    try:
        d, m, a = str(s).strip()[:10].split("/")
        return datetime.date(int(a), int(m), int(d))
    except Exception:
        return None


def grupos_pendentes(sb):
    """(vagas, assembleias) — listas de grupos Yamaha com vaga que precisam do robô."""
    hoje = datetime.date.today()
    grupos = sb.table("grupos_yamaha").select("grupo,vagas,consultado_em,prox_assembleia").execute().data or []
    ass = sb.table("yamaha_assembleias").select("grupo,data_assembleia").execute().data or []
    ult = {}
    for a in ass:
        g, d = str(a.get("grupo")), str(a.get("data_assembleia") or "")[:10]
        if d > ult.get(g, ""):
            ult[g] = d
    por = {}
    for r in grupos:                                   # 1 linha por grupo (a mais recente)
        g = str(r.get("grupo"))
        if g not in por or str(r.get("consultado_em") or "") > str(por[g].get("consultado_em") or ""):
            por[g] = r
    vagas, assemb = [], []
    for g, r in por.items():
        v = r.get("vagas")
        if v is None or int(v) <= 0:
            continue                                   # sem vaga / nunca visto pelo robô: a varredura semanal cuida
        d = _dt(r.get("consultado_em"))
        idade = (_agora() - d).days if d else 999
        if idade > FORA_DE_VENDA_DIAS:
            continue                                   # a varredura semanal não acha mais: saiu de venda
        if int(v) < POUCAS_VAGAS or idade > VALIDADE_VAGAS_DIAS:
            vagas.append(g)
        u = ult.get(g)
        prox = _data_br(r.get("prox_assembleia"))
        try:
            u_dt = datetime.date.fromisoformat(u) if u else None
        except ValueError:
            u_dt = None
        if (u_dt is None or (hoje - u_dt).days > VALIDADE_ASSEMB_DIAS
                or (prox and prox < hoje and u_dt < prox)):
            assemb.append(g)
    chave = lambda x: int(x) if x.isdigit() else 0
    return sorted(vagas, key=chave)[:MAX_GRUPOS], sorted(assemb, key=chave)[:MAX_GRUPOS]


def _expirar_velhos(sb):
    """Pedido de login parado na fila há horas (ex.: PC desligado) não pode segurar o robô ligado."""
    limite = (_agora() - datetime.timedelta(hours=EXPIRA_PENDENTE_HORAS)).isoformat()
    try:
        (sb.table("fila_automacao").update({"status": "ERRO", "mensagem": "expirou na fila (robô não pegou a tempo)"})
         .eq("tipo", "CONFERIR_GRUPOS").eq("status", "PENDENTE").lt("criado_em", limite).execute())
    except Exception:
        pass


def pre_atualizar_no_login(sb, usuario="ERP"):
    """Chamado 1x por sessão, logo depois do login. Nunca levanta erro (não pode travar o ERP).
    Devolve um texto curto do que fez (para log/depuração)."""
    try:
        _expirar_velhos(sb)
        ocup = (sb.table("fila_automacao").select("id").in_("tipo", TIPOS_COLETA)
                .in_("status", ["PENDENTE", "PROCESSANDO"]).limit(1).execute().data)
        if ocup:
            return "já tem atualização de grupos na fila"
        desde = (_agora() - datetime.timedelta(hours=INTERVALO_HORAS)).isoformat()
        rec = (sb.table("fila_automacao").select("id").eq("tipo", "CONFERIR_GRUPOS")
               .like("solicitado_por", "LOGIN:%").gte("criado_em", desde).limit(1).execute().data)
        if rec:
            return f"já houve atualização preliminar nas últimas {INTERVALO_HORAS} h"
        vagas, assemb = grupos_pendentes(sb)
        if not vagas and not assemb:
            return "base em dia"
        sb.table("fila_automacao").insert({
            "tipo": "CONFERIR_GRUPOS", "status": "PENDENTE", "prioridade": PRIORIDADE_LOGIN,
            "payload": {"vagas": vagas, "assembleias": assemb, "origem": "login"},
            "solicitado_por": f"LOGIN:{usuario}",
        }).execute()
        return f"pedido ao robô: {len(vagas)} vaga(s), {len(assemb)} assembleia(s)"
    except Exception as e:                              # noqa: BLE001
        return f"não pedi ({str(e)[:80]})"
