"""
P1a item 6: settings read from env with sane defaults.

deployment_prep_prompt.md item 2 extends this file with SEMA_ENV/
SEMA_PUBLIC_URL/SEMA_AUTH_MODE/cookie_secure and the fail-fast
validate_for_production() checks; item 8 (importing api.main actually
raises in production mode, doesn't in dev) is tested via subprocess at the
bottom of this file, since api.main's fail-fast check runs at MODULE IMPORT
time -- reloading it in-process would corrupt the module cache every other
test in this session relies on.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sema_core.settings import load_settings, validate_for_production

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VALID_FERNET_KEY = "4YuN_Pa2xK8a5jsT1v_fixLfh__sV_YGBUBg0ZL7j70="


def test_defaults_when_env_absent(monkeypatch):
    for var in ("SEMA_MODEL", "SEMA_MAX_ITERATIONS", "SEMA_ROW_LIMIT", "SEMA_CORS_ORIGINS"):
        monkeypatch.delenv(var, raising=False)
    s = load_settings()
    assert s.anthropic_model == "claude-sonnet-4-6"
    assert s.max_iterations == 8
    assert s.row_limit == 1000
    assert s.cors_origins == ["http://localhost:5173", "http://localhost:3000"]


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("SEMA_MODEL", "claude-test-model")
    monkeypatch.setenv("SEMA_MAX_ITERATIONS", "3")
    monkeypatch.setenv("SEMA_CORS_ORIGINS", "https://a.com, https://b.com")
    s = load_settings()
    assert s.anthropic_model == "claude-test-model"
    assert s.max_iterations == 3
    assert s.cors_origins == ["https://a.com", "https://b.com"]


def test_invalid_int_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SEMA_MAX_ITERATIONS", "not-a-number")
    s = load_settings()
    assert s.max_iterations == 8


# --- deployment mode: SEMA_ENV / SEMA_PUBLIC_URL / SEMA_AUTH_MODE / cookies -
def test_env_defaults_to_dev_with_insecure_cookies(monkeypatch):
    monkeypatch.delenv("SEMA_ENV", raising=False)
    s = load_settings()
    assert s.env == "dev"
    assert s.cookie_secure is False
    assert s.auth_mode == "mock"
    assert s.public_url == ""


def test_env_production_makes_cookies_secure(monkeypatch):
    monkeypatch.setenv("SEMA_ENV", "production")
    s = load_settings()
    assert s.env == "production"
    assert s.cookie_secure is True


def test_public_url_and_auth_mode_read_from_env(monkeypatch):
    monkeypatch.setenv("SEMA_PUBLIC_URL", "https://sema.example.com")
    monkeypatch.setenv("SEMA_AUTH_MODE", "real")
    s = load_settings()
    assert s.public_url == "https://sema.example.com"
    assert s.auth_mode == "real"


# --- validate_for_production: the fail-fast checklist ----------------------
def _make_production_ready_settings(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("SEMA_SECRETS_KEY", _VALID_FERNET_KEY)
    monkeypatch.setenv("SEMA_API_KEY", "a-real-api-key")
    monkeypatch.setenv("SEMA_PUBLIC_URL", "https://sema.example.com")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-production-password")
    monkeypatch.setenv("POSTGRES_READONLY_PASSWORD", "another-real-password")
    return load_settings()


def test_validate_for_production_passes_when_everything_is_set(monkeypatch):
    s = _make_production_ready_settings(monkeypatch)
    assert validate_for_production(s) == []


def test_validate_for_production_flags_missing_anthropic_key(monkeypatch):
    s = _make_production_ready_settings(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    problems = validate_for_production(s)
    assert any("ANTHROPIC_API_KEY" in p for p in problems)


def test_validate_for_production_flags_missing_secrets_key(monkeypatch):
    s = _make_production_ready_settings(monkeypatch)
    monkeypatch.setenv("SEMA_SECRETS_KEY", "")
    problems = validate_for_production(s)
    assert any("SEMA_SECRETS_KEY is not set" in p for p in problems)


def test_validate_for_production_flags_invalid_secrets_key(monkeypatch):
    s = _make_production_ready_settings(monkeypatch)
    monkeypatch.setenv("SEMA_SECRETS_KEY", "not-a-valid-fernet-key")
    problems = validate_for_production(s)
    assert any("not a valid Fernet key" in p for p in problems)


def test_validate_for_production_flags_empty_sema_api_key(monkeypatch):
    s = _make_production_ready_settings(monkeypatch)
    monkeypatch.delenv("SEMA_API_KEY", raising=False)
    s = load_settings()
    problems = validate_for_production(s)
    assert any("SEMA_API_KEY" in p for p in problems)


def test_validate_for_production_flags_missing_public_url(monkeypatch):
    s = _make_production_ready_settings(monkeypatch)
    monkeypatch.delenv("SEMA_PUBLIC_URL", raising=False)
    s = load_settings()
    problems = validate_for_production(s)
    assert any("SEMA_PUBLIC_URL" in p for p in problems)


def test_validate_for_production_flags_default_db_passwords(monkeypatch):
    s = _make_production_ready_settings(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", "sema_password")
    monkeypatch.setenv("POSTGRES_READONLY_PASSWORD", "sema_readonly_pw")
    s = load_settings()
    problems = validate_for_production(s)
    assert any("POSTGRES_PASSWORD" in p for p in problems)
    assert any("POSTGRES_READONLY_PASSWORD" in p for p in problems)


def test_validate_for_production_reports_every_problem_at_once(monkeypatch):
    """Fail-fast on the FIRST problem alone would mean a deployer fixes one
    var, redeploys, hits the next -- one crash-loop per missing var. This
    proves every check runs regardless of earlier failures."""
    for var in ("ANTHROPIC_API_KEY", "SEMA_SECRETS_KEY", "SEMA_API_KEY", "SEMA_PUBLIC_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "sema_password")
    monkeypatch.setenv("POSTGRES_READONLY_PASSWORD", "sema_readonly_pw")
    s = load_settings()
    problems = validate_for_production(s)
    assert len(problems) == 6


# --- api.main's actual startup gate (module-import-time raise) -------------
# A real subprocess, not an in-process module reload: api.main has real
# import-time side effects (store singletons, etc.), so reloading it here
# would corrupt the module cache every other test in this session depends
# on. Spawning `python -c "import api.main"` with a controlled environment
# is slower (~1s) but the only way to test "does the process actually
# refuse to boot" without that risk.
def _run_import_api_main(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_overrides}
    return subprocess.run(
        [sys.executable, "-c", "import api.main"],
        cwd=_PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_importing_api_main_fails_fast_in_production_with_missing_vars():
    # Explicitly blanks each var for the SUBPROCESS's env only (never touches
    # this test process's real os.environ, which wouldn't be restored after
    # the test since this bypasses monkeypatch entirely).
    env = {"SEMA_ENV": "production"}
    for var in ("ANTHROPIC_API_KEY", "SEMA_SECRETS_KEY", "SEMA_API_KEY", "SEMA_PUBLIC_URL"):
        env[var] = ""
    result = _run_import_api_main(env)
    assert result.returncode != 0
    assert "SEMA_ENV=production but startup checks failed" in result.stderr


def test_importing_api_main_succeeds_in_dev_even_with_missing_vars():
    env = {"SEMA_ENV": "dev"}
    for var in ("ANTHROPIC_API_KEY", "SEMA_SECRETS_KEY", "SEMA_API_KEY", "SEMA_PUBLIC_URL"):
        env[var] = ""
    result = _run_import_api_main(env)
    assert result.returncode == 0, result.stderr


def test_importing_api_main_succeeds_in_production_when_everything_is_set():
    env = {
        "SEMA_ENV": "production",
        "ANTHROPIC_API_KEY": "sk-test-key",
        "SEMA_SECRETS_KEY": _VALID_FERNET_KEY,
        "SEMA_API_KEY": "a-real-api-key",
        "SEMA_PUBLIC_URL": "https://sema.example.com",
        "POSTGRES_PASSWORD": "a-real-production-password",
        "POSTGRES_READONLY_PASSWORD": "another-real-password",
    }
    result = _run_import_api_main(env)
    assert result.returncode == 0, result.stderr
