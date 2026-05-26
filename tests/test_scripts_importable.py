"""Every script under debate/scripts/ must import cleanly.

Catches missing-deps / syntax errors / broken cross-script imports before
they show up as silent runtime failures in /run-debate. No network used.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "debate" / "scripts"

SCRIPT_MODULES = sorted(
    p.stem for p in SCRIPTS_DIR.glob("*.py") if p.stem != "__init__" and not p.stem.startswith("__")
)


@pytest.mark.parametrize("module_name", SCRIPT_MODULES)
def test_script_imports(module_name: str):
    """Importing the module must not raise (conftest puts SCRIPTS_DIR on sys.path)."""
    importlib.import_module(module_name)
