#!/usr/bin/env python3
"""A literature runner that answers from a fixture instead of the network.

WHY
---
`src/cli/__tests__/cliEndToEnd.test.ts` spawns the real runner, which calls
BRENDA and PubMed. In any environment without network access to those hosts
it does not fail -- it HANGS, on a 120-second per-invocation timeout, and
the suite is simply never run. Three consecutive verification passes have
had to report it as "not verified", which is honest and is not a substitute
for verifying it.

This stub is pointed at by `TERRIUM_LITERATURE_RUNNER`, a seam that already
existed for exactly this purpose. It exercises the REAL subprocess path --
spawn, stdin, exit code, stdout parsing -- against canned JSON.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not mock the resolver module. The bugs in that path have all been
in the boundary rather than the logic: the first version of the resolver
discarded a structured `{"ok": false, "error": "403 Forbidden"}` because the
process also exited 1, replacing a precise cause with "exited with code 1".
A module mock cannot catch that. A real subprocess can.

The canned values are real BRENDA figures already used in the golden set,
so an assertion here and an assertion there cannot disagree about what
lactate dehydrogenase's Km is.
"""
from __future__ import annotations

import json
import sys

#: Keyed by (quantity). Values match Tests/test_golden_set.py's G1/G4.
RESPONSES = {
    "km": {
        "ok": True,
        "found": True,
        "km": 10.73,
        "unit": "mM",
        "organism": "Homo sapiens",
        "source": "brenda_exact",
        "crossSpecies": False,
        "relatedness": [],
        "reliability": {
            "assayCompleteness": {
                "grade": "complete",
                "reason": "Assay reports pH 7.4 and 25.0 C, meeting STRENDA's minimum.",
            },
            "conditionProximity": {
                "grade": "not_assessed",
                "reason": "No reference conditions were supplied, so proximity was not assessed.",
            },
            "organismMatch": {
                "grade": "exact",
                "reason": "Measured in Homo sapiens, the organism asked about.",
            },
            "noAggregateReason": "Reported separately and deliberately not combined. ADR 0024.",
        },
        "assayConditions": {
            "ph": 7.4,
            "temperatureC": 25.0,
            "buffer": None,
            "unreported": [],
        },
        "citation": {
            "source": "BRENDA",
            "reference_id": "740253",
            "url": "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
        },
        "literatureCandidates": [],
        "logs": ["stub runner: canned response, no network"],
    },
    "kcat": {
        "ok": True,
        "found": False,
        "source": "not_found",
        "crossSpeciesOrganismsAvailable": [],
        "relatedness": [],
        "literatureCandidates": [],
        "logs": ["stub runner: no kcat in the fixture"],
    },
}


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    quantity = payload.get("quantity", "km")

    # The stub honours allowCrossSpecies rather than ignoring it, so a test
    # asserting the opt-in reaches the runner is testing the real hop.
    response = dict(RESPONSES.get(quantity, RESPONSES["kcat"]))
    response["logs"] = list(response.get("logs", [])) + [
        f"allowCrossSpecies={payload.get('allowCrossSpecies') is True}",
        f"physiologicalReference={'yes' if payload.get('physiologicalReference') else 'no'}",
    ]

    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    sys.exit(main())
