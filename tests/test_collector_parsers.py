# -*- coding: utf-8 -*-
# Language: 中文
"""平台响应解析测试：抖音归一化管道 + 小红书宽容解析 + 日报渲染。"""
import json
import os
import tempfile
import unittest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "collector"


class DouyinIngestPipelineTests(unittest.TestCase):
    def test_fixture_to_ingest(self):
        """normalize_aweme(fixture) → ingest_works 全链路,与采集器同一数据流。"""
        from collector.base import CollectorStore
        from collector.models import connect
        from collector.normalize import normalize_metrics
        from uploader.douyin_uploader.health import normalize_aweme

        payload = json.loads((FIXTURES / "douyin_work_list.json").read_text(encoding="utf-8"))
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        try:
            store = CollectorStore()
            try:
                account_id = store.upsert_account("douyin", "diyi")
                works = [{
                    "external_id": (w := normalize_aweme(item))["aweme_id"],
                    "title": w["title"],
                    "work_url": f"https://www.douyin.com/video/{w['aweme_id']}",
                    "publish_date": w["time"],
                    "native": {"play": w["play"], "like": w["like"], "comment": w["comment"],
                               "share": w["share"], "collect": w["collect"]},
                } for item in payload["aweme_list"]]
                seen, new = store.ingest_works("douyin", account_id, works)
                self.assertEqual((seen, new), (2, 2))

                conn = connect(store.db_path, read_only=True)
                row = conn.execute(
                    "SELECT cs.view, cs.like FROM content_snapshots cs "
                    "JOIN contents c ON c.id=cs.content_id WHERE c.external_id='7682139971381251355'"
                ).fetchone()
                conn.close()
                self.assertEqual(row["view"], 22000)
                self.assertEqual(row["like"], 340)
            finally:
                store.close()
        finally:
            os.environ.pop("SOCIAL_DATA_DIR", None)
            self._tmp.cleanup()

    def test_douyin_metric_mapping_uses_play_as_view(self):
        from collector.normalize import PLATFORM_METRIC_FIELDS

        self.assertEqual(PLATFORM_METRIC_FIELDS["douyin"]["view"], "play")


class XhsParserTests(unittest.TestCase):
    def test_parse_note_payloads_from_capture(self):
        from collector.xiaohongshu import parse_note_payloads
        from collector.normalize import normalize_metrics

        payload = json.loads((FIXTURES / "xhs_notes_capture.json").read_text(encoding="utf-8"))
        works = parse_note_payloads([payload])
        self.assertEqual(len(works), 2)
        first = next(w for w in works if w["external_id"] == "66f1a2b3000000001e00c1d2")
        self.assertEqual(first["title"], "每日新中国 0906 期")
        # parse_note_payloads 的输出已是统一键口径,直接断言
        self.assertEqual(first["native"]["view"], 8800)
        self.assertEqual(first["native"]["like"], 120)
        self.assertEqual(first["native"]["collect"], 88)

    def test_parser_ignores_non_note_dicts(self):
        from collector.xiaohongshu import parse_note_payloads

        works = parse_note_payloads([{"data": {"user": {"id": "u1", "name": "某人", "like": 3}}}])
        self.assertEqual(works, [])  # 有 id/like 但无标题,不算笔记

    def test_dedup_by_note_id_across_payloads(self):
        from collector.xiaohongshu import parse_note_payloads

        note = {"note_id": "abc", "display_title": "T", "read_num": 5}
        works = parse_note_payloads([{"data": {"notes": [note]}}, {"data": {"notes": [dict(note, read_num=None, like_num=9)]}}])
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0]["native"]["like"], 9)  # 多来源补齐缺失指标


class DailyReportTests(unittest.TestCase):
    def test_report_renders_platforms_and_failures(self):
        from collector.base import CollectorStore
        from collector.report import generate_daily_report

        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        try:
            store = CollectorStore()
            try:
                account_id = store.upsert_account("bilibili", "diyi")
                store.ingest_works("bilibili", account_id, [
                    {"external_id": "BV1", "title": "每日新中国", "publish_date": "2026-09-06",
                     "native": {"view": 1234, "like": 56}},
                ])
                run_id = store.start_run("douyin", "diyi", "full")
                store.finish_run(run_id, "failed", error="cookie 已失效")
            finally:
                store.close()

            path = generate_daily_report(store, day="2099-01-01")  # 用任意日期跑渲染
            content = path.read_text(encoding="utf-8")
            self.assertIn("各平台汇总", content)
            self.assertIn("bilibili", content)
            self.assertIn("1,234", content)
        finally:
            os.environ.pop("SOCIAL_DATA_DIR", None)
            self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
