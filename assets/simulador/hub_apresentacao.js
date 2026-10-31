/* =====================================================================
   Hub de simuladores Consorbens — camada "Apresentar ao cliente".
   Injetada pelo modulos/simuladores_hub.py ANTES do </body> de cada
   simulador (yamaha.html, itau_v2.html, itau.html). Não altera nenhuma
   conta: só lê o resultado que o simulador já mostrou na tela, clona e
   monta uma apresentação em tela cheia numa janela nova.
   Contexto em window.CBX_CTX = {sim, adm, logo, contato, grupos{}}.
   ===================================================================== */
(function () {
  var C = window.CBX_CTX || {};
  var d = document;

  // ---- onde está o resultado de cada simulador -------------------------
  function vis(el) { return !!(el && el.offsetParent !== null && (el.innerText || "").trim()); }
  function q(s) { return d.querySelector(s); }
  function qa(s) { return [].slice.call(d.querySelectorAll(s)); }
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

  // ---- utilidades -------------------------------------------------------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function pct(v) { return v == null ? "—" : (Math.round(v * 100) / 100).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 }) + "%"; }
  function clonar(el) {
    var c = el.cloneNode(true);
    // canvas (gráficos) vira imagem; campos viram texto
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
    return qa("style").map(function (s) { return s.textContent; }).join("\n")
      .replace(/body\s*\{[^}]*\}/g, ""); // o fundo do deck é nosso
  }

  // ---- slides -----------------------------------------------------------
  var LOGO = C.logo ? '<img class="cbx-logo" src="' + C.logo + '" alt="Consorbens">' : '<b class="cbx-logo-t">CONSORBENS</b>';
  function sCapa(cli) {
    var hoje = new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
    return '<div class="cbx-s cbx-capa"><div class="cbx-capa-l">' + LOGO
      + '<span class="cbx-eye">Proposta de consórcio · ' + esc(C.adm || "") + '</span>'
      + '<h1><span>' + (cli ? "Olá, " + esc(cli) + "." : "Seu plano,") + '</span><span>Seu bem com <em>planejamento</em>.</span></h1>'
      + '<p>Preparamos esta simulação para você comparar e decidir com calma.</p>'
      + '<div class="cbx-chips"><span>📅 ' + hoje + '</span><span>🏦 ' + esc(C.adm || "Consórcio") + '</span><span>🤝 Consorbens</span></div></div>'
      + '<div class="cbx-capa-r"><div class="cbx-orb"></div><div class="cbx-orb b"></div><div class="cbx-big">' + (C.sim === "yamaha" ? "🏍️" : "🚗") + '</div></div></div>';
  }
  function sComo() {
    var p = [["1", "Você entra no grupo", "Paga parcelas mensais sem juros de financiamento — só taxa de administração, fundo de reserva e seguro, quando houver."],
             ["2", "Contemplação", "Todo mês há assembleia: sorteio e lances. Com lance você aumenta suas chances de ser contemplado antes."],
             ["3", "Crédito para comprar", "Contemplado, a administradora faz a análise de crédito e libera o valor para a compra do bem."]];
    return '<div class="cbx-s cbx-como"><span class="cbx-eye">Como funciona</span><h2>Consórcio em 3 passos</h2><div class="cbx-steps">'
      + p.map(function (x, i) { return '<div class="cbx-step" style="--d:' + (i * 140) + 'ms"><b>' + x[0] + '</b><h3>' + x[1] + '</h3><p>' + x[2] + '</p></div>'; }).join("") + '</div></div>';
  }
  function sBloco(html, i, n) {
    return '<div class="cbx-s cbx-prop"><span class="cbx-eye">Sua simulação' + (n > 1 ? " · " + (i + 1) + " de " + n : "") + '</span><div class="cbx-sheet">' + html + '</div></div>';
  }
  function sGrupo(g) {
    var it = [["Média de lance", pct(g.media)], ["Menor lance que ganhou", pct(g.menor)], ["Maior lance", pct(g.maior)],
              ["Contemplados no lance livre", g.cont == null ? "—" : g.cont], ["Vagas", g.vagas == null ? "—" : g.vagas], ["Prazo", g.prazo ? g.prazo + " meses" : "—"]];
    return '<div class="cbx-s cbx-grp"><span class="cbx-eye">Por que este grupo</span><h2>Grupo ' + esc(g.g) + (g.tipo ? ' <small>' + esc(g.tipo) + '</small>' : "") + '</h2>'
      + '<div class="cbx-kp">' + it.map(function (x, i) { return '<div style="--d:' + (i * 90) + 'ms"><small>' + x[0] + '</small><b>' + x[1] + '</b></div>'; }).join("") + '</div>'
      + '<p class="cbx-note">Histórico das últimas assembleias. Lance é uma oferta: o resultado depende das ofertas de cada mês.</p></div>';
  }
  function sFim() {
    return '<div class="cbx-s cbx-fim">' + LOGO + '<h2>Próximos passos</h2><ol>'
      + '<li>Escolher a proposta e fazer a adesão à cota</li><li>Definir a estratégia de lance para as próximas assembleias</li>'
      + '<li>Contemplado: análise de crédito pela administradora e liberação do valor</li></ol>'
      + '<div class="cbx-ct">' + esc(C.contato || "") + '</div>'
      + '<p class="cbx-note">Simulação com valores aproximados, sujeita às regras e à confirmação da administradora. Não é garantia de contemplação.</p></div>';
  }

  // ---- janela de apresentação -------------------------------------------
  var DECK_CSS = "html,body{margin:0;height:100%;background:#061a17;color:#fff;font-family:'Segoe UI',Roboto,Arial,sans-serif;overflow:hidden}"
    + ".cbx-bg{position:fixed;inset:0;background:radial-gradient(900px 500px at 85% -10%,rgba(45,212,191,.28),transparent 60%),radial-gradient(700px 420px at -5% 110%,rgba(246,147,2,.2),transparent 60%),linear-gradient(140deg,#071f1c,#0b2d28 50%,#123f3e)}"
    + ".cbx-bar{position:fixed;top:0;left:0;right:0;display:flex;align-items:center;gap:12px;padding:12px 20px;z-index:3;font-size:13px;color:#a7cfc9}"
    + ".cbx-bar .t{flex:1;font-weight:700}.cbx-bar button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#fff;border-radius:999px;padding:6px 14px;font-weight:700;cursor:pointer}"
    + ".cbx-prog{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,#2dd4bf,#f69302);z-index:4;transition:width .5s}"
    + ".cbx-stage{position:fixed;inset:54px 0 46px;display:flex;align-items:center;justify-content:center}"
    + ".cbx-fit{transform-origin:center center}"
    + ".cbx-s{width:1100px;min-height:600px;box-sizing:border-box;padding:46px 60px;animation:cbxIn .6s cubic-bezier(.2,.8,.2,1) both}"
    + "@keyframes cbxIn{from{opacity:0;transform:translateX(50px)}to{opacity:1;transform:none}}"
    + ".cbx-eye{display:inline-block;font-size:13px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:#7fe9b4}"
    + ".cbx-s h2{font-size:44px;font-weight:900;letter-spacing:-.02em;margin:10px 0 26px}.cbx-s h2 small{font-size:20px;color:#a7cfc9;font-weight:700}"
    + ".cbx-logo{height:46px;background:#fff;border-radius:12px;padding:6px 12px;display:block;margin-bottom:28px}.cbx-logo-t{display:block;font-size:24px;margin-bottom:28px}"
    + ".cbx-capa{display:grid;grid-template-columns:1fr 380px;gap:30px;align-items:center}"
    + ".cbx-capa h1{font-size:62px;line-height:1.03;font-weight:900;letter-spacing:-.03em;margin:16px 0}.cbx-capa h1 span{display:block;animation:cbxUp .9s cubic-bezier(.16,1,.3,1) both}.cbx-capa h1 span+span{animation-delay:.15s}"
    + "@keyframes cbxUp{from{opacity:0;transform:translateY(40px)}to{opacity:1;transform:none}}"
    + ".cbx-capa em{font-style:normal;color:#ffb649}.cbx-capa p{font-size:20px;color:#cfe6de;margin:0 0 24px}"
    + ".cbx-chips{display:flex;gap:10px;flex-wrap:wrap}.cbx-chips span{padding:8px 16px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);font-weight:700;font-size:14px}"
    + ".cbx-capa-r{position:relative;height:420px}.cbx-orb{position:absolute;inset:30px;border-radius:50%;background:radial-gradient(circle at 30% 30%,#2dd4bf,#0f766e 60%,transparent 61%);opacity:.5;animation:cbxF 6s ease-in-out infinite}"
    + ".cbx-orb.b{inset:120px 0 0 140px;background:radial-gradient(circle at 30% 30%,#ffb649,#f69302 55%,transparent 56%);opacity:.45;animation-delay:-3s}"
    + "@keyframes cbxF{50%{transform:translateY(-14px)}}.cbx-big{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:150px;filter:drop-shadow(0 20px 30px rgba(0,0,0,.4))}"
    + ".cbx-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}.cbx-step{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:24px;padding:28px;animation:cbxUp .7s var(--d) both}"
    + ".cbx-step b{display:inline-flex;width:46px;height:46px;border-radius:50%;align-items:center;justify-content:center;background:linear-gradient(135deg,#f69302,#ffb649);color:#3b2200;font-size:22px}"
    + ".cbx-step h3{font-size:24px;margin:16px 0 8px}.cbx-step p{font-size:16.5px;line-height:1.5;color:#cfe6de;margin:0}"
    + ".cbx-prop{display:flex;flex-direction:column;align-items:center}.cbx-prop .cbx-eye{margin-bottom:16px}.cbx-prop .cbx-sheet{zoom:1.3}"
    + ".cbx-sheet{background:#fff;color:#111;border-radius:22px;padding:22px;max-width:980px;box-shadow:0 40px 80px -30px rgba(0,0,0,.7);overflow:hidden}"
    + ".cbx-kp{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.cbx-kp div{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:20px;padding:22px 24px;animation:cbxUp .6s var(--d) both}"
    + ".cbx-kp small{display:block;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#a7cfc9;font-weight:800}.cbx-kp b{display:block;font-size:40px;font-weight:900;margin-top:6px;color:#2dd4bf}"
    + ".cbx-note{font-size:14px;color:#a7cfc9;margin-top:24px}"
    + ".cbx-fim ol{font-size:24px;line-height:1.7;padding-left:28px;margin:0 0 24px}.cbx-fim li::marker{color:#ffb649;font-weight:900}"
    + ".cbx-ct{display:inline-block;font-size:22px;font-weight:800;padding:12px 22px;border-radius:999px;background:linear-gradient(135deg,#0f9d6b,#0c8a5e)}"
    + ".cbx-dots{position:fixed;bottom:16px;left:0;right:0;display:flex;justify-content:center;gap:8px;z-index:3}.cbx-dots button{width:10px;height:10px;border-radius:50%;border:0;background:rgba(255,255,255,.25);cursor:pointer;padding:0}.cbx-dots button.on{background:#ffb649;width:26px;border-radius:9px}"
    + "@media print{.cbx-bar,.cbx-dots,.cbx-prog{display:none}}";

  function abrir() {
    var B = blocos();
    if (!B.length) { alert("Gere a simulação primeiro — o modo apresentação mostra o resultado que está na tela."); return; }
    var cli = (q("#cbxCli") || {}).value || (q("#pdfCliente") || {}).value || (q("#nome") || {}).value || "";
    var htmls = B.map(clonar), txt = B.map(function (b) { return b.innerText; }).join(" ");
    var g = grupoAtual(txt);
    var S = [sCapa(cli.trim()), sComo()].concat(htmls.map(function (h, i) { return sBloco(h, i, htmls.length); }));
    if (g) S.push(sGrupo(g));
    S.push(sFim());

    var w = window.open("", "_blank");
    if (!w) { alert("O navegador bloqueou a janela da apresentação. Permita pop-ups para este site e tente de novo."); return; }
    var doc = "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'><title>Apresentação · Consorbens</title>"
      + "<style>" + estilos() + "</style><style>" + DECK_CSS + "</style></head><body><div class='cbx-bg'></div><div class='cbx-prog' id='p'></div>"
      + "<div class='cbx-bar'><span class='t'>Consorbens · " + esc(C.adm || "") + (cli ? " · " + esc(cli) : "") + "</span><span id='n'></span>"
      + "<button onclick='nav(-1)'>◀</button><button onclick='nav(1)'>▶</button><button onclick='fs()'>⛶ Tela cheia</button><button onclick='window.print()'>🖨️</button><button onclick='window.close()'>✕</button></div>"
      + "<div class='cbx-stage' id='st'><div class='cbx-fit' id='fit'></div></div><div class='cbx-dots' id='dots'></div>"
      + "<script>var S=" + JSON.stringify(S).replace(/<\/script/gi, "<\\/script") + ",i=0;"
      + "function ir(k){i=Math.max(0,Math.min(S.length-1,k));var f=document.getElementById('fit');f.innerHTML=S[i];fit();"
      + "document.getElementById('p').style.width=((i+1)/S.length*100)+'%';document.getElementById('n').textContent=(i+1)+' / '+S.length;"
      + "[].forEach.call(document.querySelectorAll('#dots button'),function(b,j){b.classList.toggle('on',j===i)});"
      + "[].forEach.call(f.querySelectorAll('img'),function(im){if(!im.complete)im.addEventListener('load',fit,{once:true})});}"
      + "function nav(k){ir(i+k)}function fit(){var st=document.getElementById('st'),f=document.getElementById('fit'),s=f.firstElementChild;if(!s)return;f.style.transform='none';"
      + "var k=Math.min((st.clientWidth-30)/s.offsetWidth,(st.clientHeight-20)/s.offsetHeight,1.6);f.style.transform='scale('+k+')';}"
      + "function fs(){var e=document.documentElement;if(!document.fullscreenElement&&e.requestFullscreen)e.requestFullscreen().catch(function(){});else if(document.exitFullscreen)document.exitFullscreen();}"
      + "document.getElementById('dots').innerHTML=S.map(function(_,j){return \"<button onclick='ir(\"+j+\")'></button>\"}).join('');"
      + "document.addEventListener('keydown',function(e){if(['ArrowRight','PageDown',' '].indexOf(e.key)>=0){e.preventDefault();nav(1)}else if(['ArrowLeft','PageUp'].indexOf(e.key)>=0){e.preventDefault();nav(-1)}else if(e.key==='f'||e.key==='F')fs();else if(e.key==='Escape'&&!document.fullscreenElement)window.close();});"
      + "window.addEventListener('resize',fit);ir(0);<\/script></body></html>";
    w.document.open(); w.document.write(doc); w.document.close();
  }
  window.cbxApresentar = abrir;

  // ---- botões ---------------------------------------------------------------
  var css = d.createElement("style");
  css.textContent = ".cbx-ribbon{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 14px;padding:10px 14px;border-radius:16px;"
    + "background:linear-gradient(135deg,#0b2d28,#17544b);color:#e6fff6;font-family:'Segoe UI',Roboto,Arial,sans-serif;font-size:13px;box-shadow:0 10px 30px -18px rgba(0,0,0,.6)}"
    + ".cbx-ribbon b{font-size:13.5px}.cbx-ribbon span{flex:1;min-width:160px;color:#a7cfc9}"
    + ".cbx-ribbon input{border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);color:#fff;border-radius:10px;padding:7px 10px;font-size:13px;min-width:190px}"
    + ".cbx-ribbon input::placeholder{color:#a7cfc9}"
    + ".cbx-btn{border:0;cursor:pointer;font-weight:800;font-size:13px;border-radius:999px;padding:9px 16px;color:#3b2200;background:linear-gradient(135deg,#f69302,#ffb649);box-shadow:0 8px 20px -10px rgba(246,147,2,.8)}"
    + ".cbx-btn:hover{filter:brightness(1.05);transform:translateY(-1px)}";
  d.head.appendChild(css);

  function botao() { var b = d.createElement("button"); b.type = "button"; b.className = "cbx-btn no-apres"; b.textContent = "🖥️ Apresentar ao cliente"; b.onclick = abrir; return b; }
  function montar() {
    var rib = d.createElement("div"); rib.className = "cbx-ribbon no-apres";
    rib.innerHTML = "<b>🖥️ Modo apresentação</b><span>Gere a simulação e apresente o resultado ao cliente em tela cheia.</span>"
      + "<input id='cbxCli' placeholder='Nome do cliente (opcional)'>";
    rib.appendChild(botao());
    var alvo = q(".container") || q("#containerPrincipal") || d.body.firstElementChild;
    if (alvo && alvo.parentNode) alvo.parentNode.insertBefore(rib, alvo); else d.body.insertBefore(rib, d.body.firstChild);
    // ao lado das ações que cada simulador já tem
    var acoes = C.sim === "yamaha" ? qa("#resumoAcoes, #resumoAcoesEstr") : C.sim === "itau_ia" ? qa(".actions") : [];
    acoes.forEach(function (a) { a.appendChild(botao()); });
    if (C.sim === "itau_manual") ["#resultado", "#resumoEstruturadoBox"].forEach(function (s) {
      var e = q(s); if (e) { var w = d.createElement("div"); w.className = "no-apres"; w.style.cssText = "margin:12px 0;text-align:center"; w.appendChild(botao()); e.parentNode.insertBefore(w, e.nextSibling); }
    });
  }
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", montar); else montar();
})();
