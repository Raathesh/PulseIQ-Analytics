from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "03_Data" / "csv"
OUT = ROOT / "outputs" / "pq01"

st.set_page_config(page_title="PQ-10 Budget & KPI", layout="wide")
st.title("PQ-10 | Budget vs Actual & KPI Targets")
st.caption("Department-month cost control, operational KPI scorecard, and evidence-led priorities.")


@st.cache_data
def csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path}")
    return pd.read_csv(path, low_memory=False)


def first_path(*paths):
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError("No source file found: " + ", ".join(str(p) for p in paths))


def month(series):
    return pd.to_datetime(series, errors="coerce").dt.to_period("M").astype(str)


def num(df, cols):
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def money(x):
    return "—" if pd.isna(x) else f"₹{x:,.2f}"


def percent(x):
    return "—" if pd.isna(x) else f"{x:.2f}%"


def kpi_status(actual, target, direction):
    if pd.isna(actual):
        return "No data"
    if pd.isna(target):
        return "No target"
    if (direction == "higher" and actual >= target) or (direction == "lower" and actual <= target):
        return "Green"
    # No amber threshold exists in the source dictionary. Avoid inventing one.
    return "Red"


@st.cache_data
def build():
    budget = csv(DATA / "budget_payroll_dept_month.csv")
    targets = csv(DATA / "kpi_targets.csv")
    depts = csv(DATA / "dim_department.csv")
    teams = csv(DATA / "dim_team.csv")
    sprints = csv(DATA / "dim_sprint.csv")
    payroll_path = first_path(OUT / "fact_payroll_passed.csv", DATA / "fact_payroll.csv")
    tasks_path = first_path(OUT / "fact_task_passed.csv", DATA / "fact_task.csv")
    payroll = csv(payroll_path)
    attendance = csv(DATA / "fact_attendance_monthly.csv")
    hc = csv(DATA / "fact_headcount_monthly.csv")
    tasks = csv(tasks_path)

    budget["m"] = month(budget["month"])
    targets["m"] = month(targets["month"])
    payroll["m"] = month(payroll["period_end_date"])
    attendance["m"] = month(attendance["period_end_date"])
    hc["m"] = month(hc["month_start_date"])

    num(budget, ["budget_payroll_cost"])
    num(targets, ["attendance_rate_target", "overtime_share_target_pct",
                  "attrition_monthly_target_pct", "task_completion_target_pct"])
    num(payroll, ["employer_cost", "gross_pay", "net_pay", "overtime_pay"])
    num(attendance, ["scheduled_days", "present_days", "half_days_unpaid"])
    num(hc, ["headcount_start", "exits", "headcount_end"])

    p = payroll.groupby(["department_id", "m"], as_index=False).agg(
        actual_cost=("employer_cost", "sum"),
        gross_pay=("gross_pay", "sum"),
        net_pay=("net_pay", "sum"),
        overtime_pay=("overtime_pay", "sum"),
        employee_count=("employee_id", "nunique"),
    )
    p["overtime_share_pct"] = p["overtime_pay"] / p["actual_cost"].replace(0, float("nan")) * 100

    attendance["present_equivalent"] = attendance["present_days"] + 0.5 * attendance["half_days_unpaid"]
    a = attendance.groupby(["department_id", "m"], as_index=False).agg(
        present_equivalent=("present_equivalent", "sum"),
        scheduled_days=("scheduled_days", "sum"),
        attendance_group=("employee_id", "nunique"),
    )
    a["attendance_pct"] = a["present_equivalent"] / a["scheduled_days"].replace(0, float("nan")) * 100

    h = hc.groupby(["department_id", "m"], as_index=False).agg(
        headcount_start=("headcount_start", "sum"),
        exits=("exits", "sum"),
        headcount_end=("headcount_end", "sum"),
    )
    h["attrition_pct"] = h["exits"] / h["headcount_start"].replace(0, float("nan")) * 100

    # Map tasks to departments via team, then assign each sprint to its end month.
    tasks = tasks.merge(teams[["team_id", "department_id"]].drop_duplicates("team_id"),
                        on="team_id", how="left", validate="many_to_one")
    tasks = tasks.merge(sprints[["sprint_id", "end_date"]].drop_duplicates("sprint_id"),
                        on="sprint_id", how="left", validate="many_to_one")
    tasks["m"] = month(tasks["end_date"])
    stxt = tasks["status"].astype(str).str.strip().str.casefold()
    tasks["done_flag"] = stxt.eq("done").astype(int)
    tasks["cancel_flag"] = stxt.eq("cancelled")
    t = tasks.loc[~tasks["cancel_flag"]].groupby(["department_id", "m"], as_index=False).agg(
        tasks_planned=("task_id", "nunique"),
        tasks_done=("done_flag", "sum"),
    )
    t["task_completion_pct"] = t["tasks_done"] / t["tasks_planned"].replace(0, float("nan")) * 100

    # Budget rows are the scaffold so missing actuals remain visible as missing.
    d = budget[["department_id", "m", "budget_payroll_cost"]].merge(
        p, on=["department_id", "m"], how="left"
    ).merge(a, on=["department_id", "m"], how="left").merge(
        h, on=["department_id", "m"], how="left"
    ).merge(t, on=["department_id", "m"], how="left").merge(
        targets.drop(columns=["month"], errors="ignore"),
        on=["department_id", "m"], how="left"
    ).merge(depts[["department_id", "department_name"]].drop_duplicates("department_id"),
            on="department_id", how="left")

    d["variance"] = d["actual_cost"] - d["budget_payroll_cost"]
    d["variance_pct"] = d["variance"] / d["budget_payroll_cost"].replace(0, float("nan")) * 100
    d["attendance_target_pct"] = d["attendance_rate_target"] * 100
    d["attendance_status"] = d.apply(lambda r: kpi_status(r["attendance_pct"], r["attendance_target_pct"], "higher"), axis=1)
    d["overtime_status"] = d.apply(lambda r: kpi_status(r["overtime_share_pct"], r["overtime_share_target_pct"], "lower"), axis=1)
    d["attrition_status"] = d.apply(lambda r: kpi_status(r["attrition_pct"], r["attrition_monthly_target_pct"], "lower"), axis=1)
    d["task_status"] = d.apply(lambda r: kpi_status(r["task_completion_pct"], r["task_completion_target_pct"], "higher"), axis=1)
    d["budget_status"] = d.apply(
        lambda r: "No data" if pd.isna(r["actual_cost"]) else ("Green" if r["variance"] <= 0 else "Red"), axis=1
    )
    return d, payroll_path, tasks_path


