"""Constitution-rule guard for Terrium: Rules 7 and 8.

Both were stated as non-negotiable, both had ADRs behind them, and neither
was enforced by anything executable until this script.

Rule 8 -- every architecturally significant decision gets an ADR -- is
checked at the bottom of this file (`check_adrs_are_indexed`). It has failed
twice in this project's history, both times caught by hand: ADR 0009 existed
but was missing from the index, and ADR 0007 was written twice by two
different implementers.

Rule 7, made executable:

    Never `pip install tellurium` (the umbrella package). Use
    `libroadrunner`, `antimony`, `python-libsbml` directly. See ADR 0001.

Why this exists
---------------
Rule 7 is listed among the nine non-negotiable rules, has a dedicated ADR,
and `requirements.txt` carries a paragraph explaining it. None of that is
executable. Adding `tellurium==2.2.10` to `requirements.txt` passed every
guard in the repository, including `verify_build.py --quick`.

Rule 5 already establishes the principle for the sibling case: undeclared
dependencies are "a category of bug with a permanent automated guard, not a
one-time fix". A *forbidden* dependency is the same category, and was being
policed by prose.

The failure this prevents is not hypothetical. The umbrella package pulls in
`python-libcombine` and `python-libnuml`, which exist for COMBINE archives
and numerical markup -- neither of which Terrium uses. On any platform
without prebuilt wheels for them, the install dies at the cmake step. Someone
hitting an import error and "fixing" it with the obvious package name would
break installation for every contributor on an unlucky platform.

What is checked
---------------
Every dependency manifest, for any requirement whose distribution name is on
the forbidden list. Matching is on the normalised project name (PEP 503), so
`Tellurium`, `tellurium`, and `tellurium==2.2.10` are all caught, while
`tellurium_engine` (this project's own module) and the `Tellurium/` package
directory are not.

Usage:
    python scripts/check_forbidden_packages.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Distribution names that must never appear in a dependency manifest, with
# the reason and the replacement. The reason is printed on failure, because
# a bare "forbidden" invites someone to delete the check.
FORBIDDEN = {
    "tellurium": (
        "the umbrella package pulls in python-libcombine and python-libnuml "
        "(COMBINE archives / numerical markup), neither of which Terrium "
        "uses; on platforms without wheels for them the install dies at the "
        "cmake step",
        "libroadrunner, antimony, python-libsbml -- see ADR 0001",
    ),
}

# Files that declare dependencies. A manifest not listed here is not checked,
# so new ones must be added deliberately.
MANIFESTS = [
    REPO_ROOT / "requirements.txt",
    REPO_ROOT / "requirements-dev.txt",
    REPO_ROOT / "pyproject.toml",
]


def _normalise(name: str) -> str:
    """PEP 503 normalisation: case-insensitive, -_. all equivalent."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_names(path: Path) -> List[Tuple[int, str]]:
    """(line number, distribution name) for each requirement in a manifest.

    Two things this deliberately does NOT do:

    - **Match inside comments.** `requirements.txt` explains at length why
      tellurium must not be installed. A substring search would flag that
      explanation as a violation, punishing the file for documenting the
      rule it obeys.
    - **Scan all of pyproject.toml.** Only `[project] dependencies` and
      `[project.optional-dependencies]` declare packages. The first version
      of this function scanned the whole file and reported
      `"Tellurium/tests/*.py"` -- a ruff per-file-ignore key -- as a
      forbidden dependency. A guard that cries wolf gets deleted.
    """
    found: List[Tuple[int, str]] = []
    in_dependency_section = path.suffix != ".toml"  # .txt is all requirements

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()

        if path.suffix == ".toml":
            # Track whether we are inside a dependency array.
            if re.match(r"^\[", line):
                in_dependency_section = False
            if re.match(r"^(dependencies|.*-dependencies)\s*=", line):
                in_dependency_section = True
                continue
            if in_dependency_section and line.startswith("]"):
                in_dependency_section = False
                continue

        if not line or line.startswith("-") or not in_dependency_section:
            continue

        # pyproject dependency entries look like:  "numpy==1.26.4",
        candidate = line.strip().strip(",").strip('"').strip("'")

        # Strip everything after the first version specifier or marker.
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", candidate)
        if not match:
            continue
        found.append((lineno, match.group(1)))
    return found


