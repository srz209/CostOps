from pathlib import Path
import json

import pandas as pd

from costops.data.recommendation_store import ensure_recommendation_columns
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


def persist_analysis_result(config, scan_result):
    recommendations = ensure_recommendation_columns(scan_result["recommendations"])
    with connect(config) as conn:
        with conn.cursor() as cursor:
            upsert_scan_run(cursor, scan_result["scan_run"])
            for _, recommendation in recommendations.iterrows():
                upsert_recommendation(cursor, recommendation)
            for _, finding in scan_result["findings"].iterrows():
                insert_finding(cursor, finding)
        conn.commit()


def persist_enterprise_control_plane(config, settings, enterprise_audit_events):
    user_directory = settings.get("user_directory", [])
    with connect(config) as conn:
        with conn.cursor() as cursor:
            upsert_enterprise_config_snapshot(cursor, settings)
            replace_enterprise_user_directory(cursor, user_directory)
            sync_enterprise_config_audit_events(cursor, enterprise_audit_events)
        conn.commit()


def upsert_scan_run(cursor, scan_run):
    cursor.execute(
        """
        MERGE INTO COSTOPS_APP.SCAN_RUN target
        USING (
            SELECT
                %s AS scan_run_id,
                %s AS scan_type,
                %s AS scan_scope,
                %s AS schedule_name,
                %s AS started_at,
                %s AS completed_at,
                %s AS scan_status,
                %s AS credits_estimated,
                %s AS scan_cost_usd,
                %s AS recommendations_found,
                %s AS recommendations_new,
                %s AS recommendations_updated,
                %s AS identified_monthly_savings,
                %s AS initiated_by,
                %s AS error_message
        ) source
        ON target.scan_run_id = source.scan_run_id
        WHEN MATCHED THEN UPDATE SET
            completed_at = source.completed_at,
            scan_status = source.scan_status,
            schedule_name = source.schedule_name,
            credits_estimated = source.credits_estimated,
            scan_cost_usd = source.scan_cost_usd,
            recommendations_found = source.recommendations_found,
            recommendations_new = source.recommendations_new,
            recommendations_updated = source.recommendations_updated,
            identified_monthly_savings = source.identified_monthly_savings,
            error_message = source.error_message
        WHEN NOT MATCHED THEN INSERT (
            scan_run_id,
            scan_type,
            scan_scope,
            schedule_name,
            started_at,
            completed_at,
            scan_status,
            credits_estimated,
            scan_cost_usd,
            recommendations_found,
            recommendations_new,
            recommendations_updated,
            identified_monthly_savings,
            initiated_by,
            error_message
        )
        VALUES (
            source.scan_run_id,
            source.scan_type,
            source.scan_scope,
            source.schedule_name,
            source.started_at,
            source.completed_at,
            source.scan_status,
            source.credits_estimated,
            source.scan_cost_usd,
            source.recommendations_found,
            source.recommendations_new,
            source.recommendations_updated,
            source.identified_monthly_savings,
            source.initiated_by,
            source.error_message
        )
        """,
        (
            scan_run["scan_id"],
            scan_run["scan_type"],
            scan_run["scan_scope"],
            scan_run.get("schedule_name"),
            clean_value(scan_run["started_at"]),
            clean_value(scan_run["completed_at"]),
            scan_run["status"],
            scan_run["credits_estimated"],
            scan_run["scan_cost_usd"],
            scan_run["recommendations_found"],
            scan_run["recommendations_new"],
            scan_run["recommendations_updated"],
            scan_run["identified_monthly_savings"],
            scan_run["initiated_by"],
            scan_run["error_message"],
        ),
    )


