from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA_DIR = ROOT / "sample_data"


def load_sample_data():
    recommendations = pd.read_csv(
        SAMPLE_DATA_DIR / "recommendations.csv",
        parse_dates=["first_seen_at", "last_seen_at", "accepted_at", "implemented_at"],
    )
    recommendation_events = pd.read_csv(SAMPLE_DATA_DIR / "recommendation_events.csv", parse_dates=["event_ts"])
    scan_runs = pd.read_csv(SAMPLE_DATA_DIR / "scan_runs.csv", parse_dates=["started_at", "completed_at"])
    warehouses = pd.read_csv(SAMPLE_DATA_DIR / "warehouse_daily.csv", parse_dates=["date"])
    workloads = pd.read_csv(SAMPLE_DATA_DIR / "workloads.csv")
    storage = pd.read_csv(SAMPLE_DATA_DIR / "storage_objects.csv")
    tasks = pd.read_csv(SAMPLE_DATA_DIR / "task_runs.csv")
    return {
        "recommendations": recommendations,
        "recommendation_events": recommendation_events,
        "scan_runs": scan_runs,
        "warehouses": warehouses,
        "workloads": workloads,
        "storage": storage,
        "tasks": tasks,
    }
