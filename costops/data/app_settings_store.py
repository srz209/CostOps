from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_STATE_DIR = ROOT / "runtime_state"
SETTINGS_STATE_FILE = RUNTIME_STATE_DIR / "app_settings.json"
SETTINGS_STATE_KEY = "costops_app_settings"

DEFAULT_APP_SETTINGS = {
    "credit_price": 3.0,
    "lookback_days": 30,
    "annualization_months": 12,
    "min_confidence": 0.70,
    "min_monthly_savings": 500.0,
    "warehouse_monthly_cost_floor": 750.0,
    "warehouse_utilization_ceiling": 25.0,
    "warehouse_queue_seconds_ceiling": 120.0,
    "warehouse_downsize_savings_pct": 0.40,
    "auto_suspend_resume_threshold": 35.0,
    "auto_suspend_savings_pct": 0.18,
    "workload_scan_gb_threshold": 2000.0,
    "workload_runtime_seconds_threshold": 300.0,
    "spill_gb_threshold": 3.0,
    "full_refresh_savings_pct": 0.55,
    "spill_savings_pct": 0.25,
    "task_executions_7d_threshold": 300.0,
    "task_failures_7d_threshold": 5.0,
    "task_schedule_savings_pct": 0.45,
    "task_failure_savings_pct": 0.20,
    "stale_object_days": 90.0,
    "stale_object_access_threshold": 0.0,
    "dev_clone_savings_pct": 0.40,
    "due_days_critical": 7,
    "due_days_high": 14,
    "due_days_medium": 30,
    "due_days_low": 45,
    "teams": [
        "Unassigned",
        "Analytics Engineering",
        "Business Intelligence",
        "Data Engineering",
        "Data Governance",
        "Data Platform",
    ],
    "business_roles": [
        "Analytics Engineer",
        "BI Lead",
        "Data Engineer",
        "Data Engineering Manager",
        "FinOps Analyst",
        "Governance Lead",
        "Platform Architect",
        "Platform Engineer",
    ],
    "application_roles": [
        "CostOps Admin",
        "CostOps Operator",
        "CostOps Viewer",
    ],
    "enterprise_production_status": "Not configured",
    "enterprise_prod_account": "",
    "enterprise_prod_region": "",
    "enterprise_app_instance": "",
    "enterprise_billing_scope": "One production Snowflake account",
    "enterprise_default_role": "CostOps Viewer",
    "enterprise_rbac_status": "Not configured",
    "enterprise_rbac_mode": "Map existing roles",
    "enterprise_role_mapping_notes": "",
    "enterprise_role_mappings": [
        {
            "source_role": "SNOWFLAKE_COSTOPS_ADMIN",
            "costops_role": "CostOps Admin",
            "scope": "Enterprise administration",
            "status": "Ready for validation",
        },
        {
            "source_role": "SNOWFLAKE_COSTOPS_OPERATOR",
            "costops_role": "CostOps Operator",
            "scope": "Workflow and recommendation execution",
            "status": "Ready for validation",
        },
        {
            "source_role": "SNOWFLAKE_COSTOPS_VIEWER",
            "costops_role": "CostOps Viewer",
            "scope": "Read-only reporting and dashboards",
            "status": "Ready for validation",
        },
    ],
    "enterprise_linked_environments_status": "Not configured",
    "enterprise_linked_environments": [
        {
            "environment": "Dev Validation",
            "account_locator": "",
            "purpose": "Pre-production validation",
            "status": "Not configured",
        },
        {
            "environment": "Test Validation",
            "account_locator": "",
            "purpose": "User acceptance and rollout testing",
            "status": "Not configured",
        },
    ],
    "enterprise_sso_status": "Not configured",
    "enterprise_sso_provider": "Not configured",
    "enterprise_allowed_domain": "",
    "enterprise_identity_protocol": "SAML 2.0",
    "enterprise_metadata_url": "",
    "enterprise_entity_id": "",
    "enterprise_sso_contact": "",
    "enterprise_persistence_status": "Not configured",
    "enterprise_persistence_target": "Dedicated Postgres",
    "enterprise_persistence_isolation": "Tenant-isolated schema",
    "enterprise_retention": "24 months",
    "enterprise_backup_status": "Not configured",
    "enterprise_restore_test_status": "Not configured",
    "enterprise_sla_status": "Not configured",
    "enterprise_support_tier": "Enterprise standard",
    "enterprise_response_sla": "Next business day",
    "enterprise_deployment_owner": "",
    "enterprise_escalation_path": "",
    "enterprise_support_notes": "",
    "user_directory": [
        {"owner": "Jordan Lee", "team": "Data Platform", "role": "Platform Architect", "email": "", "access_role": "CostOps Admin"},
        {"owner": "Sam Rivera", "team": "Data Platform", "role": "Platform Engineer", "email": "", "access_role": "CostOps Operator"},
        {"owner": "Avery Patel", "team": "Data Engineering", "role": "Data Engineer", "email": "", "access_role": "CostOps Operator"},
        {"owner": "Riley Chen", "team": "Analytics Engineering", "role": "Analytics Engineer", "email": "", "access_role": "CostOps Operator"},
        {"owner": "Morgan Brooks", "team": "Business Intelligence", "role": "BI Lead", "email": "", "access_role": "CostOps Viewer"},
        {"owner": "Casey Nguyen", "team": "Data Governance", "role": "Governance Lead", "email": "", "access_role": "CostOps Viewer"},
    ],
}


