"""
Idempotent production-startup bootstrap for a single Render-style persistent
disk (docs/deployment.md's Render section). Run ONCE, before Uvicorn starts
(api/Dockerfile.prod's CMD) -- never imported by the running app itself.

Render mounts exactly one disk for this service, at /app/persist. Two things
need to survive a restart/redeploy there (docs/deployment.md section 4):
  - SQLite metadata (SEMA_CONVERSATION_DB) + uploaded org logos under var/
    (api/main.py's _logos_dir() is already conversation_db_path.parent /
    "logos", so pointing SEMA_CONVERSATION_DB at /app/persist/var/... covers
    both with one env var -- this module only has to make the directory
    exist).
  - the writable semantic-layer tree under sql/ (sema_core.semantic_editor
    rewrites *.yaml files on disk at runtime).

Mounting the disk directly over /app would hide the application code.
Mounting an initially-EMPTY disk directly over /app/sql would hide the sql/
tree baked into the image (schema.sql, the readonly-role script, every
semantic YAML) on first boot, before anything has seeded it. So instead:
first boot seeds /app/persist/sql from the image's own (pristine) sql/ tree,
then this module SYMLINKS the image's sql/ path to the persisted copy.
Every existing module that resolves paths as PROJECT_ROOT/"sql"/... (
client_registry, agent/semantic.py, semantic_editor.py, the schema/readonly-
role script loaders, ...) keeps using the exact same path it always has and
transparently reads/writes through to the persisted tree -- no code changes
anywhere else, and a later boot's image sql/ is always the same pristine
tree again (Docker images are immutable; the symlink only ever lives in a
previous CONTAINER's writable layer, never in the image), so re-seeding
never accidentally copies an already-redirected tree.

Python, not a shell script: no chmod +x / exec-bit question, and no
Windows-line-ending risk from editing this repo on Windows (a bash script
saved with CRLF silently breaks under Linux's #!/bin/sh). Runs as
`python -m sema_core.persist_bootstrap`, the same interpreter as the app.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# sema_core/persist_bootstrap.py -> repo root (mirrors settings.py's
# _PROJECT_ROOT / client_registry.PROJECT_ROOT).
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def bootstrap(project_root: Path = PROJECT_ROOT, persist_root: Path | None = None) -> None:
    """Idempotent -- safe to call on every boot, not just the first.

    `persist_root` defaults to SEMA_PERSIST_ROOT (env, falling back to
    "/app/persist") rather than being hardcoded, so a local smoke test can
    point it at a temp directory without needing the full production
    container layout. Both params are injectable directly for tests.
    """
    persist_root = persist_root or Path(os.environ.get("SEMA_PERSIST_ROOT", "/app/persist"))
    persist_var = persist_root / "var"
    persist_sql = persist_root / "sql"
    image_sql = project_root / "sql"

    persist_var.mkdir(parents=True, exist_ok=True)

    # First boot for this disk: persist_sql doesn't exist yet, or exists but
    # is still empty (a disk that was attached but never seeded). Seed it
    # from whatever sql/ tree the CURRENT image shipped with -- see the
    # module docstring for why image_sql is always the pristine baked-in
    # tree at this point, never a previous boot's redirected copy.
    if not persist_sql.exists() or not any(persist_sql.iterdir()):
        persist_sql.mkdir(parents=True, exist_ok=True)
        if image_sql.is_dir() and not image_sql.is_symlink():
            for item in image_sql.iterdir():
                dest = persist_sql / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

    if image_sql.is_symlink():
        # Already pointed at the persisted copy -- defensive only, a fresh
        # container never actually starts in this state (see docstring).
        return
    if image_sql.exists():
        shutil.rmtree(image_sql)
    image_sql.symlink_to(persist_sql, target_is_directory=True)


if __name__ == "__main__":
    bootstrap()
