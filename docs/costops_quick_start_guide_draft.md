# CostOps Quick Start Guide Draft

This document is a consolidated quick start guide for the current CostOps application. It is intended for internal review before screenshots, formatting polish, website adaptation, or video scripting are added.

The goal of this draft is to explain what each major page does, how it is typically used, and why it matters.

## Who this guide is for

This guide is useful for:

- enterprise administrators
- data platform teams
- analytics engineering teams
- FinOps or leadership stakeholders
- internal reviewers preparing documentation or training material

## Application structure

The application is organized into four main categories:

- Command Center
- Analysis
- Value
- Admin

## 1. Command Center

The Command Center is the main operational area of CostOps. It combines the summary view, recommendation workflow, personal or team execution queues, and scan orchestration.

### Overview

The **Overview** page is the main landing page for CostOps. It gives users a high-level summary of cost exposure, savings opportunity, recommendation priority, and enterprise rollout status.

#### What this page is for

Use the Overview page to quickly understand:

- current estimated Snowflake spend
- open monthly savings opportunity
- realized monthly savings
- number of critical findings
- how recommendations are distributed by category, severity, and status
- which high-value recommendations should be reviewed first

#### Main sections

**Filter bar**

Users can filter the dashboard by:

- Status
- Category
- Team
- Owner
- Minimum confidence

These filters update the summary metrics, charts, and recommendation table below.

**KPI summary cards**

The summary cards show:

- Estimated Monthly Spend
- Monthly Savings Opportunity
- Realized Monthly Savings
- Critical Findings

**Enterprise Rollout**

For Enterprise accounts, this section shows:

- Readiness
- Active
- Action Needed
- Top blocker

**Savings Opportunity charts**

These charts show:

- savings by category
- severity distribution
- status distribution

**Highest Value Recommendations**

This table highlights the top recommendations based on financial impact and includes fields such as recommendation ID, severity, category, owner, due date, confidence, monthly savings, missed savings, and status.

#### Recommended user behavior

1. Review the KPI cards
2. Apply filters if needed
3. Review the charts for major problem areas
4. Scan the Highest Value Recommendations table
5. Move into the Recommendations page for detailed action

#### Why this page matters

The Overview page answers one central question:

**Where should we focus first to reduce Snowflake cost and improve operational efficiency?**

### Recommendations

The **Recommendations** page is the main workflow page in CostOps. It is where users review savings opportunities, assign ownership, move recommendations through implementation stages, and track audit history.

#### What this page is for

Use the Recommendations page to:

- review the prioritized backlog of optimization opportunities
- filter recommendations by severity, status, category, team, owner, and confidence
- select a recommendation and review its detail
- assign ownership and due dates
- log SQL copy activity
- move a recommendation through its lifecycle from discovery to realization

#### Main sections

**Filter bar**

The page supports filters for:

- Severity
- Status
- Category
- Team
- Owner
- Minimum confidence
- Sort

**KPI summary cards**

The page includes summary cards for:

- Estimated Monthly Spend
- Monthly Savings Opportunity
- Realized Monthly Savings
- Critical Findings

**Recommendation summary chips**

Compact indicators summarize:

- total findings
- savings opportunity
- missed savings
- average recommendation age
- overdue items
- realized savings

**Recommendation backlog table**

This is the main table where users review and select recommendations. It includes columns such as:

- recommendation ID
- severity
- category
- title
- owner
- team
- due date
- confidence
- daily savings
- monthly savings
- missed savings
- days to due
- risk
- effort
- status

**Selected recommendation detail**

When a user selects a row, the lower detail section updates to show:

- recommendation title
- summary metrics
- descriptive guidance
- related Snowflake object
- current ownership and status

**Generated SQL or implementation guidance**

If available, implementation guidance appears to the right, along with the ability to log that SQL was copied.

**Assignment section**

This section supports:

- owner
- team
- role
- due date
- assignment notes

