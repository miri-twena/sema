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

    # --- database credentials (db NAME is per-client, resolved in db.py) ---
    db_host: str
    db_port: str
    db_user: str
    db_password: str
    db_readonly_user: str
    db_readonly_password: str
    db_pool_max: int  # max pooled connections per (client, role)

    # --- API ---
    cors_origins: list[str]
    api_key: str  # X-API-Key value; empty = auth disabled (local dev)

    # --- server-side conversations ---
    conversation_db_path: Path  # SQLite file for conversation metadata
    history_token_budget: int  # approx. tokens of prior turns sent to the model


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
        db_host=os.environ.get("POSTGRES_HOST", "localhost"),
        db_port=os.environ.get("POSTGRES_PORT", "5432"),
        db_user=os.environ.get("POSTGRES_USER", "sema_user"),
        db_password=os.environ.get("POSTGRES_PASSWORD", "sema_password"),
        db_readonly_user=os.environ.get("POSTGRES_READONLY_USER", "sema_readonly"),
        db_readonly_password=os.environ.get("POSTGRES_READONLY_PASSWORD", "sema_readonly_pw"),
        db_pool_max=_int("SEMA_DB_POOL_MAX", 5),
        api_key=os.environ.get("SEMA_API_KEY", "").strip(),
        cors_origins=_csv(
            "SEMA_CORS_ORIGINS",
            ["http://localhost:5173", "http://localhost:3000"],
        ),
        conversation_db_path=Path(
            os.environ.get("SEMA_CONVERSATION_DB", str(_PROJECT_ROOT / "var" / "sema_state.db"))
        ),
        history_token_budget=_int("SEMA_HISTORY_TOKEN_BUDGET", 8000),
    )


# Module-level singleton the rest of the backend imports: `from settings import settings`.
settings = load_settings()
