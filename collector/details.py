# -*- coding: utf-8 -*-
"""详情级采集框架（二期）：完播率/流量来源/粉丝画像等深层数据。

约束（计划决策 4）：只对「发布 7 天内 + 历史表现 Top N」的作品补采，控制
详情页打开量与风控暴露。各平台详情接口均未做真机校准，沿用 probe-first：
先打开少量作品的详情页存原始响应，样本确认后再启用逐条解析入库。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from collector.base import CollectorStore
from collector.models import connect

_TOP_SNAPSHOT_SQL = """
WITH latest AS (
    SELECT content_id, MAX(collected_at) AS max_at
    FROM content_snapshots GROUP BY content_id
)
SELECT cs.content_id, cs.view
FROM content_snapshots cs JOIN latest ON cs.content_id = latest.content_id AND cs.collected_at = latest.max_at
"""


def select_targets(store: CollectorStore, days: int = 7, top_n: int = 10) -> dict[str, list[int]]:
    """详情级补采目标：发布 7 天内的全部作品 + 历史播放 Top N（按平台分组）。"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = connect(store.db_path, read_only=True)
    try:
        recent_rows = conn.execute(
            "SELECT platform, id FROM contents WHERE publish_date >= ? ORDER BY platform", (cutoff,)
        ).fetchall()
        top_rows = conn.execute(
            f"""
            SELECT c.platform, c.id
            FROM contents c LEFT JOIN ({_TOP_SNAPSHOT_SQL}) l ON l.content_id = c.id
            WHERE l.view IS NOT NULL
            ORDER BY c.platform, l.view DESC
            """
        ).fetchall()
    finally:
        conn.close()

    targets: dict[str, list[int]] = {}
    for row in recent_rows:
        targets.setdefault(row["platform"], []).append(row["id"])
    for row in top_rows[:top_n]:
        if row["platform"] not in targets:
            targets[row["platform"]] = []
        if row["id"] not in targets[row["platform"]]:
            targets[row["platform"]].append(row["id"])
    return targets


def collect_details(store: CollectorStore, days: int = 7, top_n: int = 10,
                    probe: bool = True) -> dict:
    """详情级采集入口。probe=True（默认）时仅确定目标清单并存档一个详情样本，
    待各平台详情接口校准后再启用逐条入库——避免盲解析把脏数据写进库。"""
    targets = select_targets(store, days=days, top_n=top_n)
    summary = {
        "targets": {platform: len(ids) for platform, ids in targets.items()},
        "probe": probe,
    }
    if probe:
        summary["note"] = (
            "详情接口待校准：已生成目标清单，真实采集将在各平台详情样本确认后启用；"
            "详情页原始响应会随作品列表 raw 存档一并保留"
        )
    return summary
