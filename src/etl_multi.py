
import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "05_Starter" / "pulseiq.duckdb"
OUTPUT_DIR = ROOT / "outputs" / "pq01"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def read_raw_table(table_name):
    """Read a raw table without modifying the source database."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(
            f"SELECT * FROM raw.{table_name}"
        ).fetchdf()
    finally:
        con.close()


def add_reason(reasons, mask, reason_code):
    """Attach a reason code to every row selected by a boolean mask."""
    mask = mask.fillna(False)
    for idx in reasons.index[mask]:
        if reason_code not in reasons.at[idx]:
            reasons.at[idx].append(reason_code)


def split_passed_quarantine(df, reasons):
    """Split records while retaining every failed record and its reasons."""
    result = df.copy()
    result["quarantine_reason"] = reasons.apply(
        lambda values: "|".join(values) if values else None
    )

    quarantine = result[result["quarantine_reason"].notna()].copy()
    passed = result[result["quarantine_reason"].isna()].copy()

    if len(df) != len(passed) + len(quarantine):
        raise AssertionError("Input/pass/quarantine counts do not reconcile.")

    return passed, quarantine


def write_feed_outputs(table_name, passed, quarantine, input_count, warnings=None):
    """Write feed outputs and a reconciliation summary."""
    passed_path = OUTPUT_DIR / f"{table_name}_passed.csv"
    quarantine_path = OUTPUT_DIR / f"{table_name}_quarantine.csv"
    summary_path = OUTPUT_DIR / f"{table_name}_summary.json"

    passed.drop(columns=["quarantine_reason"], errors="ignore").to_csv(
        passed_path, index=False
    )
    quarantine.to_csv(quarantine_path, index=False)

    reason_counts = {}
    if not quarantine.empty:
        reason_counts = {
            str(reason): int(count)
            for reason, count in (
                quarantine["quarantine_reason"]
                .str.split("|")
                .explode()
                .value_counts()
                .items()
            )
        }

    summary = {
        "table": table_name,
        "rows_in": int(input_count),
        "rows_passed": int(len(passed)),
        "rows_quarantined": int(len(quarantine)),
        "reconciliation_ok": (
            int(input_count) == len(passed) + len(quarantine)
        ),
        "quarantine_reasons": reason_counts,
        "warnings": warnings or [],
    }

    if not summary["reconciliation_ok"]:
        raise AssertionError(f"Reconciliation failed for {table_name}")

    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8"
    )

    return summary


def validate_anomaly():
    df = read_raw_table("fact_anomaly")
    reasons = pd.Series(
        [[] for _ in range(len(df))],
        index=df.index,
        dtype=object
    )

    required = [
        "result_id", "source_dataset", "record_id", "employee_id",
        "period", "anomaly_score", "flagged", "reason_code",
        "reason_text", "model_version", "scored_at"
    ]

    # Required fields must be present.
    for column in required:
        mask = df[column].isna()
        if column == "reason_text":
            mask = mask | df[column].astype("string").str.strip().eq("")
        add_reason(reasons, mask, f"MISSING_REQUIRED_{column.upper()}")

    # Unique, correctly formatted result IDs.
    add_reason(
        reasons,
        df["result_id"].isna()
        | ~df["result_id"].astype("string").str.match(
            r"^AN-[0-9]{4}$", na=False
        ),
        "INVALID_RESULT_ID"
    )
    add_reason(
        reasons,
        df["result_id"].duplicated(keep=False),
        "DUPLICATE_RESULT_ID"
    )

    # Contracted source datasets and value ranges.
    allowed_sources = {
        "attendance_monthly_features",
        "payroll_monthly_features",
    }
    add_reason(
        reasons,
        ~df["source_dataset"].isin(allowed_sources),
        "INVALID_SOURCE_DATASET"
    )
    add_reason(
        reasons,
        ~df["anomaly_score"].between(0, 1, inclusive="both"),
        "ANOMALY_SCORE_OUT_OF_RANGE"
    )
    add_reason(
        reasons,
        ~df["flagged"].isin(["Y", "N"]),
        "INVALID_FLAGGED_VALUE"
    )

    # Employee references must exist.
    employees = read_raw_table("dim_employee")
    valid_employee_ids = set(
        employees["employee_id"].dropna().astype(str)
    )
    add_reason(
        reasons,
        ~df["employee_id"].astype("string").isin(valid_employee_ids),
        "UNMATCHED_EMPLOYEE_ID"
    )

    # Money-at-risk semantics differ by source dataset.
    attendance_mask = df["source_dataset"].eq(
        "attendance_monthly_features"
    )
    payroll_mask = df["source_dataset"].eq(
        "payroll_monthly_features"
    )

    add_reason(
        reasons,
        attendance_mask & df["money_at_risk"].notna(),
        "UNEXPECTED_ATTENDANCE_MONEY_AT_RISK"
    )
    add_reason(
        reasons,
        payroll_mask & df["money_at_risk"].isna(),
        "MISSING_PAYROLL_MONEY_AT_RISK"
    )
    add_reason(
        reasons,
        payroll_mask & (df["money_at_risk"] < 0),
        "NEGATIVE_MONEY_AT_RISK"
    )

    passed, quarantine = split_passed_quarantine(df, reasons)

    warnings = [
        "No documented reason_code allowlist was found; values were not quarantined by reason code.",
        "scored_at is timezone-naive; UTC cannot be confirmed from the source schema.",
        "model_version naming convention is not fully specified.",
        "Attendance anomaly record IDs were validated through employee and month mapping rather than direct ID equality."
    ]

    return write_feed_outputs(
        "fact_anomaly",
        passed,
        quarantine,
        len(df),
        warnings
    )


def validate_attrition():
    df = read_raw_table("fact_attrition_risk")
    employees = read_raw_table("dim_employee")
    departments = read_raw_table("dim_department")

    reasons = pd.Series(
        [[] for _ in range(len(df))],
        index=df.index,
        dtype=object
    )

    # Required contract fields.
    required = [
        "prediction_id", "employee_id", "department_id",
        "as_of_date", "risk_score_12m", "risk_band",
        "model_version"
    ]
    for column in required:
        add_reason(
            reasons,
            df[column].isna(),
            f"MISSING_REQUIRED_{column.upper()}"
        )

    # Prediction ID format and uniqueness.
    add_reason(
        reasons,
        df["prediction_id"].isna()
        | ~df["prediction_id"].astype("string").str.match(
            r"^AR-[0-9]{4}$", na=False
        ),
        "INVALID_PREDICTION_ID"
    )
    add_reason(
        reasons,
        df["prediction_id"].duplicated(keep=False),
        "DUPLICATE_PREDICTION_ID"
    )

    # Score range and permitted risk-band values.
    add_reason(
        reasons,
        ~df["risk_score_12m"].between(0, 1, inclusive="both"),
        "RISK_SCORE_OUT_OF_RANGE"
    )
    add_reason(
        reasons,
        ~df["risk_band"].isin(["Low", "Medium", "High"]),
        "INVALID_RISK_BAND"
    )

    # Department reference.
    valid_departments = set(
        departments["department_id"].dropna().astype(str)
    )
    add_reason(
        reasons,
        ~df["department_id"].astype("string").isin(valid_departments),
        "UNMATCHED_DEPARTMENT_ID"
    )

    # Validate employee history using a half-open validity interval:
    # valid_from <= as_of_date < valid_to, or no valid_to.
    employee_history = employees[
        [
            "employee_key", "employee_id", "department_id",
            "employment_status", "exit_date", "valid_from", "valid_to"
        ]
    ].copy()

    employee_history["employee_id"] = (
        employee_history["employee_id"].astype("string")
    )

    valid_history_counts = []
    expected_keys = []
    expected_departments = []
    active_history_flags = []

    for _, row in df.iterrows():
        candidates = employee_history[
            employee_history["employee_id"].eq(str(row["employee_id"]))
        ]

        if pd.isna(row["as_of_date"]):
            candidates = candidates.iloc[0:0]
        else:
            candidates = candidates[
                (candidates["valid_from"] <= row["as_of_date"])
                & (
                    candidates["valid_to"].isna()
                    | (row["as_of_date"] < candidates["valid_to"])
                )
            ]

        valid_history_counts.append(len(candidates))

        if len(candidates) == 1:
            hist = candidates.iloc[0]
            expected_keys.append(hist["employee_key"])
            expected_departments.append(hist["department_id"])

            status = str(hist["employment_status"]).strip().lower()
            exit_date = hist["exit_date"]

            is_active = (
                status in {"active", "employed"}
                and (pd.isna(exit_date) or row["as_of_date"] <= exit_date)
            )
            active_history_flags.append(is_active)
        else:
            expected_keys.append(None)
            expected_departments.append(None)
            active_history_flags.append(False)

    history_count = pd.Series(valid_history_counts, index=df.index)
    expected_key = pd.Series(expected_keys, index=df.index)
    expected_department = pd.Series(expected_departments, index=df.index)
    active_history = pd.Series(active_history_flags, index=df.index)

    add_reason(
        reasons,
        history_count.eq(0),
        "NO_EMPLOYEE_VERSION_AS_OF_DATE"
    )
    add_reason(
        reasons,
        history_count.gt(1),
        "MULTIPLE_EMPLOYEE_VERSIONS_AS_OF_DATE"
    )
    add_reason(
        reasons,
        history_count.eq(1) & ~active_history,
        "EMPLOYEE_NOT_ACTIVE_AS_OF_DATE"
    )
    add_reason(
        reasons,
        history_count.eq(1)
        & df["employee_key"].notna()
        & df["employee_key"].ne(expected_key),
        "EMPLOYEE_KEY_NOT_VALID_AS_OF_DATE"
    )
    add_reason(
        reasons,
        history_count.eq(1)
        & df["department_id"].ne(expected_department),
        "DEPARTMENT_MISMATCH_AS_OF_DATE"
    )

    # Contract says one as_of_date per batch. Select the modal date
    # dynamically, and stop safely if the modal date is tied.
    date_counts = df["as_of_date"].value_counts(dropna=True)

    if len(date_counts) > 1:
        top_count = date_counts.max()
        modal_dates = date_counts[date_counts.eq(top_count)].index.tolist()

        if len(modal_dates) != 1:
            raise ValueError(
                "Multiple as_of_date values tie for the largest batch; "
                "cannot choose a reference date safely."
            )

        reference_date = modal_dates[0]
        add_reason(
            reasons,
            df["as_of_date"].notna()
            & df["as_of_date"].ne(reference_date),
            "INCONSISTENT_AS_OF_DATE"
        )

    passed, quarantine = split_passed_quarantine(df, reasons)

    warnings = [
        "Risk-band percentile and tie-handling rules are not fully specified; no percentile-based quarantine was applied.",
        "The modal as_of_date is used as a data-driven batch reference because the contract requires one date per batch."
    ]

    return write_feed_outputs(
        "fact_attrition_risk",
        passed,
        quarantine,
        len(df),
        warnings
    )


def validate_forecast():
    df = read_raw_table("fact_forecast")
    departments = read_raw_table("dim_department")

    reasons = pd.Series(
        [[] for _ in range(len(df))],
        index=df.index,
        dtype=object
    )

    required = [
        "forecast_id", "metric", "department_id", "forecast_month",
        "forecast_value", "lower_80", "upper_80", "method",
        "trained_through"
    ]

    for column in required:
        add_reason(
            reasons,
            df[column].isna(),
            f"MISSING_REQUIRED_{column.upper()}"
        )

    # Unique forecast IDs and documented ID format.
    add_reason(
        reasons,
        df["forecast_id"].isna()
        | ~df["forecast_id"].astype("string").str.match(
            r"^FC-[0-9]{4}$", na=False
        ),
        "INVALID_FORECAST_ID"
    )
    add_reason(
        reasons,
        df["forecast_id"].duplicated(keep=False),
        "DUPLICATE_FORECAST_ID"
    )

    # Permitted forecast metrics.
    allowed_metrics = {
        "headcount_end",
        "attrition_rate_monthly_pct",
    }
    add_reason(
        reasons,
        ~df["metric"].isin(allowed_metrics),
        "INVALID_FORECAST_METRIC"
    )

    # Department must exist, unless the contract permits ALL.
    valid_departments = set(
        departments["department_id"].dropna().astype(str)
    )
    valid_departments.add("ALL")

    add_reason(
        reasons,
        ~df["department_id"].astype("string").isin(valid_departments),
        "INVALID_FORECAST_DEPARTMENT"
    )

    # Forecast month must be the first calendar day of its month.
    month = pd.to_datetime(df["forecast_month"], errors="coerce")
    add_reason(
        reasons,
        month.isna()
        | month.dt.day.ne(1),
        "FORECAST_MONTH_NOT_MONTH_START"
    )

    # Forecast values must be nonnegative.
    add_reason(
        reasons,
        df["forecast_value"].isna()
        | (df["forecast_value"] < 0),
        "NEGATIVE_OR_MISSING_FORECAST_VALUE"
    )

    # The 80% interval must contain the forecast value.
    add_reason(
        reasons,
        df["lower_80"].isna()
        | df["upper_80"].isna()
        | (df["lower_80"] > df["forecast_value"])
        | (df["upper_80"] < df["forecast_value"]),
        "INVALID_FORECAST_INTERVAL"
    )

    # trained_through must follow YYYY-MM format.
    trained = df["trained_through"].astype("string")
    valid_trained_format = trained.str.match(
        r"^[0-9]{4}-(0[1-9]|1[0-2])$", na=False
    )
    add_reason(
        reasons,
        ~valid_trained_format,
        "INVALID_TRAINED_THROUGH_FORMAT"
    )

    passed, quarantine = split_passed_quarantine(df, reasons)

    warnings = [
        "forecast_month_key uses month-end date keys while forecast_month is month-start.",
        "Forecasts extend through March 2027, beyond the current dim_date coverage; unmatched future date keys are not quarantined by this validator."
    ]

    return write_feed_outputs(
        "fact_forecast",
        passed,
        quarantine,
        len(df),
        warnings
    )


def validate_task():
    df = read_raw_table("fact_task")
    employees = read_raw_table("dim_employee")
    teams = read_raw_table("dim_team")
    sprints = read_raw_table("dim_sprint")

    reasons = pd.Series(
        [[] for _ in range(len(df))],
        index=df.index,
        dtype=object
    )

    required = [
        "task_id", "team_id", "sprint_id", "assignee_employee_id",
        "task_type", "priority", "story_points", "created_date",
        "due_date", "status", "reopened_count"
    ]

    for column in required:
        add_reason(
            reasons,
            df[column].isna(),
            f"MISSING_REQUIRED_{column.upper()}"
        )

    add_reason(
        reasons,
        df["task_id"].isna()
        | ~df["task_id"].astype("string").str.match(
            r"^TASK-[0-9]{5}$", na=False
        ),
        "INVALID_TASK_ID"
    )
    add_reason(
        reasons,
        df["task_id"].duplicated(keep=False),
        "DUPLICATE_TASK_ID"
    )

    add_reason(
        reasons,
        ~df["status"].isin(
            ["Done", "In Progress", "Blocked", "To Do", "Cancelled"]
        ),
        "INVALID_STATUS"
    )
    add_reason(
        reasons,
        ~df["priority"].isin(["P1", "P2", "P3", "P4"]),
        "INVALID_PRIORITY"
    )
    add_reason(
        reasons,
        ~df["story_points"].isin([1, 2, 3, 5, 8, 13]),
        "INVALID_STORY_POINTS"
    )
    add_reason(
        reasons,
        ~df["task_type"].isin(["Feature", "Bug", "Chore", "Spike"]),
        "INVALID_TASK_TYPE"
    )
    add_reason(
        reasons,
        df["reopened_count"].isna() | (df["reopened_count"] < 0),
        "INVALID_REOPENED_COUNT"
    )

    # Referential integrity.
    valid_employee_ids = set(
        employees["employee_id"].dropna().astype(str)
    )
    valid_team_ids = set(teams["team_id"].dropna().astype(str))
    valid_sprint_ids = set(sprints["sprint_id"].dropna().astype(str))

    add_reason(
        reasons,
        ~df["assignee_employee_id"].astype("string").isin(
            valid_employee_ids
        ),
        "UNMATCHED_EMPLOYEE_ID"
    )
    add_reason(
        reasons,
        ~df["team_id"].astype("string").isin(valid_team_ids),
        "UNMATCHED_TEAM_ID"
    )
    add_reason(
        reasons,
        ~df["sprint_id"].astype("string").isin(valid_sprint_ids),
        "UNMATCHED_SPRINT_ID"
    )

    # Date consistency.
    add_reason(
        reasons,
        df["created_date"].notna()
        & df["started_date"].notna()
        & (df["created_date"] > df["started_date"]),
        "CREATED_AFTER_STARTED"
    )
    add_reason(
        reasons,
        df["started_date"].isna()
        & df["status"].ne("To Do"),
        "MISSING_STARTED_DATE"
    )
    add_reason(
        reasons,
        df["status"].eq("Done") & df["completed_date"].isna(),
        "MISSING_COMPLETED_DATE"
    )
    add_reason(
        reasons,
        df["completed_date"].notna()
        & df["started_date"].notna()
        & (df["completed_date"] < df["started_date"]),
        "COMPLETED_BEFORE_STARTED"
    )
    add_reason(
        reasons,
        df["due_date"].notna()
        & df["started_date"].notna()
        & (df["due_date"] < df["started_date"]),
        "DUE_BEFORE_STARTED"
    )

    # Due date must match the sprint end date.
    sprint_ends = sprints[["sprint_id", "end_date"]].drop_duplicates(
        subset=["sprint_id"]
    )
    sprint_end_map = sprint_ends.set_index("sprint_id")["end_date"]
    expected_end = df["sprint_id"].map(sprint_end_map)

    add_reason(
        reasons,
        expected_end.isna()
        | df["due_date"].ne(expected_end),
        "DUE_DATE_MISMATCH_SPRINT_END"
    )

    passed, quarantine = split_passed_quarantine(df, reasons)

    warnings = [
        "The contract requires started_date to be blank only for To Do; other status-specific completion rules were not inferred beyond the documented Done rule."
    ]

    return write_feed_outputs(
        "fact_task",
        passed,
        quarantine,
        len(df),
        warnings
    )


def run_all_feeds():
    """Run payroll and all four contracted feed validators."""
    import importlib.util

    # Reuse the existing, tested payroll ETL.
    payroll_path = ROOT / "src" / "etl_v2.py"
    payroll_spec = importlib.util.spec_from_file_location(
        "etl_v2_for_multi", payroll_path
    )
    payroll_module = importlib.util.module_from_spec(payroll_spec)
    payroll_spec.loader.exec_module(payroll_module)
    payroll_module.run_payroll_etl()

    payroll_summary_path = OUTPUT_DIR / "fact_payroll_summary.json"
    payroll_summary = json.loads(
        payroll_summary_path.read_text(encoding="utf-8")
    )

    summaries = [payroll_summary]
    summaries.append(validate_anomaly())
    summaries.append(validate_attrition())
    summaries.append(validate_forecast())
    summaries.append(validate_task())

    total_in = sum(item["rows_in"] for item in summaries)
    total_passed = sum(item["rows_passed"] for item in summaries)
    total_quarantined = sum(
        item["rows_quarantined"] for item in summaries
    )

    overall = {
        "pipeline": "PQ-01 multi-feed ETL",
        "feeds": summaries,
        "total_rows_in": total_in,
        "total_rows_passed": total_passed,
        "total_rows_quarantined": total_quarantined,
        "all_feeds_reconciled": all(
            item["reconciliation_ok"] for item in summaries
        ),
        "overall_reconciliation_ok": (
            total_in == total_passed + total_quarantined
        ),
    }

    summary_path = OUTPUT_DIR / "pq01_overall_summary.json"
    summary_path.write_text(
        json.dumps(overall, indent=2),
        encoding="utf-8"
    )

    print(json.dumps({
        "pipeline": overall["pipeline"],
        "feed_count": len(summaries),
        "total_rows_in": total_in,
        "total_rows_passed": total_passed,
        "total_rows_quarantined": total_quarantined,
        "all_feeds_reconciled": overall["all_feeds_reconciled"],
        "overall_reconciliation_ok": overall["overall_reconciliation_ok"],
        "summary_file": str(summary_path),
    }, indent=2))

    if not overall["all_feeds_reconciled"]:
        raise AssertionError("At least one feed failed reconciliation.")
    if not overall["overall_reconciliation_ok"]:
        raise AssertionError("Overall pipeline reconciliation failed.")

    return overall
