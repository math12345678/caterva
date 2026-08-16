#!/usr/bin/env python3
"""
check_mutation_tables_reproducible.py

Every NEW decision record that presents a mutation table must ship that
table as a re-runnable set file.

WHY
---
Mutation results are the evidence this project asks readers to accept. Six
"checks that cannot fail" were found that way, along with the boundary drops
of ADR 0039, the crashed sweep point of ADR 0058 and the model-selection
defect of ADR 0060.

ADR 0069 established that every one of those tables was produced by a
hand-run harness which had, by then, given a wrong answer three separate
ways: a patch that never applied, a suite that never ran, and a restore that
silently failed. `scripts/mutate.py` fixed the harness. It did not
retroactively re-verify the tables, and ADR 0069 said so rather than
pretending otherwise.

This guard exists so that honesty does not quietly become permanent. It:

- **stops the debt growing** -- a new ADR with a mutation table and no set
  file fails the build;
- **makes the existing debt countable** -- the grandfathered records are
  listed in one file with a number at the top, not scattered across 37
  documents;
- **forces the list to shrink** -- an ADR that gains a set file must be
  removed from the list, and the guard fails until it is. A baseline that
  can be added to but never emptied is a way of recording a problem instead
  of fixing it.

WHAT IT DOES NOT CLAIM
----------------------
It does not check that a set file's results MATCH the table in the ADR.
Doing that means running every set on every build, which costs minutes and
would make the check something people skip. What it establishes is narrower
and worth stating exactly: **the table can be re-derived by anyone who wants
to.** Whether it was is a separate question, answered by running the set.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = REPO_ROOT / "docs" / "adr"
SET_DIR = REPO_ROOT / "docs" / "mutations"
BASELINE = SET_DIR / "NOT-YET-REPRODUCIBLE.txt"

#: A markdown table whose first meaningful column is headed "mutation".
#: Written from the nine header forms actually present in docs/adr rather
#: than from one imagined format -- a matcher built from one example would
#: have found 3 of 37 and reported the other 34 as having no table, which is
#: the "confident false negative" failure this project has hit before.
MUTATION_TABLE_RE = re.compile(
    r"^\|\s*(?:#\s*\|\s*)?mutation\s*\|",
    re.IGNORECASE | re.MULTILINE,
)

#: A heading that introduces mutation results, for ADRs that report them as
#: prose rather than a table.
MUTATION_HEADING_RE = re.compile(r"^#+\s+.*\bmutation", re.IGNORECASE | re.MULTILINE)

ADR_NAME_RE = re.compile(r"^(\d{4})-")
SET_NAME_RE = re.compile(r"^adr-(\d{4})-")


def adr_number(path: Path) -> str | None:
    match = ADR_NAME_RE.match(path.name)
    return match.group(1) if match else None


def presents_mutation_results(text: str) -> bool:
    return bool(MUTATION_TABLE_RE.search(text) or MUTATION_HEADING_RE.search(text))


def read_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    numbers = set()
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            numbers.add(line)
    return numbers


def main() -> int:
    if not ADR_DIR.exists():
        print(f"FAIL: {ADR_DIR} does not exist.", file=sys.stderr)
        return 1

    adrs = sorted(p for p in ADR_DIR.glob("*.md") if adr_number(p))
    if not adrs:
        # A guard that examined nothing must not print OK.
        print("FAIL: found no ADR files to check.", file=sys.stderr)
        return 1

    with_results: dict[str, Path] = {}
    for path in adrs:
        if presents_mutation_results(path.read_text(encoding="utf-8", errors="replace")):
            number = adr_number(path)
            assert number is not None
            with_results[number] = path

    have_sets: dict[str, Path] = {}
    stale_sets: list[Path] = []
    if SET_DIR.exists():
        for path in sorted(SET_DIR.glob("*.json")):
            match = SET_NAME_RE.match(path.name)
            if not match:
                continue
            numbers = {match.group(1)}

            # A set may legitimately cover more than one record. ADR 0033
            # and ADR 0035 share a suite and the same finding -- a defensive
            # branch the fixtures could not reach -- so their mutations were
            # written as one file, and inferring coverage from the FILENAME
            # alone credited only the first of them.
            #
            # An optional `covers` list is authoritative; the filename is
            # the default when it is absent. Read from the file rather than
            # guessed from its name, because a name is a label and a label
            # is not a claim anyone checked.
            try:
                spec = json.loads(path.read_text(encoding="utf-8"))
                declared = spec.get("covers")
                if isinstance(declared, list):
                    numbers |= {str(n).zfill(4) for n in declared}
            except (OSError, json.JSONDecodeError):
                pass  # reported separately by the validity check below

            for number in numbers:
                have_sets[number] = path
                # A set file naming an ADR that does not exist is a dangling
                # record, and it would otherwise sit here looking like
                # coverage.
                if not list(ADR_DIR.glob(f"{number}-*.md")):
                    stale_sets.append(path)

    baseline = read_baseline()

    missing = sorted(n for n in with_results if n not in have_sets and n not in baseline)
    resolved = sorted(n for n in baseline if n in have_sets)
    ghosts = sorted(n for n in baseline if n not in with_results)

    print(f"ADRs presenting mutation results: {len(with_results)}")
    print(f"  reproducible as a set file:     {len(have_sets & with_results.keys())}")
    print(f"  grandfathered (ADR 0069 debt):  {len(baseline) - len(resolved) - len(ghosts)}")

    problems = False

    if missing:
        problems = True
        print(
            f"\nMutation results with no re-runnable set ({len(missing)}):",
            file=sys.stderr,
        )
        for number in missing:
            print(f"  - {with_results[number].name}", file=sys.stderr)
        print(
            "\nA mutation table is the evidence a reader is asked to accept, and the\n"
            "harness that produced tables in this project was wrong three separate\n"
            "ways before ADR 0069. Ship the table as a set file:\n"
            "\n"
            "    docs/mutations/adr-<NNNN>-<slug>.json\n"
            "    python3 scripts/mutate.py --set docs/mutations/adr-<NNNN>-<slug>.json\n"
            "\n"
            "The set's `test` command must run EVERY suite the ADR cites, not the\n"
            "one that looks most relevant. A narrower command produces a confident\n"
            "NOT CAUGHT that reads as a real gap -- ADR 0026's set did exactly that\n"
            "on its first run, because the test closing the mutation lived in the\n"
            "second of the two files the record names.\n"
            "\n"
            "If this record predates the harness, add its number to\n"
            f"    {BASELINE.relative_to(REPO_ROOT)}\n"
            "with a one-line reason -- and expect to be asked when it will go.",
            file=sys.stderr,
        )

    if resolved:
        problems = True
        print(
            f"\nGrandfathered records that now HAVE a set file ({len(resolved)}):",
            file=sys.stderr,
        )
        for number in resolved:
            print(f"  - {number}  ({have_sets[number].name})", file=sys.stderr)
        print(
            "\nRemove these from the baseline. A list that can be added to but never\n"
            "emptied records a problem instead of fixing it, and the count at the top\n"
            "of this output stops meaning anything.",
            file=sys.stderr,
        )

    if ghosts:
        problems = True
        print(
            f"\nBaseline entries for ADRs with no mutation results ({len(ghosts)}):",
            file=sys.stderr,
        )
        for number in ghosts:
            print(f"  - {number}", file=sys.stderr)
        print("\nThe record was renumbered or the table removed. Drop these.", file=sys.stderr)

    if stale_sets:
        problems = True
        print(f"\nSet files naming a nonexistent ADR ({len(stale_sets)}):", file=sys.stderr)
        for path in stale_sets:
            print(f"  - {path.name}", file=sys.stderr)

    for number, path in sorted(have_sets.items()):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems = True
            print(f"\n{path.name} is not valid JSON: {exc}", file=sys.stderr)
            continue
        if not spec.get("test") or not spec.get("mutations"):
            problems = True
            print(
                f"\n{path.name} has no `test` command or no `mutations`, so it cannot "
                "be run. An unrunnable set file is worse than none: it reads as "
                "coverage.",
                file=sys.stderr,
            )

    if problems:
        return 1

    print("\nOK: every ADR presenting mutation results can be re-derived, or is")
    print("    listed as outstanding with a reason.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
