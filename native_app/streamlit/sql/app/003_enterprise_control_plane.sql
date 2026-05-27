CREATE TABLE IF NOT EXISTS COSTOPS_APP.ENTERPRISE_CONFIG_SNAPSHOT (
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

CREATE TABLE IF NOT EXISTS COSTOPS_APP.ENTERPRISE_USER_DIRECTORY (
    owner_name STRING NOT NULL,
    team_name STRING,
    business_role STRING,
    email STRING,
    access_role STRING,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (owner_name)
);

CREATE TABLE IF NOT EXISTS COSTOPS_APP.ENTERPRISE_CONFIG_AUDIT_LOG (
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

CREATE OR REPLACE VIEW COSTOPS_APP.ENTERPRISE_READINESS_VIEW AS
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
FROM COSTOPS_APP.ENTERPRISE_CONFIG_SNAPSHOT;
