# 今日头条 CLI 契约

这个 skill 默认假设当前环境已经安装并可调用 `sau` 命令。

## 命令列表

### 登录

```bash
sau toutiao login --account <account>
```

- 必填参数:
  - `--account`
- 作用:
  - 启动头条号登录流程，为指定账号生成或刷新 cookie 文件
  - 登录页支持头条 APP / 抖音 APP 扫码
  - 如果登录过程中生成本地二维码图片，agent 应优先直接把图片展示/发送给用户扫码，而不是只回传路径
- 账号说明:
  - `--account` 传的是用户自定义的 `account_name`
  - 一个 `account_name` 对应一个账号文件，可用于多账号隔离和并发任务

### 校验 cookie

```bash
sau toutiao check --account <account>
```

- 必填参数:
  - `--account`
- 预期输出:
  - `valid`：cookie 可用
  - `invalid`：cookie 缺失或已失效

### 上传视频

```bash
sau toutiao upload-video \
  --account <account> \
  --file <video-path> \
  --title "<title<=30 chars>" \
  [--desc "<description>"] \
  [--tags tag1,tag2] \
  [--extra-tag-pool <pool-name>] \
  [--schedule "YYYY-MM-DD HH:MM"] \
  [--thumbnail <image-path>] \
  [--activity "<activity-name>"] \
  [--declaration "<原创|头条首发>"] \
  [--debug] \
  [--headless | --headed]
```

- 必填参数:
  - `--account`
  - `--file`
  - `--title`（不超过 30 字，超限直接报错）
- 可选参数:
  - `--desc`
  - `--tags`（最多 10 个，超限截断并告警；0908 探测实测话题可打满 10）
  - `--extra-tag-pool`（conf.PLATFORM_EXTRA_TAG_POOLS 里的组名，可重复传）
  - `--schedule`
  - `--thumbnail`
  - `--activity`（精确活动名，建议来自 list-activities 输出）
  - `--declaration`（"作品声明"区 checkbox 文本，如 AI生成/自行拍摄/引用内容；勾选失败时发布终止）
  - `--draft`（存草稿不发布，已实测可用）
  - `--debug`
  - `--headless`
  - `--headed`

### 活动发现

```bash
sau toutiao list-activities --account <account> [--headless | --headed]
```

- 必填参数:
  - `--account`
- 预期输出:
  - 空数组 `[]`（实测 2026-09-06：头条视频发布页没有活动入口，活动功能仅快手支持）
- 行为:
  - 只读，不会发布任何内容

## 发布策略

- 如果不传 `--schedule`，CLI 使用立即发布
- 如果传了 `--schedule`，CLI 自动切换为定时发布
- 时间格式为:

```text
YYYY-MM-DD HH:MM
```

## 额外说明

- `upload-video` 每次命令只支持一个视频文件
- 当前仅支持视频发布；文章、微头条、图文尚未接入
- 视频描述字段统一使用 `--desc`
- 话题标签在发布页通过平台联想下拉选择，等不到候选时跳过该标签（不阻断发布），因此 `--tags` 里的标签名应使用平台已有话题词
