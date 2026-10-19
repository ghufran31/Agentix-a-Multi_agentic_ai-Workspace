# Agentix

Agentix is a Django REST Framework backend for a planned multi-agent project
workspace. Development is being delivered one app at a time.

## Implemented now

- Django's built-in user model and password validators.
- JWT registration, login, refresh, logout, and authenticated profile endpoints
  under `/api/v1/accounts/`.
- Company creation, company membership-based listing and detail access,
  owner-only updates, and member listing under `/api/v1/companies/`.
- Company-scoped CRUD for departments, employees, employee AI profiles,
  skills, and employee-skill assignments under `/api/v1/workforce/`.
- Company-scoped document metadata CRUD under `/api/v1/documents/`.
- Company-scoped connection metadata CRUD under `/api/v1/integrations/`.
- Company-scoped AI agent metadata CRUD under `/api/v1/agents/`.
- PostgreSQL configuration through environment variables.
- Refresh-token rotation and blacklist support.

No business app beyond `companies`, `workforce`, `documents`, `integrations`,
and `agents` is implemented. Agent records are metadata only: they do not
execute tasks, call tools, or run AI workflows. Account registration creates
only a Django user. The approved schema is documented in
[`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md) and must not be changed
without approval.

## Requirements

- Python 3.12 or later.
- PostgreSQL, with a database and account available to the developer.

## Windows PowerShell setup

From the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy the root example file and edit `.env` with your PostgreSQL connection
settings and a newly generated Django secret key. The `.env` file is loaded
automatically when Django starts and is ignored by Git; never commit it.
Generate a secret key with:

```powershell
Copy-Item .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
notepad .env
```

Replace every placeholder in `.env`. `DJANGO_SECRET_KEY` and `DB_PASSWORD`
are required. `DB_NAME`, `DB_USER`, `DB_HOST`, and `DB_PORT` are optional and
default to `Agentix`, `postgres`, `localhost`, and `5432`, respectively.
Process environment variables take precedence over values loaded from `.env`.
The backend remains configured to use PostgreSQL.

Apply Django's built-in authentication, Simple JWT blacklist, and app
migrations, then start the API:

```powershell
cd agentix_backend
python manage.py migrate
python manage.py runserver
```

The app migrations create only the business tables implemented from the
approved schema: companies, workforce, documents, connections, and AI agent
metadata. The `accounts` app has no models and registration does not create a
company.

## Accounts API

| Method | Path | Authentication | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/v1/accounts/register/` | Public | Create a user with validated, hashed password |
| `POST` | `/api/v1/accounts/login/` | Public | Obtain access and refresh JWTs |
| `POST` | `/api/v1/accounts/token/refresh/` | Public | Rotate a refresh token and issue an access token |
| `POST` | `/api/v1/accounts/logout/` | Public | Blacklist the submitted refresh token |
| `GET` | `/api/v1/accounts/me/` | Bearer access token | Return the authenticated user's safe profile |

Registration requires `username`, `email`, `password`, and
`password_confirmation`; `first_name` and `last_name` are optional. Login
accepts Django's `username` and `password`. Send refresh and logout requests
with a JSON `refresh` token. Protected requests use
`Authorization: Bearer <access-token>`.

Access tokens last 15 minutes and refresh tokens last 7 days. Refresh-token
rotation and blacklisting are enabled.

## Companies API

All routes require a valid bearer access token.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/companies/` | Create a company and owner membership atomically |
| `GET` | `/api/v1/companies/` | List companies the user belongs to |
| `GET` | `/api/v1/companies/<id>/` | Retrieve a company the user belongs to |
| `PATCH` | `/api/v1/companies/<id>/` | Update company details as the owner |
| `GET` | `/api/v1/companies/<id>/members/` | List members of a company the user belongs to |

The creator is recorded as the owner. Only owners may update company details;
admins, managers, and members may read accessible companies and member lists
but cannot update company details. Users may create at most one company.
Unauthorized company detail and member requests return 404 to avoid exposing
whether an inaccessible company exists.

## Workforce API

All workforce routes require authentication and are scoped to companies in
which the requester has a membership. Owners, admins, and managers can
create, update, and delete workforce records; members have read-only access.
Foreign keys supplied on writes must reference accessible resources, and
employee-skill assignments require the employee and skill to belong to the
same company. See [the workforce API reference](docs/modules/workforce.md)
for exact routes and resource fields.

## Documents API

Document endpoints require authentication. Company members can list and
retrieve their company's document metadata; owners, admins, and managers can
create, update, and delete document records. The API stores the schema's
`file_path` text as metadata only; it does not upload or store files. See
[the documents API reference](docs/modules/documents.md) for exact routes.

## Integrations API

Integration records store provider/account labels and connection status
metadata only. They do not verify or establish an external connection and do
not accept or return credentials, API keys, tokens, or secrets. All endpoints
require authentication; company members can read, and owners, admins, and
managers can write. See
[the integrations API reference](docs/modules/integrations.md) for routes and
request fields.

## Agents API

Agent records store company, name, type, description, capabilities, status,
and creation time as metadata. They do not execute autonomous tasks, call
tools, or run AI workflows. Members may read agents in their companies;
owners, admins, and managers may create, update, and delete them. See
[the agents API reference](docs/modules/agents.md) for routes and fields.

## Tests and migration checks

Run the accounts tests against the configured PostgreSQL test database:

```powershell
cd agentix_backend
python manage.py test agents companies accounts workforce documents integrations
python manage.py makemigrations --check --dry-run
python manage.py showmigrations auth token_blacklist companies workforce documents integrations agents
```

The test runner creates and tears down its own temporary test database; it
does not delete the configured development database.

## Project documentation

- [Architecture and planned apps](docs/ARCHITECTURE.md)
- [Approved DBML schema](docs/DATABASE_SCHEMA.md)
- [Current implementation status](docs/CURRENT_STATUS.md)
- [Development log](docs/DEVELOPMENT_LOG.md)
- [Accounts API details](docs/modules/accounts.md)
- [Companies API details](docs/modules/companies.md)
- [Workforce API details](docs/modules/workforce.md)
- [Documents API details](docs/modules/documents.md)
- [Integrations API details](docs/modules/integrations.md)
- [Agents API details](docs/modules/agents.md)

Other future apps are not authorized by this implementation. Wait for the
project owner's approval before starting another app.
