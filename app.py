"""机构雷达 · 全球+国内投资机构持仓与异动监控网站。

启动: .venv/bin/python app.py   -> http://127.0.0.1:8900
功能: 13F 持仓变动 · 龙虎榜 · 沪深港通 · 十大流通股东 · 涨停池 · 7x24 快讯 · 告警推送
首次启动自动种子机构清单与自选股池，并后台执行一轮全量抓取。
"""
import sys
import threading
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from flask import Flask, jsonify, render_template, request

import db as store
import scheduler as sch
import scrapers
from scrapers.sec13f import Sec13FScraper

app = Flask(__name__)

SEED_WATCHLIST = [
    ("600519", "贵州茅台"), ("300750", "宁德时代"), ("002594", "比亚迪"), ("600036", "招商银行"),
    ("000858", "五粮液"), ("000333", "美的集团"), ("601012", "隆基绿能"), ("601318", "中国平安"),
    ("603259", "药明康德"), ("300760", "迈瑞医疗"), ("600900", "长江电力"), ("601919", "中远海控"),
    ("601899", "紫金矿业"), ("002475", "立讯精密"), ("002415", "海康威视"), ("600309", "万华化学"),
    ("600276", "恒瑞医药"), ("000568", "泸州老窖"), ("600809", "山西汾酒"), ("000725", "京东方A"),
    ("601888", "中国中免"), ("300015", "爱尔眼科"), ("600438", "通威股份"), ("300124", "汇川技术"),
    ("600031", "三一重工"), ("600111", "北方稀土"), ("300308", "中际旭创"), ("300502", "新易盛"),
    ("601138", "工业富联"), ("688981", "中芯国际"), ("688256", "寒武纪"), ("688041", "海光信息"),
    ("601689", "拓普集团"), ("601127", "赛力斯"), ("000625", "长安汽车"), ("000651", "格力电器"),
    ("600690", "海尔智家"), ("000002", "万科A"), ("600048", "保利发展"), ("601166", "兴业银行"),
    ("300059", "东方财富"), ("600030", "中信证券"), ("601688", "华泰证券"), ("002027", "分众传媒"),
    ("002714", "牧原股份"), ("600887", "伊利股份"), ("603288", "海天味业"), ("600570", "恒生电子"),
]


def seed_base():
    store.init_db()
    scrapers.ensure_sources()
    from scrapers.sec13f import Sec13FScraper
    Sec13FScraper(None).ensure_institutions()
    with store.get_db() as db:
        for code, name in SEED_WATCHLIST:
            db.execute("INSERT OR IGNORE INTO watchlist(code,name,added_at) VALUES(?,?,?)",
                       (code, name, store.now()))


def initial_scrape():
    """首轮全量抓取（后台线程），顺序: 快讯->龙虎榜历史->资金流->涨停->股东->13F。"""
    for key in ("news", "seed_billboard_history", "billboard", "hkt_flow", "zt_pool", "top_holders", "sec13f"):
        try:
            ok, msg, n = scrapers.run_source(key)
            print(f"[seed] {key}: {'OK' if ok else 'FAIL'} {msg}")
        except Exception as e:  # noqa: BLE001
            print(f"[seed] {key} 异常: {e}")


def _never_ran() -> bool:
    with store.get_db() as db:
        r = db.execute("SELECT COUNT(*) c FROM sources WHERE last_status='ok'").fetchone()
        return r["c"] == 0


