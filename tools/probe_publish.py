#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_publish.py — 发布链只读探针（2026-10-12 诊断形态沉淀，spec video-pipeline#92/#93）。

用途：发布失败时 5 分钟内区分四种形态——登录墙 / 页面空壳 / 接口转圈 / 反爬跳转；
也用于合并/改版后的过检基线。只读（不开上传、不真发布），headless 即可。

用法：
    python tools/probe_publish.py --platform douyin --account diyi
    python tools/probe_publish.py --platform kuaishou --account diyi --out-dir /tmp/probe

判据三层：
  1. 服务端 API 判据（最硬）：页内 fetch 需登录接口。cookie 文件 expires 只是本地
     有效期，服务端注销（如抖音 status_code=8「用户未登录」）才是真失效；
  2. 元素判据：上传按钮/标题框/描述框 count+visible——正常过检 vs 登录墙/空壳；
  3. 形态分类：ok / login-wall / login-wall(server) / spinner（转圈=接口限速，换时段重试）/ blank。

退出码：0=PASS，1=FAIL，2=WARN（spinner 等可重试形态）。
选择器全部集中在 PLATFORMS 常量区，编辑器改版只改这一处。
"""
import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patchright.async_api import async_playwright

from utils.base_social_media import set_init_script
from conf import LOCAL_CHROME_PATH

# ── 平台判据常量区（编辑器改版只改这里）────────────────────────────────
PLATFORMS = {
    "douyin": {
        "cookie": "cookies/douyin_{account}.json",
        "upload_url": "https://creator.douyin.com/creator-micro/content/upload",
        "markers": [
            ("文件上传入口", "div[class^='container'] input"),
            ("标题框", 'input[placeholder*="填写作品标题"]'),
            ("描述框", 'div.zone-container[contenteditable="true"]'),
            ("登录墙文案", "text=扫码登录"),
        ],
        # 服务端判据：页内 fetch 需登录接口；status_code=8 = 用户未登录（真失效）
        "server_check": """
            async () => {
                const r = await fetch('/web/api/media/user/info/', {credentials: 'same-origin'});
                return await r.json();
            }
        """,
        "server_ok": lambda d: d.get("status_code") in (0, None),
        "wait_s": 12,
    },
    "kuaishou": {
        "cookie": "cookies/kuaishou_{account}.json",
        "upload_url": "https://cp.kuaishou.com/article/publish/video",
        "markers": [
            ("上传按钮", "button[class^='_upload-btn']"),
            ("文件入口", "input[type=file]"),
            ("登录墙文案", "text=扫码登录"),
        ],
        "server_check": None,  # 快手无稳定页内判据 API，以元素判据为准
        "wait_s": 15,  # 站点接口偶发转圈（高峰限速），多给几秒
    },
    "toutiao": {
        "cookie": "cookies/toutiao_{account}.json",
        "upload_url": "https://mp.toutiao.com/profile_v4/xigua/upload-video",
        "markers": [
            ("文件入口", "input[type=file]"),
            ("登录字样", "text=登录"),
        ],
        "server_check": None,
        "wait_s": 12,
    },
    "tencent": {
        "cookie": "cookies/tencent_{account}.json",
        "upload_url": "https://channels.weixin.qq.com/platform/post/create",
        "markers": [
            ("文件入口", "input[type=file]"),
            ("登录字样", "text=扫码"),
        ],
        "server_check": None,
        "wait_s": 12,
    },
}


def classify(result):
    """三层判据 → 形态结论。"""
    if result.get("server") is not None:
        cfg = PLATFORMS[result["platform"]]
        if not cfg["server_ok"](result["server"]):
            return "login-wall(服务端注销——cookie 需重新扫码)"
    if "login" in result.get("url", "").lower():
        return "login-wall(被重定向到登录页)"
    usable = [m for m in result["markers"]
              if "登录" not in m["label"] and m["count"] > 0 and m["visible"]]
    wall = [m for m in result["markers"] if "登录" in m["label"] and m["count"] > 0 and m["visible"]]
    if usable:
        return "ok"
    if wall:
        return "login-wall"
    dormant = [m for m in result["markers"] if "登录" not in m["label"] and m["count"] > 0]
    if dormant:
        return "spinner(元素在DOM不可见——接口限速，换时段重试)"
    return "blank(页面空壳——反爬或渲染失败)"


async def probe(platform: str, account: str, repo_root: str, out_dir: str) -> int:
    cfg = PLATFORMS[platform]
    cookie_path = os.path.join(repo_root, cfg["cookie"].format(account=account))
    if not os.path.exists(cookie_path):
        print(f"FAIL {platform}: cookie 文件不存在 {cookie_path}")
        return 1
    os.makedirs(out_dir, exist_ok=True)
    result = {"platform": platform, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "cookie": cookie_path, "server": None, "markers": []}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=LOCAL_CHROME_PATH)
        context = await browser.new_context(storage_state=cookie_path)
        context = await set_init_script(context)
        page = await context.new_page()
        try:
            await page.goto(cfg["upload_url"], wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"WARN {platform}: goto 异常（load 面资源挂起常见，继续按 DOM 判据）: "
                  f"{type(e).__name__}: {str(e)[:120]}")
        await asyncio.sleep(cfg["wait_s"])

        result["url"] = page.url[:160]
        for label, sel in cfg["markers"]:
            try:
                cnt = await page.locator(sel).count()
                vis = bool(cnt) and await page.locator(sel).first.is_visible()
            except Exception:
                cnt, vis = -1, False
            result["markers"].append({"label": label, "selector": sel,
                                      "count": cnt, "visible": bool(vis)})

        if cfg["server_check"]:
            try:
                result["server"] = await page.evaluate(cfg["server_check"])
            except Exception as e:
                result["server_error"] = f"{type(e).__name__}: {str(e)[:120]}"

        shot = os.path.join(out_dir, f"probe_{platform}.png")
        await page.screenshot(path=shot)
        await browser.close()

    result["verdict"] = classify(result)
    result["screenshot"] = shot
    with open(os.path.join(out_dir, f"probe_{platform}.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    verdict = result["verdict"]
    rc = 0 if verdict == "ok" else (2 if verdict.startswith("spinner") else 1)
    print(f"{'PASS' if rc == 0 else ('WARN' if rc == 2 else 'FAIL')} {platform}: "
          f"verdict={verdict} url={result.get('url', '')[:80]}")
    for m in result["markers"]:
        print(f"    {m['label']}: count={m['count']} visible={m['visible']}")
    if result.get("server") is not None:
        print(f"    server: {json.dumps(result['server'], ensure_ascii=False)[:200]}")
    return rc


def main():
    ap = argparse.ArgumentParser(description="发布链只读探针（登录态/页面形态/服务端判据）")
    ap.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    ap.add_argument("--account", default="diyi")
    ap.add_argument("--out-dir", default="/tmp/sau_probe")
    args = ap.parse_args()
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(asyncio.run(probe(args.platform, args.account, repo_root, args.out_dir)))


if __name__ == "__main__":
    main()
