# -*- coding: utf-8 -*-
"""数据目录解析：统一落在 Windows E 盘（ADR-0002）。

优先级：环境变量 ``SOCIAL_DATA_DIR`` > ``/mnt/e/social_data``（WSL，E 盘已挂载）
> ``E:/social_data``（Windows 侧直接运行）。E 盘不可用时 :func:`ensure_layout`
抛错终止——不降级写本地盘，避免数据分叉。
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_POSIX_ROOT = Path("/mnt/e/social_data")
DEFAULT_WINDOWS_ROOT = Path("E:/social_data")


def data_root() -> Path:
    env = os.environ.get("SOCIAL_DATA_DIR")
    if env:
        return Path(env).expanduser()
    if DEFAULT_POSIX_ROOT.parent.exists():  # /mnt/e 已挂载
        return DEFAULT_POSIX_ROOT
    if DEFAULT_WINDOWS_ROOT.parent.exists():  # Windows 原生运行
        return DEFAULT_WINDOWS_ROOT
    return DEFAULT_POSIX_ROOT


def db_path() -> Path:
    return data_root() / "data.db"


def raw_dir() -> Path:
    return data_root() / "raw"


def exports_dir() -> Path:
    return data_root() / "exports"


def events_file() -> Path:
    return data_root() / "events" / "publish_events.jsonl"


def ensure_layout() -> dict:
    """启动自检：目录可建、盘可写。任何失败都抛 RuntimeError 终止采集。"""
    root = data_root()
    try:
        for directory in (root, raw_dir(), exports_dir() / "daily", events_file().parent):
            directory.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except (OSError, PermissionError) as exc:
        raise RuntimeError(
            f"数据盘不可用: {root} ({exc})。按 ADR-0002 不降级写本地盘，采集终止。"
        ) from exc
    return {"root": str(root), "db": str(db_path())}
