param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^\d{4}-(0[1-9]|1[0-2])$')]
    [string]$Month
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
    throw "Virtual environment not found. Create it with: python -m venv .venv; then install requirements.txt."
}

$Builder = Join-Path $ProjectRoot "build_report.py"
if (!(Test-Path $Builder)) {
    throw "build_report.py was not found."
}

$Database = Join-Path $ProjectRoot "05_Starter\pulseiq_warehouse.duckdb"
$Targets = Join-Path $ProjectRoot "03_Data\csv\kpi_targets.csv"
$Forecast = Join-Path $ProjectRoot "03_Data\csv\fact_forecast.csv"

foreach ($RequiredFile in @($Database, $Targets, $Forecast)) {
    if (!(Test-Path $RequiredFile)) {
        throw "Required local data file is missing: $RequiredFile. These data files are not included in the Git repository."
    }
}

Write-Host "Generating PulseIQ report for $Month..."
& $Python $Builder --month $Month

if ($LASTEXITCODE -ne 0) {
    throw "Report generation failed."
}

$Report = Join-Path $ProjectRoot "outputs\monthly_report_$Month.pdf"
if (Test-Path $Report) {
    Write-Host "SUCCESS: $Report"
} else {
    throw "Report file was not found."
}
