"""爬虫注册表：source key -> 执行函数。scheduler 与手动触发都走这里。"""
from db import get_db, now


def _set_status(key, status, msg, count):
    try:
        with get_db() as db:
            db.execute("UPDATE sources SET last_run=?, last_status=?, last_msg=?, last_count=? WHERE key=?",
                       (now(), status, msg, count, key))
    except Exception:  # noqa: BLE001
        pass


def run_source(key):
    """执行一个数据源更新，记录状态到 sources 表。返回 (ok, msg, count)。"""
    from . import eastmoney, news
    from . import sec13f  # noqa: F401  (注册用)
    from db import get_setting_json

    ok, msg, count = False, "", 0
    try:
        if key == "news":
            new, total, matched = news.run_news()
            # 有机构+动作的快讯交给告警引擎
            from . import alerting
            alerting.news_alerts(matched)
            msg, count, ok = f"新增 {new}/{total} 条", total, True

        elif key == "billboard":
            rows = eastmoney.fetch_billboard()
            with get_db() as db:
                n, dates = eastmoney.write_billboard(db, rows, limit_days=3)
            msg, count, ok = f"{dates[0] if dates else '-'} 榜单 +{n} 条", n, True

        elif key == "seed_billboard_history":
            rows = eastmoney.fetch_billboard()
            with get_db() as db:
                n, _ = eastmoney.write_billboard(db, rows, limit_days=None)
            msg, count, ok = f"历史龙虎榜 +{n} 条", n, True

        elif key == "hkt_flow":
            rows = eastmoney.fetch_hkt_flow()
            with get_db() as db:
                n = eastmoney.write_hkt_flow(db, rows)
            msg, count, ok = f"沪深港通 +{n} 条", n, True

        elif key == "top_holders":
            with get_db() as db:
                watchlist = [(c["code"], c["name"]) for c in db.execute("SELECT code,name FROM watchlist")]
            if not watchlist:
                return False, "自选股池为空", 0
            fetched = eastmoney.fetch_top_holders(watchlist)
            with get_db() as db:
                n = eastmoney.write_top_holders(db, fetched)
            from . import alerting
            alerting.holder_alerts()
            msg, count, ok = f"{len(fetched)} 只自选股, +{n} 条股东记录", n, True

        elif key == "zt_pool":
            rows = eastmoney.fetch_zt_pool()
            with get_db() as db:
                n = eastmoney.write_zt_pool(db, rows)
            msg, count, ok = f"涨停池 {n} 只", n, True

        elif key == "sec13f":
            use_proxy = get_setting_json("proxy_enabled", True)
            proxy_url = get_setting_json("proxy_url", "http://127.0.0.1:6152")
            from .alerting import holding_alerts
            scraper = sec13f.Sec13FScraper(None, proxy_url=proxy_url if use_proxy else "",
                                           logger=lambda m: print(f"[13F] {m}"))
            ok_n, nq, changes = scraper.run()
            holding_alerts()
            msg, count, ok = f"{ok_n} 家机构, 新增期数 {nq}, 变动 {changes} 条", changes, True

        else:
            msg = f"未知数据源 {key}"

    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        msg = f"{type(e).__name__}: {e}"
        ok = False

    _set_status(key, "ok" if ok else "fail", msg, count)
    return ok, msg, count


DEFAULT_SOURCES = [
    ("news", "7x24 快讯（东财+新浪）", 5),
    ("sec13f", "SEC 13F 全球机构持仓", 360),
    ("billboard", "龙虎榜", 30),
    ("hkt_flow", "沪深港通资金流", 60),
    ("top_holders", "自选股十大流通股东", 240),
    ("zt_pool", "涨停池/连板异动", 15),
]


def ensure_sources():
    with get_db() as db:
        for key, name, interval in DEFAULT_SOURCES:
            db.execute("INSERT OR IGNORE INTO sources(key,name,interval_min) VALUES(?,?,?)",
                       (key, name, interval))
