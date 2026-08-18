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

TWO SHAPES OF EVIDENCE, AND ONLY TWO
------------------------------------
The usual one is `docs/mutations/adr-NNNN-<slug>.json`: a set of mutations
plus the command that judges them.

The other exists because this guard was demanding the wrong thing of one
record. ADR 0069's table is not mutations of product source -- it is
`mutate.py --selftest`, the harness proving it reports INDETERMINATE where
it cannot establish a verdict, and `verify_build.py` runs it on every build.
That is a *stronger* guarantee than a set file, because a set file is
re-runnable and this one is actually re-run. The guard counted it as debt
anyway, because it recognised exactly one shape of evidence.

The two ways out of that were to invent a set file which could not really
reproduce the table, or to leave the record on the debt list forever.
Inventing evidence to satisfy a check is the thing this guard exists to
prevent, so it learned the second shape instead: a set file may declare

    "reproduced_by": "scripts/mutate.py --selftest"

and the guard FAILS unless `verify_build.py` really runs that command. The
check is the point. An alternative route nobody verifies is a hole, not an
alternative -- every future record could opt out by naming a command.

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

#: Where a `reproduced_by` claim is checked against reality. A command that
#: the build does not run is a command nobody runs.
VERIFY_BUILD = REPO_ROOT / "scripts" / "verify_build.py"

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

#: What `mutate.py` indexes on a mutation entry with no default:
#: `mutation["file"]`, `mutation["find"]`, `mutation["replace"]`. Anything
#: absent is a KeyError partway through a run, not a clean refusal.
REQUIRED_MUTATION_KEYS = frozenset({"file", "find", "replace"})

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


def unwired_reason(command: str) -> str | None:
    """None if `command` is one the build runs unasked; else why not.

    WHY THIS IS CHECKED RATHER THAN TRUSTED
    ---------------------------------------
    `reproduced_by` is an alternative to shipping mutations, and an
    alternative that nobody verifies is a way out of the guard rather than a
    second way of satisfying it. The requirement is not "name a command" but
    "name a command this repository already runs on every build", which is a
    fact about `verify_build.py` and therefore checkable.

    Matching is by SCRIPT BASENAME PLUS EVERY ARGUMENT, on one line.
    `verify_build.py` composes its commands (`f"python {SCRIPTS_DIR /
    'mutate.py'} --selftest"`), so an exact string match on
    `scripts/mutate.py --selftest` would find nothing and report every
    honest claim as unwired -- the confident false negative this project has
    hit before with a matcher built from one imagined format.
    """
    tokens = command.split()
    if not tokens:
        return "`reproduced_by` is empty."
    script = Path(tokens[0]).name
    if not VERIFY_BUILD.exists():
        return f"{VERIFY_BUILD.name} does not exist, so the claim cannot be checked."
    for line in VERIFY_BUILD.read_text(encoding="utf-8").splitlines():
        if script in line and all(arg in line for arg in tokens[1:]):
            return None
    return (
        f"no line of {VERIFY_BUILD.name} runs {script} with {' '.join(tokens[1:]) or '(no args)'}"
    )


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
        # Two shapes of re-runnable evidence, and only two.
        #
        # The usual one is a set of mutations plus the command that judges
        # them. The other exists because ADR 0069's table is not mutations
        # of product source at all -- it is `mutate.py --selftest`, the
        # harness proving it reports INDETERMINATE where it cannot establish
        # a verdict. There is no set file that can reproduce that table, and
        # the only ways to satisfy a mutations-only guard were to invent one
        # or to sit on the debt list forever. Inventing evidence to satisfy
        # a check is the thing this guard exists to prevent.
        if reproduced_by := spec.get("reproduced_by"):
            if reason := unwired_reason(str(reproduced_by)):
                problems = True
                print(
                    f"\n{path.name} claims `reproduced_by: {reproduced_by}`, but "
                    f"{reason}.\n"
                    "A command the build does not run is a command nobody runs, and\n"
                    "this field would then be a way out of the guard rather than a\n"
                    "second way of satisfying it.",
                    file=sys.stderr,
                )
        elif not spec.get("test") or not spec.get("mutations"):
            problems = True
            print(
                f"\n{path.name} has no `test` command or no `mutations`, and no "
                "`reproduced_by`, so it cannot be run. An unrunnable set file is "
                "worse than none: it reads as coverage.",
                file=sys.stderr,
            )
        else:
            # The keys `mutate.py` indexes without a default. The top-level
            # check above passed a set file whose entries used `search`
            # instead of `find`; the guard reported it reproducible and the
            # harness died on `KeyError: 'find'` at the first mutation.
            #
            # "It cannot be run" was being decided from the OUTER shape
            # only, which is the same half-check this project keeps finding:
            # the presence of a container taken as evidence about its
            # contents.
            #
            # `.get` rather than `["mutations"]`: this branch is only
            # reached when the `elif` above has established the key exists,
            # and depending on that is an invisible coupling between two
            # branches. It showed up immediately -- mutating the `elif`'s
            # condition made this line raise, so the harness returned
            # INDETERMINATE and no verdict could be had on the mutation at
            # all. A crash is not a refusal.
            for index, mutation in enumerate(spec.get("mutations") or []):
                if not isinstance(mutation, dict):
                    absent = REQUIRED_MUTATION_KEYS
                else:
                    absent = sorted(REQUIRED_MUTATION_KEYS - mutation.keys())
                if absent:
                    problems = True
                    label = (
                        mutation.get("id", f"#{index}")
                        if isinstance(mutation, dict)
                        else f"#{index}"
                    )
                    print(
                        f"\n{path.name} mutation {label} is missing "
                        f"{', '.join(sorted(absent))}. `mutate.py` reads these "
                        "with no default, so the run dies partway through with a "
                        "KeyError -- after the baseline, and possibly after "
                        "mutating a file.",
                        file=sys.stderr,
                    )

    if problems:
        return 1

    print("\nOK: every ADR presenting mutation results can be re-derived, or is")
    print("    listed as outstanding with a reason.")
    return 0


