#!/bin/sh
set -eu

if [ -z "${DB_USER:-}" ] || [ -z "${DB_PASSWORD:-}" ] ||
   [ "$DB_USER" = "$POSTGRES_USER" ] || [ "$DB_PASSWORD" = "$POSTGRES_PASSWORD" ]; then
    echo 'Set distinct database administrator and application credentials.' >&2
    exit 1
fi

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv app_user DB_USER
\getenv app_password DB_PASSWORD
\getenv db_name POSTGRES_DB
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
GRANT CONNECT, CREATE ON DATABASE :"db_name" TO :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
SQL
