"""Import the literature layer, which lives outside the package.

WHY THIS EXISTS
---------------
The resolvers that read BRENDA, rank rows by how well evidenced they are
and carry the disagreement between papers -- `fallback_logic`,
`parameterize`, `model_compatibility`, `assay_conditions` -- live in
`Tests/` at the repository root, as flat modules. `MANIFEST.in` prunes
`Tests/` from the wheel (its fixtures are BRENDA data under their own
licence, ADR 0177), so the release build copies exactly the modules the
resolvers import, and none of the fixtures, into `caterva/_literature/`
(`scripts/vendor_literature.py`, run by `scripts/build_release.py`). That
directory is generated, git-ignored, and present in the wheel and the app
folder.

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

WHERE IT LOOKS, IN ORDER
------------------------
1. `Tests/` beside the package's parent: the repository layout, so a
   developer's checkout behaves exactly as before.
2. `caterva/_literature/` inside the installed package: the wheel and the
   frozen app.

WHAT IT REFUSES TO DO
---------------------
Guess. When neither directory exists (a wheel built without the vendoring
step), `LiteratureLayerUnavailable` names that rather than letting an
`ImportError` surface three frames away as though the code were broken.
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

#: The literature modules as the release build vendors them into the package.
_VENDORED_DIR = _PACKAGE_DIR / "_literature"


class LiteratureLayerUnavailable(ImportError):
    """The literature resolvers are not reachable from this installation."""


def tests_directory() -> Path | None:
    """The checkout's `Tests/`, or None when running from an installed copy."""
    return _TESTS_DIR if _TESTS_DIR.is_dir() else None


def vendored_directory() -> Path | None:
    """The package's own copy of the literature modules, or None when absent."""
    return _VENDORED_DIR if _VENDORED_DIR.is_dir() else None


def literature_directory() -> Path | None:
    """Where the literature modules are: the checkout's `Tests/`, else the package's copy."""
    return tests_directory() or vendored_directory()


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

    found = literature_directory()
    if found is None:
        raise LiteratureLayerUnavailable(
            f"{name!r} is part of Caterva's literature layer, which is in "
            f"neither the repository's Tests/ directory ({_TESTS_DIR}) nor "
            f"the package's caterva/_literature/ ({_VENDORED_DIR}). A release "
            f"build puts it in the second (scripts/vendor_literature.py); "
            f"this installation was built without it, so no literature "
            f"search is possible from here."
        )

    if str(found) not in sys.path:
        # Appended, not inserted: a flat directory of modules with names as
        # general as `parameterize` must never shadow a real package.
        sys.path.append(str(found))
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise LiteratureLayerUnavailable(
            f"{name!r} was not importable even with {found} on sys.path: "
            f"{exc}. The literature layer is present but broken, which is a "
            f"different fact from its being absent."
        ) from exc


__all__ = [
    "LiteratureLayerUnavailable",
    "literature_directory",
    "literature_module",
    "tests_directory",
    "vendored_directory",
]
