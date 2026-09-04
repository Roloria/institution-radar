"""HTTP 会话工具：UA、代理、重试。"""
import os
import time
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
ROOT = Path(__file__).resolve().parent.parent


def load_sec_ua() -> str:
    """SEC 要求 UA 携带真实联系方式：优先环境变量 SEC_UA，其次本地 data/sec_ua.txt（不入库）。"""
    v = os.environ.get("SEC_UA", "").strip()
    if v:
        return v
    f = ROOT / "data" / "sec_ua.txt"
    if f.exists():
        v = f.read_text().strip()
        if v:
            return v
    return "InstitutionRadar/1.0 (set SEC_UA env or data/sec_ua.txt with a real contact)"


SEC_UA = load_sec_ua()


def make_session(use_proxy=False, proxy_url="", retries=2, sec_style=False):
    s = requests.Session()
    s.headers.update({"User-Agent": SEC_UA if sec_style else UA})
    if use_proxy and proxy_url:
        s.proxies = {"http": proxy_url, "https": proxy_url}
    return s


def get_with_retry(session, url, timeout=25, retries=2, **kw):
    last = None
    for i in range(retries + 1):
        try:
            r = session.get(url, timeout=timeout, **kw)
            if r.status_code in (429, 503):
                time.sleep(2 + i * 2)
                continue
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1 + i)
    raise last