# ---------------- 页面 ----------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------- 概览 ----------------
@app.route("/api/summary")
def summary():
    with store.get_db() as db:
        q = db.execute
        n_inst = q("SELECT COUNT(*) c FROM institutions WHERE category='global_13f'").fetchone()["c"]
        n_followed = q("SELECT COUNT(*) c FROM institutions WHERE followed=1").fetchone()["c"]
        latest_quarter = q("SELECT MAX(quarter) m FROM hchanges").fetchone()["m"] or ""
        n_changes = q("SELECT COUNT(*) c FROM hchanges WHERE quarter=?", (latest_quarter,)).fetchone()["c"]
        n_news = q("SELECT COUNT(*) c FROM news WHERE created_at>=datetime('now','-1 day')").fetchone()["c"]
        n_alerts = q("SELECT COUNT(*) c FROM alerts WHERE ts>=datetime('now','-1 day')").fetchone()["c"]
        alerts = store.rows_to_dicts(q("SELECT * FROM alerts ORDER BY id DESC LIMIT 8"))
        top_changes = store.rows_to_dicts(q(
            "SELECT h.*, i.name_cn, i.name AS inst_name FROM hchanges h JOIN institutions i ON i.id=h.inst_id "
            "WHERE h.quarter=? AND h.change_type IN ('新增','清仓') ORDER BY ABS(h.delta_value) DESC LIMIT 10", (latest_quarter,)))
        news_matched = store.rows_to_dicts(q(
            "SELECT * FROM news WHERE matched != '[]' ORDER BY published_at DESC LIMIT 8"))
        bb = store.rows_to_dicts(q(
            "SELECT trade_date, COUNT(*) n, SUM(CASE WHEN net_amt>0 THEN 1 ELSE 0 END) up FROM dt_billboard "
            "GROUP BY trade_date ORDER BY trade_date DESC LIMIT 5"))
        hkt = store.rows_to_dicts(q(
            "SELECT trade_date, mutual_type, net_amt FROM hkt_flow WHERE mutual_type IN ('北向沪股通','北向深股通') "
            "ORDER BY trade_date DESC LIMIT 8"))
        zt = q("SELECT COUNT(*) c FROM zt_pool WHERE date=date('now','localtime')").fetchone()["c"]
        sources = store.rows_to_dicts(q("SELECT key,name,last_run,last_status,last_msg FROM sources"))
    import json as _json
    for r in news_matched:
        try:
            r["matched"] = _json.loads(r.get("matched") or "[]")
        except Exception:  # noqa: BLE001
            r["matched"] = []
    return jsonify(insts=n_inst, followed=n_followed, quarter=latest_quarter, changes=n_changes,
                   news_24h=n_news, alerts_24h=n_alerts, alerts=alerts, top_changes=top_changes,
                   news_matched=news_matched, billboard_dates=bb, hkt=hkt, zt_today=zt, sources=sources)


# ---------------- 机构与 13F ----------------
@app.route("/api/institutions")
def institutions():
    with store.get_db() as db:
        rows = store.rows_to_dicts(db.execute(
            "SELECT i.*, (SELECT COUNT(*) FROM hchanges h WHERE h.inst_id=i.id AND h.quarter=(SELECT MAX(quarter) FROM hchanges)) n_moves "
            "FROM institutions i ORDER BY i.category, i.id"))
    return jsonify(rows)


@app.route("/api/institutions/<int:iid>/follow", methods=["POST"])
def follow(iid):
    with store.get_db() as db:
        db.execute("UPDATE institutions SET followed = 1 - followed WHERE id=?", (iid,))
    return jsonify(ok=True)


@app.route("/api/quarters")
def quarters():
    iid = request.args.get("inst_id", type=int)
    with store.get_db() as db:
        if iid:
            qs = [r[0] for r in db.execute(
                "SELECT DISTINCT quarter FROM filings WHERE inst_id=? ORDER BY quarter DESC", (iid,))]
        else:
            qs = [r[0] for r in db.execute("SELECT DISTINCT quarter FROM filings ORDER BY quarter DESC")]
    return jsonify(qs)


