
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.express as px


# ---------------------------------------------------------
# PQ-09 | Payroll Cost Dashboard
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "03_Data" / "csv"
VALIDATION = ROOT / "outputs" / "pq01"
VAULT = ROOT / "04_Validation_Vault"

PAYROLL_FILE = VALIDATION / "fact_payroll_passed.csv"
QUARANTINE_FILE = VALIDATION / "fact_payroll_quarantine.csv"
LEDGER_FILE = DATA / "fact_ledger.csv"
DEPARTMENT_FILE = DATA / "dim_department.csv"
ROLE_FILE = DATA / "dim_role.csv"
ANSWER_KEY_FILE = VAULT / "unlock_PQ-09_reconciliation_answer_key.csv"

PAYROLL_ACCOUNTS = ["5001", "5002", "5003", "5004", "5005"]
MIN_GROUP_HEADCOUNT = 5
TOLERANCE = 0.01


st.set_page_config(
    page_title="PQ-09 | Payroll Cost",
    page_icon="📊",
    layout="wide",
)

st.title("Payroll Cost Dashboard")
st.caption(
    "PQ-09 | Monthly payroll analysis, departmental cost trends "
    "and ledger reconciliation"
)


# ---------------------------------------------------------
# Data loading and validation
# ---------------------------------------------------------

@st.cache_data
def load_data():
    required_files = [
        PAYROLL_FILE,
        QUARANTINE_FILE,
        LEDGER_FILE,
        DEPARTMENT_FILE,
        ROLE_FILE,
        ANSWER_KEY_FILE,
    ]

    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Required input files are missing:\n" + "\n".join(missing)
        )

    payroll = pd.read_csv(PAYROLL_FILE)
    quarantine = pd.read_csv(QUARANTINE_FILE)
    ledger = pd.read_csv(LEDGER_FILE)
    departments = pd.read_csv(DEPARTMENT_FILE)
    roles = pd.read_csv(ROLE_FILE)
    answer_key = pd.read_csv(ANSWER_KEY_FILE)

    required_payroll = {
        "payroll_item_id", "employee_id", "period_end_date",
        "department_id", "role_id", "headcount_flag",
        "gross_pay", "net_pay", "employer_cost",
    }
    missing_columns = required_payroll - set(payroll.columns)
    if missing_columns:
        raise ValueError(
            f"Payroll file is missing columns: {sorted(missing_columns)}"
        )

    payroll["period_end_date"] = pd.to_datetime(
        payroll["period_end_date"], errors="coerce"
    )
    payroll["month"] = payroll["period_end_date"].dt.strftime("%Y-%m")

    answer_key["month"] = pd.to_datetime(
        answer_key["month"], errors="coerce"
    ).dt.strftime("%Y-%m")

    for col in [
        "gross_pay", "net_pay", "employer_cost", "earned_fixed_pay",
        "overtime_pay", "variable_pay", "pf_employer", "esi_employer",
    ]:
        if col in payroll.columns:
            payroll[col] = pd.to_numeric(payroll[col], errors="coerce").fillna(0)

    ledger["posting_period"] = ledger["posting_period"].astype(str)
    ledger["account_code"] = ledger["account_code"].astype(str).str.replace(
        r"\.0$", "", regex=True
    )
    ledger["signed_amount_debit_positive"] = pd.to_numeric(
        ledger["signed_amount_debit_positive"], errors="coerce"
    ).fillna(0)

    answer_numeric = [
        "employees_paid",
        "payroll_gross_pay",
        "payroll_net_pay",
        "payroll_employer_cost",
        "ledger_salary_related_expense",
        "ledger_revenue",
    ]
    for col in answer_numeric:
        if col in answer_key.columns:
            answer_key[col] = pd.to_numeric(
                answer_key[col], errors="coerce"
            ).fillna(0)

    return payroll, quarantine, ledger, departments, roles, answer_key


try:
    payroll, quarantine, ledger, departments, roles, answer_key = load_data()
except Exception as exc:
    st.error(f"Unable to load dashboard data: {exc}")
    st.stop()


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def money(value):
    return f"₹{value:,.2f}"


