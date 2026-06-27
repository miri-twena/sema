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

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Pick the semantic layer for the active client. SEMA_CLIENT=insurance points
# the agent at the auto-insurance metrics; anything else uses the ecommerce
# layer. This is the semantic-layer half of the multi-client switch (the DB
# half lives in db.py) -- same agent, different "governed measures" folder.
load_dotenv()
_SQL_DIR = Path(__file__).resolve().parent.parent.parent / "sql"
_CLIENT = os.environ.get("SEMA_CLIENT", "ecommerce").strip().lower()
SEMANTIC_DIR = _SQL_DIR / "insurance" / "semantic" if _CLIENT == "insurance" else _SQL_DIR / "semantic"

# Every metric file must define these keys, or we consider it malformed.
REQUIRED_KEYS = {"name", "label", "description", "grain", "sql", "dimensions", "examples"}


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


def load_semantic_layer() -> list[dict]:
    """Return every metric definition as a list of dicts, sorted by name.

    Raises SemanticLayerError if the folder is empty or any file is invalid.
    """
    if not SEMANTIC_DIR.exists():
        raise SemanticLayerError(f"semantic layer folder not found: {SEMANTIC_DIR}")

    files = sorted(SEMANTIC_DIR.glob("*.yaml"))
    if not files:
        raise SemanticLayerError(f"no .yaml metric files found in {SEMANTIC_DIR}")

    metrics = [_load_one(path) for path in files]

    # Guard against duplicate metric names (would confuse the agent).
    names = [m["name"] for m in metrics]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise SemanticLayerError(f"duplicate metric names: {sorted(duplicates)}")

    return metrics


def get_metric(name: str) -> dict | None:
    """Look up a single metric by its name, or None if not found."""
    for metric in load_semantic_layer():
        if metric["name"] == name:
            return metric
    return None
