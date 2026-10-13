# Language: 中文
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from uploader.douyin_uploader import main as douyin_main
from uploader.douyin_uploader.main import DouYinVideo


class DouyinDeclarationTests(unittest.TestCase):
    def test_upload_only_sets_explicit_declaration(self):
        video = DouYinVideo(
            "标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json",
            declaration="已确认声明原文",
        )
        self.assertEqual(video.declaration, "已确认声明原文")

    def test_missing_declaration_does_not_fall_back_to_personal_opinion(self):
        video = DouYinVideo("标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json")
        self.assertIsNone(video.declaration)

    def test_legacy_positional_runtime_flags_keep_their_meaning(self):
        # 上游 2026-10 演进位置序（thumbnail_landscape/productLink/productTitle/
        # thumbnail_portrait/desc/collection_name 前移）；本测试按当前签名锁位置语义
        video = DouYinVideo(
            "标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json",
            None, "", "", None, "", None,
            "scheduled", False, False, None,
        )
        self.assertEqual(video.publish_strategy, "scheduled")
        self.assertFalse(video.debug)
        self.assertFalse(video.headless)
        self.assertIsNone(video.declaration)

    def test_apply_declaration_skips_when_unspecified(self):
        video = DouYinVideo("标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json")
        video.set_self_declaration = AsyncMock()
        asyncio.run(video.apply_self_declaration(object()))
        video.set_self_declaration.assert_not_awaited()

    def test_apply_declaration_uses_exact_explicit_text(self):
        page = object()
        video = DouYinVideo(
            "标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json",
            declaration="已确认声明原文",
        )
        video.set_self_declaration = AsyncMock(return_value=True)
        asyncio.run(video.apply_self_declaration(page))
        video.set_self_declaration.assert_awaited_once_with(page, "已确认声明原文")

    def test_explicit_declaration_failure_blocks_publish(self):
        video = DouYinVideo(
            "标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json",
            declaration="已确认声明原文",
        )
        video.set_self_declaration = AsyncMock(return_value=False)
        with self.assertRaisesRegex(RuntimeError, "自主声明"):
            asyncio.run(video.apply_self_declaration(object()))

    def test_declaration_failure_closes_browser_resources(self):
        video = DouYinVideo(
            "标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json",
            declaration="已确认声明原文",
        )
        video.validate_upload_args = AsyncMock()
        video.fill_title_and_description = AsyncMock()
        video.set_thumbnail = AsyncMock()
        video.apply_self_declaration = AsyncMock(side_effect=RuntimeError("抖音自主声明设置失败"))

        locator = MagicMock()
        locator.set_input_files = AsyncMock()
        locator.count = AsyncMock(return_value=1)
        # 上游 upload 的 .first 链（wait_for attached / set_input_files / count）一次性配齐
        locator.first = MagicMock(
            count=AsyncMock(return_value=1),
            wait_for=AsyncMock(),
            set_input_files=AsyncMock(),
        )
        page = MagicMock()
        page.goto = AsyncMock()
        page.wait_for_url = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()  # 上游 upload 新增：进页后身份验证等待
        page.locator.return_value = locator

        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock(side_effect=OSError("close failed"))
        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=context)
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)

        with (
            patch.object(douyin_main, "set_init_script", AsyncMock(return_value=context)),
            patch.object(douyin_main.asyncio, "sleep", AsyncMock()),
            self.assertRaisesRegex(RuntimeError, "自主声明"),
        ):
            asyncio.run(video.upload(playwright))

        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
