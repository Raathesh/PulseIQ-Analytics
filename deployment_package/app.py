
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

st.set_page_config(
    page_title="PulseIQ Analytics | Demo",
    page_icon="📊",
    layout="wide"
)

st.title("PulseIQ Analytics")
st.subheader("Executive Company Health Scorecard")

st.warning(
    "DEMO ENVIRONMENT — All figures on this dashboard are synthetic. "
    "They do not represent actual company or employee information."
)

st.caption("Reporting data cutoff: 30 September 2026 | Synthetic demonstration data")


@st.cache_data
def load_data():
    files = [
        "m01_headcount_governed.csv",
        "m05_attrition_rolling_12m.csv",
        "m09_employer_cost_governed.csv",
        "m11_overtime_share_governed.csv",
        "m13_attendance_rate_governed.csv",
        "m17_net_profit.csv",
        "m21_overdue_receivables.csv",
        "m22_task_completion.csv",
        "dim_sprint.csv",
        "dim_team.csv",
        "kpi_targets.csv",
    ]

    frames = {
        Path(file).stem: pd.read_csv(DATA / file)
        for file in files
    }

    date_columns = {
        "m01_headcount_governed": ["month_start_date"],
        "m05_attrition_rolling_12m": ["month_start_date"],
        "m09_employer_cost_governed": ["period_end_date"],
        "m11_overtime_share_governed": ["period_end_date"],
        "m13_attendance_rate_governed": ["period_end_date"],
        "m17_net_profit": ["month_start_date"],
        "m21_overdue_receivables": ["report_date"],
        "dim_sprint": ["start_date", "end_date"],
        "kpi_targets": ["month"],
    }

    for table, columns in date_columns.items():
        for column in columns:
            frames[table][column] = pd.to_datetime(
                frames[table][column], errors="coerce"
            )

    return frames


try:
    d = load_data()
except Exception as exc:
    st.error(f"Could not load demo data: {exc}")
    st.info("Check that all 11 CSV files are inside the data folder.")
    st.stop()


def published(frame, value_column):
    return frame[
        (frame["privacy_status"] == "PUBLISHED")
        & frame[value_column].notna()
    ].copy()


headcount = d["m01_headcount_governed"]
attrition = d["m05_attrition_rolling_12m"]
cost = d["m09_employer_cost_governed"]
overtime = d["m11_overtime_share_governed"]
attendance = d["m13_attendance_rate_governed"]
profit = d["m17_net_profit"]
receivables = d["m21_overdue_receivables"]
tasks = d["m22_task_completion"]
sprints = d["dim_sprint"]
teams = d["dim_team"]
targets = d["kpi_targets"]

available_months = sorted(
    headcount["month_start_date"].dropna().unique()
)

if not available_months:
    st.error("No reporting months were found.")
    st.stop()

selected_month = st.selectbox(
    "Select reporting month",
    options=available_months,
    index=len(available_months) - 1,
    format_func=lambda value: pd.Timestamp(value).strftime("%B %Y")
)

selected_period = pd.Timestamp(selected_month).to_period("M")
previous_period = selected_period - 1
selected_label = selected_period.strftime("%B %Y")

month_targets = targets[
    targets["month"].dt.to_period("M") == selected_period
].copy()


# 1. Headcount
hc_month = headcount[
    headcount["month_start_date"].dt.to_period("M") == selected_period
]
hc_pub = published(hc_month, "headcount")
total_headcount = int(hc_pub["headcount"].sum())

hc_previous = headcount[
    headcount["month_start_date"].dt.to_period("M") == previous_period
]
previous_headcount = int(
    published(hc_previous, "headcount")["headcount"].sum()
)

headcount_change = total_headcount - previous_headcount


# 2. Rolling 12-month attrition
attr_month = attrition[
    attrition["month_start_date"].dt.to_period("M") == selected_period
]
attr_pub = published(attr_month, "attrition_rate_12m_pct")

