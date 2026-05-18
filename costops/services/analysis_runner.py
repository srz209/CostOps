from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1

import pandas as pd


DEFAULT_OWNER = "Unassigned"
DEFAULT_TEAM = "Platform"


@dataclass(frozen=True)
class AnalysisConfig:
    credit_price: float = 3.0
    lookback_days: int = 30
    scan_scope: str = "Full"
    initiated_by: str = "system"
    source_mode: str = "Sample data"


def run_environment_analysis(warehouses, workloads, storage, tasks, config=None, as_of_ts=None):
    config = config or AnalysisConfig()
    as_of_ts = pd.Timestamp(as_of_ts or datetime.now()).tz_localize(None)
    scan_id = f"SCAN-{as_of_ts.strftime('%Y%m%d-%H%M%S')}"

    recommendations = pd.concat(
        [
            warehouse_recommendations(warehouses, scan_id, as_of_ts),
            workload_recommendations(workloads, scan_id, as_of_ts),
            task_recommendations(tasks, scan_id, as_of_ts),
            storage_recommendations(storage, scan_id, as_of_ts),
        ],
        ignore_index=True,
    )

    if recommendations.empty:
        recommendations = empty_recommendations()

    findings = build_findings(scan_id, recommendations)
    credits_estimated = estimate_scan_credits(warehouses, workloads, storage, tasks)
    scan_run = {
        "scan_id": scan_id,
        "scan_type": "Ad hoc" if config.initiated_by != "system" else "Scheduled",
        "scan_scope": config.scan_scope,
        "started_at": as_of_ts - pd.Timedelta(minutes=4),
        "completed_at": as_of_ts,
        "status": "SUCCEEDED",
        "frequency": "Manual",
        "lookback_days": config.lookback_days,
        "initiated_by": config.initiated_by,
        "credits_estimated": credits_estimated,
        "recommendations_found": int(len(recommendations)),
        "recommendations_new": int(len(recommendations)),
        "recommendations_updated": 0,
        "error_message": "",
        "source_mode": config.source_mode,
        "identified_monthly_savings": float(recommendations["projected_monthly_savings"].sum()),
        "scan_cost_usd": round(credits_estimated * config.credit_price, 2),
    }
    return {"scan_run": scan_run, "recommendations": recommendations, "findings": findings}


def empty_recommendations():
    return pd.DataFrame(
        columns=[
            "recommendation_id",
            "scan_run_id",
            "category",
            "subcategory",
            "title",
            "object_name",
            "severity",
            "confidence",
            "projected_daily_savings",
            "projected_monthly_savings",
            "projected_annual_savings",
            "realized_monthly_savings",
            "owner",
            "team",
            "first_seen_at",
            "last_seen_at",
            "accepted_at",
            "implemented_at",
            "risk",
            "effort",
            "status",
            "generated_sql",
            "evidence",
        ]
    )


def recommendation_row(
    rule_id,
    scan_id,
    category,
    subcategory,
    title,
    object_name,
    severity,
    confidence,
    monthly_savings,
    risk,
    effort,
    generated_sql,
    evidence,
    as_of_ts,
    owner=DEFAULT_OWNER,
    team=DEFAULT_TEAM,
):
    monthly_savings = max(float(monthly_savings), 0.0)
    rec_id = stable_recommendation_id(rule_id, object_name)
    return {
        "recommendation_id": rec_id,
        "scan_run_id": scan_id,
        "category": category,
        "subcategory": subcategory,
        "title": title,
        "object_name": object_name,
        "severity": severity,
        "confidence": round(float(confidence), 2),
        "projected_daily_savings": round(monthly_savings / 30, 2),
        "projected_monthly_savings": round(monthly_savings, 2),
        "projected_annual_savings": round(monthly_savings * 12, 2),
        "realized_monthly_savings": 0,
        "owner": owner,
        "team": team,
        "first_seen_at": as_of_ts.normalize(),
        "last_seen_at": as_of_ts.normalize(),
        "accepted_at": pd.NaT,
        "implemented_at": pd.NaT,
        "risk": risk,
        "effort": effort,
        "status": "Proposed",
        "generated_sql": generated_sql,
        "evidence": evidence,
    }


def stable_recommendation_id(rule_id, object_name):
    digest = sha1(f"{rule_id}|{object_name}".encode("utf-8")).hexdigest()[:8].upper()
    return f"{rule_id}-{digest}"


