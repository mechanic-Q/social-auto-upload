# -*- coding: utf-8 -*-
"""抖音采集器：登录态打开创作者后台内容管理页，页内 fetch work_list 接口。

接口路径与响应结构沿用 ``uploader/douyin_uploader/health.py``（2026-09-05 真机
验证）；与巡检不同的是采集器逐页拉取并把**每页原始响应**单独存 raw 存档，
供平台改版后重放重建。
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from collector.base import CollectorStore
from collector.normalize import normalize_metrics
from conf import LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from uploader.douyin_uploader.health import (
    DOUYIN_MANAGE_URL,
    _FETCH_USER_INFO_JS,
    normalize_aweme,
)
from utils.base_social_media import set_init_script

WORK_LIST_URL = (
    "/janus/douyin/creator/pc/work_list"
    "?status=0&count={count}&max_cursor={cursor}&scene=star_atlas&device_platform=android&aid=1128"
)
PAGE_SIZE = 50
MAX_PAGES = 20  # 20 页 × 50 = 1000 条，远超个人账号量级


async def collect_douyin(store: CollectorStore, account_file: str | Path, trigger: str = "full",
                         account_name: str | None = None,
                         headless: bool = LOCAL_CHROME_HEADLESS) -> dict:
    from patchright.async_api import async_playwright

    account = account_name or Path(account_file).stem.removeprefix("douyin_")
    run_id = store.start_run("douyin", account, trigger)
    try:
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
                        f"抖音 cookie 已失效，请先 `sau douyin login --account {account}` 重新登录"
                    )

                pages_payload: list[dict] = []
                cursor = 0
                for page_no in range(MAX_PAGES):
                    fetch_url = WORK_LIST_URL.format(status=0, count=PAGE_SIZE, cursor=cursor)
                    payload = await page.evaluate(
                        "async (url) => { const r = await fetch(url, {credentials: 'same-origin'}); "
                        "return await r.json(); }",
                        fetch_url,
                    )
                    pages_payload.append(payload)
                    store.save_raw("douyin", payload, tag=f"work_list_p{page_no}")
                    items = payload.get("aweme_list") or []
                    if not payload.get("has_more") or not items:
                        break
                    cursor = items[-1].get("create_time") or 0

                user_payload = await page.evaluate(_FETCH_USER_INFO_JS)
                store.save_raw("douyin", user_payload, tag="user_info")
            finally:
                await context.close()
                await browser.close()

        user = user_payload.get("user_info") or user_payload.get("user") or {}
        account_id = store.upsert_account("douyin", account)
        today = datetime.now().strftime("%Y-%m-%d")
        store.add_account_snapshot(
            account_id, today,
            follower_count=user.get("follower_count"),
            extra={"nickname": user.get("nickname"), "aweme_count": user.get("aweme_count")},
        )

        works = []
        for payload in pages_payload:
            for item in payload.get("aweme_list") or []:
                work = normalize_aweme(item)
                if not work.get("aweme_id"):
                    continue
                works.append({
                    "external_id": work["aweme_id"],
                    "title": work.get("title") or "",
                    "work_url": f"https://www.douyin.com/video/{work['aweme_id']}",
                    "publish_date": work.get("time"),
                    "native": {
                        "play": work.get("play"),
                        "like": work.get("like"),
                        "comment": work.get("comment"),
                        "share": work.get("share"),
                        "collect": work.get("collect"),
                    },
                })
        seen, new = store.ingest_works("douyin", account_id, works, trigger=trigger)

        store.finish_run(run_id, "success", works_seen=seen, works_new=new,
                         raw_dir=f"raw/douyin/{today}")
        return {"platform": "douyin", "status": "success", "works_seen": seen, "works_new": new,
                "follower_count": user.get("follower_count")}
    except Exception as exc:
        store.finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
        return {"platform": "douyin", "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
