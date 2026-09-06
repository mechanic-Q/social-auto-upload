#!/usr/bin/env bash
# 创作者数据中台 · 验收核验(验收#1/#5: 上线日起连续 N 天自动快照与日报)
# 用法: bash scripts/acceptance_check.sh [天数, 默认 3] [起始日, 默认 2026-09-07 上线日]
set -euo pipefail
cd "$(dirname "$0")/.."
DAYS="${1:-3}"
SINCE="${2:-2026-09-07}"

python3 - "$DAYS" "$SINCE" << 'EOF'
import sys
from datetime import date, timedelta

from collector.models import connect
from collector.paths import db_path, exports_dir

days = int(sys.argv[1])
since = date.fromisoformat(sys.argv[2])
window = [since + timedelta(offset) for offset in range(days)]

conn = connect(db_path(), read_only=True)
snap_days = {row["d"] for row in conn.execute(
    "SELECT DISTINCT date(started_at) AS d FROM collect_runs WHERE platform='bilibili' AND status='success'")}
report_days = {p.name[:-3] for p in (exports_dir() / "daily").glob("*.md")}
conn.close()

print(f"核验窗口: {window[0]} 起连续 {days} 天")
print(f"B站快照成功日: {sorted(snap_days)}")
print(f"日报落盘日:   {sorted(report_days)}")

ok = True
missing_snap = [str(d) for d in window if str(d) not in snap_days]
missing_report = [str(d) for d in window if str(d) not in report_days]

if missing_snap:
    ok = False
    print(f"✗ 缺快照日期: {missing_snap}")
else:
    print(f"✓ 快照连续 {days} 天齐备(验收#1)")
if missing_report:
    ok = False
    print(f"✗ 缺日报日期: {missing_report}")
else:
    print(f"✓ 日报连续 {days} 天齐备(验收#5)")

sys.exit(0 if ok else 1)
EOF
