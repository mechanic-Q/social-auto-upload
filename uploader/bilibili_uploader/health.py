# -*- coding: utf-8 -*-
"""B站账号巡检（只读）：用 biliup cookie 直接调投稿管理官方 API，
查账号维度（已发/待审计数）与作品维度（状态、拒绝原因、数据）。"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import requests

MEMBER_ARCHIVES_URL = "https://member.bilibili.com/x/web/archives"
# 状态码语义（官方约定）：0=开放浏览，-30=待审，-40=审核通过等待转码，其他负值=被拒/异常
STATE_NORMAL = 0
STATE_PENDING_AUDIT = -30
STATE_WAIT_TRANSCODE = -40


def load_biliup_cookies(account_file: str | Path) -> dict[str, str]:
    data = json.loads(Path(account_file).read_text(encoding="utf-8"))
    cookies = (data.get("cookie_info") or {}).get("cookies") or []
    return {c["name"]: c["value"] for c in cookies if c.get("name")}


def _fetch_archives(cookies: dict[str, str], pn: int, ps: int) -> dict:
    resp = requests.get(
        MEMBER_ARCHIVES_URL,
        params={"status": "all", "pn": pn, "ps": ps},
        cookies=cookies,
        headers={
            "Referer": "https://member.bilibili.com/platform/upload-manager/article",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"B站投稿管理 API 返回异常 code={payload.get('code')}: {payload.get('message')}")
    return payload["data"] or {}


def summarize_works(works: list[dict]) -> dict:
    """纯函数：从规范化作品列表算汇总信号，便于离线测试。"""
    views = [w["view"] for w in works if w.get("view") is not None]
    return {
        "work_count": len(works),
        "pending_audit": [w["title"] for w in works if w.get("state") == STATE_PENDING_AUDIT],
        "wait_transcode": [w["title"] for w in works if w.get("state") == STATE_WAIT_TRANSCODE],
        "rejected": [
            {"title": w["title"], "state": w["state"], "reason": w.get("reject_reason") or ""}
            for w in works
            if isinstance(w.get("state"), int) and w["state"] < 0
            and w["state"] not in (STATE_PENDING_AUDIT, STATE_WAIT_TRANSCODE)
        ],
        "median_view": statistics.median(views) if views else None,
        "max_view": max(views) if views else None,
    }


def normalize_archive(entry: dict) -> dict:
    arc = entry.get("Archive") or {}
    stat = entry.get("stat") or {}
    return {
        "bvid": arc.get("bvid"),
        "title": arc.get("title"),
        "state": arc.get("state"),
        "state_desc": arc.get("state_desc"),
        "reject_reason": arc.get("reject_reason") or "",
        "ctime": arc.get("ctime"),
        "pubtime": arc.get("ptime"),
        "view": stat.get("view"),
        "like": stat.get("like"),
        "coin": stat.get("coin"),
        "favorite": stat.get("favorite"),
        "share": stat.get("share"),
        "reply": stat.get("reply"),
        "danmaku": stat.get("danmaku"),
    }


def bilibili_health(account_file: str | Path, limit: int = 20) -> dict:
    cookies = load_biliup_cookies(account_file)
    data = _fetch_archives(cookies, pn=1, ps=max(1, min(limit, 50)))

    works = [normalize_archive(e) for e in (data.get("arc_audits") or [])[:limit]]
    counts = data.get("class") or {}
    return {
        "platform": "bilibili",
        "account": {
            "published": counts.get("pubed"),
            "not_published": counts.get("not_pubed"),
            "publishing": counts.get("is_pubing"),
            "total": (data.get("page") or {}).get("count"),
        },
        "works": works,
        "summary": summarize_works(works),
    }
