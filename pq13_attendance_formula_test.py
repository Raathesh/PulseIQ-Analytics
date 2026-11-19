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

    print(f"\n{dept} | {month}")
    print("Reference comparison candidates:")
    print("Mean employee rate:", x["attendance_rate"].mean())
    print("Median employee rate:", x["attendance_rate"].median())
    print("Scheduled weighted rate:", np.average(
        x["attendance_rate"], weights=x["scheduled_days"]
    ))
    print("Present / scheduled:", (
        x["present_days"].sum() / x["scheduled_days"].sum()
    ))
    print("Employee records:", len(x))

