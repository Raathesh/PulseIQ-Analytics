
from pathlib import Path
from datetime import date
import argparse
import calendar

import duckdb
import pandas as pd

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)

# ---------------------------------------------------------
# PATHS AND CONFIGURATION
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "05_Starter" / "pulseiq_warehouse.duckdb"
TARGETS_PATH = ROOT / "03_Data" / "csv" / "kpi_targets.csv"
FORECAST_PATH = ROOT / "03_Data" / "csv" / "fact_forecast.csv"
OUTPUT_DIR = ROOT / "outputs"
FORECAST_PATH = ROOT / "03_Data" / "csv" / "fact_forecast.csv"

DEPARTMENTS = {
    "D01": "Engineering",
    "D02": "Product & Design",
    "D03": "Data & AI",
    "D04": "Sales",
    "D05": "Marketing",
    "D06": "Customer Support",
    "D07": "Human Resources",
    "D08": "Finance & Accounts",
    "D09": "Operations & IT",
    "D10": "Legal & Compliance",
}


# ---------------------------------------------------------
# DATA FUNCTIONS
# ---------------------------------------------------------

def load_view(connection, view_name):
    """Load a governed KPI view from the warehouse."""
    try:
        return connection.execute(
            f'SELECT * FROM warehouse."{view_name}"'
        ).fetchdf()
    except Exception as exc:
        raise RuntimeError(
            f"Could not read warehouse view: {view_name}. "
            f"Original error: {exc}"
        ) from exc


def published_only(df):
    """Keep published records when a privacy status is available."""
    if df.empty or "privacy_status" not in df.columns:
        return df

    status = df["privacy_status"].astype(str).str.upper()
    return df[status.isin(["PUBLISHED", "PUBLISH", "PUBLIC"])].copy()


def month_rows(df, column, start_date, end_date):
    """Filter a date column to the requested calendar month."""
    if df.empty or column not in df.columns:
        return df.iloc[0:0].copy()

    result = df.copy()
    result[column] = pd.to_datetime(result[column], errors="coerce")

    return result[
        result[column].dt.date.between(start_date, end_date)
    ].copy()


def money(value):
    if pd.isna(value):
        return "—"
    return f"INR {value:,.2f}"


def percent(value):
    if pd.isna(value):
        return "—"
    return f"{value:.2f}%"


def department_name(department_id):
    return DEPARTMENTS.get(str(department_id), str(department_id))


def make_table(data, widths=None, font_size=7):
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#203864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7C9D6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#EEF3F8")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


# ---------------------------------------------------------
# REPORT BUILDER
# ---------------------------------------------------------