def warehouse_recommendations(warehouses, scan_id, as_of_ts):
    if warehouses is None or warehouses.empty:
        return empty_recommendations()

    df = warehouses.copy()
    for column in ["cost_usd", "utilization_pct", "queued_seconds", "resumes"]:
        df[column] = pd.to_numeric(df.get(column, 0), errors="coerce").fillna(0)

    grouped = (
        df.groupby("warehouse", dropna=False)
        .agg(
            monthly_cost=("cost_usd", "sum"),
            avg_utilization=("utilization_pct", "mean"),
            queued_seconds=("queued_seconds", "sum"),
            avg_resumes=("resumes", "mean"),
            days_observed=("date", "nunique") if "date" in df else ("warehouse", "count"),
        )
        .reset_index()
    )
    rows = []
    for item in grouped.itertuples(index=False):
        warehouse = str(item.warehouse)
        projected_monthly = item.monthly_cost * (30 / max(item.days_observed, 1))
        if projected_monthly >= 750 and item.avg_utilization < 25 and item.queued_seconds < 120:
            rows.append(
                recommendation_row(
                    "WH_OVERSIZED",
                    scan_id,
                    "Warehouse",
                    "Oversized warehouse",
                    f"Downsize {warehouse} after validating concurrency",
                    warehouse,
                    "High" if projected_monthly >= 2500 else "Medium",
                    0.84 if item.avg_utilization < 20 else 0.76,
                    projected_monthly * 0.4,
                    "Medium",
                    "Medium",
                    f"-- Review query concurrency, then test a one-size reduction for {warehouse}.",
                    (
                        f"{warehouse} averaged {item.avg_utilization:.0f}% utilization with "
                        f"{item.queued_seconds:.0f}s queued during the lookback window."
                    ),
                    as_of_ts,
                    owner="Taylor Morgan",
                    team="Data Platform",
                )
            )
        if item.avg_resumes >= 35:
            rows.append(
                recommendation_row(
                    "WH_AUTO_SUSPEND_HIGH",
                    scan_id,
                    "Warehouse",
                    "Auto-suspend tuning",
                    f"Reduce idle runtime for {warehouse}",
                    warehouse,
                    "Medium",
                    0.72,
                    projected_monthly * 0.18,
                    "Low",
                    "Low",
                    f"ALTER WAREHOUSE {warehouse} SET AUTO_SUSPEND = 60;",
                    f"{warehouse} resumed about {item.avg_resumes:.0f} times per observed day, indicating idle churn.",
                    as_of_ts,
                    owner="Taylor Morgan",
                    team="Data Platform",
                )
            )

    return pd.DataFrame(rows) if rows else empty_recommendations()


def workload_recommendations(workloads, scan_id, as_of_ts):
    if workloads is None or workloads.empty:
        return empty_recommendations()

    df = workloads.copy()
    for column in ["cost_usd", "query_count", "avg_runtime_seconds", "gb_scanned", "spill_gb"]:
        df[column] = pd.to_numeric(df.get(column, 0), errors="coerce").fillna(0)

    rows = []
    for item in df.itertuples(index=False):
        workload = str(item.workload)
        if item.gb_scanned >= 2000 and item.avg_runtime_seconds >= 300:
            rows.append(
                recommendation_row(
                    "PIPELINE_FULL_REFRESH",
                    scan_id,
                    "Query",
                    "Full refresh pattern",
                    f"Convert {workload} to incremental processing",
                    workload,
                    "Critical" if item.cost_usd >= 5000 else "High",
                    0.82,
                    item.cost_usd * 0.55,
                    "Medium",
                    "High",
                    "-- Review model logic and add incremental predicates before the nightly rebuild.",
                    (
                        f"{workload} scanned {item.gb_scanned:,.0f} GB with average runtime "
                        f"of {item.avg_runtime_seconds:,.0f}s."
                    ),
                    as_of_ts,
                    owner="Riley Chen",
                    team="Analytics Engineering",
                )
            )
        if item.spill_gb >= 3:
            rows.append(
                recommendation_row(
                    "QUERY_SPILLAGE",
                    scan_id,
                    "Query",
                    "High disk spillage",
                    f"Reduce spill and scan volume for {workload}",
                    workload,
                    "High",
                    0.74,
                    item.cost_usd * 0.25,
                    "Medium",
                    "Medium",
                    "-- Inspect query profile for spilled joins, large sorts, and missing filters.",
                    f"{workload} spilled {item.spill_gb:,.1f} GB during the lookback window.",
                    as_of_ts,
                    owner="Riley Chen",
                    team="Analytics Engineering",
                )
            )

    return pd.DataFrame(rows) if rows else empty_recommendations()


