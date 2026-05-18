CREATE APPLICATION ROLE IF NOT EXISTS app_public;

CREATE SCHEMA IF NOT EXISTS app_schema;
GRANT USAGE ON SCHEMA app_schema TO APPLICATION ROLE app_public;

CREATE SCHEMA IF NOT EXISTS costops_app;
GRANT USAGE ON SCHEMA costops_app TO APPLICATION ROLE app_public;

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
    generated_sql STRING,
    evidence STRING,
    first_seen_at TIMESTAMP_NTZ,
    last_seen_at TIMESTAMP_NTZ,
    accepted_at TIMESTAMP_NTZ,
    implemented_at TIMESTAMP_NTZ,
    realized_at TIMESTAMP_NTZ,
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

CREATE STREAMLIT IF NOT EXISTS app_schema.costops_streamlit
    FROM '/streamlit'
    MAIN_FILE = 'streamlit_app.py';

GRANT USAGE ON STREAMLIT app_schema.costops_streamlit TO APPLICATION ROLE app_public;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA costops_app TO APPLICATION ROLE app_public;
