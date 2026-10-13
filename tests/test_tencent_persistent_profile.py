import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import uploader.tencent_uploader.main as tencent_main


class FakeChromium:
    def __init__(self):
        self.launch_calls = []
        self.persistent_calls = []

    async def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        return object()

    async def launch_persistent_context(self, user_data_dir, **kwargs):
        self.persistent_calls.append((Path(user_data_dir), kwargs))
        return "context"


class FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium


class FakeEmptyLocator:
    @property
    def first(self):
        return self

    def locator(self, selector):
        return self

    async def count(self):
        return 0

    async def is_visible(self):
        return False

    async def click(self):
        raise AssertionError("empty locator should not be clicked")


class FakeVisibleLocator:
    def __init__(self, src=None, visible=True):
        self._src = src
        self._visible = visible
        self.clicked = False
        self.screenshot_path = None

    @property
    def first(self):
        return self

    def locator(self, selector):
        return self

    async def count(self):
        return 1

    async def is_visible(self):
        return self._visible

    async def wait_for(self, **_kwargs):
        return None

    async def get_attribute(self, name):
        return self._src if name == "src" else None

    async def evaluate(self, _script, arg=None):
        # 2026-09 实现: iframe 内 fetch 二维码转 data URL(替代会卡死的 screenshot)
        return "data:image/png;base64,QUFB"

    async def screenshot(self, path):
        self.screenshot_path = Path(path)
        self.screenshot_path.write_bytes(b"png")

    async def click(self):
        self.clicked = True


class FakeFrame:
    url = ""

    def __init__(self, selectors):
        self.selectors = selectors

    def locator(self, selector):
        for key, locator in self.selectors.items():
            if selector == key or selector.startswith(key):
                return locator
        return FakeEmptyLocator()


class FakeQrResponse:
    """模拟 page.context.request.get 的二维码图片响应（上游 fetch 形态）。"""

    ok = True

    headers = {"content-type": "image/png"}

    async def body(self):
        return b"qr-bytes"


class FakeRequestContext:
    async def get(self, _url):
        return FakeQrResponse()


class FakeQrContext:
    def __init__(self):
        self.request = FakeRequestContext()


class FakeQrImg:
    """上游二维码提取：img.qrcode 相对 src，经 context.request 下载转 data URL。"""

    def __init__(self, src):
        self._src = src
        self._polls = 0

    @property
    def first(self):
        return self

    async def count(self):
        return 1

    async def wait_for(self, **_kwargs):
        return None

    async def get_attribute(self, name):
        if name != "src":
            return None
        self._polls += 1
        return self._src

    async def screenshot(self, path):
        raise AssertionError("上游实现不得再用 screenshot 抓二维码")


class FakeQrFrame:
    """登录 iframe：url 含 qrconnect 域，img.qrcode 提供相对 src。"""

    def __init__(self, src):
        self.url = "https://open.weixin.qq.com/connect/qrconnect?state=demo"

    def locator(self, selector):
        if selector == "img.qrcode":
            return FakeQrImg("/connect/qrcode/demo")
        return FakeEmptyLocator()


class FakePage:
    url = "https://channels.weixin.qq.com/login.html"

    def __init__(self, selectors, frames=None, context=None):
        self.selectors = selectors
        self.frames = frames if frames is not None else [FakeFrame(selectors)]
        self.goto_calls = []
        if context is not None:
            self.context = context

    def locator(self, selector):
        # 上游实现改为 page 级 locator 探测（含裸 selector 兜底），mock 同步该形态
        hit = self.selectors.get(selector)
        return hit if hit is not None else FakeEmptyLocator()

    async def wait_for_timeout(self, _milliseconds):
        return None

    async def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))