def headcount(frame):
    """Count distinct paid employees without exposing employee-level data."""
    if frame.empty:
        return 0

    eligible = frame.copy()
    if "headcount_flag" in eligible.columns:
        flag = eligible["headcount_flag"].astype(str).str.upper()
        eligible = eligible[flag.isin(["1", "Y", "YES", "TRUE"])]

    return int(eligible["employee_id"].nunique())


def aggregate_payroll(frame, group_columns):
    """Return aggregated metrics only; no individual salary rows."""
    result = (
        frame.groupby(group_columns, dropna=False)
        .agg(
            gross_pay=("gross_pay", "sum"),
            net_pay=("net_pay", "sum"),
            employer_cost=("employer_cost", "sum"),
            employees=("employee_id", "nunique"),
        )
        .reset_index()
    )
    result["cost_per_employee"] = (
        result["employer_cost"] / result["employees"].replace(0, pd.NA)
    )
    result["cost_per_employee"] = result["cost_per_employee"].fillna(0)
    return result


# ---------------------------------------------------------
# Filters
# ---------------------------------------------------------

valid_months = sorted(payroll["month"].dropna().unique().tolist())
if not valid_months:
    st.error("No valid payroll months were found.")
    st.stop()

with st.sidebar:
    st.header("Dashboard filters")

    selected_months = st.multiselect(
        "Payroll months",
        options=valid_months,
        default=valid_months,
    )

    department_options = departments["department_id"].astype(str).tolist()
    selected_departments = st.multiselect(
        "Departments",
        options=department_options,
        default=department_options,
        format_func=lambda dep_id: (
            departments.loc[
                departments["department_id"].astype(str) == dep_id,
                "department_name",
            ].iloc[0]
            if (
                departments["department_id"].astype(str) == dep_id
            ).any()
            else dep_id
        ),
    )

if not selected_months or not selected_departments:
    st.info("Select at least one month and one department to display results.")
    st.stop()

filtered = payroll[
    payroll["month"].isin(selected_months)
    & payroll["department_id"].astype(str).isin(selected_departments)
].copy()

if filtered.empty:
    st.warning("No payroll records match the selected filters.")
    st.stop()


# ---------------------------------------------------------
# KPI cards
# ---------------------------------------------------------

total_gross = filtered["gross_pay"].sum()
total_net = filtered["net_pay"].sum()
total_employer_cost = filtered["employer_cost"].sum()
total_employees = headcount(filtered)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Gross Pay", money(total_gross))
k2.metric("Net Pay", money(total_net))
k3.metric("Employer Cost", money(total_employer_cost))
k4.metric("Distinct Employees", f"{total_employees:,}")

st.divider()


# ---------------------------------------------------------
# Monthly trend
# ---------------------------------------------------------

st.subheader("Monthly payroll trend")

monthly = (
    filtered.groupby("month", as_index=False)
    .agg(
        gross_pay=("gross_pay", "sum"),
        net_pay=("net_pay", "sum"),
        employer_cost=("employer_cost", "sum"),
        employees=("employee_id", "nunique"),
    )
    .sort_values("month")
)

monthly["cost_per_employee"] = (
    monthly["employer_cost"] / monthly["employees"].replace(0, pd.NA)
).fillna(0)

trend_left, trend_right = st.columns(2)

with trend_left:
    trend_long = monthly.melt(
        id_vars="month",
        value_vars=["gross_pay", "net_pay", "employer_cost"],
        var_name="metric",
        value_name="amount",
    )
    fig = px.line(
        trend_long,
        x="month",
        y="amount",
        color="metric",
        markers=True,
        title="Gross, net and employer cost by month",
        labels={"month": "Month", "amount": "Amount (₹)", "metric": "Metric"},
    )
    st.plotly_chart(fig, use_container_width=True)

