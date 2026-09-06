# -*- coding: utf-8 -*-
"""SQLite 建表与连接（docs/data-collector-plan.md 第 5 节六表）。

快照表只追加不覆盖：指标历史即快照序列，分析取"每天最后一行"。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL,
    account_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE(platform, account_name)
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     INTEGER NOT NULL REFERENCES accounts(id),
    snapshot_date  TEXT NOT NULL,
    follower_count INTEGER,
    total_view     INTEGER,
    extra          TEXT,
    collected_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    platform         TEXT NOT NULL,
    account_id       INTEGER NOT NULL REFERENCES accounts(id),
    external_id      TEXT NOT NULL,
    work_url         TEXT,
    title            TEXT,
    normalized_title TEXT,
    publish_date     TEXT,
    match_key        TEXT,
    sau_task_id      TEXT,
    source_pipeline  TEXT,
    first_seen_at    TEXT NOT NULL,
    UNIQUE(platform, external_id)
);

CREATE TABLE IF NOT EXISTS content_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id      INTEGER NOT NULL REFERENCES contents(id),
    collected_at    TEXT NOT NULL,
    view            INTEGER,
    like            INTEGER,
    comment         INTEGER,
    share           INTEGER,
    collect         INTEGER,
    is_incremental  INTEGER NOT NULL DEFAULT 0
);

-- 二期启用：完播率/流量来源/粉丝画像等详情级数据
CREATE TABLE IF NOT EXISTS content_details (
    content_id   INTEGER NOT NULL REFERENCES contents(id),
    collected_at TEXT NOT NULL,
    detail       TEXT NOT NULL,
    PRIMARY KEY (content_id, collected_at)
);

CREATE TABLE IF NOT EXISTS collect_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT NOT NULL,
    account     TEXT,
    trigger     TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    works_seen  INTEGER,
    works_new   INTEGER,
    raw_dir     TEXT,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_content_snapshots_content ON content_snapshots(content_id, collected_at);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_account ON account_snapshots(account_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_contents_platform ON contents(platform, publish_date);
"""


def connect(db_path: Path, read_only: bool = False) -> sqlite3.Connection:
    """打开连接。只读模式用 URI 方式，杜绝误写（查询侧随便开，写侧仅 CollectorStore）。"""
    if read_only:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    else:
        conn = sqlite3.connect(str(db_path), timeout=30)
        # 9p/drvfs(Windows 盘挂载)不支持 WAL 的共享内存 mmap,会报 disk I/O error,
        # 因此用传统 rollback journal(DELETE);配合集群进程串行写(ADR-0002)足够。
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
