"""
P1a item 6: settings read from env with sane defaults.
"""

from __future__ import annotations

from settings import load_settings


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
