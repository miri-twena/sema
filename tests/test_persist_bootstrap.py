"""
sema_core.persist_bootstrap (render_pilot_prompt.md item B): the idempotent
first-boot seed / symlink-swap that lets a single Render persistent disk
back both var/ (SQLite + logos) and sql/ (the writable semantic-layer tree)
without hiding the image's own baked-in content. See the module's own
docstring for the full rationale.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sema_core.persist_bootstrap import bootstrap


def _symlinks_supported() -> bool:
    """bootstrap() always runs inside a Linux container in production, where
    an unprivileged process can create symlinks freely. On a Windows dev
    machine (this repo's primary local environment -- see AGENTS.md) that
    needs SeCreateSymbolicLinkPrivilege / Developer Mode, which a plain dev
    checkout usually doesn't have. Probed once at collection time so these
    tests skip with a clear reason instead of failing on an unrelated
    machine-permissions gap."""
    try:
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "target"
            target.mkdir()
            (Path(d) / "link").symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _symlinks_supported(),
    reason="symlink creation needs elevated privileges/Developer Mode on this machine; "
    "the real bootstrap only ever runs in a Linux container",
)


def _make_image_sql(root: Path) -> Path:
    """A minimal stand-in for the repo's real sql/ tree: a couple of
    top-level files (schema.sql, validation_queries.sql) plus a semantic
    subdirectory with a YAML file -- enough to prove the WHOLE tree is
    preserved, not just sql/semantic/."""
    sql_dir = root / "sql"
    (sql_dir / "semantic").mkdir(parents=True)
    (sql_dir / "insurance" / "semantic").mkdir(parents=True)
    (sql_dir / "schema.sql").write_text("-- schema\n", encoding="utf-8")
    (sql_dir / "validation_queries.sql").write_text("-- validation\n", encoding="utf-8")
    (sql_dir / "semantic" / "metrics.yaml").write_text("revenue: {}\n", encoding="utf-8")
    (sql_dir / "insurance" / "semantic" / "metrics.yaml").write_text("loss_ratio: {}\n", encoding="utf-8")
    return sql_dir


def test_first_boot_seeds_the_persisted_sql_tree_and_symlinks_it(tmp_path):
    project_root = tmp_path / "image"
    persist_root = tmp_path / "disk"
    image_sql = _make_image_sql(project_root)

    bootstrap(project_root=project_root, persist_root=persist_root)

    persisted_sql = persist_root / "sql"
    assert (persisted_sql / "schema.sql").read_text(encoding="utf-8") == "-- schema\n"
    assert (persisted_sql / "validation_queries.sql").read_text(encoding="utf-8") == "-- validation\n"
    assert (persisted_sql / "semantic" / "metrics.yaml").read_text(encoding="utf-8") == "revenue: {}\n"
    assert (persisted_sql / "insurance" / "semantic" / "metrics.yaml").read_text(
        encoding="utf-8"
    ) == "loss_ratio: {}\n"

    # image_sql now resolves THROUGH to the persisted copy -- every module
    # that reads PROJECT_ROOT/"sql"/... keeps using the same path.
    assert image_sql.is_symlink()
    assert image_sql.resolve() == persisted_sql.resolve()


def test_sqlite_parent_directory_is_created(tmp_path):
    project_root = tmp_path / "image"
    persist_root = tmp_path / "disk"
    _make_image_sql(project_root)

    bootstrap(project_root=project_root, persist_root=persist_root)

    assert (persist_root / "var").is_dir()


def test_second_call_in_the_same_container_is_a_no_op(tmp_path):
    """Calling bootstrap twice without the container restarting (image_sql
    already a symlink) must not raise or touch anything."""
    project_root = tmp_path / "image"
    persist_root = tmp_path / "disk"
    _make_image_sql(project_root)

    bootstrap(project_root=project_root, persist_root=persist_root)
    bootstrap(project_root=project_root, persist_root=persist_root)  # must not raise

    assert (project_root / "sql").is_symlink()


def test_a_later_boot_never_overwrites_persisted_semantic_changes(tmp_path):
    """The core persistence guarantee: an admin's Publish (sema_core.
    semantic_editor) rewrote a YAML file on the FIRST container's persisted
    disk; a brand-new container (fresh image sql/, same disk) must see that
    edit, not the original baked-in content."""
    project_root = tmp_path / "image"
    persist_root = tmp_path / "disk"
    _make_image_sql(project_root)

    # First container boot: seeds the disk.
    bootstrap(project_root=project_root, persist_root=persist_root)

    # The admin panel publishes a change -- mutates the PERSISTED file
    # directly, exactly like sema_core.semantic_editor.write_atomic does
    # through the (by-then-symlinked) sql/ path.
    (persist_root / "sql" / "semantic" / "metrics.yaml").write_text("revenue: {edited: true}\n", encoding="utf-8")

    # A brand-new container starts from the pristine image again: sql/ is a
    # real directory with the ORIGINAL content, not a symlink (Docker images
    # are immutable -- the previous container's symlink swap only ever
    # touched the FIRST container's own writable layer, never the image
    # itself). Simulate that by discarding the first container's symlink
    # (unlink, not rmtree -- rmtree refuses to descend into a symlinked
    # directory, and rightly so) and recreating a real directory in its place.
    (project_root / "sql").unlink()
    _make_image_sql(project_root)

    # Second container boot, same disk.
    bootstrap(project_root=project_root, persist_root=persist_root)

    # The persisted edit survived -- it was NOT reset back to the image's
    # original "revenue: {}".
    assert (persist_root / "sql" / "semantic" / "metrics.yaml").read_text(
        encoding="utf-8"
    ) == "revenue: {edited: true}\n"
    assert (project_root / "sql").is_symlink()


def test_persist_root_defaults_to_env_var(tmp_path, monkeypatch):
    project_root = tmp_path / "image"
    persist_root = tmp_path / "disk-from-env"
    _make_image_sql(project_root)
    monkeypatch.setenv("SEMA_PERSIST_ROOT", str(persist_root))

    bootstrap(project_root=project_root)  # no persist_root override

    assert (persist_root / "var").is_dir()
    assert (persist_root / "sql" / "schema.sql").exists()
