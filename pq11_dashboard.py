from pathlib import Path
import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Aura Workforce | PQ-11", page_icon="📊", layout="wide")
st.title("Aura Workforce – Financial Analytics")
st.subheader("PQ-11 | Profit & Loss and Expense Analytics")
st.caption("PulseIQ Analytics | Reporting cut-off: 30 September 2026")

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "03_Data" / "csv"


@st.cache_data
def load_data():
    required = ["fact_ledger.csv", "dim_account.csv", "fact_expense.csv", "dim_vendor.csv"]
    missing = [f for f in required if not (DATA_DIR / f).exists()]
    if missing:
        raise FileNotFoundError("Missing files in 03_Data/csv: " + ", ".join(missing))

    ledger = pd.read_csv(DATA_DIR / "fact_ledger.csv")
    accounts = pd.read_csv(DATA_DIR / "dim_account.csv")
    expenses = pd.read_csv(DATA_DIR / "fact_expense.csv")
    vendors = pd.read_csv(DATA_DIR / "dim_vendor.csv")

    for df in (ledger, accounts):
        df["account_code"] = df["account_code"].astype(str).str.strip()

    expenses["category_account"] = expenses["category_account"].astype(str).str.strip()
    accounts["is_group"] = accounts["is_group"].astype(str).str.strip().str.upper()
    accounts["is_active"] = accounts["is_active"].astype(str).str.strip().str.upper()
    ledger["posting_period"] = ledger["posting_period"].astype(str).str.strip()
    ledger["signed_amount_debit_positive"] = pd.to_numeric(
        ledger["signed_amount_debit_positive"], errors="coerce"
    ).fillna(0)
    expenses["amount_excl_gst"] = pd.to_numeric(
        expenses["amount_excl_gst"], errors="coerce"
    ).fillna(0)
    return ledger, accounts, expenses, vendors


try:
    ledger, accounts, expenses, vendors = load_data()
except Exception as exc:
    st.error(f"Unable to load PQ-11 data: {exc}")
    st.stop()

# Active, non-group P&L accounts only; prevents group-account double counting.
pl_accounts = accounts[
    (accounts["statement"].astype(str).str.strip() == "Profit & Loss")
    & (accounts["is_group"] == "N")
    & (accounts["is_active"] == "Y")
].copy()

pl_ledger = ledger.merge(
    pl_accounts[["account_code", "account_name", "account_type"]],
    on="account_code", how="inner", validate="many_to_one"
)

# Metric dictionary: M16 revenue = accounts 4001–4004.
# Account 4900 is other income: excluded from revenue, included in net profit.
revenue_codes = ["4001", "4002", "4003", "4004"]
revenue = (
    pl_ledger[pl_ledger["account_code"].isin(revenue_codes)]
    .groupby("posting_period")["signed_amount_debit_positive"].sum().mul(-1)
)
other_income = (
    pl_ledger[pl_ledger["account_code"] == "4900"]
    .groupby("posting_period")["signed_amount_debit_positive"].sum().mul(-1)
)
expense_accounts = pl_ledger[pl_ledger["account_code"].str.startswith("5")]
monthly_expenses = expense_accounts.groupby("posting_period")[
    "signed_amount_debit_positive"
].sum()

periods = sorted(pl_ledger["posting_period"].dropna().unique())
pnl = pd.DataFrame({"posting_period": periods})
pnl["operating_revenue"] = pnl["posting_period"].map(revenue).fillna(0)
pnl["other_income"] = pnl["posting_period"].map(other_income).fillna(0)
pnl["expenses"] = pnl["posting_period"].map(monthly_expenses).fillna(0)
pnl["net_profit"] = pnl["operating_revenue"] + pnl["other_income"] - pnl["expenses"]
pnl["operating_margin_percent"] = (
    pnl["net_profit"] / pnl["operating_revenue"].replace(0, pd.NA) * 100
).fillna(0)

st.sidebar.header("Dashboard Filters")
period_options = ["All months"] + periods
selected_month = st.sidebar.selectbox("Select reporting month", period_options)
view = pnl.copy() if selected_month == "All months" else pnl[pnl["posting_period"] == selected_month].copy()

