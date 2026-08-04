"""
SEMA: centralized settings.

One governed place to read configuration from environment variables, with
typed defaults -- instead of scattering os.environ.get(...) calls (each with
its own slightly different default) across agent.py, db.py, safety.py and the
API. Think of it like a single "parameters" reference table the whole backend
reads from.

Hand-rolled on top of os.environ, so it adds no new dependency. Values are read
once when this module is imported; restart the process after editing .env for
changes to take effect (the same rule the app already had).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

# sema_core/settings.py -> repo root (mirrors client_registry.PROJECT_ROOT).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    """Read an int from env, falling back to `default` if unset/blank/invalid."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _csv(name: str, default: list[str]) -> list[str]:
    """Read a comma-separated list from env (e.g. CORS origins)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _bool(name: str, default: bool) -> bool:
    """Read a boolean from env ("0"/"false"/"no" -> False, anything else set
    -> True), falling back to `default` if unset/blank."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no")


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the backend's configuration."""

    # --- Anthropic / agent loop ---
    anthropic_model: str
    # Backup model tried automatically when the primary model API-errors
    # (overloaded/5xx). Blank disables the fallback. When it answers, the run
    # carries a "fallback_model" notice so the swap is never silent.
    anthropic_model_fallback: str
    max_iterations: int
    max_tokens: int
    max_history_turns: int
    anthropic_timeout_s: int
    anthropic_max_retries: int

    # --- SQL safety ---
    row_limit: int
    statement_timeout_ms: int

    # --- full-data CSV export (full_data_export_prompt.md) ---
    # Ceiling on a re-run export query -- far above row_limit (the ON-SCREEN
    # display cap) since export's whole point is "more than what's shown."
    # Still a real ceiling, not "everything": a result past this returns a
    # note instead of a file (a data-pipeline job, not a chat export).
    export_row_limit: int
    # Exports per (client, org_user) per rolling clock-hour -- abuse guardrail
    # for a re-run that costs a real DB query, separate from daily_query_limit
    # (that one counts LLM calls; an export never calls the LLM at all).
    export_hourly_limit: int

    # --- database credentials (db NAME is per-client, resolved in db.py) ---
    db_host: str
    db_port: str
    db_user: str
    db_password: str
    db_readonly_user: str
    db_readonly_password: str
    # Max pooled connections per (client, role) -- e.g. "ecommerce"+"full" and
    # "ecommerce"+"readonly" are separate pools, each capped at this. Was 5
    # (fine for single-user local dev, too low for concurrent production
    # traffic -- backend_qa_prompt.md's QA sweep measured 20 concurrent
    # /api/chat requests exhausting a pool of 5 and driving latency to
    # 10-45s). Raised to 20; the request-side thundering-herd bug that made
    # 20 concurrent requests need up to 20 simultaneous connections in the
    # first place is fixed separately (sema_core/cache.py's single-flight
    # ttl_cache), so this is now real headroom, not a band-aid over it.
    db_pool_max: int

    # --- API ---
    cors_origins: list[str]
    api_key: str  # X-API-Key value; empty = auth disabled (local dev)

    # --- server-side conversations ---
    conversation_db_path: Path  # SQLite file for conversation metadata
    history_token_budget: int  # approx. tokens of prior turns sent to the model

    # --- retention sweep (org_settings_gapfix_prompt.md) ---
    # Disable the background daily sweep entirely (tests/local runs that don't
    # want a scheduled task running against their DB). Default on.
    retention_enabled: bool

    # --- data sources add-flow (data_sources_add_prompt.md) ---
    # Service-account email for the Google Sheets connector's "share this
    # sheet with..." instructions. Blank in local dev -- the flow still
    # works, it just lands in "setting up" state (see .env.example).
    gsheets_sa_email: str

    # --- deployment (deployment_prep_prompt.md) ---
    # "dev" (default, local docker-compose) or "production". Gates the
    # fail-fast startup checks below and a handful of other production-only
    # behaviors (api/main.py logs a loud mock-identity warning, cookies would
    # be Secure) -- see validate_for_production().
    env: str
    # This deployment's own externally-reachable URL (e.g.
    # "https://sema.example.com"), used to derive the CORS allowlist and
    # (once sessions exist) cookie domain/SameSite config. Blank in dev --
    # SEMA_CORS_ORIGINS already covers the Vite dev server.
    public_url: str
    # "mock" (default, today's only real mode -- see sema_core.current_user)
    # or "real". Not yet READ by any auth-deciding code path (auth_login_
    # prompt.md Parts A+B, blocked on hosting, will be the first thing that
    # branches on it) -- exists now so the env-var CONTRACT is complete and
    # every deployment declares its intent explicitly rather than silently
    # relying on "mock" being the only option that exists.
    auth_mode: str
    # Whether a session cookie (once auth lands) must set Secure -- true in
    # production (HTTPS is assumed), false in dev (plain http://localhost).
    # No cookie is actually SET anywhere yet; this is the one flag that code
    # will need, exposed now per the deployment task's "configuration surface"
    # ask rather than invented from scratch when auth lands.
    cookie_secure: bool

    # --- LLM cost guardrail (backend_qa_prompt.md item 5) ---
    # Per-(client, org_user) soft cap on /api/chat + /api/chat/stream calls
    # per calendar day (UTC). A generous default -- this exists to catch a
    # runaway script or a compromised session hammering the (billed)
    # Anthropic API, not to ration normal usage. 0 disables the cap entirely.
    daily_query_limit: int


