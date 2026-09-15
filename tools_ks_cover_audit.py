#!/usr/bin/env python3
"""tools_ks_cover_audit.py — 快手历史作品封面存活批量核查（2026-09-15 固化）。

用法：python3 tools_ks_cover_audit.py [--limit 20] [--ref <本地封面.png> ...]
逻辑：登录态进管理页抓每条作品缩略图 →（可选）与 --ref 本地封面哈希比对 →
     终裁=图片颜色数（纯色占位/纯黑 <10 色判为「无有效封面」），输出人工核查清单。
"""
import argparse, asyncio, io, json, sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from patchright.async_api import async_playwright

COOKIE = "/home/lmr/social-auto-upload/cookies/kuaishou_diyi.json"
CHROME = "/home/lmr/.cache/ms-playwright/chromium-1226/chrome-linux64/chrome"

def ahash_bytes(b):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(b)).convert('RGB').resize((32,32))
        px = list(im.getdata()); avg = sum(sum(p) for p in px)/(len(px)*3)
        return ''.join('1' if sum(p)/3>avg else '0' for p in px)
    except Exception:
        return None

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--ref', action='append', default=[], help='本地封面，输出与其距离')
    a = ap.parse_args()
    refs = [(Path(p).name, ahash_bytes(Path(p).read_bytes())) for p in a.ref]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=CHROME)
        ctx = await browser.new_context(storage_state=COOKIE)
        page = await ctx.new_page()
        await page.goto("https://cp.kuaishou.com/article/manage/video", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(12000)
        for _ in range(6):
            await page.mouse.wheel(0, 1500); await page.wait_for_timeout(1200)
        items = await page.evaluate("""(limit) => {
            const out = [];
            document.querySelectorAll('div.video-item').forEach(it => {
                const img = it.querySelector('img');
                if (img) out.push({txt:(it.innerText||'').slice(0,60).replace(/\\n/g,' '),
                                   src: img.currentSrc||img.src});
            });
            return out.slice(0, limit);
        }""", a.limit)
        await ctx.close(); await browser.close()

    print(f"抓到 {len(items)} 条\n")
    problems = []
    for it in items:
        try:
            req = urllib.request.Request(it['src'], headers={'User-Agent':'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=12).read()
        except Exception as e:
            print(f"✂️ 下载失败 | {it['txt'][:40]} | {e}")
            continue
        im_hash = ahash_bytes(data)
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert('RGB')
        colors = im.getcolors(maxcolors=200000)
        n_colors = len(colors) if colors else 999999
        verdict = "OK " if n_colors > 50 else "❌ 无效封面(纯色占位)"
        extra = ""
        if n_colors <= 50:
            problems.append(it['txt'][:40])
        if refs and im_hash:
            best = min(((name, sum(x!=y for x,y in zip(im_hash,h))) for name,h in refs if h), key=lambda t:t[1], default=None)
            if best: extra = f" | 最近似 {best[0]} d={best[1]}"
        print(f"{verdict} colors={n_colors:>6} | {it['txt'][:42]}{extra}")
    print(f"\n结论：{len(problems)} 条需补封面" + (":\n  " + "\n  ".join(problems) if problems else "，全部正常 ✅"))

asyncio.run(main())
