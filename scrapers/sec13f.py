"""SEC 13F 爬虫：全球主流机构的季度持仓 + 环比变动。

数据源: SEC EDGAR submissions API（需代理）。策略:
1. 对机构清单逐一取 filings，筛 13F-HR，取最近两个报告期；
2. 解析 information table XML 入库 holdings；
3. 与上一季度持仓 diff 生成 hchanges（新增/清仓/增持/减持）。
"""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from .http_util import get_with_retry, make_session

# 候选机构: (英文名关键词用于校验CIK, CIK候选, 中文名, 备注)
CANDIDATE_INSTITUTIONS = [
    ("BERKSHIRE HATHAWAY", "1067983", "伯克希尔·哈撒韦", "巴菲特"),
    ("RENAISSANCE TECHNOLOGIES", "1037389", "文艺复兴科技", "Jim Simons"),
    ("BRIDGEWATER ASSOCIATES", "1350694", "桥水基金", "Ray Dalio"),
    ("CITADEL ADVISORS", "1166559", "城堡投资", "Ken Griffin"),
    ("MILLENNIUM MANAGEMENT", "1273087", "千禧年基金", "Israel Englander"),
    ("HHLR ADVISORS", "1762304", "高瓴/HHLR", "张磊(高瓴美股主体)"),
    ("TIGER GLOBAL MANAGEMENT", "1167483", "老虎环球基金", "Chase Coleman"),
    ("POINT72 ASSET MANAGEMENT", "1603466", "Point72", "Steve Cohen"),
    ("TWO SIGMA INVESTMENTS", "1179392", "Two Sigma", "量化双雄"),
    ("BAUPOST GROUP", "1061768", "Baupost", "Seth Klarman"),
    ("PERSHING SQUARE", "1336528", "潘兴广场", "Bill Ackman"),
    ("SOROS FUND MANAGEMENT", "1029160", "索罗斯基金", "George Soros"),
    ("APPALOOSA MANAGEMENT", "1006438", "Appaloosa", "David Tepper"),
    ("ELLIOTT INVESTMENT MANAGEMENT", "1791786", "埃利奥特", "Paul Singer"),
    ("COATUE MANAGEMENT", "1135730", "Coatue", "Philippe Laffont,重仓中概"),
    ("LONE PINE CAPITAL", "1061165", "孤松资本", "Stephen Mandel"),
    ("FMR LLC", "315066", "富达 FMR", "Fidelity 主动管理主体"),
    ("NORGES BANK", "1374170", "挪威央行投资管理", "主权基金"),
]

# 常见大票 CUSIP -> ticker（用于展示）
CUSIP_TICKER = {
    "037833100": "AAPL", "594918104": "MSFT", "670666104": "NVDA", "02079K305": "GOOGL",
    "02079K107": "GOOG", "023135106": "AMZN", "30303M102": "META", "88160R101": "TSLA",
    "084670702": "BRK.B", "11135F101": "AVGO", "532457108": "LLY", "46647H105": "JPM",
    "92826C839": "V", "30231G102": "XOM", "91324P102": "UNH", "227966105": "COST",
    "375558103": "PG", "037833E10": "AAPL", "254687106": "DIS", "026659101": "AMD",
    "09062X108": "BABA", "20030N101": "PDD", "G7090K109": "BIDU", "09972D103": "NTES",
    "62914V105": "NIO", "03076C106": "BILI", "00727P102": "TCOM", "031162100": "ASML",
    "02209S108": "AUDC", "45767V100": "INTC", "032097108": "ABNB", "88579Y101": "UBER",
    "458140100": "NFLX", "68389X105": "ORCL", "02005N100": "ALLY", "031100100": "AXP",
    "949746101": "WFC", "060505104": "BAC", "172967424": "C", "459200101": "IBM",
    "25746U109": "DAL", "293792107": "EA", "34959E109": "FTNT", "501044103": "GM",
    "68468J108": "PAYC", "742718109": "KR", "98956V105": "ZM", "98620K101": "ZNGA",
}


def quarter_of_report_date(d: str) -> str:
    """13F reportDate(YYYY-MM-DD) -> 2026Q2"""
    date = datetime.strptime(d[:10], "%Y-%m-%d")
    return f"{date.year}Q{(date.month - 1) // 3 + 1}"


def normalize_values(rows, total):
    """2023-01 之前 13F 的 value 单位是千美元，之后是美元。"""
    if total and total < 5e9:
        for r in rows:
            r["value_usd"] *= 1000.0


def parse_infotable(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)

    def local(e):
        return e.tag.split("}")[-1]

    out = []
    for e in root.iter():
        if local(e) != "infoTable":
            continue
        d = {}
        for c in e.iter():
            if len(list(c)) == 0:
                d.setdefault(local(c), (c.text or "").strip())
        po = ""
        for c in e:
            if local(c) == "putCall":
                po = (c.text or "").strip()
        shares = d.get("sshPrnamt", "0")
        out.append({
            "cusip": d.get("cusip", ""),
            "issuer": d.get("nameOfIssuer", ""),
            "class": d.get("titleOfClass", ""),
            "put_call": po,
            "value_usd": float(d.get("value", 0) or 0),
            "shares": float(shares or 0),
        })
    return out


