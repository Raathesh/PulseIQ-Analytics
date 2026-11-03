import pandas as pd
import numpy as np

attendance = pd.read_csv("03_Data/csv/fact_attendance_monthly.csv")
reference = pd.read_csv(
    "04_Validation_Vault/unlock_PQ-13_reference_summary_dept_month.csv"
)

attendance["month"] = (
    pd.to_datetime(attendance["period_end_date"])
    .dt.to_period("M").astype(str)
)

reference["month"] = (
    pd.to_datetime(reference["month"])
    .dt.to_period("M").astype(str)
)

targets = [
    ("D04", "2025-12"),
    ("D01", "2026-03"),
    ("D04", "2026-03")
]

for department, month in targets:
    source = attendance[
        (attendance["department_id"] == department)
        & (attendance["month"] == month)
    ]

    ref = reference[
        (reference["department_id"] == department)
        & (reference["month"] == month)
    ]

    print(f"\n========== {department} | {month} ==========")
    print("Source employee records:", len(source))

    if source.empty or ref.empty:
        print("Missing source or reference records")
        continue

    scheduled = source["scheduled_days"].sum()
    present = source["present_days"].sum()

    weighted = np.average(
        source["attendance_rate"],
        weights=source["scheduled_days"]
    )

    print("Scheduled days:", scheduled)
    print("Present days:", present)
    print("Present / scheduled:", present / scheduled)
    print("Weighted source attendance rate:", weighted)
    print("Unweighted source attendance rate:", source["attendance_rate"].mean())
    print("Reference attendance rate:", ref["attendance_rate"].iloc[0])

    print("\nSource records:")
    print(
        source[
            [
                "employee_id", "scheduled_days",
                "present_days", "attendance_rate"
            ]
        ].to_string(index=False)
    )

print("\n========== ATTENDANCE SOURCE AUDIT COMPLETE ==========")
