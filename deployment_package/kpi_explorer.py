
import streamlit as st
import pandas as pd


# Demo-only role assignments.
# These are examples, not production authentication.
DEMO_ACCESS = {
    "ADMIN": {"department_id": None, "team_id": None},
    "HR": {"department_id": "DEMO-D01", "team_id": None},
    "MANAGER": {"department_id": "DEMO-D01", "team_id": "DEMO-T01"},
    "EXECUTIVE": {"department_id": None, "team_id": None},
}

MIN_GROUP_SIZE = {
    "headcount": 5,
    "attrition": 10,
    "employer_cost": 5,
    "overtime": 5,
    "attendance": 5,
    "task_completion": 5,
}

def is_group_publishable(metric, group_size):
    """Return whether a metric group meets its minimum privacy threshold."""
    if metric not in MIN_GROUP_SIZE:
        raise ValueError(f"Unknown metric: {metric}")

    if group_size < 0:
        raise ValueError("Group size cannot be negative.")

    return group_size >= MIN_GROUP_SIZE[metric]


def complementary_suppression(group_sizes, minimum_size):
    """
    Return suppression flags for sibling groups.

    Primary suppression hides groups below the threshold.
    If exactly one group is hidden, hide the smallest visible sibling too.
    This protects a total from revealing the hidden group's value
    by subtraction.
    """
    if minimum_size < 1:
        raise ValueError("Minimum size must be at least 1.")

    if any(size < 0 for size in group_sizes):
        raise ValueError("Group sizes cannot be negative.")

    suppressed = [size < minimum_size for size in group_sizes]

    if sum(suppressed) == 1:
        visible_indices = [
            index for index, hidden in enumerate(suppressed)
            if not hidden
        ]

        if visible_indices:
            smallest_index = min(
                visible_indices,
                key=lambda index: group_sizes[index],
            )
            suppressed[smallest_index] = True

    return suppressed


def _period_filter(frame, column, period):
    if frame.empty or column not in frame.columns:
        return frame.iloc[0:0].copy()

    dates = pd.to_datetime(frame[column], errors="coerce")
    return frame.loc[dates.dt.to_period("M") == period].copy()


def _is_published(frame, value_column):
    if frame.empty:
        return frame.copy()

    result = frame.copy()

    if "privacy_status" in result.columns:
        result = result[result["privacy_status"] == "PUBLISHED"]

    if value_column in result.columns:
        result = result[result[value_column].notna()]

    return result


def _suppress(message="This result is hidden because the group is below the privacy threshold."):
    st.warning(message)
    st.caption("The exact group size and suppressed value are not displayed.")

def _safe_group_ids(frame, group_column, size_column, minimum_size):
    """
    Return group IDs safe to display after primary and
    complementary suppression.
    """
    if frame.empty:
        return [], True

    if group_column not in frame.columns:
        return [], True

    if size_column not in frame.columns:
        return [], True

    group_sizes = (
        frame.groupby(group_column, dropna=True)[size_column]
        .sum()
    )

    if group_sizes.empty:
        return [], True

    group_ids = group_sizes.index.tolist()
    sizes = group_sizes.tolist()

    suppressed = complementary_suppression(
        sizes,
        minimum_size,
    )

    safe_ids = [
        group_id
        for group_id, hidden in zip(group_ids, suppressed)
        if not hidden
    ]

    return safe_ids, any(suppressed)

def _company_release_allowed(
    frame,
    group_column,
    size_column,
    minimum_size,
    metric_label,
):
    """
    Conservatively block company totals if any department
    requires primary or complementary suppression.
    """
    safe_ids, has_suppressed_groups = _safe_group_ids(
        frame,
        group_column,
        size_column,
        minimum_size,
    )

    if has_suppressed_groups:
        _suppress(
            f"Company {metric_label} is hidden because one or "
            "more departments do not meet the privacy requirements."
        )
        return False

    if not safe_ids:
        st.info(f"No eligible department data is available for {metric_label}.")
        return False

    return True




