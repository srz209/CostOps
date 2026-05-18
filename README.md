# Snowflake Cost Optimization App POC

Local proof of concept for a Snowflake-first cost optimization and architectural intelligence application.

## Run Locally

```bash
cd ~/Documents/cost-ops
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

## Optional Snowflake Mode

The app runs in demo mode by default. To test live Snowflake analysis:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Then fill in the Snowflake connection values in `.streamlit/secrets.toml` and restart Streamlit. Use the sidebar **Data source** control to switch from **Sample data** to **Snowflake**.

Current live coverage:

- Warehouse metering history from `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`
- Query/workload history from `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`
- Task history from `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY`
- Storage object metadata from `SNOWFLAKE.ACCOUNT_USAGE.TABLE_STORAGE_METRICS`

The **Scan & Schedule** page now includes a local analysis runner. In sample mode it regenerates recommendations from demo metadata. In Snowflake mode it attempts the live account-usage scan, then writes generated recommendations to the local workflow store and, when configured, the Snowflake persistence tables.

## Persistence Layer

The POC now has a Snowflake-shaped persistence layer for the recommendation lifecycle:

- `sql/app/001_core_tables.sql` creates core tables for recommendations, audit events, scan runs, scan findings, and savings snapshots.
- `sql/app/002_recommendation_workflow_procedures.sql` creates stored procedures for recommendation status changes and SQL-copy audit events.
- `costops/data/recommendation_store.py` is the local session-backed workflow adapter used by the Streamlit demo.
- `costops/data/snowflake_repository.py` initializes the Snowflake schema, calls workflow procedures, and persists analysis-run output.

In demo mode, recommendation workflow actions and ad hoc scan results are written to `runtime_state/`, which is ignored by Git so demo usage does not change the seed sample data. In Snowflake mode, the Settings page includes an **Initialize persistence schema** action that creates the table and procedure targets for the live workflow.

## Current POC Scope

- Executive cost overview
- Savings opportunity KPIs
- Recommendation backlog with severity, confidence, risk, effort, and status
- Recommendation lifecycle tracking with owner, team, first-seen date, implementation date, aging, and missed savings
- Warehouse spend and utilization charts
- Workload cost drilldowns
- Storage and task intelligence pages
- Savings Realization page with period, category, owner, team, realized savings, and audit log filters
- Reports page with executive savings summary, ownership aging, scan ROI, and export-ready detail tables
- Settings page with rule catalog and Native App readiness checklist
- Generated SQL examples for recommended actions

## Project Structure

```text
app/
  streamlit_app.py          # Local POC UI
costops/
  data/recommendation_store.py  # Session-backed recommendation workflow adapter
  data/sample_loader.py     # Sample-data loader
  data/snowflake_repository.py # Snowflake persistence helpers
  data/snowflake_loader.py  # Optional Snowflake metadata loader
  rules/rule_catalog.py     # First deterministic rule backlog
  services/analysis_runner.py # Rule engine that turns metadata into recommendations
  services/metrics.py       # Shared metric helpers
native_app/                 # Draft Snowflake Native App package skeleton
sample_data/                # CSV data used by the local POC
runtime_state/              # Local ignored workflow state created at runtime
sql/
  app/                       # Core app tables and workflow procedures
  diagnostics/               # Account usage diagnostic queries
```

## Recommendation Lifecycle

The POC models recommendations as workflow items rather than static alerts:

```text
Detected -> Proposed -> Selected / Accepted -> SQL Copied -> Implemented -> Realized
```

Each recommendation can carry an owner, team, projected daily savings, first-seen date, implementation date, missed-savings estimate, realized-savings estimate, and audit log events.

## Later Snowflake Native App Direction

The local app is intentionally structured so the first version can later move into a Snowflake Native App package with Streamlit in Snowflake, Snowflake SQL objects, scheduled scan procedures, and Marketplace packaging.

The draft `native_app/` package includes a `manifest.yml`, setup script, environment file, consumer readme, and minimal Streamlit entrypoint. It is a starting scaffold for controlled Snowflake validation, not yet a production Marketplace listing.

## Backlog

- Replace the left navigation radio list with a denser app-style sidebar using visual section markers, stronger active-state styling, and compact labels. Streamlit does not give full custom navigation primitives out of the box, so the first pass should use CSS and structured navigation groups before considering a custom component.
- Add a dedicated scheduled-task implementation after live scan permissions are validated in a Snowflake test account.
- Add rule-level threshold controls for warehouse utilization, task frequency, storage staleness, and query scan volume.
