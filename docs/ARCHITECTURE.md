# Agentix backend architecture

## Implemented

- **Django project:** `agentix_backend/config` holds project settings and root
  URL configuration.
- **Accounts API:** `agentix_backend/accounts` uses Django's existing auth
  user model and Django REST Framework. Simple JWT provides 15-minute access
  tokens, 7-day refresh tokens, rotation, and blacklist support.
- **Companies API:** `agentix_backend/companies` owns only the approved
  `companies` and `company_users` tables. It uses the configured Django user
  model for company creators and memberships, and scopes reads to company
  membership.
- **Workforce API:** `agentix_backend/workforce` owns only the approved
  `departments`, `employees`, `employee_ai_profiles`, `skills`, and
  `employee_skills` tables. All querysets are company-scoped through the
  authenticated user's memberships. Owners, admins, and managers can write;
  members are read-only.
- **Documents API:** `agentix_backend/documents` owns only the approved
  `company_documents` table. Document records are scoped to company
  memberships; owners, admins, and managers can write while members can read.
  The `file_path` field is metadata only and does not imply file upload or
  storage.
- **Integrations API:** `agentix_backend/integrations` owns only the approved
  `connections` table. Connection records are company-scoped, and provider
  and status values are metadata only. The app does not authenticate with
  external providers or store credentials.
- **Agents API:** `agentix_backend/agents` owns only the approved `ai_agents`
  table. Agent records are company-scoped metadata; they do not execute tasks,
  call tools, or run AI workflows.
- **Projects API:** `agentix_backend/projects` owns only the approved
  `projects`, `project_requirements`, and `project_members` tables. All
  project data is company-scoped; project-member assignments are restricted
  to exactly one same-company employee or AI agent.
- **Recommendations API:** `agentix_backend/recommendations` owns only the
  approved `recommendations` table. Records are scoped through their project
  company and must reference exactly one same-company employee or AI agent.
  The app stores recommendation records; it does not generate or score them.
- **Persistence configuration:** PostgreSQL remains the configured database;
  connection details and the Django secret key are read from environment
  variables.
- **Authentication persistence:** Django's standard auth tables and Simple
  JWT blacklist tables are managed by their upstream migrations. The accounts
  app defines no models and adds no business tables.

Registration creates only a user. Company creation is a separate,
authenticated API operation and atomically creates the creator's owner
membership. Owners alone may update company details; all company members can read company
details and membership. Workforce records are readable by company members and
writable only by owners, admins, and managers. No custom user table is defined.

## Not implemented

The frontend remains planned. No other business app beyond those listed above
is implemented.

## Request flow

Requests enter through `config.urls`, which mounts the accounts URL
configuration at `/api/v1/accounts/`, companies at `/api/v1/companies/`,
workforce at `/api/v1/workforce/`, documents at `/api/v1/documents/`, and
integrations at `/api/v1/integrations/`, agents at `/api/v1/agents/`, and
projects at `/api/v1/projects/`, and recommendations at
`/api/v1/recommendations/`. Public registration and token endpoints use
dedicated DRF views and serializers. Company, workforce, document,
integrations, agents, projects, and recommendations endpoints require JWT
authentication. Their querysets are scoped to the requesting user's company
membership. The profile and membership serializers expose only safe user
fields.

## Database boundary

The approved DBML is preserved verbatim in [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md).
The company, workforce, documents, integrations, agents, projects, and
recommendations migrations implement only their approved tables. Django auth
and Simple JWT own their framework tables and migrations independently of
that business schema.
