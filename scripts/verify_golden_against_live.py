#!/usr/bin/env python3
"""Re-check the golden set against BRENDA as it is today.

    python scripts/verify_golden_against_live.py
    python scripts/verify_golden_against_live.py --json

WHY THIS EXISTS
---------------
`scripts/check_golden_freshness.py` reports that nobody has verified the
golden values in N days. Until now there was nothing to verify them WITH:
re-capturing the fixtures was a manual job, so the honest response to the
guard was "yes, I know" rather than an action.

That gap matters more than a missing convenience. `Tests/test_golden_set.py`
compares the resolver against a FIXTURE -- a photograph of BRENDA taken in
July 2026. BRENDA is curated continuously. **The fixture and the resolver
can agree with each other forever while both drift away from the database
they claim to represent**, and no test in the suite would notice.

This is the thing that notices. It runs the REAL parser against the LIVE
page and compares the result to what the golden set pins.

THREE OUTCOMES, NOT TWO
-----------------------
The same discipline the resolver itself runs on:

    matched      BRENDA still reports this value for this system
    drifted      BRENDA reports something DIFFERENT -- the golden set is
                 stale and a real claim in this repository is now wrong
    unreachable  the check could not be performed

"Drifted" and "unreachable" are not the same fact and never collapse into
one. A network failure reported as drift would send someone rewriting
correct golden values; drift reported as a network failure would leave a
wrong number in place. Exit codes distinguish them: 0 matched, 2 drifted,
1 could not check.

WHY IT IS NOT A TEST
--------------------
It needs the network, and BRENDA is somebody else's server. A unit suite
that reaches out on every run is a suite that fails when a third party has
an outage, teaches people to ignore red, and is rude to DSMZ besides -- Lisa
Jeske asked specifically that tools be gentle with their infrastructure.

Run it deliberately, when the freshness guard says it is time.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Callable

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Tests"))



@dataclass
class Outcome:
    golden_id: str
    status: str  # "matched" | "drifted" | "unreachable"
    detail: str
    expected: float | None = None
    observed: float | None = None


def _load_golden() -> list[dict]:
    """Read GOLDEN from the data module.

    Imported rather than re-parsed: a second copy of the golden set is
    exactly the duplicate-source-of-truth this project keeps finding, and
    the whole point here is to compare against what the tests assert, not
    against a restatement of it.

    IT LOADS `Tests/golden_set.py`, NOT `Tests/test_golden_set.py`. The
    first version loaded the test module and its docstring claimed that was
    "without importing pytest" -- which was false, since that module imports
    pytest at the top. Outside a test environment this script died on
    `ModuleNotFoundError: No module named 'pytest'`, which meant
    `check_golden_freshness.py` was telling people to run something that
    could not run.

    The golden data now lives in a module with no test-framework
    dependency, so anything that needs ground truth can read it.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_golden_data", REPO / "Tests" / "golden_set.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Tests/golden_set.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.GOLDEN)


