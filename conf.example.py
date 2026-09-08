from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
XHS_SERVER = "http://127.0.0.1:11901"  # only used by xhs-related flows
LOCAL_CHROME_PATH = ""  # optional, e.g. C:/Program Files/Google/Chrome/Application/chrome.exe
LOCAL_CHROME_HEADLESS = True  # default headless behavior for uploader/examples
DEBUG_MODE = True  # default debug behavior
# Optional proxy for the YouTube uploader. Where youtube.com is blocked, direct
# connections time out and the (patchright) chromium does NOT use the system proxy.
# Point this at your local proxy port, e.g. "http://127.0.0.1:7890". None = no proxy.
YT_PROXY = None

# 固定标签清单：发布时 --extra-tag-pool 追加在 --tags 之后，按内容类型选组（可多组）。
# bilibili.activity 等默认池已内置在 utils/extra_tags.py，这里可按部署覆盖/扩展（同名平台键整体覆盖默认）。
PLATFORM_EXTRA_TAG_POOLS = {
    # "bilibili": {"activity": ["哔哩哔哩开学季", "开学季", "创作激励", "涨粉计划"]},
    "kuaishou": {},
    "toutiao": {},
}
