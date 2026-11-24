# Deploy Agentix Django with Dokploy

This stack targets the Oracle Cloud Ampere ARM64 server. It runs one
non-root Gunicorn web container and PostgreSQL 17 with pgvector. Django
uses its existing PostgreSQL migrations, REST routes, JWT authentication,
and versioned XGBoost artifacts. The React deployment remains separate.

## 1. Prepare the host and repository

1. On the Oracle VM, run `uname -m` and confirm it reports `aarch64`. Use a
   supported 64-bit Linux distribution and install Dokploy following its
   host requirements. Allow inbound TCP 80 and 443 in the OCI network rules
   and host firewall. Restrict SSH and Dokploy management access to
   administrators. [Dokploy installation](https://docs.dokploy.com/docs/core/installation)
2. Review the intended release branch. Include the backend, all migrations,
   both tracked files in `agentix_backend/orchestrator/ml_engine/artifacts/`,
   and the deployment files. Keep the local training workspace and provider
   credentials outside Git. The Docker build loads the actual model and
   preprocessor, so missing or incompatible artifacts fail the build.
3. Validate from the repository root. Supply disposable placeholder values
   in a local ignored `.env.production` for this step. The validation command
   prints no interpolated secrets.

   ```sh
   docker compose --env-file .env.production -f compose.production.yaml config --quiet
   DOCKER_DEFAULT_PLATFORM=linux/arm64 docker compose --env-file .env.production      -f compose.production.yaml build
   ```

## 2. Configure Dokploy and HTTPS

1. Create a Dokploy project and a **Docker Compose** service, using Compose
   mode. Choose the GitHub provider, select the reviewed repository and
   branch, and set the Compose path to `compose.production.yaml` at the
   repository root. Keep auto-deploy off until the first release is verified.
   [Dokploy Compose setup](https://docs.dokploy.com/docs/core/docker-compose/example)
2. Paste settings from `.env.production.example` into the service's
   **Environment** editor. Set the real values there and restrict access.
   Dokploy provides them for Compose interpolation. Avoid printing the full
   rendered configuration because it contains secret values.
3. Set an A record for `api.example.com` pointing to the Oracle server's
   public IPv4 address. Add an AAAA record only when IPv6 is configured.
   In **Domains**, add this hostname for service `web`, container port
   `8000`, path `/`, and enable HTTPS with Let's Encrypt. The deployment
   must publish the new domain labels. Leave PostgreSQL off public domains
   and host ports. Traefik must preserve the host and set
   `X-Forwarded-Proto`; keep trust for client-supplied forwarding headers
   disabled. [Dokploy domains](https://docs.dokploy.com/docs/core/docker-compose/domains)
4. When authorized to deploy, start the Compose deployment and watch the
   build and service logs. Use one web container. Its startup command
   applies migrations and initializes the checkpointer before starting Gunicorn.
   Schedule updates that change schema during a maintenance window.

### Environment

| Variables | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | Unique secret of at least 50 characters. Preserve it across restarts and restores. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated exact hostnames. Put the API domain first for the container healthcheck. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Exact HTTPS React origins, comma-separated, without trailing slash. JWT Authorization is allowed for existing API routes. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact HTTPS origins allowed for CSRF-protected unsafe requests. The API hostname is an appropriate starting value. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Database and application role. These must match the initial volume provisioning. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Separate bootstrap administrator and different password. Django does not receive these values. |
| `GROQ_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `TAVILY_API_KEY` | Optional to boot. Set only keys needed by the selected model and research workflows. |
| `SPECIALIST_LLM_*`, `SUPERVISOR_LLM_*` and fallback settings | Choose providers and models using the existing contract. Automatic fallback defaults off in this deployment. [Provider configuration](../orchestrator/LLM_PROVIDERS.md) |
| `GUNICORN_WORKERS`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT` | Defaults are 2, 2, and 120 seconds. Tune worker counts against memory and latency on the target VM. |

Use a password manager or `python -c "import secrets; print(secrets.token_urlsafe(64))"`
to generate separate secrets. Save them to the deployment environment, not
to the repository. The database host is fixed to the Compose service `db`.
LangGraph uses the same database under `agentix_checkpoints`. The developer
console and its test write modes are disabled in production settings.

## 3. Initialization and smoke tests

On a fresh named volume, the bundled database image enables `vector`,
creates the non-superuser application role, and grants it permissions to
create migration and checkpoint tables. PostgreSQL runs this initializer
only on an empty data directory. The web startup then runs:

```sh
python manage.py migrate --noinput
python manage.py setup_supervisor_checkpoints
python manage.py collectstatic --noinput
```

Run the following from the **web container terminal** after it is healthy.
Use the final command only if an initial Django administrator is needed.

```sh
python manage.py check --deploy
python manage.py showmigrations --plan
python manage.py createsuperuser
```

From outside the server, `curl -fsS https://api.example.com/healthz/` should
return `{"status":"ok"}`. Confirm that HTTP redirects to HTTPS,
`/dev/supervisor/` returns 404, admin static assets load, and an
`OPTIONS` preflight from the React origin returns the expected CORS
header. Check an authenticated endpoint with a short-lived test token.
Set the React API base URL to `https://api.example.com/api/v1/` and
use the existing JWT Bearer header. The production stack adds no browser
Supervisor API and does not run paid provider probes on startup.

## 4. Backups, restore, and updates

- Back up the whole PostgreSQL database, including `agentix_checkpoints`,
  using a scheduled logical dump. Store encrypted copies off the VM and
  test restores. A Docker volume copy while PostgreSQL is writing is not
  a substitute for a consistent database backup. Retain the role names,
  credentials, and Django signing key separately. [PostgreSQL backup and restore](https://www.postgresql.org/docs/17/backup-dump.html)
- Run these examples from the deployed Compose directory using the same
  project identity and Dokploy-provided environment as the original
  service. In the commands, use a POSIX shell to preserve binary dumps.

  ```sh
  docker compose -f compose.production.yaml exec -T db     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"'     > agentix.dump
  ```

  To rehearse recovery, provision a separate empty PostgreSQL 17 volume
  with the same application role, start only its database service, and
  restore into that empty target. Run the following from the **recovery**
  Compose project, then start its web service and verify migrations,
  database records, and checkpoint availability.

  ```sh
  docker compose -f compose.production.yaml exec -T db     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_restore -h 127.0.0.1 -U "$POSTGRES_USER" --exit-on-error -d "$POSTGRES_DB"'     < agentix.dump
  ```

- Back up before updates. Deploy a reviewed commit through Dokploy and
  verify health and the React API. Keep the Compose service identity and
  `postgres_data` volume. Avoid volume deletion on redeploy or removal.
  An image rollback does not undo database migrations. Check schema
  compatibility before rolling back, and handle PostgreSQL major upgrades
  as separate migration projects. [Dokploy named volumes](https://docs.dokploy.com/docs/core/docker-compose#volumes)

## Troubleshooting

| Symptom | Check |
| --- | --- |
| ARM64 build cannot resolve a wheel | Build on the target VM, check the Python 3.13 wheel and registry availability, and keep the model preprocessing pins intact. |
| PostgreSQL stays unhealthy | Check the DB service logs and credentials. A pre-existing volume will not replay initialization when environment variables change. Repair or rotate roles deliberately. |
| Web exits during migrations or checkpoint setup | Check role privileges and database connectivity. The role needs creation access in the application database. |
| HTTPS redirect loop or 400 | Verify the Dokploy domain target, TLS forwarding, and exact `DJANGO_ALLOWED_HOSTS`. |
| React fails a preflight | Check the frontend origin including scheme and port, the API prefix, and whether the request reaches Django through HTTPS. |
| Admin static files 404 or manifest errors | Check startup `collectstatic` logs, then confirm Django serves the hashed path under `/static/`. |
| Checkpoints disappear across a restart | Check that the original named database volume and schema are present. Verify the deployment still uses the same signing key. |

Production intentionally keeps HSTS preload opt-in. Django can report
`security.W021` for this, while standard HSTS and HTTPS redirection remain
enabled. Optional `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
and `SMTP_FROM_EMAIL` configure a STARTTLS relay. The current REST API
does not require an SMTP relay for startup.

## Local verification for this release preparation

Compose validation passed, including healthchecks, the internal database
network, and named storage. Both Dockerfiles passed ARM64 BuildKit checks
and pip resolved the production dependencies to Linux ARM64-compatible
wheels. The full ARM64 image build was stopped during slow Docker Hub layer
downloads, before either image completed. Complete the build and smoke
tests on the target server before routing public traffic.

Django's production profile passed the three security and readiness tests,
static collection, and a checkpoint recovery test on a disposable local
PostgreSQL database. The deployment check reported only the documented
HSTS preload warning. No production deployment was performed.
