from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_STATE_DIR = ROOT / "runtime_state"
RECOMMENDATIONS_STATE_FILE = RUNTIME_STATE_DIR / "recommendations.csv"
EVENTS_STATE_FILE = RUNTIME_STATE_DIR / "recommendation_events.csv"
SCAN_RUNS_STATE_FILE = RUNTIME_STATE_DIR / "scan_runs.csv"
RECOMMENDATION_STATE_KEY = "recommendations_workflow"
EVENT_STATE_KEY = "recommendation_events_workflow"
SCAN_RUN_STATE_KEY = "scan_runs_workflow"
RECOMMENDATION_DATE_COLUMNS = ["first_seen_at", "last_seen_at", "accepted_at", "implemented_at"]
EVENT_DATE_COLUMNS = ["event_ts"]
SCAN_RUN_DATE_COLUMNS = ["started_at", "completed_at"]

ACTIONABLE_STATUSES = {
    "Selected": ("SELECTED", "Selected for active review."),
    "Accepted": ("ACCEPTED", "Accepted for implementation planning."),
    "Deferred": ("DEFERRED", "Deferred for a future optimization cycle."),
    "Rejected": ("REJECTED", "Rejected after review."),
    "Implemented": ("IMPLEMENTED", "Marked as implemented by the owner."),
    "Realized": ("SAVINGS_REALIZED", "Validated as realized savings."),
}


def initialize_session_store(session_state, recommendations, recommendation_events, scan_runs=None):
    if RECOMMENDATION_STATE_KEY not in session_state:
        session_state[RECOMMENDATION_STATE_KEY] = _load_state_file(
            RECOMMENDATIONS_STATE_FILE,
            recommendations,
            RECOMMENDATION_DATE_COLUMNS,
        )
    if EVENT_STATE_KEY not in session_state:
        session_state[EVENT_STATE_KEY] = _load_state_file(EVENTS_STATE_FILE, recommendation_events, EVENT_DATE_COLUMNS)
    if scan_runs is not None and SCAN_RUN_STATE_KEY not in session_state:
        session_state[SCAN_RUN_STATE_KEY] = _load_state_file(SCAN_RUNS_STATE_FILE, scan_runs, SCAN_RUN_DATE_COLUMNS)


def _load_state_file(path, fallback, date_columns):
    if not path.exists():
        return fallback.copy()
    return pd.read_csv(path, parse_dates=date_columns)


def persist_session_store(session_state):
    RUNTIME_STATE_DIR.mkdir(exist_ok=True)
    session_state[RECOMMENDATION_STATE_KEY].to_csv(RECOMMENDATIONS_STATE_FILE, index=False)
    session_state[EVENT_STATE_KEY].to_csv(EVENTS_STATE_FILE, index=False)
    if SCAN_RUN_STATE_KEY in session_state:
        session_state[SCAN_RUN_STATE_KEY].to_csv(SCAN_RUNS_STATE_FILE, index=False)


def recommendations_frame(session_state):
    return session_state[RECOMMENDATION_STATE_KEY]


def recommendation_events_frame(session_state):
    return session_state[EVENT_STATE_KEY]


def scan_runs_frame(session_state):
    return session_state[SCAN_RUN_STATE_KEY]


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


def merge_scan_results(session_state, scan_result, actor, event_ts):
    generated = scan_result["recommendations"].copy()
    workflow = session_state[RECOMMENDATION_STATE_KEY].copy()

    if not generated.empty:
        existing_ids = set(workflow["recommendation_id"].astype(str))
        generated_ids = set(generated["recommendation_id"].astype(str))
        preserved_columns = ["status", "accepted_at", "implemented_at", "realized_monthly_savings", "owner", "team"]

        for rec_id in existing_ids & generated_ids:
            existing_row = workflow.loc[workflow["recommendation_id"] == rec_id].iloc[0]
            for column in preserved_columns:
                if column in generated and column in existing_row:
                    generated.loc[generated["recommendation_id"] == rec_id, column] = existing_row[column]
            generated.loc[generated["recommendation_id"] == rec_id, "first_seen_at"] = existing_row["first_seen_at"]

        workflow = workflow[~workflow["recommendation_id"].isin(generated_ids)]
        workflow = pd.concat([workflow, generated], ignore_index=True)
        session_state[RECOMMENDATION_STATE_KEY] = workflow

    scan_runs = session_state[SCAN_RUN_STATE_KEY].copy()
    scan_run = pd.DataFrame([scan_result["scan_run"]])
    session_state[SCAN_RUN_STATE_KEY] = pd.concat([scan_runs, scan_run], ignore_index=True)

    scan_id = scan_result["scan_run"]["scan_id"]
    log_recommendation_event(
        session_state,
        "",
        "SCAN_COMPLETED",
        actor,
        f"{scan_id} completed with {len(generated)} recommendations generated from analysis runner.",
        event_ts,
    )
    persist_session_store(session_state)
