import pandas as pd
import numpy as np
from pathlib import Path

processed = Path("03_Data/processed")
reference_file = Path(
    "04_Validation_Vault/unlock_PQ-13_reference_summary_dept_month.csv"
)

actual = pd.read_csv(processed / "pq13_department_month.csv")
reference = pd.read_csv(reference_file)

actual["month"] = (
    pd.to_datetime(actual["month_start_date"])
    .dt.to_period("M").astype(str)
)
reference["month"] = (
    pd.to_datetime(reference["month"])
    .dt.to_period("M").astype(str)
)

merged = actual.merge(
    reference,
    on=["department_id", "month"],
    how="outer",
    suffixes=("_actual", "_ref"),
    indicator=True
)

checks = {
    "Employer cost": ("employer_cost", "employer_cost", 0.01),
    "Gross pay": ("payroll_gross_pay", "gross_pay", 0.01),
    "Overtime cost": ("overtime_cost", "overtime_pay", 0.01),
    "Employees paid": ("payroll_employee_count", "employees_paid", 0),
    "Overtime hours": ("overtime_hours_paid", "overtime_hours", 0.01),
    "Late arrivals": ("late_arrivals", "late_arrivals", 0),
    "Attendance rate": ("attendance_rate_weighted", "attendance_rate", 0.00005),
    "Ending headcount": ("headcount_end", "headcount_end", 0),
    "Hires": ("hires", "hires", 0),
    "Exits": ("exits", "exits", 0),
    "Attrition rate": ("attrition_rate_monthly_pct", "attrition_rate_monthly_pct", 0.0001),
    "Tasks": ("tasks", "tasks", 0),
    "Tasks completed": ("tasks_done", "tasks_done", 0),
    "Story points completed": ("story_points_done", "story_points_done", 0),
    "Task completion rate": ("task_completion_rate_pct", "task_completion_rate_pct", 0.05),
}

print("\n========== PQ-13 FULL REFERENCE VALIDATION ==========")
print("Actual rows:", len(actual))
print("Reference rows:", len(reference))
print("Merged rows:", len(merged))
print("Department-month key matches:", (merged["_merge"] == "both").sum())

summary = []
mismatch_details = []

for label, (actual_col, ref_col, tolerance) in checks.items():

    actual_name = (
        f"{actual_col}_actual"
        if f"{actual_col}_actual" in merged.columns
        else actual_col
    )

    ref_name = (
        f"{ref_col}_ref"
        if f"{ref_col}_ref" in merged.columns
        else ref_col
    )

    a = pd.to_numeric(merged[actual_name], errors="coerce")
    b = pd.to_numeric(merged[ref_name], errors="coerce")

    comparable = a.notna() & b.notna()

    matches = np.isclose(
        a[comparable],
        b[comparable],
        rtol=1e-8,
        atol=tolerance
    )

    matched = int(matches.sum())
    mismatched = int((~matches).sum())

    summary.append({
        "metric": label,
        "tolerance": tolerance,
        "comparable_rows": int(comparable.sum()),
        "matches": matched,
        "mismatches": mismatched
    })

    print(
        f"{label}: {matched}/{int(comparable.sum())} matches; "
        f"{mismatched} mismatches"
    )

    failed_indices = comparable[comparable].index[~matches]

    for idx in failed_indices:
        mismatch_details.append({
            "metric": label,
            "department_id": merged.loc[idx, "department_id"],
            "month": merged.loc[idx, "month"],
            "actual_value": a.loc[idx],
            "reference_value": b.loc[idx],
            "difference": a.loc[idx] - b.loc[idx],
            "tolerance": tolerance
        })

validation = pd.DataFrame(summary)
validation.to_csv(
    processed / "pq13_reference_validation_summary.csv",
    index=False
)

mismatches = pd.DataFrame(mismatch_details)
mismatches.to_csv(
    processed / "pq13_reference_validation_mismatches.csv",
    index=False
)

print("\nSaved:")
print("pq13_reference_validation_summary.csv")
print("pq13_reference_validation_mismatches.csv")

print("\nTotal mismatches:", len(mismatches))

if not mismatches.empty:
    print("\n========== MISMATCH DETAILS ==========")
    print(mismatches.to_string(index=False))

print("\n========== VALIDATION COMPLETE ==========")
