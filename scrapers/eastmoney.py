"""东方财富爬虫：龙虎榜 / 沪深港通资金流 / 十大流通股东 / 涨停池。全部直连（不走代理）。

约定：所有网络抓取先完成、不持有数据库连接，只在最后用短事务写库，
避免网络 IO 期间长期占用 SQLite 写锁。
"""
from datetime import datetime

from .http_util import make_session

DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _session():
    return make_session(use_proxy=False)


def _dc_get(session, report, extra=None, sorts="1", stypes="-1", page=1, size=50):
    p = {"reportName": report, "columns": "ALL", "pageSize": size, "pageNumber": page,
         "sortColumns": sorts, "sortTypes": stypes, "source": "WEB", "client": "WEB"}
    if extra:
        p.update(extra)
    r = session.get(DC, params=p, timeout=20)
    r.raise_for_status()
    d = r.json()
    res = d.get("result") or {}
    return res.get("data") or []


def _fmt(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _billboard_rows(s):
    """拉取最近榜单纯数据（去重前）。"""
    rows = []
    for page in (1, 2, 3):
        chunk = _dc_get(s, "RPT_DAILYBILLBOARD_DETAILSNEW",
                        sorts="TRADE_DATE,SECURITY_CODE", stypes="-1,-1", size=200, page=page)
        if not chunk:
            break
        rows.extend(chunk)
    return rows


def _write_billboard(db, rows, limit_days=None):
    dates = sorted({r.get("TRADE_DATE", "")[:10] for r in rows if r.get("TRADE_DATE")}, reverse=True)
    if limit_days:
        dates = dates[:limit_days]
    keep = set(dates)
    n = 0
    for r in rows:
        d = r.get("TRADE_DATE", "")[:10]
        if d not in keep:
            continue
        cur = db.execute(
            "INSERT OR IGNORE INTO dt_billboard(trade_date,code,name,change_rate,net_amt,buy_amt,sell_amt,reason,explain) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (d, r.get("SECURITY_CODE", ""), r.get("SECURITY_NAME_ABBR", ""),
             _fmt(r.get("CHANGE_RATE")), _fmt(r.get("BILLBOARD_NET_AMT")), _fmt(r.get("BILLBOARD_BUY_AMT")),
             _fmt(r.get("BILLBOARD_SELL_AMT")), r.get("EXPLANATION", ""), r.get("EXPLAIN", "")))
        n += cur.rowcount
    return n, dates


# ---------- 龙虎榜 ----------
def fetch_billboard(limit_days=3):
    """最近交易日龙虎榜。返回 (行数据列表)。"""
    s = _session()
    return _billboard_rows(s)


def write_billboard(db, rows, limit_days=3):
    n, dates = _write_billboard(db, rows, limit_days)
    return n, dates


# ---------- 沪深港通资金流 ----------
MUTUAL_TYPES = [("001", "北向沪股通"), ("003", "北向深股通"), ("002", "南向沪港股通"), ("004", "南向深港股通")]


def fetch_hkt_flow(days=30):
    """沪深港通每日买卖总额与净额。"""
    s = _session()
    out = []
    for mtype, label in MUTUAL_TYPES:
        rows = _dc_get(s, "RPT_MUTUAL_DEAL_HISTORY", extra={"filter": f'(MUTUAL_TYPE="{mtype}")'},
                       sorts="TRADE_DATE", stypes="-1", size=days)
        for r in rows:
            out.append((r.get("TRADE_DATE", "")[:10], label,
                        _fmt(r.get("BUY_AMT")), _fmt(r.get("SELL_AMT")), _fmt(r.get("NET_DEAL_AMT"))))
    return out


def write_hkt_flow(db, rows):
    n = 0
    for d, label, buy, sell, net in rows:
        cur = db.execute(
            "INSERT OR IGNORE INTO hkt_flow(trade_date,mutual_type,buy_amt,sell_amt,net_amt) VALUES(?,?,?,?,?)",
            (d, label, buy, sell, net))
        n += cur.rowcount
    return n


