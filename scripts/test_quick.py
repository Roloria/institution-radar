"""快速冒烟测试：逐个小范围运行各爬虫，验证入库。"""
import sys
import time

sys.path.insert(0, ".")

import db as store
import scrapers

store.init_db()
scrapers.ensure_sources()

t0 = time.time()
ok, msg, n = scrapers.run_source("news")
print(f"news: ok={ok} {msg}  ({time.time()-t0:.1f}s)")

t0 = time.time()
ok, msg, n = scrapers.run_source("billboard")
print(f"billboard: ok={ok} {msg}  ({time.time()-t0:.1f}s)")

t0 = time.time()
ok, msg, n = scrapers.run_source("hkt_flow")
print(f"hkt_flow: ok={ok} {msg}  ({time.time()-t0:.1f}s)")

t0 = time.time()
ok, msg, n = scrapers.run_source("zt_pool")
print(f"zt_pool: ok={ok} {msg}  ({time.time()-t0:.1f}s)")

t0 = time.time()
with store.get_db() as db:
    wl = [("600519", "贵州茅台"), ("300750", "宁德时代")]
ok, msg, n = scrapers.run_source("top_holders")
print(f"top_holders: ok={ok} {msg}  ({time.time()-t0:.1f}s)")

t0 = time.time()
ok, msg, n = scrapers.run_source("seed_billboard_history")
print(f"billboard_history: ok={ok} {msg}  ({time.time()-t0:.1f}s)")

print("\n--- 库内数据 ---")
with store.get_db() as db:
    for t in ("news", "dt_billboard", "hkt_flow", "zt_pool", "top_holders"):
        print(t, db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
