# -*- coding: utf-8 -*-
"""固定标签清单（Extra Tags）解析：按平台与内容组从 conf 读出待追加标签。"""
from __future__ import annotations

try:
    # conf.py 是各部署私有文件（gitignore），旧拷贝可能缺这个键，不能让 CLI 顶层 import 崩掉
    from conf import PLATFORM_EXTRA_TAG_POOLS
except ImportError:
    PLATFORM_EXTRA_TAG_POOLS = {}

# 版本化默认池：随仓库走，conf.py 同名平台键存在时整体覆盖对应平台。
# bilibili.activity 为用户 2026-09 定稿的 B站流量活动标签（6 内容标签 + 这 4 个 = 平台上限 10；
# 活动有时效性，过期更新这里或 conf.py）。
DEFAULT_PLATFORM_EXTRA_TAG_POOLS: dict = {
    "bilibili": {
        "activity": ["哔哩哔哩开学季", "开学季", "创作激励", "涨粉计划"],
    },
}


def _pools_for(platform: str) -> dict:
    merged = dict(DEFAULT_PLATFORM_EXTRA_TAG_POOLS.get(platform, {}))
    merged.update(PLATFORM_EXTRA_TAG_POOLS.get(platform, {}))
    return merged


class UnknownTagPoolError(ValueError):
    pass


def available_tag_pools(platform: str) -> list[str]:
    return list(_pools_for(platform).keys())


def resolve_extra_tags(platform: str, pool_names: list[str] | None) -> list[str]:
    """按组名合并固定标签，保持声明顺序与组内顺序，去重且不与已有标签冲突。"""
    pools = _pools_for(platform)
    if not pool_names:
        return []

    unknown = [name for name in pool_names if name not in pools]
    if unknown:
        raise UnknownTagPoolError(
            f"平台 {platform} 没有标签组: {', '.join(unknown)}，PLATFORM_EXTRA_TAG_POOLS 里可用的组: {list(pools.keys()) or '（空）'}"
        )

    resolved: list[str] = []
    for name in pool_names:
        for tag in pools[name]:
            if tag and tag not in resolved:
                resolved.append(tag)
    return resolved


def merge_tags(tags: list[str], extra_tags: list[str]) -> list[str]:
    """话题标签在前，固定标签追加在后，去重。"""
    merged: list[str] = []
    for tag in list(tags) + list(extra_tags):
        if tag and tag not in merged:
            merged.append(tag)
    return merged