def task_recommendations(tasks, scan_id, as_of_ts):
    if tasks is None or tasks.empty:
        return empty_recommendations()

    df = tasks.copy()
    for column in ["executions_7d", "failures_7d", "avg_runtime_seconds", "estimated_compute_cost"]:
        df[column] = pd.to_numeric(df.get(column, 0), errors="coerce").fillna(0)

    rows = []
    for item in df.itertuples(index=False):
        task_name = str(item.task_name)
        if item.executions_7d >= 300:
            rows.append(
                recommendation_row(
                    "TASK_FREQUENCY_HIGH",
                    scan_id,
                    "Task",
                    "Task frequency",
                    f"Reduce schedule frequency for {task_name}",
                    task_name,
                    "High" if item.estimated_compute_cost >= 900 else "Medium",
                    0.8,
                    item.estimated_compute_cost * 0.45,
                    "Low",
                    "Low",
                    f"-- Review downstream freshness needs, then reduce the schedule for {task_name}.",
                    (
                        f"{task_name} ran {item.executions_7d:,.0f} times in seven days with "
                        f"estimated monthly compute cost of ${item.estimated_compute_cost:,.0f}."
                    ),
                    as_of_ts,
                    owner="Morgan Brooks",
                    team="Business Intelligence",
                )
            )
        if item.failures_7d >= 5:
            rows.append(
                recommendation_row(
                    "TASK_FAILURE_CHURN",
                    scan_id,
                    "Task",
                    "Failure churn",
                    f"Pause or repair failing task {task_name}",
                    task_name,
                    "Medium",
                    0.7,
                    item.estimated_compute_cost * 0.2,
                    "Low",
                    "Medium",
                    f"-- Suspend {task_name} until owner validates failure cause.",
                    f"{task_name} failed {item.failures_7d:,.0f} times in seven days.",
                    as_of_ts,
                    owner="Morgan Brooks",
                    team="Business Intelligence",
                )
            )

    return pd.DataFrame(rows) if rows else empty_recommendations()


def storage_recommendations(storage, scan_id, as_of_ts):
    if storage is None or storage.empty:
        return empty_recommendations()

    df = storage.copy()
    for column in ["monthly_storage_cost", "last_queried_days", "retention_days", "access_count_30d"]:
        df[column] = pd.to_numeric(df.get(column, 0), errors="coerce").fillna(0)

    rows = []
    for item in df.itertuples(index=False):
        object_name = str(item.object_name)
        if item.last_queried_days >= 90 and item.access_count_30d == 0:
            rows.append(
                recommendation_row(
                    "STORAGE_STALE_OBJECT",
                    scan_id,
                    "Storage",
                    "Stale object",
                    f"Archive or drop stale object {object_name}",
                    object_name,
                    "Medium",
                    0.78,
                    item.monthly_storage_cost,
                    "Medium",
                    "Medium",
                    f"-- Validate ownership, then archive or drop {object_name}.",
                    f"{object_name} has not been queried in {item.last_queried_days:,.0f} days and has no 30-day access.",
                    as_of_ts,
                    owner="Avery Patel",
                    team="Data Governance",
                )
            )
        if str(getattr(item, "database_name", "")).upper().startswith("DEV") and getattr(item, "clone_group", ""):
            rows.append(
                recommendation_row(
                    "DEV_CLONE_DUPLICATION",
                    scan_id,
                    "Storage",
                    "Dev / QA duplication",
                    f"Convert {object_name} to governed zero-copy clone lifecycle",
                    object_name,
                    "Low",
                    0.68,
                    item.monthly_storage_cost * 0.4,
                    "Low",
                    "Low",
                    f"-- Replace independent dev refreshes with zero-copy clone lifecycle for {object_name}.",
                    f"{object_name} belongs to clone group {item.clone_group} and appears in a development database.",
                    as_of_ts,
                    owner="Avery Patel",
                    team="Data Governance",
                )
            )

    return pd.DataFrame(rows) if rows else empty_recommendations()


def build_findings(scan_id, recommendations):
    if recommendations.empty:
        return pd.DataFrame(
            columns=[
                "finding_id",
                "scan_run_id",
                "recommendation_id",
                "finding_category",
                "object_name",
                "severity",
                "confidence_score",
                "projected_monthly_savings",
                "finding_payload",
            ]
        )

    findings = recommendations[
        [
            "recommendation_id",
            "category",
            "object_name",
            "severity",
            "confidence",
            "projected_monthly_savings",
            "evidence",
        ]
    ].copy()
    findings["scan_run_id"] = scan_id
    findings["finding_id"] = findings.apply(
        lambda row: f"FIND-{sha1((scan_id + row['recommendation_id']).encode('utf-8')).hexdigest()[:10].upper()}",
        axis=1,
    )
    findings["finding_category"] = findings["category"]
    findings["confidence_score"] = findings["confidence"]
    findings["finding_payload"] = findings["evidence"].apply(lambda value: {"evidence": value})
    return findings[
        [
            "finding_id",
            "scan_run_id",
            "recommendation_id",
            "finding_category",
            "object_name",
            "severity",
            "confidence_score",
            "projected_monthly_savings",
            "finding_payload",
        ]
    ]


def estimate_scan_credits(warehouses, workloads, storage, tasks):
    source_rows = sum(len(frame) for frame in [warehouses, workloads, storage, tasks] if frame is not None)
    return round(max(0.08, min(1.5, 0.08 + source_rows * 0.0025)), 2)
