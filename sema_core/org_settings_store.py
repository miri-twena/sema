"""
SEMA: server-side organization-settings store.

Backs the client admin panel's "Organization settings" screen (spec §2).
Lives in the SAME small SQLite metadata store as the conversation/org-users
stores (var/sema_state.db) -- app-owned state, entirely separate from the
tenant analytics databases in db.py.

Mirrors OrgUserStore's conventions on purpose (one connection per call,
parameterized SQL, ISO-UTC timestamps, guarded ALTER migrations, and a
client_id ownership check on every method).

One row per client, auto-created with sensible defaults on first read
(get_or_create) rather than requiring a separate seed step -- self-healing,
same spirit as conversation_store.py minting a conversation row lazily.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytz

from sema_core import sqlite_utils

# --- validation: fixed lists, not free text -------------------------------

# pytz's own curated list (~450 IANA zones) -- avoids hand-maintaining one and
# guarantees every accepted value is a real zone `zoneinfo`/pandas can use.
VALID_TIMEZONES = frozenset(pytz.common_timezones)

# {code: (symbol, position)} -- position is where the symbol sits relative to
# the number ("prefix": $100, "suffix": 100 ₪). Display-only: never drives a
# currency CONVERSION, only how a number is drawn.
CURRENCIES: dict[str, tuple[str, str]] = {
    "USD": ("$", "prefix"),
    "EUR": ("€", "prefix"),
    "GBP": ("£", "prefix"),
    "ILS": ("₪", "suffix"),
}
VALID_CURRENCIES = frozenset(CURRENCIES)

# "1,234.56" (US/UK-style) vs "1.234,56" (EU-style) -- selects the Intl locale
# the frontend formats numbers with; never changes the underlying value.
VALID_NUMBER_FORMATS = frozenset({"1,234.56", "1.234,56"})

VALID_LANGUAGES = frozenset({"en", "he"})

VALID_RETENTION_POLICIES = frozenset({"forever", "90d", "30d"})

# Every column PATCH may touch, and what validates it. Centralized so the API
# layer and the store agree on exactly one allow-list -- a field not in this
# dict can never be written via update(), whitelisted-column-injection-proof
# the same way OrgUserStore's _update() is.
_FIELD_VALIDATORS = {
    "name": lambda v: isinstance(v, str) and 1 <= len(v.strip()) <= 200,
    "timezone": lambda v: v in VALID_TIMEZONES,
    "currency": lambda v: v in VALID_CURRENCIES,
    "number_format": lambda v: v in VALID_NUMBER_FORMATS,
    "default_language": lambda v: v in VALID_LANGUAGES,
    "retention_policy": lambda v: v in VALID_RETENTION_POLICIES,
}


class InvalidSettingError(Exception):
    """Raised when a PATCH'd field fails its validator (unknown timezone,
    currency not in the fixed list, etc.) -- the API turns this into a 422
    naming the specific field."""

    def __init__(self, field: str, value):
        self.field = field
        self.value = value
        super().__init__(f"invalid value for {field!r}: {value!r}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrgSettingsStore:
    """SQLite-backed store for one organization-settings row per client."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite_utils.connect(self._path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS org_settings ("
                "client_id TEXT PRIMARY KEY, name TEXT NOT NULL, logo_path TEXT, "
                "timezone TEXT NOT NULL, currency TEXT NOT NULL, "
                "number_format TEXT NOT NULL, default_language TEXT NOT NULL, "
                "retention_policy TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "client_id": r[0],
            "name": r[1],
            "logo_path": r[2],
            "timezone": r[3],
            "currency": r[4],
            "number_format": r[5],
            "default_language": r[6],
            "retention_policy": r[7],
            "updated_at": r[8],
        }

    _SELECT_SQL = (
        "SELECT client_id, name, logo_path, timezone, currency, number_format, "
        "default_language, retention_policy, updated_at FROM org_settings"
    )

    def get(self, client_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"{self._SELECT_SQL} WHERE client_id = ?", (client_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_or_create(
        self, client_id: str, default_name: str, default_timezone: str | None = None
    ) -> dict:
        """The settings screen's primary read: auto-creates a sensible-default
        row on first access rather than requiring a separate seed step, so a
        newly-configured client (or a fresh dev DB) never 404s here. Existing
        rows are returned unchanged -- this never overwrites a saved setting."""
        existing = self.get(client_id)
        if existing is not None:
            return existing
        tz = default_timezone if default_timezone in VALID_TIMEZONES else "UTC"
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO org_settings (client_id, name, logo_path, timezone, "
                "currency, number_format, default_language, retention_policy, updated_at) "
                "VALUES (?, ?, NULL, ?, 'USD', '1,234.56', 'en', 'forever', ?)",
                (client_id, default_name, tz, now),
            )
        return self.get(client_id)

    def update(self, client_id: str, patch: dict, expected_updated_at: str | None = None) -> dict:
        """Partial (per-field) update. Validates every field in `patch` against
        `_FIELD_VALIDATORS` BEFORE writing anything -- one bad field fails the
        whole call rather than partially applying.

        Concurrency: last-write-wins, always -- this never REJECTS a write.
        `expected_updated_at`, when given, is compared to the row's current
        `updated_at` purely to tell the CALLER whether they clobbered a change
        they hadn't seen yet (returned as `_conflict` for the API to relay as
        a toast to the loser). The row is a client_id PRIMARY KEY singleton
        (get_or_create backfills it), so there's no "not found" case once a
        client is configured at all.
        """
        for field, value in patch.items():
            if field not in _FIELD_VALIDATORS:
                raise InvalidSettingError(field, value)
            if not _FIELD_VALIDATORS[field](value):
                raise InvalidSettingError(field, value)

        now = _now()
        with closing(self._connect()) as conn, conn:
            current = conn.execute(
                "SELECT updated_at FROM org_settings WHERE client_id = ?", (client_id,)
            ).fetchone()
            conflict = bool(
                expected_updated_at and current and current[0] != expected_updated_at
            )
            set_clause = ", ".join(f"{field} = ?" for field in patch)
            conn.execute(
                f"UPDATE org_settings SET {set_clause}, updated_at = ? WHERE client_id = ?",
                (*patch.values(), now, client_id),
            )
        updated = self.get(client_id)
        return {**updated, "_conflict": conflict}

    def set_logo_path(self, client_id: str, logo_path: str | None) -> dict:
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE org_settings SET logo_path = ?, updated_at = ? WHERE client_id = ?",
                (logo_path, now, client_id),
            )
        return self.get(client_id)
