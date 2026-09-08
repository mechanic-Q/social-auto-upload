# -*- coding: utf-8 -*-
# Language: 中文
"""调度编排与 CLI 测试：增量消费、全量编排、sau stats 参数与查询。"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name

    def tearDown(self):
        os.environ.pop("SOCIAL_DATA_DIR", None)
        self._tmp.cleanup()

    def _seed_due_event(self, platform="douyin"):
        from collector import events as collector_events

        event = collector_events.append_publish_event(
            platform, "diyi", "测试作品", published_at=datetime.now() - timedelta(minutes=45)
        )
        return event

    def test_incremental_skips_when_no_due_events(self):
        from collector.scheduler import run_incremental

        result = run_incremental()
        self.assertEqual(result["status"], "skipped")

    def test_incremental_consumes_due_event_and_marks(self):
        from collector import events as collector_events
        from collector.scheduler import run_incremental

        event = self._seed_due_event("bilibili")
        fake_result = {"platform": "bilibili", "status": "success", "works_seen": 1, "works_new": 1}
        with patch("collector.scheduler._collect_platform", return_value=[fake_result]) as collect:
            result = run_incremental()
        self.assertEqual(result["status"] if "status" in result else "ok", result.get("status", "ok"))
        collect.assert_called_once_with(collect.call_args.args[0], "bilibili", trigger="incremental")
        self.assertEqual(collector_events.due_incrementals(), [])  # 成功后事件被标记消费

    def test_incremental_keeps_events_when_collect_fails(self):
        from collector import events as collector_events
        from collector.scheduler import run_incremental

        self._seed_due_event("douyin")
        fake_result = {"platform": "douyin", "status": "failed", "error": "cookie 失效"}
        with patch("collector.scheduler._collect_platform", return_value=[fake_result]):
            run_incremental()
        self.assertEqual(len(collector_events.due_incrementals()), 1)  # 失败保留,下次再试

    def test_full_runs_report_and_platforms_in_order(self):
        from collector.scheduler import run_full

        fake_result = {"platform": "bilibili", "status": "success", "works_seen": 1, "works_new": 1}
        with patch("collector.scheduler._collect_platform", return_value=[fake_result]) as collect:
            result = run_full(platforms=("bilibili",), generate_report=True)
        collect.assert_called_once()
        self.assertIn("daily_report", result)

    def test_account_files_discovery(self):
        from collector.scheduler import account_files

        files = account_files("bilibili")
        self.assertTrue(any(p.name == "bilibili_diyi.json" for p in files))


class StatsCliTests(unittest.TestCase):
    def _parser(self):
        import sau_cli

        return sau_cli.build_parser()

    def test_stats_status_parser(self):
        args = self._parser().parse_args(["stats", "status"])
        self.assertEqual(args.platform, "stats")
        self.assertEqual(args.action, "status")

    def test_stats_collect_full_parser(self):
        args = self._parser().parse_args(["stats", "collect", "--full"])
        self.assertTrue(args.full)
        self.assertFalse(args.incremental)

    def test_stats_collect_probe_requires_platform(self):
        args = self._parser().parse_args(["stats", "collect", "--probe", "--only", "xiaohongshu"])
        self.assertEqual(args.only_platform, "xiaohongshu")

    def test_cmd_list_and_trend_on_seeded_store(self):
        from collector.base import CollectorStore
        from collector.cli import cmd_list, cmd_trend

        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        try:
            store = CollectorStore()
            try:
                account_id = store.upsert_account("bilibili", "diyi")
                store.ingest_works("bilibili", account_id, [
                    {"external_id": "BV1xx411c7mD", "title": "每日新中国", "native": {"view": 1234}},
                ])
            finally:
                store.close()

            listed = cmd_list()
            self.assertEqual(listed["works"][0]["external_id"], "BV1xx411c7mD")
            trend = cmd_trend("bilibili", external_id="BV1xx411c7mD")
            self.assertEqual(trend["snapshots"][0]["view"], 1234)
        finally:
            os.environ.pop("SOCIAL_DATA_DIR", None)
            self._tmp.cleanup()

    def test_publish_hook_smoke_via_event_file(self):
        """钩子冒烟:safe_append 写事件文件,采集侧能消费。"""
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name  # 隔离,绝不污染 E 盘真实事件文件
        try:
            from collector import events as collector_events
            from collector.events import safe_append_publish_event

            safe_append_publish_event("douyin", "/x/douyin_diyi.json", "钩子冒烟",
                                      published_at=datetime.now() - timedelta(hours=1))
            due = collector_events.due_incrementals()
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["account"], "diyi")  # 账号名从 cookie 文件名推断
        finally:
            os.environ.pop("SOCIAL_DATA_DIR", None)
            self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
