# Cost Optimization App

This draft package is the starting point for Snowflake Native App validation. It defines the install-time application objects, persistence tables, and default Streamlit entrypoint expected by the Marketplace packaging flow.

The current local POC remains the source of truth while the Native App package is validated in a controlled Snowflake account.

The included Streamlit file is intentionally a minimal package entrypoint. Promote the local POC app into this directory after validating Snowflake permissions, package structure, and dependency constraints.
