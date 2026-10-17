#!/bin/sh
# Database roles with least privilege (spec §14.12, §14.15). Runs once on first start.
#   devsync_migrator  owns the schema; DDL; used only by Alembic.
#   devsync_app       DML for web requests; no DDL; no UPDATE/DELETE on append-only tables.
#   devsync_worker    DML for background jobs (separate role for RLS context SYSTEM).
#   devsync_readonly  SELECT only (analytics, backups).
# None of them is superuser or has BYPASSRLS. Passwords come from the environment.
set -eu
: "${DEVSYNC_MIGRATOR_PASSWORD:?}" "${DEVSYNC_APP_PASSWORD:?}" "${DEVSYNC_WORKER_PASSWORD:?}" "${DEVSYNC_READONLY_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v migrator_pw="$DEVSYNC_MIGRATOR_PASSWORD" -v app_pw="$DEVSYNC_APP_PASSWORD" \
  -v worker_pw="$DEVSYNC_WORKER_PASSWORD" -v readonly_pw="$DEVSYNC_READONLY_PASSWORD" <<'SQL'
CREATE ROLE devsync_migrator LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS PASSWORD :'migrator_pw';
CREATE ROLE devsync_app      LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS PASSWORD :'app_pw';
CREATE ROLE devsync_worker   LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS PASSWORD :'worker_pw';
CREATE ROLE devsync_readonly LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS PASSWORD :'readonly_pw';

-- Extensions need superuser; create them here so the migrator never needs it.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO devsync_migrator, devsync_app, devsync_worker, devsync_readonly;
GRANT USAGE, CREATE ON SCHEMA public TO devsync_migrator;
GRANT USAGE ON SCHEMA public TO devsync_app, devsync_worker, devsync_readonly;

-- Tables created later by the migrator get least-privilege grants automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE devsync_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO devsync_app, devsync_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE devsync_migrator IN SCHEMA public
  GRANT SELECT ON TABLES TO devsync_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE devsync_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO devsync_app, devsync_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE devsync_migrator IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO devsync_app, devsync_worker, devsync_readonly;

ALTER ROLE devsync_app      SET statement_timeout = '5s';
ALTER ROLE devsync_worker   SET statement_timeout = '30s';
ALTER ROLE devsync_app      SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE devsync_worker   SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE devsync_app      SET lock_timeout = '3s';
ALTER ROLE devsync_worker   SET lock_timeout = '3s';
SQL
