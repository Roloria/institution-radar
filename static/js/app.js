/* 机构雷达 前端逻辑 */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

/* ---------- 格式化 ---------- */
function fmtUsd(v) { // v 美元
  if (v == null) return "-";
  if (Math.abs(v) >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e8) return `$${(v / 1e8).toFixed(1)}亿`;
  if (Math.abs(v) >= 1e4) return `$${(v / 1e4).toFixed(0)}万`;
  return `$${v.toFixed(0)}`;
}
function fmtNum(v, digits = 2) {
  if (v == null) return "-";
  return Number(v).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}
function fmtYi(v) { // 百万元 -> 亿元
  if (v == null) return "-";
  return (v / 100).toFixed(2);
}
function timeAgo(ts) {
  if (!ts) return "";
  const s = (Date.now() - new Date(ts.replace(" ", "T")) / 1) / 1000;
  if (isNaN(s)) return ts;
  if (s < 60) return "刚刚";
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`;
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`;
  return `${Math.floor(s / 86400)} 天前`;
}
const esc = (s) => (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function changeTag(t) {
  const map = { "新增": ["g", "🆕"], "新进": ["g", "🆕"], "增持": ["g", "▲"], "清仓": ["r", "❌"], "减持": ["r", "▼"], "退出": ["r", "▼"], "不变": ["n", "—"] };
  const [c, i] = map[t] || ["n", ""];
  return `<span class="tag ${c}">${i} ${esc(t)}</span>`;
}
function pctSpan(p) {
  if (p == null) return '<span class="muted">-</span>';
  const cls = p > 0 ? "pos" : p < 0 ? "neg" : "muted";
  return `<span class="${cls}">${p > 0 ? "+" : ""}${p.toFixed(1)}%</span>`;
}
function amtSpan(v) {
  if (v == null) return '<span class="muted">-</span>';
  const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
  return `<span class="${cls}">${v > 0 ? "+" : ""}${fmtNum(v)}</span>`;
}

/* ---------- 路由 ---------- */
const PAGES = {
  overview: { title: "概览", load: loadOverview },
  global: { title: "全球 13F 持仓", load: loadGlobal },
  signals: { title: "共识信号", load: loadSignals },
  domestic: { title: "国内机构动向", load: loadDomestic },
  news: { title: "7×24 快讯", load: loadNewsPage },
  alerts: { title: "告警中心", load: loadAlertsPage },
  settings: { title: "数据源与设置", load: loadSettings },
};
function route() {
  const name = (location.hash.replace("#/", "") || "overview").split("?")[0];
  const page = PAGES[name] || PAGES.overview;
  $$(".page").forEach((p) => (p.hidden = true));
  $(`#page-${name}`)?.removeAttribute("hidden");
  $$("#menu a").forEach((a) => a.classList.toggle("active", a.dataset.page === name));
  $("#page-title").textContent = page.title;
  page.load().catch((e) => console.error(e));
}
window.addEventListener("hashchange", route);

/* ---------- 概览 ---------- */
async function loadOverview() {
  const d = await api("/api/summary");
  $("#ov-quarter").textContent = d.quarter || "";
  $("#stat-grid").innerHTML = `
    <div class="stat"><div class="k">跟踪机构</div><div class="v">${d.followed}<span class="muted" style="font-size:13px">/${d.insts}</span></div><div class="d">13F 全球机构</div></div>
    <div class="stat"><div class="k">最新季报</div><div class="v" style="font-size:17px">${d.quarter || "抓取中…"}</div><div class="d">持仓变动 ${d.changes} 条</div></div>
    <div class="stat"><div class="k">24h 快讯</div><div class="v">${d.news_24h}</div><div class="d">东财 + 新浪</div></div>
    <div class="stat"><div class="k">24h 告警</div><div class="v ${d.alerts_24h > 0 ? "up" : ""}">${d.alerts_24h}</div><div class="d">待您关注</div></div>
    <div class="stat"><div class="k">今日涨停</div><div class="v">${d.zt_today}</div><div class="d">A股涨停池</div></div>
    <div class="stat"><div class="k">龙虎榜</div><div class="v" style="font-size:17px">${d.billboard_dates[0]?.trade_date?.slice(5) || "—"}</div><div class="d">${d.billboard_dates[0]?.n || 0} 只上榜</div></div>`;

  $("#ov-alerts").innerHTML = d.alerts.length
    ? d.alerts.map(alertItem).join("")
    : `<div class="empty">暂无告警 — 数据抓取完成后这里会出现机构异动提醒</div>`;
  $("#ov-changes").innerHTML = d.top_changes.length ? `<table><thead><tr><th>机构</th><th>标的</th><th>变动</th><th class="num">市值</th><th class="num">增减</th></tr></thead><tbody>${
    d.top_changes.map((c) => `<tr><td>${esc(c.name_cn || c.inst_name)}</td><td class="mono">${esc(c.issuer || c.ticker)}${c.ticker ? ` <span class="muted">${esc(c.ticker)}</span>` : ""}</td><td>${changeTag(c.change_type)}</td><td class="num">${fmtUsd(Math.max(c.curr_value, c.prev_value))}</td><td class="num">${amtSpan(c.delta_value ? (c.delta_value > 0 ? 1 : -1) * Math.abs(c.delta_value) : 0)}</td></tr>`).join("")
    }</tbody></table>` : `<div class="empty">13F 数据抓取中，请稍候…</div>`;
  $("#ov-news").innerHTML = d.news_matched.length
    ? d.news_matched.map(newsItem).join("")
    : `<div class="empty">暂无机构关键词命中的快讯</div>`;
  $("#ov-sources").innerHTML = d.sources.map((s) => {
    const dot = s.last_status === "ok" ? "ok" : s.last_status === "fail" ? "fail" : "never";
    return `<div class="srow"><span class="dot ${dot}"></span><span style="width:170px">${esc(s.name)}</span><span class="muted">${s.last_run ? timeAgo(s.last_run) : "未运行"}</span></div>`;
  }).join("");
}

/* ---------- 全球 13F ---------- */
const G = { instId: null, insts: [], tab: "changes", ctype: "", quarter: "", chart: null };

async function loadGlobal() {
  if (!G.loaded) {
    G.insts = await api("/api/institutions");
    G.insts = G.insts.filter((i) => i.category === "global_13f");
    G.instId = G.instId || (G.insts.find((i) => i.followed) || G.insts[0])?.id;
    renderInstList();
    G.loaded = true;
  }
  await loadInstData();
}
function renderInstList() {
  const kw = $("#inst-search").value.trim().toLowerCase();
  const list = G.insts.filter((i) => !kw || `${i.name}${i.name_cn}${i.note}`.toLowerCase().includes(kw));
  $("#inst-list").innerHTML = list.map((i) => `
    <div class="inst-item ${i.id === G.instId ? "active" : ""}" data-id="${i.id}">
      <div class="nm" onclick="selectInst(${i.id})"><b>${esc(i.name_cn || i.name)}</b><span>${esc(i.name)} · ${esc(i.note || "")}</span></div>
      <span class="follow ${i.followed ? "on" : ""}" onclick="toggleFollow(${i.id})" title="关注后才会推送提醒">${i.followed ? "★" : "☆"}</span>
    </div>`).join("") || `<div class="empty">无匹配</div>`;
}
window.selectInst = (id) => { G.instId = id; renderInstList(); loadInstData(); };
window.toggleFollow = async (id) => {
  await post(`/api/institutions/${id}/follow`);
  const i = G.insts.find((x) => x.id === id);
  i.followed = 1 - i.followed;
  renderInstList();
};
$("#inst-search").addEventListener("input", renderInstList);

async function loadInstData() {
  const inst = G.insts.find((i) => i.id === G.instId);
  if (!inst) return;
  const [quarters, changes] = await Promise.all([
    api(`/api/quarters?inst_id=${G.instId}`),
    api(`/api/holdings/changes?inst_id=${G.instId}&limit=2000`),
  ]);
  const latest = quarters[0] || "";
  const instRows = await api(`/api/holdings/changes?inst_id=${G.instId}&quarter=${latest}&limit=2000`);
  const total = instRows.filter((r) => r.curr_value > 0).reduce((s, r) => s + r.curr_value, 0);
  const nNew = instRows.filter((r) => r.change_type === "新增").length;
  const nExit = instRows.filter((r) => r.change_type === "清仓").length;
  $("#inst-head").innerHTML = `
    <div class="inst-head">
      <div><div class="big">${esc(inst.name_cn || inst.name)}</div><div class="muted" style="font-size:12px">${esc(inst.name)} · ${esc(inst.note || "")}</div></div>
      <div class="cell"><div class="k">最新季度</div><div class="v">${latest || "—"}</div></div>
      <div class="cell"><div class="k">组合市值</div><div class="v">${fmtUsd(total)}</div></div>
      <div class="cell"><div class="k">持仓标的</div><div class="v">${instRows.filter((r) => r.curr_value > 0).length}</div></div>
      <div class="cell"><div class="k">新增 / 清仓</div><div class="v"><span class="pos">${nNew}</span> / <span class="neg">${nExit}</span></div></div>
    </div>`;
  G.quarters = quarters;
  G.changes = changes;
  G.quarter = G.quarter && quarters.includes(G.quarter) ? G.quarter : latest;
  $("#quarter-sel").innerHTML = quarters.map((q) => `<option ${q === G.quarter ? "selected" : ""}>${q}</option>`).join("");
  renderChangeSeg();
  renderChanges();
  if (G.tab === "changes") renderChgChart();
}
function renderChangeSeg() {
  $$("#change-seg .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.t === G.ctype));
}
$("#change-seg").addEventListener("click", (e) => {
  const b = e.target.closest(".seg-btn");
  if (!b) return;
  G.ctype = b.dataset.t;
  renderChangeSeg();
  renderChanges();
  renderChgChart();
});
$("#quarter-sel").addEventListener("change", (e) => { G.quarter = e.target.value; renderChanges(); renderChgChart(); });
$("#chg-search").addEventListener("input", renderChanges);

function filteredChanges() {
  const kw = $("#chg-search").value.trim().toLowerCase();
  return G.changes.filter((r) =>
    (!G.ctype || r.change_type === G.ctype) &&
    (!G.quarter || r.quarter === G.quarter) &&
    (!kw || `${r.issuer}${r.ticker}`.toLowerCase().includes(kw)));
}
function renderChanges() {
  const rows = filteredChanges();
  $("#chg-table").innerHTML = `<table><thead><tr><th>标的</th><th>变动</th><th class="num">变动幅度</th><th class="num">上期市值</th><th class="num">本期市值</th><th class="num">增减市值</th><th class="num">上期股数</th><th class="num">本期股数</th></tr></thead><tbody>${
    rows.map((r) => `<tr>
      <td><b>${esc(r.issuer || r.ticker || r.cusip)}</b>${r.ticker ? ` <span class="muted mono">${esc(r.ticker)}</span>` : ""}</td>
      <td>${changeTag(r.change_type)}</td>
      <td class="num">${pctSpan(r.pct)}</td>
      <td class="num muted">${r.prev_value ? fmtUsd(r.prev_value) : "—"}</td>
      <td class="num">${r.curr_value ? fmtUsd(r.curr_value) : "—"}</td>
      <td class="num">${amtSpan(r.delta_value ? (r.delta_value > 0 ? 1 : -1) * Math.abs(r.delta_value) : null)}</td>
      <td class="num muted">${r.shares_prev ? fmtNum(r.shares_prev, 0) : "—"}</td>
      <td class="num">${r.shares_curr ? fmtNum(r.shares_curr, 0) : "—"}</td>
    </tr>`).join("") || `<tr><td colspan="8" class="empty">无数据</td></tr>`}</tbody></table>`;
  $("#chg-export").onclick = () => exportCsv(`13F变动_${G.quarter}.csv`, ["issuer", "ticker", "change_type", "pct", "prev_value", "curr_value", "delta_value", "shares_prev", "shares_curr"], rows);
}
function renderChgChart() {
  const rows = filteredChanges().filter((r) => r.curr_value > 0).sort((a, b) => b.curr_value - a.curr_value).slice(0, 12).reverse();
  const ctx = $("#chg-chart");
  if (G.chart) G.chart.destroy();
  G.chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.issuer || r.ticker),
      datasets: [{
        label: "本期市值",
        data: rows.map((r) => +(r.curr_value / 1e9).toFixed(2)),
        backgroundColor: rows.map((r) => r.change_type === "新增" ? "rgba(34,197,94,.7)" : r.change_type === "减持" ? "rgba(239,68,68,.65)" : r.change_type === "清仓" ? "rgba(239,68,68,.4)" : "rgba(59,130,246,.65)"),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y", maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` $${c.raw}B (${c.raw.change_type || ""})` } } },
      scales: { x: { ticks: { color: "#8b98ad" }, grid: { color: "#1f2a3d" }, title: { display: true, text: "亿美元市值 (B USD)", color: "#8b98ad" } }, y: { ticks: { color: "#c9d3e4", font: { size: 11 } }, grid: { display: false } } },
    },
  });
}
$("#hold-tabs").addEventListener("click", async (e) => {
  const b = e.target.closest(".tab");
  if (!b) return;
  $$("#hold-tabs .tab").forEach((t) => t.classList.toggle("active", t === b));
  G.tab = b.dataset.tab;
  $("#tab-changes").hidden = G.tab !== "changes";
  $("#tab-current").hidden = G.tab !== "current";
  if (G.tab === "current") await renderCurrent();
});
$("#cur-search").addEventListener("input", renderCurrent);

