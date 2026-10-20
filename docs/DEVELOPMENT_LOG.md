# Development log

## 2026-10-19 — Initial accounts app

### Changes

- Inspected the existing Django project, settings, URL configuration,
  dependencies, virtual environment, repository status, and local PostgreSQL
  listener.
- Added the `accounts` app using Django's existing user model without custom
  user or business models.
- Added registration with Django password validation and hashing; token
  obtain, refresh, and blacklist endpoints; and an authenticated safe profile
  endpoint.
- Configured Simple JWT for 15-minute access tokens, 7-day refresh tokens,
  rotation, and blacklist-after-rotation.
- Moved Django secret and PostgreSQL connection credentials to environment
  variables.
- Added accounts API tests and project documentation, including the approved
  DBML schema.

### Verification

- `python manage.py test accounts --verbosity 1`: **12 tests passed** using
  the PostgreSQL test database. The test runner created and removed
  `test_Agentix`; it did not delete development data.
- The initial test run exposed two test expectation/setup mistakes (the
  duplicate-username fixture used another username, and Simple JWT logout
  responds with HTTP 200). Both tests were corrected, and the full suite
  passed on rerun.
- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no model
  changes detected.
- `python manage.py migrate --noinput`: applied the pending Simple JWT
  blacklist migrations to the configured database; no business tables were
  introduced.
- `python manage.py showmigrations auth token_blacklist`: all migrations
  applied after migration.
- Resolved all five accounts endpoint paths successfully.

### Known issues

- `DJANGO_SECRET_KEY` must be set in the runtime environment. PostgreSQL
  connection variables are also read from the runtime environment.

## 2026-10-19 — Root dotenv configuration

### Changes

- Added `python-dotenv` and load the repository-root `.env` before reading
  settings.
- Kept PostgreSQL as the database backend and made `DB_PASSWORD` explicitly
  required alongside `DJANGO_SECRET_KEY`. Database name, user, host, and port
  retain their defaults when unset.
- Added a placeholder-only `.env.example` and updated `.gitignore` so `.env`
  remains ignored while `.env.example` can be committed.
- Updated the README with Windows instructions for copying and configuring
  `.env`.

### Verification

- `python manage.py check`: passed with configuration loaded from root
  `.env`, after clearing process environment overrides.
- `python manage.py test accounts --verbosity 1`: all 12 tests passed
  against PostgreSQL using root `.env` configuration; the temporary test
  database was removed by Django.
- `git check-ignore .env`: confirmed the local environment file is ignored.
- `.env.example` is not ignored and contains placeholder values only.

## 2026-10-19 — Companies app

### Changes

- Added only `companies.Company` and `companies.CompanyUser`, mapped to the
  approved `companies` and `company_users` table names and using Django's
  configured user model.
- Added the authenticated company create/list/detail/patch/member APIs.
  Company creation atomically creates an owner membership; membership-scoped
  reads return 404 for inaccessible company IDs.
- Chose owner-only company updates as the least-privilege rule. Admin,
  manager, and member roles may read accessible company data but may not
  update company details.
- Added the initial companies migration and focused API/database tests.

### Verification

- `python manage.py check`: passed.
- `python manage.py makemigrations --check --dry-run`: passed with no changes
  remaining after migration generation.
- `python manage.py migrate --noinput`: applied
  `companies.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test companies accounts --verbosity 2`: all 23 tests
  passed against PostgreSQL's temporary `test_Agentix` test database.
- Tests cover owner creation and atomic rollback, authorized and unauthorized
  reads, owner/admin/manager/member update permissions, duplicate creator and
  membership prevention, unauthenticated requests, input validation, and
  route resolution.
- No other business app or table was added.

## 2026-10-19 — Workforce app

### Changes

- Added the five approved workforce models with explicit DBML table names,
  relationships, nullability, defaults, and uniqueness constraints.
- Added authenticated CRUD routes for departments, employees, nested
  employee AI profiles, company skills, and employee-skill assignments.
- Scoped workforce reads to the caller's company memberships. Owners,
  admins, and managers can write; members are read-only. Write permission is
  checked against the specific company for object changes.
- Validated relationship IDs against companies where the user has write
  permission and rejected employee-skill links crossing company boundaries.
- Preserved same-company employee-skill integrity when department, employee,
  or skill company relationships are changed.
- Added the initial workforce migration and endpoint, constraint, and
  cross-company authorization tests.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied
  `workforce.0001_initial` and
  `workforce.0002_alter_department_created_at_and_more` to PostgreSQL
  `Agentix`; the latter preserves database-side `now()` defaults for
  workforce timestamps.
