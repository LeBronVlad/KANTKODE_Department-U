
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $ProjectRoot "config.json"
$Config = Get-Content -Raw -Encoding UTF8 $ConfigPath | ConvertFrom-Json

if (-not $Config.automation.enabled) {
    throw "Automation is disabled in config.json."
}

$TaskName = $Config.automation.task_name

$StartTime = [DateTime]::ParseExact(
    $Config.automation.start_time,
    "HH:mm",
    [Globalization.CultureInfo]::InvariantCulture
)

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = (Get-Command python -ErrorAction Stop).Source
}

$MainScript = Join-Path $ProjectRoot "main.py"
$Arguments = "`"$MainScript`" --api"

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument $Arguments `
    -WorkingDirectory $ProjectRoot

if ($Config.automation.schedule -ne "DAILY") {
    throw "Only DAILY schedule is supported."
}

$Trigger = New-ScheduledTaskTrigger -Daily -At $StartTime

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Vacancy analysis for region 39" `
    -Force | Out-Null

Write-Host "Task registered successfully: $TaskName" -ForegroundColor Green
Write-Host "Daily start time: $($Config.automation.start_time)"
