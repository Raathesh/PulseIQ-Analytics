"""PQ-08 Team Productivity Analytics dashboard.
Run from repository root: python -m streamlit run src/pq08_productivity_app.py
"""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "03_Data" / "csv"
MIN_GROUP = 5

st.set_page_config(page_title="PQ-08 Team Productivity", page_icon="ðŸ“ˆ", layout="wide")
st.title("PQ-08 | Team Productivity Analytics")
st.caption("Sprint-level task metrics. Velocity is team-specific and should not be compared across teams.")

@st.cache_data
def load(name):
    return pd.read_csv(DATA / name, low_memory=False)

try:
    tasks = load("fact_task.csv")
    teams = load("dim_team.csv")
    sprints = load("dim_sprint.csv")
except Exception as e:
    st.error(f"Could not load source data: {e}")
    st.stop()

required = {"task_id","team_id","sprint_id","story_points","status","reopened_count",
            "cycle_time_days","is_overdue_at_cutoff","completed_on_time"}
missing = required - set(tasks.columns)
if missing:
    st.error(f"Missing columns in fact_task.csv: {', '.join(sorted(missing))}")
    st.stop()

for c in ["story_points","reopened_count","cycle_time_days"]:
    tasks[c] = pd.to_numeric(tasks[c], errors="coerce")
team_names = teams.drop_duplicates("team_id").set_index("team_id")["team_name"].to_dict()
sprint_names = sprints.drop_duplicates("sprint_id").set_index("sprint_id")["sprint_name"].to_dict()
sprints["start_date"] = pd.to_datetime(sprints["start_date"], errors="coerce")
sprint_order = sprints.sort_values("start_date")["sprint_id"].tolist()
tasks["team_name"] = tasks["team_id"].map(team_names).fillna(tasks["team_id"])
tasks["sprint_name"] = tasks["sprint_id"].map(sprint_names).fillna(tasks["sprint_id"])

duplicate_ids = int(tasks["task_id"].duplicated().sum())
unknown_teams = int((~tasks["team_id"].isin(teams["team_id"])).sum())
unknown_sprints = int((~tasks["sprint_id"].isin(sprints["sprint_id"])).sum())
negative_cycle = int((tasks["cycle_time_days"] < 0).sum())
negative_done_cycle = int(((tasks["status"] == "Done") & (tasks["cycle_time_days"] < 0)).sum())
missing_done_cycle = int(((tasks["status"] == "Done") & tasks["cycle_time_days"].isna()).sum())

def rate(n, d):
    return (100 * n / d) if d else float("nan")

st.sidebar.header("Filters")
team_ids = teams.sort_values("team_name")["team_id"].tolist()
selected_teams = st.sidebar.multiselect(
    "Team", team_ids, default=team_ids,
    format_func=lambda x: f"{x} â€” {team_names.get(x, x)}"
)
selected_sprints = st.sidebar.multiselect(
    "Sprint", sprint_order, default=sprint_order,
    format_func=lambda x: f"{x} â€” {sprint_names.get(x, x)}"
)
df = tasks[tasks["team_id"].isin(selected_teams) & tasks["sprint_id"].isin(selected_sprints)].copy()
if df.empty:
    st.warning("No tasks match the selected filters.")
    st.stop()

def metrics(g):
    done = g[g.status == "Done"]
    non_cancel = g[g.status != "Cancelled"]
    valid_cycle = done.loc[done.cycle_time_days.notna() & (done.cycle_time_days >= 0), "cycle_time_days"]
    return pd.Series({
        "Tasks": len(g),
        "Done": len(done),
        "Cancelled": int((g.status == "Cancelled").sum()),
        "Velocity points": done.story_points.fillna(0).sum(),
        "Completion rate (%)": (
            rate(len(done), len(non_cancel))
            if len(g) >= MIN_GROUP else float("nan")
        ),
        "On-time rate (%)": (
            rate(int((done.completed_on_time == "Y").sum()), len(done))
            if len(g) >= MIN_GROUP else float("nan")
        ),
        "Average valid cycle time (days)": valid_cycle.mean(),
        "Valid cycle-time n": len(valid_cycle),
        "Negative Done cycle times": int((done.cycle_time_days < 0).sum()),
        "Blocked tasks": int((g.status == "Blocked").sum()),
        "Overdue-flagged tasks": int((g.is_overdue_at_cutoff == "Y").sum()),
        "Tasks reopened": int((g.reopened_count.fillna(0) > 0).sum()),
        "Reopen events": int(g.reopened_count.fillna(0).clip(lower=0).sum()),
    })