class TencentPersistentProfileTests(unittest.TestCase):
    def test_profile_dir_is_derived_from_tencent_account_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_base_dir = tencent_main.BASE_DIR
            try:
                tencent_main.BASE_DIR = Path(tmp_dir)
                account_file = Path(tmp_dir) / "cookies" / "tencent_diyi.json"

                profile_dir = Path(tencent_main._resolve_persistent_profile_dir(account_file))
            finally:
                tencent_main.BASE_DIR = original_base_dir

        self.assertEqual(
            profile_dir,
            Path(tmp_dir) / "cookies" / "tencent_profiles" / "diyi",
        )

    def test_launch_context_uses_persistent_profile_when_forced(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_base_dir = tencent_main.BASE_DIR
            try:
                tencent_main.BASE_DIR = Path(tmp_dir)
                account_file = Path(tmp_dir) / "cookies" / "tencent_diyi.json"
                chromium = FakeChromium()

                context, browser = asyncio.run(
                    tencent_main._launch_tencent_context(
                        FakePlaywright(chromium),
                        account_file,
                        headless=False,
                        storage_state=False,
                        persistent=True,
                    )
                )
            finally:
                tencent_main.BASE_DIR = original_base_dir

        self.assertEqual(context, "context")
        self.assertIsNone(browser)
        self.assertEqual(chromium.launch_calls, [])
        self.assertEqual(
            chromium.persistent_calls[0][0],
            Path(tmp_dir) / "cookies" / "tencent_profiles" / "diyi",
        )

    def test_save_qrcode_screenshots_visible_wechat_connect_qr(self):
        import base64

        with tempfile.TemporaryDirectory() as tmp_dir:
            account_file = Path(tmp_dir) / "cookies" / "tencent_diyi.json"
            qr_path = Path(tmp_dir) / "cookies" / "qr.png"

            saved = {}

            def fake_save_data_url_image(data_url, path):
                saved["data_url"] = data_url
                return path

            fake_utils = {
                "build_login_qrcode_path": lambda account, suffix: qr_path,
                "decode_qrcode_from_path": lambda path: None,
                "print_terminal_qrcode": lambda *args, **kwargs: None,
                "remove_qrcode_file": lambda path: False,
                "save_data_url_image": fake_save_data_url_image,
            }
            page = FakePage({}, frames=[FakeQrFrame("/connect/qrcode/demo")], context=FakeQrContext())
            with patch("uploader.tencent_uploader.main._get_qrcode_utils", return_value=fake_utils):
                info = asyncio.run(tencent_main._save_tencent_qrcode(page, str(account_file)))

        # 2026-09 实现: 相对 src 走 qrconnect iframe + context.request 下载 → data URL 落盘
        expected_data_url = "data:image/png;base64," + base64.b64encode(b"qr-bytes").decode()
        self.assertEqual(saved["data_url"], expected_data_url)
        self.assertEqual(info["image_path"], str(qr_path))
        self.assertEqual(info["image_data_url"], expected_data_url)

    def test_expired_qrcode_is_detected_inside_login_iframe(self):
        expired_tip = FakeVisibleLocator()
        page = FakePage({'div.mask.show p.refresh-tip:has-text("二维码已过期，点击刷新")': expired_tip})

        self.assertTrue(asyncio.run(tencent_main._is_tencent_qrcode_expired(page)))

    def test_hidden_bare_refresh_tip_is_not_treated_as_expired(self):
        # 上游 page 级 locator 含裸 selector 兜底：不可见（隐藏）的 tip 不算过期
        hidden_template_tip = FakeVisibleLocator(visible=False)
        page = FakePage({'p.refresh-tip:has-text("二维码已过期，点击刷新")': hidden_template_tip})

        self.assertFalse(asyncio.run(tencent_main._is_tencent_qrcode_expired(page)))

    def test_refresh_qrcode_clicks_refresh_tip_inside_login_iframe(self):
        refresh_tip = FakeVisibleLocator()
        page = FakePage({'div.mask.show p.refresh-tip:has-text("二维码已过期，点击刷新")': refresh_tip})

        asyncio.run(tencent_main._refresh_tencent_qrcode(page))

        self.assertTrue(refresh_tip.clicked)

    def test_wait_refreshes_qrcode_by_time_before_timeout(self):
        page = FakePage({})
        refreshed_info = {"image_path": "/tmp/qr2.png"}

        with patch(
            "uploader.tencent_uploader.main._is_tencent_login_completed",
            new=AsyncMock(return_value=False),
        ), patch(
            "uploader.tencent_uploader.main._is_tencent_qrcode_scanned",
            new=AsyncMock(return_value=False),
        ), patch(
            "uploader.tencent_uploader.main._is_tencent_qrcode_expired",
            new=AsyncMock(return_value=True),
        ), patch(
            "uploader.tencent_uploader.main._refresh_tencent_qrcode",
            new=AsyncMock(),
        ) as refresh_qr, patch(
            "uploader.tencent_uploader.main._save_tencent_qrcode",
            new=AsyncMock(return_value=refreshed_info),
        ) as save_qr, patch(
            "uploader.tencent_uploader.main.asyncio.sleep",
            new=AsyncMock(),
        ):
            result = asyncio.run(
                tencent_main._wait_for_tencent_login(
                    page,
                    "account.json",
                    {"image_path": "/tmp/qr1.png"},
                    max_checks=2,
                    poll_interval=0,
                )
            )

        self.assertEqual(result["status"], "timeout")
        refresh_qr.assert_awaited()
        save_qr.assert_awaited()

    def test_wait_refreshes_even_when_scanned_logged_true(self):
        page = FakePage({})
        refreshed_info = {"image_path": "/tmp/qr3.png"}

        with patch(
            "uploader.tencent_uploader.main._is_tencent_login_completed",
            new=AsyncMock(return_value=False),
        ), patch(
            "uploader.tencent_uploader.main._is_tencent_qrcode_scanned",
            new=AsyncMock(return_value=True),
        ), patch(
            "uploader.tencent_uploader.main._is_tencent_qrcode_expired",
            new=AsyncMock(return_value=True),
        ), patch(
            "uploader.tencent_uploader.main._refresh_tencent_qrcode",
            new=AsyncMock(),
        ), patch(
            "uploader.tencent_uploader.main._save_tencent_qrcode",
            new=AsyncMock(return_value=refreshed_info),
        ) as save_qr, patch(
            "uploader.tencent_uploader.main.asyncio.sleep",
            new=AsyncMock(),
        ):
            result = asyncio.run(
                tencent_main._wait_for_tencent_login(
                    page,
                    "account.json",
                    {"image_path": "/tmp/qr1.png"},
                    max_checks=2,
                    poll_interval=0,
                )
            )

        self.assertEqual(result["status"], "timeout")
        save_qr.assert_awaited()


if __name__ == "__main__":
    unittest.main()
