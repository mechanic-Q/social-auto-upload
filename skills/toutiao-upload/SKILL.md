---
name: toutiao-upload
description: 当 agent 需要通过已安装的 `sau` CLI 完成今日头条（头条号）登录、cookie 校验或视频上传时使用这个 skill。该 skill 适用于已经安装 `social-auto-upload` 且可调用 `sau` 命令的环境。优先使用这个 skill 进行稳定的命令式头条工作流，而不是一开始就阅读 uploader 源码。
---

# 今日头条上传 Skill

优先把 `sau` 作为主接口。

不要假设当前环境一定能读取仓库源码。
不要一开始就去读 `uploader/`。
只有在命令不可用或 CLI 执行失败时，才回退到故障排查说明。

## 功能概览

| 功能 | 命令入口 | 说明 |
| --- | --- | --- |
| 头条登录 | `sau toutiao login --account <name>` | 生成或刷新指定账号的 cookie（支持头条/抖音 APP 扫码） |
| cookie 校验 | `sau toutiao check --account <name>` | 检查指定账号 cookie 是否有效 |
| 视频上传 | `sau toutiao upload-video ...` | 上传并发布头条视频 |
| 活动发现 | `sau toutiao list-activities --account <name>` | 列出当前可参加的创作活动（JSON，只读） |

元数据约定：

- 视频使用 `title + desc + tags`
- 标题必填且不超过 30 字（2026-09-08 实测平台限制，超限直接报错）
- 当前仅支持视频发布，暂无图文/文章

## 默认工作流

1. 先确认 `references/runtime-requirements.md` 里的运行前提。
2. 再确认 `references/cli-contract.md` 里的命令契约。
3. 执行匹配的 `sau toutiao ...` 命令。
4. 如果命令失败，再看 `references/troubleshooting.md`。

## 支持动作

- 使用 `sau toutiao login --account <name>` 登录头条号
- 使用 `sau toutiao check --account <name>` 校验 cookie 是否有效
- 使用 `sau toutiao upload-video ...` 上传头条视频
- 使用 `sau toutiao list-activities --account <name>` 发现可参加的创作活动

## 命令选择建议

- 当用户需要新的 cookie，或现有 cookie 已失效时，使用 `login`
- 当用户只需要确认 cookie 状态时，使用 `check`
- 当用户要发布视频时，使用 `upload-video`
- 当用户想"参加活动/拿活动流量扶持"时，先用 `list-activities` 拿到活动名，再把该活动名通过 `--activity` 传给 upload-video

## 活动与标签使用约束

- 头条视频发布页当前没有活动入口（实测），不要传 `--activity`；活动功能目前仅快手支持
- 只参加与视频内容真实相关的活动，无关活动会被平台判定滥用反而限流
- `--extra-tag-pool <组名>` 追加 conf.py 里配置的固定标签组；**不传就不追加**
- `--declaration "AI生成"` 勾选"作品声明"区选项（AI生成/自行拍摄/引用内容等）；勾选失败时发布**终止**，不会静默发布
- 不要为了流量把无关热门标签堆给每个视频，平台对"滥用话题标签"有限流处罚

## 执行前检查

- 先确认当前 shell 里是否可以调用 `sau`
- 如果 `sau` 不可用，按 `references/runtime-requirements.md` 里的回退方式处理
- 当用户明确指定无头或有头模式时，显式传 `--headless` 或 `--headed`
- 只有用户明确要求定时发布时，才使用 `--schedule`
- 如果登录流程生成了本地二维码图片，不要只把图片路径告诉用户
- 二维码图片本身就是给用户扫码的，优先直接把本地图片展示/发送给用户

## 模板文件

当你需要稳定的命令模板时，使用 `scripts/examples/` 下的文件：

- `toutiao_commands.sh`
- `toutiao_commands.ps1`
- `toutiao_cli_template.py`

## 参考文档

- 运行前提：`references/runtime-requirements.md`
- CLI 契约：`references/cli-contract.md`
- 故障排查：`references/troubleshooting.md`
