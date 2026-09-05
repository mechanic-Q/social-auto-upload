# Language: 中文
import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from uploader.ks_uploader.main import KUAISHOU_MAX_TAGS, KSVideo
from uploader.toutiao_uploader.main import TOUTIAO_MAX_TAGS, TOUTIAO_TITLE_MAX_LEN, ToutiaoVideo
from utils.extra_tags import UnknownTagPoolError, merge_tags, resolve_extra_tags


def _fake_video_file() -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    handle.close()
    return handle.name


class ExtraTagsTests(unittest.TestCase):
    def test_unknown_pool_raises(self):
        with self.assertRaises(UnknownTagPoolError):
            resolve_extra_tags("kuaishou", ["不存在"])

    def test_empty_pools_resolve_to_empty(self):
        self.assertEqual(resolve_extra_tags("kuaishou", []), [])
        self.assertEqual(resolve_extra_tags("toutiao", None), [])

    def test_merge_tags_dedupes_and_keeps_order(self):
        self.assertEqual(merge_tags(["a", "b"], ["b", "c"]), ["a", "b", "c"])


class KuaishouActivityTagTests(unittest.TestCase):
    def test_video_accepts_activity(self):
        video = KSVideo("标题", "/tmp/demo.mp4", ["a"], 0, "/tmp/cookie.json", activity="光合计划")
        self.assertEqual(video.activity, "光合计划")

    def test_video_without_activity_is_none(self):
        video = KSVideo("标题", "/tmp/demo.mp4", ["a"], 0, "/tmp/cookie.json")
        self.assertIsNone(video.activity)

    def test_tags_over_limit_are_truncated_with_warning(self):
        video_file = _fake_video_file()
        self.addCleanup(os.unlink, video_file)
        tags = [f"tag{i}" for i in range(KUAISHOU_MAX_TAGS + 2)]
        video = KSVideo("标题", video_file, tags, 0, "/tmp/cookie.json")
        video.validate_base_args = AsyncMock()
        asyncio.run(video.validate_upload_args())
        self.assertEqual(len(video.tags), KUAISHOU_MAX_TAGS)

    def test_set_activity_skips_when_unspecified(self):
        video = KSVideo("标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json")
        video._open_activity_panel = AsyncMock()
        asyncio.run(video.set_activity(object()))
        video._open_activity_panel.assert_not_awaited()

    def test_set_activity_aborts_when_panel_missing(self):
        from unittest.mock import MagicMock

        video = KSVideo("标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json", activity="光合计划")
        cards = MagicMock()
        cards.first.wait_for = AsyncMock(side_effect=Exception("timeout"))
        video._activity_cards = MagicMock(return_value=cards)
        page = MagicMock()
        page.evaluate = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "活动推荐区"):
            asyncio.run(video.set_activity(page))


class ToutiaoVideoTests(unittest.TestCase):
    def test_title_over_300_chars_rejected(self):
        video = ToutiaoVideo("字" * (TOUTIAO_TITLE_MAX_LEN + 1), "/tmp/demo.mp4", [], 0, "/tmp/cookie.json")
        video.validate_base_args = AsyncMock()
        with self.assertRaisesRegex(ValueError, "300"):
            asyncio.run(video.validate_upload_args())

    def test_tags_over_limit_truncated(self):
        video_file = _fake_video_file()
        self.addCleanup(os.unlink, video_file)
        tags = [f"tag{i}" for i in range(TOUTIAO_MAX_TAGS + 1)]
        video = ToutiaoVideo("标题", video_file, tags, 0, "/tmp/cookie.json")
        video.validate_base_args = AsyncMock()
        asyncio.run(video.validate_upload_args())
        self.assertEqual(len(video.tags), TOUTIAO_MAX_TAGS)

    def test_declaration_required_means_abort_when_toggle_missing(self):
        video = ToutiaoVideo("标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json", declaration="AI生成")
        page = MagicMock()
        empty = MagicMock()
        empty.count = AsyncMock(return_value=0)
        page.locator.return_value = empty
        with self.assertRaisesRegex(RuntimeError, "作品声明区没有找到选项"):
            asyncio.run(video.apply_declaration(page))

    def test_set_activity_reports_unsupported_when_requested(self):
        video = ToutiaoVideo("标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json", activity="某活动")
        page = MagicMock()
        with self.assertRaisesRegex(RuntimeError, "不提供活动入口"):
            asyncio.run(video.set_activity(page))

    def test_declaration_skipped_when_unspecified(self):
        video = ToutiaoVideo("标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json")
        page = MagicMock()
        asyncio.run(video.apply_declaration(page))

    def test_set_activity_aborts_when_panel_missing(self):
        video = ToutiaoVideo("标题", "/tmp/demo.mp4", [], 0, "/tmp/cookie.json", activity="某活动")
        video._open_activity_panel = AsyncMock(return_value=None)
        with self.assertRaisesRegex(RuntimeError, "活动入口"):
            asyncio.run(video.set_activity(object()))


if __name__ == "__main__":
    unittest.main()
