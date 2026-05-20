# CostOps Enterprise Entitlements Roadmap

## Context

CostOps is part of the GrainAI product suite. Catalog is the core GrainAI catalog product, and CostOps is a separate product focused on Snowflake cost optimization. Future products may include SyncOps, NightOps, and other suite apps.

The suite should eventually share common design and entitlement patterns, while each product keeps product-specific value metrics and pricing.

## Current Pricing Direction

CostOps plans currently use this working model:

- Free: $0, evaluation tier.
- Team: $749 / month.
- Business / Pro: $2,499 / month.
- Enterprise: $6,000 / month per production Snowflake account.

Enterprise is scoped to one production Snowflake account / CostOps instance. Dev and test Snowflake accounts used only for validation can be linked to that production instance. Separate production Snowflake accounts should require separate CostOps instances unless covered by a suite enterprise agreement.

## Current Implementation State

The Streamlit app now has a lightweight in-app entitlement model:

- Plans are defined in `app/streamlit_app.py`.
- Each plan has a `features` entitlement set.
- `has_entitlement(...)` checks whether the active plan unlocks a feature.
- The sidebar shows the current plan.
- The Upgrade Plan page shows current usage, observed versus included limits, plan cards, and upgrade/downgrade behavior language.
- Admin navigation includes an Enterprise Controls page.

Enterprise Controls is currently a product/design surface, not a complete production security implementation.

### Implementation Update (2026-05-20)

The Enterprise admin surface has now been expanded beyond a single overview page. The Admin navigation includes:

- Upgrade Plan
- Enterprise Controls
- RBAC Mapping
- Environments
- Persistence
- SSO & Identity
- SLA & Support
- Users and Roles
- Settings

The new Enterprise pages currently:

- save configuration into the app settings state
- track configuration readiness using:
  - Not configured
  - Ready for validation
  - Active
  - Action needed
- support product demos and internal workflow reviews
- reflect the current Enterprise pricing and one-production-account billing model

They do not yet provide production SSO, hard security enforcement, Marketplace entitlement sync, or provisioned dedicated persistence.

RBAC Mapping is now the most mature of the enterprise admin pages. It includes:

- mapping status and role-coverage summaries
- editable source-role to CostOps-role mapping records
- effective access preview for a selected source role
- a permission matrix that shows the current Admin / Operator / Viewer capabilities
- two onboarding paths:
  - map existing Snowflake or identity roles
  - use recommended starter roles with generated Snowflake SQL guidance

This remains an in-app admin workflow surface rather than full backend authorization enforcement.

Environments now includes:

- a production-instance summary with billing anchor language
- linked validation environment counts and status metrics
- add, edit, and remove actions for dev/test environments
- an environment-readiness table that separates the billable production instance from validation accounts

Persistence now includes:

- top-level health and readiness metrics
- explicit target and isolation selections
- retention, backup cadence, and restore-test tracking
- a readiness table that explains the current persistence posture in product language

SSO & Identity now includes:

- top-level identity status and provider metrics
- explicit provider and protocol selections
- allowed-domain, metadata URL, entity ID, and implementation-contact capture
- an identity-readiness table that frames the current SSO posture in implementation language

SLA & Support now includes:

- top-level support status and response metrics
- explicit support-tier and response-window selections
- deployment-owner and escalation-path capture
- a support-readiness table that frames commitments and operational ownership in product language

Enterprise Controls now also functions as a rollup dashboard. It includes:

- an enterprise readiness score
- active / ready / action-needed counts
- rollout blocker callouts
- a readiness table across the enterprise admin areas
- recent enterprise configuration audit events

The app also now surfaces enterprise operating context in working pages such as Scan & Schedule and Reports so the saved enterprise configuration affects user-facing workflow context.

Enterprise config audit logging is now in place. It includes:

- a dedicated local enterprise configuration audit store
- saved admin events for:
  - RBAC Mapping
  - Environments
  - Persistence
  - SSO & Identity
  - SLA & Support
- timestamps, actor, area, changed fields, status, and details
- a dedicated Enterprise Config Audit Trail report for PDF, Excel, and HTML export

RBAC behavior wiring has also advanced beyond a static admin form. The app now supports:

- manual CostOps role simulation
- source-role-to-CostOps-role simulation using saved RBAC mappings
- resolved-role display in the sidebar and settings
- permission messages that explain which resolved role is active and why an action is locked

Environment-aware operating context is now included in:

- Scan & Schedule
- on-screen report context
- PDF export headers
- Excel executive summary sheets
- HTML report packets

This means the production Snowflake account, linked validation environments, app instance, and billing scope now appear in the working output surfaces rather than living only inside Admin.

### Native App Phase 1 Update (2026-05-20)

The first native-compatible control-plane foundation is now in place.

Phase 1 currently includes:

- Snowflake DDL for enterprise-native control-plane objects in `sql/app/003_enterprise_control_plane.sql`
- a Snowflake config snapshot table
- a Snowflake enterprise user directory table
- a Snowflake enterprise config audit log table
- an enterprise readiness view
- repository support to sync the current in-app enterprise state into Snowflake
- a manual `Sync native control plane` action in the app

