import pandas as pd
import numpy as np

df = pd.read_csv("03_Data/csv/fact_attendance_monthly.csv")

df["month"] = (
    pd.to_datetime(df["period_end_date"])
    .dt.to_period("M").astype(str)
)

targets = [
    ("D04", "2025-12"),
    ("D01", "2026-03"),
    ("D04", "2026-03")
]

for dept, month in targets:
    x = df[
        (df["department_id"] == dept)
        & (df["month"] == month)
    ]

    scheduled = x["scheduled_days"].sum()
    present = x["present_days"].sum()
    paid = x["paid_leave_days"].sum()
    unpaid = x["unpaid_absence_days"].sum()
    wfh = x["wfh_days"].sum()

    print(f"\n========== {dept} | {month} ==========")
    print("Scheduled days:", scheduled)
    print("Present days:", present)
    print("Paid leave days:", paid)
    print("Unpaid absence days:", unpaid)
    print("WFH days:", wfh)

    print("\nCandidate calculations:")
    print("Present / scheduled:", present / scheduled)
    print("(Present + paid leave) / scheduled:",
          (present + paid) / scheduled)
    print("(Scheduled - unpaid absence) / scheduled:",
          (scheduled - unpaid) / scheduled)

    print("\nReference:")
    ref = pd.read_csv(
        "04_Validation_Vault/unlock_PQ-13_reference_summary_dept_month.csv"
    )
    value = ref.loc[
        (ref["department_id"] == dept)
        & (pd.to_datetime(ref["month"]).dt.to_period("M").astype(str) == month),
        "attendance_rate"
    ].iloc[0]
    print(value)

