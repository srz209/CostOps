from pathlib import Path
from html import escape
from io import BytesIO
import os
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from costops.data.app_settings_store import (
    application_role_catalog,
    business_role_catalog,
    current_app_settings,
    initialize_app_settings,
    persist_app_settings,
    team_catalog,
    user_directory_frame,
    user_lookup_map,
)
from costops.data.enterprise_audit_store import (
    enterprise_audit_frame,
    initialize_enterprise_audit_store,
    log_enterprise_audit_event,
)
from costops.data.sample_loader import load_sample_data
from costops.data.recommendation_store import (
    initialize_session_store,
    log_sql_copied,
    merge_scan_results,
    recommendation_events_frame,
    recommendations_frame,
    scan_runs_frame,
    update_recommendation_assignment,
    update_recommendation_status,
)
from costops.data.snowflake_repository import (
    initialize_app_schema,
    persist_analysis_result,
    persist_enterprise_control_plane,
)
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




NATIVE_APP_MODE = os.environ.get("COSTOPS_NATIVE_APP", "0") == "1"


def configure_page():
    page_config = {
        "layout": "wide",
        "initial_sidebar_state": "expanded",
    }
    if not NATIVE_APP_MODE:
        page_config["page_title"] = "GrainAI CostOps"
        page_config["page_icon"] = ""
    try:
        st.set_page_config(**page_config)
    except Exception:
        pass


configure_page()

_BASE_STREAMLIT_DATAFRAME = st.dataframe


def friendly_column_name(name):
    if not isinstance(name, str):
        return name
    parts = [part for part in name.replace("_", " ").split(" ") if part]
    acronym_map = {
        "id": "ID",
        "roi": "ROI",
        "sql": "SQL",
        "usd": "USD",
        "mtd": "MTD",
        "qtd": "QTD",
        "ytd": "YTD",
        "etl": "ETL",
        "bi": "BI",
        "qa": "QA",
        "api": "API",
    }
    display_parts = []
    for part in parts:
        lower = part.lower()
        if lower in acronym_map:
            display_parts.append(acronym_map[lower])
        elif lower.endswith("id") and lower[:-2] in {"recommendation", "baseline", "scan", "event", "object"}:
            display_parts.append(f"{lower[:-2].capitalize()} ID")
        else:
            display_parts.append(part.capitalize())
    return " ".join(display_parts)


def app_dataframe(data=None, **kwargs):
    if isinstance(data, pd.DataFrame):
        renamed = data.copy()
        renamed.columns = [friendly_column_name(column) for column in renamed.columns]
        column_config = kwargs.get("column_config")
        if column_config:
            remapped_config = {}
            for key, value in column_config.items():
                remapped_key = friendly_column_name(key) if isinstance(key, str) else key
                remapped_config[remapped_key] = value
            kwargs["column_config"] = remapped_config
        return _BASE_STREAMLIT_DATAFRAME(renamed, **kwargs)
    return _BASE_STREAMLIT_DATAFRAME(data, **kwargs)


st.dataframe = app_dataframe

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
        font-weight: 700;
        margin: 0.25rem 0 0.2rem 0;
        display: block;
        width: 100%;
        padding: 0.48rem 0.7rem;
        border-radius: 8px;
        background: #fde68a;
        border: 1px solid #f59e0b;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.28);
        color: #78350f;
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
    .workflow-ribbon {
        display: flex;
        gap: 0;
        margin: 0.15rem 0 0.55rem 0;
        overflow: hidden;
        border-radius: 10px;
    }
    .workflow-step {
        position: relative;
        flex: 1 1 0;
        padding: 0.65rem 0.85rem 0.65rem 1.15rem;
        font-size: 0.78rem;
        font-weight: 700;
        color: #475569;
        background: #e5e7eb;
        clip-path: polygon(0 0, calc(100% - 18px) 0, 100% 50%, calc(100% - 18px) 100%, 0 100%, 18px 50%);
        margin-left: -12px;
        white-space: nowrap;
        text-align: center;
    }
    .workflow-step:first-child {
        margin-left: 0;
        clip-path: polygon(0 0, calc(100% - 18px) 0, 100% 50%, calc(100% - 18px) 100%, 0 100%);
        padding-left: 0.85rem;
    }
    .workflow-step.complete {
        background: #d8f3e6;
        color: #0f5132;
    }
    .workflow-step.active {
        background: #ffedd5;
        color: #9a3412;
    }
    .workflow-step.pending {
        background: #e5e7eb;
        color: #64748b;
    }
    .workflow-outcome {
        display: inline-block;
        margin: 0.15rem 0 0.5rem 0;
        padding: 0.22rem 0.55rem;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 700;
        background: #fef3c7;
        color: #92400e;
        border: 1px solid #fcd34d;
    }
    .costops-sidebar-status {
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.75rem;
        background: #111827;
        color: #e5e7eb;
        margin: 0.8rem 0 0.65rem 0;
    }
    .costops-sidebar-status-title {
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.02rem;
        margin-bottom: 0.45rem;
    }
    .costops-sidebar-status-row {
        display: flex;
        justify-content: space-between;
        gap: 0.65rem;
        padding: 0.24rem 0;
        border-top: 1px solid rgba(148, 163, 184, 0.24);
        font-size: 0.76rem;
        line-height: 1.05rem;
    }
    .costops-sidebar-status-row:first-of-type {
        border-top: 0;
    }
    .costops-sidebar-status-label {
        color: #9ca3af;
    }
    .costops-sidebar-status-value {
        color: #f9fafb;
        font-weight: 700;
        text-align: right;
    }
    .costops-plan-pill {
        display: inline-block;
        border-radius: 999px;
        padding: 0.18rem 0.55rem;
        background: #e0f2fe;
        color: #075985;
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }
    .costops-founder-callout {
        border: 1px solid #bae6fd;
        border-left: 5px solid #0284c7;
        border-radius: 8px;
        padding: 0.85rem 1rem;
        background: #f0f9ff;
        margin: 0.75rem 0 1rem 0;
    }
    .costops-founder-title {
        color: #0c4a6e;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    .costops-founder-copy {
        color: #334155;
        font-size: 0.9rem;
        line-height: 1.35rem;
    }
    .costops-usage-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.7rem;
        margin: 0.4rem 0 1rem 0;
    }
    .costops-usage-card {
        border: 1px solid #d7e3f4;
        border-radius: 8px;
        padding: 0.75rem 0.85rem;
        background: #ffffff;
        min-height: 5.2rem;
    }
    .costops-usage-label {
        color: #475569;
        font-size: 0.74rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    .costops-usage-value {
        color: #0f172a;
        font-size: 1.35rem;
        font-weight: 800;
        line-height: 1.7rem;
    }
    .costops-usage-limit {
        color: #475569;
        font-size: 0.78rem;
        line-height: 1.05rem;
        margin-top: 0.25rem;
    }
    .costops-plan-card {
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 0.95rem;
        background: #ffffff;
        min-height: 22.5rem;
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
    }
    .costops-plan-card.current {
        border: 2px solid #1f8a5b;
        background: #f3fbf7;
        box-shadow: 0 10px 24px rgba(31, 138, 91, 0.14);
    }
    .costops-plan-name {
        color: #0f172a;
        font-size: 1.08rem;
        font-weight: 850;
        margin-bottom: 0.15rem;
    }
    .costops-plan-audience {
        color: #334155;
        font-size: 0.8rem;
        min-height: 2.1rem;
        line-height: 1.05rem;
    }
    .costops-plan-price {
        color: #075985;
        font-size: 1.2rem;
        font-weight: 850;
        margin: 0.55rem 0;
    }
    .costops-plan-feature {
        color: #1f2937;
        font-size: 0.8rem;
        line-height: 1.15rem;
        padding: 0.26rem 0;
        border-top: 1px solid #e5e7eb;
    }
    .costops-current-tag {
        display: inline-block;
        color: #166534;
        background: #dcfce7;
        border: 1px solid #86efac;
        border-radius: 999px;
        padding: 0.12rem 0.45rem;
        font-size: 0.7rem;
        font-weight: 800;
        margin-bottom: 0.45rem;
    }
    .costops-entitlement-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.65rem 0 1rem 0;
    }
    .costops-entitlement-card {
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 0.85rem;
        background: #ffffff;
        min-height: 7.25rem;
    }
    .costops-entitlement-card.locked {
        background: #f8fafc;
        border-style: dashed;
    }
    .costops-entitlement-title {
        color: #0f172a;
        font-weight: 800;
        font-size: 0.9rem;
        margin-bottom: 0.25rem;
    }
    .costops-entitlement-copy {
        color: #475569;
        font-size: 0.8rem;
        line-height: 1.15rem;
    }
    .costops-entitlement-state {
        display: inline-block;
        border-radius: 999px;
        padding: 0.12rem 0.45rem;
        font-size: 0.68rem;
        font-weight: 800;
        margin-top: 0.55rem;
        color: #166534;
        background: #dcfce7;
        border: 1px solid #86efac;
    }
    .costops-entitlement-state.locked {
        color: #92400e;
        background: #fef3c7;
        border-color: #fcd34d;
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
    "Recommendation lifecycle",
    "Unresolved opportunity",
    "Owner accountability",
    "Users and roles",
    "Scan ROI history",
    "Enterprise readiness",
    "Enterprise config audit",
]
REPORT_PRESETS = {
    "Comprehensive finance packet": REPORT_SECTION_OPTIONS,
    "Executive ROI summary": [],
    "Savings by team": ["Savings by team", "Unresolved opportunity"],
    "Savings by category": ["Savings by category", "Unresolved opportunity"],
    "Recommendation lifecycle": ["Recommendation lifecycle", "Unresolved opportunity"],
    "Unresolved opportunity": ["Unresolved opportunity", "Owner accountability"],
    "Owner accountability": ["Owner accountability", "Users and roles"],
    "Users and roles": ["Users and roles", "Owner accountability"],
    "Scan ROI history": ["Scan ROI history"],
    "Enterprise readiness": ["Enterprise readiness"],
    "Enterprise config audit trail": ["Enterprise config audit"],
    "Recommendation backlog": [],
    "Recommendation audit trail": [],
    "Custom report": ["Savings by category", "Savings by team", "Recommendation lifecycle", "Users and roles", "Enterprise readiness", "Enterprise config audit"],
}
REPORT_DETAIL_LIMITS = {
    "Summary only": {"backlog": 10, "audit": 10, "section": 10},
    "Standard detail": {"backlog": 40, "audit": 40, "section": 25},
    "Full detail": {"backlog": 200, "audit": 200, "section": 100},
}
ACCESS_ROLES = ["CostOps Admin", "CostOps Operator", "CostOps Viewer"]
ROLE_PERMISSIONS = {
    "CostOps Admin": {"admin", "operate", "assign", "view_sensitive"},
    "CostOps Operator": {"operate", "assign", "view_sensitive"},
    "CostOps Viewer": set(),
}
COSTOPS_PLAN_ORDER = ("Free", "Team", "Business / Pro", "Enterprise")
COSTOPS_PLAN_ENTITLEMENTS = {
    "Free": {
        "price": "$0",
        "audience": "Snowflake cost evaluation",
        "warehouses": "3 warehouses",
        "recommendations": "25 active recommendations",
        "lookback": "30-day lookback",
        "reports": "2 report exports / month",
        "categories": ("Warehouses", "Tasks"),
        "scheduled_scans": "Manual scans",
        "workflow": "Single admin",
        "support": "Community / self-serve",
        "cta": "Current Plan",
        "features": {"basic_workflow", "manual_scans"},
    },
    "Team": {
        "price": "$749 / month",
        "audience": "Small platform teams",
        "warehouses": "15 warehouses",
        "recommendations": "250 active recommendations",
        "lookback": "90-day lookback",
        "reports": "25 report exports / month",
        "categories": ("Warehouses", "Tasks", "Workloads"),
        "scheduled_scans": "Weekly scheduled scans",
        "workflow": "Owners, teams, and due dates",
        "support": "Standard support",
        "cta": "Upgrade Through Marketplace",
        "features": {"basic_workflow", "manual_scans", "team_workflow", "scheduled_scans"},
    },
    "Business / Pro": {
        "price": "$2,499 / month",
        "audience": "FinOps and data platform programs",
        "warehouses": "75 warehouses",
        "recommendations": "Unlimited recommendations",
        "lookback": "365-day lookback",
        "reports": "Unlimited report exports",
        "categories": ("Warehouses", "Tasks", "Workloads", "Storage"),
        "scheduled_scans": "Daily scheduled scans",
        "workflow": "Audit trail and savings realization",
        "support": "Priority support",
        "cta": "Upgrade Through Marketplace",
        "features": {
            "basic_workflow",
            "manual_scans",
            "team_workflow",
            "scheduled_scans",
            "savings_realization",
            "advanced_reports",
        },
    },
    "Enterprise": {
        "price": "$6,000 / month",
        "audience": "One production Snowflake account",
        "warehouses": "Unlimited warehouses in one production account",
        "recommendations": "Unlimited recommendations",
        "lookback": "Custom retention",
        "reports": "Executive and audit packs",
        "categories": ("Warehouses", "Tasks", "Workloads", "Storage", "Custom rules"),
        "scheduled_scans": "Daily production scans plus dev/test validation",
        "workflow": "Dedicated persistence, SSO, RBAC, SLA",
        "support": "Dedicated success path",
        "cta": "Select Enterprise",
        "features": {
            "basic_workflow",
            "manual_scans",
            "team_workflow",
            "scheduled_scans",
            "savings_realization",
            "advanced_reports",
            "enterprise_controls",
            "sso",
            "rbac",
            "dedicated_persistence",
            "sla",
            "linked_dev_test",
        },
    },
}
ENTERPRISE_CONTROL_FEATURES = {
    "sso": {
        "title": "SSO & Identity",
        "copy": "Configure SAML/OIDC metadata, domain allowlists, and identity-provider handoff for enterprise sign-in.",
    },
    "rbac": {
        "title": "RBAC Mapping",
        "copy": "Map Snowflake/application roles to CostOps Admin, Operator, and Viewer permissions.",
    },
    "dedicated_persistence": {
        "title": "Dedicated Persistence",
        "copy": "Track isolated Postgres storage, retention, backup status, and tenant-specific connection health.",
    },
    "sla": {
        "title": "SLA & Support",
        "copy": "Show the active support tier, response window, deployment owner, and escalation path.",
    },
    "linked_dev_test": {
        "title": "Linked Dev/Test",
        "copy": "Register dev and test Snowflake accounts for validating configuration before production rollout.",
    },
    "enterprise_controls": {
        "title": "Production Instance",
        "copy": "Record the production Snowflake account locator, region, account role, and installed app instance.",
    },
}
ENTERPRISE_STATUS_OPTIONS = ["Not configured", "Ready for validation", "Active", "Action needed"]
ENTERPRISE_SUPPORT_TIERS = ["Enterprise standard", "Priority", "Named success manager", "Custom"]
ENTERPRISE_RESPONSE_WINDOWS = ["4 business hours", "Next business day", "24x7 severity 1", "Custom"]


def load_data():
    cache_key = "costops_sample_data_cache"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = load_sample_data()
    return st.session_state[cache_key]


def load_live_warehouse_metering(config, lookback_days, credit_price):
    cache_key = "costops_live_warehouse_metering_cache"
    cache_state = st.session_state.setdefault(cache_key, {})
    cache_token = (
        config.get("account"),
        config.get("user"),
        config.get("warehouse"),
        int(lookback_days),
        float(credit_price),
    )
    cached = cache_state.get("token")
    if cached != cache_token:
        cache_state["token"] = cache_token
        cache_state["data"] = load_warehouse_metering_history(
            config,
            lookback_days=lookback_days,
            credit_price=credit_price,
        )
    return cache_state["data"]


def get_snowflake_config():
    try:
        return dict(st.secrets.get("snowflake", {}))
    except Exception:
        return {}


def current_role_context(settings=None):
    settings = settings or current_app_settings(st.session_state)
    simulation_mode = st.session_state.get("access_simulation_mode", "Manual role")
    source_role = st.session_state.get("current_source_role", "Default fallback")
    manual_role = st.session_state.get("current_access_role", ACCESS_ROLES[0])
    default_role = settings.get("enterprise_default_role", ACCESS_ROLES[0])
    mappings = pd.DataFrame(settings.get("enterprise_role_mappings", []))

    resolved_role = manual_role
    mapping_status = "Manual override"
    mapping_scope = "Direct session role selection."

    if simulation_mode == "Source role mapping":
        if source_role == "Default fallback":
            resolved_role = default_role
            mapping_status = settings.get("enterprise_rbac_status", "Not configured")
            mapping_scope = "Fallback role applied when no explicit mapping exists."
        elif not mappings.empty and source_role in mappings["source_role"].tolist():
            mapped = mappings[mappings["source_role"] == source_role].iloc[0].to_dict()
            resolved_role = mapped.get("costops_role", default_role)
            mapping_status = mapped.get("status", "Not configured")
            mapping_scope = mapped.get("scope", "Mapped application access")
        else:
            resolved_role = default_role
            mapping_status = "Action needed"
            mapping_scope = "Selected source role does not currently map to a saved CostOps role."

    return {
        "simulation_mode": simulation_mode,
        "source_role": source_role,
        "manual_role": manual_role,
        "resolved_role": resolved_role,
        "mapping_status": mapping_status,
        "mapping_scope": mapping_scope,
    }


def has_permission(permission):
    role = current_role_context()["resolved_role"]
    return permission in ROLE_PERMISSIONS.get(role, set())


def permission_message(permission):
    context = current_role_context()
    required_roles = [
        role_name for role_name, permissions in ROLE_PERMISSIONS.items() if permission in permissions
    ]
    return (
        f"{context['resolved_role']} is active for this session. "
        f"{'Source role ' + context['source_role'] + ' resolves to this role. ' if context['simulation_mode'] == 'Source role mapping' else ''}"
        f"This action requires {' or '.join(required_roles)}."
    )


def notify_user(message, level="success"):
    if not NATIVE_APP_MODE and hasattr(st, "toast"):
        try:
            st.toast(message)
            return
        except Exception:
            pass
    fallback = getattr(st, level, st.info)
    fallback(message)


data = load_data()
AS_OF_DATE = pd.Timestamp("2026-05-18")
initialize_app_settings(st.session_state)
initialize_session_store(st.session_state, data["recommendations"], data["recommendation_events"], data["scan_runs"])
initialize_enterprise_audit_store(st.session_state)
st.session_state.setdefault("current_access_role", "CostOps Admin")
st.session_state.setdefault("access_simulation_mode", "Manual role")
st.session_state.setdefault("current_source_role", "Default fallback")
st.session_state.setdefault("data_source_mode", "Sample data")
st.session_state.setdefault("costops_plan_name", "Enterprise")

recommendations = enrich_recommendation_lifecycle(recommendations_frame(st.session_state), AS_OF_DATE)
recommendation_events = recommendation_events_frame(st.session_state)
scan_runs = scan_runs_frame(st.session_state)
warehouses = data["warehouses"]
data_source_status = "Sample data loaded"
data_source_mode = st.session_state.get("data_source_mode", "Sample data")
snowflake_config = get_snowflake_config()
workloads = data["workloads"]
storage = data["storage"]
tasks = data["tasks"]
if data_source_mode == "Snowflake":
    if snowflake_config:
        try:
            warehouses = load_live_warehouse_metering(
                snowflake_config,
                lookback_days=int(current_app_settings(st.session_state)["lookback_days"]),
                credit_price=float(current_app_settings(st.session_state)["credit_price"]),
            )
            data_source_status = "Snowflake warehouse metering loaded"
        except Exception as exc:
            data_source_status = f"Snowflake load failed; using sample data. {exc}"
            warehouses = data["warehouses"]
    else:
        data_source_status = "Snowflake secrets missing; using sample data"
        warehouses = data["warehouses"]

severity_order = ["Critical", "High", "Medium", "Low"]
status_order = ["Proposed", "Selected", "Accepted", "Deferred", "Rejected", "Implemented", "Realized"]
status_options = ["All"] + [status for status in status_order if status in recommendations["status"].unique().tolist()]
category_options = ["All"] + sorted(recommendations["category"].unique().tolist())
owner_options = ["All"] + sorted(recommendations["owner"].unique().tolist())
team_options = ["All"] + sorted(recommendations["team"].unique().tolist())
role_options = ["All"] + sorted(recommendations["role"].unique().tolist())

