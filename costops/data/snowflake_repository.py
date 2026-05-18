from pathlib import Path

from costops.data.snowflake_loader import connect


ROOT = Path(__file__).resolve().parents[2]
APP_SQL_DIR = ROOT / "sql" / "app"


def execute_sql_file(config, path):
    sql_text = Path(path).read_text()

    with connect(config) as conn:
        conn.execute_string(sql_text)


def initialize_app_schema(config):
    for sql_file in sorted(APP_SQL_DIR.glob("*.sql")):
        execute_sql_file(config, sql_file)


def update_recommendation_status(config, recommendation_id, new_status, actor, details):
    with connect(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "CALL COSTOPS_APP.UPDATE_RECOMMENDATION_STATUS(%s, %s, %s, %s)",
                (recommendation_id, new_status, actor, details),
            )
            return cursor.fetchone()[0]


def log_sql_copied(config, recommendation_id, actor):
    with connect(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "CALL COSTOPS_APP.LOG_SQL_COPIED(%s, %s)",
                (recommendation_id, actor),
            )
            return cursor.fetchone()[0]