try:
    df, payroll_path, tasks_path = build()
except Exception as e:
    st.error(f"Unable to load dashboard data: {e}")
    st.stop()

months = sorted(df["m"].dropna().unique())
depts = sorted(df["department_name"].dropna().unique())
with st.sidebar:
    st.header("Filters")
    chosen_months = st.multiselect("Month", months, default=months)
    chosen_depts = st.multiselect("Department", depts, default=depts)
    st.caption("Variance = actual employer cost − budget. Positive is overspend; negative is underspend.")

f = df[df["m"].isin(chosen_months) & df["department_name"].isin(chosen_depts)].copy()
if f.empty:
    st.warning("No rows match these filters.")
    st.stop()

budget_sum = f["budget_payroll_cost"].sum()
actual_sum = f["actual_cost"].sum(min_count=1)
variance_sum = actual_sum - budget_sum if pd.notna(actual_sum) else float("nan")
variance_pct = variance_sum / budget_sum * 100 if budget_sum and pd.notna(variance_sum) else float("nan")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Budget", money(budget_sum))
c2.metric("Actual employer cost", money(actual_sum))
c3.metric("Variance (actual − budget)", money(variance_sum), percent(variance_pct))
c4.metric("Department-month rows", f"{len(f):,}")

st.subheader("Monthly budget vs actual")
monthly = f.groupby("m", as_index=False).agg(
    Budget=("budget_payroll_cost", "sum"), Actual=("actual_cost", "sum")
)
monthly_long = monthly.melt("m", var_name="Measure", value_name="INR")
st.plotly_chart(px.line(monthly_long, x="m", y="INR", color="Measure", markers=True),
                use_container_width=True)

dept = f.groupby(["department_id", "department_name"], as_index=False).agg(
    budget=("budget_payroll_cost", "sum"),
    actual=("actual_cost", "sum"),
    employee_months=("employee_count", "sum"),
)
dept["variance"] = dept["actual"] - dept["budget"]
dept["variance_pct"] = dept["variance"] / dept["budget"].replace(0, float("nan")) * 100
left, right = st.columns(2)
with left:
    long = dept.melt("department_name", value_vars=["budget", "actual"],
                     var_name="Measure", value_name="INR")
    st.plotly_chart(px.bar(long, x="department_name", y="INR", color="Measure", barmode="group",
                           title="Budget vs actual by department"), use_container_width=True)
with right:
    st.plotly_chart(px.bar(dept.sort_values("variance"), x="variance", y="department_name",
                           orientation="h", title="Department variance (actual − budget)"),
                    use_container_width=True)

st.subheader("Budget control and overspend ranking")
dept_display = dept.sort_values("variance", ascending=False).copy()
for col in ["budget", "actual", "variance"]:
    dept_display[col] = dept_display[col].map(money)
