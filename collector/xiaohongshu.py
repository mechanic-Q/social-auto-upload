# -*- coding: utf-8 -*-
"""小红书采集器：打开创作服务平台笔记管理页，监听页面加载的接口响应。

小红书没有经过真机验证的接口文档（发布通道也处于停用状态），因此本采集器
采取「probe 优先」策略：第一跑只把命中 ``web_api``/``api`` 的 JSON 响应全部
存 raw 存档（``probe=True``），待样本确认后再由 :func:`parse_note_payloads`
解析入库。解析器是宽容递归：不绑定具体路径，只要字典长得像"笔记"就收。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from collector.base import CollectorStore
from collector.fuzzy import DEFAULT_TITLE_KEYS, parse_work_payloads

XHS_NOTES_URL = "https://creator.xiaohongshu.com/creator/notes"

# id 只认笔记专有键名，不认通用 "id"——否则用户/评论等 dict 会被误收
XHS_ID_KEYS = ("note_id", "noteId", "take_id")
_METRIC_CANDIDATES = None  # 兼容占位：候选键名已收敛至 collector.fuzzy 默认表


def looks_like_note(d: dict) -> bool:
    """兼容别名：判定逻辑收敛到 collector.fuzzy.looks_like_work。"""
    from collector.fuzzy import DEFAULT_METRIC_CANDIDATES, looks_like_work

    return looks_like_work(d, XHS_ID_KEYS, DEFAULT_TITLE_KEYS, DEFAULT_METRIC_CANDIDATES)


def parse_note_payloads(payloads: list) -> list[dict]:
    """兼容别名：小红书笔记解析 = 通用宽容解析 + 小红书 id 键。"""
    return parse_work_payloads(payloads, id_keys=XHS_ID_KEYS)


def parse_published_time(candidate) -> str | None:
    """笔记管理页的时间戳形态多样，尽力而为；解析不出由 DOM 兜底阶段补。"""
    return None


async def collect_xiaohongshu(store: CollectorStore, account_file: str | Path, trigger: str = "full",
                              account_name: str | None = None, probe: bool = False,
                              headless: bool = True) -> dict:
    from patchright.async_api import async_playwright

    from utils.base_social_media import set_init_script

    account = account_name or Path(account_file).stem.removeprefix("xiaohongshu_")
    run_id = store.start_run("xiaohongshu", account, "probe" if probe else trigger)
    try:
        payloads: list = []
        async with async_playwright() as playwright:
            if Path("/home/lmr/.cache/ms-playwright").exists():
                import conf as conf_mod

                browser = await playwright.chromium.launch(
                    headless=headless, executable_path=conf_mod.LOCAL_CHROME_PATH
                )
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
                        if "xiaohongshu.com" not in response.url:
                            return
                        if not any(k in response.url for k in ("web_api", "/api/", "note")):
                            return
                        if "json" not in (response.headers.get("content-type") or ""):
                            return
                        payloads.append(await response.json())
                        store.save_raw("xiaohongshu", payloads[-1], tag=f"capture_{len(payloads)}")
                    except Exception:
                        pass

                page.on("response", _capture)
                await page.goto(XHS_NOTES_URL, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(8000)
                if "login" in page.url or "passport" in page.url:
                    raise RuntimeError(
                        f"小红书 cookie 已失效，请先 `sau xiaohongshu login --account {account}` 重新登录"
                    )
                # 触底加载分页
                for _ in range(3):
                    await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2500)
            finally:
                await context.close()
                await browser.close()

        if probe:
            store.finish_run(run_id, "success", works_seen=0, raw_dir=f"raw/xiaohongshu/{datetime.now():%Y-%m-%d}")
            return {"platform": "xiaohongshu", "status": "probe", "samples": len(payloads)}

        works = parse_note_payloads(payloads)
        if not works:
            raise RuntimeError(
                f"捕获了 {len(payloads)} 个响应但未解析出笔记字段——页面结构可能已变化，"
                f"请查看 raw/xiaohongshu/ 存档校准 parse_note_payloads"
            )

        account_id = store.upsert_account("xiaohongshu", account)
        works = [{
            "external_id": work["external_id"],
            "title": work["title"],
            "work_url": f"https://www.xiaohongshu.com/explore/{work['external_id']}",
            "native": work["native"],
        } for work in works]
        seen, new = store.ingest_works("xiaohongshu", account_id, works, trigger=trigger)

        today = datetime.now().strftime("%Y-%m-%d")
        store.finish_run(run_id, "success", works_seen=seen, works_new=new,
                         raw_dir=f"raw/xiaohongshu/{today}")
        return {"platform": "xiaohongshu", "status": "success", "works_seen": seen, "works_new": new}
    except Exception as exc:
        store.finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
        return {"platform": "xiaohongshu", "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
