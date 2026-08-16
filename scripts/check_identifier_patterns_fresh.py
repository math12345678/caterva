#!/usr/bin/env python3
"""The identifiers.org accession patterns are a dated copy. Is it still true?

`Terium/core/miriam.py` decides whether Terrium may mint a resolvable URI
for an accession, using patterns captured from the identifiers.org registry
into `Tests/fixtures/identifiers/identifiers_org_namespaces.json`.

Those patterns are the only thing standing between a real citation and a
fabricated one. The cautionary case is BRENDA: its namespace covers **EC
numbers**, so a BRENDA reference id like 649716 has no URI form at all, and
minting `identifiers.org/brenda:649716` would produce a machine-actionable
citation resolving to nothing.

A dated copy is right on the day it is taken and drifts silently after. This
is the same problem as the golden set and it gets the same treatment:
`check_golden_freshness.py` says how old the capture is, this says whether it
is still *true*.

## Three outcomes, three exit codes

    0  matched     — the live registry agrees with the capture
    2  drifted     — the registry has changed; the capture is stale
    1  unreachable — the registry could not be consulted

The third is not folded into either of the others. Reporting "matched" when
the network was down would make this a check that cannot fail, and reporting
"drifted" would send someone hunting a registry change that never happened.
Terrium keeps these apart everywhere else (resolution exit codes, relatedness
verdicts, golden verification) and a guard is not exempt from its own rule.

## What drift would mean

A **widened** pattern means Terrium is refusing accessions that are in fact
valid — it under-annotates, which is the safe direction and still wrong.

A **narrowed** pattern means Terrium is minting URIs the registry no longer
considers well-formed — it fabricates, which is the direction this whole
module exists to prevent.

Both are reported; neither is auto-applied. Rewriting the fixture from the
live registry without a person looking would mean a registry change silently
alters what Terrium is willing to claim.

Usage:
    python scripts/check_identifier_patterns_fresh.py
    python scripts/check_identifier_patterns_fresh.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "Tests" / "fixtures" / "identifiers" / "identifiers_org_namespaces.json"
REGISTRY = "https://registry.api.identifiers.org/restApi/namespaces/search/findByPrefix"
TIMEOUT = 20


def fetch(prefix: str) -> dict:
    import httpx

    response = httpx.get(REGISTRY, params={"prefix": prefix}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def main() -> int:
    as_json = "--json" in sys.argv

    if not FIXTURE.exists():
        print(f"UNREACHABLE  {FIXTURE.relative_to(REPO)} does not exist.")
        print("      Nothing to compare. This is not 'the patterns are fine'.")
        return 1

    captured = json.loads(FIXTURE.read_text(encoding="utf-8"))
    namespaces = captured["namespaces"]

    matched: list[str] = []
    drifted: list[dict] = []
    unreachable: list[tuple[str, str]] = []

    for prefix, spec in sorted(namespaces.items()):
        try:
            live = fetch(prefix)
        except Exception as exc:  # httpx errors, proxies, DNS, TLS, JSON
            unreachable.append((prefix, f"{type(exc).__name__}: {exc}"))
            continue

        live_pattern = live.get("pattern")
        if live_pattern is None:
            unreachable.append((prefix, "registry returned no 'pattern' field"))
            continue

        if live_pattern == spec["pattern"]:
            matched.append(prefix)
        else:
            drifted.append(
                {
                    "prefix": prefix,
                    "captured": spec["pattern"],
                    "live": live_pattern,
                    "capturedSample": spec.get("sampleId"),
                    "liveSample": live.get("sampleId"),
                }
            )

    verdict = "matched" if drifted == [] and unreachable == [] else (
        "drifted" if drifted else "unreachable"
    )

    if as_json:
        print(
            json.dumps(
                {
                    "verdict": verdict,
                    "capturedOn": captured.get("_captured_on"),
                    "matched": matched,
                    "drifted": drifted,
                    "unreachable": [
                        {"prefix": p, "reason": r} for p, r in unreachable
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Capture dated {captured.get('_captured_on')}, {len(namespaces)} namespace(s).")
        for prefix in matched:
            print(f"  matched      {prefix}")
        for entry in drifted:
            print(f"  DRIFTED      {entry['prefix']}")
            print(f"      captured: {entry['captured']}")
            print(f"      live:     {entry['live']}")
        for prefix, reason in unreachable:
            print(f"  unreachable  {prefix}  ({reason})")

        if verdict == "matched":
            print("\nOK  every captured pattern still matches the live registry.")
            print("    Not checked: whether any accession Terrium holds actually")
            print("    exists. This compares patterns, not records.")
        elif verdict == "drifted":
            print("\nDRIFTED  the registry has changed since the capture.")
            print("    A WIDENED pattern means Terrium now refuses valid accessions")
            print("    (under-annotates — safe direction, still wrong).")
            print("    A NARROWED pattern means Terrium mints URIs the registry no")
            print("    longer considers well-formed (fabricates — the direction this")
            print("    module exists to prevent).")
            print("    Re-capture deliberately; do not let a script rewrite it.")
        else:
            print("\nUNREACHABLE  the registry could not be consulted.")
            print("    This says nothing about whether the patterns are current.")
            print("    'Could not check' is not 'checked and fine'.")

    return {"matched": 0, "drifted": 2, "unreachable": 1}[verdict]


if __name__ == "__main__":
    sys.exit(main())
