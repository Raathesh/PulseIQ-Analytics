from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="PulseIQ | PQ-13 Analytics", page_icon="📊", layout="wide")
DATA = Path("03_Data/processed/pq13_department_month.csv")
VALIDATION = Path("03_Data/processed/pq13_reference_validation_summary.csv")
MISMATCHES = Path("03_Data/processed/pq13_reference_validation_mismatches.csv")

st.title("PulseIQ Analytics")
st.subheader("PQ-13 | Department-Month Cross-Functional Dashboard")
st.caption("Workforce • Payroll • Attendance & Leave • Productivity")

if not DATA.exists():
    st.error(f"Dataset not found: {DATA}. Run pq13_department_month_etl.py from the project root.")
    st.stop()

df = pd.read_csv(DATA)
df["month_start_date"] = pd.to_datetime(df["month_start_date"], errors="coerce")
df = df.dropna(subset=["month_start_date"]).copy()
df["department_name"] = df["department_name"].fillna(df["department_id"])

numeric_cols = [
    "headcount_start", "hires", "exits", "voluntary_exits", "transfers_in",
    "transfers_out", "headcount_end", "attrition_rate_monthly_pct",
    "average_headcount", "payroll_rows", "payroll_employee_count",
    "payroll_gross_pay", "payroll_net_pay", "overtime_hours_paid",
    "overtime_cost", "employer_cost", "scheduled_days", "present_days",
    "wfh_days", "paid_leave_days", "unpaid_absence_days", "late_arrivals",
    "attendance_overtime_hours", "attendance_rate_weighted",
    "approved_leave_days", "allocated_leave_request_months", "tasks",
    "tasks_done", "story_points_done", "task_completion_rate_pct",
    "leave_days_per_average_head", "overtime_cost_per_average_head",
    "overtime_hours_variance",
]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

st.sidebar.header("Dashboard filters")
departments = sorted(df["department_name"].dropna().unique())
selected_departments = st.sidebar.multiselect("Department", departments, default=departments)
min_date, max_date = df["month_start_date"].min().date(), df["month_start_date"].max().date()
date_range = st.sidebar.date_input("Month range", value=(min_date, max_date),
                                   min_value=min_date, max_value=max_date)
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

data = df[
    df["department_name"].isin(selected_departments)
    & df["month_start_date"].dt.date.between(start_date, end_date)
].copy()
if data.empty:
    st.warning("No records match these filters. Select another department or month range.")
    st.stop()

data = data.sort_values(["month_start_date", "department_name"])
latest_month = data["month_start_date"].max()
latest = data[data["month_start_date"] == latest_month]

def total(col):
    return data[col].sum(min_count=1) if col in data else float("nan")

def money(x):
    return "—" if pd.isna(x) else f"₹{x:,.0f}"

def fmt_num(x):
    return "—" if pd.isna(x) else f"{x:,.0f}"

def fmt_pct(x):
    return "—" if pd.isna(x) else f"{x:.2f}%"

valid_att = data[["attendance_rate_weighted", "scheduled_days"]].dropna()
valid_att = valid_att[valid_att["scheduled_days"] > 0]
attendance = (
    (valid_att["attendance_rate_weighted"] * valid_att["scheduled_days"]).sum()
    / valid_att["scheduled_days"].sum() * 100
    if not valid_att.empty else float("nan")
)
task_rows = data[data["tasks"].notna() & data["tasks_done"].notna()]
task_rate = (
    task_rows["tasks_done"].sum() / task_rows["tasks"].sum() * 100
    if not task_rows.empty and task_rows["tasks"].sum() > 0 else float("nan")
)

st.markdown("### Executive overview")
k = st.columns(4)
k[0].metric("Employer cost", money(total("employer_cost")))
k[1].metric("Gross pay", money(total("payroll_gross_pay")))
k[2].metric("Overtime cost", money(total("overtime_cost")))
k[3].metric(f"Ending headcount · {latest_month:%b %Y}", fmt_num(latest["headcount_end"].sum(min_count=1)))