velocity = done.story_points.fillna(0).sum()
blocked = int((df.status == "Blocked").sum())
overdue = int((df.is_overdue_at_cutoff == "Y").sum())
reopened = int((df.reopened_count.fillna(0) > 0).sum())

st.subheader("Productivity overview")
a,b,c,d = st.columns(4)
a.metric("Tasks in selection", f"{len(df):,}")
b.metric("Task completion rate", f"{completion:.1f}%" if pd.notna(completion) else "N/A")
c.metric("On-time delivery rate", f"{ontime:.1f}%" if pd.notna(ontime) else "N/A")
d.metric("Average cycle time", f"{valid_cycles.mean():.2f} days" if len(valid_cycles) else "N/A")
e,f,g,h = st.columns(4)
e.metric("Completed story points", f"{velocity:,.0f}")
f.metric("Blocked tasks", f"{blocked:,}")
g.metric("Overdue-flagged tasks", f"{overdue:,}")
h.metric("Tasks reopened at least once", f"{reopened:,}")
st.caption("Completion = Done / non-cancelled. On-time = completed_on_time=Y / Done. Average cycle time excludes negative and missing values.")

group_rows = []
for (tid, sid), g in df.groupby(["team_id", "sprint_id"]):
    m = metrics(g).to_dict()
    m.update({"team_id":tid, "Team":team_names.get(tid,tid), "sprint_id":sid, "Sprint":sprint_names.get(sid,sid)})
    group_rows.append(m)
grouped = pd.DataFrame(group_rows)
grouped["sprint_order"] = grouped.sprint_id.map({s:i for i,s in enumerate(sprint_order)})
grouped = grouped.sort_values(["sprint_order","Team"])

st.subheader("Sprint velocity trend")
velocity_team_options = selected_teams if selected_teams else team_ids
velocity_team = st.selectbox("Choose one team (do not compare velocity across teams)", velocity_team_options,
                             format_func=lambda x: f"{x} â€” {team_names.get(x,x)}")
v = grouped[grouped.team_id == velocity_team].sort_values("sprint_order")
if not v.empty:
    fig = px.bar(v, x="Sprint", y="Velocity points", hover_data=["Done","Completion rate (%)"])
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, width="stretch")

st.subheader("Team comparison")
team_rows = []
for tid, g in df.groupby("team_id"):
    gd = g[g.status == "Done"]
    gn = g[g.status != "Cancelled"]
    team_rows.append({
        "Team ID":tid, "Team":team_names.get(tid,tid), "Tasks":len(g),
        "Completion rate (%)":rate(len(gd),len(gn)),
        "On-time rate (%)":rate(int((gd.completed_on_time == "Y").sum()),len(gd)),
        "Blocked tasks":int((g.status == "Blocked").sum()),
        "Tasks reopened":int((g.reopened_count.fillna(0)>0).sum()),
    })
team_summary = pd.DataFrame(team_rows)
if not team_summary.empty:
    chart = team_summary.melt(id_vars=["Team ID","Team","Tasks"],
        value_vars=["Completion rate (%)","On-time rate (%)"], var_name="Metric", value_name="Rate (%)")
    fig = px.bar(chart, x="Team", y="Rate (%)", color="Metric", barmode="group", hover_data=["Tasks"])
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, width="stretch")
    work = team_summary.melt(id_vars=["Team ID","Team"], value_vars=["Blocked tasks","Tasks reopened"],
                             var_name="Indicator", value_name="Task count")
    fig = px.bar(work, x="Team", y="Task count", color="Indicator", barmode="group")
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, width="stretch")

