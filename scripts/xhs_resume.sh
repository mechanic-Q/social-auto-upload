#!/usr/bin/env bash
# 小红书数据采集恢复(验收#2 收尾): 扫码登录 → probe 采样 → 提示校准
# 用法: bash scripts/xhs_resume.sh
# 流程: 启动后弹出二维码(约 5 分钟内有效, 过期会自动刷新一到两轮),
#       用小红书 APP 扫码; 登录成功后自动跑 probe 收集真实接口样本。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── 步骤 1/2: 扫码登录(请用小红书 APP 扫屏幕上的二维码) ──"
python3 sau_cli.py xiaohongshu login --account diyi

# 登录脚本成功返回即 cookie 已写入
echo
echo "── 步骤 2/2: probe 采集真实接口样本 ──"
python3 sau_cli.py stats collect --probe --only xiaohongshu

echo
echo "✅ 样本已存 E:\\social_data\\raw\\xiaohongshu\\"
echo "→ 叫助手按样本校准 parse_note_payloads 候选键, 然后跑全量:"
echo "  sau stats collect --full --only xiaohongshu"
