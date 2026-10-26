# PQ-03 — Data Quality Gatekeeper Report

**Project:** PulseIQ Analytics
**Notebook:** `PQ-03_Data_Quality_Gatekeeper.ipynb`
**Report status:** Partial implementation; final end-to-end notebook review remains pending.

## 1. Objective

Implement SQL-based data-quality checks, persist a results summary, test checks against known planted issues, and assess minimum-group-size suppression rules.

## 2. Quality-check results

The saved `warehouse.dq_results` table contains 14 checks.

| Status | Count | Interpretation |
|---|---:|---|
| PASS | 1 | No ledger-balancing exceptions were returned |
| FAIL | 11 | Implemented checks detected data-quality exceptions |
| BLOCKED | 1 | Pipeline freshness cannot be established from a successful upstream-load record |
| PARTIAL | 1 | Minimum-group-size privacy review is not yet complete |

The 11 FAIL statuses represent detected exceptions in the current dataset; they do not by themselves mean the SQL checks failed to execute.

### Saved check summary

| Check ID | Check | Severity | Status | Failing rows |
|---|---|---|---|---:|
| DQ-C01 | Payroll equals ledger | Critical | FAIL | 5 |
| DQ-C02 | Ledger balanced | Critical | PASS | 0 |
| DQ-C03 | Unique payroll rows | Critical | FAIL | 2 |
| DQ-C04 | No orphan employees | Critical | FAIL | 2 |
| DQ-C05 | No attendance after exit | Warning | FAIL | 4 |
| DQ-C06 | Unpaid leave deducted | Warning | FAIL | 48 |
| DQ-C07 | Invoice arithmetic | Warning | FAIL | 1 |
| DQ-C08 | Expense arithmetic | Warning | FAIL | 1 |
| DQ-C09 | Task dates sensible | Warning | FAIL | 20 |
| DQ-C10 | Leave dates sensible | Warning | FAIL | 2 |
| DQ-C11 | AI feeds are fresh | Warning | FAIL | 5 |
| DQ-C12 | Dimension history does not overlap | Critical | FAIL | 1 |
| DQ-C13 | Pipeline freshness | Critical | BLOCKED | Not determined |
| DQ-C14 | Minimum group size | Critical | PARTIAL | Not determined |

**DQ-C13 note:** The recorded quality-gate execution ended with status `FAILED`. A quality-check run is not evidence of a successful upstream data load, so it must not be used to claim load freshness. C13 remains BLOCKED because no successful upstream-load run is recorded.

## 3. Planted-issue coverage

The saved file `04_Validation_Vault/PQ-03_planted_issue_coverage.csv` reports all 11 planted issue types as detected.

| Coverage measure | Result |
|---|---:|
| Planted issue types | 11 |
| Expected records | 40 |
| Detected records | 40 |
| Missed records | 0 |
| Issue types passing | 11 of 11 |

| Issue ID | Issue type | Expected | Detected | Missed | Status |
|---|---|---:|---:|---:|---|
| DQ-01 | ATTENDANCE_AFTER_EXIT | 4 | 4 | 0 | PASS |
| DQ-02 | DUPLICATE_PAYROLL_ROW | 2 | 2 | 0 | PASS |
| DQ-03 | ORPHAN_FOREIGN_KEY | 2 | 2 | 0 | PASS |
| DQ-04 | PAYROLL_LEDGER_MISMATCH | 2 | 2 | 0 | PASS |
| DQ-05 | OVERPAID_INVOICE | 1 | 1 | 0 | PASS |
| DQ-06 | COMPLETED_BEFORE_STARTED | 12 | 12 | 0 | PASS |
| DQ-07 | DONE_WITHOUT_DATE | 8 | 8 | 0 | PASS |
| DQ-08 | END_BEFORE_START | 2 | 2 | 0 | PASS |
| DQ-09 | STALE_PREDICTION | 5 | 5 | 0 | PASS |
| DQ-10 | TOTAL_MISMATCH | 1 | 1 | 0 | PASS |
| DQ-11 | SCD_INTERVAL_OVERLAP | 1 | 1 | 0 | PASS |

This demonstrates detection of the known planted cases. It does not prove detection of every possible data-quality issue.

## 4. Minimum group size and privacy review (DQ-C14)

