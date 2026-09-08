# 多平台创作者数据中台 · 实施计划

> 2026-09-07 定稿。来源：GitHub/Gitee 穷举调研 + 六项决策确认（grill 记录见对话）。
> 术语定义见根目录 `CONTEXT.md`「数据采集」小节；存储位置决策见 `docs/adr/0002`。

## 实施状态（2026-09-07 更新：一期完成，二期/三期代码就绪）

一期 12 项任务全部落地，二期/三期采集能力同日补齐。要点修订与验证记录：

- **发布钩子机制**：发布进程不写库（ADR-0002 约束）。6 个 uploader 的 10 处发布成功点 + B 站 CLI 出口，经 `collector/events.py` 向 `E:\social_data\events\publish_events.jsonl` 追加事件行（append 在 9p 上安全）；任何钩子失败只记 warning，绝不阻塞发布。
- **SQLite journal 修订**：9p 不支持 WAL（共享内存 mmap 报 `disk I/O error`，实测确认），改用 `journal_mode=DELETE` + `synchronous=NORMAL`，见 ADR-0002 实测补充。
- **真实验证**：B 站 124 作品 + 粉丝 3136 入库成功，二次采集幂等（works_new=0）；抖音 40 作品 + 粉丝 68 入库；增量消费链路端到端验证；数据盘故障模拟通过；Windows 任务计划两任务注册并真实触发成功（Last Result=0）。
- **二期/三期补齐（2026-09-07 第二、三轮）**：
  - 快手采集器**真机校准成功并全量入库**（10 作品）：probe 样本揭示列表接口键名 `workId/title/playCount/likeCount/commentCount`，且管理页需用 `status=0` 筛选（`status=2` 下 total=0）；候选键已按真实样本收紧进 `ProbeProfile`。
  - 快手/视频号/头条通用采集器 `collector/generic.py`（probe-first + 宽容解析 `collector/fuzzy.py`），capture 存档文件名带接口 URL 尾部便于校准。
  - 头条/视频号：probe 机制工作正常（cookie 有效、页面可开），但真实作品列表接口尚未捕获到（头条候选样本均为消息接口 `msg_list`；视频号 0 命中候选标记）——需真机 DevTools 观察网络面板后收紧 `ProbeProfile`，raw 存档持续积累。
  - 详情级框架 `collector/details.py`：7 天内 + Top N 目标筛选（有测试）、`content_details` 写入接口、probe-first 纪律（样本未校准前不写库）。
  - 三期聚合接口：`sau stats crosswalk [--output x.json]` 导出 match_key 清单，供 daily-china published-track 按键 join。
- **遗留（按责任人）**：
  - 用户操作：小红书 cookie 已失效——`sau xiaohongshu login --account diyi` 扫码后跑 `sau stats collect --probe --only xiaohongshu`，用真实样本校准解析器。
  - 时间自然累积：验收 #1/#5 的"连续 3 天"由已注册的任务计划自动完成（09-08/09-09 09:30），核验命令 `sau stats status` 看 collect_runs 按日出现 success。
  - 真实发布：验收 #3 由下一次真实发布自动验证（钩子 → 事件 → 30-90 分钟后增量采集 → is_incremental=1 首日快照）。
  - 样本校准：快手/头条/视频号的宽容解析候选键，随 probe 样本积累后收紧（raw 存档可重放）。
  - 套件中 2 个失败为用户未提交的视频号改动所致（二维码 fetch 重构、发布按钮点击方式），与本模块无关。

## 1. 目标

每天通过 social-auto-upload 发布作品后，自动采集各平台本人账号的运营数据（播放、互动、粉丝），落成时序快照库，支持 CLI 问数、每日日报与跨平台复盘分析。

