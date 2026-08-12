"""Every third-party import must be declared in requirements(.txt|-dev.txt).

This exists because of a real incident: brenda_client.py imported httpx and
pydantic at module level, neither was declared, and nothing caught it until
CI did a genuinely fresh install and the entire literature-layer suite failed
to collect. See scripts/check_dependencies_declared.py for the static
analysis this test wraps.
"""

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_dependencies_declared import find_undeclared  # noqa: E402


def test_every_import_is_declared_in_requirements():
    undeclared = find_undeclared()
    assert not undeclared, (
        "These imports have no matching entry in requirements.txt or "
        f"requirements-dev.txt: {sorted(undeclared)}. A fresh install "
        "(exactly what CI does) will fail to collect the affected tests."
    )