def build_report(month_text):
    try:
        month_start = pd.Timestamp(f"{month_text}-01").date()
    except ValueError as exc:
        raise ValueError("Month must be in YYYY-MM format, e.g. 2026-09") from exc

    if month_start.strftime("%Y-%m") != month_text:
        raise ValueError("Month must be in YYYY-MM format, e.g. 2026-09")

    last_day = calendar.monthrange(
        month_start.year, month_start.month
    )[1]
    month_end = date(month_start.year, month_start.month, last_day)

    if not DB_PATH.exists():
        raise FileNotFoundError(f"Warehouse database not found: {DB_PATH}")

    if not TARGETS_PATH.exists():
        raise FileNotFoundError(f"KPI targets file not found: {TARGETS_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"monthly_report_{month_text}.pdf"

    print(f"Building PulseIQ report for {month_text}...")

    # Read-only connection protects the source database.
    connection = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        headcount = published_only(load_view(
            connection, "m01_headcount_governed"
        ))
        employer_cost = published_only(load_view(
            connection, "m09_employer_cost_governed"
        ))
        overtime = published_only(load_view(
            connection, "m11_overtime_share_governed"
        ))
        attendance = published_only(load_view(
            connection, "m13_attendance_rate_governed"
        ))
        net_profit = load_view(connection, "m17_net_profit")
        operating_margin = load_view(connection, "m18_operating_margin")
        receivables = load_view(connection, "m21_overdue_receivables")

    finally:
        connection.close()

    # Filter each metric using its own reporting date column.
    headcount = month_rows(
        headcount, "month_start_date", month_start, month_end
    )
    employer_cost = month_rows(
        employer_cost, "period_end_date", month_start, month_end
    )
    overtime = month_rows(
        overtime, "period_end_date", month_start, month_end
    )
    attendance = month_rows(
        attendance, "period_end_date", month_start, month_end
    )
    net_profit = month_rows(
        net_profit, "month_start_date", month_start, month_end
    )
    operating_margin = month_rows(
        operating_margin, "month_start_date", month_start, month_end
    )

    # Receivables are a point-in-time snapshot, not a monthly flow.
    receivables["report_date"] = pd.to_datetime(
        receivables["report_date"], errors="coerce"
    )
    eligible_receivables = receivables[
        receivables["report_date"].dt.date <= month_end
    ].copy()

    receivables_cutoff = None
    if not eligible_receivables.empty:
        receivables_cutoff = eligible_receivables["report_date"].max()
        eligible_receivables = eligible_receivables[
            eligible_receivables["report_date"] == receivables_cutoff
        ]

    targets = pd.read_csv(TARGETS_PATH)
    targets["month"] = pd.to_datetime(
        targets["month"], errors="coerce"
    ).dt.strftime("%Y-%m")
    targets = targets[targets["month"] == month_text].copy()
        # Load forecast data separately from actual KPI data.
    if not FORECAST_PATH.exists():
        raise FileNotFoundError(
            f"Forecast file not found: {FORECAST_PATH}"
        )

    forecasts = pd.read_csv(FORECAST_PATH)

    forecasts["forecast_month"] = pd.to_datetime(
        forecasts["forecast_month"], errors="coerce"
    ).dt.strftime("%Y-%m")

    forecast_month = forecasts[
        forecasts["forecast_month"] == month_text
    ].copy()

    # -----------------------------------------------------
    # SUMMARY VALUES
    # -----------------------------------------------------

    published_headcount = (
        headcount["headcount"].sum()
        if not headcount.empty else None
    )

    total_employer_cost = (
        employer_cost["employer_cost"].sum()
        if not employer_cost.empty else None
    )

    profit_value = (
        net_profit["net_profit"].iloc[0]
        if not net_profit.empty else None
    )

    margin_value = (
        operating_margin["operating_margin_pct"].iloc[0]
        if not operating_margin.empty else None
    )

    overdue_value = (
        eligible_receivables["overdue_receivables"].sum()
        if not eligible_receivables.empty else None
    )

    # -----------------------------------------------------
    # PDF CONTENT
    # -----------------------------------------------------

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        leading=25,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#203864"),
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#203864"),
        spaceBefore=10,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SmallNote",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#555555"),
    ))

    document = SimpleDocTemplate(
        str(output_file),
        pagesize=landscape(A4),
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"PulseIQ Monthly Analytics Report - {month_text}",
        author="PulseIQ Analytics",
    )

    story = []

    story.append(Paragraph(
        "PulseIQ Analytics",
        styles["ReportTitle"]
    ))
    story.append(Paragraph(
        f"Monthly Management Report — {month_text}",
        styles["Heading2"]
    ))
    story.append(Paragraph(
        f"Reporting period: {month_start} to {month_end}",
        styles["Normal"]
    ))
    story.append(Paragraph(
        "Data cut-off: Each KPI uses its stated reporting date. "
        "Receivables use the latest available snapshot on or before "
        f"{month_end}.",
        styles["SmallNote"]
    ))
    story.append(Spacer(1, 10))

    # 1. Executive KPI summary
    story.append(Paragraph("1. Executive KPI Summary", styles["SectionHeading"]))

    summary_data = [
        ["Metric", "Reported value", "Reporting basis"],
        ["Published headcount",
         f"{published_headcount:,.0f}" if published_headcount is not None else "No data",
         "Published departments only"],
        ["Employer cost",
         money(total_employer_cost) if total_employer_cost is not None else "No data",
         "Published departments only"],
        ["Net profit",
         money(profit_value) if profit_value is not None else "No data",
         "Monthly value"],
        ["Operating margin",
         percent(margin_value) if margin_value is not None else "No data",
         "Monthly value"],
        ["Overdue receivables",
         money(overdue_value) if overdue_value is not None else "No data",
         f"Snapshot: {receivables_cutoff.date() if receivables_cutoff is not None else 'Unavailable'}"],
    ]

    story.append(make_table(
        summary_data,
        widths=[55 * mm, 45 * mm, 100 * mm],
        font_size=8
    ))

    story.append(Paragraph(
        "Headcount and employer cost totals exclude suppressed groups. "
        "They are published subtotals, not necessarily the full company total.",
        styles["SmallNote"]
    ))

    # -----------------------------------------------------
    # FORECAST OUTLOOK
    # -----------------------------------------------------

    story.append(Paragraph(
        f"Forecast Outlook — {month_text}",
        styles["SectionHeading"]
    ))

    headcount_forecast = forecast_month[
        forecast_month["metric"] == "headcount_end"
    ].copy()

    attrition_forecast = forecast_month[
        forecast_month["metric"] == "attrition_rate_monthly_pct"
    ].copy()

    overall_headcount = headcount_forecast[
        headcount_forecast["department_id"].astype(str) == "ALL"
    ]

    overall_attrition = attrition_forecast[
        attrition_forecast["department_id"].astype(str) == "ALL"
    ]

    def forecast_value_text(value, metric):
        if pd.isna(value):
            return "—"
        if metric == "attrition_rate_monthly_pct":
            return percent(float(value))
        return f"{float(value):,.1f}"

    forecast_summary = [
        ["Forecast metric", "Forecast", "80% lower", "80% upper"]
    ]

    if not overall_headcount.empty:
        row = overall_headcount.iloc[0]
        forecast_summary.append([
            "Total headcount",
            forecast_value_text(row["forecast_value"], "headcount_end"),
            forecast_value_text(row["lower_80"], "headcount_end"),
            forecast_value_text(row["upper_80"], "headcount_end"),
        ])

    if not overall_attrition.empty:
        row = overall_attrition.iloc[0]
        forecast_summary.append([
            "Monthly attrition",
            forecast_value_text(
                row["forecast_value"], "attrition_rate_monthly_pct"
            ),
            forecast_value_text(
                row["lower_80"], "attrition_rate_monthly_pct"
            ),
            forecast_value_text(
                row["upper_80"], "attrition_rate_monthly_pct"
            ),
        ])

    if len(forecast_summary) == 1:
        forecast_summary.append([
            "No forecast available", "—", "—", "—"
        ])

    story.append(make_table(
        forecast_summary,
        widths=[65 * mm, 35 * mm, 35 * mm, 35 * mm],
        font_size=8
    ))

    story.append(Spacer(1, 6))

    # Department-wise headcount forecast
    story.append(Paragraph(
        "Department-wise Headcount Forecast",
        styles["Heading3"]
    ))

    department_forecast = headcount_forecast[
        headcount_forecast["department_id"].astype(str) != "ALL"
    ].copy()

    department_data = [[
        "Department", "Forecast headcount", "80% lower", "80% upper"
    ]]

    for _, row in department_forecast.sort_values(
        "department_id"
    ).iterrows():
        department_data.append([
            department_name(row["department_id"]),
            forecast_value_text(row["forecast_value"], "headcount_end"),
            forecast_value_text(row["lower_80"], "headcount_end"),
            forecast_value_text(row["upper_80"], "headcount_end"),
        ])

    if len(department_data) == 1:
        department_data.append([
            "No department forecast", "—", "—", "—"
        ])

    story.append(make_table(
        department_data,
        widths=[65 * mm, 40 * mm, 35 * mm, 35 * mm],
        font_size=7
    ))

    # Forecast methodology and training cut-off
    if not forecast_month.empty:
        method = str(forecast_month.iloc[0]["method"])
        trained_through = str(
            forecast_month.iloc[0]["trained_through"]
        )

        story.append(Spacer(1, 5))
        story.append(Paragraph(
            f"Forecast methodology: {method}. "
            f"Model trained through: {trained_through}. "
            "The intervals shown are 80% prediction intervals. "
            "Forecasts are estimates, not actual results.",
            styles["SmallNote"]
        ))
    else:
        story.append(Paragraph(
            "No forecast records are available for this selected month.",
            styles["SmallNote"]
        ))




    # 2. Department headcount
    headcount_heading = Paragraph(
        "2. Department Headcount",
        styles["SectionHeading"]
    )

    data = [["Department", "Published headcount"]]

    for _, row in headcount.sort_values("department_id").iterrows():
        data.append([
            department_name(row["department_id"]),
            f"{row['headcount']:,.0f}" if pd.notna(row["headcount"]) else "—"
        ])

    if len(data) == 1:
        data.append(["No published records", "—"])

    headcount_table = make_table(
        data,
        widths=[100 * mm, 55 * mm]
    )

    story.append(KeepTogether([
        headcount_heading,
        headcount_table
    ]))


    # 3. Employer cost

    # 3. Employer cost
    employer_heading = Paragraph(
        "3. Employer Cost by Department",
        styles["SectionHeading"]
    )

    data = [["Department", "Employee count", "Employer cost"]]

    for _, row in employer_cost.sort_values("department_id").iterrows():
        data.append([
            department_name(row["department_id"]),
            f"{row['employee_count']:,.0f}",
            money(row["employer_cost"])
        ])

    if len(data) == 1:
        data.append(["No published records", "—", "—"])

    employer_table = make_table(
        data,
        widths=[75 * mm, 45 * mm, 65 * mm]
    )

    story.append(KeepTogether([
        employer_heading,
        employer_table
    ]))


    # 4. Attendance and overtime
    story.append(Paragraph(
        "4. Attendance and Overtime by Department",
        styles["SectionHeading"]
    ))

    attendance_map = {}
    if not attendance.empty:
        for _, row in attendance.iterrows():
            attendance_map[str(row["department_id"])] = row

    overtime_map = {}
    if not overtime.empty:
        for _, row in overtime.iterrows():
            overtime_map[str(row["department_id"])] = row

    data = [[
        "Department", "Attendance rate", "Attendance target",
        "Overtime share", "Overtime target"
    ]]

    for department_id in sorted(DEPARTMENTS):
        att = attendance_map.get(department_id)
        ot = overtime_map.get(department_id)

        target_row = targets[
            targets["department_id"].astype(str) == department_id
        ]

        attendance_target = None
        overtime_target = None

        if not target_row.empty:
            raw_att_target = target_row.iloc[0].get("attendance_rate_target")
            raw_ot_target = target_row.iloc[0].get("overtime_share_target_pct")

            if pd.notna(raw_att_target):
                attendance_target = float(raw_att_target) * 100

            if pd.notna(raw_ot_target):
                overtime_target = float(raw_ot_target)

        data.append([
            department_name(department_id),
            percent(att["attendance_rate_pct"]) if att is not None else "—",
            percent(attendance_target) if attendance_target is not None else "Not set",
            percent(ot["overtime_share_pct"]) if ot is not None else "—",
            percent(overtime_target) if overtime_target is not None else "Not set",
        ])

    story.append(make_table(
        data,
        widths=[55 * mm, 35 * mm, 35 * mm, 35 * mm, 35 * mm],
        font_size=7
    ))

    story.append(Paragraph(
        "Target values are displayed for comparison. A missing target is "
        "reported as 'Not set'; no pass/fail status is inferred for it.",
        styles["SmallNote"]
    ))

    # 5. Receivables snapshot
    story.append(Paragraph(
        "5. Overdue Receivables Snapshot",
        styles["SectionHeading"]
    ))

    if not eligible_receivables.empty:
        data = [["Client ID", "Overdue receivables"]]
        for _, row in eligible_receivables.sort_values("client_id").iterrows():
            data.append([
                str(row["client_id"]),
                money(row["overdue_receivables"])
            ])
        story.append(make_table(data, widths=[75 * mm, 65 * mm]))
        story.append(Paragraph(
            f"Snapshot date: {receivables_cutoff.date()}. "
            "This is a point-in-time overdue balance, not total open invoices.",
            styles["SmallNote"]
        ))
    else:
        story.append(Paragraph(
            "No eligible receivables snapshot was available for this month.",
            styles["Normal"]
        ))

    # 6. Data notes
    story.append(Paragraph("6. Data and Interpretation Notes", styles["SectionHeading"]))
    notes = [
        "Governed KPI views are used for headcount, employer cost, overtime, attendance, profit, margin and receivables.",
        "Privacy-suppressed records are excluded from published department tables.",
        "The receivables figure uses the latest snapshot on or before the month-end date.",
        "Department targets are read from the KPI targets CSV for the selected month.",
        "A blank or unavailable value is shown as a dash or 'No data'; it is not treated as zero.",
    ]

    for note in notes:
        story.append(Paragraph(f"• {note}", styles["Normal"]))
        story.append(Spacer(1, 3))

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(14 * mm, 8 * mm, "PulseIQ Analytics | Internal Management Report")
        canvas.drawRightString(
            landscape(A4)[0] - 14 * mm,
            8 * mm,
            f"Page {doc.page}"
        )
        canvas.restoreState()

    document.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number
    )

    print("\nREPORT CREATED SUCCESSFULLY")
    print(f"Month: {month_text}")
    print(f"Reporting period: {month_start} to {month_end}")
    print(f"Output: {output_file}")


# ---------------------------------------------------------
# COMMAND-LINE ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build a PulseIQ monthly analytics PDF report."
    )
    parser.add_argument(
        "--month",
        required=True,
        help="Reporting month in YYYY-MM format, e.g. 2026-09"
    )

    args = parser.parse_args()
    build_report(args.month)