# ---------- 十大流通股东（跟踪自选股池） ----------
HOLDER_TYPE_PATTERNS = [
    ("国家队", ("汇金", "证金", "中国证券金融", "中央汇金")),
    ("社保基金", ("社保基金", "全国社保")),
    ("QFII", ("QFII", "ABU DHABI", "NORGES", "GOVERNMENT PENSION", "MORGAN STANLEY &", "GOLDMAN SACHS INTER",
              "MERRILL LYNCH INTER", "UBS AG", "CITIGROUP GLOBAL", "JP MORGAN CHASE", "BARCLAYS BANK")),
    ("北向资金", ("香港中央结算",)),
    ("保险资金", ("保险", "人寿", "财险", "再保", "养老金", "年金")),
    ("信托", ("信托",)),
    ("券商", ("证券股份", "证券资管", "证券有限公司")),
    ("私募", ("私募", "资产管理计划", "资产管理有限公司", "合伙企业(有限合伙)", "合伙企业（有限合伙）")),
    ("公募基金", ("证券投资基金", "基金管理", "交易型开放式", "ETF", "混合型", "发起式", "指数分级")),
]


def classify_holder(name: str) -> str:
    up = (name or "").upper()
    for t, pats in HOLDER_TYPE_PATTERNS:
        if any(p in up for p in pats):
            return t
    return "其他"


def _change_type(raw):
    raw = (raw or "").strip()
    if raw in ("不变", "新进", "增持", "减持", ""):
        return raw
    try:
        delta = float(raw.replace(",", ""))
        return "增持" if delta > 0 else ("减持" if delta < 0 else "不变")
    except ValueError:
        return raw


def fetch_top_holders(watchlist):
    """对自选股逐只拉取最新一期十大流通股东。返回 [(股, [行数据])]。"""
    s = _session()
    out = []
    for code, name in watchlist:
        try:
            rows = _dc_get(s, "RPT_F10_EH_FREEHOLDERS",
                           extra={"filter": f'(SECURITY_CODE="{code}")'},
                           sorts="END_DATE,HOLDER_RANK", stypes="-1,1", size=60)
        except Exception:  # noqa: BLE001
            continue
        if not rows:
            continue
        latest = max(r["END_DATE"][:10] for r in rows)
        recs = []
        for r in rows:
            if r["END_DATE"][:10] != latest:
                continue
            recs.append((
                latest, code, name or r.get("SECURITY_NAME_ABBR", ""), r.get("HOLDER_RANK"),
                r.get("HOLDER_NAME", ""), classify_holder(r.get("HOLDER_NAME", "")),
                _fmt(r.get("HOLD_NUM")), _fmt(r.get("FREE_HOLDNUM_RATIO")),
                _change_type(r.get("HOLD_NUM_CHANGE")), _fmt(r.get("CHANGE_RATIO"))))
        out.append((code, recs))
    return out


def write_top_holders(db, fetched):
    n_rows = 0
    for _, recs in fetched:
        for rec in recs:
            cur = db.execute(
                "INSERT OR IGNORE INTO top_holders(end_date,code,sec_name,holder_rank,holder_name,holder_type,"
                "hold_num,hold_ratio,change_type,change_ratio) VALUES(?,?,?,?,?,?,?,?,?,?)", rec)
            n_rows += cur.rowcount
    return n_rows


# ---------- 涨停池 / 异动 ----------
def fetch_zt_pool():
    """当日涨停池（含连板数），交易日有效。"""
    s = _session()
    today = datetime.now().strftime("%Y%m%d")
    r = s.get("https://push2ex.eastmoney.com/getTopicZTPool",
              params={"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt",
                      "Pageindex": 0, "pagesize": 320, "sort": "fbt:asc", "date": today},
              timeout=20)
    r.raise_for_status()
    pool = (r.json().get("data") or {}).get("pool") or []
    out = []
    for p in pool:
        fbt, lbt = p.get("fbt", 0) or 0, p.get("lbt", 0) or 0
        first = f"{fbt // 10000:02d}:{fbt % 10000 // 100:02d}:{fbt % 100:02d}" if fbt else ""
        last = f"{lbt // 10000:02d}:{lbt % 10000 // 100:02d}:{lbt % 100:02d}" if lbt else ""
        out.append((datetime.now().strftime("%Y-%m-%d"), str(p.get("c", "")), p.get("n", ""),
                    p.get("lbc", 1), first, last, _fmt(p.get("amount")), _fmt(p.get("ltsz"))))
    return out


def write_zt_pool(db, rows):
    n = 0
    for row in rows:
        cur = db.execute(
            "INSERT INTO zt_pool(date,code,name,lbc,first_time,last_time,amount,ltsz,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(date,code) DO UPDATE SET "
            "lbc=excluded.lbc, first_time=excluded.first_time, last_time=excluded.last_time, "
            "amount=excluded.amount, updated_at=excluded.updated_at",
            (*row, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        n += cur.rowcount
    return n
