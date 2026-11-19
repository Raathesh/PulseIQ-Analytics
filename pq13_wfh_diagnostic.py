import pandas as pd

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
    wfh = x["wfh_days"].sum()

    print(f"\n{dept} | {month}")
    print("Scheduled days:", scheduled)
    print("Present days:", present)
    print("WFH days:", wfh)
    print("Present / scheduled:", present / scheduled)
    print("Present + WFH / scheduled:", (present + wfh) / scheduled)
    print("Weighted attendance_rate:",
          (x["attendance_rate"] * x["scheduled_days"]).sum() / scheduled)

