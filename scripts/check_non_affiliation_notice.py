#!/usr/bin/env python3
"""The Tellurium non-affiliation notice must reach every surface that ships.

WHY THIS EXISTS
---------------
Terrium and Tellurium differ by two letters, work in the same field, and
target the same people. Terrium *runs on* the Sauro lab's libRoadRunner and
generates their Antimony. That is a permitted and ordinary use (see
`docs/LICENSING.md`), but the name makes it look like something else, and
once it actually did: Matthias König read a cold outreach email as a false
claim of credit for Tellurium's work.

Before this guard, the disclaimer lived in exactly two files -- `README.md`
and `NOTICE` -- both of which stay in the repository. Someone who runs
`pip install terrium`, or reads the citation metadata, or copies a BibTeX
entry off the landing page, never sees either.

That is the same failure the BRENDA attribution had until 2026-08-13: a
real obligation, correctly understood, present nowhere a downstream user
would encounter it. The fix then was to make it mechanically checkable.
This is that fix, for the naming problem.

WHAT THIS CHECKS
----------------
Each surface in `SURFACES` still carries the notice. A surface is a file
that travels with the software or is read by someone deciding what to
credit:

  * `NOTICE` and `README.md` -- the repository
  * `CITATION.cff` -- what a citation manager ingests
  * `pyproject.toml` and `package.json` -- what PyPI and npm display
  * `Terium/__init__.py` -- what `help(Terium)` prints, which travels with
    the installed package while a README does not
  * the landing page's "How to cite" section -- where someone actually
    decides whose name goes in the paper

WHY IT CANNOT QUIETLY PASS
--------------------------
A surface listed here but missing from disk is a FAILURE, not a skip. The
easiest way to defeat a checklist is to delete the thing being checked, and
a guard that shrugs at a missing file rewards exactly that.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Below this the list has been gutted rather than the notice being fine.
_MIN_SURFACES = 6

#: file -> (human name, regexes that must ALL match, case-insensitive)
#:
#: Matched on meaning rather than an exact sentence, so the wording can be
#: adapted to each surface -- a BibTeX panel and a package docstring should
#: not read identically -- while the two load-bearing claims survive:
#: that Terrium is not Tellurium, and that it is unaffiliated.
SURFACES: dict[str, tuple[str, tuple[str, ...]]] = {
    "NOTICE": (
        "the file Apache 2.0 4(d) makes travel with redistribution",
        (r"not\s+tellurium", r"unaffiliated"),
    ),
    "README.md": (
        "the repository front page",
        (r"not\s+tellurium", r"unaffiliated"),
    ),
    "CITATION.cff": (
        "citation metadata, ingested by reference managers",
        (r"not\s+tellurium", r"unaffiliated"),
    ),
    "pyproject.toml": (
        "what PyPI displays under the package name",
        (r"unaffiliated with tellurium",),
    ),
    "package.json": (
        "what npm displays under the package name",
        (r"unaffiliated with tellurium",),
    ),
    "Terium/__init__.py": (
        "the package docstring -- travels with the installed software",
        (r"not\s+tellurium", r"unaffiliated"),
    ),
    "Science-Agent-Pipeline/artifacts/terrium-landing/src/cli/HowToCiteSection.tsx": (
        "the landing page, where a reader decides whom to credit",
        (r"not\s+tellurium", r"unaffiliated"),
    ),
}

#: Surfaces where the notice should also name what Terrium actually builds
#: on. Saying "we are not them" without saying "we run on their software"
#: is a denial rather than an attribution, and the attribution is the part
#: the licences ask for.
MUST_CREDIT: tuple[str, ...] = (
    "NOTICE",
    "README.md",
    "CITATION.cff",
    "Terium/__init__.py",
    "Science-Agent-Pipeline/artifacts/terrium-landing/src/cli/HowToCiteSection.tsx",
)

_CREDIT_RE = re.compile(r"libroadrunner", re.I)


def check() -> list[str]:
    """Problems found, one per line. Empty means every surface carries it."""
    problems: list[str] = []
    for rel, (what, patterns) in SURFACES.items():
        path = ROOT / rel
        if not path.exists():
            problems.append(
                f"{rel} is listed as a surface but does not exist ({what}). "
                "If it moved, update SURFACES; do not let the check quietly "
                "cover one file fewer."
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            if not re.search(pattern, text, re.I):
                problems.append(
                    f"{rel} no longer says it ({what}): nothing matches "
                    f"/{pattern}/."
                )
        if rel in MUST_CREDIT and not _CREDIT_RE.search(text):
            problems.append(
                f"{rel} disclaims the association but does not credit "
                "libRoadRunner. A denial without an attribution is not what "
                "the licences ask for."
            )
    return problems


def main() -> int:
    if len(SURFACES) < _MIN_SURFACES:
        print(
            f"FAIL: SURFACES lists only {len(SURFACES)} file(s), below the "
            f"floor of {_MIN_SURFACES}.\n"
            "      The list has been gutted. Deleting the checklist is the "
            "easiest way to pass a check."
        )
        return 1

    problems = check()
    print(f"Surfaces checked:        {len(SURFACES)}")
    print(f"Carrying the notice:     {len(SURFACES) - len({p.split()[0] for p in problems})}")
    print(f"Problems:                {len(problems)}")

    if problems:
        print("\nThe Tellurium notice has gone missing:\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nThis is not decoration. Terrium and Tellurium differ by two "
            "letters, in the same\nfield, and one researcher has already read "
            "a Terrium email as a claim on\nTellurium's work. See "
            "docs/RENAME_PLAN.md."
        )
        return 1

    print("\nOK: every shipping surface carries the non-affiliation notice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
