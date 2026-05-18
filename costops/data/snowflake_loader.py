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
