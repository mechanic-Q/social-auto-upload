# CLI 使用说明

项目现在提供一个统一的 CLI 入口 `sau`，当前主线已经接入：

- `douyin`
- `kuaishou`
- `xiaohongshu`
- `bilibili`
- `tencent`（视频号）
- `youtube`
- `toutiao`

实现说明：

- `sau_cli.py` 是当前 CLI 的主入口和唯一主要实现文件
- `sau.exe` 是安装后在 Windows 虚拟环境里自动生成的命令入口，本质上还是调用 `sau_cli.py`
- 如果需要给 OpenClaw、Codex 等 agent 使用，可参考仓库内 skill：
  - `skills/douyin-upload/`
  - `skills/kuaishou-upload/`
  - `skills/xiaohongshu-upload/`
  - `skills/bilibili-upload/`

## 安装 CLI 入口

如果你希望直接使用 `sau` 命令，而不是手动执行 `python sau_cli.py`，先在项目根目录安装一次：

```bash
uv pip install -e .
```

安装后就可以直接使用：

```bash
sau douyin --help
sau kuaishou --help
sau xiaohongshu --help
sau bilibili --help
```

## 安装 patchright 浏览器

Windows 下推荐先指定镜像，再安装 Chromium：

```powershell
$env:PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright"; patchright install chromium
```

## 抖音 CLI 子命令

```bash
sau douyin login --account <account_name>
sau douyin login --account <account_name> --headless
sau douyin check --account <account_name>
sau douyin upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --tags 运动,训练
sau douyin upload-note --account <account_name> --images videos/1.png videos/2.png --title "图文标题" --note "图文示例" --tags 图文,测试
```

## 快手 CLI 子命令

```bash
sau kuaishou login --account <account_name>
sau kuaishou check --account <account_name>
sau kuaishou upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --tags 运动,训练
sau kuaishou upload-note --account <account_name> --images videos/1.png videos/2.png videos/3.png --title "图文标题" --note "图文示例" --tags 图文,测试
sau kuaishou list-activities --account <account_name>
```

## 今日头条 CLI 子命令

```bash
sau toutiao login --account <account_name>
sau toutiao check --account <account_name>
sau toutiao upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --tags 科技,人工智能
sau toutiao list-activities --account <account_name>
```

- 头条当前仅支持视频发布（`upload-video`），暂无图文/文章；发布走西瓜上传通道
- 标题必填且不超过 300 字；话题最多 10 个（联想命中平台词库才生效，未命中自动跳过不阻断）
- `--declaration "AI生成"` 等勾选"作品声明"区的声明项（常见：AI生成/自行拍摄/引用内容/虚构演绎）；
  勾选失败时发布终止（不静默发布）。该页面无"声明原创"选项（需账号开通原创权益后才可能出现）
- `--draft` 存草稿不发布（已实测）；`--activity` 在头条视频发布页不可用（实测无活动入口，
  传了会明确报错终止），活动功能当前仅快手支持
- 登录支持头条 APP / 抖音 APP 扫码

## 小红书 CLI 子命令（已停用）

> **⛔ 小红书通道已于 2026-09-05 停用**：现有浏览器自动化方式在该平台封号风险过高（多次实测）。调用会返回错误；恢复需将 `conf.py` 的 `XIAOHONGSHU_ENABLED` 改为 `True`。以下命令仅作历史参考。

```bash
sau xiaohongshu login --account <account_name>
sau xiaohongshu check --account <account_name>
sau xiaohongshu upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --tags 小红书,视频
sau xiaohongshu upload-note --account <account_name> --images videos/1.png videos/2.png videos/3.png --title "图文标题" --note "图文示例" --tags 图文,测试
```

海外环境如果无法登录默认创作者后台，可以通过环境变量切换到 RedNote 域名。该设置同时作用于登录、cookie 校验、视频发布和图文发布：

```bash
SAU_XHS_CREATOR_BASE_URL=https://creator.rednote.com sau xiaohongshu login --account <account_name>
```

## Bilibili CLI 子命令

