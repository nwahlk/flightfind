# Windows 任务计划配置脚本
# 以管理员权限运行此脚本

$TaskName = "FlightFind"
$ScriptPath = "python"
$Argument = "D:\workspace\flightfind\main.py"
$WorkingDir = "D:\workspace\flightfind"
$Description = "机票价格监控 - 每天8:00、12:00、18:00执行"

# 删除旧任务（如果存在）
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已删除旧任务" -ForegroundColor Yellow
} catch {}

# 创建触发器 - 每天3次
$trigger = New-ScheduledTaskTrigger -Daily -At "08:00", "12:00", "18:00"

# 创建执行动作
$action = New-ScheduledTaskAction -Execute $ScriptPath -Argument $Argument -WorkingDirectory $WorkingDir

# 设置任务
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description $Description

Write-Host "========================================" -ForegroundColor Green
Write-Host "任务创建成功！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "任务名称: $TaskName"
Write-Host "执行时间: 每天 08:00, 12:00, 18:00"
Write-Host ""
Write-Host "查看任务: Get-ScheduledTask -TaskName `"$TaskName`""
Write-Host "手动运行: Start-ScheduledTask -TaskName `"$TaskName`""
Write-Host "删除任务: Unregister-ScheduledTask -TaskName `"$TaskName`""
Write-Host ""
