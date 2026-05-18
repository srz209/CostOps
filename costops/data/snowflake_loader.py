import pandas as pd
import snowflake.connector


WAREHOUSE_METERING_SQL = """
SELECT
    DATE_TRUNC('day', START_TIME)::DATE AS USAGE_DATE,
    WAREHOUSE_NAME,
    SUM(CREDITS_USED) AS CREDITS_USED
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD('day', -%s, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY 1 DESC, 3 DESC
"""

QUERY_WORKLOAD_SQL = """
SELECT
    COALESCE(QUERY_TAG, QUERY_TYPE, 'UNTAGGED') AS WORKLOAD,
    WAREHOUSE_NAME,
    COUNT(*) AS QUERY_COUNT,
    AVG(TOTAL_ELAPSED_TIME) / 1000 AS AVG_RUNTIME_SECONDS,
    SUM(BYTES_SCANNED) / POWER(1024, 3) AS GB_SCANNED,
    SUM(BYTES_SPILLED_TO_LOCAL_STORAGE + BYTES_SPILLED_TO_REMOTE_STORAGE) / POWER(1024, 3) AS SPILL_GB,
    QUERY_TYPE AS CATEGORY
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -%s, CURRENT_TIMESTAMP())
  AND WAREHOUSE_NAME IS NOT NULL
  AND EXECUTION_STATUS = 'SUCCESS'
GROUP BY 1, 2, 7
ORDER BY GB_SCANNED DESC
LIMIT 500
"""

TASK_HISTORY_SQL = """
SELECT
    NAME AS TASK_NAME,
    DATABASE_NAME,
    SCHEMA_NAME,
    WAREHOUSE_NAME AS WAREHOUSE,
    'Observed schedule' AS SCHEDULE,
    COUNT(*) AS EXECUTIONS_7D,
    SUM(IFF(STATE = 'FAILED', 1, 0)) AS FAILURES_7D,
    AVG(DATEDIFF('second', QUERY_START_TIME, COMPLETED_TIME)) AS AVG_RUNTIME_SECONDS,
    0 AS CLOUD_SERVICES_CREDITS,
    0 AS ESTIMATED_COMPUTE_COST,
    MAX(STATE) AS LAST_STATE,
    '' AS RECOMMENDATION
FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY
WHERE SCHEDULED_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1, 2, 3, 4
ORDER BY EXECUTIONS_7D DESC
LIMIT 500
"""

STORAGE_OBJECT_SQL = """
SELECT
    TABLE_CATALOG || '.' || TABLE_SCHEMA || '.' || TABLE_NAME AS OBJECT_NAME,
    TABLE_CATALOG AS DATABASE_NAME,
    TABLE_SCHEMA AS SCHEMA_NAME,
    'TABLE' AS OBJECT_TYPE,
    ACTIVE_BYTES / POWER(1024, 3) AS SIZE_GB,
    ACTIVE_BYTES / POWER(1024, 4) * 23 AS MONTHLY_STORAGE_COST,
    999 AS LAST_QUERIED_DAYS,
    1 AS RETENTION_DAYS,
    0 AS ACCESS_COUNT_30D,
    '' AS CLONE_GROUP,
    'Storage metrics' AS CLASSIFICATION
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLE_STORAGE_METRICS
WHERE DELETED = FALSE
ORDER BY ACTIVE_BYTES DESC
LIMIT 500
"""


def connect(config):
    connection_args = {
        "account": config.get("account"),
        "user": config.get("user"),
        "role": config.get("role"),
        "warehouse": config.get("warehouse"),
        "database": config.get("database"),
        "schema": config.get("schema"),
    }
    connection_args = {key: value for key, value in connection_args.items() if value}

    if config.get("password"):
        connection_args["password"] = config["password"]
    if config.get("authenticator"):
        connection_args["authenticator"] = config["authenticator"]

    return snowflake.connector.connect(**connection_args)


def test_connection(config):
    with connect(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    CURRENT_ACCOUNT() AS account_name,
                    CURRENT_REGION() AS region_name,
                    CURRENT_VERSION() AS snowflake_version
                """
            )
            row = cursor.fetchone()
    return {
        "account": row[0],
        "region": row[1],
        "version": row[2],
    }


def load_warehouse_metering_history(config, lookback_days=30, credit_price=3.0):
    with connect(config) as conn:
        df = pd.read_sql(WAREHOUSE_METERING_SQL, conn, params=(lookback_days,))

    if df.empty:
        return pd.DataFrame(
            columns=["date", "warehouse", "credits", "cost_usd", "utilization_pct", "queued_seconds", "resumes"]
        )

    df.columns = [column.lower() for column in df.columns]
    df = df.rename(
        columns={
            "usage_date": "date",
            "warehouse_name": "warehouse",
            "credits_used": "credits",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    df["cost_usd"] = df["credits"].astype(float) * credit_price
    df["utilization_pct"] = 0
    df["queued_seconds"] = 0
    df["resumes"] = 0
    return df[["date", "warehouse", "credits", "cost_usd", "utilization_pct", "queued_seconds", "resumes"]]


def load_query_workloads(config, lookback_days=30, credit_price=3.0):
    with connect(config) as conn:
        df = pd.read_sql(QUERY_WORKLOAD_SQL, conn, params=(lookback_days,))

    if df.empty:
        return pd.DataFrame(
            columns=["workload", "cost_usd", "warehouse", "query_count", "avg_runtime_seconds", "gb_scanned", "spill_gb", "category"]
        )

    df.columns = [column.lower() for column in df.columns]
    df["cost_usd"] = 0.0
    return df[["workload", "cost_usd", "warehouse_name", "query_count", "avg_runtime_seconds", "gb_scanned", "spill_gb", "category"]].rename(
        columns={"warehouse_name": "warehouse"}
    )


def load_task_history(config):
    with connect(config) as conn:
        df = pd.read_sql(TASK_HISTORY_SQL, conn)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "task_name",
                "database_name",
                "schema_name",
                "warehouse",
                "schedule",
                "executions_7d",
                "failures_7d",
                "avg_runtime_seconds",
                "cloud_services_credits",
                "estimated_compute_cost",
                "last_state",
                "recommendation",
            ]
        )

    df.columns = [column.lower() for column in df.columns]
    return df


def load_storage_objects(config):
    with connect(config) as conn:
        df = pd.read_sql(STORAGE_OBJECT_SQL, conn)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "object_name",
                "database_name",
                "schema_name",
                "object_type",
                "size_gb",
                "monthly_storage_cost",
                "last_queried_days",
                "retention_days",
                "access_count_30d",
                "clone_group",
                "classification",
            ]
        )

    df.columns = [column.lower() for column in df.columns]
    return df


def load_account_usage_snapshot(config, lookback_days=30, credit_price=3.0):
    return {
        "warehouses": load_warehouse_metering_history(config, lookback_days, credit_price),
        "workloads": load_query_workloads(config, lookback_days, credit_price),
        "tasks": load_task_history(config),
        "storage": load_storage_objects(config),
    }
