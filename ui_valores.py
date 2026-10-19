"""Campos de valor em R$ com separador de milhares (1.234.567,89).

`st.number_input` não mostra ponto de milhar. Estes campos são texto, reformatados quando a
pessoa sai do campo (Enter/Tab), e devolvem sempre um número (float)."""
import re

import streamlit as st
import streamlit.components.v1 as components

# Marcas invisíveis no fim do rótulo: dizem ao script do navegador que o campo é de valor.
_M_DEC = "​"   # com 2 casas decimais
_M_INT = "‌"   # inteiro

_JS_MASCARA = r"""
<script>
(function () {
  var P = window.parent, doc = P.document;
  if (P.__mascaraMilhar) return;
  P.__mascaraMilhar = true;
  var setter = Object.getOwnPropertyDescriptor(P.HTMLInputElement.prototype, 'value').set;
  doc.addEventListener('input', function (ev) {
    var el = ev.target;
    if (!el || el.tagName !== 'INPUT') return;
    var lab = el.getAttribute('aria-label') || '';
    var casas = lab.endsWith('​') ? 2 : (lab.endsWith('‌') ? 0 : (lab.endsWith('‍') ? -2 : -1));
    if (casas === -1) return;
    if (casas === -2) {            // estilo "R$ 1.234,56": os dígitos entram como centavos
      var dg = el.value.replace(/\D/g, '').replace(/^0+/, '');
      var o2 = '';
      if (dg !== '') {
        while (dg.length < 3) dg = '0' + dg;
        o2 = 'R$ ' + dg.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ',' + dg.slice(-2);
      }
      if (o2 !== el.value) {
        setter.call(el, o2);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        try { el.setSelectionRange(o2.length, o2.length); } catch (e) {}
      }
      return;
    }
    var old = el.value, pos = el.selectionStart == null ? old.length : el.selectionStart;
    var digitsBefore = (old.slice(0, pos).match(/\d/g) || []).length;
    var charBefore = old.charAt(pos - 1);
    var partes = old.split(',');
    var ip = partes[0].replace(/\D/g, '').replace(/^0+(?=\d)/, '');
    var dp = partes.slice(1).join('').replace(/\D/g, '');
    var out = ip.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    var temVirgula = casas > 0 && old.indexOf(',') >= 0;
    if (temVirgula) out += ',' + dp.slice(0, casas);
    if (out === old) return;
    setter.call(el, out);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    var p = 0, c = 0;
    if (temVirgula && charBefore === ',') { p = out.indexOf(',') + 1; }
    else { while (p < out.length && c < digitsBefore) { if (/\d/.test(out.charAt(p))) c++; p++; } }
    try { el.setSelectionRange(p, p); } catch (e) {}
  }, true);
})();
</script>
"""


def ativar_mascara_milhar():
    """Liga, uma vez por página, a formatação de milhares ENQUANTO se digita nos campos feitos por input_valor."""
    components.html(_JS_MASCARA, height=0)


def parse_valor(txt, padrao=0.0):
    """'1.000.000' / '1.234,56' / '1000000' / 'R$ 500.000,00' -> float. Inválido -> padrao."""
    bruto = str(txt if txt is not None else "").upper().replace("R$", "")
    if re.search(r"[A-Z]", bruto):          # "500 mil", "1e5", "abc": não adivinha número no meio do texto
        return padrao
    t = re.sub(r"[^\d,.\-]", "", bruto)
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
    label = label + (_M_DEC if casas > 0 else _M_INT)          # marca p/ a máscara em tempo real
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
