#!/usr/bin/env python3
"""A path in a contributor-facing document must point at a real file.

THE DEFECT THIS COMES FROM
--------------------------
While editing CONTRIBUTING.md to fix a *different* broken reference, the
editor wrote:

    (in `Tests/test_brenda_flags.py`)

There is no such file. The test named in that sentence lives in
`Terium/tests/test_brenda_integration.py`. The wrong path was plausible --
right shape, right naming convention, right directory for a literature
test -- which is exactly why nobody would have questioned it, and why the
mistake survived being typed by someone who was at that moment fixing
broken paths.

`check_commands_runnable.py` did not catch it. That guard checks every
`scripts/<name>.py` a document names, because its own origin was a guard
printing an unrunnable command. A test module under `Terium/tests/` is
outside its scope.

So the repository had a rule about one directory and no rule about the
rest, and a new contributor sent to a file that does not exist has no way
to tell whether they are lost or the document is wrong. They assume they
are lost. That is the cost this exists to prevent.

WHAT THIS CHECKS
----------------
In each document under `DOCS`, every backticked token that looks like a
repo-relative path *with a directory component* -- `Tests/foo.py`,
`docs/adr/0012-x.md` -- must exist.

**Bare filenames are deliberately not checked.** These documents refer to
`terium_engine.py` and `brenda_client.py` conversationally, the way you
would in a sentence, and demanding a full path there would either fail
constantly or push people to stop naming files at all. A token with a
slash in it is a claim about where something lives; a bare name is a claim
about what it is called. Only the first is checkable, so only the first is
checked.

WHY IT CANNOT QUIETLY PASS
--------------------------
If the extraction finds nothing it FAILS. A regex that stops matching
otherwise reports a clean bill of health for a scan that never happened,
and the two defects this guard was written against were both found by
looking -- not by trusting a green tick.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The documents a newcomer is actually pointed at. Not every markdown file
#: in the repository: 81 sit at the root, most of them archived session
#: reports (see docs/ARCHIVE_TRIAGE.md), and holding a superseded 2026
#: status report to this standard would bury the two live defects in
#: hundreds of stale ones. These are the ones that must be right.
DOCS: tuple[str, ...] = (
    "README.md",
    "CONTRIBUTING.md",
    "DOCUMENTATION_INDEX.md",
    "START_HERE.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "docs/REPO_MAP.md",
    "docs/INTERN_ONBOARDING.md",
    "docs/CONSTITUTION.md",
    "docs/API.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)

#: Below this, the extraction is broken rather than the docs being clean.
#: The real count is in the forties across these files.
_MIN_REFS = 20

#: A backticked token containing a directory separator and a file suffix.
_PATH_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*/[A-Za-z0-9_./-]+\.[a-zA-Z]{2,4})`")

#: Paths that name something deliberately absent. Each needs a reason.
KNOWN_ABSENT: dict[str, str] = {}


def _tracked() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return set(out.stdout.split())


def extract(text: str) -> set[str]:
    """Backticked repo-relative paths that carry a directory component."""
    return set(_PATH_RE.findall(text))


def unresolved(doc: str, text: str, tracked: set[str]) -> list[str]:
    """Paths named in `doc` that point at nothing. Order is stable."""
    bad = []
    for ref in sorted(extract(text)):
        if ref in KNOWN_ABSENT:
            continue
        if ref in tracked or (ROOT / ref).exists():
            continue
        bad.append(ref)
    return bad


def main() -> int:
    tracked = _tracked()
    total = 0
    problems: list[tuple[str, str]] = []
    missing_docs: list[str] = []

    for doc in DOCS:
        path = ROOT / doc
        if not path.exists():
            missing_docs.append(doc)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total += len(extract(text))
        for ref in unresolved(doc, text, tracked):
            problems.append((doc, ref))

    if missing_docs:
        print("FAIL: a document this guard is supposed to check is gone:")
        for doc in missing_docs:
            print(f"  {doc}")
        print(
            "\nIf it was renamed or archived, update DOCS in this script. A "
            "guard\nquietly checking nine files when it names ten is how "
            "coverage disappears."
        )
        return 1

    if total < _MIN_REFS:
        print(
            f"FAIL: extracted only {total} path reference(s) across "
            f"{len(DOCS)} documents, below the floor of {_MIN_REFS}.\n"
            "      The extraction is broken, not the documentation. A scan "
            "that finds nothing must not report success."
        )
        return 1

    print(f"Documents checked:       {len(DOCS)}")
    print(f"Path references found:   {total}")
    print(f"Pointing at nothing:     {len(problems)}")

    if problems:
        print("\nThese paths do not exist:\n")
        for doc, ref in problems:
            print(f"  {doc}: {ref}")
        print(
            "\nA newcomer sent to a file that is not there assumes they are "
            "lost, not that\nthe document is wrong. Correct the path, or add "
            "it to KNOWN_ABSENT with the\nreason it names something that "
            "deliberately does not exist."
        )
        return 1

    print("\nOK: every path named in the contributor-facing docs resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
