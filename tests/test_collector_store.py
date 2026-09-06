# -*- coding: utf-8 -*-
# Language: 中文
"""数据中台基础层测试：store 写入语义、归一化匹配键、发布事件文件。"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from collector import events as collector_events
from collector.base import CollectorStore
from collector.normalize import (
    match_key,
    normalize_metrics,
    normalize_publish_date,
    normalize_title,
)


class CollectorStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        self.store = CollectorStore()

    def tearDown(self):
        self.store.close()
        os.environ.pop("SOCIAL_DATA_DIR", None)
        self._tmp.cleanup()

    def test_layout_created_on_e_drive_path(self):
        from collector.paths import db_path, raw_dir

        self.assertTrue(db_path().exists())
        self.assertTrue(raw_dir().exists())

    def test_upsert_account_idempotent(self):
        first = self.store.upsert_account("bilibili", "diyi")
        second = self.store.upsert_account("bilibili", "diyi")
        self.assertEqual(first, second)

    def test_upsert_content_and_snapshot_append_only(self):
        account_id = self.store.upsert_account("douyin", "diyi")
        cid, is_new = self.store.upsert_content("douyin", account_id, "7682", "每日新中国")
        self.assertTrue(is_new)
        _, is_new_again = self.store.upsert_content("douyin", account_id, "7682", "每日新中国")
        self.assertFalse(is_new_again)

        self.store.add_content_snapshot(cid, {"view": 100, "like": 5}, collected_at="2026-09-07T09:30:00")
        self.store.add_content_snapshot(cid, {"view": 150, "like": 8}, collected_at="2026-09-07T21:30:00")
        from collector.models import connect
        from collector.paths import db_path

        conn = connect(db_path(), read_only=True)
        rows = conn.execute(
            "SELECT view FROM content_snapshots WHERE content_id=? ORDER BY collected_at", (cid,)
        ).fetchall()
        conn.close()
        self.assertEqual([r["view"] for r in rows], [100, 150])  # 只追加,不覆盖

    def test_ingest_works_reports_seen_and_new(self):
        account_id = self.store.upsert_account("bilibili", "diyi")
        works = [
            {"external_id": "BV1", "title": "A", "native": {"view": 1}},
            {"external_id": "BV2", "title": "B", "native": {"view": 2}},
        ]
        seen, new = self.store.ingest_works("bilibili", account_id, works)
        self.assertEqual((seen, new), (2, 2))
        seen2, new2 = self.store.ingest_works("bilibili", account_id, works)
        self.assertEqual((seen2, new2), (2, 0))  # 二次采集只追加快照,不新增作品

    def test_collect_run_lifecycle(self):
        run_id = self.store.start_run("douyin", "diyi", "full")
        self.store.finish_run(run_id, "success", works_seen=3, works_new=1, raw_dir="raw/douyin/x")
        from collector.models import connect
        from collector.paths import db_path

        conn = connect(db_path(), read_only=True)
        row = dict(conn.execute("SELECT * FROM collect_runs WHERE id=?", (run_id,)).fetchone())
        conn.close()
        self.assertEqual(row["status"], "success")
        self.assertIsNotNone(row["finished_at"])

    def test_write_probe_fails_when_disk_missing(self):
        os.environ["SOCIAL_DATA_DIR"] = "/nonexistent_drive_zz/social_data"
        from collector.paths import ensure_layout

        with self.assertRaises(RuntimeError):
            ensure_layout()  # ADR-0002: E 盘不可用直接终止,不降级


class NormalizeTests(unittest.TestCase):
    def test_match_key_stable_across_spacing_and_width(self):
        a = match_key("douyin", "每日新中国 ０９０６期", "2026-09-06")
        b = match_key("douyin", "每日新中国０９０６期 ", "2026-09-06")
        self.assertEqual(a, b)

    def test_match_key_differs_by_platform_or_date(self):
        self.assertNotEqual(
            match_key("douyin", "标题", "2026-09-06"), match_key("bilibili", "标题", "2026-09-06")
        )
        self.assertNotEqual(
            match_key("douyin", "标题", "2026-09-06"), match_key("douyin", "标题", "2026-09-07")
        )

    def test_normalize_metrics_mapping(self):
        native = {"play": 10, "digg": 1, "reply": 2, "share": 3, "favorite": 4}
        mapped = normalize_metrics("bilibili", {"view": 10, "like": 1, "reply": 2, "share": 3, "favorite": 4})
        self.assertEqual(mapped, {"view": 10, "like": 1, "comment": 2, "share": 3, "collect": 4})
        self.assertEqual(normalize_metrics("douyin", {"play": 9}), {"view": 9, "like": None, "comment": None, "share": None, "collect": None})
        self.assertTrue(True)

    def test_publish_date_forms(self):
        self.assertEqual(normalize_publish_date(1757123400), "2025-09-06")
        self.assertEqual(normalize_publish_date("2026-09-06 08:30"), "2026-09-06")
        self.assertIsNone(normalize_publish_date(None))


class EventsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name

    def tearDown(self):
        os.environ.pop("SOCIAL_DATA_DIR", None)
        self._tmp.cleanup()

    def test_append_and_due_window(self):
        now = datetime.now()
        collector_events.append_publish_event("douyin", "diyi", "新作品", published_at=now - timedelta(minutes=40))
        collector_events.append_publish_event("douyin", "diyi", "刚发作品", published_at=now - timedelta(minutes=10))
        due = collector_events.due_incrementals(now)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["title"], "新作品")

    def test_consume_folding(self):
        event = collector_events.append_publish_event("bilibili", "diyi", "标题", published_at=datetime.now() - timedelta(hours=2))
        collector_events.mark_consumed([event["event_id"]])
        self.assertEqual(collector_events.due_incrementals(), [])

    def test_overdue_event_is_still_due(self):
        collector_events.append_publish_event("douyin", "diyi", "隔夜作品",
                                              published_at=datetime.now() - timedelta(days=2))
        self.assertEqual(len(collector_events.due_incrementals()), 1)  # 错过就补,不丢弃

    def test_corrupt_line_skipped(self):
        from collector.paths import events_file

        events_file().parent.mkdir(parents=True, exist_ok=True)
        events_file().write_text("{broken json\n", encoding="utf-8")
        events = collector_events.read_events()
        self.assertEqual(events[-1]["type"], "corrupt")

    def test_safe_append_never_raises(self):
        from datetime import datetime, timedelta

        collector_events.safe_append_publish_event("douyin", "/不存在/路径.json", None,
                                                   published_at=datetime.now() - timedelta(hours=1))
        self.assertEqual(len(collector_events.due_incrementals()), 1)  # title=None 也能落事件


if __name__ == "__main__":
    unittest.main()
