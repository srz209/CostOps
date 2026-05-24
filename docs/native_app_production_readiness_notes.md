# Native App Production Readiness Notes

## Naming Cleanup Before Production

The current Snowflake Native App validation install uses development names:

- Installed application object: `COSTOPS_APP_DEV`
- Application package: `COSTOPS_PKG`
- Version label: `Cost optimization POC`

Before production or Marketplace submission, remove POC/dev language from customer-facing surfaces.

Recommended production naming:

- Listing / product name: `GrainAI CostOps`
- Version label: `GrainAI CostOps`
- Application package: `GRAINAI_COSTOPS_PKG`
- Installed app object for internal testing: `GRAINAI_COSTOPS_DEV`
- Installed app object for production validation: `GRAINAI_COSTOPS`

## Where The Current Names Come From

### `COSTOPS_APP_DEV`

This is not read from a file name. It is the Snowflake application object name used in the install SQL.

Current file:

- `native_app/sql/03_create_dev_app_from_package.sql`

Current setting:

```sql
SET APPLICATION_NAME = 'COSTOPS_APP_DEV';
```

For a cleaner test install, create the app with:

```sql
CREATE APPLICATION GRAINAI_COSTOPS_DEV
FROM APPLICATION PACKAGE COSTOPS_PKG
USING RELEASE CHANNEL DEFAULT;
```

For a production-style validation install, use:

```sql
CREATE APPLICATION GRAINAI_COSTOPS
FROM APPLICATION PACKAGE COSTOPS_PKG
USING RELEASE CHANNEL DEFAULT;
```

### `Cost optimization POC`

This is the Native App package version label in:

- `native_app/manifest.yml`

Current value:

```yaml
version:
  label: "Cost optimization POC"
```

Before production, change it to:

```yaml
version:
  label: "GrainAI CostOps"
```

Also update the version comment to remove draft/POC language.

## Production Checklist

- Replace `Cost optimization POC` with `GrainAI CostOps`.
- Replace `Draft Snowflake Native App package skeleton for local validation.` with production-safe wording.
- Use production-style install names in validation docs and scripts.
- Keep `COSTOPS_APP_DEV` only in local/dev runbooks if useful.
- Confirm Snowsight app browser, installed app page, Streamlit title, and Marketplace listing all show `GrainAI CostOps`.

## Native App Loading Feedback

During Snowflake Native App validation, long-running reads or scans can make the Streamlit screen look idle. Add visible feedback before production:

- Wrap Snowflake reads and scan actions with `st.spinner(...)` so users see that CostOps is actively working.
- Add a compact status area for scan lifecycle states such as `Ready`, `Running`, `Completed`, and `Failed`.
- Show the last refresh timestamp near the overview metrics.
- Use `st.progress(...)` only when the app knows the scan step count or percent complete.
- After a scan completes, call `st.rerun()` or provide a clear refresh action so metrics and recommendations update immediately.

This is especially important in the native app because the first empty-state screen currently says recommendations will appear after CostOps writes scan results, but it does not show whether a read or scan is currently in progress.
