# 创作者数据中台：数据库与原始存档放 Windows E 盘，接受单进程写约束

数据中台（`collector/` 模块）的 SQLite 库、原始接口响应存档与导出报表统一放 `E:\social_data\`（WSL 内经 `/mnt/e` 访问），而不是 WSL 本地文件系统。决定动机：用户要求运营数据留在 Windows 侧——可直接用 DB Browser 打开查看、可直接纳入 Windows 侧备份，且 E 盘容量（约 436G 空闲）远大于 WSL 虚拟盘。代价是 WSL2 经 9p/drvfs 访问该文件时锁不可靠、读写比本地盘慢 5–10 倍，因此立下硬约束：**只允许采集进程单线程串行写库**，查询连接只读。本项目的写入量（每平台每天一至两次快照、共数百行）远低于该约束的敏感区，性能损耗无感。

## Considered Options

- 库放 WSL 本地盘、每日备份到 E 盘：性能最好且锁可靠，但 Windows 侧看到的副本永远滞后，且两份文件增加心智负担，与"数据在 E 盘"的目标相悖。
- 库放 E 盘但用 SQLite WAL 多进程并发写：9p 上的 WAL 锁语义不被支持，会出现静默数据损坏，直接排除。

## Consequences

- 任何未来功能（如 Web 看板、定时聚合任务）若要写库，必须与采集器共用同一串行写入路径（加进程内队列），不得另开进程直接写。
- 库文件损坏时的恢复策略依赖 `raw/` 原始响应存档：全部指标可由存档重放重建，因此存档与库同盘存放且清理策略一致（raw 默认保留 90 天，重建窗口内必须保留）。
- **2026-09-07 实测补充**：9p/drvfs 不支持 SQLite WAL 的共享内存 mmap（`PRAGMA journal_mode=WAL` 直接报 `disk I/O error`），实际采用传统 rollback journal（`journal_mode=DELETE`）+ `synchronous=NORMAL`；本 ADR 标题所述"单进程写"约束因此更为关键。
- 发布进程不写库的落地机制：发布成功后向 `E:\social_data\events\publish_events.jsonl` 追加事件行（append 在 9p 上安全），由采集进程消费并排程增量采集（`collector/events.py`）。
