from pathlib import Path
import duckdb
import pandas as pd
import streamlit as st
import altair as alt

# ------------------------------------------------------------
# PQ-15 | Executive Company-Health Scorecard Advanced
# Aura Workforce | PulseIQ Analytics
# Uses governed warehouse metric views only (plus official KPI targets).
# ------------------------------------------------------------

st.set_page_config(
    page_title="PQ-15 | Executive Health Scorecard",
    page_icon="📈",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "05_Starter" / "pulseiq_warehouse.duckdb"
TARGET_PATH = ROOT / "03_Data" / "csv" / "kpi_targets.csv"

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.1rem; padding-bottom: 1rem; max-width: 1500px;}
    .kpi-card {
        border: 1px solid rgba(128,128,128,.35);
        border-radius: 10px; padding: 13px 14px; min-height: 178px;
        background: var(--secondary-background-color);
    }
    .kpi-label {font-size: .83rem; opacity: .78; margin-bottom: 5px;}
    .kpi-value {font-size: 1.65rem; font-weight: 700; line-height: 1.2;}
    .kpi-meta {font-size: .78rem; opacity: .8; margin-top: 7px;}
    .kpi-reason {font-size: .79rem; margin-top: 9px; line-height: 1.35;}
    .status-good {color: #16834a; font-weight: 700;}
    .status-watch {color: #b7791f; font-weight: 700;}
    .status-bad {color: #c0392b; font-weight: 700;}
    .status-neutral {opacity: .8; font-weight: 700;}
    .print-note {font-size: .75rem; opacity: .75;}
    @media print {
      @page { size: A4 landscape; margin: 7mm; }
      header, footer, [data-testid="stSidebar"], [data-testid="stToolbar"],
      [data-testid="stDecoration"], [data-testid="stButton"],
      .st-key-screen_only { display: none !important; }
      .st-key-print_scorecard { display: block !important; }
      .block-container { max-width: none !important; padding: 0 !important; }
      .kpi-card { break-inside: avoid; min-height: 112px; padding: 7px 9px; }
      .kpi-value { font-size: 16pt; }
      .kpi-label { font-size: 8pt; }
      .kpi-meta, .kpi-reason { font-size: 7.3pt; }
      .st-key-print_scorecard [data-testid="stHorizontalBlock"] {
        gap: 8px !important;
      }
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container(key="print_scorecard"):
    st.title("PulseIQ Analytics")
    st.subheader("PQ-15 | Executive Company-Health Scorecard Advanced")
    st.caption("Aura Workforce | Governed KPI layer • Executive overview • Human review")

    if not DB_PATH.exists():
        st.error(f"Warehouse database not found: {DB_PATH}")
        st.stop()
    if not TARGET_PATH.exists():
        st.error(f"Official KPI target file not found: {TARGET_PATH}")
        st.stop()


    @st.cache_data
    def load_data(db_path: str, target_path: str):
        con = duckdb.connect(db_path, read_only=True)
        try:
            names = [
                "m01_headcount_governed",
                "m05_attrition_rolling_12m",
                "m09_employer_cost_governed",
                "m11_overtime_share_governed",
                "m13_attendance_rate_governed",
                "m17_net_profit",
                "m21_overdue_receivables",
                "m22_task_completion",
                "dim_sprint",
                "dim_team",
            ]
            data = {
                name: con.execute(f"SELECT * FROM warehouse.{name}").fetchdf()
                for name in names
            }
        finally:
            con.close()

        targets = pd.read_csv(target_path)
        targets["month"] = pd.to_datetime(targets["month"], errors="coerce")
        for frame, col in [
            (data["m01_headcount_governed"], "month_start_date"),
            (data["m05_attrition_rolling_12m"], "month_start_date"),
            (data["m09_employer_cost_governed"], "period_end_date"),
            (data["m11_overtime_share_governed"], "period_end_date"),
            (data["m13_attendance_rate_governed"], "period_end_date"),
            (data["m17_net_profit"], "month_start_date"),
            (data["m21_overdue_receivables"], "report_date"),
            (data["dim_sprint"], "start_date"),
        ]:
            frame[col] = pd.to_datetime(frame[col], errors="coerce")

        return data, targets


    try:
        D, targets = load_data(str(DB_PATH), str(TARGET_PATH))
    except Exception as exc:
        st.error(f"Unable to load governed KPI data: {exc}")
        st.info("Run this dashboard from the PulseIQ project root.")
        st.stop()


    def month_start(value):
        return pd.Timestamp(value).to_period("M").to_timestamp()


    def money(value):
        if pd.isna(value):
            return "—"
        return f"₹{value:,.0f}"


    def pct(value):
        return "—" if pd.isna(value) else f"{value:.2f}%"


    def status_for(value, target, direction="higher"):
        if pd.isna(value) or pd.isna(target):
            return "Not rated", "status-neutral"
        passed = value >= target if direction == "higher" else value <= target
        return ("On target", "status-good") if passed else ("Below target", "status-bad")


    def published(frame):
        if "privacy_status" in frame.columns:
            return frame[frame["privacy_status"].astype(str).str.upper() == "PUBLISHED"].copy()
        return frame.copy()


    # Month selector is limited to the common monthly scorecard period.
    available = sorted(
        set(D["m01_headcount_governed"]["month_start_date"].dropna().map(month_start))
        & set(D["m09_employer_cost_governed"]["period_end_date"].dropna().map(month_start))
        & set(D["m11_overtime_share_governed"]["period_end_date"].dropna().map(month_start))
        & set(D["m13_attendance_rate_governed"]["period_end_date"].dropna().map(month_start))
        & set(D["m17_net_profit"]["month_start_date"].dropna().map(month_start))
    )
    if not available:
        st.error("No common reporting months are available across the required metric views.")
        st.stop()

    default_month = pd.Timestamp("2026-09-01")
    default_index = available.index(default_month) if default_month in available else len(available) - 1

    with st.sidebar:
        st.header("Scorecard controls")
        selected_month = st.selectbox(
            "Reporting month",
            available,
            index=default_index,
            format_func=lambda x: x.strftime("%B %Y"),
        )
        st.caption("Month selector applies to monthly metrics. M21 is a point-in-time snapshot.")
        st.divider()
        st.markdown("**Print**")
        st.caption("Use your browser's Print command and select A4 landscape.")
        st.markdown('<span class="print-note">Detailed KPI navigation is available below the scorecard.</span>',
                    unsafe_allow_html=True)

    month = month_start(selected_month)
    month_end = month + pd.offsets.MonthEnd(0)
    previous_month = month - pd.offsets.MonthBegin(1)


    def month_rows(key, date_col):
        frame = D[key].copy()
        return frame[frame[date_col].map(lambda x: month_start(x) if pd.notna(x) else pd.NaT) == month].copy()


    # M01: published subtotal only; suppressed D00 is excluded and explicitly disclosed.
    hc_all = month_rows("m01_headcount_governed", "month_start_date")
    hc_pub = published(hc_all)
    headcount_value = hc_pub["headcount"].sum(min_count=1) if not hc_pub.empty else float("nan")
    hc_suppressed = int((hc_all.get("privacy_status", pd.Series(dtype=str)).astype(str).str.upper() == "SUPPRESSED").sum())

    # M05: show range and highest department, never average department percentages.
    attr_all = D["m05_attrition_rolling_12m"]
    attr_all = attr_all[attr_all["month_start_date"].map(lambda x: month_start(x) if pd.notna(x) else pd.NaT) == month]
    attr_pub = published(attr_all).dropna(subset=["attrition_rate_12m_pct"])
    if not attr_pub.empty:
        attr_min = attr_pub["attrition_rate_12m_pct"].min()
        attr_max_row = attr_pub.loc[attr_pub["attrition_rate_12m_pct"].idxmax()]
        attr_display = f"{attr_min:.2f}%–{attr_max_row['attrition_rate_12m_pct']:.2f}%"
        attr_detail = f"Highest: {attr_max_row['department_id']} ({attr_max_row['attrition_rate_12m_pct']:.2f}%)"
    else:
        attr_display, attr_detail = "—", "No publishable department values"

    # M09: sum governed department-level values; do not include suppressed groups.
    cost_all = month_rows("m09_employer_cost_governed", "period_end_date")
    cost_pub = published(cost_all)
    cost_value = cost_pub["employer_cost"].sum(min_count=1) if not cost_pub.empty else float("nan")
    cost_suppressed = int((cost_all.get("privacy_status", pd.Series(dtype=str)).astype(str).str.upper() == "SUPPRESSED").sum())

    # M11: department-level target compliance count, not mean of percentages.
    ot_all = month_rows("m11_overtime_share_governed", "period_end_date")
    ot_pub = published(ot_all)
    target_month = targets[targets["month"] == month][["department_id", "overtime_share_target_pct"]]
    ot_check = ot_pub.merge(target_month, on="department_id", how="left")
    ot_check = ot_check.dropna(subset=["overtime_share_pct", "overtime_share_target_pct"])
    ot_pass = int((ot_check["overtime_share_pct"] <= ot_check["overtime_share_target_pct"]).sum())
    ot_total = int(len(ot_check))

    # M13: weighted attendance from official governed scheduled-day denominators.
    att_all = month_rows("m13_attendance_rate_governed", "period_end_date")
    att_pub = published(att_all).dropna(subset=["attendance_rate_pct", "total_scheduled_days"])
    att_pub = att_pub[att_pub["total_scheduled_days"] > 0]
    attendance_value = (
        (att_pub["attendance_rate_pct"] * att_pub["total_scheduled_days"]).sum()
        / att_pub["total_scheduled_days"].sum()
        if not att_pub.empty else float("nan")
    )
    att_check = att_pub.merge(
        targets[targets["month"] == month][["department_id", "attendance_rate_target"]],
        on="department_id", how="left"
    )
    att_pass = int((att_check["attendance_rate_pct"] >= att_check["attendance_rate_target"] * 100).sum())
    att_total = int(att_check["attendance_rate_target"].notna().sum())

    # M17: company-level metric.
    profit = D["m17_net_profit"].copy()
    profit["month_key"] = profit["month_start_date"].map(month_start)
    profit_value_rows = profit[profit["month_key"] == month]
    profit_value = profit_value_rows["net_profit"].sum(min_count=1) if not profit_value_rows.empty else float("nan")
    prev_profit_rows = profit[profit["month_key"] == previous_month]
    prev_profit = prev_profit_rows["net_profit"].sum(min_count=1) if not prev_profit_rows.empty else float("nan")
    profit_delta = (
        (profit_value - prev_profit) / abs(prev_profit) * 100
        if pd.notna(profit_value) and pd.notna(prev_profit) and prev_profit != 0
        else float("nan")
    )

    # M21: point-in-time snapshot only. Do not fabricate a trend for earlier months.
    ar = D["m21_overdue_receivables"].copy()
    ar_dates = sorted(ar["report_date"].dropna().unique())
    ar_snapshot_date = pd.Timestamp(ar_dates[-1]) if ar_dates else pd.NaT
    ar_snapshot = ar[ar["report_date"] == ar_snapshot_date] if pd.notna(ar_snapshot_date) else ar.iloc[0:0]
    ar_value = ar_snapshot["overdue_receivables"].sum(min_count=1) if not ar_snapshot.empty else float("nan")
    ar_clients = ar_snapshot["client_id"].nunique() if not ar_snapshot.empty else 0
    ar_matches_month = pd.notna(ar_snapshot_date) and month_start(ar_snapshot_date) == month

    # M22: latest sprint ending in selected month, aggregate tasks by counts.
    sprints = D["dim_sprint"].copy()
    sprints["end_date"] = pd.to_datetime(sprints["end_date"], errors="coerce")
    sprints_in_month = sprints[sprints["end_date"].map(lambda x: month_start(x) if pd.notna(x) else pd.NaT) == month]
    task_rows = D["m22_task_completion"].merge(
        D["dim_team"][["team_id", "department_id"]], on="team_id", how="left"
    ).merge(
        sprints[["sprint_id", "start_date", "end_date"]], on="sprint_id", how="left"
    )
    task_rows["end_month"] = task_rows["end_date"].map(lambda x: month_start(x) if pd.notna(x) else pd.NaT)
    if not sprints_in_month.empty:
        latest_sprint = sprints_in_month.sort_values("end_date").iloc[-1]
        sprint_id = latest_sprint["sprint_id"]
        sprint_data = published(task_rows[task_rows["sprint_id"] == sprint_id])
        sprint_dept = sprint_data.groupby("department_id", as_index=False).agg(
            planned_tasks=("planned_tasks", "sum"),
            completed_tasks=("completed_tasks", "sum"),
        )
        sprint_dept["completion_pct"] = (
            100 * sprint_dept["completed_tasks"] / sprint_dept["planned_tasks"].replace(0, pd.NA)
        )
        task_targets = targets[targets["month"] == month][
            ["department_id", "task_completion_target_pct"]
        ]
        sprint_dept = sprint_dept.merge(task_targets, on="department_id", how="left")
        valid_task = sprint_dept.dropna(subset=["task_completion_target_pct", "completion_pct"])
        task_value = (
            100 * sprint_data["completed_tasks"].sum() / sprint_data["planned_tasks"].sum()
            if not sprint_data.empty and sprint_data["planned_tasks"].sum() > 0 else float("nan")
        )
        task_pass = int((valid_task["completion_pct"] >= valid_task["task_completion_target_pct"]).sum())
        task_total = int(len(valid_task))
    else:
        latest_sprint, sprint_data, sprint_dept = None, pd.DataFrame(), pd.DataFrame()
        task_value, task_pass, task_total = float("nan"), 0, 0

    # Previous month comparisons for selected monthly metrics.
    def previous_month_sum(key, date_col, value_col, privacy=True):
        frame = D[key].copy()
        frame["month_key"] = frame[date_col].map(lambda x: month_start(x) if pd.notna(x) else pd.NaT)
        frame = frame[frame["month_key"] == previous_month]
        if privacy:
            frame = published(frame)
        return frame[value_col].sum(min_count=1) if not frame.empty else float("nan")

    prev_hc = previous_month_sum("m01_headcount_governed", "month_start_date", "headcount")
    prev_cost = previous_month_sum("m09_employer_cost_governed", "period_end_date", "employer_cost")
    prev_hc_pub = published(month_rows("m01_headcount_governed", "month_start_date"))
    prev_hc_value = prev_hc
    prev_cost_value = prev_cost

    # Compact scorecard helpers.
    def delta_text(current, previous, unit="", inverse=False):
        if pd.isna(current) or pd.isna(previous):
            return "Trend: unavailable"
        change = current - previous
        sign = "+" if change > 0 else ""
        return f"Previous month: {sign}{change:,.2f}{unit}"


    def card(title, metric, value, target, trend, status, reason, key):
        # Keep the entire card in one HTML block. Separate markdown calls caused
        # Streamlit to render the border wrapper as an empty rectangle.
        card_html = f"""
        <div class="kpi-card">
          <div class="kpi-label">{metric} · {title}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-meta">Target: {target} &nbsp; | &nbsp;
            <span class="{status[1]}">{status[0]}</span>
          </div>
          <div class="kpi-meta">{trend}</div>
          <div class="kpi-reason">{reason}</div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
        if st.button(f"Open {metric} details", key=f"open_{key}", use_container_width=True):
            # The selectbox is declared below, so set its state before it renders.
            st.session_state["detail_selector"] = key


    # KPI status logic.
    hc_status = ("Published subtotal", "status-neutral")
    attr_status = ("Department view", "status-neutral")
    cost_status = ("No target defined", "status-neutral")
    ot_status = (f"{ot_pass}/{ot_total} departments on target", "status-good" if ot_total and ot_pass == ot_total else "status-watch")
    att_status = (f"{att_pass}/{att_total} departments on target", "status-good" if att_total and att_pass == att_total else "status-watch")
    profit_status = ("No target defined", "status-neutral")
    ar_status = ("Exposure snapshot", "status-neutral")
    task_status = (f"{task_pass}/{task_total} departments on target", "status-good" if task_total and task_pass == task_total else "status-watch")

    st.markdown(f"**Reporting period:** {month:%B %Y}  ·  **Scorecard refresh:** governed warehouse views")
    st.caption("Suppressed values are excluded from published subtotals. Department percentages are not averaged to create company rates.")

    # Eight KPI cards in a compact 4 x 2 grid.
    rows = [
        [
            ("Headcount", "M01", f"{headcount_value:,.0f}" if pd.notna(headcount_value) else "—",
             "Published departments only", delta_text(headcount_value, prev_hc_value),
             hc_status, "Shows the published workforce subtotal; suppressed groups are excluded.", "headcount"),
            ("Rolling attrition", "M05", attr_display, "No rolling target defined",
             attr_detail, attr_status, "Highlights workforce stability by showing the spread across publishable departments.", "attrition"),
            ("Employer cost", "M09", money(cost_value), "No target defined",
             delta_text(cost_value, prev_cost_value, " INR"), cost_status,
             "Tracks the monthly employer-cost base for financial and workforce planning.", "cost"),
            ("Overtime share", "M11", f"{ot_pass}/{ot_total}", "Department-specific targets",
             "Departments meeting their overtime-share limits", ot_status,
             "Identifies departments exceeding their approved overtime-share thresholds.", "overtime"),
        ],
        [
            ("Attendance", "M13", pct(attendance_value), "94% departmental target",
             f"{att_pass}/{att_total} departments meet target", att_status,
             "Measures workforce availability using scheduled-day-weighted attendance.", "attendance"),
            ("Net profit", "M17", money(profit_value), "No target defined",
             delta_text(profit_value, prev_profit, " INR"), profit_status,
             "Provides the headline monthly financial outcome from the governed ledger metric.", "profit"),
            ("Overdue receivables", "M21", money(ar_value) if ar_matches_month else "Snapshot only",
             "No target defined",
             f"{ar_clients} clients · {ar_snapshot_date:%d %b %Y}" if pd.notna(ar_snapshot_date) else "No snapshot available",
             ar_status, "Shows unpaid balances past due and the collection exposure at the reporting date.", "receivables"),
            ("Task completion", "M22", pct(task_value), "80% for departments with a defined target",
             f"{latest_sprint['sprint_id']} · {latest_sprint['start_date']:%d %b}–{latest_sprint['end_date']:%d %b}" if latest_sprint is not None else "No sprint in selected month",
             task_status, "Measures delivered work against planned work for the latest sprint ending in the selected month.", "tasks"),
        ],
    ]

    for row in rows:
        cols = st.columns(4)
        for col, item in zip(cols, row):
            with col:
                card(*item)


with st.container(key="screen_only"):
    st.markdown("---")
    st.subheader("Executive five-KPI shortlist")
    st.write(
        "**Retain:** M05 Rolling attrition, M09 Employer cost, M17 Net profit, "
        "M21 Overdue receivables, and M22 Task completion."
    )
    st.write(
        "**Remove from the five-KPI view:** M01 Headcount (capacity context), "
        "M11 Overtime share (operational cost driver), and M13 Attendance "
        "(operational input indicator). Keep all eight in the full scorecard."
    )
    st.caption(
        "The shortlist is a management-priority recommendation, not a statistical ranking. "
        "M05 is shown as a department spread, not a company-wide attrition rate."
    )

    # Detail navigation: buttons above set the selected detail key.
    st.markdown("---")
    st.subheader("KPI detail pages")
    detail_options = {
        "headcount": "M01 · Headcount",
        "attrition": "M05 · Rolling attrition",
        "cost": "M09 · Employer cost",
        "overtime": "M11 · Overtime share",
        "attendance": "M13 · Attendance",
        "profit": "M17 · Net profit",
        "receivables": "M21 · Overdue receivables",
        "tasks": "M22 · Task completion",
    }
    if "detail_selector" not in st.session_state:
        st.session_state["detail_selector"] = "profit"
    detail_key = st.selectbox(
        "Choose a KPI detail page",
        list(detail_options.keys()),
        format_func=lambda x: detail_options[x],
        key="detail_selector",
    )

    if detail_key == "headcount":
        st.markdown("**M01 — Published headcount by department**")
        st.dataframe(hc_pub, use_container_width=True, hide_index=True)
        st.caption(f"{hc_suppressed} suppressed department row(s) excluded from the published subtotal.")
    elif detail_key == "attrition":
        st.markdown("**M05 — Rolling 12-month attrition by department**")
        st.dataframe(attr_all, use_container_width=True, hide_index=True)
        st.caption("No company-wide average is calculated. Suppressed rows remain suppressed.")
    elif detail_key == "cost":
        st.markdown("**M09 — Employer cost by department**")
        st.dataframe(cost_all, use_container_width=True, hide_index=True)
        st.caption(f"{cost_suppressed} suppressed department row(s) excluded from the published subtotal.")
    elif detail_key == "overtime":
        st.markdown("**M11 — Overtime share versus departmental targets**")
        st.dataframe(ot_check, use_container_width=True, hide_index=True)
    elif detail_key == "attendance":
        st.markdown("**M13 — Attendance by department**")
        st.dataframe(att_check, use_container_width=True, hide_index=True)
        st.caption("Weighted published-department attendance uses total scheduled days as the denominator.")
    elif detail_key == "profit":
        st.markdown("**M17 — Monthly net profit trend**")
        trend = profit.sort_values("month_start_date")
        chart = alt.Chart(trend).mark_line(point=True).encode(
            x=alt.X("month_start_date:T", title="Month"),
            y=alt.Y("net_profit:Q", title="Net profit (INR)"),
            tooltip=["month_start_date:T", alt.Tooltip("net_profit:Q", format=",.0f")],
        ).properties(height=260)
        st.altair_chart(chart, use_container_width=True)
        st.dataframe(trend[["month_start_date", "net_profit"]].sort_values("month_start_date", ascending=False),
                     use_container_width=True, hide_index=True)
    elif detail_key == "receivables":
        st.markdown("**M21 — Overdue receivables by client**")
        st.dataframe(ar_snapshot, use_container_width=True, hide_index=True)
        st.caption("Only the latest available report date is present in this metric view; no trend is displayed.")
    elif detail_key == "tasks":
        st.markdown("**M22 — Latest sprint department breakdown**")
        if latest_sprint is not None:
            st.caption(f"{latest_sprint['sprint_id']} · {latest_sprint['start_date']:%d %b %Y} to {latest_sprint['end_date']:%d %b %Y}")
            st.dataframe(sprint_dept, use_container_width=True, hide_index=True)
            st.caption("Department task completion is calculated from task counts. D10 is not included because its target is missing.")
        else:
            st.info("No sprint ends in the selected month.")

    st.markdown("---")
    st.caption(
        "Metric source: warehouse governed metric views and official kpi_targets.csv. "
        "M17, M21 and M22 retain their catalog grain and reporting-period limitations."
    )
