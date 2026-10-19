# Current status

Updated: 2026-10-19

## Implemented

- Django project settings now use environment-provided secret and PostgreSQL
  credentials instead of checked-in values; local settings load them from the
  repository-root `.env` file.
- `.env.example` documents the required and optional PostgreSQL configuration
  placeholders and is allowed through the Git ignore rules.
- The `accounts` app uses Django's existing user model; it defines no models
  and registration creates no company or other business record.
- Registration, login, refresh, logout, and authenticated safe-profile API
  routes are implemented under `/api/v1/accounts/`.
- Simple JWT is configured for 15-minute access tokens and 7-day refresh
  tokens, with rotation and blacklist support.
- The `companies` app implements only the approved `companies` and
  `company_users` tables, with a unique creator, unique company membership,
  role choices, and the requested APIs.
- Company creation transactionally creates the creator's owner membership.
  All endpoints require authentication; reads require membership, and only
  owners may patch company details.
- The `workforce` app implements only the approved departments, employees,
  employee AI profiles, skills, and employee-skill tables and their
  authenticated CRUD APIs.
- Workforce reads are membership-scoped; owners, admins, and managers may
  write. Employee-skill links are validated to keep both records in the same
  company.
- The `documents` app implements only the approved `company_documents` table
  and authenticated, company-scoped document metadata CRUD APIs.
- Company members may read their documents; owners, admins, and managers may
  create, update, and delete. `file_path` is metadata only; no file upload or
  storage implementation is included.
- Focused accounts API tests have been added.
- The exact approved DBML is recorded in `docs/DATABASE_SCHEMA.md`.

## Verification

- `python manage.py test accounts --verbosity 1`: **12 tests passed** against
  PostgreSQL's temporary `test_Agentix` database; Django removed that
  temporary test database after the run.
- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed; no model
  changes detected.
- `python manage.py check`: passed with configuration loaded from the root
  `.env` file and no process environment overrides.
- `python manage.py test accounts --verbosity 1`: all 12 tests passed with
  PostgreSQL and configuration loaded from the root `.env` file. Django
  removed its temporary test database after the run.
- `python manage.py check`: passed after adding `companies`.
- `python manage.py makemigrations --check --dry-run`: passed after applying
  the companies migration; no model changes detected.
- `python manage.py test companies accounts --verbosity 2`: all 23 tests
  passed against PostgreSQL's temporary `test_Agentix` database.
- `python manage.py migrate --noinput`: applied
  `companies.0001_initial` to the configured PostgreSQL database.
- All company route patterns were resolved in the automated test suite.
- Confirmed the configured database engine is PostgreSQL and its name is
  `Agentix`.
- `python manage.py check`: passed after adding workforce.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes after workforce migration generation.
- An earlier `python manage.py test workforce companies accounts
  --verbosity 1` run passed all 40 tests against PostgreSQL's temporary
  `test_Agentix` database.
- After adding an additional role-permission test, a 41-test run was
  interrupted by five PostgreSQL connection errors when the local PostgreSQL
  service stopped. Once PostgreSQL was available again, the combined suite
  passed all 41 tests using the existing `test_Agentix` test database with
  `--keepdb`; the database was preserved.
- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no model
  changes detected.
- `python manage.py migrate --noinput`: applied
  `workforce.0001_initial` and `workforce.0002_alter_department_created_at_and_more`
  to the configured PostgreSQL database.
- All workforce route patterns were resolved successfully after the test run.
- Confirmed database engine `django.db.backends.postgresql` and name
  `Agentix`.
- `python manage.py migrate --noinput`: applied the Simple JWT blacklist
  migrations to the configured development database. Existing Django auth
  migrations were already applied; no business-schema migrations were added.
- `python manage.py showmigrations auth token_blacklist`: all listed auth and
  blacklist migrations are applied.
- Resolved all five requested account paths to their expected URL names.
- `python manage.py check`: passed after adding documents.
- `python manage.py makemigrations --check --dry-run`: passed with no model
  changes detected.
- `python manage.py migrate --noinput`: applied
  `documents.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test documents companies accounts workforce --verbosity
  2 --keepdb`: all 51 tests passed against the existing PostgreSQL
  `test_Agentix` test database, which was preserved.
- Both documents routes resolved successfully in the automated tests.
- Confirmed the configured database remains PostgreSQL `Agentix`.

## Not implemented

Connections, AI agents, projects, recommendations, project assignments, and
the frontend remain planned. The next development step is to present the
verified documents implementation to the project owner and wait for approval
before implementing another app.
