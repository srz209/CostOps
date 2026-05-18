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

## Current POC Scope

- Executive cost overview
- Savings opportunity KPIs
- Recommendation backlog with severity, confidence, risk, effort, and status
- Warehouse spend and utilization charts
- Workload cost drilldowns
- Storage and task intelligence pages
- Settings page with rule catalog and Native App readiness checklist
- Generated SQL examples for recommended actions

## Project Structure

```text
app/
  streamlit_app.py          # Local POC UI
costops/
  data/sample_loader.py     # Sample-data loader
  rules/rule_catalog.py     # First deterministic rule backlog
  services/metrics.py       # Shared metric helpers
sample_data/                # CSV data used by the local POC
sql/                        # Placeholder for future Snowflake SQL assets
```

## Later Snowflake Native App Direction

The local app is intentionally structured so the first version can later move into a Snowflake Native App package with Streamlit in Snowflake, Snowflake SQL objects, scheduled scan procedures, and Marketplace packaging.