def upsert_recommendation(cursor, recommendation):
    cursor.execute(
        """
        MERGE INTO COSTOPS_APP.COST_RECOMMENDATION target
        USING (
            SELECT
                %s AS recommendation_id,
                %s AS scan_run_id,
                %s AS recommendation_category,
                %s AS recommendation_subcategory,
                %s AS title,
                %s AS object_name,
                %s AS severity,
                %s AS confidence_score,
                %s AS projected_daily_savings,
                %s AS projected_monthly_savings,
                %s AS projected_annual_savings,
                %s AS implementation_risk,
                %s AS implementation_effort,
                %s AS recommendation_status,
                %s AS owner_name,
                %s AS team_name,
                %s AS owner_role,
                %s AS due_date,
                %s AS generated_sql,
                %s AS evidence,
                %s AS work_notes,
                %s AS first_seen_at,
                %s AS last_seen_at,
                %s AS last_note_at,
                %s AS assignment_updated_at
        ) source
        ON target.recommendation_id = source.recommendation_id
        WHEN MATCHED THEN UPDATE SET
            scan_run_id = source.scan_run_id,
            recommendation_category = source.recommendation_category,
            recommendation_subcategory = source.recommendation_subcategory,
            title = source.title,
            object_name = source.object_name,
            severity = source.severity,
            confidence_score = source.confidence_score,
            projected_daily_savings = source.projected_daily_savings,
            projected_monthly_savings = source.projected_monthly_savings,
            projected_annual_savings = source.projected_annual_savings,
            implementation_risk = source.implementation_risk,
            implementation_effort = source.implementation_effort,
            owner_name = source.owner_name,
            team_name = source.team_name,
            owner_role = source.owner_role,
            due_date = source.due_date,
            generated_sql = source.generated_sql,
            evidence = source.evidence,
            work_notes = source.work_notes,
            last_seen_at = source.last_seen_at,
            last_note_at = source.last_note_at,
            assignment_updated_at = source.assignment_updated_at,
            updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (
            recommendation_id,
            scan_run_id,
            recommendation_category,
            recommendation_subcategory,
            title,
            object_name,
            severity,
            confidence_score,
            projected_daily_savings,
            projected_monthly_savings,
            projected_annual_savings,
            implementation_risk,
            implementation_effort,
            recommendation_status,
            owner_name,
            team_name,
            owner_role,
            due_date,
            generated_sql,
            evidence,
            work_notes,
            first_seen_at,
            last_seen_at,
            last_note_at,
            assignment_updated_at
        )
        VALUES (
            source.recommendation_id,
            source.scan_run_id,
            source.recommendation_category,
            source.recommendation_subcategory,
            source.title,
            source.object_name,
            source.severity,
            source.confidence_score,
            source.projected_daily_savings,
            source.projected_monthly_savings,
            source.projected_annual_savings,
            source.implementation_risk,
            source.implementation_effort,
            source.recommendation_status,
            source.owner_name,
            source.team_name,
            source.owner_role,
            source.due_date,
            source.generated_sql,
            source.evidence,
            source.work_notes,
            source.first_seen_at,
            source.last_seen_at,
            source.last_note_at,
            source.assignment_updated_at
        )
        """,
        (
            recommendation["recommendation_id"],
            recommendation.get("scan_run_id"),
            recommendation["category"],
            recommendation["subcategory"],
            recommendation["title"],
            recommendation["object_name"],
            recommendation["severity"],
            clean_value(recommendation["confidence"]),
            clean_value(recommendation["projected_daily_savings"]),
            clean_value(recommendation["projected_monthly_savings"]),
            clean_value(recommendation["projected_annual_savings"]),
            recommendation["risk"],
            recommendation["effort"],
            recommendation["status"],
            recommendation["owner"],
            recommendation["team"],
            recommendation["role"],
            clean_value(recommendation["due_date"]),
            recommendation["generated_sql"],
            recommendation["evidence"],
            recommendation.get("work_notes", ""),
            clean_value(recommendation["first_seen_at"]),
            clean_value(recommendation["last_seen_at"]),
            clean_value(recommendation.get("last_note_at")),
            clean_value(recommendation.get("assignment_updated_at")),
        ),
    )


def insert_finding(cursor, finding):
    cursor.execute(
        """
        INSERT INTO COSTOPS_APP.SCAN_FINDING (
            finding_id,
            scan_run_id,
            recommendation_id,
            finding_category,
            object_name,
            severity,
            confidence_score,
            projected_monthly_savings,
            finding_payload
        )
        SELECT %s, %s, %s, %s, %s, %s, %s, %s, PARSE_JSON(%s)
        """,
        (
            finding["finding_id"],
            finding["scan_run_id"],
            finding["recommendation_id"],
            finding["finding_category"],
            finding["object_name"],
            finding["severity"],
            clean_value(finding["confidence_score"]),
            clean_value(finding["projected_monthly_savings"]),
            json.dumps(finding["finding_payload"]),
        ),
    )