async function renderCurrent() {
  const kw = $("#cur-search").value.trim();
  const d = await api(`/api/holdings/current?inst_id=${G.instId}&q=${encodeURIComponent(kw)}`);
  const total = d.rows.reduce((s, r) => s + r.value_usd, 0) || 1;
  $("#cur-meta").textContent = `${d.quarter} · ${d.rows.length} 笔 · ${fmtUsd(total)}`;
  $("#cur-table").innerHTML = `<table><thead><tr><th>#</th><th>标的</th><th>类别</th><th class="num">市值</th><th class="num">占比</th><th class="num">股数</th><th>类型</th></tr></thead><tbody>${
    d.rows.map((r, i) => `<tr>
      <td class="muted">${i + 1}</td>
      <td><b>${esc(r.issuer)}</b>${r.ticker ? ` <span class="muted mono">${esc(r.ticker)}</span>` : ""}</td>
      <td class="muted">${esc(r.class || "-")}</td>
      <td class="num">${fmtUsd(r.value_usd)}</td>
      <td class="num">${(r.value_usd / total * 100).toFixed(1)}%</td>
      <td class="num">${fmtNum(r.shares, 0)}</td>
      <td>${r.put_call ? `<span class="tag y">${esc(r.put_call)}</span>` : '<span class="tag n">股票</span>'}</td>
    </tr>`).join("") || `<tr><td colspan="7" class="empty">无数据</td></tr>`}</tbody></table>`;
}

