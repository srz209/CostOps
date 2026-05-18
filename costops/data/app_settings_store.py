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
