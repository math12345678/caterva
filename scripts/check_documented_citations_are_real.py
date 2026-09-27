#!/usr/bin/env python3
"""A citation in the documentation must be a citation that exists.

WHY THIS EXISTS
---------------
Caterva's entire claim is that every number carries a real reference. Its
README demonstrated that claim with three citations, and all three were
wrong:

    Citation  BRENDA ref 649716      <- an ACETYLCHOLINESTERASE reference,
                                        printed under a lactate
                                        dehydrogenase example
    km   0.14 mM   BRENDA ref 12345  <- not a reference at all. A placeholder
                                        that appears in no fixture, no
                                        corpus, and nowhere in BRENDA
    vmax 0.25 mM/s BRENDA ref 649716 <- the AChE reference again

The front page of a provenance tool, inventing provenance.

This is not a cosmetic defect. Matthias König read a Caterva outreach email
as a false claim of credit and replied that it "is not a good idea to let AI
just create lies about your own achievements" (ADR 0100, docs/RENAME_PLAN.md).
A reader who checks `ref 12345` and finds nothing has that suspicion
confirmed by the project's own README, and there is no recovering from it
with a better argument.

WHAT THIS CHECKS
----------------
Every `BRENDA ref NNNNNN` appearing in the documented surfaces below must be
a reference id that occurs in a committed fixture. The fixtures are real
BRENDA pages, so "in a fixture" means "a real reference a reader could look
up" -- and, unlike a live query, it is checkable offline and in CI.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
That the reference belongs to the enzyme in the example. Deciding that would
mean parsing which fixture the surrounding prose is about, and a check that
guesses is a check that cries wolf. `649716` was a real id in the wrong
place, and this guard would not have caught it -- only the human question
"is that an LDH reference?" did.

So this closes the flagrant case (a number nobody could ever verify) and is
honest that the subtle one still needs a reader. Documented rather than
quietly hoped over, because a guard whose limits are unstated gets trusted
past them.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Where a reader meets an example citation, named explicitly.
_NAMED_SURFACES = (
    "README.md",
    "docs/DESIGN.md",
    "CONTRIBUTING.md",
)

#: The front page of every PUBLISHED repository, DISCOVERED rather than listed.
#:
#: The first version of this guard enumerated three files and missed the two
#: that matter most. `docs/readmes/main.md` and `docs/readmes/backend-main.md`
#: are the READMEs of published repositories — the page a stranger lands on —
#: and both still carried `BRENDA ref 12345`, the invented citation this guard
#: was written to remove, for a full day after it was written.
#:
#: A hand-written list covers what its author remembered. `check_published_
#: repo_readmes.py` already treats this directory as the set of shipping front
#: pages; discovering it the same way means the eighteenth published README is
#: covered on the day it is added, by nobody.
_README_DIR = "docs/readmes"


def surfaces() -> tuple[str, ...]:
    """Named surfaces plus every published README, in a stable order."""
    discovered = sorted(
        f"{_README_DIR}/{path.name}"
        for path in (REPO_ROOT / _README_DIR).glob("*.md")
    )
    return _NAMED_SURFACES + tuple(discovered)


#: Below this, the surface list has been gutted rather than the problem fixed.
#: Raised from 3 once the published READMEs were discovered rather than listed:
#: a floor that only counts the hand-written names would not notice the whole
#: discovered set disappearing.
_MIN_SURFACES = 10

FIXTURE_DIR = REPO_ROOT / "Tests" / "fixtures"

#: `BRENDA ref 740253`, `BRENDA reference 740253`, `ref 740253`.
CITATION_RE = re.compile(r"\bBRENDA\s+ref(?:erence)?\s+(\d{3,})\b", re.IGNORECASE)


def known_reference_ids() -> set[str]:
    """Every reference id occurring in a committed BRENDA fixture."""
    found: set[str] = set()
    for path in sorted(FIXTURE_DIR.glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        found.update(re.findall(r"\b(\d{6,})\b", text))
    return found


def check() -> list[str]:
    problems: list[str] = []
    known = known_reference_ids()

    if not known:
        # An empty corpus would make every citation "unknown" and the check
        # would fail loudly rather than passing vacuously -- but say why,
        # because the cause is the fixtures, not the README.
        return [
            f"No reference ids found in {FIXTURE_DIR}. The fixtures are the "
            "only offline evidence of what a real reference looks like; "
            "without them this check cannot mean anything."
        ]

    for rel in surfaces():
        path = REPO_ROOT / rel
        if not path.exists():
            problems.append(
                f"{rel} is listed as a surface but does not exist. If it "
                "moved, update SURFACES; do not let the check quietly cover "
                "one file fewer."
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in CITATION_RE.finditer(text):
            ref = match.group(1)
            if ref not in known:
                line = text[: match.start()].count("\n") + 1
                problems.append(
                    f"{rel}:{line} cites BRENDA ref {ref}, which appears in "
                    "no committed fixture. If it is real, add the fixture "
                    "that proves it; if it is a placeholder, it is an "
                    "invented citation on a page that promises real ones."
                )
    return problems


def main() -> int:
    active = surfaces()
    if len(active) < _MIN_SURFACES:
        print(
            f"FAIL: only {len(active)} surface(s) resolved, below the "
            f"floor of {_MIN_SURFACES}. Deleting the checklist is the "
            "easiest way to pass a check."
        )
        return 1

    problems = check()
    known = known_reference_ids()
    print(f"Reference ids in fixtures: {len(known)}")
    print(f"Surfaces checked:          {len(active)}")
    print(f"Problems:                  {len(problems)}")

    if problems:
        print("\nInvented citations:\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nCaterva's whole claim is that every number carries a real "
            "reference.\nA reader who checks one of these and finds nothing "
            "has learned something\nabout the project that no later argument "
            "will undo."
        )
        return 1

    print("\nOK: every documented BRENDA reference exists in a fixture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