with trend_right:
    fig = px.line(
        monthly,
        x="month",
        y="cost_per_employee",
        markers=True,
        title="Employer cost per employee",
        labels={
            "month": "Month",
            "cost_per_employee": "Cost per employee (₹)",
        },
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------
# Department aggregation
# ---------------------------------------------------------

st.subheader("Department cost analysis")

dept_data = aggregate_payroll(
    filtered,
    ["department_id"],
)

dept_data = dept_data.merge(
    departments[["department_id", "department_name"]],
    on="department_id",
    how="left",
)

dept_data = dept_data[
    dept_data["employees"] >= MIN_GROUP_HEADCOUNT
].copy()

if dept_data.empty:
    st.info("No department groups meet the minimum headcount of five.")
else:
    dept_left, dept_right = st.columns(2)

    with dept_left:
        fig = px.bar(
            dept_data.sort_values("employer_cost", ascending=False),
            x="department_name",
            y="employer_cost",
            title="Employer cost by department",
            labels={
                "department_name": "Department",
                "employer_cost": "Employer cost (₹)",
            },
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

    with dept_right:
        fig = px.bar(
            dept_data.sort_values("cost_per_employee", ascending=False),
            x="department_name",
            y="cost_per_employee",
            title="Employer cost per employee by department",
            labels={
                "department_name": "Department",
                "cost_per_employee": "Cost per employee (₹)",
            },
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        dept_data[
            [
                "department_name", "employees", "gross_pay",
                "net_pay", "employer_cost", "cost_per_employee",
            ]
        ].rename(
            columns={
                "department_name": "Department",
                "employees": "Employees",
                "gross_pay": "Gross Pay",
                "net_pay": "Net Pay",
                "employer_cost": "Employer Cost",
                "cost_per_employee": "Cost per Employee",
            }
        ).style.format(
            {
                "Gross Pay": "₹{:,.2f}",
                "Net Pay": "₹{:,.2f}",
                "Employer Cost": "₹{:,.2f}",
                "Cost per Employee": "₹{:,.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------
# Role aggregation
# ---------------------------------------------------------

st.subheader("Role cost analysis")

role_data = aggregate_payroll(filtered, ["role_id"])

role_data = role_data.merge(
    roles[["role_id", "role_title", "department_id"]],
    on="role_id",
    how="left",
)

role_data = role_data[
    role_data["employees"] >= MIN_GROUP_HEADCOUNT
].copy()

if role_data.empty:
    st.info("No role groups meet the minimum headcount of five.")
else:
    st.caption(
        "Roles with fewer than five distinct employees are hidden."
    )

    fig = px.bar(
        role_data.sort_values("employer_cost", ascending=False),
        x="role_title",
        y="employer_cost",
        title="Employer cost by role",
        labels={"role_title": "Role", "employer_cost": "Employer cost (₹)"},
    )
    fig.update_layout(xaxis_tickangle=-35)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        role_data[
            [
                "role_title", "employees", "gross_pay",
                "net_pay", "employer_cost", "cost_per_employee",
            ]
        ].rename(
            columns={
                "role_title": "Role",
                "employees": "Employees",
                "gross_pay": "Gross Pay",
                "net_pay": "Net Pay",
                "employer_cost": "Employer Cost",
                "cost_per_employee": "Cost per Employee",
            }
        ).style.format(
            {
                "Gross Pay": "₹{:,.2f}",
                "Net Pay": "₹{:,.2f}",
                "Employer Cost": "₹{:,.2f}",
                "Cost per Employee": "₹{:,.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------
# Official answer key reconciliation
# ---------------------------------------------------------

st.divider()
st.subheader("Official reconciliation")

payroll_monthly = (
    payroll.groupby("month", as_index=False)
    .agg(
        actual_employees=("employee_id", "nunique"),
        actual_gross=("gross_pay", "sum"),
        actual_net=("net_pay", "sum"),
        actual_employer_cost=("employer_cost", "sum"),
    )
)

ledger_payroll = ledger[
    ledger["account_code"].isin(PAYROLL_ACCOUNTS)
].copy()

ledger_monthly = (
    ledger_payroll.groupby("posting_period", as_index=False)
    .agg(ledger_salary_expense=("signed_amount_debit_positive", "sum"))
    .rename(columns={"posting_period": "month"})
)

reconciliation = (
    answer_key.merge(payroll_monthly, on="month", how="left")
    .merge(ledger_monthly, on="month", how="left")
)

for col in [
    "actual_employees", "actual_gross", "actual_net",
    "actual_employer_cost", "ledger_salary_expense",
]:
    reconciliation[col] = reconciliation[col].fillna(0)

reconciliation["gross_delta"] = (
    reconciliation["actual_gross"] - reconciliation["payroll_gross_pay"]
)
reconciliation["net_delta"] = (
    reconciliation["actual_net"] - reconciliation["payroll_net_pay"]
)
reconciliation["employer_cost_delta"] = (
    reconciliation["actual_employer_cost"]
    - reconciliation["payroll_employer_cost"]
)
reconciliation["ledger_key_delta"] = (
    reconciliation["ledger_salary_expense"]
    - reconciliation["ledger_salary_related_expense"]
)
reconciliation["payroll_vs_ledger_delta"] = (
    reconciliation["actual_employer_cost"]
    - reconciliation["ledger_salary_expense"]
)

reconciliation["payroll_key_match"] = (
    reconciliation["gross_delta"].abs().le(TOLERANCE)
    & reconciliation["net_delta"].abs().le(TOLERANCE)
    & reconciliation["employer_cost_delta"].abs().le(TOLERANCE)
    & (
        reconciliation["actual_employees"]
        - reconciliation["employees_paid"]
    ).abs().le(0)
)

reconciliation["ledger_key_match"] = (
    reconciliation["ledger_key_delta"].abs().le(TOLERANCE)
)

reconciliation["status"] = reconciliation.apply(
    lambda row: (
        "PASS"
        if row["payroll_key_match"] and row["ledger_key_match"]
        else "REVIEW"
    ),
    axis=1,
)

reconciliation = reconciliation.sort_values("month")

payroll_pass_count = int(reconciliation["payroll_key_match"].sum())
ledger_pass_count = int(reconciliation["ledger_key_match"].sum())

r1, r2, r3 = st.columns(3)
r1.metric(
    "Payroll months matching key",
    f"{payroll_pass_count}/{len(reconciliation)}",
)
r2.metric(
    "Ledger months matching key",
    f"{ledger_pass_count}/{len(reconciliation)}",
)
r3.metric(
    "Months requiring review",
    str(int((reconciliation["status"] == "REVIEW").sum())),
)

ledger_mismatches = reconciliation[
    ~reconciliation["ledger_key_match"]
]

if not ledger_mismatches.empty:
    st.warning(
        "One or more ledger months do not match the official answer key. "
        "Investigate the source records before making any adjustment."
    )

june_exception = reconciliation[
    (reconciliation["month"] == "2026-06")
    & (~reconciliation["ledger_key_match"])
]

if not june_exception.empty:
    june_delta = float(june_exception.iloc[0]["ledger_key_delta"])
    st.error(
        "June 2026 unresolved ledger variance: "
        f"{money(june_delta)}. "
        "The variance is isolated to Engineering (D01), ledger line "
        "JL-005614, journal JE-002094. "
        "Source data has not been altered."
    )

display_columns = [
    "month",
    "employees_paid",
    "actual_employees",
    "payroll_gross_pay",
    "actual_gross",
    "payroll_net_pay",
    "actual_net",
    "payroll_employer_cost",
    "actual_employer_cost",
    "ledger_salary_related_expense",
    "ledger_salary_expense",
    "gross_delta",
    "net_delta",
    "employer_cost_delta",
    "ledger_key_delta",
    "payroll_vs_ledger_delta",
    "status",
]

display_columns = [
    col for col in display_columns if col in reconciliation.columns
]

st.dataframe(
    reconciliation[display_columns].rename(
        columns={
            "month": "Month",
            "employees_paid": "Key Employees",
            "actual_employees": "Actual Employees",
            "payroll_gross_pay": "Key Gross Pay",
            "actual_gross": "Actual Gross Pay",
            "payroll_net_pay": "Key Net Pay",
            "actual_net": "Actual Net Pay",
            "payroll_employer_cost": "Key Employer Cost",
            "actual_employer_cost": "Actual Employer Cost",
            "ledger_salary_related_expense": "Key Ledger Expense",
            "ledger_salary_expense": "Actual Ledger Expense",
            "gross_delta": "Gross Delta",
            "net_delta": "Net Delta",
            "employer_cost_delta": "Employer Cost Delta",
            "ledger_key_delta": "Ledger Delta",
            "payroll_vs_ledger_delta": "Payroll vs Ledger",
            "status": "Status",
        }
    ).style.format(
        {
            col: "₹{:,.2f}"
            for col in [
                "Key Gross Pay", "Actual Gross Pay",
                "Key Net Pay", "Actual Net Pay",
                "Key Employer Cost", "Actual Employer Cost",
                "Key Ledger Expense", "Actual Ledger Expense",
                "Gross Delta", "Net Delta", "Employer Cost Delta",
                "Ledger Delta", "Payroll vs Ledger",
            ]
        },
        na_rep="—",
    ),
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "Download reconciliation CSV",
    data=reconciliation.to_csv(index=False).encode("utf-8"),
    file_name="pq09_monthly_reconciliation.csv",
    mime="text/csv",
)


# ---------------------------------------------------------
# Quarantine audit summary
# ---------------------------------------------------------

st.divider()
st.subheader("Excluded payroll records — audit summary")

if quarantine.empty:
    st.info("The quarantine file contains no excluded records.")
else:
    if "quarantine_reason" in quarantine.columns:
        reason_counts = (
            quarantine.groupby("quarantine_reason")
            .size()
            .reset_index(name="records")
            .sort_values("quarantine_reason")
        )

        q1, q2 = st.columns(2)
        q1.metric("Quarantined records", f"{len(quarantine):,}")
        q2.metric(
            "Reason categories",
            f"{reason_counts['quarantine_reason'].nunique():,}",
        )

        reason_labels = {
            "DUPLICATE_EMPLOYEE_RUN": (
                "Duplicate employee/run record — excluded to prevent "
                "double counting."
            ),
            "UNMATCHED_EMPLOYEE_KEY": (
                "Unmatched employee key — excluded because the employee "
                "key could not be reliably matched."
            ),
        }

        audit_rows = []
        for _, row in reason_counts.iterrows():
            reason = str(row["quarantine_reason"])
            audit_rows.append(
                {
                    "Reason code": reason,
                    "Explanation": reason_labels.get(
                        reason, "Excluded by the upstream validation process."
                    ),
                    "Excluded records": int(row["records"]),
                }
            )

        st.dataframe(
            pd.DataFrame(audit_rows),
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "This audit view intentionally omits employee IDs and salary "
            "amounts. The four quarantined records remain excluded from "
            "the validated payroll dataset."
        )
    else:
        st.warning(
            "The quarantine file has no quarantine_reason column; "
            "the audit summary cannot be categorized."
        )


# ---------------------------------------------------------
# Data privacy and definitions
# ---------------------------------------------------------

with st.expander("Definitions and controls"):
    st.markdown(
        """
        - **Gross pay:** Sum of validated payroll gross pay.
        - **Net pay:** Sum of validated payroll net pay.
        - **Employer cost:** Sum of the payroll employer-cost field.
        - **Cost per employee:** Employer cost divided by distinct employees
          represented in the relevant aggregate.
        - **Ledger salary expense:** Sum of debit-positive amounts for
          ledger accounts 5001–5005.
        - **Reconciliation tolerance:** ₹0.01.
        - **Small-group suppression:** Department and role aggregates with
          fewer than five distinct employees are hidden.
        - **Privacy:** The dashboard does not display employee-level salary
          records or employee identifiers.
        - **Data quality:** Four quarantined rows remain excluded according
          to the existing PQ-01 validation output.
        """
    )

st.caption(
    "PQ-09 Payroll Cost Dashboard | Built from validated project CSV inputs."
)

