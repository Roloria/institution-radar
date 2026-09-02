"""第二轮探测：两融/十大流通股东/增减持/龙虎榜席位/涨停池 的正确 reportName。"""
import json

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def dc(report, extra=None, sorts="1", stypes="-1"):
    p = {"reportName": report, "columns": "ALL", "pageSize": 3, "pageNumber": 1,
         "sortColumns": sorts, "sortTypes": stypes, "source": "WEB", "client": "WEB"}
    if extra:
        p.update(extra)
    try:
        r = requests.get(DC, headers=UA, params=p, timeout=15)
        d = r.json()
        res = d.get("result") or {}
        rows = res.get("data") or []
        print(f"{'PASS' if rows else 'FAIL'}  {report}  rows={len(rows)} count={res.get('count')}")
        if rows:
            print("   keys:", sorted(rows[0].keys())[:18])
            print("   sample:", json.dumps(rows[0], ensure_ascii=False)[:300])
        return rows
    except Exception as e:
        print(f"ERR   {report}  {type(e).__name__}: {str(e)[:100]}")
        return []


dc("RPTA_WEB_RZRQ_ZSLSHJ", sorts="dim_date")
dc("RPTA_WEB_RZRQ_LSHJ", sorts="dim_date")
dc("RPT_F10_EH_FREEHOLDERS", extra={"filter": '(SECURITY_CODE="600519")'}, sorts="END_DATE")
dc("RPT_MAIN_ORGHOLDDETAILS", extra={"filter": '(SECURITY_CODE="600519")'}, sorts="END_DATE")
dc("RPT_ORGHOLDDETAILS", extra={"filter": '(SECURITY_CODE="600519")'}, sorts="END_DATE")
dc("RPT_INCREASE_STOCK_HOLDER", sorts="CHANGE_DATE")
dc("RPT_SHAREHOLDERS_INCREASE", sorts="CHANGE_DATE")
dc("RPT_ORGANIZATION_SURVEY", sorts="RECEIVE_START_DATE")

bt = dc("RPT_DAILYBILLBOARD_DETAILSNEW", sorts="TRADE_DATE,SECURITY_CODE", stypes="-1,-1")
if bt:
    d = bt[0].get("TRADE_DATE", "")[:10]
    print("\nbillboard trade_date =", d)
    dc("RPT_BILLBOARD_TRADEDETAILSNEW", extra={"filter": f'(TRADE_DATE=\'{d}\')'}, sorts="TRADE_DATE")

print("\n== 涨停池 push2ex ==")
try:
    r = requests.get("https://push2ex.eastmoney.com/getTopicZTPool",
                     params={"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt",
                             "Pageindex": 0, "pagesize": 5, "sort": "fbt:asc", "date": "20260902"},
                     headers=UA, timeout=15)
    pool = (r.json().get("data") or {}).get("pool") or []
    print("PASS  ZTPool" if pool else "FAIL  ZTPool (可能非交易日)", f"n={len(pool)}")
    if pool:
        print("   sample:", json.dumps(pool[0], ensure_ascii=False)[:200])
except Exception as e:
    print("ERR   ZTPool", e)
