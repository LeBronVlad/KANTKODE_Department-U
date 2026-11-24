$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Config = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "config.json") | ConvertFrom-Json
Unregister-ScheduledTask -TaskName $Config.automation.task_name -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Задача планировщика удалена (если существовала)." -ForegroundColor Yellow
