# Language: 中文
import asyncio
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import sau_cli


def _video_args(**overrides):
    base = {
        "platform": "toutiao",
        "action": "upload-video",
        "account": "diyi",
        "file": Path("demo.mp4"),
        "title": "标题",
        "desc": "简介",
        "tags": "a,b",
        "extra_tag_pool": [],
        "schedule": None,
        "thumbnail": None,
        "activity": None,
        "declaration": None,
        "draft": False,
        "debug": False,
        "headless": True,
    }
    base.update(overrides)
    return Namespace(**base)


class ToutiaoCliParserTests(unittest.TestCase):
    def test_build_parser_accepts_toutiao_login_and_check(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["toutiao", "login", "--account", "diyi"])
        self.assertEqual((args.platform, args.action), ("toutiao", "login"))
        args = parser.parse_args(["toutiao", "check", "--account", "diyi"])
        self.assertEqual(args.action, "check")

    def test_upload_video_accepts_new_flags(self):
        # argparse 的 existing_file_path 要求文件真实存在，测试需自备
        fake_video = "/tmp/fake.mp4"
        Path(fake_video).write_bytes(b"")
        self.addCleanup(Path(fake_video).unlink, missing_ok=True)
        parser = sau_cli.build_parser()
        args = parser.parse_args(
            [
                "toutiao", "upload-video",
                "--account", "diyi",
                "--file", "/tmp/fake.mp4",
                "--title", "标题",
                "--tags", "a,b",
                "--extra-tag-pool", "news",
                "--schedule", "2026-09-10 10:00",
                "--activity", "某活动",
                "--declaration", "原创",
            ]
        )
        self.assertEqual(args.activity, "某活动")
        self.assertEqual(args.declaration, "原创")
        self.assertEqual(args.extra_tag_pool, ["news"])
        self.assertIsNotNone(args.schedule)

    def test_list_activities_subcommand_exists(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["toutiao", "list-activities", "--account", "diyi"])
        self.assertEqual(args.action, "list-activities")


class ToutiaoCliDispatchTests(unittest.TestCase):
    def test_dispatch_check_prints_valid(self):
        args = Namespace(platform="toutiao", action="check", account="diyi")
        with patch("sau_cli.check_toutiao_account", new=AsyncMock(return_value=True)):
            code = asyncio.run(sau_cli.dispatch(args))
        self.assertEqual(code, 0)

    def test_dispatch_check_invalid_returns_one(self):
        args = Namespace(platform="toutiao", action="check", account="diyi")
        with patch("sau_cli.check_toutiao_account", new=AsyncMock(return_value=False)):
            code = asyncio.run(sau_cli.dispatch(args))
        self.assertEqual(code, 1)

    def test_dispatch_upload_video_passes_activity_and_declaration(self):
        captured = {}

        async def fake_upload(request):
            captured["request"] = request
            return Path("cookies/toutiao_diyi.json")

        args = _video_args(activity="某活动", declaration="原创", tags="a,b", extra_tag_pool=["news"])
        with (
            patch("sau_cli.resolve_extra_tags", return_value=["新闻"]),
            patch("sau_cli.upload_toutiao_video", new=fake_upload),
        ):
            code = asyncio.run(sau_cli.dispatch(args))
        self.assertEqual(code, 0)
        request = captured["request"]
        self.assertEqual(request.activity, "某活动")
        self.assertEqual(request.declaration, "原创")
        self.assertEqual(request.tags, ["a", "b", "新闻"])


if __name__ == "__main__":
    unittest.main()