- An earlier `python manage.py test workforce companies accounts
  --verbosity 1` run passed all 40 tests against PostgreSQL's temporary
  `test_Agentix` database; Django removed the temporary test database.
- After adding another role-permission test, the subsequent 41-test run
  failed with five database connection errors when the PostgreSQL Windows
  service stopped.
- After PostgreSQL became available again, `python manage.py test workforce
  companies accounts --verbosity 2 --keepdb` passed all 41 tests against the
  existing PostgreSQL `test_Agentix` database. The database was preserved by
  `--keepdb`.
- `python manage.py check` and `python manage.py makemigrations --check
  --dry-run` both passed after the recovery.
- Resolved every workforce route and confirmed the active Django database
  configuration uses `django.db.backends.postgresql` with name `Agentix`.
- No documents, connections, AI agents, projects, recommendations, or other
  unapproved business models were added.

## 2026-10-19 — Documents app

### Changes

- Added only the approved `CompanyDocument` model, mapped to
  `company_documents` with the approved fields, relation, and timestamp
  defaults.
- Added authenticated list/create and detail/retrieve/update/delete routes
  under `/api/v1/documents/`.
- Scoped reads to company memberships and writes to owners, admins, and
  managers. Company IDs supplied on writes are restricted to companies where
  the requester has a writable membership; inaccessible document IDs return
  404.
- Implemented `file_path` as nullable metadata only; no file upload or
  storage behavior is claimed.
- Added documents API and permission tests and registered the app and routes.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied
  `documents.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test documents companies accounts workforce --verbosity
  2 --keepdb`: all 51 tests passed against the existing PostgreSQL
  `test_Agentix` test database; it was preserved.
- Both document URL patterns resolved successfully in the automated tests.
- No integrations, agents, projects, recommendations, or other unapproved
  apps or business tables were added.

## 2026-10-19 — Integrations app

### Changes

- Added only the approved `Connection` model mapped to the `connections`
  table, including the company relation, provider metadata, `disconnected`
  status default, and nullable `connected_at`.
- Added authenticated connection list/create and detail/retrieve/update/delete
  routes under `/api/v1/integrations/`.
- Scoped reads to company members and writes to owners, admins, and managers.
  Company IDs supplied on create/update must belong to a company where the
  requester has a writable membership; inaccessible records return 404.
- Limited this app to connection metadata. It does not establish or verify
  external provider connections or store credentials, API keys, or tokens.
- Added the initial migration, API tests, and integrations module
  documentation.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied
  `integrations.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test integrations companies accounts workforce documents
  --verbosity 2 --keepdb`: all 62 tests passed against the existing
  PostgreSQL `test_Agentix` test database; it was preserved.
- Both integration URL patterns resolved successfully.
- No agents, projects, recommendations, or other unapproved apps/tables were
  added.

## 2026-10-19 — Agents app

### Changes

- Added only the approved `AIAgent` model mapped to `ai_agents`, with the
  company relation, metadata fields, `active` status default, and
  current-timestamp defaults.
- Added authenticated agent list/create and detail/retrieve/update/delete
  routes under `/api/v1/agents/`.
- Scoped reads to company members and writes to owners, admins, and managers.
  Company IDs supplied on create/update must belong to a company where the
  requester has a writable membership; inaccessible records return 404.
- Limited the app to agent records and metadata. It does not execute
  autonomous tasks, call tools, run AI workflows, or handle credentials.
- Added the initial migration, API tests, and agents module documentation.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied `agents.0001_initial` to
  PostgreSQL `Agentix`.
- `python manage.py test agents companies accounts workforce documents
  integrations --verbosity 2 --keepdb`: all 75 tests passed against the
  existing PostgreSQL `test_Agentix` test database; it was preserved.
- Both agent URL patterns resolved successfully.
- No projects, recommendations, or other unapproved apps/tables were added.

## 2026-10-19 — Projects app

### Changes

- Added only the approved `Project`, `ProjectRequirement`, and `ProjectMember`
  models mapped to their exact DBML table names and existing `Company`,
  `Employee`, and `AIAgent` model classes.
- Added authenticated project CRUD and nested project requirement and member
  CRUD routes under `/api/v1/projects/`.
- Scoped project and nested-resource queries to the user's company
  memberships. Owners, admins, and managers can write; members can read.
