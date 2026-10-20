# PQ-02: Star-Schema Warehouse

## 1. Objective

Build a separate DuckDB warehouse from the read-only PulseIQ source.

## 2. Architecture

- Source: `05_Starter/pulseiq.duckdb`
- Warehouse: `05_Starter/pulseiq_warehouse.duckdb`
- Source schema: `raw`
- Warehouse schema: `warehouse`
- Source database remains unchanged.

## 3. Validation Results

- 23 tables reconciled successfully.
- 25 relationship checks passed.
- 23 primary-key candidates passed validation.
- 23 primary-key constraints were added and verified.
- All 72 forecast date keys match the warehouse calendar.
- Calendar extended by 90 days, through 2027-03-31.

## 4. Known Exceptions

- Payroll `PI-X0003`: employee `EMP-9001`, employee key `-1`.
- Payroll `PI-X0004`: employee `EMP-9002`, employee key `-1`.
- 12 company-wide forecast records use department ID `ALL`.
- These records were retained rather than deleted or reassigned.

## 5. Calendar Notes

- Warehouse date rows: 2,647.
- Source date rows: 2,557.
- Generated holiday and working-day flags remain NULL because they were not verified.

## 6. Primary Keys

All 23 validated warehouse tables have primary-key constraints. `fact_headcount_monthly` uses the composite key `(date_key, department_id)`.

## 7. Completion Status

The documented PQ-02 integrity checks passed. Git status, commit, and pull-request steps must still be verified separately.
