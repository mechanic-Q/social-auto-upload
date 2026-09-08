# -*- coding: utf-8 -*-
"""CollectorStore：SQLite 的唯一写入口（ADR-0002 单进程写约束）。

所有写操作经进程内锁串行化；查询侧用 :func:`collector.models.connect`
的 read_only 模式随意开。原始接口响应统一经 :meth:`save_raw` 落
``raw/<平台>/<日期>/``，平台改版后可由存档重放重建库。
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from collector.models import init_db
from collector.normalize import match_key, normalize_publish_date, normalize_title
from collector.paths import db_path, ensure_layout, raw_dir

EPOCH = datetime(1970, 1, 1)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CollectorStore:
    def __init__(self, db: Path | None = None):
        self.db_path = db or db_path()
        ensure_layout()
        init_db(self.db_path)
        self._lock = threading.Lock()
        self._conn = None  # 惰性：真正写库时才建连接
        self._raw_seq = 0

    def _connection(self):
        if self._conn is None:
            from collector.models import connect

            self._conn = connect(self.db_path)
        return self._conn

    @contextmanager
    def write(self) -> Iterator:
        """串行写事务：进程内锁保护，任何采集线程/任务共用这一个入口。"""
        with self._lock:
            conn = self._connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---------- raw 存档 ----------

    def save_raw(self, platform: str, payload, tag: str = "") -> str:
        """原始响应存档到 raw/<平台>/<日期>/，返回相对路径。payload 为 dict/list 或原始文本。"""
        now = datetime.now()
        day_dir = raw_dir() / platform / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        self._raw_seq += 1
        name = f"{now.strftime('%H%M%S')}_{self._raw_seq:04d}"
        if tag:
            name += f"_{tag}"
        path = day_dir / f"{name}.json"
        if isinstance(payload, (dict, list)):
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            path.write_text(str(payload), encoding="utf-8")
        return str(path.relative_to(raw_dir()))

    # ---------- 维表与快照 ----------

    def upsert_account(self, platform: str, account_name: str) -> int:
        with self.write() as conn:
            conn.execute(
                "INSERT INTO accounts(platform, account_name, created_at) VALUES(?,?,?) "
                "ON CONFLICT(platform, account_name) DO NOTHING",
                (platform, account_name, _now_iso()),
            )
            row = conn.execute(
                "SELECT id FROM accounts WHERE platform=? AND account_name=?", (platform, account_name)
            ).fetchone()
            return int(row["id"])

    def upsert_content(
        self,
        platform: str,
        account_id: int,
        external_id: str,
        title: str,
        work_url: str = "",
        publish_date=None,
        source_pipeline: str = "collector",
    ) -> tuple[int, bool]:
        """返回 (content_id, is_new)。external_id 平台内唯一（bvid/aweme_id/note_id）。"""
        date_str = normalize_publish_date(publish_date)
        key = match_key(platform, title, date_str)
        with self.write() as conn:
            cursor = conn.execute(
                "INSERT INTO contents(platform, account_id, external_id, work_url, title, "
                "normalized_title, publish_date, match_key, source_pipeline, first_seen_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(platform, external_id) DO NOTHING",
                (platform, account_id, external_id, work_url, title, normalize_title(title),
                 date_str, key, source_pipeline, _now_iso()),
            )
            row = conn.execute(
                "SELECT id FROM contents WHERE platform=? AND external_id=?", (platform, external_id)
            ).fetchone()
            return int(row["id"]), cursor.rowcount > 0

    def add_content_snapshot(self, content_id: int, metrics: dict, collected_at: str | None = None,
                             is_incremental: bool = False) -> None:
        with self.write() as conn:
            conn.execute(
                "INSERT INTO content_snapshots(content_id, collected_at, view, like, comment, share, collect, "
                "is_incremental) VALUES(?,?,?,?,?,?,?,?)",
                (
                    content_id,
                    collected_at or _now_iso(),
                    metrics.get("view"),
                    metrics.get("like"),
                    metrics.get("comment"),
                    metrics.get("share"),
                    metrics.get("collect"),
                    1 if is_incremental else 0,
                ),
            )

    def add_account_snapshot(self, account_id: int, snapshot_date: str, follower_count=None,
                             total_view=None, extra: dict | None = None) -> None:
        with self.write() as conn:
            conn.execute(
                "INSERT INTO account_snapshots(account_id, snapshot_date, follower_count, total_view, extra, "
                "collected_at) VALUES(?,?,?,?,?,?)",
                (account_id, snapshot_date, follower_count, total_view,
                 json.dumps(extra, ensure_ascii=False) if extra else None, _now_iso()),
            )

    def add_content_detail(self, content_id: int, detail: dict, collected_at: str | None = None) -> None:
        """详情级数据（完播率/流量来源/画像），二期启用，主键幂等。"""
        with self.write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO content_details(content_id, collected_at, detail) VALUES(?,?,?)",
                (content_id, collected_at or _now_iso(), json.dumps(detail, ensure_ascii=False)),
            )

    # ---------- 采集运行记账 ----------

    def start_run(self, platform: str, account: str, trigger: str) -> int:
        with self.write() as conn:
            cursor = conn.execute(
                "INSERT INTO collect_runs(platform, account, trigger, started_at, status) VALUES(?,?,?,?, 'running')",
                (platform, account, trigger, _now_iso()),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, works_seen: int = 0, works_new: int = 0,
                   raw_dir: str = "", error: str = "") -> None:
        with self.write() as conn:
            conn.execute(
                "UPDATE collect_runs SET finished_at=?, status=?, works_seen=?, works_new=?, raw_dir=?, error=? "
                "WHERE id=?",
                (_now_iso(), status, works_seen, works_new, raw_dir, error[:2000], run_id),
            )

    # ---------- 作品入库(平台采集器共用的纯数据流,可离线测试) ----------

    def ingest_works(self, platform: str, account_id: int, works: list[dict],
                     trigger: str = "full") -> tuple[int, int]:
        """把归一化后的作品列表写入维表 + 快照表。

        每个 work 需要:external_id / title,可选 work_url / publish_date / native。
        native 的键允许两种形态:平台原生键(如 douyin 的 play)走映射表归一;
        已经是统一键(view/like/...)的直接入库(小红书宽容解析的输出)。
        返回 (seen, new)。
        """
        from collector.normalize import PLATFORM_METRIC_FIELDS, normalize_metrics

        unified = {"view", "like", "comment", "share", "collect"}
        native_form_keys = set(PLATFORM_METRIC_FIELDS[platform].values()) - {None}
        seen = new = 0
        for work in works:
            content_id, is_new = self.upsert_content(
                platform=platform,
                account_id=account_id,
                external_id=work["external_id"],
                title=work.get("title") or "",
                work_url=work.get("work_url") or "",
                publish_date=work.get("publish_date"),
            )
            native = work.get("native") or {}
            if native and set(native) <= unified and set(native) != native_form_keys:
                # 键已经是统一口径(小红书宽容解析的输出)——注意 douyin 原生键
                # 与统一键部分同名,须先确认整个键集不是平台原生形态再直取。
                metrics = {key: native.get(key) for key in unified}
            else:
                metrics = normalize_metrics(platform, native)
            self.add_content_snapshot(content_id, metrics, is_incremental=(trigger == "incremental"))
            seen += 1
            new += int(is_new)
        return seen, new
