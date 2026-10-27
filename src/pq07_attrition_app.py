"""
PQ-07 Attrition Analytics Dashboard
Run from the repository root:
    python -m streamlit run src/pq07_attrition_app.py

This dashboard distinguishes historical actual exits from model-predicted risk.
It intentionally avoids employee-level risk rankings and suppresses small risk groups.
"""

from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "03_Data" / "csv"
PRIVACY_MIN_GROUP = 5

st.set_page_config(
    page_title="PQ-07 | Attrition Analytics",
    page_icon="ðŸ“Š",
    layout="wide",
)

st.title("PQ-07 | Attrition Analytics")
st.caption(
    "Historical exits and headcount trends are actual recorded data. "
    "Attrition risk is a model prediction, not a confirmed future exit."
)

@st.cache_data
def load_csv(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Required data file was not found: {path}")
    return pd.read_csv(path, low_memory=False)

def parse_dates(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df

def safe_pct(numerator, denominator):
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return 0.0
    return 100.0 * numerator / denominator

try:
    headcount = load_csv("fact_headcount_monthly.csv")
    employee = load_csv("dim_employee.csv")
    risk = load_csv("fact_attrition_risk.csv")
    departments = load_csv("dim_department.csv")
except Exception as exc:
    st.error(f"Could not load the required CSV data: {exc}")
    st.info("Run this app from the PulseIQ repository; expected data folder is 03_Data/csv.")
    st.stop()

headcount = parse_dates(headcount, ["month_start_date"])
employee = parse_dates(employee, ["hire_date", "exit_date", "valid_from", "valid_to"])
risk = parse_dates(risk, ["as_of_date"])
for col in [
    "headcount_start", "hires", "exits", "voluntary_exits",
    "transfers_in", "transfers_out", "headcount_end",
    "attrition_rate_monthly_pct",
]:
    if col in headcount.columns:
        headcount[col] = pd.to_numeric(headcount[col], errors="coerce")
if "risk_score_12m" in risk.columns:
    risk["risk_score_12m"] = pd.to_numeric(risk["risk_score_12m"], errors="coerce")

required_headcount = {
    "month_start_date", "department_id", "headcount_start", "exits",
    "voluntary_exits", "headcount_end", "attrition_rate_monthly_pct",
}
missing = required_headcount - set(headcount.columns)
if missing:
    st.error(f"fact_headcount_monthly.csv is missing columns: {', '.join(sorted(missing))}")
    st.stop()

dept_map = departments.drop_duplicates("department_id").set_index("department_id")["department_name"].to_dict()
headcount["department_name"] = headcount["department_id"].map(dept_map).fillna(headcount["department_id"])
risk["department_name"] = risk["department_id"].map(dept_map).fillna(risk["department_id"])
employee["department_name"] = employee["department_id"].map(dept_map).fillna(employee["department_id"])

# Filters
st.sidebar.header("Dashboard filters")
available_departments = sorted(
    headcount["department_name"].dropna().astype(str).unique().tolist()
)
selected_departments = st.sidebar.multiselect(
    "Department",
    options=available_departments,
    default=available_departments,
)
min_month = headcount["month_start_date"].min()
max_month = headcount["month_start_date"].max()
if pd.isna(min_month) or pd.isna(max_month):
    st.error("No valid month_start_date values were found.")
    st.stop()
date_range = st.sidebar.date_input(
    "Historical period",
    value=(min_month.date(), max_month.date()),
    min_value=min_month.date(),
    max_value=max_month.date(),
)
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
else:
    start_date, end_date = min_month, max_month

filtered = headcount[
    headcount["department_name"].isin(selected_departments)
    & headcount["month_start_date"].between(start_date, end_date)
].copy()

if filtered.empty:
    st.warning("No monthly records match these filters. Select a wider date range or more departments.")
    st.stop()

# Actual historical metrics
total_exits = int(filtered["exits"].fillna(0).sum())
total_voluntary = int(filtered["voluntary_exits"].fillna(0).sum())
weighted_attrition = safe_pct(
    filtered["exits"].fillna(0).sum(),
    filtered["headcount_start"].fillna(0).sum(),
)
latest_month = filtered["month_start_date"].max()
latest_rows = filtered[filtered["month_start_date"] == latest_month]
latest_start_hc = int(latest_rows["headcount_start"].fillna(0).sum())
latest_end_hc = int(latest_rows["headcount_end"].fillna(0).sum())
latest_exits = int(latest_rows["exits"].fillna(0).sum())

st.subheader("Historical attrition overview")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Recorded exits", f"{total_exits:,}")
m2.metric("Voluntary exits", f"{total_voluntary:,}")
m3.metric("Weighted period attrition", f"{weighted_attrition:.2f}%")
m4.metric(f"Ending headcount Â· {latest_month:%b %Y}", f"{latest_end_hc:,}")

st.caption(
    "Weighted period attrition is calculated as total exits divided by the sum of monthly starting headcount "
    "across the selected department-month rows. It is a period-level analytical ratio, not a cumulative employee probability."
)

monthly = (
    filtered.groupby("month_start_date", as_index=False)
    .agg(
        exits=("exits", "sum"),
        voluntary_exits=("voluntary_exits", "sum"),
        starting_headcount=("headcount_start", "sum"),
        ending_headcount=("headcount_end", "sum"),
    )
    .sort_values("month_start_date")
)
monthly["attrition_rate_pct"] = monthly.apply(
    lambda r: safe_pct(r["exits"], r["starting_headcount"]), axis=1
)
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Monthly recorded exits**")
    fig = px.line(
        monthly, x="month_start_date", y="exits", markers=True,
        labels={"month_start_date": "Month", "exits": "Recorded exits"},
    )
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")
with c2:
    st.markdown("**Monthly attrition rate**")
    fig = px.line(
        monthly, x="month_start_date", y="attrition_rate_pct", markers=True,
        labels={"month_start_date": "Month", "attrition_rate_pct": "Attrition rate (%)"},
    )
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")

st.markdown("**Department comparison**")
dept_summary = (
    filtered.groupby(["department_id", "department_name"], as_index=False)
    .agg(
        exits=("exits", "sum"),
        voluntary_exits=("voluntary_exits", "sum"),
        starting_headcount_months=("headcount_start", "sum"),
    )
)
dept_summary["attrition_rate_pct"] = dept_summary.apply(
    lambda r: safe_pct(r["exits"], r["starting_headcount_months"]), axis=1
)
dept_summary = dept_summary.sort_values("attrition_rate_pct", ascending=False)
fig = px.bar(
    dept_summary, x="department_name", y="attrition_rate_pct",
    hover_data=["exits", "voluntary_exits"],
    labels={"department_name": "Department", "attrition_rate_pct": "Weighted attrition rate (%)"},
)
fig.update_layout(xaxis_tickangle=-35, margin=dict(l=10, r=10, t=20, b=10))
st.plotly_chart(fig, width="stretch")
st.dataframe(
    dept_summary[["department_name", "exits", "voluntary_exits", "starting_headcount_months", "attrition_rate_pct"]]
    .rename(columns={
        "department_name": "Department",
        "exits": "Recorded exits",
        "voluntary_exits": "Voluntary exits",
        "starting_headcount_months": "Sum of monthly starting headcount",
        "attrition_rate_pct": "Weighted attrition rate (%)",
    }).round(2),
    width="stretch",
    hide_index=True,
)

# Tenure at exit: one exit record per employee_id, selecting the earliest valid hire date
st.subheader("Tenure at recorded exit")
st.caption(
    "Tenure uses the employee's earliest recorded hire date and the recorded exit date, deduplicated by employee ID. "
    "This is a descriptive historical view; it does not establish why an employee left."
)
exit_rows = employee[
    employee["exit_date"].notna()
    & employee["employee_id"].notna()
    & employee["hire_date"].notna()
].copy()
if not exit_rows.empty:
    exit_rows = exit_rows.sort_values(["employee_id", "hire_date", "exit_date"])
    # Deduplicate historical SCD rows to one row per employee for this summary.
    exit_rows = exit_rows.groupby("employee_id", as_index=False).agg(
        hire_date=("hire_date", "min"),
        exit_date=("exit_date", "max"),
        employment_status=("employment_status", "last"),
        department_id=("department_id", "last"),
    )
    exit_rows["department_name"] = exit_rows["department_id"].map(dept_map).fillna(exit_rows["department_id"])
    exit_rows["tenure_years"] = (exit_rows["exit_date"] - exit_rows["hire_date"]).dt.days / 365.25
    exit_rows = exit_rows[exit_rows["tenure_years"].between(0, 70)]
    if selected_departments:
        tenure_filtered = exit_rows[exit_rows["department_name"].isin(selected_departments)]
    else:
        tenure_filtered = exit_rows.iloc[0:0]
    if not tenure_filtered.empty:
        tenure_filtered["tenure_band"] = pd.cut(
            tenure_filtered["tenure_years"],
            bins=[-0.01, 1, 3, 5, 10, 70],
            labels=["Under 1 year", "1â€“3 years", "3â€“5 years", "5â€“10 years", "10+ years"],
            include_lowest=True,
        )
        tenure_summary = (
            tenure_filtered.groupby("tenure_band", observed=False)
            .size().rename("recorded_exits").reset_index()
        )
        fig = px.bar(
            tenure_summary, x="tenure_band", y="recorded_exits",
            labels={"tenure_band": "Tenure at exit", "recorded_exits": "Unique employees"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Tenure analysis includes {len(tenure_filtered):,} unique exited employees in the selected departments.")
    else:
        st.info("No exited-employee records match the selected departments.")
else:
    st.info("No usable hire/exit dates were found in dim_employee.csv.")

# Predicted risk is kept separate from historical actual exits.
st.subheader("Predicted 12-month attrition risk")
st.warning(
    "These are model-generated risk signals, not confirmed exits. Do not use them as the sole basis for "
    "employment decisions. This dashboard shows group-level summaries only; it does not rank or display individual employees."
)
if risk.empty or "as_of_date" not in risk.columns or risk["as_of_date"].notna().sum() == 0:
    st.info("No valid risk snapshot date is available.")
else:
    snapshot_date = risk["as_of_date"].max()
    snapshot = risk[risk["as_of_date"] == snapshot_date].copy()
    snapshot = snapshot[snapshot["department_name"].isin(selected_departments)]
    st.caption(f"Risk snapshot date: {snapshot_date:%d %b %Y}. Only this latest snapshot is shown.")
    if snapshot.empty:
        st.info("No risk records match the selected departments for the latest snapshot.")
    else:
        risk_counts = snapshot.groupby("risk_band").size().rename("records").reset_index()
        risk_counts["records"] = risk_counts["records"].astype(int)
        st.markdown("**Risk-band distribution across the selected departments**")
        fig = px.bar(
            risk_counts, x="risk_band", y="records",
            category_orders={"risk_band": ["Low", "Medium", "High"]},
            labels={"risk_band": "Predicted risk band", "records": "Prediction records"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, width="stretch")

        # Department summaries are suppressed below the minimum group size.
        risk_dept = (
            snapshot.groupby(["department_id", "department_name"], as_index=False)
            .agg(prediction_count=("prediction_id", "count"))
        )
        risk_dept["display"] = risk_dept.apply(
            lambda r: f"{int(r['prediction_count'])} records"
            if int(r["prediction_count"]) >= PRIVACY_MIN_GROUP
            else "Suppressed (<5 records)",
            axis=1,
        )
        st.markdown("**Department-level snapshot coverage**")
        st.dataframe(
            risk_dept[["department_name", "display"]].rename(
                columns={"department_name": "Department", "display": "Risk snapshot records"}
            ),
            width="stretch",
            hide_index=True,
        )
        if "risk_score_12m" in snapshot.columns:
            mean_score = snapshot["risk_score_12m"].mean()
            if pd.notna(mean_score):
                st.metric("Mean predicted risk score (selected groups)", f"{mean_score:.1%}")
        st.caption(
            "The risk file contains model predictions. The snapshot may cover only part of the employee population; "
            "prediction counts should not be interpreted as headcount or actual attrition."
        )

# Data-quality and interpretation notes
with st.expander("Data quality, definitions, and limitations"):
    st.markdown(
        """
        - **Actual exits and attrition rates:** sourced from `fact_headcount_monthly.csv`.
        - **Historical tenure:** sourced from `dim_employee.csv`, deduplicated by employee ID for tenure summaries.
        - **Risk predictions:** sourced from `fact_attrition_risk.csv`; latest available `as_of_date` is selected.
        - **Exit reasons:** the supplied employee dimension does not provide a verified exit-reason field. `change_reason` describes dimension-history changes and is not treated as exit reason.
        - **Headcount validation:** the reconciliation formula is `starting headcount + hires + transfers in âˆ’ exits âˆ’ transfers out = ending headcount`.
        - **Rate validation:** the monthly rate is checked as `exits / starting headcount Ã— 100`.
        - **Privacy:** no employee-level names, IDs, or risk scores are displayed. Department-level risk coverage under five records is suppressed.
        - **Interpretation:** a historical department-month rate can be volatile when the starting headcount is small. Review counts and denominators together.
        """
    )

st.divider()
st.caption("PulseIQ Analytics Â· Phase 2 Â· PQ-07 Attrition Analytics")