## 2. 已定决策

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | 代码落点 | 本项目内新增 `collector/` 模块，复用现有 cookie 体系与 Playwright 环境，不建独立仓库 |
| 2 | 数据位置 | `E:\social_data\`（WSL 侧 `/mnt/e/social_data/`），SQLite 直放，仅采集进程单线程写库 |
| 3 | 平台分期 | 一期 **B站(API) → 抖音 → 小红书**；二期 视频号、快手；三期 头条；百家号无 cookie 不做 |
| 4 | 指标范围 | 一期仅列表页指标；完播率/流量来源/粉丝画像放二期，且只对「发布 7 天内 + 周表现 Top N」作品补采 |
| 5 | 输出形态 | 一期 `sau stats` CLI + 每日 Markdown 日报落 E 盘；推送、前端看板二期再议 |
| 6 | 调度 | A：发布成功后延迟 30–60 分钟（随机）单平台增量采集；B：每日 09:30 全量采集 + 隔天开机补跑；Windows 任务计划程序触发 |
| 7 | daily-china 衔接 | 一期完全独立；`contents` 表预留规范化标题 + 发布日期的匹配键，二期聚合时 join |

## 3. 架构总览

```
发布通道 uploader/*.py ──发布成功──> publish 钩子（写 publish 事件 + 排程增量采集）
                                        │ 延迟随机 30–60 分钟
                                        ▼
Windows 任务计划(每日 09:30) ──────> collector/scheduler.py（含隔天补跑判断）
                                        │
                        ┌───────────────┼───────────────┐
                        ▼               ▼               ▼
                  bilibili.py      douyin.py     xiaohongshu.py
                  （HTTP API）   （Playwright 拦 XHR，DOM 兜底）
                        └───────────────┼───────────────┘
                                        ▼
                    E:\social_data\data.db（SQLite WAL，六表）
                    E:\social_data\raw\<平台>\<日期>\（原始响应存档）
                    E:\social_data\exports\daily\<日期>.md（日报）
                                        ▼
                    sau stats CLI ／ ZCode 直接问数 ／ 每日日报
```

关键取舍：
- **拦 XHR 接口响应优先于解析 DOM**（借鉴 douyin-creator-data-collector）：平台改版时接口往往还在，且原始响应落 `raw/` 后可重放重建库。
- **采集与发布时间脱开**（决策 6-A 的延迟随机）：避免平台把「发完立刻翻后台」识别为固定自动化模式；采集失败只记 `collect_runs`，绝不阻塞发布主流程。
- **B 站不走浏览器**：`bilibili-API-collect` 社区接口 + 现有 `bilibili_diyi.json` cookie 即可拿自己视频的统计数据，最稳。

## 4. 目录布局

项目内（新增）：

```
collector/
├── __init__.py
├── base.py        # Collector 基类：cookie 加载、collect_runs 记账、raw 存档、串行写库锁
├── models.py      # 建表与轻量迁移
├── normalize.py   # 平台原生字段 → 统一字段映射（借鉴 data-scientist-community），保留原始值列
├── bilibili.py    # API 采集器
├── douyin.py      # 创作者中心内容管理页
├── xiaohongshu.py # 创作服务平台笔记管理页
├── scheduler.py   # A/B 触发、补跑判断、publish 事件消费
├── report.py      # 每日日报
└── cli.py         # sau stats 子命令实现
```

E 盘：

```
E:\social_data\
├── data.db                        # SQLite（WAL），仅采集进程可写
├── raw\<平台>\<yyyy-mm-dd>\*.json # 原始接口响应，保留 90 天（重建窗口）
└── exports\daily\<yyyy-mm-dd>.md  # 每日日报，永久保留
```

## 5. 数据库设计（六表）

```sql
-- 账号维表（多账号就绪，当前每平台一号）
accounts(id, platform, account_name, created_at)

-- 账号级每日快照（粉丝数、主页访问、总获赞等，平台可见什么采什么）
account_snapshots(id, account_id, snapshot_date, follower_count, total_view, raw JSON)

-- 作品维表；sau_task_id 关联发布任务；match_key = 规范化标题 + 发布日期（决策 7）
contents(id, platform, account_id, work_url, title, normalized_title, publish_date,
         sau_task_id, source_pipeline, first_seen_at)

-- 作品级指标时序（核心表，只追加不覆盖）
content_snapshots(id, content_id, collected_at, view, like, comment, share, collect,
                  is_incremental BOOL)        -- 区分 A 触发 / B 触发

-- 详情级数据（二期启用：完播率、平均播放时长、流量来源、粉丝画像 JSON）
content_details(content_id, collected_at, detail JSON)

-- 采集运行日志（成败、耗时、原始响应存档路径、失败原因）
collect_runs(id, platform, account_id, trigger, started_at, finished_at,
             status, works_seen, works_new, raw_dir, error)
```

统一指标口径原则：`view` 在 B 站 = 播放、小红书 = 阅读（观看）、视频号 = 观看，映射表放 `normalize.py`，每行同时保留平台原生字段值。

## 6. 一期任务清单

1. `models.py` 建表 + 路径常量（`E:\social_data` 可写性自检）+ 单测
2. `base.py`：cookie 加载（复用 `cookies/*_diyi.json` 的 storage_state）、raw 存档、collect_runs 记账
3. **B 站采集器**（最简，先打通全链路）：API 拉本人视频列表 + 统计 → 快照
4. 发布钩子：各 uploader 成功路径追加一行式调用，写 publish 事件（try/except 包裹，失败不影响发布）。注意：`uploader/douyin_uploader/main.py` 与 `uploader/tencent_uploader/main.py` 当前有未提交改动，钩子基于最新代码合并
5. 抖音采集器：创作者中心内容管理页，XHR 拦截（参考 `xhs_douyin_content`、`social-auto-upload-data-center` 的页面路径与解析字段）
6. 小红书采集器：创作服务平台笔记管理页（参考 `wuwangfanchai/xhs-creator-analytics` 的字段，其「绕过半年显示限制」的分页遍历思路一并借鉴）
7. `normalize.py` 映射表 + 快照写入（增量/全量标记）
8. `sau stats` CLI：`status`（各平台上次采集时间与健康度）、`list`（作品跨平台表现）、`trend`（单作品/单平台时序）
9. `report.py` 每日日报：各平台汇总、发布 7 天内作品表现、Top 播放、采集异常告警 → 落 `exports/daily/`
10. Windows 任务计划注册脚本（`wsl` 命令触发，09:30 全量；补跑逻辑：`collect_runs` 无今日成功记录即先跑全量）
11. 增量采集消费：发布钩子排程的延迟任务由 scheduler 在既有进程内执行（不新增常驻进程）
12. 文档收尾：README 增加 collector 章节

## 7. 二期 / 三期范围

- **二期**：视频号、快手采集器；详情级采集（`content_details`，限 7 天内 + 周 Top N）；视一期使用感受决定推送（飞书/钉钉/TG）或 sau_frontend「数据统计」页（借鉴 luya-yoliya/social-auto-upload-data-center 的注入方式）
- **三期**：头条采集器（参考 mf-yang/toutiao-ops 的浏览器内 API 思路）；与 daily-china published-track 按 `match_key` 聚合

## 8. 风险与对策

| 风险 | 对策 |
|------|------|
| 创作者后台改版致解析失效 | 原始响应全量存档 `raw/`，解析器可重放重建；失败写 `collect_runs` 并进日报告警 |
| 平台风控 | 频率克制（A 单平台一次 + B 每日一次）、A 延迟随机、采集与发布不同时共用浏览器会话；必要时引入 Patchright（CreatorHub 方案） |
| 9p 单进程写约束被破坏 | 写库唯一入口在 `base.py`（进程内队列串行），ADR-0002 立此存照 |
| 跨平台指标口径混淆 | `normalize.py` 统一字段 + 保留原生值列，报告标注口径来源 |
| E 盘不可用（未挂载/满） | 采集启动自检，失败只告警不落 WSL 本地（避免数据分叉） |

## 9. 一期验收标准

1. B 站连续 3 天自动快照，数值与创作者后台人工核对一致
2. 抖音、小红书各完成 ≥1 次成功全量采集
3. 发布一条抖音后 30–60 分钟内自动出现首日快照（`is_incremental=1`）
4. `sau stats trend` 一条命令输出跨平台对比
5. 日报连续 3 天自动落 `E:\social_data\exports\daily\`
6. 拔掉 E 盘模拟故障：采集告警、发布主流程不受任何影响

## 10. 参考项目与借鉴点

| 项目 | 借鉴 |
|------|------|
| luya-yoliya/social-auto-upload-data-center | 同生态扩展的页面路径、cookie 转换、日报形态；二期前端注入方式 |
| cwjcw/xhs_douyin_content (304★) | 抖音/小红书指标全集（含 2s 跳出、播放时长）、每日增长对比思路 |
| Xavier-168/data-scientist-community | 四平台字段归一化映射表 |
| fxl1209739475-fxl/douyin-creator-data-collector | XHR 拦截优于 DOM 解析、JSONL 存档 |
| yimeizhanggemini-arch/xiaohongshu-mcp | 采集元数据（字段覆盖率、缺失原因、质量警告） |
| wuwangfanchai/xhs-creator-analytics | 小红书分页遍历全量笔记（绕半年限制） |
| 3441293738/creatorhub (1895★) | 二期 Patchright 反检测、账号独立 Profile |
| mf-yang/toutiao-ops | 三期头条「浏览器内 API」取数 |
| xntj-ai/creator-analytics | 分析层方法论（insight-playbook），可装为 ZCode skill 出周报 |
