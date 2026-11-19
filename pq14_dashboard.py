from pathlib import Path
import pandas as pd
import streamlit as st
import altair as alt

# ------------------------------------------------------------
# PQ-14 | AI Signals Dashboard Advanced
# Aura Workforce | PulseIQ Analytics
# ------------------------------------------------------------

st.set_page_config(
    page_title="PQ-14 | AI Signals Dashboard",
    page_icon="📊",
    layout="wide"
)

DATA_DIR = Path("03_Data/csv")
OUTPUT_DIR = Path("05_Evidence/PQ-14")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_FILES = [
    "fact_anomaly.csv",
    "fact_forecast.csv",
    "fact_headcount_monthly.csv",
]

AI_LABEL = "AI-generated, for human review"

st.title("PulseIQ Analytics")
st.subheader("PQ-14 | AI Signals Dashboard Advanced")
st.caption("Aura Workforce | Anomaly Detection • Workforce Forecasting • Model Transparency")

@st.cache_data
def load_data():
    missing = [name for name in REQUIRED_FILES if not (DATA_DIR / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing source file(s) in 03_Data/csv: " + ", ".join(missing)
        )

    anomaly = pd.read_csv(DATA_DIR / "fact_anomaly.csv")
    forecast = pd.read_csv(DATA_DIR / "fact_forecast.csv")
    headcount = pd.read_csv(DATA_DIR / "fact_headcount_monthly.csv")

    anomaly["money_at_risk"] = pd.to_numeric(
        anomaly["money_at_risk"], errors="coerce"
    )
    anomaly["anomaly_score"] = pd.to_numeric(
        anomaly["anomaly_score"], errors="coerce"
    )

    forecast["forecast_month"] = pd.to_datetime(
        forecast["forecast_month"], errors="coerce"
    )
    for col in ["forecast_value", "lower_80", "upper_80"]:
        forecast[col] = pd.to_numeric(forecast[col], errors="coerce")

    headcount["month_start_date"] = pd.to_datetime(
        headcount["month_start_date"], errors="coerce"
    )
    headcount["headcount_end"] = pd.to_numeric(
        headcount["headcount_end"], errors="coerce"
    )

    return anomaly, forecast, headcount


try:
    anomaly, forecast, headcount = load_data()
except Exception as exc:
    st.error(str(exc))
    st.info("Run this dashboard from the PulseIQ project root folder.")
    st.stop()

# ------------------------------------------------------------
# Anomaly aggregation
# ------------------------------------------------------------

flagged = anomaly[anomaly["flagged"].astype(str).str.upper() == "Y"].copy()

anomaly_summary = (
    flagged.groupby("reason_code", dropna=False)
    .agg(
        flagged_records=("result_id", "count"),
        known_exposure=("money_at_risk", lambda x: x.sum(min_count=1)),
        records_with_known_exposure=("money_at_risk", "count"),
        records_without_exposure=("money_at_risk", lambda x: x.isna().sum()),
    )
    .reset_index()
    .sort_values("known_exposure", ascending=False, na_position="last")
)

anomaly_summary["known_exposure"] = anomaly_summary["known_exposure"].round(2)
anomaly_summary.to_csv(
    OUTPUT_DIR / "PQ14_anomaly_exposure_by_type.csv", index=False
)

# Preserve missing exposure as missing, not zero.
known_exposure = flagged["money_at_risk"].sum(min_count=1)
payroll_rows = int(flagged["money_at_risk"].notna().sum())
missing_exposure_rows = int(flagged["money_at_risk"].isna().sum())

# ------------------------------------------------------------
# Forecast and actual alignment
# ------------------------------------------------------------

head_forecast = forecast[
    forecast["metric"] == "headcount_end"
].copy()

attrition_forecast = forecast[
    forecast["metric"] == "attrition_rate_monthly_pct"
].copy()

# Forecast ALL scope is modeled across D01-D10.
# Exclude D00 from historical actuals because it is not in the forecast scope.
modeled_departments = sorted(
    head_forecast.loc[
        head_forecast["department_id"] != "ALL", "department_id"
    ].dropna().unique()
)

actual_scope = headcount[
    headcount["department_id"].isin(modeled_departments)
].copy()

actual_monthly = (
    actual_scope.groupby("month_start_date", as_index=False)
    .agg(actual_headcount=("headcount_end", "sum"))
    .rename(columns={"month_start_date": "month"})
    .sort_values("month")
)

head_forecast = head_forecast[
    head_forecast["department_id"] == "ALL"
].copy()

head_forecast = head_forecast.sort_values("forecast_month")

# Calculate metric-specific errors only where actuals overlap forecasts.
# Headcount actuals use the same D01-D10 scope as the ALL forecast.
# Attrition actuals use a headcount-weighted department rate.

actual_headcount = actual_monthly[
    ["month", "actual_headcount"]
].rename(columns={
    "month": "forecast_month",
    "actual_headcount": "actual"
})

actual_scope["attrition_rate_monthly_pct"] = pd.to_numeric(
    actual_scope["attrition_rate_monthly_pct"], errors="coerce"
)
actual_scope["headcount_start"] = pd.to_numeric(
    actual_scope["headcount_start"], errors="coerce"
)
actual_scope["headcount_end"] = pd.to_numeric(
    actual_scope["headcount_end"], errors="coerce"
)

actual_scope["average_headcount"] = (
    actual_scope["headcount_start"] + actual_scope["headcount_end"]
) / 2

valid_attrition = actual_scope[
    actual_scope["attrition_rate_monthly_pct"].notna()
    & actual_scope["average_headcount"].gt(0)
].copy()

valid_attrition["weighted_attrition"] = (
    valid_attrition["attrition_rate_monthly_pct"]
    * valid_attrition["average_headcount"]
)

actual_attrition = (
    valid_attrition.groupby("month_start_date", as_index=False)
    .agg(
        weighted_attrition=("weighted_attrition", "sum"),
        average_headcount_total=("average_headcount", "sum")
    )
)

actual_attrition["actual"] = (
    actual_attrition["weighted_attrition"]
    / actual_attrition["average_headcount_total"]
)

actual_attrition = actual_attrition.rename(
    columns={"month_start_date": "forecast_month"}
)[["forecast_month", "actual"]]

error_rows = []

for metric_name, metric_df, actual_df in [
    ("headcount_end", head_forecast, actual_headcount),
    ("attrition_rate_monthly_pct", attrition_forecast, actual_attrition),
]:
    joined = metric_df.merge(
        actual_df, on="forecast_month", how="inner"
    )

    valid = joined[
        joined["actual"].notna()
        & joined["forecast_value"].notna()
    ].copy()

    overlap_count = len(valid)

    # MAPE is undefined for zero actual values.
    valid = valid[valid["actual"] != 0].copy()

    if not valid.empty:
        valid["absolute_percentage_error_pct"] = (
            (valid["actual"] - valid["forecast_value"]).abs()
            / valid["actual"].abs()
            * 100
        )
        mape = valid["absolute_percentage_error_pct"].mean()
        status = "Calculated on overlapping actual months"
    else:
        mape = float("nan")
        if overlap_count == 0:
            status = "Not yet measurable - no overlapping actual months"
        else:
            status = "MAPE undefined - actual values are zero"

    error_rows.append({
        "metric": metric_name,
        "forecast_months": len(metric_df),
        "overlapping_actual_months": overlap_count,
        "MAPE_pct": mape,
        "status": status,
    })

forecast_error = pd.DataFrame(error_rows)
forecast_error.to_csv(
    OUTPUT_DIR / "PQ14_forecast_error_table.csv", index=False
)

# Forecast detail evidence.
forecast_detail = forecast[
    [
        "forecast_id", "metric", "department_id", "forecast_month",
        "forecast_value", "lower_80", "upper_80", "method",
        "trained_through", "model_version"
    ]
].copy()
forecast_detail.to_csv(
    OUTPUT_DIR / "PQ14_forecast_values_and_ranges.csv", index=False
)

# ------------------------------------------------------------
# Executive overview
# ------------------------------------------------------------

st.markdown("### 1. Executive overview")

k = st.columns(4)
k[0].metric("Flagged anomalies", f"{len(flagged):,}")
k[1].metric("Payroll records with exposure", f"{payroll_rows:,}")
k[2].metric(
    "Known money at risk",
    "N/A" if pd.isna(known_exposure) else f"{known_exposure:,.2f}"
)
k[3].metric("Forecast horizon", f"{len(head_forecast)} months")

st.caption(
    f"{missing_exposure_rows:,} flagged records have no money-at-risk value. "
    "These are not treated as zero exposure."
)

st.divider()

# ------------------------------------------------------------
# Anomaly signals
# ------------------------------------------------------------

st.markdown("### 2. Anomaly signals by type")
st.caption(
    "Flagged records are grouped by reason code. Financial exposure is "
    "summed only where the source provides a value."
)

st.markdown("**Known financial exposure by anomaly type**")
exposure_chart_data = anomaly_summary.dropna(
    subset=["known_exposure"]
).copy()

if not exposure_chart_data.empty:
    exposure_chart = (
        alt.Chart(exposure_chart_data)
        .mark_bar()
        .encode(
            x=alt.X("known_exposure:Q", title="Known exposure (source units)"),
            y=alt.Y(
                "reason_code:N",
                sort="-x",
                title="Anomaly type",
                axis=alt.Axis(labelLimit=300, labelFontSize=12)
            ),
            tooltip=[
                "reason_code",
                "flagged_records",
                "known_exposure",
                "records_with_known_exposure",
                "records_without_exposure",
            ],
        )
        .properties(height=350)
    )
    st.altair_chart(exposure_chart, use_container_width=True)
else:
    st.info("No known financial exposure values are available.")

st.caption(AI_LABEL)
st.info(
    "The largest known exposure is associated with statistical outliers. "
    "Attendance anomalies have missing financial exposure by design in the "
    "source contract; they are not assigned a monetary value here."
)

st.markdown("**Anomaly type detail**")
st.dataframe(
    anomaly_summary,
    use_container_width=True,
    hide_index=True
)

st.divider()

# ------------------------------------------------------------
# Headcount forecast
# ------------------------------------------------------------

st.markdown("### 3. Workforce headcount forecast")

st.caption(
    "Historical actuals are aggregated across D01-D10 to align with the "
    "forecast's ALL scope. D00 is excluded because it is not included in "
    "the forecast scope."
)

if not actual_monthly.empty and not head_forecast.empty:
    actual_plot = actual_monthly.copy()
    actual_plot["series"] = "Historical actual"
    actual_plot = actual_plot.rename(
        columns={"actual_headcount": "value"}
    )
    actual_plot = actual_plot[["month", "value", "series"]]

    forecast_plot = head_forecast[
        ["forecast_month", "forecast_value", "lower_80", "upper_80"]
    ].copy()
    forecast_plot = forecast_plot.rename(
        columns={
            "forecast_month": "month",
            "forecast_value": "value",
        }
    )
    forecast_plot["series"] = "Forecast"
    forecast_plot = forecast_plot[["month", "value", "series"]]

    band = head_forecast[
        ["forecast_month", "lower_80", "upper_80"]
    ].rename(columns={"forecast_month": "month"})

    band_chart = (
        alt.Chart(band)
        .mark_area(opacity=0.22)
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("lower_80:Q", title="Ending headcount"),
            y2="upper_80:Q",
            tooltip=["month:T", "lower_80:Q", "upper_80:Q"],
        )
    )

    actual_line = (
        alt.Chart(actual_plot)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("value:Q", title="Ending headcount"),
            color=alt.value("#2878B5"),
            tooltip=["month:T", "value:Q"],
        )
    )

    forecast_line = (
        alt.Chart(forecast_plot)
        .mark_line(point=True, strokeWidth=3, strokeDash=[6, 3])
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("value:Q", title="Ending headcount"),
            color=alt.value("#D97706"),
            tooltip=["month:T", "value:Q"],
        )
    )

    st.altair_chart(
        (band_chart + actual_line + forecast_line).properties(height=400),
        use_container_width=True
    )
    st.caption(AI_LABEL)

    latest_actual = actual_monthly["actual_headcount"].iloc[-1]
    first_forecast = head_forecast["forecast_value"].iloc[0]
    st.info(
        f"Plain-language note: the latest aligned historical headcount is "
        f"{latest_actual:,.0f}. The October 2026 point forecast is "
        f"{first_forecast:,.1f}. The shaded region represents the model's "
        "80% prediction interval, not a guaranteed range."
    )
