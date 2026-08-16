#!/usr/bin/env python3
"""How old is Terrium's ground truth?

WHAT THIS CHECKS, AND WHAT IT DOES NOT
--------------------------------------
It checks the AGE of the golden set. It does NOT check that the golden set
is still correct, and it must never be read as though it does.

That distinction is the whole reason this file is careful. A green tick from
a script called "check_golden_freshness" invites exactly one misreading --
"the golden values have been verified" -- and the truthful statement is much
weaker: *nobody has looked at these in N days.* Age is a proxy for staleness
and a poor one; a value can be wrong the day it is captured and right for a
decade.

WHY IT EXISTS
-------------
`Tests/test_golden_set.py` is where every claim Terrium makes about
resolving real literature values bottoms out. Those assertions compare the
resolver against a FIXTURE -- a photograph of BRENDA taken in July 2026.

BRENDA is curated continuously. A reference id can be superseded, a row
corrected, an organism assignment revised. **None of that would fail a
single test**, because the fixture and the resolver would go on agreeing
with each other while both drifted away from the database they claim to
represent.

That is the "check that cannot fail" shape one level below the code: ground
truth that ages silently while everything downstream keeps reporting
"verified". Lisa Jeske's entire reply was about consuming BRENDA
*correctly*; a snapshot nobody revisits is a slow way of failing at that.

WHY IT IS A GUARD AND NOT A TEST
--------------------------------
"Should a human look at this?" is not a correctness question, and a unit
test that starts failing on a calendar date is a test people learn to
disable. This reports, and only fails past a horizon long enough that
crossing it is genuinely a problem rather than a Tuesday.

WHAT TO DO WHEN IT SAYS SO
--------------------------
    python scripts/verify_golden_against_live.py

That answers the question this script cannot: whether the values are still
what BRENDA reports today. A guard that says "someone should look" without
saying what to look WITH is an alarm with no procedure attached, and the
first version of this file was exactly that.

Exit 0 = within the review window. Exit 1 = past the hard horizon.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

#: Past this, the script says so and still exits 0. A nudge, not a blocker.
REVIEW_AFTER_DAYS = 180

#: Past this, it fails. Deliberately generous: a hard failure that arrives
#: too eagerly is a hard failure people route around, and a guard people
#: route around is worse than no guard.
STALE_AFTER_DAYS = 365

#: Loaded, not parsed.
#:
#: The first version read `Tests/test_golden_set.py` with three regexes.
#: That worked and was fragile in a specific way: the golden data has since
#: MOVED to `Tests/golden_set.py`, and a regex-based reader pointed at the
#: old file would have found nothing.
#:
#: It would have said so -- refusing to report success on an empty set is
#: the one thing that version got right -- but "the guard broke" and "the
#: data is fine" would have looked identical, and only one of them is
#: actionable.
#:
#: The data module imports no test framework, precisely so guards can read
#: it. There is no reason to parse a file that can simply be loaded.
GOLDEN_MODULE = REPO / "Tests" / "golden_set.py"


def _load_golden() -> list[dict]:
    """The golden tuples, as data.

    Raises rather than returning empty on failure. An empty list would be
    indistinguishable from "the golden set is fine and contains nothing",
    and this project has repeatedly found checks that examined nothing and
    printed OK.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_golden_data", GOLDEN_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {GOLDEN_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.GOLDEN)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report how old the golden set's BRENDA verification is."
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Override today's date (YYYY-MM-DD). For testing this script.",
    )
    args = parser.parse_args()

    today = (
        dt.date.fromisoformat(args.today)
        if args.today
        else dt.date.today()
    )

    if not GOLDEN_MODULE.is_file():
        print(f"{GOLDEN_MODULE} is missing; refusing to report on an empty set.")
        return 1

    try:
        golden = _load_golden()
    except Exception as exc:  # a broken data module is a loud failure
        print(
            f"Could not load {GOLDEN_MODULE.relative_to(REPO)}: "
            f"{type(exc).__name__}: {exc}\n"
            "Refusing to report success on a golden set that cannot be read."
        )
        return 1

    dates = {entry.get("id", "(unnamed)"): entry.get("verified_on", "")
             for entry in golden}

    if not dates:
        # An empty result means the parsing is wrong, not that the golden
        # set is fine. Reporting success here would be the exact failure
        # this project keeps finding -- a check that examined nothing and
        # printed OK.
        print(
            "No golden tuples found in "
            f"{GOLDEN_MODULE.relative_to(REPO)}. Either the data was removed "
            "or this reader is broken; either way, refusing to report "
            "success on an empty set."
        )
        return 1

    undated = [name for name, value in dates.items() if not value]
    ages: list[tuple[str, int]] = []
    for name, value in dates.items():
        if not value:
            continue
        try:
            ages.append((name, (today - dt.date.fromisoformat(value)).days))
        except ValueError:
            undated.append(name)

    print(f"Golden set: {len(dates)} tuple(s), checked against {today}.")
    for name, age in sorted(ages, key=lambda pair: -pair[1]):
        marker = (
            "STALE" if age > STALE_AFTER_DAYS
            else "review" if age > REVIEW_AFTER_DAYS
            else "ok"
        )
        print(f"  [{marker:>6}] {age:>4}d  {name}")

    if undated:
        print()
        print(f"Golden tuple(s) with no verified_on ({len(undated)}):")
        for name in undated:
            print(f"  - {name}")
        print()
        print(
            "A tuple with no verification date cannot be assessed at all, "
            "which is worse than an old one: an old date is a known "
            "quantity."
        )
        return 1

    oldest = max(age for _, age in ages)
    print()
    print(
        "This checks AGE, not correctness. It cannot tell you whether these "
        "values are still what BRENDA says -- only that nobody has looked."
    )

    if oldest > STALE_AFTER_DAYS:
        print()
        print(
            f"Oldest verification is {oldest} days old, past the "
            f"{STALE_AFTER_DAYS}-day horizon.\n\n"
            "  python scripts/verify_golden_against_live.py\n\n"
            "That re-resolves every golden tuple against BRENDA as it is "
            "today and reports matched, drifted, or could-not-check. "
            "Re-capture the fixtures for anything that drifted, then update "
            "verified_on.\n\n"
            "Every claim Terrium makes about resolving real values rests on "
            "these numbers, and right now nobody has confirmed them in over "
            "a year."
        )
        return 1

    if oldest > REVIEW_AFTER_DAYS:
        print()
        print(
            f"Oldest verification is {oldest} days old, past the "
            f"{REVIEW_AFTER_DAYS}-day review mark but within the "
            f"{STALE_AFTER_DAYS}-day horizon. Worth re-checking; not yet a "
            "build failure.\n\n"
            "  python scripts/verify_golden_against_live.py"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