class Sec13FScraper:
    def __init__(self, db, proxy_url="", logger=print):
        self.db = db
        self.proxy_url = proxy_url
        self.log = logger
        self.session = make_session(use_proxy=bool(proxy_url), proxy_url=proxy_url, sec_style=True)

    # ---- 机构清单 ----
    def ensure_institutions(self):
        from db import get_db
        with get_db() as db:
            for kw, cik, cn, note in CANDIDATE_INSTITUTIONS:
                db.execute(
                    "INSERT INTO institutions(name,name_cn,category,cik,region,note) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(name, category) DO UPDATE SET cik=excluded.cik, name_cn=excluded.name_cn, "
                    "note=excluded.note", (kw.title(), cn, "global_13f", cik, "US", note))

    def resolve_institutions(self):
        """校验 CIK 是否与机构名匹配，不匹配时用 EDGAR 全文搜索自动修正。"""
        from db import get_db
        stats = {"ok": 0, "fixed": [], "bad": []}
        with get_db() as db:
            insts = db.execute("SELECT id,name,cik FROM institutions WHERE category='global_13f'").fetchall()
        for it in insts:
            kw = it["name"].upper()
            name = ""
            try:
                r = get_with_retry(self.session, f"https://data.sec.gov/submissions/CIK{int(it['cik']):010d}.json", retries=1)
                name = (r.json().get("name") or "").upper()
            except Exception:  # noqa: BLE001
                name = ""
            if kw.split()[0] in name:
                stats["ok"] += 1
                continue
            fixed = self._cik_via_fts(kw)
            if fixed:
                with get_db() as db:
                    db.execute("UPDATE institutions SET cik=? WHERE id=?", (fixed, it["id"]))
                stats["fixed"].append((it["name"], it["cik"], fixed))
            else:
                stats["bad"].append((it["name"], name or "请求失败"))
        return stats

    def _cik_via_fts(self, kw):
        """按机构名做全文搜索，返回匹配的 CIK 或 None。"""
        try:
            r = get_with_retry(self.session,
                               "https://efts.sec.gov/LATEST/search-index?q=" +
                               requests.utils.requote_uri(f'"{kw}"') + "&forms=13F-HR", retries=1)
            for h in r.json().get("hits", {}).get("hits", []):
                src = h.get("_source", {})
                names = [n.upper() for n in (src.get("display_names") or [])]
                ciks = src.get("ciks") or []
                if ciks and any(kw in n for n in names):
                    return ciks[0]
        except Exception:  # noqa: BLE001
            pass
        return None

    # ---- 单机构抓取 ----
    def fetch_institution(self, inst, max_filings=2):
        """抓单个机构最近 max_filings 期 13F，返回 (新增期数, 明细数)。"""
        from db import get_db, now
        cik = f"{int(inst['cik']):010d}"
        r = get_with_retry(self.session, f"https://data.sec.gov/submissions/CIK{cik}.json")
        meta = r.json()
        recent = meta["filings"]["recent"]
        pairs = [(f, a, d, rd) for f, a, d, rd in
                 zip(recent["form"], recent["accessionNumber"], recent["filingDate"], recent["reportDate"])
                 if f == "13F-HR" and rd]
        seen_quarters = set()
        new_quarters, detail_count = [], 0
        for form, acc, fdate, rdate in pairs[:max_filings]:
            quarter = quarter_of_report_date(rdate)
            if quarter in seen_quarters:
                continue
            seen_quarters.add(quarter)
            acc_nodash = acc.replace("-", "")
            base = f"https://www.sec.gov/Archives/edgar/data/{int(inst['cik'])}/{acc_nodash}"
            idx = get_with_retry(self.session, f"{base}/index.json").json()
            xmls = [it["name"] for it in idx["directory"]["item"]
                    if it["name"].lower().endswith(".xml") and "primary_doc" not in it["name"].lower()
                    and not it["name"].endswith(".xsd")]
            if not xmls:
                continue
            rows = None
            for xn in xmls:
                try:
                    rows = parse_infotable(get_with_retry(self.session, f"{base}/{xn}").content)
                except ET.ParseError:
                    rows = None
                if rows:
                    break
            if not rows:
                continue
            total = sum(x["value_usd"] for x in rows)
            normalize_values(rows, total)
            total = sum(x["value_usd"] for x in rows)
            with get_db() as db:
                cur = db.execute(
                    "INSERT OR IGNORE INTO filings(accession,inst_id,quarter,filed_date,total_value,holdings_count,fetched_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (acc, inst["id"], quarter, fdate, total, len(rows), now()))
                if cur.rowcount == 0:
                    continue  # 已入库过
                for x in rows:
                    x["ticker"] = CUSIP_TICKER.get(x["cusip"], "")
                    db.execute(
                        "INSERT OR IGNORE INTO holdings(inst_id,quarter,cusip,issuer,ticker,class,put_call,value_usd,shares) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (inst["id"], quarter, x["cusip"], x["issuer"], x["ticker"], x["class"],
                         x["put_call"], x["value_usd"], x["shares"]))
            new_quarters.append(quarter)
            detail_count += len(rows)
            self.log(f"  {inst['name_cn'] or inst['name']} {quarter}: {len(rows)} 笔持仓, 总值 ${total/1e9:.1f}B")
        return new_quarters, detail_count

    # ---- 变动计算 ----
    def compute_changes(self, inst_id=None):
        """对每个机构：最近两期 diff。返回生成的变动条数。"""
        from db import get_db, now
        n = 0
        with get_db() as db:
            inst_ids = ([inst_id] if inst_id else
                        [r[0] for r in db.execute("SELECT id FROM institutions WHERE category='global_13f'")])
        for iid in inst_ids:
            with get_db() as db:
                qs = [r[0] for r in db.execute(
                    "SELECT DISTINCT quarter FROM holdings WHERE inst_id=? ORDER BY quarter DESC LIMIT 2", (iid,))]
                if len(qs) < 1:
                    continue
                cur_rows = db.execute(
                    "SELECT cusip,issuer,ticker,class,put_call,value_usd,shares FROM holdings "
                    "WHERE inst_id=? AND quarter=?", (iid, qs[0])).fetchall()
                prev = {}
                if len(qs) == 2:
                    prev = {r["cusip"] + "|" + r["put_call"]: r for r in db.execute(
                        "SELECT cusip,put_call,value_usd,shares FROM holdings WHERE inst_id=? AND quarter=?",
                        (iid, qs[1])).fetchall()}
            rows = [dict(r) for r in cur_rows]
            for r in rows:
                key = r["cusip"] + "|" + r["put_call"]
                p = prev.pop(key, None)
                if p is None:
                    ctype, pct = "新增", 100.0
                elif r["value_usd"] > p["value_usd"]:
                    ctype = "增持"
                    pct = (r["value_usd"] / p["value_usd"] - 1) * 100 if p["value_usd"] else 0
                elif r["value_usd"] < p["value_usd"]:
                    ctype = "减持"
                    pct = (r["value_usd"] / p["value_usd"] - 1) * 100 if p["value_usd"] else -100
                else:
                    ctype, pct = "不变", 0.0
                self._save_change(iid, qs[0], r, ctype, pct,
                                  p["value_usd"] if p else 0, p["shares"] if p else 0)
                n += 1
            # 上季有、本季没有 -> 清仓
            for key, p in prev.items():
                if p["value_usd"] <= 0:
                    continue
                self._save_change(iid, qs[0], {"cusip": p["cusip"], "issuer": "", "ticker": "",
                                               "class": "", "put_call": p["put_call"],
                                               "value_usd": 0, "shares": 0},
                                  "清仓", -100.0, p["value_usd"], p["shares"])
                n += 1
        return n

    def _save_change(self, inst_id, quarter, r, ctype, pct, prev_value, prev_shares):
        from db import get_db, now
        with get_db() as db:
            db.execute(
                "INSERT OR REPLACE INTO hchanges(inst_id,quarter,cusip,issuer,ticker,change_type,"
                "prev_value,curr_value,delta_value,pct,shares_prev,shares_curr,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (inst_id, quarter, r["cusip"], r["issuer"] or self._issuer_lookup(inst_id, r["cusip"]),
                 r["ticker"], ctype, prev_value, r["value_usd"], r["value_usd"] - prev_value,
                 round(pct, 2), prev_shares, r["shares"], now()))

    def _issuer_lookup(self, inst_id, cusip):
        from db import get_db
        with get_db() as db:
            r = db.execute("SELECT issuer,ticker FROM holdings WHERE inst_id=? AND cusip=? ORDER BY id DESC LIMIT 1",
                           (inst_id, cusip)).fetchone()
            return r["issuer"] if r else cusip

    def run(self, max_filings=2):
        """全量跑：所有 13F 机构。返回 (机构数, 新期数, 变动数)。"""
        from db import get_db
        self.ensure_institutions()
        resolved = self.resolve_institutions()
        if resolved["fixed"]:
            self.log(f"  CIK 自动修正: {resolved['fixed']}")
        if resolved["bad"]:
            self.log(f"  CIK 未能解析: {resolved['bad']}")
        with get_db() as db:
            insts = [dict(r) for r in db.execute(
                "SELECT * FROM institutions WHERE category='global_13f' AND followed=1")]
        nq_total, n_changes, ok = 0, 0, 0
        for it in insts:
            try:
                nq, _ = self.fetch_institution(it, max_filings=max_filings)
                nq_total += len(nq)
                ok += 1
            except Exception as e:  # noqa: BLE001
                self.log(f"  [13F] {it['name']} 失败: {e}")
        n_changes = self.compute_changes()
        return ok, nq_total, n_changes
