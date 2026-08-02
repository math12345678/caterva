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

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Skips are counted per suite, in the order `make test` runs them.
SUITES = [
    ("engine", REPO_ROOT / "Tellurium" / "tests"),
    ("literature", REPO_ROOT / "Tests"),
]

# The whole point of the guard. See module docstring before changing.
EXPECTED_MAX_SKIPS = 0


def run_suite(path: Path) -> Optional[Tuple[int, int, List[str]]]:
    """Run one suite. Returns (passed, skipped, skip_reasons) or None.

    `-rs` makes pytest print the reason for every skip, so a failure can name
    what stopped running instead of just reporting a number.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(path), "-q", "-rs",
             "-p", "no:randomly"],
            capture_output=True,
            text=True,
            timeout=1800,
            cwd=str(REPO_ROOT),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  ! could not run {path.name}: {exc}")
        return None

    out = proc.stdout
    passed = 0
    skipped = 0

    m = re.search(r"(\d+) passed", out)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) skipped", out)
    if m:
        skipped = int(m.group(1))

    # "SKIPPED [1] path/to/test.py:120: no flagged entries in this fixture"
    reasons = re.findall(r"^SKIPPED \[\d+\] (.+)$", out, re.MULTILINE)

    if passed == 0 and skipped == 0:
        print(f"  ! no test results parsed from {path}")
        print(out[-800:])
        return None

    return passed, skipped, reasons


def main() -> int:
    total_skipped = 0
    all_reasons: List[str] = []
    ran_any = False

    print("Running suites to count skips...")
    for name, path in SUITES:
        result = run_suite(path)
        if result is None:
            continue
        ran_any = True
        passed, skipped, reasons = result
        total_skipped += skipped
        all_reasons.extend(reasons)
        flag = "" if skipped == 0 else f"   <-- {skipped} skipped"
        print(f"  {name:<12} {passed:>4} passed, {skipped} skipped{flag}")

    if not ran_any:
        print("\nFAIL: no suite could be run; cannot verify skip count.")
        return 1

    print()
    if total_skipped > EXPECTED_MAX_SKIPS:
        print(f"FAIL: {total_skipped} skipped test(s), expected at most "
              f"{EXPECTED_MAX_SKIPS}.")
        if all_reasons:
            print("\nSkipped:")
            for reason in all_reasons:
                print(f"  - {reason}")
        print(
            "\nA skipped test is a test that did not run. Before raising\n"
            "EXPECTED_MAX_SKIPS, check whether the skip condition actually\n"
            "indicates a regression -- that is what it meant the last time\n"
            "(see this script's docstring)."
        )
        return 1

    print(f"OK: {total_skipped} skipped (limit {EXPECTED_MAX_SKIPS}). "
          "Every collected test ran.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