**Workflow stage**

The workflow ribbon shows the lifecycle stage:

- Proposed
- Selected
- Accepted
- Implemented
- Realized

**Lifecycle and audit panel**

This section shows milestone information and a recent audit event table for the selected recommendation.

#### Recommended user behavior

1. Apply filters to narrow the backlog
2. Select a recommendation
3. Review the detail and expected savings
4. Assign ownership and due date if needed
5. Review or copy the SQL
6. Move the item through the workflow
7. Use the audit section to confirm history and actions

#### Why this page matters

The Recommendations page is the operational core of CostOps because it turns detected inefficiencies into managed, trackable work.

### My Work

The **My Work** page is the focused execution view for individual owners, teams, or roles. It helps users work from their own assigned queue rather than the full recommendation backlog.

#### What this page is for

Use the My Work page to:

- view recommendations by owner, team, or role
- focus only on assigned items
- see overdue work and near-term due items
- understand the open savings tied to a specific person or group
- manage recommendation detail and workflow from a narrower operational view

#### Main sections

**Work queue filters**

The page supports:

- View by
- Owner / Team / Role
- Open only
- Lane
- Category

**Summary metrics**

The top metrics show:

- Owned recommendations
- Overdue
- Due in 7 days
- Open monthly savings

**Work queue summary**

This section provides a compact summary of the selected lane and its related value.

**Due queue table**

This table highlights current due items with fields such as title, owner, due date, days to due, and missed savings.

**Owned Queue**

The Owned Queue table is the main working table for the selected owner, team, or role.

**Selected recommendation detail**

The lower section updates when a recommendation is selected and supports the same core actions as the Recommendations page.

**Generated SQL or implementation guidance**

SQL guidance appears to the right when available, along with the ability to log copy activity.

**Assignment section**

Users can review or update assignment details from this page.

**Workflow stage**

The lifecycle ribbon shows where the selected recommendation stands.

**Lifecycle and audit detail**

The page also shows milestone values and recent audit events for traceability.

#### Recommended user behavior

1. Choose a view by owner, team, or role
2. Enable Open only when focusing on unresolved work
3. Review the summary metrics and due queue
4. Select a recommendation from the Owned Queue
5. Review the detail and expected savings
6. Copy or review SQL if needed
7. Update assignment or workflow stage as work progresses

#### Why this page matters

The My Work page answers:

**What am I responsible for right now, and what value is attached to it?**

### Scan & Schedule

The **Scan & Schedule** page is the operational control page for CostOps analysis runs. It allows users to review scan freshness, understand scan economics, configure scan timing, and run new analysis against the Snowflake environment.

#### What this page is for

Use the Scan & Schedule page to:

- see when the last analysis run occurred
- understand whether scan data is current
- review scan credit and cost estimates
- see how much savings was identified by the latest scan
- configure when scans should run
- run a new analysis manually
- review scan history over time

#### Main sections

**Enterprise scan context banner**

For Enterprise tenants, a banner may explain whether the scan context is fully ready and what blockers remain.

**Scan Control**

The page shows:

- Last Full Scan
- Freshness
- Scan Credits
- Scan Cost
- Identified Monthly Savings
- Savings Found per $1 Scan Cost

**Enterprise environment context**

For Enterprise accounts, the page also shows:

- Production account
- App instance
- Linked validation environments

**Scan scheduling controls**

Typical controls include:

- Schedule
- Preferred scan time
- Scan scope
- Lookback window
- Next scheduled scan
- Run analysis now

**Analysis runner explanation**

The page explains the difference between sample mode and Snowflake mode.

**Analysis Runner Coverage**

This table summarizes:

- warehouse metering
- query/workload history
- task history
- storage objects

along with rows available and rules applied.

**Scan Run History**

The scan history table shows prior runs and includes fields such as:

- scan ID
- scan type
- scan scope
- started at
- completed at
- status
- frequency
- lookback days
- credits
- found / new / updated
- error message

