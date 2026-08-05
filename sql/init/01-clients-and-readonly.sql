-- ============================================================================
-- SEMA: Postgres init script (runs once, on a FRESH volume).
-- ============================================================================
-- LOCAL DEVELOPMENT / DOCKER COMPOSE ONLY -- this is NOT the Render/
-- production workflow and must never be run against a Render (or any other
-- managed/production) database. It only ever executes automatically via the
-- official postgres image's own /docker-entrypoint-initdb.d mechanism
-- (docker-compose.yml, and docker-compose.prod.yml's LOCAL smoke-test
-- Postgres both mount sql/init here) -- a Render-managed Postgres instance
-- does not run init scripts at all, so this file simply never reaches it.
-- It hardcodes the role's password ('sema_readonly_pw') ON PURPOSE: that's
-- the well-known LOCAL dev default (.env.example's own POSTGRES_READONLY_
-- PASSWORD), the exact value sema_core/settings.py's validate_for_
-- production() refuses to let the app boot with in production, which is
-- precisely why it must stay confined to this local-only file.
--
-- For Render (or any other real deployment), use sql/create_readonly_role.sql
-- instead (docs/deployment.md's Render section has the full walkthrough) --
-- it creates the SAME role and grants but with NO password baked in,
-- deliberately, set interactively via `\password sema_readonly` so it can
-- match whatever random value Render generated for POSTGRES_READONLY_
-- PASSWORD, instead of every deployment sharing this one dev-only secret.
-- ============================================================================
--
-- The official postgres image runs every file in /docker-entrypoint-initdb.d
-- exactly once, the first time the data volume is created, connected to the
-- default POSTGRES_DB (sema_db) as POSTGRES_USER. We use it to:
--   1. create the read-only agent role (sema_readonly)
--   2. create the second client database (insurance_db)
--   3. grant the read-only role CONNECT + SELECT on BOTH databases
--
-- Per-table SELECT is also granted by each client's load_data.py after it
-- creates tables; the ALTER DEFAULT PRIVILEGES here covers anything created
-- later by the owning role.
--
-- NOTE: this does NOT run on an already-initialised volume. To re-bootstrap a
-- machine from scratch: `docker compose down -v && docker compose up -d`
-- (this DELETES all local data), then run the load_data scripts.
-- ============================================================================

-- 1. Read-only role (idempotent).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sema_readonly') THEN
        CREATE ROLE sema_readonly LOGIN PASSWORD 'sema_readonly_pw';
    END IF;
END
$$;

-- 2. Grants on the ecommerce DB (we are connected to sema_db by default).
GRANT CONNECT ON DATABASE sema_db TO sema_readonly;
\connect sema_db
GRANT USAGE ON SCHEMA public TO sema_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sema_readonly;

-- 3. Second client database + its grants.
CREATE DATABASE insurance_db;
GRANT CONNECT ON DATABASE insurance_db TO sema_readonly;
\connect insurance_db
GRANT USAGE ON SCHEMA public TO sema_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sema_readonly;