def selftest() -> int:
    """Drive this guard through its own failure modes in a temporary tree.

    It was wired into `verify_build.py` with no self-test, which is the
    position `check_exports_reach_a_caller.py` was in before ADR 0090 and
    the position ADR 0058's M3, ADR 0072's set file and ADR 0079's
    comment-stripper were each found in: **a property defended only in prose
    is a property that stops being checked.** This guard enforces that rule
    on other people's records while not meeting it itself.

    The fifth case is the one that matters most. `reproduced_by` is an
    alternative route to satisfying the guard, and an unchecked alternative
    route is a hole. If a set file can name any command at all and pass,
    every future record can opt out by naming one.
    """
    import contextlib
    import io
    import tempfile

    # REPO_ROOT is patched too, not for the checks but because main()
    # composes its advice with `BASELINE.relative_to(REPO_ROOT)`, which
    # raises if the two are unrelated. Harmless in production and fatal in a
    # temporary tree.
    global ADR_DIR, SET_DIR, BASELINE, VERIFY_BUILD, REPO_ROOT
    saved = (ADR_DIR, SET_DIR, BASELINE, VERIFY_BUILD, REPO_ROOT)
    failures = 0

    print("Self-test: the failure modes this guard claims to catch.\n")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            REPO_ROOT = root
            ADR_DIR = root / "adr"
            SET_DIR = root / "mutations"
            BASELINE = SET_DIR / "NOT-YET-REPRODUCIBLE.txt"
            VERIFY_BUILD = root / "verify_build.py"
            ADR_DIR.mkdir()
            SET_DIR.mkdir()

            (ADR_DIR / "0001-a-record.md").write_text(
                "# ADR 0001\n\n## Mutation testing\n\n"
                "| mutation | expected | result |\n|---|---|---|\n| x | y | ok |\n",
                encoding="utf-8",
            )
            VERIFY_BUILD.write_text(
                "run_guard(\n"
                "    'Mutation Harness Self-Check',\n"
                '    f"python {SCRIPTS_DIR / \'mutate.py\'} --selftest",\n'
                ")\n",
                encoding="utf-8",
            )

            def run(label: str, want: int) -> None:
                nonlocal failures
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    got = main()
                ok = got == want
                failures += 0 if ok else 1
                print(f"  [{'ok' if ok else 'FAIL'}] {label} (exit {got}, want {want})")

            def write_set(name: str, spec: dict) -> Path:
                path = SET_DIR / name
                path.write_text(json.dumps(spec), encoding="utf-8")
                return path

            def clear_sets() -> None:
                for stale in SET_DIR.glob("*.json"):
                    stale.unlink()

            BASELINE.write_text("", encoding="utf-8")
            run("a mutation table with no set file fails", 1)

            BASELINE.write_text("0001  # deliberate\n", encoding="utf-8")
            run("recording it in the baseline passes", 0)

            valid = {
                "test": "pytest",
                "mutations": [{"file": "a.py", "find": "x", "replace": "y"}],
            }
            write_set("adr-0001-x.json", valid)
            run("a baselined record that gains a set file fails", 1)

            BASELINE.write_text("", encoding="utf-8")
            run("a set file with mutations passes", 0)

            # The set file that passed this guard and then killed the
            # harness: entries keyed `search` instead of `find`. The guard
            # was checking the outer shape and calling it runnable.
            clear_sets()
            write_set(
                "adr-0001-x.json",
                {"test": "pytest", "mutations": [{"file": "a.py", "search": "x", "replace": "y"}]},
            )
            run("a mutation entry missing a key mutate.py requires fails", 1)

            # The pre-existing unrunnable-set check, which had no case here
            # until a mutation asked. Replacing its condition with `False`
            # was NOT CAUGHT by the first eight cases: every one of them
            # either shipped a valid set or took the `reproduced_by` branch
            # in front of it, so the branch this guard has enforced since it
            # was written was the one branch nothing exercised.
            clear_sets()
            write_set("adr-0001-x.json", {"test": "pytest"})
            run("a set file with a test command but no mutations fails", 1)

            clear_sets()
            write_set("adr-0001-x.json", {})
            run("an empty set file fails rather than reading as coverage", 1)

            # The escape hatch, opened and closed.
            clear_sets()
            write_set("adr-0001-x.json", {"reproduced_by": "scripts/mutate.py --selftest"})
            run("`reproduced_by` naming a command the build runs passes", 0)

            clear_sets()
            write_set("adr-0001-x.json", {"reproduced_by": "scripts/nothing_runs_this.py"})
            run("`reproduced_by` naming an UNWIRED command fails", 1)

            clear_sets()
            write_set("adr-0001-x.json", {"reproduced_by": "scripts/mutate.py --not-a-real-flag"})
            run("`reproduced_by` with an argument the build never passes fails", 1)

            # A guard that examined nothing must not print OK -- the same
            # trap as the citation guard that parsed zero entries.
            clear_sets()
            ADR_DIR = root / "no-such-dir"
            run("an empty scan fails rather than passing", 1)
    finally:
        ADR_DIR, SET_DIR, BASELINE, VERIFY_BUILD, REPO_ROOT = saved

    print()
    if failures:
        print(f"FAIL: {failures} self-test case(s) failed.", file=sys.stderr)
        return 1
    print("OK: the guard catches a missing set, forces the baseline to shrink, and")
    print("    refuses a `reproduced_by` the build does not actually run.")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
