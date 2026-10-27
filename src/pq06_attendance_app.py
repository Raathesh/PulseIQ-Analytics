from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

# PQ-06 Attendance & Leave Trends
# Run from repository root:
#   .\.venv\Scripts\python.exe -m streamlit run src\pq06_attendance_app.py

st.set_page_config(page_title="PQ-06 | Attendance & Leave", page_icon="ðŸ“Š", layout="wide")

DATA_DIR = Path(__file__).resolve().parents[1] / "03_Data" / "csv"

@st.cache_data
def load_data():
    attendance = pd.read_csv(DATA_DIR / "fact_attendance_monthly.csv")
    leave = pd.read_csv(DATA_DIR / "fact_leave.csv")
    calendar = pd.read_csv(DATA_DIR / "dim_date.csv")
    departments = pd.read_csv(DATA_DIR / "dim_department.csv")
    leave_types = pd.read_csv(DATA_DIR / "dim_leave_type.csv")

    attendance["period_end_date"] = pd.to_datetime(attendance["period_end_date"], errors="coerce")
    attendance["month"] = attendance["period_end_date"].dt.to_period("M").astype(str)
    attendance["department_id"] = attendance["department_id"].astype(str)
    departments["department_id"] = departments["department_id"].astype(str)

    calendar["date"] = pd.to_datetime(calendar["date"], errors="coerce")
    calendar["month"] = calendar["date"].dt.to_period("M").astype(str)
    for col in ["is_holiday", "is_weekend", "is_working_day"]:
        calendar[col] = calendar[col].astype(str).str.strip().str.upper()

    leave["start_date"] = pd.to_datetime(leave["start_date"], errors="coerce")
    leave["end_date"] = pd.to_datetime(leave["end_date"], errors="coerce")
    leave["days"] = pd.to_numeric(leave["days"], errors="coerce").fillna(0)
    leave["month"] = leave["start_date"].dt.to_period("M").astype(str)
    leave["employee_key"] = leave["employee_key"].astype(str)

    # Allocate approved leave across calendar months using working dates.
    # Because source leave days are request-level totals, allocation assumes
    # leave days are spread evenly across working dates in the request interval.
    cal_work = calendar.loc[calendar["is_working_day"].eq("Y"), ["date", "month"]].copy()
    work_dates = set(cal_work["date"].dropna())
    month_lookup = cal_work.set_index("date")["month"].to_dict()
    allocations = []
    approved = leave.loc[leave["status"].astype(str).str.strip().str.lower().eq("approved")].copy()
    for row in approved.itertuples(index=False):
        if pd.isna(row.start_date) or pd.isna(row.end_date) or row.end_date < row.start_date:
            continue
        eligible = [d for d in pd.date_range(row.start_date.normalize(), row.end_date.normalize(), freq="D") if d in work_dates]
        if not eligible:
            # Preserve visibility of approved records that do not intersect calendar working dates.
            allocations.append({"month": row.start_date.to_period("M").strftime("%Y-%m"),
                                "leave_type_code": row.leave_type_code, "days": float(row.days),
                                "employee_id": row.employee_id, "allocation_note": "No calendar working dates in interval"})
            continue
        daily_amount = float(row.days) / len(eligible)
        per_month = {}
        for d in eligible:
            m = month_lookup[d]
            per_month[m] = per_month.get(m, 0.0) + daily_amount
        for m, amount in per_month.items():
            allocations.append({"month": m, "leave_type_code": row.leave_type_code,
                                "days": amount, "employee_id": row.employee_id,
                                "allocation_note": "Allocated across working dates"})
    leave_monthly = pd.DataFrame(allocations, columns=["month", "leave_type_code", "days", "employee_id", "allocation_note"])
    leave_monthly = leave_monthly.merge(leave_types[["leave_type_code", "leave_type_name"]], on="leave_type_code", how="left")
    return attendance, leave, calendar, departments, leave_monthly

attendance, leave, calendar, departments, leave_monthly = load_data()

st.title("Attendance & Leave Trends")
st.caption("PQ-06 Â· PulseIQ Analytics Â· Attendance and leave are descriptive measures, not causal explanations.")

