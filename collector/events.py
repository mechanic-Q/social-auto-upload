# -*- coding: utf-8 -*-
"""发布事件文件（ADR-0002 的单进程写库约束配套机制）。

发布进程**不写 SQLite**：发布成功后只向 ``events/publish_events.jsonl``
追加一行 JSON 事件（append 在 9p 上安全）；采集进程追加 ``consume`` 行标记
消费完成。读取时按行折叠，永不改写历史行。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from collector.paths import events_file

# 发布后至少延迟 30 分钟才值得采（首波分发需要时间）；消费任务每小时跑一次，
# 实际延迟落在 30~90 分钟之间，天然带随机性，与发布动作在时间轴上脱开。
MIN_DELAY = timedelta(minutes=30)


def append_publish_event(
    platform: str,
    account_name: str,
    title: str,
    published_at: datetime | None = None,
    video_path: str = "",
    source: str = "uploader",
    event_id: str | None = None,
) -> dict:
    """发布钩子调用：追加一行 publish 事件。失败由调用方 try/except 吸收，绝不阻塞发布。"""
    event = {
        "event_id": event_id or uuid.uuid4().hex,
        "type": "publish",
        "platform": platform,
        "account": account_name,
        "title": title,
        "published_at": (published_at or datetime.now()).isoformat(timespec="seconds"),
        "video_path": video_path,
        "source": source,
    }
    path = events_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return event


def safe_append_publish_event(platform: str, account_file, title: str, **kwargs) -> None:
    """发布钩子专用：从 cookie 路径推断账号名，任何失败只记 warning、绝不阻塞发布主流程。

    发布进程经由本函数只 append 事件文件，不 import SQLite 相关模块（ADR-0002）。
    """
    try:
        name = Path(str(account_file)).stem
        for prefix in ("bilibili_", "douyin_", "kuaishou_", "tencent_", "toutiao_", "xiaohongshu_"):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        append_publish_event(platform=platform, account_name=name, title=title or "", **kwargs)
    except Exception as exc:  # 采集依赖故障不能影响发布
        import logging

        logging.getLogger(__name__).warning("发布事件记录失败（已忽略）: %s", exc)


def _append_consume(event_ids: list[str]) -> None:
    path = events_file()
    with open(path, "a", encoding="utf-8") as fh:
        for event_id in event_ids:
            fh.write(
                json.dumps(
                    {"event_id": event_id, "type": "consume", "consumed_at": datetime.now().isoformat(timespec="seconds")},
                    ensure_ascii=False,
                )
                + "\n"
            )


def read_events(path: Path | None = None) -> list[dict]:
    """读取并折叠事件：publish 行带 consumed 标志，损坏行跳过并计数。"""
    path = path or events_file()
    if not path.exists():
        return []
    publishes: dict[str, dict] = {}
    consumed: set[str] = set()
    bad_lines = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        if row.get("type") == "publish":
            publishes[row.get("event_id") or ""] = {**row, "consumed": False}
        elif row.get("type") == "consume":
            consumed.add(row.get("event_id") or "")
    events = []
    for event_id, event in publishes.items():
        if event_id in consumed:
            event["consumed"] = True
        events.append(event)
    if bad_lines:
        events.append({"type": "corrupt", "count": bad_lines})
    return events


def due_incrementals(now: datetime | None = None, path: Path | None = None) -> list[dict]:
    """到期未消费的发布事件：发布已满 MIN_DELAY 且未被处理过（错过就补，不丢弃）。"""
    now = now or datetime.now()
    due = []
    for event in read_events(path):
        if event.get("type") != "publish" or event.get("consumed"):
            continue
        try:
            published_at = datetime.fromisoformat(event["published_at"])
        except (KeyError, ValueError):
            continue
        if now - published_at >= MIN_DELAY:
            due.append(event)
    return due


def mark_consumed(event_ids: list[str], path: Path | None = None) -> None:
    if not event_ids:
        return
    if path is not None:  # 测试注入路径时同样走 append 折叠
        with open(path, "a", encoding="utf-8") as fh:
            for event_id in event_ids:
                fh.write(json.dumps({"event_id": event_id, "type": "consume"}, ensure_ascii=False) + "\n")
        return
    _append_consume(event_ids)
