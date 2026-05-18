from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_STATE_DIR = ROOT / "runtime_state"
RECOMMENDATIONS_STATE_FILE = RUNTIME_STATE_DIR / "recommendations.csv"
EVENTS_STATE_FILE = RUNTIME_STATE_DIR / "recommendation_events.csv"
RECOMMENDATION_STATE_KEY = "recommendations_workflow"
EVENT_STATE_KEY = "recommendation_events_workflow"
RECOMMENDATION_DATE_COLUMNS = ["first_seen_at", "last_seen_at", "accepted_at", "implemented_at"]
EVENT_DATE_COLUMNS = ["event_ts"]

ACTIONABLE_STATUSES = {
    "Selected": ("SELECTED", "Selected for active review."),
    "Accepted": ("ACCEPTED", "Accepted for implementation planning."),
    "Deferred": ("DEFERRED", "Deferred for a future optimization cycle."),
    "Rejected": ("REJECTED", "Rejected after review."),
    "Implemented": ("IMPLEMENTED", "Marked as implemented by the owner."),
    "Realized": ("SAVINGS_REALIZED", "Validated as realized savings."),
}


def initialize_session_store(session_state, recommendations, recommendation_events):
    if RECOMMENDATION_STATE_KEY not in session_state:
        session_state[RECOMMENDATION_STATE_KEY] = _load_state_file(
            RECOMMENDATIONS_STATE_FILE,
            recommendations,
            RECOMMENDATION_DATE_COLUMNS,
        )
    if EVENT_STATE_KEY not in session_state:
        session_state[EVENT_STATE_KEY] = _load_state_file(EVENTS_STATE_FILE, recommendation_events, EVENT_DATE_COLUMNS)


def _load_state_file(path, fallback, date_columns):
    if not path.exists():
        return fallback.copy()
    return pd.read_csv(path, parse_dates=date_columns)


def persist_session_store(session_state):
    RUNTIME_STATE_DIR.mkdir(exist_ok=True)
    session_state[RECOMMENDATION_STATE_KEY].to_csv(RECOMMENDATIONS_STATE_FILE, index=False)
    session_state[EVENT_STATE_KEY].to_csv(EVENTS_STATE_FILE, index=False)


def recommendations_frame(session_state):
    return session_state[RECOMMENDATION_STATE_KEY]


def recommendation_events_frame(session_state):
    return session_state[EVENT_STATE_KEY]


def log_recommendation_event(session_state, recommendation_id, event_type, actor, details, event_ts):
    events = session_state[EVENT_STATE_KEY].copy()
    next_id = f"EVT-DEMO-{len(events) + 1:03d}"
    new_event = pd.DataFrame(
        [
            {
                "event_id": next_id,
                "recommendation_id": recommendation_id,
                "event_ts": event_ts,
                "event_type": event_type,
                "actor": actor,
                "details": details,
            }
        ]
    )
    session_state[EVENT_STATE_KEY] = pd.concat([events, new_event], ignore_index=True)
    persist_session_store(session_state)


def log_sql_copied(session_state, recommendation_id, actor, event_ts):
    log_recommendation_event(
        session_state,
        recommendation_id,
        "SQL_COPIED",
        actor,
        "Copied generated SQL or implementation guidance from the recommendation detail.",
        event_ts,
    )


def update_recommendation_status(session_state, recommendation_id, new_status, actor, notes, as_of_date):
    workflow = session_state[RECOMMENDATION_STATE_KEY].copy()
    mask = workflow["recommendation_id"] == recommendation_id
    if not mask.any():
        return False

    now = as_of_date.normalize() + pd.Timedelta(hours=12)
    event_type, default_detail = ACTIONABLE_STATUSES[new_status]
    workflow.loc[mask, "status"] = new_status
    workflow.loc[mask, "last_seen_at"] = as_of_date.normalize()

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

    session_state[RECOMMENDATION_STATE_KEY] = workflow
    details = notes.strip() if notes and notes.strip() else default_detail
    log_recommendation_event(session_state, recommendation_id, event_type, actor, details, now)
    return True
