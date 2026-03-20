# FlightFind Scheduled Task Setup
# Run as Administrator

$TaskName = "FlightFind"
$ScriptPath = "python"
$Argument = "D:\workspace\flightfind\main.py"
$WorkingDir = "D:\workspace\flightfind"
$Description = "Flight price monitoring - runs at 8:00, 12:00, 18:00 daily"

# Remove old task
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

# Create 3 separate triggers
$trigger1 = New-ScheduledTaskTrigger -Daily -At "08:00"
$trigger2 = New-ScheduledTaskTrigger -Daily -At "12:00"
$trigger3 = New-ScheduledTaskTrigger -Daily -At "18:00"

# Create action
$action = New-ScheduledTaskAction -Execute $ScriptPath -Argument $Argument -WorkingDirectory $WorkingDir

# Register task with multiple triggers
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger1,$trigger2,$trigger3 -Description $Description

Write-Host "========================================" -ForegroundColor Green
Write-Host "Task created successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Task Name: $TaskName"
Write-Host "Schedule: Daily at 08:00, 12:00, 18:00"
Write-Host ""
Write-Host "Commands:" -ForegroundColor Cyan
Write-Host "  View task: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Run now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Delete task: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
