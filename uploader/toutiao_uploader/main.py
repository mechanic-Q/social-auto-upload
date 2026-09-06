# -*- coding: utf-8 -*-
"""今日头条（头条号 mp.toutiao.com）视频发布通道。

页面交互基于创作者后台的一般结构实现；发布页为 SPA 且平台常改版，
选择器集中放在常量区，实测后在此修正。
"""
from __future__ import annotations

import asyncio
import inspect, re
import os
from datetime import datetime
from pathlib import Path

from patchright.async_api import Page
from patchright.async_api import Playwright
from patchright.async_api import async_playwright

from conf import DEBUG_MODE, LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from uploader.base_video import BaseVideoUploader
from utils.base_social_media import set_init_script
from utils.files_times import get_absolute_path
from utils.login_qrcode import build_login_qrcode_path
from utils.login_qrcode import decode_qrcode_from_path
from utils.login_qrcode import print_terminal_qrcode
from utils.login_qrcode import remove_qrcode_file
from utils.login_qrcode import save_data_url_image
from utils.log import toutiao_logger

# 实测：头条发视频走西瓜上传通道（/profile_v4/video/upload 是不渲染的后台壳页）
TOUTIAO_UPLOAD_URL = "https://mp.toutiao.com/profile_v4/xigua/upload-video"
TOUTIAO_MANAGE_URL = "https://mp.toutiao.com/profile_v4/graphic/publish/manage"
# 实测：带尾斜杠的 auth/page/login/ 是废弃空壳页；不带尾斜杠的才渲染登录 UI。
# 更稳的做法是直接打开后台页，由后台重定向到真实登录页。
TOUTIAO_LOGIN_URL = "https://mp.toutiao.com/auth/page/login?redirect_url=%2Fprofile_v4%2Fvideo%2Fupload"
TOUTIAO_UPLOAD_URL_PATTERN = "**/profile_v4/xigua/upload-video**"
TOUTIAO_MANAGE_URL_PATTERN = "**/profile_v4/graphic/publish/manage**"
# 登录态失效时后台会跳到登录页
TOUTIAO_LOGIN_URL_KEYWORD = "auth/page/login"
TOUTIAO_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
TOUTIAO_PUBLISH_STRATEGY_SCHEDULED = "scheduled"
# 实测（2026-09-06）：标题上限 300 字，话题最多 10 个
TOUTIAO_MAX_TAGS = 10
TOUTIAO_TITLE_MAX_LEN = 300
# 实测：西瓜上传通道的视频发布页没有活动入口（活动是文章/微头条功能），
# 传 --activity 会明确报错终止而不是静默跳过。
TOUTIAO_ACTIVITY_UNSUPPORTED = True
# 作品声明是 checkbox 组（byte-checkbox），常见项：AI生成、自行拍摄、允许转载、
# 引用内容、虚构演绎、影视综艺等；文案以页面实际渲染为准。
TOUTIAO_DECLARATION_ITEM_SELECTOR = 'label.byte-checkbox'


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


async def _emit_qrcode_callback(qrcode_callback, payload: dict):
    if not qrcode_callback:
        return
    callback_result = qrcode_callback(payload)
    if inspect.isawaitable(callback_result):
        await callback_result


def _build_login_result(
    success: bool,
    status: str,
    message: str,
    account_file: str,
    qrcode: dict | None = None,
    current_url: str = "",
) -> dict:
    return {
        "success": success,
        "status": status,
        "message": message,
        "account_file": str(account_file),
        "qrcode": qrcode,
        "current_url": current_url,
    }


def _looks_logged_out(url: str) -> bool:
    return TOUTIAO_LOGIN_URL_KEYWORD in url


