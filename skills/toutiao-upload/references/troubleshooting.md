# 故障排查

## 找不到 `sau` 命令

可以尝试以下方式：

```powershell
.\.venv\Scripts\Activate.ps1
sau toutiao --help
```

```powershell
.\.venv\Scripts\sau.exe toutiao --help
```

```bash
uv run sau toutiao --help
```

如果当前环境还没有安装项目：

```bash
uv pip install -e .
```

## cookie 无效或已过期

先检查 cookie 状态：

```bash
sau toutiao check --account <account>
```

如果无效，就重新登录：

```bash
sau toutiao login --account <account>
```

## 登录二维码问题

如果用户反馈二维码在终端里不好扫：

- 先优先使用 CLI / uploader 生成的本地二维码图片
- 只有用户明确需要可见浏览器窗口，或图片方案仍然不方便时，再切到 `--headed`
- 如果 CLI / uploader 已经生成临时二维码图片，agent 不要只回图片路径
- agent 应优先直接把本地二维码图片展示/发送给用户扫码
- 图片路径只作为补充信息

## 登录页没有出现二维码

头条登录页默认可能展示手机号登录：

- 无头模式会尝试自动点击"扫码登录"切换
- 如果仍然失败，用 `--headed` 人工登录一次，登录成功后 cookie 会自动落盘

## 上传参数缺失

### 视频上传

最少需要：

- `--account`
- `--file`
- `--title`（不超过 30 字）

## 标题超 30 字报错

头条视频标题上限 30 字（2026-09-08 页面实测），CLI 会直接报错而不是自动截断：

- 让用户给一个更短的标题
- 或者把长标题放进 `--desc`

## 标题回读校验失败（发布被终止）

uploader 填完标题会回读页面值做校验，不一致会重试 3 次，仍失败则终止发布并截图 `/tmp/toutiao_title_fail.png`。这通常意味着平台又改版了：

- 看截图确认标题框的真实结构
- 更新 `uploader/toutiao_uploader/main.py` 常量区的 `TOUTIAO_TITLE_CONTAINER` / `TOUTIAO_TITLE_PLACEHOLDER`

## 点击发布后失败

点"发布"后的失败现在会写入 `logs/toutiao.log`（ERROR 级）并截图 `/tmp/toutiao_submit_fail.png`，不再只出现在终端 stderr。排查顺序：

1. `tail -50 logs/toutiao.log` 看最后几行（成功必有"视频发布成功"）
2. 看截图 `/tmp/toutiao_submit_fail.png` 确认页面当时状态（弹窗？报错气泡？）
3. 若弹窗文案含"标题"，说明平台拦了空/超限标题——先解决标题问题
4. 到头条后台内容管理页人工核验是否实际已发出，**确认没发才能重试，禁止盲目重复点击发布**

## 声明原创失败导致发布终止

`--declaration` 声明失败（如账号未开通原创权益）时发布终止，这是有意设计：

- 确认账号是否已开通原创权益
- 或去掉 `--declaration` 发布（不声明原创）

## 活动参与失败导致发布终止

`--activity` 匹配不到活动时发布终止，这是有意设计：

- 先跑 `sau toutiao list-activities --account <account>` 拿到当前可参加活动的精确名称
- 活动名要与 list-activities 输出完全一致

## 定时发布

时间格式使用：

```text
YYYY-MM-DD HH:MM
```

如果不需要定时发布，去掉 `--schedule` 即可改为立即发布。