```bash
sau bilibili login --account <account_name>
sau bilibili check --account <account_name>
sau bilibili upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --tid 249 --tags 足球,测试
# 内容标签 + 固定活动标签拼满 10 个上限：--extra-tag-pool activity（组清单在 conf.PLATFORM_EXTRA_TAG_POOLS）
```

补充说明：

- `creator` 之类的名字只是示例值，真正传的是用户自定义的 `account_name`
- 一个 `account_name` 对应一个账号文件，可以准备多个账号并发使用
- 浏览器平台统一元数据约定：
- 视频使用 `title + desc + tags`
- 图文使用 `title + note + tags`
- `sau bilibili ...` 会自动准备 `biliup`
- 如果本地没有 `biliup`，第一次运行会自动下载
- 如果上游 GitHub Release 有更新，运行时会先自动更新
- `sau bilibili login --account <name>` 建议由用户自己在本地真实终端里执行；如果终端里的二维码显示不完整，可直接打开当前目录下的 `qrcode.png` 扫码

## 登录二维码说明

- 抖音、快手、小红书登录过程中，CLI / uploader 可能会生成临时二维码图片
- 对普通用户来说，可以直接打开该图片扫码
- 对可操作本地文件的 agent 来说，不要只把图片路径告诉用户
- 这类二维码图片本身就是给用户扫码的，agent 应优先直接展示/发送本地图片给用户
- Bilibili 当前不走这套本地二维码图片托管链路，登录按上面的 Bilibili CLI 说明处理即可

## 账号巡检（health）

抖音与 B站支持只读巡检命令 `health`：登录态抓取账号处罚状态与作品状态、数据，输出 JSON 供 pipeline/agent 判断，不做任何发布操作。

```bash
sau douyin health --account <account_name> [--limit 30]
sau bilibili health --account <account_name> [--limit 20]
```

返回结构：

- `account`：账号维度。抖音含昵称/粉丝/作品数/处罚记录；B站含已发/待审计数
- `works`：每条作品的状态与数据。抖音含 `flags`（审核中/仅自己可见/禁止播放等标志）、播放/点赞/评论/分享/收藏；B站含 `state`/`state_desc`/拒绝原因与播放数据
- `summary`：聚合信号——异常状态作品清单、待审清单、被拒清单、播放中位数

判断口径：

- 处罚记录（抖音 `has_punished`）或 `works` 里出现"仅自己可见/禁止播放/被拒"= 平台侧处罚，需按平台申诉流程处理
- 状态全部正常但播放中位数持续极低 = 低流量池（内容信号问题，不是违规），从封面点击率、前 3 秒留存、内容赛道入手

快手、头条、小红书、视频号的巡检将在各平台 DOM 侦察后接入同一命令形态。

## 创作活动与固定标签

快手与头条支持"发布时参与创作活动"和"固定标签清单"：

```bash
# 活动发现：列出当前可参加的活动（JSON，只读不发布）
sau kuaishou list-activities --account <account_name>
sau toutiao list-activities --account <account_name>

# 活动参与：发布时选中指定活动（活动名需与 list-activities 输出一致）
sau kuaishou upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --activity "光合计划"
```

活动注意事项：

- `--activity` 是精确承诺：发布页找不到该活动入口或匹配不到活动名时，发布**终止**而不是静默跳过
- 只参加与内容真实相关的活动；无关活动会被平台判定为滥用，反而限流

固定标签清单（Extra Tags）：

- 在 `conf.py` 的 `PLATFORM_EXTRA_TAG_POOLS` 里按平台、按内容类型组维护（如 `news`、`tech`）
- 发布时用 `--extra-tag-pool <组名>`（可重复）把对应组的标签追加在 `--tags` 之后
- 不传 `--extra-tag-pool` 就不追加——避免把无关热门标签堆到每个视频上触发"滥用话题"限流

```bash
sau kuaishou upload-video ... --tags 科技 --extra-tag-pool tech --extra-tag-pool news
```

## 定时发布

抖音、快手、小红书、头条的图文和视频上传，以及 Bilibili 的视频上传都支持 `--schedule`。只要传了 `--schedule`，CLI 就会自动切换到对应平台的定时发布策略；不传则默认立即发布。

