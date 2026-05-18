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

The app runs in demo mode by default. To test live Snowflake warehouse metering:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Then fill in the Snowflake connection values in `.streamlit/secrets.toml` and restart Streamlit. Use the sidebar **Data source** control to switch from **Sample data** to **Snowflake**.

Current live coverage:

- Warehouse metering history from `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`

Current demo-only areas:

- Recommendations
- Scan history
- Storage
- Tasks
- Workload attribution
- Savings realization

## Current POC Scope

- Executive cost overview
- Savings opportunity KPIs
- Recommendation backlog with severity, confidence, risk, effort, and status
- Recommendation lifecycle tracking with owner, team, first-seen date, implementation date, aging, and missed savings
- Warehouse spend and utilization charts
- Workload cost drilldowns
- Storage and task intelligence pages
- Savings Realization page with period, category, owner, team, realized savings, and audit log filters
- Settings page with rule catalog and Native App readiness checklist
- Generated SQL examples for recommended actions

## Project Structure

```text
app/
  streamlit_app.py          # Local POC UI
costops/
  data/sample_loader.py     # Sample-data loader
  data/snowflake_loader.py  # Optional Snowflake metadata loader
  rules/rule_catalog.py     # First deterministic rule backlog
  services/metrics.py       # Shared metric helpers
sample_data/                # CSV data used by the local POC
sql/                        # Placeholder for future Snowflake SQL assets
```

## Recommendation Lifecycle

The POC models recommendations as workflow items rather than static alerts:

```text
Detected -> Proposed -> Selected / Accepted -> SQL Copied -> Implemented -> Realized
```

Each recommendation can carry an owner, team, projected daily savings, first-seen date, implementation date, missed-savings estimate, realized-savings estimate, and audit log events.

## Later Snowflake Native App Direction

The local app is intentionally structured so the first version can later move into a Snowflake Native App package with Streamlit in Snowflake, Snowflake SQL objects, scheduled scan procedures, and Marketplace packaging.
