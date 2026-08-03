"""Forbidden-package guard for Terrium.

Rule 7 of the constitution, made executable:

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

    print(f"Checked {checked} dependency manifest(s) for forbidden packages.")

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

    print("OK: no forbidden packages declared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
