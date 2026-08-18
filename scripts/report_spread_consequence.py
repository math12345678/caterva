#!/usr/bin/env python3
"""What the tie among equally-evidenced values does to the simulation.

Reads a JSON payload on stdin, writes a JSON verdict on stdout.

    {"parameter": "km" | "vmax",
     "vmax": 0.25, "km": null, "s0": 10.0,
     "end": 10.0, "points": 51,
     "candidates": [{"value": 0.5, "selected": true,
                     "conditions": "pH 7.4, 25 C", "referenceId": "740253"}]}

The counterpart to `export_citations.py`, and the reachable end of
`Tests/spread_consequence.py`. ADR 0051 reports that several literature
values were ranked equal; this is what running the model at each of them
does.

WHAT THIS SCRIPT WILL NOT DO
----------------------------
It will not supply a missing `vmax`, `km` or `s0`. Those are experimental
settings, not properties of the enzyme, and a plausible default here would
change the trajectory a student is shown while looking like a result. A
payload missing one gets a `not_assessed` verdict naming it — an answer, and
a different answer from "the candidates agreed".

An empty or single-candidate list IS an error at this boundary, though not
in the library: asking a script "what does the disagreement do" while
supplying no disagreement is a malformed request, whereas a resolver finding
one value is an ordinary outcome.
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "Tests"))
# The repository root too — `Terium.continuous.simulations` is imported by
# the module below. `export_citations.py` shipped in HEAD with only the
# first of these two lines and died on its import line (ADR 0107).
sys.path.insert(0, str(REPO_ROOT))

from selection_tie import TiedCandidate  # noqa: E402
from spread_consequence import consequence_of  # noqa: E402


def _fail(message: str) -> int:
    print(json.dumps({"ok": False, "error": message}))
    return 1


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        return _fail(f"Invalid JSON payload: {exc}")

    entries = payload.get("candidates") or []
    if len(entries) < 2:
        return _fail(
            f"{len(entries)} candidate(s) supplied. This script reports what a "
            "DISAGREEMENT does to the model; with fewer than two values there "
            "is no disagreement, and a verdict saying so would read as a "
            "result rather than a malformed request."
        )

    candidates = []
    for entry in entries:
        if entry.get("value") is None:
            return _fail(
                "A candidate has no value. Every entry must be a number some "
                "source actually reported — this script never interpolates."
            )
        candidates.append(
            TiedCandidate(
                value=float(entry["value"]),
                unit=entry.get("unit"),
                organism=entry.get("organism"),
                reference_id=entry.get("referenceId"),
                conditions=entry.get("conditions"),
                selected=bool(entry.get("selected", False)),
            )
        )

    parameter = payload.get("parameter")
    if not parameter:
        return _fail("No 'parameter' given: say which value the candidates are.")

    verdict = consequence_of(
        candidates,
        parameter=str(parameter),
        vmax=payload.get("vmax"),
        km=payload.get("km"),
        s0=payload.get("s0"),
        end=float(payload.get("end", 10.0)),
        points=int(payload.get("points", 51)),
    )

    print(json.dumps({"ok": True, "consequence": verdict.model_dump()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
