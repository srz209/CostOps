CREATE SCHEMA IF NOT EXISTS COSTOPS_APP;

CREATE TABLE IF NOT EXISTS COSTOPS_APP.COST_RECOMMENDATION (
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

ALTER TABLE COSTOPS_APP.COST_RECOMMENDATION ADD COLUMN IF NOT EXISTS owner_role STRING;
ALTER TABLE COSTOPS_APP.COST_RECOMMENDATION ADD COLUMN IF NOT EXISTS due_date DATE;
ALTER TABLE COSTOPS_APP.COST_RECOMMENDATION ADD COLUMN IF NOT EXISTS work_notes STRING;
ALTER TABLE COSTOPS_APP.COST_RECOMMENDATION ADD COLUMN IF NOT EXISTS last_note_at TIMESTAMP_NTZ;
ALTER TABLE COSTOPS_APP.COST_RECOMMENDATION ADD COLUMN IF NOT EXISTS assignment_updated_at TIMESTAMP_NTZ;

CREATE TABLE IF NOT EXISTS COSTOPS_APP.RECOMMENDATION_EVENT_LOG (
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

CREATE TABLE IF NOT EXISTS COSTOPS_APP.SCAN_RUN (
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

CREATE TABLE IF NOT EXISTS COSTOPS_APP.SCAN_FINDING (
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

CREATE TABLE IF NOT EXISTS COSTOPS_APP.SAVINGS_SNAPSHOT (
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
