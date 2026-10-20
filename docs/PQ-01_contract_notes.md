# PQ-01 — Initial Data Contract Notes

## Inspection status
The CSV files have been loaded into the DuckDB raw schema.
The data dictionary documents columns, expected data types,
descriptions, null counts, null percentages, and examples.

Important: data_contracts.csv explicitly contains contracts for
four feeds: fact_anomaly, fact_attrition_risk, fact_forecast,
and fact_task. It does not directly define column contracts for
the three tables below. Any additional rules must be documented
as proposed validation rules, not as source-provided contracts.

## 1. fact_payroll
- Observed columns: 34
- Key identifier: payroll_item_id
- Employee references: employee_id and employee_key
- Time references: date_key and period_end_date
- Financial fields include gross_pay, total_deductions,
  net_pay, employer_cost, and payroll components.
- Proposed checks: required identifiers, duplicate payroll item
  IDs, valid date keys, numeric values, and payroll arithmetic.
- Do not reject a row solely because variable_pay_type is blank:
  the dictionary reports 6,192 nulls (84.3%), which may be valid.

## 2. fact_attendance_monthly
- Observed columns: 16
- Key identifier: attendance_fact_id
- Employee references: employee_id and employee_key
- Time references: date_key and period_end_date
- Attendance measures include scheduled_days, present_days,
  paid_leave_days, unpaid_absence_days, and attendance_rate.
- Proposed checks: required identifiers, duplicate fact IDs,
  valid date keys, non-negative measures, and attendance-rate
  consistency with the documented formula.

## 3. dim_employee
- Observed columns: 21
- employee_key identifies a version of an employee record.
- employee_id identifies the employee across versions.
- valid_from and valid_to define the version validity period.
- is_current indicates the latest employee version.
- exit_date may be blank for active employees; the dictionary
  reports 1,036 nulls (64.5%).
- Proposed checks: unique employee_key, valid employment dates,
  allowed status/type/work-mode values, and manager references.
- Preserve employee history; do not assume employee_id is unique
  across all historical versions.

## Important validation policy
- Separate source-defined rules from proposed rules.
- Quarantine invalid records with a reason; do not silently drop them.
- Distinguish valid optional nulls from missing required values.
- Record input, passed, and quarantined row counts.
- Retain the original raw tables unchanged.


## fact_attrition_risk — Validation evidence

- Total input records: 430
- Missing required fields: 0
- Duplicate prediction IDs: 0
- Invalid prediction ID formats: 0
- Risk scores outside 0–1: 0
- Invalid risk-band values: 0
- Missing department references: 0
- Missing employee references: 0
- Missing employee-history version on prediction date: 0
- Predictions for inactive employees: 0
- Missing optional reason fields: 0
- Distinct prediction dates: 2
- Contract finding: as_of_date must be constant across a batch,
  but five records use 2026-03-31 and 425 use 2026-09-30.
- Risk-band finding: score 0.127 occurs in both Low and Medium
  bands across 13 records; percentile assignment requires investigation.
- Model version: attrition-logreg-baseline-0.1 (430 records)
- Raw source data modified: No

Status: Initial validation checks completed. The date contract
violation and percentile-band assignment remain unresolved.
These findings do not authorize deleting or quarantining records.


## fact_forecast — Validation evidence

- Total input records: 72
- Contract fields checked: 9
- Missing required fields: 0
- Duplicate forecast IDs: 0
- Invalid FC-nnnn ID formats: 0
- Invalid metric values: 0
- Invalid department references: 0
- Forecast months not on the first day of the month: 0
- Negative forecast values: 0
- Invalid lower confidence bounds: 0
- Invalid upper confidence bounds: 0
- Invalid trained_through formats: 0
- Duplicate metric/department/month combinations: 0
- Training cut-off: 2026-09 for all 72 records
- Forecast period: October 2026 through March 2027
- Additional physical columns: model_version, forecast_month_key
- Raw source data modified: No

Status: All checked contract rules passed. Additional physical
columns were observed and have not been treated as violations.


## fact_task — Validation Evidence

Validation performed against `raw.fact_task` and its reference tables.
Raw source data was not modified.

