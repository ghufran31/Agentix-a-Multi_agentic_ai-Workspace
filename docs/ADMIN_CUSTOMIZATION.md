# Agentix Django Admin customization

This document describes the implemented Agentix Master Control Center: a
presentation-only customization of Django Admin at `/admin/`. It does not
replace Django Admin with a separate application and does not change the
approved business schema or REST APIs.

## Architecture and file structure

| Path | Role |
| --- | --- |
| `agentix_backend/admin_center/` | Presentation-only app (no models, no migrations) |
| `admin_center/admin_config.py` | `AgentixAdminConfig` — custom `AdminConfig.default_site` |
| `admin_center/site.py` | `AgentixAdminSite` branding, app order, dashboard index |
| `admin_center/dashboard.py` | Permission-aware metrics from existing PostgreSQL tables |
| `admin_center/templates/admin/` | Overrides for `base_site.html`, `index.html`, `login.html` |
| `admin_center/templates/admin/includes/` | Dashboard partials |
| `admin_center/static/admin_center/css/tokens.css` | Design-token source of truth |
| `admin_center/static/admin_center/css/admin.css` | Layout, sidebar, cards, tables, forms |
| `admin_center/tests.py` | Dashboard, permission, index, and feature-flag tests |
| `config/settings.py` | `AGENTIX_ADMIN_CUSTOMIZATION_ENABLED` and conditional apps |

Model CRUD configuration remains in each business app's `admin.py`:

- `companies/admin.py`
- `workforce/admin.py`
- `documents/admin.py`
- `integrations/admin.py`
- `agents/admin.py`
- `projects/admin.py`
- `recommendations/admin.py`

Django's built-in User and Group admins stay registered by `django.contrib.auth`.
Simple JWT may also register blacklist token models.

## Feature flag

Setting: `AGENTIX_ADMIN_CUSTOMIZATION_ENABLED`

- Read from the environment (and optionally from the repository-root `.env`
  via `python-dotenv`).
- Accepted truthy values: `1`, `true`, `yes`, `on` (case-insensitive).
- Default when unset: `true`.
- Documented in `.env.example`.

### Enabled (default)

`INSTALLED_APPS` starts with:

1. `admin_center` (templates and static files first so they override stock admin)
2. `admin_center.admin_config.AgentixAdminConfig` (replaces `django.contrib.admin`)

The default admin site is `AgentixAdminSite` with Agentix branding and the
Master Control dashboard.

### Disabled

Set in `.env` or the process environment:

```dotenv
AGENTIX_ADMIN_CUSTOMIZATION_ENABLED=false
```

Restart the Django process. `INSTALLED_APPS` then uses stock
`django.contrib.admin` only; `admin_center` is not installed, so stock
templates and the default index are restored.

**Important:** changing the flag with `override_settings` inside an already
running process does not rebuild `INSTALLED_APPS`. A fresh process is
required. Model registrations in each app's `admin.py` remain active in both
modes.

## Dashboard

`build_dashboard(request, admin_site)` builds cards only when the user has
`view_*` or `change_*` permission for that model. Add links require `add_*`.

Metrics (real counts only):

- Registered users
- Companies and company memberships (optional role breakdown)
- Departments and employees
- AI agents (optional status breakdown from stored values)
- Projects (optional status breakdown)
- Recommendations (optional status breakdown)
- Documents
- Integrations / connections (optional status breakdown)

Also shown when permitted: recent companies, projects, agents, and
recommendations; quick “Add …” actions; module navigation; Django's recent
admin actions sidebar.

Empty states: zero counts show “No records yet.” When every visible
business card (excluding users) is zero, a soft “Database is ready” notice
appears. No invented charts, activity logs, or system-health widgets.

## Branding and design tokens

Edit `admin_center/static/admin_center/css/tokens.css` for colors, spacing,
radii, shadows, and typography. `admin.css` consumes those tokens and maps
them onto Django's admin CSS variables (`--primary`, `--secondary`,
`--header-bg`, and related).

Visual direction:

- Navy sidebar and header
- White / light-neutral content surfaces
- Indigo primary with subtle violet accents
- Refined cards, tables, forms, badges, and focus indicators

## Customizing tables, forms, filters, and navigation

- Keep model-specific `list_display`, `search_fields`, `list_filter`,
  inlines, and forms in each app's `admin.py`.
- Shared chrome and dashboard live only under `admin_center`.
- App sidebar/index order is controlled by `APP_ORDER` in
  `admin_center/site.py`.

## Static files and templates

With `APP_DIRS` enabled, Django loads `admin_center/templates/admin/` when
the customization flag is on. Static files are served from
`admin_center/static/admin_center/` during `runserver`. No extra packages
are required.

## Adding another model to Django Admin

1. Register the model in that app's `admin.py` with `@admin.register`.
2. If it should appear on the dashboard, extend `metric_specs` (and optional
   recent-list helpers) in `admin_center/dashboard.py`.
3. Optionally add the app label to `APP_ORDER` in `admin_center/site.py`.
4. Do not put model registration into `admin_center`.

## Permissions and company isolation

- Django Admin uses Django staff/superuser permissions and sessions.
- Company roles (`owner`, `admin`, `manager`, `member`) apply to the REST
  API only and do not grant `/admin/` access.
- Dashboard cards and links respect Django model permissions.
- Existing admin form validation that enforces same-company relationships
  is unchanged.
- Passwords, password hashes, and secrets are not exposed on the dashboard.

## Testing

From `agentix_backend` with the virtual environment active:

```powershell
python manage.py check
python manage.py test admin_center --keepdb
python manage.py test admin_center recommendations projects agents workforce companies accounts documents integrations --keepdb
python manage.py makemigrations --check --dry-run
```

Feature-flag off coverage uses a fresh subprocess that sets
`AGENTIX_ADMIN_CUSTOMIZATION_ENABLED=false` and asserts stock
`django.contrib.admin` is installed and `AgentixAdminSite` is not the
default site.

## Disable or completely remove the visual customization

### Soft disable (recommended)

1. Set `AGENTIX_ADMIN_CUSTOMIZATION_ENABLED=false`.
2. Restart `runserver` (or the WSGI/ASGI process).
3. Confirm `/admin/` shows the stock Django Admin index and chrome.
4. Confirm model changelists still work.

### Hard remove

1. Soft-disable and verify stock admin first.
2. Delete the `agentix_backend/admin_center/` package.
3. Restore `INSTALLED_APPS` to start with `django.contrib.admin` and remove
   the feature-flag branching if desired.
4. Remove `docs/ADMIN_CUSTOMIZATION.md` references from README/status docs
   if no longer needed.
5. Remove `AGENTIX_ADMIN_CUSTOMIZATION_ENABLED` from `.env.example`.

### Files that must be retained during rollback

Do **not** delete model administration when removing visual customization:

- Every app-level `admin.py`
- Models, migrations, serializers, views, permissions, and API tests
- Django auth User/Group administration behavior

## How to run and verify

```powershell
cd agentix_backend
python manage.py runserver
```

Open `http://127.0.0.1:8000/admin/` and sign in with a Django superuser (or
staff user with model permissions). Company membership alone is not enough.