@app.route("/api/holdings/changes")
def holdings_changes():
    inst = request.args.get("inst_id", type=int)
    ctype = request.args.get("type", "")
    kw = request.args.get("q", "").strip()
    quarter = request.args.get("quarter", "")
    limit = min(request.args.get("limit", 500, type=int), 2000)
    sql = ("SELECT h.*, i.name_cn, i.name AS inst_name FROM hchanges h JOIN institutions i ON i.id=h.inst_id WHERE 1=1")
    args = []
    if inst:
        sql += " AND h.inst_id=?"
        args.append(inst)
    if ctype:
        sql += " AND h.change_type=?"
        args.append(ctype)
    if quarter:
        sql += " AND h.quarter=?"
        args.append(quarter)
    if kw:
        sql += " AND (h.issuer LIKE ? OR h.ticker LIKE ? OR i.name_cn LIKE ?)"
        args += [f"%{kw}%"] * 3
    sql += " ORDER BY h.quarter DESC, ABS(h.delta_value) DESC LIMIT ?"
    args.append(limit)
    with store.get_db() as db:
        rows = store.rows_to_dicts(db.execute(sql, args))
    return jsonify(rows)


@app.route("/api/holdings/current")
def holdings_current():
    iid = request.args.get("inst_id", type=int)
    kw = request.args.get("q", "").strip()
    with store.get_db() as db:
        quarter = request.args.get("quarter") or db.execute(
            "SELECT MAX(quarter) m FROM holdings WHERE inst_id=?", (iid,)).fetchone()["m"]
        sql = "SELECT * FROM holdings WHERE inst_id=? AND quarter=?"
        args = [iid, quarter]
        if kw:
            sql += " AND (issuer LIKE ? OR ticker LIKE ?)"
            args += [f"%{kw}%"] * 2
        sql += " ORDER BY value_usd DESC LIMIT 300"
        rows = store.rows_to_dicts(db.execute(sql, args))
    return jsonify(quarter=quarter, rows=rows)


# ---------------- 国内数据 ----------------
@app.route("/api/billboard")
def billboard():
    date = request.args.get("date", "")
    kw = request.args.get("q", "").strip()
    with store.get_db() as db:
        if not date:
            date = db.execute("SELECT MAX(trade_date) m FROM dt_billboard").fetchone()["m"] or ""
        sql, args = "SELECT * FROM dt_billboard WHERE trade_date=?", [date]
        if kw:
            sql += " AND (name LIKE ? OR code LIKE ?)"
            args += [f"%{kw}%"] * 2
        sql += " ORDER BY ABS(COALESCE(net_amt,0)) DESC LIMIT 200"
        rows = store.rows_to_dicts(db.execute(sql, args))
        dates = [r[0] for r in db.execute("SELECT DISTINCT trade_date FROM dt_billboard ORDER BY trade_date DESC LIMIT 15")]
    return jsonify(date=date, dates=dates, rows=rows)


@app.route("/api/hkt")
def hkt():
    days = request.args.get("days", 30, type=int)
    with store.get_db() as db:
        rows = store.rows_to_dicts(db.execute(
            "SELECT * FROM hkt_flow ORDER BY trade_date DESC, mutual_type LIMIT ?", (days * 4,)))
    return jsonify(rows)


@app.route("/api/holders")
def holders():
    code = request.args.get("code", "")
    htype = request.args.get("type", "")
    kw = request.args.get("q", "").strip()
    with store.get_db() as db:
        sql, args = "SELECT * FROM top_holders WHERE 1=1", []
        if code:
            sql += " AND code=?"
            args.append(code)
        if htype:
            sql += " AND holder_type=?"
            args.append(htype)
        if kw:
            sql += " AND (holder_name LIKE ? OR sec_name LIKE ?)"
            args += [f"%{kw}%"] * 2
        sql += " ORDER BY end_date DESC, code, holder_rank LIMIT 1000"
        rows = store.rows_to_dicts(db.execute(sql, args))
        wl = store.rows_to_dicts(db.execute("SELECT * FROM watchlist ORDER BY code"))
    return jsonify(rows=rows, watchlist=wl)


