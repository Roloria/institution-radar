"""第三轮探测：EDGAR 全文搜索解析 13F 机构 CIK + 解析 infotable 持仓明细。"""
import re
import xml.etree.ElementTree as ET

import requests

S = requests.Session()
S.headers.update({"User-Agent": "InstitutionRadar/1.0 (set-your-contact)"})
S.proxies = {"http": "http://127.0.0.1:6152", "https": "http://127.0.0.1:6152"}

print("== EDGAR FTS entity search ==")
for q in ["Bridgewater", "Hillhouse", "Tiger Global", "Millennium Management"]:
    try:
        r = S.get("https://efts.sec.gov/LATEST/search-index?q=" + requests.utils.requote_uri(f'"{q}"') + "&forms=13F-HR", timeout=20)
        d = r.json()
        hits = d.get("hits", {}).get("hits", [])
        ciks = sorted({(h.get("_source", {}).get("ciks") or [None])[0] for h in hits})[:4]
        names = sorted({h.get("_source", {}).get("display_names", [None])[0] for h in hits})[:3]
        print(f"  {q}: hits={d.get('hits',{}).get('total',{}).get('value')} ciks={ciks} names={names}")
    except Exception as e:
        print(f"  {q}: ERR {type(e).__name__} {str(e)[:80]}")

print("\n== Berkshire latest 13F infotable ==")
r = S.get("https://www.sec.gov/Archives/edgar/data/1067983/000119312526352200/index.json", timeout=20)
items = r.json()["directory"]["item"]
for it in items:
    print("  file:", it["name"], it.get("size"))
xmls = [it["name"] for it in items if it["name"].lower().endswith(".xml") and "infotable" in it["name"].lower() or it["name"].lower().endswith("infotable.xml")]
if not xmls:
    xmls = [it["name"] for it in items if it["name"].lower().endswith(".xml") and it["name"].lower() not in ("primary_doc.xml",)]
print("  chosen:", xmls[:2])
xml_name = xmls[0]
r = S.get(f"https://www.sec.gov/Archives/edgar/data/1067983/000119312526352200/{xml_name}", timeout=30)
r.raise_for_status()
root = ET.fromstring(r.content)
tag = lambda e, t: re.sub(r"^\{.*?\}", "", e.tag) == t
rows = [e for e in root.iter() if tag(e, "infoTable")]
print(f"  infoTable count: {len(rows)}")


def gv(e, t):
    for c in e:
        if tag(c, t):
            return c.text
    return None


first = rows[0]
print("  sample:", gv(first, "nameOfIssuer"), gv(first, "titleOfClass"), gv(first, "cusip"),
      "value=", gv(first, "value"), "sh=", gv([c for c in first if tag(c, "shrsOrPrnAmt")][0], "sshPrnamt"))
tot = sum(int(gv(e, "value")) for e in rows)
print(f"  total value(USD k): {tot:,}")
tops = sorted(((gv(e, "nameOfIssuer"), int(gv(e, "value"))) for e in rows), key=lambda x: -x[1])[:5]
print("  top5:", tops)
