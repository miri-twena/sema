-- Read-only database role for the SEMA agent -- the Render/production
-- workflow (docs/deployment.md's Render section has the full interactive
-- walkthrough; sql/init/01-clients-and-readonly.sql is the SEPARATE,
-- local-development-only equivalent that docker-compose runs automatically).
--
-- Defense in depth: the agent generates SQL, and although we also validate
-- every query in the app layer (agent/safety.py), the strongest guarantee
-- is at the database itself -- this role can ONLY read. Even a perfect
-- injection or a bug in our validator cannot INSERT/UPDATE/DELETE/DROP,
-- because the role was never granted those privileges.
--
-- NO PASSWORD IS SET BY THIS FILE, ON PURPOSE. The role is created with
-- LOGIN but no PASSWORD clause, so password auth stays disabled until you
-- set one INTERACTIVELY, in the same psql session, right after running this
-- file:
--     \password sema_readonly
-- psql prompts for the value and sends it over the connection directly --
-- it is never typed as a command-line argument, never written to this
-- file, and never appears in shell history or logs. Enter the EXACT value
-- already stored as Render's POSTGRES_READONLY_PASSWORD so the database
-- role and the app's configured credential stay in sync.
--
-- NO DATABASE NAME IS HARDCODED EITHER. The CONNECT grant below applies to
-- whichever database `psql` is CURRENTLY CONNECTED to (current_database()),
-- so the SAME file is correct for every tenant database -- run it once per
-- database (`\c sema_db` / `\c insurance_db`, then `\i` this file each
-- time), rather than being tied to one tenant's name. The role itself is
-- cluster-wide (CREATE ROLE has no database scope) and this whole script is
-- idempotent: running it again against a database it already covers only
-- reapplies the same grants, it never errors or duplicates anything --
-- safe (and expected) to re-run after a loader recreates tables.
--
-- Run once per tenant database, connected as an admin/owner role:
--   docker exec -i sema-postgres psql -U sema_user -d sema_db < sql/create_readonly_role.sql
--   docker exec -i sema-postgres psql -U sema_user -d insurance_db < sql/create_readonly_role.sql

-- 1. The role itself (idempotent, no password set here -- see above).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sema_readonly') THEN
        CREATE ROLE sema_readonly LOGIN;
    END IF;
END
$$;

-- 2. Allow connecting to THIS database -- current_database(), never a
-- literal name. GRANT's object name can't be a plain expression, so this
-- needs PL/pgSQL's EXECUTE format(...) (%I safely quotes the identifier).
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO sema_readonly', current_database());
END
$$;

-- 3. Read the public schema: USAGE to see it, SELECT on every table that
-- exists right now.
GRANT USAGE ON SCHEMA public TO sema_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sema_readonly;

-- 4. Apply SELECT automatically to any tables created in the future BY THE
-- ROLE RUNNING THIS SCRIPT (typically the admin/owner role that also runs
-- the loaders) -- covers a loader's DROP + CREATE TABLE without needing to
-- re-run this file, though re-running it after a loader is still the
-- documented, verified way to confirm access (docs/deployment.md).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sema_readonly;

-- 5. Belt-and-suspenders: explicitly revoke every write privilege, so this
-- stays true even if some other statement ever granted one by mistake.
-- (DROP isn't in this list because it isn't a grantable TABLE privilege at
-- all -- only the owner or a superuser can drop a table, so sema_readonly
-- is structurally incapable of it, not just denied by a REVOKE.)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM sema_readonly;
