"""Silent-skip guard for Caterva.

Fails when the test suites skip more tests than expected.

Why this exists
---------------
`make test` reported "857 passed, 1 skipped" for months. The 1 was
`test_flagged_brenda_entries_do_not_become_confident_numbers`, which read:

    flagged = [e for e in ldh_entries if e.flagged]
    if not flagged:
        pytest.skip("no flagged entries in this fixture")

Every fixture in the repository parses to zero flagged entries, so the skip
fired on every run and the assertions below it had **never executed once**.
The test was counted in the suite total while testing nothing, and it
guarded the exact failure its own file exists to catch: a value the
literature layer flagged as suspicious quietly becoming a confident number.

A green suite cannot distinguish "ran and passed" from "declined to run".
That is the gap this closes. A skip is not automatically wrong -- some are
genuinely conditional on an absent optional dependency -- but an *unexpected*
skip, or a rising skip count, is a signal that something stopped being
tested.

Policy
------
`EXPECTED_MAX_SKIPS` is 0. Every skip in the suites is currently either
removed (converted to an assertion, because the condition indicates a
regression rather than an unsupported environment) or inert (`skipif` on a
package split that is present).

Raising this number is a deliberate act that must be justified in the commit
message. Do not raise it to make a red build green.

Usage:
    python scripts/check_no_silent_skips.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Skips are counted per suite, in the order `make test` runs them.
SUITES = [
    ("engine", REPO_ROOT / "caterva" / "tests"),
    ("literature", REPO_ROOT / "Tests"),
]

# The whole point of the guard. See module docstring before changing.
EXPECTED_MAX_SKIPS = 0

#: Skips that are a documented optional dependency rather than a
#: regression, keyed by the identifier this guard prints, with the reason.
#:
#: WHY THIS EXISTS RATHER THAN A HIGHER EXPECTED_MAX_SKIPS
#: -------------------------------------------------------
#: The docstring above already allows for this case -- "some are genuinely
#: conditional on an absent optional dependency" -- and gives only one
#: lever, a count. A count is the wrong shape: raising it to 1 to admit
#: the popgen skip also silently admits the NEXT skip, whatever it is, and
#: the thing this guard exists to catch is precisely a skip nobody
#: expected. One number cannot say "this one, for this reason".
#:
#: Naming them keeps the guard's whole power: an unexpected skip still
#: fails, because it is not in here.
#:
#: THE LIST IS SUPPOSED TO SHRINK. An entry whose test stops skipping
#: fails too -- same rule as EXPECTED_WIRING and NOT-YET-REPRODUCIBLE.txt.
#: A baseline that can be added to but never emptied records a problem
#: instead of fixing it.
ALLOWED_SKIPS: dict[str, str] = {
    "test_popgen_resolver": (
        "Needs `stdpopsim`, which lives in the optional "
        "requirements-popgen.txt. `make setup` installs requirements-dev.txt "
        "and so does CI, so following CONTRIBUTING produces exactly this "
        "skip -- it is the documented setup working as documented, not a "
        "test that stopped running. Clear it by installing the popgen "
        "extra, or by folding stdpopsim into requirements-dev if the "
        "population-genetics domain stops being optional."
    ),
    "test_the_guards_selftest_passes[check_codegen_loads.py]": (
        "The codegen load check's selftest needs npx and an installed zod, "
        "which the Python CI jobs do not install, so it exits 2 ('could not "
        "run'), reported as this skip. It is not untested: the api-server "
        "job installs the toolchain and runs the selftest for real. Added "
        "2026-09-27; before, it reported the missing toolchain as a failure."
    ),
}

#: Allowances whose skip depends on what the MACHINE has installed, not on
#: the code: on a machine with the toolchain the test runs, which is the
#: good outcome, so these are exempt from the stale-entry rule below. Every
#: other allowance must still skip or be deleted.
CONDITIONAL_ON_ENVIRONMENT: frozenset[str] = frozenset({
    "test_the_guards_selftest_passes[check_codegen_loads.py]",
})


def _skip_key(reason: str) -> str:
    """The test identifier out of a printed skip line.

    Lines look like `path::name: message` or `::name: message`. The key is
    the name, because the file half is empty for a collection-level skip
    and the message half is whatever pytest chose to say that day.
    """
    location = reason.split(":", 1)[0] if "::" not in reason else reason.split("::", 1)[1]
    return location.split(":", 1)[0].strip()


def run_suite(path: Path) -> Tuple[int, int, List[str]] | None:
    """Run one suite. Returns (passed, skipped, skip_reasons) or None.

    RESULTS ARE READ FROM JUnit XML, NOT FROM THE TERMINAL OUTPUT.

    This used to parse `(\\d+) passed` out of stdout, and for the engine
    suite it parsed nothing at all -- so the guard reported "1 of 2 suite(s)
    did not run: engine" on a suite that ran perfectly and exited 0.

    The cause is worth writing down because it is invisible and it will
    recur. `caterva/pytest.ini` already sets `addopts = -q`. When pytest is
    invoked with `caterva/tests` as the argument it resolves rootdir to
    `caterva/` and picks up that ini, so this guard's own `-q` became the
    SECOND one. Two `-q` flags is quiet level 2, which suppresses the
    summary line entirely. The suite printed its dots, exited 0, and said
    nothing a regex could read.

    Any tool that shells out to pytest with `-q` hits this. The fix is not
    to drop the flag -- it is to stop reading prose that a verbosity setting
    three directories away can silently delete. JUnit XML carries exact
    counts, is unaffected by `-q`, and distinguishes skipped from passed
    structurally instead of by wording.
    """
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.xml"
        try:
            subprocess.run(
                [sys.executable, "-m", "pytest", str(path), "-rs",
                 "-p", "no:randomly", f"--junitxml={report}"],
                capture_output=True,
                text=True,
                timeout=1800,
                cwd=str(REPO_ROOT),
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"  ! could not run {path.name}: {exc}")
            return None

        if not report.exists():
            print(f"  ! pytest produced no JUnit report for {path}")
            return None

        try:
            root = ET.parse(report).getroot()
        except ET.ParseError as exc:
            print(f"  ! unreadable JUnit report for {path}: {exc}")
            return None

    cases = root.iter("testcase")
    passed = 0
    skipped = 0
    reasons: List[str] = []

    for case in cases:
        skip = case.find("skipped")
        if skip is not None:
            skipped += 1
            where = f"{case.get('file') or case.get('classname')}::{case.get('name')}"
            why = (skip.get("message") or "").strip()
            reasons.append(f"{where}: {why}" if why else where)
        elif case.find("failure") is None and case.find("error") is None:
            passed += 1

    if passed == 0 and skipped == 0:
        # A report containing no test cases means collection produced
        # nothing -- still an unknown skip count, not a zero.
        print(f"  ! no test cases in the JUnit report for {path}")
        return None

    return passed, skipped, reasons


def main() -> int:
    total_skipped = 0
    total_passed = 0
    all_reasons: List[str] = []
    ran: List[str] = []
    unrun: List[str] = []

    print("Running suites to count skips...")
    for name, path in SUITES:
        result = run_suite(path)
        if result is None:
            # A suite that could not run has an UNKNOWN skip count, which is
            # not the same as zero.
            #
            # This used to be `continue`, with `ran_any` needing only one
            # success. Stubbing the literature suite to fail reproduced the
            # exact defect this guard exists to close:
            #
            #   engine        857 passed, 0 skipped
            #   ! could not run Tests: simulated collection error
            #   OK: 0 skipped (limit 0). Every collected test ran.
            #   EXIT CODE: 0
            #
            # 275 tests did not run and the guard said every collected test
            # ran. In CI the `!` line scrolls past inside a green step. That
            # is this file's own docstring -- "a green suite cannot
            # distinguish 'ran and passed' from 'declined to run'" --
            # reproduced inside the guard written to close it.
            #
            # `run_suite` returns None on a timeout, an OSError, or output
            # with no parseable counts, i.e. a collection error or an import
            # failure at module scope. Every one of those is a reason to go
            # red.
            unrun.append(name)
            continue
        ran.append(name)
        passed, skipped, reasons = result
        total_passed += passed
        total_skipped += skipped
        all_reasons.extend(reasons)
        flag = "" if skipped == 0 else f"   <-- {skipped} skipped"
        print(f"  {name:<12} {passed:>4} passed, {skipped} skipped{flag}")

    print()
    if unrun:
        print(
            f"FAIL: {len(unrun)} of {len(SUITES)} suite(s) did not run: "
            f"{', '.join(unrun)}."
        )
        print(
            "\nA suite that did not run has an unknown skip count. Reporting\n"
            "a skip total that omits it would be a number about the suites\n"
            "that happened to work, presented as a number about all of them."
        )
        return 1

    if total_skipped > EXPECTED_MAX_SKIPS:
        unexpected = [r for r in all_reasons if _skip_key(r) not in ALLOWED_SKIPS]
        allowed_seen = {_skip_key(r) for r in all_reasons} & set(ALLOWED_SKIPS)

        if allowed_seen:
            print(f"\nSkipped, and recorded as expected ({len(allowed_seen)}):")
            for key in sorted(allowed_seen):
                print(f"  - {key}\n      {ALLOWED_SKIPS[key]}")

        if unexpected:
            print(
                f"\nFAIL: {len(unexpected)} unexpected skipped test(s), "
                f"expected at most {EXPECTED_MAX_SKIPS}."
            )
            print("\nSkipped:")
            for reason in unexpected:
                print(f"  - {reason}")
            print(
                "\nA skipped test is a test that did not run. Before adding\n"
                "it to ALLOWED_SKIPS, check whether the skip condition\n"
                "actually indicates a regression -- that is what it meant the\n"
                "last time (see this script's docstring). An entry there needs\n"
                "a reason, and a reason that is really 'it was red' is how a\n"
                "budget becomes a suppression list."
            )
            return 1

        # An allowance whose skip stopped happening is stale, and a baseline
        # that only ever grows records a problem instead of fixing it.
        stale = sorted(set(ALLOWED_SKIPS) - allowed_seen - CONDITIONAL_ON_ENVIRONMENT)
        if stale:
            print(
                f"\nFAIL: {len(stale)} entr(y/ies) in ALLOWED_SKIPS no longer "
                "skip:"
            )
            for key in stale:
                print(f"  - {key}")
            print(
                "\nThe test runs again, which is the good outcome. Delete the\n"
                "entry so the list keeps meaning what it says."
            )
            return 1

    # The success line names its own denominator, so "every collected test
    # ran" is a claim a reader can check rather than take on trust.
    # "1 skipped (limit 0)" read as a contradiction the moment named
    # allowances existed. The unexpected count is the one the limit governs,
    # and it is the number a reader should be able to check.
    print(
        f"OK: {len(ran)}/{len(SUITES)} suites ran, {total_passed} tests, "
        f"0 unexpected skips (limit {EXPECTED_MAX_SKIPS}); "
        f"{total_skipped} skipped and recorded."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
