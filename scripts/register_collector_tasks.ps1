# 注册 Windows 任务计划:创作者数据中台采集器(ADR/计划见 docs/data-collector-plan.md)
# - sau-collector-full:      每日 09:30 全量采集;错过(未开机)由 StartWhenAvailable 开机补跑
# - sau-collector-incremental: 09:00-23:00 每 30 分钟检查到期发布事件,无事件时秒退
# 由 scripts/register_collector_tasks.sh 从 WSL 侧调用,distro 与项目路径自动探测。
param(
    [Parameter(Mandatory = $true)][string]$Distro,
    [Parameter(Mandatory = $true)][string]$ProjectWin
)

$ErrorActionPreference = "Stop"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$wslArgs = "-d $Distro --cd `"$ProjectWin`" -- python3 sau_cli.py stats collect --full"
$fullAction = New-ScheduledTaskAction -Execute "wsl.exe" -Argument $wslArgs
$fullTrigger = New-ScheduledTaskTrigger -Daily -At 09:30
Register-ScheduledTask -TaskName "sau-collector-full" `
    -Description "social-auto-upload 创作者数据全量采集(每日 09:30)" `
    -Action $fullAction -Trigger $fullTrigger -Settings $settings -Force | Out-Null
Write-Host "[OK] sau-collector-full 已注册(每日 09:30,开机补跑)"

# 每 30 分钟的增量消费:从 09:00 起每 30 分钟一次,持续 14 小时(覆盖 09:00-23:00)
$incArgs = "-d $Distro --cd `"$ProjectWin`" -- python3 sau_cli.py stats collect --incremental"
$incAction = New-ScheduledTaskAction -Execute "wsl.exe" -Argument $incArgs
$incTrigger = New-ScheduledTaskTrigger -Once -At "09:00" `
    -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 14)
Register-ScheduledTask -TaskName "sau-collector-incremental" `
    -Description "social-auto-upload 发布后增量采集(消费到期发布事件)" `
    -Action $incAction -Trigger $incTrigger -Settings $settings -Force | Out-Null
Write-Host "[OK] sau-collector-incremental 已注册(09:00-23:00 每 30 分钟)"

Get-ScheduledTask -TaskName "sau-collector-*" | Format-Table TaskName, State
