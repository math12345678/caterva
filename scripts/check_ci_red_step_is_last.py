#!/usr/bin/env python3
"""A step that is expected to fail must not stand in front of the tests.

WHAT THIS COST BEFORE IT EXISTED
--------------------------------
ADR 0143 wired `check_quickstart_clone_works.py` into CI **deliberately
red**: no documented `git clone` works for a stranger, that is true, and
muting it would be recording the problem instead of fixing it. The argument
was right and is not revisited here.

It was placed at step 32 of 52, next to the other documentation guards.

A GitHub Actions job stops at its first failing step. So the twenty steps
after it never ran:

    - Build guards (verify_build.py --quick)
    - Simulation engine tests
    - Literature layer tests

**Every test in this repository stopped running in CI on 2026-08-21**, and
nothing said so. The signal was in plain sight and unread: every run since
finished in about 55 seconds, where a real suite takes seven minutes.

ADR 0143 argued for keeping a true finding visible and said nothing about
ordering, because the cost of the ordering was not noticed. A guard that is
correct, verified, honest about its limits, and positioned wrongly can still
disable everything behind it.

WHAT THIS CHECKS
----------------
Every step known to be expected-red must come after every step that runs a
test suite or a build guard. There is one such step today; the list is
explicit rather than inferred, because "which steps are allowed to fail" is
a decision somebody makes, not a property a script can read off YAML.

WHAT IT DOES NOT CHECK
----------------------
That the expected-red step is still expected to be red. The day the
repositories are published, `check_quickstart_clone_works` goes green and
this guard keeps passing while enforcing an ordering nobody needs any more.
That is harmless, and saying so is cheaper than a cleverness that guesses.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"

#: Scripts wired into CI while failing on purpose. One entry, one ADR.
EXPECTED_RED = {
    "check_quickstart_clone_works.py": "ADR 0143 — the repository is private",
}

#: Substrings identifying a step whose whole purpose is to run something
#: substantial. Losing one of these to an earlier failure is the harm.
MUST_RUN_FIRST = ("pytest", "verify_build.py")


def steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["test"]["steps"]


def _positions(all_steps: list[dict]) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    red: list[tuple[int, str]] = []
    heavy: list[tuple[int, str]] = []
    for index, step in enumerate(all_steps, start=1):
        run = step.get("run") or ""
        name = step.get("name") or step.get("uses") or "?"
        if any(script in run for script in EXPECTED_RED):
            # `--selftest` is a different step and is genuinely expected to
            # pass, so it does not gate anything.
            if "--selftest" not in run:
                red.append((index, name))
        if any(marker in run for marker in MUST_RUN_FIRST):
            heavy.append((index, name))
    return red, heavy


def _selftest() -> int:
    """Prove it can say no, on text rather than on the tree.

    A guard checked only against a passing repository passes when it is
    doing nothing, which is the shape it exists to catch elsewhere.
    """
    bad = [
        {"name": "clone guard", "run": "python scripts/check_quickstart_clone_works.py"},
        {"name": "tests", "run": "python -m pytest -v"},
    ]
    good = list(reversed(bad))

    failures = 0
    red, heavy = _positions(bad)
    if red and heavy and red[0][0] < heavy[0][0]:
        print("  [ok] detects an expected-red step placed before the tests")
    else:
        print("  [SELFTEST FAILED] did not detect the bad ordering")
        failures += 1

    red, heavy = _positions(good)
    if red and heavy and red[0][0] > heavy[0][0]:
        print("  [ok] accepts the same two steps in the right order")
    else:
        print("  [SELFTEST FAILED] rejected a correct ordering")
        failures += 1

    if not _positions([{"name": "x", "run": "echo hi"}])[0]:
        print("  [ok] an unrelated step is neither red nor heavy")
    else:
        print("  [SELFTEST FAILED] matched a step it should ignore")
        failures += 1

    if failures:
        print(f"\nSELFTEST FAILED: {failures} case(s).")
        return 1
    print("\nSelftest passed.")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    all_steps = steps()
    red, heavy = _positions(all_steps)

    if not red:
        print("No expected-red step in the workflow. Nothing to order.")
        print(f"  (Looking for: {', '.join(EXPECTED_RED)})")
        return 0

    if not heavy:
        print("FAIL: no step in the `test` job runs pytest or verify_build.")
        print("  That is a bigger problem than the ordering this checks.")
        return 1

    last_heavy = max(heavy)
    broken = [(i, n) for i, n in red if i < last_heavy[0]]

    print(f"Steps in the `test` job: {len(all_steps)}")
    print(f"  last step that runs something substantial: #{last_heavy[0]} {last_heavy[1]}")
    for index, name in red:
        print(f"  expected-red step: #{index} {name}")

    if not broken:
        print("\nOK: every expected-red step runs after the test suites.")
        return 0

    print("\nFAIL: a step expected to fail stands in front of the tests.\n")
    for index, name in broken:
        script = next(s for s in EXPECTED_RED if s in (all_steps[index - 1].get("run") or ""))
        print(f"  #{index} {name}")
        print(f"      {script} — {EXPECTED_RED[script]}")
    print(
        f"\n  A job stops at its first failing step, so everything from\n"
        f"  #{broken[0][0] + 1} to #{last_heavy[0]} will not run — including the test\n"
        "  suites. This happened once already: from 2026-08-21 every run\n"
        "  finished in ~55 seconds instead of seven minutes, and nothing\n"
        "  said the tests had stopped.\n\n"
        "  Move the step to the end of the job. The build stays red, which\n"
        "  is the point of it; the tests come back, which was never meant\n"
        "  to be the price."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
