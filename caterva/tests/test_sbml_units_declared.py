"""The exported SBML states its units, and libSBML can verify them.

WHAT THIS PINS
--------------
ADR 0150's index row claimed "libSBML: 15 consistency warnings. Now 0"
while no code declared a unit anywhere (found in ADR 0165: the row was
written and the work was not -- measured at 15 on `874b191`). The work
now exists: `caterva/core/sbml_units.py` writes real unitDefinitions and
`scripts/export_annotated_model.py` drives it from the provenance rows'
unit strings.

These tests pin the three claims that matter, against the REAL exporter
process rather than the module alone, because the seam between them is
where this feature broke twice while being built (two mismatched
signatures, each half correct on its own):

  1. the mm export with stated units has ZERO libSBML unit-consistency
     problems -- the number the ADR row promised;
  2. declaring units does not move the trajectory by one part in 1e9 --
     the declarations describe the run, they must not change it;
  3. every refusal direction refuses WHOLE, with a named symbol -- a
     half-declared file reads as a checked file.

The subprocess boundary also pins the wire keys (`unitsDeclared`,
`unitsRefused: [{symbol, reason}]`) that the TypeScript side renders; a
rename on either side fails here rather than printing nothing.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
EXPORTER = REPO / "scripts" / "export_annotated_model.py"

pytest.importorskip("libsbml", reason="declared in requirements.txt; make setup installs it")

MM_PROVENANCE = {
    "km": {"origin": "resolved", "unit": "mM"},
    "vmax": {"origin": "user", "unit": "mM/s"},
    "s0": {"origin": "user", "unit": "mM"},
}


def export(payload: dict) -> dict:
    completed = subprocess.run(
        [sys.executable, str(EXPORTER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=300,
    )
    assert completed.stdout.strip(), (
        f"exporter wrote nothing to stdout (exit {completed.returncode}).\n"
        f"stderr:\n{completed.stderr[-2000:]}"
    )
    return json.loads(completed.stdout)


def mm_payload(**overrides) -> dict:
    payload = {
        "domain": "mm",
        "format": "sbml",
        "parameters": {"km": 0.03, "vmax": 0.25, "s0": 10.0},
        "provenance": {k: dict(v) for k, v in MM_PROVENANCE.items()},
        "units": {"concentration": "mM", "time": "s"},
    }
    payload.update(overrides)
    return payload


def unit_consistency_problems(sbml: str) -> int:
    import libsbml

    document = libsbml.readSBMLFromString(sbml)
    document.setConsistencyChecks(libsbml.LIBSBML_CAT_UNITS_CONSISTENCY, True)
    return document.checkConsistency()


def test_the_mm_export_has_zero_unit_consistency_problems():
    out = export(mm_payload())
    assert out["ok"] is True
    assert sorted(out["unitsDeclared"]) == ["Km", "P", "S", "Vmax"], (
        "the declaration list is the claim; a subset would mean a "
        "half-declared file, which the module exists to refuse"
    )
    assert out["unitsRefused"] == []
    problems = unit_consistency_problems(out["model"])
    assert problems == 0, (
        f"libSBML reports {problems} unit-consistency problem(s) on the "
        "declared export. ADR 0150's number was 15 before the work and 0 "
        "after it; anything else is a regression in the declarations."
    )


def test_declaring_units_does_not_move_the_trajectory():
    """The declarations describe the run; they must not change it.

    The kinetic-law rewrite (x compartment) is the risky half: it changes
    the MathML, and is only value-preserving while the compartment is
    size 1. Integrated, not reasoned about."""
    roadrunner = pytest.importorskip("roadrunner")

    declared = export(mm_payload())["model"]
    bare = export(mm_payload(provenance={}, units=None))["model"]

    final_declared = float(roadrunner.RoadRunner(declared).simulate(0, 10, 51)[-1][1])
    final_bare = float(roadrunner.RoadRunner(bare).simulate(0, 10, 51)[-1][1])
    assert final_declared == pytest.approx(final_bare, rel=1e-9)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_symbol"),
    [
        # A parameter with no stated unit: refuse whole, name the symbol.
        ("km unit missing",
         lambda p: p["provenance"]["km"].pop("unit"),
         "Km"),
        # Two scales in one file: the numbers were normalised into ONE
        # system, so mixed strings mean something upstream lied.
        ("mixed scales",
         lambda p: p["provenance"]["km"].__setitem__("unit", "uM"),
         "concentration system"),
        # A unit outside the vocabulary: never parsed creatively.
        ("unencodable unit",
         lambda p: p["provenance"]["km"].__setitem__("unit", "mg/mL"),
         "Km"),
        # A non-second time base: the declarations state per-second rates.
        ("minutes",
         lambda p: p.__setitem__("units", {"concentration": "mM", "time": "min"}),
         "time"),
    ],
)
def test_refusals_are_whole_and_named(label, mutate, expected_symbol):
    payload = mm_payload()
    mutate(payload)
    out = export(payload)
    assert out["unitsDeclared"] == [], (
        f"{label}: a refusal must declare NOTHING -- a partially declared "
        "file reads as a checked one"
    )
    symbols = [entry["symbol"] for entry in out["unitsRefused"]]
    assert expected_symbol in symbols, (
        f"{label}: expected a refusal naming {expected_symbol!r}, got {symbols}"
    )
    # And the refused file carries no declarations at all.
    assert "<unitDefinition" not in out["model"]


def test_a_domain_without_concentration_semantics_refuses():
    out = export({
        "domain": "sir",
        "format": "sbml",
        "parameters": {"beta": 0.3, "gamma": 0.1, "s0": 990.0,
                       "i0": 10.0, "r0_recovered": 0.0},
        "provenance": {},
    })
    assert out["unitsDeclared"] == []
    assert [e["symbol"] for e in out["unitsRefused"]] == ["domain"], (
        "an SIR model's species are not concentrations; declaring molar "
        "units on them would be an invented fact, and the refusal must say "
        "it is about the domain rather than about a missing entry"
    )
