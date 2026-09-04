"""回填 13F 持仓的 ticker：
1. NASDAQ SymbolDir 尝试（现无 CUSIP 列，保留以备官方恢复）；
2. SEC company_tickers.json (cik->ticker->title)，按发行方名称规范化匹配回填。
用法: .venv/bin/python scripts/update_tickers.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from db import get_db
from scrapers.http_util import load_sec_ua

ROOT = Path(__file__).resolve().parent.parent
PROXY = {"http": "http://127.0.0.1:6152", "https": "http://127.0.0.1:6152"}


def norm_name(s: str) -> str:
    """规范化发行方名称便于匹配：大写、去标点、去公司后缀。"""
    s = re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper())
    s = re.sub(r"\b(INC|CORP|CORPORATION|LTD|LIMITED|LLC|LP|CO|COMPANY|PLC|SA|AG|NV|TR|TRUST|THE|CLASS|A|B|C|COM|NEW)\b", " ", s)
    return re.sub(r"\s+", "", s)


def fetch_sec_tickers() -> dict:
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers={"User-Agent": load_sec_ua()}, proxies=PROXY, timeout=30)
    r.raise_for_status()
    out = {}
    for v in r.json().values():
        out[norm_name(v["title"])] = v["ticker"]
    print(f"[tickers] SEC company_tickers: {len(out)} 条名称映射")
    return out


def backfill(name_map: dict):
    with get_db() as db:
        issuers = [r[0] for r in db.execute(
            "SELECT DISTINCT issuer FROM holdings WHERE issuer != '' AND "
            "(ticker IS NULL OR ticker='')").fetchall()]
        n = 0
        for issuer in issuers:
            sym = name_map.get(norm_name(issuer))
            if not sym:
                continue
            c1 = db.execute("UPDATE holdings SET ticker=? WHERE issuer=? AND (ticker IS NULL OR ticker='')",
                            (sym, issuer)).rowcount
            c2 = db.execute("UPDATE hchanges SET ticker=? WHERE issuer=? AND (ticker IS NULL OR ticker='')",
                            (sym, issuer)).rowcount
            n += c1 + c2
        # hchanges 里 issuer 可能为空的清仓行：用 cusip 从 holdings 补
        db.execute("""UPDATE hchanges SET ticker=COALESCE(
            (SELECT h.ticker FROM holdings h WHERE h.cusip=hchanges.cusip AND h.ticker!=''), '')
            WHERE (ticker IS NULL OR ticker='')""")
        remain = db.execute("SELECT COUNT(DISTINCT issuer) FROM holdings WHERE ticker IS NULL OR ticker=''").fetchone()[0]
    print(f"[tickers] 回填 {n} 行，剩余无 ticker 的发行方 {remain} 个")


def main():
    try:
        name_map = fetch_sec_tickers()
    except Exception as e:  # noqa: BLE001
        print(f"[tickers] SEC 拉取失败: {e}")
        return
    backfill(name_map)
    # 存一份规范化映射供后续新数据增量使用
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "sec_name_ticker.json").write_text(json.dumps(name_map, ensure_ascii=False))


if __name__ == "__main__":
    main()