def scan_schedule_page():
    st.title("Scan & Schedule")
    st.caption("Schedule, run, and review Snowflake environment analysis runs. POC mode uses demo history.")
    render_enterprise_behavior_banner(current_app_settings(st.session_state), "Scan & Schedule")
    scan_control_page_section(current_app_settings(st.session_state)["credit_price"])


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
    settings = current_app_settings(st.session_state)
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
            "Min confidence",
            0.0,
            1.0,
            float(settings["min_confidence"]),
            0.05,
            key=f"{key_prefix}_min_confidence",
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
            "role",
            "due_date",
            "confidence",
            "projected_daily_savings",
            "projected_monthly_savings",
            "missed_savings_to_date",
            "days_lingering",
            "days_to_due",
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
            "days_to_due": st.column_config.NumberColumn("Days to Due", format="%d"),
            "due_date": st.column_config.DateColumn("Due date", format="YYYY-MM-DD"),
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
            <div class="compact-chip">Overdue <strong>{int(df["is_overdue"].sum()) if not df.empty else 0}</strong></div>
            <div class="compact-chip">Realized <strong>{money(df["realized_monthly_savings"].sum())}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workflow_ribbon(status):
    stages = ["Proposed", "Selected", "Accepted", "Implemented", "Realized"]
    fallback_stage = {"Deferred": "Selected", "Rejected": "Accepted"}
    active_stage = fallback_stage.get(status, status if status in stages else "Proposed")
    active_index = stages.index(active_stage)

    parts = ['<div class="workflow-ribbon">']
    for idx, stage in enumerate(stages):
        step_class = "complete" if idx < active_index else "active" if idx == active_index else "pending"
        parts.append(f'<div class="workflow-step {step_class}">{stage}</div>')
    parts.append("</div>")
    if status in {"Deferred", "Rejected"}:
        parts.append(f'<div class="workflow-outcome">Current outcome: {status}</div>')
    return "".join(parts)


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
                <div class="compact-chip">Due <strong>{pd.Timestamp(rec["due_date"]).strftime('%Y-%m-%d')}</strong></div>
            </div>
            <div class="compact-meta">
                {rec["object_name"]} | {rec["category"]} / {rec["subcategory"]} | {rec["owner"]} | {rec["team"]} | {rec["role"]} | {rec["status"]}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write(rec["evidence"])
        with st.container(border=True):
            st.caption("Assignment")
            directory_lookup = user_lookup_map(current_app_settings(st.session_state))
            owner_choices = sorted(directory_lookup.keys())
            owner_profile = directory_lookup.get(rec["owner"], {"team": rec["team"], "role": rec["role"]})
            assignment_cols = st.columns([1.2, 1.0, 1.0, 0.9])
            assigned_owner = assignment_cols[0].selectbox(
                "Owner",
                owner_choices,
                index=owner_choices.index(rec["owner"]),
                key=f"{selected_recommendation_id}_owner",
            )
            selected_profile = directory_lookup.get(assigned_owner, owner_profile)
            assignment_cols[1].text_input(
                "Team",
                value=selected_profile["team"],
                key=f"{selected_recommendation_id}_team",
                disabled=True,
            )
            assignment_cols[2].text_input(
                "Role",
                value=selected_profile["role"],
                key=f"{selected_recommendation_id}_role",
                disabled=True,
            )
            due_date = assignment_cols[3].date_input(
                "Due date",
                value=pd.Timestamp(rec["due_date"]).date(),
                key=f"{selected_recommendation_id}_due_date",
                disabled=not has_permission("assign"),
            )
            notes = st.text_area(
                "Assignment notes",
                value=rec.get("work_notes", ""),
                placeholder="Add handoff context, dependency notes, or owner commitments.",
                height=80,
                key=f"{selected_recommendation_id}_notes",
                disabled=not has_permission("assign"),
            )
            assignment_action_cols = st.columns([1, 2.2])
            if assignment_action_cols[0].button(
                "Assign ownership",
                key=f"{selected_recommendation_id}_save_assignment",
                type="primary",
                disabled=not has_permission("assign"),
            ):
                update_recommendation_assignment(
                    st.session_state,
                    selected_recommendation_id,
                    assigned_owner,
                    due_date,
                    notes,
                    assigned_owner,
                    AS_OF_DATE,
                )
                notify_user(f"{selected_recommendation_id} ownership updated.")
                st.rerun()
            assignment_action_cols[1].caption(
                "Assign the owner, team, role, and due date for this recommendation."
            )
            if not has_permission("assign"):
                st.caption("Viewer access: assignment changes are disabled for this session role.")

        with st.container(border=True):
            st.caption("Workflow stage")
            st.markdown(render_workflow_ribbon(rec["status"]), unsafe_allow_html=True)
            st.caption("Selected means the recommendation is in the active queue. Accepted means the team approved it for implementation.")
            action_cols = st.columns([1, 1, 1, 1, 1.15, 1.15])
            action_labels = [
                ("Select", "Selected"),
                ("Accept", "Accepted"),
                ("Defer", "Deferred"),
                ("Reject", "Rejected"),
                ("Implement", "Implemented"),
                ("Realize", "Realized"),
            ]
            for col, (label, status) in zip(action_cols, action_labels):
                disabled = rec["status"] == status
                if col.button(
                    label,
                    disabled=disabled or not has_permission("operate"),
                    key=f"{selected_recommendation_id}_{status}",
                ):
                    update_recommendation_status(
                        st.session_state,
                        selected_recommendation_id,
                        status,
                        assigned_owner,
                        notes,
                        AS_OF_DATE,
                    )
                    notify_user(f"{selected_recommendation_id} moved to {status}.")
                    st.rerun()
    with right:
        st.caption("Generated SQL or implementation guidance")
        st.code(rec["generated_sql"], language="sql")
        if st.button(
            "Log SQL copied",
            key=f"{selected_recommendation_id}_copy_sql",
            disabled=not has_permission("operate"),
        ):
            log_sql_copied(st.session_state, selected_recommendation_id, assigned_owner, AS_OF_DATE + pd.Timedelta(hours=12))
            notify_user("SQL copy event logged.")
            st.rerun()
        st.caption("Lifecycle")
        lifecycle = pd.DataFrame(
            [
                ("First seen", rec["first_seen_at"].date()),
                ("Due date", pd.Timestamp(rec["due_date"]).date()),
                ("Ownership lane", rec["ownership_lane"]),
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
    st.title("GrainAI CostOps")
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

    if current_costops_plan()[0] == "Enterprise":
        settings = current_app_settings(st.session_state)
        rollup = enterprise_rollup_metrics(settings)
        blockers = enterprise_blockers(settings)
        st.subheader("Enterprise Rollout")
        rollout_cols = st.columns([0.9, 0.9, 0.9, 2.3], gap="small")
        rollout_cols[0].metric("Readiness", f"{rollup['readiness_score']:.0%}")
        rollout_cols[1].metric("Active", int(rollup["status_counts"].get("Active", 0)))
        rollout_cols[2].metric("Action Needed", int(rollup["status_counts"].get("Action needed", 0)))
        with rollout_cols[3]:
            if blockers:
                st.warning("Top blocker: " + blockers[0])
            else:
                st.success("Enterprise rollout has no current blocker flagged in the saved configuration.")

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


def my_work_page():
    st.title("My Work")
    focus_cols = st.columns([0.8, 1.2, 0.9, 0.9, 1.1])
    focus_mode = focus_cols[0].selectbox("View by", ["Owner", "Team", "Role"], index=0)
    if focus_mode == "Owner":
        focus_value = focus_cols[1].selectbox("Owner", sorted(recommendations["owner"].dropna().unique().tolist()))
        my_recs = recommendations[recommendations["owner"] == focus_value]
    elif focus_mode == "Team":
        focus_value = focus_cols[1].selectbox("Team", sorted(recommendations["team"].dropna().unique().tolist()))
        my_recs = recommendations[recommendations["team"] == focus_value]
    else:
        focus_value = focus_cols[1].selectbox("Role", sorted(recommendations["role"].dropna().unique().tolist()))
        my_recs = recommendations[recommendations["role"] == focus_value]
    open_only = focus_cols[2].toggle("Open only", value=True)
    lane = focus_cols[3].selectbox("Lane", ["All", "Overdue", "Due this week", "Assigned", "Closed"], index=0)
    category = focus_cols[4].selectbox("Category", category_options, index=0, key="my_work_category")

    if open_only:
        my_recs = my_recs[my_recs["is_open"]]
    if lane != "All":
        my_recs = my_recs[my_recs["ownership_lane"] == lane]
    if category != "All":
        my_recs = my_recs[my_recs["category"] == category]

    overdue_count = int(my_recs["is_overdue"].sum()) if not my_recs.empty else 0
    due_week = int(((my_recs["is_open"]) & (my_recs["days_to_due"] <= 7) & (my_recs["days_to_due"] >= 0)).sum()) if not my_recs.empty else 0
    open_savings = my_recs.loc[my_recs["is_open"], "projected_monthly_savings"].sum() if not my_recs.empty else 0
    missed = my_recs.loc[my_recs["is_open"], "missed_savings_to_date"].sum() if not my_recs.empty else 0

    cols = st.columns(4)
    cols[0].metric("Owned recommendations", f"{len(my_recs):,}")
    cols[1].metric("Overdue", f"{overdue_count:,}")
    cols[2].metric("Due in 7 days", f"{due_week:,}")
    cols[3].metric("Open monthly savings", money(open_savings), money(missed))

    st.caption(
        f"{focus_mode} view for {focus_value}. Use this page as the working queue for assignments, due dates, and unresolved savings."
    )

    left, right = st.columns([1.15, 1])
    with left:
        lane_summary = my_recs.groupby("ownership_lane", as_index=False).agg(
            recommendations=("recommendation_id", "count"),
            projected_monthly_savings=("projected_monthly_savings", "sum"),
        )
        if lane_summary.empty:
            st.info("No recommendations match the current ownership view.")
        else:
            fig = px.bar(
                lane_summary,
                x="ownership_lane",
                y="projected_monthly_savings",
                color="ownership_lane",
                text="recommendations",
                labels={"ownership_lane": "", "projected_monthly_savings": "Monthly Savings"},
            )
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with right:
        due_queue = my_recs[
            ["recommendation_id", "title", "status", "owner", "team", "role", "due_date", "days_to_due", "missed_savings_to_date"]
        ].sort_values(["days_to_due", "missed_savings_to_date"], ascending=[True, False])
        st.dataframe(
            due_queue,
            use_container_width=True,
            hide_index=True,
            column_config={
                "missed_savings_to_date": st.column_config.NumberColumn("Missed Savings", format="$%d"),
                "days_to_due": st.column_config.NumberColumn("Days to Due", format="%d"),
            },
        )

    st.subheader("Owned Queue")
    selected_recommendation_id = scrolling_recommendation_table(
        my_recs.sort_values(["is_overdue", "missed_savings_to_date"], ascending=[False, False]),
        page_size=20,
        sort_by="missed_savings_to_date",
        ascending=False,
    )
    render_recommendation_detail(my_recs, selected_recommendation_id)


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
        "role",
        "status",
        "due_date",
        "days_to_due",
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
            "days_to_due": st.column_config.NumberColumn("Days to Due", format="%d"),
            "due_date": st.column_config.DateColumn("Due date", format="YYYY-MM-DD"),
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


def enterprise_readiness_frames(settings):
    readiness_summary = pd.DataFrame(
        [
            {
                "area": "RBAC Mapping",
                "status": settings["enterprise_rbac_status"],
                "current_state": settings.get("enterprise_rbac_mode", "Map existing roles"),
                "owner_signal": settings["enterprise_default_role"],
                "notes": f"{len(settings.get('enterprise_role_mappings', []))} role mappings configured",
            },
            {
                "area": "Environments",
                "status": settings["enterprise_linked_environments_status"],
                "current_state": settings["enterprise_prod_account"] or "Production account pending",
                "owner_signal": settings["enterprise_app_instance"] or "App instance pending",
                "notes": f"{len(settings.get('enterprise_linked_environments', []))} linked validation environments",
            },
            {
                "area": "Persistence",
                "status": settings["enterprise_persistence_status"],
                "current_state": settings["enterprise_persistence_target"],
                "owner_signal": settings["enterprise_persistence_isolation"],
                "notes": f"{settings['enterprise_retention']} retention | backup {settings['enterprise_backup_status']}",
            },
            {
                "area": "SSO & Identity",
                "status": settings["enterprise_sso_status"],
                "current_state": settings["enterprise_sso_provider"],
                "owner_signal": settings["enterprise_identity_protocol"],
                "notes": settings["enterprise_allowed_domain"] or "Allowed domain pending",
            },
            {
                "area": "SLA & Support",
                "status": settings["enterprise_sla_status"],
                "current_state": settings["enterprise_support_tier"],
                "owner_signal": settings["enterprise_response_sla"],
                "notes": settings["enterprise_deployment_owner"] or "Deployment owner pending",
            },
        ]
    )
    rbac_report = pd.DataFrame(settings.get("enterprise_role_mappings", []))
    environments_report = pd.DataFrame(settings.get("enterprise_linked_environments", []))
    persistence_report = pd.DataFrame(
        [
            {"area": "Persistence target", "value": settings["enterprise_persistence_target"]},
            {"area": "Isolation model", "value": settings["enterprise_persistence_isolation"]},
            {"area": "Retention", "value": settings["enterprise_retention"]},
            {"area": "Backup status", "value": settings["enterprise_backup_status"]},
            {"area": "Restore readiness", "value": settings["enterprise_restore_test_status"]},
        ]
    )
    identity_report = pd.DataFrame(
        [
            {"area": "SSO provider", "value": settings["enterprise_sso_provider"]},
            {"area": "Identity protocol", "value": settings["enterprise_identity_protocol"]},
            {"area": "Allowed domain", "value": settings["enterprise_allowed_domain"] or "Not configured"},
            {"area": "Metadata URL", "value": settings["enterprise_metadata_url"] or "Not configured"},
            {"area": "Entity ID", "value": settings["enterprise_entity_id"] or "Not configured"},
            {"area": "Implementation contact", "value": settings["enterprise_sso_contact"] or "Not configured"},
        ]
    )
    support_report = pd.DataFrame(
        [
            {"area": "Support tier", "value": settings["enterprise_support_tier"]},
            {"area": "Response window", "value": settings["enterprise_response_sla"]},
            {"area": "Deployment owner", "value": settings["enterprise_deployment_owner"] or "Not configured"},
            {"area": "Escalation path", "value": settings["enterprise_escalation_path"] or "Not configured"},
            {"area": "Support notes", "value": "Captured" if settings["enterprise_support_notes"].strip() else "Not configured"},
        ]
    )
    return readiness_summary, rbac_report, environments_report, persistence_report, identity_report, support_report


def current_demo_actor():
    return f"{st.session_state.get('current_access_role', 'CostOps Admin')} session"


def diff_settings(before, after, tracked_fields):
    changes = []
    for field in tracked_fields:
        before_value = before.get(field)
        after_value = after.get(field)
        before_text = "" if before_value is None else str(before_value)
        after_text = "" if after_value is None else str(after_value)
        if before_text != after_text:
            changes.append((field, before_text or "blank", after_text or "blank"))
    return changes


def log_enterprise_config_change(session_state, area, before, after, tracked_fields, status_field):
    changes = diff_settings(before, after, tracked_fields)
    if not changes:
        return
    fields_changed = ", ".join(field for field, _, _ in changes)
    detail_lines = [f"{field}: {old} -> {new}" for field, old, new in changes[:8]]
    if len(changes) > 8:
        detail_lines.append(f"+ {len(changes) - 8} additional field changes")
    log_enterprise_audit_event(
        session_state,
        area=area,
        change_type="CONFIG_UPDATED",
        actor=current_demo_actor(),
        status=after.get(status_field, "Not configured"),
        fields_changed=fields_changed,
        details="; ".join(detail_lines),
        event_ts=report_timestamp(),
    )


def sync_native_control_plane(settings_snapshot, config=None):
    config = config or snowflake_config
    if not config:
        return False, "No Snowflake secrets found. Add credentials before syncing the native control plane."
    try:
        initialize_app_schema(config)
        persist_enterprise_control_plane(
            config,
            settings_snapshot,
            enterprise_audit_frame(st.session_state),
        )
    except Exception as exc:
        return False, f"Native sync failed: {exc}"
    return True, "Enterprise control-plane settings, user directory, and config audit trail were synced to Snowflake."


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
    lifecycle_report,
    unresolved,
    owner_report,
    directory_report,
    team_coverage_report,
    access_role_report,
    scan_report,
    event_type_report,
    actor_activity_report,
    sql_evidence_report,
    enterprise_readiness_report,
    enterprise_config_audit_report,
    enterprise_config_area_report,
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
    elif report_type == "Recommendation lifecycle" and not lifecycle_report.empty:
        top_status = lifecycle_report.sort_values("projected_monthly_savings", ascending=False).iloc[0]
        highest_missed_status = lifecycle_report.sort_values("missed_savings", ascending=False).iloc[0]
        rows.extend(
            [
                ("Largest lifecycle opportunity", f"{top_status['status']} - {money(top_status['projected_monthly_savings'])}/mo"),
                ("Highest missed-savings stage", f"{highest_missed_status['status']} - {money(highest_missed_status['missed_savings'])} missed"),
                ("Lifecycle stages represented", f"{int(lifecycle_report['recommendations'].gt(0).sum()):,}"),
            ]
        )
        narrative = (
            f"The recommendation lifecycle report shows where savings are getting stuck in the workflow. "
            f"{top_status['status']} holds the largest monthly opportunity at {money(top_status['projected_monthly_savings'])}, "
            f"while {highest_missed_status['status']} carries the highest missed savings at "
            f"{money(highest_missed_status['missed_savings'])}."
        )
    elif report_type == "Users and roles":
        defined_users = int(directory_report["owner"].nunique()) if not directory_report.empty else 0
        defined_teams = int(team_coverage_report["team"].nunique()) if not team_coverage_report.empty else 0
        largest_team = (
            team_coverage_report.sort_values("assigned_users", ascending=False).iloc[0]
            if not team_coverage_report.empty
            else None
        )
        dominant_access = (
            access_role_report.sort_values("users", ascending=False).iloc[0]
            if not access_role_report.empty
            else None
        )
        rows.extend(
            [
                ("Defined users", f"{defined_users:,}"),
                ("Defined teams", f"{defined_teams:,}"),
                (
                    "Largest staffed team",
                    "None"
                    if largest_team is None
                    else f"{largest_team['team']} - {int(largest_team['assigned_users']):,} users",
                ),
                (
                    "Most common access role",
                    "None"
                    if dominant_access is None
                    else f"{dominant_access['access_role']} - {int(dominant_access['users']):,} users",
                ),
            ]
        )
        narrative = (
            f"The users and roles report summarizes ownership coverage behind the recommendation engine. "
            f"The current directory includes {defined_users:,} users across {defined_teams:,} teams. "
            f"{'No teams are staffed yet.' if largest_team is None else f'{largest_team["team"]} is the largest staffed team with {int(largest_team["assigned_users"]):,} users.'}"
        )
    elif report_type == "Recommendation backlog":
        total_recommendations = int(category_report["recommendations"].sum()) if not category_report.empty else 0
        actioned_count = max(total_recommendations - recommendations_open, 0)
        top_backlog = unresolved.iloc[0] if not unresolved.empty else None
        rows.extend(
            [
                ("Backlog rows in scope", f"{len(unresolved):,}"),
                ("Actioned recommendations", f"{actioned_count:,}"),
                ("Realized monthly savings", money(realized_monthly)),
                (
                    "Top unresolved backlog item",
                    "None"
                    if top_backlog is None
                    else f"{top_backlog['recommendation_id']} - {money(top_backlog['missed_savings_to_date'])} missed",
                ),
            ]
        )
        narrative = (
            f"The recommendation backlog report is an operational export of prioritized findings. "
            f"It includes {len(unresolved):,} open recommendations in the current filtered view, "
            f"{actioned_count:,} actioned recommendations, and {money(realized_monthly)} in realized monthly savings. "
            f"It is intended for execution planning rather than executive readout."
        )
    elif report_type == "Recommendation audit trail":
        total_events = int(event_type_report["events"].sum()) if not event_type_report.empty else 0
        distinct_actors = int(actor_activity_report["actor"].nunique()) if not actor_activity_report.empty else 0
        sql_evidence_count = len(sql_evidence_report)
        implemented_events = (
            int(event_type_report.loc[event_type_report["event_type"] == "IMPLEMENTED", "events"].sum())
            if not event_type_report.empty
            else 0
        )
        rows.extend(
            [
                ("Audit events in scope", f"{total_events:,}"),
                ("Distinct actors", f"{distinct_actors:,}"),
                ("SQL / implementation evidence rows", f"{sql_evidence_count:,}"),
                ("Implemented events", f"{implemented_events:,}"),
            ]
        )
        narrative = (
            "The recommendation audit trail report is intended for workflow review, change tracking, and "
            f"implementation evidence. The current filtered view includes {total_events:,} audit events across "
            f"{distinct_actors:,} actors, with {sql_evidence_count:,} SQL or implementation evidence entries."
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
    elif report_type == "Enterprise readiness":
        active_count = int((enterprise_readiness_report["status"] == "Active").sum()) if not enterprise_readiness_report.empty else 0
        action_needed = int((enterprise_readiness_report["status"] == "Action needed").sum()) if not enterprise_readiness_report.empty else 0
        ready_count = int((enterprise_readiness_report["status"] == "Ready for validation").sum()) if not enterprise_readiness_report.empty else 0
        rows.extend(
            [
                ("Enterprise areas tracked", f"{len(enterprise_readiness_report):,}"),
                ("Active enterprise areas", f"{active_count:,}"),
                ("Ready for validation", f"{ready_count:,}"),
                ("Action needed", f"{action_needed:,}"),
            ]
        )
        narrative = (
            f"The enterprise readiness report summarizes administrative rollout posture across "
            f"{len(enterprise_readiness_report):,} enterprise areas. {active_count:,} are active, "
            f"{ready_count:,} are ready for validation, and {action_needed:,} currently need action."
        )
    elif report_type == "Enterprise config audit trail":
        total_events = len(enterprise_config_audit_report)
        active_areas = int(enterprise_config_area_report["area"].nunique()) if not enterprise_config_area_report.empty else 0
        latest_actor = (
            enterprise_config_audit_report.sort_values("event_ts", ascending=False).iloc[0]["actor"]
            if not enterprise_config_audit_report.empty
            else "None"
        )
        rows.extend(
            [
                ("Enterprise config events", f"{total_events:,}"),
                ("Enterprise areas changed", f"{active_areas:,}"),
                ("Most recent actor", str(latest_actor)),
            ]
        )
        narrative = (
            f"The enterprise config audit trail captures {total_events:,} configuration changes across "
            f"{active_areas:,} enterprise areas. It provides an evidence trail for RBAC, environments, "
            f"persistence, identity, and support administration."
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


def pdf_report_frame(df, columns, rename_map=None, limit=None):
    rename_map = rename_map or {}
    available = [column for column in columns if column in df.columns]
    frame = df[available].copy()
    if limit is not None:
        frame = frame.head(limit)
    if rename_map:
        frame = frame.rename(columns=rename_map)
    return frame


def append_totals_row(df, label_column, label, sum_columns):
    if df.empty:
        return df
    totals = {column: "" for column in df.columns}
    totals[label_column] = label
    for column in sum_columns:
        if column in df.columns:
            totals[column] = df[column].fillna(0).sum()
    return pd.concat([df, pd.DataFrame([totals])], ignore_index=True)


def build_excel_report(
    report_type,
    executive_narrative,
    summary_rows,
    enterprise_context_rows,
    category_report,
    team_report,
    lifecycle_report,
    unresolved,
    owner_report,
    directory_report,
    team_coverage_report,
    access_role_report,
    scan_report,
    backlog_export,
    open_backlog_totals,
    actioned_backlog_totals,
    remediated_backlog_totals,
    event_view,
    event_type_report,
    actor_activity_report,
    sql_evidence_report,
    enterprise_readiness_report,
    enterprise_rbac_report,
    enterprise_environments_report,
    enterprise_persistence_report,
    enterprise_identity_report,
    enterprise_support_report,
    enterprise_config_audit_report,
    enterprise_config_area_report,
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
        enterprise_context_rows.to_excel(writer, sheet_name="Executive Summary", index=False, startrow=18)
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
        if "Recommendation lifecycle" in selected_sections:
            lifecycle_report.to_excel(writer, sheet_name="Lifecycle", index=False)
        if "Unresolved opportunity" in selected_sections:
            unresolved.head(limits["section"]).to_excel(writer, sheet_name="Unresolved", index=False)
        if "Owner accountability" in selected_sections:
            owner_report.to_excel(writer, sheet_name="Owner Accountability", index=False)
        if "Users and roles" in selected_sections:
            team_coverage_report.to_excel(writer, sheet_name="Team Coverage", index=False)
            directory_report.to_excel(writer, sheet_name="User Directory", index=False)
            access_role_report.to_excel(writer, sheet_name="Access Roles", index=False)
        if "Scan ROI history" in selected_sections:
            scan_report.to_excel(writer, sheet_name="Scan ROI", index=False)
        if "Enterprise readiness" in selected_sections:
            enterprise_readiness_report.to_excel(writer, sheet_name="Enterprise Ready", index=False)
            enterprise_rbac_report.to_excel(writer, sheet_name="Enterprise RBAC", index=False)
            enterprise_environments_report.to_excel(writer, sheet_name="Enterprise Env", index=False)
            enterprise_persistence_report.to_excel(writer, sheet_name="Enterprise Data", index=False)
            enterprise_identity_report.to_excel(writer, sheet_name="Enterprise SSO", index=False)
            enterprise_support_report.to_excel(writer, sheet_name="Enterprise SLA", index=False)
        if report_type == "Enterprise config audit trail":
            enterprise_config_area_report.to_excel(writer, sheet_name="Config Areas", index=False)
            enterprise_config_audit_report.head(limits["audit"]).to_excel(writer, sheet_name="Config Audit", index=False)
        if report_type == "Recommendation backlog":
            open_backlog_totals.head(limits["backlog"] + 1).to_excel(writer, sheet_name="Open Backlog", index=False)
            actioned_backlog_totals.head(limits["backlog"] + 1).to_excel(writer, sheet_name="Actioned", index=False)
            remediated_backlog_totals.head(limits["backlog"] + 1).to_excel(writer, sheet_name="Remediated", index=False)
        elif report_type == "Recommendation audit trail":
            event_type_report.to_excel(writer, sheet_name="Audit Summary", index=False)
            actor_activity_report.to_excel(writer, sheet_name="Actor Activity", index=False)
            sql_evidence_report.head(limits["audit"]).to_excel(writer, sheet_name="SQL Evidence", index=False)
            event_view.sort_values("event_ts", ascending=False).head(limits["audit"]).to_excel(
                writer, sheet_name="Audit Log", index=False
            )
        else:
            backlog_export.head(min(limits["backlog"], 25)).to_excel(writer, sheet_name="Backlog Snapshot", index=False)
            event_view.sort_values("event_ts", ascending=False).head(min(limits["audit"], 25)).to_excel(
                writer, sheet_name="Audit Snapshot", index=False
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
            "Lifecycle": lifecycle_report,
            "Unresolved": unresolved,
            "Owner Accountability": owner_report,
            "Team Coverage": team_coverage_report,
            "User Directory": directory_report,
            "Access Roles": access_role_report,
            "Scan ROI": scan_report,
            "Backlog": backlog_export,
            "Open Backlog": open_backlog_totals,
            "Actioned": actioned_backlog_totals,
            "Remediated": remediated_backlog_totals,
            "Audit Summary": event_type_report,
            "Actor Activity": actor_activity_report,
            "SQL Evidence": sql_evidence_report,
            "Enterprise Ready": enterprise_readiness_report,
            "Enterprise RBAC": enterprise_rbac_report,
            "Enterprise Env": enterprise_environments_report,
            "Enterprise Data": enterprise_persistence_report,
            "Enterprise SSO": enterprise_identity_report,
            "Enterprise SLA": enterprise_support_report,
            "Config Areas": enterprise_config_area_report,
            "Config Audit": enterprise_config_audit_report,
        }.items():
            if sheet_name not in writer.sheets:
                continue
            worksheet = writer.sheets[sheet_name]
            for idx, column in enumerate(df.columns):
                if column in money_columns:
                    worksheet.set_column(idx, idx, 18, money_fmt)
    output.seek(0)
    return output.getvalue()


def pdf_table(df, money_cols=None, percent_cols=None, limit=20, max_cols=None, available_width=None):
    display = format_export_frame(df, money_cols, percent_cols, limit=limit)
    if max_cols is not None and len(display.columns) > max_cols:
        display = display.iloc[:, :max_cols]
    if available_width is None:
        available_width = landscape(letter)[0] - 48

    col_count = max(len(display.columns), 1)
    if col_count <= 4:
        font_size = 7.5
        min_col_width = 72
    elif col_count <= 7:
        font_size = 6.5
        min_col_width = 62
    elif col_count <= 10:
        font_size = 5.7
        min_col_width = 52
    else:
        font_size = 5.2
        min_col_width = 44

    header_style = ParagraphStyle(
        "ReportTableHeader",
        fontName="Helvetica-Bold",
        fontSize=font_size,
        leading=font_size + 1.3,
        textColor=colors.HexColor("#172033"),
        wordWrap="CJK",
        splitLongWords=True,
    )
    cell_style = ParagraphStyle(
        "ReportTableCell",
        fontName="Helvetica",
        fontSize=font_size,
        leading=font_size + 1.6,
        textColor=colors.HexColor("#172033"),
        wordWrap="CJK",
        splitLongWords=True,
    )

    weight_map = []
    for column in display.columns:
        col_key = str(column).strip().lower()
        weight = 1.0
        if col_key in {"title", "description", "details", "work_notes"}:
            weight = 2.7
        elif col_key in {"recommendation_id", "status", "owner", "team", "role", "category", "subcategory", "event_type", "actor", "access_role"}:
            weight = 1.15
        elif col_key in {"event_ts", "started_at", "completed_at", "generated_at", "due_date", "first_seen_at"}:
            weight = 1.3
        elif "savings" in col_key or "cost" in col_key or "rate" in col_key or "confidence" in col_key:
            weight = 1.05
        elif col_key == "email":
            weight = 1.5

        sample_lengths = [len(str(column))]
        for value in display[column].head(min(len(display), 12)).tolist():
            sample_lengths.append(min(len(str(value)), 80))
        density = max(sample_lengths) if sample_lengths else 12
        if density > 36:
            weight += 0.55
        elif density > 24:
            weight += 0.25
        weight_map.append(weight)

    total_weight = sum(weight_map) or 1
    raw_widths = [(weight / total_weight) * available_width for weight in weight_map]
    col_widths = [max(min_col_width, width) for width in raw_widths]
    width_total = sum(col_widths)
    if width_total > available_width:
        scale = available_width / width_total
        col_widths = [max(34, width * scale) for width in col_widths]

    header_row = [Paragraph(escape(str(column)), header_style) for column in display.columns.tolist()]
    data_rows = []
    for _, row in display.astype(str).iterrows():
        data_rows.append([Paragraph(escape(value), cell_style) for value in row.tolist()])

    rows = [header_row] + data_rows
    table = Table(rows, repeatRows=1, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F1FA")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8DEE9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
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
    enterprise_context_rows,
    category_report,
    team_report,
    lifecycle_report,
    unresolved,
    owner_report,
    directory_report,
    team_coverage_report,
    access_role_report,
    scan_report,
    backlog_export,
    open_backlog_totals,
    actioned_backlog_totals,
    remediated_backlog_totals,
    event_view,
    event_type_report,
    actor_activity_report,
    sql_evidence_report,
    enterprise_readiness_report,
    enterprise_rbac_report,
    enterprise_environments_report,
    enterprise_persistence_report,
    enterprise_identity_report,
    enterprise_support_report,
    enterprise_config_audit_report,
    enterprise_config_area_report,
    selected_sections,
    report_detail,
):
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("PDF export is unavailable in this runtime because ReportLab is not installed.")
    money_columns = report_money_columns()
    limits = REPORT_DETAIL_LIMITS[report_detail]
    rename_map = {
        "recommendation_id": "Rec ID",
        "projected_monthly_savings": "Proj Mo",
        "projected_annual_savings": "Proj Yr",
        "realized_monthly_savings": "Realized Mo",
        "projected_daily_savings": "Daily Save",
        "missed_savings": "Missed",
        "missed_savings_to_date": "Missed",
        "days_lingering": "Days Open",
        "avg_days_open": "Avg Days",
        "open_items": "Open",
        "recommendations": "Recs",
        "assigned_users": "Users",
        "savings_per_scan_dollar": "Save per $1",
        "scan_cost_usd": "Scan Cost",
        "identified_monthly_savings": "Found Mo",
        "recommendations_new": "New",
        "recommendations_updated": "Updated",
        "event_ts": "When",
        "event_type": "Event",
        "access_role": "Access Role",
    }
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
        Spacer(1, 8),
        Paragraph("Enterprise Context", styles["Heading2"]),
        pdf_table(enterprise_context_rows, limit=20, max_cols=2),
    ]

    sections = []
    if "Savings by category" in selected_sections:
        sections.append(
            (
                "Savings by Category",
                pdf_report_frame(
                    category_report.sort_values("projected_monthly_savings", ascending=False),
                    [
                        "category",
                        "recommendations",
                        "open_items",
                        "projected_monthly_savings",
                        "realized_monthly_savings",
                        "missed_savings",
                        "realization_rate",
                    ],
                    rename_map,
                ),
            )
        )
    if "Savings by team" in selected_sections:
        sections.append(
            (
                "Savings by Team",
                pdf_report_frame(
                    team_report.sort_values("missed_savings", ascending=False),
                    [
                        "team",
                        "recommendations",
                        "open_items",
                        "projected_monthly_savings",
                        "realized_monthly_savings",
                        "missed_savings",
                        "realization_rate",
                    ],
                    rename_map,
                ),
            )
        )
    if "Recommendation lifecycle" in selected_sections:
        sections.append(
            (
                "Recommendation Lifecycle",
                pdf_report_frame(
                    lifecycle_report,
                    [
                        "status",
                        "recommendations",
                        "open_items",
                        "projected_monthly_savings",
                        "realized_monthly_savings",
                        "missed_savings",
                        "realization_rate",
                    ],
                    rename_map,
                ),
            )
        )
    if "Unresolved opportunity" in selected_sections:
        sections.append(
            (
                "Unresolved Opportunity",
                pdf_report_frame(
                    unresolved,
                    [
                        "recommendation_id",
                        "category",
                        "owner",
                        "team",
                        "status",
                        "projected_daily_savings",
                        "missed_savings_to_date",
                        "days_lingering",
                    ],
                    rename_map,
                ),
            )
        )
    if "Owner accountability" in selected_sections:
        sections.append(
            (
                "Owner Accountability",
                pdf_report_frame(
                    owner_report.sort_values("missed_savings", ascending=False),
                    [
                        "owner",
                        "team",
                        "recommendations",
                        "open_items",
                        "projected_monthly_savings",
                        "realized_monthly_savings",
                        "missed_savings",
                        "avg_days_open",
                    ],
                    rename_map,
                ),
            )
        )
    if "Scan ROI history" in selected_sections:
        sections.append(
            (
                "Scan ROI History",
                pdf_report_frame(
                    scan_report.sort_values("started_at", ascending=False),
                    [
                        "started_at",
                        "status",
                        "recommendations_new",
                        "recommendations_updated",
                        "scan_cost_usd",
                        "identified_monthly_savings",
                        "savings_per_scan_dollar",
                    ],
                    rename_map,
                ),
            )
        )
    if "Enterprise readiness" in selected_sections:
        sections.append(
            (
                "Enterprise Readiness",
                pdf_report_frame(
                    enterprise_readiness_report,
                    ["area", "status", "current_state", "owner_signal", "notes"],
                    rename_map,
                ),
            )
        )

    include_users_roles = "Users and roles" in selected_sections

    if sections or include_users_roles:
        story.append(PageBreak())

    for title, frame in sections:
        story.extend(
            [
                Paragraph(title, styles["Heading2"]),
                pdf_table(frame, money_columns, ["realization_rate"], limit=limits["section"]),
                Spacer(1, 10),
            ]
        )

    if include_users_roles:
        story.extend(
            [
                Paragraph("Users and Roles", styles["Heading2"]),
                Paragraph("Team Coverage", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        team_coverage_report,
                        [
                            "team",
                            "assigned_users",
                            "recommendations",
                            "open_items",
                            "projected_monthly_savings",
                            "missed_savings",
                            "realization_rate",
                        ],
                        rename_map,
                    ),
                    money_columns,
                    ["realization_rate"],
                    limit=limits["section"],
                ),
                Spacer(1, 8),
                Paragraph("User Directory", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        directory_report,
                        ["owner", "team", "role", "access_role", "email"],
                        rename_map,
                    ),
                    limit=limits["section"],
                    max_cols=5,
                ),
                Spacer(1, 8),
                Paragraph("Access Role Coverage", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(access_role_report, ["access_role", "users"], rename_map),
                    limit=limits["section"],
                    max_cols=2,
                ),
                Spacer(1, 10),
            ]
        )

    if "Enterprise readiness" in selected_sections:
        story.extend(
            [
                Paragraph("Enterprise RBAC Mapping", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        enterprise_rbac_report,
                        ["source_role", "costops_role", "scope", "status"],
                        rename_map,
                    ),
                    limit=limits["section"],
                    max_cols=4,
                ),
                Spacer(1, 8),
                Paragraph("Enterprise Environments", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        enterprise_environments_report,
                        ["environment", "account_locator", "purpose", "status"],
                        rename_map,
                    ),
                    limit=limits["section"],
                    max_cols=4,
                ),
                Spacer(1, 8),
                Paragraph("Persistence, Identity, and Support", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        pd.concat(
                            [
                                enterprise_persistence_report.assign(section="Persistence"),
                                enterprise_identity_report.assign(section="Identity"),
                                enterprise_support_report.assign(section="Support"),
                            ],
                            ignore_index=True,
                        ),
                        ["section", "area", "value"],
                        rename_map,
                    ),
                    limit=limits["section"] * 2,
                    max_cols=3,
                ),
                Spacer(1, 10),
            ]
        )

    if sections or include_users_roles:
        story.append(PageBreak())
    else:
        story.append(Spacer(1, 12))

    if report_type == "Recommendation backlog":
        story.extend(
            [
                Paragraph("Open Recommendation Backlog", styles["Heading2"]),
                pdf_table(
                    pdf_report_frame(
                        open_backlog_totals,
                        [
                            "recommendation_id",
                            "severity",
                            "category",
                            "owner",
                            "status",
                            "projected_monthly_savings",
                            "missed_savings_to_date",
                        "days_lingering",
                    ],
                    rename_map,
                ),
                money_columns,
                    limit=limits["backlog"] + 1,
                ),
                Spacer(1, 8),
                Paragraph("Actioned Recommendations", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        actioned_backlog_totals,
                        [
                            "recommendation_id",
                            "category",
                            "owner",
                            "team",
                            "status",
                            "accepted_at",
                            "implemented_at",
                            "projected_monthly_savings",
                            "realized_monthly_savings",
                        ],
                        rename_map,
                    ),
                    money_columns,
                    limit=limits["backlog"] + 1,
                ),
                Spacer(1, 8),
                Paragraph("Implemented / Realized Recommendations", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        remediated_backlog_totals,
                        [
                            "recommendation_id",
                            "category",
                            "owner",
                            "team",
                            "status",
                            "implemented_at",
                            "projected_monthly_savings",
                            "realized_monthly_savings",
                        ],
                        rename_map,
                    ),
                    money_columns,
                    limit=limits["backlog"] + 1,
                ),
                Spacer(1, 8),
                Paragraph("Recommendation Title Appendix", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        backlog_export,
                        ["recommendation_id", "subcategory", "title"],
                        rename_map,
                    ),
                    limit=min(limits["backlog"], 80),
                    max_cols=3,
                ),
            ]
        )
    elif report_type == "Recommendation audit trail":
        story.extend(
            [
                Paragraph("Audit Event Summary", styles["Heading2"]),
                pdf_table(
                    pdf_report_frame(
                        event_type_report,
                        ["event_type", "events", "recommendations", "actors", "latest_event_ts"],
                        rename_map,
                    ),
                    limit=limits["audit"],
                    max_cols=5,
                ),
                Spacer(1, 8),
                Paragraph("Actor Activity", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        actor_activity_report,
                        ["actor", "events", "recommendations", "sql_copied", "implemented", "latest_event_ts"],
                        rename_map,
                    ),
                    limit=min(limits["audit"], 40),
                    max_cols=6,
                ),
                Spacer(1, 8),
                Paragraph("SQL / Implementation Evidence", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        sql_evidence_report,
                        ["event_ts", "recommendation_id", "event_type", "actor", "details"],
                        rename_map,
                    ),
                    limit=min(limits["audit"], 60),
                    max_cols=5,
                ),
                Spacer(1, 8),
                Paragraph("Audit Log Summary", styles["Heading2"]),
                pdf_table(
                    pdf_report_frame(
                        event_view.sort_values("event_ts", ascending=False),
                        ["event_ts", "recommendation_id", "event_type", "actor", "owner", "team"],
                        rename_map,
                    ),
                    limit=limits["audit"],
                ),
                Spacer(1, 8),
                Paragraph("Audit Detail Appendix", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        event_view.sort_values("event_ts", ascending=False),
                        ["recommendation_id", "title", "details"],
                        rename_map,
                    ),
                    limit=min(limits["audit"], 80),
                    max_cols=3,
                ),
            ]
        )
    elif report_type == "Enterprise config audit trail":
        story.extend(
            [
                Paragraph("Enterprise Config Area Summary", styles["Heading2"]),
                pdf_table(
                    pdf_report_frame(
                        enterprise_config_area_report,
                        ["area", "events", "actors", "latest_event_ts", "latest_status"],
                        rename_map,
                    ),
                    limit=limits["audit"],
                    max_cols=5,
                ),
                Spacer(1, 8),
                Paragraph("Enterprise Config Audit Detail", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        enterprise_config_audit_report.sort_values("event_ts", ascending=False),
                        ["event_ts", "area", "change_type", "actor", "status", "fields_changed", "details"],
                        rename_map,
                    ),
                    limit=min(limits["audit"], 80),
                    max_cols=7,
                ),
            ]
        )
    else:
        story.extend(
            [
                Paragraph("Recommendation Backlog Snapshot", styles["Heading2"]),
                pdf_table(
                    pdf_report_frame(
                        backlog_export,
                        [
                            "recommendation_id",
                            "severity",
                            "category",
                            "owner",
                            "status",
                            "projected_monthly_savings",
                            "missed_savings_to_date",
                        ],
                        rename_map,
                    ),
                    money_columns,
                    limit=min(limits["backlog"], 20),
                ),
                Spacer(1, 8),
                Paragraph("Audit Snapshot", styles["Heading3"]),
                pdf_table(
                    pdf_report_frame(
                        event_view.sort_values("event_ts", ascending=False),
                        ["event_ts", "recommendation_id", "event_type", "actor"],
                        rename_map,
                    ),
                    limit=min(limits["audit"], 20),
                ),
            ]
        )

    story.extend(
        [
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
    enterprise_context_rows,
    roi_bridge,
    category_report,
    team_report,
    lifecycle_report,
    unresolved,
    owner_report,
    directory_report,
    team_coverage_report,
    access_role_report,
    scan_report,
    backlog_export,
    open_backlog_totals,
    actioned_backlog_totals,
    remediated_backlog_totals,
    event_view,
    event_type_report,
    actor_activity_report,
    sql_evidence_report,
    enterprise_readiness_report,
    enterprise_rbac_report,
    enterprise_environments_report,
    enterprise_persistence_report,
    enterprise_identity_report,
    enterprise_support_report,
    enterprise_config_audit_report,
    enterprise_config_area_report,
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

    lifecycle_chart = lifecycle_report.melt(
        "status",
        value_vars=["projected_monthly_savings", "realized_monthly_savings", "missed_savings"],
        var_name="metric",
        value_name="amount",
    )
    lifecycle_fig = px.bar(
        lifecycle_chart,
        x="status",
        y="amount",
        color="metric",
        barmode="group",
        labels={"amount": "USD", "status": ""},
        color_discrete_map=REPORT_METRIC_COLORS,
    )
    lifecycle_fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=30), legend_title_text="", template="plotly_white")

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

    team_coverage_fig = px.bar(
        team_coverage_report.sort_values("assigned_users", ascending=True),
        x="assigned_users",
        y="team",
        color="open_items",
        orientation="h",
        labels={"assigned_users": "Assigned Users", "team": "", "open_items": "Open Items"},
        color_continuous_scale="Blues",
    )
    team_coverage_fig.update_layout(height=390, margin=dict(l=20, r=20, t=30, b=30), template="plotly_white")

    access_role_fig = px.bar(
        access_role_report,
        x="access_role",
        y="users",
        color="access_role",
        labels={"access_role": "", "users": "Users"},
        color_discrete_sequence=REPORT_COLORS,
    )
    access_role_fig.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=30), showlegend=False, template="plotly_white")

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
    lifecycle_section = ""
    unresolved_section = ""
    owner_section = ""
    users_roles_section = ""
    scan_section = ""
    audit_section = ""
    enterprise_section = ""
    enterprise_audit_section = ""

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

    if "Recommendation lifecycle" in selected_sections:
        lifecycle_section = f"""
  <h2>Recommendation Lifecycle</h2>
  {chart_html(lifecycle_fig)}
  {format_report_table(lifecycle_report, money_columns, ["realization_rate"])}
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

    if "Users and roles" in selected_sections:
        users_roles_section = f"""
  <h2>Users and Roles</h2>
  {chart_html(team_coverage_fig)}
  {format_report_table(team_coverage_report.sort_values(['assigned_users', 'missed_savings'], ascending=[False, False]), money_columns)}
  <h3>Access Role Coverage</h3>
  {chart_html(access_role_fig)}
  {format_report_table(access_role_report)}
  <h3>User Directory</h3>
  {format_report_table(directory_report.sort_values(['team', 'owner']))}
