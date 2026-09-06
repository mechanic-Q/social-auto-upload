# -*- coding: utf-8 -*-
"""B 站采集器：纯 HTTP API，不开浏览器（一期最稳通道）。

复用 ``uploader/bilibili_uploader/health.py`` 的投稿管理 API 模式：
``member.bilibili.com/x/web/archives``（本人稿件列表 + 各项互动数据，
需 biliup cookie），粉丝数走公开的 ``api.bilibili.com/x/relation/stat``。
全部响应存 raw 存档。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import requests

from collector.base import CollectorStore
from collector.normalize import normalize_metrics
from uploader.bilibili_uploader.health import (
    MEMBER_ARCHIVES_URL,
    _fetch_archives,
    load_biliup_cookies,
    normalize_archive,
)

RELATION_STAT_URL = "https://api.bilibili.com/x/relation/stat"
PAGE_SIZE = 50


def _fetch_all_archives(cookies: dict[str, str], save_raw) -> list[dict]:
    """分页拉全量稿件，每页原始响应落存档。"""
    entries: list[dict] = []
    pn = 1
    total = None
    while True:
        data = _fetch_archives(cookies, pn=pn, ps=PAGE_SIZE)
        save_raw(data, tag=f"archives_pn{pn}")
        entries.extend(data.get("arc_audits") or [])
        total = (data.get("page") or {}).get("count")
        if total is None or len(entries) >= int(total) or not (data.get("arc_audits") or []):
            break
        pn += 1
    return entries


def fetch_follower_count(cookies: dict[str, str]) -> int | None:
    """公开接口拿粉丝数；mid 取 cookie 里的 DedeUserID。"""
    mid = cookies.get("DedeUserID")
    if not mid:
        return None
    resp = requests.get(RELATION_STAT_URL, params={"vmid": mid}, timeout=30,
                        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0.0.0"})
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"B站粉丝数接口异常 code={payload.get('code')}")
    return (payload.get("data") or {}).get("follower")


def collect_bilibili(store: CollectorStore, account_file: str | Path, trigger: str = "full",
                     account_name: str | None = None) -> dict:
    account = account_name or Path(account_file).stem.removeprefix("bilibili_")
    run_id = store.start_run("bilibili", account, trigger)
    try:
        cookies = load_biliup_cookies(account_file)
        entries = _fetch_all_archives(cookies, lambda data, tag: store.save_raw("bilibili", data, tag=tag))
        follower = fetch_follower_count(cookies)
        store.save_raw("bilibili", {"follower": follower}, tag="relation_stat")

        account_id = store.upsert_account("bilibili", account)
        today = datetime.now().strftime("%Y-%m-%d")
        store.add_account_snapshot(account_id, today, follower_count=follower)

        works = []
        for entry in entries:
            work = normalize_archive(entry)
            if not work.get("bvid"):
                continue
            works.append({
                "external_id": work["bvid"],
                "title": work.get("title") or "",
                "work_url": f"https://www.bilibili.com/video/{work['bvid']}",
                "publish_date": work.get("pubtime"),
                "native": {
                    "view": work.get("view"),
                    "like": work.get("like"),
                    "reply": work.get("reply"),
                    "share": work.get("share"),
                    "favorite": work.get("favorite"),
                },
            })
        seen, new = store.ingest_works("bilibili", account_id, works, trigger=trigger)

        store.finish_run(run_id, "success", works_seen=seen, works_new=new,
                         raw_dir=f"raw/bilibili/{today}")
        return {"platform": "bilibili", "status": "success", "works_seen": seen, "works_new": new,
                "follower_count": follower}
    except Exception as exc:
        store.finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
        return {"platform": "bilibili", "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