#### Recommended user behavior

1. Review the last scan and freshness status
2. Check the scan cost and identified savings
3. Confirm production and validation context if on Enterprise
4. Adjust schedule, scan scope, or lookback if needed
5. Run an ad hoc analysis when fresh results are needed
6. Review scan history to confirm successful execution

#### Why this page matters

The Scan & Schedule page answers:

**When did CostOps last analyze the environment, what did it cost, and how much value did that scan uncover?**

## 2. Analysis

The Analysis section breaks down the main technical domains that CostOps evaluates inside Snowflake.

### Warehouses

The **Warehouses** page focuses on Snowflake warehouse cost, utilization, queueing behavior, and resume activity.

#### What this page is for

Use the Warehouses page to:

- analyze warehouse-level spend
- compare utilization against cost
- identify oversized or underutilized warehouses
- review queueing and resume behavior
- support rightsizing decisions

#### Main sections

**KPI summary cards**

These connect warehouse analysis to cost and savings context.

**Warehouse cost trend**

The top chart shows warehouse cost over time and helps users identify major compute contributors.

**Warehouse summary scatterplot**

The lower-left chart compares average utilization and weekly cost.

**Warehouse summary table**

The lower-right table provides exact values for cost, utilization, queued seconds, and resumes.

#### Recommended user behavior

1. Review the top cost contributors
2. Compare utilization and cost
3. Validate details in the summary table
4. Move into Recommendations if warehouse actions have already been generated

#### Why this page matters

The Warehouses page answers:

**Are we paying for more warehouse capacity than we actually need?**

### Workloads

The **Workloads** page analyzes query, transformation, dashboard, ingestion, task, ad hoc, and procedure workloads by cost, scan volume, runtime, and spill.

#### What this page is for

Use the Workloads page to:

- compare workload cost
- identify expensive transformations or queries
- review scan volume and runtime behavior
- spot workloads that may benefit from redesign

#### Main sections

**Workload cost ranking**

The left chart ranks workloads by cost and groups them by category.

**Runtime versus scan-volume scatterplot**

The right chart compares GB scanned and average runtime across workload categories.

**Workload Drilldown**

The lower table shows detailed workload-level fields including:

- workload
- cost
- warehouse
- query count
- runtime
- GB scanned
- spill
- category

#### Recommended user behavior

1. Review the cost ranking
2. Use the scatterplot to identify inefficient patterns
3. Confirm exact values in the drilldown table
4. Move to Recommendations if workload-related items already exist

#### Why this page matters

The Workloads page answers:

**Which workloads are actually driving Snowflake cost, and are they using compute efficiently?**

### Storage

The **Storage** page helps users understand storage cost, retention, staleness, and clone or cleanup opportunities.

#### What this page is for

Use the Storage page to:

- review total storage cost
- identify stale objects
- find high-retention objects
- detect clone or drop candidates
- compare object-level storage cost

#### Main sections

**Storage summary metrics**

The page surfaces:

- Monthly Storage Cost
- Stale Objects
- High Retention Objects
- Clone / Drop Candidates

**Storage footprint treemap**

The left treemap shows how cost is distributed across databases, schemas, and objects.

**Ranked object cost view**

The right chart ranks objects by monthly storage cost and classification.

**Storage Object Review**

The lower table includes fields such as:

- object name
- database
- schema
- object type
- size
- monthly cost
- last queried days
- retention days
- access count
- clone group
- classification

#### Recommended user behavior

1. Review the top metrics
2. Use the treemap to understand where storage is concentrated
3. Review the ranked object chart
4. Inspect the object review table
5. Move into Recommendations if storage actions have already been generated

#### Why this page matters

The Storage page answers:

**What data are we still paying to keep, and do we still need it in its current form?**

### Tasks

The **Tasks** page analyzes task activity, runtime behavior, failures, and compute cost.

#### What this page is for

Use the Tasks page to:

