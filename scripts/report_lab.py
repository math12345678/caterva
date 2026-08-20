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


class ConflictingValue(ValueError):
    """The same quantity arrived twice, with two different numbers."""


def model_inputs(
    resolved: dict,
    quantities: dict[str, str],
    supplied: list[SuppliedValue],
    payload: dict,
) -> dict[str, float]:
    """Every number the model will run at, each taken from exactly ONE place.

    WHY THIS IS A FUNCTION AND NOT THREE `payload.get` CALLS
    -------------------------------------------------------
    Before this, `s0` could arrive twice: as `payload["s0"]`, which is what
    the ensemble ran at, and inside `payload["supplied"]`, which is what the
    Parameters table printed. Nothing compared them. A caller passing 10 in
    one and 5 in the other got a document whose table said 5, whose ensemble
    was computed at 10, and which looked entirely consistent.

    That is this repository's most-repeated defect -- one fact, two copies,
    no check (ADR 0003, 0027, 0036, 0086) -- and a lab report is the worst
    place for it, because the whole document is a claim that the numbers
    shown are the numbers used.

    So the sections do not each read the payload. They are all handed this.
    A disagreement is refused rather than resolved by precedence: picking a
    winner silently would restore the original defect with a rule attached.
    """
    values: dict[str, float] = {}
    origin: dict[str, str] = {}

    def claim(name: str, value: float, where: str) -> None:
        if name in values and float(values[name]) != float(value):
            raise ConflictingValue(
                f"{name} was given twice with different values: "
                f"{values[name]} ({origin[name]}) and {value} ({where}). "
                "Terrium will not choose between them, because the report "
                "would state one number and be computed from the other."
            )
        values[name] = float(value)
        origin.setdefault(name, where)

    # Literature-resolved values are keyed by the QUANTITY they measure, not
    # by the label the caller chose. A caller naming a parameter "km_lactate"
    # still resolved a km, and the model takes a km.
    for name, result in resolved.items():
        if getattr(result, "found", False) and result.value is not None:
            claim(quantities.get(name, name), result.value, f"literature, via {name}")

    for entry in supplied:
        claim(entry.name, entry.value, "supplied by you")

    for name in ("km", "vmax", "s0"):
        if payload.get(name) is not None:
            claim(name, float(payload[name]), f"payload {name!r}")

    return values


#: What the Michaelis-Menten model cannot run without, and who owns each.
#:
#: The distinction is the one the professors' correspondence turns on: a km
#: is a property of the enzyme that the literature can supply, while s0 is
#: how much substrate the student put in the tube. Reporting a missing s0
#: the same way as a missing km tells a reader to go looking for a paper
#: that cannot exist.
MM_REQUIRED = {
    "km": "a measured property of the enzyme; Terrium resolves it or refuses",
    "vmax": "yours to supply, or derived from kcat and the enzyme concentration",
    "s0": "yours to choose — how much substrate you put in, not a property "
    "of the enzyme",
}


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
    quantities: dict[str, str] = {}
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
        quantities[str(name)] = str(entry.get("quantity", "km"))

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

    try:
        inputs = model_inputs(resolved, quantities, supplied, payload)
    except ConflictingValue as exc:
        return _fail(str(exc))

    # ---- The ensemble, and the run, from the SAME numbers -----------------
    #
    # Both of these used to read `payload` directly. They now read `inputs`,
    # so "what the model does across the evidence" and "what the model did"
    # cannot be computed at different values than the table states.
    for name, result in resolved.items():
        candidates = list(getattr(result, "cross_species_candidates", []) or [])
        tie = getattr(result, "selection_tie", None)
        if tie is not None and getattr(tie, "is_tied", False):
            candidates = list(tie.candidates)
        if len(candidates) > 1:
            ensembles[name] = consequence_of(
                candidates,
                parameter=quantities.get(name, "km"),
                vmax=inputs.get("vmax"),
                s0=inputs.get("s0"),
            )

    simulation = None
    also_refused: list[str] = []
    missing = [name for name in MM_REQUIRED if name not in inputs]

    if missing:
        # NOT silence. Until now the Result section simply did not render
        # when the model could not be run, which is indistinguishable from a
        # report where nobody tried to run it -- the exact failure the "What
        # Terrium would not do" section exists to prevent, occurring inside
        # the document that section belongs to.
        also_refused.append(
            "the simulation was not run: "
            + "; ".join(f"{name} is missing — {MM_REQUIRED[name]}" for name in missing)
        )
    else:
        try:
            from Terium.continuous.simulations import simulate_michaelis_menten

            simulation = simulate_michaelis_menten(
                km=inputs["km"],
                vmax=inputs["vmax"],
                s0=inputs["s0"],
                end=float(payload.get("endTime", 10.0)),
                points=int(payload.get("points", 51)),
            )
        except Exception as exc:  # noqa: BLE001 - reported, never a traceback
            # A model that would not integrate is a finding about the
            # parameters, which are printed directly above it. Swallowing it
            # would leave a report asserting values that cannot be run.
            also_refused.append(
                f"the simulation was not run: the model would not integrate "
                f"at these values — {exc}"
            )

    report = build_report(
        title=str(payload.get("title") or f"EC {ec} in {organism}"),
        question=str(payload.get("question") or ""),
        resolved=resolved,
        supplied=supplied,
        ensembles=ensembles,
        simulation=simulation,
        bibtex=payload.get("bibtex"),
        also_refused=also_refused,
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
