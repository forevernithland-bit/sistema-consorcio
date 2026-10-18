"""Campos de valor em R$ com separador de milhares (1.234.567,89).

`st.number_input` não mostra ponto de milhar. Estes campos são texto, reformatados quando a
pessoa sai do campo (Enter/Tab), e devolvem sempre um número (float)."""
import re

import streamlit as st


def parse_valor(txt, padrao=0.0):
    """'1.000.000' / '1.234,56' / '1000000' / 'R$ 500.000,00' -> float. Inválido -> padrao."""
    t = re.sub(r"[^\d,.\-]", "", str(txt if txt is not None else ""))
    if t in ("", "-"):
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):          # só pontos de milhar
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return padrao


def fmt_valor(v, casas=2):
    """1234567.8 -> '1.234.567,80' (casas=0 -> '1.234.568')."""
    try:
        s = f"{float(v):,.{casas}f}"
    except (TypeError, ValueError):
        s = f"{0:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def input_valor(label, value=0.0, key=None, casas=2, em_form=False, help=None, disabled=False,
                min_value=0.0, placeholder=None):
    """Campo de valor com milhar. Devolve float. `em_form=True` dentro de st.form (sem callback;
    o texto é lido no envio). Passe `key` único por registro quando o valor inicial mudar."""
    if em_form or key is None:
        txt = st.text_input(label, value=fmt_valor(value, casas), key=key, help=help, disabled=disabled,
                            placeholder=placeholder)
    else:
        if key not in st.session_state:
            st.session_state[key] = fmt_valor(value, casas)

        def _reformata():
            st.session_state[key] = fmt_valor(parse_valor(st.session_state[key]), casas)
        txt = st.text_input(label, key=key, on_change=_reformata, help=help, disabled=disabled,
                            placeholder=placeholder)
    v = parse_valor(txt)
    return max(v, min_value) if min_value is not None else v
