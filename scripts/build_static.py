"""生成公开静态快照站（GitHub Pages 用）——与本地 SPA 完全同构。

复用本地同一套 index.html / app.css / app.js（body 标记 data-static="1" 进入只读模式），
数据源从 /api/* 换成 data/*.json（API 响应形状一致，前端过滤逻辑复用）。
用法: .venv/bin/python scripts/build_static.py
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def api_json(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path}: HTTP {r.status_code}"
    return r.get_json()


def export_sql_extras():
    """导出无法通过分页 API 一次拿到的大表与按日期分组数据。"""
    import db as store

    out = {}
    with store.get_db() as db:
        # 全量持仓变动（最近两期 × 全部机构，与 /api/holdings/changes 行形状一致）
        rows = store.rows_to_dicts(db.execute(
            "SELECT h.inst_id, h.quarter, h.cusip, h.issuer, h.ticker, h.change_type, h.pct, "
            "h.prev_value, h.curr_value, h.delta_value, h.shares_prev, h.shares_curr, "
            "i.name_cn, i.name AS inst_name FROM hchanges h JOIN institutions i ON i.id=h.inst_id"))
        out["changes"] = rows

        # 各机构可用季度
        all_q = [r[0] for r in db.execute("SELECT DISTINCT quarter FROM hchanges ORDER BY quarter DESC")]
        by_inst = {}
        for r in db.execute("SELECT DISTINCT inst_id, quarter FROM hchanges"):
            by_inst.setdefault(str(r[0]), []).append(r[1])
        for v in by_inst.values():
            v.sort(reverse=True)
        out["quarters"] = {"all": all_q, "byInst": by_inst}

        # 各机构最新一期持仓 top500（形状同 /api/holdings/current）
        hc = {"byInst": {}}
        inst_ids = [r[0] for r in db.execute("SELECT id FROM institutions WHERE category='global_13f'")]
        for iid in inst_ids:
            q = db.execute("SELECT MAX(quarter) m FROM holdings WHERE inst_id=?", (iid,)).fetchone()["m"]
            hrows = store.rows_to_dicts(db.execute(
                "SELECT * FROM holdings WHERE inst_id=? AND quarter=? ORDER BY value_usd DESC LIMIT 500", (iid, q)))
            hc["byInst"][str(iid)] = {"quarter": q, "rows": hrows}
        out["holdings_current"] = hc

        # 龙虎榜按日期分组（最近15日）
        dates = [r[0] for r in db.execute(
            "SELECT DISTINCT trade_date FROM dt_billboard ORDER BY trade_date DESC LIMIT 15")]
        by_date = {}
        for d in dates:
            by_date[d] = store.rows_to_dicts(db.execute(
                "SELECT * FROM dt_billboard WHERE trade_date=?", (d,)))
        out["billboard"] = {"dates": dates, "byDate": by_date}

        # 十大流通股东全量 + 自选池
        out["holders"] = {
            "rows": store.rows_to_dicts(db.execute("SELECT * FROM top_holders")),
            "watchlist": store.rows_to_dicts(db.execute("SELECT * FROM watchlist ORDER BY code")),
        }

        # 涨停池按日期分组
        zdates = [r[0] for r in db.execute("SELECT DISTINCT date FROM zt_pool ORDER BY date DESC LIMIT 15")]
        zby = {}
        for d in zdates:
            zby[d] = store.rows_to_dicts(db.execute("SELECT * FROM zt_pool WHERE date=? ORDER BY lbc DESC", (d,)))
        out["ztpool"] = {"dates": zdates, "byDate": zby}

    out["built"] = {"built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    return out


def main():
    from app import app

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(exist_ok=True)
    (SITE / "data").mkdir(exist_ok=True)

    client = app.test_client()
    api_exports = {
        "summary": "/api/summary",
        "institutions": "/api/institutions",
        "consensus": "/api/consensus",
        "hkt": "/api/hkt?days=60",
        "news": "/api/news?limit=300",
        "alerts": "/api/alerts?limit=500",
    }
    sizes = {}
    for name, path in api_exports.items():
        data = api_json(client, path)
        (SITE / "data" / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        sizes[name] = len(json.dumps(data, ensure_ascii=False))

    for name, data in export_sql_extras().items():
        (SITE / "data" / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        sizes[name] = len(json.dumps(data, ensure_ascii=False))

    # 复用本地 SPA 三件套
    shutil.copy(ROOT / "static" / "css" / "app.css", SITE / "app.css")
    shutil.copy(ROOT / "static" / "js" / "app.js", SITE / "app.js")
    shutil.copy(ROOT / "static" / "vendor" / "chart.umd.min.js", SITE / "chart.umd.min.js")

    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    html = html.replace("<body>", '<body class="static" data-static="1">')
    html = html.replace('href="/static/css/app.css"', 'href="./app.css"')
    html = html.replace('src="/static/vendor/chart.umd.min.js"', 'src="./chart.umd.min.js"')
    html = html.replace('src="/static/js/app.js"', 'src="./app.js"')
    (SITE / "index.html").write_text(html, encoding="utf-8")

    total = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"[static] site/ 生成完成: {len(sizes)} 个数据文件, "
          f"changes {sizes.get('changes', 0)//1024}KB, 总大小 {total/1024/1024:.1f}MB")


if __name__ == "__main__":
    main()
