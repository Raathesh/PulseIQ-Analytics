
import pandas as pd
import numpy as np
from pathlib import Path

# ==========================================
# PQ-13 | Reference Validation Diagnostics
# ==========================================

PROCESSED = Path("03_Data/processed")

actual = pd.read_csv(
    PROCESSED / "pq13_department_month.csv"
)

reference = pd.read_csv(
    "04_Validation_Vault/unlock_PQ-13_reference_summary_dept_month.csv"
)

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
    how="inner",
    suffixes=("_actual", "_ref"),
    validate="one_to_one"
)

def inspect(label, actual_col, reference_col, tolerance=1e-6):

    a = merged[actual_col].astype(float)
    b = merged[reference_col].astype(float)

    valid = a.notna() & b.notna()

    matches = np.isclose(
        a, b,
        rtol=1e-8,
        atol=tolerance
    )

    print(f"\n========== {label} ==========")
    print("Comparable:", int(valid.sum()))
    print("Matches:", int((matches & valid).sum()))
    print("Mismatches:", int((~matches & valid).sum()))

    columns = [
        "department_id", "month",
        actual_col, reference_col
    ]

    print("\nFirst 12 comparable rows:")
    print(
        merged.loc[valid, columns]
        .head(12).to_string(index=False)
    )

    print("\nFirst 15 mismatches:")
    print(
        merged.loc[valid & ~matches, columns]
        .head(15).to_string(index=False)
    )


# Attendance: compare to four-decimal reference precision.
inspect(
    "ATTENDANCE RATE",
    "attendance_rate_weighted",
    "attendance_rate",
    tolerance=0.00005
)

# Task completion: both columns receive suffixes after merge.
inspect(
    "TASK COMPLETION RATE",
    "task_completion_rate_pct_actual",
    "task_completion_rate_pct_ref",
    tolerance=0.05
)

# Check whether the task reference uses a 0-1 scale.
a = merged["task_completion_rate_pct_actual"].astype(float)
b = merged["task_completion_rate_pct_ref"].astype(float)

valid = a.notna() & b.notna()

print("\n========== TASK RATE SCALE CHECK ==========")

print(
    "Reference divided by 100:",
    int(np.isclose(
        a[valid], b[valid] / 100, atol=0.01
    ).sum()),
    "/", int(valid.sum())
)

print(
    "Actual divided by 100:",
    int(np.isclose(
        a[valid] / 100, b[valid], atol=0.01
    ).sum()),
    "/", int(valid.sum())
)

print("\n========== DIAGNOSTICS COMPLETE ==========")
