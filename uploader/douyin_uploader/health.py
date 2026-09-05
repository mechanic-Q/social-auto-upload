# -*- coding: utf-8 -*-
"""抖音账号巡检（只读）：登录态打开创作者后台内容管理页，
在页面上下文调用 work_list 等接口，汇总账号处罚状态、作品状态标志与播放数据。
交互方法已在 2026-09-05 真机验证。"""
from __future__ import annotations

import asyncio
import statistics
from datetime import datetime
from pathlib import Path

from patchright.async_api import async_playwright

from conf import LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from utils.base_social_media import set_init_script

DOUYIN_MANAGE_URL = "https://creator.douyin.com/creator-micro/content/manage"
WORK_LIST_API = (
    "/janus/douyin/creator/pc/work_list"
    "?status={status}&count={count}&max_cursor={cursor}"
    "&scene=star_atlas&device_platform=android&aid=1128"
)

# 与浏览器 JS 通信抓取作品列表与账号信息（页内 fetch 自动带 cookie/签名环境）
_FETCH_WORKS_JS = """
async (maxWorks) => {
    const out = [];
    let cursor = 0;
    for (let i = 0; i < 10 && out.length < maxWorks; i++) {
        const r = await fetch(
            `/janus/douyin/creator/pc/work_list?status=0&count=50&max_cursor=${cursor}&scene=star_atlas&device_platform=android&aid=1128`,
            {credentials: 'same-origin'}
        );
        const j = await r.json();
        const items = j.aweme_list || [];
        out.push(...items);
        if (!j.has_more || !items.length) break;
        cursor = items[items.length - 1].create_time;
    }
    return out.slice(0, maxWorks);
}
"""

_FETCH_USER_INFO_JS = """
async () => {
    const r = await fetch('/web/api/media/user/info/', {credentials: 'same-origin'});
    return await r.json();
}
"""

# 账号处罚信息挂在合集列表接口的 user_punish_info 字段上（真机验证）
_FETCH_PUNISH_JS = """
async () => {
    const r = await fetch('/web/api/mix/list/?status=0%2C1%2C2%2C3%2C6&count=1&cursor=0', {credentials: 'same-origin'});
    const j = await r.json();
    return j.user_punish_info || null;
}
"""


def summarize_works(works: list[dict]) -> dict:
    """纯函数：从规范化作品列表算汇总信号，便于离线测试。"""
    views = [w["play"] for w in works if w.get("play") is not None]
    abnormal = [
        {"title": w["title"], "flags": w["flags"]}
        for w in works
        if any(f in w["flags"] for f in ("in_reviewing", "self_see", "is_private", "is_prohibited"))
    ]
    return {
        "work_count": len(works),
        "abnormal_status": abnormal,
        "median_play": statistics.median(views) if views else None,
        "max_play": max(views) if views else None,
        "plays_over_100": sum(1 for v in views if v > 100),
    }


def normalize_aweme(item: dict) -> dict:
    status = item.get("status") or {}
    stat = item.get("statistics") or {}
    create_time = item.get("create_time")
    flag_keys = ("in_reviewing", "is_private", "is_prohibited", "private_status", "self_see", "reviewed")
    return {
        "aweme_id": item.get("aweme_id"),
        "title": (item.get("desc") or item.get("Title") or "").strip()[:60],
        "time": datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M") if create_time else None,
        "flags": {k: status.get(k) for k in flag_keys if status.get(k)},
        "play": stat.get("play_count"),
        "like": stat.get("digg_count"),
        "comment": stat.get("comment_count"),
        "share": stat.get("share_count"),
        "collect": stat.get("collect_count"),
    }


async def douyin_health(account_file: str | Path, limit: int = 30, headless: bool = LOCAL_CHROME_HEADLESS) -> dict:
    async with async_playwright() as playwright:
        if LOCAL_CHROME_PATH:
            browser = await playwright.chromium.launch(headless=headless, executable_path=LOCAL_CHROME_PATH)
        else:
            browser = await playwright.chromium.launch(headless=headless, channel="chromium")
        context = await browser.new_context(
            storage_state=str(account_file),
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        context = await set_init_script(context)
        try:
            page = await context.new_page()
            await page.goto(DOUYIN_MANAGE_URL, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(8000)
            if "login" in page.url or "passport" in page.url:
                raise RuntimeError(
                    f"抖音 cookie 已失效，请先 `sau douyin login --account <账号>` 重新登录（当前跳转到 {page.url}）"
                )

            raw_works = await page.evaluate(_FETCH_WORKS_JS, max(1, min(limit, 100)))
            user_payload = await page.evaluate(_FETCH_USER_INFO_JS)
            punish_info = await page.evaluate(_FETCH_PUNISH_JS)
        finally:
            await context.close()
            await browser.close()

    user = user_payload.get("user_info") or user_payload.get("user") or {}
    works = [normalize_aweme(item) for item in raw_works]
    return {
        "platform": "douyin",
        "account": {
            "nickname": user.get("nickname"),
            "follower_count": user.get("follower_count"),
            "aweme_count": user.get("aweme_count"),
            "punish_info": punish_info,
        },
        "works": works,
        "summary": summarize_works(works),
    }