k = st.columns(4)
k[0].metric("Attendance rate", fmt_pct(attendance))
k[1].metric("Approved leave days", fmt_num(total("approved_leave_days")))
k[2].metric("Overtime hours", fmt_num(total("overtime_hours_paid")))
k[3].metric("Task completion rate", fmt_pct(task_rate))
st.caption(
    f"Selected: {start_date:%d %b %Y} – {end_date:%d %b %Y} · "
    f"{data['department_id'].nunique()} departments · {len(data)} department-month rows"
)

st.divider()
st.markdown("### 1. Workforce analytics")
monthly = data.groupby("month_start_date", as_index=False).agg(
    ending_headcount=("headcount_end", "sum"),
    hires=("hires", "sum"), exits=("exits", "sum"),
    attrition_rate=("attrition_rate_monthly_pct", "mean"),
)
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Ending headcount trend**")
    st.line_chart(monthly.set_index("month_start_date")[["ending_headcount"]])
with c2:
    st.markdown("**Monthly hires and exits**")
    st.bar_chart(monthly.set_index("month_start_date")[["hires", "exits"]])

dept_workforce = data.groupby("department_name", as_index=False).agg(
    average_ending_headcount=("headcount_end", "mean"),
    hires=("hires", "sum"), exits=("exits", "sum"),
    average_attrition_rate=("attrition_rate_monthly_pct", "mean"),
).sort_values("average_ending_headcount", ascending=False)
st.dataframe(dept_workforce, use_container_width=True, hide_index=True)

st.divider()
st.markdown("### 2. Payroll and overtime analytics")
pay_month = data.groupby("month_start_date", as_index=False).agg(
    employer_cost=("employer_cost", "sum"),
    gross_pay=("payroll_gross_pay", "sum"),
    overtime_cost=("overtime_cost", "sum"),
    overtime_hours=("overtime_hours_paid", "sum"),
)
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Employer cost and gross pay**")
    st.line_chart(pay_month.set_index("month_start_date")[["employer_cost", "gross_pay"]])
with c2:
    st.markdown("**Overtime cost**")
    st.bar_chart(pay_month.set_index("month_start_date")[["overtime_cost"]])

dept_pay = data.groupby("department_name", as_index=False).agg(
    employer_cost=("employer_cost", "sum"),
    gross_pay=("payroll_gross_pay", "sum"),
    overtime_cost=("overtime_cost", "sum"),
    overtime_hours=("overtime_hours_paid", "sum"),
).sort_values("employer_cost", ascending=False)
st.markdown("**Department payroll comparison**")
st.dataframe(dept_pay, use_container_width=True, hide_index=True)

st.divider()
st.markdown("### 3. Attendance and leave analytics")
att_month_rows = []
for month, group in data.groupby("month_start_date"):
    valid = group[["attendance_rate_weighted", "scheduled_days"]].dropna()
    valid = valid[valid["scheduled_days"] > 0]
    rate = (
        (valid["attendance_rate_weighted"] * valid["scheduled_days"]).sum()
        / valid["scheduled_days"].sum() * 100
        if not valid.empty else float("nan")
    )
    att_month_rows.append({
        "month_start_date": month,
        "attendance_rate_pct": rate,
        "approved_leave_days": group["approved_leave_days"].sum(),
        "paid_leave_days": group["paid_leave_days"].sum(),
        "unpaid_absence_days": group["unpaid_absence_days"].sum(),
    })
att_month = pd.DataFrame(att_month_rows).sort_values("month_start_date")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Attendance rate trend (%)**")
    st.line_chart(att_month.set_index("month_start_date")[["attendance_rate_pct"]])
with c2:
    st.markdown("**Approved leave days**")
    st.bar_chart(att_month.set_index("month_start_date")[["approved_leave_days"]])

