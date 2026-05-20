# CostOps Native App Install/Test Sequence

This runbook is the exact sequence to validate CostOps as a Snowflake Native App in a test account without going through the Marketplace.

## What this is

This flow installs CostOps directly from an **application package** in Snowflake.

- Your Git repo is the source of truth.
- The `native_app/` folder is the package source.
- Snowflake stages and application packages are the deployable/installable layer.
- Marketplace is **not required** for this test pass.

## Files in this folder

- `manifest.yml`
- `setup_script.sql`
- `readme.md`
- `streamlit/streamlit_app.py`
- `streamlit/environment.yml`
- `sql/01_provider_bootstrap.sql`
- `sql/02_add_version_and_release_directive.sql`
- `sql/03_create_dev_app_from_package.sql`
- `sql/04_validation_queries.sql`
- `sql/05_cleanup.sql`
- `scripts/upload_package_files_snowsql.sh`

## Prerequisites

You need a role with privileges to:

- create an application package
- create a stage
- add versions to the package
- set release directives
- create an application

Snowflake documents local app testing and application-package creation here:

- [Install and test an app locally](https://docs.snowflake.com/en/developer-guide/native-apps/installing-testing-application)
- [Create and manage an application package](https://docs.snowflake.com/en/developer-guide/native-apps/creating-app-package)
- [ALTER APPLICATION PACKAGE ... VERSION](https://docs.snowflake.com/en/sql-reference/sql/alter-application-package-version)
- [ALTER APPLICATION PACKAGE ... RELEASE DIRECTIVE](https://docs.snowflake.com/en/sql-reference/sql/alter-application-package-release-directive)
- [PUT](https://docs.snowflake.com/en/sql-reference/sql/put)

## Recommended object names

Use these defaults unless you already have a naming standard:

- package database: `COSTOPS_NATIVE_DEV`
- package schema: `PACKAGE_SRC`
- package stage: `COSTOPS_STAGE`
- application package: `COSTOPS_PKG`
- test application install: `COSTOPS_APP_DEV`
- version: `V0_1`

## End-to-end sequence

### 1. Bootstrap provider-side objects

Run:

- `native_app/sql/01_provider_bootstrap.sql`

This creates:

- package database/schema
- named internal stage
- application package
- install grant for your test role

### 2. Upload the package files to the named stage

Use one of these methods:

- `native_app/scripts/upload_package_files_snowsql.sh`
- Snowsight file upload to the named internal stage
- SnowSQL `PUT` commands manually

Important Snowflake requirement:

- `manifest.yml` must be at the root of the staged directory
- `streamlit/` must stay as a subdirectory

### 3. Add a version and set the default release directive

Run:

- `native_app/sql/02_add_version_and_release_directive.sql`

This:

- adds version `V0_1` from the staged files
- sets the default release directive to `V0_1` patch `0`

### 4. Install the app in development mode

Run:

- `native_app/sql/03_create_dev_app_from_package.sql`

This creates the test application directly from the application package using the version you just defined.

### 5. Validate the install

Run:

- `native_app/sql/04_validation_queries.sql`

Then in Snowsight:

1. open the installed app
2. confirm the Streamlit UI launches
3. go to `Enterprise Controls`
4. go to `Settings`
5. test `Sync native control plane`

### 6. Optional post-install grant for usage telemetry

If you want CostOps to read `SNOWFLAKE.ACCOUNT_USAGE`, run:

```sql
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION COSTOPS_APP_DEV;
```

That grant is an explicit consumer/admin approval step.

### 7. Re-test after the grant

Re-open the app and validate:

- connection test
- scan/readiness surfaces
- native control-plane sync

### 8. Clean up when finished

Run:

- `native_app/sql/05_cleanup.sql`

This removes the test application. It leaves the package and stage in place unless you uncomment the deeper cleanup lines.

## What success looks like

You should be able to confirm all of the following:

- the app installs without Marketplace
- the setup script creates schemas, tables, view, procedures, and Streamlit object
- application roles exist:
  - `costops_admin`
  - `costops_operator`
  - `costops_viewer`
- the Streamlit app opens
- the Enterprise pages render
- `Sync native control plane` writes data into:
  - `COSTOPS_APP.ENTERPRISE_CONFIG_SNAPSHOT`
  - `COSTOPS_APP.ENTERPRISE_USER_DIRECTORY`
  - `COSTOPS_APP.ENTERPRISE_CONFIG_AUDIT_LOG`

## Notes

- This is a **development-mode** validation flow.
- Marketplace/private listing comes later if we want to test the consumer install experience through listings.
- The current native mode intentionally disables report-download delivery until we validate supported file handling in Snowflake.
