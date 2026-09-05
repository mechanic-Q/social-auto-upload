# Language: 中文
import asyncio
import unittest
from argparse import Namespace
from unittest.mock import AsyncMock, patch

import sau_cli
from uploader.bilibili_uploader.health import normalize_archive, summarize_works
from uploader.douyin_uploader.health import normalize_aweme, summarize_works as summarize_douyin


class HealthParserTests(unittest.TestCase):
    def test_douyin_health_parser(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["douyin", "health", "--account", "diyi", "--limit", "10"])
        self.assertEqual((args.platform, args.action), ("douyin", "health"))
        self.assertEqual(args.limit, 10)

    def test_bilibili_health_parser(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["bilibili", "health", "--account", "diyi"])
        self.assertEqual(args.action, "health")
        self.assertEqual(args.limit, 20)

    def test_dispatch_douyin_health_prints_json(self):
        args = Namespace(platform="douyin", action="health", account="diyi", limit=5, headless=True)
        report = {"platform": "douyin", "works": [], "summary": {}}
        with patch("sau_cli.health_douyin_account", new=AsyncMock(return_value=report)):
            code = asyncio.run(sau_cli.dispatch(args))
        self.assertEqual(code, 0)

    def test_dispatch_bilibili_health_prints_json(self):
        args = Namespace(platform="bilibili", action="health", account="diyi", limit=5)
        report = {"platform": "bilibili", "works": [], "summary": {}}
        with patch("sau_cli.health_bilibili_account", new=AsyncMock(return_value=report)):
            code = asyncio.run(sau_cli.dispatch(args))
        self.assertEqual(code, 0)


class BilibiliHealthTests(unittest.TestCase):
    def test_summarize_flags_pending_and_rejected(self):
        works = [
            {"title": "正常", "state": 0, "view": 100, "reject_reason": ""},
            {"title": "待审", "state": -30, "view": 0, "reject_reason": ""},
            {"title": "被拒", "state": -50, "view": None, "reject_reason": "内容不符合规范"},
        ]
        summary = summarize_works(works)
        self.assertEqual(summary["pending_audit"], ["待审"])
        self.assertEqual(summary["rejected"][0]["title"], "被拒")
        self.assertEqual(summary["rejected"][0]["reason"], "内容不符合规范")
        self.assertEqual(summary["median_view"], 50)

    def test_normalize_archive_extracts_fields(self):
        entry = {
            "Archive": {"bvid": "BV1", "title": "t", "state": 0, "state_desc": "开放浏览",
                        "ctime": 1, "ptime": 2, "reject_reason": ""},
            "stat": {"view": 10, "like": 1, "coin": 0, "favorite": 0, "share": 0, "reply": 0, "danmaku": 0},
        }
        work = normalize_archive(entry)
        self.assertEqual((work["bvid"], work["view"], work["state"]), ("BV1", 10, 0))


class DouyinHealthTests(unittest.TestCase):
    def test_summarize_flags_abnormal_status(self):
        works = [
            {"title": "正常", "flags": {}, "play": 5},
            {"title": "仅自己可见", "flags": {"self_see": True}, "play": 0},
        ]
        summary = summarize_douyin(works)
        self.assertEqual(summary["abnormal_status"][0]["title"], "仅自己可见")
        self.assertEqual(summary["median_play"], 2.5)

    def test_normalize_aweme_keeps_only_true_flags(self):
        item = {
            "aweme_id": "1", "desc": "标题", "create_time": 0,
            "status": {"in_reviewing": False, "self_see": True, "is_prohibited": False},
            "statistics": {"play_count": 7, "digg_count": 1},
        }
        work = normalize_aweme(item)
        self.assertEqual(work["flags"], {"self_see": True})
        self.assertEqual(work["play"], 7)


if __name__ == "__main__":
    unittest.main()