if not attr_pub.empty:
    attr_min = attr_pub["attrition_rate_12m_pct"].min()
    attr_max = attr_pub["attrition_rate_12m_pct"].max()
    highest_attrition = attr_pub.loc[
        attr_pub["attrition_rate_12m_pct"].idxmax()
    ]
    highest_attrition_dept = highest_attrition["department_id"]
else:
    attr_min = attr_max = None
    highest_attrition_dept = "No published data"


# 3. Employer cost
cost_month = cost[
    cost["period_end_date"].dt.to_period("M") == selected_period
]
cost_pub = published(cost_month, "employer_cost")
total_employer_cost = cost_pub["employer_cost"].sum()

cost_previous = cost[
    cost["period_end_date"].dt.to_period("M") == previous_period
]
previous_employer_cost = published(
    cost_previous, "employer_cost"
)["employer_cost"].sum()


# 4. Overtime target compliance
ot_month = overtime[
    overtime["period_end_date"].dt.to_period("M") == selected_period
]
ot_pub = published(ot_month, "overtime_share_pct")

ot_check = ot_pub.merge(
    month_targets[["department_id", "overtime_share_target_pct"]],
    on="department_id",
    how="inner"
)
ot_meeting = int(
    (
        ot_check["overtime_share_pct"]
        <= ot_check["overtime_share_target_pct"]
    ).sum()
)


# 5. Weighted attendance and target compliance
att_month = attendance[
    attendance["period_end_date"].dt.to_period("M") == selected_period
]
att_pub = published(att_month, "attendance_rate_pct")

if not att_pub.empty and att_pub["total_scheduled_days"].sum() > 0:
    weighted_attendance = (
        att_pub["attendance_rate_pct"]
        .mul(att_pub["total_scheduled_days"])
        .sum()
        / att_pub["total_scheduled_days"].sum()
    )
else:
    weighted_attendance = None

att_check = att_pub.merge(
    month_targets[["department_id", "attendance_rate_target"]],
    on="department_id",
    how="inner"
)
att_check["target_pct"] = (
    att_check["attendance_rate_target"].where(
        att_check["attendance_rate_target"] > 1,
        att_check["attendance_rate_target"] * 100
    )
)
att_meeting = int(
    (att_check["attendance_rate_pct"] >= att_check["target_pct"]).sum()
)


# 6. Net profit
profit_month = profit[
    profit["month_start_date"].dt.to_period("M") == selected_period
]
profit_previous = profit[
    profit["month_start_date"].dt.to_period("M") == previous_period
]

net_profit = (
    profit_month["net_profit"].sum()
    if not profit_month.empty else None
)
previous_profit = (
    profit_previous["net_profit"].sum()
    if not profit_previous.empty else None
)


# 7. Overdue receivables: latest available snapshot
latest_receivable_date = receivables["report_date"].max()
latest_receivables = receivables[
    receivables["report_date"] == latest_receivable_date
]
overdue_total = latest_receivables["overdue_receivables"].sum()


# 8. Sprint task completion
sprints_month = sprints[
    sprints["end_date"].dt.to_period("M") == selected_period
]

if not sprints_month.empty:
    latest_sprint = sprints_month.sort_values("end_date").iloc[-1]
    sprint_id = latest_sprint["sprint_id"]

    task_month = tasks[tasks["sprint_id"] == sprint_id]
    task_pub = published(task_month, "completion_rate_pct")

    task_detail = task_pub.merge(
        teams[["team_id", "department_id"]],
        on="team_id",
        how="left"
    )

    task_detail = task_detail.groupby(
        "department_id", as_index=False
    ).agg(
        planned_tasks=("planned_tasks", "sum"),
        completed_tasks=("completed_tasks", "sum")
    )

    task_detail["completion_rate_pct"] = (
        task_detail["completed_tasks"]
        / task_detail["planned_tasks"]
        * 100
    )

    task_detail = task_detail.merge(
        month_targets[["department_id", "task_completion_target_pct"]],
        on="department_id",
        how="inner"
    )

    task_meeting = int(
        (
            task_detail["completion_rate_pct"]
            >= task_detail["task_completion_target_pct"]
        ).sum()
    )