- review task execution volume
- identify tasks with high failure rates
- compare estimated compute cost across tasks
- detect high-frequency task activity
- support scheduling and orchestration optimization

#### Main sections

**Task summary metrics**

The page shows:

- 7-Day Task Executions
- 7-Day Failures
- Estimated Compute Cost
- High-Frequency Tasks

**Task cost ranking**

The left chart ranks tasks by estimated compute cost.

**Runtime versus execution scatterplot**

The right chart compares executions over 7 days and average runtime.

**Task Review Queue**

The lower table includes:

- task name
- database
- schema
- warehouse
- schedule
- executions
- failures
- runtime
- cloud credits
- compute cost
- last state
- recommendation

#### Recommended user behavior

1. Review the top metrics
2. Identify high-cost tasks
3. Use the scatterplot to spot noisy or unstable tasks
4. Review the detailed queue
5. Use the recommendation column to guide next actions

#### Why this page matters

The Tasks page answers:

**Are our recurring tasks running at the right cadence and with acceptable reliability, or are they creating unnecessary cost and churn?**

## 3. Value

The Value section translates technical findings into measurable ROI, savings tracking, and evidence for leadership or finance.

### Savings Realization

The **Savings Realization** page shows how much projected value has actually been captured over time.

#### What this page is for

Use the Savings Realization page to:

- compare projected opportunity with realized savings
- track missed savings from unresolved recommendations
- review open recommendations
- understand savings performance by category, status, team, and ownership

#### Main sections

**Filter bar**

Filters include:

- Status
- Category
- Team
- Owner
- Minimum confidence

**Period selector**

The page supports:

- MTD
- QTD
- YTD
- Since inception

**Savings summary metrics**

The page shows:

- Realized Savings
- Projected Opportunity
- Missed Savings
- Open Recommendations

**Savings by category chart**

This compares projected, realized, and missed value by category.

**Ownership / team savings view**

This compares projected monthly savings and missed savings across teams or ownership groups.

**Savings Lifecycle by Status**

This table shows projected monthly, realized monthly, missed savings, projected annual, and recommendation counts by status.

**Aging and Ownership Queue**

The lower table shows aging recommendations with ownership and missed value context.

#### Recommended user behavior

1. Choose the reporting period
2. Apply filters as needed
3. Review the top savings metrics
4. Review category and team value distribution
5. Review lifecycle by status
6. Use the ownership queue to follow up on unresolved items

#### Why this page matters

The Savings Realization page answers:

**How much value have we actually captured, and how much are we still leaving unrealized?**

### Reports

The **Reports** page is the primary reporting and export surface in CostOps.

#### What this page is for

Use the Reports page to:

- generate filtered reports across savings, lifecycle, ownership, and enterprise readiness
- compare projected, realized, and missed savings
- prepare finance-friendly reporting packets
- review enterprise rollout context alongside cost outcomes
- export structured reporting views

#### Main sections

**Enterprise reporting context banner**

This may show rollout blockers or reporting-context limitations.

**Report configuration controls**

Common controls include:

- Report
- Time range
- Category
- Team
- Owner
- Status
- Severity
- Report detail
- Download format
- Download report

**Supported report types**

The page supports:

- Comprehensive finance packet
- Executive ROI summary
- Savings by team
- Savings by category
- Recommendation lifecycle
- Unresolved opportunity
- Owner accountability
- Users and roles
- Scan ROI history
- Enterprise readiness
- Enterprise config audit trail
- Recommendation backlog
- Recommendation audit trail
- Custom report

**KPI summary cards**

The page surfaces:

- Realized Savings
- Projected Savings
- Annualized Opportunity
- Unresolved Missed Savings
- Savings Found per $1 Scan Cost
- Net Monthly Benefit Found

**Executive Summary**

This provides a narrative explanation of the selected report context.

**Enterprise Context**

This section summarizes the production account, region, app instance, billing scope, and linked validation environments.

