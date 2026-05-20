CREATE APPLICATION ROLE IF NOT EXISTS costops_admin;
CREATE APPLICATION ROLE IF NOT EXISTS costops_operator;
CREATE APPLICATION ROLE IF NOT EXISTS costops_viewer;

CREATE SCHEMA IF NOT EXISTS app_schema;
GRANT USAGE ON SCHEMA app_schema TO APPLICATION ROLE costops_admin;
GRANT USAGE ON SCHEMA app_schema TO APPLICATION ROLE costops_operator;
GRANT USAGE ON SCHEMA app_schema TO APPLICATION ROLE costops_viewer;

CREATE SCHEMA IF NOT EXISTS costops_app;
GRANT USAGE ON SCHEMA costops_app TO APPLICATION ROLE costops_admin;
GRANT USAGE ON SCHEMA costops_app TO APPLICATION ROLE costops_operator;
GRANT USAGE ON SCHEMA costops_app TO APPLICATION ROLE costops_viewer;

CREATE TABLE IF NOT EXISTS costops_app.cost_recommendation (
    recommendation_id STRING NOT NULL,
    scan_run_id STRING,
    recommendation_category STRING NOT NULL,
    recommendation_subcategory STRING,
    title STRING NOT NULL,
    object_name STRING,
    severity STRING,
    confidence_score NUMBER(5, 4),
    projected_daily_savings NUMBER(18, 2),
    projected_monthly_savings NUMBER(18, 2),
    projected_annual_savings NUMBER(18, 2),
    realized_monthly_savings NUMBER(18, 2) DEFAULT 0,
    implementation_risk STRING,
    implementation_effort STRING,
    recommendation_status STRING DEFAULT 'Proposed',
    owner_name STRING,
    team_name STRING,
    owner_role STRING,
    due_date DATE,
    generated_sql STRING,
    evidence STRING,
    work_notes STRING,
    first_seen_at TIMESTAMP_NTZ,
    last_seen_at TIMESTAMP_NTZ,
    accepted_at TIMESTAMP_NTZ,
    implemented_at TIMESTAMP_NTZ,
    realized_at TIMESTAMP_NTZ,
    last_note_at TIMESTAMP_NTZ,
    assignment_updated_at TIMESTAMP_NTZ,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (recommendation_id)
);

CREATE TABLE IF NOT EXISTS costops_app.recommendation_event_log (
    event_id STRING NOT NULL,
    recommendation_id STRING,
    event_ts TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    event_type STRING NOT NULL,
    actor STRING,
    details STRING,
    previous_status STRING,
    new_status STRING,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (event_id)
);

CREATE TABLE IF NOT EXISTS costops_app.scan_run (
    scan_run_id STRING NOT NULL,
    scan_type STRING,
    scan_scope STRING,
    schedule_name STRING,
    started_at TIMESTAMP_NTZ,
    completed_at TIMESTAMP_NTZ,
    scan_status STRING,
    credits_estimated NUMBER(18, 4),
    scan_cost_usd NUMBER(18, 2),
    recommendations_found NUMBER(18, 0),
    recommendations_new NUMBER(18, 0),
    recommendations_updated NUMBER(18, 0),
    identified_monthly_savings NUMBER(18, 2),
    initiated_by STRING,
    error_message STRING,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (scan_run_id)
);

CREATE TABLE IF NOT EXISTS costops_app.scan_finding (
    finding_id STRING NOT NULL,
    scan_run_id STRING NOT NULL,
    recommendation_id STRING,
    finding_category STRING,
    object_name STRING,
    severity STRING,
    confidence_score NUMBER(5, 4),
    projected_monthly_savings NUMBER(18, 2),
    finding_payload VARIANT,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (finding_id)
);

