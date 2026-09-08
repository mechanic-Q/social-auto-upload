# -*- coding: utf-8 -*-
"""``sau stats`` 子命令：status / list / trend / collect。

输出风格与 health 命令一致（JSON）。查询走只读连接，手动采集与任务计划共用
scheduler 的同一入口。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from collector.models import connect
from collector.paths import db_path, ensure_layout
from collector.scheduler import run_full, run_incremental, run_probe

_LATEST_SQL = """
WITH latest AS (
    SELECT content_id, MAX(collected_at) AS max_at
    FROM content_snapshots GROUP BY content_id
)
SELECT cs.content_id, cs.view, cs.like, cs.comment, cs.share, cs.collect
FROM content_snapshots cs
JOIN latest ON cs.content_id = latest.content_id AND cs.collected_at = latest.max_at
"""


def _last_runs(conn, limit: int = 3) -> list[dict]:
    rows = conn.execute(
        "SELECT platform, account, trigger, started_at, status, works_seen, works_new, error "
        "FROM collect_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


def cmd_status() -> dict:
    ensure_layout()
    conn = connect(db_path(), read_only=True)
    try:
        accounts = [dict(r) for r in conn.execute("SELECT platform, account_name, created_at FROM accounts")]
        runs = _last_runs(conn)
        totals = [dict(r) for r in conn.execute(
            "SELECT platform, COUNT(*) AS works FROM contents GROUP BY platform")]
    finally:
        conn.close()
    return {"db": str(db_path()), "accounts": accounts, "works_by_platform": totals, "recent_runs": runs}


def cmd_list(platform: str | None = None, limit: int = 30) -> dict:
    conn = connect(db_path(), read_only=True)
    try:
        where = "WHERE c.platform = ?" if platform else ""
        params = (platform, limit) if platform else (limit,)
        rows = conn.execute(
            f"""
            SELECT c.platform, c.external_id, c.title, c.publish_date, c.work_url,
                   l.view, l.like, l.comment, l.share, l.collect
            FROM contents c
            LEFT JOIN ({_LATEST_SQL}) l ON l.content_id = c.id
            {where}
            ORDER BY l.view IS NULL, l.view DESC LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        conn.close()
    return {"works": [dict(row) for row in rows]}


def cmd_trend(platform: str, external_id: str | None = None, title: str | None = None) -> dict:
    conn = connect(db_path(), read_only=True)
    try:
        if external_id:
            work = conn.execute(
                "SELECT id, title, platform FROM contents WHERE platform=? AND external_id=?",
                (platform, external_id),
            ).fetchone()
        elif title:
            work = conn.execute(
                "SELECT id, title, platform FROM contents WHERE platform=? AND title LIKE ? ORDER BY id DESC",
                (platform, f"%{title}%"),
            ).fetchone()
        else:
            raise SystemExit("需要 --external-id 或 --title 之一")
        if work is None:
            return {"error": "未找到匹配作品"}
        rows = conn.execute(
            "SELECT collected_at, view, like, comment, share, collect, is_incremental "
            "FROM content_snapshots WHERE content_id=? ORDER BY collected_at",
            (work["id"],),
        ).fetchall()
        return {"work": dict(work), "snapshots": [dict(row) for row in rows]}
    finally:
        conn.close()


def cmd_crosswalk(output: str | None = None) -> dict:
    """导出 match_key 清单（JSON），供 daily-china published-track 按 key 聚合（三期）。"""
    conn = connect(db_path(), read_only=True)
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT platform, external_id, title, publish_date, match_key, work_url "
            "FROM contents ORDER BY platform, publish_date")]
    finally:
        conn.close()
    if output:
        from pathlib import Path

        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"exported": len(rows), "path": str(path)}
    return {"works": rows}


def cmd_collect(mode: str, platform: str | None = None) -> dict:
    if mode == "full":
        platforms = (platform,) if platform else None
        return run_full(platforms=platforms)
    if mode == "incremental":
        return run_incremental()
    if mode == "probe":
        if not platform:
            raise SystemExit("probe 模式需要 --only")
        return run_probe(platform)
    raise SystemExit(f"未知采集模式: {mode}")


def register_stats_parser(subparsers) -> argparse.ArgumentParser:
    stats = subparsers.add_parser("stats", help="创作者数据中台：查询与手动采集")
    actions = stats.add_subparsers(dest="action", required=True)

    status_p = actions.add_parser("status", help="库位置、账号、最近采集运行")
    status_p.set_defaults(stats_handler=lambda args: cmd_status())

    list_p = actions.add_parser("list", help="作品跨平台表现（按最新播放排序）")
    list_p.add_argument("--only", dest="only_platform", default=None, help="限定平台(避免与外层路由参数同名)")
    list_p.add_argument("--limit", type=int, default=30)
    list_p.set_defaults(stats_handler=lambda args: cmd_list(args.only_platform, args.limit))

    trend_p = actions.add_parser("trend", help="单作品快照时序")
    trend_p.add_argument("--only", dest="only_platform", required=True, help="平台名")
    trend_p.add_argument("--external-id", default=None, help="平台作品 ID（bvid/aweme_id/note_id）")
    trend_p.add_argument("--title", default=None, help="标题模糊匹配")
    trend_p.set_defaults(stats_handler=lambda args: cmd_trend(args.only_platform, args.external_id, args.title))

    collect_p = actions.add_parser("collect", help="手动采集（full/incremental/probe）")
    collect_p.add_argument("--full", action="store_true", help="全量采集")
    collect_p.add_argument("--incremental", action="store_true", help="消费到期发布事件的增量采集")
    collect_p.add_argument("--probe", action="store_true", help="只存原始响应不写快照（校准用）")
    collect_p.add_argument("--only", dest="only_platform", default=None, help="限定平台")
    collect_p.set_defaults(stats_handler=lambda args: cmd_collect(
        "full" if args.full else "incremental" if args.incremental else "probe", args.only_platform))

    crosswalk_p = actions.add_parser("crosswalk", help="导出 match_key 清单供 published-track 聚合")
    crosswalk_p.add_argument("--output", default=None, help="写出 JSON 文件路径(缺省打印)")
    crosswalk_p.set_defaults(stats_handler=lambda args: cmd_crosswalk(args.output))
    return stats


def handle(args) -> int:
    result = args.stats_handler(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0
