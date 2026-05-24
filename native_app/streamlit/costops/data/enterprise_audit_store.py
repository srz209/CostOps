from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_STATE_DIR = ROOT / "runtime_state"
AUDIT_STATE_FILE = RUNTIME_STATE_DIR / "enterprise_config_audit.csv"
AUDIT_STATE_KEY = "enterprise_config_audit_workflow"
AUDIT_DATE_COLUMNS = ["event_ts"]


def initialize_enterprise_audit_store(session_state):
    if AUDIT_STATE_KEY not in session_state:
        session_state[AUDIT_STATE_KEY] = _load_state_file()


def _load_state_file():
    if not AUDIT_STATE_FILE.exists():
        return pd.DataFrame(
            columns=[
                "event_id",
                "event_ts",
                "area",
                "change_type",
                "actor",
                "status",
                "fields_changed",
                "details",
            ]
        )
    df = pd.read_csv(AUDIT_STATE_FILE)
    for column in AUDIT_DATE_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def enterprise_audit_frame(session_state):
    initialize_enterprise_audit_store(session_state)
    return session_state[AUDIT_STATE_KEY].copy()


def persist_enterprise_audit_store(session_state):
    initialize_enterprise_audit_store(session_state)
    RUNTIME_STATE_DIR.mkdir(exist_ok=True)
    session_state[AUDIT_STATE_KEY].to_csv(AUDIT_STATE_FILE, index=False)


def log_enterprise_audit_event(session_state, area, change_type, actor, status, fields_changed, details, event_ts):
    initialize_enterprise_audit_store(session_state)
    audit = session_state[AUDIT_STATE_KEY].copy()
    next_id = f"CFG-{len(audit) + 1:04d}"
    new_row = pd.DataFrame(
        [
            {
                "event_id": next_id,
                "event_ts": pd.Timestamp(event_ts),
                "area": area,
                "change_type": change_type,
                "actor": actor,
                "status": status,
                "fields_changed": fields_changed,
                "details": details,
            }
        ]
    )
    session_state[AUDIT_STATE_KEY] = pd.concat([audit, new_row], ignore_index=True)
    persist_enterprise_audit_store(session_state)
