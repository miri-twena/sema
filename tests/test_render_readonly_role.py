"""
Render read-only PostgreSQL role setup (docs/deployment.md's Render
section): sql/create_readonly_role.sql must be safe to run against Render's
managed Postgres for EITHER tenant database, with no hardcoded credential
and no hardcoded database name, and the docs must actually describe that
workflow correctly for both `sema_db` and `insurance_db` -- these are
content/text assertions (there's no live Postgres in CI to execute the SQL
against), each one guarding against a specific regression:
  - the well-known local-dev password leaking into the production script
  - a hardcoded database name defeating the "run once per tenant" design
  - the script silently granting (or the docs silently condoning) write
    access, which would gut the whole "read-only" guarantee
  - the local-dev-only init script being mistaken for the Render workflow
  - the Windows instructions reverting to bash-only syntax
"""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_READONLY_ROLE_SQL = _PROJECT_ROOT / "sql" / "create_readonly_role.sql"
_LOCAL_INIT_SQL = _PROJECT_ROOT / "sql" / "init" / "01-clients-and-readonly.sql"
_DEPLOYMENT_DOC = _PROJECT_ROOT / "docs" / "deployment.md"

_DEV_PASSWORD = "sema_readonly_pw"
_WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")


def _readonly_role_sql() -> str:
    return _READONLY_ROLE_SQL.read_text(encoding="utf-8")


def _local_init_sql() -> str:
    return _LOCAL_INIT_SQL.read_text(encoding="utf-8")


def _deployment_doc() -> str:
    return _DEPLOYMENT_DOC.read_text(encoding="utf-8")


# --- sql/create_readonly_role.sql: the Render/production script -----------


def test_no_hardcoded_dev_password():
    assert _DEV_PASSWORD not in _readonly_role_sql()


def test_create_role_has_no_password_clause_at_all():
    """Not just "not the dev password" -- no PASSWORD clause of any kind.
    The whole point is that this script creates the role UNAUTHENTICATED
    for login, and the password is set afterward via the interactive
    `\\password` psql meta-command (docs/deployment.md), never embedded here."""
    sql = _readonly_role_sql()
    create_role_stmt = re.search(r"CREATE ROLE sema_readonly[^;]*;", sql, re.IGNORECASE)
    assert create_role_stmt is not None, "expected a CREATE ROLE sema_readonly statement"
    assert "PASSWORD" not in create_role_stmt.group(0).upper()


def test_connect_grant_uses_current_database_not_a_literal_name():
    sql = _readonly_role_sql()
    assert "current_database()" in sql
    # No EXECUTABLE statement hardcodes a tenant database name -- only the
    # comments illustrate "sema_db"/"insurance_db" as examples of what
    # current_database() resolves to per invocation. Strip comment lines
    # before checking, so the illustrative prose doesn't false-positive.
    executable_lines = "\n".join(
        line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")
    )
    assert "sema_db" not in executable_lines
    assert "insurance_db" not in executable_lines


def test_grant_connect_statement_itself_has_no_hardcoded_database():
    """More targeted than the file-wide check above: specifically the
    GRANT CONNECT ON DATABASE clause must reference current_database(),
    not any literal identifier."""
    sql = _readonly_role_sql()
    grant_connect = re.search(r"GRANT CONNECT ON DATABASE[^;]*;", sql, re.IGNORECASE)
    assert grant_connect is not None, "expected a GRANT CONNECT ON DATABASE statement"
    assert "current_database" in grant_connect.group(0)


def test_script_never_grants_write_privileges():
    sql = _readonly_role_sql()
    for verb in _WRITE_VERBS:
        assert not re.search(rf"GRANT\s+[^;]*\b{verb}\b[^;]*TO\s+sema_readonly", sql, re.IGNORECASE), (
            f"script must never GRANT {verb} to sema_readonly"
        )
    assert not re.search(r"GRANT\s+ALL\b", sql, re.IGNORECASE)


def test_script_explicitly_revokes_write_privileges():
    sql = _readonly_role_sql()
    revoke = re.search(r"REVOKE[^;]*;", sql, re.IGNORECASE)
    assert revoke is not None, "expected an explicit REVOKE statement"
    revoked = revoke.group(0).upper()
    for verb in _WRITE_VERBS:
        assert verb in revoked


def test_script_preserves_usage_and_select_grants():
    sql = _readonly_role_sql()
    assert re.search(r"GRANT USAGE ON SCHEMA public TO sema_readonly", sql)
    assert re.search(r"GRANT SELECT ON ALL TABLES IN SCHEMA public TO sema_readonly", sql)


def test_script_preserves_default_privileges_for_future_tables():
    sql = _readonly_role_sql()
    assert re.search(
        r"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sema_readonly", sql
    )


def test_role_creation_is_idempotent():
    sql = _readonly_role_sql()
    assert "IF NOT EXISTS" in sql
    assert "pg_roles" in sql


# --- sql/init/01-clients-and-readonly.sql: LOCAL DEV ONLY, must say so ----


