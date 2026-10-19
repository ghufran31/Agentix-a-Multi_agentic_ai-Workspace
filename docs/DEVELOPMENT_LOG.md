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
