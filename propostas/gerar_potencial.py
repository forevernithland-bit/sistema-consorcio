"""Tela "Potencial de contemplação" para o CLIENTE FINAL (Itaú e Yamaha).

Uso:  py -V:3.14 gerar_potencial.py <config.json>
config.json = lista de cenários, cada um:
  {"adm": "Itaú"|"Yamaha", "grupo": 20601, "bem": "Automóvel", "credito": 128779, "cotas_txt": "2 cotas: R$ 53.658 + R$ 75.121",
   "liquido": 90145.30, "proprio": 45000, "embutido": 38633.70, "lance_pct": 64.94, "prox": "24/11/2026",
   "saida": "C:/.../Potencial-Itau-20601-A.png"}
Histórico carregado sozinho (últimos 12 meses com lance livre):
  Itaú   -> planilha mais recente "*Planilha Lance*.xlsb" (aba Base) em G:/Meu Drive/CONSORBENS/Tabelas/ITAU
  Yamaha -> tabela yamaha_assembleias do ERP Consorbens (se faltar mês, rodar o robô coletar_assembleias.py antes)
Regra: "teria sido contemplado" = lance do cliente >= menor lance livre vencedor do mês.
Regra de marketing: nunca "sem análise"/"crédito na hora"; crédito sempre sujeito à análise da administradora.
"""
import base64, datetime, glob, json, math, os, pathlib, sys

ERP = r"G:\Meu Drive\CLODE\ERP_CONSORBENS"
MES = "jan fev mar abr mai jun jul ago set out nov dez".split()
br = lambda v, d=2: "R$ " + f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
pc = lambda v, d=1: f"{v:.{d}f}".replace(".", ",") + "%"


def hist_itau(grupo):
    from pyxlsb import open_workbook
    arqs = sorted(glob.glob(r"G:\Meu Drive\CONSORBENS\Tabelas\ITAU\*Planilha Lance*.xlsb"))
    arq = arqs[-1]; rows = {}
    with open_workbook(arq) as w, w.get_sheet("Base") as sh:
        for row in sh.rows():
            v = [c.v for c in row]
            try: g = int(v[0])
            except Exception: continue
            if g == int(grupo) and v[4] and (v[1] or 0) > 0:
                d = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v[4]))
                rows[d] = dict(d=d, mn=float(v[2]), mx=float(v[3]), ll=int(v[1]), lf=int(v[8] or 0))
    fonte = "Planilha de Lance Itaú de " + os.path.basename(arq)[6:8] + "/" + os.path.basename(arq)[4:6] + "/" + os.path.basename(arq)[:4]
    return [rows[k] for k in sorted(rows)][-12:], fonte


def hist_yamaha(grupo):
    sys.path.insert(0, r"C:\Users\desta\.claude\skills\erp-consorbens\scripts")
    import erp
    r = erp.sb().table("yamaha_assembleias").select("*").eq("grupo", str(grupo)).execute().data
    out = []
    for x in r:
        if not x.get("lance_livre_min"): continue
        out.append(dict(d=datetime.date.fromisoformat(x["data_assembleia"]), mn=float(x["lance_livre_min"]), mx=float(x["lance_livre_max"]),
                        ll=int(x.get("n_lance_livre") or 0), lf=int(x.get("n_lance_fixo") or 0), tot=int(x.get("n_total") or 0)))
    out.sort(key=lambda o: o["d"])
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    return out[-12:], f"resultados das assembleias Yamaha (Newcon), consultados até {hoje}"