def load_settings() -> Settings:
    """Build a Settings snapshot from the current environment.

    Kept as a function (not just a module constant) so tests can monkeypatch
    env vars and reload a fresh Settings without importing side effects.
    """
    return Settings(
        anthropic_model=os.environ.get("SEMA_MODEL", "claude-sonnet-4-6"),
        anthropic_model_fallback=os.environ.get(
            "SEMA_MODEL_FALLBACK", "claude-haiku-4-5-20251001"
        ),
        max_iterations=_int("SEMA_MAX_ITERATIONS", 8),
        max_tokens=_int("SEMA_MAX_TOKENS", 4000),
        max_history_turns=_int("SEMA_MAX_HISTORY_TURNS", 10),
        anthropic_timeout_s=_int("SEMA_ANTHROPIC_TIMEOUT_S", 60),
        anthropic_max_retries=_int("SEMA_ANTHROPIC_MAX_RETRIES", 2),
        row_limit=_int("SEMA_ROW_LIMIT", 1000),
        statement_timeout_ms=_int("SEMA_STATEMENT_TIMEOUT_MS", 5000),
        export_row_limit=_int("SEMA_EXPORT_ROW_LIMIT", 250_000),
        export_hourly_limit=_int("SEMA_EXPORT_HOURLY_LIMIT", 20),
        db_host=os.environ.get("POSTGRES_HOST", "localhost"),
        db_port=os.environ.get("POSTGRES_PORT", "5432"),
        db_user=os.environ.get("POSTGRES_USER", "sema_user"),
        db_password=os.environ.get("POSTGRES_PASSWORD", "sema_password"),
        db_readonly_user=os.environ.get("POSTGRES_READONLY_USER", "sema_readonly"),
        db_readonly_password=os.environ.get("POSTGRES_READONLY_PASSWORD", "sema_readonly_pw"),
        db_pool_max=_int("SEMA_DB_POOL_MAX", 20),
        api_key=os.environ.get("SEMA_API_KEY", "").strip(),
        cors_origins=_csv(
            "SEMA_CORS_ORIGINS",
            ["http://localhost:5173", "http://localhost:3000"],
        ),
        conversation_db_path=Path(
            os.environ.get("SEMA_CONVERSATION_DB", str(_PROJECT_ROOT / "var" / "sema_state.db"))
        ),
        history_token_budget=_int("SEMA_HISTORY_TOKEN_BUDGET", 8000),
        retention_enabled=_bool("SEMA_RETENTION_ENABLED", True),
        gsheets_sa_email=os.environ.get("SEMA_GSHEETS_SA_EMAIL", "").strip(),
        env=(os.environ.get("SEMA_ENV", "dev").strip() or "dev"),
        public_url=os.environ.get("SEMA_PUBLIC_URL", "").strip(),
        auth_mode=(os.environ.get("SEMA_AUTH_MODE", "mock").strip() or "mock"),
        cookie_secure=(os.environ.get("SEMA_ENV", "dev").strip() == "production"),
        daily_query_limit=_int("SEMA_DAILY_QUERY_LIMIT", 200),
    )


def validate_for_production(s: Settings) -> list[str]:
    """Fail-fast checks for SEMA_ENV=production. Returns every problem found
    (empty = ready to boot) rather than stopping at the first one, so a
    deployer sees the whole list in one failed deploy instead of fixing vars
    one crash-loop at a time. Called once at API startup (api/main.py) --
    never in `load_settings()` itself, so importing this module under the
    default SEMA_ENV=dev (every test, local dev) never risks aborting.

    Checks vars that already have permissive defaults today (empty API key =
    auth off; the well-known local-dev DB password) -- exactly the settings
    that are safe for local docker-compose but would be a real security hole
    left as-is in production.
    """
    problems: list[str] = []
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        problems.append("ANTHROPIC_API_KEY is not set")
    secrets_key = os.environ.get("SEMA_SECRETS_KEY", "").strip()
    if not secrets_key:
        problems.append(
            "SEMA_SECRETS_KEY is not set (data-source credential storage would be unusable)"
        )
    else:
        try:
            Fernet(secrets_key.encode())
        except Exception:
            problems.append("SEMA_SECRETS_KEY is not a valid Fernet key")
    if not s.api_key:
        problems.append("SEMA_API_KEY is not set -- the API would have NO authentication")
    if not s.public_url:
        problems.append("SEMA_PUBLIC_URL is not set (needed for CORS configuration)")
    if s.db_password == "sema_password":
        problems.append("POSTGRES_PASSWORD is still the local-dev default")
    if s.db_readonly_password == "sema_readonly_pw":
        problems.append("POSTGRES_READONLY_PASSWORD is still the local-dev default")
    return problems


# Module-level singleton the rest of the backend imports: `from settings import settings`.
settings = load_settings()
