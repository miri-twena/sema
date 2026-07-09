"""
SEMA agent: semantic-layer loader.

Loads every metric definition from sql/semantic/*.yaml -- the agent's
"grounding". Think of these YAML files as the governed measure definitions
in a BI tool: one trusted place that says what "Revenue", "Churn Risk",
etc. mean and how to compute them, so the agent never invents its own
(possibly wrong) definition.

This module is pure file-loading + validation. It has NO dependency on the
Claude API key -- it works whether or not the key is configured.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from sema_core.client_registry import PROJECT_ROOT, active_client_id, get_client_by_id

# Every metric file must define these keys, or we consider it malformed.
REQUIRED_KEYS = {"name", "label", "description", "grain", "sql", "dimensions", "examples"}


def semantic_dir(client_id: str | None = None) -> Path:
    """Folder of *.yaml metric files for the active (or given) client.

    Resolved at call time (not import time) so switching clients in the UI
    immediately changes which semantic layer the agent is grounded in.
    """
    client = get_client_by_id(client_id or active_client_id())
    return PROJECT_ROOT / client["semantic_dir"]


class SemanticLayerError(Exception):
    """Raised when a metric file is missing or malformed."""


def _load_one(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise SemanticLayerError(f"{path.name}: top level must be a mapping")

    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise SemanticLayerError(f"{path.name}: missing required keys {sorted(missing)}")

    return data


def load_semantic_layer(client_id: str | None = None) -> list[dict]:
    """Return every metric definition for the active (or given) client.

    Raises SemanticLayerError if the folder is empty or any file is invalid.
    """
    folder = semantic_dir(client_id)
    if not folder.exists():
        raise SemanticLayerError(f"semantic layer folder not found: {folder}")

    files = sorted(folder.glob("*.yaml"))
    if not files:
        raise SemanticLayerError(f"no .yaml metric files found in {folder}")

    metrics = [_load_one(path) for path in files]

    # Guard against duplicate metric names (would confuse the agent).
    names = [m["name"] for m in metrics]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise SemanticLayerError(f"duplicate metric names: {sorted(duplicates)}")

    return metrics


def get_metric(name: str, client_id: str | None = None) -> dict | None:
    """Look up a single metric by its name, or None if not found."""
    for metric in load_semantic_layer(client_id):
        if metric["name"] == name:
            return metric
    return None