def check_adrs_are_indexed() -> List[str]:
    """Rule 8: every architecturally significant decision gets an ADR.

    An ADR that exists but is absent from `docs/adr/README.md` is invisible
    to anyone reading the index -- present in the tree, missing from the
    record. That is not hypothetical: ADR 0009 was found unindexed during
    the Stage 5 audit, and a *duplicate* ADR 0007 was found in Stage 4 (two
    implementers each writing one). Both were caught by hand.

    Checks both directions. An index row pointing at a file that does not
    exist is the same defect wearing the other hat.
    """
    errors: List[str] = []
    adr_dir = REPO_ROOT / "docs" / "adr"
    index = adr_dir / "README.md"

    if not adr_dir.is_dir() or not index.exists():
        return ["docs/adr/README.md not found; cannot verify Rule 8"]

    on_disk = {
        p.name for p in adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")
    }
    index_text = index.read_text(encoding="utf-8")
    linked = set(re.findall(r"\(([0-9]{4}-[^)]+\.md)\)", index_text))

    for missing in sorted(on_disk - linked):
        errors.append(
            f"docs/adr/{missing} exists but is not linked from the ADR index "
            "-- invisible to anyone reading it (Rule 8)"
        )
    for dangling in sorted(linked - on_disk):
        errors.append(
            f"the ADR index links docs/adr/{dangling}, which does not exist"
        )

    # Duplicate numbers: two ADRs claiming 0007 happened once already.
    numbers: dict = {}
    for name in on_disk:
        numbers.setdefault(name[:4], []).append(name)
    for number, names in sorted(numbers.items()):
        if len(names) > 1:
            errors.append(
                f"ADR number {number} is claimed by {len(names)} files: "
                f"{sorted(names)}"
            )

    return errors


def main() -> int:
    violations: List[str] = []
    checked = 0

    for manifest in MANIFESTS:
        if not manifest.exists():
            continue
        checked += 1
        for lineno, name in _requirement_names(manifest):
            key = _normalise(name)
            if key in FORBIDDEN:
                reason, instead = FORBIDDEN[key]
                violations.append(
                    f"{manifest.name}:{lineno} declares '{name}'\n"
                    f"      why not: {reason}\n"
                    f"      use instead: {instead}"
                )

    if checked == 0:
        print("FAIL: no dependency manifests found; nothing was checked.")
        return 1

    print(f"Rule 7: checked {checked} dependency manifest(s).")

    if violations:
        print("\nFAIL: a forbidden package is declared")
        for violation in violations:
            print(f"  - {violation}")
        print(
            "\nThis is Rule 7 of docs/CONSTITUTION.md, and it is "
            "non-negotiable.\nIf the rule itself needs to change, that is an "
            "ADR superseding 0001,\nnot an edit to this list."
        )
        return 1

    adr_errors = check_adrs_are_indexed()
    adr_count = len(list((REPO_ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md")))
    print(f"Rule 8: checked {adr_count} ADR(s) against the index.")

    if adr_errors:
        print("\nFAIL: the ADR record is inconsistent")
        for error in adr_errors:
            print(f"  - {error}")
        print(
            "\nThis is Rule 8 of docs/CONSTITUTION.md. An ADR missing from "
            "the index\nis present in the tree and absent from the record -- "
            "which has happened\ntwice (ADR 0009 unindexed, ADR 0007 "
            "duplicated)."
        )
        return 1

    print("OK: no forbidden packages, and every ADR is indexed exactly once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
