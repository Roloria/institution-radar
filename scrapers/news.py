"""快讯/异动新闻爬虫：东方财富 7x24 + 新浪财经 7x24。直连。"""
import hashlib
import json
import re
from datetime import datetime

from .http_util import make_session
from db import get_db, upsert_news, now

# 机构关键词（新闻匹配用；可在设置里扩展）
INSTITUTION_KEYWORDS = [
    "伯克希尔", "巴菲特", "桥水", "达里奥", "文艺复兴", "西蒙斯", "城堡", "Citadel",
    "千禧年", "Millennium", "高瓴", "HHLR", "老虎基金", "老虎环球", "Tiger Global",
    "Point72", "Two Sigma", "Baupost", "潘兴广场", "Pershing", "索罗斯", "Soros",
    "Appaloosa", "德佩", "埃利奥特", "Elliott", "Coatue", "孤松", "Lone Pine",
    "贝莱德", "BlackRock", "先锋集团", "Vanguard", "富达", "Fidelity", "摩根士丹利",
    "高盛", "摩根大通", "瑞银", "淡马锡", "GIC", "挪威主权基金", "阿布扎比",
    "红杉", "IDG资本", "软银", "愿景基金", "黑石", "凯雷", "KKR", "华平", "春华资本",
    "易方达", "华夏基金", "南方基金", "嘉实基金", "广发基金", "富国基金", "招商基金",
    "社保基金", "汇金", "证金", "国家大基金", "中投公司", "宁德时代基金",
]
# 动作词
ACTION_KEYWORDS = [
    "增持", "减持", "清仓", "建仓", "加仓", "买入", "卖出", "做空", "做多",
    "举牌", "回购", "收购", "入股", "投资", "重仓", "减仓", "新进", "退出",
    "调研", "上调评级", "下调评级", "增持评级", "目标价",
]


def match_keywords(text: str):
    """返回命中的 (机构, 动作) 列表。"""
    insts = [k for k in INSTITUTION_KEYWORDS if k and k in text]
    acts = [k for k in ACTION_KEYWORDS if k and k in text]
    return insts, acts


def _hash(source, text, ts):
    return hashlib.md5(f"{source}|{text}|{ts}".encode("utf-8", "ignore")).hexdigest()


def fetch_eastmoney_fastnews():
    """东财 7x24 快讯（biz=web_724 全部频道）。"""
    s = make_session(use_proxy=False)
    r = s.get("https://np-listapi.eastmoney.com/comm/web/getFastNewsList",
              params={"client": "web", "biz": "web_724", "fastColumn": "102",
                      "sortEnd": "", "pageSize": 50, "req_trace": "1"}, timeout=20)
    r.raise_for_status()
    items = (r.json().get("data") or {}).get("fastNewsList") or []
    out = []
    for it in items:
        title = (it.get("title") or "").strip()
        summary = re.sub(r"<[^>]+>", "", it.get("summary") or "").strip()
        ts = (it.get("showTime") or it.get("time") or "")
        out.append({
            "source": "东财快讯", "title": title or summary[:40] or "(无标题)",
            "content": summary, "url": it.get("url") or it.get("webLink") or "",
            "published_at": ts.replace("T", " ")[:19],
            "hash": _hash("em", title + summary, ts),
        })
    return out


def fetch_sina_7x24():
    """新浪财经 7x24 直播。"""
    s = make_session(use_proxy=False)
    out = []
    for page in (1, 2):
        try:
            r = s.get("https://zhibo.sina.com.cn/api/zhibo/feed",
                      params={"page": page, "page_size": 50, "zhibo_id": 152, "tag_id": 0,
                              "dire": "f", "dpc": 1}, timeout=20)
            r.raise_for_status()
            feed = ((r.json().get("result") or {}).get("data") or {}).get("feed") or {}
            for it in feed.get("list") or []:
                rich = it.get("rich_text") or ""
                text = re.sub(r"<[^>]+>", "", rich).strip()
                ts = datetime.strptime(it.get("create_time", ""), "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S") \
                    if it.get("create_time") else ""
                ext = it.get("ext") or {}
                url = ext.get("url") or ""
                out.append({
                    "source": "新浪7x24", "title": text[:60] or "(快讯)",
                    "content": text, "url": url, "published_at": ts,
                    "hash": _hash("sina", text, ts),
                })
        except Exception:  # noqa: BLE001
            continue
    return out


def run_news():
    """抓取全部快讯并入库，返回 (新增数, 总数, 命中机构+动作的快讯)。"""
    all_items = []
    for fn in (fetch_eastmoney_fastnews, fetch_sina_7x24):
        try:
            all_items.extend(fn())
        except Exception as e:  # noqa: BLE001
            print(f"[news] {fn.__name__} 失败: {e}", flush=True)
    new = 0
    matched_alerts = []
    with get_db() as db:
        for it in all_items:
            text = (it.get("title") or "") + " " + (it.get("content") or "")
            insts, acts = match_keywords(text)
            it["matched"] = insts + [f"动作:{a}" for a in acts]
            if upsert_news(db, it):
                new += 1
                if insts and acts:
                    matched_alerts.append({**it, "insts": insts, "acts": acts})
    return new, len(all_items), matched_alerts
