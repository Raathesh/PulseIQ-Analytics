
import pandas as pd
import numpy as np
from pathlib import Path

# ============================================================
# PQ-13 | Department-Month Cross-Functional Analytics
# Independent ETL - Aura Workforce / PulseIQ Analytics
# Reporting period: April 2025 to September 2026
# ============================================================

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "03_Data" / "csv"
OUTPUT = ROOT / "03_Data" / "processed"

OUTPUT.mkdir(parents=True, exist_ok=True)

START_MONTH = pd.Timestamp("2025-04-01")
END_MONTH = pd.Timestamp("2026-09-01")
REPORT_END = pd.Timestamp("2026-09-30")

# Confirmed synthetic duplicate payroll rows from source inspection.
SYNTHETIC_DUPLICATE_IDS = {"PI-X0001", "PI-X0002"}

def read_csv(name):
    path = SOURCE / name
    if not path.exists():
        raise FileNotFoundError(f"Required source file not found: {path}")
    return pd.read_csv(path)

def require_columns(df, columns, label):
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")

def largest_remainder(total, weights):
    """Allocate an integer total across buckets while preserving the total."""
    weights = np.asarray(weights, dtype=float)
    if total < 0 or np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Invalid total or allocation weights.")
    raw = total * weights / weights.sum()
    base = np.floor(raw).astype(int)
    remainder = int(total - base.sum())
    if remainder:
        order = np.argsort(-(raw - base), kind="stable")
        base[order[:remainder]] += 1
    return base

# -----------------------------
# 1. Load source datasets
# -----------------------------
payroll = read_csv("fact_payroll.csv")
attendance = read_csv("fact_attendance_monthly.csv")
leave = read_csv("fact_leave.csv")
headcount = read_csv("fact_headcount_monthly.csv")
employee = read_csv("dim_employee.csv")
dim_date = read_csv("dim_date.csv")
department = read_csv("dim_department.csv")

require_columns(
    payroll,
    [
        "payroll_item_id", "employee_id", "employee_key",
        "period_end_date", "department_id", "overtime_hours_paid",
        "overtime_pay", "gross_pay", "net_pay", "employer_cost"
    ],
    "fact_payroll"
)
require_columns(
    attendance,
    [
        "employee_id", "department_id", "period_end_date",
        "scheduled_days", "present_days", "wfh_days",
        "paid_leave_days", "unpaid_absence_days",
        "overtime_hours", "attendance_rate"
    ],
    "fact_attendance_monthly"
)
require_columns(
    leave,
    [
        "leave_request_id", "employee_id", "employee_key",
        "leave_type_code", "start_date", "end_date", "days", "status"
    ],
    "fact_leave"
)
require_columns(
    headcount,
    [
        "month_start_date", "department_id", "headcount_start",
        "hires", "exits", "voluntary_exits", "transfers_in",
        "transfers_out", "headcount_end", "attrition_rate_monthly_pct"
    ],
    "fact_headcount_monthly"
)
require_columns(
    employee,
    ["employee_key", "employee_id", "department_id"],
    "dim_employee"
)
require_columns(
    dim_date,
    ["date", "year_month", "is_weekend", "is_working_day"],
    "dim_date"
)
require_columns(
    department,
    ["department_id", "department_name"],
    "dim_department"
)

# -----------------------------
# 2. Normalize dates and keys
# -----------------------------
payroll["period_end_date"] = pd.to_datetime(
    payroll["period_end_date"], errors="raise"
)
attendance["period_end_date"] = pd.to_datetime(
    attendance["period_end_date"], errors="raise"
)
leave["start_date"] = pd.to_datetime(leave["start_date"], errors="coerce")
leave["end_date"] = pd.to_datetime(leave["end_date"], errors="coerce")
dim_date["date"] = pd.to_datetime(dim_date["date"], errors="raise")
headcount["month_start_date"] = pd.to_datetime(
    headcount["month_start_date"], errors="raise"
)

for frame in [payroll, attendance, leave, employee, headcount, department]:
    if "department_id" in frame.columns:
        frame["department_id"] = frame["department_id"].astype(str)

