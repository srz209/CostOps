# Cost Optimization App

This draft package is the starting point for Snowflake Native App validation. It defines the install-time application objects, persistence tables, and default Streamlit entrypoint expected by the Marketplace packaging flow.

The current local POC remains the source of truth while the Native App package is validated in a controlled Snowflake account.

The included Streamlit file is intentionally a minimal package entrypoint. Promote the local POC app into this directory after validating Snowflake permissions, package structure, and dependency constraints.

## Phase 1 native-compatible core

The current Phase 1 foundation is intentionally narrow and practical:

- core recommendation, scan, finding, event, and savings tables
- enterprise control-plane tables for:
  - config snapshot
  - user directory
  - enterprise config audit log
- a readiness view for enterprise posture rollups
- a manual app-side sync path that pushes the saved enterprise admin state into Snowflake

This gives the app a Snowflake-native system of record for the enterprise control plane before the scan runner itself is migrated into Snowflake execution paths.

## Phase 2 native-compatible UI adaptation

The local app now supports a native compatibility mode intended for the Snowflake Streamlit path:

- page configuration avoids unsupported title/icon assumptions when native mode is active
- the app avoids `st.cache_data` and uses session-backed memoization instead
- notification toasts fall back to standard Streamlit status messages
- the app can run with a simpler sidebar router instead of relying on `st.navigation`
- the native Streamlit entrypoint now boots the shared app in native compatibility mode for local validation

Phase 3 package tightening adds:

- `streamlit/environment.yml` beside the native Streamlit entrypoint, matching Snowflake’s recommended package structure
- a setup script that now creates the enterprise control-plane tables, readiness view, and recommendation workflow procedures
- a validation checklist in `package_validation_checklist.md`
- native-safe report behavior that keeps export delivery disabled until it is validated inside Snowflake

This is still a validation bridge, not the final package layout. Later phases should copy only the native-safe surfaces and persistence paths into the Native App package itself.

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