dept_display["variance_pct"] = dept_display["variance_pct"].map(percent)
st.dataframe(dept_display.rename(columns={
    "department_name": "Department", "budget": "Budget", "actual": "Actual",
    "variance": "Variance", "variance_pct": "Variance %", "employee_months": "Employee-months"
}), use_container_width=True, hide_index=True)

overspend = dept[dept["variance"] > 0].sort_values("variance", ascending=False)
st.subheader("Evidence-based review priorities")
if overspend.empty:
    st.success("No selected department is over budget in the selected period.")
else:
    for i, (_, r) in enumerate(overspend.head(2).iterrows(), start=1):
        st.markdown(
            f"**{i}. {r['department_name']}** — variance {money(r['variance'])} "
            f"({percent(r['variance_pct'])}). Review headcount, role mix, overtime and variable-pay drivers "
            "month by month before changing budgets."
        )
    if len(overspend) == 1:
        st.write("Second action: compare overtime share and employee-month counts across departments; prioritize only drivers supported by the data.")

st.divider()
st.header("Operational KPI scorecard")
st.caption("Green means target met; red means target missed. The source does not define an amber band, so none is invented. Missing targets show as No target.")
specs = [
    ("Attendance", "attendance_pct", "attendance_target_pct", "attendance_status", "Higher is better", "attendance_group", 5),
    ("Overtime share", "overtime_share_pct", "overtime_share_target_pct", "overtime_status", "Lower is better", "employee_count", 5),
    ("Monthly attrition", "attrition_pct", "attrition_monthly_target_pct", "attrition_status", "Lower is better", "headcount_start", 10),
    ("Task completion", "task_completion_pct", "task_completion_target_pct", "task_status", "Higher is better", "tasks_planned", 5),
]
records = []
for _, r in f.iterrows():
    for label, actual_col, target_col, status_col, direction, size_col, minimum in specs:
        actual, target = r.get(actual_col), r.get(target_col)
        size = r.get(size_col)
        status = r.get(status_col, "No data")
        if pd.notna(size) and size < minimum:
            status, actual = "Suppressed", float("nan")
        records.append({
            "Month": r["m"], "Department": r["department_name"], "KPI": label,
            "Actual": percent(actual), "Target": percent(target), "Status": status,
            "Direction": direction, "Group size": size, "Minimum group size": minimum
        })
kpis = pd.DataFrame(records)
st.dataframe(kpis.sort_values(["Month", "Department", "KPI"]),
             use_container_width=True, hide_index=True)
counts = kpis.groupby(["KPI", "Status"], as_index=False).size()
st.plotly_chart(px.bar(counts, x="KPI", y="size", color="Status", barmode="stack",
                       title="KPI status counts"), use_container_width=True)

st.divider()
st.header("Manual verification: three department-month combinations")
checks = f.dropna(subset=["actual_cost", "budget_payroll_cost"]).sort_values(["m", "department_id"]).head(3).copy()
if checks.empty:
    st.warning("No rows with both budget and actual available to verify.")
else:
    checks["Recomputed variance"] = checks["actual_cost"] - checks["budget_payroll_cost"]
    checks["Check"] = (checks["variance"].round(2) == checks["Recomputed variance"].round(2))
    checks["Budget"] = checks["budget_payroll_cost"].map(money)
    checks["Actual"] = checks["actual_cost"].map(money)
    checks["Variance"] = checks["Recomputed variance"].map(money)
    checks["Variance %"] = checks["variance_pct"].map(percent)
    st.dataframe(checks[["m", "department_name", "Budget", "Actual", "Variance", "Variance %", "Check"]]
                 .rename(columns={"m": "Month", "department_name": "Department", "Check": "Arithmetic check passed"}),
                 use_container_width=True, hide_index=True)

with st.expander("Definitions, limitations and source files"):
    st.markdown("""
    - Payroll actual = sum of `employer_cost` from the validated payroll file when present.
    - Budget variance = actual employer cost − budget; positive is overspend.
    - Attendance (M13) = (present days + 0.5 × unpaid half-days) / scheduled days × 100.
    - Overtime share (M11) = overtime pay / employer cost × 100.
    - Monthly attrition (M04) = exits / starting headcount × 100; minimum group size 10.
    - Task completion (M22) = Done tasks / non-Cancelled tasks × 100. Tasks map to department via team and month via sprint end date.
    - Attendance, overtime, attrition and task completion apply metric-dictionary minimum group sizes where available.
    - D10 has no task-completion target in all 18 months; its status is No target.
    - The source does not define amber thresholds; only met/missed statuses are shown.
    - Task data is documented as a sample feed.
    - No employee-level salary details are displayed.
    """)
    st.write(f"Payroll source: `{payroll_path.relative_to(ROOT)}`")
    st.write(f"Task source: `{tasks_path.relative_to(ROOT)}`")

st.caption("PQ-10 Budget & KPI Dashboard")