total_revenue = view["operating_revenue"].sum()
total_other_income = view["other_income"].sum()
total_expenses = view["expenses"].sum()
total_profit = view["net_profit"].sum()
overall_margin = total_profit / total_revenue * 100 if total_revenue else 0

st.markdown("### Financial Performance")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Operating Revenue", f"₹{total_revenue:,.0f}")
c2.metric("Total Expenses", f"₹{total_expenses:,.0f}")
c3.metric("Net Profit", f"₹{total_profit:,.0f}")
c4.metric("Operating Margin", f"{overall_margin:.2f}%")
st.caption(
    f"Other income (account 4900): ₹{total_other_income:,.0f}. "
    "Excluded from operating revenue but included in net profit."
)

st.markdown("### Monthly Profit & Loss")
display_pnl = view.rename(columns={
    "posting_period": "Month",
    "operating_revenue": "Operating Revenue",
    "other_income": "Other Income",
    "expenses": "Expenses",
    "net_profit": "Net Profit",
    "operating_margin_percent": "Operating Margin (%)",
})
st.dataframe(display_pnl.style.format({
    "Operating Revenue": "₹{:,.2f}",
    "Other Income": "₹{:,.2f}",
    "Expenses": "₹{:,.2f}",
    "Net Profit": "₹{:,.2f}",
    "Operating Margin (%)": "{:.2f}%",
}), use_container_width=True, hide_index=True)

st.markdown("### Revenue, Expenses and Profit Trends")
# Convert the three financial measures to long form and use xOffset
# so the bars are grouped side-by-side rather than stacked.
trend_long = view[
    ["posting_period", "operating_revenue", "expenses", "net_profit"]
].melt(
    id_vars="posting_period",
    var_name="Measure",
    value_name="Amount",
)
trend_long["Measure"] = trend_long["Measure"].map({
    "operating_revenue": "Operating Revenue",
    "expenses": "Expenses",
    "net_profit": "Net Profit",
})

grouped_trend = (
    alt.Chart(trend_long)
    .mark_bar()
    .encode(
        x=alt.X("posting_period:N", title="Month", sort=periods,
                axis=alt.Axis(labelAngle=-45)),
        xOffset=alt.XOffset("Measure:N"),
        y=alt.Y("Amount:Q", title="Amount (₹)", axis=alt.Axis(format=",.0f")),
        color=alt.Color("Measure:N", title="Financial Measure"),
        tooltip=[
            alt.Tooltip("posting_period:N", title="Month"),
            alt.Tooltip("Measure:N", title="Measure"),
            alt.Tooltip("Amount:Q", title="Amount (₹)", format=",.2f"),
        ],
    )
    .properties(height=380)
)
st.altair_chart(grouped_trend, use_container_width=True)

st.markdown("### Operating Margin Trend")
margin_trend = view.set_index("posting_period")[["operating_margin_percent"]].rename(
    columns={"operating_margin_percent": "Operating Margin (%)"}
)
st.line_chart(margin_trend, use_container_width=True)

st.markdown("### Expense Category Analysis")
category_spend = (
    expenses.groupby("category_account", as_index=False)["amount_excl_gst"].sum()
    .merge(
        accounts[["account_code", "account_name"]],
        left_on="category_account", right_on="account_code",
        how="left", validate="many_to_one"
    )
    .sort_values("amount_excl_gst", ascending=False)
)
category_chart = (
    alt.Chart(category_spend)
    .mark_bar()
    .encode(
        x=alt.X("amount_excl_gst:Q", title="Amount excluding GST (₹)",
                axis=alt.Axis(format=",.0f")),
        y=alt.Y("account_name:N", title="Expense Category",
                sort="-x", axis=alt.Axis(labelLimit=260)),
        tooltip=[
            alt.Tooltip("account_name:N", title="Category"),
            alt.Tooltip("amount_excl_gst:Q", title="Amount (₹)", format=",.2f"),
        ],
    )
    .properties(height=420)
)
st.altair_chart(category_chart, use_container_width=True)
st.dataframe(category_spend[
    ["category_account", "account_name", "amount_excl_gst"]
].rename(columns={
    "category_account": "Account Code",
    "account_name": "Expense Category",
    "amount_excl_gst": "Amount Excluding GST (₹)",
}).style.format({"Amount Excluding GST (₹)": "₹{:,.2f}"}),
    use_container_width=True, hide_index=True)