- Validated that a project member references exactly one employee or AI
  agent, that the candidate belongs to the project's company, and that
  company changes cannot invalidate existing project-member assignments.
- Added the initial migration and project API tests.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied `projects.0001_initial` to
  PostgreSQL `Agentix`; the migration is recorded as applied.
- `python manage.py test projects agents workforce companies accounts
  documents integrations --verbosity 2 --keepdb`: all 91 tests passed
  against the existing PostgreSQL `test_Agentix` test database; it was
  preserved.
- Project, requirement, and member route patterns resolved in the tests.
- Confirmed the configured database remains PostgreSQL `Agentix`.

## 2026-10-19 — Recommendations app

### Changes

- Added only the approved `Recommendation` model and `recommendations` table,
  referencing the existing `Project`, `Employee`, and `AIAgent` models.
- Added database and serializer validation requiring exactly one employee
  or AI-agent target.
- Added authenticated list/create and detail/retrieve/update/delete routes,
  plus a project-scoped recommendation listing route.
- Scoped all record and project queries through company membership. Owners,
  admins, and managers can write; members can read. Candidate targets are
  checked against the project's company.
- The app stores recommendation records only; no recommendation-generation
  or AI-scoring algorithm was added.
- Added the initial migration, API tests, and module documentation.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied
  `recommendations.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test recommendations projects agents workforce companies
  accounts documents integrations --verbosity 2 --keepdb`: all 108 tests
  passed against the existing PostgreSQL `test_Agentix` test database; it was
  preserved.
- Recommendation list, detail, and project-scoped list routes resolved in
  the tests.
- Confirmed the configured database is PostgreSQL `Agentix`.

## 2026-10-20 — Django Admin configuration

### Changes

- Registered the existing company, workforce, document, connection, AI agent,
  project, and recommendation models in their app admin modules. Accounts
  continues to use Django's standard registered User and Group administration;
  it defines no models.
- Added useful list columns, searches, filters, ordering, relationship
  selectors, read-only timestamps, and company/project/employee inlines.
- Added admin form validation for employee-skill company consistency and
  project-member/recommendation one-candidate and same-company rules. Existing
  database constraints and API behavior are unchanged.
- Confirmed the existing root URL configuration mounts Django Admin at
  `/admin/`.

### Verification

- `python manage.py check`: passed with no issues.
- Confirmed the Django Admin registry includes Django's built-in User and
  Group plus all 14 implemented business models.
- `python manage.py test accounts companies workforce documents integrations
  agents projects recommendations`: the initial run could not create its
  temporary test database because `test_Agentix` already existed and the
  non-interactive confirmation prompt could not be answered. No database was
  deleted.
- Reran the requested app suite with `--keepdb`: all 108 tests passed against
  the existing PostgreSQL `test_Agentix` test database, which was preserved.
- Five focused admin-form tests passed for employee-skill company matching,
  project-member/recommendation candidate and company validation, and
  department/employee/skill/project changes that could invalidate existing
  assignments.
- The final full app suite passed all 113 tests with `--keepdb`, preserving
  the existing PostgreSQL `test_Agentix` test database.
- `git diff --check`: passed.
- No migration was created; Django Admin configuration did not change models
  or the approved database schema.

## 2026-10-20 — Agentix Master Control Center (admin presentation)

### Changes

- Added presentation-only `admin_center` app with `AgentixAdminSite`,
  permission-aware dashboard metrics, branded templates, and CSS design
  tokens. No business models or migrations were added.
- Wired `AGENTIX_ADMIN_CUSTOMIZATION_ENABLED` in settings so disabling the
  flag (and restarting) restores stock Django Admin presentation while
  keeping all existing model registrations.
- Documented architecture, flag behavior, and rollback in
  `docs/ADMIN_CUSTOMIZATION.md`. Existing app-level `admin.py` files were
  left as the source of model administration.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed; no model
  changes detected.
- `python manage.py test admin_center --keepdb`: all 9 tests passed against
  the existing PostgreSQL `test_Agentix` database.
- `python manage.py test admin_center recommendations projects agents
  workforce companies accounts documents integrations --keepdb`: all 122
  tests passed against the existing PostgreSQL `test_Agentix` database,
  which was preserved.
- Strengthened the feature-flag subprocess test to verify that disabled
  customization resolves Django's stock admin index template and preserves
  User, Group, and all 14 business-model registrations.
- Added enabled-mode coverage for the complete admin model registry.
- `git diff --check`: passed.
- Uncommitted prior README/status/log admin-registration notes were
  preserved and extended rather than reverted.
