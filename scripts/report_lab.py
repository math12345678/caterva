#!/usr/bin/env python3
"""One document a student can hand in.

Reads a JSON payload on stdin, writes Markdown on stdout.

    {"title": "...", "question": "...",
     "ec": "1.1.1.27", "organism": "Homo sapiens",
     "parameters": [{"name": "km", "substrate": "lactate", "quantity": "km"}],
     "supplied":   [{"name": "s0", "value": 10, "unit": "mM",
                     "basis": "lab handout"}],
     "vmax": 0.25, "s0": 10}

WHY THIS EXISTS
---------------
Terrium could resolve a literature value, record its provenance, parse the
assay conditions, grade it on Bakker's axes, run an ensemble over values the
evidence cannot rank, export BibTeX, annotate a model, and integrate it.

Nine capabilities, and nothing a person could hand to a teacher. Each one
answered a question nobody asks in isolation; the student's actual job is
"run the simulation and show where the numbers came from", and they were
left to assemble that from a terminal transcript and two export files.

WHAT IT WILL NOT DO
-------------------
It does not resolve anything it was not asked for, and it does not fill a
gap. A parameter that could not be sourced appears in the report as a
refusal with its reason — because a document that silently omits what it
could not find is indistinguishable from one where nobody looked, and the
student cannot defend a gap they cannot see.
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "Tests"))
# The repository root too — `lab_report` reaches modules that import
# `Terium.*`. `export_citations.py` shipped in HEAD with only the first of
# these lines and died on its import line (ADR 0107).
sys.path.insert(0, str(REPO_ROOT))

from brenda_client import fetch_brenda_html  # noqa: E402
from fallback_logic import resolve_kinetic_value  # noqa: E402
from lab_report import SuppliedValue, build_report  # noqa: E402
from spread_consequence import consequence_of  # noqa: E402


def _fail(message: str) -> int:
    print(json.dumps({"ok": False, "error": message}))
    return 1


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        return _fail(f"Invalid JSON payload: {exc}")

    ec = payload.get("ec")
    organism = payload.get("organism")
    if not ec or not organism:
        return _fail(
            "A report needs 'ec' and 'organism'. Both are the identity of "
            "what is being modelled, and neither is inferred from free text: "
            "guessing either would attach real citations to a system nobody "
            "named."
        )

    resolved: dict = {}
    ensembles: dict = {}
    for entry in payload.get("parameters") or []:
        name = entry.get("name")
        substrate = entry.get("substrate")
        if not name or not substrate:
            return _fail(
                "Every parameter needs a 'name' and a 'substrate'. BRENDA's "
                "tables are keyed on the substrate, so a lookup without one "
                "is answered by every compound ever tested against the enzyme."
            )
        try:
            result = resolve_kinetic_value(
                str(ec), str(organism), str(substrate),
                html_provider=fetch_brenda_html,
                quantity=str(entry.get("quantity", "km")),
                allow_cross_species=bool(entry.get("allowCrossSpecies", False)),
            )
        except Exception as exc:  # noqa: BLE001 - reported, never a traceback
            return _fail(f"Could not resolve {name!r}: {exc}")

        resolved[str(name)] = result

        # An ensemble only where the model can actually be run at each
        # value. `consequence_of` refuses without vmax/s0 and says so, so
        # the refusal reaches the report rather than being pre-empted here.
        candidates = list(getattr(result, "cross_species_candidates", []) or [])
        tie = getattr(result, "selection_tie", None)
        if tie is not None and getattr(tie, "is_tied", False):
            candidates = list(tie.candidates)
        if len(candidates) > 1:
            ensembles[str(name)] = consequence_of(
                candidates,
                parameter=str(entry.get("quantity", "km")),
                vmax=payload.get("vmax"),
                s0=payload.get("s0"),
            )

    supplied = [
        SuppliedValue(
            name=str(s.get("name")),
            value=float(s.get("value")),
            unit=s.get("unit"),
            basis=s.get("basis"),
        )
        for s in payload.get("supplied") or []
        if s.get("name") is not None and s.get("value") is not None
    ]

    report = build_report(
        title=str(payload.get("title") or f"EC {ec} in {organism}"),
        question=str(payload.get("question") or ""),
        resolved=resolved,
        supplied=supplied,
        ensembles=ensembles,
        bibtex=payload.get("bibtex"),
    )

    print(
        json.dumps(
            {
                "ok": True,
                "markdown": report.markdown,
                "sourced": report.sourced,
                "supplied": report.supplied,
                "refusals": report.refusals,
                "disagreements": report.disagreements,
                "defensible": report.is_defensible,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
