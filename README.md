# PulseIQ Analytics

## Overview
PulseIQ Analytics is a workforce analytics project using Python, DuckDB, Streamlit and Plotly.

## Requirements
- Windows 10/11
- Python 3.10 or later
- Authorized local PulseIQ warehouse and datasets

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Local data prerequisites
Private datasets, validation answer materials and the DuckDB warehouse are not included in this repository.
Required local files: 05_Starter/pulseiq_warehouse.duckdb, 03_Data/csv/kpi_targets.csv, 03_Data/csv/fact_forecast.csv.

## Monthly PDF report
```powershell
.\run_monthly_report.ps1 -Month 2026-09
.\run_current_month_report.ps1
```

Reports are saved in outputs/.

## Project files
- build_report.py: monthly PDF generator
- run_monthly_report.ps1: specified-month runner
- run_current_month_report.ps1: current-month runner
- src/: ETL and analytics components
- pq11_dashboard.py to pq15_dashboard.py: dashboards

## Data and privacy
Do not commit private datasets, database files, validation answer keys, credentials, virtual environments or generated local reports.
