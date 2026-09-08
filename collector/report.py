# -*- coding: utf-8 -*-
"""每日运营日报：各平台汇总 + 近 7 天作品表现 + Top 播放 + 采集健康度。

落到 ``exports/daily/<日期>.md``。数字单一来源是快照库（creator-analytics
方法论：不手填、异常如实标注）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from collector.models import connect
from collector.paths import exports_dir

# 每个 content 取最新一条快照（每天可能多行，取当天最后采集的那条）
_LATEST_SNAPSHOT_SQL = """
WITH latest AS (
    SELECT content_id, MAX(collected_at) AS max_at
    FROM content_snapshots GROUP BY content_id
)
SELECT cs.content_id, cs.view, cs.like, cs.comment, cs.share, cs.collect
FROM content_snapshots cs
JOIN latest ON cs.content_id = latest.content_id AND cs.collected_at = latest.max_at
"""


def _platform_summary(conn, day: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.platform, COUNT(DISTINCT c.id) AS works,
               SUM(l.view) AS total_view, SUM(l.like) AS total_like
        FROM contents c
        LEFT JOIN (""" + _LATEST_SNAPSHOT_SQL + """) l ON l.content_id = c.id
        GROUP BY c.platform ORDER BY c.platform
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _recent_works(conn, since: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.platform, c.title, c.publish_date, c.work_url, l.view, l.like, l.comment
        FROM contents c
        LEFT JOIN (""" + _LATEST_SNAPSHOT_SQL + """) l ON l.content_id = c.id
        WHERE c.publish_date >= ?
        ORDER BY c.platform, c.publish_date DESC
        """,
        (since,),
    ).fetchall()
    return [dict(row) for row in rows]


def _top_works(conn, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.platform, c.title, c.work_url, l.view
        FROM contents c
        LEFT JOIN (""" + _LATEST_SNAPSHOT_SQL + """) l ON l.content_id = c.id
        WHERE l.view IS NOT NULL
        ORDER BY l.view DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _failed_runs(conn, day: str) -> list[dict]:
    rows = conn.execute(
        "SELECT platform, account, trigger, error FROM collect_runs "
        "WHERE date(started_at)=? AND status='failed'",
        (day,),
    ).fetchall()
    return [dict(row) for row in rows]


def _fmt(value) -> str:
    return "—" if value is None else f"{value:,}"


def render_daily_report(day: str, summary: list[dict], recent: list[dict],
                        top: list[dict], failures: list[dict]) -> str:
    lines = [f"# 运营日报 {day}", ""]
    lines.append("## 各平台汇总")
    lines.append("")
    lines.append("| 平台 | 作品数 | 总播放 | 总点赞 |")
    lines.append("|---|---|---|---|")
    for row in summary:
        lines.append(f"| {row['platform']} | {row['works']} | {_fmt(row['total_view'])} | {_fmt(row['total_like'])} |")
    if not summary:
        lines.append("| （暂无数据） | | | |")

    lines.append("")
    lines.append(f"## 近 7 天作品（{recent[0]['publish_date'] if recent else '无'} 起）")
    lines.append("")
    lines.append("| 平台 | 标题 | 发布日 | 播放 | 点赞 | 评论 |")
    lines.append("|---|---|---|---|---|---|")
    for row in recent:
        title = (row["title"] or "")[:24]
        lines.append(
            f"| {row['platform']} | {title} | {row['publish_date'] or '—'} "
            f"| {_fmt(row['view'])} | {_fmt(row['like'])} | {_fmt(row['comment'])} |"
        )

    lines.append("")
    lines.append("## 播放 Top 10（全量作品）")
    lines.append("")
    lines.append("| 平台 | 标题 | 播放 |")
    lines.append("|---|---|---|")
    for row in top:
        lines.append(f"| {row['platform']} | {(row['title'] or '')[:30]} | {_fmt(row['view'])} |")

    lines.append("")
    if failures:
        lines.append("## 采集异常（待核实）")
        lines.append("")
        for row in failures:
            lines.append(f"- **{row['platform']}/{row['account']}**（{row['trigger']}）: {row['error']}")
    else:
        lines.append("## 采集健康度")
        lines.append("")
        lines.append("今日无失败采集。")

    lines.append("")
    lines.append(f"_生成时间 {datetime.now().isoformat(timespec='seconds')}；"
                 f"数据口径见 collector/normalize.py 映射表。_")
    return "\n".join(lines)


def generate_daily_report(store, day: str | None = None) -> Path:
    day = day or datetime.now().strftime("%Y-%m-%d")
    since = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    conn = connect(store.db_path, read_only=True)
    try:
        content = render_daily_report(
            day,
            _platform_summary(conn, day),
            _recent_works(conn, since),
            _top_works(conn),
            _failed_runs(conn, day),
        )
    finally:
        conn.close()
    path = exports_dir() / "daily" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
