"""Shared pytest fixtures + sys.path setup for debate/scripts/* tests.

The scripts under debate/scripts/ are invoked as scripts (not as a package),
so they use plain `from _common import ...` imports. Tests need the scripts
directory on sys.path before they can import the modules under test.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "debate" / "scripts"

# Put the scripts dir at the FRONT so `_common` etc. resolve to our package, not
# to any similarly-named module that might be installed in the env.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
