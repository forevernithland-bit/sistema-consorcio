"""
Segurança de acesso do ERP Consorbens: senhas criptografadas e permissões.

Senha: PBKDF2-HMAC-SHA256 com sal próprio por usuário (biblioteca padrão do
Python, sem dependência extra). O banco guarda só o hash — nunca a senha.
    formato:  pbkdf2_sha256$<iterações>$<sal_b64>$<hash_b64>

Permissões: cada tela/simulador tem uma chave (PERMISSOES). O Administrador
("Master": Breno e Uriel) enxerga tudo; o Vendedor só o que estiver na lista
dele (`usuarios.permissoes`) — ou o padrão do perfil quando a lista é NULL.
"""
import base64
import hashlib
import hmac
import os
import secrets
import string

ITERACOES = 600_000          # recomendação OWASP p/ PBKDF2-HMAC-SHA256
PREFIXO = "pbkdf2_sha256"
MAX_TENTATIVAS = 5           # erros seguidos antes do bloqueio
BLOQUEIO_MIN = 10            # minutos de bloqueio


# ---------------------------------------------------------------- senha
def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def hash_senha(senha: str, iteracoes: int = ITERACOES) -> str:
    sal = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", str(senha).encode("utf-8"), sal, iteracoes)
    return f"{PREFIXO}${iteracoes}${_b64(sal)}${_b64(dk)}"


def verificar_senha(senha: str, hash_guardado: str) -> bool:
    """True se `senha` confere com o hash. Qualquer formato inesperado = False."""
    try:
        prefixo, it, sal_b64, dk_b64 = str(hash_guardado).split("$")
        if prefixo != PREFIXO:
            return False
        sal = base64.b64decode(sal_b64)
        esperado = base64.b64decode(dk_b64)
        dk = hashlib.pbkdf2_hmac("sha256", str(senha).encode("utf-8"), sal, int(it))
        return hmac.compare_digest(dk, esperado)
    except Exception:
        return False


def precisa_rehash(hash_guardado: str) -> bool:
    """True se o hash foi gerado com menos iterações que o padrão atual."""
    try:
        return int(str(hash_guardado).split("$")[1]) < ITERACOES
    except Exception:
        return True


def gerar_senha_temporaria(tamanho: int = 10) -> str:
    """Senha temporária legível (sem 0/O, 1/l/I), com letra e número."""
    letras = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
    numeros = "23456789"
    while True:
        s = "".join(secrets.choice(letras + numeros) for _ in range(tamanho))
        if any(c in letras for c in s) and any(c in numeros for c in s):
            return s


def validar_forca(senha: str):
    """(ok, mensagem). Mínimo 8 caracteres, com letra e número."""
    senha = str(senha or "")
    if len(senha) < 8:
        return False, "A senha precisa ter pelo menos 8 caracteres."
    if not any(c.isalpha() for c in senha) or not any(c.isdigit() for c in senha):
        return False, "A senha precisa ter letras e números."
    return True, ""


# ----------------------------------------------------------- permissões
# chave -> (rótulo, grupo)
PERMISSOES = {
    "dashboard":     ("Dashboard (só os clientes dele)",          "Telas do sistema"),
    "nova_venda":    ("Nova Venda",                               "Telas do sistema"),
    "ofertar_lance": ("Ofertar Lance (cotas dos clientes dele)",  "Telas do sistema"),
    "boletos":       ("Emissão de Boletos (cotas dos clientes dele)", "Telas do sistema"),
    "relatorios":    ("Relatórios (só a comissão dele)",          "Telas do sistema"),
    "midias":        ("Mídias",                                   "Telas do sistema"),
    "sim_yamaha":    ("Simulador Yamaha",                         "Simuladores"),
    "sim_itau_v2":   ("Simulador Itaú V 2.0",                     "Simuladores"),
    "sim_itau":      ("Simulador Itaú",                           "Simuladores"),
    "oport_itau":    ("Oportunidades Itaú",                       "Simuladores"),
    "comparador":    ("Financiamento x Consórcio",                "Simuladores"),
    "cartas_site":   ("Atalho do admin de Cartas Contempladas",   "Site"),
}

# menu lateral -> chave de permissão (telas só do Administrador não aparecem aqui)
MENU_PARA_PERMISSAO = {
    "Dashboard": "dashboard",
    "Nova Venda": "nova_venda",
    "Ofertar Lance": "ofertar_lance",
    "Emissão de Boletos": "boletos",
    "Relatórios": "relatorios",
    "Mídias": "midias",
    "🏍️ Simulador Yamaha": "sim_yamaha",
    "🚀 Simulador Itaú V 2.0": "sim_itau_v2",
    "🏦 Simulador Itaú": "sim_itau",
    "🎯 Oportunidades Itaú": "oport_itau",
    "⚖️ Financiamento x Consórcio": "comparador",
}

# Padrão do vendedor (usado quando `permissoes` é NULL): igual ao menu que o
# perfil "Vendedor" já tinha antes desta migração.
PERMISSOES_PADRAO_VENDEDOR = [
    "dashboard", "nova_venda", "ofertar_lance", "boletos", "relatorios", "midias",
    "sim_yamaha", "sim_itau_v2", "sim_itau", "oport_itau", "comparador", "cartas_site",
]

# Modelos prontos para a tela de cadastro
MODELOS_PERMISSAO = {
    "Vendedor completo (padrão)": PERMISSOES_PADRAO_VENDEDOR,
    "Vendedor de loja (sem lance e boleto)": [
        "dashboard", "nova_venda", "relatorios", "midias",
        "sim_yamaha", "sim_itau_v2", "sim_itau", "oport_itau", "comparador"],
    "Só simuladores": ["sim_yamaha", "sim_itau_v2", "sim_itau", "oport_itau", "comparador"],
}

PERFIL_ADMIN = "Master"       # valor guardado no banco; no ERP aparece como "Administrador"
PERFIL_VENDEDOR = "Vendedor"
ROTULO_PERFIL = {PERFIL_ADMIN: "Administrador", PERFIL_VENDEDOR: "Vendedor"}


def permissoes_efetivas(perfil, permissoes, eh_admin=False):
    """Conjunto de chaves que o usuário pode usar. Administrador = todas."""
    if eh_admin or perfil == PERFIL_ADMIN:
        return set(PERMISSOES) | {"__admin__"}
    if permissoes is None:
        return set(PERMISSOES_PADRAO_VENDEDOR)
    return {p for p in permissoes if p in PERMISSOES}
