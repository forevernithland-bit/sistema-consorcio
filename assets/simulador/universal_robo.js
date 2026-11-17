/* universal_robo.js — Simulador Consorbens × robô (16/11/2026)
   Injetado pelo modulos/simulador_universal.py logo depois do script principal.
   1) Depois de cada simulação, manda ao ERP os grupos Yamaha que apareceram (campo oculto
      "univ_conferir"). O ERP decide se precisa conferir vaga/assembleia e chama o robô.
   2) Mostra no topo do resultado a faixa "Aguarde, atualizando grupos enquanto o robô atualiza"
      (window.__ROBO vem do ERP com o estado).
   3) Quando o robô termina, o ERP recarrega a página com a base nova: aqui a gente restaura
      o que foi digitado e refaz a simulação sozinho. */
(function () {
  "use strict";
  var R = window.__ROBO || {};
  var K_ULT = "cbx_univ_ultima", K_ENV = "cbx_univ_enviado";
  function ss(k, v) {
    try { if (v === undefined) return sessionStorage.getItem(k); sessionStorage.setItem(k, v); } catch (e) { return null; }
  }
  function $(id) { return document.getElementById(id); }
  function U() { return window.__univ || {}; }

  /* ---------- faixa de aviso ---------- */
  var CORES = {
    fila:    ["#fff7e3", "#5c4511", "#f0cf7a"],
    rodando: ["#fff7e3", "#5c4511", "#f0cf7a"],
    ok:      ["#e4f6ee", "#0b5e3e", "#9fd8bd"],
    offline: ["#fdeceb", "#6d1d18", "#eba4a0"],
    erro:    ["#fdeceb", "#6d1d18", "#eba4a0"],
    demorou: ["#eef3f7", "#24384a", "#b9c8d6"],
    base_salva: ["#eef3f7", "#24384a", "#b9c8d6"]
  };
  function textoFaixa() {
    var d = R.detalhe ? " (" + R.detalhe + ")" : "";
    switch (R.estado) {
      case "fila":
      case "rodando": return "<b>⏳ Aguarde, atualizando grupos enquanto o robô atualiza" + d + ".</b> Os números abaixo usam a base mais recente e se atualizam sozinhos quando o robô terminar.";
      case "ok": return "<b>✅ Grupos atualizados pelo robô às " + R.hora + d + ".</b> Esta simulação já usa os dados novos.";
      case "offline": return "<b>🔌 Robô desligado:</b> não deu para conferir agora" + d + ". A simulação usa a base mais recente do sistema; confira a vaga antes de fechar.";
      case "erro": return "<b>⚠️ O Newcon não respondeu agora</b>" + d + ". A simulação usa a base mais recente do sistema.";
      case "demorou": return "<b>⌛ O robô ainda não terminou de conferir</b>" + d + ". A simulação usa a base mais recente; a conferência continua na fila.";
      case "base_salva": return "<b>⚡ Usando a base salva.</b> O robô continua conferindo em segundo plano" + d + "; na próxima simulação os dados já estarão atualizados.";
    }
    return "";
  }
  var mexendo = false;
  function faixa() {
    var res = $("res"); if (!res) return;
    mexendo = true;
    var old = $("roboFaixa"); if (old) old.remove();
    var t = R.estado && res.firstChild ? textoFaixa() : "";
    if (t) {
      var c = CORES[R.estado] || CORES.demorou, d = document.createElement("div");
      d.id = "roboFaixa"; d.setAttribute("role", "status");
      d.style.cssText = "margin:4px 0 12px;padding:12px 16px;border-radius:14px;font-size:14px;line-height:1.5;"
        + "background:" + c[0] + ";color:" + c[1] + ";border:1.5px solid " + c[2];
      d.innerHTML = t;
      if (R.estado === "fila" || R.estado === "rodando") {
        var b = document.createElement("button");
        b.type = "button"; b.textContent = "⚡ Usar base salva";
        b.title = "Para de esperar o robô e segue com os dados que já estão no sistema";
        b.style.cssText = "display:inline-block;margin-left:10px;margin-top:6px;padding:7px 14px;border-radius:10px;border:0;"
          + "background:#5c4511;color:#fff;font:inherit;font-weight:800;font-size:13px;cursor:pointer";
        b.addEventListener("click", function () { b.disabled = true; b.textContent = "Usando a base salva…"; ponte("__BASE__"); });
        d.appendChild(b);
      }
      res.insertBefore(d, res.firstChild);
    }
    setTimeout(function () { mexendo = false; }, 0);
  }

  /* ---------- guarda o que foi digitado / refaz depois do recarregamento ---------- */
  function guardar() {
    var S = U().S; if (!S || !S.res) return;
    ss(K_ULT, JSON.stringify({ nome: $("nome").value, liq: $("liq").value, rec: $("rec").value, par: $("par").value,
                               ml: !!($("minLance") && $("minLance").checked), mp: !!($("minParc") && $("minParc").checked),
                               prod: S.prod, sel: S.sel, t: Date.now() }));
  }
  function restaurar() {
    var x; try { x = JSON.parse(ss(K_ULT) || "null"); } catch (e) { x = null; }
    if (!x || Date.now() - x.t > 30 * 60 * 1000 || ($("res") && $("res").firstChild)) return;
    $("nome").value = x.nome || ""; $("liq").value = x.liq || ""; $("rec").value = x.rec || ""; $("par").value = x.par || "";
    if ($("minLance")) $("minLance").checked = !!x.ml;
    if ($("minParc")) $("minParc").checked = !!x.mp;
    if (typeof window.syncMin === "function") window.syncMin();
    var b = document.querySelector('.prod[data-p="' + x.prod + '"]'); if (b) b.click();
    if (!x.liq) return;
    $("go").click();
    var S = U().S;
    if (S && x.sel && S.res) {     // volta para a opção que estava aberta em cada administradora
      var muda = false;
      ["yamaha", "itau"].forEach(function (a) { if (x.sel[a] && S.res[a] && S.res[a].length > x.sel[a]) { S.sel[a] = x.sel[a]; muda = true; } });
      if (muda) { var o = document.querySelector('.opt[data-adm="yamaha"][data-k="' + S.sel.yamaha + '"]'); if (o) o.click(); }
    }
  }

  /* ---------- manda os grupos ao ERP ---------- */
  function enviar() {
    var S = U().S; if (!S || !S.res) return;
    var gs = {};
    (S.res.yamaha || []).slice(0, 5).forEach(function (v) { gs[v.g.g] = 1; });
    var lista = Object.keys(gs).sort();
    if (!lista.length) return;
    var chave = lista.join(",");
    if (ss(K_ENV) === chave) return;
    if (ponte(chave)) ss(K_ENV, chave);
  }
  /* escreve no campo oculto do ERP e dá Enter (o Streamlit roda de novo com o valor) */
  function ponte(valor) {
    try {
      var P = window.parent, doc = P && P.document; if (!doc || P === window) return false;
      var inp = doc.querySelector('input[aria-label="univ_conferir"]'); if (!inp) return false;
      var setter = Object.getOwnPropertyDescriptor(P.HTMLInputElement.prototype, "value").set;
      setter.call(inp, valor + "|" + Date.now().toString(36));
      inp.dispatchEvent(new P.Event("input", { bubbles: true }));
      inp.dispatchEvent(new P.KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
      return true;
    } catch (e) { return false; /* fora do ERP (arquivo solto): só não pede ao robô */ }
  }

  var res = $("res");
  if (res && window.MutationObserver) {
    new MutationObserver(function () {
      if (mexendo) return;
      if (!res.firstChild || ($("roboFaixa") && res.childNodes.length === 1)) return;
      guardar();
      faixa();
      setTimeout(enviar, 400);
    }).observe(res, { childList: true });
  }
  restaurar();
})();
