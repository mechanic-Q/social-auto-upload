# integration 分支 NOTES（2026-10-13，video-pipeline#94）

merge origin/main（0012d2c，上游 48 提交）进 fork main（3c5550e）。
冲突解决基线策略：**全按上游**（--theirs），本地定制由三个并行域票移植回来。
回滚锚点：tag `pre-upstream-merge-20261012`（合并前的 fork main）。

## 冲突文件域归属与待移植清单

| 文件 | 域票 | 基线形态 | 待移植（本地 → 上游版） |
|---|---|---|---|
| uploader/ks_uploader/main.py | video-pipeline#95 | theirs 上游版 | 本地 `_verify_and_refill_cover`（封面核验+补传，0913/0914 实证）；`KUAISHOU_MAX_TAGS` 等本地常量；活动标签测试适配 |
| uploader/douyin_uploader/main.py | video-pipeline#96 | theirs 上游版 | 核对本地 health.py（未冲突原样在）；`test_douyin_declaration.py` 适配上游 set_self_declaration 新签名（返回 bool、显式传参） |
| uploader/tencent_uploader/main.py | video-pipeline#97 | theirs 上游版 | 本地 UA 侧车（#9 会话绑 UA）+ cookie 单一事实源（#10 废弃持久 profile 遮蔽）；test_tencent_persistent_profile / test_tencent_thumbnail 适配 |
| sau_cli.py | video-pipeline#97 | theirs 上游版 | 本地 stats/collector 等子命令并集（上游版已含新平台入口 baijiahao/alipay 等） |
| utils/log.py | video-pipeline#97 | **ours+并集**（特例） | 已在基线直接补齐：上游版缺 douyin/tencent/tiktok/xhs/toutiao_logger（本地 collector/toutiao 依赖），尾部 append 五个 create_logger；#97 复核是否需要再并 |
| README.md / docs/CLI.md | video-pipeline#97 | theirs 上游版 | 本地运维说明（视频号 cookie 路径、快手封面三层防线）并回 |
| tests/test_sau_bilibili_cli.py / test_sau_browser_cli.py | #95/#96/#97 按归属分摊 | theirs | 按失败清单逐个适配 |

## 基线状态（merge 后即时）

- 可导入：uploader 四平台 + collector.cli + sau_cli + tools.probe_publish 全 OK
- CLI：`sau --help` 正常（含上游新平台入口）
- venv 增补：`playwright`（上游新平台 baijiahao/alipay 依赖）、`pytest`（uv pip install）
- pytest 现状（不要求绿，域票逐个修）：
  - test_tencent_thumbnail 9 + test_tencent_persistent_profile 7 + verification 1 + sau_tencent_cli 1 → #97
  - test_sau_toutiao_cli 6 + test_health_cli 4（toutiao 域本地定制测试）→ #97 或随 #95 顺带（活动标签同族）
  - test_sau_browser_cli 3 → 按内容归属
  - test_collector_scheduler_cli 3 → collector 零冲突但依赖 utils/log，需复核（疑似 log 并集已修，重跑确认）
  - test_kuaishou_publish_dialog 2（上游新增测试，红的原因为本地测试环境桩差异）→ #95
  - test_douyin_declaration 2 → #96
  - test_ks_toutiao_activity_tags（收集错误：KUAISHOU_MAX_TAGS 缺失）→ #95

## 基线快照

四平台探针基线（#93 产出）：douyin=login-wall(服务端注销) / kuaishou=ok /
toutiao=spinner / tencent=login-wall(重定向)。域票验收引用此基线对比。