def load_app_settings():
    if not SETTINGS_STATE_FILE.exists():
        return DEFAULT_APP_SETTINGS.copy()
    try:
        stored = json.loads(SETTINGS_STATE_FILE.read_text())
    except Exception:
        return DEFAULT_APP_SETTINGS.copy()
    merged = DEFAULT_APP_SETTINGS.copy()
    merged.update(stored)
    return merged


def initialize_app_settings(session_state):
    if SETTINGS_STATE_KEY not in session_state:
        session_state[SETTINGS_STATE_KEY] = load_app_settings()
    return session_state[SETTINGS_STATE_KEY]


def current_app_settings(session_state):
    settings = initialize_app_settings(session_state)
    return settings.copy()


def persist_app_settings(session_state, updates):
    RUNTIME_STATE_DIR.mkdir(exist_ok=True)
    current = initialize_app_settings(session_state).copy()
    current.update(updates)
    session_state[SETTINGS_STATE_KEY] = current
    SETTINGS_STATE_FILE.write_text(json.dumps(current, indent=2, sort_keys=True))
    return current


def due_days_by_severity(settings=None):
    settings = settings or load_app_settings()
    return {
        "Critical": int(settings["due_days_critical"]),
        "High": int(settings["due_days_high"]),
        "Medium": int(settings["due_days_medium"]),
        "Low": int(settings["due_days_low"]),
    }


def team_catalog(settings=None):
    settings = settings or load_app_settings()
    teams = settings.get("teams", []) or DEFAULT_APP_SETTINGS["teams"]
    return sorted(dict.fromkeys(["Unassigned", *teams]))


def business_role_catalog(settings=None):
    settings = settings or load_app_settings()
    roles = settings.get("business_roles", []) or DEFAULT_APP_SETTINGS["business_roles"]
    return sorted(dict.fromkeys(roles))


def application_role_catalog(settings=None):
    settings = settings or load_app_settings()
    roles = settings.get("application_roles", []) or DEFAULT_APP_SETTINGS["application_roles"]
    return [role for role in DEFAULT_APP_SETTINGS["application_roles"] if role in roles] or DEFAULT_APP_SETTINGS["application_roles"]


def user_directory_frame(settings=None):
    settings = settings or load_app_settings()
    directory = settings.get("user_directory", [])
    if not directory:
        directory = DEFAULT_APP_SETTINGS["user_directory"]
    normalized = []
    for entry in directory:
        normalized.append(
            {
                "owner": entry.get("owner", ""),
                "team": entry.get("team", ""),
                "role": entry.get("role", "Contributor"),
                "email": entry.get("email", ""),
                "access_role": entry.get("access_role", "CostOps Viewer"),
            }
        )
    return normalized


def user_lookup_map(settings=None):
    directory = user_directory_frame(settings)
    return {
        entry["owner"]: {
            "team": entry["team"],
            "role": entry["role"],
            "email": entry["email"],
            "access_role": entry["access_role"],
        }
        for entry in directory
    }
