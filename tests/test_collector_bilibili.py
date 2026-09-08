# -*- coding: utf-8 -*-
# Language: 中文
"""B 站采集器端到端（mock HTTP）：fixture 响应 → 快照入库。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

FIXTURES = Path(__file__).parent / "fixtures" / "collector"


class CollectBilibiliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SOCIAL_DATA_DIR"] = self._tmp.name
        self.store = None

    def tearDown(self):
        if self.store is not None:
            self.store.close()
        os.environ.pop("SOCIAL_DATA_DIR", None)
        self._tmp.cleanup()

    def test_collect_bilibili_end_to_end(self):
        from collector.base import CollectorStore
        from collector.bilibili import collect_bilibili
        from collector.models import connect
        from collector.paths import db_path

        archives = json.loads((FIXTURES / "bilibili_archives.json").read_text(encoding="utf-8"))
        account_file = self._tmp.name + "/bilibili_diyi.json"
        Path(account_file).write_text(json.dumps({"cookie_info": {"cookies": [
            {"name": "SESSDATA", "value": "x"}, {"name": "DedeUserID", "value": "12345"},
        ]}}), encoding="utf-8")

        self.store = CollectorStore()
        with patch("collector.bilibili._fetch_archives", return_value=archives["data"]), \
             patch("collector.bilibili.fetch_follower_count", return_value=4321):
            result = collect_bilibili(self.store, account_file, trigger="full")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["works_seen"], 2)
        self.assertEqual(result["follower_count"], 4321)

        conn = connect(db_path(), read_only=True)
        try:
            works = conn.execute(
                "SELECT external_id, title, publish_date FROM contents WHERE platform='bilibili' ORDER BY external_id"
            ).fetchall()
            snaps = conn.execute(
                "SELECT cs.view, cs.like, cs.comment, cs.collect FROM content_snapshots cs "
                "JOIN contents c ON c.id=cs.content_id WHERE c.external_id='BV1xx411c7mD'"
            ).fetchall()
            accounts = conn.execute("SELECT follower_count FROM account_snapshots").fetchall()
        finally:
            conn.close()
        self.assertEqual([w["external_id"] for w in works], ["BV1xx411c7mD", "BV1xx411c8mD"])
        self.assertEqual(works[0]["publish_date"], "2025-09-06")  # ptime 时间戳已归一
        self.assertEqual(snaps[0]["view"], 1234)
        self.assertEqual(snaps[0]["comment"], 11)  # reply → comment 统一口径
        self.assertEqual(snaps[0]["collect"], 89)  # favorite → collect
        self.assertEqual(accounts[0]["follower_count"], 4321)

    def test_second_collect_does_not_duplicate_works(self):
        from collector.base import CollectorStore
        from collector.bilibili import collect_bilibili

        archives = json.loads((FIXTURES / "bilibili_archives.json").read_text(encoding="utf-8"))
        account_file = self._tmp.name + "/bilibili_diyi.json"
        Path(account_file).write_text(json.dumps({"cookie_info": {"cookies": []}}), encoding="utf-8")

        self.store = CollectorStore()
        with patch("collector.bilibili._fetch_archives", return_value=archives["data"]), \
             patch("collector.bilibili.fetch_follower_count", return_value=None):
            first = collect_bilibili(self.store, account_file, trigger="full")
            second = collect_bilibili(self.store, account_file, trigger="incremental")
        self.assertEqual(first["works_new"], 2)
        self.assertEqual(second["works_new"], 0)
        self.assertEqual(second["works_seen"], 2)

    def test_raw_archives_saved(self):
        from collector.base import CollectorStore
        from collector.bilibili import collect_bilibili
        from collector.paths import raw_dir

        archives = json.loads((FIXTURES / "bilibili_archives.json").read_text(encoding="utf-8"))
        account_file = self._tmp.name + "/bilibili_diyi.json"
        Path(account_file).write_text(json.dumps({"cookie_info": {"cookies": []}}), encoding="utf-8")
        self.store = CollectorStore()
        with patch("collector.bilibili._fetch_archives", return_value=archives["data"]), \
             patch("collector.bilibili.fetch_follower_count", return_value=None):
            collect_bilibili(self.store, account_file, trigger="full")
        saved = list((raw_dir() / "bilibili").rglob("*.json"))
        self.assertTrue(len(saved) >= 2)  # archives + relation_stat


if __name__ == "__main__":
    unittest.main()
