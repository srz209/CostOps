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
