"""Constitution-rule guard for Caterva: Rules 7 and 8.

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
and numerical markup -- neither of which Caterva uses. On any platform
without prebuilt wheels for them, the install dies at the cmake step. Someone
hitting an import error and "fixing" it with the obvious package name would
break installation for every contributor on an unlucky platform.

What is checked
---------------
Every dependency manifest, for any requirement whose distribution name is on
the forbidden list. Matching is on the normalised project name (PEP 503), so
`Tellurium`, `tellurium`, and `tellurium==2.2.10` are all caught, while
`caterva_engine` (this project's own module, renamed from the upstream-
echoing `tellurium_engine`) and the `caterva/` package directory are not.
That distinction is now load-bearing: the 2026-08-11 rename briefly
rewrote this entry to `caterva`, which forbade this project's OWN name
and permitted the upstream package the guard exists to block.

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
        ("the umbrella package pulls in python-libcombine and python-libnuml "
         "(COMBINE archives / numerical markup), neither of which Caterva "
         "uses; on platforms without wheels for them the install dies at the "
         "cmake step"),
        "libroadrunner, antimony, python-libsbml -- see ADR 0001",
    ),
}

# Files that declare dependencies. A manifest not listed here is not checked,
# so new ones must be added deliberately.
#
# "Added deliberately" was the intent and "not checked" was the effect. The
# list was three files; nothing verified it was still the complete set, so a
# new `requirements-*.txt` would have been silently unscanned from the moment
# it was created. `_unlisted_manifests()` below closes that, and it fired on
# its first run against `requirements-popgen.txt`, added the same day.
MANIFESTS = [
    REPO_ROOT / "requirements.txt",
    REPO_ROOT / "requirements-dev.txt",
    REPO_ROOT / "requirements-popgen.txt",
    REPO_ROOT / "requirements-release.txt",
    REPO_ROOT / "pyproject.toml",
]

# Dockerfiles install packages too, and none of them is a manifest.
#
# `RUN pip install tellurium` in a Dockerfile would have installed the
# forbidden package into every image built from it while this guard reported
# green, because the guard only ever read three .txt/.toml files. The rule is
# "never install this package"; policing only the files that DECLARE
# dependencies leaves the files that INSTALL them unpoliced.
INSTALL_SCRIPTS = [
    REPO_ROOT / "Dockerfile",
    REPO_ROOT / ".devcontainer" / "Dockerfile",
]

#: `pip install foo`, `pip3 install --no-cache-dir foo bar`, `uv pip install foo`.
#: Flags are skipped; `-r file.txt` is ignored because the file it names is a
#: manifest and is checked as one.
_PIP_INSTALL = re.compile(r"\bpip3?\s+install\b(?P<rest>[^\n&|;]*)")


def _packages_installed_by(text: str) -> List[Tuple[int, str]]:
    """`(line number, distribution name)` for each package a script installs."""
    found: List[Tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for match in _PIP_INSTALL.finditer(line):
            skip_next = False
            for token in match.group("rest").split():
                if skip_next:
                    skip_next = False
                    continue
                if token in {"-r", "--requirement", "-c", "--constraint"}:
                    skip_next = True
                    continue
                if token.startswith("-"):
                    continue
                if token in {"\\", "&&", "|"}:
                    continue
                # Strip a version specifier: `tellurium==2.2.10` -> `tellurium`
                name = re.split(r"[<>=!~\[;]", token, maxsplit=1)[0].strip()
                if name:
                    found.append((lineno, name))
    return found


def _unlisted_manifests() -> List[str]:
    """Dependency manifests on disk that MANIFESTS does not name.

    Without this the explicit list fails open: a manifest that exists and is
    not listed is simply unscanned, and looks identical to one that was
    checked and passed. That is the defect shape this project has hit
    repeatedly -- a correct check on too narrow a scope.
    """
    listed = {path.resolve() for path in MANIFESTS}
    unlisted: List[str] = []
    for path in sorted(REPO_ROOT.glob("requirements*.txt")):
        if path.resolve() not in listed:
            unlisted.append(str(path.relative_to(REPO_ROOT)))
    return unlisted


def _normalise(name: str) -> str:
    """PEP 503 normalisation: case-insensitive, -_. all equivalent."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _strip_toml_comment(line: str) -> str:
    """Remove a TOML comment without touching # characters in strings."""
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if quote:
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "#":
            return line[:index]
    return line


