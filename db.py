"""SQLite 数据层：建表、连接、通用增删改查。"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "instmon.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS institutions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  name_cn TEXT DEFAULT '',
  category TEXT NOT NULL DEFAULT 'global_13f',  -- global_13f / domestic
  cik TEXT DEFAULT '',
  region TEXT DEFAULT 'US',
  followed INTEGER DEFAULT 1,
  note TEXT DEFAULT '',
  UNIQUE(name, category)
);

CREATE TABLE IF NOT EXISTS filings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inst_id INTEGER NOT NULL REFERENCES institutions(id),
  accession TEXT UNIQUE NOT NULL,
  quarter TEXT NOT NULL,
  filed_date TEXT,
  total_value REAL DEFAULT 0,
  holdings_count INTEGER DEFAULT 0,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS holdings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inst_id INTEGER NOT NULL REFERENCES institutions(id),
  quarter TEXT NOT NULL,
  cusip TEXT NOT NULL,
  issuer TEXT NOT NULL,
  ticker TEXT DEFAULT '',
  class TEXT DEFAULT '',
  put_call TEXT DEFAULT '',
  value_usd REAL NOT NULL,
  shares REAL DEFAULT 0,
  UNIQUE(inst_id, quarter, cusip, put_call)
);

CREATE TABLE IF NOT EXISTS hchanges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inst_id INTEGER NOT NULL REFERENCES institutions(id),
  quarter TEXT NOT NULL,
  cusip TEXT NOT NULL,
  issuer TEXT NOT NULL,
  ticker TEXT DEFAULT '',
  change_type TEXT NOT NULL,          -- 新增 / 清仓 / 增持 / 减持 / 不变
  prev_value REAL DEFAULT 0,
  curr_value REAL DEFAULT 0,
  delta_value REAL DEFAULT 0,
  pct REAL DEFAULT 0,
  shares_prev REAL DEFAULT 0,
  shares_curr REAL DEFAULT 0,
  created_at TEXT,
  UNIQUE(inst_id, quarter, cusip, change_type)
);

CREATE TABLE IF NOT EXISTS news (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hash TEXT UNIQUE NOT NULL,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT DEFAULT '',
  url TEXT DEFAULT '',
  published_at TEXT,
  matched TEXT DEFAULT '',            -- JSON: 匹配到的机构/关键词
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_pub ON news(published_at DESC);

CREATE TABLE IF NOT EXISTS dt_billboard (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  change_rate REAL,
  net_amt REAL,
  buy_amt REAL,
  sell_amt REAL,
  reason TEXT DEFAULT '',
  explain TEXT DEFAULT '',
  UNIQUE(trade_date, code, reason)
);

CREATE TABLE IF NOT EXISTS hkt_flow (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_date TEXT NOT NULL,
  mutual_type TEXT NOT NULL,          -- 北向合计 / 南向合计 ...
  buy_amt REAL, sell_amt REAL, net_amt REAL,
  UNIQUE(trade_date, mutual_type)
);

CREATE TABLE IF NOT EXISTS top_holders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  end_date TEXT NOT NULL,
  code TEXT NOT NULL,
  sec_name TEXT DEFAULT '',
  holder_rank INTEGER,
  holder_name TEXT NOT NULL,
  holder_type TEXT DEFAULT '',
  hold_num REAL,
  hold_ratio REAL,
  change_type TEXT DEFAULT '',        -- 新进 / 增持 / 减持 / 不变
  change_ratio REAL,
  UNIQUE(end_date, code, holder_name)
);

CREATE TABLE IF NOT EXISTS zt_pool (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT DEFAULT '',
  lbc INTEGER DEFAULT 1,              -- 连板数
  first_time TEXT,
  last_time TEXT,
  amount REAL,
  ltsz REAL,
  updated_at TEXT,
  UNIQUE(date, code)
);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  level TEXT DEFAULT 'info',          -- info / important / critical
  kind TEXT NOT NULL,                 -- news_13f / holding / holder / news_kw / system
  title TEXT NOT NULL,
  detail TEXT DEFAULT '',
  link TEXT DEFAULT '',
  pushed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  interval_min INTEGER DEFAULT 30,
  enabled INTEGER DEFAULT 1,
  last_run TEXT,
  last_status TEXT DEFAULT '',        -- ok / fail / never
  last_msg TEXT DEFAULT '',
  last_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
  code TEXT PRIMARY KEY,
  name TEXT DEFAULT '',
  added_at TEXT
);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def get_setting(key, default=""):
    with get_db() as db:
        r = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_setting(key, value):
    with get_db() as db:
        db.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value) if not isinstance(value, str) else value))


def get_setting_json(key, default=None):
    v = get_setting(key)
    if not v:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


def upsert_news(db, item: dict) -> bool:
    """插入新闻，重复返回 False。"""
    cur = db.execute(
        "INSERT OR IGNORE INTO news(hash,source,title,content,url,published_at,matched,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (item["hash"], item["source"], item["title"], item.get("content", ""),
         item.get("url", ""), item.get("published_at", ""), json.dumps(item.get("matched", []), ensure_ascii=False), now()))
    return cur.rowcount > 0
