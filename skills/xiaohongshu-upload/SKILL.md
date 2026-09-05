---
name: xiaohongshu-upload
description: "【已停用】小红书通道因封号风险过高已关闭（2026-09-05 决定）：现有 patchright 浏览器自动化方式在该平台多次导致封号。不要调用 `sau xiaohongshu ...`（CLI 会拦截），除非用户明确要求恢复且已有更安全的发布方式。"
---

# 小红书上传 Skill（已停用）

> **⛔ 此通道已于 2026-09-05 停用。**
>
> 原因：现有 patchright 浏览器自动化方式在小红书平台存在较高封号风险，已实际多次触发。用户决定关闭，直到出现更安全的发布方式（如官方开放接口）。
>
> - 调用 `sau xiaohongshu ...` 会被 CLI 拦截并返回错误提示，这是预期行为
> - 恢复方式：将 `conf.py` 的 `XIAOHONGSHU_ENABLED` 改为 `True`
> - 不要绕过闸门直接调用 uploader 内部函数

## 历史文档（恢复时参考）

- CLI 契约：`references/cli-contract.md`
- 运行前提：`references/runtime-requirements.md`
- 故障排查：`references/troubleshooting.md`
- 命令模板：`scripts/examples/`
