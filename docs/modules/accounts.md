# Accounts app

## Scope and data

The app uses `django.contrib.auth`'s configured user model and Django's
password validation and hashing. It defines no model or migration. Registering
creates only a user; it does not create a company. Password values and hashes
are not present in API responses.

## Endpoints

All routes are mounted below `/api/v1/accounts/`.

| Method and path | Access | Behavior |
| --- | --- | --- |
| `POST /register/` | Public | Creates a user after validating username, required email, password strength, and password confirmation. Returns a safe profile with HTTP 201. |
| `POST /login/` | Public | Accepts `username` and `password`; returns Simple JWT `access` and `refresh` tokens. Invalid credentials and inactive users are rejected. |
| `POST /token/refresh/` | Public | Accepts a `refresh` token, returns a new access token, and rotates the refresh token. The previous refresh token is blacklisted. |
| `POST /logout/` | Public | Accepts a `refresh` token and blacklists it. |
| `GET /me/` | Bearer access token | Returns the current user's `id`, `username`, `email`, `first_name`, `last_name`, and `date_joined`. |

The registration request requires `username`, `email`, `password`, and
`password_confirmation`. `first_name` and `last_name` are optional. Django's
configured password validators run before user creation, and `set_password`
stores the password hash.

Public token endpoints are intentionally public; `/me/` requires a valid,
active user's JWT. An access token expires after 15 minutes and a refresh
token after 7 days. Refresh rotation and blacklist-after-rotation are enabled.

## Configuration and migrations

`rest_framework_simplejwt.token_blacklist` is installed so refresh-token
blacklisting is persisted using the package's migrations. Database name,
user, password, host, and port are configured by `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, and `DB_PORT`. `DJANGO_SECRET_KEY` and
`DB_PASSWORD` are required. Local development loads these values from the
repository-root `.env` via `python-dotenv`; process environment variables
override values in the file. See the root README and `.env.example`.

## Tests

Run `python manage.py test accounts` from `agentix_backend` with the
environment configured to use PostgreSQL. Tests cover registration and
password hashing, input validation, login and inactive/invalid credentials,
refresh rotation, logout blacklisting, and authenticated profile access.