async def _save_toutiao_qrcode(page: Page, account_file: str, previous_qrcode_path: Path | None = None, qrcode_callback=None) -> dict:
    """从登录页抓二维码：实测二维码是页面上 132px 的 data-URL img（2026-09-05）。"""
    login_root = page.locator("body")

    # 二维码 img 是 data-URL（页面上的 logo 等都是 http URL，data-URL 选择器天然精准）
    qrcode_img = login_root.locator('img[src^="data:image"]').first
    try:
        if not await qrcode_img.count() or not await qrcode_img.is_visible():
            # 兜底：旧版页面可能有 qrcode 关键字的 src 或需要先点"扫码登录"
            qrcode_img = login_root.locator('img[src*="qrcode"], div.qrcode img').first
            if not await qrcode_img.count() or not await qrcode_img.is_visible():
                switch = login_root.locator("text=/扫码登录|二维码登录/").first
                await switch.click(timeout=5000)
                await asyncio.sleep(1)
    except Exception:
        pass

    await qrcode_img.wait_for(state="visible", timeout=15000)
    qrcode_src = await qrcode_img.get_attribute("src")
    if not qrcode_src:
        raise RuntimeError("未获取到头条登录二维码地址")
    if not qrcode_src.startswith("data:image") and not qrcode_src.startswith("http"):
        qrcode_src = f"data:image/png;base64,{qrcode_src}"

    qrcode_path = save_data_url_image(qrcode_src, build_login_qrcode_path(account_file, suffix="toutiao_login_qrcode"))
    if previous_qrcode_path and previous_qrcode_path != qrcode_path:
        if remove_qrcode_file(previous_qrcode_path):
            toutiao_logger.info(_msg("🧹", f"临时二维码文件已清理: {previous_qrcode_path}"))

    toutiao_logger.info(_msg("🖼️", f"二维码已经准备好啦，已保存到: {qrcode_path}"))
    qrcode_content = decode_qrcode_from_path(qrcode_path)
    if qrcode_content:
        print_terminal_qrcode(qrcode_content, qrcode_path, "头条APP")
    else:
        toutiao_logger.warning(_msg("😵", f"终端没法完整显示二维码，请打开 {qrcode_path} 扫码"))

    qrcode_info = {
        "image_path": str(qrcode_path),
        "image_data_url": qrcode_src,
    }
    await _emit_qrcode_callback(qrcode_callback, qrcode_info)
    return qrcode_info


async def _is_toutiao_qrcode_expired(page: Page) -> bool:
    expired = page.locator("text=/二维码(已)?过期|已失效|刷新重试/").first
    try:
        if not await expired.count():
            return False
        return await expired.is_visible()
    except Exception:
        return False


async def cookie_auth(account_file, headless: bool = True) -> bool:
    async with async_playwright() as playwright:
        if LOCAL_CHROME_PATH:
            browser = await playwright.chromium.launch(headless=headless, executable_path=LOCAL_CHROME_PATH)
        else:
            browser = await playwright.chromium.launch(headless=headless, channel="chromium")
        try:
            context = await browser.new_context(storage_state=str(account_file))
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto(TOUTIAO_UPLOAD_URL)
            await asyncio.sleep(3)
            if _looks_logged_out(page.url):
                toutiao_logger.info(_msg("🥹", "cookie 已失效，得重新登录一下"))
                return False

            toutiao_logger.success(_msg("🥳", "cookie 有效"))
            return True
        except Exception as exc:
            toutiao_logger.warning(_msg("😵", f"cookie 校验时出错，按失效处理: {exc}"))
            return False
        finally:
            await browser.close()