This means the Enterprise admin model is no longer only local demo state. The app can now push its saved enterprise settings, user directory, and enterprise config audit trail into Snowflake as the beginning of a native system of record.

Still deferred to later phases:

- moving the analysis runner into Snowflake execution paths
- replacing local session/runtime stores completely
- adapting unsupported Streamlit features for Native App constraints
- full native packaging and install validation

### Native App Phase 2 Update (2026-05-20)

The second native-compatible pass now focuses on UI/runtime adaptation rather than new product surface area.

Phase 2 currently includes:

- a native compatibility mode in the shared Streamlit app
- page configuration that avoids unsupported title and icon assumptions in native mode
- session-backed memoization in place of `st.cache_data`
- native-safe notification fallback in place of direct toast dependence
- a simpler sidebar navigation path that avoids depending on `st.navigation`
- a native package entrypoint that boots the shared app in compatibility mode for local validation

This keeps the current POC usable locally while making it easier to evaluate which screens and workflows can survive inside a Snowflake Native App runtime with minimal redesign.

### Native App Phase 3 Update (2026-05-20)

The Phase 3 pass focuses on package readiness and native-safe surface tightening.

Phase 3 currently includes:

- a tighter native package setup script that now creates:
  - enterprise control-plane tables
  - enterprise readiness view
  - recommendation workflow procedures
- a native Streamlit directory structure that places `environment.yml` beside the app entrypoint
- a pinned native dependency file for Streamlit warehouse runtime validation
- a package validation checklist for provider-side and consumer-side install testing
- native-safe report behavior that disables export delivery until file handling and supported dependencies are validated inside Snowflake

This does not yet mean the package is production-ready, but it is much closer to a real private-install validation candidate than the earlier scaffold.

## Recommended Build Levels

### Level 1: Product Demo UI

Estimated effort: 1-2 focused work sessions.

Build polished Enterprise screens that look and feel like real product surfaces:

- SSO & Identity
- RBAC Mapping
- Dedicated Persistence
- SLA & Support
- Linked Dev/Test
- Production Instance

These screens can show statuses, collect values, and explain what is configured versus pending. This is enough for demos, sales review, investor review, and internal product direction.

### Level 2: Functional Admin Workflow

Estimated effort: 1-2 weeks depending on depth.

Make the screens save settings and influence app behavior:

- RBAC mapping affects page/action permissions.
- Linked dev/test accounts appear in scan and rollout configuration.
- Persistence settings are stored and surfaced.
- SSO metadata can be stored and validation-tracked.
- Enterprise status determines which controls are unlocked.
- Downgrades lock Enterprise-only controls without deleting prior configuration.

### Level 3: Production Enterprise Infrastructure

Estimated effort: 3-6+ weeks, depending on security, deployment, and Marketplace requirements.

Production-grade Enterprise requires:

- Real SAML/OIDC SSO integration.
- Secure tenant-specific Postgres provisioning.
- Migration, backup, restore, and retention strategy.
- Snowflake Marketplace entitlement sync.
- Audit logs for admin/security changes.
- Encryption and secrets handling.
- RBAC enforcement across every page and action.
- SLA/support operational process.

## Recommended Next Build

Build Level 1.5 next.

Create the Enterprise pages and make them feel real, while clearly marking operational state as one of:

- Not configured
- Ready for validation
- Active
- Action needed

Recommended Admin navigation:

- Upgrade Plan
- Enterprise Controls
- SSO & Identity
- RBAC Mapping
- Persistence
- Environments
- SLA & Support
- Users and Roles
- Settings

Enterprise Controls should remain the overview/dashboard. The other pages should become detailed configuration screens.

## Suggested Implementation Order

1. RBAC Mapping
   - Most important first because it connects directly to existing CostOps roles: Admin, Operator, Viewer.
   - Define mappings from Snowflake/application roles to CostOps roles.
   - Show what each role can do.

2. Production Instance / Environments
   - Define the production Snowflake account.
   - Link dev/test validation accounts.
   - Clarify that billing applies to production accounts, not normal dev/test validation.

3. Dedicated Persistence
   - Track persistence target, status, retention, backups, and isolation.
   - Keep this separate from Catalog persistence to avoid crossover.

4. SSO & Identity
   - Start with metadata capture and status tracking.
   - Production SSO integration can come later.

5. SLA & Support
   - Show support tier, response window, deployment owner, and escalation path.

## Downgrade Behavior

Downgrades should never delete customer data.

Recommended behavior:

- Preserve recommendations, users, audit history, settings, and prior Enterprise configuration.
- Lock Enterprise-only pages and controls when the plan is downgraded.
- Keep existing Enterprise configuration visible as read-only or hidden behind a locked state.
- Limit new scans to the downgraded plan.
- Show an over-plan warning if current usage exceeds the new plan's limits.
- Allow admins to reduce scope, archive recommendations, or upgrade again.

## Design Notes

The UI should make it obvious what Enterprise unlocks without overstating production readiness. Use clear status labels instead of vague claims:

- Not configured
- Ready for validation
- Active
- Action needed

Avoid saying that SSO, dedicated persistence provisioning, Marketplace entitlement sync, or SLA operations are complete until those integrations actually exist.
