# -*- coding: utf-8 -*-
"""宽容解析共用层：在未知结构的平台 JSON 响应里按候选键名收集"作品"字典。

各平台创作者后台没有公开接口文档，页面结构随版本变化，因此解析器不绑定
具体路径——只要字典长得像作品（笔记/视频/图文）就收，多来源间按 id 去重
并补齐缺失指标。首次接入新平台时先用 probe 模式收集真实样本，再按样本
收紧候选键名。
"""
from __future__ import annotations

# id 只认作品专有键名，不认通用 "id"——否则用户/评论等 dict 会被误收
DEFAULT_ID_KEYS = ("note_id", "noteId", "take_id", "itemId", "itemIdStr", "item_id",
                   "video_id", "videoId", "aweme_id", "awemeId", "article_id", "articleId",
                   "media_id", "mediaId", "tgt_iid", "objectId", "workId")
DEFAULT_TITLE_KEYS = ("display_title", "title", "desc", "name", "caption")
DEFAULT_METRIC_CANDIDATES = {
    "view": ("read_num", "view_num", "read", "view_count", "pv", "exposure", "play_cnt", "playCount",
             "watch_cnt", "readCount", "show_cnt", "readCnt", "watchCount", "go_detail_count", "playCnt"),
    "like": ("like_num", "likes", "like_count", "like", "digg_cnt", "diggCount", "praise_cnt", "likeCnt", "likeCount"),
    "comment": ("comment_num", "comment_count", "comment", "comments", "cmt_cnt", "comment_cnt", "commentCnt"),
    "share": ("share_num", "share_count", "share", "forward", "share_cnt", "shareCnt"),
    "collect": ("collect_num", "collect_count", "collect", "fav_num", "favorite_cnt", "store_cnt", "collectCnt"),
}

_UNIFIED = ("view", "like", "comment", "share", "collect")


def walk_dicts(node, depth: int = 0):
    if depth > 8:
        return
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_dicts_nested(value, depth + 1)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_dicts_nested(value, depth + 1)


def _walk_dicts_nested(value, depth):
    yield from walk_dicts(value, depth)


def pick(d: dict, keys):
    for key in keys:
        if key in d and isinstance(d[key], (str, int, float)):
            return d[key]
    return None


def looks_like_work(d: dict, id_keys, title_keys, metric_candidates) -> bool:
    if pick(d, id_keys) is None:
        return False
    if pick(d, title_keys) is None:
        return False
    return any(pick(d, candidates) is not None for candidates in metric_candidates.values())


def parse_work_payloads(payloads: list, id_keys=DEFAULT_ID_KEYS, title_keys=DEFAULT_TITLE_KEYS,
                        metric_candidates=DEFAULT_METRIC_CANDIDATES) -> list[dict]:
    """从若干 JSON 响应里宽容地收集作品 dict（去重按 id，多来源补齐缺失指标）。

    输出的 native 已是统一键口径（view/like/comment/share/collect）。
    """
    merged: dict[str, dict] = {}
    for payload in payloads:
        for candidate in walk_dicts(payload):
            if not looks_like_work(candidate, id_keys, title_keys, metric_candidates):
                continue
            external_id = str(pick(candidate, id_keys))
            native = {unified: pick(candidate, candidates) for unified, candidates in metric_candidates.items()}
            merged.setdefault(external_id, {
                "external_id": external_id,
                "title": str(pick(candidate, title_keys) or ""),
                "native": native,
            })
            for key, value in native.items():
                if merged[external_id]["native"].get(key) is None and value is not None:
                    merged[external_id]["native"][key] = value
    return list(merged.values())
