"""告警规则引擎：13F 大变动 / 十大股东异动 / 机构关键词快讯 -> alerts + webhook 推送。"""
from db import get_db, get_setting_json, now


def save_alert(kind, title, detail, level="important", link="", push=True):
    """写一条告警并（可选）立即推送。返回 alert id。"""
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO alerts(ts,level,kind,title,detail,link,pushed) VALUES(?,?,?,?,?,?,0)",
            (now(), level, kind, title, detail, link))
        alert_id = cur.lastrowid
    if push:
        _push_one(alert_id, title, detail)
    return alert_id


def _push_one(alert_id, title, detail):
    try:
        from notify import push_alert
        push_alert(title, detail)
    except Exception:  # noqa: BLE001
        pass
    with get_db() as db:
        db.execute("UPDATE alerts SET pushed=1 WHERE id=?", (alert_id,))


# ---------- 1. SEC 13F 持仓变动 ----------
def holding_alerts():
    """对最近生成的 hchanges 找值得提醒的：新增/清仓 或 变动幅度超阈值。单次最多 50 条。"""
    rules = get_setting_json("alert_13f", {"big_pct": 50, "min_value_usd": 5e8, "max_per_run": 50})
    big_pct = rules.get("big_pct", 50)
    min_value = rules.get("min_value_usd", 5e8)
    max_per_run = rules.get("max_per_run", 50)
    made = 0
    with get_db() as db:
        rows = db.execute(
            "SELECT h.*, i.name AS inst, i.name_cn FROM hchanges h JOIN institutions i ON i.id=h.inst_id "
            "WHERE h.created_at >= datetime('now','-1 day') AND i.followed=1 "
            "ORDER BY ABS(COALESCE(h.delta_value,0)) DESC").fetchall()
    for r in rows:
        if made >= max_per_run:
            break
        hit = (r["change_type"] in ("新增", "清仓")
               or (r["change_type"] in ("增持", "减持") and abs(r["pct"] or 0) >= big_pct))
        if not hit:
            continue
        value = max(r["curr_value"] or 0, r["prev_value"] or 0)
        if value < min_value:
            continue
        title = f"[{r['name_cn'] or r['inst']}] {r['change_type']} {r['issuer'] or r['ticker']}"
        with get_db() as db:
            exists = db.execute(
                "SELECT 1 FROM alerts WHERE kind='holding' AND title=? AND ts>=datetime('now','-1 day')",
                (title,)).fetchone()
        if exists:
            continue
        delta = r["delta_value"] or 0
        detail = (f"{r['quarter']} 环比{r['change_type']} {abs(r['pct']):.0f}% | "
                  f"持仓市值 ${value/1e8:.1f}亿 ({'+' if delta >= 0 else '-'}${abs(delta)/1e8:.1f}亿) "
                  f"股数 {r['shares_curr'] or 0:,.0f}")
        save_alert("holding", title, detail,
                   "critical" if r["change_type"] in ("新增", "清仓") else "important")
        made += 1
    return made


# ---------- 2. 十大流通股东异动 ----------
def holder_alerts():
    rules = get_setting_json("alert_holder",
                             {"types": ["社保基金", "QFII", "公募基金", "国家队", "保险资金", "北向资金"], "pct": 5})
    watch_types, pct = rules.get("types", []), rules.get("pct", 5)
    made = 0
    with get_db() as db:
        rows = db.execute("SELECT * FROM top_holders WHERE end_date >= date('now','-60 day')").fetchall()
    for r in rows:
        if r["holder_type"] not in watch_types:
            continue
        if r["change_type"] not in ("新进", "增持", "减持", "退出"):
            continue
        ratio = abs(r["change_ratio"] or 0)
        if r["change_type"] not in ("新进", "退出") and ratio < pct:
            continue
        title = f"[{r['sec_name']}] {(r['holder_name'] or '')[:24]} {r['change_type']}"
        with get_db() as db:
            exists = db.execute("SELECT 1 FROM alerts WHERE kind='holder' AND title=?",
                                (title,)).fetchone()
        if exists:
            continue
        ratio_txt = f"{ratio:.1f}%" if ratio else ""
        detail = (f"{r['end_date']} 十大流通股东 | {r['holder_type']} "
                  f"{r['change_type']} {ratio_txt} | 持股 {r['hold_num'] or 0:,.0f} 股, "
                  f"占流通 {r['hold_ratio'] or 0:.2f}%")
        save_alert("holder", title, detail, "important")
        made += 1
    return made


# ---------- 3. 快讯关键词 ----------
def news_alerts(matched_items):
    """matched_items: run_news 返回的命中(机构+动作)快讯。"""
    if not matched_items:
        return 0
    made = 0
    with get_db() as db:
        for it in matched_items:
            insts, acts = it["insts"], it["acts"]
            title = " | ".join(insts[:3]) + "：" + (it.get("title") or it.get("content", "")[:40])
            exists = db.execute("SELECT 1 FROM alerts WHERE kind='news_kw' AND title=?", (title,)).fetchone()
            if exists:
                continue
            detail = f"[{it['source']}] {it['content'][:180]}"
            save_alert("news_kw", title, detail, "important", it.get("url", ""))
            made += 1
    return made
