"""
Validação e formatação dos dados cadastrais do vendedor (CNPJ, CPF, telefone, CEP).
"""
import re


def so_digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def validar_cnpj(v) -> bool:
    n = so_digitos(v)
    if len(n) != 14 or n == n[0] * 14:
        return False

    def dv(base, pesos):
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        r = soma % 11
        return "0" if r < 2 else str(11 - r)

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    d1 = dv(n[:12], p1)
    d2 = dv(n[:12] + d1, p2)
    return n[12:] == d1 + d2


def validar_cpf(v) -> bool:
    n = so_digitos(v)
    if len(n) != 11 or n == n[0] * 11:
        return False

    def dv(base, peso_ini):
        soma = sum(int(d) * p for d, p in zip(base, range(peso_ini, 1, -1)))
        r = (soma * 10) % 11
        return "0" if r == 10 else str(r)

    d1 = dv(n[:9], 10)
    d2 = dv(n[:9] + d1, 11)
    return n[9:] == d1 + d2


def fmt_cnpj(v) -> str:
    n = so_digitos(v)
    if len(n) != 14:
        return str(v or "")
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


def fmt_cpf(v) -> str:
    n = so_digitos(v)
    if len(n) != 11:
        return str(v or "")
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def fmt_tel(v) -> str:
    n = so_digitos(v)
    if n.startswith("55") and len(n) in (12, 13):
        n = n[2:]
    if len(n) == 11:
        return f"({n[:2]}) {n[2:7]}-{n[7:]}"
    if len(n) == 10:
        return f"({n[:2]}) {n[2:6]}-{n[6:]}"
    return str(v or "")


def fmt_cep(v) -> str:
    n = so_digitos(v)
    return f"{n[:5]}-{n[5:]}" if len(n) == 8 else str(v or "")