def grafico(H, lance):
    W, Hh, ml, mr, mt, mb = 792, 300, 46, 120, 26, 40
    lo = math.floor((min(min(r["mn"] for r in H), lance) - 4) / 10) * 10
    hi = math.ceil((max(max(r["mx"] for r in H), lance) + 3) / 10) * 10
    X = lambda i: ml + (i + .5) * (W - ml - mr) / len(H)
    Y = lambda v: mt + (hi - v) * (Hh - mt - mb) / (hi - lo)
    s = f'<svg viewBox="0 0 {W} {Hh}" width="{W}" height="{Hh}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI,Arial">'
    for v in range(lo, hi + 1, 10):
        s += f'<line x1="{ml}" x2="{W-mr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e6eeed"/><text x="{ml-8}" y="{Y(v)+4:.1f}" text-anchor="end" font-size="12" fill="#7a8a99">{v}%</text>'
    bw = min(34, (W - ml - mr) / len(H) * .5)
    for i, r in enumerate(H):
        ok = lance >= r["mn"]; x = X(i)
        col = "#12a66f" if ok else "#c9d3d2"
        s += f'<rect x="{x-bw/2:.1f}" y="{Y(r["mx"]):.1f}" width="{bw:.1f}" height="{max(Y(r["mn"])-Y(r["mx"]),3):.1f}" rx="6" fill="{col}"/>'
        s += f'<text x="{x:.1f}" y="{Y(r["mn"])+15:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="{"#0b7a51" if ok else "#8a9696"}">{r["mn"]:.0f}%</text>'
        s += f'<text x="{x:.1f}" y="{Hh-mb+20}" text-anchor="middle" font-size="12" fill="#5b6b80">{MES[r["d"].month-1]}/{r["d"].year%100:02d}</text>'
    y = Y(lance)
    s += f'<line x1="{ml}" x2="{W-mr}" y1="{y:.1f}" y2="{y:.1f}" stroke="#0f3735" stroke-width="2.6" stroke-dasharray="8 6"/>'
    s += (f'<rect x="{W-mr+6}" y="{y-21:.1f}" width="{mr-8}" height="42" rx="12" fill="#0f3735"/>'
          f'<text x="{W-mr+6+(mr-8)/2:.1f}" y="{y-4:.1f}" text-anchor="middle" font-size="11.5" fill="#cfe3e0">Seu lance</text>'
          f'<text x="{W-mr+6+(mr-8)/2:.1f}" y="{y+13:.1f}" text-anchor="middle" font-size="15" font-weight="800" fill="#fff">{pc(lance)}</text>')
    return s + "</svg>"


CSS = """*{box-sizing:border-box}body{margin:0;background:#eef3f2;font-family:'Segoe UI',Arial,sans-serif;color:#15302f}
#r{width:860px;background:#fff;overflow:hidden}
.hd{background:linear-gradient(135deg,#0f3735 0%,#1b5e59 100%);color:#fff;padding:26px 34px 86px;position:relative}
.hd .top{display:flex;justify-content:space-between;align-items:center}.logo{background:#fff;border-radius:14px;padding:8px 14px;height:58px}.logo img{height:42px}
.tag{font-size:12.5px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;background:rgba(255,255,255,.14);padding:7px 14px;border-radius:30px}
.hd h1{font-size:34px;margin:22px 0 4px;letter-spacing:-.4px}.hd .sub{font-size:16px;opacity:.9}
.hero{margin:-62px 26px 0;background:#fff;border-radius:22px;box-shadow:0 14px 38px rgba(15,55,53,.18);padding:24px 28px;display:flex;gap:26px;align-items:center;position:relative}
.dn{position:relative;width:150px;height:150px;flex:none}.dn .v{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.dn .v b{font-size:38px;line-height:1;font-weight:900}.dn .v span{font-size:12px;color:#5b6b80;margin-top:4px;font-weight:600}
.badge{display:inline-block;font-weight:800;font-size:13px;letter-spacing:.8px;text-transform:uppercase;padding:6px 13px;border-radius:30px;margin-bottom:8px}
.hero h2{margin:0 0 8px;font-size:22px;line-height:1.3}.hero p{margin:0;color:#4b5d6b;font-size:15px;line-height:1.5}
.sec{padding:22px 34px 0}.sec h3{font-size:18px;margin:0 0 4px}.sec .lg{font-size:13.5px;color:#5b6b80;margin-bottom:12px}
.ln{display:flex;align-items:stretch;gap:10px}.ln .b{flex:1;border-radius:16px;padding:14px 16px;background:#f3f7f6}.ln .b span{display:block;font-size:12.5px;color:#5b6b80;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.ln .b b{display:block;font-size:22px;margin-top:4px}.ln .b small{font-size:12.5px;color:#5b6b80}.ln .op{align-self:center;font-size:26px;font-weight:900;color:#9fb1af}
.ln .b.t{background:#0f3735;color:#fff}.ln .b.t span,.ln .b.t small{color:#cfe3e0}
.mh{margin-top:12px;display:flex;gap:10px}.mh .b{flex:1;border:2px solid #12a66f;border-radius:16px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center}
.mh .b span{font-size:14px;color:#3d5260;font-weight:600}.mh .b b{font-size:22px;color:#0b7a51}
.chips{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}.ch{border-radius:14px;padding:10px 6px;text-align:center}
.ch.ok{background:#e4f6ee;color:#0b7a51}.ch.no{background:#f1f3f3;color:#8a9696}.ch .m{font-size:13px;font-weight:700;text-transform:uppercase}.ch .i{font-size:22px;font-weight:900;line-height:1.3}.ch .p{font-size:11.5px}
.facts{display:flex;gap:10px}.facts .f{flex:1;background:#f3f7f6;border-radius:16px;padding:12px 14px}.facts .f span{font-size:12px;color:#5b6b80;font-weight:700;text-transform:uppercase;letter-spacing:.4px}.facts .f b{display:block;font-size:19px;margin-top:3px}
.tip{margin:18px 34px 0;background:#fff7e3;border:1.5px solid #f0cf7a;border-radius:16px;padding:14px 18px;font-size:14.5px;line-height:1.5;color:#5c4511}.tip b{color:#3d2e08}
.how{margin:18px 34px 0;font-size:14px;color:#3d5260;line-height:1.6;background:#f3f7f6;border-radius:16px;padding:14px 18px}
.ft{margin-top:20px;background:#0f3735;color:#cfe3e0;font-size:12px;line-height:1.55;padding:16px 34px}.ft b{color:#fff}"""


