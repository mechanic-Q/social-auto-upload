# -*- coding: utf-8 -*-
"""固定标签清单（Extra Tags）解析：按平台与内容组从 conf 读出待追加标签。"""
from __future__ import annotations

from conf import PLATFORM_EXTRA_TAG_POOLS


class UnknownTagPoolError(ValueError):
    pass


def available_tag_pools(platform: str) -> list[str]:
    return list(PLATFORM_EXTRA_TAG_POOLS.get(platform, {}).keys())


def resolve_extra_tags(platform: str, pool_names: list[str] | None) -> list[str]:
    """按组名合并固定标签，保持声明顺序与组内顺序，去重且不与已有标签冲突。"""
    pools = PLATFORM_EXTRA_TAG_POOLS.get(platform, {})
    if not pool_names:
        return []

    unknown = [name for name in pool_names if name not in pools]
    if unknown:
        raise UnknownTagPoolError(
            f"平台 {platform} 没有标签组: {', '.join(unknown)}，conf.PLATFORM_EXTRA_TAG_POOLS 里可用的组: {list(pools.keys()) or '（空）'}"
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