employee["employee_key"] = pd.to_numeric(
    employee["employee_key"], errors="raise"
)
leave["employee_key"] = pd.to_numeric(
    leave["employee_key"], errors="raise"
)
payroll["employee_key"] = pd.to_numeric(
    payroll["employee_key"], errors="coerce"
)

dim_date["is_weekend"] = (
    dim_date["is_weekend"].astype(str).str.upper()
)
dim_date["is_working_day"] = (
    dim_date["is_working_day"].astype(str).str.upper()
)
dim_date["year_month"] = dim_date["date"].dt.to_period("M").astype(str)

# All date-dimension dates must be unique.
if dim_date["date"].duplicated().any():
    raise ValueError("dim_date contains duplicate dates.")

# -----------------------------
# 3. Payroll quality treatment
# -----------------------------
duplicate_rows = payroll[
    payroll["payroll_item_id"].isin(SYNTHETIC_DUPLICATE_IDS)
].copy()

found_ids = set(duplicate_rows["payroll_item_id"].astype(str))
if found_ids != SYNTHETIC_DUPLICATE_IDS:
    raise ValueError(
        "Expected synthetic payroll duplicate IDs were not all found. "
        f"Found: {sorted(found_ids)}"
    )

# Verify each synthetic row has an original matching record on all
# business/pay components, excluding payroll_item_id.
for synthetic_id in sorted(SYNTHETIC_DUPLICATE_IDS):
    row = payroll.loc[
        payroll["payroll_item_id"].astype(str).eq(synthetic_id)
    ].iloc[0]
    candidates = payroll[
        payroll["payroll_item_id"].astype(str).ne(synthetic_id)
    ]
    match = candidates[
        candidates["employee_id"].eq(row["employee_id"])
        & candidates["run_id"].eq(row["run_id"])
        & candidates["period_end_date"].eq(row["period_end_date"])
        & candidates["department_id"].eq(row["department_id"])
        & np.isclose(candidates["gross_pay"], row["gross_pay"])
        & np.isclose(candidates["employer_cost"], row["employer_cost"])
        & np.isclose(candidates["overtime_pay"], row["overtime_pay"])
    ]
    if match.empty:
        raise ValueError(
            f"Synthetic duplicate {synthetic_id} has no matching original row."
        )

payroll_clean = payroll[
    ~payroll["payroll_item_id"].astype(str).isin(SYNTHETIC_DUPLICATE_IDS)
].copy()

if payroll_clean["payroll_item_id"].duplicated().any():
    raise ValueError("Payroll still contains duplicate payroll_item_id values.")

payroll_clean["month_start_date"] = (
    payroll_clean["period_end_date"].dt.to_period("M").dt.to_timestamp()
)
payroll_clean = payroll_clean[
    payroll_clean["month_start_date"].between(START_MONTH, END_MONTH)
].copy()

payroll_month = payroll_clean.groupby(
    ["department_id", "month_start_date"], as_index=False
).agg(
    payroll_rows=("payroll_item_id", "count"),
    payroll_employee_count=("employee_id", "nunique"),
    payroll_gross_pay=("gross_pay", "sum"),
    payroll_net_pay=("net_pay", "sum"),
    overtime_hours_paid=("overtime_hours_paid", "sum"),
    overtime_cost=("overtime_pay", "sum"),
    employer_cost=("employer_cost", "sum")
)

# -----------------------------
# 4. Attendance aggregation
# -----------------------------
attendance["month_start_date"] = (
    attendance["period_end_date"].dt.to_period("M").dt.to_timestamp()
)
attendance_period = attendance[
    attendance["month_start_date"].between(START_MONTH, END_MONTH)
].copy()

attendance_month = attendance.groupby(
    ["department_id", "month_start_date"],
    as_index=False
).agg(
    scheduled_days=("scheduled_days", "sum"),
    present_days=("present_days", "sum"),
    wfh_days=("wfh_days", "sum"),
    paid_leave_days=("paid_leave_days", "sum"),
    unpaid_absence_days=("unpaid_absence_days", "sum"),
    late_arrivals=("late_arrivals", "sum"),
    attendance_overtime_hours=("overtime_hours", "sum"),
    attendance_rate_weighted=(
        "attendance_rate",
        lambda x: np.average(
            x,
            weights=attendance.loc[x.index, "scheduled_days"]
        )
    )
)