"""

    if "Scan ROI history" in selected_sections:
        scan_section = f"""
  <h2>Scan ROI History</h2>
  {chart_html(scan_fig)}
  {format_report_table(scan_report.sort_values("started_at", ascending=False), money_columns)}
"""

    if "Enterprise readiness" in selected_sections:
        enterprise_section = f"""
  <h2>Enterprise Readiness</h2>
  {format_report_table(enterprise_readiness_report)}
  <h3>RBAC Mapping</h3>
  {format_report_table(enterprise_rbac_report)}
  <h3>Environments</h3>
  {format_report_table(enterprise_environments_report)}
  <h3>Persistence</h3>
  {format_report_table(enterprise_persistence_report)}
  <h3>SSO & Identity</h3>
  {format_report_table(enterprise_identity_report)}
  <h3>SLA & Support</h3>
  {format_report_table(enterprise_support_report)}
"""

    if report_type == "Enterprise config audit trail":
        enterprise_audit_section = f"""
  <h2>Enterprise Config Area Summary</h2>
  {format_report_table(enterprise_config_area_report)}
  <h2>Enterprise Config Audit Detail</h2>
  {format_report_table(enterprise_config_audit_report.sort_values("event_ts", ascending=False), limit=limits["audit"])}
"""

    if report_type == "Recommendation audit trail":
        audit_section = f"""
  <h2>Audit Event Summary</h2>
  {format_report_table(event_type_report.sort_values("events", ascending=False))}
  <h2>Actor Activity</h2>
  {format_report_table(actor_activity_report.sort_values("events", ascending=False))}
  <h2>SQL / Implementation Evidence</h2>
  {format_report_table(sql_evidence_report.sort_values("event_ts", ascending=False), limit=limits["audit"])}
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
  <h2>Enterprise Context</h2>
  {format_report_table(enterprise_context_rows)}
  {executive_section}
  {category_section}
  {team_section}
  {lifecycle_section}
  {unresolved_section}
  {owner_section}
  {users_roles_section}
  {scan_section}
  {audit_section}
  {enterprise_section}
  {enterprise_audit_section}
  <h2>{'Open Recommendation Backlog' if report_type == 'Recommendation backlog' else 'Recommendation Backlog Snapshot'}</h2>
  {format_report_table((open_backlog_totals if report_type == 'Recommendation backlog' else backlog_export), money_columns, limit=((limits["backlog"] + 1) if report_type == 'Recommendation backlog' else min(limits["backlog"], 25)))}
  {'<h2>Actioned Recommendations</h2>' + format_report_table(actioned_backlog_totals, money_columns, limit=limits["backlog"] + 1) if report_type == 'Recommendation backlog' else ''}
  {'<h2>Implemented / Realized Recommendations</h2>' + format_report_table(remediated_backlog_totals, money_columns, limit=limits["backlog"] + 1) if report_type == 'Recommendation backlog' else ''}
  <h2>{'Audit Log Evidence' if report_type == 'Recommendation audit trail' else 'Audit Snapshot'}</h2>
  {format_report_table(event_view.sort_values("event_ts", ascending=False), limit=(limits["audit"] if report_type == 'Recommendation audit trail' else min(limits["audit"], 25)))}
  <div class="footer">Downloaded/generated timestamp: {escape(generated_ts)}</div>