def check_one(
    entry: dict,
    resolve: Callable[[dict], object],
) -> Outcome:
    """Re-resolve a single golden tuple and compare it to what is pinned.

    IT CALLS THE REAL RESOLVER, NOT A REIMPLEMENTATION OF PART OF IT.

    The first version called `parse_brenda_km_html` directly and picked the
    smallest row with `min()`. That is a SECOND selection policy: the
    resolver filters by substrate, applies variant and plausibility rules,
    and chooses among what survives. Running the parser in permissive mode
    and taking a minimum reported the golden set as DRIFTED against the very
    fixture it was verified from -- a false alarm that would have sent
    someone rewriting correct values.

    Two selection policies is the duplicate source of truth this project
    keeps finding, and the verifier is the worst place for it: it exists
    precisely to say whether the resolver still agrees with reality, so it
    must ask the resolver.
    """
    expected = entry["expected"]
    quantity = entry.get("quantity", "km")

    try:
        result = resolve(entry)
    except Exception as exc:  # noqa: BLE001 - any failure is "could not check"
        # Deliberately broad. Every way this can fail -- DNS, TLS, proxy,
        # timeout, 500, or the parser raising on markup that has moved --
        # means the same thing: nothing was learned. None of them mean the
        # value changed, and reporting any of them as drift would send
        # someone rewriting correct golden values.
        return Outcome(
            entry["id"],
            "unreachable",
            f"could not re-resolve EC {entry['ec']}: {type(exc).__name__}: {exc}",
            expected=expected["km"],
        )

    if not getattr(result, "found", False):
        return Outcome(
            entry["id"],
            "drifted",
            (
                f"the resolver no longer finds a {quantity.upper()} for "
                f"{entry['substrate']} in {expected['organism']} "
                f"(source: {getattr(result, 'source', 'unknown')}). Either "
                "BRENDA changed, or the markup moved and the parser reads "
                "nothing; both mean the golden set no longer describes the "
                "live database."
            ),
            expected=expected["km"],
        )

    observed = getattr(result, "value", None)
    if observed is not None and abs(observed - expected["km"]) < 1e-12:
        return Outcome(
            entry["id"],
            "matched",
            f"{quantity.upper()} = {observed} {expected['unit']}, as pinned",
            expected=expected["km"],
            observed=observed,
        )

    return Outcome(
        entry["id"],
        "drifted",
        (
            f"pinned {expected['km']} {expected['unit']}, the resolver now "
            f"returns {observed}. A claim in this repository is out of date."
        ),
        expected=expected["km"],
        observed=observed,
    )


def live_resolver(entry: dict):
    """Re-resolve one golden tuple against the live databases.

    `search_literature=False` keeps this to BRENDA. A PubMed candidate list
    is not a value and cannot confirm or refute a pinned number, so
    including it would only add ways for the check to be slow and
    inconclusive.
    """
    import fallback_logic

    return fallback_logic.resolve_kinetic_value(
        enzyme_ec=entry["ec"],
        organism=entry["organism"],
        substrate=entry["substrate"],
        search_literature=False,
        quantity=entry.get("quantity", "km"),
        allow_cross_species=bool(entry.get("allow_cross_species")),
    )


def run(
    golden: list[dict],
    resolve: Callable[[dict], object],
) -> list[Outcome]:
    return [check_one(entry, resolve) for entry in golden]


def render(outcomes: list[Outcome]) -> str:
    lines = [f"Golden set re-checked against live BRENDA: {len(outcomes)} tuple(s).", ""]
    for outcome in outcomes:
        marker = {
            "matched": "     ok",
            "drifted": "DRIFTED",
            "unreachable": "  ??  ",
        }[outcome.status]
        lines.append(f"  [{marker}] {outcome.golden_id}")
        lines.append(f"            {outcome.detail}")
    lines.append("")

    drifted = [o for o in outcomes if o.status == "drifted"]
    unreachable = [o for o in outcomes if o.status == "unreachable"]

    if drifted:
        lines += [
            f"{len(drifted)} tuple(s) DRIFTED. The golden set no longer matches",
            "BRENDA. Re-capture the fixtures, update the expected values and",
            "verified_on, and check whether anything this project has published",
            "quoted the old number.",
            "",
        ]
    if unreachable:
        lines += [
            f"{len(unreachable)} tuple(s) could NOT be checked. That is not a",
            "pass. Nothing is known about those values today beyond what was",
            "known yesterday.",
            "",
        ]
    if not drifted and not unreachable:
        lines.append("Every pinned value still matches what BRENDA reports today.")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-check the golden set against live BRENDA."
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    golden = _load_golden()
    if not golden:
        print("The golden set is empty; refusing to report success on nothing.")
        return 1

    outcomes = run(golden, live_resolver)

    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(outcomes),
                    "results": [vars(outcome) for outcome in outcomes],
                },
                indent=2,
            )
        )
    else:
        print(render(outcomes), end="")

    if any(outcome.status == "drifted" for outcome in outcomes):
        return 2
    if any(outcome.status == "unreachable" for outcome in outcomes):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