def _toml_string_values(line: str) -> List[str]:
    """Extract basic or literal TOML strings from one array line."""
    return [
        match.group(1) if match.group(1) is not None else match.group(2)
        for match in re.finditer(r'"((?:\\.|[^"\\])*)"|\'([^\']*)\'', line)
    ]


def _array_has_terminator(line: str) -> bool:
    """Return whether an array-closing bracket appears outside a TOML string."""
    quote: str | None = None
    escaped = False
    for char in line:
        if quote:
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "]":
            return True
    return False


def _requirement_names(path: Path) -> List[Tuple[int, str]]:
    """(line number, distribution name) for each requirement in a manifest.

    Two things this deliberately does NOT do:

    - **Match inside comments.** `requirements.txt` explains at length why
      caterva must not be installed. A substring search would flag that
      explanation as a violation, punishing the file for documenting the
      rule it obeys.
    - **Scan all of pyproject.toml.** Only `[project] dependencies` and
      `[project.optional-dependencies]` declare packages. The first version
      of this function scanned the whole file and reported
      `"caterva/tests/*.py"` -- a ruff per-file-ignore key -- as a
      forbidden dependency. A guard that cries wolf gets deleted.
    """
    found: List[Tuple[int, str]] = []
    in_dependency_section = path.suffix != ".toml"  # .txt is all requirements
    in_dependency_array = False
    dependency_key_allowed = True

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = _strip_toml_comment(raw).strip()

        if path.suffix == ".toml":
            # Dependencies can live in either [project].dependencies or an
            # arbitrary key under [project.optional-dependencies] (usually
            # `dev`, `test`, or `docs`). Track the section and then each TOML
            # array, rather than assuming the key itself ends in
            # "-dependencies".
            section = re.match(r"^\[([^]]+)\]$", line)
            if section:
                section_name = section.group(1).strip()
                in_dependency_section = section_name in {
                    "project",
                    "project.optional-dependencies",
                }
                # In [project], only the dependencies key is a package list;
                # fields such as authors and classifiers are arrays too, but
                # they are not dependency declarations. Optional dependency
                # groups may use any key (including a quoted TOML key).
                dependency_key_allowed = (
                    section_name == "project.optional-dependencies"
                )
                in_dependency_array = False
                continue

            if not in_dependency_section:
                continue

            if not in_dependency_array:
                array_start = re.match(
                    r"^(?P<key>[A-Za-z0-9][A-Za-z0-9._-]*|\"[^\"]+\"|'[^']+')\s*=\s*\[",
                    line,
                )
                if not array_start:
                    continue
                key = array_start.group("key").strip('"').strip("'")
                if not dependency_key_allowed and key != "dependencies":
                    continue
                in_dependency_array = True
                line = line[array_start.end():].strip()

            # A closing bracket may share a line with the final dependency.
            if line.startswith("]"):
                in_dependency_array = False
                continue

            # TOML dependency arrays contain quoted requirement strings.
            for candidate in _toml_string_values(line):
                match = re.match(
                    r"^([A-Za-z0-9][A-Za-z0-9._-]*)", candidate
                )
                if match:
                    found.append((lineno, match.group(1)))
            if _array_has_terminator(line):
                in_dependency_array = False
            continue

        if not line or line.startswith("-"):
            continue

        # requirements.txt entries are one requirement per line. Strip
        # everything after the first version specifier or marker.
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if match:
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

    errors.extend(
        f"docs/adr/{missing} exists but is not linked from the ADR index "
        "-- invisible to anyone reading it (Rule 8)"
        for missing in sorted(on_disk - linked)
    )
    errors.extend(
        f"the ADR index links docs/adr/{dangling}, which does not exist"
        for dangling in sorted(linked - on_disk)
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


#: An INSTRUCTION to install a forbidden package: `pip install tellurium`.
#:
#: Rule 7 was policed by prose, and this guard was written to make it
#: executable -- but only for dependency manifests. The 2026-08-11 rename
#: surfaced what that left uncovered: SIX documents told the reader to run
#: `pip install tellurium libroadrunner` in a copy-pasteable code fence.
#:
#: A manifest is what CI installs; a setup guide is what a HUMAN installs
#: from, and it is the more likely route by which the umbrella package
#: actually lands on someone's machine. The guard was checking the path
#: nobody was taking.
#:
#: Matched only in an imperative form (`pip install <pkg>`), so prose that
#: NAMES the package to forbid it -- "Never `pip install tellurium`" in the
#: constitution, ADR 0001's title, this docstring -- is not itself a
#: violation. That distinction is the same one check_example_endpoints
#: needed: a document warning against a thing must not be punished for
#: naming it.
INSTALL_INSTRUCTION = re.compile(
    r"(?<!`)\bpip3?\s+install\s+(?!.*#)([A-Za-z0-9._-][^\n`]*)"
)

#: Wording that turns a mention into a prohibition rather than an
#: instruction. Checked on the same line.
PROHIBITION = re.compile(
    r"\b(never|not|do not|don't|forbidden|banned|avoid|instead of)\b", re.I
)

DOC_GLOBS = ("*.md", "docs/**/*.md")


def _check_docs_do_not_instruct() -> Tuple[List[str], int]:
    """Documents must not tell a reader to install a forbidden package."""
    violations: List[str] = []
    seen: set[Path] = set()

    for pattern in DOC_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file() or path in seen:
                continue
            # Historical records describe what was true on a date; rewriting
            # them to satisfy a rule destroys their value.
            if "build-stages" in path.parts:
                continue
            seen.add(path)

            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                match = INSTALL_INSTRUCTION.search(line)
                if not match or PROHIBITION.search(line):
                    continue
                for token in match.group(1).split():
                    if _normalise(token.strip("`'\",")) in FORBIDDEN:
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{lineno} tells the "
                            f"reader to run `pip install {token}`\n"
                            f"      A setup guide is what a human installs "
                            f"from, so this is the likelier route by which "
                            f"the package reaches a machine than any manifest."
                        )
                        break

    return violations, len(seen)


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

    # Files that INSTALL packages, not just files that declare them.
    scripts_checked = 0
    for script in INSTALL_SCRIPTS:
        if not script.exists():
            continue
        scripts_checked += 1
        text = script.read_text(encoding="utf-8")
        for lineno, name in _packages_installed_by(text):
            key = _normalise(name)
            if key in FORBIDDEN:
                reason, instead = FORBIDDEN[key]
                violations.append(
                    f"{script.relative_to(REPO_ROOT)}:{lineno} installs '{name}'\n"
                    f"      why not: {reason}\n"
                    f"      use instead: {instead}"
                )

    # A manifest that exists and is not listed is unscanned, and an unscanned
    # manifest looks exactly like a clean one.
    for unlisted in _unlisted_manifests():
        violations.append(
            f"{unlisted} is a dependency manifest that MANIFESTS does not name, "
            "so nothing checked it.\n"
            "      Add it to MANIFESTS in this script. The explicit list is "
            "deliberate -- but\n"
            "      an omission from it must fail loudly rather than silently "
            "skip a file."
        )

    doc_violations, docs_checked = _check_docs_do_not_instruct()
    violations.extend(doc_violations)

    print(
        f"Rule 7: checked {checked} dependency manifest(s), "
        f"{scripts_checked} install script(s) and {docs_checked} document(s)."
    )

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
