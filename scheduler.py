"""APScheduler 自动更新：按 sources 表的 interval 定时执行各爬虫。"""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import scrapers
from db import get_db

_scheduler = None
_jobs = {}


def _job(key):
    def _run():
        import threading
        lock = _job_locks.setdefault(key, threading.Lock())
        if lock.locked():
            return  # 上一次还没跑完，跳过
        with lock:
            ok, msg, count = scrapers.run_source(key)
            print(f"[auto] {key}: {'OK' if ok else 'FAIL'} {msg}")
    return _run


_job_locks = {}


def build_jobs():
    with get_db() as db:
        rows = db.execute("SELECT key, interval_min, enabled FROM sources").fetchall()
    return [(r["key"], max(2, int(r["interval_min"] or 30))) for r in rows if r["enabled"]]


def sync_jobs():
    """根据 sources 表重建所有定时任务。"""
    global _jobs
    for key, job in _jobs.items():
        job.remove()
    _jobs = {}
    for key, minutes in build_jobs():
        _jobs[key] = _scheduler.add_job(
            _job(key), "interval", minutes=minutes, id=f"src_{key}",
            max_instances=1, coalesce=True, misfire_grace_time=120)
    # 启动后 15 秒先刷新一轮快讯
    _scheduler.add_job(_job("news"), "date",
                       run_date=datetime.now() + timedelta(seconds=15), id="boot_news")
    print(f"[scheduler] 已注册 {len(_jobs)} 个定时任务: {list(_jobs)}")


def start():
    global _scheduler
    scrapers.ensure_sources()
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    sync_jobs()
    _scheduler.start()
    print("[scheduler] started")


def shutdown():
    if _scheduler:
        _scheduler.shutdown(wait=False)