def test_local_init_script_is_clearly_marked_local_dev_only():
    sql = _local_init_sql()
    assert "LOCAL DEVELOPMENT" in sql
    assert "NOT the Render" in sql or "not the Render" in sql.lower() or "NOT be run against a Render" in sql
    assert "sql/create_readonly_role.sql" in sql, "must point readers at the real Render script"


def test_local_init_script_still_documents_why_it_hardcodes_a_password():
    """This file is EXPECTED to hardcode sema_readonly_pw (it's the local
    dev default matching .env.example) -- the fix is documenting that
    loudly, not removing it, so this asserts the explanation exists rather
    than asserting the password is gone."""
    sql = _local_init_sql()
    assert _DEV_PASSWORD in sql
    assert "validate_for_production" in sql or "production" in sql.lower()


# --- docs/deployment.md: the Render workflow itself ------------------------


def test_docs_never_contain_the_dev_password():
    assert _DEV_PASSWORD not in _deployment_doc()


def test_docs_never_claim_the_admin_user_can_be_reused_as_readonly():
    doc = _deployment_doc()
    assert "Never set `POSTGRES_READONLY_USER` to Render's own admin user" in doc
    # Regression guard: no sentence anywhere tells the reader to point
    # POSTGRES_READONLY_USER at the admin user.
    assert not re.search(r"POSTGRES_READONLY_USER.{0,40}(same as|reuse|=\s*`?POSTGRES_USER)", doc, re.IGNORECASE)


def test_docs_use_interactive_password_workflow():
    doc = _deployment_doc()
    assert r"\password sema_readonly" in doc


def test_docs_use_powershell_env_syntax_not_bash_inline_assignment():
    doc = _deployment_doc()
    assert "$env:POSTGRES_HOST" in doc
    assert "$env:POSTGRES_PASSWORD" in doc
    # The old bug: a bash-style `VAR=value \` line-continuation prefix in a
    # doc explicitly aimed at Windows PowerShell users.
    assert not re.search(r"^POSTGRES_HOST=\S+.*\\\s*$", doc, re.MULTILINE)
    assert "POSTGRES_HOST=<external host> POSTGRES_PORT=5432 \\" not in doc


def test_docs_include_cleanup_for_temporary_env_vars():
    doc = _deployment_doc()
    assert "Remove-Item Env:\\SEMA_TMP_DB_URL" in doc
    assert "Remove-Item Env:\\POSTGRES_HOST" in doc


def test_docs_cover_both_tenant_databases_explicitly():
    doc = _deployment_doc()
    assert "POSTGRES_DB=sema_db" in doc
    assert "POSTGRES_DB_INSURANCE=insurance_db" in doc
    assert "CREATE DATABASE insurance_db;" in doc
    # Never the same value for both -- the exact anti-pattern this task
    # guards against.
    assert not re.search(r"POSTGRES_DB_INSURANCE\s*=\s*sema_db", doc)


def test_docs_apply_readonly_grants_to_both_databases_separately():
    doc = _deployment_doc()
    assert re.search(r"\\c sema_db\s*\n\\i sql/create_readonly_role\.sql", doc)
    assert re.search(r"\\c insurance_db\s*\n\\i sql/create_readonly_role\.sql", doc)


def test_docs_include_table_existence_verification_for_both_tenants():
    doc = _deployment_doc()
    assert "SELECT count(*) FROM orders;" in doc
    assert "SELECT count(*) FROM policies;" in doc
    assert "SELECT count(*) FROM claims;" in doc


def test_docs_include_cross_tenant_isolation_verification():
    doc = _deployment_doc()
    assert "SELECT * FROM policies LIMIT 1;" in doc
    assert "SELECT * FROM orders LIMIT 1;" in doc
    assert "relation \"policies\" does not exist" in doc
    assert "relation \"orders\" does not exist" in doc


def test_docs_include_sema_readonly_write_rejection_verification():
    doc = _deployment_doc()
    for verb in ("INSERT INTO orders", "UPDATE orders", "DELETE FROM orders", "TRUNCATE orders", "DROP TABLE orders"):
        assert verb in doc
    assert doc.count("EXPECTED TO ERROR") >= 5
    # insurance_db's write-rejection checks are documented as "repeat these
    # against insurance_db" rather than a literally duplicated SQL block --
    # confirm that instruction is actually present, not just implied.
    assert "Repeat against `insurance_db`" in doc


def test_docs_include_client_id_fallback_verification():
    doc = _deployment_doc()
    assert "not-a-real-client" in doc
    assert "404" in doc


def test_render_yaml_still_declares_exactly_one_postgres_service():
    """Both tenants share ONE Render Postgres instance (separate databases,
    not separate services) -- render.yaml's `databases:` section must
    declare exactly one entry, never a second one for `insurance`."""
    render_yaml = (_PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    databases_section = render_yaml.split("\ndatabases:", 1)[1]
    assert databases_section.count("\n  - name:") == 1
    assert "sema-pilot-db" in databases_section