def upsert_enterprise_config_snapshot(cursor, settings):
    cursor.execute(
        """
        MERGE INTO COSTOPS_APP.ENTERPRISE_CONFIG_SNAPSHOT target
        USING (
            SELECT
                %s AS config_scope,
                %s AS production_account,
                %s AS production_region,
                %s AS app_instance,
                %s AS billing_scope,
                %s AS rbac_status,
                %s AS environment_status,
                %s AS persistence_status,
                %s AS sso_status,
                %s AS sla_status,
                PARSE_JSON(%s) AS config_payload
        ) source
        ON target.config_scope = source.config_scope
        WHEN MATCHED THEN UPDATE SET
            production_account = source.production_account,
            production_region = source.production_region,
            app_instance = source.app_instance,
            billing_scope = source.billing_scope,
            rbac_status = source.rbac_status,
            environment_status = source.environment_status,
            persistence_status = source.persistence_status,
            sso_status = source.sso_status,
            sla_status = source.sla_status,
            config_payload = source.config_payload,
            updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (
            config_scope,
            production_account,
            production_region,
            app_instance,
            billing_scope,
            rbac_status,
            environment_status,
            persistence_status,
            sso_status,
            sla_status,
            config_payload
        )
        VALUES (
            source.config_scope,
            source.production_account,
            source.production_region,
            source.app_instance,
            source.billing_scope,
            source.rbac_status,
            source.environment_status,
            source.persistence_status,
            source.sso_status,
            source.sla_status,
            source.config_payload
        )
        """,
        (
            "enterprise",
            settings.get("enterprise_prod_account", ""),
            settings.get("enterprise_prod_region", ""),
            settings.get("enterprise_app_instance", ""),
            settings.get("enterprise_billing_scope", ""),
            settings.get("enterprise_rbac_status", "Not configured"),
            settings.get("enterprise_linked_environments_status", "Not configured"),
            settings.get("enterprise_persistence_status", "Not configured"),
            settings.get("enterprise_sso_status", "Not configured"),
            settings.get("enterprise_sla_status", "Not configured"),
            json.dumps(settings, default=str),
        ),
    )


def replace_enterprise_user_directory(cursor, user_directory):
    cursor.execute("DELETE FROM COSTOPS_APP.ENTERPRISE_USER_DIRECTORY")
    for entry in user_directory:
        owner_name = (entry.get("owner") or "").strip()
        if not owner_name:
            continue
        cursor.execute(
            """
            INSERT INTO COSTOPS_APP.ENTERPRISE_USER_DIRECTORY (
                owner_name,
                team_name,
                business_role,
                email,
                access_role
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                owner_name,
                (entry.get("team") or "").strip(),
                (entry.get("role") or "").strip(),
                (entry.get("email") or "").strip(),
                (entry.get("access_role") or "").strip(),
            ),
        )


def sync_enterprise_config_audit_events(cursor, enterprise_audit_events):
    audit_rows = enterprise_audit_events.to_dict("records") if hasattr(enterprise_audit_events, "to_dict") else []
    for event in audit_rows:
        cursor.execute(
            """
            MERGE INTO COSTOPS_APP.ENTERPRISE_CONFIG_AUDIT_LOG target
            USING (
                SELECT
                    %s AS event_id,
                    %s AS event_ts,
                    %s AS area,
                    %s AS change_type,
                    %s AS actor,
                    %s AS status,
                    %s AS fields_changed,
                    %s AS details
            ) source
            ON target.event_id = source.event_id
            WHEN MATCHED THEN UPDATE SET
                event_ts = source.event_ts,
                area = source.area,
                change_type = source.change_type,
                actor = source.actor,
                status = source.status,
                fields_changed = source.fields_changed,
                details = source.details
            WHEN NOT MATCHED THEN INSERT (
                event_id,
                event_ts,
                area,
                change_type,
                actor,
                status,
                fields_changed,
                details
            )
            VALUES (
                source.event_id,
                source.event_ts,
                source.area,
                source.change_type,
                source.actor,
                source.status,
                source.fields_changed,
                source.details
            )
            """,
            (
                event.get("event_id"),
                clean_value(event.get("event_ts")),
                event.get("area"),
                event.get("change_type"),
                event.get("actor"),
                event.get("status"),
                event.get("fields_changed"),
                event.get("details"),
            ),
        )


def clean_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value
