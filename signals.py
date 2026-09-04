"""机构共识信号：跨机构聚合同季同向变动（对标 Dataroma 个股透视 / WhaleWisdom Double-down）。"""
from db import get_db


def compute_consensus(quarter=None):
    """聚合最新季度（或指定季度）全部 13F 变动，按标的分组。

    返回 (quarter, items)，items 按 净买入机构数、|合计增减| 排序：
      {key, issuer, tickers, cusips, buy, sell, new, exit, net, delta, value,
       score, insts: [{name, change_type, delta, pct, value}]}
    """
    with get_db() as db:
        if not quarter:
            quarter = db.execute("SELECT MAX(quarter) m FROM hchanges").fetchone()["m"]
        rows = db.execute(
            "SELECT h.cusip, h.issuer, h.ticker, h.change_type, h.delta_value, h.pct, h.curr_value, "
            "h.shares_curr, i.name_cn, i.name AS inst_name "
            "FROM hchanges h JOIN institutions i ON i.id=h.inst_id "
            "WHERE h.quarter=? AND h.change_type != '不变' AND i.followed=1", (quarter,)).fetchall()

    groups = {}
    for r in rows:
        issuer = r["issuer"] or r["cusip"]
        # 按 (issuer, cusip) 分组 = 每只证券一组，避免 ETF 发行方(如 ISHARES TR)
        # 把几百只不同 ETF 聚成假共识；ALPHABET 的 GOOG/GOOGL 两种股票也自然分开
        key = (issuer, r["cusip"])
        g = groups.setdefault(key, {
            "issuer": issuer, "tickers": set(), "cusips": set(),
            "buy": 0, "sell": 0, "new": 0, "exit": 0, "delta": 0.0, "value": 0.0, "insts": []})
        if r["ticker"]:
            g["tickers"].add(r["ticker"])
        g["cusips"].add(r["cusip"])
        ct = r["change_type"]
        g["insts"].append({"name": r["name_cn"] or r["inst_name"], "change_type": ct,
                           "delta": r["delta_value"] or 0, "pct": r["pct"],
                           "value": r["curr_value"] or 0})
        if ct == "新增":
            g["new"] += 1
            g["buy"] += 1
        elif ct == "增持":
            g["buy"] += 1
        elif ct == "清仓":
            g["exit"] += 1
            g["sell"] += 1
        elif ct == "减持":
            g["sell"] += 1
        g["delta"] += r["delta_value"] or 0
        g["value"] = max(g["value"], r["curr_value"] or 0)

    items = []
    for (issuer, cusip), g in groups.items():
        g["key"] = issuer
        g["tickers"] = sorted(g["tickers"])
        g["cusips"] = sorted(g["cusips"])
        g["net"] = g["buy"] - g["sell"]
        # 共识分 = 净机构数为主导，叠加资金增减量级（十亿美元封顶 3 分）
        g["score"] = round(g["net"] * 2 + (1 if g["delta"] > 0 else -1) * min(abs(g["delta"]) / 1e9, 3), 2)
        g["insts"].sort(key=lambda x: -abs(x["delta"]))
        items.append(g)
    items.sort(key=lambda x: (-x["net"], -abs(x["delta"])))
    return quarter, items


def consensus_alerts():
    """≥3 家机构同向买入(净≥2) 视为强共识告警；≥4 家为关键级别。"""
    made = 0
    try:
        quarter, items = compute_consensus()
    except Exception:  # noqa: BLE001
        return 0
    for g in items:
        if not (g["buy"] >= 5 and g["net"] >= 4 and g["delta"] > 0):
            continue
        if g["value"] < 1.5e9:  # 至少一家持仓 ≥ $15 亿，过滤小票噪音
            continue
        title = f"[共识] {g['buy']} 家机构净买入 {g['issuer']}"
        with get_db() as db:
            exists = db.execute("SELECT 1 FROM alerts WHERE kind='consensus' AND title=? AND detail LIKE ?",
                                (title, f"%{quarter}%")).fetchone()
        if exists:
            continue
        names = "、".join(x["name"] for x in g["insts"] if x["change_type"] in ("新增", "增持"))[:80]
        detail = (f"{quarter} 共识买入: 新增{g['new']} 增持{g['buy'] - g['new']} 减持{g['sell'] - g['exit']} "
                  f"清仓{g['exit']} | 合计增持 ${g['delta']/1e8:.1f}亿 | {names}")
        level = "critical" if g["buy"] >= 4 else "important"
        from scrapers.alerting import save_alert
        save_alert("consensus", title, detail, level)
        made += 1
    return made
