"""生成公开静态快照站点（GitHub Pages 用）。

从本地 SQLite 导出最新数据快照 -> site/ 目录（纯静态 HTML + JSON，相对路径）。
用法: .venv/bin/python scripts/build_static.py
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db as store
import signals as sig

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def build_snapshot() -> dict:
    quarter, items = sig.compute_consensus()
    buys = [x for x in items if x["net"] >= 2 or x["new"] >= 2][:20]
    sells = [x for x in items if x["net"] <= -2 or x["exit"] >= 2][:20]

    with store.get_db() as db:
        stats = {
            "insts": db.execute("SELECT COUNT(*) c FROM institutions WHERE category='global_13f'").fetchone()["c"],
            "changes": db.execute("SELECT COUNT(*) c FROM hchanges WHERE quarter=?", (quarter,)).fetchone()["c"],
            "alerts": db.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"],
            "news": db.execute("SELECT COUNT(*) c FROM news WHERE created_at>=datetime('now','-1 day')").fetchone()["c"],
        }
        top_changes = store.rows_to_dicts(db.execute(
            "SELECT h.issuer, h.ticker, h.change_type, h.pct, h.delta_value, h.curr_value, i.name_cn "
            "FROM hchanges h JOIN institutions i ON i.id=h.inst_id WHERE h.quarter=? "
            "ORDER BY ABS(h.delta_value) DESC LIMIT 20", (quarter,)))
        alerts = store.rows_to_dicts(db.execute(
            "SELECT ts,level,kind,title,detail FROM alerts ORDER BY id DESC LIMIT 15"))
        bb_date = db.execute("SELECT MAX(trade_date) m FROM dt_billboard").fetchone()["m"] or ""
        billboard = store.rows_to_dicts(db.execute(
            "SELECT code,name,change_rate,net_amt,buy_amt,reason FROM dt_billboard WHERE trade_date=? "
            "ORDER BY ABS(COALESCE(net_amt,0)) DESC LIMIT 15", (bb_date,)))
        hkt_rows = store.rows_to_dicts(db.execute(
            "SELECT trade_date, mutual_type, net_amt FROM hkt_flow WHERE mutual_type IN ('南向沪港股通','南向深港股通') "
            "ORDER BY trade_date DESC LIMIT 60"))
        news_matched = store.rows_to_dicts(db.execute(
            "SELECT source,title,content,published_at,url,matched FROM news WHERE matched != '[]' "
            "ORDER BY published_at DESC LIMIT 12"))
        zt_date = db.execute("SELECT MAX(date) m FROM zt_pool").fetchone()["m"] or ""
        zt = store.rows_to_dicts(db.execute(
            "SELECT code,name,lbc FROM zt_pool WHERE date=? ORDER BY lbc DESC LIMIT 10", (zt_date,)))

    for n in news_matched:
        try:
            n["matched"] = json.loads(n.get("matched") or "[]")
        except Exception:  # noqa: BLE001
            n["matched"] = []

    north = {}
    for r in hkt_rows:
        if r["mutual_type"].startswith("南向"):
            north[r["trade_date"]] = round(north.get(r["trade_date"], 0) + (r["net_amt"] or 0) / 100, 2)
    north = dict(sorted(north.items())[-40:])
    if not north:
        print("[static] 警告: 南向净买数据为空")

    return {
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "quarter": quarter,
        "stats": stats,
        "consensus_buys": buys,
        "consensus_sells": sells,
        "top_changes": top_changes,
        "alerts": alerts,
        "billboard_date": bb_date,
        "billboard": billboard,
        "south_net": north,
        "zt_date": zt_date,
        "zt": zt,
        "news_matched": news_matched,
    }


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>机构雷达 · 公开快照 | Institution Radar</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📡</text></svg>">
<style>
:root{--bg:#0a0e16;--panel:#111827;--panel2:#161f31;--border:#1f2a3d;--text:#e5eaf3;--muted:#8b98ad;--accent:#3b82f6;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;--purple:#a78bfa}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.55;padding:0 20px 60px}
header{padding:22px 0 14px;display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;border-bottom:1px solid var(--border);margin-bottom:18px}
header h1{font-size:22px}
header .sub{color:var(--muted);font-size:13px}
header .right{margin-left:auto;display:flex;gap:12px;align-items:center}
a{color:var(--accent);text-decoration:none}
.badge{background:var(--panel2);border:1px solid var(--border);border-radius:8px;padding:4px 10px;font-size:12px;color:var(--muted)}
.stat-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:18px}
@media(max-width:1000px){.stat-grid{grid-template-columns:repeat(3,1fr)}}
.stat{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:12px 14px}
.stat .v{font-size:20px;font-weight:700;margin:2px 0}
.stat .k{font-size:12px;color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px}
.panel h3{font-size:15px;margin-bottom:12px}
.panel h3 .sub{color:var(--muted);font-size:12px;font-weight:400;margin-left:8px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:1000px){.grid2{grid-template-columns:1fr}}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--muted);font-weight:500;font-size:12px;padding:7px 9px;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:7px 9px;border-bottom:1px solid rgba(31,42,61,.5);white-space:nowrap}
tr:hover td{background:rgba(59,130,246,.05)}
.num{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:var(--green)}.neg{color:var(--red)}.muted{color:var(--muted)}
.mono{font-family:Menlo,monospace;font-size:12px}
.tag{display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;border:1px solid;margin:1px 3px 1px 0}
.tag.g{color:var(--green);border-color:rgba(34,197,94,.4);background:rgba(34,197,94,.08)}
.tag.r{color:var(--red);border-color:rgba(239,68,68,.4);background:rgba(239,68,68,.08)}
.tag.p{color:var(--purple);border-color:rgba(167,139,250,.4);background:rgba(167,139,250,.08)}
.tag.y{color:var(--amber);border-color:rgba(245,158,11,.4);background:rgba(245,158,11,.08)}
.tag.n{color:var(--muted);border-color:var(--border)}
.alert-item{padding:9px 12px;border-left:3px solid var(--muted);background:var(--panel2);border-radius:8px;margin-bottom:7px}
.alert-item.critical{border-left-color:var(--red)}
.alert-item.important{border-left-color:var(--amber)}
.alert-item .t{font-weight:600;font-size:13px}
.alert-item .d{font-size:12px;color:var(--muted)}
.news-item{padding:8px 2px;border-bottom:1px solid rgba(31,42,61,.5);font-size:13px}
.news-item .meta{font-size:11px;color:var(--muted);margin-bottom:2px}
.news-item .src{color:var(--accent)}
footer{color:var(--muted);font-size:12px;text-align:center;padding:24px 0 0;border-top:1px solid var(--border)}
.chart-box{height:280px}
.empty{color:var(--muted);text-align:center;padding:24px}
</style>
</head>
<body>
<header>
  <h1>📡 机构雷达 <span style="font-size:14px;color:var(--muted)">Institution Radar</span></h1>
  <span class="sub" id="built"></span>
  <div class="right"><a class="badge" href="https://github.com/Roloria/institution-radar">⭐ GitHub 开源</a><span class="badge">数据快照 · 定期更新</span></div>
</header>
<div class="stat-grid" id="stats"></div>
<div class="panel"><h3>🎯 机构共识增持 <span class="sub" id="q-buys"></span></h3><div class="table-wrap" id="buys"></div></div>
<div class="grid2">
  <div class="panel"><h3>⚠️ 共识减持 / 清仓 <span class="sub" id="q-sells"></span></h3><div class="table-wrap" id="sells"></div></div>
  <div class="panel"><h3>🌐 最新大变动 <span class="sub" id="q-chg"></span></h3><div class="table-wrap" id="changes"></div></div>
</div>
<div class="grid2">
  <div class="panel"><h3>🔔 最新告警</h3><div id="alerts"></div></div>
  <div class="panel"><h3>⚡ 机构关键词快讯</h3><div id="news"></div></div>
</div>
<div class="grid2">
  <div class="panel"><h3>🌊 南向资金净买入（亿）</h3><div class="chart-box"><canvas id="hkt-chart"></canvas></div></div>
  <div class="panel"><h3>🇨🇳 A 股动向 <span class="sub" id="cn-meta"></span></h3><div class="table-wrap" id="cn"></div></div>
</div>
<footer id="foot"></footer>
<script src="./chart.umd.min.js"></script>
<script>
const $=(s)=>document.querySelector(s);
const esc=(s)=>(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function fmtUsd(v){if(v==null)return"-";if(Math.abs(v)>=1e12)return`$${(v/1e12).toFixed(2)}T`;if(Math.abs(v)>=1e9)return`$${(v/1e9).toFixed(2)}B`;if(Math.abs(v)>=1e8)return`$${(v/1e8).toFixed(1)}亿`;return`$${(v/1e4).toFixed(0)}万`}
function fmtNum(v,d=2){return v==null?"-":Number(v).toLocaleString("zh-CN",{maximumFractionDigits:d})}
const pctS=(p)=>p==null?"-":`<span class="${p>0?"pos":p<0?"neg":"muted"}">${p>0?"+":""}${p.toFixed(1)}%</span>`;
const amtS=(v)=>v==null?"-":`<span class="${v>0?"pos":v<0?"neg":""}">${v>0?"+":""}${fmtUsd(v)}</span>`;
const CT={"新增":"g","新进":"g","增持":"g","清仓":"r","减持":"r","退出":"r"};
const ctTag=(t)=>`<span class="tag ${CT[t]||"n"}">${esc(t)}</span>`;
function consTable(items){
  if(!items||!items.length)return'<div class="empty">暂无</div>';
  return `<table><thead><tr><th>标的</th><th class="num">净机构</th><th class="num">新增</th><th class="num">增持</th><th class="num">减持</th><th class="num">清仓</th><th class="num">合计增减</th><th>机构</th></tr></thead><tbody>${
    items.map(g=>`<tr><td><b>${esc(g.issuer)}</b>${g.tickers&&g.tickers.length?` <span class="muted mono">${g.tickers.map(esc).join("/")}</span>`:""}</td>
    <td class="num"><b class="${g.net>0?"pos":g.net<0?"neg":""}">${g.net>0?"+":""}${g.net}</b></td>
    <td class="num pos">${g.new||""}</td><td class="num pos">${g.buy-g.new||""}</td>
    <td class="num neg">${g.sell-g.exit||""}</td><td class="num neg">${g.exit||""}</td>
    <td class="num">${amtS(g.delta)}</td>
    <td style="max-width:330px;white-space:normal">${g.insts.slice(0,6).map(x=>`<span class="tag ${CT[x.change_type]||"n"}">${esc(x.name)}</span>`).join("")}</td></tr>`).join("")}</tbody></table>`;
}
fetch("./data/snapshot.json?t=__BUILD_TS__").then(r=>r.json()).then(d=>{
  $("#built").textContent = `快照生成于 ${d.built_at} · 本地实例持续自动更新`;
  $("#stats").innerHTML=`
    <div class="stat"><div class="k">跟踪机构</div><div class="v">${d.stats.insts}</div></div>
    <div class="stat"><div class="k">最新 13F 季度</div><div class="v" style="font-size:16px">${d.quarter}</div></div>
    <div class="stat"><div class="k">机构调仓条目</div><div class="v">${d.stats.changes}</div></div>
    <div class="stat"><div class="k">累计告警</div><div class="v">${d.stats.alerts}</div></div>
    <div class="stat"><div class="k">24h 快讯</div><div class="v">${d.stats.news}</div></div>
    <div class="stat"><div class="k">数据域</div><div class="v" style="font-size:15px">全球+中国</div></div>`;
  $("#q-buys").textContent=d.quarter+" · 净买入机构 ≥2";
  $("#buys").innerHTML=consTable(d.consensus_buys);
  $("#q-sells").textContent=d.quarter;
  $("#sells").innerHTML=consTable(d.consensus_sells);
  $("#q-chg").textContent=d.quarter;
  $("#changes").innerHTML=`<table><thead><tr><th>机构</th><th>标的</th><th>变动</th><th class="num">增减</th></tr></thead><tbody>${
    d.top_changes.map(c=>`<tr><td>${esc(c.name_cn)}</td><td>${esc(c.issuer)}${c.ticker?` <span class="muted mono">${esc(c.ticker)}</span>`:""}</td><td>${ctTag(c.change_type)}</td><td class="num">${amtS(c.delta_value)}</td></tr>`).join("")}</tbody></table>`;
  $("#alerts").innerHTML=d.alerts.map(a=>`<div class="alert-item ${a.level}"><div class="t">${esc(a.title)}</div><div class="d">${esc(a.detail)}</div><div class="d muted">${esc((a.ts||"").slice(0,16))}</div></div>`).join("")||'<div class="empty">暂无</div>';
  $("#news").innerHTML=d.news_matched.map(n=>`<div class="news-item"><div class="meta"><span class="src">${esc(n.source)}</span> · ${esc((n.published_at||"").slice(5,16))}</div><div>${esc((n.content||n.title).slice(0,120))}</div></div>`).join("")||'<div class="empty">暂无</div>';
  const dates=Object.keys(d.south_net), vals=dates.map(x=>d.south_net[x]);
  new Chart($("#hkt-chart"),{type:"bar",data:{labels:dates.map(x=>x.slice(5)),datasets:[{data:vals,backgroundColor:vals.map(v=>v>=0?"rgba(34,197,94,.7)":"rgba(239,68,68,.7)"),borderRadius:3}]},options:{maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#8b98ad",maxTicksLimit:10},grid:{display:false}},y:{ticks:{color:"#8b98ad"},grid:{color:"#1f2a3d"}}}}});
  $("#cn-meta").textContent=`龙虎榜 ${d.billboard_date} · 涨停 ${d.zt_date}`;
  $("#cn").innerHTML=`<table><thead><tr><th>龙虎榜净买</th><th class="num">净额(万)</th><th>连板</th></tr></thead><tbody>${
    d.billboard.slice(0,10).map((r,i)=>`<tr><td>${esc(r.name)} <span class="muted mono">${esc(r.code)}</span></td><td class="num ${(r.net_amt||0)>=0?"pos":"neg"}">${r.net_amt!=null?(r.net_amt>0?"+":"")+(r.net_amt/1e4).toFixed(0):"-"}</td><td>${d.zt[i]?`${esc(d.zt[i].name)} <span style="color:var(--red)">${d.zt[i].lbc>1?d.zt[i].lbc+"板":"首板"}</span>`:""}</td></tr>`).join("")}</tbody></table>`;
  $("#foot").innerHTML='数据来源：SEC EDGAR 13F · 东方财富 · 新浪财经｜快照为季度/日频数据的静态导出，存在披露时滞，仅供研究学习，不构成投资建议。<br><a href="https://github.com/Roloria/institution-radar">Roloria/institution-radar</a> · 本地实例含实时告警与推送';
}).catch(e=>{document.body.insertAdjacentHTML("beforeend",`<div class="empty">快照加载失败: ${e}</div>`)});
</script>
</body>
</html>
"""


def main():
    snap = build_snapshot()
    SITE.mkdir(exist_ok=True)
    (SITE / "data").mkdir(exist_ok=True)
    with open(SITE / "data" / "snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    html = HTML.replace("__BUILD_TS__", snap["built_at"].replace(":", "").replace("-", "").replace(" ", ""))
    (SITE / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(ROOT / "static" / "vendor" / "chart.umd.min.js", SITE / "chart.umd.min.js")
    size = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"[static] site/ 生成完成: snapshot {snap['built_at']}, quarter={snap['quarter']}, "
          f"共识买入 {len(snap['consensus_buys'])} / 卖出 {len(snap['consensus_sells'])}, 总大小 {size/1024:.0f}KB")


if __name__ == "__main__":
    main()
