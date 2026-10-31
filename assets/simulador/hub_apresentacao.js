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
    hero.innerHTML = '<div class="cbx-blob b1"></div><div class="cbx-blob b2"></div><div class="cbx-dots"></div>'
      + '<div class="cbx-hero-in"><div class="cbx-top"><div class="cbx-brand"><div class="cbx-logo-box">' + logo + '</div><div class="cbx-div"></div>'
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
      .map(function (s) { return s.textContent; }).join("\n").replace(/body\s*\{[^}]*\}/g, "");
  }

  var LOGO = C.logo ? '<img class="ap-logo" src="' + C.logo + '" alt="Consorbens">' : '<b class="ap-logo-t">CONSORBENS</b>';
  var NOME_PROD = { imovel: "imóvel", auto: "automóvel", moto: "moto", caminhao: "veículo pesado" };
  var MOTO_SVG = '<svg viewBox="0 0 200 120" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"><circle cx="45" cy="82" r="26"/><circle cx="155" cy="82" r="26"/><path d="M45 82h40l28-38h24l18 38"/><path d="M113 44l-10-20H85"/><path d="M137 44l-6-18h18"/><path d="M70 50h34"/></svg>';
  function sCapa(cli, prod) {
    var hoje = new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
    var foto = (C.fotos || {})[prod];
    var arte = foto ? '<div class="ap-ph" style="background-image:url(' + foto + ')"></div>' : '<div class="ap-ph ap-ph-art">' + MOTO_SVG + "</div>";
    var rot = ["Como funciona o consórcio", "Sua simulação", "O grupo indicado", "Próximos passos"];
    return '<div class="cbx-s ap-capa"><div class="ap-l">' + LOGO
      + '<span class="ap-eye">Proposta de consórcio · ' + esc(C.adm || "") + "</span>"
      + "<h1><span>" + (cli ? "Olá, " + esc(cli) + "." : "Seu plano,") + "</span><span>" + (cli ? "Seu " : "seu ") + esc(NOME_PROD[prod] || "bem") + " com <em>planejamento</em>.</span></h1>"
      + "<p>Preparamos esta simulação para você comparar e decidir com calma.</p>"
      + '<ol class="ap-rot">' + rot.map(function (r, i) { return '<li style="--d:' + (300 + i * 110) + 'ms"><b>' + (i + 1) + "</b>" + r + "</li>"; }).join("") + "</ol>"
      + '<div class="ap-chips"><span>📅 ' + hoje + "</span><span>🤝 Consorbens</span></div></div>"
      + '<div class="ap-r">' + arte + '<div class="ap-float a"><small>Administradora</small><b>' + esc(C.adm || "—") + "</b></div>"
      + '<div class="ap-float b"><small>Modalidade</small><b>Consórcio</b></div></div></div>';
  }
  function sComo() {
    var p = [["1", "Você entra no grupo", "Paga parcelas mensais sem juros de financiamento: taxa de administração, fundo de reserva e seguro, quando houver."],
             ["2", "Contemplação", "Todo mês há assembleia com sorteio e lances. Com lance você aumenta suas chances de ser contemplado antes."],
             ["3", "Crédito para comprar", "Contemplado, a administradora faz a análise de crédito e libera o valor para a compra do bem."]];
    return '<div class="cbx-s ap-como"><span class="ap-eye">Como funciona</span><h2>Consórcio em 3 passos</h2><div class="ap-steps">'
      + p.map(function (x, i) { return '<div class="ap-step" style="--d:' + (i * 140) + 'ms"><b>' + x[0] + "</b><h3>" + x[1] + "</h3><p>" + x[2] + "</p></div>"; }).join("")
      + '</div><svg class="ap-path" viewBox="0 0 1000 40" preserveAspectRatio="none"><path d="M10 20 H990" stroke="rgba(255,182,73,.6)" stroke-width="3" stroke-dasharray="10 8" fill="none"/></svg></div>';
  }
  function sBloco(html, i, n) {
    return '<div class="cbx-s ap-prop"><span class="ap-eye">Sua simulação' + (n > 1 ? " · " + (i + 1) + " de " + n : "") + '</span><div class="ap-sheet">' + html + "</div></div>";
  }
  function sGrupo(g) {
    var it = [["Média de lance", pct(g.media)], ["Menor lance que ganhou", pct(g.menor)], ["Maior lance", pct(g.maior)],
              ["Contemplados no lance livre", g.cont == null ? "—" : g.cont], ["Vagas", g.vagas == null ? "—" : g.vagas], ["Prazo", g.prazo ? g.prazo + " meses" : "—"]];
    var bar = g.media != null ? '<div class="ap-bar"><div class="ap-bar-t"><span>Média de lance do grupo</span><b>' + pct(g.media) + '</b></div><div class="ap-bar-b"><i style="width:' + Math.min(100, g.media) + '%"></i>'
      + (g.menor != null ? '<u style="left:' + Math.min(100, g.menor) + '%"></u>' : "") + "</div></div>" : "";
    return '<div class="cbx-s ap-grp"><span class="ap-eye">Por que este grupo</span><h2>Grupo ' + esc(g.g) + (g.tipo ? " <small>" + esc(g.tipo) + "</small>" : "") + "</h2>"
      + '<div class="ap-kp">' + it.map(function (x, i) { return '<div style="--d:' + (i * 90) + 'ms"><small>' + x[0] + "</small><b>" + x[1] + "</b></div>"; }).join("") + "</div>" + bar
      + '<p class="ap-note">Histórico das últimas assembleias. Lance é uma oferta: o resultado depende das ofertas de cada mês.</p></div>';
  }
  function sFim() {
    return '<div class="cbx-s ap-fim"><div>' + LOGO + "<h2>Próximos passos</h2><ol>"
      + "<li style='--d:100ms'>Escolher a proposta e fazer a adesão à cota</li><li style='--d:220ms'>Definir a estratégia de lance para as próximas assembleias</li>"
      + "<li style='--d:340ms'>Contemplado: análise de crédito pela administradora e liberação do valor</li></ol>"
      + '<div class="ap-ct">' + esc(C.contato || "") + "</div>"
      + '<p class="ap-note">Simulação com valores aproximados, sujeita às regras e à confirmação da administradora. Não é garantia de contemplação.</p></div></div>';
  }

  var DECK_CSS = ""
    + "html,body{margin:0;height:100%;background:#061a17;color:#fff;font-family:'Plus Jakarta Sans',ui-sans-serif,system-ui,'Segoe UI',Roboto,Arial,sans-serif;overflow:hidden;-webkit-font-smoothing:antialiased}"
    + ".ap-bg{position:fixed;inset:0;overflow:hidden;background:linear-gradient(140deg,#071f1c,#0b2d28 50%,#123f3e)}"
    + ".ap-bg i{position:absolute;border-radius:50%;filter:blur(80px)}.ap-bg i:nth-child(1){width:620px;height:620px;right:-160px;top:-260px;background:rgba(45,212,191,.32);animation:apDr 18s ease-in-out infinite alternate}"
    + ".ap-bg i:nth-child(2){width:520px;height:520px;left:-180px;bottom:-280px;background:rgba(246,147,2,.24);animation:apDr 22s ease-in-out infinite alternate-reverse}"
    + "@keyframes apDr{to{transform:translate3d(-80px,50px,0) scale(1.12)}}"
    + ".ap-barra{position:fixed;top:0;left:0;right:0;display:flex;align-items:center;gap:10px;padding:12px 20px;z-index:3;font-size:13px;color:#a7cfc9}"
    + ".ap-barra .t{flex:1;font-weight:700}.ap-barra button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#fff;border-radius:999px;padding:7px 14px;font-weight:700;cursor:pointer;font-family:inherit}"
    + ".ap-barra button:hover{background:rgba(255,255,255,.18)}"
    + ".ap-prog{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,#2dd4bf,#f69302);z-index:4;transition:width .5s}"
    + ".ap-stage{position:fixed;inset:54px 0 46px;display:flex;align-items:center;justify-content:center}"
    + ".ap-fit{transform-origin:center center}"
    + ".cbx-s{width:1180px;min-height:640px;box-sizing:border-box;padding:46px 60px;animation:apIn .7s cubic-bezier(.2,.8,.2,1) both}"
    + ".ap-fit.back .cbx-s{animation-name:apInB}"
    + "@keyframes apIn{from{opacity:0;transform:translateX(60px) scale(.98)}to{opacity:1;transform:none}}@keyframes apInB{from{opacity:0;transform:translateX(-60px) scale(.98)}to{opacity:1;transform:none}}"
    + "@keyframes apUp{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:none}}"
    + ".ap-eye{display:inline-flex;align-items:center;gap:10px;font-size:13px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:#ffb649}.ap-eye::before{content:'';width:30px;height:3px;border-radius:3px;background:#f69302}"
    + ".cbx-s h2{font-size:46px;font-weight:800;letter-spacing:-.03em;margin:12px 0 28px}.cbx-s h2 small{font-size:20px;color:#a7cfc9;font-weight:700}"
    + ".ap-logo{height:46px;background:#fff;border-radius:14px;padding:7px 14px;display:block;margin-bottom:26px}.ap-logo-t{display:block;font-size:24px;margin-bottom:26px}"
    + ".ap-capa{display:grid;grid-template-columns:1fr 470px;gap:44px;align-items:center}"
    + ".ap-capa h1{font-size:58px;line-height:1.04;font-weight:800;letter-spacing:-.035em;margin:16px 0}.ap-capa h1 span{display:block;animation:apUp .9s cubic-bezier(.16,1,.3,1) both}.ap-capa h1 span+span{animation-delay:.15s}"
    + ".ap-capa em{font-style:normal;color:#ffb649}.ap-capa p{font-size:19px;color:#cfe6de;margin:0 0 22px}"
    + ".ap-rot{list-style:none;padding:0;margin:0 0 22px;display:grid;grid-template-columns:1fr 1fr;gap:10px 18px}.ap-rot li{display:flex;align-items:center;gap:10px;font-size:15.5px;font-weight:700;color:#e6f6f2;animation:apUp .6s var(--d) both}"
    + ".ap-rot b{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;background:rgba(45,212,191,.16);color:#7fe9b4;font-size:13px;flex:none}"
    + ".ap-chips{display:flex;gap:10px;flex-wrap:wrap}.ap-chips span{padding:8px 16px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);font-weight:700;font-size:14px}"
    + ".ap-r{position:relative;height:520px;animation:apUp 1s .1s cubic-bezier(.16,1,.3,1) both}"
    + ".ap-ph{position:absolute;inset:0;border-radius:34px;background-size:cover;background-position:center;box-shadow:0 40px 80px -30px rgba(0,0,0,.8);animation:apKb 9s ease-out both;overflow:hidden}"
    + ".ap-ph::after{content:'';position:absolute;inset:0;border-radius:inherit;background:linear-gradient(180deg,transparent 50%,rgba(6,26,23,.55))}"
    + ".ap-ph-art{display:grid;place-items:center;background:radial-gradient(circle at 30% 30%,#2dd4bf,#0f766e 55%,#0b2d28)}.ap-ph-art svg{width:72%}"
    + "@keyframes apKb{from{transform:scale(1.08)}to{transform:scale(1)}}"
    + ".ap-float{position:absolute;background:rgba(255,255,255,.95);color:#0f2a2a;border-radius:18px;padding:12px 16px;box-shadow:0 20px 40px -18px rgba(0,0,0,.6);animation:apBob 5s ease-in-out infinite}"
    + ".ap-float small{display:block;font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#64748b}.ap-float b{font-size:18px}"
    + ".ap-float.a{left:-34px;bottom:56px}.ap-float.b{right:-20px;top:40px;animation-delay:-2.5s;background:linear-gradient(135deg,#ffb649,#f69302);color:#2b1700}.ap-float.b small{color:#5b3600}"
    + "@keyframes apBob{50%{transform:translateY(-8px)}}"
    + ".ap-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;position:relative;z-index:1}.ap-step{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:26px;padding:30px;animation:apUp .7s var(--d) both}"
    + ".ap-step b{display:inline-flex;width:48px;height:48px;border-radius:16px;align-items:center;justify-content:center;background:linear-gradient(135deg,#ffb649,#f69302);color:#2b1700;font-size:22px}"
    + ".ap-step h3{font-size:25px;margin:18px 0 8px}.ap-step p{font-size:17px;line-height:1.55;color:#cfe6de;margin:0}"
    + ".ap-path{display:block;width:100%;height:40px;margin-top:18px}.ap-path path{animation:apDash 2s linear infinite}@keyframes apDash{to{stroke-dashoffset:-36}}"
    + ".ap-prop{display:flex;flex-direction:column;align-items:center}.ap-prop .ap-eye{margin-bottom:18px}.ap-prop .ap-sheet{zoom:1.25}"
    + ".ap-sheet{background:#fff;color:#111;border-radius:24px;padding:22px;max-width:980px;box-shadow:0 40px 80px -30px rgba(0,0,0,.7);overflow:hidden;animation:apUp .8s .1s cubic-bezier(.16,1,.3,1) both}"
    + ".ap-kp{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.ap-kp div{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:22px;padding:22px 24px;animation:apUp .6s var(--d) both}"
    + ".ap-kp small{display:block;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#a7cfc9;font-weight:800}.ap-kp b{display:block;font-size:40px;font-weight:800;margin-top:6px;color:#2dd4bf;letter-spacing:-.02em}"
    + ".ap-bar{margin-top:24px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:18px 22px}.ap-bar-t{display:flex;justify-content:space-between;font-size:15px;color:#cfe6de;margin-bottom:10px}.ap-bar-t b{color:#ffb649}"
    + ".ap-bar-b{position:relative;height:12px;border-radius:9px;background:rgba(0,0,0,.35)}.ap-bar-b i{display:block;height:100%;border-radius:9px;background:linear-gradient(90deg,#22c55e,#f69302);transform-origin:left;animation:apGrow 1.2s .3s cubic-bezier(.2,.8,.2,1) both}"
    + ".ap-bar-b u{position:absolute;top:-5px;width:3px;height:22px;background:#fff;border-radius:2px}@keyframes apGrow{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
    + ".ap-note{font-size:14px;color:#a7cfc9;margin-top:24px}"
    + ".ap-fim{display:flex;align-items:center}.ap-fim ol{font-size:25px;line-height:1.7;padding-left:30px;margin:0 0 26px}.ap-fim li{animation:apUp .6s var(--d) both}.ap-fim li::marker{color:#ffb649;font-weight:900}"
    + ".ap-ct{display:inline-block;font-size:22px;font-weight:800;padding:13px 24px;border-radius:999px;background:linear-gradient(135deg,#ffb649,#f69302);color:#2b1700;box-shadow:0 18px 36px -16px rgba(246,147,2,.8)}"
    + ".ap-dots{position:fixed;bottom:16px;left:0;right:0;display:flex;justify-content:center;gap:8px;z-index:3}.ap-dots button{width:10px;height:10px;border-radius:50%;border:0;background:rgba(255,255,255,.25);cursor:pointer;padding:0;transition:.3s}.ap-dots button.on{background:#ffb649;width:28px;border-radius:9px}"
    + "@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none !important;transition:none !important}}"
    + "@media print{.ap-barra,.ap-dots,.ap-prog{display:none}}";

  function montarSlides() {
    var B = blocos();
    if (!B.length) return null;
    var cli = (q("#cbxCli") || {}).value || (q("#pdfCliente") || {}).value || (q("#nome") || {}).value || "";
    var htmls = B.map(clonar), txt = B.map(function (b) { return b.innerText; }).join(" ");
    var g = grupoAtual(txt), prod = produtoAtual(txt);
    var S = [sCapa(cli.trim(), prod), sComo()].concat(htmls.map(function (h, i) { return sBloco(h, i, htmls.length); }));
    if (g) S.push(sGrupo(g));
    S.push(sFim());
    return { S: S, cli: cli.trim() };
  }
  function deckHTML(S, cli) {
    return "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'><title>Apresentação · Consorbens</title>"
      + "<link href='https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap' rel='stylesheet'>"
      + "<style>" + estilos() + "</style><style>" + DECK_CSS + "</style></head><body><div class='ap-bg'><i></i><i></i></div><div class='ap-prog' id='p'></div>"
      + "<div class='ap-barra'><span class='t'>Consorbens · " + esc(C.adm || "") + (cli ? " · " + esc(cli) : "") + "</span><span id='n'></span>"
      + "<button onclick='nav(-1)'>◀</button><button onclick='nav(1)'>▶</button><button onclick='fs()'>⛶ Tela cheia</button><button onclick='window.print()'>🖨️</button><button onclick='window.close()'>✕</button></div>"
      + "<div class='ap-stage' id='st'><div class='ap-fit' id='fit'></div></div><div class='ap-dots' id='dots'></div>"
      + "<script>var S=" + JSON.stringify(S).replace(/<\/script/gi, "<\\/script") + ",i=0;"
      + "function ir(k,back){i=Math.max(0,Math.min(S.length-1,k));var f=document.getElementById('fit');f.classList.toggle('back',!!back);f.innerHTML=S[i];fit();"
      + "document.getElementById('p').style.width=((i+1)/S.length*100)+'%';document.getElementById('n').textContent=(i+1)+' / '+S.length;"
      + "[].forEach.call(document.querySelectorAll('#dots button'),function(b,j){b.classList.toggle('on',j===i)});"
      + "[].forEach.call(f.querySelectorAll('img'),function(im){if(!im.complete)im.addEventListener('load',fit,{once:true})});}"
      + "function nav(k){ir(i+k,k<0)}function fit(){var st=document.getElementById('st'),f=document.getElementById('fit'),s=f.firstElementChild;if(!s)return;f.style.transform='none';"
      + "var k=Math.min((st.clientWidth-30)/s.offsetWidth,(st.clientHeight-20)/s.offsetHeight,1.6);f.style.transform='scale('+k+')';}"
      + "function fs(){var e=document.documentElement;if(!document.fullscreenElement&&e.requestFullscreen)e.requestFullscreen().catch(function(){});else if(document.exitFullscreen)document.exitFullscreen();}"
      + "document.getElementById('dots').innerHTML=S.map(function(_,j){return \"<button onclick='ir(\"+j+\",\"+j+\"<i)'></button>\"}).join('');"
      + "document.addEventListener('keydown',function(e){if(['ArrowRight','PageDown',' '].indexOf(e.key)>=0){e.preventDefault();nav(1)}else if(['ArrowLeft','PageUp'].indexOf(e.key)>=0){e.preventDefault();nav(-1)}else if(e.key==='f'||e.key==='F')fs();else if(e.key==='Escape'&&!document.fullscreenElement)window.close();});"
      + "if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit);window.addEventListener('resize',fit);ir(0);<\/script></body></html>";
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