def tela(c):
    H, fonte = (hist_itau if c["adm"].lower().startswith("ita") else hist_yamaha)(c["grupo"])
    # "extra": meses mais novos que a planilha (ex.: Lance mín./máx./Contemp. do portal Itaú 360i), [{"d":"2026-11-10","mn":61.07,"mx":77.67,"ll":75}]
    if c.get("extra"):
        tem = {(r["d"].year, r["d"].month) for r in H}
        for e in c["extra"]:
            d = datetime.date.fromisoformat(e["d"])
            if (d.year, d.month) not in tem: H.append(dict(d=d, mn=float(e["mn"]), mx=float(e["mx"]), ll=int(e.get("ll", 0)), lf=0))
        H = sorted(H, key=lambda r: r["d"])[-12:]
        fonte += " e portal Itaú 360i (" + c.get("extra_fonte", "último resultado") + ")"
    if len(H) < 3: raise SystemExit(f"Grupo {c['grupo']}: histórico insuficiente ({len(H)} meses) -> rodar o robô de assembleias antes")
    L = c["lance_pct"]; N = len(H); hits = sum(L >= r["mn"] for r in H); taxa = hits / N
    nivel, cor, fundo = (("Potencial alto", "#0b7a51", "#e4f6ee") if taxa >= .75 else
                         ("Potencial moderado", "#9a6a00", "#fff3d6") if taxa >= .4 else ("Potencial baixo", "#a33a17", "#fde7df"))
    R = 62; circ = 2 * math.pi * R
    dn = (f'<svg width="150" height="150" viewBox="0 0 150 150"><circle cx="75" cy="75" r="{R}" fill="none" stroke="#e8eeee" stroke-width="15"/>'
          f'<circle cx="75" cy="75" r="{R}" fill="none" stroke="{cor}" stroke-width="15" stroke-linecap="round" stroke-dasharray="{circ*taxa:.1f} {circ:.1f}" transform="rotate(-90 75 75)"/></svg>')
    frase = (f"Nas últimas {N} assembleias, um lance igual ao seu teria sido contemplado <b>todas as vezes</b>." if hits == N else
             f"Em <b>{hits} das últimas {N}</b> assembleias, um lance igual ao seu teria sido contemplado.")
    maxmin = max(r["mn"] for r in H); folga = L - maxmin
    chips = "".join(f'<div class="ch {"ok" if L >= r["mn"] else "no"}"><div class="m">{MES[r["d"].month-1]}/{r["d"].year%100:02d}</div>'
                    f'<div class="i">{"✓" if L >= r["mn"] else "✗"}</div><div class="p">ganhou com {pc(r["mn"])}</div></div>' for r in H)
    lls = [r["ll"] for r in H if r["ll"]] or [0]; ultimo = H[-1]
    tip = ""
    if hits < N:
        base = (c["proprio"] + c["embutido"]) / (L / 100); alvo = math.ceil((maxmin + .05) * 10) / 10
        extra = math.ceil((alvo / 100 * base - c["embutido"] - c["proprio"]) / 100) * 100
        tip = (f'<div class="tip"><b>Quer aumentar a chance?</b> Para ter entrado em todos os {N} meses, o lance precisaria chegar a {pc(alvo)}: '
               f'cerca de <b>{br(extra, 0)} a mais do seu bolso</b> (total do bolso ≈ {br(c["proprio"] + extra, 0)}). Lance maior também deixa a parcela depois da contemplação menor.</div>')
    seg = (f'Seu lance ficou <b>{abs(folga):.1f} pontos {"acima" if folga >= 0 else "abaixo"}</b> do maior "menor lance vencedor" do período.').replace(".", ",", 1)
    logo = "data:image/png;base64," + base64.b64encode(open(os.path.join(ERP, "logo.png"), "rb").read()).decode()
    adm_nome = "Itaú Consórcio" if c["adm"].lower().startswith("ita") else "Consórcio Yamaha"
    html = f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style><div id="r">
