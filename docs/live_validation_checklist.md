# Live Validation Checklist

## Short answer

You do **not** need Render to connect this app to a real Snowflake account.

For the next phase, the best path is:

1. Run the app locally with Streamlit.
2. Connect it to a real Snowflake account using local secrets.
3. Validate the rules, permissions, and outputs.
4. Only after that, decide whether to:
   - keep an external hosted POC for demos, or
   - move directly toward Snowflake Native App packaging.

## Deployment decision

There are three realistic paths:

### Path 1: Local Streamlit plus Snowflake connection

Use this now.

- Fastest way to validate real metadata access.
- Easiest way to debug credentials, privileges, and thresholds.
- No hosting work required.
- Closest to the current codebase.

This is the recommended next step.

### Path 2: External hosted app, for example Render

Use this only if you want a hosted demo before Marketplace packaging.

- Good for sharing a web demo with others.
- Still uses the Python connector from an external app to connect into Snowflake.
- Requires secret management, outbound network validation, auth decisions, and basic app hardening.
- Does **not** prove the Snowflake Marketplace install model.

This is optional, not required for live validation.

### Path 3: Streamlit in Snowflake / Native App

This is the target path for Marketplace distribution.

- Best fit for the final product direction.
- Keeps app execution inside Snowflake.
- Aligns with the install, role, and privilege model you want.
- Requires more packaging and permission work than local validation.

This should follow successful live validation, not come before it.

## Recommendation

Do **not** move to Render yet.

Do the first live validation locally, because it answers the most important product questions:

- Can we read the right Snowflake metadata?
- Do the recommendations make sense?
- Are the threshold controls enough?
- Is the access model right?
- What privileges are truly required?

After that:

- Push to GitHub for source control and backup if you want a clean checkpoint.
- Only set up Render if you want a hosted demo.
- Move toward Native App packaging once the live scan output is credible.

## Live validation prerequisites

### Local app

- Current repo runs locally.
- `.venv` is working.
- Streamlit app launches on `localhost`.
- Snowflake secrets are available in `.streamlit/secrets.toml`.

### Snowflake account

- Controlled test account or non-production validation environment.
- Installer/admin role available.
- Ability to test with `SNOWFLAKE.ACCOUNT_USAGE`.
- Permission to create the app schema objects used by the POC.

### Recommended Snowflake role for validation

Use a controlled admin/platform role, not a general analyst role.

Minimum practical validation role should be able to:

- connect to the target account
- read approved usage metadata
- create the persistence schema objects
- approve imported privileges if testing the Native App pattern

## Validation sequence

### Phase 1: Connectivity

1. Confirm Snowflake credentials work from the local app.
2. Confirm the selected role can connect successfully.
3. Verify the app can initialize the persistence schema.

Success criteria:

- connection test passes
- persistence schema initializes without permission errors

### Phase 2: Metadata access

Validate access to the sources the app expects:

- `WAREHOUSE_METERING_HISTORY`
- `QUERY_HISTORY`
- `TASK_HISTORY`
- `TABLE_STORAGE_METRICS`

Success criteria:

- each loader returns real rows
- no privilege errors on approved metadata sources
- row volumes are reasonable for the chosen lookback window

### Phase 3: First live scan

1. Run the first live analysis from the Scan & Schedule page.
2. Review the generated recommendations.
3. Check that scan history and recommendation workflow update correctly.

Success criteria:

- scan completes successfully
- recommendation count is believable
- obvious false positives are limited
- recommendations map to reasonable teams and owners

### Phase 4: Threshold tuning

Use Settings to tune:

- minimum monthly savings
- minimum confidence
- warehouse utilization ceiling
- warehouse cost floor
- task execution threshold
- task failure threshold
- stale object threshold
- full refresh scan threshold
- spill threshold

Success criteria:

- recommendation noise decreases
- high-value findings remain visible
- teams can trust the backlog

### Phase 5: Workflow validation

1. Reassign ownership on live recommendations.
2. Update statuses.
3. Add notes.
4. Confirm My Work behaves correctly by owner, team, and role.

Success criteria:

- ownership updates persist
- due dates and overdue signals look right
- admin/operator/viewer behavior matches expectations

### Phase 6: Native App readiness

After live validation succeeds:

1. review the current `native_app/` scaffold
2. verify application roles
3. verify post-install grant instructions
4. validate the `ACCOUNT_USAGE` approval flow

Success criteria:

- installer/admin flow is clear
- operator/viewer roles are minimal and sensible
- metadata access is explicit and documented

## Likely failure points

- Snowflake role can connect but cannot read `ACCOUNT_USAGE`.
- Test account does not expose enough metadata history.
- Recommendations are too noisy with default thresholds.
- External network or MFA requirements block connector usage.
- Persistence schema creates successfully but workflow updates fail on later writes.

## GitHub and Render decision

### GitHub

Recommended soon, but not required for live validation.

Reasons:

- clean checkpoint before testing against a real account
- easier rollback and collaboration
- useful for later Render or Native App packaging workflows

### Render

Not recommended yet.

Use Render only if you need:

- a hosted demo URL
- shared stakeholder access outside your machine
- an external-app proof of concept

If you go to Render, treat it as a separate deployment track from the Marketplace track.

## Best next move

Run the first live Snowflake validation locally.

That means:

1. verify secrets
2. test connection
3. initialize schema
4. run first live scan
5. tune thresholds
6. review recommendation quality

Only after that should we decide whether to:

- push to GitHub and keep moving locally
- add Render for external demos
- or shift directly into Native App packaging