async def toutiao_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless: bool = LOCAL_CHROME_HEADLESS):
    account_file = get_absolute_path(account_file, "toutiao_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(str(account_file)):
        if not handle:
            result = _build_login_result(False, "cookie_invalid", "cookie文件不存在或已失效", account_file)
            return result if return_detail else False
        toutiao_logger.info(_msg("🥹", "cookie 失效了，准备重新登录头条号后台"))
        result = await get_toutiao_cookie(account_file, qrcode_callback=qrcode_callback, headless=headless)
        return result if return_detail else result["success"]

    result = _build_login_result(True, "cookie_valid", "cookie有效", account_file)
    return result if return_detail else True


async def get_toutiao_cookie(
    account_file,
    qrcode_callback=None,
    headless: bool = LOCAL_CHROME_HEADLESS,
    poll_interval: int = 3,
    max_checks: int = 300,
):
    if headless:
        toutiao_logger.info(_msg("🖼️", "头条登录将以无头模式运行，小人会输出终端二维码并保存本地二维码图片"))

    async with async_playwright() as playwright:
        if LOCAL_CHROME_PATH:
            browser = await playwright.chromium.launch(headless=headless, executable_path=LOCAL_CHROME_PATH)
        else:
            browser = await playwright.chromium.launch(headless=headless, channel="chromium")
        context = await browser.new_context()
        context = await set_init_script(context)
        qrcode_path = None
        qrcode_info = None
        result = _build_login_result(False, "failed", "头条登录失败", account_file)
        page = None
        try:
            page = await context.new_page()
            # 实测：直接 goto 登录页 URL 会卡在 load；打开后台页让其重定向到登录页更稳
            await page.goto(TOUTIAO_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
            toutiao_logger.info(_msg("🧍", "请在浏览器里扫码登录头条号（支持头条/抖音APP扫码）"))
            try:
                await page.wait_for_url("**/auth/page/login**", timeout=30000)
            except Exception:
                pass  # 已登录状态下不会重定向，后续 cookie_auth 会给出结论
            await asyncio.sleep(3)

            if not _looks_logged_out(page.url):
                # 未被重定向到登录页：cookie 可能已有效
                await context.storage_state(path=str(account_file))
                if await cookie_auth(str(account_file)):
                    toutiao_logger.success(_msg("🥳", "已有登录态有效，无需扫码"))
                    result = _build_login_result(True, "success", "已有登录态有效", account_file, current_url=page.url)
                    return result

            qrcode_info = await _save_toutiao_qrcode(page, account_file, qrcode_callback=qrcode_callback)
            qrcode_path = Path(qrcode_info["image_path"])

            for _ in range(max_checks):
                current_url = page.url
                if not _looks_logged_out(current_url) and "passport" not in current_url:
                    await context.storage_state(path=str(account_file))
                    if await cookie_auth(str(account_file)):
                        toutiao_logger.success(_msg("🥳", "头条扫码登录成功，小人开心收工"))
                        result = _build_login_result(True, "success", "头条扫码登录成功", account_file, qrcode_info, current_url)
                    else:
                        toutiao_logger.error(_msg("😢", "头条扫码完成了，但 cookie 校验失败"))
                        result = _build_login_result(False, "cookie_invalid", "头条扫码流程结束，但 cookie 校验失败", account_file, qrcode_info, current_url)
                    return result

                # 页面二维码约 3 分钟自动刷新，但过期提示文案未实测可靠；
                # 每 ~30 秒主动重抓当前页面的二维码图片，桌面/文件里的码始终跟页面一致
                if _ % 10 == 9:
                    try:
                        qrcode_info = await _save_toutiao_qrcode(page, account_file, qrcode_path, qrcode_callback=qrcode_callback)
                        qrcode_path = Path(qrcode_info["image_path"])
                    except Exception:
                        pass  # 抓取失败不中断登录等待

                await asyncio.sleep(poll_interval)

            result = _build_login_result(False, "timeout", "等待头条扫码登录超时", account_file, qrcode_info, page.url)
        except Exception as exc:
            result = _build_login_result(False, "failed", str(exc), account_file, current_url=page.url if page else "")
        finally:
            if remove_qrcode_file(qrcode_path):
                toutiao_logger.info(_msg("🧹", f"临时二维码文件已清理: {qrcode_path}"))
            if not result["success"]:
                toutiao_logger.error(_msg("😢", f"登录失败: {result['message']}"))
            await context.close()
            await browser.close()

    return result


class ToutiaoVideo(BaseVideoUploader):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime | int,
        account_file,
        publish_strategy: str | None = None,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
        thumbnail_path=None,
        desc: str | None = None,
        activity: str | None = None,
        declaration: str | None = None,
        draft: bool = False,
    ):
        self.publish_date = publish_date
        self.account_file = str(account_file)
        self.draft = draft
        self.publish_strategy = publish_strategy
        self.debug = debug
        self.headless = headless
        self.local_executable_path = LOCAL_CHROME_PATH
        self.title = title
        self.file_path = file_path
        self.tags = tags or []
        self.thumbnail_path = thumbnail_path
        self.desc = desc or ""
        self.activity = activity
        # 与抖音先例一致：显式要求声明原创，没做到就终止发布
        self.declaration = declaration

        if self.publish_strategy is None:
            self.publish_strategy = (
                TOUTIAO_PUBLISH_STRATEGY_SCHEDULED if self.publish_date != 0 else TOUTIAO_PUBLISH_STRATEGY_IMMEDIATE
            )
        if self.publish_strategy not in {TOUTIAO_PUBLISH_STRATEGY_IMMEDIATE, TOUTIAO_PUBLISH_STRATEGY_SCHEDULED}:
            raise ValueError(f"不支持的发布策略: {self.publish_strategy}")
        if self.publish_strategy == TOUTIAO_PUBLISH_STRATEGY_SCHEDULED:
            self.publish_date = self.validate_publish_date(self.publish_date)
        else:
            self.publish_date = 0

    async def validate_base_args(self):
        if not os.path.exists(self.account_file):
            raise RuntimeError(f"cookie文件不存在，请先完成头条登录: {self.account_file}")
        if not await cookie_auth(self.account_file):
            raise RuntimeError(f"cookie文件已失效，请先完成头条登录: {self.account_file}")

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("头条视频上传时，title 是必须的")
        if len(self.title) > TOUTIAO_TITLE_MAX_LEN:
            raise ValueError(f"头条视频标题超过 {TOUTIAO_TITLE_MAX_LEN} 字（当前 {len(self.title)} 字）: {self.title}")
        self.file_path = str(self.validate_video_file(self.file_path))
        if self.thumbnail_path:
            self.thumbnail_path = str(self.validate_image_file(self.thumbnail_path))
        if len(self.tags) > TOUTIAO_MAX_TAGS:
            toutiao_logger.warning(
                _msg("🏷️", f"话题 {len(self.tags)} 个超过保守上限 {TOUTIAO_MAX_TAGS} 个，"
                            f"仅使用前 {TOUTIAO_MAX_TAGS} 个: {self.tags[:TOUTIAO_MAX_TAGS]}")
            )
            self.tags = self.tags[:TOUTIAO_MAX_TAGS]

    async def wait_for_upload_complete(self, page: Page) -> None:
        max_retries = 90
        for retry_count in range(max_retries):
            try:
                if await page.locator("text=/上传中|上传进度/").count() == 0:
                    toutiao_logger.success(_msg("🥳", "视频已经传完啦"))
                    return
                if retry_count % 5 == 0:
                    toutiao_logger.info(_msg("🏃", "小人正在努力上传视频"))
                if await page.locator("text=上传失败").count():
                    toutiao_logger.warning(_msg("😵", "视频上传摔了一跤，小人马上重新上传"))
                    await page.locator('input[type="file"]').first.set_input_files(self.file_path)
            except Exception as exc:
                toutiao_logger.warning(_msg("😵", f"检查上传状态时出错，小人继续重试: {exc}"))
            await asyncio.sleep(2)
        raise RuntimeError("超过最大重试次数，视频上传未完成")

    async def set_thumbnail(self, page: Page) -> None:
        if not self.thumbnail_path:
            return

        toutiao_logger.info(_msg("🖼️", "小人准备设置封面"))
        toggle = page.locator("text=/设置封面|编辑封面|上传封面/").first
        await toggle.wait_for(state="visible", timeout=30000)
        await toggle.click()

        modal = page.locator('div[class*="modal"], div[role="dialog"]').last
        await modal.wait_for(state="visible", timeout=15000)
        # 弹窗里优先"上传封面"tab / 本地上传入口
        upload_tab = modal.locator("text=/上传封面|本地上传/").first
        if await upload_tab.count():
            await upload_tab.click()
            await asyncio.sleep(1)

        file_input = modal.locator('input[type="file"][accept*="image"]')
        await file_input.wait_for(state="attached", timeout=30000)
        await file_input.set_input_files(self.thumbnail_path)
        await asyncio.sleep(2)

        # 2026-09-06 四修（DOM dump 定案）：按钮 = .btn-sure「确定」，容器 = .m-xigua-dialog.m-modal；
        # 旧 .m-dialog-edit/[role=dialog] 选择器完全失配；图片处理完 DOM 尾部会多挂一个
        # 不可见的空 .m-shark-modal，容器用 .last 会选错——按「modal 内可见按钮」过滤；
        # visible ≠ enabled：处理中确定按钮就是 disabled 红钮，:not([disabled]) + 未关闭重试（≤3 次）
        btn = page.locator('div[class*="modal"] button:visible:not([disabled])',
                           has_text=re.compile(r"确定|完成|确认")).last
        clicked = False
        for attempt in range(3):
            box = None
            try:
                await btn.wait_for(state="visible", timeout=90000 if attempt == 0 else 30000)
                b = await btn.bounding_box()
                if b:
                    box = {"x": b["x"] + b["width"] / 2, "y": b["y"] + b["height"] / 2}
            except Exception:
                box = None
            if not box:  # 兜底：querySelectorAll 全局搜（不依赖容器类名，只收 enabled）
                for _ in range(10):
                    box = await page.evaluate(
                        """() => {
                        const btns = [...document.querySelectorAll('div[class*="modal"] button, .m-xigua-dialog button')]
                          .filter(b => /确定|完成|确认/.test(b.innerText.trim()) && !b.disabled
                                       && (b.offsetParent || b.getClientRects().length));
                        if (!btns.length) return null;
                        const r = btns[btns.length - 1].getBoundingClientRect();
                        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                    }""")
                    if box:
                        break
                    await asyncio.sleep(3)
            if not box:
                break
            await page.mouse.click(box["x"], box["y"])
            clicked = True
            toutiao_logger.info(_msg("🖱️", f"鼠标物理点击确认键 @({box['x']:.0f},{box['y']:.0f}) 第{attempt + 1}次"))
            try:
                await modal.wait_for(state="hidden", timeout=10000)
                break  # 弹窗已关 = 封面确认成功
            except Exception:
                toutiao_logger.warning(_msg("😵", f"第{attempt + 1}次点击后弹窗未关（按钮可能仍 disabled），重试"))
        else:
            await page.screenshot(path="/tmp/toutiao_after_click.png", full_page=True)
            if clicked:
                raise RuntimeError("封面弹窗点击 3 次仍未关闭（确定按钮始终无效）")
            raise RuntimeError("封面弹窗确定按钮不可点（locator+querySelectorAll 双失败）")
        toutiao_logger.success(_msg("🥳", "封面已经设置完成"))

    async def set_activity(self, page: Page) -> None:
        """头条视频发布页（西瓜上传通道）没有活动入口（2026-09-06 实测）。
        显式传了 --activity 时明确报错终止，不静默跳过。"""
        if not self.activity:
            return
        raise RuntimeError(
            f"头条视频发布页当前不提供活动入口（实测 2026-09-06），无法参加活动 '{self.activity}'。"
            "活动功能目前仅支持快手（活动推荐卡片）。为避免发布与预期不符，已终止。"
        )

    async def apply_declaration(self, page: Page) -> None:
        """勾选"作品声明"区指定 checkbox（如 AI生成/自行拍摄/引用内容）。
        显式传了 --declaration 却没勾上时终止发布（照抖音先例）。"""
        if not self.declaration:
            return

        toutiao_logger.info(_msg("📝", f"小人准备勾选作品声明: {self.declaration}"))
        item = page.locator(TOUTIAO_DECLARATION_ITEM_SELECTOR).filter(has_text=self.declaration).first
        try:
            await item.wait_for(state="visible", timeout=10000)
        except Exception:
            raise RuntimeError(
                f"作品声明区没有找到选项 '{self.declaration}'（常见: AI生成/自行拍摄/引用内容/虚构演绎等，"
                "以发布页实际渲染为准）。声明失败，已终止发布。"
            )

        # byte-checkbox 已勾选时 inner checkbox 带 checked 属性
        already = await item.locator('input[type="checkbox"]:checked').count()
        if not already:
            await item.click()
            await asyncio.sleep(1)
            already = await item.locator('input[type="checkbox"]:checked').count()
            if not already:
                raise RuntimeError(
                    f"声明 '{self.declaration}' 点击后未变为勾选状态（可能账号无该声明权限），已终止发布。"
                )
        toutiao_logger.success(_msg("🥳", f"已勾选声明: {self.declaration}"))

    async def set_schedule_time(self, page: Page, publish_date: datetime) -> None:
        toutiao_logger.info(_msg("🕒", "小人准备设置定时发布时间"))
        publish_date_str = publish_date.strftime("%Y-%m-%d %H:%M")

        toggle = page.locator("text=/定时发布/").first
        await toggle.wait_for(state="visible", timeout=10000)
        await toggle.click()
        await asyncio.sleep(1)

        time_input = page.locator('input[placeholder*="日期"], input[placeholder*="时间"]').first
        await time_input.wait_for(state="visible", timeout=10000)
        js_code = """
        (args) => {
            const [selectorHint, newValue] = args;
            const inputs = [...document.querySelectorAll('input')].filter(i =>
                (i.placeholder || '').includes(selectorHint));
            const input = inputs[0];
            if (!input) return false;
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            nativeSetter.call(input, newValue);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        """
        ok = await page.evaluate(js_code, ["日期", publish_date_str])
        if not ok:
            raise RuntimeError("找不到定时发布的时间输入框")
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        await asyncio.sleep(2)
        toutiao_logger.info(f"✅ 定时发布时间已设置为 {publish_date_str}")

    async def submit_publish(self, page: Page) -> None:
        footer = page.locator(".video-batch-footer .button-group").first
        try:
            await footer.wait_for(state="visible", timeout=30000)
        except Exception:
            # 0906 深夜实证：AI 声明勾选后 footer 可能 >30s 才渲染（懒加载/服务端慢），
            # 先截图留证再放宽等 60s；两次都没出才放弃
            await page.screenshot(path="/tmp/toutiao_footer_debug.png", full_page=True)
            await footer.wait_for(state="visible", timeout=60000)

        if self.draft:
            draft_btn = footer.get_by_text("存草稿", exact=True).first
            await draft_btn.click()
            await page.wait_for_timeout(4000)
            # 成功信号：跳转到管理页或出现成功提示；失败则截图报错
            if "manage" in page.url or await page.locator("text=/保存成功|提交成功/").count():
                toutiao_logger.success(_msg("🥳", "草稿已保存（未发布），小人开心收工"))
                return
            if self.debug:
                await page.screenshot(full_page=True)
            raise RuntimeError("点击存草稿后未检测到成功信号，请到后台核验，禁止重复点击")

        publish_btn = footer.get_by_text("发布", exact=True).first
        await publish_btn.click()
        try:
            await page.wait_for_url(TOUTIAO_MANAGE_URL_PATTERN, timeout=30000)
            toutiao_logger.success(_msg("🥳", "视频发布成功，小人开心收工"))
            from collector.events import safe_append_publish_event
            safe_append_publish_event("toutiao", self.account_file, self.title)
            return
        except Exception:
            pass

        # 可能出现二次确认弹窗（声明提醒/发布确认）
        confirm = page.locator('button:has-text("确认"), button:has-text("确定")').last
        try:
            if await confirm.count() and await confirm.is_visible():
                await confirm.click()
                await page.wait_for_url(TOUTIAO_MANAGE_URL_PATTERN, timeout=30000)
                toutiao_logger.success(_msg("🥳", "视频发布成功，小人开心收工"))
                from collector.events import safe_append_publish_event
                safe_append_publish_event("toutiao", self.account_file, self.title)
                return
        except Exception:
            pass

        if self.debug:
            await page.screenshot(full_page=True)
        raise RuntimeError("点击发布后未跳转到内容管理页，请到后台核验是否已发布，禁止重复点击发布")

    async def fill_title_description_and_tags(self, page: Page) -> None:
        # 实测：标题 input 上传后已自动填入文件名，必须清空重填
        title_input = page.get_by_placeholder("标题和简介").first
        if not await title_input.count():
            title_input = page.locator('div[class*="basic"] input, input.ipt').first
        await title_input.wait_for(state="visible", timeout=30000)
        await title_input.click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")
        await page.keyboard.type(self.title, delay=20)
        await asyncio.sleep(1)

        if self.desc:
            desc_input = page.get_by_placeholder("请输入视频简介").first
            if await desc_input.count():
                await desc_input.click()
                await page.keyboard.type(self.desc[:60], delay=20)
                await asyncio.sleep(1)

        # 话题：独立输入框，输入后从联想下拉选择；等不到候选则跳过
        topic_input = page.get_by_placeholder("请输入，最多可添加10个话题").first
        if not await topic_input.count():
            topic_input = page.get_by_placeholder("请输入").first
        for index, tag in enumerate(self.tags, start=1):
            toutiao_logger.info(_msg("🏷️", f"小人正在添加第 {index} 个话题: #{tag}"))
            if not await topic_input.count():
                toutiao_logger.warning(_msg("😵", "没有找到话题输入框，跳过剩余话题"))
                break
            await topic_input.click()
            await topic_input.fill(tag)
            await page.wait_for_timeout(2000)
            suggestion = page.locator(
                '[class*="suggest"] li, [class*="dropdown"] li, [class*="option"]'
            ).first
            try:
                if await suggestion.count() and await suggestion.is_visible():
                    await suggestion.click()
                    await asyncio.sleep(1)
                else:
                    await topic_input.fill("")
                    toutiao_logger.warning(_msg("😵", f"话题 #{tag} 没有匹配的平台候选，已跳过"))
            except Exception:
                await topic_input.fill("")
                toutiao_logger.warning(_msg("😵", f"话题 #{tag} 选择失败，已跳过"))

    async def upload(self, playwright: Playwright) -> None:
        toutiao_logger.info(_msg("🧍", "小人先检查 cookie、视频文件、封面和发布时间"))
        await self.validate_upload_args()
        toutiao_logger.info(_msg("🥳", "上传前检查通过"))

        if self.local_executable_path:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                executable_path=self.local_executable_path,
            )
        else:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                channel="chromium",
            )
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)

        upload_success = False
        try:
            page = await context.new_page()
            await page.goto(TOUTIAO_UPLOAD_URL)
            toutiao_logger.info(_msg("🧭", "小人正在赶往头条视频发布页"))
            await page.wait_for_url(TOUTIAO_UPLOAD_URL_PATTERN)
            await asyncio.sleep(3)

            toutiao_logger.info(_msg("🏃", f"小人开始搬运视频: {self.title}.mp4"))
            upload_input = page.locator('input[type="file"]').first
            await upload_input.wait_for(state="attached", timeout=30000)
            await upload_input.set_input_files(self.file_path)
            await asyncio.sleep(2)

            await self.fill_title_description_and_tags(page)
            await self.wait_for_upload_complete(page)
            await self.set_activity(page)
            await self.set_thumbnail(page)
            await self.apply_declaration(page)
            if self.publish_strategy == TOUTIAO_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
                if not self.draft:  # 存草稿时无需定时设置
                    await self.set_schedule_time(page, self.publish_date)
            await self.submit_publish(page)

            upload_success = True
        finally:
            if upload_success:
                await context.storage_state(path=self.account_file)
                toutiao_logger.success(_msg("🥳", "cookie 更新完毕"))
                await asyncio.sleep(2)
            await context.close()
            await browser.close()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


async def list_toutiao_activities(account_file, headless: bool = LOCAL_CHROME_HEADLESS) -> list[dict]:
    """活动发现：实测（2026-09-06）头条视频发布页（西瓜上传通道）没有活动入口，
    活动功能在头条体系内挂载于文章/微头条。诚实返回空列表，由 CLI 输出说明。"""
    toutiao_logger.warning(_msg("😵", "头条视频发布页当前不提供活动入口（实测），返回空列表"))
    return []