# -----------------------------
# 5. Allocate approved leave to months
# -----------------------------
approved = leave[leave["status"].astype(str).str.strip().eq("Approved")].copy()

# Exclude only the confirmed reversed-date record from allocation.
invalid_leave = approved[
    approved["start_date"].isna()
    | approved["end_date"].isna()
    | approved["end_date"].lt(approved["start_date"])
].copy()

valid_leave = approved.drop(index=invalid_leave.index).copy()

# Historical employee key is unique in the SCD dimension.
if employee["employee_key"].duplicated().any():
    raise ValueError("dim_employee.employee_key is not unique.")

employee_map = employee[
    ["employee_key", "employee_id", "department_id"]
].copy()

valid_leave = valid_leave.merge(
    employee_map,
    on="employee_key",
    how="left",
    suffixes=("_leave", "_dimension"),
    validate="many_to_one",
    indicator=True
)

if not valid_leave["_merge"].eq("both").all():
    bad = valid_leave.loc[
        valid_leave["_merge"].ne("both"),
        ["leave_request_id", "employee_id_leave", "employee_key"]
    ]
    raise ValueError(f"Unmapped approved leave rows:\n{bad.to_string(index=False)}")

# Check employee ID consistency on the dimension-key mapping.
id_mismatch = valid_leave[
    valid_leave["employee_id_leave"].astype(str)
    != valid_leave["employee_id_dimension"].astype(str)
]
if not id_mismatch.empty:
    raise ValueError(
        "Leave employee_id does not agree with employee_key dimension mapping."
    )

valid_leave["department_id"] = valid_leave["department_id"].astype(str)

date_lookup = dim_date.set_index("date")
allocation_rows = []
leave_audit_rows = []

for _, req in valid_leave.iterrows():
    start = req["start_date"]
    end = req["end_date"]
    leave_type = str(req["leave_type_code"])
    recorded_days = int(req["days"])
    department_id = req["department_id"]

    period_dates = date_lookup.loc[
        (date_lookup.index >= start) & (date_lookup.index <= end)
    ].copy()

    if period_dates.empty:
        raise ValueError(
            f"No date-dimension dates for leave request {req['leave_request_id']}."
        )

    # ML: source's 130 days reconcile to weekdays (weekends excluded),
    # with holidays included. Other leave types use is_working_day.
    if leave_type == "ML":
        eligible = period_dates[
            period_dates["is_weekend"].eq("N")
        ]
    else:
        eligible = period_dates[
            period_dates["is_working_day"].eq("Y")
        ]

    expected_days = len(eligible)

    if leave_type != "ML" and recorded_days != expected_days:
        raise ValueError(
            f"Leave-day mismatch for {req['leave_request_id']}: "
            f"recorded={recorded_days}, date-dimension working days={expected_days}"
        )

    if leave_type == "ML" and recorded_days != 130:
        raise ValueError(
            f"Unexpected maternity leave total for {req['leave_request_id']}: "
            f"{recorded_days}"
        )

    # Build weights across the entire request period, including months
    # beyond the dashboard cutoff. This preserves the original ML total.
    monthly_weights = eligible.groupby(
        eligible.index.to_period("M").astype(str)
    ).size()

    if monthly_weights.empty or monthly_weights.sum() <= 0:
        raise ValueError(
            f"No eligible dates for leave request {req['leave_request_id']}."
        )

    if leave_type == "ML":
        monthly_allocations = largest_remainder(
            recorded_days, monthly_weights.to_numpy()
        )
        allocated_by_month = dict(
            zip(monthly_weights.index.tolist(), monthly_allocations.tolist())
        )
        if sum(allocated_by_month.values()) != recorded_days:
            raise AssertionError("Maternity allocation does not preserve 130 days.")
    else:
        allocated_by_month = monthly_weights.astype(int).to_dict()
        if sum(allocated_by_month.values()) != recorded_days:
            raise AssertionError(
                f"Leave allocation does not reconcile for {req['leave_request_id']}."
            )

    in_scope_allocated = 0
    for month_text, allocated_days in allocated_by_month.items():
        month_start = pd.Period(month_text, freq="M").to_timestamp()
        if START_MONTH <= month_start <= END_MONTH and allocated_days > 0:
            allocation_rows.append({
                "department_id": department_id,
                "month_start_date": month_start,
                "allocated_leave_days": int(allocated_days),
                "leave_request_id": req["leave_request_id"],
                "leave_type_code": leave_type
            })
            in_scope_allocated += int(allocated_days)

    leave_audit_rows.append({
        "leave_request_id": req["leave_request_id"],
        "employee_id": req["employee_id_leave"],
        "employee_key": req["employee_key"],
        "department_id": department_id,
        "leave_type_code": leave_type,
        "start_date": start,
        "end_date": end,
        "recorded_days": recorded_days,
        "eligible_calendar_days": expected_days,
        "allocated_days_full_request": int(sum(allocated_by_month.values())),
        "allocated_days_in_reporting_period": in_scope_allocated
    })