st.subheader("Team Ã— sprint detail")
detail_cols = ["Team","team_id","Sprint","sprint_id","Tasks","Done","Cancelled","Velocity points",
               "Completion rate (%)","On-time rate (%)","Average valid cycle time (days)",
               "Valid cycle-time n","Negative Done cycle times","Blocked tasks","Overdue-flagged tasks",
               "Tasks reopened","Reopen events"]
detail = grouped[detail_cols].round(2).rename(columns={"team_id":"Team ID","sprint_id":"Sprint ID"})
st.dataframe(detail, width="stretch", hide_index=True)
st.download_button("Download filtered team-sprint metrics (CSV)", detail.to_csv(index=False).encode("utf-8"),
                   file_name="PQ08_team_sprint_metrics.csv", mime="text/csv")

st.subheader("Hand-check two teams")
st.caption("Audit the raw task counts for two teams in a selected sprint. Groups below five tasks have rates suppressed.")
available_sprints = [s for s in sprint_order if s in selected_sprints] or sprint_order
audit_sprint = st.selectbox("Sprint for hand-check", available_sprints,
                            format_func=lambda x: f"{x} â€” {sprint_names.get(x,x)}")
audit_team_ids = teams.sort_values("team_name")["team_id"].head(2).tolist()
audit_rows = []
for tid in audit_team_ids:
    g = df[(df.team_id == tid) & (df.sprint_id == audit_sprint)]
    gd = g[g.status == "Done"]
    gn = g[g.status != "Cancelled"]
    valid = gd.loc[gd.cycle_time_days.notna() & (gd.cycle_time_days >= 0), "cycle_time_days"]
    suppress = len(g) < MIN_GROUP
    audit_rows.append({
        "Team":team_names.get(tid,tid), "Tasks":len(g), "Done":len(gd), "Non-cancelled":len(gn),
        "Velocity points":gd.story_points.fillna(0).sum(),
        "Completion rate (%)":None if suppress else rate(len(gd),len(gn)),
        "On-time rate (%)":None if suppress else rate(int((gd.completed_on_time=="Y").sum()),len(gd)),
        "Valid cycle-time n":len(valid),
        "Note":"Rates suppressed (<5 tasks)" if suppress else "Rates available",
    })
st.dataframe(pd.DataFrame(audit_rows).round(2), width="stretch", hide_index=True)

with st.expander("Data quality, official definitions, and limitations"):
    st.markdown(f"""
    - Source rows: {len(tasks):,}; unique task IDs: {tasks.task_id.nunique():,}; duplicate task IDs: {duplicate_ids}.
    - Team coverage: {tasks.team_id.nunique()} teams / {len(teams)} dimension rows; unknown team references: {unknown_teams}.
    - Sprint coverage: {tasks.sprint_id.nunique()} sprints / {len(sprints)} dimension rows; unknown sprint references: {unknown_sprints}.
    - Negative cycle-time values: {negative_cycle}; among Done tasks: {negative_done_cycle}. Done tasks with missing cycle time: {missing_done_cycle}.
    - Negative and missing cycle times are excluded from averages; source records are not changed.
    - M22 completion rate: Done / non-cancelled tasks; minimum group size 5.
    - M23 on-time delivery: completed_on_time=Y / Done tasks; minimum group size 5.
    - M24 velocity: sum story_points for Done tasks; do not compare across teams.
    - M25 average cycle time: average cycle_time_days for Done tasks; negative values are data errors.
    - Blocked tasks use status=Blocked; overdue uses the source is_overdue_at_cutoff flag.
    - Tasks reopened counts records with reopened_count > 0; reopen events sum the reopened_count field.
    - Caveat: metric_dictionary.csv describes this as a sample feed until the live board is ready.
    """)

st.divider()
st.caption("PulseIQ Analytics Â· Phase 2 Â· PQ-08 Team Productivity")
