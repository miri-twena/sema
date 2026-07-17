"""
Test that the Streamlit freeze is enforced.

Streamlit (app/) is frozen as an internal dev tool. Product code (sema_core/,
api/) must not import from app/. This test scans for any violations.
"""

import re
from pathlib import Path


def test_no_product_imports_from_streamlit():
    """Fail if sema_core/ or api/ import from app/."""
    project_root = Path(__file__).parent.parent
    product_dirs = [project_root / "sema_core", project_root / "api"]

    violations = []

    for product_dir in product_dirs:
        if not product_dir.exists():
            continue

        for py_file in product_dir.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Match patterns like "from app import X" or "import app"
            if re.search(r"^\s*(from\s+app\s+import|import\s+app\b)", content, re.MULTILINE):
                violations.append(py_file.relative_to(project_root))

    if violations:
        violation_list = "\n  ".join(str(v) for v in violations)
        raise AssertionError(
            f"Streamlit freeze violation: the following product files import from app/:\n"
            f"  {violation_list}\n\n"
            f"Streamlit (app/) is frozen as an internal dev tool. "
            f"Product code (sema_core/, api/) must not depend on it."
        )