leave_allocations = pd.DataFrame(allocation_rows)
leave_audit = pd.DataFrame(leave_audit_rows)

if leave_allocations.empty:
    raise ValueError("No leave allocations were produced.")

leave_month = leave_allocations.groupby(
    ["department_id", "month_start_date"], as_index=False
).agg(
    approved_leave_days=("allocated_leave_days", "sum"),
    allocated_leave_request_months=("leave_request_id", "nunique")
)

# -----------------------------
# 6. Headcount aggregation
# -----------------------------
headcount_scope = headcount[
    headcount["month_start_date"].between(START_MONTH, END_MONTH)
].copy()

if headcount_scope.duplicated(
    ["department_id", "month_start_date"]
).any():
    raise ValueError("Headcount contains duplicate department-month rows.")

headcount_month = headcount_scope[
    [
        "department_id", "month_start_date",
        "headcount_start", "hires", "exits", "voluntary_exits",
        "transfers_in", "transfers_out", "headcount_end",
        "attrition_rate_monthly_pct"
    ]
].copy()

headcount_month["average_headcount"] = (
    headcount_month["headcount_start"]
    + headcount_month["headcount_end"]
) / 2

# -----------------------------
# 7. Join only department-month aggregates
# -----------------------------
# Payroll periods define the 18-month reporting population.
# Headcount supplies the complete 11-department x 18-month grid.
# Add each independently aggregated fact table to that reporting spine.
result = headcount_month.merge(
    payroll_month,
    on=["department_id", "month_start_date"],
    how="left",
    validate="one_to_one"
)

result = result.merge(
    attendance_month,
    on=["department_id", "month_start_date"],
    how="left",
    validate="one_to_one"
)

result = result.merge(
    leave_month,
    on=["department_id", "month_start_date"],
    how="left",
    validate="one_to_one"
)

result = result.merge(
    department[["department_id", "department_name"]],
    on="department_id",
    how="left",
    validate="many_to_one"
)

# Restrict to the common department-month reporting window.
result = result[
    result["month_start_date"].between(START_MONTH, END_MONTH)
].copy()


result = result[
    result["month_start_date"].between(START_MONTH, END_MONTH)
].copy()

# -----------------------------
# 7A. Task and sprint aggregation
# -----------------------------
tasks = read_csv("fact_task.csv")
team = read_csv("dim_team.csv")
sprint = read_csv("dim_sprint.csv")

require_columns(
    tasks,
    [
        "task_id", "team_id", "sprint_id",
        "status", "story_points"
    ],
    "fact_task"
)

require_columns(
    team,
    ["team_id", "department_id"],
    "dim_team"
)

require_columns(
    sprint,
    ["sprint_id", "start_date"],
    "dim_sprint"
)

# Map each task to its department and sprint start month.
task_detail = tasks.merge(
    team[["team_id", "department_id"]],
    on="team_id",
    how="left",
    validate="many_to_one"
)