dept_leave = data.groupby("department_name", as_index=False).agg(
    approved_leave_days=("approved_leave_days", "sum"),
    leave_days_per_average_head=("leave_days_per_average_head", "mean"),
    paid_leave_days=("paid_leave_days", "sum"),
    unpaid_absence_days=("unpaid_absence_days", "sum"),
    late_arrivals=("late_arrivals", "sum"),
).sort_values("approved_leave_days", ascending=False)
st.markdown("**Department leave and attendance indicators**")
st.dataframe(dept_leave, use_container_width=True, hide_index=True)

st.divider()
st.markdown("### 4. Department productivity")
task_data = data[data["tasks"].notna()].copy()
if task_data.empty:
    st.info("No task data is available for the selected departments and period.")
else:
    task_month = task_data.groupby("month_start_date", as_index=False).agg(
        tasks=("tasks", "sum"), tasks_done=("tasks_done", "sum"),
        story_points_done=("story_points_done", "sum"),
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Tasks created and completed**")
        st.line_chart(task_month.set_index("month_start_date")[["tasks", "tasks_done"]])
    with c2:
        st.markdown("**Story points completed**")
        st.bar_chart(task_month.set_index("month_start_date")[["story_points_done"]])

    dept_tasks = task_data.groupby("department_name", as_index=False).agg(
        tasks=("tasks", "sum"), tasks_done=("tasks_done", "sum"),
        story_points_done=("story_points_done", "sum"),
    )
    dept_tasks["completion_rate_pct"] = dept_tasks["tasks_done"] / dept_tasks["tasks"] * 100
    st.markdown("**Department productivity comparison**")
    st.dataframe(
        dept_tasks.sort_values("completion_rate_pct", ascending=False),
        use_container_width=True, hide_index=True,
    )
st.caption("Task metrics remain blank for departments without task-team mappings; blanks are not converted to zero.")

st.divider()
st.markdown("### 5. Data quality and reference validation")
q = st.columns(3)
q[0].metric("Department-month rows", f"{len(df):,}")
q[1].metric("Departments", f"{df['department_id'].nunique():,}")
q[2].metric("Months", f"{df['month_start_date'].dt.to_period('M').nunique():,}")

if VALIDATION.exists():
    st.markdown("**Reference validation summary**")
    st.dataframe(pd.read_csv(VALIDATION), use_container_width=True, hide_index=True)
if MISMATCHES.exists():
    mismatch = pd.read_csv(MISMATCHES)
    st.markdown("**Reference mismatch details**")
    st.caption("Source-derived ETL values are retained. Differences are disclosed, not silently overwritten.")
    if not mismatch.empty:
        opts = sorted(mismatch["metric"].dropna().unique())
        chosen = st.multiselect("Filter mismatch metrics", opts, default=opts)
        st.dataframe(mismatch[mismatch["metric"].isin(chosen)], use_container_width=True, hide_index=True)
    else:
        st.success("No reference mismatches found.")

st.divider()
st.markdown("### 6. Department-month detail")
detail_cols = [
    "department_id", "department_name", "month_start_date", "headcount_end",
    "hires", "exits", "attrition_rate_monthly_pct", "employer_cost",
    "payroll_gross_pay", "overtime_cost", "overtime_hours_paid",
    "attendance_rate_weighted", "approved_leave_days",
    "leave_days_per_average_head", "tasks", "tasks_done",
    "story_points_done", "task_completion_rate_pct",
]
detail_cols = [c for c in detail_cols if c in data.columns]
st.dataframe(
    data[detail_cols].sort_values(["month_start_date", "department_name"], ascending=[False, True]),
    use_container_width=True, hide_index=True,
)
csv = data.drop(columns=["month_label"], errors="ignore").to_csv(index=False).encode("utf-8")
st.download_button(
    "Download filtered department-month data (CSV)",
    data=csv, file_name="pq13_department_month_filtered.csv", mime="text/csv",
)
st.caption("Source: PQ-13 department-month ETL. Attendance and payroll reference differences are disclosed.")
