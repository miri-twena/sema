"""
Internal-pilot access gate (render_pilot_prompt.md): SEMA_API_KEY is a
temporary SHARED-KEY gate for a private Render pilot, not real
authentication -- see docs/deployment.md's Render section and
require_api_key's docstring in api/main.py.

Covers the routing behavior that changed to make the gate safe to enable
without also blocking the SPA itself:
  - require_api_key now only enforces on /healthz + /api/* (previously
    /healthz was the only exemption, which would have 401'd the built
    frontend's own index.html/JS/CSS once SEMA_API_KEY was set).
  - the interactive API docs are disabled outright in production, since
    they live outside /api and would otherwise become publicly reachable
    once the gate stopped covering non-/api paths.

test_healthz.py already covers /healthz itself and /api/clients requiring
the key; this file covers the NEW exemption (non-/api paths) and the docs
gating, which needs a real subprocess import (api.main's FastAPI() call
reads settings.env once at import time -- see test_settings.py's own
subprocess pattern and its docstring for why an in-process reload isn't
safe here).
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.requests import Request

import api.main as main

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VALID_FERNET_KEY = "4YuN_Pa2xK8a5jsT1v_fixLfh__sV_YGBUBg0ZL7j70="


def _make_request(path: str) -> Request:
    """A minimal Starlette Request for a GET to `path` -- enough for
    require_api_key, which only reads request.url.path."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_non_api_paths_are_exempt_even_when_key_is_configured(monkeypatch):
    """The SPA's index.html and its built JS/CSS/asset paths (served by the
    catch-all route, which lives outside /api) must stay reachable with no
    key -- otherwise the browser could never load the access-gate screen
    itself. Exercised at the dependency-function level since the catch-all
    route is only REGISTERED when frontend/dist exists on disk (a real prod
    Docker build), not something to fake in a unit test."""
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, api_key="super-secret"))
    for path in ["/", "/index.html", "/assets/index-abc123.js", "/login", "/some/client/route"]:
        # No exception raised (would raise HTTPException(401) if gated).
        main.require_api_key(_make_request(path), x_api_key=None)


def test_api_paths_still_gated_after_the_exemption(monkeypatch):
    """Sanity check alongside the exemption above: broadening it to 'not
    /healthz' must not accidentally swallow /api/* too."""
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, api_key="super-secret"))
    with pytest.raises(Exception):
        main.require_api_key(_make_request("/api/clients"), x_api_key=None)
    with pytest.raises(Exception):
        main.require_api_key(_make_request("/api/chat"), x_api_key="wrong-key")
    # Correct key: no exception.
    main.require_api_key(_make_request("/api/clients"), x_api_key="super-secret")


def test_healthz_still_exempt_after_the_change(monkeypatch):
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, api_key="super-secret"))
    main.require_api_key(_make_request("/healthz"), x_api_key=None)


def test_empty_key_preserves_local_dev_behavior_on_api_paths(monkeypatch):
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, api_key=""))
    main.require_api_key(_make_request("/api/clients"), x_api_key=None)


# --- docs/redoc/openapi gating: real subprocess import, same rationale as
# test_settings.py's _run_import_api_main (api.main's FastAPI() call reads
# settings.env once at import time; reloading in-process would corrupt the
# module cache every other test in this session relies on). -----------------
def _run_and_capture_docs_urls(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_overrides}
    snippet = (
        "import api.main as m; "
        "print(m.app.docs_url, m.app.redoc_url, m.app.openapi_url)"
    )
    return subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=_PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_docs_are_disabled_in_production():
    env = {
        "SEMA_ENV": "production",
        "ANTHROPIC_API_KEY": "sk-test-key",
        "SEMA_SECRETS_KEY": _VALID_FERNET_KEY,
        "SEMA_API_KEY": "a-real-api-key",
        "SEMA_PUBLIC_URL": "https://sema.example.com",
        "POSTGRES_PASSWORD": "a-real-production-password",
        "POSTGRES_READONLY_PASSWORD": "another-real-password",
    }
    result = _run_and_capture_docs_urls(env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "None None None"


def test_docs_remain_enabled_in_dev():
    env = {"SEMA_ENV": "dev"}
    result = _run_and_capture_docs_urls(env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "/docs /redoc /openapi.json"