task_detail = task_detail.merge(
    sprint[["sprint_id", "start_date"]],
    on="sprint_id",
    how="left",
    validate="many_to_one"
)

if task_detail["department_id"].isna().any():
    raise ValueError("Some task team IDs did not map to departments.")

if task_detail["start_date"].isna().any():
    raise ValueError("Some task sprint IDs did not map to sprint dates.")

task_detail["month_start_date"] = (
    pd.to_datetime(task_detail["start_date"])
    .dt.to_period("M")
    .dt.to_timestamp()
)

# Use the validated reporting period.
task_detail = task_detail[
    task_detail["month_start_date"].between(
        START_MONTH, END_MONTH
    )
].copy()

# Cancelled tasks are excluded from the task denominator.
eligible_tasks = task_detail[
    task_detail["status"] != "Cancelled"
].copy()

# Aggregate task metrics before joining to the department-month spine.
task_month = eligible_tasks.groupby(
    ["department_id", "month_start_date"],
    as_index=False
).agg(
    tasks=("task_id", "nunique"),
    tasks_done=(
        "status",
        lambda x: int((x == "Done").sum())
    ),
    story_points_done=(
        "story_points",
        lambda x: x[
            eligible_tasks.loc[x.index, "status"] == "Done"
        ].sum()
    )
)

task_month["task_completion_rate_pct"] = np.where(
    task_month["tasks"].gt(0),
    task_month["tasks_done"] / task_month["tasks"] * 100,
    np.nan
)

# Add the independently aggregated task metrics.
result = result.merge(
    task_month,
    on=["department_id", "month_start_date"],
    how="left",
    validate="one_to_one"
)

numeric_fill = [

    "payroll_rows", "payroll_employee_count", "payroll_gross_pay",
    "payroll_net_pay", "overtime_hours_paid", "overtime_cost",
    "employer_cost", "attendance_employee_count", "scheduled_days",
    "present_days", "wfh_days", "paid_leave_days_attendance",
    "unpaid_absence_days", "attendance_overtime_hours",
    "approved_leave_days", "allocated_leave_request_months",
    "hires", "exits", "voluntary_exits", "transfers_in", "transfers_out"
]
for col in numeric_fill:
    if col in result.columns:
        result[col] = result[col].fillna(0)



result["leave_days_per_average_head"] = np.where(
    result["average_headcount"].gt(0),
    result["approved_leave_days"] / result["average_headcount"],
    np.nan
)
result["overtime_cost_per_average_head"] = np.where(
    result["average_headcount"].gt(0),
    result["overtime_cost"] / result["average_headcount"],
    np.nan
)
result["overtime_hours_variance"] = (
    result["overtime_hours_paid"] - result["attendance_overtime_hours"]
)

result = result.sort_values(
    ["month_start_date", "department_id"]
).reset_index(drop=True)

# -----------------------------
# 8. Validation and reconciliation
# -----------------------------
if result.duplicated(["department_id", "month_start_date"]).any():
    raise ValueError("Final output is not unique at department-month grain.")

expected_months = pd.date_range(START_MONTH, END_MONTH, freq="MS")
expected_departments = sorted(department["department_id"].unique())
expected_pairs = len(expected_months) * len(expected_departments)

if len(result) != expected_pairs:
    raise ValueError(
        f"Expected {expected_pairs} department-month rows "
        f"({len(expected_departments)} departments x {len(expected_months)} months), "
        f"but produced {len(result)}."
    )

if result["department_name"].isna().any():
    raise ValueError("Some department IDs did not map to dim_department.")

if result[
    ["headcount_start", "headcount_end", "average_headcount"]
].isna().any().any():
    raise ValueError("Missing headcount values in the reporting period.")

# Department-month row counts and source totals for audit.
source_totals = pd.DataFrame([
    {
        "source": "payroll_clean",
        "rows_in_scope": len(payroll_clean),
        "gross_pay": payroll_clean["gross_pay"].sum(),
        "overtime_cost": payroll_clean["overtime_pay"].sum(),
        "employer_cost": payroll_clean["employer_cost"].sum()
    },
    {
        "source": "attendance",
        "rows_in_scope": len(attendance_period),
        "gross_pay": np.nan,
        "overtime_cost": np.nan,
        "employer_cost": np.nan
    },
    {
        "source": "approved_leave_valid",
        "rows_in_scope": len(valid_leave),
        "gross_pay": np.nan,
        "overtime_cost": np.nan,
        "employer_cost": np.nan
    }
])