The source metric catalog has 28 metrics:
- 19 have a defined `minimum_group_size`.
- 9 do not have a defined minimum group size: M16–M21, M24, M26, and M28.

No threshold should be invented for metrics where the catalog does not define one. Those entries should be documented as catalog gaps and assigned an owner for policy clarification.

### Workforce metrics M01–M06

M01–M04 were evaluated at department-month grain. For M05 and M06, rolling 12-month calculations were corrected to use the **unrounded** rolling average headcount and to suppress incomplete windows.

| M05/M06 measure | Count per metric |
|---|---:|
| Department-month groups | 891 |
| Complete 12-month windows | 770 |
| Incomplete windows | 121 |
| RELEASE | 539 |
| SUPPRESS | 352 |

The 352 suppressed groups consist of 121 incomplete windows and 231 complete windows whose rolling average headcount is below 10. Validation confirmed that suppressed M05/M06 metric values were hidden.

### Payroll metrics M07–M12 and M15

Payroll measures were checked using department-month as the privacy-safe reporting grain, while the source catalog's original grain is retained in documentation. Do not interpret these department-month checks as changing the source catalog's metric definitions.

- M10 cost-per-head, M11 overtime share, and M12 variable-pay share: 198 department-month groups; 180 RELEASE and 18 SUPPRESS.
- M10–M12 formula validation: zero formula errors for all three measures.
- Suppressed M10–M12 metric values were hidden.
- M07–M09 and M15 reconciliation: all 198 department-month groups matched the independent recalculation; no differences were found in gross pay, net pay, employer cost, LOP days, or employee counts.

These results validate the calculations and the reporting-grain reconciliation performed in this notebook; they do not establish that all upstream financial reconciliation exceptions have been resolved.

### Attendance, task, and attrition-risk metrics

- M13–M14 attendance metrics were calculated and privacy-checked at department-month grain.
- M22, M23, and M25 task metrics were calculated at team-sprint grain. M23 uses completion dates and excludes tasks missing completion dates from the date-based denominator. Task data includes 8 Done tasks without completion dates and 12 negative cycle-time records; these exceptions require transparent reporting.
- M27 high-risk share was calculated by department using the latest prediction per employee. The source metric's caveat prohibits ranking named individuals.

### DQ-C14 conclusion

C14 remains **PARTIAL**. Although metric calculations and suppression behavior have been tested across the listed metric families, the final evidence consolidation, metric-specific policy review, and handling of nine catalog entries without defined thresholds remain outstanding. The saved `failing_rows` field is NULL because the old value (18) represented the prior headcount suppression count, not a count of failed privacy checks.

## 5. Known limitations and follow-up actions

1. **C13 — Pipeline freshness:** Integrate the freshness check with genuine upstream-load completion metadata. Do not treat a PQ-03 quality-check execution as a successful data load.
2. **C14 — Privacy policy:** Assign an owner to define minimum-group-size rules for M16–M21, M24, M26, and M28. Do not invent thresholds.
3. **C14 — Final evidence consolidation:** Verify each metric's formula, grain, threshold interpretation, suppression behavior, and saved evidence in a single repeatable report.
4. **Task metrics:** Document the 8 Done tasks missing completion dates and 12 negative cycle-time records; ensure M23 denominator policy is explicit.
5. **End-to-end reproducibility:** Restart the notebook kernel and run the notebook from top to bottom. Confirm it recreates the check results, coverage output, and saved `warehouse.dq_results` without relying on stale in-memory variables.
6. **Pipeline gate:** Implement and test the requested fail-on-critical-check behavior only after defining the intended critical-check policy and expected treatment of known planted issues.
7. **Git hygiene:** Review the working tree and stage only the intended PQ-03 report/notebook changes. Do not stage, reset, or modify the pre-existing `PQ-01_ETL_Validation.ipynb` change, and do not modify PQ-02 artifacts.

## 6. Overall conclusion

PQ-03 has a functioning SQL check suite with persisted results and complete detection of the 11 known planted issue types in the saved coverage report. It is **not yet complete as a production-ready gate**: C13 is BLOCKED and C14 is PARTIAL. The remaining work is to finish privacy-policy/evidence consolidation, connect freshness to real upstream-load metadata, and validate a clean end-to-end notebook run.