else:
    task_detail = pd.DataFrame()
    task_meeting = 0


st.markdown(f"### Reporting month: {selected_label}")

# KPI cards
c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Published headcount",
    f"{total_headcount:,}",
    f"{headcount_change:+,} vs previous month"
)

if attr_min is not None:
    c2.metric(
        "Rolling 12M attrition range",
        f"{attr_min:.1f}% – {attr_max:.1f}%"
    )
    c2.caption(f"Highest department: {highest_attrition_dept}")
else:
    c2.metric("Rolling 12M attrition", "No data")

c3.metric(
    "Employer cost",
    f"₹{total_employer_cost:,.0f}",
    f"Previous: ₹{previous_employer_cost:,.0f}"
)

c4.metric(
    "Overtime target compliance",
    f"{ot_meeting}/{len(ot_check)} departments"
    if not ot_check.empty else "No data"
)

c5, c6, c7, c8 = st.columns(4)

c5.metric(
    "Weighted attendance",
    f"{weighted_attendance:.2f}%"
    if weighted_attendance is not None else "No data"
)
c5.caption(
    f"Departments meeting target: {att_meeting}/{len(att_check)}"
)

c6.metric(
    "Net profit",
    f"₹{net_profit:,.0f}" if net_profit is not None else "No data",
    f"Previous: ₹{previous_profit:,.0f}"
    if previous_profit is not None else None
)

c7.metric("Overdue receivables", f"₹{overdue_total:,.0f}")
c7.caption(
    f"Snapshot: {pd.Timestamp(latest_receivable_date).strftime('%d %b %Y')}"
)

c8.metric(
    "Task completion target",
    f"{task_meeting}/{len(task_detail)} departments"
    if not task_detail.empty else "No sprint data"
)

st.divider()

# Net profit trend
st.subheader("Monthly net profit trend")

profit_chart = profit.sort_values("month_start_date").copy()
profit_chart["month_label"] = profit_chart["month_start_date"].dt.strftime(
    "%b %Y"
)

chart = alt.Chart(profit_chart).mark_line(
    point=True
).encode(
    x=alt.X("month_label:N", title="Month", sort=None),
    y=alt.Y("net_profit:Q", title="Net profit (₹)"),
    tooltip=[
        alt.Tooltip("month_label:N", title="Month"),
        alt.Tooltip("net_profit:Q", title="Net profit", format=",.0f")
    ]
).properties(height=320)

st.altair_chart(chart, width="stretch")

# Department details
st.subheader("Department performance")

tab1, tab2, tab3, tab4 = st.tabs([
    "Headcount",
    "Attendance & overtime",
    "Employer cost & attrition",
    "Task completion"
])

with tab1:
    st.dataframe(
        hc_pub[["department_id", "headcount"]],
        width="stretch",
        hide_index=True
    )

with tab2:
    attendance_view = att_pub[
        ["department_id", "attendance_rate_pct"]
    ].merge(
        ot_pub[["department_id", "overtime_share_pct"]],
        on="department_id",
        how="outer"
    )
    st.dataframe(
        attendance_view,
        width="stretch",
        hide_index=True
    )

with tab3:
    cost_view = cost_pub[
        ["department_id", "employee_count", "employer_cost"]
    ].merge(
        attr_pub[["department_id", "attrition_rate_12m_pct"]],
        on="department_id",
        how="outer"
    )
    st.dataframe(
        cost_view,
        width="stretch",
        hide_index=True
    )

with tab4:
    if not task_detail.empty:
        st.dataframe(
            task_detail,
            width="stretch",
            hide_index=True
        )
    else:
        st.info("No sprint data is available for this month.")

st.caption(
    "Privacy note: This demonstration uses synthetic department-level "
    "aggregates only. No employee names, employee IDs, client IDs, or "
    "production records are included."
)