payroll_reconciliation = pd.DataFrame([
    {
        "metric": "Payroll source rows",
        "source_value": len(payroll),
        "analytical_value": len(payroll_clean),
        "difference": len(payroll) - len(payroll_clean)
    },
    {
        "metric": "Gross pay",
        "source_value": payroll.loc[
            ~payroll["payroll_item_id"].astype(str).isin(SYNTHETIC_DUPLICATE_IDS),
            "gross_pay"
        ].sum(),
        "analytical_value": result["payroll_gross_pay"].sum(),
        "difference": (
            payroll.loc[
                ~payroll["payroll_item_id"].astype(str).isin(SYNTHETIC_DUPLICATE_IDS),
                "gross_pay"
            ].sum() - result["payroll_gross_pay"].sum()
        )
    },
    {
        "metric": "Overtime cost",
        "source_value": payroll_clean["overtime_pay"].sum(),
        "analytical_value": result["overtime_cost"].sum(),
        "difference": payroll_clean["overtime_pay"].sum() - result["overtime_cost"].sum()
    },
    {
        "metric": "Employer cost",
        "source_value": payroll_clean["employer_cost"].sum(),
        "analytical_value": result["employer_cost"].sum(),
        "difference": payroll_clean["employer_cost"].sum() - result["employer_cost"].sum()
    }
])

# -----------------------------
# 9. Save outputs
# -----------------------------
output_file = OUTPUT / "pq13_department_month.csv"
result.to_csv(output_file, index=False)

leave_allocations.to_csv(
    OUTPUT / "pq13_leave_month_allocations.csv", index=False
)
leave_audit.to_csv(
    OUTPUT / "pq13_leave_allocation_audit.csv", index=False
)
invalid_leave.to_csv(
    OUTPUT / "pq13_invalid_approved_leave_exceptions.csv", index=False
)
duplicate_rows.to_csv(
    OUTPUT / "pq13_excluded_synthetic_payroll_duplicates.csv", index=False
)
payroll_reconciliation.to_csv(
    OUTPUT / "pq13_payroll_reconciliation.csv", index=False
)
source_totals.to_csv(
    OUTPUT / "pq13_source_summary.csv", index=False
)

print("\n========== PQ-13 ETL COMPLETED ==========")
print("Output:", output_file)
print("Reporting period:", START_MONTH.date(), "to", REPORT_END.date())
print("Departments:", result["department_id"].nunique())
print("Months:", result["month_start_date"].nunique())
print("Final department-month rows:", len(result))

print("\n========== PAYROLL QUALITY TREATMENT ==========")
print("Original payroll rows:", len(payroll))
print("Excluded synthetic duplicate rows:", len(duplicate_rows))
print("Analytical payroll rows:", len(payroll_clean))
unmapped_payroll_key_mask = (
    payroll_clean["employee_key"].isna()
    | payroll_clean["employee_key"].eq(-1)
)
print(
    "Unmapped payroll employee-key rows retained in cost totals:",
    int(unmapped_payroll_key_mask.sum())
)

print("\n========== LEAVE QUALITY TREATMENT ==========")
print("Approved leave requests:", len(approved))
print("Valid requests allocated:", len(valid_leave))
print("Invalid approved requests excluded:", len(invalid_leave))
print("Approved leave days in reporting period:",
      int(result["approved_leave_days"].sum()))
print("Maternity leave days allocated in reporting period:",
      int(leave_allocations.loc[
          leave_allocations["leave_type_code"].eq("ML"),
          "allocated_leave_days"
      ].sum()))

print("\n========== RECONCILIATION ==========")
print(payroll_reconciliation.to_string(index=False))

print("\n========== FINAL DATA SAMPLE ==========")
print(result.head(12).to_string(index=False))

print("\nSaved audit files in:", OUTPUT)
