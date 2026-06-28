-- ============================================================================
-- SEMA: Postgres init script (runs once, on a FRESH volume).
-- ============================================================================
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
