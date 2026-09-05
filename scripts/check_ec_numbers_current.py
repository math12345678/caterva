#!/usr/bin/env python3
"""Every EC number Terrium ships must still be the current one.

WHAT THIS COMES FROM
--------------------
`enzymes.ts` listed cytochrome c oxidase as **EC 1.9.3.1**. IUBMB
transferred that number to **EC 7.1.1.9** in 2018, when class EC 7
(translocases) was created -- cytochrome c oxidase pumps protons across a
membrane, so it belongs there. Expasy's record for the old number has read
`Transferred entry: 7.1.1.9` ever since.

A transferred EC number is the same failure shape as a DOI that resolves to
the wrong paper, and it hid for the same reason: **it still looks like a
working identifier.** Nothing 404s. A lookup keyed on it does not obviously
break; it silently asks the wrong question. Only reading the record catches
it, which is ADR 0076's lesson applied to a different namespace.

Checked against Expasy on 2026-09-05, that was the only stale entry of the
24 in the table. The point of this guard is that nobody had ever asked.

WHY A SNAPSHOT
--------------
The authoritative answer lives on enzyme.expasy.org, and a guard that needs
the network to pass turns every offline run red -- which is how a guard
earns the habit of being skipped (ADR 0028).

So the default path is offline and compares `enzymes.ts` against a
committed snapshot: every EC the code ships must be recorded there as
`current`. That catches the case that actually happens -- somebody adds an
enzyme, or edits an EC, without checking it -- because a new or changed
number is simply absent from the snapshot and fails.

What it cannot catch is IUBMB transferring a number tomorrow. Nothing
offline can. `--live` re-asks Expasy and is where that is caught; the
snapshot records when someone last did.

This is the same division `check_golden_freshness.py` draws, and the same
caveat applies: a green tick here means "these numbers were current when
someone last looked", not "these numbers are current".

Usage:
    python scripts/check_ec_numbers_current.py            # offline
    python scripts/check_ec_numbers_current.py --live     # re-ask Expasy
    python scripts/check_ec_numbers_current.py --live --write
    python scripts/check_ec_numbers_current.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
ENZYMES_TS = (
    REPO_ROOT
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
    / "enzymes.ts"
)
SNAPSHOT = REPO_ROOT / "Tests" / "fixtures" / "ec_numbers_verified.json"

EXPASY = "https://enzyme.expasy.org/EC/{ec}.txt"

#: How long before the snapshot is old enough to say so. Not a failure:
#: EC numbers change on IUBMB's schedule, not ours, and a hard expiry
#: would make an offline guard fail for the passage of time.
STALE_AFTER_DAYS = 365

#: Matches the `enzymeName` / `ecNumber` pair in each ENZYMES entry. The
#: two fields are separated by `substrates`, so this deliberately spans it
#: rather than matching either field alone -- an ecNumber with no name
#: beside it would otherwise be reported under whatever name came last.
ENTRY = re.compile(
    r'enzymeName:\s*"(?P<name>[^"]+)",'
    r'(?:.|\n)*?'
    r'ecNumber:\s*"(?P<ec>[0-9]+(?:\.[0-9\-]+){3})"'
)


def declared_ec_numbers(source: str) -> List[Tuple[str, str]]:
    """(enzymeName, ecNumber) for every entry in enzymes.ts."""
    return [(m.group("name"), m.group("ec")) for m in ENTRY.finditer(source)]


def load_snapshot() -> dict:
    if not SNAPSHOT.is_file():
        return {}
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def audit_offline(source: str, snapshot: dict) -> List[str]:
    """Every declared EC must be recorded as current. Pure, for --selftest."""
    failures: List[str] = []
    declared = declared_ec_numbers(source)

    if not declared:
        # A matcher that found nothing would pass every check below while
        # checking nothing -- the shape this repository keeps rediscovering.
        return [
            f"parsed 0 EC numbers out of {ENZYMES_TS.name}; the pattern no "
            f"longer matches the table, so nothing was checked"
        ]

    entries = snapshot.get("entries", {})
    for name, ec in declared:
        record = entries.get(ec)
        if record is None:
            failures.append(
                f"{name}: EC {ec} is shipped by {ENZYMES_TS.name} but is not "
                f"in {SNAPSHOT.name}. Verify it against Expasy and re-run "
                f"with --live --write."
            )
            continue
        if record.get("status") != "current":
            failures.append(
                f"{name}: EC {ec} is recorded as "
                f"{record.get('status')!r}"
                + (
                    f" -> {record['transferredTo']}"
                    if record.get("transferredTo")
                    else ""
                )
                + ". A transferred number still resolves; it just asks the "
                "wrong question."
            )
    return failures


def fetch_expasy(ec: str) -> Tuple[str, str]:
    """Return (status, detail) for one EC number.

    status is "current", "transferred", "deleted" or "unreachable".
    """
    try:
        with urllib.request.urlopen(EXPASY.format(ec=ec), timeout=30) as fh:
            raw = fh.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "deleted", "Expasy has no record for this number (404)"
        return "unreachable", f"HTTP {exc.code}"
    except Exception as exc:  # network down, DNS, timeout
        return "unreachable", f"{type(exc).__name__}: {exc}"

    de = " ".join(
        line[5:].strip() for line in raw.splitlines() if line.startswith("DE ")
    ).rstrip(".")
    moved = re.search(r"Transferred entry:\s*([0-9.\- ,and]+)", de)
    if moved:
        return "transferred", moved.group(1).strip()
    if "Deleted entry" in de:
        return "deleted", de
    return "current", de


def run_live(source: str, write: bool) -> int:
    declared = declared_ec_numbers(source)
    print(f"Asking Expasy about {len(declared)} EC number(s)\n")

    entries: Dict[str, dict] = {}
    failures: List[str] = []
    unreachable = 0

    for name, ec in declared:
        status, detail = fetch_expasy(ec)
        if status == "unreachable":
            unreachable += 1
            print(f"  ?  {ec:<11} {name:<34} {detail}")
            continue
        mark = "ok" if status == "current" else "!!"
        print(f"  {mark} {ec:<11} {name:<34} {detail[:44]}")
        record = {"enzyme": name, "status": status, "acceptedName": detail}
        if status == "transferred":
            record["transferredTo"] = detail
            record["acceptedName"] = None
            failures.append(
                f"{name}: EC {ec} was TRANSFERRED to {detail}. It still "
                f"resolves, so nothing breaks -- it just identifies the "
                f"wrong entry."
            )
        elif status == "deleted":
            failures.append(f"{name}: EC {ec} has been deleted from the list.")
        entries[ec] = record

    if unreachable:
        # Reported, never silently tolerated: a run that reached nothing
        # must not print the same summary as a run that verified everything.
        print(
            f"\n  {unreachable} number(s) could not be reached. Those were "
            f"NOT verified and are not recorded."
        )

    if write:
        if unreachable:
            print(
                "\nRefusing to write the snapshot from an incomplete run: it "
                "would record fewer numbers as checked than the table ships, "
                "and the offline guard would then fail for the wrong reason.",
                file=sys.stderr,
            )
            return 1
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(
            json.dumps(
                {
                    "source": "https://enzyme.expasy.org/",
                    "checkedOn": date.today().isoformat(),
                    "note": (
                        "Status of every EC number shipped in "
                        "api-server/src/lib/enzymes.ts, as Expasy reported "
                        "it on checkedOn. Regenerate with "
                        "scripts/check_ec_numbers_current.py --live --write."
                    ),
                    "entries": entries,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {SNAPSHOT.relative_to(REPO_ROOT)}")

    if failures:
        print("\nFAIL: EC numbers that are no longer current\n", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"\nOK: {len(entries)} EC number(s) current on Expasy")
    return 0


def selftest() -> int:
    """Break each check and confirm it fails."""
    source = ENZYMES_TS.read_text(encoding="utf-8")
    snapshot = load_snapshot()

    baseline = audit_offline(source, snapshot)
    if baseline:
        print(
            "SELFTEST FAIL: the tree already fails, so mutations prove "
            "nothing:",
            file=sys.stderr,
        )
        for f in baseline:
            print(f"  - {f}", file=sys.stderr)
        return 1

    ok = True
    cases: List[Tuple[str, str, dict, str]] = [
        (
            "an EC number reverted to its transferred form",
            source.replace('ecNumber: "7.1.1.9"', 'ecNumber: "1.9.3.1"'),
            snapshot,
            "not in ec_numbers_verified.json",
        ),
        (
            "a new enzyme added without verifying its EC",
            source.replace(
                'enzymeName: "catalase",',
                'enzymeName: "catalase",\n    ecNumber: "9.9.9.9",',
                1,
            ),
            snapshot,
            "EC 9.9.9.9",
        ),
        (
            "the snapshot records a number as transferred",
            source,
            {
                **snapshot,
                "entries": {
                    **snapshot.get("entries", {}),
                    "7.1.1.9": {
                        "enzyme": "cytochrome c oxidase",
                        "status": "transferred",
                        "transferredTo": "9.9.9.9",
                    },
                },
            },
            "transferred",
        ),
        (
            "the parser stops matching the table",
            "export const ENZYMES = [];",
            snapshot,
            "parsed 0 EC numbers",
        ),
    ]

    for label, mutated_source, mutated_snapshot, expected in cases:
        if mutated_source == source and mutated_snapshot == snapshot:
            print(f"  NO-OP  {label}: mutation changed nothing", file=sys.stderr)
            ok = False
            continue
        found = audit_offline(mutated_source, mutated_snapshot)
        caught = any(expected in f for f in found)
        print(f"  {'caught' if caught else 'MISSED'}  {label}")
        if not caught:
            print(
                f"           expected a failure mentioning {expected!r}; "
                f"got: {found or 'nothing'}",
                file=sys.stderr,
            )
            ok = False

    if ok:
        print(f"selftest OK: {len(cases)} mutations, all caught")
        return 0
    print("SELFTEST FAILED", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="re-ask Expasy (needs network)")
    parser.add_argument("--write", action="store_true",
                        help="with --live, refresh the snapshot")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if not ENZYMES_TS.is_file():
        print(f"FAIL: {ENZYMES_TS} not found", file=sys.stderr)
        return 1
    source = ENZYMES_TS.read_text(encoding="utf-8")

    if args.selftest:
        return selftest()
    if args.live:
        return run_live(source, args.write)
    if args.write:
        print("--write requires --live", file=sys.stderr)
        return 1

    snapshot = load_snapshot()
    if not snapshot:
        print(
            f"FAIL: {SNAPSHOT} is missing, so no EC number has been "
            f"verified. Run with --live --write.",
            file=sys.stderr,
        )
        return 1

    failures = audit_offline(source, snapshot)
    if failures:
        print("FAIL: EC numbers that nobody has verified\n", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    checked_on = snapshot.get("checkedOn", "never")
    age = ""
    try:
        days = (date.today() - datetime.fromisoformat(checked_on).date()).days
        age = f", {days} day(s) ago"
        if days > STALE_AFTER_DAYS:
            age += " -- worth re-running with --live"
    except ValueError:
        pass
    print(
        f"OK: {len(declared_ec_numbers(source))} EC number(s) all recorded "
        f"current as of {checked_on}{age}."
    )
    print(
        "    This says nobody has found them stale, not that they are "
        "current today; only --live can say that."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