@app.route("/api/watchlist", methods=["POST"])
def add_watch():
    data = request.get_json(force=True)
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    if not code.isdigit() or len(code) != 6:
        return jsonify(ok=False, msg="请输入 6 位股票代码"), 400
    with store.get_db() as db:
        db.execute("INSERT OR IGNORE INTO watchlist(code,name,added_at) VALUES(?,?,?)", (code, name, store.now()))
    return jsonify(ok=True)


@app.route("/api/watchlist/<code>", methods=["DELETE"])
def del_watch(code):
    with store.get_db() as db:
        db.execute("DELETE FROM watchlist WHERE code=?", (code,))
    return jsonify(ok=True)


@app.route("/api/ztpool")
def ztpool():
    date = request.args.get("date", "")
    with store.get_db() as db:
        if not date:
            date = db.execute("SELECT MAX(date) m FROM zt_pool").fetchone()["m"] or ""
        rows = store.rows_to_dicts(db.execute(
            "SELECT * FROM zt_pool WHERE date=? ORDER BY lbc DESC, first_time LIMIT 400", (date,)))
        dates = [r[0] for r in db.execute("SELECT DISTINCT date FROM zt_pool ORDER BY date DESC LIMIT 15")]
    return jsonify(date=date, dates=dates, rows=rows)


# ---------------- 新闻与告警 ----------------
@app.route("/api/news")
def news_list():
    limit = min(request.args.get("limit", 100, type=int), 300)
    source = request.args.get("source", "")
    kw = request.args.get("q", "").strip()
    only_matched = request.args.get("matched") == "1"
    with store.get_db() as db:
        sql, args = "SELECT * FROM news WHERE 1=1", []
        if source:
            sql += " AND source=?"
            args.append(source)
        if kw:
            sql += " AND (title LIKE ? OR content LIKE ?)"
            args += [f"%{kw}%"] * 2
        if only_matched:
            sql += " AND matched != '[]'"
        sql += " ORDER BY published_at DESC, id DESC LIMIT ?"
        args.append(limit)
        rows = store.rows_to_dicts(db.execute(sql, args))
    for r in rows:
        try:
            r["matched"] = __import__("json").loads(r["matched"] or "[]")
        except Exception:  # noqa: BLE001
            r["matched"] = []
    return jsonify(rows)


# ---------------- 共识信号与个股透视 ----------------
@app.route("/api/consensus")
def consensus():
    import signals as sig
    quarter, items = sig.compute_consensus(request.args.get("quarter") or None)
    buys = [x for x in items if x["net"] >= 2 or x["new"] >= 2][:60]
    # 共识卖出：卖方机构数 > 买方，或明确清仓退出
    sells = [x for x in items if (x["net"] <= -2 or (x["exit"] >= 2 and x["net"] <= 0))][:60]
    sells.sort(key=lambda x: (x["net"], -abs(x["delta"])))
    return jsonify(quarter=quarter, n_all=len(items), buys=buys, sells=sells)


@app.route("/api/stock")
def stock_view():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(rows=[], quarter="")
    ql = q.upper()
    import signals as sig
    with store.get_db() as db:
        quarter = db.execute("SELECT MAX(quarter) m FROM hchanges").fetchone()["m"]
        rows = store.rows_to_dicts(db.execute(
            "SELECT h.inst_id, h.quarter, h.cusip, h.issuer, h.ticker, h.change_type, h.pct, "
            "h.prev_value, h.curr_value, h.delta_value, h.shares_prev, h.shares_curr, "
            "i.name_cn, i.name AS inst_name "
            "FROM hchanges h JOIN institutions i ON i.id=h.inst_id "
            "WHERE h.quarter=? AND (UPPER(h.issuer) LIKE ? OR UPPER(h.ticker) LIKE ? OR h.cusip LIKE ?) "
            "ORDER BY h.curr_value DESC",
            (quarter, f"%{ql}%", f"%{ql}%", f"%{ql}%")))
    return jsonify(quarter=quarter, rows=rows)


