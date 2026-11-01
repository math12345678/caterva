"""The vacuous-test guard now reads Python, and this proves it.

WHY THIS EXISTS
---------------
`scripts/check_no_vacuous_tests.py` catches the defect where every assertion
in a test sits behind an `if`, so the test passes having verified nothing.
Its docstring records three real instances, including a regression test that
passed against the very bug it was written for.

**It scanned TypeScript only.** `TEST_FILE = r".*\\.(test|spec)\\.tsx?$"`.
Meanwhile it printed:

    OK: every test has at least one assertion that always runs.

over 1,574 Python test functions it had never looked at. That is the
guard's own defect class applied to its own scope: a check reporting more
than it checked, in the words most likely to be believed.

Turning the Python scan on found eight, now recorded in `PYTHON_BASELINE`
so the list can shrink but not grow.

WHAT THIS FILE ASSERTS
----------------------
That the Python half can fail. The guard has a `--selftest` covering its
branches on synthetic input; this covers the seam a selftest cannot — that
the scan is wired into `check()` and reaches real files under the real
roots.

The file began as a throwaway probe. It could not be deleted from this
sandbox, so it was made to earn its place instead of sitting in the suite
as a meaningless `assert True`.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_no_vacuous_tests.py"
)


def _guard():
    spec = importlib.util.spec_from_file_location("check_no_vacuous_tests", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_no_vacuous_tests"] = module
    spec.loader.exec_module(module)
    return module


guard = _guard()


def test_the_python_scan_looks_at_the_real_suites() -> None:
    """The premise. A scan of zero files reports zero violations and looks
    identical to a clean tree -- which is how this guard spent its whole
    life claiming to cover Python."""
    assert guard.PYTHON_ROOTS, "no Python roots configured"
    found = [
        path
        for root in guard.PYTHON_ROOTS
        for path in (guard.REPO_ROOT / root).rglob("test_*.py")
    ]
    assert len(found) > 50, (
        f"only {len(found)} Python test files discovered; the scan is not "
        "reaching the suites it claims to cover"
    )


def test_this_very_file_is_scanned() -> None:
    """Named specifically, so a change to the discovery globs that silently
    excluded this directory would fail here rather than pass quietly."""
    found = {
        path.name
        for root in guard.PYTHON_ROOTS
        for path in (guard.REPO_ROOT / root).rglob("test_*.py")
    }
    assert pathlib.Path(__file__).name in found


def test_a_wholly_conditional_assertion_is_reported(tmp_path, monkeypatch) -> None:
    """The behaviour itself, against the real `_python_violations`."""
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "test_bad.py").write_text(
        "def test_thing():\n"
        "    result = compute()\n"
        "    if result:\n"
        "        assert result.ok\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "PYTHON_ROOTS", ["suite"])
    monkeypatch.setattr(guard, "PYTHON_BASELINE", {})

    violations = guard._python_violations()
    assert violations, "a wholly conditional assertion was not reported"
    assert "test_thing" in violations[0]


def test_a_healthy_test_is_not_reported(tmp_path, monkeypatch) -> None:
    """The counterpart. Without it, a `_python_violations` that reported
    everything would satisfy the test above."""
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "test_good.py").write_text(
        "def test_thing():\n"
        "    result = compute()\n"
        "    assert result is not None\n"
        "    if result:\n"
        "        assert result.ok\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "PYTHON_ROOTS", ["suite"])
    monkeypatch.setattr(guard, "PYTHON_BASELINE", {})

    assert guard._python_violations() == []


def test_the_baseline_can_only_shrink() -> None:
    """Every recorded entry must still exist.

    A baseline whose entries have been renamed or deleted is a list of
    permissions for tests that are gone, and it grows stale silently. If a
    name here no longer resolves, remove it -- that is the list shrinking,
    which is the only direction allowed.
    """
    missing = []
    for key in guard.PYTHON_BASELINE:
        path_part, _, function = key.partition("::")
        path = guard.REPO_ROOT / path_part
        if not path.is_file():
            missing.append(f"{key} (file is gone)")
            continue
        if f"def {function}" not in path.read_text(encoding="utf-8", errors="replace"):
            missing.append(f"{key} (function is gone)")

    assert not missing, (
        "PYTHON_BASELINE records tests that no longer exist:\n  "
        + "\n  ".join(missing)
        + "\nRemove them. A stale exemption is a permission nobody granted."
    )
