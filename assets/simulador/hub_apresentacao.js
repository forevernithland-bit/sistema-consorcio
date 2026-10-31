/* =====================================================================
   Hub de simuladores Consorbens — camada visual injetada no simulador.
   Injetada pelo modulos/simuladores_hub.py ANTES do </body> de cada
   simulador (yamaha.html, itau_v2.html, itau.html), junto com a skin
   (hub_skin.css). Faz:
     1) hero Consorbens com KPIs clicáveis + barra de abas (as abas
        originais do simulador são MOVIDAS para a barra, com os mesmos
        IDs e onclick — nada de lógica muda);
     2) aba "📘 Guia de Grupos" (guia + menores lances com vaga);
     3) modo "Apresentar ao cliente" (lê o resultado já mostrado na tela).
   NÃO altera nenhuma conta, ID, name ou handler do simulador.
   Contexto em window.CBX_CTX = {sim, adm, logo, contato, grupos{}, meta{}, fotos{}}.
   ===================================================================== */
(function () {
  var C = window.CBX_CTX || {};
  var d = document;
  d.documentElement.setAttribute("data-cbx", C.sim || "");
  try { if (window.top === window) d.documentElement.classList.add("cbx-solo"); } catch (e) { /* iframe de outra origem */ }

  // ---- utilidades -------------------------------------------------------
  function q(s, r) { return (r || d).querySelector(s); }
  function qa(s, r) { return [].slice.call((r || d).querySelectorAll(s)); }
  function vis(el) { return !!(el && el.offsetParent !== null && (el.innerText || "").trim()); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function pct(v) { return v == null || isNaN(v) ? "—" : (Math.round(v * 100) / 100).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 }) + "%"; }
  function kR(v) { if (v == null) return "—"; return v >= 1000 ? "R$ " + (v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " mil" : "R$ " + Math.round(v).toLocaleString("pt-BR"); }
  function faixa(l) { return l.cmin == null ? "—" : (l.cmin === l.cmax ? kR(l.cmin) : kR(l.cmin) + " – " + kR(l.cmax)); }
  function norm(s) { return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function dt(s) {
    s = String(s || "");
    var m = /^(\d{1,2})\/(\d{1,2})\/(\d{2,4})/.exec(s);
    if (m) { var y = +m[3]; if (y < 100) y += 2000; return new Date(y, m[2] - 1, +m[1]); }
    m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    return m ? new Date(+m[1], m[2] - 1, +m[3]) : null;
  }
  function hoje0() { var h = new Date(); h.setHours(0, 0, 0, 0); return h; }
  var SVG_TELA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>';

  var M = C.meta || {};
  var L = []; Object.keys(C.grupos || {}).forEach(function (k) { L.push(C.grupos[k]); });
  function comVaga(l) { return (+l.vagas || 0) > 0; }
  function prazoOk(l) { return !l.prazo || +l.prazo >= 12; }

  // ---- configuração por simulador ----------------------------------------
  var CFG = {
    yamaha: {
      orig: ".container", tabs: ["#tb-sim", "#tb-estr", "#tb-base"], acts: [".hero-actions > *"],
      tag: "Simulador Yamaha", tagS: "crédito · lance · contemplação", eye: "Consórcio Yamaha",
      h1: "Simule, compare e <em>apresente</em> o plano certo.",
      p: "Grupos, vagas e lances de referência coletados pelo robô Newcon. Monte a proposta e apresente ao cliente em tela cheia."
    },
    itau_ia: {
      orig: ".wrap", tabs: [], acts: ["#guiaVer"], simLbl: "✨ Simulador IA",
      tag: "Itaú · Lance por IA", tagS: "Guia de Oportunidades", eye: "Consórcio Itaú · IA",
      h1: "A IA monta a proposta, você <em>apresenta</em>.",
      p: "Responda quatro perguntas e a IA cruza a Guia de Oportunidades para sugerir os grupos com vaga mais aderentes ao cliente."
    },
    itau_manual: {
      orig: "#containerPrincipal", tabs: ["#tabBtnSimples", "#tabBtnEstruturado"], acts: [".btn-assembleia"],
      tag: "Itaú · Manual", tagS: "digitação livre", eye: "Consórcio Itaú · Manual",
      h1: "Sua simulação, do <em>seu jeito</em>.",
      p: "Digite os dados do grupo e do lance, gere a proposta e consulte a Guia de Grupos para escolher pelo histórico de lances."
    }
  };
  var K = CFG[C.sim] || CFG.itau_manual;

  // ---- "Simular este →" (só onde é simples e seguro) ------------------------
  function prodYamaha(tipo) {
    var t = norm(tipo);
    if (t.indexOf("imov") >= 0) return "imovel";
    if (t.indexOf("moto") >= 0) return "moto";
    if (t.indexOf("caminh") >= 0 || t.indexOf("pesad") >= 0) return "caminhao";
    if (t.indexOf("auto") >= 0 || t.indexOf("carro") >= 0) return "auto";
    return "";
  }
  function flash(el) { if (!el) return; el.classList.remove("cbx-flash"); void el.offsetWidth; el.classList.add("cbx-flash"); }
  var SIMULAR = {
    // Itaú manual: só escreve o nº do grupo no campo "Grupo" (que não dispara cálculo)
    itau_manual: function (l) {
      guia(false);
      var b = q("#tabBtnSimples"); if (b) b.click();
      var g = q("#grupo"); if (!g) return;
      g.value = l.g;
      flash(g); g.scrollIntoView({ behavior: "smooth", block: "center" });
      var c = q("#credito"); if (c) setTimeout(function () { c.focus({ preventScroll: true }); }, 350);
    },
    // Yamaha: faz o que o usuário faria — escolhe o produto e digita o grupo na busca do próprio simulador
    yamaha: function (l) {
      var p = prodYamaha(l.tipo); if (!p) return;
      guia(false);
      var t = q("#tb-sim"); if (t) t.click();
      var bp = q('#abaSim .btnProduto[data-prod="' + p + '"]');
      if (bp && !bp.classList.contains("active")) bp.click();
      var inp = q("#grupoBusca"); if (!inp) return;
      inp.value = l.g;
      inp.dispatchEvent(new Event("input", { bubbles: true }));
      flash(inp); inp.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(function () { inp.focus({ preventScroll: true }); }, 350);
    }
  };
  function podeSimular(l) {
    if (C.sim === "itau_manual") return !!q("#grupo");
    if (C.sim === "yamaha") return !!(prodYamaha(l.tipo) && q("#grupoBusca"));
    return false;
  }

  // ---- HERO + ABAS ---------------------------------------------------------
  var hero, ribbon, guiaBox, tabBar, btnGuia, btnSim, origEl;
  function botao() { var b = d.createElement("button"); b.type = "button"; b.className = "cbx-btn no-apres"; b.textContent = "🖥️ Apresentar ao cliente"; b.onclick = abrir; return b; }

  function montarHero() {
    origEl = q(K.orig) || d.body.firstElementChild;
    if (origEl) origEl.classList.add("cbx-orig");

    hero = d.createElement("header");
    hero.className = "cbx-hero no-apres";
    var logo = C.logo ? '<img src="' + C.logo + '" alt="Consorbens">' : "<b>CONSORBENS</b>";
    var admLogo = C.logo_adm ? '<span class="cbx-x" aria-hidden="true">×</span><div class="cbx-adm-logo ' + (C.sim === "yamaha" ? "yamaha" : "itau") + '"><img src="' + C.logo_adm + '" alt="' + esc(C.adm || "") + '"></div>' : "";
    hero.innerHTML = '<div class="cbx-blob b1"></div><div class="cbx-blob b2"></div><div class="cbx-dots"></div>'
      + '<div class="cbx-hero-in"><div class="cbx-top"><div class="cbx-brand"><div class="cbx-logo-box">' + logo + "</div>" + admLogo + '<div class="cbx-div"></div>'
      + '<div class="cbx-tag">' + esc(K.tag) + "<small>" + esc(K.tagS) + '</small></div></div><div class="cbx-acts" id="cbxActs"></div></div>'
      + '<div class="cbx-intro"><div><span class="cbx-eye">' + esc(K.eye) + "</span><h1>" + K.h1 + "</h1><p>" + esc(K.p) + "</p></div>"
      + '<div class="cbx-kpis">'
      + '<button type="button" class="cbx-hk" data-k="vaga"><small>Grupos com vaga</small><b id="cbxK1">—</b><em id="cbxK1s">—</em></button>'
      + '<button type="button" class="cbx-hk o" data-k="media" id="cbxKrot"><span class="dots" id="cbxDots"></span><small>Menor média de lance</small><b class="rv" id="cbxK2">—</b><em id="cbxK2s">—</em></button>'
      + '<button type="button" class="cbx-hk" data-k="assemb"><small>Próxima assembleia</small><b id="cbxK3">—</b><em id="cbxK3s">—</em></button>'
      + '</div></div><nav class="cbx-tabs" id="cbxTabs" aria-label="Abas do simulador"></nav></div>';
    d.body.insertBefore(hero, d.body.firstChild);

    var acts = q("#cbxActs");
    K.acts.forEach(function (s) { qa(s).forEach(function (el) { acts.appendChild(el); }); });

    tabBar = q("#cbxTabs");
    if (K.tabs.length) {
      K.tabs.forEach(function (s) {
        var b = q(s); if (!b) return;
        tabBar.appendChild(b);                                     // mesmo elemento: id e onclick preservados
        b.addEventListener("click", function () { guia(false); }, true);
      });
    } else {
      btnSim = d.createElement("button"); btnSim.type = "button"; btnSim.className = "cbx-on"; btnSim.textContent = K.simLbl || "Simulador";
      btnSim.addEventListener("click", function () { guia(false); });
      tabBar.appendChild(btnSim);
    }
    btnGuia = d.createElement("button"); btnGuia.type = "button"; btnGuia.className = "cbx-tg"; btnGuia.textContent = "📘 Guia de Grupos";
    btnGuia.addEventListener("click", function () { guia(true); });
    tabBar.appendChild(btnGuia);

    qa(".cbx-hk", hero).forEach(function (b) { b.addEventListener("click", function () { guia(true, b.getAttribute("data-k")); }); });

    ribbon = d.createElement("div"); ribbon.className = "cbx-ribbon cbx-orig no-apres";
    ribbon.innerHTML = '<div class="ic">' + SVG_TELA + "</div><b>Modo apresentação</b><span>Gere a simulação e mostre o resultado ao cliente em tela cheia.</span>"
      + "<input id='cbxCli' placeholder='Nome do cliente (opcional)'>";
    ribbon.appendChild(botao());
    hero.parentNode.insertBefore(ribbon, hero.nextSibling);

    guiaBox = d.createElement("section"); guiaBox.id = "cbxGuia"; guiaBox.className = "no-apres";
    ribbon.parentNode.insertBefore(guiaBox, ribbon.nextSibling);

    kpisHero();
  }

  var guiaFeita = false, TAB_ATIVA = [];
  function guia(on, foco) {
    var ja = d.body.classList.contains("cbx-guia-on");
    if (on) {
      if (!guiaFeita) { montarGuia(); guiaFeita = true; }
      if (!ja) {
        TAB_ATIVA = qa("#cbxTabs > .active");
        TAB_ATIVA.forEach(function (b) { b.classList.remove("active"); });
      }
      d.body.classList.add("cbx-guia-on");
      btnGuia.classList.add("cbx-on"); if (btnSim) btnSim.classList.remove("cbx-on");
      if (foco) {
        G.ord = { assemb: "assemb", vaga: "vagas", media: "media" }[foco] || G.ord; G.dir = 1;
        var s = q("#ggOrd"); if (s) s.value = G.ord; tabela();
      }
      try { window.scrollTo({ top: 0, behavior: "smooth" }); } catch (e) { window.scrollTo(0, 0); }
    } else if (ja) {
      d.body.classList.remove("cbx-guia-on");
      btnGuia.classList.remove("cbx-on"); if (btnSim) btnSim.classList.add("cbx-on");
      TAB_ATIVA.forEach(function (b) { b.classList.add("active"); }); TAB_ATIVA = [];
    }
  }
  window.cbxAbrirGuia = function (k) { guia(true, k); };

  // ---- KPIs do hero ----------------------------------------------------------
  var ROT = [], RI = 0, ROT_T = null;
  function proxAssemb(F) {
    var h = hoje0(), p = null;
    F.forEach(function (l) { var x = dt(l.assemb); if (x && x >= h && (!p || x < p.d)) p = { d: x, g: l.g }; });
    return p;
  }
  function kpisHero() {
    var V = L.filter(comVaga);
    q("#cbxK1").textContent = M.erro ? "—" : V.length;
    q("#cbxK1s").textContent = M.erro ? "base indisponível agora" : "de " + L.length + " grupos na base";
    ROT = V.filter(function (l) { return l.media != null && prazoOk(l); }).sort(function (a, b) { return a.media - b.media; }).slice(0, 3);
    q("#cbxDots").innerHTML = ROT.length > 1 ? ROT.map(function () { return "<i></i>"; }).join("") : "";
    RI = 0; rot(false);
    if (ROT_T) clearInterval(ROT_T);
    var reduz = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (ROT.length > 1 && !reduz) ROT_T = setInterval(function () { RI = (RI + 1) % ROT.length; rot(true); }, 4200);
    var p = proxAssemb(L);
    if (p) {
      var dias = Math.round((p.d - hoje0()) / 864e5);
      q("#cbxK3").textContent = p.d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
      q("#cbxK3s").textContent = (dias === 0 ? "hoje" : dias === 1 ? "amanhã" : "em " + dias + " dias") + " · grupo " + p.g;
    } else { q("#cbxK3").textContent = "—"; q("#cbxK3s").textContent = "sem data na base"; }
  }
  function rot(anim) {
    var b = q("#cbxK2"), s = q("#cbxK2s"), box = q("#cbxKrot");
    if (!ROT.length) { b.textContent = "—"; s.textContent = M.erro ? "base indisponível agora" : "sem histórico de lance"; return; }
    var l = ROT[RI];
    b.textContent = pct(l.media);
    s.textContent = (RI + 1) + "º · grupo " + l.g + (l.tipo ? " · " + l.tipo : "");
    qa("#cbxDots i").forEach(function (x, i) { x.classList.toggle("on", i === RI); });
    if (anim) { box.classList.remove("troca"); void box.offsetWidth; box.classList.add("troca"); }
  }

  // ---- GUIA DE GRUPOS ---------------------------------------------------------
  var G = { tipo: "", q: "", soVaga: true, semFim: true, ord: "media", dir: 1 };
  var COLS = [["g", "Grupo"], ["tipo", "Tipo"], ["vagas", "Vagas"], ["prazo", "Prazo"], ["cmax", "Crédito"], ["media", "Média lance"],
              ["menor", "Menor"], ["maior", "Maior"], ["cont", "Contempl."], ["assemb", "Assembleia"], ["obs", "Obs."]];
  function montarGuia() {
    var tipos = []; L.forEach(function (l) { if (l.tipo && tipos.indexOf(l.tipo) < 0) tipos.push(l.tipo); });
    var src = M.erro ? '<span class="gg-chip"><span class="gg-dot off"></span>Base indisponível agora</span>'
      : '<span class="gg-chip"><span class="gg-dot"></span>Fonte: <b>' + esc(M.fonte || "—") + "</b></span>"
        + (M.atualizado ? '<span class="gg-chip">Atualizado em <b>' + esc(M.atualizado) + "</b></span>" : "");
    var simCol = C.sim !== "itau_ia";
    guiaBox.innerHTML = '<div class="gg-head"><div><span class="cbx-eye">Guia de grupos · ' + esc(C.adm || "") + "</span>"
      + "<h2>Grupos com vaga e lances de referência</h2><p>Histórico das últimas assembleias para escolher o grupo com mais critério. Lance é uma oferta: o resultado depende das ofertas de cada mês.</p></div>"
      + '<div class="gg-status">' + src + "</div></div>"
      + (M.erro ? '<div class="gg-erro">⚠️ Não consegui carregar os grupos desta administradora agora. O simulador continua funcionando normalmente na outra aba.<br><small>' + esc(M.erro) + "</small></div>" : "")
      + '<div class="gg-kpis" id="ggK"></div>'
      + '<div class="gg-sec"><h3>🏆 Menores lances com vaga <i id="ggTopN">top 8</i></h3><div class="gg-tools">'
      + '<label title="Grupos que acabam em menos de 12 meses têm lance baixo, mas parcela muito alta"><input type="checkbox" id="ggFim" checked> ocultar fim de prazo (&lt; 12 meses)</label>'
      + (tipos.length > 1 ? '<div class="gg-chips" id="ggChips"><button type="button" class="on" data-v="">Todos</button>' + tipos.map(function (t) { return '<button type="button" data-v="' + esc(t) + '">' + esc(t) + "</button>"; }).join("") + "</div>" : "")
      + '</div></div><div id="ggTop"></div>'
      + '<div class="gg-sec"><h3>📘 Todos os grupos</h3><div class="gg-tools">'
      + '<input type="search" id="ggQ" placeholder="Buscar grupo ou tipo…">'
      + '<select id="ggOrd"><option value="media">Menor média de lance</option><option value="vagas">Mais vagas</option><option value="prazoA">Prazo menor</option><option value="prazoD">Prazo maior</option><option value="assemb">Assembleia mais próxima</option><option value="g">Número do grupo</option></select>'
      + '<label><input type="checkbox" id="ggVaga" checked> só com vaga</label></div></div>'
      + '<div class="gg-tbl"><table><thead><tr>' + COLS.map(function (c) { return '<th data-c="' + c[0] + '">' + c[1] + "</th>"; }).join("")
      + (simCol ? "<th></th>" : "") + '</tr></thead><tbody id="ggTb"></tbody></table></div>'
      + '<p class="gg-note">Valores de referência a partir dos dados da administradora. Contemplação depende de sorteio ou lance em assembleia.</p>';

    q("#ggFim").addEventListener("change", function () { G.semFim = this.checked; tudoGuia(); });
    q("#ggVaga").addEventListener("change", function () { G.soVaga = this.checked; tabela(); });
    q("#ggQ").addEventListener("input", function () { G.q = this.value.trim(); tabela(); });
    q("#ggOrd").addEventListener("change", function () { G.ord = this.value; G.dir = 1; tabela(); });
    qa("#ggChips button").forEach(function (b) {
      b.addEventListener("click", function () { G.tipo = b.getAttribute("data-v"); qa("#ggChips button").forEach(function (x) { x.classList.toggle("on", x === b); }); tudoGuia(); });
    });
    qa(".gg-tbl th[data-c]").forEach(function (th) {
      th.addEventListener("click", function () {
        var c = th.getAttribute("data-c"), o = c === "prazo" ? "prazoA" : c;
        if (G.ord === o) G.dir = -G.dir; else { G.ord = o; G.dir = 1; }
        var s = q("#ggOrd"); if ([].some.call(s.options, function (op) { return op.value === o; })) s.value = o;
        tabela();
      });
    });
    guiaBox.addEventListener("click", function (e) {
      var b = e.target.closest("[data-sim]"); if (!b) return;
      var l = C.grupos[b.getAttribute("data-sim")]; if (l && SIMULAR[C.sim]) SIMULAR[C.sim](l);
    });
    tudoGuia();
  }
  function filtT() { return L.filter(function (l) { return (!G.tipo || l.tipo === G.tipo) && (!G.semFim || prazoOk(l)); }); }
  function tudoGuia() { kpisGuia(); top(); tabela(); }
  function kpisGuia() {
    var F = filtT(), V = F.filter(comVaga), mel = V.filter(function (l) { return l.media != null; }).sort(function (a, b) { return a.media - b.media; })[0];
    var p = proxAssemb(F), c = 0; F.forEach(function (l) { c += +l.cont || 0; });
    var it = [["Grupos com vaga", V.length, "de " + F.length + " no filtro", ""],
              ["Menor média de lance", mel ? pct(mel.media) : "—", mel ? "grupo " + mel.g + (mel.tipo ? " · " + mel.tipo : "") : "sem histórico", "o"],
              ["Próxima assembleia", p ? p.d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : "—", p ? "grupo " + p.g : "sem data na base", ""],
              ["Contemplados no lance livre", c.toLocaleString("pt-BR"), "soma do período da base", ""]];
    q("#ggK").innerHTML = it.map(function (x) { return '<div class="gg-k ' + x[3] + '"><small>' + x[0] + "</small><b>" + x[1] + "</b><em>" + esc(x[2]) + "</em></div>"; }).join("");
  }
  function top() {
    var el = q("#ggTop"); if (M.erro) { el.innerHTML = ""; return; }
    var V = filtT().filter(function (l) { return comVaga(l) && l.media != null; }).sort(function (a, b) { return a.media - b.media; }).slice(0, 8);
    q("#ggTopN").textContent = "top " + V.length;
    if (!V.length) { el.innerHTML = '<div class="gg-vazio">Nenhum grupo com vaga e histórico de lance' + (G.tipo ? " em " + esc(G.tipo) : "") + " na base agora.</div>"; return; }
    el.innerHTML = '<div class="gg-top">' + V.map(function (l, i) {
      return '<div class="gg-c' + (i === 0 ? " first" : "") + '" style="animation-delay:' + (i * 50) + 'ms"><span class="rk">#' + (i + 1) + '</span><div class="gn">Grupo ' + esc(l.g) + '</div><div class="tp">' + esc(l.tipo || "—") + "</div>"
        + '<div class="md"><b>' + pct(l.media) + '</b><span>média de lance</span></div><div class="gg-meter"><i style="width:' + Math.max(2, Math.min(100, l.media)) + '%"></i></div>'
        + '<div class="ln"><i>Menor que ganhou</i><span>' + pct(l.menor) + "</span></div>"
        + '<div class="ln"><i>Vagas</i><span>' + (l.vagas == null ? "—" : l.vagas) + "</span></div>"
        + '<div class="ln"><i>Prazo</i><span>' + (l.prazo ? l.prazo + " meses" : "—") + "</span></div>"
        + '<div class="ln"><i>Crédito</i><span>' + faixa(l) + "</span></div>"
        + (podeSimular(l) ? '<button type="button" class="gg-sim" data-sim="' + esc(l.g) + '">Simular este →</button>' : "")
        + "</div>";
    }).join("") + "</div>";
  }
  function tabela() {
    var tb = q("#ggTb"); if (!tb) return;
    var qq = norm(G.q);
    var R = filtT().filter(function (l) { return (!G.soVaga || comVaga(l)) && (!qq || norm(l.g).indexOf(qq) >= 0 || norm(l.tipo).indexOf(qq) >= 0); });
    var big = 1e12, D = G.dir;
    function nz(v) { return v == null || v === "" ? big : +v; }
    var f = {
      media: function (a, b) { return D * (nz(a.media) - nz(b.media)); },
      vagas: function (a, b) { return D * ((+b.vagas || 0) - (+a.vagas || 0)); },
      prazoA: function (a, b) { return D * ((+a.prazo || big) - (+b.prazo || big)); },
      prazoD: function (a, b) { return D * ((+b.prazo || 0) - (+a.prazo || 0)); },
      assemb: function (a, b) { return D * ((dt(a.assemb) || big) - (dt(b.assemb) || big)); },
      g: function (a, b) { return D * String(a.g).localeCompare(String(b.g), undefined, { numeric: true }); },
      menor: function (a, b) { return D * (nz(a.menor) - nz(b.menor)); },
      maior: function (a, b) { return D * (nz(a.maior) - nz(b.maior)); },
      cont: function (a, b) { return D * ((+b.cont || 0) - (+a.cont || 0)); },
      cmax: function (a, b) { return D * ((+b.cmax || 0) - (+a.cmax || 0)); },
      tipo: function (a, b) { return D * String(a.tipo || "").localeCompare(String(b.tipo || "")); },
      obs: function (a, b) { return D * String(a.obs || "").localeCompare(String(b.obs || "")); }
    };
    R.sort(f[G.ord] || f.media);
    var colOrd = { prazoA: "prazo", prazoD: "prazo" }[G.ord] || G.ord;
    qa(".gg-tbl th[data-c]").forEach(function (th) { th.classList.toggle("ord", th.getAttribute("data-c") === colOrd); });
    var simCol = C.sim !== "itau_ia";
    tb.innerHTML = R.length ? R.map(function (l) {
      return "<tr><td><b>" + esc(l.g) + "</b></td><td>" + esc(l.tipo || "—") + '</td><td><span class="gg-pill ' + (comVaga(l) ? "gg-p1" : "gg-p0") + '">' + (l.vagas == null ? "—" : l.vagas) + "</span></td><td>" + (l.prazo || "—") + "</td><td>" + faixa(l)
        + "</td><td><b>" + pct(l.media) + "</b></td><td>" + pct(l.menor) + "</td><td>" + pct(l.maior) + "</td><td>" + (l.cont == null ? "—" : l.cont) + "</td><td>" + esc(l.assemb || "—") + "</td><td>" + esc(l.obs || "") + "</td>"
        + (simCol ? "<td>" + (podeSimular(l) ? '<button type="button" class="gg-sim" data-sim="' + esc(l.g) + '">Simular →</button>' : "") + "</td>" : "") + "</tr>";
    }).join("") : '<tr><td colspan="12" style="text-align:center;color:#94a3b8;padding:22px">' + (M.erro ? "Base indisponível agora." : "Nenhum grupo com esse filtro.") + "</td></tr>";
  }

  // ---- rótulos visíveis no Itaú manual (o original só tem placeholder) ---------
  function rotulosItauManual() {
    var card = q("#tab-simples .card"); if (!card) return;
    var nomes = { cotas: "Quantidade de cotas", temSeguro: "Seguro prestamista", parcelaAntes: "" };
    qa("input,select", card).forEach(function (el) {
      if (nomes[el.id] === "") return;
      var txt = nomes[el.id] || el.getAttribute("placeholder") || ""; if (!txt) return;
      var lb = d.createElement("span"); lb.className = "cbx-lbl"; lb.textContent = txt;
      if (el.parentNode === card) {          // embrulha (o mesmo elemento, só muda o pai visual)
        var w = d.createElement("div"); w.className = "cbx-f";
        card.insertBefore(w, el); w.appendChild(lb); w.appendChild(el);
      } else {
        el.parentNode.classList.add("cbx-f"); el.parentNode.insertBefore(lb, el);
      }
    });
  }

  // ---- MODO APRESENTAÇÃO -------------------------------------------------------
  function blocos() {
    var b = [];
    if (C.sim === "yamaha") {
      if (vis(q("#abaEstr"))) b = [q("#resultadoEstr"), q("#fluxoEstr")];
      else b = [q("#resumo .proposta") || q("#resultado")];
    } else if (C.sim === "itau_ia") {
      if (vis(q("#manual"))) b = [q("#mLista"), q("#mTotais")];
      else b = qa("#cards > .rc").slice(0, 4);
    } else {
      b = [q("#resultado"), q("#resumoEstruturadoBox")];
    }
    return b.filter(vis);
  }
  function grupoAtual(textos) {
    var cands = [];
    ["#grupo", "#mGrupo", "#mGrupoManual"].forEach(function (s) { var e = q(s); if (e && vis(e.closest("div") || e) && e.value) cands.push(e.value); });
    var m = /grupo\s*:?\s*0*(\d{3,6})/i.exec(textos || "");
    if (m) cands.unshift(m[1]);
    for (var i = 0; i < cands.length; i++) {
      var g = String(cands[i]).replace(/\D/g, "").replace(/^0+/, "");
      if (g && C.grupos && C.grupos[g]) return C.grupos[g];
    }
    return null;
  }
  function produtoAtual(txt) {
    var p = "";
    try { if (typeof produto !== "undefined") p = String(produto); } catch (e) { p = ""; }   // variável global dos simuladores
    if (!p && C.sim === "itau_ia") {
      var s = q("#fTipo button.sel") || q("#mTipo button.sel");
      p = s ? (s.getAttribute("data-v") === "Imóvel" ? "imovel" : "auto") : "";
    }
    if (!p) { var t = norm(txt); p = t.indexOf("imov") >= 0 ? "imovel" : t.indexOf("caminh") >= 0 ? "caminhao" : t.indexOf("moto") >= 0 ? "moto" : "auto"; }
    return p;
  }
  function clonar(el) {
    var c = el.cloneNode(true);
    var orig = el.querySelectorAll("canvas"), cl = c.querySelectorAll("canvas");
    [].forEach.call(cl, function (cv, i) { try { var im = d.createElement("img"); im.src = orig[i].toDataURL(); im.style.maxWidth = "100%"; cv.replaceWith(im); } catch (e) { cv.remove(); } });
    var oi = el.querySelectorAll("input,select,textarea"), ci = c.querySelectorAll("input,select,textarea");
    [].forEach.call(ci, function (inp, i) {
      var o = oi[i], v = o.tagName === "SELECT" ? (o.selectedOptions[0] || {}).text : o.value;
      if (o.type === "checkbox" || o.type === "radio" || o.type === "range" || o.type === "hidden") { inp.remove(); return; }
      var s = d.createElement("b"); s.textContent = v || ""; inp.replaceWith(s);
    });
    c.querySelectorAll("button,.actions,.resumo-acoes,.no-apres,details,script").forEach(function (e) { e.remove(); });
    c.removeAttribute("id"); c.querySelectorAll("[id]").forEach(function (e) { e.removeAttribute("id"); });
    c.style.display = ""; c.style.margin = "0";
    return c.outerHTML;
  }
  function estilos() {
    return qa("style").filter(function (s) { return !s.hasAttribute("data-cbx-skin"); })
      .map(function (s) { return s.textContent; }).join("\n").replace(/(^|[\s,}])body\s*\{[^}]*\}/g, "$1");
  }

  // ===================================================================
  // DECK — apresentação ao cliente (janela própria, canvas 1280×720 escalado)
  // Slides com passos revelados ([data-step], seta/espaço), números contando
  // ([data-count]), wipe laranja nas trocas de seção e transição entre slides.
  // Conteúdo: só o que está na tela do simulador + dados do grupo (CBX_CTX)
  // + diferenciais verificados (diferenciais.json). Nada é inventado aqui.
  // ===================================================================
  var NOME_PROD = { imovel: "imóvel", auto: "automóvel", moto: "moto", caminhao: "caminhão" };
  var ICO_PROD = { imovel: "🏠", auto: "🚗", moto: "🏍️", caminhao: "🚚" };
  var SIN_PROD = { imovel: ["imovel", "imoveis", "casa"], auto: ["auto", "automovel", "automoveis", "carro", "veiculo", "veiculos", "leve", "leves"],
                   moto: ["moto", "motos", "motocicleta"], caminhao: ["caminhao", "caminhoes", "pesado", "pesados", "veiculo pesado"] };
  function dA(dl, cls) { return ' class="dk-a' + (cls ? " " + cls : "") + '" style="--d:' + dl + 's"'; }
  function logoCB(cls) { return C.logo ? '<img class="dk-lcb ' + (cls || "") + '" src="' + C.logo + '" alt="Consorbens">' : '<b class="dk-lcb-t">CONSORBENS</b>'; }
  function logoAdm(cls) { return C.logo_adm ? '<img class="dk-ladm ' + (C.sim === "yamaha" ? "y" : "i") + " " + (cls || "") + '" src="' + C.logo_adm + '" alt="' + esc(C.adm || "") + '">' : ""; }
  function fixoTxt(g) {   // lance fixo real do grupo: número (Itaú) ou lista (Yamaha, ex. [35, 10])
    var f = g && g.fixo; if (f == null || f === "" || (f.length === 0)) return "";
    return [].concat(f).map(function (x) { return String(x).replace(".", ",") + "%"; }).join(" e ");
  }
  function rodape(alt) { return esc((C.dif || {}).rodape || "") || alt; }
  function primeiro(n) { return n ? esc(String(n).trim().split(/\s+/)[0]) : ""; }

  // números da proposta, lidos do texto que o simulador mostrou (sem recalcular nada)
  function brl(txt, re) {
    var m = re.exec(txt); if (!m) return "";
    var r = /R\$\s?[\d.]+,\d{2}/.exec(txt.slice(m.index, m.index + 180));
    return r ? r[0].replace(/R\$\s?/, "R$ ") : "";
  }
  function extrair(txt) {
    var o = {
      credito: brl(txt, /cr[ée]dito\s+(contratado|total)/i),
      liquido: brl(txt, /cr[ée]dito\s+(l[ií]quido|liberado)/i),
      parcela: brl(txt, /parcela\s+(inicial|antes)/i),
      parcelaPos: brl(txt, /(parcela\s+(p[óo]s|depois|ap[óo]s)|novo valor com seguro)/i)
    };
    var m = /prazo\s+contratado[^\d]{0,30}(\d{1,3})/i.exec(txt); o.prazo = m ? +m[1] : null;
    m = /lance\s+(total\s+ofertado|total\s+em|livre)\s*:?\s*([\d]+(?:[.,]\d+)?)\s?%/i.exec(txt);
    o.lance = m ? parseFloat(m[2].replace(",", ".")) : null;
    return o;
  }
  var TODOS = ["moto", "auto", "imovel", "caminhao"];
  function difAdm(prod) {
    return ((C.dif || {}).adm || []).filter(function (x) {
      var ps = (x.produtos || []).map(norm);
      var vale = !ps.length || ps.indexOf("todos") >= 0 || (prod ? (SIN_PROD[prod] || [prod]).some(function (p) { return ps.indexOf(p) >= 0; })
                                                             : TODOS.every(function (p) { return ps.indexOf(p) >= 0; }));
      if (!vale) return false;
      var t = norm(x.id + " " + x.titulo + " " + x.texto);
      if (C.sim !== "yamaha" && /lance parcelado|parcelar o lance|pagar o lance em|lance.{0,20}\d+x/.test(t)) return false;   // Itaú: nunca lance parcelado
      if (prod === "moto" && (x.id === "lance_4x" || /\b4x\b/.test(t))) return false;   // Yamaha: lance em 4x nunca para moto
      return true;
    });
  }

  // ---- slides ----------------------------------------------------------------
  function sCapa(X) {
    var hoje = new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
    var foto = (C.fotos || {})[X.prod] || (C.fotos || {}).auto || "";
    var L2 = [(X.cli ? primeiro(X.cli) + ", seu " : "Seu ") + esc(NOME_PROD[X.prod] || "bem"), "com <em>planejamento</em>", "e sem juros."];
    var chips = [];
    if (X.g && X.num.credito) chips.push(ICO_PROD[X.prod] + " Grupo " + esc(X.g.g) + " · " + esc(X.num.credito));
    else if (X.num.credito) chips.push(ICO_PROD[X.prod] + " Crédito de " + esc(X.num.credito));
    var p = X.g ? dt(X.g.assemb) : null;
    if (p && p >= hoje0()) chips.push("📅 Próxima assembleia " + p.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }));
    chips.push("🎯 Sorteio e lance todo mês");
    return '<div class="dk-s dk-capa" data-capa="1"><div class="dk-capa-t">'
      + '<div' + dA(.05, "dk-logos") + ">" + logoCB() + (C.logo_adm ? "<i>×</i>" + logoAdm() : "") + "</div>"
      + '<span' + dA(.25, "dk-eye") + ">" + (X.cli ? "Proposta exclusiva para " + esc(X.cli) : "Proposta de consórcio · " + esc(C.adm || "")) + "</span>"
      + '<h1 class="dk-h">' + L2.map(function (l, i) { return '<span class="ln"><span style="--d:' + (.4 + i * .13).toFixed(2) + 's">' + l + "</span></span>"; }).join("") + "</h1>"
      + '<p' + dA(1, "dk-por") + ">Apresentado pela <b>Consorbens</b> · " + hoje + "</p>"
      + '<div class="dk-chips">' + chips.map(function (c, i) { return '<span' + dA((1.1 + i * .09).toFixed(2)) + ">" + c + "</span>"; }).join("") + "</div></div>"
      + '<div class="dk-capa-ph"><div class="dk-ph" style="background-image:url(' + foto + ')"></div>'
      + (C.logo_adm ? '<div class="dk-capa-adm">' + logoAdm() + "</div>" : "") + "</div></div>";
  }
  function sComo() {
    var P = [["🧭", "Você escolhe", "o crédito e o prazo que cabem no seu orçamento."],
             ["📅", "Paga sem juros", "o custo é a taxa de administração, diluída no prazo."],
             ["🎯", "Concorre todo mês", "nas assembleias, por sorteio e por lance."],
             ["🔑", "Contemplado, compra", "após a análise de crédito da administradora, o valor é liberado para a compra."]];
    return '<div class="dk-s dk-como"><span' + dA(.05, "dk-eye") + ">Como funciona</span>"
      + "<h2" + dA(.15) + ">Do plano à <em>chave na mão</em>, em 4 passos</h2>"
      + '<div class="dk-w-line"><i></i></div><div class="dk-w">'
      + P.map(function (p, i) { var dl = .45 + i * .5; return '<div class="dk-w-s"><span class="dk-w-n" style="--d:' + dl.toFixed(2) + 's">' + (i + 1) + "</span>"
        + '<div class="dk-a dk-w-c" style="--d:' + (dl + .15).toFixed(2) + 's"><span class="dk-w-i">' + p[0] + "</span><b>" + p[1] + "</b><p>" + p[2] + "</p></div></div>"; }).join("")
      + "</div><p" + dA(2.4, "dk-rod") + ">A contemplação acontece por sorteio ou lance em assembleia e não tem data garantida.</p></div>";
  }
  function sChances(X) {
    var g = X.g, N = [["SORTEIO", "todo mês", "o"]];
    if (fixoTxt(g)) N.push([[].concat(g.fixo).length > 1 ? [].concat(g.fixo).join("·") + "%" : fixoTxt(g), "lance fixo", "w"]);
    N.push(["LANCE", "LIVRE", "b"]);
    var pos = N.length === 3 ? [[110, 80], [510, 80], [310, 320]] : [[100, 200], [520, 200]];
    var svg = '<svg class="dk-x" viewBox="0 0 620 400">';
    pos.forEach(function (p, i) { svg += '<path class="dk-x-l" pathLength="1" style="--d:' + (.45 + i * .2).toFixed(2) + 's" d="M310 200 L' + p[0] + " " + p[1] + '"/><path class="dk-x-f" d="M310 200 L' + p[0] + " " + p[1] + '"/>'; });
    svg += '<g class="dk-x-c"><rect x="226" y="152" width="168" height="96" rx="20"/><text x="310" y="196" class="t1">1 COTA</text><text x="310" y="222" class="t2">' + N.length + " CHANCES</text></g>";
    N.forEach(function (n, i) {
      var p = pos[i];
      svg += '<g class="dk-x-n ' + n[2] + '" style="--d:' + (.75 + i * .2).toFixed(2) + 's"><circle class="r" cx="' + p[0] + '" cy="' + p[1] + '" r="62"/><circle cx="' + p[0] + '" cy="' + p[1] + '" r="62"/>'
        + '<text x="' + p[0] + '" y="' + (p[1] - 2) + '" class="a">' + n[0] + '</text><text x="' + p[0] + '" y="' + (p[1] + 21) + '" class="b">' + n[1] + "</text></g>";
    });
    svg += "</svg>";
    var info = [];
    var pa = g ? dt(g.assemb) : null;
    if (pa && pa >= hoje0()) { var dd = Math.round((pa - hoje0()) / 864e5); info.push("📅 Próxima assembleia do grupo " + esc(g.g) + ": <b>" + pa.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + "</b> · " + (dd === 0 ? "hoje" : dd === 1 ? "amanhã" : "em " + dd + " dias")); }
    if (g && g.red) info.push("🔻 Grupo com opção de <b>parcela reduzida</b> até a contemplação");
    if (g && g.cont != null) info.push("🏆 <b>" + esc(g.cont) + "</b> contemplações por lance livre no período analisado");
    var frase = (g ? "No grupo " + esc(g.g) : "Nos grupos " + esc(C.adm || "")) + ", a mesma cota concorre no sorteio"
      + (fixoTxt(g) ? ", pode ofertar lance fixo de " + fixoTxt(g) : "") + " e pode ofertar lance livre em cada assembleia, conforme o regulamento.";
    return '<div class="dk-s dk-ch"><div class="dk-ch-t"><span' + dA(.05, "dk-eye") + ">Contemplação</span>"
      + "<h2" + dA(.15) + ">1 cota, <em>" + N.length + " chances</em> todo mês</h2><p" + dA(.3, "dk-lead") + ">" + frase + "</p>"
      + (info.length ? '<div class="dk-ch-i">' + info.map(function (t, i) { return "<span" + dA((1.4 + i * .12).toFixed(2)) + ">" + t + "</span>"; }).join("") + "</div>" : "")
      + "<p" + dA(1.9, "dk-rod") + ">A contemplação depende do resultado de cada assembleia.</p></div>"
      + '<div class="dk-ch-s">' + svg + "</div></div>";
  }
  // ícone pelo assunto do item (só enfeite visual: o texto é o do diferenciais.json)
  var ICONES = [[/fgts/, "🏦"], [/embutid/, "🧩"], [/4x|parcelad/, "🗓️"], [/antecip/, "⏩"], [/abate|diluir|reduzir o valor/, "⚖️"],
    [/adesao|fundo de reserva/, "🚫"], [/chances|modalidades|sorteio/, "🎲"], [/prime|fidelidade/, "👑"], [/parcela reduzida|30% menor/, "📉"],
    [/aumente|upgrade/, "⬆️"], [/usado|qualquer marca/, "🚗"], [/construir|reformar|imovel|casa|apartamento/, "🏠"], [/junte|juntar|juncao/, "🔗"],
    [/reajuste/, "📈"], [/seguro/, "🛡️"], [/analise/, "⚡"], [/quitar|financiamento/, "✅"], [/pesados|maquina|caminh/, "🚚"],
    [/mais de um bem|varios/, "📦"], [/lance fixo/, "📌"], [/consultiv|atendimento/, "🤝"], [/perfil|orcamento/, "🧭"], [/lance ofertado|oferta do seu lance/, "🎯"],
    [/equipe|experien/, "🏅"], [/representante|autorizad/, "✔️"], [/dados|assembleia/, "📊"]];
  function icone(v, i) {
    var t = norm(v.titulo + " " + v.texto);
    for (var k = 0; k < ICONES.length; k++) if (ICONES[k][0].test(norm(v.titulo)) ) return ICONES[k][1];
    for (k = 0; k < ICONES.length; k++) if (ICONES[k][0].test(t)) return ICONES[k][1];
    return ["⭐", "✅", "💡", "🛡️", "📈", "🤝"][i % 6];
  }
  function sCards(eye, h2, todos, rod, cls) {
    if (!todos.length) return "";
    var itens = todos.slice(0, 6), extra = todos.slice(6);
    return '<div class="dk-s dk-v ' + (cls || "") + '"><div class="dk-v-h"><div><span' + dA(.05, "dk-eye") + ">" + eye + "</span><h2" + dA(.15) + ">" + h2 + "</h2></div>"
      + (cls === "adm" && C.logo_adm ? '<div' + dA(.2, "dk-v-logo") + ">" + logoAdm() + "</div>" : cls === "cb" ? '<div' + dA(.2, "dk-v-logo cb") + ">" + logoCB() + "</div>" : "") + "</div>"
      + '<div class="dk-v-g n' + Math.min(itens.length, 6) + '">'
      + itens.map(function (v, i) { return '<div' + dA((.35 + i * .1).toFixed(2), "dk-v-c") + ">"
        + '<span class="dk-v-i">' + esc(v.icone || icone(v, i)) + "</span><b>" + esc(v.titulo) + "</b>" + (v.texto ? "<p>" + esc(v.texto) + "</p>" : "") + "</div>"; }).join("")
      + "</div>" + (extra.length ? '<div' + dA(1.1, "dk-v-x") + "><small>Também no seu plano</small>" + extra.map(function (v) { return "<span>" + esc(v.titulo) + "</span>"; }).join("") + "</div>" : "")
      + (rod ? "<p" + dA(1.2, "dk-rod") + ">" + rod + "</p>" : "") + "</div>";
  }
  function sCredito(X) {
    var n = X.num; if (!n.credito && !n.liquido) return "";
    var nv = function (t) { return parseFloat(String(t || "").replace(/[^\d,]/g, "").replace(",", ".")) || 0; };
    var somaCotas = n.credito && n.liquido && nv(n.liquido) > nv(n.credito);
    var big = somaCotas ? n.liquido : (n.credito || n.liquido);
    var meta = [];
    if (n.parcela) meta.push("Parcela inicial de <b>" + esc(n.parcela) + "</b>");
    if (n.prazo) meta.push("<b>" + n.prazo + "</b> meses");
    if (X.g) meta.push("Grupo <b>" + esc(X.g.g) + "</b>");
    var steps = "";
    if (n.liquido && n.credito && !somaCotas) steps += '<div class="dk-b-st" data-step><span>Crédito líquido na contemplação<small>valor para a compra, após a análise de crédito da administradora</small></span><b data-count data-dur="1.4">' + esc(n.liquido) + "</b></div>";
    if (n.parcela && n.parcelaPos) steps += '<div class="dk-b-pp" data-step><div><small>Até a contemplação</small><b>' + esc(n.parcela) + '<em>/mês</em></b></div><i>→</i><div class="o"><small>Depois de contemplado</small><b>' + esc(n.parcelaPos) + "<em>/mês</em></b></div></div>";
    return '<div class="dk-s dk-b" data-fx="wipe" data-prop="1"><span' + dA(.05, "dk-eye") + ">Agora, a sua proposta</span>"
      + "<h2" + dA(.15) + ">" + (X.cli ? primeiro(X.cli) + ", este é o seu crédito" : "Este é o seu crédito") + (somaCotas ? " liberado" : "") + "</h2>"
      + '<div' + dA(.3, "dk-b-v") + '><b data-count data-delay=".4" data-dur="1.8">' + esc(big) + '</b><i class="dk-b-u"></i></div>'
      + (meta.length ? "<div" + dA(1.9, "dk-b-meta") + ">" + meta.join('<i class="sep">·</i>') + "</div>" : "")
      + steps + (steps ? '<div class="dk-b-dica">▶ avance para revelar</div>' : "") + "<p" + dA(2.2, "dk-rod") + ">Valores aproximados da simulação. " + rodape("") + "</p></div>";
  }
  function sFolha(html, i, n, cards, X) {
    var eye = "<span" + dA(.05, "dk-eye") + ">Sua simulação" + (n > 1 ? " · " + (i + 1) + " de " + n : "") + "</span>";
    var rod = "<p" + dA(1.6, "dk-rod") + ">Valores aproximados da simulação. " + rodape("") + "</p>";
    if (X) {   // um card estreito: destaques à esquerda, o card real à direita
      var m = X.num, L2 = [];
      if (m.credito) L2.push(["Crédito contratado", m.credito]);
      if (m.parcela) L2.push(["Parcela até a contemplação", m.parcela]);
      if (m.parcelaPos) L2.push(["Parcela depois de contemplado", m.parcelaPos]);
      if (m.prazo) L2.push(["Prazo", m.prazo + " meses"]);
      if (m.liquido) L2.push(["Crédito líquido na contemplação", m.liquido, 1]);
      return '<div class="dk-s dk-f side"><div class="dk-f-l">' + eye + "<h2" + dA(.15) + ">O detalhe, <em>tim-tim por tim-tim</em></h2>"
        + '<div class="dk-f-k">' + L2.map(function (k, j) { return "<div" + dA((.4 + j * .12).toFixed(2), k[2] ? "o" : "") + "><small>" + k[0] + "</small><b data-count data-delay=\"" + (.5 + j * .12).toFixed(2) + "\">" + esc(k[1]) + "</b></div>"; }).join("") + "</div></div>"
        + '<div class="dk-f-r"><div class="dk-f-sheet">' + html + "</div></div>" + rod + "</div>";
    }
    return '<div class="dk-s dk-f"><div class="dk-f-h">' + eye
      + "<h2" + dA(.15) + ">" + (cards ? "As opções, <em>lado a lado</em>" : "O detalhe, <em>tim-tim por tim-tim</em>") + "</h2></div>"
      + '<div class="dk-f-sheet' + (cards ? " cards" : "") + '">' + html + "</div>" + rod + "</div>";
  }
  function sGrupo(X) {
    var g = X.g; if (!g) return "";
    var K = [["Média de lance", pct(g.media)], ["Menor lance contemplado", pct(g.menor)], ["Maior lance", pct(g.maior)],
             ["Contemplados no lance livre", g.cont == null ? "—" : String(g.cont)], ["Vagas", g.vagas == null ? "—" : String(g.vagas)], ["Prazo", g.prazo ? g.prazo + " meses" : "—"]];
    var bar = "";
    if (g.media != null) {
      var mk = function (v, cls, lb) { return v == null ? "" : '<u class="' + cls + '" style="left:' + Math.max(0, Math.min(100, v)) + '%"><em>' + lb + " " + pct(v) + "</em></u>"; };
      bar = '<div' + dA(1.1, "dk-g-bar") + '><div class="t"><span>Lances contemplados no grupo</span><b>média ' + pct(g.media) + "</b></div>"
        + '<div class="b"><i class="rng" style="left:' + Math.max(0, g.menor == null ? g.media : g.menor) + "%;right:" + (100 - Math.min(100, g.maior == null ? g.media : g.maior)) + '%"></i>'
        + mk(g.menor, "mn", "menor") + mk(g.media, "md", "média") + mk(g.maior, "mx", "maior") + (X.num.lance != null ? mk(X.num.lance, "voce", "seu lance") : "") + "</div>"
        + '<div class="esc"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div></div>';
    }
    var chips = [];
    var pa = dt(g.assemb); if (pa && pa >= hoje0()) chips.push("📅 Próxima assembleia <b>" + pa.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + "</b>");
    if (fixoTxt(g)) chips.push("📌 Lance fixo de <b>" + fixoTxt(g) + "</b>");
    if (g.emb) chips.push("🧩 Lance embutido de até <b>" + String(g.emb).replace(".", ",") + "%</b> do crédito");
    if (g.red) chips.push("🔻 <b>Parcela reduzida</b> até a contemplação");
    if (g.cmin != null) chips.push("💳 Créditos de <b>" + faixa(g) + "</b>");
    return '<div class="dk-s dk-g" data-fx="wipe"><div class="dk-g-h"><div><span' + dA(.05, "dk-eye") + ">Por que este grupo</span>"
      + "<h2" + dA(.15) + ">Seu grupo <em>" + esc(g.g) + "</em>" + (g.tipo ? " <small>" + esc(g.tipo) + "</small>" : "") + "</h2></div>"
      + (C.logo_adm ? '<div' + dA(.2, "dk-v-logo") + ">" + logoAdm() + "</div>" : "") + "</div>"
      + '<div class="dk-g-k">' + K.map(function (k, i) { return "<div" + dA((.3 + i * .08).toFixed(2)) + "><small>" + k[0] + "</small><b" + (/\d/.test(k[1]) ? ' data-count data-delay="' + (.4 + i * .08).toFixed(2) + '" data-dur="1.2"' : "") + ">" + esc(k[1]) + "</b></div>"; }).join("") + "</div>"
      + bar + (chips.length ? '<div class="dk-g-c">' + chips.map(function (c, i) { return "<span" + dA((1.5 + i * .08).toFixed(2)) + ">" + c + "</span>"; }).join("") + "</div>" : "")
      + "<p" + dA(1.9, "dk-rod") + ">Histórico das últimas assembleias, como referência: o resultado depende das ofertas de cada mês. " + rodape("A contemplação não é garantida.") + "</p></div>";
  }
  function sFim(X) {
    var n = X.num, g = X.g, pa = g ? dt(g.assemb) : null;
    var sub = pa && pa >= hoje0() ? "Próxima assembleia do grupo " + esc(g.g) + ": <b>" + pa.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + "</b>. Quanto antes a adesão, antes a sua cota passa a concorrer."
      : "Quanto antes a adesão, antes a sua cota passa a concorrer nas assembleias.";
    var P = ["Confirmamos o grupo, o crédito e a estratégia de lance", "Você assina a adesão e paga a 1ª parcela", "Sua cota concorre todo mês, por sorteio e por lance", "Contemplado, a administradora analisa o crédito e libera o valor"];
    var R = [];
    if (n.credito) R.push(["Crédito", n.credito]); if (n.parcela) R.push(["Parcela inicial", n.parcela]);
    if (n.prazo) R.push(["Prazo", n.prazo + " meses"]); if (g) R.push(["Grupo", g.g]);
    return '<div class="dk-s dk-fim" data-fx="wipe"><div class="dk-fim-g"><div><span' + dA(.05, "dk-eye") + ">Próximo passo</span>"
      + "<h2" + dA(.15) + ">" + (X.cli ? primeiro(X.cli) + ", vamos colocar a sua cota <em>para concorrer?</em>" : "Vamos colocar a sua cota <em>para concorrer?</em>") + "</h2>"
      + "<p" + dA(.3, "dk-lead") + ">" + sub + '</p><ol class="dk-fim-p">'
      + P.map(function (p, i) { return "<li" + dA((.55 + i * .2).toFixed(2)) + "><i>" + (i + 1) + "</i>" + p + "</li>"; }).join("") + "</ol></div>"
      + '<div' + dA(.8, "dk-ct") + '><div class="dk-ct-l">' + logoCB() + (C.logo_adm ? "<i>×</i>" + logoAdm() : "") + "</div>"
      + "<small>Fale com a Consorbens</small><b>" + esc(C.whats || "") + '</b><span class="site">' + esc(C.site || "") + "</span>"
      + '<span class="wa">WhatsApp · atendimento de consultor</span></div></div>'
      + (R.length ? '<div' + dA(1.4, "dk-fim-r") + ">" + R.map(function (r) { return "<span>" + esc(r[0]) + " <b>" + esc(r[1]) + "</b></span>"; }).join("") + "</div>" : "")
      + "<p" + dA(1.6, "dk-rod") + ">Simulação com valores aproximados. " + rodape("A contemplação não é garantida e a liberação do crédito depende da análise da administradora.") + "</p></div>";
  }

  var DECK_CSS = [
    "html,body{margin:0;height:100%;background:#061a17;color:#fff;font-family:'Plus Jakarta Sans',ui-sans-serif,system-ui,'Segoe UI',Roboto,Arial,sans-serif;overflow:hidden;-webkit-font-smoothing:antialiased}",
    ".dk-bg{position:fixed;inset:0;overflow:hidden;background:radial-gradient(1200px 600px at 100% -10%,rgba(45,212,191,.16),transparent 60%),radial-gradient(900px 600px at -10% 110%,rgba(246,147,2,.10),transparent 60%),linear-gradient(160deg,#061a17,#0b2d28 55%,#0f3a35)}",
    ".dk-bg i{position:absolute;border-radius:50%;filter:blur(90px)}.dk-bg i:nth-child(1){width:640px;height:640px;right:-200px;top:-280px;background:rgba(45,212,191,.22);animation:dkDr 18s ease-in-out infinite alternate}",
    ".dk-bg i:nth-child(2){width:560px;height:560px;left:-220px;bottom:-300px;background:rgba(246,147,2,.16);animation:dkDr 22s ease-in-out infinite alternate-reverse}",
    ".dk-bg b{position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,.09) 1px,transparent 1.4px);background-size:28px 28px;-webkit-mask-image:linear-gradient(180deg,#000,transparent 70%);mask-image:linear-gradient(180deg,#000,transparent 70%)}",
    "@keyframes dkDr{to{transform:translate3d(-80px,50px,0) scale(1.12)}}",
    ".dk-bar{position:fixed;top:0;left:0;right:0;display:flex;align-items:center;gap:10px;padding:12px 20px;z-index:6;font-size:13px;color:#a7cfc9;transition:opacity .3s}",
    ".dk-bar .t{flex:1;font-weight:700;display:flex;align-items:center;gap:10px}.dk-bar .t img{height:20px;background:#fff;border-radius:6px;padding:3px 6px}",
    ".dk-bar button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#fff;border-radius:999px;padding:7px 14px;font-weight:700;cursor:pointer;font-family:inherit}.dk-bar button:hover{background:rgba(255,255,255,.18)}",
    ".dk-prog{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,#2dd4bf,#f69302);z-index:7;transition:width .6s cubic-bezier(.2,.8,.2,1)}",
    ".dk-stage{position:fixed;inset:52px 0 44px;display:flex;align-items:center;justify-content:center}",
    ".dk-fit{position:relative}.dk-slide{position:absolute;left:0;top:0;width:1280px;transform-origin:0 0}",
    ".dk-slide.in{animation:dkSIn .65s cubic-bezier(.2,.8,.2,1) both;z-index:1}.dk-stage.b .dk-slide.in{--fr:-60px}",
    "@keyframes dkSIn{from{opacity:0;translate:var(--fr,60px) 0}to{opacity:1;translate:0 0}}",
    ".dk-ghost{pointer-events:none;z-index:0;animation:dkSOut .45s cubic-bezier(.6,0,.4,1) forwards}.dk-stage.b .dk-ghost{--to:80px}",
    "@keyframes dkSOut{to{opacity:0;translate:var(--to,-80px) 0}}",
    ".dk-wipe{position:fixed;inset:0;z-index:5;pointer-events:none;overflow:hidden}.dk-wipe::before{content:'';position:absolute;top:-10%;bottom:-10%;left:0;width:40%;transform:translateX(-130%) skewX(-14deg);background:linear-gradient(90deg,transparent,#f69302 40%,#ffb649 60%,transparent)}",
    ".dk-wipe.go::before{animation:dkWipe .85s cubic-bezier(.77,0,.18,1)}@keyframes dkWipe{to{transform:translateX(330%) skewX(-14deg)}}",
    ".dk-a{animation:dkUp .75s cubic-bezier(.16,1,.3,1) both;animation-delay:var(--d,0s)}@keyframes dkUp{from{opacity:0;transform:translateY(26px)}to{opacity:1;transform:none}}",
    "[data-step]{transition:opacity .5s,translate .6s cubic-bezier(.2,.8,.2,1)}[data-step]:not(.on){opacity:0;translate:0 24px}",
    "[data-count]{display:inline-block;font-variant-numeric:tabular-nums}.dk-hit{animation:dkHit .5s ease}@keyframes dkHit{50%{transform:scale(1.06)}}",
    ".dk-s{box-sizing:border-box;width:1280px;min-height:720px;padding:56px 72px 30px;position:relative;display:flex;flex-direction:column}",
    ".dk-eye{display:inline-flex;align-items:center;gap:10px;font-size:13px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:#ffb649}.dk-eye::before{content:'';width:30px;height:3px;border-radius:3px;background:#f69302}",
    ".dk-s h2{font-size:50px;line-height:1.06;font-weight:800;letter-spacing:-.035em;margin:12px 0 28px;color:#fff}.dk-s h2 em,.dk-h em{font-style:normal;color:#ffb649}.dk-s h2 small{font-size:22px;color:#a7cfc9;font-weight:700;letter-spacing:0}",
    ".dk-lead{font-size:20px;line-height:1.55;color:#cfe6de;margin:0 0 22px;max-width:60ch}",
    ".dk-rod{margin:auto 0 0;padding-top:22px;font-size:12.5px;line-height:1.5;color:#8fb0aa;max-width:110ch;align-self:stretch;text-align:left}",
    ".dk-lcb{height:44px;background:#fff;border-radius:14px;padding:7px 14px;display:block}.dk-lcb-t{font-size:22px}",
    ".dk-ladm.i{height:58px;border-radius:14px;display:block}.dk-ladm.y{height:30px;display:block}",
    ".dk-logos{display:flex;align-items:center;gap:16px}.dk-logos i{font-style:normal;font-size:22px;color:rgba(255,255,255,.5);font-weight:700}",
    /* capa */
    ".dk-capa{display:grid;grid-template-columns:1fr 480px;gap:48px;align-items:center;padding:56px 64px 56px 72px}",
    ".dk-capa-t .dk-eye{margin-top:34px}.dk-h{font-size:62px;line-height:1.02;font-weight:800;letter-spacing:-.04em;margin:16px 0 18px}",
    ".dk-h .ln{display:block;overflow:hidden;padding-bottom:.06em}.dk-h .ln>span{display:inline-block;animation:dkLn .9s cubic-bezier(.16,1,.3,1) both;animation-delay:var(--d)}@keyframes dkLn{from{transform:translateY(110%)}to{transform:none}}",
    ".dk-por{font-size:17px;color:#cfe6de;margin:0 0 22px}.dk-chips{display:flex;gap:10px;flex-wrap:wrap}.dk-chips span{padding:9px 16px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);font-weight:700;font-size:15px}",
    ".dk-capa-ph{position:relative;height:600px;border-radius:36px;overflow:hidden;box-shadow:0 50px 90px -40px rgba(0,0,0,.9);animation:dkUp 1s .15s cubic-bezier(.16,1,.3,1) both}",
    ".dk-ph{position:absolute;inset:0;background-size:cover;background-position:center;animation:dkKb 12s ease-out both}@keyframes dkKb{from{transform:scale(1.14)}to{transform:scale(1)}}",
    ".dk-capa-ph::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,transparent 45%,rgba(6,26,23,.75))}",
    ".dk-capa-adm{position:absolute;left:24px;bottom:24px;z-index:1;padding:12px 16px;border-radius:18px;background:rgba(6,26,23,.55);border:1px solid rgba(255,255,255,.2);backdrop-filter:blur(8px);animation:dkUp .8s 1.2s both}",
    /* como */
    ".dk-w-line{position:relative;height:4px;margin:30px 60px 0;background:rgba(255,255,255,.08);border-radius:4px}.dk-w-line i{position:absolute;inset:0;border-radius:4px;background:linear-gradient(90deg,#2dd4bf,#f69302);transform-origin:left;animation:dkGrow 2.1s .4s cubic-bezier(.6,0,.2,1) both}",
    "@keyframes dkGrow{from{transform:scaleX(0)}to{transform:scaleX(1)}}",
    ".dk-w{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin-top:-22px}.dk-w-s{display:flex;flex-direction:column;align-items:stretch;text-align:center}.dk-w-n{align-self:center}.dk-w-c{flex:1}",
    ".dk-w-n{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;font-weight:800;color:#2b1700;background:linear-gradient(135deg,#ffb649,#f69302);box-shadow:0 0 0 8px rgba(246,147,2,.15);animation:dkPop .5s cubic-bezier(.3,1.6,.5,1) both;animation-delay:var(--d)}",
    "@keyframes dkPop{from{transform:scale(0)}to{transform:scale(1)}}",
    ".dk-w-c{margin-top:22px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:26px;padding:28px 22px;min-height:230px;box-sizing:border-box}",
    ".dk-w-i{font-size:42px;display:block}.dk-w-c b{display:block;font-size:24px;margin:14px 0 8px}.dk-w-c p{margin:0;font-size:17px;line-height:1.5;color:#cfe6de}",
    /* chances */
    ".dk-ch{display:grid;grid-template-columns:1fr 560px;gap:28px;align-items:center}.dk-ch-t{display:flex;flex-direction:column}.dk-ch-i{display:flex;flex-direction:column;gap:10px}.dk-ch-i span{font-size:16px;color:#e6f6f2;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:12px 16px}",
    ".dk-x{width:100%;height:auto;overflow:visible}.dk-x-l{stroke:rgba(255,182,73,.75);stroke-width:3;fill:none;stroke-dasharray:1;stroke-dashoffset:1;animation:dkDraw .6s ease forwards;animation-delay:var(--d)}@keyframes dkDraw{to{stroke-dashoffset:0}}",
    ".dk-x-f{stroke:#ffb649;stroke-width:3;fill:none;stroke-dasharray:6 14;animation:dkFlow 1.2s linear infinite;opacity:.6}@keyframes dkFlow{to{stroke-dashoffset:-40}}",
    ".dk-x-c rect{fill:#fff}.dk-x-c text{text-anchor:middle;font-weight:800;fill:#0b2d28}.dk-x-c .t1{font-size:24px}.dk-x-c .t2{font-size:14px;letter-spacing:.12em;fill:#f69302}",
    ".dk-x-n{animation:dkPop .55s cubic-bezier(.3,1.6,.5,1) both;animation-delay:var(--d);transform-box:fill-box;transform-origin:center}.dk-x-n circle{fill:#123f3e;stroke:#2dd4bf;stroke-width:3}.dk-x-n.o circle{fill:#f69302;stroke:#ffb649}.dk-x-n.w circle{fill:#fff;stroke:#ffb649}",
    ".dk-x-n .r{fill:none !important;stroke-width:2;opacity:.5;animation:dkRing 2.4s ease-out infinite;transform-box:fill-box;transform-origin:center}@keyframes dkRing{from{transform:scale(1);opacity:.6}to{transform:scale(1.45);opacity:0}}",
    ".dk-x-n text{text-anchor:middle;font-weight:800;fill:#fff}.dk-x-n .a{font-size:19px}.dk-x-n .b{font-size:13px;letter-spacing:.06em;opacity:.85}.dk-x-n.o text{fill:#2b1700}.dk-x-n.w text{fill:#0b2d28}",
    /* cards (diferenciais / pilares) */
    ".dk-v-h{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}.dk-v-logo{padding:14px 18px;border-radius:20px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14)}.dk-v-logo.cb{background:none;border:0;padding:0}",
    ".dk-v-g{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.dk-v-g.n1,.dk-v-g.n2,.dk-v-g.n4{grid-template-columns:repeat(2,1fr)}",
    ".dk-v-c{background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.03));border:1px solid rgba(255,255,255,.13);border-radius:24px;padding:24px 24px 22px;position:relative;overflow:hidden}",
    ".dk-v-c::after{content:'';position:absolute;right:-40px;top:-40px;width:120px;height:120px;border-radius:50%;background:rgba(45,212,191,.10)}",
    ".dk-v-i{width:52px;height:52px;border-radius:16px;display:grid;place-items:center;font-size:26px;background:rgba(246,147,2,.14);border:1px solid rgba(246,147,2,.3)}",
    ".dk-v-c b{display:block;font-size:22px;margin:16px 0 6px;letter-spacing:-.01em}.dk-v-c p{margin:0;font-size:16px;line-height:1.5;color:#cfe6de}",
    ".dk-v-x{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:18px}.dk-v-x small{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#ffb649;font-weight:800;margin-right:6px}",
    ".dk-v-x span{font-size:14px;font-weight:700;padding:7px 13px;border-radius:999px;background:rgba(45,212,191,.10);border:1px solid rgba(45,212,191,.28);color:#d9f7ef}",
    /* crédito */
    ".dk-b{text-align:center;display:flex;flex-direction:column;align-items:center}.dk-b h2{margin-bottom:10px}",
    ".dk-b-v{position:relative;margin:6px 0 4px}.dk-b-v b{font-size:120px;font-weight:800;letter-spacing:-.05em;line-height:1;background:linear-gradient(180deg,#fff,#bff3e8);-webkit-background-clip:text;background-clip:text;color:transparent}",
    ".dk-b-u{display:block;height:6px;border-radius:6px;background:linear-gradient(90deg,#2dd4bf,#f69302);margin:10px auto 0;width:60%;transform-origin:left;animation:dkGrow 1.2s 1.2s cubic-bezier(.6,0,.2,1) both}",
    ".dk-b-meta{font-size:19px;color:#cfe6de;margin:18px 0 26px}.dk-b-meta .sep{font-style:normal;margin:0 12px;color:#ffb649}",
    ".dk-b-st{display:flex;align-items:center;justify-content:space-between;gap:30px;width:820px;box-sizing:border-box;padding:22px 28px;border-radius:24px;background:linear-gradient(135deg,#0f9d6b,#0c7a55);box-shadow:0 30px 60px -30px rgba(15,157,107,.8);text-align:left;margin-bottom:16px}",
    ".dk-b-st span{font-size:20px;font-weight:800}.dk-b-st small{display:block;font-size:14px;font-weight:600;color:#c9f7e3;margin-top:4px}.dk-b-st b{font-size:44px;font-weight:800;letter-spacing:-.03em}",
    ".dk-b-pp{display:flex;align-items:stretch;gap:18px;width:820px}.dk-b-pp>div{flex:1;text-align:left;padding:18px 24px;border-radius:22px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14)}",
    ".dk-b-pp>div.o{background:rgba(246,147,2,.12);border-color:rgba(246,147,2,.4)}.dk-b-pp small{display:block;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#a7cfc9;font-weight:800}.dk-b-pp b{font-size:34px;font-weight:800}.dk-b-pp em{font-style:normal;font-size:16px;color:#a7cfc9;margin-left:4px}",
    ".dk-b-pp>i{align-self:center;font-style:normal;font-size:30px;color:#ffb649}",
    ".dk-b-dica{position:absolute;bottom:26px;left:0;right:0;font-size:13px;color:#8fb0aa;animation:dkBlink 1.6s ease-in-out infinite}@keyframes dkBlink{50%{opacity:.35}}.dk-b-dica.off{display:none}",
    /* folha (card real do simulador) */
    ".dk-f{display:flex;flex-direction:column;align-items:center}.dk-f-h{text-align:center}.dk-f h2{margin-bottom:22px}",
    ".dk-f-sheet{background:#fff;color:#111;border-radius:26px;padding:22px;max-width:1080px;box-shadow:0 50px 90px -40px rgba(0,0,0,.9);animation:dkSheet 1s .25s cubic-bezier(.16,1,.3,1) both;transform-origin:50% 0}",
    "@keyframes dkSheet{from{opacity:0;transform:translateY(40px) rotateX(10deg) scale(.96)}to{opacity:1;transform:none}}",
    ".dk-f-sheet.cards{background:transparent;padding:0;box-shadow:none;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;width:1120px;max-width:none;color:inherit}",
    ".dk-f.side{display:grid;grid-template-columns:1fr 420px;gap:56px;align-items:center}.dk-f.side h2{font-size:44px}.dk-f.side .dk-rod{grid-column:1/-1}",
    ".dk-f-l h2{margin-bottom:24px}.dk-f-k{display:grid;gap:10px}.dk-f-k>div{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding:15px 20px;border-radius:18px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12)}",
    ".dk-f-k small{font-size:16px;color:#cfe6de;font-weight:600}.dk-f-k b{font-size:26px;font-weight:800;letter-spacing:-.02em}.dk-f-k>div.o{background:linear-gradient(135deg,#0f9d6b,#0c7a55);border-color:transparent}.dk-f-k>div.o small{color:#d7fbe9}",
    ".dk-f-r{perspective:1400px;display:flex;justify-content:center}.dk-f.side .dk-f-sheet{padding:12px;max-width:380px;animation:dkSheet3 1.1s .3s cubic-bezier(.16,1,.3,1) both,dkFloat 6s 1.4s ease-in-out infinite alternate;transform:rotateY(-8deg) rotateX(3deg)}",
    "@keyframes dkSheet3{from{opacity:0;transform:translateY(60px) rotateY(-25deg) rotateX(8deg)}to{opacity:1;transform:rotateY(-8deg) rotateX(3deg)}}@keyframes dkFloat{from{transform:rotateY(-8deg) rotateX(3deg) translateY(0)}to{transform:rotateY(-4deg) rotateX(2deg) translateY(-10px)}}",
    ".dk-f.side .dk-f-sheet>*{max-width:none !important;width:100% !important}",
    /* cards do Itaú IA com a paleta da casa */
    ".dk-f-sheet.cards{--bg1:#071d1a;--bg2:#071d1a;--card:#10302b;--card2:#153a34;--line:#1f4a43;--mut:#a9c9c3;--txt:#eaf6f3;--blue:#5eead4;color:#eaf6f3}",
    ".dk-f-sheet.cards .rc{background:linear-gradient(180deg,#153a34,#0c2824) !important;border-radius:22px;box-shadow:0 40px 70px -40px rgba(0,0,0,.9)}.dk-f-sheet.cards .rc .mgrid div,.dk-f-sheet.cards .rc .note{background:#081f1c}",
    /* grupo */
    ".dk-g-h{display:flex;justify-content:space-between;align-items:flex-start}.dk-g-k{display:grid;grid-template-columns:repeat(6,1fr);gap:14px}",
    ".dk-g-k>div{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.13);border-radius:22px;padding:18px 18px}.dk-g-k small{display:block;font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:#a7cfc9;font-weight:800;min-height:28px}",
    ".dk-g-k b{display:block;white-space:nowrap;font-size:30px;font-weight:800;margin-top:6px;color:#2dd4bf;letter-spacing:-.02em}.dk-g-k>div:first-child{background:linear-gradient(135deg,#ffb649,#f69302);border-color:transparent}.dk-g-k>div:first-child small{color:#5b3600}.dk-g-k>div:first-child b{color:#2b1700}",
    ".dk-g-bar{margin-top:22px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:24px;padding:20px 28px 16px}",
    ".dk-g-bar .t{display:flex;justify-content:space-between;font-size:16px;color:#cfe6de;margin-bottom:40px}.dk-g-bar .t b{color:#ffb649}",
    ".dk-g-bar .b{position:relative;height:14px;border-radius:9px;background:rgba(0,0,0,.35)}.dk-g-bar .rng{position:absolute;top:0;bottom:0;border-radius:9px;background:linear-gradient(90deg,#22c55e,#f69302);transform-origin:left;animation:dkGrow 1.3s 1.3s cubic-bezier(.2,.8,.2,1) both}",
    ".dk-g-bar u{position:absolute;top:-8px;width:3px;height:30px;background:#fff;border-radius:2px;text-decoration:none;animation:dkUp .6s 2s both}.dk-g-bar u em{position:absolute;bottom:34px;left:50%;transform:translateX(-50%);white-space:nowrap;font-style:normal;font-size:13px;font-weight:800;color:#e6f6f2;background:rgba(6,26,23,.85);border:1px solid rgba(255,255,255,.18);padding:3px 9px;border-radius:999px}",
    ".dk-g-bar u.md{background:#ffb649}.dk-g-bar u.md em{color:#2b1700;background:#ffb649;border-color:transparent}.dk-g-bar u.mx em,.dk-g-bar u.mn em{bottom:-30px}.dk-g-bar u.voce{background:#2dd4bf;width:5px}.dk-g-bar u.voce em{background:#2dd4bf;color:#062a24;border-color:transparent}",
    ".dk-g-bar .esc{display:flex;justify-content:space-between;font-size:12px;color:#6f908a;margin-top:42px}",
    ".dk-g-c{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.dk-g-c span{font-size:15px;padding:9px 15px;border-radius:999px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14);color:#e6f6f2}",
    /* fim */
    ".dk-fim-g{display:grid;grid-template-columns:1fr 400px;gap:44px;align-items:start}.dk-fim-p{list-style:none;padding:0;margin:0;display:grid;gap:12px}",
    ".dk-fim-p li{display:flex;align-items:center;gap:16px;font-size:19px;font-weight:700;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:14px 18px}",
    ".dk-fim-p li i{font-style:normal;flex:none;width:34px;height:34px;border-radius:11px;display:grid;place-items:center;background:rgba(45,212,191,.16);color:#7fe9b4;font-weight:800}",
    ".dk-ct{margin-top:46px;background:#fff;color:#0f2a2a;border-radius:30px;padding:30px 30px 26px;box-shadow:0 50px 90px -40px rgba(0,0,0,.9);display:flex;flex-direction:column;gap:6px}",
    ".dk-ct-l{display:flex;align-items:center;gap:12px;margin-bottom:16px}.dk-ct-l i{font-style:normal;color:#94a3b8;font-weight:700}.dk-ct .dk-lcb{padding:0;height:46px}.dk-ct .dk-ladm.y{filter:invert(1) brightness(.2);height:26px}.dk-ct .dk-ladm.i{height:48px}",
    ".dk-ct small{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:#64748b;font-weight:800}.dk-ct b{font-size:34px;font-weight:800;letter-spacing:-.02em}.dk-ct .site{font-size:18px;font-weight:700;color:#0f766e}",
    ".dk-ct .wa{margin-top:12px;align-self:flex-start;font-size:14px;font-weight:800;color:#fff;background:linear-gradient(135deg,#25d366,#128c4b);border-radius:999px;padding:9px 16px}",
    ".dk-fim-r{display:flex;gap:12px;margin-top:26px}.dk-fim-r span{flex:1;font-size:14px;color:#a7cfc9;background:rgba(246,147,2,.1);border:1px solid rgba(246,147,2,.35);border-radius:18px;padding:12px 16px}.dk-fim-r b{display:block;font-size:22px;color:#fff;margin-top:2px}",
    /* rodapé de navegação */
    ".dk-dots{position:fixed;bottom:16px;left:0;right:0;display:flex;justify-content:center;gap:8px;z-index:6}.dk-dots button{width:10px;height:10px;border-radius:50%;border:0;background:rgba(255,255,255,.25);cursor:pointer;padding:0;transition:.3s}.dk-dots button.on{background:#ffb649;width:30px;border-radius:9px}",
    ".na-capa .dk-bar .t{opacity:0}",
    "@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none !important;transition:none !important}[data-step]:not(.on){opacity:1;translate:none}}",
    "@media print{.dk-bar,.dk-dots,.dk-prog{display:none}}"
  ].join("");

  // runtime da janela de apresentação (serializado com toString; roda lá, não aqui)
  function DECK_RT() {
    var S = window.__S, i = 0, tok = 0, RM = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var st = document.getElementById("st"), fit = document.getElementById("fit"), sl = document.getElementById("sl");
    function num(t) { return parseFloat(String(t).replace(/[^\d,]/g, "").replace(",", ".")); }
    function count(el) {
      var fim = el.getAttribute("data-fim") || el.textContent.trim(); el.setAttribute("data-fim", fim);
      var to = num(fim); if (!(to > 0) || RM) { el.textContent = fim; return; }
      var pre = (fim.match(/^[^\d]*/) || [""])[0], suf = (fim.match(/[^\d]*$/) || [""])[0], m = /,(\d+)\D*$/.exec(fim), dec = m ? m[1].length : 0;
      var dur = (+el.getAttribute("data-dur") || 1.2) * 1e3, my = tok, t0 = null;
      var fmt = function (v) { return pre + v.toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suf; };
      el.style.minWidth = el.offsetWidth + "px"; el.textContent = fmt(0);
      setTimeout(function () { requestAnimationFrame(function step(t) {
        if (my !== tok || !el.isConnected) { el.textContent = fim; return; }
        if (t0 === null) t0 = t; var k = Math.min(1, (t - t0) / dur), e = k === 1 ? 1 : 1 - Math.pow(2, -10 * k);
        el.textContent = k < 1 ? fmt(to * e) : fim; if (k < 1) requestAnimationFrame(step); else el.classList.add("dk-hit");
      }); }, (+el.getAttribute("data-delay") || 0) * 1e3);
    }
    function doFit() {
      var s = sl.firstElementChild; if (!s) return;
      sl.style.transform = "none"; var h = Math.max(720, sl.offsetHeight);
      var k = Math.min((st.clientWidth - 24) / 1280, (st.clientHeight - 16) / h); k = Math.max(.25, Math.min(2, k));
      sl.style.transform = "scale(" + k + ")"; fit.style.width = 1280 * k + "px"; fit.style.height = h * k + "px";
      [].forEach.call(fit.querySelectorAll(".dk-ghost"), function (g) { g.style.transform = sl.style.transform; });
    }
    function ir(n, dir) {
      n = Math.max(0, Math.min(S.length - 1, n));
      if (sl.firstElementChild && n !== i && !RM) {
        [].forEach.call(fit.querySelectorAll(".dk-ghost"), function (g) { g.remove(); });
        var gh = sl.cloneNode(true); gh.removeAttribute("id"); gh.className = "dk-slide dk-ghost"; fit.appendChild(gh); setTimeout(function () { gh.remove(); }, 500);
      }
      var back = (dir || (n >= i ? 1 : -1)) < 0; st.classList.toggle("b", back);
      i = n; tok++; sl.innerHTML = S[i]; sl.classList.remove("in"); void sl.offsetWidth; sl.classList.add("in");
      var f = sl.firstElementChild;
      document.body.classList.toggle("na-capa", !!(f && f.hasAttribute("data-capa")));
      if (f && f.getAttribute("data-fx") === "wipe" && !RM) { var w = document.getElementById("wipe"); w.classList.remove("go"); void w.offsetWidth; w.classList.add("go"); }
      if (back) [].forEach.call(sl.querySelectorAll("[data-step]"), function (e) { e.classList.add("on"); });
      document.getElementById("p").style.width = ((i + 1) / S.length * 100) + "%";
      document.getElementById("n").textContent = (i + 1) + " / " + S.length;
      [].forEach.call(document.querySelectorAll("#dots button"), function (b, j) { b.classList.toggle("on", j === i); });
      doFit();
      [].forEach.call(sl.querySelectorAll("[data-count]"), function (el) { if (!el.closest("[data-step]:not(.on)")) count(el); });
      [].forEach.call(sl.querySelectorAll("img"), function (im) {   // imagem quebrada (ex.: logo externo offline) some em vez de mostrar o ícone
        if (im.complete && !im.naturalWidth) { im.remove(); return; }
        im.addEventListener("error", function () { im.remove(); doFit(); }, { once: true });
        if (!im.complete) im.addEventListener("load", doFit, { once: true });
      });
    }
    function nav(dd) {
      if (dd > 0) {
        var nx = sl.querySelector("[data-step]:not(.on)");
        if (nx) { nx.classList.add("on"); [].forEach.call(nx.querySelectorAll("[data-count]"), count); var dc = sl.querySelector(".dk-b-dica"); if (dc && !sl.querySelector("[data-step]:not(.on)")) dc.classList.add("off"); return; }
      }
      ir(i + dd, dd);
    }
    function fs() { var e = document.documentElement; if (!document.fullscreenElement && e.requestFullscreen) e.requestFullscreen().catch(function () {}); else if (document.exitFullscreen) document.exitFullscreen(); }
    window.ir = ir; window.nav = nav; window.fs = fs;
    window.revelar = function () { [].forEach.call(sl.querySelectorAll("[data-step]"), function (e) { e.classList.add("on"); [].forEach.call(e.querySelectorAll("[data-count]"), count); }); var dc = sl.querySelector(".dk-b-dica"); if (dc) dc.classList.add("off"); };
    document.getElementById("dots").innerHTML = S.map(function (_, j) { return "<button aria-label='Slide " + (j + 1) + "'></button>"; }).join("");
    [].forEach.call(document.querySelectorAll("#dots button"), function (b, j) { b.onclick = function () { ir(j); }; });
    document.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (["ArrowRight", "PageDown", " ", "Enter"].indexOf(e.key) >= 0) { e.preventDefault(); nav(1); }
      else if (["ArrowLeft", "PageUp", "Backspace"].indexOf(e.key) >= 0) { e.preventDefault(); nav(-1); }
      else if (e.key === "f" || e.key === "F") fs();
      else if (e.key === "Home") ir(0); else if (e.key === "End") ir(S.length - 1);
      else if (/^[1-9]$/.test(e.key)) ir(+e.key - 1);
      else if (e.key === "p" || e.key === "P") { for (var k = 0; k < S.length; k++) if (S[k].indexOf('data-prop="1"') >= 0) { ir(k); break; } }
      else if (e.key === "Escape" && !document.fullscreenElement) window.close();
    });
    st.addEventListener("click", function (e) { if (!e.target.closest("a,button")) nav(1); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(doFit);
    window.addEventListener("resize", doFit);
    ir(0);
  }

  function montarSlides() {
    var B = blocos();
    if (!B.length) return null;
    var cli = ((q("#cbxCli") || {}).value || (q("#pdfCliente") || {}).value || (q("#nome") || {}).value || "").trim();
    var txt = B.map(function (b) { return b.innerText; }).join("\n");
    var X = { cli: cli, num: extrair(txt), g: grupoAtual(txt), prod: produtoAtual(txt) };
    if (C.sim !== "yamaha" && X.g && X.g.tipo) {
      var tp = norm(X.g.tipo);
      X.prod = tp.indexOf("imov") >= 0 ? "imovel" : /caminh|pesad/.test(tp) ? "caminhao" : tp.indexOf("moto") >= 0 ? "moto" : /roda|auto|leve|veic/.test(tp) ? "auto" : X.prod;
    }
    var cards = C.sim === "itau_ia" && !vis(q("#manual"));
    var lado = C.sim === "yamaha" && B.length === 1;
    var folhas = cards ? [sFolha(B.map(clonar).join(""), 0, 1, true)] : B.map(function (b, i) { return sFolha(clonar(b), i, B.length, false, lado ? X : null); });
    var nomeAdm = esc(C.adm || "administradora"), art = /^ita/i.test(C.adm || "") ? "o" : "a";   // "o Itaú", "a Yamaha"
    var S = [sCapa(X), sComo(), sChances(X),
             sCards("Por que " + art + " " + nomeAdm, "O que " + art + " <em>" + nomeAdm + "</em> oferece no seu plano", difAdm(X.prod), rodape("Condições conforme o regulamento e as regras vigentes da administradora."), "adm"),
             sCredito(X)].concat(folhas).concat([
             sGrupo(X),
             sCards("Por que a Consorbens", "Quem cuida do seu plano <em>do início ao fim</em>", ((C.dif || {}).consorbens || []).slice(0, 6), "", "cb"),
             sFim(X)]);
    return { S: S.filter(Boolean), cli: cli };
  }
  function deckHTML(S, cli) {
    return "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'><title>Apresentação · Consorbens</title>"
      + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      + "<link href='https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap' rel='stylesheet'>"
      + "<style>" + estilos() + "</style><style>" + DECK_CSS + "</style></head><body>"
      + "<div class='dk-bg'><i></i><i></i><b></b></div><div class='dk-prog' id='p'></div><i class='dk-wipe' id='wipe'></i>"
      + "<div class='dk-bar'><span class='t'>" + (C.logo ? "<img src='" + C.logo + "' alt=''>" : "") + "Consorbens · " + esc(C.adm || "") + (cli ? " · " + esc(cli) : "") + "</span><span id='n'></span>"
      + "<button onclick='nav(-1)' aria-label='Voltar'>◀</button><button onclick='nav(1)' aria-label='Avançar'>▶</button><button onclick='fs()'>⛶ Tela cheia</button><button onclick='window.close()' aria-label='Fechar'>✕</button></div>"
      + "<div class='dk-stage' id='st'><div class='dk-fit' id='fit'><div class='dk-slide' id='sl'></div></div></div><div class='dk-dots' id='dots'></div>"
      + "<script>window.__S=" + JSON.stringify(S).replace(/<\/script/gi, "<\\/script").replace(/<!--/g, "<\\!--") + ";(" + DECK_RT.toString() + ")();<\/script></body></html>";
  }
  function abrir() {
    var m = montarSlides();
    if (!m) { alert("Gere a simulação primeiro — o modo apresentação mostra o resultado que está na tela."); return; }
    var w = window.open("", "_blank");
    if (!w) { alert("O navegador bloqueou a janela da apresentação. Permita pop-ups para este site e tente de novo."); return; }
    w.document.open(); w.document.write(deckHTML(m.S, m.cli)); w.document.close();
  }
  window.cbxApresentar = abrir;
  window.cbxDeckHTML = function () { var m = montarSlides(); return m ? deckHTML(m.S, m.cli) : ""; };   // usado nos testes

  function botoesNasAcoes() {
    var acoes = C.sim === "yamaha" ? qa("#resumoAcoes, #resumoAcoesEstr") : C.sim === "itau_ia" ? qa(".actions") : [];
    acoes.forEach(function (a) { a.appendChild(botao()); });
    if (C.sim === "itau_manual") ["#resultado", "#resumoEstruturadoBox"].forEach(function (s) {
      var e = q(s); if (e) { var w = d.createElement("div"); w.className = "no-apres"; w.style.cssText = "margin:14px 0;text-align:center"; w.appendChild(botao()); e.parentNode.insertBefore(w, e.nextSibling); }
    });
  }

  function montar() {
    try { montarHero(); } catch (e) { if (window.console) console.warn("cbx hero", e); }
    try { if (C.sim === "itau_manual") rotulosItauManual(); } catch (e) { if (window.console) console.warn("cbx rotulos", e); }
    botoesNasAcoes();
  }
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", montar); else montar();
})();
