# -*- coding: utf-8 -*-
# Language: 中文
"""二期/三期平台测试：三平台宽容解析、详情级目标筛选、crosswalk 导出、profile 注册。"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "collector"


class GenericProfileTests(unittest.TestCase):
    def test_profiles_cover_three_platforms(self):
        from collector.generic import PROFILES

        for platform, url in (
            ("kuaishou", "cp.kuaishou.com"),
            ("tencent", "channels.weixin.qq.com"),
            ("toutiao", "mp.toutiao.com"),
        ):
            self.assertIn(platform, PROFILES)
            self.assertIn(url, PROFILES[platform].manage_url)

    def test_parse_kuaishou_capture(self):
        from collector.fuzzy import parse_work_payloads

        payload = json.loads((FIXTURES / "kuaishou_capture.json").read_text(encoding="utf-8"))
        works = parse_work_payloads([payload])
        self.assertEqual(len(works), 2)
        first = next(w for w in works if w["external_id"] == "3xtvnqrp6er9dhu")
        self.assertIn("机器人来抢活儿", first["title"])
        self.assertEqual(first["native"]["view"], 1200)
        self.assertEqual(first["native"]["like"], 35)

    def test_parse_tencent_capture(self):
        from collector.fuzzy import parse_work_payloads

        payload = json.loads((FIXTURES / "tencent_capture.json").read_text(encoding="utf-8"))
        works = parse_work_payloads([payload])
        self.assertEqual(len(works), 2)
        first = next(w for w in works if w["external_id"] == "export/U05600abc")
        self.assertEqual(first["native"]["view"], 3200)
        self.assertEqual(first["native"]["collect"], 20)

    def test_parse_toutiao_capture(self):
        from collector.fuzzy import parse_work_payloads

        payload = json.loads((FIXTURES / "toutiao_capture.json").read_text(encoding="utf-8"))
        works = parse_work_payloads([payload])
        self.assertEqual(len(works), 2)
        first = next(w for w in works if w["external_id"] == "745600001")
        self.assertEqual(first["native"]["view"], 7800)
        self.assertEqual(first["native"]["comment"], 30)

    def test_ingest_generic_works_via_store(self):
        from collector.base import CollectorStore
        from collector.fuzzy import parse_work_payloads

        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        try:
            store = CollectorStore()
            try:
                payload = json.loads((FIXTURES / "kuaishou_capture.json").read_text(encoding="utf-8"))
                works = parse_work_payloads([payload])
                account_id = store.upsert_account("kuaishou", "diyi")
                seen, new = store.ingest_works(
                    "kuaishou", account_id,
                    [{**w, "work_url": f"https://www.kuaishou.com/short-video/{w['external_id']}"} for w in works],
                )
                self.assertEqual((seen, new), (2, 2))
            finally:
                store.close()
        finally:
            os.environ.pop("SOCIAL_DATA_DIR", None)
            self._tmp.cleanup()


class DetailsSelectionTests(unittest.TestCase):
    def test_select_targets_recent_plus_topn(self):
        from collector.base import CollectorStore
        from collector.details import select_targets
        from collector.models import connect

        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        try:
            store = CollectorStore()
            try:
                account_id = store.upsert_account("bilibili", "diyi")
                recent_date = datetime.now().strftime("%Y-%m-%d")
                store.ingest_works("bilibili", account_id, [
                    {"external_id": "BV_recent", "title": "7天内", "publish_date": recent_date,
                     "native": {"view": 10}},
                    {"external_id": "BV_old_top", "title": "老爆款", "publish_date": "2026-01-01",
                     "native": {"view": 99999}},
                    {"external_id": "BV_old_low", "title": "老普通", "publish_date": "2026-01-01",
                     "native": {"view": 5}},
                ])
                id_map = {r["external_id"]: r["id"] for r in
                          connect(store.db_path, read_only=True).execute(
                              "SELECT external_id, id FROM contents")}
                targets = select_targets(store, days=7, top_n=1)
            finally:
                store.close()

            self.assertIn(id_map["BV_recent"], targets["bilibili"])   # 7 天内 → 入选
            self.assertIn(id_map["BV_old_top"], targets["bilibili"])  # Top N → 入选
            self.assertNotIn(id_map["BV_old_low"], targets["bilibili"])  # 老且低 → 排除
        finally:
            os.environ.pop("SOCIAL_DATA_DIR", None)
            self._tmp.cleanup()

    def test_collect_details_probe_mode(self):
        from collector.base import CollectorStore
        from collector.details import collect_details

        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        try:
            store = CollectorStore()
            try:
                result = collect_details(store)
                self.assertTrue(result["probe"])
                self.assertIn("待校准", result["note"])
            finally:
                store.close()
        finally:
            os.environ.pop("SOCIAL_DATA_DIR", None)
            self._tmp.cleanup()


class CrosswalkTests(unittest.TestCase):
    def test_crosswalk_export(self):
        from collector.base import CollectorStore
        from collector.cli import cmd_crosswalk

        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        try:
            store = CollectorStore()
            try:
                account_id = store.upsert_account("douyin", "diyi")
                store.ingest_works("douyin", account_id, [
                    {"external_id": "7682", "title": "每日新中国", "publish_date": "2026-09-06",
                     "native": {"play": 100}},
                ])
            finally:
                store.close()

            out_file = Path(self._tmp.name) / "crosswalk.json"
            result = cmd_crosswalk(str(out_file))
            self.assertEqual(result["exported"], 1)
            rows = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["platform"], "douyin")
            self.assertTrue(rows[0]["match_key"].startswith("douyin:"))
        finally:
            os.environ.pop("SOCIAL_DATA_DIR", None)
            self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