```bash
sau douyin upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --schedule "2026-03-24 21:30"
sau douyin upload-note --account <account_name> --images videos/1.png videos/2.png --title "图文标题" --note "图文示例" --schedule "2026-03-24 21:30"
sau kuaishou upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --schedule "2026-03-24 21:30"
sau kuaishou upload-note --account <account_name> --images videos/1.png videos/2.png videos/3.png --title "图文标题" --note "图文示例" --schedule "2026-03-24 21:30"
sau xiaohongshu upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --schedule "2026-03-24 21:30"
sau xiaohongshu upload-note --account <account_name> --images videos/1.png videos/2.png videos/3.png --title "图文标题" --note "图文示例" --schedule "2026-03-24 21:30"
sau bilibili upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --tid 249 --schedule "2026-03-24 21:30"
sau toutiao upload-video --account <account_name> --file videos/demo.mp4 --title "示例标题" --desc "示例简介" --schedule "2026-03-24 21:30"
```

## 运行时参数

CLI 将 `debug` 和 `headless` 拆成了两个独立维度：

```bash
--debug
--headless
--headed
```

- `--debug`: 打开调试行为，例如失败时保留更多调试信息
- `--headless`: 无头模式运行
- `--headed`: 有头模式运行

如果都不传，CLI 当前默认按 `headless=True` 运行。

补充：

- 抖音和快手的 CLI 默认都是无头模式
- 如果用户明确要求可见浏览器窗口，或确实需要人工看页面，再显式传 `--headed`

## 视频上传参数

```bash
--file videos/demo.mp4
--title "示例标题"
--desc "示例简介"
--tags 运动,训练
--thumbnail videos/demo.png
--thumbnail-landscape videos/cover-4x3.png
--thumbnail-portrait videos/cover-3x4.png
```

抖音和视频号支持同时设置两种比例的封面图：

- `--thumbnail-landscape`: 4:3 横版封面
- `--thumbnail-portrait`: 3:4 竖版封面
- `--thumbnail`: 兼容旧参数，等同于 3:4 竖版封面

抖音额外支持：

```bash
--product-link https://example.com/item
--product-title 示例商品
```

Bilibili 额外要求：

```bash
--tid 249
```

- `--tid` 第一版是必填
- `--tags` 会映射到 `biliup upload --tag`
- `--schedule` 会映射到 Bilibili 所需的时间戳参数

## 图文上传参数

```bash
--images videos/1.png videos/2.png videos/3.png
--title "图文标题"
--note "图文内容"
--tags 图文,测试
```

图文上传当前限制：

- 抖音：最多 35 张图片，不支持 GIF
- 快手：支持多张图片，建议传真实不同文件，不要把同一路径重复多次
- 小红书：支持多张图片，正文 `--note` 可选，但 `--title` 建议始终显式传入

后续维护 CLI 时，优先看 `sau_cli.py`、`uploader/` 和 `skills/`。

## 视频号（tencent）登录与 cookie 刷新定稿路径（2026-09-15）

> **禁止用 `sau tencent login`（WSL xvfb 扫码）**：二维码 2 分钟过期，无人值守必超时（0915 三连败实证）。
> 定稿路径 = Windows Chrome 真浏览器登录 + CDP 导出，cookie 单一事实源 = `cookies/tencent_<账号>.json` + `.ua` 侧车。

```bash
# 一键刷新（9222 不在线时加 --launch 自动拉 Chrome 并打开视频号后台）
bash /home/lmr/.hermes/skills/video-production/video-pipeline/scripts/tencent_refresh_cookie.sh diyi --launch
```

流程：Chrome `--remote-debugging-port=9222` 打开视频号后台 → 微信扫码（网页版二维码不过期）→
CDP 导出 cookie+localStorage → 组装 storage_state 写回 json → 清理 `cookies/tencent_profiles/` 影子 → `sau tencent check`。

**持久 profile 已废弃**（`_has_persistent_profile` 恒 False）：profile 存在会遮蔽 json 更新，
导致「导了新 cookie 仍判失效」。cookie 校验（cookie_auth）导航已放宽到 60s+domcontentloaded，
5s 硬超时误判有效会话的问题已根治。