st.markdown("### Top 10 Vendors by Expense")
vendor_spend = (
    expenses.groupby("vendor_id", as_index=False)["amount_excl_gst"].sum()
    .merge(vendors[["vendor_id", "vendor_name"]], on="vendor_id",
           how="left", validate="many_to_one")
    .sort_values("amount_excl_gst", ascending=False).head(10)
)
vendor_chart = (
    alt.Chart(vendor_spend)
    .mark_bar()
    .encode(
        x=alt.X("amount_excl_gst:Q", title="Amount excluding GST (₹)",
                axis=alt.Axis(format=",.0f")),
        y=alt.Y("vendor_name:N", title="Vendor", sort="-x",
                axis=alt.Axis(labelLimit=300)),
        tooltip=[
            alt.Tooltip("vendor_id:N", title="Vendor ID"),
            alt.Tooltip("vendor_name:N", title="Vendor"),
            alt.Tooltip("amount_excl_gst:Q", title="Amount (₹)", format=",.2f"),
        ],
    )
    .properties(height=420)
)
st.altair_chart(vendor_chart, use_container_width=True)
st.dataframe(vendor_spend[
    ["vendor_id", "vendor_name", "amount_excl_gst"]
].rename(columns={
    "vendor_id": "Vendor ID",
    "vendor_name": "Vendor",
    "amount_excl_gst": "Amount Excluding GST (₹)",
}).style.format({"Amount Excluding GST (₹)": "₹{:,.2f}"}),
    use_container_width=True, hide_index=True)

st.markdown("### Expense Reconciliation")
expense_ledger = ledger[
    ledger["source_type"].astype(str).str.strip().str.upper() == "EXPENSE"
].copy()
expense_ledger["account_code"] = expense_ledger["account_code"].astype(str).str.strip()
expense_account_codes = set(category_spend["category_account"])
expense_ledger = expense_ledger[
    expense_ledger["account_code"].isin(expense_account_codes)
]
fact_expense_total = expenses["amount_excl_gst"].sum()
ledger_expense_total = expense_ledger["signed_amount_debit_positive"].sum()
variance = fact_expense_total - ledger_expense_total

tieout = pd.DataFrame({
    "Measure": [
        "Fact expense excluding GST",
        "Ledger expense-account debits",
        "Difference",
    ],
    "Amount (₹)": [fact_expense_total, ledger_expense_total, variance],
})
st.dataframe(tieout.style.format({"Amount (₹)": "₹{:,.2f}"}),
             use_container_width=True, hide_index=True)
if abs(variance) < 0.01:
    st.success("Expense reconciliation passed: zero variance.")
else:
    st.warning("Expense reconciliation requires investigation.")

st.markdown("### Dataset Coverage")
d1, d2, d3 = st.columns(3)
d1.metric("Ledger Lines", f"{len(ledger):,}")
d2.metric("Expense Bills", f"{len(expenses):,}")
d3.metric("P&L Months", f"{len(pnl):,}")

st.info(
    "The workbook README provides dataset coverage counts, not a P&L revenue "
    "or profit headline total. The expense-to-ledger tie-out above is independently "
    "reconciled; no unsupported README financial tie-out is claimed."
)

st.markdown("### Download PQ-11 Evidence")
st.download_button(
    "Download Monthly P&L CSV",
    data=pnl.to_csv(index=False).encode("utf-8"),
    file_name="PQ11_monthly_PnL.csv",
    mime="text/csv",
)
st.download_button(
    "Download Expense Reconciliation CSV",
    data=tieout.to_csv(index=False).encode("utf-8"),
    file_name="PQ11_expense_reconciliation.csv",
    mime="text/csv",
)
st.caption("Aura Workforce | PulseIQ Analytics | PQ-11")
