"""Tell a packaging problem apart from a missing dependency.

THE BUG THIS EXISTS TO KILL
---------------------------
Caterva is importable two ways: as a package (`from caterva.core.utils import
...`, repo root on sys.path) and flat (`from core.utils import ...`,
`caterva/` on sys.path). Twenty-two modules support both with the same
shape:

    try:
        from caterva.core.utils import _fmt
    except ModuleNotFoundError:
        from core.utils import _fmt

That is correct for the case it was written for and silently wrong for a
much more common one.

`caterva/core/utils.py` imports `roadrunner`. With roadrunner not installed,
the FIRST import fails with `ModuleNotFoundError: No module named
'roadrunner'` -- the true and actionable error. The `except` catches it,
retries flat mode, and that fails with:

    ModuleNotFoundError: No module named 'core'

So a missing third-party dependency is reported as a missing INTERNAL
module. Someone reading that goes looking for a packaging bug in `caterva/`,
which is not where the problem is and not something they can fix. The real
cause is two frames up in a chained traceback almost nobody scrolls to.

Same family as the runner-boundary bug this project already fixed once:
an error path that discards the reason and substitutes its own. There it
was an exit code replacing `403 Forbidden`; here it is a fallback replacing
`No module named 'roadrunner'`.

THE RULE
--------
A flat-mode retry is only ever the right response to the PACKAGE PATH being
unavailable. If the missing module is anything else, the retry cannot help
and re-raising preserves the answer.

`ModuleNotFoundError.name` carries exactly what is needed, so the test is
precise rather than a guess at the message text.

    from caterva.core.import_mode import package_path_missing

    try:
        from caterva.core.utils import _fmt
    except ModuleNotFoundError as exc:
        if not package_path_missing(exc):
            raise
        from core.utils import _fmt
"""
from __future__ import annotations

#: The package root. A failure to import anything under this name means the
#: repo root is not on sys.path, which is what flat mode is for.
PACKAGE_ROOT = "caterva"


def package_path_missing(exc: ModuleNotFoundError) -> bool:
    """True when `exc` says the Caterva PACKAGE path is unavailable.

    False for a missing third-party dependency, which flat mode cannot fix
    and must not be allowed to disguise.

    `exc.name` is None on some exotic import failures; treated as "not the
    package path", because re-raising an unclassifiable import error shows
    the real traceback while retrying would bury it.
    """
    name = getattr(exc, "name", None)
    if not name:
        return False
    return name == PACKAGE_ROOT or name.startswith(f"{PACKAGE_ROOT}.")
