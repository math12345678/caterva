"""Guard that every source file is reachable from something that runs.

THE PROBLEM THIS EXISTS FOR

On 2026-08-11 a single commit added 77 files and 10,448 lines. Among them:

    src/integrations/brenda-real.ts          234 lines   0 importers
    src/integrations/real-literature-service  329 lines   0 importers
    src/engine/kinetic-models.ts             217 lines   0 importers
    src/engine/tellurium-real.py             254 lines   0 importers
    src/execution/job-manager.ts             369 lines   0 importers
    src/analysis/advanced-analytics.ts       362 lines   0 importers
    src/cli/advanced-features.ts             244 lines   0 importers

2,009 lines that nothing imports, alongside thirteen new markdown files
with names like IMPLEMENTATION_COMPLETE.md and PHASE_4_COMPLETE.md.

Every guard passed. `tsc` compiled them — they are inside the tsconfig's
`include`, so they type-check perfectly. The tests passed, because nothing
imports them so nothing can break. The build was green and the commit
looked like a large delivery.

This is the failure mode that matters most in a repository several AI
agents write to concurrently: **adding is rewarded and nothing punishes
never being called.** The result is four parallel implementations of
Michaelis-Menten and three of BRENDA lookup, and no way for a reader to
tell which one the product actually uses. Duplicate sources of truth are
how this codebase got a `verifyDOI` that returned true for anything, a
reproducibility verifier that could not fail, and a kcat labelled "mM" --
each lived in a copy nobody was watching.

An orphan module is not merely wasted space. It is a second answer to a
question that already had one.

WHAT COUNTS AS REACHABLE

A file is reachable if something else imports it, or if it is an entry
point: declared in package.json (`main`, `bin`, `scripts`), a test, a type
declaration, or a build/tool config. Entry points are listed explicitly
rather than guessed, because a heuristic that exempts "anything that looks
like an entry point" is how an orphan sneaks back in.

Run directly: python scripts/check_no_orphan_modules.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Trees whose modules must be reachable. Deliberately the first-party
#: application code, not vendored or generated output.
SEARCH_ROOTS = ["src", "examples"]

SKIP_PARTS = {
    "node_modules",
    "dist",
    ".next",
    "out-tsc",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    "coverage",
}

#: Files that are entry points by nature: nothing imports them, and that is
#: correct. Kept short and explicit.
ENTRY_POINT_PATTERNS = (
    re.compile(r".*\.d\.ts$"),          # type declarations
    re.compile(r".*\.config\.(ts|js)$"),  # tool configs, loaded by the tool
    re.compile(r".*/__tests__/.*"),      # tests are run, not imported
    re.compile(r".*\.test\.(ts|tsx)$"),
    re.compile(r".*\.spec\.(ts|tsx)$"),
    re.compile(r".*/test_[^/]+\.py$"),
)


def _iter_source_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root_name in SEARCH_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for current, directories, names in os.walk(root):
            directories[:] = [d for d in directories if d not in SKIP_PARTS]
            here = pathlib.Path(current)
            for name in names:
                if name.endswith((".ts", ".tsx", ".py")):
                    files.append(here / name)
    return sorted(files)


def _declared_entry_points() -> set[str]:
    """Module basenames referenced by package.json's main/bin/scripts."""
    declared: set[str] = set()
    package_json = REPO_ROOT / "package.json"
    if not package_json.is_file():
        return declared

    try:
        package = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # An unreadable package.json must not silently exempt nothing AND
        # must not silently exempt everything. Returning empty means the
        # guard is stricter, and a real entry point would be reported --
        # visibly, rather than an orphan slipping through.
        return declared

    blobs: list[str] = []
    for key in ("main", "module", "types"):
        value = package.get(key)
        if isinstance(value, str):
            blobs.append(value)
    for key in ("bin", "scripts"):
        value = package.get(key)
        if isinstance(value, dict):
            blobs.extend(str(v) for v in value.values())
        elif isinstance(value, str):
            blobs.append(value)

    for blob in blobs:
        for match in re.finditer(r"[\w./-]+\.(?:ts|tsx|js|py)", blob):
            declared.add(pathlib.Path(match.group(0)).stem)
    return declared


def _is_entry_point(path: pathlib.Path, declared: set[str]) -> bool:
    relative = path.relative_to(REPO_ROOT).as_posix()
    if any(pattern.match(relative) for pattern in ENTRY_POINT_PATTERNS):
        return True
    return path.stem in declared


def check() -> list[str]:
    """Returns a list of violation strings, empty when nothing is orphaned."""
    sources = _iter_source_files()
    if not sources:
        return [
            f"No source files found under {', '.join(SEARCH_ROOTS)}. Refusing "
            "to report success -- an empty scan is not a clean tree."
        ]

    declared = _declared_entry_points()

    # Read every file once, then ask which stems appear in others. A stem
    # match rather than full import parsing: TypeScript imports drop the
    # extension, Python uses dots, and both may be dynamic. Over-matching
    # is the safe direction here -- it can only make the guard MISS an
    # orphan, never invent one.
    contents: dict[pathlib.Path, str] = {}
    for path in sources:
        try:
            contents[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    violations: list[str] = []
    for path in sources:
        if _is_entry_point(path, declared):
            continue

        stem = path.stem
        pattern = re.compile(rf"(?<![\w-]){re.escape(stem)}(?![\w-])")

        # A module referenced ONLY by its own test is still not wired to
        # anything. It is arguably worse than a plain orphan, because the
        # test makes it look covered: `sbml-builder.ts` shipped with 400
        # lines and a full test file, and nothing in the product called it.
        #
        # Same lesson as check_plausibility_constants: tests are not users.
        # A test proves a module WORKS; it says nothing about whether the
        # product uses it.
        referenced_by_product = False
        referenced_by_test = False
        for other, text in contents.items():
            if other == path:
                continue
            if not pattern.search(text):
                continue
            relative_other = other.relative_to(REPO_ROOT).as_posix()
            if any(p.match(relative_other) for p in ENTRY_POINT_PATTERNS):
                referenced_by_test = True
            else:
                referenced_by_product = True
                break

        if not referenced_by_product and referenced_by_test:
            line_count = contents.get(path, "").count("\n") + 1
            violations.append(
                f"{path.relative_to(REPO_ROOT)} ({line_count} lines) is "
                "imported ONLY by its own test. The test proves it works; "
                "nothing in the product calls it. Wire it to a command or a "
                "code path, or retire it -- a tested orphan looks covered, "
                "which makes it harder to notice than an untested one."
            )
            continue

        if not referenced_by_product:
            line_count = contents.get(path, "").count("\n") + 1
            violations.append(
                f"{path.relative_to(REPO_ROOT)} ({line_count} lines) is "
                "imported by nothing. Either wire it to something that runs, "
                "or delete it -- an unreachable module is a second answer to "
                "a question that already had one, and this repository has "
                "been bitten repeatedly by defects living in the copy nobody "
                "was watching."
            )

    return violations


def main() -> int:
    violations = check()
    if not violations:
        print(
            f"OK: every module under {', '.join(SEARCH_ROOTS)} is reachable "
            "from something that runs."
        )
        return 0

    total = sum(
        int(match.group(1))
        for match in (re.search(r"\((\d+) lines\)", v) for v in violations)
        if match
    )
    print(f"Orphaned modules found ({len(violations)}, {total} lines):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nAdding code that nothing calls is not progress. If a module is "
        "genuinely an entry point, add it to package.json or to "
        "ENTRY_POINT_PATTERNS in this script with a reason."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