CREATE TABLE IF NOT EXISTS costops_app.savings_snapshot (
    snapshot_id STRING NOT NULL,
    snapshot_date DATE NOT NULL,
    recommendation_id STRING,
    category STRING,
    owner_name STRING,
    team_name STRING,
    projected_daily_savings NUMBER(18, 2),
    projected_monthly_savings NUMBER(18, 2),
    realized_daily_savings NUMBER(18, 2),
    realized_monthly_savings NUMBER(18, 2),
    missed_savings_to_date NUMBER(18, 2),
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (snapshot_id)
);

CREATE TABLE IF NOT EXISTS costops_app.enterprise_config_snapshot (
    config_scope STRING NOT NULL,
    production_account STRING,
    production_region STRING,
    app_instance STRING,
    billing_scope STRING,
    rbac_status STRING,
    environment_status STRING,
    persistence_status STRING,
    sso_status STRING,
    sla_status STRING,
    config_payload VARIANT,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (config_scope)
);

CREATE TABLE IF NOT EXISTS costops_app.enterprise_user_directory (
    owner_name STRING NOT NULL,
    team_name STRING,
    business_role STRING,
    email STRING,
    access_role STRING,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (owner_name)
);

CREATE TABLE IF NOT EXISTS costops_app.enterprise_config_audit_log (
    event_id STRING NOT NULL,
    event_ts TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    area STRING NOT NULL,
    change_type STRING NOT NULL,
    actor STRING,
    status STRING,
    fields_changed STRING,
    details STRING,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (event_id)
);

CREATE OR REPLACE VIEW costops_app.enterprise_readiness_view AS
SELECT
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
    updated_at
FROM costops_app.enterprise_config_snapshot;