</body>
</html>"""


def reports_page():
    settings = current_app_settings(st.session_state)
    st.title("Reports")
    render_enterprise_behavior_banner(settings, "Reports")
    top_cols = st.columns([1.35, 0.95, 1, 1, 1, 1])
    with top_cols[0]:
        report_type = st.selectbox(
            "Report",
            [
                "Comprehensive finance packet",
                "Executive ROI summary",
                "Savings by team",
                "Savings by category",
                "Recommendation lifecycle",
                "Unresolved opportunity",
                "Owner accountability",
                "Users and roles",
                "Scan ROI history",
                "Enterprise readiness",
                "Enterprise config audit trail",
                "Recommendation backlog",
                "Recommendation audit trail",
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
    scan_cost = latest_scan["credits_estimated"] * float(settings["credit_price"]) if latest_scan is not None else 0
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
    lifecycle_report = page_recs.groupby("status", as_index=False).agg(
        recommendations=("recommendation_id", "count"),
        open_items=("is_open", "sum"),
        projected_monthly_savings=("projected_monthly_savings", "sum"),
        projected_annual_savings=("projected_annual_savings", "sum"),
        realized_monthly_savings=("realized_monthly_savings", "sum"),
        missed_savings=("missed_savings_to_date", "sum"),
        avg_days_open=("days_lingering", "mean"),
    )
    lifecycle_report["status"] = pd.Categorical(lifecycle_report["status"], categories=status_order, ordered=True)
    lifecycle_report = lifecycle_report.sort_values("status")
    lifecycle_report["realization_rate"] = (
        lifecycle_report["realized_monthly_savings"] / lifecycle_report["projected_monthly_savings"]
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
    scan_report["scan_cost_usd"] = scan_report["credits_estimated"] * float(settings["credit_price"])
    scan_report["identified_monthly_savings"] = monthly_opportunity
    scan_report["savings_per_scan_dollar"] = scan_report["identified_monthly_savings"] / scan_report["scan_cost_usd"]
    scan_report.loc[scan_report["scan_cost_usd"] == 0, "savings_per_scan_dollar"] = 0
    directory_report = pd.DataFrame(user_directory_frame(settings))
    if directory_report.empty:
        directory_report = pd.DataFrame(columns=["owner", "team", "role", "access_role", "email"])
    else:
        directory_report = directory_report.reindex(columns=["owner", "team", "role", "access_role", "email"]).sort_values(
            ["team", "owner"]
        )
    app_role_options = application_role_catalog(settings)
    team_coverage_report = pd.DataFrame({"team": team_catalog(settings)})
    directory_counts = (
        directory_report.groupby("team", as_index=False).agg(assigned_users=("owner", "count"))
        if not directory_report.empty
        else pd.DataFrame(columns=["team", "assigned_users"])
    )
    team_metrics = team_report[
        [
            "team",
            "recommendations",
            "open_items",
            "projected_monthly_savings",
            "projected_annual_savings",
            "realized_monthly_savings",
            "missed_savings",
            "avg_days_open",
            "realization_rate",
        ]
    ]
    team_coverage_report = team_coverage_report.merge(directory_counts, on="team", how="left").merge(
        team_metrics, on="team", how="left"
    )
    if not directory_report.empty:
        access_matrix = (
            directory_report.assign(user_count=1)
            .pivot_table(index="team", columns="access_role", values="user_count", aggfunc="sum", fill_value=0)
            .reset_index()
        )
        team_coverage_report = team_coverage_report.merge(access_matrix, on="team", how="left")
    for role_name in app_role_options:
        if role_name not in team_coverage_report.columns:
            team_coverage_report[role_name] = 0
    numeric_fill = [
        "assigned_users",
        "recommendations",
        "open_items",
        "projected_monthly_savings",
        "projected_annual_savings",
        "realized_monthly_savings",
        "missed_savings",
        "avg_days_open",
        "realization_rate",
        *app_role_options,
    ]
    for column in numeric_fill:
        if column in team_coverage_report.columns:
            team_coverage_report[column] = team_coverage_report[column].fillna(0)
    access_role_report = (
        directory_report.groupby("access_role", as_index=False).agg(users=("owner", "count"))
        if not directory_report.empty
        else pd.DataFrame({"access_role": app_role_options, "users": [0] * len(app_role_options)})
    )
    if not access_role_report.empty:
        access_role_report["access_role"] = pd.Categorical(
            access_role_report["access_role"], categories=app_role_options, ordered=True
        )
        access_role_report = access_role_report.sort_values("access_role")
    backlog_cols = [
        "recommendation_id",
        "severity",
        "category",
        "subcategory",
        "title",
        "owner",
        "team",
        "status",
        "accepted_at",
        "implemented_at",
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
    open_backlog_report = backlog_export[~backlog_export["status"].isin(["Implemented", "Realized", "Rejected"])].copy()
    actioned_backlog_report = backlog_export[backlog_export["status"].isin(["Accepted", "Implemented", "Realized"])].copy()
    remediated_backlog_report = backlog_export[backlog_export["status"].isin(["Implemented", "Realized"])].copy()

    open_backlog_totals = append_totals_row(
        open_backlog_report[
            [
                "recommendation_id",
                "severity",
                "category",
                "owner",
                "status",
                "projected_monthly_savings",
                "projected_annual_savings",
                "missed_savings_to_date",
                "days_lingering",
            ]
        ],
        "recommendation_id",
        "Totals",
        ["projected_monthly_savings", "projected_annual_savings", "missed_savings_to_date"],
    )
    actioned_backlog_totals = append_totals_row(
        actioned_backlog_report[
            [
                "recommendation_id",
                "category",
                "owner",
                "team",
                "status",
                "accepted_at",
                "implemented_at",
                "projected_monthly_savings",
                "realized_monthly_savings",
            ]
        ],
        "recommendation_id",
        "Totals",
        ["projected_monthly_savings", "realized_monthly_savings"],
    )
    remediated_backlog_totals = append_totals_row(
        remediated_backlog_report[
            [
                "recommendation_id",
                "category",
                "owner",
                "team",
                "status",
                "implemented_at",
                "projected_monthly_savings",
                "realized_monthly_savings",
            ]
        ],
        "recommendation_id",
        "Totals",
        ["projected_monthly_savings", "realized_monthly_savings"],
    )
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
    event_type_report = (
        event_view.groupby("event_type", as_index=False)
        .agg(
            events=("event_id", "count"),
            recommendations=("recommendation_id", "nunique"),
            actors=("actor", "nunique"),
            latest_event_ts=("event_ts", "max"),
        )
        .sort_values("events", ascending=False)
    )
    actor_activity_report = (
        event_view.groupby("actor", as_index=False)
        .agg(
            events=("event_id", "count"),
            recommendations=("recommendation_id", "nunique"),
            sql_copied=("event_type", lambda values: int((values == "SQL_COPIED").sum())),
            implemented=("event_type", lambda values: int(values.isin(["IMPLEMENTED", "REALIZED"]).sum())),
            latest_event_ts=("event_ts", "max"),
        )
        .sort_values(["events", "implemented"], ascending=False)
    )
    sql_evidence_report = event_view[
        event_view["event_type"].isin(["SQL_COPIED", "IMPLEMENTED", "REALIZED", "SAVINGS_CALCULATED"])
    ][["event_ts", "recommendation_id", "event_type", "actor", "details", "owner", "team", "title"]].copy()
    (
        enterprise_readiness_report,
        enterprise_rbac_report,
        enterprise_environments_report,
        enterprise_persistence_report,
        enterprise_identity_report,
        enterprise_support_report,
    ) = enterprise_readiness_frames(settings)
    env_context = enterprise_environment_context(settings)
    enterprise_context_rows = pd.DataFrame(
        [
            ("Production account", env_context["production_account"]),
            ("Production region", env_context["production_region"]),
            ("App instance", env_context["app_instance"]),
            ("Billing scope", env_context["billing_scope"]),
            ("Linked validation environments", env_context["linked_names"]),
            ("Configured validation accounts", f"{env_context['configured_linked_count']}/{env_context['linked_count']}"),
        ],
        columns=["Metric", "Value"],
    )
    enterprise_config_audit_report = enterprise_audit_frame(st.session_state)
    if not enterprise_config_audit_report.empty:
        enterprise_config_area_report = (
            enterprise_config_audit_report.groupby("area", as_index=False)
            .agg(
                events=("event_id", "count"),
                actors=("actor", "nunique"),
                latest_event_ts=("event_ts", "max"),
                latest_status=("status", "last"),
            )
            .sort_values("events", ascending=False)
        )
    else:
        enterprise_config_area_report = pd.DataFrame(
            columns=["area", "events", "actors", "latest_event_ts", "latest_status"]
        )
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
        lifecycle_report,
        unresolved,
        owner_report,
        directory_report,
        team_coverage_report,
        access_role_report,
        scan_report,
        event_type_report,
        actor_activity_report,
        sql_evidence_report,
        enterprise_readiness_report,
        enterprise_config_audit_report,
        enterprise_config_area_report,
    )
    native_export_mode = NATIVE_APP_MODE
    action_cols = st.columns([1.15, 1.12, 1.05, 2.9], gap="small", vertical_alignment="top")
    with action_cols[0]:
        report_detail = st.selectbox(
            "Report detail",
            ["Summary only", "Standard detail", "Full detail"],
            index=2,
        )
        st.markdown('<div class="control-help">Amount of recommendation and audit detail included.</div>', unsafe_allow_html=True)
    with action_cols[1]:
        if native_export_mode:
            download_format = "Disabled"
            st.text_input("Download format", value="On-screen only", disabled=True, label_visibility="visible")
            st.markdown(
                '<div class="control-help">Native mode keeps exports disabled until package delivery and supported dependencies are validated inside Snowflake.</div>',
                unsafe_allow_html=True,
            )
        else:
            download_format = st.radio("Download format", ["PDF", "Excel", "HTML"], horizontal=True, index=0)
            st.markdown('<div class="control-help">Choose the file type for this report.</div>', unsafe_allow_html=True)

    generated_at = report_timestamp()
    download_data = None
    download_extension = ""
    download_mime = ""
    if download_format == "PDF":
        download_data = build_pdf_report(
            report_type,
            period,
            generated_at,
            executive_narrative,
            summary_rows,
            enterprise_context_rows,
            category_report,
            team_report,
            lifecycle_report,
            unresolved,
            owner_report,
            directory_report,
            team_coverage_report,
            access_role_report,
        scan_report,
        backlog_export,
        open_backlog_totals,
        actioned_backlog_totals,
            remediated_backlog_totals,
            event_view,
            event_type_report,
            actor_activity_report,
            sql_evidence_report,
            enterprise_readiness_report,
            enterprise_rbac_report,
            enterprise_environments_report,
            enterprise_persistence_report,
            enterprise_identity_report,
            enterprise_support_report,
            enterprise_config_audit_report,
            enterprise_config_area_report,
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
            enterprise_context_rows,
            category_report,
            team_report,
            lifecycle_report,
            unresolved,
            owner_report,
            directory_report,
            team_coverage_report,
            access_role_report,
        scan_report,
        backlog_export,
        open_backlog_totals,
        actioned_backlog_totals,
            remediated_backlog_totals,
            event_view,
            event_type_report,
            actor_activity_report,
            sql_evidence_report,
            enterprise_readiness_report,
            enterprise_rbac_report,
            enterprise_environments_report,
            enterprise_persistence_report,
            enterprise_identity_report,
            enterprise_support_report,
            enterprise_config_audit_report,
            enterprise_config_area_report,
            selected_sections,
            report_detail,
        )
        download_extension = "xlsx"
        download_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif download_format == "HTML":
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
            enterprise_context_rows,
            roi_bridge,
            category_report,
            team_report,
            lifecycle_report,
            unresolved,
            owner_report,
            directory_report,
            team_coverage_report,
            access_role_report,
        scan_report,
        backlog_export,
        open_backlog_totals,
        actioned_backlog_totals,
            remediated_backlog_totals,
            event_view,
            event_type_report,
            actor_activity_report,
            sql_evidence_report,
            enterprise_readiness_report,
            enterprise_rbac_report,
            enterprise_environments_report,
            enterprise_persistence_report,
            enterprise_identity_report,
            enterprise_support_report,
            enterprise_config_audit_report,
            enterprise_config_area_report,
            selected_sections,
            report_detail,
        )
        download_extension = "html"
        download_mime = "text/html"

    with action_cols[2]:
        st.markdown('<div class="download-spacer"></div>', unsafe_allow_html=True)
        if native_export_mode:
            st.button(
                "Download report",
                disabled=True,
                use_container_width=True,
                type="primary",
            )
        else:
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
    st.subheader("Enterprise Context")
    st.dataframe(enterprise_context_rows, use_container_width=True, hide_index=True)
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

    if "Recommendation lifecycle" in selected_sections:
        st.subheader("Recommendation Lifecycle")
        left, right = st.columns([1.05, 1])
        with left:
            lifecycle_chart = lifecycle_report.melt(
                "status",
                value_vars=["projected_monthly_savings", "realized_monthly_savings", "missed_savings"],
                var_name="metric",
                value_name="amount",
            )
            fig = px.bar(
                lifecycle_chart,
                x="status",
                y="amount",
                color="metric",
                barmode="group",
                labels={"amount": "USD", "status": ""},
            )
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.dataframe(
                lifecycle_report,
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

    if "Users and roles" in selected_sections:
        st.subheader("Users and Roles")
        left, right = st.columns([1.05, 1])
        with left:
            fig = px.bar(
                team_coverage_report.sort_values(["assigned_users", "missed_savings"], ascending=[True, True]),
                x="assigned_users",
                y="team",
                color="open_items",
                orientation="h",
                labels={"assigned_users": "Assigned Users", "team": "", "open_items": "Open Items"},
                color_continuous_scale="Blues",
            )
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        with right:
            fig = px.bar(
                access_role_report,
                x="access_role",
                y="users",
                color="access_role",
                labels={"access_role": "", "users": "Users"},
                color_discrete_sequence=REPORT_COLORS,
            )
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            team_coverage_report.sort_values(["assigned_users", "missed_savings"], ascending=[False, False]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "assigned_users": st.column_config.NumberColumn("Assigned Users", format="%d"),
                "projected_monthly_savings": st.column_config.NumberColumn("Projected Monthly", format="$%d"),
                "projected_annual_savings": st.column_config.NumberColumn("Projected Annual", format="$%d"),
                "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
                "missed_savings": st.column_config.NumberColumn("Missed Savings", format="$%d"),
                "avg_days_open": st.column_config.NumberColumn("Avg Days Open", format="%.1f"),
                "realization_rate": st.column_config.NumberColumn("Realization Rate", format="%.0%"),
            },
        )
        st.dataframe(
            directory_report,
            use_container_width=True,
            hide_index=True,
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

    if report_type == "Recommendation backlog":
        st.subheader("Open Recommendation Backlog")
        st.dataframe(
            open_backlog_totals,
            use_container_width=True,
            hide_index=True,
            column_config={
                "projected_monthly_savings": st.column_config.NumberColumn("Projected Monthly", format="$%d"),
                "projected_annual_savings": st.column_config.NumberColumn("Projected Annual", format="$%d"),
                "missed_savings_to_date": st.column_config.NumberColumn("Missed Savings", format="$%d"),
                "days_lingering": st.column_config.NumberColumn("Days Open", format="%d"),
            },
        )
        st.subheader("Actioned Recommendations")
        st.dataframe(
            actioned_backlog_totals,
            use_container_width=True,
            hide_index=True,
            column_config={
                "accepted_at": st.column_config.DatetimeColumn("Accepted At", format="YYYY-MM-DD"),
                "implemented_at": st.column_config.DatetimeColumn("Implemented At", format="YYYY-MM-DD"),
                "projected_monthly_savings": st.column_config.NumberColumn("Projected Monthly", format="$%d"),
                "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
            },
        )
        st.subheader("Implemented / Realized Recommendations")
        st.dataframe(
            remediated_backlog_totals,
            use_container_width=True,
            hide_index=True,
            column_config={
                "implemented_at": st.column_config.DatetimeColumn("Implemented At", format="YYYY-MM-DD"),
                "projected_monthly_savings": st.column_config.NumberColumn("Projected Monthly", format="$%d"),
                "realized_monthly_savings": st.column_config.NumberColumn("Realized Monthly", format="$%d"),
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
    settings = current_app_settings(st.session_state)
    env_context = enterprise_environment_context(settings)
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

    if current_costops_plan()[0] == "Enterprise":
        env_cols = st.columns([1, 1, 1], gap="small")
        env_cols[0].metric("Production account", env_context["production_account"])
        env_cols[1].metric("App instance", env_context["app_instance"])
        env_cols[2].metric("Linked validation envs", env_context["linked_count"])
        st.caption(
            f"Enterprise scan scope: billable production account {env_context['production_account']} in "
            f"{env_context['production_region']}; linked validation environments: {env_context['linked_names']}."
        )

    left, center, right = st.columns([1.1, 1.1, 1])
    with left:
        schedule = st.selectbox("Schedule", ["Daily", "Weekly", "Monthly", "Off"], index=0)
        preferred_time = st.time_input("Preferred scan time", value=pd.Timestamp("2026-05-18 08:00").time())
    with center:
        scan_scope = st.selectbox("Scan scope", ["Full", "Incremental"], index=0)
        lookback_map = [7, 30, 90, 365]
        lookback_labels = ["7 days", "30 days", "90 days", "All available"]
        lookback_index = lookback_map.index(int(settings["lookback_days"])) if int(settings["lookback_days"]) in lookback_map else 1
        lookback_window = st.selectbox("Lookback window", lookback_labels, index=lookback_index)
    with right:
        st.selectbox("Next scheduled scan", ["2026-05-19 08:00", "2026-05-20 08:00", "Manual only"], index=0)
        run_now = st.button("Run analysis now", type="primary", disabled=not has_permission("operate"))

    lookback_days = {"7 days": 7, "30 days": 30, "90 days": 90, "All available": 365}[lookback_window]
    st.caption(
        "Run analysis now uses the CostOps rule engine against the selected source. In sample mode it regenerates "
        "recommendations from demo warehouse, workload, task, and storage data. In Snowflake mode it attempts to "
        "read account usage metadata, then writes results to the local workflow store and optional Snowflake tables."
    )
    if not has_permission("operate"):
        st.info(permission_message("operate"))

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
                credit_price=float(settings["credit_price"]),
                lookback_days=lookback_days,
                scan_scope=scan_scope,
                initiated_by=actor,
                source_mode=data_source_mode,
                min_confidence=float(settings["min_confidence"]),
                min_monthly_savings=float(settings["min_monthly_savings"]),
                warehouse_monthly_cost_floor=float(settings["warehouse_monthly_cost_floor"]),
                warehouse_utilization_ceiling=float(settings["warehouse_utilization_ceiling"]),
                warehouse_queue_seconds_ceiling=float(settings["warehouse_queue_seconds_ceiling"]),
                warehouse_downsize_savings_pct=float(settings["warehouse_downsize_savings_pct"]),
                auto_suspend_resume_threshold=float(settings["auto_suspend_resume_threshold"]),
                auto_suspend_savings_pct=float(settings["auto_suspend_savings_pct"]),
                workload_scan_gb_threshold=float(settings["workload_scan_gb_threshold"]),
                workload_runtime_seconds_threshold=float(settings["workload_runtime_seconds_threshold"]),
                spill_gb_threshold=float(settings["spill_gb_threshold"]),
                full_refresh_savings_pct=float(settings["full_refresh_savings_pct"]),
                spill_savings_pct=float(settings["spill_savings_pct"]),
                task_executions_7d_threshold=float(settings["task_executions_7d_threshold"]),
                task_failures_7d_threshold=float(settings["task_failures_7d_threshold"]),
                task_schedule_savings_pct=float(settings["task_schedule_savings_pct"]),
                task_failure_savings_pct=float(settings["task_failure_savings_pct"]),
                stale_object_days=float(settings["stale_object_days"]),
                stale_object_access_threshold=float(settings["stale_object_access_threshold"]),
                dev_clone_savings_pct=float(settings["dev_clone_savings_pct"]),
            ),
            as_of_ts=run_ts,
        )
        scan_result["scan_run"]["frequency"] = schedule
        scan_result["scan_run"]["schedule_name"] = f"{schedule} at {preferred_time.strftime('%H:%M')}"
        scan_result["scan_run"]["production_account"] = env_context["production_account"]
        scan_result["scan_run"]["production_region"] = env_context["production_region"]
        scan_result["scan_run"]["app_instance"] = env_context["app_instance"]
        scan_result["scan_run"]["billing_scope"] = env_context["billing_scope"]
        scan_result["scan_run"]["linked_validation_envs"] = env_context["linked_names"]
        scan_result["scan_run"]["environment_scope"] = (
            f"Production: {env_context['production_account']} | Validation: {env_context['linked_names']}"
        )
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
    settings = current_app_settings(st.session_state)
    app_settings = settings
    st.title("Settings")
    st.caption("POC controls for scan configuration, thresholds, and Snowflake Marketplace packaging assumptions.")
    if not has_permission("admin"):
        st.warning(permission_message("admin"))

    st.subheader("Session Controls")
    role_context = current_role_context(settings)
    mapped_source_options = ["Default fallback"]
    mapped_source_options.extend(
        pd.DataFrame(settings.get("enterprise_role_mappings", []))
        .get("source_role", pd.Series(dtype=str))
        .dropna()
        .astype(str)
        .tolist()
    )
    mapped_source_options = list(dict.fromkeys(mapped_source_options))
    session_cols = st.columns(4)
    with session_cols[0]:
        st.selectbox(
            "Session role mode",
            ["Manual role", "Source role mapping"],
            index=["Manual role", "Source role mapping"].index(
                st.session_state.get("access_simulation_mode", "Manual role")
            ),
            key="access_simulation_mode",
            help="Manual role uses the direct CostOps role selector. Source role mapping resolves through the saved RBAC mapping.",
        )
    with session_cols[1]:
        if st.session_state.get("access_simulation_mode", "Manual role") == "Manual role":
            st.selectbox(
                "Access role",
                ACCESS_ROLES,
                index=ACCESS_ROLES.index(st.session_state.get("current_access_role", "CostOps Admin")),
                key="current_access_role",
                help="Local demo selector for testing Admin, Operator, and Viewer permissions.",
            )
        else:
            st.selectbox(
                "Source role",
                mapped_source_options,
                index=mapped_source_options.index(st.session_state.get("current_source_role", "Default fallback"))
                if st.session_state.get("current_source_role", "Default fallback") in mapped_source_options
                else 0,
                key="current_source_role",
                help="Simulate a Snowflake or identity role resolving through the saved RBAC mappings.",
            )
    with session_cols[2]:
        st.text_input("Resolved CostOps role", value=role_context["resolved_role"], disabled=True)
    with session_cols[3]:
        st.selectbox(
            "Data source",
            ["Sample data", "Snowflake"],
            index=["Sample data", "Snowflake"].index(st.session_state.get("data_source_mode", "Sample data")),
            key="data_source_mode",
            help="Use sample data for demos, or Snowflake when secrets are configured.",
        )
    st.caption(
        f"Session context: {role_context['simulation_mode']} | "
        f"Resolved role: {role_context['resolved_role']} | "
        f"Status: {role_context['mapping_status']} | "
        f"Scope: {role_context['mapping_scope']}"
    )

    left, center, right = st.columns(3)
    with left:
        st.subheader("Cost Model")
        credit_price = st.number_input("Credit price USD", min_value=0.0, value=float(settings["credit_price"]), step=0.25)
        lookback_days = st.select_slider("Default lookback days", options=[7, 30, 90, 365], value=int(settings["lookback_days"]), format_func=lambda value: "All available" if value == 365 else f"{value} days")
        annualization_months = st.slider("Annualization months", 1, 12, int(settings["annualization_months"]), 1)
        min_monthly_savings = st.number_input("Minimum monthly savings", min_value=0.0, value=float(settings["min_monthly_savings"]), step=100.0)
        min_confidence_setting = st.slider("Default recommendation confidence", 0.0, 1.0, float(settings["min_confidence"]), 0.05)
    with center:
        st.subheader("Rule Thresholds")
        warehouse_utilization_ceiling = st.number_input("Warehouse utilization ceiling %", min_value=1.0, max_value=100.0, value=float(settings["warehouse_utilization_ceiling"]), step=1.0)
        warehouse_monthly_cost_floor = st.number_input("Warehouse monthly cost floor", min_value=0.0, value=float(settings["warehouse_monthly_cost_floor"]), step=100.0)
        auto_suspend_resume_threshold = st.number_input("Warehouse resume threshold", min_value=1.0, value=float(settings["auto_suspend_resume_threshold"]), step=1.0)
        task_executions_threshold = st.number_input("Task executions threshold (7d)", min_value=1.0, value=float(settings["task_executions_7d_threshold"]), step=10.0)
        task_failures_threshold = st.number_input("Task failures threshold (7d)", min_value=0.0, value=float(settings["task_failures_7d_threshold"]), step=1.0)
    with right:
        st.subheader("Data Thresholds")
        stale_days = st.number_input("Stale object threshold days", min_value=1.0, value=float(settings["stale_object_days"]), step=15.0)
        workload_scan_gb_threshold = st.number_input("Full refresh scan threshold GB", min_value=0.0, value=float(settings["workload_scan_gb_threshold"]), step=100.0)
        workload_runtime_threshold = st.number_input("Full refresh runtime threshold sec", min_value=0.0, value=float(settings["workload_runtime_seconds_threshold"]), step=30.0)
        spill_gb_threshold = st.number_input("Spill threshold GB", min_value=0.0, value=float(settings["spill_gb_threshold"]), step=0.5)
        due_days_critical = st.number_input("Due days critical", min_value=1, value=int(settings["due_days_critical"]), step=1)
        due_days_high = st.number_input("Due days high", min_value=1, value=int(settings["due_days_high"]), step=1)
        due_days_medium = st.number_input("Due days medium", min_value=1, value=int(settings["due_days_medium"]), step=1)
        due_days_low = st.number_input("Due days low", min_value=1, value=int(settings["due_days_low"]), step=1)

    exec_cols = st.columns(3)
    with exec_cols[0]:
        st.toggle("Read-only recommendations", value=True, disabled=not has_permission("admin"))
    with exec_cols[1]:
        st.toggle("Generate implementation SQL", value=True, disabled=not has_permission("admin"))
    with exec_cols[2]:
        st.toggle("Allow approved SQL execution", value=False, disabled=not has_permission("admin"))

    if has_permission("admin"):
        if st.button("Save threshold settings", type="primary"):
            app_settings = persist_app_settings(
                st.session_state,
                {
                    "credit_price": credit_price,
                    "lookback_days": lookback_days,
                    "annualization_months": annualization_months,
                    "min_monthly_savings": min_monthly_savings,
                    "min_confidence": min_confidence_setting,
                    "warehouse_utilization_ceiling": warehouse_utilization_ceiling,
                    "warehouse_monthly_cost_floor": warehouse_monthly_cost_floor,
                    "auto_suspend_resume_threshold": auto_suspend_resume_threshold,
                    "task_executions_7d_threshold": task_executions_threshold,
                    "task_failures_7d_threshold": task_failures_threshold,
                    "stale_object_days": stale_days,
                    "workload_scan_gb_threshold": workload_scan_gb_threshold,
                    "workload_runtime_seconds_threshold": workload_runtime_threshold,
                    "spill_gb_threshold": spill_gb_threshold,
                    "due_days_critical": due_days_critical,
                    "due_days_high": due_days_high,
                    "due_days_medium": due_days_medium,
                    "due_days_low": due_days_low,
                },
            )
            st.success("Threshold settings saved. New scans and default filters will use these values.")

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
        if st.button("Test Snowflake connection", disabled=not has_permission("admin")):
            if not snowflake_config:
                st.error("No Snowflake secrets found. Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml and fill in credentials.")
            else:
                try:
                    result = test_connection(snowflake_config)
                    st.success(f"Connected to {result['account']} in {result['region']} on Snowflake {result['version']}.")
                except Exception as exc:
                    st.error(f"Connection failed: {exc}")
        if st.button("Initialize persistence schema", disabled=not has_permission("admin")):
            if not snowflake_config:
                st.error("No Snowflake secrets found. Add credentials before creating Snowflake objects.")
            else:
                try:
                    initialize_app_schema(snowflake_config)
                    st.success("Core recommendation, scan, event, and savings objects are ready in Snowflake.")
                except Exception as exc:
                    st.error(f"Schema initialization failed: {exc}")
        if st.button("Sync native control plane", disabled=not has_permission("admin")):
            ok, message = sync_native_control_plane(current_app_settings(st.session_state), snowflake_config)
            if ok:
                st.success(message)
            else:
                st.error(message)
    with right_conn:
        st.caption(
            "Live mode can pull warehouse, query, task, and storage account-usage metadata. The persistence schema button creates the "
            "Snowflake tables and workflow procedures that will back recommendation status changes, audit events, "
            "scan history, and savings snapshots."
        )
        st.caption(
            "Phase 1 native sync pushes the saved Enterprise control plane into Snowflake as a config snapshot, "
            "user directory, and enterprise config audit trail so the app has a native system of record to build on."
        )
        st.code(
            "GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION <installed_app_name>;",
            language="sql",
        )
        st.caption(
            "Best practice is to have the consumer ACCOUNTADMIN or delegated installer run this grant explicitly after install "
            "if they approve sharing ACCOUNT_USAGE metadata with the app."
        )

    st.subheader("Persistence Layer")
    persistence_assets = pd.DataFrame(
        [
            ("Core tables", "sql/app/001_core_tables.sql", "Recommendation, event, scan, finding, and savings tables"),
            ("Workflow procedures", "sql/app/002_recommendation_workflow_procedures.sql", "Status updates and SQL-copy audit events"),
            ("Enterprise control plane", "sql/app/003_enterprise_control_plane.sql", "Config snapshot, user directory, enterprise audit log, and readiness view"),
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
            ("Persistence schema", "Phase 1 ready", "Core tables, workflow procedures, and enterprise control-plane tables created under sql/app"),
            ("Analysis runner", "POC ready", "Rules generate recommendations from warehouse, workload, task, and storage metadata"),
            ("Native control-plane sync", "Phase 1 ready", "Sync saved enterprise config, user directory, and enterprise audit trail into Snowflake"),
            ("Scan procedure", "Next", "Move Python runner logic into Snowflake-executable stored procedure/task path"),
            ("Scheduled task", "Not started", "Nightly scan option"),
            ("Marketplace listing", "Not started", "Screenshots, support, security notes"),
            ("Customer install test", "Not started", "Private listing or controlled account"),
        ],
        columns=["Area", "Status", "Next Step"],
    )
    st.dataframe(readiness, use_container_width=True, hide_index=True)

    st.subheader("Marketplace Access Model")
    access_model = pd.DataFrame(
        [
            ("CostOps Admin", "Installer / platform admin", "Install app, approve ACCOUNT_USAGE grant, run scans, configure settings"),
            ("CostOps Operator", "Architect / engineer", "Review recommendations, manage ownership, validate implementation"),
            ("CostOps Viewer", "Leadership / read-only", "View dashboards, reports, and realized savings without making changes"),
        ],
        columns=["Application Role", "Typical User", "Scope"],
    )
    st.dataframe(access_model, use_container_width=True, hide_index=True)

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
        "Credit price": money(app_settings["credit_price"]),
        "Lookback window": f"{app_settings['lookback_days']} days",
        "Minimum monthly savings": money(app_settings["min_monthly_savings"]),
        "Annualization period": f"{app_settings['annualization_months']} months",
        "Warehouse utilization ceiling": f"{app_settings['warehouse_utilization_ceiling']:.0f}%",
        "Task executions threshold": f"{app_settings['task_executions_7d_threshold']:.0f} per 7d",
        "Stale object threshold": f"{app_settings['stale_object_days']:.0f} days",
        "Default confidence": f"{app_settings['min_confidence']:.0%}",
    }
    st.json(assumptions)


def users_roles_page():
    settings = current_app_settings(st.session_state)
    st.title("Users and Roles")
    st.caption("Manage the teams, user directory, business roles, and application access model that drive ownership and workflow routing.")
    if not has_permission("admin"):
        st.warning(permission_message("admin"))

    raw_directory = [dict(entry) for entry in user_directory_frame(settings)]
    directory = pd.DataFrame(raw_directory)

    team_seed = team_catalog(settings)
    business_roles = business_role_catalog(settings)
    app_roles = application_role_catalog(settings)

    st.subheader("Manage Teams")
    team_modes = ["Edit team", "Remove team", "Add team"]
    if st.session_state.get("users_roles_team_mode_version") != 2:
        st.session_state["users_roles_team_mode"] = "Edit team"
        st.session_state["users_roles_team_mode_version"] = 2
    team_action_cols = st.columns([1.35, 0.72, 3.6], gap="small", vertical_alignment="bottom")
    with team_action_cols[0]:
        team_mode = st.segmented_control(
            "Team action",
            team_modes,
            default="Edit team",
            key="users_roles_team_mode",
            label_visibility="collapsed",
            width="stretch",
        )
    with team_action_cols[1]:
        st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
        save_team = st.button("Save", key="save_team", type="primary", use_container_width=True)

    existing_team = ""
    team_name = ""
    if team_mode in {"Edit team", "Remove team"}:
        detail_cols = st.columns([1.1, 1.25, 2.55], gap="small")
        existing_team = detail_cols[0].selectbox(
            "Choose team",
            [""] + team_seed,
            index=0,
            key="users_roles_existing_team",
            label_visibility="collapsed",
        )
        if team_mode == "Edit team":
            team_name = detail_cols[1].text_input(
                "Team name",
                value=existing_team if existing_team else "",
                placeholder="Team name",
                key=f"users_roles_team_name_{team_mode}_{existing_team or 'new'}",
                label_visibility="collapsed",
            )
    else:
        team_name = st.columns([1.15, 3.75], gap="small")[0].text_input(
            "Team name",
            value="",
            placeholder="Team name",
            key="users_roles_team_name_add",
            label_visibility="collapsed",
        )

    if has_permission("admin"):
        if save_team:
            updated_teams = list(team_seed)
            updated_directory = [dict(entry) for entry in raw_directory]
            if team_mode == "Add team":
                if not team_name.strip():
                    st.warning("Enter a team name before saving.")
                elif team_name.strip() in updated_teams:
                    st.warning("That team already exists.")
                else:
                    updated_teams.append(team_name.strip())
                    persist_app_settings(st.session_state, {"teams": sorted(updated_teams)})
                    st.success("Team added.")
                    st.rerun()
            elif team_mode == "Edit team":
                if not existing_team:
                    st.warning("Choose a team to edit.")
                elif not team_name.strip():
                    st.warning("Enter the updated team name.")
                elif existing_team == "Unassigned":
                    st.warning("Unassigned is the fallback team and can't be renamed.")
                else:
                    updated_teams = [team_name.strip() if team == existing_team else team for team in updated_teams]
                    for entry in updated_directory:
                        if entry.get("team") == existing_team:
                            entry["team"] = team_name.strip()
                    persist_app_settings(
                        st.session_state,
                        {"teams": sorted(dict.fromkeys(updated_teams)), "user_directory": updated_directory},
                    )
                    st.success("Team updated.")
                    st.rerun()
            else:
                if not existing_team:
                    st.warning("Choose a team to remove.")
                elif existing_team == "Unassigned":
                    st.warning("Unassigned is the fallback team and can't be removed.")
                else:
                    for entry in updated_directory:
                        if entry.get("team") == existing_team:
                            entry["team"] = "Unassigned"
                    updated_teams = [team for team in updated_teams if team != existing_team]
                    persist_app_settings(
                        st.session_state,
                        {
                            "teams": sorted(dict.fromkeys(["Unassigned", *updated_teams])),
                            "user_directory": updated_directory,
                        },
                    )
                    st.success("Team removed. Assigned users were moved to Unassigned.")
                    st.rerun()

    st.dataframe(pd.DataFrame({"team": team_seed}), use_container_width=True, hide_index=True)

    st.subheader("Manage Users")
    user_modes = ["Add new", "Edit existing", "Remove"]
    user_action_cols = st.columns([1.35, 0.72, 3.6], gap="small", vertical_alignment="bottom")
    with user_action_cols[0]:
        mode = st.segmented_control(
            "Action",
            user_modes,
            default=st.session_state.get("users_roles_mode", user_modes[0]),
            key="users_roles_mode",
            label_visibility="collapsed",
            width="stretch",
        )
    with user_action_cols[1]:
        button_label = "Save" if mode != "Remove" else "Remove"
        button_kind = "primary" if mode != "Remove" else "secondary"
        st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
        save_user = st.button(button_label, type=button_kind, use_container_width=True)

    selected_owner = None
    selected_entry = None
    if mode in {"Edit existing", "Remove"}:
        directory_names = [""] + sorted(directory["owner"].dropna().tolist()) if not directory.empty else [""]
        selected_owner = st.selectbox(
            "Choose user",
            directory_names,
            index=0,
            key="users_roles_selected_owner",
            label_visibility="collapsed",
        )
        if selected_owner:
            selected_entry = next((entry for entry in raw_directory if entry.get("owner") == selected_owner), None)

    owner_value = selected_entry.get("owner", "") if selected_entry else ""
    team_value = selected_entry.get("team", team_seed[0]) if selected_entry else team_seed[0]
    role_value = selected_entry.get("role", "") if selected_entry else ""
    email_value = selected_entry.get("email", "") if selected_entry else ""
    access_role_value = selected_entry.get("access_role", app_roles[-1]) if selected_entry else app_roles[-1]

    admin_cols = st.columns([1.15, 1.0, 1.0, 1.0, 1.2], gap="small")
    user_name = admin_cols[0].text_input(
        "User name",
        value=owner_value,
        placeholder="Enter person name",
        disabled=mode == "Remove",
        key=f"users_roles_name_{mode}_{selected_owner or 'new'}",
        label_visibility="collapsed",
    )
    team_index = team_seed.index(team_value) if team_value in team_seed else 0
    assigned_team = admin_cols[1].selectbox(
        "Assigned team",
        team_seed,
        index=team_index,
        disabled=mode == "Remove",
        key=f"users_roles_team_{mode}_{selected_owner or 'new'}",
        label_visibility="collapsed",
    )
    role_index = business_roles.index(role_value) if role_value in business_roles else 0
    assigned_role = admin_cols[2].selectbox(
        "Business role",
        business_roles,
        index=role_index,
        disabled=mode == "Remove",
        key=f"users_roles_role_{mode}_{selected_owner or 'new'}",
        label_visibility="collapsed",
    )
    access_role_index = app_roles.index(access_role_value) if access_role_value in app_roles else len(app_roles) - 1
    assigned_access_role = admin_cols[3].selectbox(
        "App access role",
        app_roles,
        index=access_role_index,
        disabled=mode == "Remove",
        key=f"users_roles_access_{mode}_{selected_owner or 'new'}",
        label_visibility="collapsed",
    )
    email_address = admin_cols[4].text_input(
        "Email address",
        value=email_value,
        placeholder="name@company.com",
        disabled=mode == "Remove",
        key=f"users_roles_email_{mode}_{selected_owner or 'new'}",
        label_visibility="collapsed",
    )

    if has_permission("admin"):
        if save_user:
            updated_directory = [dict(entry) for entry in raw_directory]
            target_owner = selected_owner if mode in {"Edit existing", "Remove"} else user_name.strip()
            if mode == "Remove":
                if not target_owner:
                    st.warning("Choose a user before removing them.")
                else:
                    updated_directory = [entry for entry in updated_directory if entry.get("owner") != target_owner]
                    st.session_state["users_roles_selected_owner"] = ""
                    persist_app_settings(st.session_state, {"user_directory": updated_directory})
                    st.success("User removed from the directory.")
                    st.rerun()
            else:
                if not user_name.strip():
                    st.warning("Enter a user name before saving.")
                else:
                    payload = {
                        "owner": user_name.strip(),
                        "team": assigned_team,
                        "role": assigned_role,
                        "email": email_address.strip(),
                        "access_role": assigned_access_role,
                    }
                    if mode == "Edit existing" and target_owner:
                        updated_directory = [entry for entry in updated_directory if entry.get("owner") != target_owner]
                    else:
                        updated_directory = [entry for entry in updated_directory if entry.get("owner") != payload["owner"]]
                    updated_directory.append(payload)
                    updated_directory = sorted(updated_directory, key=lambda entry: entry.get("owner", ""))
                    st.session_state["users_roles_selected_owner"] = ""
                    persist_app_settings(st.session_state, {"user_directory": updated_directory})
                    st.success("User directory updated.")
                    st.rerun()
    else:
        st.caption("Viewer and operator roles can review the directory, but only admins can change it.")

    st.subheader("Current Directory")
    directory_view = directory.copy()
    directory_view = directory_view.reindex(columns=["owner", "team", "role", "access_role", "email"])
    st.dataframe(directory_view, use_container_width=True, hide_index=True)

    catalog_cols = st.columns(2, gap="large")
    with catalog_cols[0]:
        st.subheader("Business Role Catalog")
        st.dataframe(pd.DataFrame({"business_role": business_roles}), use_container_width=True, hide_index=True)
    with catalog_cols[1]:
        st.subheader("Application Access Roles")
        st.dataframe(pd.DataFrame({"application_role": app_roles}), use_container_width=True, hide_index=True)

    st.subheader("Access Model")
    access_model = pd.DataFrame(
        [
            ("CostOps Admin", "Installer / platform admin", "Install app, approve ACCOUNT_USAGE grant, manage settings and users"),
            ("CostOps Operator", "Architect / engineer", "Review recommendations, manage ownership, validate implementation"),
            ("CostOps Viewer", "Leadership / read-only", "View dashboards, reports, and realized savings without making changes"),
        ],
        columns=["Application Role", "Typical User", "Scope"],
    )
    st.dataframe(access_model, use_container_width=True, hide_index=True)


def current_costops_plan():
    plan_name = st.session_state.get("costops_plan_name", "Enterprise")
    if plan_name not in COSTOPS_PLAN_ENTITLEMENTS:
        plan_name = "Enterprise"
    return plan_name, COSTOPS_PLAN_ENTITLEMENTS[plan_name]


def current_entitlements():
    _, plan = current_costops_plan()
    return set(plan.get("features", set()))


def has_entitlement(feature_name):
    return feature_name in current_entitlements()


def set_costops_plan(plan_name):
    if plan_name in COSTOPS_PLAN_ENTITLEMENTS:
        st.session_state["costops_plan_name"] = plan_name


def warehouse_observed_count(warehouse_frame):
    if "warehouse" in warehouse_frame.columns:
        return int(warehouse_frame["warehouse"].nunique())
    if "warehouse_name" in warehouse_frame.columns:
        return int(warehouse_frame["warehouse_name"].nunique())
    return int(len(warehouse_frame))


def numeric_plan_limit(limit_text):
    first_token = str(limit_text).split(" ", 1)[0].replace(",", "")
    return int(first_token) if first_token.isdigit() else None


def usage_limit_warnings(plan, warehouse_count, recommendation_count):
    warnings = []
    warehouse_limit = numeric_plan_limit(plan["warehouses"])
    recommendation_limit = numeric_plan_limit(plan["recommendations"])
    if warehouse_limit is not None and warehouse_count > warehouse_limit:
        warnings.append(f"{warehouse_count} warehouses observed exceeds the included {warehouse_limit} warehouses.")
    if recommendation_limit is not None and recommendation_count > recommendation_limit:
        warnings.append(
            f"{recommendation_count} active recommendations observed exceeds the included {recommendation_limit} recommendations."
        )
    return warnings


def render_sidebar_plan_status(recommendation_count, warehouse_count):
    plan_name, plan = current_costops_plan()
    role_context = current_role_context()
    category_text = ", ".join(plan["categories"])
    st.markdown(
        f"""
        <div class="costops-sidebar-status">
            <div class="costops-sidebar-status-title">Current Plan</div>
            <div class="costops-sidebar-status-row">
                <span class="costops-sidebar-status-label">Plan</span>
                <span class="costops-sidebar-status-value">{escape(plan_name)}</span>
            </div>
            <div class="costops-sidebar-status-row">
                <span class="costops-sidebar-status-label">Warehouses</span>
                <span class="costops-sidebar-status-value">{warehouse_count} / {escape(plan["warehouses"])}</span>
            </div>
            <div class="costops-sidebar-status-row">
                <span class="costops-sidebar-status-label">Recommendations</span>
                <span class="costops-sidebar-status-value">{recommendation_count} / {escape(plan["recommendations"])}</span>
            </div>
            <div class="costops-sidebar-status-row">
                <span class="costops-sidebar-status-label">Coverage</span>
                <span class="costops-sidebar-status-value">{escape(category_text)}</span>
            </div>
            <div class="costops-sidebar-status-row">
                <span class="costops-sidebar-status-label">Scan cadence</span>
                <span class="costops-sidebar-status-value">{escape(plan["scheduled_scans"])}</span>
            </div>
            <div class="costops-sidebar-status-row">
                <span class="costops-sidebar-status-label">Resolved role</span>
                <span class="costops-sidebar-status-value">{escape(role_context["resolved_role"])}</span>
            </div>
            <div class="costops-sidebar-status-row">
                <span class="costops-sidebar-status-label">Session mode</span>
                <span class="costops-sidebar-status-value">{escape(role_context["simulation_mode"])}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def upgrade_plan_page():
    plan_name, active_plan = current_costops_plan()
    recommendation_count = int(recommendations["recommendation_id"].nunique())
    warehouse_count = warehouse_observed_count(warehouses)
    active_categories = ", ".join(active_plan["categories"])

    st.title("Upgrade Plan")
    st.caption(
        "Choose the CostOps tier for the Snowflake estate you want to monitor. "
        "Paid plans are scoped to a production Snowflake account. Dev and test "
        "validation environments can be linked to that production account for rollout testing."
    )

    st.subheader("Current Usage")
    st.markdown(
        f"""
        <div class="costops-usage-grid">
            <div class="costops-usage-card">
                <div class="costops-usage-label">Current plan</div>
                <div class="costops-usage-value">{escape(plan_name)}</div>
                <div class="costops-usage-limit">Price: {escape(active_plan["price"])}</div>
            </div>
            <div class="costops-usage-card">
                <div class="costops-usage-label">Warehouses observed</div>
                <div class="costops-usage-value">{warehouse_count:,}</div>
                <div class="costops-usage-limit">Included: {escape(active_plan["warehouses"])}</div>
            </div>
            <div class="costops-usage-card">
                <div class="costops-usage-label">Recommendations observed</div>
                <div class="costops-usage-value">{recommendation_count:,}</div>
                <div class="costops-usage-limit">Included: {escape(active_plan["recommendations"])}</div>
            </div>
            <div class="costops-usage-card">
                <div class="costops-usage-label">Coverage included</div>
                <div class="costops-usage-value">{len(active_plan["categories"])} categories</div>
                <div class="costops-usage-limit">{escape(active_categories)} | {escape(active_plan["lookback"])}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for warning in usage_limit_warnings(active_plan, warehouse_count, recommendation_count):
        st.warning(
            warning
            + " Existing history is preserved, but new scans should be reduced in scope or upgraded before production use."
        )

    st.markdown(
        """
        <div class="costops-founder-callout">
            <div class="costops-founder-title">CostOps upgrade path and billing unit</div>
            <div class="costops-founder-copy">
                Free focuses on the two most common cost-control areas: warehouse sizing and task hygiene.
                Team adds workload analysis and weekly scans. Business / Pro unlocks storage, daily scans,
                unlimited reporting, and savings realization. Enterprise is $6,000 per month for one
                production Snowflake account, with dedicated persistence, SSO, RBAC, SLA, and linked
                dev/test validation for safe rollout. Separate production Snowflake accounts require
                separate CostOps instances unless covered by a suite enterprise agreement.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Choose A Plan")
    plan_columns = st.columns(len(COSTOPS_PLAN_ORDER))
    for index, candidate_name in enumerate(COSTOPS_PLAN_ORDER):
        with plan_columns[index]:
            _render_costops_plan_card(candidate_name, plan_name)

    _render_costops_marketplace_workflow()


def _render_costops_plan_card(candidate_name, active_plan_name):
    plan = COSTOPS_PLAN_ENTITLEMENTS[candidate_name]
    is_current = candidate_name == active_plan_name
    card_class = "costops-plan-card current" if is_current else "costops-plan-card"
    current_tag = '<div class="costops-current-tag">Current plan</div>' if is_current else ""
    card_html = (
        f'<div class="{card_class}">'
        f'{current_tag}'
        f'<div class="costops-plan-name">{escape(candidate_name)}</div>'
        f'<div class="costops-plan-audience">{escape(plan["audience"])}</div>'
        f'<div class="costops-plan-price">{escape(plan["price"])}</div>'
        f'<div class="costops-plan-feature">{escape(plan["warehouses"])}</div>'
        f'<div class="costops-plan-feature">{escape(plan["recommendations"])}</div>'
        f'<div class="costops-plan-feature">{escape(plan["lookback"])}</div>'
        f'<div class="costops-plan-feature">{escape(plan["reports"])}</div>'
        f'<div class="costops-plan-feature">Coverage: {escape(", ".join(plan["categories"]))}</div>'
        f'<div class="costops-plan-feature">{escape(plan["scheduled_scans"])}</div>'
        f'<div class="costops-plan-feature">{escape(plan["workflow"])}</div>'
        f'<div class="costops-plan-feature">{escape(plan["support"])}</div>'
        "</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)

    if is_current:
        st.button("Current Plan", disabled=True, width="stretch", key=f"current_{candidate_name}")
        return

    if st.button(plan["cta"], width="stretch", key=f"select_plan_{candidate_name}"):
        set_costops_plan(candidate_name)
        if candidate_name == "Enterprise":
            st.success("Enterprise selected for this demo session at $6,000/month per production Snowflake account.")
        else:
            st.success(f"{candidate_name} selected for this demo session.")
        st.rerun()


def _render_costops_marketplace_workflow():
    st.subheader("Marketplace Upgrade Workflow")
    st.markdown(
        """
        1. A user reaches a CostOps limit or wants broader scan coverage.
        2. CostOps shows the plan comparison and recommended upgrade path.
        3. An admin upgrades through Snowflake Marketplace for one production Snowflake account.
        4. Snowflake handles subscription, billing, invoice, or offer acceptance.
        5. CostOps receives the updated entitlement and keeps the same workspace history.
        6. Dev and test accounts can validate configuration changes before production rollout.
        7. Separate production accounts are billed as separate CostOps instances unless covered by a suite enterprise agreement.
        """
    )


def _enterprise_badge(status):
    tone_map = {
        "Not configured": ("#e5e7eb", "#475569"),
        "Ready for validation": ("#dbeafe", "#1d4ed8"),
        "Active": ("#dcfce7", "#166534"),
        "Action needed": ("#fef3c7", "#92400e"),
    }
    background, text = tone_map.get(status, ("#e5e7eb", "#334155"))
    return (
        f'<span style="display:inline-block;border-radius:999px;padding:0.14rem 0.48rem;'
        f'background:{background};color:{text};font-size:0.72rem;font-weight:800;">{escape(status)}</span>'
    )


def _enterprise_overview_cards(items):
    cards = []
    for title, status, copy in items:
        cards.append(
            "<div class='costops-entitlement-card'>"
            f"<div class='costops-entitlement-title'>{escape(title)}</div>"
            f"<div class='costops-entitlement-copy'>{escape(copy)}</div>"
            f"{_enterprise_badge(status)}"
            "</div>"
        )
    st.markdown("<div class='costops-entitlement-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def _enterprise_locked_message(plan_name, feature_label):
    st.warning(
        f"{feature_label} is locked on the {plan_name} plan. Upgrade to Enterprise to configure this surface."
    )
    st.link_button("Review Enterprise Plan", "/upgrade_plan", type="primary")


def enterprise_control_rows(settings):
    return [
        {
            "area": "Production Instance",
            "status": settings["enterprise_production_status"],
            "current_state": settings["enterprise_prod_account"] or "Production account pending",
            "next_step": "Define the production Snowflake account and installed app instance.",
        },
        {
            "area": "RBAC Mapping",
            "status": settings["enterprise_rbac_status"],
            "current_state": settings.get("enterprise_rbac_mode", "Map existing roles"),
            "next_step": "Confirm source-role mapping coverage for Admin, Operator, and Viewer.",
        },
        {
            "area": "Linked Dev/Test",
            "status": settings["enterprise_linked_environments_status"],
            "current_state": f"{len(settings.get('enterprise_linked_environments', []))} validation environments",
            "next_step": "Link dev/test validation accounts and confirm their purpose.",
        },
        {
            "area": "Dedicated Persistence",
            "status": settings["enterprise_persistence_status"],
            "current_state": settings["enterprise_persistence_target"],
            "next_step": "Validate isolation, retention, backup cadence, and restore readiness.",
        },
        {
            "area": "SSO & Identity",
            "status": settings["enterprise_sso_status"],
            "current_state": settings["enterprise_sso_provider"],
            "next_step": "Capture provider metadata, domain rules, and implementation contact.",
        },
        {
            "area": "SLA & Support",
            "status": settings["enterprise_sla_status"],
            "current_state": settings["enterprise_support_tier"],
            "next_step": "Assign deployment owner and escalation path.",
        },
    ]


def enterprise_environment_context(settings):
    linked = settings.get("enterprise_linked_environments", []) or []
    configured_linked = [entry for entry in linked if str(entry.get("account_locator", "")).strip()]
    return {
        "production_account": settings.get("enterprise_prod_account", "") or "Not configured",
        "production_region": settings.get("enterprise_prod_region", "") or "Not configured",
        "app_instance": settings.get("enterprise_app_instance", "") or "Not configured",
        "billing_scope": settings.get("enterprise_billing_scope", "") or "Not configured",
        "linked_count": len(linked),
        "configured_linked_count": len(configured_linked),
        "linked_names": ", ".join(entry.get("environment", "") for entry in linked if entry.get("environment")) or "None",
    }


def enterprise_rollup_metrics(settings):
    rows = enterprise_control_rows(settings)
    status_counts = pd.Series([row["status"] for row in rows]).value_counts()
    weights = {
        "Not configured": 0.0,
        "Action needed": 0.25,
        "Ready for validation": 0.7,
        "Active": 1.0,
    }
    score = 0.0
    if rows:
        score = sum(weights.get(row["status"], 0.0) for row in rows) / len(rows)
    return {
        "rows": rows,
        "status_counts": status_counts.to_dict(),
        "readiness_score": score,
    }


def enterprise_blockers(settings):
    blockers = []
    if not settings["enterprise_prod_account"]:
        blockers.append("Production Snowflake account is not defined yet.")
    if settings["enterprise_rbac_status"] == "Not configured":
        blockers.append("RBAC mappings have not been established.")
    if settings["enterprise_sso_status"] == "Action needed":
        blockers.append("SSO & Identity needs follow-up before rollout.")
    if settings["enterprise_persistence_status"] in {"Not configured", "Action needed"}:
        blockers.append("Dedicated persistence is not ready for rollout validation.")
    if not settings["enterprise_deployment_owner"]:
        blockers.append("SLA & Support does not have a deployment owner assigned.")
    return blockers


def render_enterprise_behavior_banner(settings, location_label):
    plan_name, _ = current_costops_plan()
    if plan_name != "Enterprise":
        return

    blockers = enterprise_blockers(settings)
    prod_account = settings["enterprise_prod_account"] or "Not configured"
    if location_label == "Scan & Schedule":
        if blockers:
            st.warning(
                f"Enterprise scan context is not fully ready. Production account: {prod_account}. "
                f"Top blocker: {blockers[0]}"
            )
        else:
            st.success(
                f"Enterprise scan context is anchored to production account {prod_account} with "
                f"{len(settings.get('enterprise_linked_environments', []))} linked validation environments."
            )
    elif location_label == "Reports":
        if blockers:
            st.info(
                f"Enterprise rollout is still in progress for reporting context. Production account: {prod_account}. "
                f"{len(blockers)} blocker(s) remain."
            )
        else:
            st.success(
                f"Enterprise reporting context is ready for production account {prod_account}. "
                "Readiness and config audit reports are available for export."
            )


def _rbac_permission_catalog():
    return [
        ("admin", "Admin controls", "Manage enterprise configuration, persistence, and settings."),
        ("operate", "Workflow actions", "Run scans, update recommendation stages, and manage execution workflow."),
        ("assign", "Assignment updates", "Assign ownership, due dates, and operating responsibility."),
        ("view_sensitive", "Sensitive views", "See financial detail, audit history, and sensitive reporting surfaces."),
    ]


def _rbac_permission_summary(role_name):
    permissions = ROLE_PERMISSIONS.get(role_name, set())
    rows = []
    for permission_key, label, description in _rbac_permission_catalog():
        rows.append(
            {
                "Capability": label,
                "Allowed": "Yes" if permission_key in permissions else "No",
                "Description": description,
            }
        )
    return pd.DataFrame(rows)


def _rbac_starter_roles():
    return [
        {
            "source_role": "COSTOPS_ADMIN",
            "costops_role": "CostOps Admin",
            "scope": "Enterprise administration and privileged configuration",
        },
        {
            "source_role": "COSTOPS_OPERATOR",
            "costops_role": "CostOps Operator",
            "scope": "Recommendation workflow, scans, and day-to-day operations",
        },
        {
            "source_role": "COSTOPS_VIEWER",
            "costops_role": "CostOps Viewer",
            "scope": "Read-only dashboards, reports, and audit visibility",
        },
    ]


def _rbac_suggested_source_roles(existing_roles=None):
    existing_roles = existing_roles or []
    seeded = [
        "SNOWFLAKE_COSTOPS_ADMIN",
        "SNOWFLAKE_COSTOPS_OPERATOR",
        "SNOWFLAKE_COSTOPS_VIEWER",
        "COSTOPS_ADMIN",
        "COSTOPS_OPERATOR",
        "COSTOPS_VIEWER",
        *existing_roles,
    ]
    return list(dict.fromkeys([role for role in seeded if role]))


def enterprise_controls_page():
    settings = current_app_settings(st.session_state)
    plan_name, plan = current_costops_plan()
    enterprise_unlocked = has_entitlement("enterprise_controls")

    st.title("Enterprise Controls")
    st.caption(
        "Enterprise-only controls for identity, role mapping, dedicated persistence, "
        "support commitments, and production-instance governance."
    )

    if not enterprise_unlocked:
        _enterprise_locked_message(plan_name, "Enterprise Controls")
        st.subheader("Enterprise Feature Status")
        _render_enterprise_feature_grid(locked=True)
        return

    st.success(
        f"Enterprise is active at {plan['price']} for one production Snowflake account. "
        "The controls below represent the enterprise configuration surface."
    )
    st.info(
        "Demo note: these controls model the Enterprise workflow. Full SSO, persistence provisioning, "
        "and marketplace entitlement sync still need production integrations."
    )

    sync_cols = st.columns([1.1, 2.3], gap="small", vertical_alignment="bottom")
    with sync_cols[0]:
        sync_now = st.button("Sync native control plane", type="primary", disabled=not has_permission("admin"), width="stretch")
    with sync_cols[1]:
        st.caption(
            "Phase 1 native sync writes the current enterprise settings, user directory, and enterprise config audit log "
            "into Snowflake so the control plane starts living natively with the customer account."
        )
    if sync_now:
        ok, message = sync_native_control_plane(settings, snowflake_config)
        if ok:
            st.success(message)
        else:
            st.error(message)

    rollup = enterprise_rollup_metrics(settings)
    blockers = enterprise_blockers(settings)
    recent_audit = enterprise_audit_frame(st.session_state).sort_values("event_ts", ascending=False)
    rollup_cols = st.columns(4, gap="small")
    rollup_cols[0].metric("Enterprise readiness", f"{rollup['readiness_score']:.0%}")
    rollup_cols[1].metric("Active areas", int(rollup["status_counts"].get("Active", 0)))
    rollup_cols[2].metric("Ready for validation", int(rollup["status_counts"].get("Ready for validation", 0)))
    rollup_cols[3].metric("Action needed", int(rollup["status_counts"].get("Action needed", 0)))

    if blockers:
        st.warning("Current rollout blockers: " + " | ".join(blockers[:3]))
    else:
        st.success("No current enterprise rollout blockers are flagged in the saved configuration state.")

    st.subheader("Enterprise Feature Status")
    _render_enterprise_feature_grid(locked=False)
    _enterprise_overview_cards(
        [
            (
                "Production Instance",
                settings["enterprise_production_status"],
                settings["enterprise_prod_account"] or "Define the production Snowflake account and installed app instance.",
            ),
            (
                "RBAC Mapping",
                settings["enterprise_rbac_status"],
                f"Default role: {settings['enterprise_default_role']}. Maintain Admin, Operator, and Viewer mappings.",
            ),
            (
                "Linked Dev/Test",
                settings["enterprise_linked_environments_status"],
                "Track validation environments before production rollout.",
            ),
            (
                "Dedicated Persistence",
                settings["enterprise_persistence_status"],
                f"{settings['enterprise_persistence_target']} | {settings['enterprise_retention']} retention",
            ),
            (
                "SSO & Identity",
                settings["enterprise_sso_status"],
                f"{settings['enterprise_sso_provider']} | {settings['enterprise_identity_protocol']}",
            ),
            (
                "SLA & Support",
                settings["enterprise_sla_status"],
                f"{settings['enterprise_support_tier']} | {settings['enterprise_response_sla']}",
            ),
        ]
    )

    st.subheader("Readiness Rollup")
    st.dataframe(
        pd.DataFrame(rollup["rows"]).rename(
            columns={
                "area": "Area",
                "status": "Status",
                "current_state": "Current State",
                "next_step": "Next Step",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    if not recent_audit.empty:
        st.subheader("Recent Enterprise Config Changes")
        st.dataframe(
            recent_audit[
                ["event_ts", "area", "actor", "status", "fields_changed", "details"]
            ].head(8),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.subheader("Recent Enterprise Config Changes")
        st.caption("No enterprise config changes have been logged yet. Save an enterprise admin page to start the audit trail.")

    st.subheader("Implementation Scope")
    st.dataframe(
        pd.DataFrame(
            [
                ("Enterprise Controls", "Overview dashboard", "Live"),
                ("RBAC Mapping", "Role-to-role mapping with status tracking", "Ready"),
                ("Environments", "Production instance plus linked dev/test", "Ready"),
                ("Persistence", "Dedicated persistence operating model", "Ready"),
                ("SSO & Identity", "Metadata capture and readiness tracking", "Ready"),
                ("SLA & Support", "Support tier and escalation ownership", "Ready"),
            ],
            columns=["Area", "Purpose", "Current State"],
        ),
        use_container_width=True,
        hide_index=True,
    )


def rbac_mapping_page():
    settings = current_app_settings(st.session_state)
    plan_name, _ = current_costops_plan()
    unlocked = has_entitlement("rbac")
    editable = unlocked and has_permission("admin")

    st.title("RBAC Mapping")
    st.caption("Map Snowflake or application roles to CostOps Admin, Operator, and Viewer responsibilities.")
    if not unlocked:
        _enterprise_locked_message(plan_name, "RBAC Mapping")
    elif not has_permission("admin"):
        st.info("RBAC Mapping is visible in read-only mode for this session role.")

    mappings = pd.DataFrame(settings.get("enterprise_role_mappings", []))
    if mappings.empty:
        mappings = pd.DataFrame(columns=["source_role", "costops_role", "scope", "status"])

    mapped_roles = {value for value in mappings.get("costops_role", pd.Series(dtype=str)).tolist() if value}
    active_mappings = int((mappings["status"] == "Active").sum()) if "status" in mappings else 0
    ready_mappings = int((mappings["status"] == "Ready for validation").sum()) if "status" in mappings else 0
    summary_cols = st.columns(4, gap="small")
    summary_cols[0].metric("Mapped source roles", f"{len(mappings)}")
    summary_cols[1].metric("CostOps role coverage", f"{len(mapped_roles)}/{len(ACCESS_ROLES)}")
    summary_cols[2].metric("Active mappings", f"{active_mappings}")
    summary_cols[3].metric("Ready for validation", f"{ready_mappings}")

    mapping_cols = st.columns([1, 1, 1.1], gap="small")
    rbac_status = mapping_cols[0].selectbox(
        "Status",
        ENTERPRISE_STATUS_OPTIONS,
        index=ENTERPRISE_STATUS_OPTIONS.index(settings["enterprise_rbac_status"]),
        disabled=not editable,
    )
    default_role = mapping_cols[1].selectbox(
        "Default CostOps role",
        ACCESS_ROLES,
        index=ACCESS_ROLES.index(settings["enterprise_default_role"]),
        disabled=not editable,
    )
    mapping_cols[2].text_input("Current plan", value=current_costops_plan()[0], disabled=True)
    mapping_notes = st.text_area(
        "Mapping notes",
        value=settings["enterprise_role_mapping_notes"],
        placeholder="Example: SNOWFLAKE_FINOPS_ADMIN -> CostOps Admin",
        disabled=not editable,
    )

    role_strategy = st.segmented_control(
        "Role onboarding path",
        ["Map existing roles", "Use recommended roles"],
        default=settings.get("enterprise_rbac_mode", "Map existing roles"),
        width="stretch",
        disabled=not editable,
    )
    if role_strategy == "Use recommended roles":
        st.info(
            "Recommended roles work well for smaller or less mature teams. CostOps suggests account-role names and "
            "the SQL needed to grant the app’s roles into those Snowflake roles."
        )
    else:
        st.info(
            "Map existing Snowflake or identity roles when the customer already has an established access model."
        )

    action_cols = st.columns([2.2, 0.95, 2], gap="small", vertical_alignment="bottom")
    with action_cols[0]:
        mode = st.segmented_control(
            "Mapping action",
            ["Edit mapping", "Remove mapping", "Add mapping"],
            default="Edit mapping",
            width="stretch",
        )
    with action_cols[1]:
        st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
        save_mapping = st.button("Save", type="primary", disabled=not editable, width="stretch")
    with action_cols[2]:
        if mode == "Add mapping":
            st.caption("Create a new Snowflake or application role mapping into CostOps.")
        elif mode == "Edit mapping":
            st.caption("Update an existing source-role mapping and validation status.")
        else:
            st.caption("Remove a mapping. The default CostOps role will still apply as a fallback.")

    selected_source = ""
    selected_record = {}
    if mode in {"Edit mapping", "Remove mapping"} and not mappings.empty:
        selected_source = st.selectbox("Source role", [""] + mappings["source_role"].tolist())
        if selected_source:
            selected_record = mappings[mappings["source_role"] == selected_source].iloc[0].to_dict()

    suggested_roles = _rbac_suggested_source_roles(mappings["source_role"].tolist() if "source_role" in mappings else [])
    recommended_roles = _rbac_starter_roles()
    source_role = selected_record.get("source_role", "")
    if mode == "Add mapping":
        if role_strategy == "Use recommended roles":
            recommended_options = [entry["source_role"] for entry in recommended_roles] + ["Custom role"]
            selected_recommended_role = st.selectbox(
                "Recommended source role",
                recommended_options,
                disabled=not editable,
            )
            if selected_recommended_role == "Custom role":
                source_role = ""
            else:
                source_role = selected_recommended_role
                starter_match = next(
                    (entry for entry in recommended_roles if entry["source_role"] == selected_recommended_role),
                    {},
                )
                selected_record = {
                    **selected_record,
                    "source_role": starter_match.get("source_role", ""),
                    "costops_role": starter_match.get("costops_role", default_role),
                    "scope": starter_match.get("scope", "Mapped application access"),
                    "status": "Ready for validation",
                }
        else:
            suggested_option = st.selectbox(
                "Suggested source role",
                suggested_roles + ["Custom role"],
                disabled=not editable,
            )
            if suggested_option != "Custom role":
                source_role = suggested_option

    form_cols = st.columns([1.15, 1, 1.25, 1], gap="small")
    source_role_value = source_role or selected_record.get("source_role", "")
    show_source_input = mode != "Remove mapping" and not (
        mode == "Add mapping" and source_role_value and source_role_value != "Custom role"
    )
    if show_source_input:
        source_role_value = form_cols[0].text_input(
            "Source role",
            value=source_role_value,
            placeholder="SNOWFLAKE_COSTOPS_ADMIN",
            disabled=not editable or mode == "Remove mapping",
        )
    else:
        form_cols[0].text_input("Source role", value=source_role_value, disabled=True)
    mapped_role = form_cols[1].selectbox(
        "CostOps role",
        ACCESS_ROLES,
        index=ACCESS_ROLES.index(selected_record.get("costops_role", default_role))
        if selected_record.get("costops_role", default_role) in ACCESS_ROLES
        else 0,
        disabled=not editable or mode == "Remove mapping",
    )
    mapping_scope = form_cols[2].text_input(
        "Scope",
        value=selected_record.get("scope", ""),
        placeholder="Workflow and reporting",
        disabled=not editable or mode == "Remove mapping",
    )
    mapping_state = form_cols[3].selectbox(
        "Mapping status",
        ENTERPRISE_STATUS_OPTIONS,
        index=ENTERPRISE_STATUS_OPTIONS.index(selected_record.get("status", "Not configured"))
        if selected_record.get("status", "Not configured") in ENTERPRISE_STATUS_OPTIONS
        else 0,
        disabled=not editable or mode == "Remove mapping",
    )

    if editable and save_mapping:
        before_settings = settings.copy()
        updated = [dict(entry) for entry in settings.get("enterprise_role_mappings", [])]
        if mode == "Remove mapping":
            if not selected_source:
                st.error("Choose a source role to remove.")
                st.stop()
            updated = [entry for entry in updated if entry.get("source_role") != selected_source]
        else:
            payload = {
                "source_role": source_role_value.strip(),
                "costops_role": mapped_role,
                "scope": mapping_scope.strip() or "Mapped application access",
                "status": mapping_state,
            }
            if not payload["source_role"]:
                st.error("Source role is required.")
                st.stop()
            if mode == "Edit mapping" and selected_source:
                updated = [entry for entry in updated if entry.get("source_role") != selected_source]
            else:
                updated = [entry for entry in updated if entry.get("source_role") != payload["source_role"]]
            updated.append(payload)
        updated_settings = persist_app_settings(
            st.session_state,
            {
                "enterprise_rbac_status": rbac_status,
                "enterprise_rbac_mode": role_strategy,
                "enterprise_default_role": default_role,
                "enterprise_role_mapping_notes": mapping_notes,
                "enterprise_role_mappings": sorted(updated, key=lambda entry: entry.get("source_role", "")),
            },
        )
        log_enterprise_config_change(
            st.session_state,
            "RBAC Mapping",
            before_settings,
            updated_settings,
            [
                "enterprise_rbac_status",
                "enterprise_rbac_mode",
                "enterprise_default_role",
                "enterprise_role_mapping_notes",
                "enterprise_role_mappings",
            ],
            "enterprise_rbac_status",
        )
        st.success("RBAC mapping settings saved.")
        st.rerun()

    if editable and role_strategy == "Use recommended roles":
        if st.button("Apply recommended starter mappings"):
            before_settings = settings.copy()
            starter_payload = [
                {
                    "source_role": entry["source_role"],
                    "costops_role": entry["costops_role"],
                    "scope": entry["scope"],
                    "status": "Ready for validation",
                }
                for entry in recommended_roles
            ]
            updated_settings = persist_app_settings(
                st.session_state,
                {
                    "enterprise_rbac_status": rbac_status,
                    "enterprise_rbac_mode": role_strategy,
                    "enterprise_default_role": default_role,
                    "enterprise_role_mapping_notes": mapping_notes,
                    "enterprise_role_mappings": starter_payload,
                },
            )
            log_enterprise_config_change(
                st.session_state,
                "RBAC Mapping",
                before_settings,
                updated_settings,
                [
                    "enterprise_rbac_status",
                    "enterprise_rbac_mode",
                    "enterprise_default_role",
                    "enterprise_role_mappings",
                ],
                "enterprise_rbac_status",
            )
            st.success("Recommended starter mappings applied.")
            st.rerun()

    if role_strategy == "Use recommended roles":
        st.subheader("Recommended Snowflake Role Setup")
        starter_rows = []
        for entry in recommended_roles:
            starter_rows.append(
                {
                    "Recommended Role": entry["source_role"],
                    "Maps To": entry["costops_role"],
                    "Purpose": entry["scope"],
                }
            )
        st.dataframe(pd.DataFrame(starter_rows), use_container_width=True, hide_index=True)
        st.code(
            "\n".join(
                [
                    "-- Example starter SQL for a customer account",
                    "CREATE ROLE IF NOT EXISTS COSTOPS_ADMIN;",
                    "CREATE ROLE IF NOT EXISTS COSTOPS_OPERATOR;",
                    "CREATE ROLE IF NOT EXISTS COSTOPS_VIEWER;",
                    "",
                    "-- Grant CostOps application roles to the customer roles",
                    "GRANT APPLICATION ROLE <installed_app_name>.costops_admin TO ROLE COSTOPS_ADMIN;",
                    "GRANT APPLICATION ROLE <installed_app_name>.costops_operator TO ROLE COSTOPS_OPERATOR;",
                    "GRANT APPLICATION ROLE <installed_app_name>.costops_viewer TO ROLE COSTOPS_VIEWER;",
                ]
            ),
            language="sql",
        )
    else:
        st.caption(
            "For mature environments, map existing Snowflake or identity roles into CostOps without forcing new role creation."
        )

    st.subheader("Mapping Coverage")
    coverage_rows = []
    for role_name in ACCESS_ROLES:
        mapped_sources = mappings[mappings["costops_role"] == role_name] if not mappings.empty else pd.DataFrame()
        statuses = ", ".join(sorted({status for status in mapped_sources.get("status", pd.Series(dtype=str)).tolist() if status})) or "Not configured"
        coverage_rows.append(
            {
                "CostOps Role": role_name,
                "Mapped Source Roles": int(len(mapped_sources)),
                "Coverage Status": "Covered" if len(mapped_sources) else "Missing",
                "Validation State": statuses,
            }
        )
    st.dataframe(pd.DataFrame(coverage_rows), use_container_width=True, hide_index=True)

    st.subheader("Current Role Mappings")
    st.dataframe(
        mappings.sort_values("source_role").rename(
            columns={
                "source_role": "Source Role",
                "costops_role": "CostOps Role",
                "scope": "Scope",
                "status": "Status",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Effective Access Preview")
    preview_cols = st.columns([1.3, 1.1, 1.6], gap="small")
    preview_source = preview_cols[0].selectbox(
        "Preview source role",
        ["Default fallback"] + mappings["source_role"].tolist(),
        index=0,
    )
    if preview_source == "Default fallback":
        resolved_role = default_role
        preview_status = settings["enterprise_rbac_status"]
        preview_scope = "Fallback role applied when no explicit mapping exists."
    else:
        preview_record = mappings[mappings["source_role"] == preview_source].iloc[0].to_dict()
        resolved_role = preview_record.get("costops_role", default_role)
        preview_status = preview_record.get("status", "Not configured")
        preview_scope = preview_record.get("scope", "Mapped application access")
    preview_cols[1].metric("Resolved CostOps role", resolved_role)
    preview_cols[2].markdown(
        f"**Validation state:** {preview_status}<br>**Scope:** {escape(preview_scope)}",
        unsafe_allow_html=True,
    )
    st.dataframe(_rbac_permission_summary(resolved_role), use_container_width=True, hide_index=True)

    permission_rows = []
    for role_name, permissions in ROLE_PERMISSIONS.items():
        permission_rows.append(
            {
                "CostOps Role": role_name,
                "Admin Access": "Yes" if "admin" in permissions else "No",
                "Workflow Actions": "Yes" if "operate" in permissions else "No",
                "Assignment Updates": "Yes" if "assign" in permissions else "No",
                "Sensitive Views": "Yes" if "view_sensitive" in permissions else "No",
            }
        )
    st.subheader("CostOps Permission Matrix")
    st.dataframe(pd.DataFrame(permission_rows), use_container_width=True, hide_index=True)


def environments_page():
    settings = current_app_settings(st.session_state)
    plan_name, _ = current_costops_plan()
    unlocked = has_entitlement("linked_dev_test")
    editable = unlocked and has_permission("admin")

    st.title("Environments")
    st.caption("Define the production Snowflake account and register linked dev/test environments for validation.")
    if not unlocked:
        _enterprise_locked_message(plan_name, "Environments")
    elif not has_permission("admin"):
        st.info("Environments are visible in read-only mode for this session role.")

    linked = pd.DataFrame(settings.get("enterprise_linked_environments", []))
    if linked.empty:
        linked = pd.DataFrame(columns=["environment", "account_locator", "purpose", "status"])

    linked_rows = len(linked)
    configured_accounts = int(linked["account_locator"].fillna("").astype(str).str.strip().ne("").sum()) if "account_locator" in linked else 0
    active_linked = int((linked["status"] == "Active").sum()) if "status" in linked else 0
    env_summary = st.columns(4, gap="small")
    env_summary[0].metric("Production instance", "Defined" if settings["enterprise_prod_account"] else "Pending")
    env_summary[1].metric("Linked validation envs", f"{linked_rows}")
    env_summary[2].metric("Configured account locators", f"{configured_accounts}")
    env_summary[3].metric("Active linked envs", f"{active_linked}")

    prod_cols = st.columns([1, 1, 1, 1], gap="small")
    production_status = prod_cols[0].selectbox(
        "Production status",
        ENTERPRISE_STATUS_OPTIONS,
        index=ENTERPRISE_STATUS_OPTIONS.index(settings["enterprise_production_status"]),
        disabled=not editable,
    )
    prod_account = prod_cols[1].text_input(
        "Production Snowflake account",
        value=settings["enterprise_prod_account"],
        placeholder="ORG-ACCOUNT",
        disabled=not editable,
    )
    prod_region = prod_cols[2].text_input(
        "Region",
        value=settings["enterprise_prod_region"],
        placeholder="AWS us-east-1",
        disabled=not editable,
    )
    app_instance = prod_cols[3].text_input(
        "Installed app instance",
        value=settings["enterprise_app_instance"],
        placeholder="GRAINAI_COSTOPS_PROD",
        disabled=not editable,
    )
    billing_scope = st.text_input("Billing scope", value=settings["enterprise_billing_scope"], disabled=not editable)

    if settings["enterprise_prod_account"]:
        st.success(
            f"Enterprise billing is anchored to production account `{settings['enterprise_prod_account']}`. "
            "Linked dev/test environments below are modeled as validation accounts, not separate production instances."
        )
    else:
        st.info("Define the production Snowflake account first so linked validation environments have a clear billing anchor.")

    env_status_cols = st.columns([1, 1.25, 0.9], gap="small", vertical_alignment="bottom")
    with env_status_cols[0]:
        linked_status = st.selectbox(
            "Linked environment status",
            ENTERPRISE_STATUS_OPTIONS,
            index=ENTERPRISE_STATUS_OPTIONS.index(settings["enterprise_linked_environments_status"]),
            disabled=not editable,
        )
    with env_status_cols[1]:
        env_mode = st.segmented_control(
            "Environment action",
            ["Edit environment", "Remove environment", "Add environment"],
            default="Edit environment",
            width="stretch",
        )
    with env_status_cols[2]:
        st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
        save_environment = st.button("Save", type="primary", disabled=not editable, width="stretch")

    selected_env = ""
    selected_record = {}
    if env_mode in {"Edit environment", "Remove environment"} and not linked.empty:
        selected_env = st.selectbox("Environment name", [""] + linked["environment"].tolist())
        if selected_env:
            selected_record = linked[linked["environment"] == selected_env].iloc[0].to_dict()

    manage_cols = st.columns([1, 1, 1.4, 1], gap="small")
    env_name = manage_cols[0].text_input(
        "Environment",
        value=selected_record.get("environment", ""),
        placeholder="Dev Validation",
        disabled=not editable or env_mode == "Remove environment",
    )
    env_account = manage_cols[1].text_input(
        "Account locator",
        value=selected_record.get("account_locator", ""),
        placeholder="ORG-ACCOUNT_DEV",
        disabled=not editable or env_mode == "Remove environment",
    )
    env_purpose = manage_cols[2].text_input(
        "Purpose",
        value=selected_record.get("purpose", ""),
        placeholder="Pre-production validation",
        disabled=not editable or env_mode == "Remove environment",
    )
    env_state = manage_cols[3].selectbox(
        "Environment status",
        ENTERPRISE_STATUS_OPTIONS,
        index=ENTERPRISE_STATUS_OPTIONS.index(selected_record.get("status", "Not configured"))
        if selected_record.get("status", "Not configured") in ENTERPRISE_STATUS_OPTIONS
        else 0,
        disabled=not editable or env_mode == "Remove environment",
    )

    if editable and save_environment:
        before_settings = settings.copy()
        updated = [dict(entry) for entry in settings.get("enterprise_linked_environments", [])]
        if env_mode == "Remove environment":
            if not selected_env:
                st.error("Choose an environment to remove.")
                st.stop()
            updated = [entry for entry in updated if entry.get("environment") != selected_env]
        else:
            payload = {
                "environment": env_name.strip(),
                "account_locator": env_account.strip(),
                "purpose": env_purpose.strip() or "Validation",
                "status": env_state,
            }
            if not payload["environment"]:
                st.error("Environment name is required.")
                st.stop()
            if env_mode == "Edit environment" and selected_env:
                updated = [entry for entry in updated if entry.get("environment") != selected_env]
            else:
                updated = [entry for entry in updated if entry.get("environment") != payload["environment"]]
            updated.append(payload)
        updated_settings = persist_app_settings(
            st.session_state,
            {
                "enterprise_production_status": production_status,
                "enterprise_prod_account": prod_account,
                "enterprise_prod_region": prod_region,
                "enterprise_app_instance": app_instance,
                "enterprise_billing_scope": billing_scope,
                "enterprise_linked_environments_status": linked_status,
                "enterprise_linked_environments": sorted(updated, key=lambda entry: entry.get("environment", "")),
            },
        )
        log_enterprise_config_change(
            st.session_state,
            "Environments",
            before_settings,
            updated_settings,
            [
                "enterprise_production_status",
                "enterprise_prod_account",
                "enterprise_prod_region",
                "enterprise_app_instance",
                "enterprise_billing_scope",
                "enterprise_linked_environments_status",
                "enterprise_linked_environments",
            ],
            "enterprise_linked_environments_status",
        )
        st.success("Environment settings saved.")
        st.rerun()

    st.subheader("Environment Readiness")
    readiness_rows = [
        {
            "Environment Type": "Production",
            "Name": settings["enterprise_app_instance"] or "Production instance pending",
            "Account": settings["enterprise_prod_account"] or "Not configured",
            "Purpose": "Billable production instance",
            "Status": settings["enterprise_production_status"],
        }
    ]
    for entry in linked.to_dict("records"):
        readiness_rows.append(
            {
                "Environment Type": "Validation",
                "Name": entry.get("environment", ""),
                "Account": entry.get("account_locator", "") or "Not configured",
                "Purpose": entry.get("purpose", "") or "Validation",
                "Status": entry.get("status", "Not configured"),
            }
        )
    st.dataframe(pd.DataFrame(readiness_rows), use_container_width=True, hide_index=True)

    st.subheader("Linked Validation Environments")
    st.dataframe(
        linked.sort_values("environment").rename(
            columns={
                "environment": "Environment",
                "account_locator": "Account Locator",
                "purpose": "Purpose",
                "status": "Status",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def persistence_page():
    settings = current_app_settings(st.session_state)
    plan_name, _ = current_costops_plan()
    unlocked = has_entitlement("dedicated_persistence")
    editable = unlocked and has_permission("admin")

    st.title("Persistence")
    st.caption("Track the dedicated persistence target, isolation model, retention, backups, and restore readiness.")
    if not unlocked:
        _enterprise_locked_message(plan_name, "Dedicated Persistence")
    elif not has_permission("admin"):
        st.info("Persistence settings are visible in read-only mode for this session role.")

    persistence_target_options = ["Dedicated Postgres", "Managed Postgres", "Marketplace-managed store", "Custom"]
    isolation_options = ["Tenant-isolated schema", "Tenant-isolated database", "Dedicated cluster", "Custom"]
    retention_options = ["12 months", "24 months", "36 months", "Custom"]
    backup_options = ["Not configured", "Daily", "Hourly", "Custom"]

    persistence_summary = st.columns(4, gap="small")
    persistence_summary[0].metric("Persistence status", settings["enterprise_persistence_status"])
    persistence_summary[1].metric("Target", settings["enterprise_persistence_target"])
    persistence_summary[2].metric("Retention", settings["enterprise_retention"])
    persistence_summary[3].metric("Restore readiness", settings["enterprise_restore_test_status"])

    if settings["enterprise_persistence_status"] == "Active":
        st.success(
            f"Dedicated persistence is marked active using `{settings['enterprise_persistence_target']}` "
            f"with `{settings['enterprise_persistence_isolation']}` isolation."
        )
    else:
        st.info(
            "Use this page to define where enterprise data lives, how it is isolated, and whether backup "
            "and restore workflows are ready for validation."
        )

    top_cols = st.columns([1, 1, 1], gap="small")
    persistence_status = top_cols[0].selectbox(
        "Persistence status",
        ENTERPRISE_STATUS_OPTIONS,
        index=ENTERPRISE_STATUS_OPTIONS.index(settings["enterprise_persistence_status"]),
        disabled=not editable,
    )
    persistence_target = top_cols[1].selectbox(
        "Persistence target",
        persistence_target_options,
        index=persistence_target_options.index(settings["enterprise_persistence_target"])
        if settings["enterprise_persistence_target"] in persistence_target_options
        else 0,
        disabled=not editable,
    )
    isolation = top_cols[2].selectbox(
        "Isolation model",
        isolation_options,
        index=isolation_options.index(settings["enterprise_persistence_isolation"])
        if settings["enterprise_persistence_isolation"] in isolation_options
        else 0,
        disabled=not editable,
    )

    action_cols = st.columns([1.8, 1.2, 1.2, 0.85, 1.6], gap="small", vertical_alignment="bottom")
    with action_cols[0]:
        retention = st.selectbox(
            "Retention",
            retention_options,
            index=retention_options.index(settings["enterprise_retention"])
            if settings["enterprise_retention"] in retention_options
            else 1,
            disabled=not editable,
        )
    with action_cols[1]:
        backup_status = st.selectbox(
            "Backup status",
            backup_options,
            index=backup_options.index(settings["enterprise_backup_status"])
            if settings["enterprise_backup_status"] in backup_options
            else 0,
            disabled=not editable,
        )
    with action_cols[2]:
        restore_status = st.selectbox(
            "Restore test status",
            ENTERPRISE_STATUS_OPTIONS,
            index=ENTERPRISE_STATUS_OPTIONS.index(settings["enterprise_restore_test_status"]),
            disabled=not editable,
        )
    with action_cols[3]:
        st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
        save_persistence = st.button("Save", type="primary", disabled=not editable, width="stretch")
    with action_cols[4]:
        st.caption("Capture the operating target, isolation posture, retention, and backup/restore state.")

    if editable and save_persistence:
        before_settings = settings.copy()
        updated_settings = persist_app_settings(
            st.session_state,
            {
                "enterprise_persistence_status": persistence_status,
                "enterprise_persistence_target": persistence_target,
                "enterprise_persistence_isolation": isolation,
                "enterprise_retention": retention,
                "enterprise_backup_status": backup_status,
                "enterprise_restore_test_status": restore_status,
            },
        )
        log_enterprise_config_change(
            st.session_state,
            "Persistence",
            before_settings,
            updated_settings,
            [
                "enterprise_persistence_status",
                "enterprise_persistence_target",
                "enterprise_persistence_isolation",
                "enterprise_retention",
                "enterprise_backup_status",
                "enterprise_restore_test_status",
            ],
            "enterprise_persistence_status",
        )
        st.success("Persistence settings saved.")
        st.rerun()

    st.subheader("Persistence Readiness")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Area": "Persistence Target",
                    "Current State": persistence_target,
                    "Readiness": persistence_status,
                    "Notes": "Primary data store for enterprise configuration and operating history.",
                },
                {
                    "Area": "Isolation Model",
                    "Current State": isolation,
                    "Readiness": persistence_status,
                    "Notes": "Controls tenant separation for enterprise data.",
                },
                {
                    "Area": "Retention",
                    "Current State": retention,
                    "Readiness": "Configured" if retention else "Not configured",
                    "Notes": "Intended operating window for persisted application data.",
                },
                {
                    "Area": "Backup Cadence",
                    "Current State": backup_status,
                    "Readiness": "Ready for validation" if backup_status != "Not configured" else "Not configured",
                    "Notes": "Expected backup operating rhythm for the persistence layer.",
                },
                {
                    "Area": "Restore Test",
                    "Current State": restore_status,
                    "Readiness": restore_status,
                    "Notes": "Operational readiness for recovery validation.",
                },
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


def sso_identity_page():
    settings = current_app_settings(st.session_state)
    plan_name, _ = current_costops_plan()
    unlocked = has_entitlement("sso")
    editable = unlocked and has_permission("admin")

    st.title("SSO & Identity")
    st.caption("Capture identity-provider metadata, domain allowlists, and validation readiness for enterprise sign-in.")
    if not unlocked:
        _enterprise_locked_message(plan_name, "SSO & Identity")
    elif not has_permission("admin"):
        st.info("SSO & Identity is visible in read-only mode for this session role.")

    sso_provider_options = ["Not configured", "Okta", "Microsoft Entra ID", "Ping Identity", "Google Workspace", "Other"]
    protocol_options = ["SAML 2.0", "OIDC", "Marketplace-managed"]

    sso_summary = st.columns(4, gap="small")
    sso_summary[0].metric("SSO status", settings["enterprise_sso_status"])
    sso_summary[1].metric("Identity provider", settings["enterprise_sso_provider"])
    sso_summary[2].metric("Protocol", settings["enterprise_identity_protocol"])
    sso_summary[3].metric("Allowed domain", settings["enterprise_allowed_domain"] or "Not configured")

    if settings["enterprise_sso_status"] == "Active":
        st.success(
            f"Enterprise identity is marked active using `{settings['enterprise_sso_provider']}` "
            f"over `{settings['enterprise_identity_protocol']}`."
        )
    else:
        st.info(
            "Use this page to define the identity provider, allowed domain, metadata handoff, and "
            "validation readiness before any production SSO integration work."
        )

    cols = st.columns(3, gap="small")
    sso_status = cols[0].selectbox(
        "SSO status",
        ENTERPRISE_STATUS_OPTIONS,
        index=ENTERPRISE_STATUS_OPTIONS.index(settings["enterprise_sso_status"]),
        disabled=not editable,
    )
    sso_provider = cols[1].selectbox(
        "SSO provider",
        sso_provider_options,
        index=sso_provider_options.index(settings["enterprise_sso_provider"])
        if settings["enterprise_sso_provider"] in sso_provider_options
        else 0,
        disabled=not editable,
    )
    identity_protocol = cols[2].selectbox(
        "Identity protocol",
        protocol_options,
        index=protocol_options.index(settings["enterprise_identity_protocol"])
        if settings["enterprise_identity_protocol"] in protocol_options
        else 0,
        disabled=not editable,
    )

    action_cols = st.columns([1.2, 1.5, 1.25, 0.8, 1.5], gap="small", vertical_alignment="bottom")
    with action_cols[0]:
        allowed_domain = st.text_input(
            "Allowed domain",
            value=settings["enterprise_allowed_domain"],
            placeholder="company.com",
            disabled=not editable,
        )
    with action_cols[1]:
        metadata_url = st.text_input(
            "Metadata URL",
            value=settings["enterprise_metadata_url"],
            placeholder="https://idp.example.com/metadata",
            disabled=not editable,
        )
    with action_cols[2]:
        entity_id = st.text_input(
            "Entity ID",
            value=settings["enterprise_entity_id"],
            placeholder="urn:costops:enterprise",
            disabled=not editable,
        )
    with action_cols[3]:
        st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
        save_sso = st.button("Save", type="primary", disabled=not editable, width="stretch")
    with action_cols[4]:
        st.caption("Capture provider metadata and domain rules for enterprise identity validation.")

    sso_contact = st.text_input(
        "Implementation contact",
        value=settings["enterprise_sso_contact"],
        placeholder="identity-admin@company.com",
        disabled=not editable,
    )

    if editable and save_sso:
        before_settings = settings.copy()
        updated_settings = persist_app_settings(
            st.session_state,
            {
                "enterprise_sso_status": sso_status,
                "enterprise_sso_provider": sso_provider,
                "enterprise_identity_protocol": identity_protocol,
                "enterprise_allowed_domain": allowed_domain,
                "enterprise_metadata_url": metadata_url,
                "enterprise_entity_id": entity_id,
                "enterprise_sso_contact": sso_contact,
            },
        )
        log_enterprise_config_change(
            st.session_state,
            "SSO & Identity",
            before_settings,
            updated_settings,
            [
                "enterprise_sso_status",
                "enterprise_sso_provider",
                "enterprise_identity_protocol",
                "enterprise_allowed_domain",
                "enterprise_metadata_url",
                "enterprise_entity_id",
                "enterprise_sso_contact",
            ],
            "enterprise_sso_status",
        )
        st.success("SSO settings saved.")
        st.rerun()

    st.subheader("Identity Readiness")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Area": "Identity Provider",
                    "Current State": sso_provider,
                    "Readiness": sso_status,
                    "Notes": "Selected provider for enterprise identity integration.",
                },
                {
                    "Area": "Identity Protocol",
                    "Current State": identity_protocol,
                    "Readiness": sso_status,
                    "Notes": "Expected authentication protocol for enterprise sign-in.",
                },
                {
                    "Area": "Allowed Domain",
                    "Current State": allowed_domain or "Not configured",
                    "Readiness": "Configured" if allowed_domain else "Not configured",
                    "Notes": "Primary email domain or tenant boundary for user access.",
                },
                {
                    "Area": "Metadata URL",
                    "Current State": metadata_url or "Not configured",
                    "Readiness": "Ready for validation" if metadata_url else "Not configured",
                    "Notes": "IdP metadata location used for implementation handoff.",
                },
                {
                    "Area": "Implementation Contact",
                    "Current State": sso_contact or "Not configured",
                    "Readiness": "Configured" if sso_contact else "Action needed",
                    "Notes": "Primary identity or admin contact for rollout and validation.",
                },
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


def sla_support_page():
    settings = current_app_settings(st.session_state)
    plan_name, _ = current_costops_plan()
    unlocked = has_entitlement("sla")
    editable = unlocked and has_permission("admin")

    st.title("SLA & Support")
    st.caption("Track support tier, response expectations, deployment ownership, and escalation path for enterprise accounts.")
    if not unlocked:
        _enterprise_locked_message(plan_name, "SLA & Support")
    elif not has_permission("admin"):
        st.info("SLA & Support is visible in read-only mode for this session role.")

    support_summary = st.columns(4, gap="small")
    support_summary[0].metric("SLA status", settings["enterprise_sla_status"])
    support_summary[1].metric("Support tier", settings["enterprise_support_tier"])
    support_summary[2].metric("Response window", settings["enterprise_response_sla"])
    support_summary[3].metric("Deployment owner", settings["enterprise_deployment_owner"] or "Not assigned")

    if settings["enterprise_sla_status"] == "Active":
        st.success(
            f"Enterprise support is marked active with `{settings['enterprise_support_tier']}` "
            f"and a `{settings['enterprise_response_sla']}` response target."
        )
    else:
        st.info(
            "Use this page to define the enterprise support tier, expected response window, named owner, "
            "and escalation model before go-live."
        )

    cols = st.columns(3, gap="small")
    sla_status = cols[0].selectbox(
        "SLA status",
        ENTERPRISE_STATUS_OPTIONS,
        index=ENTERPRISE_STATUS_OPTIONS.index(settings["enterprise_sla_status"]),
        disabled=not editable,
    )
    support_tier = cols[1].selectbox(
        "Support tier",
        ENTERPRISE_SUPPORT_TIERS,
        index=ENTERPRISE_SUPPORT_TIERS.index(settings["enterprise_support_tier"])
        if settings["enterprise_support_tier"] in ENTERPRISE_SUPPORT_TIERS
        else 0,
        disabled=not editable,
    )
    response_sla = cols[2].selectbox(
        "Response window",
        ENTERPRISE_RESPONSE_WINDOWS,
        index=ENTERPRISE_RESPONSE_WINDOWS.index(settings["enterprise_response_sla"])
        if settings["enterprise_response_sla"] in ENTERPRISE_RESPONSE_WINDOWS
        else 1,
        disabled=not editable,
    )

    action_cols = st.columns([1.3, 1.9, 0.8, 1.5], gap="small", vertical_alignment="bottom")
    with action_cols[0]:
        deployment_owner = st.text_input(
            "Deployment owner",
            value=settings["enterprise_deployment_owner"],
            placeholder="customer-success@grainai.com",
            disabled=not editable,
        )
    with action_cols[1]:
        escalation_path = st.text_input(
            "Escalation path",
            value=settings["enterprise_escalation_path"],
            placeholder="Support -> Platform -> Engineering",
            disabled=not editable,
        )
    with action_cols[2]:
        st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
        save_sla = st.button("Save", type="primary", disabled=not editable, width="stretch")
    with action_cols[3]:
        st.caption("Define the support owner, escalation route, and response commitment.")

    support_notes = st.text_area(
        "Support notes",
        value=settings["enterprise_support_notes"],
        placeholder="Named contacts, support exclusions, go-live conditions",
        disabled=not editable,
    )
    if editable and save_sla:
        before_settings = settings.copy()
        updated_settings = persist_app_settings(
            st.session_state,
            {
                "enterprise_sla_status": sla_status,
                "enterprise_support_tier": support_tier,
                "enterprise_response_sla": response_sla,
                "enterprise_deployment_owner": deployment_owner,
                "enterprise_escalation_path": escalation_path,
                "enterprise_support_notes": support_notes,
            },
        )
        log_enterprise_config_change(
            st.session_state,
            "SLA & Support",
            before_settings,
            updated_settings,
            [
                "enterprise_sla_status",
                "enterprise_support_tier",
                "enterprise_response_sla",
                "enterprise_deployment_owner",
                "enterprise_escalation_path",
                "enterprise_support_notes",
            ],
            "enterprise_sla_status",
        )
        st.success("SLA & support settings saved.")
        st.rerun()

    st.subheader("Support Readiness")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Area": "Support Tier",
                    "Current State": support_tier,
                    "Readiness": sla_status,
                    "Notes": "Named enterprise support level for the account.",
                },
                {
                    "Area": "Response Window",
                    "Current State": response_sla,
                    "Readiness": sla_status,
                    "Notes": "Expected response target for support handling.",
                },
                {
                    "Area": "Deployment Owner",
                    "Current State": deployment_owner or "Not assigned",
                    "Readiness": "Configured" if deployment_owner else "Action needed",
                    "Notes": "Primary owner coordinating rollout and support readiness.",
                },
                {
                    "Area": "Escalation Path",
                    "Current State": escalation_path or "Not configured",
                    "Readiness": "Configured" if escalation_path else "Action needed",
                    "Notes": "Expected internal route for issues that need escalation.",
                },
                {
                    "Area": "Support Notes",
                    "Current State": "Captured" if support_notes.strip() else "Not configured",
                    "Readiness": "Configured" if support_notes.strip() else "Not configured",
                    "Notes": "Additional support commitments, exclusions, or go-live notes.",
                },
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_enterprise_feature_grid(locked):
    cards = []
    for feature_name, metadata in ENTERPRISE_CONTROL_FEATURES.items():
        enabled = has_entitlement(feature_name) and not locked
        card_class = "costops-entitlement-card" if enabled else "costops-entitlement-card locked"
        state_class = "costops-entitlement-state" if enabled else "costops-entitlement-state locked"
        state_text = "Unlocked" if enabled else "Enterprise"
        cards.append(
            f'<div class="{card_class}">'
            f'<div class="costops-entitlement-title">{escape(metadata["title"])}</div>'
            f'<div class="costops-entitlement-copy">{escape(metadata["copy"])}</div>'
            f'<span class="{state_class}">{state_text}</span>'
            "</div>"
        )
    st.markdown(
        '<div class="costops-entitlement-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


NAVIGATION_SPECS = {
    "Command Center": [
        {"fn": overview, "title": "Overview", "icon": ":material/space_dashboard:", "default": True},
        {"fn": recommendations_page, "title": "Recommendations", "icon": ":material/rule_folder:"},
        {"fn": my_work_page, "title": "My Work", "icon": ":material/badge:"},
        {"fn": scan_schedule_page, "title": "Scan & Schedule", "icon": ":material/schedule_send:"},
    ],
    "Analysis": [
        {"fn": warehouses_page, "title": "Warehouses", "icon": ":material/database:"},
        {"fn": workloads_page, "title": "Workloads", "icon": ":material/monitoring:"},
        {"fn": storage_page, "title": "Storage", "icon": ":material/storage:"},
        {"fn": tasks_page, "title": "Tasks", "icon": ":material/task_alt:"},
    ],
    "Value": [
        {"fn": savings_realization_page, "title": "Savings Realization", "icon": ":material/trending_up:"},
        {"fn": reports_page, "title": "Reports", "icon": ":material/assessment:"},
    ],
    "Admin": [
        {"fn": upgrade_plan_page, "title": "Upgrade Plan", "icon": ":material/workspace_premium:", "url_path": "upgrade_plan"},
        {"fn": enterprise_controls_page, "title": "Enterprise Controls", "icon": ":material/admin_panel_settings:", "url_path": "enterprise_controls"},
        {"fn": rbac_mapping_page, "title": "RBAC Mapping", "icon": ":material/admin_panel_settings:", "url_path": "rbac_mapping"},
        {"fn": environments_page, "title": "Environments", "icon": ":material/account_tree:", "url_path": "enterprise_environments"},
        {"fn": persistence_page, "title": "Persistence", "icon": ":material/database:", "url_path": "enterprise_persistence"},
        {"fn": sso_identity_page, "title": "SSO & Identity", "icon": ":material/badge:", "url_path": "enterprise_identity"},
        {"fn": sla_support_page, "title": "SLA & Support", "icon": ":material/support_agent:", "url_path": "enterprise_support"},
        {"fn": users_roles_page, "title": "Users and Roles", "icon": ":material/group:"},
        {"fn": settings_page, "title": "Settings", "icon": ":material/settings:"},
    ],
}


def create_navigation_pages():
    return {
        section: [
            st.Page(
                page["fn"],
                title=page["title"],
                icon=page.get("icon"),
                default=page.get("default", False),
                url_path=page.get("url_path"),
            )
            for page in pages
        ]
        for section, pages in NAVIGATION_SPECS.items()
    }


def select_native_page():
    page_options = []
    for section, pages in NAVIGATION_SPECS.items():
        for page in pages:
            page_options.append((f"{section} / {page['title']}", page))
    labels = [label for label, _ in page_options]
    default_index = next(
        (index for index, (_, page) in enumerate(page_options) if page.get("default")),
        0,
    )
    selected_label = st.radio(
        "Navigation",
        labels,
        index=default_index,
        label_visibility="collapsed",
    )
    st.caption("Native compatibility navigation")
    return dict(page_options)[selected_label]


if NATIVE_APP_MODE:
    current_page = None
else:
    current_page = st.navigation(create_navigation_pages(), position="sidebar", expanded=True)

with st.sidebar:
    native_page = select_native_page() if NATIVE_APP_MODE else None
    st.divider()
    if NATIVE_APP_MODE:
        st.caption("Snowflake Native compatibility mode")
    render_sidebar_plan_status(
        recommendation_count=int(recommendations["recommendation_id"].nunique()),
        warehouse_count=warehouse_observed_count(warehouses),
    )
    st.divider()
    st.caption("Data source status")
    state = "complete" if data_source_status in {"Sample data loaded", "Snowflake warehouse metering loaded"} else "error"
    st.status(data_source_status, state=state, expanded=False)

if NATIVE_APP_MODE:
    native_page["fn"]()
else:
    current_page.run()
