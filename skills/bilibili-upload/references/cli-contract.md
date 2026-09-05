# Bilibili CLI 契约

这个 skill 默认假设当前环境已经安装并可调用 `sau` 命令。

## 命令列表

### 账号巡检（只读）

```bash
sau bilibili health --account <account> [--limit 20]
```

- 预期输出:
  - JSON：`account`（已发/待审计数）、`works`（bvid/标题/`state`/`state_desc`/拒绝原因/播放数据）、`summary`（待审清单、被拒清单、播放中位数）
- 行为:
  - 只读，走投稿管理官方 API，不发布任何内容
- 判断口径:
  - `state` 为负值（-30=待审，-40=等待转码，其他负值=被拒）需关注；`rejected` 清单里的 `reason` 是官方拒绝理由

### 登录


```bash
sau bilibili login --account <account>
```

- 必填参数：
  - `--account`
- 作用：
  - 自动准备 `biliup`
  - 触发 Bilibili 登录流程
- 账号说明：
  - `--account` 传的是用户自定义的 `account_name`，不是固定只能叫 `creator`
  - 一个 `account_name` 对应一个账号文件，可用于多账号隔离和并发任务
- 登录方式说明：
  - 这个命令应该由用户自己在本地真实终端里运行
  - 如果终端二维码显示不完整，可直接打开当前目录下的 `qrcode.png` 扫码
  - agent 不应该在非交互环境里硬跑这个命令

### 校验账号

```bash
sau bilibili check --account <account>
```

- 必填参数：
  - `--account`
- 预期输出：
  - `valid`
  - `invalid`

### 上传视频

```bash
sau bilibili upload-video \
  --account <account> \
  --file <video-path> \
  --title "<title>" \
  --desc "<desc>" \
  --tid <category-id> \
  [--tags tag1,tag2] \
  [--schedule "YYYY-MM-DD HH:MM"]
```

- 必填参数：
  - `--account`
  - `--file`
  - `--title`
  - `--desc`
  - `--tid`
- 可选参数：
  - `--tags`
  - `--schedule`

## 额外说明

- `--tid` 第一版必须传
- `--tags` 使用逗号分隔
- `--schedule` 走 `sau` 统一时间格式
- 程序会自动准备和更新 `biliup`