**Executive ROI Summary**

This section compares spend, opportunity, realized savings, and unresolved value in one structured view.

**Additional report sections**

Depending on the report type, detailed sections may include:

- savings by category
- savings by team
- recommendation lifecycle
- unresolved opportunity
- owner accountability
- users and roles
- scan ROI history
- backlog
- audit trail
- enterprise readiness
- enterprise config audit

#### Recommended user behavior

1. Choose the report type
2. Set the time range
3. Apply filters
4. Choose detail level and format
5. Review summary metrics and narrative
6. Review the detailed sections below
7. Download the report if needed

#### Why this page matters

The Reports page answers:

**How do we turn recommendations and activity into a clear, shareable story about value, ownership, and progress?**

## 4. Admin

The Admin section controls enterprise readiness, roles, environments, persistence, identity, support posture, people management, and application settings.

### Enterprise Controls

The **Enterprise Controls** page acts as the enterprise command center for rollout readiness and native control-plane progress.

#### What this page is for

Use the Enterprise Controls page to:

- review enterprise rollout readiness
- identify incomplete enterprise setup areas
- understand rollout blockers
- confirm enterprise feature availability
- sync enterprise configuration into Snowflake
- monitor overall enterprise configuration status

#### Main sections

**Enterprise status banners**

These explain:

- enterprise pricing and scope
- current enterprise posture
- whether the workflow is still modeled or fully production-ready

**Sync native control plane**

This action writes the enterprise settings, user directory, and enterprise config audit data into Snowflake.

**Enterprise readiness metrics**

The page shows:

- Enterprise readiness
- Active areas
- Ready for validation
- Action needed

**Rollout blockers**

The page surfaces current blockers such as missing production account or incomplete persistence setup.

**Enterprise Feature Status**

Feature cards summarize enterprise areas such as:

- SSO & Identity
- RBAC Mapping
- Dedicated Persistence
- SLA & Support
- Linked Dev/Test
- Production Instance

**Enterprise readiness rollup**

This summarizes the readiness state of the major enterprise setup areas.

#### Recommended user behavior

1. Review the status banners and readiness metrics
2. Review blockers
3. Review feature status and readiness rollup
4. Use Sync native control plane when configuration should be written into Snowflake
5. Move into the detailed enterprise admin pages as needed

#### Why this page matters

The Enterprise Controls page answers:

**Are we operationally ready to run CostOps as an enterprise-managed platform in this Snowflake environment?**

### RBAC Mapping

The **RBAC Mapping** page is used to map Snowflake or identity roles into CostOps application roles.

#### What this page is for

Use the RBAC Mapping page to:

- map source roles to CostOps roles
- define a default CostOps role
- choose a role onboarding strategy
- manage individual mappings
- review coverage across Admin, Operator, and Viewer

#### Main sections

**Mapping summary metrics**

The page shows:

- mapped source roles
- CostOps role coverage
- active mappings
- ready for validation

**RBAC status and default role**

This section defines the overall RBAC posture and fallback behavior.

**Role onboarding path**

The page supports:

- Map existing roles
- Use recommended roles

**Mapping action controls**

Users can:

- edit mapping
- remove mapping
- add mapping
- save

**Source role mapping editor**

Typical fields include:

- source role
- CostOps role
- scope
- mapping status

**Mapping Coverage**

This table confirms whether Admin, Operator, and Viewer are covered.

**Current Role Mappings**

This section lists the current role mappings in effect.

**Effective access preview**

This helps validate how mappings will behave.

#### Recommended user behavior

1. Review the summary metrics
2. Choose the onboarding path
3. Define the default role
4. Add or edit source-role mappings
5. Confirm full coverage
6. Review current mappings and effective access behavior

#### Why this page matters

The RBAC Mapping page answers:

**Who should be able to administer, operate, and view CostOps, and how does that map back to our Snowflake or identity access model?**

### Environments

