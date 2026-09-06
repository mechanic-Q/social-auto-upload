# -*- coding: utf-8 -*-
"""跨平台字段归一化。

统一指标口径（借鉴 data-scientist-community 的映射思路）：所有平台的作品指标
归一到 ``view / like / comment / share / collect`` 五个统一字段，映射表同时
保留平台原生字段名——报告侧标注口径来源，避免"播放/阅读/观看"混为一谈。
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime

PLATFORMS = ("bilibili", "douyin", "xiaohongshu", "kuaishou", "tencent", "toutiao")

# 统一字段 -> 各平台原生字段名（值为 None 表示该平台列表页不提供此指标）
# kuaishou/tencent/toutiao 走宽容解析(collector/fuzzy),解析层直接输出统一键,
# 映射条目留作样本校准后的精确映射位。
PLATFORM_METRIC_FIELDS: dict[str, dict[str, str | None]] = {
    "bilibili": {
        "view": "view",
        "like": "like",
        "comment": "reply",
        "share": "share",
        "collect": "favorite",
    },
    "douyin": {
        "view": "play",
        "like": "like",
        "comment": "comment",
        "share": "share",
        "collect": "collect",
    },
    "xiaohongshu": {
        "view": "read",
        "like": "like",
        "comment": "comment",
        "share": "share",
        "collect": "collect",
    },
    "kuaishou": {
        "view": "view",
        "like": "like",
        "comment": "comment",
        "share": "share",
        "collect": "collect",
    },
    "tencent": {
        "view": "view",
        "like": "like",
        "comment": "comment",
        "share": "share",
        "collect": "collect",
    },
    "toutiao": {
        "view": "view",
        "like": "like",
        "comment": "comment",
        "share": "share",
        "collect": "collect",
    },
}


def normalize_metrics(platform: str, native: dict) -> dict[str, int | None]:
    """平台原生指标 dict -> 统一五字段 dict（缺失的键保留为 None）。"""
    mapping = PLATFORM_METRIC_FIELDS[platform]
    return {unified: native.get(native_key) for unified, native_key in mapping.items()}


def normalize_title(title: str) -> str:
    """规范化标题，作为跨系统内容匹配键的一部分。

    NFKC 折叠全角/半角、去掉全部空白与零宽字符、统一小写——发布侧与采集侧
    标题可能有细微排版差异，匹配键必须在两侧算出同一个值。
    """
    text = unicodedata.normalize("NFKC", title or "")
    return "".join(ch for ch in text if not ch.isspace() and not unicodedata.category(ch) in ("Cf",)).lower()


def normalize_publish_date(value) -> str | None:
    """把各平台日期形态（时间戳/字符串/datetime）折成 ISO 日期串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).date().isoformat()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt) + 2], fmt).date().isoformat()
        except ValueError:
            continue
    return text[:10] if len(text) >= 10 else None


def match_key(platform: str, title: str, publish_date) -> str:
    """内容匹配键：规范标题 + 发布日期。daily-china published-track 聚合时同键 join。"""
    return f"{platform}:{normalize_title(title)}:{normalize_publish_date(publish_date)}"