- Total records checked: 28,868.
- Task IDs: 28,868 distinct IDs; all match `TASK-` followed by five digits.
- Required fields: no missing mandatory values in the checked fields.
- Allowed values: priority, story points, status, and task type passed.
- Reopened count: no invalid negative or missing values.
- References: no unmatched employee, team, or sprint IDs.
- Sprint due-date rule: zero mismatches.
- Created date after started date: zero violations.
- Started date missing outside `To Do`: zero violations.
- Due date before started date: zero cases in the plausibility check.
- `Done` tasks missing completed date: 8 records require investigation.
- Completed date earlier than started date: 12 records require investigation.
- Additional physical columns: `cycle_time_days`, `is_overdue_at_cutoff`,
  and `completed_on_time`. These are not listed as contract fields.

The 8 missing completion dates and 12 date-order violations must be handled
by the validation/quarantine process. No source records were changed.


## Payroll ETL — Execution and Test Evidence

- Script: `src/etl_v2.py`
- Source: `raw.fact_payroll` and `raw.dim_employee`
- Source connection: DuckDB read-only mode.
- Input rows: 7344.
- Passed rows: 7340.
- Quarantined rows: 4.
- Reconciliation passed: True.
- Quarantine reasons: {"DUPLICATE_EMPLOYEE_RUN": 2, "UNMATCHED_EMPLOYEE_KEY": 2}.
- Output files: `fact_payroll_passed.csv`,
  `fact_payroll_quarantine.csv`, and `fact_payroll_summary.json`.
- Repeatability: two consecutive executions produced identical
  output-file SHA-256 fingerprints.
- Source row-count checks after execution:
  `raw.fact_payroll` = 7,344 and `raw.dim_employee` = 1,606.
- Limitation: matching row counts do not establish full row-level
  source immutability. No intentional writes to raw tables were performed.

The original `src/etl.py` prototype remains unchanged. The replacement
prototype is `src/etl_v2.py`.


## Fact Anomaly — Validation Evidence

- Input records: 405.
- Unique result IDs: 405; duplicate result-ID rows: 0.
- Missing required fields in the checks performed: 0.
- Invalid anomaly scores outside 0–1: 0.
- Invalid flag values: 0; all 405 records have flag Y.
- Invalid source-dataset values: 0.
- Unmatched employee IDs: 0.
- Payroll anomalies: 184/184 matched directly by payroll item ID.
- Attendance anomalies: 221/221 matched uniquely by employee and calendar month.
- Duplicate source/employee/period combinations: 0.
- Missing or blank reason text: 0.
- Missing scoring timestamps: 0; all 405 share timestamp
  2026-10-01 02:00:00.
- Negative money-at-risk values: 0 in the checks performed.
- Raw source data was not intentionally modified.

### Outstanding Contract Questions

1. The complete published reason-code allowlist was not found in the
   inspected contract, dictionary, or DQ catalog sources.
2. The model-version values are
   `iforest-attendance-0.1` and `iforest-payroll-0.1`.
   Their compliance with the intended semantic-version convention needs
   clarification; failure of a strict numeric SemVer pattern alone is
   not proof of invalidity.
3. The scoring timestamp is timezone-naive in the database, so UTC
   cannot be independently verified from the stored value.

These findings cover the checks listed above; they do not establish
that every anomaly contract requirement has passed. No records should
be quarantined solely because these reference questions remain unresolved.


## Fact Attrition Risk — Validation Evidence

- Input records: 430; unique prediction IDs: 430.
- Missing required fields in the checks performed: 0.
- Invalid prediction ID formats: 0.
- Invalid risk scores outside 0–1: 0.
- Invalid risk-band values: 0.
- Unmatched employee or department IDs in the checks performed: 0.
- As-of-date distribution: 5 records dated 2026-03-31 and
  425 records dated 2026-09-30.
- Two March records reference an employee key that differs from
  the employee version valid on their as-of date.
- September risk-band counts: High 43 (10.12%), Medium 86 (20.24%),
  Low 296 (69.65%).
- The score 0.127 occurs in both Medium and Low bands. The
  percentile and tie-handling method remains unresolved.
- Raw source data was not intentionally modified.

### Outstanding Contract Questions

1. The contract requires the same as-of date for the whole batch.
   The five March records conflict with the 425 September records.
2. Two March records have employee keys inconsistent with the
   historical employee version valid on their as-of date.
3. The tie-handling rule for risk-band percentile assignment is
   not documented in the inspected sources.

These findings cover the checks listed above; they do not establish
that every attrition contract requirement has passed.