The **Environments** page is used to define the production Snowflake account and linked validation environments.

#### What this page is for

Use the Environments page to:

- define the production Snowflake account
- record the production region and installed app instance
- identify the billing scope
- register linked development and test environments
- document the purpose and status of each validation environment

#### Main sections

**Environment summary metrics**

The page shows:

- Production instance
- Linked validation environments
- Configured account locators
- Active linked environments

**Production environment configuration**

This section defines:

- production status
- production account
- region
- installed app instance
- billing scope

**Linked environment controls**

This section supports:

- linked environment status
- edit environment
- remove environment
- add environment
- environment details
- save

**Environment Readiness**

This table shows production and validation environments in one structured view.

**Linked Validation Environments**

This table focuses only on the linked validation environments.

#### Recommended user behavior

1. Define the production account first
2. Confirm the billing scope
3. Enter the production region and app instance
4. Add development and test validation environments
5. Document purpose and status
6. Review readiness

#### Why this page matters

The Environments page answers:

**Which Snowflake account is the real production instance, and which linked accounts are being used to validate changes before rollout?**

### Persistence

The **Persistence** page documents where enterprise application data lives and whether the persistence model is ready for validation.

#### What this page is for

Use the Persistence page to:

- define the persistence target
- document the isolation model
- set retention expectations
- track backup readiness
- track restore-test readiness

#### Main sections

**Persistence summary metrics**

The page shows:

- Persistence status
- Target
- Retention
- Restore readiness

**Persistence guidance banner**

This explains that the page captures where enterprise data lives, how it is isolated, and whether backup and restore are ready.

**Persistence configuration controls**

Typical fields include:

- persistence status
- persistence target
- isolation model
- retention
- backup status
- restore test status
- save

**Persistence Readiness**

This table summarizes the persistence target, isolation, retention, backup cadence, and restore test posture.

#### Recommended user behavior

1. Review the top-level persistence posture
2. Confirm the persistence target
3. Define the isolation model
4. Set retention
5. Document backup and restore readiness
6. Review the Persistence Readiness table

#### Why this page matters

The Persistence page answers:

**Where does CostOps data live, how is it isolated, and can we trust that it is durable and recoverable?**

### SSO & Identity

The **SSO & Identity** page is used to define and document the enterprise identity setup required for future sign-in integration.

#### What this page is for

Use the SSO & Identity page to:

- define the identity provider
- choose the sign-in protocol
- record the allowed domain
- capture metadata details
- identify the implementation contact

#### Main sections

**Identity summary metrics**

The page shows:

- SSO status
- Identity provider
- Protocol
- Allowed domain

**Identity guidance banner**

This explains that the page is for provider, domain, metadata, and validation-readiness setup.

**Identity configuration controls**

Typical fields include:

- SSO status
- SSO provider
- Identity protocol
- Allowed domain
- Metadata URL
- Entity ID
- Implementation contact
- save

**Identity Readiness**

This table summarizes provider, protocol, allowed domain, metadata URL, and implementation contact.

#### Recommended user behavior

1. Define the provider
2. Confirm the protocol
3. Enter the allowed domain
4. Record metadata details
5. Assign the implementation contact
6. Review the Identity Readiness table

#### Why this page matters

The SSO & Identity page answers:

**How will users authenticate into CostOps, and how close are we to having that identity model ready for rollout?**

### SLA & Support

The **SLA & Support** page defines the support model for an Enterprise deployment.

#### What this page is for

Use the SLA & Support page to:

- define the support tier
- record the expected response window
- assign a deployment owner
- document the escalation path
- capture support notes

#### Main sections

**Support summary metrics**

The page shows:

- SLA status
- Support tier
- Response window
- Deployment owner

**Support guidance banner**

This explains that the page is for defining support expectations and ownership before go-live.

**Support configuration controls**

Typical fields include:

- SLA status
- Support tier
- Response window
- Deployment owner
- Escalation path
- Support notes
- save

