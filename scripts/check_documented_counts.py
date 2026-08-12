"""
Documented-counts guard for Terrium.

Verifies that the test counts and domain count printed in README.md match
what the repository actually contains.

Why this exists
---------------
Three README numbers had drifted silently and were found by hand during the
Stage 7 audit:

    make test           claimed   524 tests   actual 1,040
    Terium/tests/    claimed   833 tests   actual   858
    Tests/              claimed   124 tests   actual   182

and the domain count was stated twice in the same file with two different
values ("Eight" in the prose, "Ten" in the detailed list).

These are exactly the class of claim Rule 1 governs: a factual assertion
that no executable check covered, so nothing objected as it went stale. The
Stage 4 amendment applies -- *a guard is not delivered until something runs
it unasked* -- so this is wired into verify_domain.sh and CI rather than
being a script someone remembers to run.

The counts are collected from pytest itself (--collect-only), not
recomputed by a parallel implementation that could drift in its own way.

Usage:
    python scripts/check_documented_counts.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

# Suites `make test` runs, in the order it runs them.
SUITES = [
    ("engine", REPO_ROOT / "Terium" / "tests"),
    ("literature", REPO_ROOT / "Tests"),
]


def collect_count(path: Path) -> int | None:
    """Number of tests pytest collects under `path`.

    Returns None (rather than raising or guessing) when collection cannot
    run -- a missing dependency must not be reported as a count mismatch.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(path), "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(REPO_ROOT),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  ! could not collect {path.name}: {exc}")
        return None

    # `-q` prints "path/to/test_file.py: N" per file, then a summary line.
    total = 0
    seen = False
    for line in proc.stdout.splitlines():
        match = re.match(r"^\S+\.py:\s*(\d+)\s*$", line.strip())
        if match:
            total += int(match.group(1))
            seen = True

    if not seen:
        # Fall back to the summary line ("182 tests collected in 0.31s").
        match = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
        if match:
            return int(match.group(1))
        print(f"  ! no collectable tests found under {path}")
        return None

    return total


def documented_numbers(text: str) -> dict:
    """Pull the claimed counts out of README.md."""
    found = {}

    # "make test      # runs all 1,040 tests (858 engine + 182 literature)"
    m = re.search(r"make test\s+#\s*runs all ([\d,]+) tests", text)
    if m:
        found["make_test"] = int(m.group(1).replace(",", ""))

    # Repo-structure block: "└── tests/              858 tests"
    m = re.search(r"tests/\s+([\d,]+) tests", text)
    if m:
        found["engine"] = int(m.group(1).replace(",", ""))

    # "└── ...                 182 tests"
    m = re.search(r"\.\.\.\s+([\d,]+) tests", text)
    if m:
        found["literature"] = int(m.group(1).replace(",", ""))

    return found


def documented_guard_counts(text: str) -> List[Tuple[int, int]]:
    """Every "<N> guard scripts" claim in the README, with its line number.

    Added after the README was found claiming "all 14 guard scripts" and
    "~20 guard scripts" on two different lines while `scripts/` held 21.
    Both numbers had been true once. Neither was checked by anything, so
    both rotted quietly — and a stale count in the one file newcomers read
    is a small lie that makes every other number in it less trustworthy.

    Constitution Rule 1: every factual claim is checked, not only numerical
    ones about science. A count of files in this repository is about as
    checkable as a claim gets.

    "~20" is accepted as approximate: the tilde is a claim about the order
    of magnitude, and holding it to exactness would push people toward
    vaguer wording rather than truer wording.
    """
    claims: List[Tuple[int, int]] = []
    pattern = re.compile(r"(~)?\s*(\d+)\s+guard scripts?\b", re.IGNORECASE)
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            approximate = match.group(1) is not None
            value = int(match.group(2))
            claims.append((lineno, -value if approximate else value))
    return claims


def documented_domain_counts(text: str) -> List[Tuple[int, int]]:
    """Every "<N> simulation domains" claim, with its line number.

    Returned as a list so that two claims disagreeing with *each other* is
    detectable, which is how the original defect presented.
    """
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
        "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    }
    claims: List[Tuple[int, int]] = []
    pattern = re.compile(r"\b([A-Za-z]+|\d+)\s+simulation domains\b", re.IGNORECASE)
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            token = match.group(1).lower()
            value = words.get(token)
            if value is None and token.isdigit():
                value = int(token)
            if value is not None:
                claims.append((lineno, value))
    return claims


def main() -> int:
    if not README.exists():
        print(f"FAIL: {README} not found")
        return 1

    text = README.read_text(encoding="utf-8")
    claimed = documented_numbers(text)
    failures: List[str] = []
    skipped = False

    print("Collecting actual test counts...")
    actual = {}
    for name, path in SUITES:
        count = collect_count(path)
        if count is None:
            skipped = True
            continue
        actual[name] = count
        print(f"  {name:<12} {count}")

    if "engine" in actual and "literature" in actual:
        actual["make_test"] = actual["engine"] + actual["literature"]

    for key in ("make_test", "engine", "literature"):
        if key not in claimed:
            failures.append(f"README no longer states a '{key}' test count")
            continue
        if key not in actual:
            continue
        if claimed[key] != actual[key]:
            failures.append(
                f"{key}: README says {claimed[key]:,}, actual is {actual[key]:,}"
            )

    # Domain counts must agree with each other. The true number is not
    # derived here: `DISPATCH` includes a run-mode (ssa_replicates) and a
    # generic ingest path (sbml) that are not teaching domains, so any
    # automatic count would encode a judgment call. Internal consistency is
    # checkable without making that call, and it is what actually broke.
    claims = documented_domain_counts(text)
    if len(claims) < 2:
        failures.append(
            f"expected at least 2 'N simulation domains' claims in README, found {len(claims)}"
        )
    else:
        values = {value for _, value in claims}
        if len(values) > 1:
            detail = ", ".join(f"line {ln}: {v}" for ln, v in claims)
            failures.append(f"README states conflicting domain counts ({detail})")
        else:
            print(f"  domains      {claims[0][1]} (consistent across {len(claims)} claims)")

    actual_guards = len(list((REPO_ROOT / "scripts").glob("check_*.py")))
    guard_claims = documented_guard_counts(text)
    if not guard_claims:
        failures.append(
            "README no longer states a guard-script count. It stated two, "
            "and both had gone stale; removing the claim rather than fixing "
            "it is not the intended resolution."
        )
    else:
        for lineno, claimed_guards in guard_claims:
            approximate = claimed_guards < 0
            value = abs(claimed_guards)
            # An approximate claim is allowed to be off by a couple; an
            # exact one is not allowed to be off at all.
            tolerance = 3 if approximate else 0
            if abs(value - actual_guards) > tolerance:
                failures.append(
                    f"README line {lineno} claims "
                    f"{'~' if approximate else ''}{value} guard scripts; "
                    f"scripts/ contains {actual_guards}"
                )
        if not any("guard scripts" in f for f in failures):
            print(f"  guards       {actual_guards} (matches {len(guard_claims)} README claim(s))")

    print()
    if failures:
        print("FAIL: documented counts do not match reality")
        for failure in failures:
            print(f"  - {failure}")
        print("\nUpdate README.md, or the counts above if the change was intended.")
        return 1

    if skipped:
        print("OK (partial): every count that could be collected matches README.")
        return 0

    print("OK: README test counts and domain counts match the repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
