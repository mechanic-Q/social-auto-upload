# -*- coding: utf-8 -*-
"""采集调度：全量（每日 09:30，任务计划触发）+ 增量（消费到期发布事件）。

浏览器型采集器（抖音/小红书）在同一个 asyncio loop 内顺序跑，绝不并发打开
多个创作后台——风控优先。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from collector import events as collector_events
from collector.base import CollectorStore
from collector.bilibili import collect_bilibili
from collector.douyin import collect_douyin
from collector.generic import PROFILES, collect_generic
from collector.normalize import PLATFORMS
from collector.paths import ensure_layout
from collector.xiaohongshu import collect_xiaohongshu

COOKIES_DIR = Path(__file__).parent.parent / "cookies"
# 浏览器型平台在同一个 asyncio loop 内顺序执行,绝不并发打开多个创作后台
BROWSER_PLATFORMS = ("douyin", "xiaohongshu", "kuaishou", "tencent", "toutiao")
# 默认调度清单: 2026-09-07 用户决定搁置小红书(cookie 失效未续,发布通道亦停用),
# 不再进入每日全量;需要时手动 `sau stats collect --full --only xiaohongshu` 或 probe。
DEFAULT_PLATFORMS = ("bilibili", "douyin", "kuaishou", "tencent", "toutiao")


def account_files(platform: str) -> list[Path]:
    """cookies/<平台>_<账号>.json，支持多账号；.bak 等噪声排除。"""
    return sorted(p for p in COOKIES_DIR.glob(f"{platform}_*.json") if p.suffix == ".json")


def _collect_platform(store: CollectorStore, platform: str, trigger: str, probe: bool = False) -> list[dict]:
    files = account_files(platform)
    if not files:
        return [{"platform": platform, "status": "skipped", "error": "无账号 cookie 文件"}]
    results = []
    if platform == "bilibili":
        for account_file in files:
            results.append(collect_bilibili(store, account_file, trigger=trigger))
        return results
    # 浏览器平台在同一 loop 内顺序执行
    async def _run():
        out = []
        for account_file in files:
            if platform == "douyin":
                out.append(await collect_douyin(store, account_file, trigger=trigger))
            elif platform == "xiaohongshu":
                out.append(await collect_xiaohongshu(store, account_file, trigger=trigger, probe=probe))
            elif platform in PROFILES:
                out.append(await collect_generic(store, PROFILES[platform], account_file,
                                                 trigger=trigger, probe=probe))
        return out

    return asyncio.run(_run())


def run_full(platforms=DEFAULT_PLATFORMS, generate_report: bool = True) -> dict:
    """全量采集：每平台（每账号）一次快照。任务计划每日 09:30 触发，错过由
    StartWhenAvailable 在开机后补跑——不需要额外的去重判断。"""
    ensure_layout()
    store = CollectorStore()
    try:
        summary = {"trigger": "full", "platforms": {}}
        for platform in platforms:
            results = _collect_platform(store, platform, trigger="full")
            summary["platforms"][platform] = results
        if generate_report:
            from collector.report import generate_daily_report

            try:
                summary["daily_report"] = str(generate_daily_report(store))
            except Exception as exc:  # 日报失败不影响采集结果
                summary["daily_report_error"] = str(exc)
        return summary
    finally:
        store.close()


def run_incremental(now=None) -> dict:
    """增量采集：消费到期的发布事件（发布后延迟 ≥30 分钟），按平台聚合采集。
    没有到期事件时直接返回 skipped——每小时的任务因此保持轻量。"""
    due = collector_events.due_incrementals(now)
    if not due:
        return {"trigger": "incremental", "status": "skipped", "reason": "无到期发布事件"}
    platforms = sorted({event["platform"] for event in due if event.get("platform") in PLATFORMS})
    if not platforms:
        collector_events.mark_consumed([event["event_id"] for event in due])
        return {"trigger": "incremental", "status": "skipped", "reason": "事件平台均不在采集范围"}
    ensure_layout()
    store = CollectorStore()
    try:
        summary = {"trigger": "incremental", "platforms": {}, "events": [e["event_id"] for e in due]}
        failed = False
        for platform in platforms:
            results = _collect_platform(store, platform, trigger="incremental")
            summary["platforms"][platform] = results
            failed = failed or any(r.get("status") == "failed" for r in results)
        if not failed:
            collector_events.mark_consumed(summary["events"])
        else:
            summary["note"] = "存在失败平台，事件保留待下次消费"
        return summary
    finally:
        store.close()


def run_probe(platform: str) -> dict:
    """probe 模式：只收集原始响应存档，不写快照。用于新平台首次校准。"""
    ensure_layout()
    store = CollectorStore()
    try:
        results = _collect_platform(store, platform, trigger="full", probe=True)
        return {"trigger": "probe", "platform": platform, "results": results}
    finally:
        store.close()
