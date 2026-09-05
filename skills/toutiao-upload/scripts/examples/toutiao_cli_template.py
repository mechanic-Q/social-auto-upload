# -*- coding: utf-8 -*-
"""以编程方式调用 sau_cli 发布头条视频的模板。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import sau_cli
from sau_cli import ToutiaoVideoUploadRequest, login_toutiao_account, resolve_account_file
from uploader.toutiao_uploader.main import toutiao_setup


async def main() -> None:
    account_name = "account_a"
    account_file = resolve_account_file("toutiao", account_name)

    if not await toutiao_setup(str(account_file), handle=False):
        await login_toutiao_account(account_name, headless=True)

    request = ToutiaoVideoUploadRequest(
        account_name=account_name,
        video_file=Path("videos/demo.mp4"),
        title="头条视频标题（30字内）",
        description="视频简介描述",
        tags=["科技", "人工智能"],
        publish_date=0,
        # thumbnail_file=Path("videos/demo.png"),
        # activity="某创作活动全名",
        # declaration="原创",
    )
    await sau_cli.upload_toutiao_video(request)
    print(f"Toutiao video submitted: {request.video_file}")


if __name__ == "__main__":
    asyncio.run(main())
