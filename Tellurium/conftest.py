"""Make the flat ``tellurium_engine`` import resolve regardless of pytest rootdir.

``Tellurium/pytest.ini`` declares ``pythonpath = . ..``, which works only when
rootdir is ``Tellurium/``. Running pytest from the repo root (plain
``python3 -m pytest``, which pyproject.toml's ``testpaths`` promise, or
``python3 -m pytest Tellurium Tests``) makes rootdir the repo root; the
relative pythonpath entries then resolve elsewhere, and the flat
``from tellurium_engine import ...`` imports in ``Tellurium/tests/`` fail with
ModuleNotFoundError.

This conftest restores sys.path unconditionally. It lives in an argument
directory, so pytest loads it in every mode that collects Tellurium tests;
it is not loaded for Tests/ (root-level) collections, whose tests use the
packaged ``from Tellurium import tellurium_engine`` import and are therefore
unaffected.
"""

import pathlib
import sys

_TELLURIUM_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _TELLURIUM_DIR.parent

for _entry in (_TELLURIUM_DIR, _REPO_ROOT):
    _path = str(_entry)
    if _path not in sys.path:
        sys.path.insert(0, _path)
