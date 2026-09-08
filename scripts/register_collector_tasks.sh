#!/usr/bin/env bash
# 从 WSL 侧注册 Windows 任务计划(自动探测 distro 与 Windows 路径后调 PowerShell)。
# 用法: bash scripts/register_collector_tasks.sh
set -euo pipefail

DISTRO="${WSL_DISTRO_NAME:-}"
if [[ -z "$DISTRO" ]]; then
  DISTRO=$(wsl.exe -l --quiet 2>/dev/null | tr -d '\0\r' | head -1)
fi
if [[ -z "$DISTRO" ]]; then
  echo "无法确定 WSL distro 名,请设置 WSL_DISTRO_NAME 后重试" >&2
  exit 1
fi

PROJECT_WIN=$(wslpath -w "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)")
echo "distro=$DISTRO project=$PROJECT_WIN"

/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile \
  -ExecutionPolicy Bypass -File "$(wslpath -w "$(dirname "${BASH_SOURCE[0]}")")/register_collector_tasks.ps1" \
  -Distro "$DISTRO" -ProjectWin "$PROJECT_WIN"