@app.route("/api/alerts")
def alerts_list():
    limit = min(request.args.get("limit", 100, type=int), 500)
    since_id = request.args.get("since_id", 0, type=int)
    kind = request.args.get("kind", "")
    with store.get_db() as db:
        sql = "SELECT * FROM alerts WHERE id>?"
        args = [since_id]
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = store.rows_to_dicts(db.execute(sql, args))
        unread = db.execute("SELECT COUNT(*) c FROM alerts WHERE id>?", (since_id,)).fetchone()["c"]
    return jsonify(rows=rows, unread=unread)


@app.route("/api/alerts", methods=["DELETE"])
def alerts_clear():
    with store.get_db() as db:
        db.execute("DELETE FROM alerts")
    return jsonify(ok=True)


# ---------------- 数据源与设置 ----------------
@app.route("/api/sources")
def sources():
    with store.get_db() as db:
        rows = store.rows_to_dicts(db.execute("SELECT * FROM sources ORDER BY id"))
    return jsonify(rows)


@app.route("/api/run/<key>", methods=["POST"])
def run_now(key):
    def _bg():
        ok, msg, n = scrapers.run_source(key)
        print(f"[manual] {key}: {'OK' if ok else 'FAIL'} {msg}")
    threading.Thread(target=_bg, daemon=True).start()
    return jsonify(ok=True, msg="已在后台启动更新，请稍后刷新查看")


@app.route("/api/sources/<key>", methods=["POST"])
def update_source(key):
    data = request.get_json(force=True)
    with store.get_db() as db:
        if "interval_min" in data:
            db.execute("UPDATE sources SET interval_min=? WHERE key=?", (max(2, int(data["interval_min"])), key))
        if "enabled" in data:
            db.execute("UPDATE sources SET enabled=? WHERE key=?", (1 if data["enabled"] else 0, key))
    sch.sync_jobs()
    return jsonify(ok=True)


@app.route("/api/settings", methods=["GET"])
def get_settings():
    keys = ["proxy_url", "proxy_enabled", "notify_bark", "notify_serverchan", "notify_feishu",
            "notify_dingtalk", "notify_custom", "alert_min_level"]
    out = {k: store.get_setting_json(k, "") for k in keys}
    out["alert_min_level"] = out["alert_min_level"] or "important"
    out["proxy_url"] = out["proxy_url"] or "http://127.0.0.1:6152"
    out["alert_13f"] = store.get_setting_json("alert_13f", {"big_pct": 50, "min_value_usd": 5e8, "max_per_run": 50})
    out["alert_holder"] = store.get_setting_json("alert_holder", {"types": ["社保基金", "QFII", "公募基金", "国家队", "保险资金", "北向资金"], "pct": 5})
    return jsonify(out)


@app.route("/api/settings", methods=["POST"])
def set_settings():
    data = request.get_json(force=True)
    for k in ("proxy_url", "proxy_enabled", "notify_bark", "notify_serverchan", "notify_feishu",
              "notify_dingtalk", "notify_custom", "alert_min_level"):
        if k in data:
            store.set_setting(k, data[k])
    if "alert_13f" in data:
        store.set_setting("alert_13f", data["alert_13f"])
    if "alert_holder" in data:
        store.set_setting("alert_holder", data["alert_holder"])
    return jsonify(ok=True)


@app.route("/api/notify/test", methods=["POST"])
def notify_test():
    from notify import test_channel
    data = request.get_json(force=True)
    result = test_channel(data.get("channel"), data.get("config"))
    return jsonify(ok=(result is True), result=str(result))


if __name__ == "__main__":
    seed_base()
    threading.Thread(target=initial_scrape, daemon=True).start() if _never_ran() else None
    sch.start()
    print("机构雷达 -> http://127.0.0.1:8900")
    app.run(host="127.0.0.1", port=8900, debug=False, use_reloader=False)
