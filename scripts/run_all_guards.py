#!/usr/bin/env python3
"""Run every guard and report all of them, instead of stopping at the first.

``make guards`` is a sequential list of recipe lines. Make stops at the first
one that fails, so the guards after it do not run -- and their silence reads
exactly like success.

That is not hypothetical. Across an entire session of work, ``make guards``
died at the fifth of twenty-eight guards (`check_forbidden_packages.py`,
failing on an ADR index entry pointing at another agent's uncommitted files).
**Twenty-three guards never executed once**, and the session's notes repeatedly
recorded "only the two known failures remain" on the strength of having seen
five. Running them individually then found a guard wiring violation introduced
that same session, which nothing had reported.

Fail-fast is the right default for a *gate*: the first failure is the one to
fix, and the rest cost time nobody needs to spend. It is the wrong default for
a *report*, and the two had been the same command.

So this runs all of them and prints a table. It exits non-zero if anything is
wrong, so it can still be used as a gate -- but it is worth the extra minutes
precisely when somebody wants to know the whole state rather than the next
thing to fix.

Four outcomes per guard, not two:

    OK            exit 0
    FAIL          exit 1 or 2 -- it checked, and found a problem
    UNDETERMINED  exit 3 -- it could not check; not a pass and not a failure
    TIMEOUT       it did not finish, so its verdict is unknown

TIMEOUT is reported as its own state rather than folded into FAIL, because
one of these guards runs both pytest suites and legitimately takes minutes. A
timeout is this runner's limit, not the guard's verdict, and printing it as a
failure would be this runner making a claim the guard never made.

The list of guards is read from the Makefile's ``guards`` target rather than
duplicated here. Two lists would drift, and the drift would be invisible in
exactly the way this script exists to prevent.

Usage:
    python scripts/run_all_guards.py [--timeout SECONDS] [--list]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = REPO_ROOT / "Makefile"

#: Per-guard wall-clock limit. Generous: `check_no_silent_skips.py` runs both
#: pytest suites end to end and takes minutes on a warm machine.
DEFAULT_TIMEOUT_SECONDS = 900


def guard_invocations() -> tuple[list[list[str]], str | None]:
    """Every ``scripts/*.py`` invocation in the Makefile's ``guards`` target.

    Returns ``(invocations, problem)``. A problem is not an empty list: a
    Makefile this cannot parse means the runner does not know what to run,
    and reporting "0 guards, all fine" would be the exact failure this file
    is about.
    """
    if not MAKEFILE.exists():
        return [], f"{MAKEFILE.name} not found at {REPO_ROOT}"

    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^guards:.*?\n((?:\t.*\n|\n)*)", text, re.MULTILINE)
    if match is None:
        return [], "no `guards:` target found in the Makefile"

    invocations: list[list[str]] = []
    for line in match.group(1).splitlines():
        found = re.search(r"(scripts/[A-Za-z0-9_]+\.py)((?:\s+--[A-Za-z-]+)*)", line)
        if found is None:
            continue
        invocations.append([found.group(1), *found.group(2).split()])

    if not invocations:
        return [], "the `guards:` target invokes no scripts/*.py -- did it move?"

    return invocations, None


def classify(returncode: int, timed_out: bool) -> str:
    if timed_out:
        return "TIMEOUT"
    if returncode == 0:
        return "OK"
    if returncode == 3:
        return "UNDETERMINED"
    return "FAIL"


def run_one(invocation: list[str], timeout: int) -> tuple[str, float, str]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, *invocation],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.monotonic() - started
        output = (result.stdout or "") + (result.stderr or "")
        return classify(result.returncode, False), elapsed, output
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.monotonic() - started, ""


def first_meaningful_line(output: str) -> str:
    """The line a reader needs, not the first line printed.

    Several guards print a progress table before their verdict, so the first
    line of output is routinely a column header. Prefer a line that announces
    a verdict; fall back to the last non-empty line, which is where a verdict
    usually ends up.
    """
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "(no output)"
    for line in lines:
        if re.match(r"^\s*(FAIL|ERROR|UNDETERMINED|UNREACHABLE|MISSING|BROKEN)", line):
            return line.strip()
    return lines[-1].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--list", action="store_true", help="print the guards and exit")
    args = parser.parse_args()

    invocations, problem = guard_invocations()
    if problem is not None:
        print(f"UNDETERMINED  {problem}")
        print("  No guard was run. This is not a clean result.")
        return 3

    if args.list:
        for inv in invocations:
            print(" ".join(inv))
        return 0

    print(f"Running all {len(invocations)} guards from the Makefile's `guards` target.")
    print("Unlike `make guards`, this does not stop at the first failure.\n")

    results: list[tuple[str, str, float, str]] = []
    width = max(len(inv[0]) for inv in invocations)

    for inv in invocations:
        label = " ".join(inv)
        state, elapsed, output = run_one(inv, args.timeout)
        results.append((label, state, elapsed, output))
        mark = {"OK": "  ok", "FAIL": "FAIL", "UNDETERMINED": "  ??", "TIMEOUT": "TIME"}[state]
        print(f"  {mark}  {inv[0]:<{width}}  {elapsed:6.1f}s")

    failures = [r for r in results if r[1] == "FAIL"]
    undetermined = [r for r in results if r[1] == "UNDETERMINED"]
    timeouts = [r for r in results if r[1] == "TIMEOUT"]
    total = sum(r[2] for r in results)

    print(f"\n{len(results)} guards in {total:.0f}s.")
    print(
        f"  ok {len(results) - len(failures) - len(undetermined) - len(timeouts)}"
        f" · failed {len(failures)}"
        f" · undetermined {len(undetermined)}"
        f" · timed out {len(timeouts)}"
    )

    for heading, group in (
        ("FAILED", failures),
        ("UNDETERMINED (could not check -- not a pass)", undetermined),
        ("TIMED OUT (verdict unknown, not a failure)", timeouts),
    ):
        if not group:
            continue
        print(f"\n{heading}:")
        for label, _, _, output in group:
            print(f"  {label}")
            print(f"      {first_meaningful_line(output)}")

    if failures or timeouts:
        return 1
    if undetermined:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
