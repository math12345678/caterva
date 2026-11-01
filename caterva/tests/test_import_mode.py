"""A missing dependency must not be reported as a packaging fault.

THE BUG
-------
Caterva supports two import styles -- package (`from caterva.core.utils
import ...`) and flat (`from core.utils import ...`) -- with twenty-two
fallbacks shaped like this:

    try:
        from caterva.core.utils import _fmt
    except ModuleNotFoundError:
        from core.utils import _fmt

`caterva/core/utils.py` imports `roadrunner`. With roadrunner missing, the
first import fails with the true reason, the `except` swallows it, flat
mode is tried, and the user is shown:

    ModuleNotFoundError: No module named 'core'

A missing third-party package, reported as a missing internal module. The
reader goes hunting for a packaging bug that does not exist, while the real
cause sits two frames up a chained traceback.

Same family as the runner-boundary bug this project already fixed: an error
path that discards the reason and substitutes its own.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from caterva.core.import_mode import PACKAGE_ROOT, package_path_missing

REPO = pathlib.Path(__file__).resolve().parent.parent.parent


def test_a_missing_third_party_dependency_is_not_a_package_path_problem():
    """The case that caused the bug."""
    assert package_path_missing(ModuleNotFoundError(name="roadrunner")) is False
    assert package_path_missing(ModuleNotFoundError(name="antimony")) is False
    assert package_path_missing(ModuleNotFoundError(name="libsbml")) is False
    assert package_path_missing(ModuleNotFoundError(name="numpy")) is False


def test_a_missing_package_path_is_recognised():
    """The case flat mode genuinely exists for."""
    assert package_path_missing(ModuleNotFoundError(name=PACKAGE_ROOT)) is True
    assert package_path_missing(ModuleNotFoundError(name="caterva.core")) is True
    assert package_path_missing(
        ModuleNotFoundError(name="caterva.core.data_structures")
    ) is True


def test_a_lookalike_top_level_module_is_not_the_package():
    """`Catervafoo` starts with the package name and is not the package.

    A `startswith("caterva")` test without the dot would treat it as one,
    and a third-party package named that way would be silently retried in
    flat mode.
    """
    assert package_path_missing(ModuleNotFoundError(name="Catervafoo")) is False
    assert package_path_missing(ModuleNotFoundError(name="Catervalike.core")) is False


def test_an_unclassifiable_import_error_is_not_treated_as_the_package():
    """`name` is None on some import failures. Re-raising shows the real
    traceback; retrying would bury it."""
    assert package_path_missing(ModuleNotFoundError("no name attribute")) is False


def test_every_dual_mode_fallback_reraises_a_dependency_failure():
    """The rule, enforced across the engine rather than in one file.

    A fallback added later without the guard would reintroduce exactly the
    bug this module exists to prevent, and nothing else would notice: the
    code works fine as long as every dependency happens to be installed.
    """
    offenders: list[str] = []
    for path in sorted(REPO.glob("caterva/**/*.py")):
        if path.name == "import_mode.py" or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"except ModuleNotFoundError[^\n]*\n", text):
            following = text[match.end(): match.end() + 400]
            if "_package_path_missing" not in following:
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(REPO)}:{line}")

    assert not offenders, (
        "dual-mode import fallback(s) with no dependency guard:\n  "
        + "\n  ".join(offenders)
        + "\n\nEach one can report a missing third-party package as a missing "
        "internal module. See caterva/core/import_mode.py."
    )
