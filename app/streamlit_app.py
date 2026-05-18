from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from costops.data.sample_loader import load_sample_data
from costops.rules.rule_catalog import RULE_CATALOG
from costops.services.metrics import money, projected_monthly_warehouse_spend, recommendation_summary




st.set_page_config(
    page_title="Cost Optimization POC",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def load_data():
    return load_sample_data()


data = load_data()
recommendations = data["recommendations"]
warehouses = data["warehouses"]
workloads = data["workloads"]
storage = data["storage"]
tasks = data["tasks"]

severity_order = ["Critical", "High", "Medium", "Low"]
status_options = ["All"] + sorted(recommendations["status"].unique().tolist())
category_options = ["All"] + sorted(recommendations["category"].unique().tolist())

with st.sidebar:
    st.title("Cost Optimization")
    page = st.radio(
        "Navigation",
        [
            "Overview",
            "Recommendations",
            "Warehouses",
            "Workloads",
            "Storage",
            "Tasks",
            "Savings Tracker",
            "Settings",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    status_filter = st.selectbox("Status", status_options)
    category_filter = st.selectbox("Category", category_options)
    min_confidence = st.slider("Minimum confidence", 0.0, 1.0, 0.65, 0.05)
    st.divider()
    st.caption("POC data mode")
    st.status("Sample data loaded", state="complete", expanded=False)


filtered_recs = recommendations.copy()
if status_filter != "All":
    filtered_recs = filtered_recs[filtered_recs["status"] == status_filter]
if category_filter != "All":
    filtered_recs = filtered_recs[filtered_recs["category"] == category_filter]
filtered_recs = filtered_recs[filtered_recs["confidence"] >= min_confidence]


def render_kpis():
    total_spend = projected_monthly_warehouse_spend(warehouses)
    summary = recommendation_summary(recommendations)

    cols = st.columns(4)
    cols[0].metric("Estimated Monthly Spend", money(total_spend), "sample-data projection")
    cols[1].metric("Monthly Savings Opportunity", money(summary["monthly_savings"]), "open recommendations")
    cols[2].metric("Annualized Opportunity", money(summary["annual_savings"]), "projected")
    cols[3].metric("Critical Findings", f"{summary['critical_count']}", "highest priority")


def recommendation_table(df):
    display = df[
        [
            "recommendation_id",
            "severity",
            "category",
            "title",
            "object_name",
            "confidence",
            "projected_monthly_savings",
            "risk",
            "effort",
            "status",
        ]
    ].sort_values(["projected_monthly_savings", "confidence"], ascending=[False, False])
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "recommendation_id": "ID",
            "projected_monthly_savings": st.column_config.NumberColumn("Monthly Savings", format="$%d"),
            "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1),
        },
    )


def render_filter_chips(df):
    chips = st.columns(5)
    chips[0].metric("Visible Findings", f"{len(df):,.0f}")
    chips[1].metric("Savings In View", money(df["projected_monthly_savings"].sum()))
    chips[2].metric("Avg Confidence", f"{df['confidence'].mean():.0%}" if not df.empty else "0%")
    chips[3].metric("Low Risk", f"{(df['risk'] == 'Low').sum():,.0f}")
    chips[4].metric("Accepted", f"{(df['status'] == 'Accepted').sum():,.0f}")


def render_recommendation_detail(df):
    if df.empty:
        st.info("No recommendations match the current filters.")
        return
    options = df["recommendation_id"] + " - " + df["title"]
    selected = st.selectbox("Recommendation detail", options)
    rec = df.loc[options == selected].iloc[0]

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader(rec["title"])
        detail_cols = st.columns(4)
        detail_cols[0].metric("Severity", rec["severity"])
        detail_cols[1].metric("Monthly Savings", money(rec["projected_monthly_savings"]))
        detail_cols[2].metric("Risk", rec["risk"])
        detail_cols[3].metric("Effort", rec["effort"])
        st.caption(f"Object: {rec['object_name']} | Category: {rec['category']} | Status: {rec['status']}")
        st.write(rec["evidence"])
        st.text_area("Implementation notes", value="", placeholder="Add validation notes, owner, or implementation decision.", height=90)
    with right:
        st.caption("Generated SQL or implementation guidance")
        st.code(rec["generated_sql"], language="sql")


def overview():
    st.title("Snowflake Cost Optimization POC")
    render_kpis()

    st.subheader("Savings Opportunity")
    left, center, right = st.columns([1.2, 1, 1])

    with left:
        by_category = recommendations.groupby("category", as_index=False)["projected_monthly_savings"].sum()
        fig = px.bar(
            by_category,
            x="projected_monthly_savings",
            y="category",
            orientation="h",
            text="projected_monthly_savings",
            labels={"projected_monthly_savings": "Monthly Savings", "category": ""},
        )
        fig.update_traces(texttemplate="$%{text:,.0f}", marker_color="#2E74B5")
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with center:
        severity = recommendations.groupby("severity", as_index=False).size()
        severity["severity"] = pd.Categorical(severity["severity"], severity_order, ordered=True)
        severity = severity.sort_values("severity")
        fig = px.pie(severity, values="size", names="severity", hole=0.55)
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        status = recommendations.groupby("status", as_index=False)["projected_monthly_savings"].sum()
        fig = px.bar(status, x="status", y="projected_monthly_savings", text="projected_monthly_savings")
        fig.update_traces(texttemplate="$%{text:,.0f}", marker_color="#4C78A8")
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Highest Value Recommendations")
    recommendation_table(filtered_recs.head(8))


def recommendations_page():
    st.title("Recommendations")
    render_kpis()
    render_filter_chips(filtered_recs)
    st.subheader("Prioritized Backlog")
    recommendation_table(filtered_recs)
    render_recommendation_detail(filtered_recs)


def warehouses_page():
    st.title("Warehouse Intelligence")
    render_kpis()

    daily = warehouses.groupby(["date", "warehouse"], as_index=False)["cost_usd"].sum()
    fig = px.area(daily, x="date", y="cost_usd", color="warehouse", labels={"cost_usd": "Cost USD", "date": ""})
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)
    with left:
        summary = warehouses.groupby("warehouse", as_index=False).agg(
            cost_usd=("cost_usd", "sum"),
            utilization_pct=("utilization_pct", "mean"),
            queued_seconds=("queued_seconds", "sum"),
            resumes=("resumes", "sum"),
        )
        fig = px.scatter(
            summary,
            x="utilization_pct",
            y="cost_usd",
            size="resumes",
            color="warehouse",
            hover_data=["queued_seconds"],
            labels={"utilization_pct": "Avg Utilization %", "cost_usd": "Weekly Cost"},
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.dataframe(summary.sort_values("cost_usd", ascending=False), use_container_width=True, hide_index=True)


def workloads_page():
    st.title("Workload Intelligence")
    left, right = st.columns([1.1, 1])
    with left:
        fig = px.bar(
            workloads.sort_values("cost_usd"),
            x="cost_usd",
            y="workload",
            color="category",
            orientation="h",
            labels={"cost_usd": "Cost USD", "workload": ""},
        )
        fig.update_layout(height=440, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = px.scatter(
            workloads,
            x="gb_scanned",
            y="avg_runtime_seconds",
            size="cost_usd",
            color="category",
            hover_name="workload",
            labels={"gb_scanned": "GB Scanned", "avg_runtime_seconds": "Avg Runtime Seconds"},
        )
        fig.update_layout(height=440, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Workload Drilldown")
    st.dataframe(workloads.sort_values("cost_usd", ascending=False), use_container_width=True, hide_index=True)


def storage_page():
    st.title("Storage Intelligence")
    storage_cost = storage["monthly_storage_cost"].sum()
    stale_objects = (storage["last_queried_days"] >= 90).sum()
    high_retention = (storage["retention_days"] > 7).sum()
    clone_candidates = storage["classification"].str.contains("Clone|candidate", case=False, na=False).sum()

    cols = st.columns(4)
    cols[0].metric("Monthly Storage Cost", money(storage_cost), "sample-data estimate")
    cols[1].metric("Stale Objects", f"{stale_objects}", "90+ days without query")
    cols[2].metric("High Retention Objects", f"{high_retention}", "above target threshold")
    cols[3].metric("Clone / Drop Candidates", f"{clone_candidates}", "review required")

    left, right = st.columns([1.1, 1])
    with left:
        fig = px.treemap(
            storage,
            path=["database_name", "schema_name", "object_name"],
            values="monthly_storage_cost",
            color="classification",
            hover_data=["size_gb", "last_queried_days", "retention_days"],
        )
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        ranked = storage.sort_values("monthly_storage_cost", ascending=True)
        fig = px.bar(
            ranked,
            x="monthly_storage_cost",
            y="object_name",
            color="classification",
            orientation="h",
            labels={"monthly_storage_cost": "Monthly Storage Cost", "object_name": ""},
        )
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Storage Object Review")
    st.dataframe(
        storage.sort_values(["monthly_storage_cost", "last_queried_days"], ascending=[False, False]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "monthly_storage_cost": st.column_config.NumberColumn("Monthly Cost", format="$%d"),
            "size_gb": st.column_config.NumberColumn("Size GB", format="%d"),
        },
    )


def tasks_page():
    st.title("Task Intelligence")
    task_cost = tasks["estimated_compute_cost"].sum()
    failures = tasks["failures_7d"].sum()
    executions = tasks["executions_7d"].sum()
    noisy_tasks = (tasks["executions_7d"] >= 168).sum()

    cols = st.columns(4)
    cols[0].metric("7-Day Task Executions", f"{executions:,.0f}")
    cols[1].metric("7-Day Failures", f"{failures:,.0f}")
    cols[2].metric("Estimated Compute Cost", money(task_cost))
    cols[3].metric("High-Frequency Tasks", f"{noisy_tasks}", "hourly or more")

    left, right = st.columns([1.1, 1])
    with left:
        fig = px.bar(
            tasks.sort_values("estimated_compute_cost"),
            x="estimated_compute_cost",
            y="task_name",
            color="warehouse",
            orientation="h",
            labels={"estimated_compute_cost": "Estimated Compute Cost", "task_name": ""},
        )
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = px.scatter(
            tasks,
            x="executions_7d",
            y="avg_runtime_seconds",
            size="estimated_compute_cost",
            color="last_state",
            hover_name="task_name",
            labels={"executions_7d": "Executions 7D", "avg_runtime_seconds": "Avg Runtime Seconds"},
        )
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Task Review Queue")
    st.dataframe(
        tasks.sort_values(["estimated_compute_cost", "failures_7d"], ascending=[False, False]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "cloud_services_credits": st.column_config.NumberColumn("Cloud Credits", format="%.1f"),
            "estimated_compute_cost": st.column_config.NumberColumn("Compute Cost", format="$%d"),
        },
    )


def savings_tracker_page():
    st.title("Savings Tracker")
    tracker = recommendations.groupby("status", as_index=False).agg(
        monthly_savings=("projected_monthly_savings", "sum"),
        annual_savings=("projected_annual_savings", "sum"),
        recommendations=("recommendation_id", "count"),
    )
    fig = go.Figure(
        go.Waterfall(
            name="Savings",
            orientation="v",
            measure=["relative"] * len(tracker),
            x=tracker["status"],
            text=[money(v) for v in tracker["monthly_savings"]],
            y=tracker["monthly_savings"],
        )
    )
    fig.update_layout(height=380, yaxis_title="Projected Monthly Savings", margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(tracker, use_container_width=True, hide_index=True)


def settings_page():
    st.title("Settings")
    st.caption("POC controls for scan configuration, thresholds, and Snowflake Marketplace packaging assumptions.")

    left, center, right = st.columns(3)
    with left:
        st.subheader("Cost Model")
        credit_price = st.number_input("Credit price USD", min_value=0.0, value=3.0, step=0.25)
        lookback_days = st.slider("Default lookback days", 7, 90, 30, 1)
        annualization_months = st.slider("Annualization months", 1, 12, 12, 1)
    with center:
        st.subheader("Rule Thresholds")
        auto_suspend_target = st.number_input("Auto-suspend target seconds", min_value=30, value=60, step=30)
        stale_days = st.number_input("Stale object threshold days", min_value=30, value=90, step=15)
        min_confidence_setting = st.slider("Default recommendation confidence", 0.0, 1.0, 0.70, 0.05)
    with right:
        st.subheader("Execution Mode")
        st.toggle("Read-only recommendations", value=True)
        st.toggle("Generate implementation SQL", value=True)
        st.toggle("Allow approved SQL execution", value=False)

    st.subheader("Native App Readiness Checklist")
    readiness = pd.DataFrame(
        [
            ("Application package", "Not started", "manifest.yml and setup_script.sql"),
            ("Privilege model", "Not started", "Document access to account usage metadata"),
            ("Scan procedure", "POC only", "Replace sample data with SQL-backed scan"),
            ("Scheduled task", "Not started", "Nightly scan option"),
            ("Marketplace listing", "Not started", "Screenshots, support, security notes"),
            ("Customer install test", "Not started", "Private listing or controlled account"),
        ],
        columns=["Area", "Status", "Next Step"],
    )
    st.dataframe(readiness, use_container_width=True, hide_index=True)

    st.subheader("Rule Catalog")
    rules = pd.DataFrame(RULE_CATALOG)
    st.dataframe(
        rules,
        use_container_width=True,
        hide_index=True,
        column_config={
            "mvp": st.column_config.CheckboxColumn("MVP"),
            "rule_id": "Rule ID",
            "data_sources": "Data Sources",
        },
    )

    st.subheader("Current POC Assumptions")
    assumptions = {
        "Credit price": money(credit_price),
        "Lookback window": f"{lookback_days} days",
        "Annualization period": f"{annualization_months} months",
        "Auto-suspend target": f"{auto_suspend_target} seconds",
        "Stale object threshold": f"{stale_days} days",
        "Default confidence": f"{min_confidence_setting:.0%}",
    }
    st.json(assumptions)


if page == "Overview":
    overview()
elif page == "Recommendations":
    recommendations_page()
elif page == "Warehouses":
    warehouses_page()
elif page == "Workloads":
    workloads_page()
elif page == "Storage":
    storage_page()
elif page == "Tasks":
    tasks_page()
elif page == "Savings Tracker":
    savings_tracker_page()
else:
    settings_page()
