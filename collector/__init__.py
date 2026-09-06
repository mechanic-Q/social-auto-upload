# -*- coding: utf-8 -*-
"""创作者数据中台采集模块。

架构约定（docs/adr/0002）：
- 所有数据落在 Windows E 盘 ``E:\\social_data\\``（WSL 侧 ``/mnt/e/social_data``），
  由 :mod:`collector.paths` 解析；E 盘不可用时采集直接终止，禁止降级写本地盘。
- SQLite 只允许采集进程单线程串行写入，唯一入口是 :class:`collector.base.CollectorStore`。
- 发布流程不写库：发布成功后只向 ``events/publish_events.jsonl`` 追加事件行，
  由采集进程消费（:mod:`collector.events`）。
"""
