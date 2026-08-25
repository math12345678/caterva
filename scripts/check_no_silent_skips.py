"""Silent-skip guard for Terrium.

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

import importlib.util
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Skips are counted per suite, in the order `make test` runs them.
SUITES = [
    ("engine", REPO_ROOT / "Terium" / "tests"),
    ("literature", REPO_ROOT / "Tests"),
]

# The whole point of the guard. See module docstring before changing.
EXPECTED_MAX_SKIPS = 0

#: Skips that a declared OPTIONAL requirements file explains.
#:
#: `requirements-popgen.txt` keeps stdpopsim out of the default install on
#: purpose: it is GPL-3.0-or-later and Terrium is Apache-2.0, so a default
#: install must not quietly put copyleft code in the environment (ADR 0061).
#: That file states the intended consequence in as many words -- the popgen
#: tests "skip, and `make check` reports the skip as a warning rather than
#: passing silently".
#:
#: A warning is not what happened. With `EXPECTED_MAX_SKIPS = 0` this was a
#: red build, so the two documents disagreed about the same deliberate
#: design, and the only routes out were installing the GPL package the split
#: exists to avoid or raising the limit -- which this file's docstring
#: forbids, and which would also blind the guard to the next real skip.
#:
#: So the exemption is per-test and CONDITIONAL, not a raised count. The
#: entry is honoured only while the named module is genuinely absent; if
#: someone installs the extra and the test skips anyway, that is a skip
#: nothing explains and it goes red. An exemption that cannot expire is a
#: rubber stamp.
OPTIONAL_EXTRAS = {
    "test_popgen_resolver": (
        "stdpopsim", "requirements-popgen.txt",
        "GPL-3.0-or-later, deliberately outside the default install (ADR 0061)",
    ),
}


def explained_by_optional_extra(reason: str) -> tuple[str, str] | None:
    """(requirements file, note) if an absent optional package explains it.

    Matches on the test id in the reason line rather than on the skip
    message, because the message is prose an author can reword.
    """
    for test_id, (module, req_file, note) in OPTIONAL_EXTRAS.items():
        if test_id not in reason:
            continue
        if importlib.util.find_spec(module) is not None:
            # Installed and still skipping: not explained. Fall through so
            # it is reported as an ordinary unexplained skip.
            return None
        return req_file, note
    return None


def run_suite(path: Path) -> Tuple[int, int, List[str]] | None:
    r"""Run one suite. Returns (passed, skipped, skip_reasons) or None.

    RESULTS ARE READ FROM JUnit XML, NOT FROM THE TERMINAL OUTPUT.

    This used to parse `(\d+) passed` out of stdout, and for the engine
    suite it parsed nothing at all -- so the guard reported "1 of 2 suite(s)
    did not run: engine" on a suite that ran perfectly and exited 0.

    The cause is worth writing down because it is invisible and it will
    recur. `Terium/pytest.ini` already sets `addopts = -q`. When pytest is
    invoked with `Terium/tests` as the argument it resolves rootdir to
    `Terium/` and picks up that ini, so this guard's own `-q` became the
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
    failures: List[str] = []

    for case in cases:
        where = f"{case.get('file') or case.get('classname')}::{case.get('name')}"
        skip = case.find("skipped")
        if skip is not None:
            skipped += 1
            why = (skip.get("message") or "").strip()
            reasons.append(f"{where}: {why}" if why else where)
        elif case.find("failure") is not None or case.find("error") is not None:
            # COUNTED, not discarded.
            #
            # This branch used to be `elif no failure and no error: passed
            # += 1`, so a failing test was neither passed nor skipped -- it
            # left the totals entirely. The guard then printed "1,222
            # passed, 0 skipped" and exited 0 with tests failing in the
            # report it had just parsed.
            #
            # That is this file's own docstring turned inward: "a green
            # suite cannot distinguish 'ran and passed' from 'declined to
            # run'." Here it could distinguish and said nothing. Measured
            # the hard way on 2026-08-25 -- a full local guard sweep
            # reported 41/41 green, and CI failed on a test this guard had
            # already read.
            failures.append(where)
        else:
            passed += 1

    if failures:
        print(f"  ! {len(failures)} failing test(s) in {path.name}:")
        for where in failures[:10]:
            print(f"      {where}")
        if len(failures) > 10:
            print(f"      ... and {len(failures) - 10} more")
        # None means "no trustworthy skip count", which is exactly right: a
        # suite with failures may also have stopped short of tests that
        # would have skipped. `main` turns this into a red build via the
        # `unrun` path, and says the suite did not run cleanly rather than
        # reporting a skip total about a suite that was already broken.
        return None

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
            "\nA suite that did not run, or that ran with failures, has an\n"
            "unknown skip count. Reporting a skip total that omits it would\n"
            "be a number about the suites that happened to work, presented\n"
            "as a number about all of them.\n"
            "\n"
            "Failing tests are listed above. This guard is not the place to\n"
            "diagnose them -- run the suite directly -- but it will not\n"
            "print OK while holding a report that says they failed."
        )
        return 1

    # Partition before counting: a skip an optional extra explains is
    # reported, not tolerated silently, and not counted against the limit.
    explained = [(r, e) for r in all_reasons if (e := explained_by_optional_extra(r))]
    unexplained = [r for r in all_reasons if explained_by_optional_extra(r) is None]

    if explained:
        print(f"Explained by an optional extra ({len(explained)}), not counted:")
        for reason, (req_file, note) in explained:
            print(f"  - {reason}")
            print(f"      absent by design: {note}")
            print(f"      to run these:     pip install -r {req_file}")
        print()

    # The limit now applies to skips NOTHING explains. Counting the explained
    # ones against it would leave no honest setting: 0 fails on a deliberate
    # split, and 1 quietly buys room for an unrelated regression.
    total_skipped -= len(explained)

    if total_skipped > EXPECTED_MAX_SKIPS:
        print(f"FAIL: {total_skipped} skipped test(s), expected at most "
              f"{EXPECTED_MAX_SKIPS}.")
        if unexplained:
            print("\nSkipped:")
            for reason in unexplained:
                print(f"  - {reason}")
        print(
            "\nA skipped test is a test that did not run. Before raising\n"
            "EXPECTED_MAX_SKIPS, check whether the skip condition actually\n"
            "indicates a regression -- that is what it meant the last time\n"
            "(see this script's docstring)."
        )
        return 1

    # The success line names its own denominator, so "every collected test
    # ran" is a claim a reader can check rather than take on trust.
    print(
        f"OK: {len(ran)}/{len(SUITES)} suites ran, {total_passed} tests, "
        f"{total_skipped} unexplained skip(s) (limit {EXPECTED_MAX_SKIPS})"
        + (f", {len(explained)} explained by an optional extra." if explained else ".")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