else:
    st.warning("Historical actuals or headcount forecast records are unavailable.")

st.markdown("**Headcount forecast values and prediction ranges**")
st.dataframe(
    head_forecast[
        [
            "forecast_month", "forecast_value", "lower_80",
            "upper_80", "trained_through", "method"
        ]
    ],
    use_container_width=True,
    hide_index=True
)

st.divider()

# ------------------------------------------------------------
# Attrition rate forecast
# ------------------------------------------------------------

st.markdown("### 4. Monthly attrition-rate forecast")

if not attrition_forecast.empty:
    attrition_plot = attrition_forecast[
        ["forecast_month", "forecast_value", "lower_80", "upper_80"]
    ].copy()

    attrition_band = (
        alt.Chart(attrition_plot)
        .mark_area(opacity=0.22)
        .encode(
            x=alt.X("forecast_month:T", title="Forecast month", axis=alt.Axis(format="%b %Y", labelAngle=-30, tickCount=6)),
            y=alt.Y("lower_80:Q", title="Monthly attrition rate (%)"),
            y2="upper_80:Q",
            tooltip=[
                "forecast_month:T", "lower_80:Q", "upper_80:Q"
            ],
        )
    )

    attrition_line = (
        alt.Chart(attrition_plot)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X("forecast_month:T", title="Forecast month", axis=alt.Axis(format="%b %Y", labelAngle=-30, tickCount=6)),
            y=alt.Y("forecast_value:Q", title="Monthly attrition rate (%)"),
            tooltip=[
                "forecast_month:T", "forecast_value:Q",
                "lower_80:Q", "upper_80:Q"
            ],
        )
    )

    st.altair_chart(
        (attrition_band + attrition_line).properties(height=320),
        use_container_width=True
    )
    st.caption(AI_LABEL)
    st.info(
        "Plain-language note: this chart shows the model's projected monthly "
        "attrition rate and its 80% prediction interval. It is a planning "
        "signal, not a confirmed future outcome."
    )

    st.dataframe(
        attrition_forecast[
            [
                "forecast_month", "forecast_value", "lower_80",
                "upper_80", "trained_through", "method"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No attrition-rate forecast records are available.")

st.divider()

# ------------------------------------------------------------
# Forecast error and model transparency
# ------------------------------------------------------------

st.markdown("### 5. Forecast error and model validation")

st.dataframe(
    forecast_error,
    use_container_width=True,
    hide_index=True
)

st.warning(
    "Forecast error is not yet measurable for the current forecast horizon. "
    "Actual headcount ends in September 2026, and the first forecast month "
    "is October 2026. MAPE is intentionally left blank until actuals become "
    "available for forecast months."
)

st.markdown("**Forecast model metadata**")
metadata = (
    forecast.groupby(
        ["metric", "method", "trained_through", "model_version"],
        dropna=False
    )
    .agg(
        forecast_rows=("forecast_id", "count"),
        first_forecast_month=("forecast_month", "min"),
        last_forecast_month=("forecast_month", "max"),
    )
    .reset_index()
)
st.dataframe(metadata, use_container_width=True, hide_index=True)

st.caption(
    "Prediction intervals are model estimates. AI outputs are decision-support "
    "signals and require human review."
)

# ------------------------------------------------------------
# Downloads and source notes
# ------------------------------------------------------------

st.divider()
st.markdown("### 6. Evidence and downloads")

st.download_button(
    "Download anomaly exposure table",
    data=(OUTPUT_DIR / "PQ14_anomaly_exposure_by_type.csv").read_bytes(),
    file_name="PQ14_anomaly_exposure_by_type.csv",
    mime="text/csv",
)

st.download_button(
    "Download forecast error table",
    data=(OUTPUT_DIR / "PQ14_forecast_error_table.csv").read_bytes(),
    file_name="PQ14_forecast_error_table.csv",
    mime="text/csv",
)

st.download_button(
    "Download forecast values and ranges",
    data=(OUTPUT_DIR / "PQ14_forecast_values_and_ranges.csv").read_bytes(),
    file_name="PQ14_forecast_values_and_ranges.csv",
    mime="text/csv",
)

st.caption(
    "Source: fact_anomaly, fact_forecast and fact_headcount_monthly. "
    "AI-generated, for human review."
)
