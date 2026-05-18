# Cost Optimization App

This draft package is the starting point for Snowflake Native App validation. It defines the install-time application objects, persistence tables, and default Streamlit entrypoint expected by the Marketplace packaging flow.

The current local POC remains the source of truth while the Native App package is validated in a controlled Snowflake account.

The included Streamlit file is intentionally a minimal package entrypoint. Promote the local POC app into this directory after validating Snowflake permissions, package structure, and dependency constraints.

## Consumer install model

Recommended install pattern:

- Install the app with a controlled consumer role such as `ACCOUNTADMIN` or a delegated marketplace installer role.
- Grant application roles after install rather than letting broad analyst roles install or administer the app.

Suggested application-role mapping:

- `costops_admin`: installer / platform admin
- `costops_operator`: architecture and engineering operators
- `costops_viewer`: read-only consumers of dashboards and reports

## ACCOUNT_USAGE access

If the consumer wants the app to read usage and cost telemetry from the `SNOWFLAKE.ACCOUNT_USAGE` schema, they must explicitly approve that access after installation.

Manual grant:

```sql
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION <installed_app_name>;
```

Snowflake documents this as a manual post-install grant for Native Apps. Treat it as an admin approval step because it allows the app to access usage and cost information from the consumer account.
