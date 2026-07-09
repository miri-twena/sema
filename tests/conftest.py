"""
Shared pytest setup for the SEMA backend tests.

The backend modules import as top-level (``from db import ...``,
``import client_registry``) because they live in ``app/``. Putting ``app/`` on
sys.path here is the test-suite equivalent of ``PYTHONPATH=app`` -- so tests
run without launching Streamlit, and without a live DB or API key.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
