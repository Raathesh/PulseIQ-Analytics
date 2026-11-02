from pathlib import Path
import pandas as pd
import streamlit as st
import altair as alt

# ------------------------------------------------------------
# PQ-12 | Receivables Aging & Cash Flow Analytics
# Aura Workforce | Data Analytics
# ------------------------------------------------------------

st.set_page_config(
    page_title="PQ-12 | Receivables & Cash Flow",
    page_icon="📊",
    layout="wide"
)

DATA_DIR = Path("03_Data/csv")
OUTPUT_DIR = Path("05_Evidence/PQ-12")

REQUIRED_FILES = [
    "fact_invoice.csv",
    "fact_invoice_payment.csv",
    "dim_client.csv",
    "fact_ledger.csv",
]

st.title("PQ-12 | Receivables Aging & Cash Flow Analytics")
st.caption("Aura Workforce | Data Analytics | Reporting cutoff: 30 September 2026")

@st.cache_data
def load_data():
    missing = [name for name in REQUIRED_FILES if not (DATA_DIR / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing source file(s) in 03_Data/csv: " + ", ".join(missing)
        )

    invoice = pd.read_csv(DATA_DIR / "fact_invoice.csv")
    payment = pd.read_csv(DATA_DIR / "fact_invoice_payment.csv")
    client = pd.read_csv(DATA_DIR / "dim_client.csv")
    ledger = pd.read_csv(DATA_DIR / "fact_ledger.csv")

    for col in ["invoice_date", "due_date", "last_payment_date"]:
        invoice[col] = pd.to_datetime(invoice[col], errors="coerce")
    payment["payment_date"] = pd.to_datetime(payment["payment_date"], errors="coerce")
    ledger["entry_date"] = pd.to_datetime(ledger["entry_date"], errors="coerce")

    return invoice, payment, client, ledger


try:
    invoice, payment, client, ledger = load_data()
except Exception as exc:
    st.error(str(exc))
    st.info("Run this app from the PulseIQ project root folder.")
    st.stop()

# Fixed reporting cutoff based on the latest ledger date in the source data.
cutoff = ledger["entry_date"].max()
if pd.isna(cutoff):
    st.error("Could not determine the reporting cutoff from fact_ledger.csv.")
    st.stop()

# ------------------------------------------------------------
# Receivables
# ------------------------------------------------------------
OPEN_STATUSES = ["SENT", "OVERDUE", "PARTIALLY_PAID"]
open_inv = invoice[invoice["status"].isin(OPEN_STATUSES)].copy()

open_inv["days_past_due_calc"] = (cutoff - open_inv["due_date"]).dt.days
open_inv["days_past_due_calc"] = open_inv["days_past_due_calc"].fillna(0).clip(lower=0)

def make_ageing_bucket(row):
    if pd.isna(row["due_date"]):
        return "Date missing"
    if row["due_date"] > cutoff:
        return "Not yet due"
    days = int(row["days_past_due_calc"])
    if days <= 30:
        return "0-30 days"
    if days <= 60:
        return "31-60 days"
    if days <= 90:
        return "61-90 days"
    return "90+ days"

open_inv["calculated_bucket"] = open_inv.apply(make_ageing_bucket, axis=1)

bucket_order = ["Not yet due", "0-30 days", "31-60 days", "61-90 days", "90+ days"]
ageing = (
    open_inv.groupby("calculated_bucket", dropna=False)
    .agg(invoice_count=("invoice_id", "nunique"),
         outstanding=("balance_due", "sum"))
    .reindex(bucket_order, fill_value=0)
    .reset_index()
    .rename(columns={"calculated_bucket": "ageing_bucket"})
)

open_total = float(open_inv["balance_due"].sum())
ageing_total = float(ageing["outstanding"].sum())
overdue_inv = open_inv[open_inv["due_date"] <= cutoff]
overdue_total = float(overdue_inv["balance_due"].sum())

# ------------------------------------------------------------
# Payment reconciliation and client performance
# ------------------------------------------------------------
payment_by_invoice = payment.groupby("invoice_id", as_index=False)["amount"].sum()
payment_by_invoice = payment_by_invoice.rename(columns={"amount": "payment_transaction_total"})

invoice_recon = invoice.merge(payment_by_invoice, on="invoice_id", how="left")
invoice_recon["payment_transaction_total"] = invoice_recon[
    "payment_transaction_total"
].fillna(0)
invoice_recon["payment_difference"] = (
    invoice_recon["amount_paid"] - invoice_recon["payment_transaction_total"]
)

payment_exceptions = invoice_recon[
    invoice_recon["payment_difference"].abs() > 0.01
].copy()

paid = invoice[
    (invoice["status"] == "PAID") & invoice["days_to_pay"].notna()
].copy()

client_perf = (
    paid.groupby("client_id")
    .agg(
        paid_invoice_count=("invoice_id", "nunique"),
        average_days_to_pay=("days_to_pay", "mean"),
        median_days_to_pay=("days_to_pay", "median"),
    )
    .reset_index()
    .merge(
        client[["client_id", "client_name", "payment_terms_days", "payment_behaviour"]],
        on="client_id",
        how="left",
        validate="one_to_one",
    )
)

client_perf["days_over_terms"] = (
    client_perf["average_days_to_pay"] - client_perf["payment_terms_days"]
)
client_perf = client_perf.sort_values("average_days_to_pay", ascending=False)

# ------------------------------------------------------------
# Cash flow: bank account 1001 only
# ------------------------------------------------------------
bank = ledger[ledger["account_code"] == 1001].copy()
bank = bank[bank["source_type"] != "OPENING"].copy()

inflow_types = ["INVOICE_PAYMENT", "INTEREST"]
outflow_types = [
    "EXPENSE_PAYMENT",
    "SALARY_PAYMENT",
    "STATUTORY_REMITTANCE",
    "GST_SETTLEMENT",
    "BANK_CHARGES",
]

bank["cash_inflow"] = 0.0
bank["cash_outflow"] = 0.0
bank.loc[bank["source_type"].isin(inflow_types), "cash_inflow"] = bank["debit"]
bank.loc[bank["source_type"].isin(outflow_types), "cash_outflow"] = bank["credit"]
bank["month"] = bank["entry_date"].dt.to_period("M").astype(str)

monthly_cash = (
    bank.groupby("month", as_index=False)
    .agg(cash_inflow=("cash_inflow", "sum"),
         cash_outflow=("cash_outflow", "sum"))
)
monthly_cash["net_cash_flow"] = (
    monthly_cash["cash_inflow"] - monthly_cash["cash_outflow"]
)

total_inflow = float(monthly_cash["cash_inflow"].sum())
total_outflow = float(monthly_cash["cash_outflow"].sum())
net_cash_flow = total_inflow - total_outflow

# ------------------------------------------------------------
# Sidebar filters
# ------------------------------------------------------------
st.sidebar.header("Dashboard filters")
selected_statuses = st.sidebar.multiselect(
    "Invoice status",
    options=OPEN_STATUSES,
    default=OPEN_STATUSES,
)
selected_clients = st.sidebar.multiselect(
    "Client",
    options=sorted(open_inv["client_id"].dropna().unique()),
    format_func=lambda cid: (
        client.set_index("client_id")["client_name"].get(cid, cid)
    ),
)

filtered = open_inv[open_inv["status"].isin(selected_statuses)].copy()
if selected_clients:
    filtered = filtered[filtered["client_id"].isin(selected_clients)]

filtered_total = float(filtered["balance_due"].sum())
filtered_overdue = float(
    filtered.loc[filtered["due_date"] <= cutoff, "balance_due"].sum()
)

# ------------------------------------------------------------
# KPI cards
# ------------------------------------------------------------
st.subheader("Receivables overview")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Open receivables", f"₹{filtered_total:,.0f}")
k2.metric("Overdue receivables", f"₹{filtered_overdue:,.0f}")
k3.metric("Open invoices", f"{len(filtered):,}")
k4.metric(
    "Average days to pay (all paid invoices)",
    f"{paid['days_to_pay'].mean():.2f} days"
)
st.caption(
    f"Cutoff: {cutoff:%d %B %Y} | Open statuses included: SENT, OVERDUE, PARTIALLY_PAID"
)

# ------------------------------------------------------------
# Ageing
# ------------------------------------------------------------
st.divider()
st.subheader("Receivables ageing")

filtered["calculated_bucket"] = filtered.apply(make_ageing_bucket, axis=1)
filtered_ageing = (
    filtered.groupby("calculated_bucket")
    .agg(invoice_count=("invoice_id", "nunique"),
         outstanding=("balance_due", "sum"))
    .reindex(bucket_order, fill_value=0)
    .reset_index()
    .rename(columns={"calculated_bucket": "ageing_bucket"})
)

left, right = st.columns([1.25, 1])
with left:
    ageing_chart = alt.Chart(filtered_ageing).mark_bar().encode(
        x=alt.X("ageing_bucket:N", sort=bucket_order, title="Ageing bucket"),
        y=alt.Y("outstanding:Q", title="Outstanding (₹)"),
        tooltip=[
            alt.Tooltip("ageing_bucket:N", title="Bucket"),
            alt.Tooltip("invoice_count:Q", title="Invoices"),
            alt.Tooltip("outstanding:Q", title="Outstanding", format=",.0f"),
        ],
    ).properties(height=330)
    st.altair_chart(ageing_chart, use_container_width=True)

with right:
    st.dataframe(
        filtered_ageing.style.format({"outstanding": "₹{:,.0f}"}),
        use_container_width=True,
        hide_index=True,
    )
    st.metric("Filtered ageing reconciliation variance",
              f"₹{filtered_total - filtered_ageing['outstanding'].sum():,.2f}")

# ------------------------------------------------------------
# Client performance
# ------------------------------------------------------------
st.divider()
st.subheader("Client payment performance")
st.caption(
    "Based on paid invoices with a populated days_to_pay value. "
    "Days over terms compares average days to pay with contractual payment terms."
)

client_chart = alt.Chart(client_perf.head(15)).mark_bar().encode(
    x=alt.X("average_days_to_pay:Q", title="Average days to pay"),
    y=alt.Y("client_name:N", sort="-x", title="Client"),
    color=alt.condition(
        alt.datum.days_over_terms > 0,
        alt.value("#D97706"),
        alt.value("#2563EB"),
    ),
    tooltip=[
        "client_name:N",
        alt.Tooltip("paid_invoice_count:Q", title="Paid invoices"),
        alt.Tooltip("average_days_to_pay:Q", title="Average days", format=".2f"),
        alt.Tooltip("payment_terms_days:Q", title="Terms (days)"),
        alt.Tooltip("days_over_terms:Q", title="Days over terms", format=".2f"),
    ],
).properties(height=430)
st.altair_chart(client_chart, use_container_width=True)
st.dataframe(
    client_perf.style.format({
        "average_days_to_pay": "{:.2f}",
        "median_days_to_pay": "{:.2f}",
        "days_over_terms": "{:+.2f}",
    }),
    use_container_width=True,
    hide_index=True,
)

# ------------------------------------------------------------
# Cash flow
# ------------------------------------------------------------
st.divider()
st.subheader("Monthly cash flow — Operating bank account 1001")

c1, c2, c3 = st.columns(3)
c1.metric("Cash inflow", f"₹{total_inflow:,.0f}")
c2.metric("Cash outflow", f"₹{total_outflow:,.0f}")
c3.metric("Net cash flow", f"₹{net_cash_flow:,.0f}")

cash_long = monthly_cash.melt(
    id_vars="month",
    value_vars=["cash_inflow", "cash_outflow"],
    var_name="cash_type",
    value_name="amount",
)
cash_long["cash_type"] = cash_long["cash_type"].map({
    "cash_inflow": "Cash inflow",
    "cash_outflow": "Cash outflow",
})

cash_chart = alt.Chart(cash_long).mark_bar().encode(
    x=alt.X("month:N", title="Month", sort=monthly_cash["month"].tolist()),
    xOffset="cash_type:N",
    y=alt.Y("amount:Q", title="Cash movement (₹)"),
    color="cash_type:N",
    tooltip=[
        "month:N",
        "cash_type:N",
        alt.Tooltip("amount:Q", format=",.0f"),
    ],
).properties(height=360)
st.altair_chart(cash_chart, use_container_width=True)

net_chart = alt.Chart(monthly_cash).mark_line(point=True).encode(
    x=alt.X("month:N", title="Month", sort=monthly_cash["month"].tolist()),
    y=alt.Y("net_cash_flow:Q", title="Net cash flow (₹)"),
    tooltip=[
        "month:N",
        alt.Tooltip("net_cash_flow:Q", format=",.0f"),
    ],
).properties(height=260)
st.altair_chart(net_chart, use_container_width=True)
st.dataframe(
    monthly_cash.style.format({
        "cash_inflow": "₹{:,.0f}",
        "cash_outflow": "₹{:,.0f}",
        "net_cash_flow": "₹{:,.0f}",
    }),
    use_container_width=True,
    hide_index=True,
)

st.caption(
    "Cash-flow methodology: bank account 1001; invoice payments and interest are inflows; "
    "expense payments, salary payments, statutory remittances, GST settlements and bank "
    "charges are outflows. Opening balance is excluded."
)

# ------------------------------------------------------------
# Reconciliation and exceptions
# ------------------------------------------------------------
st.divider()
st.subheader("Reconciliation & data-quality checks")

r1, r2, r3 = st.columns(3)
r1.metric("Open receivables", f"₹{open_total:,.0f}")
r2.metric("Ageing bucket total", f"₹{ageing_total:,.0f}")
r3.metric("Ageing variance", f"₹{open_total - ageing_total:,.2f}")

st.write("**Invoice vs payment transaction reconciliation**")
st.write(
    f"Invoice amount_paid total: ₹{invoice['amount_paid'].sum():,.2f}  \n"
    f"Payment transaction total: ₹{payment['amount'].sum():,.2f}  \n"
    f"Aggregate difference: ₹{invoice['amount_paid'].sum() - payment['amount'].sum():,.2f}"
)

if payment_exceptions.empty:
    st.success("No invoice-level payment differences found.")
else:
    st.warning(
        f"{len(payment_exceptions)} invoice(s) have a payment difference. "
        "Review the exceptions; source data has not been modified."
    )
    st.dataframe(
        payment_exceptions[
            ["invoice_id", "status", "amount_paid",
             "payment_transaction_total", "payment_difference"]
        ].style.format({
            "amount_paid": "₹{:,.2f}",
            "payment_transaction_total": "₹{:,.2f}",
            "payment_difference": "₹{:+,.2f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

# ------------------------------------------------------------
# CSV exports
# ------------------------------------------------------------
st.divider()
st.subheader("Download PQ-12 analysis files")

receivables_export = open_inv[
    [
        "invoice_id", "invoice_number", "client_id", "invoice_date",
        "due_date", "status", "total_amount", "amount_paid",
        "balance_due", "days_past_due_calc", "calculated_bucket",
    ]
].copy()

client_export = client_perf.copy()
cash_export = monthly_cash.copy()
ageing_export = ageing.copy()

def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")

d1, d2, d3, d4 = st.columns(4)
d1.download_button(
    "Receivables ageing CSV",
    data=csv_bytes(receivables_export),
    file_name="PQ12_receivables_ageing.csv",
    mime="text/csv",
)
d2.download_button(
    "Client performance CSV",
    data=csv_bytes(client_export),
    file_name="PQ12_client_payment_performance.csv",
    mime="text/csv",
)
d3.download_button(
    "Monthly cash flow CSV",
    data=csv_bytes(cash_export),
    file_name="PQ12_monthly_cash_flow.csv",
    mime="text/csv",
)
d4.download_button(
    "Ageing summary CSV",
    data=csv_bytes(ageing_export),
    file_name="PQ12_ageing_reconciliation.csv",
    mime="text/csv",
)

st.caption(
    "Source data is read-only. CSV downloads contain calculated outputs; "
    "they do not overwrite the original datasets."
)

