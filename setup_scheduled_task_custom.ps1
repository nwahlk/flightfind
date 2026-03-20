# Windows 任务计划配置脚本（自定义版）
# 以管理员权限运行此脚本

# ============ 配置区 ============
$TaskName = "FlightFind"
$ScriptPath = "python"
$Argument = "D:\workspace\flightfind\main.py"
$WorkingDir = "D:\workspace\flightfind"
$Description = "机票价格监控"

# 执行时间列表（24小时制，格式 HH:mm）
# 示例：每天8:00、12:00、18:00、22:00执行
$ExecutionTimes = @("08:00", "12:00", "18:00", "22:00")
# ===============================

# 删除旧任务
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已删除旧任务" -ForegroundColor Yellow
} catch {}

# 创建触发器
$triggers = foreach ($time in $ExecutionTimes) {
    $hour, $minute = $time -split ':'
    New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval ([TimeSpan]::FromDays(1)) -RepetitionDur ([TimeSpan]::MaxValue) -At (Get-Date -Hour $hour -Minute $minute)
}

# 创建执行动作
$action = New-ScheduledTaskAction -Execute $ScriptPath -Argument $Argument -WorkingDirectory $WorkingDir

# 设置任务（使用最高延迟30分钟以避免冲突）
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -Description $Description

Write-Host "========================================" -ForegroundColor Green
Write-Host "任务创建成功！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "任务名称: $TaskName"
Write-Host "执行时间: $($ExecutionTimes -join ', ')"
Write-Host ""
Write-Host "常用命令:" -ForegroundColor Cyan
Write-Host "  查看任务: Get-ScheduledTask -TaskName `"$TaskName`""
Write-Host "  手动运行: Start-ScheduledTask -TaskName `"$TaskName`""
Write-Host "  查看历史: Get-ScheduledTaskInfo -TaskName `"$TaskName`""
Write-Host "  删除任务: Unregister-ScheduledTask -TaskName `"$TaskName`" -Confirm:`$false"
Write-Host ""
