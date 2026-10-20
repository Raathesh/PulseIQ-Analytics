import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "05_Starter" / "pulseiq.duckdb"
OUTPUT_DIR = ROOT / "outputs" / "pq01"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_payroll_etl():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        payroll = con.execute(
            "SELECT * FROM raw.fact_payroll"
        ).fetchdf()

        employees = con.execute(
            "SELECT DISTINCT employee_key FROM raw.dim_employee"
        ).fetchdf()
    finally:
        con.close()

    # Validate employee references using the historical employee key.
    valid_employee_keys = set(
        employees["employee_key"].dropna().tolist()
    )

    payroll["quarantine_reasons"] = [[] for _ in range(len(payroll))]

    unmatched_mask = (
        payroll["employee_key"].isna()
        | ~payroll["employee_key"].isin(valid_employee_keys)
    )

    for idx in payroll.index[unmatched_mask]:
        payroll.at[idx, "quarantine_reasons"].append(
            "UNMATCHED_EMPLOYEE_KEY"
        )

    # Detect duplicate employee-run groups dynamically.
    duplicate_mask = payroll.duplicated(
        subset=["employee_key", "run_id"],
        keep=False
    )

    duplicate_rows = payroll.loc[duplicate_mask].copy()

    if not duplicate_rows.empty:
        group_sizes = duplicate_rows.groupby(
            ["employee_key", "run_id"],
            dropna=False
        ).size()

        pi_x_counts = duplicate_rows.assign(
            is_pi_x=duplicate_rows["payroll_item_id"]
            .astype("string")
            .str.startswith("PI-X", na=False)
        ).groupby(
            ["employee_key", "run_id"],
            dropna=False
        )["is_pi_x"].sum()

        normal_counts = group_sizes - pi_x_counts

        unexpected = (
            (group_sizes != 2)
            | (pi_x_counts != 1)
            | (normal_counts != 1)
        )

        if unexpected.any():
            bad_groups = unexpected[unexpected].index.tolist()
            raise ValueError(
                "Unexpected duplicate patterns found; "
                f"pipeline stopped safely. Groups: {bad_groups}"
            )

        # Keep the non-PI-X record in each validated duplicate pair.
        pi_x_mask = (
            payroll["payroll_item_id"]
            .astype("string")
            .str.startswith("PI-X", na=False)
        )

        duplicate_quarantine_mask = duplicate_mask & pi_x_mask

        for idx in payroll.index[duplicate_quarantine_mask]:
            payroll.at[idx, "quarantine_reasons"].append(
                "DUPLICATE_EMPLOYEE_RUN"
            )

    # Serialize reasons so every failure remains visible in output.
    payroll["quarantine_reason"] = payroll[
        "quarantine_reasons"
    ].apply(lambda reasons: "|".join(reasons) if reasons else None)

    quarantine = payroll[
        payroll["quarantine_reason"].notna()
    ].copy()

    passed = payroll[
        payroll["quarantine_reason"].isna()
    ].copy()

    input_count = len(payroll)
    passed_count = len(passed)
    quarantine_count = len(quarantine)

    if input_count != passed_count + quarantine_count:
        raise AssertionError("Input/pass/quarantine counts do not reconcile.")

    # Remove internal helper column from the business-data outputs.
    helper_columns = ["quarantine_reasons"]

    quarantine.drop(columns=helper_columns).to_csv(
        OUTPUT_DIR / "fact_payroll_quarantine.csv",
        index=False
    )
    passed.drop(
        columns=helper_columns + ["quarantine_reason"]
    ).to_csv(
        OUTPUT_DIR / "fact_payroll_passed.csv",
        index=False
    )

    summary = {
        "table": "fact_payroll",
        "rows_in": input_count,
        "rows_passed": passed_count,
        "rows_quarantined": quarantine_count,
        "reconciliation_ok": (
            input_count == passed_count + quarantine_count
        ),
        "quarantine_reasons": {
            str(reason): int(count)
            for reason, count in (
                quarantine["quarantine_reason"]
                .str.split("|")
                .explode()
                .value_counts()
                .items()
            )
        },
    }

    with open(
        OUTPUT_DIR / "fact_payroll_summary.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nOutput folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    run_payroll_etl()