min_month = attendance["month"].min()
max_month = attendance["month"].max()
months = sorted(attendance["month"].dropna().unique().tolist())
if not months:
    st.error("No valid attendance months were found.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    chosen_months = st.select_slider("Month range", options=months, value=(months[0], months[-1]))
    department_names = ["All departments"] + sorted(departments["department_name"].dropna().unique().tolist())
    chosen_department = st.selectbox("Department", department_names)
    st.caption("Attendance source: fact_attendance_monthly.csv")
    st.caption("Leave source: approved fact_leave.csv requests")
    st.caption("Holiday source: dim_date.csv")

start_month, end_month = chosen_months
filtered = attendance.loc[attendance["month"].between(start_month, end_month)].copy()
if chosen_department != "All departments":
    selected_ids = departments.loc[departments["department_name"].eq(chosen_department), "department_id"]
    filtered = filtered.loc[filtered["department_id"].isin(selected_ids)]

if filtered.empty:
    st.warning("No attendance rows match these filters.")
    st.stop()

filtered = filtered.merge(departments[["department_id", "department_name"]], on="department_id", how="left")
filtered["department_name"] = filtered["department_name"].fillna("Unknown")

monthly = filtered.groupby("month", as_index=False).agg(
    employees=("employee_id", "nunique"),
    scheduled_days=("scheduled_days", "sum"),
    present_days=("present_days", "sum"),
    late_arrivals=("late_arrivals", "sum"),
    overtime_hours=("overtime_hours", "sum"),
)
monthly["attendance_rate_pct"] = monthly["present_days"].div(monthly["scheduled_days"].replace(0, pd.NA)).mul(100)

calendar_filtered = calendar.loc[calendar["month"].between(start_month, end_month)].copy()
calendar_monthly = calendar_filtered.groupby("month", as_index=False).agg(
    calendar_holidays=("is_holiday", lambda s: int(s.eq("Y").sum())),
    calendar_weekend_days=("is_weekend", lambda s: int(s.eq("Y").sum())),
    calendar_working_days=("is_working_day", lambda s: int(s.eq("Y").sum())),
)
monthly = monthly.merge(calendar_monthly, on="month", how="left")

total_scheduled = filtered["scheduled_days"].sum()
total_present = filtered["present_days"].sum()
overall_rate = (100 * total_present / total_scheduled) if total_scheduled else 0
total_late = filtered["late_arrivals"].sum()
total_overtime = filtered["overtime_hours"].sum()
approved_leave_days = leave_monthly.loc[leave_monthly["month"].between(start_month, end_month), "days"].sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Attendance rate", f"{overall_rate:.2f}%")
k2.metric("Late arrivals", f"{total_late:,.0f}")
k3.metric("Overtime hours", f"{total_overtime:,.1f}")
k4.metric("Approved leave days*", f"{approved_leave_days:,.1f}")

st.caption("*Approved leave is allocated to months using calendar working dates. This allocation assumes the request's recorded leave days are distributed evenly over eligible working dates; validate this assumption before treating monthly allocation as official.")

st.subheader("Monthly attendance rate")
fig = px.line(monthly, x="month", y="attendance_rate_pct", markers=True,
              labels={"month": "Month", "attendance_rate_pct": "Attendance rate (%)"},
              title="Attendance rate = total present days Ã· total scheduled days")
fig.update_yaxes(ticksuffix="%", rangemode="tozero")
st.plotly_chart(fig, width="stretch")

left, right = st.columns(2)
with left:
    st.subheader("Late arrivals by month")
    st.plotly_chart(px.bar(monthly, x="month", y="late_arrivals",
                           labels={"month": "Month", "late_arrivals": "Late arrivals"}),
                    width="stretch")
with right:
    st.subheader("Overtime hours by month")
    st.plotly_chart(px.bar(monthly, x="month", y="overtime_hours",
                           labels={"month": "Month", "overtime_hours": "Overtime hours"}),
                    width="stretch")

st.subheader("Attendance rate by department")
dept_monthly = filtered.groupby(["month", "department_id"], as_index=False).agg(
    scheduled_days=("scheduled_days", "sum"),
    present_days=("present_days", "sum"),
    late_arrivals=("late_arrivals", "sum"),
    overtime_hours=("overtime_hours", "sum"),
)
dept_monthly = dept_monthly.merge(departments[["department_id", "department_name"]], on="department_id", how="left")
dept_monthly["attendance_rate_pct"] = dept_monthly["present_days"].div(
    dept_monthly["scheduled_days"].replace(0, pd.NA)
).mul(100)
st.plotly_chart(px.line(dept_monthly, x="month", y="attendance_rate_pct", color="department_name",
                        markers=True, labels={"month": "Month", "attendance_rate_pct": "Attendance rate (%)",
                                              "department_name": "Department"}),
                width="stretch")

st.subheader("Leave days by type and month")
lm = leave_monthly.loc[leave_monthly["month"].between(start_month, end_month)].copy()
if chosen_department != "All departments":
    # Leave fact is employee-key based; map employee keys to departments through attendance records.
    # If employee-key-to-department history is ambiguous, this filter is intentionally not applied.
    emp_dept = filtered[["employee_id", "department_id"]].drop_duplicates()
    counts = emp_dept.groupby("employee_id")["department_id"].nunique()
    unique_ids = counts[counts.eq(1)].index
    mapping = emp_dept.loc[emp_dept["employee_id"].isin(unique_ids)].drop_duplicates("employee_id")
    lm = lm.merge(mapping[["employee_id", "department_id"]], on="employee_id", how="left")
    lm = lm.loc[lm["department_id"].isin(selected_ids)]

if lm.empty:
    st.info("No approved leave records are available for this month range and department filter.")
else:
    leave_chart = lm.groupby(["month", "leave_type_name"], as_index=False)["days"].sum()
    st.plotly_chart(px.bar(leave_chart, x="month", y="days", color="leave_type_name",
                           labels={"month": "Month", "days": "Allocated approved leave days",
                                   "leave_type_name": "Leave type"}, barmode="stack"),
                    width="stretch")

st.subheader("Calendar context")
st.write("Holiday and weekend counts below come from the calendar dimension. They provide context; they do not prove that a holiday caused an attendance change.")
st.dataframe(calendar_monthly.loc[calendar_monthly["month"].between(start_month, end_month)].sort_values("month"),
             width="stretch", hide_index=True)

st.subheader("Monthly evidence table")
display_monthly = monthly.copy()
display_monthly["attendance_rate_pct"] = display_monthly["attendance_rate_pct"].round(2)
st.dataframe(display_monthly, width="stretch", hide_index=True)

with st.expander("Data definitions and caveats"):
    st.markdown("""
    - **Attendance rate:** sum of `present_days` divided by sum of `scheduled_days`, not the unweighted average of row-level percentages.
    - **Late arrivals / overtime:** sums of the values provided by the attendance fact.
    - **Approved leave:** excludes Pending, Rejected and Cancelled requests.
    - **Monthly leave allocation:** allocated across calendar working dates because the source records store leave at request level. This is an analytical allocation, not a source-provided daily leave fact.
    - **Calendar context:** holiday/weekend counts are calendar counts. Attendance data is monthly and does not itself identify the exact days absent.
    - **Causality:** a coincident holiday or long weekend is context only; investigate other causes before attributing an attendance dip.
    """)

