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

## Planned, not implemented

These domains correspond to the approved schema and require separate approval
and one-app-at-a-time implementation:

- **Company resources:** company documents and external connections.
- **AI agents:** company-scoped agent records.
- **Projects:** projects and project requirements.
- **Recommendations and assignments:** candidate recommendations and project
  members with the approved exactly-one-candidate constraints.

These are planning groupings only; they do not define new database tables or
alter the approved DBML.

## Request flow

Requests enter through `config.urls`, which mounts the accounts URL
configuration at `/api/v1/accounts/` and the companies URL configuration at
`/api/v1/companies/` and the workforce URL configuration at
`/api/v1/workforce/`. Public registration and token endpoints use dedicated
DRF views and serializers. All company and workforce endpoints require JWT
authentication. Company and workforce querysets are scoped to the requesting
user's membership. The profile and membership serializers expose only safe
user fields.

## Database boundary

The approved DBML is preserved verbatim in [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md).
The company and workforce migrations implement only their approved tables.
Django auth and Simple JWT own their framework tables and migrations
independently of that business schema.
