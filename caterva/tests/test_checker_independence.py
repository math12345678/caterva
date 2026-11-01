"""scripts/check_checker_independence.py: the checker imports nothing of the producer, and the guard can tell.

WHY THIS EXISTS
---------------
`caterva verify` is worth something only while caterva/check/ shares no
code with caterva/evidence/ (ADR 0179). The guard is what enforces that,
and this file runs it unasked in the engine suite as well as in
verify_build. Both directions are exercised: the real package passes, and a
planted `from caterva.evidence...` fails, because a guard only ever seen
green on a clean tree is indistinguishable from one whose matcher matches
nothing (ADR 0015).
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "scripts" / "check_checker_independence.py"
CHECK_DIR = REPO / "caterva" / "check"


def _load():
    spec = importlib.util.spec_from_file_location("check_checker_independence", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


def _package(tmp_path: Path, **modules: str) -> Path:
    package = tmp_path / "check"
    package.mkdir()
    (package / "__init__.py").write_text('"""a checker"""\n', encoding="utf-8")
    for name, text in modules.items():
        (package / f"{name}.py").write_text(text, encoding="utf-8")
    return package


def test_the_selftest_passes():
    assert guard.selftest() == 0


def test_the_real_checker_is_independent():
    result = subprocess.run([sys.executable, str(GUARD)], capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "every one standard library or a sibling in the package" in result.stdout


def test_the_scan_covers_the_real_package():
    """The premise: a scan of nothing would pass for free."""
    modules, statements = guard.scanned(CHECK_DIR)
    assert modules >= 3, "caterva/check has __init__, verify and __main__ at least"
    assert statements >= 5


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("from caterva.evidence.canonical import digest", "caterva"),
        ("import caterva.evidence.claims", "caterva"),
        ("from Tests.brenda_client import parse_brenda_km_html", "Tests"),
        ("import numpy", "numpy"),
        ("import pydantic", "pydantic"),
        ("from bs4 import BeautifulSoup", "bs4"),
        ("import httpx", "not in the standard library"),
        ("from ..evidence import claims", "leaves the package"),
        ("import importlib", "run time"),
    ],
)
def test_each_kind_of_forbidden_import_is_found(tmp_path, line, expected):
    package = _package(tmp_path, verify=f"import json\n{line}\n")
    problems = guard.findings(package)
    assert len(problems) == 1
    assert problems[0].startswith("check/verify.py:2:")
    assert expected in problems[0]


def test_standard_library_and_sibling_imports_pass(tmp_path):
    package = _package(
        tmp_path,
        verify="from __future__ import annotations\nimport gzip\nimport hashlib\nimport json\nimport re\n"
               "from decimal import Decimal\nfrom pathlib import Path\nfrom typing import Any\n",
        __main__="import argparse\nfrom .verify import verify_bundle\nfrom . import verify\n",
    )
    assert guard.findings(package) == []


def test_a_sibling_that_does_not_exist_is_refused(tmp_path):
    package = _package(tmp_path, verify="from .parser import rows\n")
    assert len(guard.findings(package)) == 1
    assert "not a module of the package" in guard.findings(package)[0]


def test_an_empty_package_is_not_a_pass(tmp_path):
    (tmp_path / "empty").mkdir()
    assert guard.scanned(tmp_path / "empty") == (0, 0)


def test_the_forbidden_names_each_carry_a_reason():
    for name, reason in guard.FORBIDDEN.items():
        assert len(reason) > 20, name
    assert set(guard.FORBIDDEN) == {"caterva", "Tests", "bs4", "pydantic", "numpy"}
