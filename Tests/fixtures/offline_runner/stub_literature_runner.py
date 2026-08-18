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
    # A RESOLVED VALUE THE EVIDENCE DID NOT CHOOSE (Bakker; ADR 0048/0051).
    #
    # The real LDH turnover frontier, abbreviated: rows the non-dominated
    # filter could not separate, whose values disagree 306-fold. `min()`
    # returns 21.1 and the CLI printed it alone until ADR 0114.
    #
    # The third candidate carries no `value`. `parseSelectionTie` drops it,
    # so a test can tell "rendered what it was given" from "filtered first"
    # -- the same trick the candidate-papers fixture uses, and for the same
    # reason: a fixture of only good rows cannot distinguish them.
    "kcat_tied": {
        "ok": True,
        "found": True,
        # Emitted under whatever quantity was ASKED for -- see main(). A
        # fixture keyed "kcat_tied" would otherwise carry its value under
        # "kcat" and the resolver, which reads `parsed[quantity]`, would
        # raise "found=true but no usable value".
        "_value": 21.1,
        "unit": "1/s",
        "organism": "Homo sapiens",
        "source": "brenda_exact",
        "crossSpecies": False,
        "relatedness": [],
        "citation": {"source": "BRENDA", "referenceId": "684519"},
        "selectionTie": {
            "candidates": [
                {"value": 21.1, "unit": "1/s", "organism": "Homo sapiens",
                 "reference_id": "684519", "selected": True,
                 "conditions": "pH 6.0, 25C, recombinant wild-type, with FBP"},
                {"value": 6467, "unit": "1/s", "organism": "Homo sapiens",
                 "reference_id": "761568", "selected": False,
                 "conditions": "wild-type, presence of D-fructose-1,6-diphosphate"},
                {"value": None, "unit": "1/s", "organism": "Homo sapiens",
                 "reference_id": "000000", "selected": False, "conditions": None},
            ],
            "low": 21.1,
            "high": 6467,
            "fold_range": 306.5,
            "reason": ("2 rows were equally well evidenced and their values span "
                       "21.1 to 6467, a 306-fold range. The value returned was "
                       "chosen by taking the lowest, which the evidence does not "
                       "justify."),
        },
        "literatureCandidates": [],
        "logs": ["stub runner: tied kcat frontier"],
    },
    # NOT FOUND, BUT THE FALLBACK FOUND PAPERS. A distinct fixture, because
    # this is a distinct outcome and the two used to share a rendering: the
    # CLI printed "BRENDA and PubMed were searched and returned nothing" for
    # both, which is true of `kcat` above and FALSE here.
    #
    # The fourth entry is deliberately unusable -- a title with no pmid, doi
    # or url. `parseCandidatePapers` drops it, so a test can tell the
    # difference between "rendered what it was given" and "filtered first",
    # which a fixture of four good rows cannot.
    "ki": {
        "ok": True,
        "found": False,
        "source": "literature_candidates",
        "crossSpeciesOrganismsAvailable": [],
        "relatedness": [],
        "literatureCandidates": [
            {
                "title": "Kinetics of human muscle lactate dehydrogenase",
                "url": "https://pubmed.ncbi.nlm.nih.gov/1234567/",
                "source": "pubmed",
                "pmid": "1234567",
                "doi": None,
            },
            {
                "title": "Substrate affinity of LDH isoenzymes",
                "url": "https://core.ac.uk/download/98765.pdf",
                "source": "core",
                "pmid": None,
                "doi": "10.1000/example",
            },
            {"title": "", "url": "https://example.org/blank", "source": "core",
             "pmid": None, "doi": None},
            {"title": "A paper nobody can look up", "url": None,
             "source": "core", "pmid": None, "doi": None},
        ],
        "logs": ["stub runner: BRENDA had no ki; PubMed/CORE returned 4 candidates"],
    },
}


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    quantity = payload.get("quantity", "km")

    # The stub honours allowCrossSpecies rather than ignoring it, so a test
    # asserting the opt-in reaches the runner is testing the real hop.
    response = dict(RESPONSES.get(quantity, RESPONSES["kcat"]))
    # A fixture may carry `_value` instead of a quantity-named key, so one
    # fixture can be requested under any quantity. The real runner emits the
    # value under the quantity's own name and the resolver reads it back the
    # same way, so this keeps the stub honest about that contract rather
    # than working around it.
    if "_value" in response:
        response[quantity] = response.pop("_value")

    response["logs"] = list(response.get("logs", [])) + [
        f"allowCrossSpecies={payload.get('allowCrossSpecies') is True}",
        f"physiologicalReference={'yes' if payload.get('physiologicalReference') else 'no'}",
    ]

    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    sys.exit(main())
