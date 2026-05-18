from pathlib import Path
from html import escape
from io import BytesIO
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from costops.data.sample_loader import load_sample_data
from costops.data.recommendation_store import (
    initialize_session_store,
    log_sql_copied,
    merge_scan_results,
    recommendation_events_frame,
    recommendations_frame,
    scan_runs_frame,
    update_recommendation_status,
)
from costops.data.snowflake_repository import initialize_app_schema, persist_analysis_result
from costops.data.snowflake_loader import load_account_usage_snapshot, load_warehouse_metering_history, test_connection
from costops.rules.rule_catalog import RULE_CATALOG
from costops.services.analysis_runner import AnalysisConfig, run_environment_analysis
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
    .report-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 0.55rem;
        margin: 0.35rem 0 0.8rem 0;
    }
    .report-card {
        border: 1px solid #d8dee9;
        border-radius: 8px;
        padding: 0.5rem 0.6rem;
        background: #ffffff;
        min-height: 4.1rem;
    }
    .report-card strong {
        display: block;
        font-size: 1.1rem;
        line-height: 1.45rem;
        color: #111827;
    }
    .report-card span {
        display: block;
        font-size: 0.7rem;
        color: #64748b;
        line-height: 0.95rem;
    }
    .control-help {
        color: #64748b;
        font-size: 0.72rem;
        line-height: 1rem;
        margin-top: -0.45rem;
        margin-bottom: 0.25rem;
    }
    .download-spacer {
        height: 1.75rem;
    }
    div[data-testid="stDownloadButton"] button {
        border-radius: 7px;
        font-weight: 700;
        min-height: 2.55rem;
        box-shadow: 0 6px 14px rgba(46, 116, 181, 0.22);
    }
    div[data-testid="stDownloadButton"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 9px 18px rgba(46, 116, 181, 0.28);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DEFAULT_CREDIT_PRICE = 3.0
REPORT_COLORS = ["#1f8a5b", "#2e74b5", "#c2410c", "#7a5af8", "#d19a00", "#486581", "#00838f"]
REPORT_METRIC_COLORS = {
    "projected_monthly_savings": "#2e74b5",
    "realized_monthly_savings": "#1f8a5b",
    "missed_savings": "#c2410c",
}
REPORT_SECTION_OPTIONS = [
    "Savings by category",
    "Savings by team",
    "Unresolved opportunity",
    "Owner accountability",
    "Scan ROI history",
]
REPORT_PRESETS = {
    "Comprehensive finance packet": REPORT_SECTION_OPTIONS,
    "Executive ROI summary": [],
    "Savings by team": ["Savings by team", "Unresolved opportunity"],
    "Savings by category": ["Savings by category", "Unresolved opportunity"],
    "Unresolved opportunity": ["Unresolved opportunity", "Owner accountability"],
    "Owner accountability": ["Owner accountability", "Unresolved opportunity"],
    "Scan ROI history": ["Scan ROI history"],
    "Custom report": ["Savings by category", "Savings by team"],
}
REPORT_DETAIL_LIMITS = {
    "Summary only": {"backlog": 10, "audit": 10, "section": 10},
    "Standard detail": {"backlog": 40, "audit": 40, "section": 25},
    "Full detail": {"backlog": 200, "audit": 200, "section": 100},
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


data = load_data()
AS_OF_DATE = pd.Timestamp("2026-05-18")
initialize_session_store(st.session_state, data["recommendations"], data["recommendation_events"], data["scan_runs"])

recommendations = enrich_recommendation_lifecycle(recommendations_frame(st.session_state), AS_OF_DATE)
recommendation_events = recommendation_events_frame(st.session_state)
scan_runs = scan_runs_frame(st.session_state)
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
            "Reports",
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
                update_recommendation_status(st.session_state, selected_recommendation_id, status, actor, notes, AS_OF_DATE)
                st.toast(f"{selected_recommendation_id} moved to {status}.")
                st.rerun()
    with right:
        st.caption("Generated SQL or implementation guidance")
        st.code(rec["generated_sql"], language="sql")
        if st.button("Log SQL copied", key=f"{selected_recommendation_id}_copy_sql"):
            log_sql_copied(st.session_state, selected_recommendation_id, rec["owner"], AS_OF_DATE + pd.Timedelta(hours=12))
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
    st.caption(f"Report generated at {pd.Timestamp.now(tz='America/New_York').strftime('%Y-%m-%d %I:%M %p %Z')}.")


def format_report_table(df, money_cols=None, percent_cols=None, limit=None):
    money_cols = set(money_cols or [])
    percent_cols = set(percent_cols or [])
    display = df.copy()
    if limit is not None:
        display = display.head(limit)
    for column in display.columns:
        if column in money_cols:
            display[column] = display[column].fillna(0).map(lambda value: money(float(value)))
        elif column in percent_cols:
            display[column] = display[column].fillna(0).map(lambda value: f"{float(value):.0%}")
        elif pd.api.types.is_datetime64_any_dtype(display[column]):
            display[column] = display[column].dt.strftime("%Y-%m-%d %H:%M")
    return display.to_html(index=False, escape=True, classes="report-table")


def format_export_frame(df, money_cols=None, percent_cols=None, limit=None):
    money_cols = set(money_cols or [])
    percent_cols = set(percent_cols or [])
    display = df.copy()
    if limit is not None:
        display = display.head(limit)
    for column in display.columns:
        if column in money_cols:
            display[column] = display[column].fillna(0).map(lambda value: money(float(value)))
        elif column in percent_cols:
            display[column] = display[column].fillna(0).map(lambda value: f"{float(value):.0%}")
        elif pd.api.types.is_datetime64_any_dtype(display[column]):
            display[column] = display[column].dt.strftime("%Y-%m-%d %H:%M")
    return display.fillna("")


def chart_html(fig):
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


def report_timestamp():
    return pd.Timestamp.now(tz="America/New_York")


def report_filename(report_type, generated_at, extension="html"):
    slug = report_type.lower().replace(" ", "_")
    timestamp = generated_at.strftime("%Y-%m-%d_%H%M")
    return f"{slug}_{timestamp}.{extension}"


def executive_report_context(
    report_type,
    period,
    total_spend,
    realized,
    projected,
    annualized_opportunity,
    open_missed,
    scan_cost,
    scan_roi,
    net_monthly_benefit,
    recommendations_open,
    recommendations_realized,
    monthly_opportunity,
    realized_monthly,
    category_report,
    team_report,
    unresolved,
    owner_report,
    scan_report,
):
    rows = [
        ("Time range", period),
        ("Report type", report_type),
        ("Estimated monthly spend", money(total_spend)),
        (f"{period} realized savings", money(realized)),
        (f"{period} projected savings", money(projected)),
        ("Annualized savings opportunity", money(annualized_opportunity)),
        ("Unresolved missed savings", money(open_missed)),
        ("Open recommendations", f"{recommendations_open:,}"),
        ("Realized recommendations", f"{recommendations_realized:,}"),
        ("Latest scan cost", money(scan_cost)),
        ("Savings found per $1 scan cost", money(scan_roi)),
        ("Net monthly benefit found", money(net_monthly_benefit)),
    ]

    narrative = (
        f"This comprehensive packet shows {money(realized)} in {period} realized savings, "
        f"{money(projected)} in projected savings, and {money(open_missed)} in unresolved missed savings. "
        f"The latest scan found {money(scan_roi)} in monthly opportunity for every estimated dollar of scan cost."
    )

    if report_type == "Savings by category" and not category_report.empty:
        top_projected = category_report.sort_values("projected_monthly_savings", ascending=False).iloc[0]
        top_missed = category_report.sort_values("missed_savings", ascending=False).iloc[0]
        top_realized = category_report.sort_values("realized_monthly_savings", ascending=False).iloc[0]
        rows.extend(
            [
                ("Top projected category", f"{top_projected['category']} - {money(top_projected['projected_monthly_savings'])}/mo"),
                ("Top realized category", f"{top_realized['category']} - {money(top_realized['realized_monthly_savings'])}/mo"),
                ("Highest unresolved category", f"{top_missed['category']} - {money(top_missed['missed_savings'])} missed"),
            ]
        )
        narrative = (
            f"The category report shows {top_projected['category']} as the largest monthly savings opportunity at "
            f"{money(top_projected['projected_monthly_savings'])}. {top_realized['category']} has the highest realized "
            f"monthly savings at {money(top_realized['realized_monthly_savings'])}, while {top_missed['category']} has "
            f"the most unresolved missed savings at {money(top_missed['missed_savings'])}."
        )
    elif report_type == "Savings by team" and not team_report.empty:
        top_projected = team_report.sort_values("projected_monthly_savings", ascending=False).iloc[0]
        top_missed = team_report.sort_values("missed_savings", ascending=False).iloc[0]
        top_realized = team_report.sort_values("realized_monthly_savings", ascending=False).iloc[0]
        rows.extend(
            [
                ("Top projected team", f"{top_projected['team']} - {money(top_projected['projected_monthly_savings'])}/mo"),
                ("Top realized team", f"{top_realized['team']} - {money(top_realized['realized_monthly_savings'])}/mo"),
                ("Highest unresolved team", f"{top_missed['team']} - {money(top_missed['missed_savings'])} missed"),
            ]
        )
        narrative = (
            f"The team report shows {top_projected['team']} as the largest monthly savings opportunity at "
            f"{money(top_projected['projected_monthly_savings'])}. {top_realized['team']} has the highest realized "
            f"monthly savings at {money(top_realized['realized_monthly_savings'])}, while {top_missed['team']} has "
            f"the most unresolved missed savings at {money(top_missed['missed_savings'])}."
        )
    elif report_type == "Unresolved opportunity":
        daily_exposure = unresolved["projected_daily_savings"].sum()
        top_open = unresolved.iloc[0] if not unresolved.empty else None
        rows.extend(
            [
                ("Open daily cost exposure", money(daily_exposure)),
                (
                    "Largest unresolved item",
                    "None"
                    if top_open is None
                    else f"{top_open['recommendation_id']} - {money(top_open['missed_savings_to_date'])} missed",
                ),
            ]
        )
        narrative = (
            f"The unresolved opportunity report focuses on avoidable cost that is still aging. The filtered backlog has "
            f"{recommendations_open:,} open items, representing {money(daily_exposure)} in daily savings exposure and "
            f"{money(open_missed)} in missed savings to date."
        )
    elif report_type == "Owner accountability" and not owner_report.empty:
        top_owner = owner_report.sort_values("missed_savings", ascending=False).iloc[0]
        top_realized = owner_report.sort_values("realized_monthly_savings", ascending=False).iloc[0]
        rows.extend(
            [
                ("Highest unresolved owner", f"{top_owner['owner']} - {money(top_owner['missed_savings'])} missed"),
                ("Highest realized owner", f"{top_realized['owner']} - {money(top_realized['realized_monthly_savings'])}/mo"),
                ("Open items for highest unresolved owner", f"{int(top_owner['open_items']):,}"),
            ]
        )
        narrative = (
            f"The owner accountability report highlights ownership of unresolved savings. {top_owner['owner']} has the "
            f"largest unresolved missed savings at {money(top_owner['missed_savings'])}, while {top_realized['owner']} "
            f"has the highest realized monthly savings at {money(top_realized['realized_monthly_savings'])}."
        )
    elif report_type == "Scan ROI history":
        successful_scans = int((scan_report["status"] == "SUCCEEDED").sum()) if "status" in scan_report else len(scan_report)
        avg_scan_cost = scan_report["scan_cost_usd"].mean() if not scan_report.empty else 0
        avg_roi = scan_report["savings_per_scan_dollar"].mean() if not scan_report.empty else 0
        rows.extend(
            [
                ("Successful scans", f"{successful_scans:,}"),
                ("Average scan cost", money(avg_scan_cost)),
                ("Average savings found per $1 scan cost", money(avg_roi)),
            ]
        )
        narrative = (
            f"The scan ROI report shows whether analysis runs are economically justified. Across the filtered view, "
            f"the latest scan cost is {money(scan_cost)} and found {money(scan_roi)} in monthly opportunity for every "
            f"estimated dollar of scan cost."
        )
    elif report_type == "Executive ROI summary":
        realization_rate = realized_monthly / monthly_opportunity if monthly_opportunity else 0
        rows.append(("Realization rate", f"{realization_rate:.0%}"))
        narrative = (
            f"The executive ROI report summarizes financial impact for leadership. It shows {money(realized)} in "
            f"{period} realized savings, {money(projected)} in projected savings, and a {realization_rate:.0%} "
            f"monthly realization rate for the current filtered view."
        )

    return narrative, pd.DataFrame(rows, columns=["Metric", "Value"])


def report_money_columns():
    return [
        "projected_monthly_savings",
        "projected_annual_savings",
        "realized_monthly_savings",
        "missed_savings",
        "projected_daily_savings",
        "missed_savings_to_date",
        "scan_cost_usd",
        "identified_monthly_savings",
        "savings_per_scan_dollar",
    ]


def build_excel_report(
    report_type,
    executive_narrative,
    summary_rows,
    category_report,
    team_report,
    unresolved,
    owner_report,
    scan_report,
    backlog_export,
    event_view,
    selected_sections,
    report_detail,
):
    money_columns = report_money_columns()
    limits = REPORT_DETAIL_LIMITS[report_detail]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#E8F1FA", "border": 1})
        money_fmt = workbook.add_format({"num_format": "$#,##0"})

        pd.DataFrame([{"Executive Summary": executive_narrative}]).to_excel(
            writer, sheet_name="Executive Summary", index=False, startrow=0
        )
        summary_rows.to_excel(writer, sheet_name="Executive Summary", index=False, startrow=3)
        if report_type == "Executive ROI summary":
            roi_lines = pd.DataFrame(
                [
                    {"Included Report": "Executive ROI summary only"},
                    {"Included Report": "Use a savings/team/category report preset for operational breakdown tabs."},
                ]
            )
            roi_lines.to_excel(writer, sheet_name="Executive ROI", index=False)
        if "Savings by category" in selected_sections:
            category_report.to_excel(writer, sheet_name="Category Savings", index=False)
        if "Savings by team" in selected_sections:
            team_report.to_excel(writer, sheet_name="Team Savings", index=False)
        if "Unresolved opportunity" in selected_sections:
            unresolved.head(limits["section"]).to_excel(writer, sheet_name="Unresolved", index=False)
        if "Owner accountability" in selected_sections:
            owner_report.to_excel(writer, sheet_name="Owner Accountability", index=False)
        if "Scan ROI history" in selected_sections:
            scan_report.to_excel(writer, sheet_name="Scan ROI", index=False)
        backlog_export.head(limits["backlog"]).to_excel(writer, sheet_name="Backlog", index=False)
        event_view.sort_values("event_ts", ascending=False).head(limits["audit"]).to_excel(
            writer, sheet_name="Audit Log", index=False
        )

        for sheet_name, worksheet in writer.sheets.items():
            worksheet.freeze_panes(1, 0)
            worksheet.set_row(0, None, header_fmt)
            worksheet.set_column(0, 0, 22)
            worksheet.set_column(1, 20, 18)
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            worksheet.autofilter(0, 0, 0, 20)
            for col_idx in range(0, 20):
                worksheet.set_column(col_idx, col_idx, 18)
            if sheet_name != "Executive Summary":
                worksheet.set_column(0, 0, 24)
        for sheet_name, df in {
            "Category Savings": category_report,
            "Team Savings": team_report,
            "Unresolved": unresolved,
            "Owner Accountability": owner_report,
            "Scan ROI": scan_report,
            "Backlog": backlog_export,
        }.items():
            if sheet_name not in writer.sheets:
                continue
            worksheet = writer.sheets[sheet_name]
            for idx, column in enumerate(df.columns):
                if column in money_columns:
                    worksheet.set_column(idx, idx, 18, money_fmt)
    output.seek(0)
    return output.getvalue()


def pdf_table(df, money_cols=None, percent_cols=None, limit=20, max_cols=8):
    display = format_export_frame(df, money_cols, percent_cols, limit=limit)
    if len(display.columns) > max_cols:
        display = display.iloc[:, :max_cols]
    rows = [display.columns.tolist()] + display.astype(str).values.tolist()
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F1FA")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8DEE9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    return table


def build_pdf_report(
    report_type,
    period,
    generated_at,
    executive_narrative,
    summary_rows,
    category_report,
    team_report,
    unresolved,
    owner_report,
    scan_report,
    backlog_export,
    event_view,
    selected_sections,
    report_detail,
):
    money_columns = report_money_columns()
    limits = REPORT_DETAIL_LIMITS[report_detail]
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(letter),
        rightMargin=24,
        leftMargin=24,
        topMargin=24,
        bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(report_type.title(), styles["Title"]),
        Paragraph(f"Generated {generated_at.strftime('%Y-%m-%d %I:%M %p %Z')}", styles["Normal"]),
        Spacer(1, 10),
        Paragraph("Executive Summary", styles["Heading2"]),
        Paragraph(executive_narrative, styles["BodyText"]),
        Spacer(1, 8),
        Paragraph("Executive ROI Summary", styles["Heading2"]),
        pdf_table(summary_rows, limit=30, max_cols=2),
    ]

    sections = []
    if "Savings by category" in selected_sections:
        sections.append(("Savings by Category", category_report.sort_values("projected_monthly_savings", ascending=False)))
    if "Savings by team" in selected_sections:
        sections.append(("Savings by Team", team_report.sort_values("missed_savings", ascending=False)))
    if "Unresolved opportunity" in selected_sections:
        sections.append(("Unresolved Opportunity", unresolved))
    if "Owner accountability" in selected_sections:
        sections.append(("Owner Accountability", owner_report.sort_values("missed_savings", ascending=False)))
    if "Scan ROI history" in selected_sections:
        sections.append(("Scan ROI History", scan_report.sort_values("started_at", ascending=False)))

    if sections:
        story.append(PageBreak())

    for title, frame in sections:
        story.extend(
            [
                Paragraph(title, styles["Heading2"]),
                pdf_table(frame, money_columns, ["realization_rate"], limit=limits["section"]),
                Spacer(1, 10),
            ]
        )

    if sections:
        story.append(PageBreak())
    else:
        story.append(Spacer(1, 12))

    story.extend(
        [
            Paragraph("Recommendation Backlog Detail", styles["Heading2"]),
            pdf_table(backlog_export, money_columns, limit=limits["backlog"]),
            Spacer(1, 10),
            Paragraph("Audit Log Evidence", styles["Heading2"]),
            pdf_table(event_view.sort_values("event_ts", ascending=False), limit=limits["audit"]),
            Spacer(1, 12),
            Paragraph(f"Downloaded/generated timestamp: {generated_at.strftime('%Y-%m-%d %I:%M %p %Z')}", styles["Normal"]),
        ]
    )
    doc.build(story)
    output.seek(0)
    return output.getvalue()


def build_finance_packet_html(
    report_type,
    period,
    filters,
    generated_at,
    executive_narrative,
    summary_rows,
    roi_bridge,
    category_report,
    team_report,
    unresolved,
    owner_report,
    scan_report,
    backlog_export,
    event_view,
    selected_sections,
    report_detail,
):
    generated_ts = generated_at.strftime("%Y-%m-%d %I:%M %p %Z")
    filter_rows = pd.DataFrame(
        [
            ("Report", report_type),
            ("Time range", period),
            ("Category", filters["category"]),
            ("Team", filters["team"]),
            ("Owner", filters["owner"]),
            ("Status", filters["status"]),
            ("Severity", filters["severity"]),
        ],
        columns=["Filter", "Value"],
    )

    roi_fig = px.bar(roi_bridge, x="Measure", y="Amount", text="Amount", labels={"Amount": "USD", "Measure": ""})
    roi_fig.update_traces(texttemplate="$%{text:,.0f}", marker_color="#1f8a5b")
    roi_fig.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=30, b=80),
        xaxis_tickangle=-25,
        template="plotly_white",
    )

    category_chart = category_report.melt(
        "category",
        value_vars=["projected_monthly_savings", "realized_monthly_savings", "missed_savings"],
        var_name="metric",
        value_name="amount",
    )
    category_fig = px.bar(
        category_chart,
        x="amount",
        y="category",
        color="metric",
        orientation="h",
        barmode="group",
        labels={"amount": "USD", "category": ""},
        color_discrete_map=REPORT_METRIC_COLORS,
    )
    category_fig.update_layout(height=390, margin=dict(l=20, r=20, t=30, b=30), legend_title_text="", template="plotly_white")

    team_fig = px.scatter(
        team_report,
        x="projected_monthly_savings",
        y="missed_savings",
        size="open_items",
        color="team",
        hover_name="team",
        labels={"projected_monthly_savings": "Projected Monthly Savings", "missed_savings": "Unresolved Missed Savings"},
        color_discrete_sequence=REPORT_COLORS,
    )
    team_fig.update_layout(height=390, margin=dict(l=20, r=20, t=30, b=30), legend_title_text="", template="plotly_white")

    unresolved_fig = px.bar(
        unresolved.head(15).sort_values("missed_savings_to_date"),
        x="missed_savings_to_date",
        y="recommendation_id",
        color="team",
        orientation="h",
        hover_data=["title", "owner", "category", "days_lingering"],
        labels={"missed_savings_to_date": "Missed Savings", "recommendation_id": ""},
        color_discrete_sequence=REPORT_COLORS,
    )
    unresolved_fig.update_layout(height=430, margin=dict(l=20, r=20, t=30, b=30), legend_title_text="", template="plotly_white")

    owner_fig = px.bar(
        owner_report.sort_values("missed_savings", ascending=True),
        x="missed_savings",
        y="owner",
        color="team",
        orientation="h",
        hover_data=["open_items", "projected_monthly_savings", "realized_monthly_savings", "avg_days_open"],
        labels={"missed_savings": "Unresolved Missed Savings", "owner": ""},
        color_discrete_sequence=REPORT_COLORS,
    )
    owner_fig.update_layout(height=390, margin=dict(l=20, r=20, t=30, b=30), legend_title_text="", template="plotly_white")

    scan_fig = px.line(
        scan_report.sort_values("completed_at"),
        x="completed_at",
        y="savings_per_scan_dollar",
        markers=True,
        labels={"completed_at": "", "savings_per_scan_dollar": "Savings Found per $1 Scan Cost"},
    )
    scan_fig.update_traces(line_color="#1f8a5b")
    scan_fig.update_xaxes(tickformat="%b %d")
    scan_fig.update_layout(height=330, margin=dict(l=20, r=20, t=30, b=30), template="plotly_white")

    money_columns = [
        "projected_monthly_savings",
        "projected_annual_savings",
        "realized_monthly_savings",
        "missed_savings",
        "projected_daily_savings",
        "missed_savings_to_date",
        "scan_cost_usd",
        "identified_monthly_savings",
        "savings_per_scan_dollar",
    ]
    summary_cards = "".join(
        f"<div class='metric-card'><span>{escape(str(row.Metric))}</span><strong>{escape(str(row.Value))}</strong></div>"
        for row in summary_rows.itertuples(index=False)
        if row.Metric not in {"Time range", "Report type"}
    )
    limits = REPORT_DETAIL_LIMITS[report_detail]
    category_section = ""
    team_section = ""
    unresolved_section = ""
    owner_section = ""
    scan_section = ""

    executive_section = f"""
  <h2>Executive Summary</h2>
  <p>
    {escape(executive_narrative)}
  </p>
  <h2>Executive ROI Summary</h2>
  <div class="metric-grid">{summary_cards}</div>
  {chart_html(roi_fig)}
  {format_report_table(summary_rows)}
"""

    if "Savings by category" in selected_sections:
        category_section = f"""
  <h2>Savings by Category</h2>
  {chart_html(category_fig)}
  {format_report_table(category_report.sort_values("projected_monthly_savings", ascending=False), money_columns, ["realization_rate"])}
"""

    if "Savings by team" in selected_sections:
        team_section = f"""
  <h2>Savings by Team</h2>
  {chart_html(team_fig)}
  {format_report_table(team_report.sort_values("missed_savings", ascending=False), money_columns, ["realization_rate"])}
"""

    if "Unresolved opportunity" in selected_sections:
        unresolved_section = f"""
  <h2>Unresolved Opportunity</h2>
  {chart_html(unresolved_fig)}
  {format_report_table(unresolved[["recommendation_id", "title", "category", "team", "owner", "status", "projected_daily_savings", "missed_savings_to_date", "days_lingering"]], money_columns, limit=limits["section"])}
"""

    if "Owner accountability" in selected_sections:
        owner_section = f"""
  <h2>Owner Accountability</h2>
  {chart_html(owner_fig)}
  {format_report_table(owner_report.sort_values("missed_savings", ascending=False), money_columns)}
"""

    if "Scan ROI history" in selected_sections:
        scan_section = f"""
  <h2>Scan ROI History</h2>
  {chart_html(scan_fig)}
  {format_report_table(scan_report.sort_values("started_at", ascending=False), money_columns)}
"""

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(report_type.title())}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; color: #172033; margin: 28px; }}
    h1 {{ margin-bottom: 4px; }}
    h2 {{ border-bottom: 1px solid #d8dee9; padding-bottom: 6px; margin-top: 30px; }}
    .meta {{ color: #64748b; font-size: 13px; margin-bottom: 18px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 18px 0; }}
    .metric-card {{ border: 1px solid #d8dee9; border-left: 5px solid #1f8a5b; border-radius: 8px; padding: 10px 12px; }}
    .metric-card span {{ display: block; color: #64748b; font-size: 12px; }}
    .metric-card strong {{ display: block; font-size: 21px; margin-top: 3px; }}
    .report-table {{ border-collapse: collapse; width: 100%; font-size: 12px; margin: 10px 0 18px; }}
    .report-table th {{ text-align: left; background: #f1f5f9; border: 1px solid #d8dee9; padding: 7px; }}
    .report-table td {{ border: 1px solid #e5e7eb; padding: 7px; vertical-align: top; }}
    .footer {{ margin-top: 34px; color: #64748b; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>{escape(report_type.title())}</h1>
  <div class="meta">Generated {escape(generated_ts)} from the current filtered report view.</div>
  <h2>Report Context</h2>
  {format_report_table(filter_rows)}
  {executive_section}
  {category_section}
  {team_section}
  {unresolved_section}
  {owner_section}
  {scan_section}
  <h2>Recommendation Backlog Detail</h2>
  {format_report_table(backlog_export, money_columns, limit=limits["backlog"])}
  <h2>Audit Log Evidence</h2>
  {format_report_table(event_view.sort_values("event_ts", ascending=False), limit=limits["audit"])}
  <div class="footer">Downloaded/generated timestamp: {escape(generated_ts)}</div>
</body>
</html>"""


def reports_page():
    st.title("Reports")
    top_cols = st.columns([1.35, 0.95, 1, 1, 1, 1])
    with top_cols[0]:
        report_type = st.selectbox(
            "Report",
            [
                "Comprehensive finance packet",
                "Executive ROI summary",
                "Savings by team",
                "Savings by category",
                "Unresolved opportunity",
                "Owner accountability",
                "Scan ROI history",
                "Custom report",
            ],
        )
    with top_cols[1]:
        period = st.selectbox("Time range", ["MTD", "QTD", "YTD", "Since inception"], index=2)
    with top_cols[2]:
        category = st.selectbox("Category", category_options, key="reports_category")
    with top_cols[3]:
        team = st.selectbox("Team", team_options, key="reports_team")
    with top_cols[4]:
        owner = st.selectbox("Owner", owner_options, key="reports_owner")
    with top_cols[5]:
        status = st.selectbox("Status", status_options, key="reports_status")

    severity = st.segmented_control("Severity", ["All"] + severity_order, default="All")
    selected_sections = REPORT_PRESETS[report_type]
    page_recs = apply_recommendation_filters(
        recommendations,
        status=status,
        category=category,
        owner=owner,
        team=team,
        min_confidence=0.0,
    )
    if severity != "All":
        page_recs = page_recs[page_recs["severity"] == severity]

    total_spend = projected_monthly_warehouse_spend(warehouses)
    realized, projected = savings_by_period(page_recs, period)
    monthly_opportunity = page_recs["projected_monthly_savings"].sum()
    open_missed = page_recs.loc[page_recs["is_open"], "missed_savings_to_date"].sum()
    realized_monthly = page_recs["realized_monthly_savings"].sum()
    realization_rate = realized_monthly / monthly_opportunity if monthly_opportunity else 0
    annualized_opportunity = monthly_opportunity * 12
    recommendations_open = int(page_recs["is_open"].sum())
    recommendations_realized = int((page_recs["status"] == "Realized").sum())
    latest_scan = latest_successful_scan(scan_runs)
    scan_cost = latest_scan["credits_estimated"] * DEFAULT_CREDIT_PRICE if latest_scan is not None else 0
    scan_roi = monthly_opportunity / scan_cost if scan_cost else 0
    net_monthly_benefit = monthly_opportunity - scan_cost

    roi_bridge = pd.DataFrame(
        [
            ("Current monthly spend", total_spend),
            ("Monthly opportunity found", monthly_opportunity),
            ("Realized monthly savings", realized_monthly),
            ("Unresolved missed savings", open_missed),
            ("Latest scan cost", scan_cost),
            ("Net monthly benefit found", net_monthly_benefit),
        ],
        columns=["Measure", "Amount"],
    )
    category_report = page_recs.groupby("category", as_index=False).agg(
        recommendations=("recommendation_id", "count"),
        open_items=("is_open", "sum"),
        projected_monthly_savings=("projected_monthly_savings", "sum"),
        projected_annual_savings=("projected_annual_savings", "sum"),
        realized_monthly_savings=("realized_monthly_savings", "sum"),
        missed_savings=("missed_savings_to_date", "sum"),
        avg_days_open=("days_lingering", "mean"),
    )
    category_report["realization_rate"] = (
        category_report["realized_monthly_savings"] / category_report["projected_monthly_savings"]
    ).fillna(0)
    team_report = page_recs.groupby("team", as_index=False).agg(
        recommendations=("recommendation_id", "count"),
        open_items=("is_open", "sum"),
        projected_monthly_savings=("projected_monthly_savings", "sum"),
        projected_annual_savings=("projected_annual_savings", "sum"),
        realized_monthly_savings=("realized_monthly_savings", "sum"),
        missed_savings=("missed_savings_to_date", "sum"),
        avg_days_open=("days_lingering", "mean"),
    )
    team_report["realization_rate"] = (
        team_report["realized_monthly_savings"] / team_report["projected_monthly_savings"]
    ).fillna(0)
    unresolved = page_recs[page_recs["is_open"]].sort_values(
        ["missed_savings_to_date", "projected_daily_savings"], ascending=False
    )
    owner_report = page_recs.groupby(["owner", "team"], as_index=False).agg(
        recommendations=("recommendation_id", "count"),
        open_items=("is_open", "sum"),
        projected_monthly_savings=("projected_monthly_savings", "sum"),
        realized_monthly_savings=("realized_monthly_savings", "sum"),
        missed_savings=("missed_savings_to_date", "sum"),
        avg_days_open=("days_lingering", "mean"),
    )
    scan_report = scan_runs.copy()
    scan_report["scan_cost_usd"] = scan_report["credits_estimated"] * DEFAULT_CREDIT_PRICE
    scan_report["identified_monthly_savings"] = monthly_opportunity
    scan_report["savings_per_scan_dollar"] = scan_report["identified_monthly_savings"] / scan_report["scan_cost_usd"]
    scan_report.loc[scan_report["scan_cost_usd"] == 0, "savings_per_scan_dollar"] = 0
    backlog_cols = [
        "recommendation_id",
        "severity",
        "category",
        "subcategory",
        "title",
        "owner",
        "team",
        "status",
        "projected_daily_savings",
        "projected_monthly_savings",
        "projected_annual_savings",
        "missed_savings_to_date",
        "realized_monthly_savings",
        "days_lingering",
        "risk",
        "effort",
    ]
    backlog_export = page_recs[backlog_cols].sort_values("missed_savings_to_date", ascending=False)
    event_view = recommendation_events.merge(
        recommendations[["recommendation_id", "category", "owner", "team", "title"]],
        on="recommendation_id",
        how="left",
    )
    if category != "All":
        event_view = event_view[event_view["category"] == category]
    if owner != "All":
        event_view = event_view[event_view["owner"] == owner]
    if team != "All":
        event_view = event_view[event_view["team"] == team]
    executive_narrative, summary_rows = executive_report_context(
        report_type,
        period,
        total_spend,
        realized,
        projected,
        annualized_opportunity,
        open_missed,
        scan_cost,
        scan_roi,
        net_monthly_benefit,
        recommendations_open,
        recommendations_realized,
        monthly_opportunity,
        realized_monthly,
        category_report,
        team_report,
        unresolved,
        owner_report,
        scan_report,
    )
    action_cols = st.columns([1.15, 1.12, 1.05, 2.9], gap="small", vertical_alignment="top")
    with action_cols[0]:
        report_detail = st.selectbox(
            "Report detail",
            ["Summary only", "Standard detail", "Full detail"],
            index=2,
        )
        st.markdown('<div class="control-help">Amount of recommendation and audit detail included.</div>', unsafe_allow_html=True)
    with action_cols[1]:
        download_format = st.radio("Download format", ["PDF", "Excel", "HTML"], horizontal=True, index=0)
        st.markdown('<div class="control-help">Choose the file type for this report.</div>', unsafe_allow_html=True)

    generated_at = report_timestamp()
    if download_format == "PDF":
        download_data = build_pdf_report(
            report_type,
            period,
            generated_at,
            executive_narrative,
            summary_rows,
            category_report,
            team_report,
            unresolved,
            owner_report,
            scan_report,
            backlog_export,
            event_view,
            selected_sections,
            report_detail,
        )
        download_extension = "pdf"
        download_mime = "application/pdf"
    elif download_format == "Excel":
        download_data = build_excel_report(
            report_type,
            executive_narrative,
            summary_rows,
            category_report,
            team_report,
            unresolved,
            owner_report,
            scan_report,
            backlog_export,
            event_view,
            selected_sections,
            report_detail,
        )
        download_extension = "xlsx"
        download_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        download_data = build_finance_packet_html(
            report_type,
            period,
            {
                "category": category,
                "team": team,
                "owner": owner,
                "status": status,
                "severity": severity,
            },
            generated_at,
            executive_narrative,
            summary_rows,
            roi_bridge,
            category_report,
            team_report,
            unresolved,
            owner_report,
            scan_report,
            backlog_export,
            event_view,
            selected_sections,
            report_detail,
        )
        download_extension = "html"
        download_mime = "text/html"

    with action_cols[2]:
        st.markdown('<div class="download-spacer"></div>', unsafe_allow_html=True)
        st.download_button(
            "Download report",
            download_data,
            file_name=report_filename(report_type, generated_at, download_extension),
            mime=download_mime,
            use_container_width=True,
            type="primary",
        )
    with action_cols[3]:
        st.markdown('<div class="download-spacer"></div>', unsafe_allow_html=True)
        st.caption(
            f"Sections: {', '.join(selected_sections) if selected_sections else 'Executive summary only'} | "
            f"Format: {download_format}"
        )

    st.markdown(
        f"""
        <div class="report-grid">
            <div class="report-card"><span>{period} Realized Savings</span><strong>{money(realized)}</strong><span>validated benefit</span></div>
            <div class="report-card"><span>{period} Projected Savings</span><strong>{money(projected)}</strong><span>total opportunity</span></div>
            <div class="report-card"><span>Annualized Opportunity</span><strong>{money(annualized_opportunity)}</strong><span>based on current findings</span></div>
            <div class="report-card"><span>Unresolved Missed Savings</span><strong>{money(open_missed)}</strong><span>open items aging</span></div>
            <div class="report-card"><span>Savings Found per $1 Scan Cost</span><strong>{money(scan_roi)}</strong><span>latest scan estimate</span></div>
            <div class="report-card"><span>Net Monthly Benefit Found</span><strong>{money(net_monthly_benefit)}</strong><span>opportunity less scan cost</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Executive Summary")
    st.write(executive_narrative)
    st.subheader("Executive ROI Summary")
    roi_cols = st.columns([1, 1])
    with roi_cols[0]:
        fig = px.bar(
            roi_bridge,
            x="Measure",
            y="Amount",
            text="Amount",
            labels={"Amount": "USD", "Measure": ""},
        )
        fig.update_traces(texttemplate="$%{text:,.0f}", marker_color="#1f8a5b")
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=20, b=10), xaxis_tickangle=-25)
        st.plotly_chart(fig, use_container_width=True)
    with roi_cols[1]:
        st.dataframe(
            summary_rows,
            use_container_width=True,
            hide_index=True,
        )

    if "Savings by category" in selected_sections:
        st.subheader("Savings by Category")
        left, right = st.columns([1.1, 1])
        with left:
            category_chart = category_report.melt(
                "category",
                value_vars=["projected_monthly_savings", "realized_monthly_savings", "missed_savings"],
                var_name="metric",
                value_name="amount",
            )
            fig = px.bar(
                category_chart,
                x="amount",
                y="category",
                color="metric",
                orientation="h",
                barmode="group",
                labels={"amount": "USD", "category": ""},
            )
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.dataframe(
                category_report.sort_values("projected_monthly_savings", ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "projected_monthly_savings": st.column_config.NumberColumn("Projected Monthly", format="$%d"),
                    "projected_annual_savings": st.column_config.NumberColumn("Projected Annual", format="$%d"),
                    "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
                    "missed_savings": st.column_config.NumberColumn("Missed Savings", format="$%d"),
                    "avg_days_open": st.column_config.NumberColumn("Avg Days Open", format="%.1f"),
                    "realization_rate": st.column_config.NumberColumn("Realization Rate", format="%.0%"),
                },
            )

    if "Savings by team" in selected_sections:
        st.subheader("Savings by Team")
        left, right = st.columns([1.05, 1])
        with left:
            fig = px.scatter(
                team_report,
                x="projected_monthly_savings",
                y="missed_savings",
                size="open_items",
                color="team",
                hover_name="team",
                labels={"projected_monthly_savings": "Projected Monthly Savings", "missed_savings": "Unresolved Missed Savings"},
            )
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.dataframe(
                team_report.sort_values("missed_savings", ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "projected_monthly_savings": st.column_config.NumberColumn("Projected Monthly", format="$%d"),
                    "projected_annual_savings": st.column_config.NumberColumn("Projected Annual", format="$%d"),
                    "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
                    "missed_savings": st.column_config.NumberColumn("Missed Savings", format="$%d"),
                    "avg_days_open": st.column_config.NumberColumn("Avg Days Open", format="%.1f"),
                    "realization_rate": st.column_config.NumberColumn("Realization Rate", format="%.0%"),
                },
            )

    if "Unresolved opportunity" in selected_sections:
        st.subheader("Unresolved Opportunity")
        st.markdown(
            f"""
            The filtered backlog has **{recommendations_open:,}** open recommendations. If left unresolved, those
            items continue to add approximately **{money(unresolved["projected_daily_savings"].sum())}** per day
            in avoidable cost exposure.
            """
        )
        left, right = st.columns([1, 1])
        with left:
            top_unresolved = unresolved.head(15)
            fig = px.bar(
                top_unresolved.sort_values("missed_savings_to_date"),
                x="missed_savings_to_date",
                y="recommendation_id",
                color="team",
                orientation="h",
                hover_data=["title", "owner", "category", "days_lingering"],
                labels={"missed_savings_to_date": "Missed Savings", "recommendation_id": ""},
            )
            fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.dataframe(
                unresolved[
                    [
                        "recommendation_id",
                        "title",
                        "category",
                        "team",
                        "owner",
                        "status",
                        "projected_daily_savings",
                        "missed_savings_to_date",
                        "days_lingering",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "projected_daily_savings": st.column_config.NumberColumn("Daily Savings", format="$%d"),
                    "missed_savings_to_date": st.column_config.NumberColumn("Missed Savings", format="$%d"),
                    "days_lingering": st.column_config.NumberColumn("Days Open", format="%d"),
                },
            )

    if "Owner accountability" in selected_sections:
        st.subheader("Owner Accountability")
        fig = px.bar(
            owner_report.sort_values("missed_savings", ascending=True),
            x="missed_savings",
            y="owner",
            color="team",
            orientation="h",
            hover_data=["open_items", "projected_monthly_savings", "realized_monthly_savings", "avg_days_open"],
            labels={"missed_savings": "Unresolved Missed Savings", "owner": ""},
        )
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            owner_report.sort_values("missed_savings", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "projected_monthly_savings": st.column_config.NumberColumn("Projected Monthly", format="$%d"),
                "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
                "missed_savings": st.column_config.NumberColumn("Missed Savings", format="$%d"),
                "avg_days_open": st.column_config.NumberColumn("Avg Days Open", format="%.1f"),
            },
        )

    if "Scan ROI history" in selected_sections:
        st.subheader("Scan ROI History")
        left, right = st.columns([1, 1])
        with left:
            fig = px.bar(
                scan_report.sort_values("completed_at"),
                x="completed_at",
                y=["recommendations_new", "recommendations_updated"],
                labels={"completed_at": "", "value": "Recommendations", "variable": ""},
            )
            fig.update_xaxes(tickformat="%b %d")
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            fig = px.line(
                scan_report.sort_values("completed_at"),
                x="completed_at",
                y="savings_per_scan_dollar",
                markers=True,
                labels={"completed_at": "", "savings_per_scan_dollar": "Savings Found per $1 Scan Cost"},
            )
            fig.update_traces(line_color="#1f8a5b")
            fig.update_xaxes(tickformat="%b %d")
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            scan_report.sort_values("started_at", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "credits_estimated": st.column_config.NumberColumn("Credits", format="%.2f"),
                "scan_cost_usd": st.column_config.NumberColumn("Scan Cost", format="$%d"),
                "identified_monthly_savings": st.column_config.NumberColumn("Identified Monthly Savings", format="$%d"),
                "savings_per_scan_dollar": st.column_config.NumberColumn("Savings per $1 Scan Cost", format="$%d"),
            },
        )

    st.subheader("Comprehensive Detail")
    st.dataframe(
        backlog_export,
        use_container_width=True,
        hide_index=True,
        column_config={
            "projected_daily_savings": st.column_config.NumberColumn("Daily Savings", format="$%d"),
            "projected_monthly_savings": st.column_config.NumberColumn("Monthly Savings", format="$%d"),
            "projected_annual_savings": st.column_config.NumberColumn("Annual Savings", format="$%d"),
            "missed_savings_to_date": st.column_config.NumberColumn("Missed Savings", format="$%d"),
            "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
            "days_lingering": st.column_config.NumberColumn("Days Open", format="%d"),
        },
    )
    st.dataframe(
        event_view.sort_values("event_ts", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"Report generated at {generated_at.strftime('%Y-%m-%d %I:%M %p %Z')}.")


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
        schedule = st.selectbox("Schedule", ["Daily", "Weekly", "Monthly", "Off"], index=0)
        preferred_time = st.time_input("Preferred scan time", value=pd.Timestamp("2026-05-18 08:00").time())
    with center:
        scan_scope = st.selectbox("Scan scope", ["Full", "Incremental"], index=0)
        lookback_window = st.selectbox("Lookback window", ["7 days", "30 days", "90 days", "All available"], index=1)
    with right:
        st.selectbox("Next scheduled scan", ["2026-05-19 08:00", "2026-05-20 08:00", "Manual only"], index=0)
        run_now = st.button("Run analysis now", type="primary")

    lookback_days = {"7 days": 7, "30 days": 30, "90 days": 90, "All available": 365}[lookback_window]
    st.caption(
        "Run analysis now uses the CostOps rule engine against the selected source. In sample mode it regenerates "
        "recommendations from demo warehouse, workload, task, and storage data. In Snowflake mode it attempts to "
        "read account usage metadata, then writes results to the local workflow store and optional Snowflake tables."
    )

    if run_now:
        actor = "Ad hoc user"
        run_ts = pd.Timestamp.now().tz_localize(None)
        analysis_inputs = {
            "warehouses": warehouses,
            "workloads": workloads,
            "storage": storage,
            "tasks": tasks,
        }
        if data_source_mode == "Snowflake" and snowflake_config:
            try:
                analysis_inputs = load_account_usage_snapshot(
                    snowflake_config,
                    lookback_days=lookback_days,
                    credit_price=credit_price,
                )
            except Exception as exc:
                st.warning(f"Snowflake metadata scan failed; running against currently loaded data instead. {exc}")

        scan_result = run_environment_analysis(
            analysis_inputs["warehouses"],
            analysis_inputs["workloads"],
            analysis_inputs["storage"],
            analysis_inputs["tasks"],
            AnalysisConfig(
                credit_price=credit_price,
                lookback_days=lookback_days,
                scan_scope=scan_scope,
                initiated_by=actor,
                source_mode=data_source_mode,
            ),
            as_of_ts=run_ts,
        )
        scan_result["scan_run"]["frequency"] = schedule
        scan_result["scan_run"]["schedule_name"] = f"{schedule} at {preferred_time.strftime('%H:%M')}"
        merge_scan_results(st.session_state, scan_result, actor, run_ts)

        if data_source_mode == "Snowflake" and snowflake_config:
            try:
                persist_analysis_result(snowflake_config, scan_result)
                st.success(
                    f"{scan_result['scan_run']['scan_id']} generated {len(scan_result['recommendations'])} recommendations "
                    "and persisted them to Snowflake."
                )
            except Exception as exc:
                st.warning(
                    f"{scan_result['scan_run']['scan_id']} generated {len(scan_result['recommendations'])} recommendations "
                    f"locally, but Snowflake persistence failed: {exc}"
                )
        else:
            st.success(
                f"{scan_result['scan_run']['scan_id']} generated {len(scan_result['recommendations'])} recommendations "
                "from the local analysis runner."
            )
        st.rerun()

    st.subheader("Analysis Runner Coverage")
    coverage = pd.DataFrame(
        [
            ("Warehouse metering", len(warehouses), "Oversizing, idle runtime, auto-suspend tuning"),
            ("Query/workload history", len(workloads), "Full refresh, scan volume, spill reduction"),
            ("Task history", len(tasks), "Over-frequent schedules and failure churn"),
            ("Storage objects", len(storage), "Stale objects and dev/QA duplication"),
        ],
        columns=["Source", "Rows Available", "Rules Applied"],
    )
    st.dataframe(coverage, use_container_width=True, hide_index=True)

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
        if st.button("Initialize persistence schema"):
            if not snowflake_config:
                st.error("No Snowflake secrets found. Add credentials before creating Snowflake objects.")
            else:
                try:
                    initialize_app_schema(snowflake_config)
                    st.success("Core recommendation, scan, event, and savings objects are ready in Snowflake.")
                except Exception as exc:
                    st.error(f"Schema initialization failed: {exc}")
    with right_conn:
        st.caption(
            "Live mode can pull warehouse, query, task, and storage account-usage metadata. The persistence schema button creates the "
            "Snowflake tables and workflow procedures that will back recommendation status changes, audit events, "
            "scan history, and savings snapshots."
        )

    st.subheader("Persistence Layer")
    persistence_assets = pd.DataFrame(
        [
            ("Core tables", "sql/app/001_core_tables.sql", "Recommendation, event, scan, finding, and savings tables"),
            ("Workflow procedures", "sql/app/002_recommendation_workflow_procedures.sql", "Status updates and SQL-copy audit events"),
            ("Local adapter", "costops/data/recommendation_store.py", "Session-backed workflow store for POC actions"),
            ("Snowflake adapter", "costops/data/snowflake_repository.py", "Schema initialization and procedure calls"),
            ("Analysis runner", "costops/services/analysis_runner.py", "Turns warehouse, workload, task, and storage metadata into recommendations"),
            ("Native App scaffold", "native_app/", "Draft manifest, setup script, readme, and environment file"),
        ],
        columns=["Asset", "Path", "Purpose"],
    )
    st.dataframe(persistence_assets, use_container_width=True, hide_index=True)

    st.subheader("Native App Readiness Checklist")
    readiness = pd.DataFrame(
        [
            ("Application package", "Drafted", "Validate native_app manifest and setup script in a Snowflake test package"),
            ("Privilege model", "Not started", "Document access to account usage metadata"),
            ("Persistence schema", "POC ready", "Core tables and workflow procedures created under sql/app"),
            ("Analysis runner", "POC ready", "Rules generate recommendations from warehouse, workload, task, and storage metadata"),
            ("Scan procedure", "Next", "Move Python runner logic into Snowflake-executable stored procedure/task path"),
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
elif page == "Reports":
    reports_page()
else:
    settings_page()
