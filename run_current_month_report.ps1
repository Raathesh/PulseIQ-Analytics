$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Month = Get-Date -Format "yyyy-MM"

& (Join-Path $ProjectRoot "run_monthly_report.ps1") -Month $Month
if ($LASTEXITCODE -ne 0) {
    throw "Monthly report task failed."
}