def render_kpi_explorer(data, selected_month, role):
    """
    Render the synthetic self-service KPI explorer.

    `data` is the existing dictionary returned by load_data() in app.py.
    `selected_month` is the selected reporting month.
    """

    st.divider()
    st.header("Self-Service KPI Explorer")

    st.warning(
        "Demo role simulation only. This public demo does not provide "
        "production authentication or authorization.")

    access = DEMO_ACCESS[role]
    period = pd.Timestamp(selected_month).to_period("M")

    st.caption(
        f"Role: {role} | Reporting period: {period.strftime('%B %Y')}"
    )

    # Define the metrics available to each role.
    role_metrics = {
        "ADMIN": [
            "Headcount",
            "Rolling 12-month attrition",
            "Employer cost",
            "Overtime share",
            "Attendance rate",
            "Task completion",
            "Net profit",
            "Overdue receivables",
        ],
        "HR": [
            "Headcount",
            "Rolling 12-month attrition",
            "Employer cost",
            "Overtime share",
            "Attendance rate",
        ],
        "MANAGER": [
            "Task completion",
        ],
        "EXECUTIVE": [
            "Headcount",
            "Employer cost",
            "Attendance rate",
            "Task completion",
            "Net profit",
            "Overdue receivables",
        ],
    }

    metric = st.selectbox(
        "Choose a KPI",
        role_metrics[role],
        key="kpi_explorer_metric",
    )

    metric_key = {
        "Headcount": "headcount",
        "Rolling 12-month attrition": "attrition",
        "Employer cost": "employer_cost",
        "Overtime share": "overtime",
        "Attendance rate": "attendance",
        "Task completion": "task_completion",
        "Net profit": "net_profit",
        "Overdue receivables": "overdue_receivables",
    }[metric]

    # Roles are restricted to permitted hierarchy levels.
    if role == "EXECUTIVE":
        level = "Company"
    elif role == "HR":
        level = "Department"
    elif role == "MANAGER":
        level = "Team"
    else:
        allowed_levels = ["Company", "Department"]

        if metric_key == "task_completion":
            allowed_levels.append("Team")

        level = st.selectbox(
            "Drill-down level",
            allowed_levels,
            key="kpi_explorer_level",
        )

    # ---------------------------------------------------------
    # HEADCOUNT
    # ---------------------------------------------------------
    if metric_key == "headcount":
        frame = _period_filter(
            data["m01_headcount_governed"],
            "month_start_date",
            period,
        )

        frame = _is_published(frame, "headcount")

        if level == "Company":
            allowed = _company_release_allowed(
                frame,
                group_column="department_id",
                size_column="headcount",
                minimum_size=MIN_GROUP_SIZE["headcount"],
                metric_label="headcount",
            )

            if not allowed:
                return

            total = frame["headcount"].sum()

            if total < MIN_GROUP_SIZE["headcount"]:
                _suppress()
            else:
                st.metric(
                    "Company headcount",
                    f"{int(total):,}",
                )
        else:
            departments, has_suppressed_groups = _safe_group_ids(
                frame,
    group_column="department_id",
    size_column="headcount",
    minimum_size=MIN_GROUP_SIZE["headcount"],
)

            if has_suppressed_groups:
                st.info(
                    "Some departments are hidden to protect small-group privacy."
                )

            if not departments:
                st.info("No eligible department data is available.")
                return

            if role == "HR":
                department_id = access["department_id"]

                if department_id not in departments:
                    _suppress(
                        "Your assigned department is hidden because it "
                        "does not meet the privacy requirements."
                    )
                    return
            else:
                department_id = st.selectbox(
                    "Choose department",
                    departments,
                    key="kpi_headcount_department",
                )


            selected = frame[
                frame["department_id"] == department_id
            ]


    # ---------------------------------------------------------
    # ROLLING 12-MONTH ATTRITION
    # ---------------------------------------------------------
    elif metric_key == "attrition":
        frame = _period_filter(
            data["m05_attrition_rolling_12m"],
            "month_start_date",
            period,
        )
        frame = _is_published(
            frame,
            "attrition_rate_12m_pct",
        )

        headcount_frame = _period_filter(
            data["m01_headcount_governed"],
            "month_start_date",
            period,
        )
        headcount_frame = _is_published(
            headcount_frame,
            "headcount",
        )

        if frame.empty or headcount_frame.empty:
            st.info("No published attrition data is available.")
            return

        if level != "Department":
            st.info(
                "Company-level attrition is unavailable because the "
                "demo does not contain the underlying leaver and "
                "average-headcount components needed for a reliable "
                "company calculation."
            )
            return

        departments, has_suppressed_groups = _safe_group_ids(
            headcount_frame,
            group_column="department_id",
            size_column="headcount",
            minimum_size=MIN_GROUP_SIZE["attrition"],
        )

        if has_suppressed_groups:
            st.info(
                "Some departments are hidden to protect small-group privacy."
            )

        if role == "HR":
            department_id = access["department_id"]

            if department_id not in departments:
                _suppress(
                    "This department's attrition data is hidden "
                    "because it does not meet the privacy requirements."
                )
                return
        else:
            if not departments:
                st.info("No eligible attrition data is available.")
                return

            department_id = st.selectbox(
                "Choose department",
                departments,
                key="kpi_attrition_department",
            )

        selected = frame[
            frame["department_id"] == department_id
        ]
        hc = headcount_frame[
            headcount_frame["department_id"] == department_id
        ]

        if selected.empty or hc.empty:
            st.info("No published attrition data is available.")
            return

        group_size = hc["headcount"].sum()

        if group_size < MIN_GROUP_SIZE["attrition"]:
            _suppress()
            return

        value = selected["attrition_rate_12m_pct"].iloc[0]

        st.metric(
            f"Rolling 12-month attrition — {department_id}",
            f"{value:.2f}%",
        )

    # ---------------------------------------------------------
    # EMPLOYER COST
    # ---------------------------------------------------------
    elif metric_key == "employer_cost":
        frame = _period_filter(
            data["m09_employer_cost_governed"],
        "period_end_date",
            period,
        )

        frame = _is_published(frame, "employer_cost")

        if frame.empty:
            st.info("No published employer cost data is available.")
            return

        if level == "Company":
            allowed = _company_release_allowed(
                frame,
                group_column="department_id",
                size_column="employee_count",
                minimum_size=MIN_GROUP_SIZE["employer_cost"],
                metric_label="employer cost",
            )

            if not allowed:
                return

            total_count = frame["employee_count"].sum()
            total = frame["employer_cost"].sum()

            if total_count < MIN_GROUP_SIZE["employer_cost"]:
                _suppress()
            else:
                st.metric(
                    "Company employer cost",
                    f"₹{total:,.2f}",
                )

        else:
            departments, has_suppressed_groups = _safe_group_ids(
                frame,
                group_column="department_id",
                size_column="employee_count",
                minimum_size=MIN_GROUP_SIZE["employer_cost"],
            )

            if has_suppressed_groups:
                st.info(
                    "Some departments are hidden to protect small-group privacy."
                )

            if not departments:
                st.info("No eligible department data is available.")
                return

            if role == "HR":
                department_id = access["department_id"]

                if department_id not in departments:
                    _suppress(
                        "This department is hidden because it does not "
                        "meet the privacy requirements.")
                    return
            else:
                department_id = st.selectbox(
                    "Choose department",
                    departments,
                    key="kpi_cost_department",
                )
            selected = frame[
                frame["department_id"] == department_id
            ]

            if selected.empty:
                st.info("No published headcount data is available.")
                return

            group_size = selected["employee_count"].sum()

            if group_size < MIN_GROUP_SIZE["employer_cost"]:
                _suppress()
            else:
                total = selected["employer_cost"].sum()

                st.metric(
                    f"Employer cost — {department_id}",
                    f"₹{total:,.2f}",
                )


    # ---------------------------------------------------------
    # OVERTIME SHARE
    # ---------------------------------------------------------
    elif metric_key == "overtime":
        frame = _period_filter(
            data["m11_overtime_share_governed"],
            "period_end_date",
            period,
        )

        frame = _is_published(frame, "overtime_share_pct")

        if frame.empty:
            st.info("No published overtime data is available.")
            return

        if level != "Department":
            st.info(
                "Company-level overtime share is unavailable because "
                "the synthetic demo lacks the underlying overtime-pay "
                "and employer-cost components."
            )
            return

        departments, has_suppressed_groups = _safe_group_ids(
            frame,
            group_column="department_id",
            size_column="employees_paid",
            minimum_size=MIN_GROUP_SIZE["overtime"],
        )

        if has_suppressed_groups:
            st.info(
                "Some departments are hidden to protect small-group privacy."
            )

        if role == "HR":
            department_id = access["department_id"]

            if department_id not in departments:
                _suppress(
                    "This department's overtime data is hidden because "
                    "it does not meet the privacy requirements."
                )
                return
        else:
            if not departments:
                st.info("No eligible overtime data is available.")
                return

            department_id = st.selectbox(
                "Choose department",
                departments,
                key="kpi_overtime_department",
            )

        selected = frame[
            frame["department_id"] == department_id
        ]

        if selected.empty:
            st.info("No published overtime data is available.")
            return

        group_size = selected["employees_paid"].sum()

        if group_size < MIN_GROUP_SIZE["overtime"]:
            _suppress()
        else:
            value = selected["overtime_share_pct"].iloc[0]

            st.metric(
                f"Overtime share — {department_id}",
                f"{value:.2f}%",
            )

    # ---------------------------------------------------------
    # ATTENDANCE RATE
    # ---------------------------------------------------------
    elif metric_key == "attendance":
        frame = _period_filter(
            data["m13_attendance_rate_governed"],
            "period_end_date",
            period,
        )
        frame = _is_published(frame, "attendance_rate_pct")

        if frame.empty:
            st.info("No published attendance data is available.")
            return

        if level == "Company":
            allowed = _company_release_allowed(
                frame,
                group_column="department_id",
                size_column="employee_count",
                minimum_size=MIN_GROUP_SIZE["attendance"],
                metric_label="attendance",
            )

            if not allowed:
                return

            employee_count = frame["employee_count"].sum()
            scheduled_days = frame["total_scheduled_days"].sum()

            if employee_count < MIN_GROUP_SIZE["attendance"]:
                _suppress()
                return

            if scheduled_days <= 0:
                st.info("Attendance denominator is unavailable.")
                return

            weighted_rate = (
                frame["attendance_rate_pct"]
                .mul(frame["total_scheduled_days"])
                .sum()
                / scheduled_days
            )

            st.metric(
                "Company attendance rate",
                f"{weighted_rate:.2f}%",
            )

        else:
            departments, has_suppressed_groups = _safe_group_ids(
                frame,
                group_column="department_id",
                size_column="employee_count",
                minimum_size=MIN_GROUP_SIZE["attendance"],
            )

            if has_suppressed_groups:
                st.info(
                    "Some departments are hidden to protect small-group privacy."
                )
            if role == "HR":
                department_id = access["department_id"]

                if department_id not in departments:
                    _suppress(
                        "This department is hidden because it does not "
                        "meet the privacy requirements."
                    )
                    return

            else:
                if not departments:
                    st.info("No eligible department data is available.")
                    return

                department_id = st.selectbox(
                    "Choose department",
                    departments,
                    key="kpi_attendance_department",
                )

            selected = frame[
                frame["department_id"] == department_id
            ]

            if selected.empty:
                st.info("No published headcount data is available.")
                return

            employee_count = selected["employee_count"].sum()
            scheduled_days = selected["total_scheduled_days"].sum()

            if employee_count < MIN_GROUP_SIZE["attendance"]:
                _suppress()
                return

            if scheduled_days <= 0:
                st.info("Attendance denominator is unavailable.")
                return

            value = (
                selected["attendance_rate_pct"]
                .mul(selected["total_scheduled_days"])
                .sum()
                / scheduled_days
            )

            st.metric(
                f"Attendance rate — {department_id}",
                f"{value:.2f}%",
            )

    # ---------------------------------------------------------
    # TASK COMPLETION
    # ---------------------------------------------------------
    elif metric_key == "task_completion":
        tasks = data["m22_task_completion"].copy()
        teams = data["dim_team"].copy()
        sprints = data["dim_sprint"].copy()

        sprint_month = _period_filter(
            sprints,
            "end_date",
            period,
        )

        if sprint_month.empty:
            st.info("No sprint ended in the selected reporting month.")
            return

        latest_sprint = sprint_month.sort_values("end_date").iloc[-1]
        sprint_id = latest_sprint["sprint_id"]

        frame = tasks[tasks["sprint_id"] == sprint_id].copy()
        frame = _is_published(frame, "completion_rate_pct")

        frame = frame.merge(
            teams[["team_id", "department_id"]],
            on="team_id",
            how="left",
            validate="many_to_one",
        )

        frame = frame.dropna(subset=["department_id"])

        if frame.empty:
            st.info("No published task completion data is available.")
            return

        minimum_tasks = MIN_GROUP_SIZE["task_completion"]

        # Team-level view

        # Team-level view
        if level == "Team":
            if role == "MANAGER":
                team_id = access["team_id"]

                selected = frame[
                    frame["team_id"] == team_id
                ]

                if selected.empty:
                    st.info(
                        "No published task data is available for your assigned team."
                    )
                    return

                team_task_count = selected["planned_tasks"].sum()

                if (
                    pd.isna(team_task_count)
                    or team_task_count < minimum_tasks
                ):
                    _suppress(
                        "Team task completion is hidden because fewer "
                        "than 5 planned tasks are included."
                    )
                    return

            else:
                available_teams, has_suppressed_groups = _safe_group_ids(
                    frame,
                    group_column="team_id",
                    size_column="planned_tasks",
                    minimum_size=minimum_tasks,
                )

                if has_suppressed_groups:
                    st.info(
                        "Some teams are hidden to protect small-group privacy."
                    )

                if not available_teams:
                    st.info("No eligible team task data is available.")
                    return

                team_id = st.selectbox(
                    "Choose team",
                    available_teams,
                    key="kpi_task_team",
                )

                selected = frame[
                    frame["team_id"] == team_id
                ]


        # Department-level view
        elif level == "Department":
            departments, has_suppressed_groups = _safe_group_ids(
                frame,
                group_column="department_id",
                size_column="planned_tasks",
                minimum_size=minimum_tasks,
            )

            if has_suppressed_groups:
                st.info(
                    "Some departments are hidden to protect small-group privacy."
                )

            if not departments:
                st.info("No eligible department task data is available.")
                return

            department_id = st.selectbox(
                "Choose department",
                departments,
                key="kpi_task_department",
            )

            selected = frame[
                frame["department_id"] == department_id
            ]

        # Company-level view
        else:
            departments, has_suppressed_groups = _safe_group_ids(
                frame,
                group_column="department_id",
                size_column="planned_tasks",
                minimum_size=minimum_tasks,
            )

            if has_suppressed_groups:
                _suppress(
                    "Company task completion is hidden because one or "
                    "more departments do not meet the minimum group size."
                )
                return

            if not departments:
                st.info("No eligible company task data is available.")
                return

            selected = frame

        if selected.empty:
            st.info("No eligible task completion data is available.")
            return

        planned = selected["planned_tasks"].sum()
        completed = selected["completed_tasks"].sum()

        if pd.isna(planned) or planned < minimum_tasks:
            _suppress(
                "Task completion is hidden because fewer than "
                "5 planned tasks are included."
            )
            return

        if pd.isna(completed) or planned <= 0:
            st.info("Task completion denominator is unavailable.")
            return

        rate = completed / planned * 100

        st.metric(
            f"Task completion — {level}",
            f"{rate:.2f}%",
        )

        st.caption(
            f"Sprint: {sprint_id} | "
            "Only aggregate task counts are displayed."
        )


    # ---------------------------------------------------------
    # COMPANY-ONLY FINANCIAL METRICS
    # ---------------------------------------------------------
    elif metric_key == "net_profit":
        frame = _period_filter(
            data["m17_net_profit"],
            "month_start_date",
            period,
        )

        if frame.empty:
            st.info("No net profit data is available.")
        else:
            total = frame["net_profit"].sum()
            st.metric("Company net profit", f"INR{total:,.2f}")

    elif metric_key == "overdue_receivables":
        frame = data["m21_overdue_receivables"].copy()

        if frame.empty:
            st.info("No receivables data is available.")
        else:
            latest_date = frame["report_date"].max()
            latest = frame[
                frame["report_date"] == latest_date
            ]
            total = latest["overdue_receivables"].sum()

            st.metric("Overdue receivables", f"INR{total:,.2f}")
