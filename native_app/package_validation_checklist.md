# CostOps Native App Phase 3 Validation Checklist

Use this checklist when validating the current Native App scaffold in a Snowflake test account.

## Provider-side package checks

1. Confirm package file layout:
   - `manifest.yml`
   - `setup_script.sql`
   - `readme.md`
   - `streamlit/streamlit_app.py`
   - `streamlit/environment.yml`
2. Upload the package files to a named stage.
3. Create or refresh the application package from the staged files.
4. Verify that the manifest resolves:
   - setup script path
   - readme path
   - default Streamlit object name

## Install-time checks

1. Install the app in a controlled test consumer account.
2. Confirm the setup script creates:
   - application roles
   - `APP_SCHEMA`
   - `COSTOPS_APP`
   - recommendation workflow tables
   - enterprise control-plane tables
   - enterprise readiness view
   - recommendation workflow procedures
   - Streamlit object
3. Confirm application-role grants on:
   - schema usage
   - Streamlit usage
   - table access
   - readiness view access

## Streamlit checks

1. Launch the app in Snowsight.
2. Confirm the app runs in native compatibility mode.
3. Confirm sidebar navigation works without `st.navigation`.
4. Confirm Enterprise admin pages render cleanly.
5. Confirm Reports render on-screen without requiring export downloads.

## Functional checks

1. Save Enterprise settings in the app.
2. Run `Sync native control plane`.
3. Verify Snowflake objects receive:
   - config snapshot row
   - user directory rows
   - enterprise config audit log rows
4. Verify the enterprise readiness view reflects the synced state.

## Security / grant checks

1. Confirm install is performed by `ACCOUNTADMIN` or delegated installer role.
2. Confirm application roles can be granted to consumer roles.
3. If usage telemetry is required, validate the manual post-install grant:

```sql
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION <installed_app_name>;
```

## Known deferred items

- recommendation scans still run through the local Python analysis runner path
- local/session workflow state still exists outside Snowflake
- report export delivery remains disabled in native compatibility mode
- entitlement sync and production SSO are still later-phase work
