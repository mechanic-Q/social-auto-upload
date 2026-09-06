# -*- coding: utf-8 -*-
"""快手 / 视频号 / 头条通用采集器（probe-first，二期+三期平台）。

三个平台的创作者后台接口均未做真机校准，因此与小红书采集器同一策略：
登录态打开内容管理页 → 监听并存档命中的 JSON 响应 → 宽容解析（
collector/fuzzy）入库。首次接入先跑 probe 收集真实样本，再按样本收紧
各平台 profile 的候选键名。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from collector.base import CollectorStore
from collector.fuzzy import (
    DEFAULT_ID_KEYS,
    DEFAULT_METRIC_CANDIDATES,
    DEFAULT_TITLE_KEYS,
    parse_work_payloads,
)

XHS_NOTES_URL = "https://creator.xiaohongshu.com/creator/notes"


@dataclass
class ProbeProfile:
    platform: str
    manage_url: str
    login_markers: tuple[str, ...]
    url_markers: tuple[str, ...] = ("web_api", "/api/", "note", "item", "video", "article", "manage")
    id_keys: tuple[str, ...] = DEFAULT_ID_KEYS
    title_keys: tuple[str, ...] = DEFAULT_TITLE_KEYS
    metric_candidates: dict = field(default_factory=lambda: DEFAULT_METRIC_CANDIDATES)
    work_url_template: str = ""
    scroll_rounds: int = 3


PROFILES: dict[str, ProbeProfile] = {
    "kuaishou": ProbeProfile(
        platform="kuaishou",
        manage_url="https://cp.kuaishou.com/article/manage/video?status=0&from=publish",
        login_markers=("login", "passport", "account.kuaishou"),
        scroll_rounds=6,
        # 2026-09-07 真机样本校准: 列表接口键名 workId/title/playCount/likeCount/commentCount
        id_keys=("workId",),
        metric_candidates={
            "view": ("playCount",),
            "like": ("likeCount",),
            "comment": ("commentCount",),
            "share": ("shareCount",),
            "collect": ("storeCount", "collectCount"),
        },
        work_url_template="https://www.kuaishou.com/short-video/{external_id}",
    ),
    "tencent": ProbeProfile(
        platform="tencent",
        manage_url="https://channels.weixin.qq.com/platform/post/list",
        login_markers=("login", "scanlogin"),
        url_markers=("web_api", "/api/", "cgi-bin", "note", "item", "video", "manage"),
        work_url_template="https://channels.weixin.qq.com/{external_id}",
    ),
    "toutiao": ProbeProfile(
        platform="toutiao",
        manage_url="https://mp.toutiao.com/profile_v4/graphic/publish/manage?category=video",
        login_markers=("login", "sso", "passport"),
        url_markers=("web_api", "/api/", "mp/impeach", "article", "video", "manage", "content", "list"),
        work_url_template="https://www.toutiao.com/article/{external_id}",
    ),
}


def _local_chrome_path() -> str | None:
    try:
        import conf

        return conf.LOCAL_CHROME_PATH if Path("/home/lmr/.cache/ms-playwright").exists() else None
    except Exception:
        return None


async def collect_generic(store: CollectorStore, profile: ProbeProfile, account_file: str | Path,
                          trigger: str = "full", account_name: str | None = None,
                          probe: bool = False, headless: bool = True) -> dict:
    """打开内容管理页，捕获 JSON 响应 → probe 存档 或 宽容解析入库。"""
    from patchright.async_api import async_playwright

    from utils.base_social_media import set_init_script

    account = account_name or Path(account_file).stem.removeprefix(f"{profile.platform}_")
    run_trigger = "probe" if probe else trigger
    run_id = store.start_run(profile.platform, account, run_trigger)
    try:
        payloads: list = []
        async with async_playwright() as playwright:
            chrome = _local_chrome_path()
            if chrome:
                browser = await playwright.chromium.launch(headless=headless, executable_path=chrome)
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

                async def _capture(response):
                    try:
                        if profile.platform.split()[0] not in response.url:
                            return
                        if not any(marker in response.url for marker in profile.url_markers):
                            return
                        content_type = response.headers.get("content-type") or ""
                        if "json" not in content_type and not (
                            profile.platform == "tencent" and "text" in content_type
                        ):
                            return
                        if "json" in content_type:
                            payloads.append(await response.json())
                        else:
                            payloads.append({"_text": await response.text()})
                        # URL path 尾部进 tag: 校准候选键时一眼看出每个样本来自哪个接口
                        from urllib.parse import urlparse

                        path_tail = urlparse(response.url).path.rstrip("/").split("/")[-1] or "root"
                        store.save_raw(profile.platform, payloads[-1],
                                       tag=f"capture_{len(payloads)}_{path_tail[:40]}")
                    except Exception:
                        pass

                page.on("response", _capture)
                await page.goto(profile.manage_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(8000)
                if any(marker in page.url for marker in profile.login_markers):
                    raise RuntimeError(
                        f"{profile.platform} cookie 已失效，请先重新登录（当前跳转到 {page.url}）"
                    )
                for _ in range(profile.scroll_rounds):
                    await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    await page.evaluate("() => window.scrollTo(0, 0)")
                    await page.wait_for_timeout(3000)
            finally:
                await context.close()
                await browser.close()

        if probe:
            store.finish_run(run_id, "success",
                             raw_dir=f"raw/{profile.platform}/{datetime.now():%Y-%m-%d}")
            return {"platform": profile.platform, "status": "probe", "samples": len(payloads)}

        works = parse_work_payloads(payloads, id_keys=profile.id_keys,
                                    title_keys=profile.title_keys,
                                    metric_candidates=profile.metric_candidates)
        if not works:
            raise RuntimeError(
                f"捕获了 {len(payloads)} 个响应但未解析出作品字段——请查看 "
                f"raw/{profile.platform}/ 存档校准 ProbeProfile 候选键"
            )

        account_id = store.upsert_account(profile.platform, account)
        works_ingest = [{
            "external_id": work["external_id"],
            "title": work["title"],
            "work_url": profile.work_url_template.format(external_id=work["external_id"]),
            "native": work["native"],
        } for work in works]
        seen, new = store.ingest_works(profile.platform, account_id, works_ingest, trigger=trigger)

        today = datetime.now().strftime("%Y-%m-%d")
        store.finish_run(run_id, "success", works_seen=seen, works_new=new,
                         raw_dir=f"raw/{profile.platform}/{today}")
        return {"platform": profile.platform, "status": "success", "works_seen": seen, "works_new": new}
    except Exception as exc:
        store.finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
        return {"platform": profile.platform, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
