"""数据源连通性探测：逐个验证爬虫依赖的 API 是否可用。"""
import json
import sys

import requests

UA = {"User-Agent": "InstitutionRadar/1.0 (set-your-contact)"}
PROXY = {"http": "http://127.0.0.1:6152", "https": "http://127.0.0.1:6152"}


def probe(name, url, use_proxy=False, headers=None, params=None, check=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    try:
        r = requests.get(url, headers=h, params=params, timeout=15,
                         proxies=PROXY if use_proxy else None)
        ok = r.status_code == 200
        detail = f"HTTP {r.status_code}"
        if ok and check:
            try:
                ok, detail = check(r)
            except Exception as e:
                ok, detail = False, f"check error: {e}"
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ({detail})")
        return r if ok else None
    except Exception as e:
        print(f"FAIL  {name}  ({type(e).__name__}: {str(e)[:120]})")
        return None


def j(r):
    return r.json()


print("== SEC EDGAR (proxy) ==")
r = probe("submissions(berkshire)", "https://data.sec.gov/submissions/CIK0001067983.json",
          use_proxy=True, check=lambda r: (True, f"{len(j(r).get('filings',{}).get('recent',{}).get('form',[]))} filings") if isinstance(j(r), dict) else (False, "bad"))
if r:
    recent = j(r)["filings"]["recent"]
    forms = [(f, a, d) for f, a, d in zip(recent["form"], recent["accessionNumber"], recent["filingDate"]) if f.startswith("13F")]
    print("   recent 13F:", forms[:2])

probe("company_tickers", "https://www.sec.gov/files/company_tickers.json", use_proxy=True,
      check=lambda r: (True, f"{len(j(r))} tickers"))

print("\n== 东方财富 datacenter ==")
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def dc_check(r):
    d = j(r)
    n = (d.get("result") or {}).get("count", 0)
    return (n > 0, f"count={n}"),


def _dc(report, extra=None, sorts="UPDATE_DATE,SECURITY_CODE", stypes="-1,-1"):
    p = {"reportName": report, "columns": "ALL", "pageSize": 5, "pageNumber": 1,
         "sortColumns": sorts, "sortTypes": stypes, "source": "WEB", "client": "WEB"}
    if extra:
        p.update(extra)
    return probe(report, DC, params=p, check=lambda r: (bool((j(r).get("result") or {}).get("data")), f"rows={len((j(r).get('result') or {}).get('data') or [])}"))


_dc("RPT_DAILYBILLBOARD_DETAILSNEW", sorts="TRADE_DATE,SECURITY_CODE", stypes="-1,-1")
_dc("RPT_MUTUAL_DEAL_HISTORY", extra={"filter": '(MUTUAL_TYPE="001")'}, sorts="TRADE_DATE", stypes="-1")
_dc("RPT_RZRQ_LSHJ", sorts="dim_date", stypes="-1")
_dc("RPT_MAIN_ORGHOLDDETAILS", sorts="END_DATE", stypes="-1")
_dc("RPT_SHARE_HOLDER_INCREASE", sorts="CHANGE_DATE", stypes="-1")
_dc("RPT_INCREASE_DECREASE_HOLDERNEW", sorts="CHANGE_DATE", stypes="-1")
_dc("RPT_CUSTOM_HOLDER_10FREENEW", sorts="END_DATE", stypes="-1")

print("\n== 新闻快讯 ==")
probe("eastmoney-fastnews", "https://np-listapi.eastmoney.com/comm/web/getFastNewsList",
      params={"client": "web", "biz": "web_724", "fastColumn": "102", "sortEnd": "", "pageSize": 20, "req_trace": "1"},
      check=lambda r: (bool(j(r).get("data", {}).get("fastNewsList")), f"items={len(j(r).get('data',{}).get('fastNewsList') or [])}"))
probe("sina-7x24", "https://zhibo.sina.com.cn/api/zhibo/feed",
      params={"page": 1, "page_size": 20, "zhibo_id": 152, "tag_id": 0, "dire": "f", "dpc": 1},
      check=lambda r: (bool(j(r).get("result", {}).get("data", {}).get("feed", {}).get("list")), "sina feed"))