**Support Readiness**

This table summarizes support tier, response window, owner, escalation path, and notes.

#### Recommended user behavior

1. Define the support tier
2. Confirm the response window
3. Assign the deployment owner
4. Document the escalation path
5. Capture support notes
6. Review the Support Readiness table

#### Why this page matters

The SLA & Support page answers:

**Who owns support for this deployment, what response should be expected, and how will issues be escalated if something goes wrong?**

### Users and Roles

The **Users and Roles** page manages the internal assignment structure used for ownership, routing, and application access.

#### What this page is for

Use the Users and Roles page to:

- manage teams
- maintain the user directory
- assign business roles
- assign application access roles
- support recommendation ownership routing

#### Main sections

**Manage Teams**

Administrators can:

- edit team
- remove team
- add team
- save

**Team list**

This table shows the current team catalog.

**Manage Users**

Administrators can:

- add new
- edit existing
- remove
- save

Typical fields include:

- person name
- team
- business role
- application access role
- email

**Current Directory**

This table shows current user assignments and access roles.

**Business Role Catalog**

This provides the internal business role list used across the platform.

**Application Access Roles**

This lists the CostOps application-level access roles.

#### Recommended user behavior

1. Review the team structure
2. Add or update teams as needed
3. Maintain the user directory
4. Confirm that each user has the correct team, role, and access level
5. Review the Current Directory for consistency

#### Why this page matters

The Users and Roles page answers:

**Who owns the work in CostOps, how are they organized, and what level of access do they need?**

### Settings

The **Settings** page is the main operational configuration page for CostOps.

#### What this page is for

Use the Settings page to:

- control session mode and data source
- define financial assumptions
- tune recommendation thresholds
- control data thresholds
- test Snowflake connectivity
- support native readiness setup

#### Main sections

**Session Controls**

This section controls:

- Session role mode
- Access role
- Resolved CostOps role
- Data source

**Cost Model**

Typical settings include:

- credit price
- lookback days
- annualization months
- minimum monthly savings
- default recommendation confidence

**Rule Thresholds**

Typical settings include:

- warehouse utilization ceiling
- warehouse monthly cost floor
- warehouse resume threshold
- task execution threshold
- task failure threshold

**Data Thresholds**

Typical settings include:

- stale object threshold
- full refresh scan threshold
- runtime threshold
- spill threshold
- due days by severity

**Recommendation behavior controls**

Examples include:

- read-only recommendations
- generate implementation SQL
- allow approved SQL execution

**Snowflake Connection**

This section summarizes the current Snowflake connection configuration.

**Native and persistence readiness actions**

This broader workflow also includes actions such as:

- testing Snowflake connection
- initializing the persistence schema
- syncing the native control plane

#### Recommended user behavior

1. Confirm the session role and data source
2. Review the cost model assumptions
3. Tune rule and data thresholds as needed
4. Save threshold settings
5. Review Snowflake connection status
6. Use native-readiness actions when preparing for deployment or testing

#### Why this page matters

The Settings page answers:

**How is CostOps currently configured to interpret data, generate recommendations, and connect to Snowflake?**

## Suggested next documentation steps

The next best documentation steps after this draft are:

1. Add screenshots page by page
2. Shorten or tighten sections where needed for the final audience
3. Decide whether the first guide is aimed at:
   - executives
   - general users
   - admins
4. Convert the guide into:
   - a formatted PDF
   - website-ready content
   - short training or YouTube scripts

## Production follow-up checklist

Save these as future documentation and enablement tasks:

- Use this guide as the base script for a short CostOps overview video
- Capture clean screenshots for all major pages
- Expand this guide into a fuller illustrated instruction manual
- Break the guide into website-ready documentation sections
- Create short walkthroughs for pages that are more complex:
  - Recommendations
  - Scan & Schedule
  - Reports
  - Enterprise Controls
  - RBAC Mapping
  - Users and Roles
