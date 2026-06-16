-- Read-only database role for the SEMA agent.
--
-- Defense in depth: the agent generates SQL, and although we also validate
-- every query in the app layer (agent/safety.py), the strongest guarantee
-- is at the database itself -- this role can ONLY read. Even a perfect
-- injection or a bug in our validator cannot INSERT/UPDATE/DELETE/DROP,
-- because the role was never granted those privileges.
--
-- Run once (idempotent):
--   docker exec -i sema-postgres psql -U sema_user -d sema_db < sql/create_readonly_role.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sema_readonly') THEN
        CREATE ROLE sema_readonly LOGIN PASSWORD 'sema_readonly_pw';
    END IF;
END
$$;

-- Allow connecting and reading the public schema.
GRANT CONNECT ON DATABASE sema_db TO sema_readonly;
GRANT USAGE ON SCHEMA public TO sema_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sema_readonly;

-- Apply SELECT automatically to any tables created in the future.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sema_readonly;

-- Belt-and-suspenders: make sure no write privileges are present.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM sema_readonly;
