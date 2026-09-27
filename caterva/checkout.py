"""Import the literature layer, which lives outside the package.

WHY THIS EXISTS
---------------
The resolvers that read BRENDA, rank rows by how well evidenced they are
and carry the disagreement between papers -- `fallback_logic`,
`parameterize`, `model_compatibility`, `assay_conditions` -- live in
`Tests/` at the repository root. They are not part of the wheel
(`MANIFEST.in` prunes them, and ADR 0177 records why the released artifacts
carry Caterva's code only).

Seven places in `caterva/` reach for them, each with the same two-line
idiom:

    try:
        from Tests.fallback_logic import resolve_kinetic_value
    except ImportError:
        from fallback_logic import resolve_kinetic_value

Both arms fail from an ordinary interpreter. `Tests/` has no
`__init__.py`, so `Tests.fallback_logic` only resolves when the repository
root is on `sys.path` AND the directory is treated as a namespace package;
the bare `fallback_logic` only resolves when `Tests/` itself is on the
path. Under pytest, `caterva/conftest.py` arranges the first. Under
`python -m caterva.compose`, nothing arranges either.

The measured consequence (ADR 0178): every literature scout failed with
`ModuleNotFoundError: No module named 'fallback_logic'`, and the search
that contained them **reported `converged=True`**. A run that reports
success while every agent inside it failed is the precise shape of failure
this project exists to refuse, and it sat in the flagship feature because
nothing user-facing called it.

So the path is arranged in one place, by a function that says plainly when
it cannot.

WHAT IT REFUSES TO DO
---------------------
Guess. It looks for `Tests/` beside the package's own parent, which is the
repository layout and nothing else. From an installed wheel or the app
folder there is no such directory, and `LiteratureLayerUnavailable` names
that rather than letting an `ImportError` surface three frames away as
though the code were broken.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

#: The repository root, when this package is being run from a checkout.
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent
_TESTS_DIR = _REPO_ROOT / "Tests"


class LiteratureLayerUnavailable(ImportError):
    """The literature resolvers are not reachable from this installation."""


def tests_directory() -> Path | None:
    """The checkout's `Tests/`, or None when running from an installed copy."""
    return _TESTS_DIR if _TESTS_DIR.is_dir() else None


def literature_module(name: str) -> Any:
    """Import `name` from the literature layer, wherever it is reachable.

    Tries the package form, then the flat form, then puts the checkout's
    `Tests/` on `sys.path` and tries the flat form again. Raises
    `LiteratureLayerUnavailable` with the reason when none works, because
    "no literature search is possible here" is a fact a caller must be able
    to report rather than a traceback.
    """
    for candidate in (f"Tests.{name}", name):
        try:
            return importlib.import_module(candidate)
        except ImportError:
            continue

    tests = tests_directory()
    if tests is None:
        raise LiteratureLayerUnavailable(
            f"{name!r} is part of Caterva's literature layer, which lives in "
            f"the repository's Tests/ directory and is not shipped in the "
            f"wheel or the app folder (ADR 0177). No literature search is "
            f"possible from this installation; clone the repository to run "
            f"one. Looked for {_TESTS_DIR}."
        )

    if str(tests) not in sys.path:
        # Appended, not inserted: a flat directory of modules with names as
        # general as `parameterize` must never shadow a real package.
        sys.path.append(str(tests))
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise LiteratureLayerUnavailable(
            f"{name!r} was not importable even with {tests} on sys.path: "
            f"{exc}. The literature layer is present but broken, which is a "
            f"different fact from its being absent."
        ) from exc


__all__ = ["LiteratureLayerUnavailable", "literature_module", "tests_directory"]