<div class="hd"><div class="top"><div class="logo"><img src="{logo}"></div><div class="tag">Próxima assembleia · {c['prox']}</div></div>
<h1>Potencial de contemplação</h1><div class="sub">{adm_nome} · Grupo {c['grupo']} · {c.get('bem','Automóvel')} · {c.get('cotas_txt','')}</div></div>
<div class="hero"><div class="dn">{dn}<div class="v"><b style="color:{cor}">{taxa*100:.0f}%</b><span>{hits} de {N} meses</span></div></div>
<div><span class="badge" style="color:{cor};background:{fundo}">{nivel}</span><h2>{frase}</h2><p>{seg} Base: lances que de fato contemplaram neste grupo, mês a mês.</p></div></div>
<div class="sec"><h3>O seu lance</h3><div class="lg">O embutido sai da própria carta: você não tira esse valor do bolso.</div>
<div class="ln"><div class="b"><span>Do seu bolso</span><b>{br(c['proprio'],0)}</b></div><div class="op">+</div>
<div class="b"><span>Embutido da carta</span><b>{br(c['embutido'],0)}</b></div><div class="op">=</div>
<div class="b t"><span>Lance total</span><b>{br(c['proprio']+c['embutido'],0)}</b><small>{pc(L)} do plano</small></div></div>
<div class="mh"><div class="b"><span>Crédito contratado</span><b style="color:#15302f">{br(c['credito'],0)}</b></div><div class="b"><span>Fica na sua mão (≈)</span><b>{br(c['liquido'],0)}</b></div></div></div>
<div class="sec"><h3>Mês a mês: seu lance teria ganhado?</h3><div class="lg">✓ = seu lance era maior que o menor lance que foi contemplado naquele mês.</div><div class="chips">{chips}</div></div>
<div class="sec"><h3>Seu lance x lances que ganharam</h3><div class="lg">Cada barra vai do menor ao maior lance contemplado no mês. Verde: o seu lance (linha tracejada) estava dentro.</div>{grafico(H, L)}</div>
<div class="sec"><div class="facts"><div class="f"><span>Contemplados por lance livre</span><b>{min(lls)} a {max(lls)} por mês</b></div>
<div class="f"><span>Menor lance vencedor ({MES[ultimo['d'].month-1]}/{ultimo['d'].year%100:02d})</span><b>{pc(ultimo['mn'])}</b></div>
<div class="f"><span>Próxima assembleia</span><b>{c['prox']}</b></div></div></div>{tip}
<div class="how"><b>Como funciona:</b> todo mês o grupo contempla quem oferece os maiores lances. Quando o seu lance é maior que o menor lance vencedor do mês, você está entre os contemplados. Ofertamos o seu lance todo mês até a contemplação.</div>
<div class="ft"><b>Estimativa com base no histórico real do grupo, não é garantia de contemplação</b>: o resultado depende dos lances ofertados em cada assembleia. Após a contemplação, a liberação do crédito passa pela análise da administradora. Fonte: {fonte}. Consorbens · consorbens.com.br</div></div>"""
    h = c["saida"][:-4] + ".html"; open(h, "w", encoding="utf-8").write(html)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 860, "height": 1200}, device_scale_factor=2)
        pg.goto(pathlib.Path(h).as_uri(), wait_until="networkidle"); pg.locator("#r").screenshot(path=c["saida"]); b.close()
    print(f"{c['adm']} {c['grupo']}: {hits}/{N} ({taxa:.0%}) lance {L}% folga {folga:+.2f} -> {c['saida']}")


if __name__ == "__main__":
    for c in json.load(open(sys.argv[1], encoding="utf-8")): tela(c)