function exportCsv(name, cols, rows) {
  if (!rows.length) return alert("无数据可导出");
  if (!cols.length) cols = Object.keys(rows[0]).filter((k) => typeof rows[0][k] !== "object");
  const csv = "\ufeff" + [cols.join(","), ...rows.map((r) => cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = name;
  a.click();
}


/* ---------- 共识信号 ---------- */
function consensusTable(items, kind) {
  if (!items.length) return `<div class="empty">本季度暂无${kind}共识</div>`;
  return `<table><thead><tr><th>标的</th><th class="num">净机构</th><th class="num">新增</th><th class="num">增持</th><th class="num">减持</th><th class="num">清仓</th><th class="num">合计增减</th><th>机构明细</th></tr></thead><tbody>${
    items.map((g) => `<tr>
      <td><b>${esc(g.issuer)}</b>${g.tickers.length ? ` <span class="muted mono">${g.tickers.map(esc).join("/")}</span>` : ""}</td>
      <td class="num"><b class="${g.net > 0 ? "pos" : g.net < 0 ? "neg" : ""}">${g.net > 0 ? "+" : ""}${g.net}</b></td>
      <td class="num pos">${g.new || ""}</td>
      <td class="num pos">${g.buy - g.new || ""}</td>
      <td class="num neg">${g.sell - g.exit || ""}</td>
      <td class="num neg">${g.exit || ""}</td>
      <td class="num">${amtSpan(g.delta)}</td>
      <td style="max-width:420px;white-space:normal">${g.insts.slice(0, 8).map((x) => `<span class="tag ${x.change_type === "新增" || x.change_type === "增持" ? "g" : x.change_type === "清仓" || x.change_type === "减持" ? "r" : "n"}" title="${x.change_type} ${fmtUsd(x.value)}">${esc(x.name)}${x.pct != null ? " " + (x.pct > 0 ? "+" : "") + x.pct.toFixed(0) + "%" : ""}</span>`).join("")}</td>
    </tr>`).join("")}</tbody></table>`;
}
async function loadSignals() {
  const d = await api("/api/consensus");
  d.buys = d.buys.slice(0, 25);
  d.sells = d.sells.slice(0, 12);
  $("#sig-quarter").textContent = d.quarter + ` · 全部 ${d.n_all} 只标的出现机构调仓`;
  $("#sig-buys").innerHTML = consensusTable(d.buys, "买入");
  $("#sig-sells").innerHTML = consensusTable(d.sells, "卖出");
  renderStockView();

  // A 股今日关注：北向近5日 + 龙虎榜净买Top + 连板天梯
  const [hkt, bb, zt] = await Promise.all([api("/api/hkt?days=10"), api("/api/billboard"), api("/api/ztpool")]);
  const byDate = {};
  hkt.forEach((r) => { if (r.mutual_type.startsWith("南向")) byDate[r.trade_date] = (byDate[r.trade_date] || 0) + (r.net_amt || 0) / 100; });
  const days = Object.keys(byDate).sort().slice(-5);
  const north = days.map((d2) => `<div class="srow"><span>${d2.slice(5)}</span><span class="${byDate[d2] >= 0 ? "pos" : "neg"}" style="margin-left:auto">${byDate[d2] >= 0 ? "+" : ""}${byDate[d2].toFixed(1)} 亿</span></div>`).join("") || '<div class="empty">无数据</div>';
  const bbTop = bb.rows.slice(0, 8).map((r) => `<div class="srow"><span><b>${esc(r.name)}</b> <span class="muted mono">${esc(r.code)}</span></span><span class="${(r.net_amt || 0) >= 0 ? "pos" : "neg"}" style="margin-left:auto">${r.net_amt != null ? (r.net_amt > 0 ? "+" : "") + (r.net_amt / 1e4).toFixed(0) + " 万" : "-"}</span></div>`).join("") || '<div class="empty">无数据</div>';
  const ztTop = zt.rows.slice(0, 8).map((r) => `<div class="srow"><span><b>${esc(r.name)}</b> <span class="muted mono">${esc(r.code)}</span></span><span class="lbc" style="margin-left:auto;color:var(--red)">${r.lbc > 1 ? r.lbc + " 连板" : "首板"}</span></div>`).join("") || '<div class="empty">无数据</div>';
  $("#sig-domestic").innerHTML = `
    <div><div class="hint" style="margin-bottom:8px">🌊 南向资金近 5 日净买</div>${north}</div>
    <div><div class="hint" style="margin-bottom:8px">🐉 龙虎榜净买 Top8（${esc(bb.date)}）</div>${bbTop}</div>
    <div><div class="hint" style="margin-bottom:8px">🔥 连板天梯（${esc(zt.date)}）</div>${ztTop}</div>`;
}
async function renderStockView() {
  const q = $("#sig-stock-q").value.trim();
  if (!q) { $("#sig-stock").innerHTML = '<div class="empty">输入美股代码或公司名查看机构持仓（如 AAPL / ALPHABET / NVDA / BABA）</div>'; return; }
  const d = await api(`/api/stock?q=${encodeURIComponent(q)}`);
  const total = d.rows.reduce((s2, r) => s2 + r.curr_value, 0);
  $("#sig-stock").innerHTML = d.rows.length ? `
    <div class="hint" style="margin-bottom:8px">${esc(d.rows[0].issuer)} ${d.rows[0].ticker ? "(" + esc(d.rows[0].ticker) + ")" : ""} · ${d.rows.length} 家机构持有 · 合计 ${fmtUsd(total)}（${esc(d.quarter)}）</div>
    <table><thead><tr><th>机构</th><th>变动</th><th class="num">幅度</th><th class="num">市值</th><th class="num">增减</th><th class="num">股数</th></tr></thead><tbody>${
    d.rows.map((r) => `<tr>
      <td>${esc(r.name_cn || r.inst_name)}</td><td>${changeTag(r.change_type)}</td>
      <td class="num">${pctSpan(r.pct)}</td><td class="num">${fmtUsd(r.curr_value)}</td>
      <td class="num">${amtSpan(r.delta_value)}</td><td class="num muted">${r.shares_curr ? fmtNum(r.shares_curr, 0) : "-"}</td>
    </tr>`).join("")}</tbody></table>`
    : `<div class="empty">没有机构持有「${esc(q)}」（或数据未覆盖）</div>`;
}
$("#sig-stock-btn").addEventListener("click", renderStockView);
$("#sig-stock-q").addEventListener("keydown", (e) => { if (e.key === "Enter") renderStockView(); });

/* ---------- 国内 ---------- */
const D = { tab: "billboard", hktChart: null, watchCode: null, holderType: "" };
async function loadDomestic() {
  $$("#dom-tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === D.tab));
  ["billboard", "hkt", "holders", "ztpool"].forEach((t) => ($(t === D.tab ? `#dom-${t}` : `#dom-${t}`)).hidden = t !== D.tab);
  if (D.tab === "billboard") await loadBillboard();
  if (D.tab === "hkt") await loadHkt();
  if (D.tab === "holders") await loadHolders();
  if (D.tab === "ztpool") await loadZtpool();
}
$("#dom-tabs").addEventListener("click", (e) => {
  const b = e.target.closest(".tab");
  if (!b) return;
  D.tab = b.dataset.tab;
  loadDomestic().catch(console.error);
});

async function loadBillboard() {
  const kw = $("#bb-search").value.trim();
  const d = await api(`/api/billboard?q=${encodeURIComponent(kw)}${D.bbDate ? `&date=${D.bbDate}` : ""}`);
  D.bbDate = d.date;
  $("#bb-date").innerHTML = d.dates.map((x) => `<option ${x === d.date ? "selected" : ""}>${x}</option>`).join("");
  $("#bb-meta").textContent = `${d.date} · ${d.rows.length} 只上榜`;
  $("#bb-table").innerHTML = `<table><thead><tr><th>代码</th><th>名称</th><th class="num">涨跌幅</th><th class="num">榜内净买(万)</th><th class="num">榜内买入(万)</th><th class="num">榜内卖出(万)</th><th>上榜原因</th><th>解读</th></tr></thead><tbody>${
    d.rows.map((r) => `<tr>
      <td class="mono">${esc(r.code)}</td><td><b>${esc(r.name)}</b></td>
      <td class="num">${pctSpan(r.change_rate)}</td>
      <td class="num">${amtSpan(r.net_amt ? (r.net_amt > 0 ? 1 : -1) * Math.abs(r.net_amt) / 1e4 : null)}</td>
      <td class="num muted">${r.buy_amt != null ? fmtNum(r.buy_amt / 1e4, 0) : "-"}</td>
      <td class="num muted">${r.sell_amt != null ? fmtNum(r.sell_amt / 1e4, 0) : "-"}</td>
      <td>${esc(r.reason || "")}</td><td class="muted">${esc((r.explain || "").slice(0, 40))}</td>
    </tr>`).join("") || `<tr><td colspan="8" class="empty">暂无数据（收盘后更新）</td></tr>`}</tbody></table>`;
}
$("#bb-search").addEventListener("input", () => loadBillboard().catch(console.error));
$("#bb-date").addEventListener("change", (e) => { D.bbDate = e.target.value; loadBillboard().catch(console.error); });

async function loadHkt() {
  const rows = await api("/api/hkt?days=60");
  const byDate = {};
  rows.forEach((r) => {
    if (!r.mutual_type.startsWith("南向")) return;
    byDate[r.trade_date] = (byDate[r.trade_date] || 0) + (r.net_amt || 0) / 100;
  });
  const dates = Object.keys(byDate).sort().slice(-40);
  const net = dates.map((d) => byDate[d]);
  if (D.hktChart) D.hktChart.destroy();
  D.hktChart = new Chart($("#hkt-chart"), {
    type: "bar",
    data: { labels: dates.map((d) => d.slice(5)), datasets: [{ label: "南向净买入(亿)", data: net, backgroundColor: net.map((v) => (v >= 0 ? "rgba(34,197,94,.7)" : "rgba(239,68,68,.7)")), borderRadius: 3 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: "#8b98ad", maxTicksLimit: 12 }, grid: { display: false } }, y: { ticks: { color: "#8b98ad" }, grid: { color: "#1f2a3d" } } } },
  });
  $("#hkt-table").innerHTML = `<table><thead><tr><th>日期</th><th>通道</th><th class="num">买入(亿)</th><th class="num">卖出(亿)</th><th class="num">净买(亿)</th></tr></thead><tbody>${
    rows.slice(0, 40).map((r) => `<tr><td>${esc(r.trade_date)}</td><td>${esc(r.mutual_type)}</td>
      <td class="num muted">${fmtYi(r.buy_amt)}</td><td class="num muted">${fmtYi(r.sell_amt)}</td>
      <td class="num">${amtSpan(r.net_amt ? (r.net_amt > 0 ? 1 : -1) * Math.abs(r.net_amt) / 100 : null)}</td></tr>`).join("")}</tbody></table>`;
}

const HOLDER_TYPES = ["社保基金", "QFII", "公募基金", "国家队", "保险资金", "北向资金", "私募", "券商", "信托", "其他"];
async function loadHolders() {
  const kw = $("#holder-search").value.trim();
  const d = await api(`/api/holders?q=${encodeURIComponent(kw)}${D.watchCode ? `&code=${D.watchCode}` : ""}${D.holderType ? `&type=${encodeURIComponent(D.holderType)}` : ""}`);
  // 类型 seg
  const types = ["", ...HOLDER_TYPES];
  $("#holder-type-seg").innerHTML = types.map((t) => `<button class="seg-btn ${t === D.holderType ? "active" : ""}" data-t="${t}">${t || "全部类型"}</button>`).join("");
  // 自选 chips
  $("#watch-chips").innerHTML = d.watchlist.map((w) =>
    `<span class="chip ${w.code === D.watchCode ? "active" : ""}" onclick="pickWatch('${w.code}')">${esc(w.code)} ${esc(w.name)}<span class="x" onclick="delWatch('${w.code}', event)">✕</span></span>`).join("");
  $("#holder-table").innerHTML = `<table><thead><tr><th>报告期</th><th>股票</th><th>排名</th><th>股东名称</th><th>类型</th><th class="num">持股(万股)</th><th class="num">占流通</th><th>变动</th><th class="num">变动幅度</th></tr></thead><tbody>${
    d.rows.map((r) => `<tr>
      <td class="muted">${esc(r.end_date)}</td>
      <td>${esc(r.sec_name)} <span class="muted mono">${esc(r.code)}</span></td>
      <td class="muted">${r.holder_rank}</td>
      <td style="max-width:340px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.holder_name)}"><b>${esc(r.holder_name)}</b></td>
      <td>${holderTag(r.holder_type)}</td>
      <td class="num">${r.hold_num != null ? fmtNum(r.hold_num / 1e4, 0) : "-"}</td>
      <td class="num">${r.hold_ratio != null ? r.hold_ratio.toFixed(2) + "%" : "-"}</td>
      <td>${changeTag(r.change_type)}</td>
      <td class="num">${pctSpan(r.change_ratio)}</td>
    </tr>`).join("") || `<div class="empty">暂无数据 — 可点上方"立即更新"抓取自选股股东</div>`}</tbody></table>`;
}
function holderTag(t) {
  const map = { "社保基金": "b", "QFII": "p", "公募基金": "g", "国家队": "r", "保险资金": "y", "北向资金": "p", "私募": "n", "券商": "n", "信托": "n" };
  return `<span class="tag ${map[t] || "n"}">${esc(t)}</span>`;
}
window.pickWatch = (code) => { D.watchCode = D.watchCode === code ? null : code; loadHolders().catch(console.error); };
window.delWatch = async (code, ev) => {
  ev.stopPropagation();
  await api(`/api/watchlist/${code}`, { method: "DELETE" });
  loadHolders().catch(console.error);
};
$("#wl-add").addEventListener("click", async () => {
  const code = $("#wl-code").value.trim(), name = $("#wl-name").value.trim();
  if (!/^\d{6}$/.test(code)) return alert("请输入 6 位 A 股代码");
  await post("/api/watchlist", { code, name });
  $("#wl-code").value = $("#wl-name").value = "";
  loadHolders().catch(console.error);
});
$("#holder-search").addEventListener("input", () => loadHolders().catch(console.error));
$("#holder-type-seg").addEventListener("click", (e) => {
  const b = e.target.closest(".seg-btn");
  if (!b) return;
  D.holderType = b.dataset.t;
  loadHolders().catch(console.error);
});

async function loadZtpool() {
  const d = await api(`/api/ztpool${D.ztDate ? `?date=${D.ztDate}` : ""}`);
  D.ztDate = d.date;
  $("#zt-date").innerHTML = d.dates.map((x) => `<option ${x === d.date ? "selected" : ""}>${x}</option>`).join("");
  $("#zt-meta").textContent = `${d.date} · 涨停 ${d.rows.length} 只`;
  $("#zt-grid").innerHTML = d.rows.map((r) => `
    <div class="zt-card">
      <div class="n"><span>${esc(r.name)}</span><span class="lbc">${r.lbc > 1 ? `${r.lbc} 连板` : "首板"}</span></div>
      <div class="s mono">${esc(r.code)} · 首封 ${esc(r.first_time || "-")} ${r.lbc > 1 ? `· 末封 ${esc(r.last_time || "-")}` : ""}</div>
      <div class="s">流通 ${fmtNum(r.ltsz / 1e8, 0)} 亿 · 成交 ${fmtNum(r.amount / 1e8, 1)} 亿</div>
    </div>`).join("") || `<div class="empty">暂无数据（交易时段自动更新）</div>`;
}
$("#zt-date").addEventListener("change", (e) => { D.ztDate = e.target.value; loadZtpool().catch(console.error); });

/* ---------- 快讯 ---------- */
const N = { source: "", kw: "" };
const NEWS_HL = ["伯克希尔", "巴菲特", "桥水", "达里奥", "文艺复兴", "西蒙斯", "城堡", "Citadel", "千禧年", "Millennium", "高瓴", "HHLR", "老虎基金", "老虎环球", "Tiger Global", "Point72", "Two Sigma", "Baupost", "潘兴广场", "Pershing", "索罗斯", "Soros", "Appaloosa", "埃利奥特", "Elliott", "Coatue", "孤松", "Lone Pine", "贝莱德", "BlackRock", "先锋集团", "Vanguard", "富达", "Fidelity", "摩根士丹利", "高盛", "摩根大通", "瑞银", "淡马锡", "GIC", "挪威主权基金", "阿布扎比", "红杉", "IDG资本", "软银", "愿景基金", "黑石", "凯雷", "KKR", "华平", "春华资本", "易方达", "华夏基金", "南方基金", "嘉实基金", "广发基金", "富国基金", "招商基金", "社保基金", "汇金", "证金", "国家大基金", "中投公司"];
const ACT_HL = ["增持", "减持", "清仓", "建仓", "加仓", "做空", "做多", "举牌", "回购", "收购", "入股", "重仓", "减仓", "新进", "退出", "调研", "上调评级", "下调评级", "目标价"];
function highlight(text) {
  let h = esc(text);
  NEWS_HL.forEach((k) => { h = h.split(esc(k)).join(`<span class="inst">${esc(k)}</span>`); });
  ACT_HL.forEach((k) => { h = h.split(esc(k)).join(`<span class="kw">${esc(k)}</span>`); });
  return h;
}
function newsItem(n) {
  const m = (Array.isArray(n.matched) ? n.matched : []).filter((x) => !String(x).startsWith("动作:"));
  return `<div class="news-item">
    <div class="meta"><span>${esc(n.published_at?.slice(5, 16) || "")}</span><span class="src">${esc(n.source)}</span>${m.length ? `<span class="tag p">⚡ ${m.slice(0, 3).map(esc).join(" / ")}</span>` : ""}</div>
    <div class="content">${highlight(n.content || n.title)}${n.url ? ` <a href="${esc(n.url)}" target="_blank" rel="noopener">🔗</a>` : ""}</div>
  </div>`;
}
async function loadNewsPage() {
  const kw = $("#news-search").value.trim();
  const url = `/api/news?limit=200&q=${encodeURIComponent(kw)}${N.source === "matched" ? "&matched=1" : N.source ? `&source=${encodeURIComponent(N.source)}` : ""}`;
  const rows = await api(url);
  $("#news-list").innerHTML = rows.map(newsItem).join("") || `<div class="empty">暂无快讯</div>`;
}
$("#news-seg").addEventListener("click", (e) => {
  const b = e.target.closest(".seg-btn");
  if (!b) return;
  $$("#news-seg .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
  N.source = b.dataset.t;
  loadNewsPage().catch(console.error);
});
$("#news-search").addEventListener("input", () => loadNewsPage().catch(console.error));

/* ---------- 告警 ---------- */
let alertSince = 0;
function alertItem(a) {
  const kindMap = { holding: "13F", holder: "股东", news_kw: "快讯", system: "系统" };
  return `<div class="alert-item ${a.level}">
    <div class="t">${highlight(a.title)}</div>
    <div class="d">${highlight(a.detail)}</div>
    <div class="meta"><span>${esc(a.ts?.slice(5, 16))}</span><span class="tag ${a.level === "critical" ? "r" : a.level === "important" ? "y" : "b"}">${kindMap[a.kind] || a.kind}</span>${a.pushed ? '<span class="muted">已推送</span>' : ""}${a.link ? `<a href="${esc(a.link)}" target="_blank" rel="noopener">原文</a>` : ""}</div>
  </div>`;
}
async function loadAlertsPage() {
  const kind = $("#alert-seg .seg-btn.active")?.dataset.t || "";
  const d = await api(`/api/alerts?limit=200${kind ? `&kind=${kind}` : ""}`);
  $("#alert-list").innerHTML = d.rows.map(alertItem).join("") || `<div class="empty">暂无告警 — 保持运行，机构一动就有提醒</div>`;
}
$("#alert-seg").addEventListener("click", (e) => {
  const b = e.target.closest(".seg-btn");
  if (!b) return;
  $$("#alert-seg .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
  loadAlertsPage().catch(console.error);
});
$("#alert-clear").addEventListener("click", async () => {
  if (!confirm("确定清空全部告警记录？")) return;
  await api("/api/alerts", { method: "DELETE" });
  loadAlertsPage().catch(console.error);
});

/* 告警轮询 + 桌面通知 */
async function pollAlerts() {
  try {
    const d = await api(`/api/alerts?limit=20&since_id=${alertSince}`);
    if (alertSince === 0 && d.rows.length) { alertSince = d.rows[0].id; return; }
    if (d.rows.length) {
      const badge = $("#alert-badge");
      badge.hidden = false;
      badge.textContent = d.rows.length;
      if (notifyOn && Notification.permission === "granted") {
        d.rows.slice(0, 3).forEach((a) => new Notification(a.title, { body: a.detail, tag: `instmon-${a.id}` }));
      }
    }
  } catch (e) { /* 忽略 */ }
}
let notifyOn = false;
$("#desktop-notify").addEventListener("change", async (e) => {
  if (e.target.checked) {
    const perm = await Notification.requestPermission();
    notifyOn = perm === "granted";
    if (!notifyOn) e.target.checked = false;
  } else notifyOn = false;
});
$("#btn-refresh-all").addEventListener("click", async (e) => {
  e.target.disabled = true;
  for (const k of ["news", "billboard", "hkt_flow", "zt_pool", "top_holders"]) await post(`/api/run/${k}`);
  setTimeout(() => { e.target.disabled = false; route(); }, 1500);
  alert("已触发一轮全量更新（13F 较慢，约 1-2 分钟），数据将陆续入库");
});

/* ---------- 设置 ---------- */
const NOTIFY_CHANNELS = [
  ["bark", "Bark (iOS)", "https://api.day.app/你的Key"],
  ["serverchan", "Server酱", "https://sctapi.ftqq.com/你的KEY.send"],
  ["feishu", "飞书群机器人", "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"],
  ["dingtalk", "钉钉群机器人", "https://oapi.dingtalk.com/robot/send?access_token=xxx"],
  ["custom", "自定义 Webhook", "https://your.server/hook"],
];
const HOLDER_TYPE_ALL = ["社保基金", "QFII", "公募基金", "国家队", "保险资金", "北向资金", "私募", "券商", "信托"];
async function loadSettings() {
  const [srcs, cfg] = await Promise.all([api("/api/sources"), api("/api/settings")]);
  $("#src-list").innerHTML = srcs.map((s) => {
    const dot = s.last_status === "ok" ? "ok" : s.last_status === "fail" ? "fail" : "never";
    return `<div class="src-row">
      <div class="nm"><span class="dot ${dot}"></span><b>${esc(s.name)}</b></div>
      <div class="st">${s.last_status === "ok" ? "✅" : s.last_status === "fail" ? "❌" : "⏳"} ${esc(s.last_msg || "尚未运行")}<br>${s.last_run ? "上次: " + esc(s.last_run) : ""}</div>
      <label class="switch"><input type="checkbox" ${s.enabled ? "checked" : ""} onchange="toggleSrc('${s.key}', this.checked)"><span>启用</span></label>
      <span class="muted">每</span><input class="input num" type="number" value="${s.interval_min}" min="2" onchange="setSrcInterval('${s.key}', this.value)"><span class="muted">分钟</span>
      <button class="btn primary" onclick="runSrc('${s.key}')">立即更新</button>
    </div>`;
  }).join("");

  $("#r-13f-pct").value = cfg.alert_13f.big_pct;
  $("#r-13f-val").value = Math.round(cfg.alert_13f.min_value_usd / 1e8);
  $("#r-holder-pct").value = cfg.alert_holder.pct;
  $("#r-holder-types").innerHTML = HOLDER_TYPE_ALL.map((t) =>
    `<label><input type="checkbox" value="${t}" ${cfg.alert_holder.types.includes(t) ? "checked" : ""}>${t}</label>`).join("");
  $("#r-min-level").value = cfg.alert_min_level;

  $("#notify-form").innerHTML = NOTIFY_CHANNELS.map(([ch, nm, ph]) => `
    <div class="notify-row">
      <span class="nm">${nm}</span>
      <input class="input" id="nf-${ch}" placeholder="${ph}" value="${esc(cfg["notify_" + ch] || "")}">
      <button class="btn ghost" onclick="saveNotify('${ch}')">保存</button>
      <button class="btn ghost" onclick="testNotify('${ch}')">测试</button>
    </div>`).join("");

  $("#proxy-url").value = cfg.proxy_url || "";
  $("#proxy-on").checked = !!cfg.proxy_enabled;
}
window.toggleSrc = async (key, on) => { await post(`/api/sources/${key}`, { enabled: on }); };
window.setSrcInterval = async (key, v) => { await post(`/api/sources/${key}`, { interval_min: +v }); };
window.runSrc = async (key) => {
  const r = await post(`/api/run/${key}`);
  alert(r.msg);
  setTimeout(loadSettings, 3000);
};
$("#r-save").addEventListener("click", async () => {
  await post("/api/settings", {
    alert_13f: { big_pct: +$("#r-13f-pct").value || 30, min_value_usd: (+$("#r-13f-val").value || 2) * 1e8 },
    alert_holder: { pct: +$("#r-holder-pct").value || 5, types: $$("#r-holder-types input:checked").map((i) => i.value) },
    alert_min_level: $("#r-min-level").value,
  });
  alert("已保存告警规则");
});
window.saveNotify = async (ch) => {
  await post("/api/settings", { ["notify_" + ch]: $(`#nf-${ch}`).value.trim() });
  alert("已保存");
};
window.testNotify = async (ch) => {
  await post("/api/settings", { ["notify_" + ch]: $(`#nf-${ch}`).value.trim() });
  const r = await post("/api/notify/test", { channel: ch, config: $(`#nf-${ch}`).value.trim() });
  alert(r.ok ? "✅ 测试推送已发送，请查收" : `❌ ${r.result}`);
};
$("#proxy-save").addEventListener("click", async () => {
  await post("/api/settings", { proxy_url: $("#proxy-url").value.trim() || "http://127.0.0.1:6152", proxy_enabled: $("#proxy-on").checked });
  alert("已保存，13F 爬虫将使用新代理设置");
});

/* ---------- 启动 ---------- */
setInterval(() => ($("#foot-clock").textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false })), 1000);
setInterval(pollAlerts, 30000);
route();
pollAlerts();
setInterval(() => { if (["overview"].includes((location.hash.replace("#/", "") || "overview"))) route(); }, 60000);
