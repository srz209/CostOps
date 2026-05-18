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
from costops.data.snowflake_loader import load_warehouse_metering_history, test_connection
from costops.rules.rule_catalog import RULE_CATALOG
from costops.services.metrics import (
    enrich_recommendation_lifecycle,
    latest_successful_scan,
    money,
    projected_monthly_warehouse_spend,
    recommendation_summary,
    savings_by_period,
    scan_freshness,
)




st.set_page_config(
    page_title="Cost Optimization POC",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        padding: 0.15rem 0;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.05rem;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.74rem;
    }
    .compact-chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin: 0.25rem 0 0.45rem 0;
    }
    .compact-chip {
        border: 1px solid #d8dee9;
        border-radius: 6px;
        padding: 0.18rem 0.45rem;
        font-size: 0.78rem;
        line-height: 1.15rem;
        background: #f8fafc;
    }
    .compact-chip strong {
        font-size: 0.86rem;
    }
    .compact-title {
        font-size: 1rem;
        font-weight: 600;
        margin: 0.25rem 0 0.15rem 0;
    }
    .compact-meta {
        font-size: 0.78rem;
        color: #4b5563;
        margin-bottom: 0.3rem;
    }
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.65rem;
        margin: 0.35rem 0 0.8rem 0;
    }
    .kpi-card {
        border: 1px solid #d7e3f4;
        border-left: 5px solid #2e74b5;
        border-radius: 8px;
        padding: 0.55rem 0.7rem;
        background: #f7fbff;
        min-height: 4.2rem;
    }
    .kpi-card.savings {
        border-left-color: #1f8a5b;
        background: #f3fbf7;
    }
    .kpi-card.realized {
        border-left-color: #7a5af8;
        background: #f8f6ff;
    }
    .kpi-card.critical {
        border-left-color: #c2410c;
        background: #fff7ed;
    }
    .kpi-label {
        font-size: 0.72rem;
        color: #475569;
        line-height: 1rem;
    }
    .kpi-value {
        font-size: 1.35rem;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.7rem;
    }
    .kpi-note {
        font-size: 0.72rem;
        color: #64748b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DEFAULT_CREDIT_PRICE = 3.0
ACTIONABLE_STATUSES = {
    "Selected": ("SELECTED", "Selected for active review."),
    "Accepted": ("ACCEPTED", "Accepted for implementation planning."),
    "Deferred": ("DEFERRED", "Deferred for a future optimization cycle."),
    "Rejected": ("REJECTED", "Rejected after review."),
    "Implemented": ("IMPLEMENTED", "Marked as implemented by the owner."),
    "Realized": ("SAVINGS_REALIZED", "Validated as realized savings."),
}


@st.cache_data
def load_data():
    return load_sample_data()


@st.cache_data(ttl=900)
def load_live_warehouse_metering(config, lookback_days, credit_price):
    return load_warehouse_metering_history(config, lookback_days=lookback_days, credit_price=credit_price)


def get_snowflake_config():
    try:
        return dict(st.secrets.get("snowflake", {}))
    except Exception:
        return {}


def log_recommendation_event(recommendation_id, event_type, actor, details):
    events = st.session_state["recommendation_events_workflow"].copy()
    next_id = f"EVT-DEMO-{len(events) + 1:03d}"
    new_event = pd.DataFrame(
        [
            {
                "event_id": next_id,
                "recommendation_id": recommendation_id,
                "event_ts": AS_OF_DATE + pd.Timedelta(hours=12, minutes=len(events) % 60),
                "event_type": event_type,
                "actor": actor,
                "details": details,
            }
        ]
    )
    st.session_state["recommendation_events_workflow"] = pd.concat([events, new_event], ignore_index=True)


def update_recommendation_status(recommendation_id, new_status, actor, notes):
    workflow = st.session_state["recommendations_workflow"].copy()
    mask = workflow["recommendation_id"] == recommendation_id
    if not mask.any():
        return

    now = AS_OF_DATE + pd.Timedelta(hours=12)
    event_type, default_detail = ACTIONABLE_STATUSES[new_status]
    workflow.loc[mask, "status"] = new_status
    workflow.loc[mask, "last_seen_at"] = AS_OF_DATE

    if new_status in {"Accepted", "Implemented", "Realized"} and workflow.loc[mask, "accepted_at"].isna().any():
        workflow.loc[mask, "accepted_at"] = now
    if new_status in {"Implemented", "Realized"}:
        workflow.loc[mask, "implemented_at"] = now
    if new_status == "Realized":
        unrealized = workflow.loc[mask, "realized_monthly_savings"].fillna(0) == 0
        if unrealized.any():
            workflow.loc[mask, "realized_monthly_savings"] = (
                workflow.loc[mask, "projected_monthly_savings"] * 0.85
            ).round(0).astype(int)

    st.session_state["recommendations_workflow"] = workflow
    details = notes.strip() if notes and notes.strip() else default_detail
    log_recommendation_event(recommendation_id, event_type, actor, details)


data = load_data()
AS_OF_DATE = pd.Timestamp("2026-05-18")
if "recommendations_workflow" not in st.session_state:
    st.session_state["recommendations_workflow"] = data["recommendations"].copy()
if "recommendation_events_workflow" not in st.session_state:
    st.session_state["recommendation_events_workflow"] = data["recommendation_events"].copy()

recommendations = enrich_recommendation_lifecycle(st.session_state["recommendations_workflow"], AS_OF_DATE)
recommendation_events = st.session_state["recommendation_events_workflow"]
scan_runs = data["scan_runs"]
warehouses = data["warehouses"]
data_source_status = "Sample data loaded"
data_source_mode = "Sample data"
snowflake_config = get_snowflake_config()
workloads = data["workloads"]
storage = data["storage"]
tasks = data["tasks"]

severity_order = ["Critical", "High", "Medium", "Low"]
status_options = ["All"] + sorted(recommendations["status"].unique().tolist())
category_options = ["All"] + sorted(recommendations["category"].unique().tolist())
owner_options = ["All"] + sorted(recommendations["owner"].unique().tolist())
team_options = ["All"] + sorted(recommendations["team"].unique().tolist())

with st.sidebar:
    st.title("Cost Optimization")
    data_source_mode = st.selectbox("Data source", ["Sample data", "Snowflake"], index=0)
    if data_source_mode == "Snowflake":
        if snowflake_config:
            try:
                warehouses = load_live_warehouse_metering(snowflake_config, lookback_days=30, credit_price=DEFAULT_CREDIT_PRICE)
                data_source_status = "Snowflake warehouse metering loaded"
            except Exception as exc:
                data_source_status = f"Snowflake load failed; using sample data. {exc}"
                warehouses = data["warehouses"]
        else:
            data_source_status = "Snowflake secrets missing; using sample data"
            warehouses = data["warehouses"]

    page = st.radio(
        "Navigation",
        [
            "Overview",
            "Recommendations",
            "Warehouses",
            "Workloads",
            "Storage",
            "Tasks",
            "Scan & Schedule",
            "Savings Realization",
            "Settings",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Data source status")
    state = "complete" if data_source_status in {"Sample data loaded", "Snowflake warehouse metering loaded"} else "error"
    st.status(data_source_status, state=state, expanded=False)


def apply_recommendation_filters(df, status="All", category="All", owner="All", team="All", min_confidence=0.65):
    filtered = df.copy()
    if status != "All":
        filtered = filtered[filtered["status"] == status]
    if category != "All":
        filtered = filtered[filtered["category"] == category]
    if owner != "All":
        filtered = filtered[filtered["owner"] == owner]
    if team != "All":
        filtered = filtered[filtered["team"] == team]
    return filtered[filtered["confidence"] >= min_confidence]


def render_recommendation_filter_bar(key_prefix="global", include_severity=False, include_daily_sort=False):
    filters = {}
    columns = [1, 1, 1.1, 1.1, 1]
    if include_severity:
        columns = [0.95] + columns
    if include_daily_sort:
        columns = columns + [1]

    filter_cols = st.columns(columns)
    idx = 0
    if include_severity:
        with filter_cols[idx]:
            filters["severity"] = st.selectbox("Severity", ["All"] + severity_order, key=f"{key_prefix}_severity")
        idx += 1
    with filter_cols[idx]:
        filters["status"] = st.selectbox("Status", status_options, key=f"{key_prefix}_status")
    idx += 1
    with filter_cols[idx]:
        filters["category"] = st.selectbox("Category", category_options, key=f"{key_prefix}_category")
    idx += 1
    with filter_cols[idx]:
        filters["team"] = st.selectbox("Team", team_options, key=f"{key_prefix}_team")
    idx += 1
    with filter_cols[idx]:
        filters["owner"] = st.selectbox("Owner", owner_options, key=f"{key_prefix}_owner")
    idx += 1
    with filter_cols[idx]:
        filters["min_confidence"] = st.slider(
            "Min confidence", 0.0, 1.0, 0.65, 0.05, key=f"{key_prefix}_min_confidence"
        )
    if include_daily_sort:
        idx += 1
        with filter_cols[idx]:
            filters["daily_savings_sort"] = st.selectbox(
                "Daily savings", ["High to low", "Low to high"], key=f"{key_prefix}_daily_savings"
            )
    return filters


def render_kpis(recs=None):
    recs = recommendations if recs is None else recs
    total_spend = projected_monthly_warehouse_spend(warehouses)
    summary = recommendation_summary(recs)
    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">Estimated Monthly Spend</div>
                <div class="kpi-value">{money(total_spend)}</div>
                <div class="kpi-note">current projection</div>
            </div>
            <div class="kpi-card savings">
                <div class="kpi-label">Monthly Savings Opportunity</div>
                <div class="kpi-value">{money(summary["monthly_savings"])}</div>
                <div class="kpi-note">open recommendations</div>
            </div>
            <div class="kpi-card realized">
                <div class="kpi-label">Realized Monthly Savings</div>
                <div class="kpi-value">{money(summary["realized_monthly_savings"])}</div>
                <div class="kpi-note">validated savings</div>
            </div>
            <div class="kpi-card critical">
                <div class="kpi-label">Critical Findings</div>
                <div class="kpi-value">{summary["critical_count"]}</div>
                <div class="kpi-note">highest priority</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def recommendation_table(df, key="recommendation_table", selectable=False, height=None, sort_by=None, ascending=False):
    display = df[
        [
            "recommendation_id",
            "severity",
            "category",
            "title",
            "object_name",
            "owner",
            "team",
            "confidence",
            "projected_daily_savings",
            "projected_monthly_savings",
            "missed_savings_to_date",
            "days_lingering",
            "risk",
            "effort",
            "status",
        ]
    ]
    if sort_by:
        display = display.sort_values([sort_by, "confidence"], ascending=[ascending, False])
    else:
        display = display.sort_values(["projected_monthly_savings", "confidence"], ascending=[False, False])
    table_kwargs = {
        "use_container_width": True,
        "hide_index": True,
        "key": key,
        "on_select": "rerun" if selectable else "ignore",
        "selection_mode": "single-row" if selectable else "multi-row",
        "column_config": {
            "recommendation_id": "ID",
            "projected_daily_savings": st.column_config.NumberColumn("Daily Savings", format="$%d"),
            "projected_monthly_savings": st.column_config.NumberColumn("Monthly Savings", format="$%d"),
            "missed_savings_to_date": st.column_config.NumberColumn("Missed Savings", format="$%d"),
            "days_lingering": st.column_config.NumberColumn("Days Since First Seen", format="%d"),
            "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1),
        },
    }
    if height is not None:
        table_kwargs["height"] = height
    event = st.dataframe(display, **table_kwargs)
    if not selectable or not event.selection.rows:
        return None
    selected_position = event.selection.rows[0]
    return display.iloc[selected_position]["recommendation_id"]


def scrolling_recommendation_table(df, page_size=20, sort_by="projected_daily_savings", ascending=False):
    sorted_df = df.sort_values([sort_by, "confidence"], ascending=[ascending, False]).reset_index(drop=True)
    total_rows = len(sorted_df)
    if total_rows == 0:
        st.info("No recommendations match the current filters.")
        return None

    visible_rows = min(total_rows, 25)
    table_height = 38 * (visible_rows + 1)
    st.caption(f"{total_rows:,.0f} recommendations. Scroll the table to review more; select one row to open the detail below.")
    selected_id = recommendation_table(
        sorted_df,
        key="recommendation_backlog_scroll",
        selectable=True,
        height=table_height,
        sort_by=sort_by,
        ascending=ascending,
    )
    return selected_id or sorted_df.iloc[0]["recommendation_id"]


def render_filter_chips(df):
    avg_age = f"{df['days_lingering'].mean():.0f} days" if not df.empty else "0 days"
    st.markdown(
        f"""
        <div class="compact-chip-row">
            <div class="compact-chip">Findings <strong>{len(df):,.0f}</strong></div>
            <div class="compact-chip">Savings <strong>{money(df["projected_monthly_savings"].sum())}</strong></div>
            <div class="compact-chip">Missed <strong>{money(df["missed_savings_to_date"].sum())}</strong></div>
            <div class="compact-chip">Avg age <strong>{avg_age}</strong></div>
            <div class="compact-chip">Realized <strong>{money(df["realized_monthly_savings"].sum())}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recommendation_detail(df, selected_recommendation_id=None):
    if df.empty or selected_recommendation_id is None:
        st.info("No recommendations match the current filters.")
        return
    rec = df.loc[df["recommendation_id"] == selected_recommendation_id].iloc[0]

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown(f'<div class="compact-title">{rec["title"]}</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="compact-chip-row">
                <div class="compact-chip">Severity <strong>{rec["severity"]}</strong></div>
                <div class="compact-chip">Monthly <strong>{money(rec["projected_monthly_savings"])}</strong></div>
                <div class="compact-chip">Missed <strong>{money(rec["missed_savings_to_date"])}</strong></div>
                <div class="compact-chip">Age <strong>{rec["days_lingering"]} days</strong></div>
            </div>
            <div class="compact-meta">
                {rec["object_name"]} | {rec["category"]} / {rec["subcategory"]} | {rec["owner"]} | {rec["team"]} | {rec["status"]}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write(rec["evidence"])
        actor = st.selectbox(
            "Action owner",
            sorted(recommendations["owner"].dropna().unique().tolist()),
            index=sorted(recommendations["owner"].dropna().unique().tolist()).index(rec["owner"]),
            key=f"{selected_recommendation_id}_actor",
        )
        notes = st.text_area(
            "Workflow notes",
            value="",
            placeholder="Add validation notes, owner handoff, or implementation decision.",
            height=80,
            key=f"{selected_recommendation_id}_notes",
        )
        action_cols = st.columns(6)
        action_labels = [
            ("Select", "Selected"),
            ("Accept", "Accepted"),
            ("Defer", "Deferred"),
            ("Reject", "Rejected"),
            ("Implemented", "Implemented"),
            ("Realized", "Realized"),
        ]
        for col, (label, status) in zip(action_cols, action_labels):
            disabled = rec["status"] == status
            if col.button(label, disabled=disabled, key=f"{selected_recommendation_id}_{status}"):
                update_recommendation_status(selected_recommendation_id, status, actor, notes)
                st.toast(f"{selected_recommendation_id} moved to {status}.")
                st.rerun()
    with right:
        st.caption("Generated SQL or implementation guidance")
        st.code(rec["generated_sql"], language="sql")
        if st.button("Log SQL copied", key=f"{selected_recommendation_id}_copy_sql"):
            log_recommendation_event(
                selected_recommendation_id,
                "SQL_COPIED",
                rec["owner"],
                "Copied generated SQL or implementation guidance from the recommendation detail.",
            )
            st.toast("SQL copy event logged.")
            st.rerun()
        st.caption("Lifecycle")
        lifecycle = pd.DataFrame(
            [
                ("First seen", rec["first_seen_at"].date()),
                ("Accepted", "" if pd.isna(rec["accepted_at"]) else rec["accepted_at"].date()),
                ("Implemented", "" if pd.isna(rec["implemented_at"]) else rec["implemented_at"].date()),
                ("Risk", rec["risk"]),
                ("Effort", rec["effort"]),
            ],
            columns=["Milestone", "Value"],
        )
        st.dataframe(lifecycle, use_container_width=True, hide_index=True)
        st.caption("Recent audit events")
        rec_events = recommendation_events[recommendation_events["recommendation_id"] == selected_recommendation_id]
        if rec_events.empty:
            st.info("No events logged yet.")
        else:
            st.dataframe(
                rec_events.sort_values("event_ts", ascending=False).head(5),
                use_container_width=True,
                hide_index=True,
            )


def overview():
    st.title("Snowflake Cost Optimization POC")
    overview_filters = render_recommendation_filter_bar("overview")
    page_recs = apply_recommendation_filters(
        recommendations,
        status=overview_filters["status"],
        category=overview_filters["category"],
        owner=overview_filters["owner"],
        team=overview_filters["team"],
        min_confidence=overview_filters["min_confidence"],
    )
    render_kpis(page_recs)

    st.subheader("Savings Opportunity")
    left, center, right = st.columns([1.2, 1, 1])

    with left:
        by_category = page_recs.groupby("category", as_index=False)["projected_monthly_savings"].sum()
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
        severity = page_recs.groupby("severity", as_index=False).size()
        severity["severity"] = pd.Categorical(severity["severity"], severity_order, ordered=True)
        severity = severity.sort_values("severity")
        fig = px.pie(severity, values="size", names="severity", hole=0.55)
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        status = page_recs.groupby("status", as_index=False)["projected_monthly_savings"].sum()
        fig = px.bar(status, x="status", y="projected_monthly_savings", text="projected_monthly_savings")
        fig.update_traces(texttemplate="$%{text:,.0f}", marker_color="#4C78A8")
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Highest Value Recommendations")
    recommendation_table(page_recs.head(8))


def recommendations_page():
    st.title("Recommendations")
    rec_filters = render_recommendation_filter_bar(
        "recommendations", include_severity=True, include_daily_sort=True
    )
    page_recs = apply_recommendation_filters(
        recommendations,
        status=rec_filters["status"],
        category=rec_filters["category"],
        owner=rec_filters["owner"],
        team=rec_filters["team"],
        min_confidence=rec_filters["min_confidence"],
    )
    if rec_filters["severity"] != "All":
        page_recs = page_recs[page_recs["severity"] == rec_filters["severity"]]
    sort_ascending = rec_filters["daily_savings_sort"] == "Low to high"
    render_kpis(page_recs)

    render_filter_chips(page_recs)
    selected_recommendation_id = scrolling_recommendation_table(
        page_recs,
        page_size=20,
        sort_by="projected_daily_savings",
        ascending=sort_ascending,
    )
    render_recommendation_detail(page_recs, selected_recommendation_id)


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


def savings_realization_page():
    st.title("Savings Realization")
    savings_filters = render_recommendation_filter_bar("savings")
    page_recs = apply_recommendation_filters(
        recommendations,
        status=savings_filters["status"],
        category=savings_filters["category"],
        owner=savings_filters["owner"],
        team=savings_filters["team"],
        min_confidence=savings_filters["min_confidence"],
    )
    period = st.segmented_control("Period", ["MTD", "QTD", "YTD", "Since inception"], default="YTD")
    realized, projected = savings_by_period(page_recs, period)
    open_missed = page_recs.loc[page_recs["is_open"], "missed_savings_to_date"].sum()

    cols = st.columns(4)
    cols[0].metric("Realized Savings", money(realized), period)
    cols[1].metric("Projected Opportunity", money(projected), period)
    cols[2].metric("Missed Savings", money(open_missed), "open items")
    cols[3].metric("Open Recommendations", f"{page_recs['is_open'].sum():,.0f}", "filtered view")

    tracker = page_recs.groupby("status", as_index=False).agg(
        monthly_savings=("projected_monthly_savings", "sum"),
        realized_monthly_savings=("realized_monthly_savings", "sum"),
        missed_savings=("missed_savings_to_date", "sum"),
        annual_savings=("projected_annual_savings", "sum"),
        recommendations=("recommendation_id", "count"),
    )

    left, right = st.columns([1.1, 1])
    with left:
        by_category = page_recs.groupby("category", as_index=False).agg(
            projected=("projected_monthly_savings", "sum"),
            realized=("realized_monthly_savings", "sum"),
            missed=("missed_savings_to_date", "sum"),
        )
        melted = by_category.melt("category", var_name="metric", value_name="amount")
        fig = px.bar(
            melted,
            x="category",
            y="amount",
            color="metric",
            barmode="group",
            labels={"amount": "USD", "category": ""},
        )
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        by_owner = page_recs.groupby(["owner", "team"], as_index=False).agg(
            projected_monthly_savings=("projected_monthly_savings", "sum"),
            realized_monthly_savings=("realized_monthly_savings", "sum"),
            missed_savings=("missed_savings_to_date", "sum"),
            open_items=("is_open", "sum"),
        )
        fig = px.scatter(
            by_owner,
            x="projected_monthly_savings",
            y="missed_savings",
            size="open_items",
            color="team",
            hover_name="owner",
            labels={"projected_monthly_savings": "Projected Monthly Savings", "missed_savings": "Missed Savings"},
        )
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Savings Lifecycle by Status")
    st.dataframe(
        tracker.sort_values("missed_savings", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={
            "monthly_savings": st.column_config.NumberColumn("Projected Monthly", format="$%d"),
            "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
            "missed_savings": st.column_config.NumberColumn("Missed Savings", format="$%d"),
            "annual_savings": st.column_config.NumberColumn("Projected Annual", format="$%d"),
        },
    )

    st.subheader("Aging and Ownership Queue")
    queue_cols = [
        "recommendation_id",
        "category",
        "subcategory",
        "title",
        "owner",
        "team",
        "status",
        "first_seen_at",
        "days_lingering",
        "projected_daily_savings",
        "missed_savings_to_date",
        "realized_monthly_savings",
    ]
    st.dataframe(
        page_recs[queue_cols].sort_values(["missed_savings_to_date", "days_lingering"], ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={
            "projected_daily_savings": st.column_config.NumberColumn("Daily Savings", format="$%d"),
            "missed_savings_to_date": st.column_config.NumberColumn("Missed Savings", format="$%d"),
            "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
            "days_lingering": st.column_config.NumberColumn("Days Open", format="%d"),
        },
    )

    st.subheader("Audit Log")
    event_view = recommendation_events.merge(
        recommendations[["recommendation_id", "category", "owner", "team", "title"]],
        on="recommendation_id",
        how="left",
    )
    if savings_filters["category"] != "All":
        event_view = event_view[event_view["category"] == savings_filters["category"]]
    if savings_filters["owner"] != "All":
        event_view = event_view[event_view["owner"] == savings_filters["owner"]]
    if savings_filters["team"] != "All":
        event_view = event_view[event_view["team"] == savings_filters["team"]]
    st.dataframe(
        event_view.sort_values("event_ts", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


def scan_control_page_section(credit_price):
    latest_scan = latest_successful_scan(scan_runs)
    freshness = scan_freshness(scan_runs, AS_OF_DATE + pd.Timedelta(hours=12), stale_after_hours=24)

    st.subheader("Scan Control")
    if latest_scan is not None:
        scan_cost = latest_scan["credits_estimated"] * credit_price
        monthly_opportunity = recommendations["projected_monthly_savings"].sum()
        roi = monthly_opportunity / scan_cost if scan_cost else 0
        cols = st.columns([1.25, 0.9, 0.85, 0.9, 1.15, 1])
        cols[0].metric("Last Full Scan", latest_scan["completed_at"].strftime("%b %d, %I:%M %p"))
        cols[1].metric("Freshness", freshness["status"])
        cols[2].metric("Scan Credits", f"{latest_scan['credits_estimated']:.2f}", "credits used")
        cols[3].metric("Scan Cost", money(scan_cost), "estimated")
        cols[4].metric("Identified Monthly Savings", money(monthly_opportunity), "from latest results")
        cols[5].metric("Savings Found per $1 Scan Cost", money(roi), "monthly opportunity")
    else:
        st.warning("No successful scan exists yet.")

    left, center, right = st.columns([1.1, 1.1, 1])
    with left:
        st.selectbox("Schedule", ["Daily", "Weekly", "Monthly", "Off"], index=0)
        st.time_input("Preferred scan time", value=pd.Timestamp("2026-05-18 08:00").time())
    with center:
        st.selectbox("Scan scope", ["Full", "Incremental"], index=0)
        st.selectbox("Lookback window", ["7 days", "30 days", "90 days", "All available"], index=1)
    with right:
        st.selectbox("Next scheduled scan", ["2026-05-19 08:00", "2026-05-20 08:00", "Manual only"], index=0)
        st.button("Run scan now", type="primary")

    st.caption("POC mode: controls are not connected to Snowflake yet. They model the future scheduled/ad hoc scan workflow.")

    st.subheader("Scan Run History")
    st.dataframe(
        scan_runs.sort_values("started_at", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={
            "credits_estimated": st.column_config.NumberColumn("Credits", format="%.2f"),
            "recommendations_found": st.column_config.NumberColumn("Found", format="%d"),
            "recommendations_new": st.column_config.NumberColumn("New", format="%d"),
            "recommendations_updated": st.column_config.NumberColumn("Updated", format="%d"),
        },
    )


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

    st.subheader("Snowflake Connection")
    config_rows = []
    for key in ["account", "user", "role", "warehouse", "database", "schema", "authenticator"]:
        value = snowflake_config.get(key)
        config_rows.append((key, "Configured" if value else "Missing", "" if not value else str(value)))
    st.dataframe(
        pd.DataFrame(config_rows, columns=["Setting", "Status", "Value"]),
        use_container_width=True,
        hide_index=True,
    )
    left_conn, right_conn = st.columns([1, 2])
    with left_conn:
        if st.button("Test Snowflake connection"):
            if not snowflake_config:
                st.error("No Snowflake secrets found. Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml and fill in credentials.")
            else:
                try:
                    result = test_connection(snowflake_config)
                    st.success(f"Connected to {result['account']} in {result['region']} on Snowflake {result['version']}.")
                except Exception as exc:
                    st.error(f"Connection failed: {exc}")
    with right_conn:
        st.caption(
            "Live mode currently pulls warehouse metering history only. Recommendations, scan history, storage, tasks, "
            "and savings realization remain in demo data until the scan engine is implemented."
        )

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
elif page == "Scan & Schedule":
    st.title("Scan & Schedule")
    st.caption("Schedule, run, and review Snowflake environment analysis runs. POC mode uses demo history.")
    scan_control_page_section(DEFAULT_CREDIT_PRICE)
elif page == "Savings Realization":
    savings_realization_page()
else:
    settings_page()