CREATE OR REPLACE PROCEDURE costops_app.log_recommendation_event(
    P_RECOMMENDATION_ID STRING,
    P_EVENT_TYPE STRING,
    P_ACTOR STRING,
    P_DETAILS STRING,
    P_PREVIOUS_STATUS STRING,
    P_NEW_STATUS STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    INSERT INTO costops_app.recommendation_event_log (
        event_id,
        recommendation_id,
        event_ts,
        event_type,
        actor,
        details,
        previous_status,
        new_status
    )
    VALUES (
        UUID_STRING(),
        P_RECOMMENDATION_ID,
        CURRENT_TIMESTAMP(),
        P_EVENT_TYPE,
        P_ACTOR,
        P_DETAILS,
        P_PREVIOUS_STATUS,
        P_NEW_STATUS
    );

    RETURN 'EVENT_LOGGED';
END;
$$;

CREATE OR REPLACE PROCEDURE costops_app.update_recommendation_status(
    P_RECOMMENDATION_ID STRING,
    P_NEW_STATUS STRING,
    P_ACTOR STRING,
    P_DETAILS STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    V_PREVIOUS_STATUS STRING;
    V_EVENT_TYPE STRING;
    V_DETAILS STRING;
BEGIN
    SELECT recommendation_status
      INTO :V_PREVIOUS_STATUS
      FROM costops_app.cost_recommendation
     WHERE recommendation_id = P_RECOMMENDATION_ID;

    V_EVENT_TYPE := CASE P_NEW_STATUS
        WHEN 'Selected' THEN 'SELECTED'
        WHEN 'Accepted' THEN 'ACCEPTED'
        WHEN 'Deferred' THEN 'DEFERRED'
        WHEN 'Rejected' THEN 'REJECTED'
        WHEN 'Implemented' THEN 'IMPLEMENTED'
        WHEN 'Realized' THEN 'SAVINGS_REALIZED'
        ELSE 'STATUS_CHANGED'
    END;

    V_DETAILS := COALESCE(NULLIF(P_DETAILS, ''), 'Recommendation status updated.');

    UPDATE costops_app.cost_recommendation
       SET recommendation_status = P_NEW_STATUS,
           last_seen_at = CURRENT_TIMESTAMP(),
           accepted_at = CASE
               WHEN P_NEW_STATUS IN ('Accepted', 'Implemented', 'Realized')
                    AND accepted_at IS NULL THEN CURRENT_TIMESTAMP()
               ELSE accepted_at
           END,
           implemented_at = CASE
               WHEN P_NEW_STATUS IN ('Implemented', 'Realized') THEN CURRENT_TIMESTAMP()
               ELSE implemented_at
           END,
           realized_at = CASE
               WHEN P_NEW_STATUS = 'Realized' THEN CURRENT_TIMESTAMP()
               ELSE realized_at
           END,
           updated_at = CURRENT_TIMESTAMP()
     WHERE recommendation_id = P_RECOMMENDATION_ID;

    CALL costops_app.log_recommendation_event(
        P_RECOMMENDATION_ID,
        V_EVENT_TYPE,
        P_ACTOR,
        V_DETAILS,
        V_PREVIOUS_STATUS,
        P_NEW_STATUS
    );

    RETURN 'STATUS_UPDATED';
END;
$$;

CREATE OR REPLACE PROCEDURE costops_app.log_sql_copied(
    P_RECOMMENDATION_ID STRING,
    P_ACTOR STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    V_CURRENT_STATUS STRING;
BEGIN
    SELECT recommendation_status
      INTO :V_CURRENT_STATUS
      FROM costops_app.cost_recommendation
     WHERE recommendation_id = P_RECOMMENDATION_ID;

    CALL costops_app.log_recommendation_event(
        P_RECOMMENDATION_ID,
        'SQL_COPIED',
        P_ACTOR,
        'Copied generated SQL or implementation guidance from the recommendation detail.',
        V_CURRENT_STATUS,
        V_CURRENT_STATUS
    );

    RETURN 'SQL_COPY_LOGGED';
END;
$$;

CREATE OR REPLACE STREAMLIT app_schema.costops_streamlit
    FROM '/streamlit'
    MAIN_FILE = '/streamlit_app.py';

GRANT USAGE ON STREAMLIT app_schema.costops_streamlit TO APPLICATION ROLE costops_admin;
GRANT USAGE ON STREAMLIT app_schema.costops_streamlit TO APPLICATION ROLE costops_operator;
GRANT USAGE ON STREAMLIT app_schema.costops_streamlit TO APPLICATION ROLE costops_viewer;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA costops_app TO APPLICATION ROLE costops_admin;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA costops_app TO APPLICATION ROLE costops_operator;
GRANT SELECT ON ALL TABLES IN SCHEMA costops_app TO APPLICATION ROLE costops_viewer;
GRANT SELECT ON VIEW costops_app.enterprise_readiness_view TO APPLICATION ROLE costops_admin;
GRANT SELECT ON VIEW costops_app.enterprise_readiness_view TO APPLICATION ROLE costops_operator;
GRANT SELECT ON VIEW costops_app.enterprise_readiness_view TO APPLICATION ROLE costops_viewer;
GRANT USAGE ON PROCEDURE costops_app.log_recommendation_event(STRING, STRING, STRING, STRING, STRING, STRING) TO APPLICATION ROLE costops_admin;
GRANT USAGE ON PROCEDURE costops_app.log_recommendation_event(STRING, STRING, STRING, STRING, STRING, STRING) TO APPLICATION ROLE costops_operator;
GRANT USAGE ON PROCEDURE costops_app.update_recommendation_status(STRING, STRING, STRING, STRING) TO APPLICATION ROLE costops_admin;
GRANT USAGE ON PROCEDURE costops_app.update_recommendation_status(STRING, STRING, STRING, STRING) TO APPLICATION ROLE costops_operator;
GRANT USAGE ON PROCEDURE costops_app.log_sql_copied(STRING, STRING) TO APPLICATION ROLE costops_admin;
GRANT USAGE ON PROCEDURE costops_app.log_sql_copied(STRING, STRING) TO APPLICATION ROLE costops_operator;
