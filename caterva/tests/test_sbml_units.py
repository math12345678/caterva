"""The exported SBML states its own units, and stating them changed nothing.

ADR 0150's index row claimed libSBML's consistency findings went 15 -> 0
via unitDefinition support, before the work existed (the row was written,
the document never was, and the tree measured 15). These tests pin the
work that now exists, in the row's own terms: libSBML `checkConsistency`
with unit checking on, before and after.

The load-bearing test is the equivalence one. `declare_units` multiplies
every kinetic law by the compartment -- concentration/time becomes
substance/time, the dimension SBML defines a rate to have -- and at the
builders' 1-litre compartment that must be numerically invisible. That is
asserted by integrating both documents and comparing every point, not by
trusting the comment that says so.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import antimony
import libsbml
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from caterva.continuous.model_building import (  # noqa: E402
    build_michaelis_menten_antimony,
    build_mm_competitive_antimony,
)
from caterva.core.sbml_units import declare_units  # noqa: E402

MM_UNITS = {"S": "mM", "Vmax": "mM/s", "Km": "mM"}
COMP_UNITS = {**MM_UNITS, "Ki": "mM", "I": "mM"}


def _sbml(antimony_text: str) -> str:
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(antimony_text) >= 0, antimony.getLastError()
    return antimony.getSBMLString(antimony.getMainModuleName())


def _unit_problems(sbml_text: str) -> int:
    document = libsbml.readSBMLFromString(sbml_text)
    document.setConsistencyChecks(libsbml.LIBSBML_CAT_UNITS_CONSISTENCY, True)
    return document.checkConsistency()


def _mm() -> str:
    return _sbml(build_michaelis_menten_antimony(0.03, 0.25, 10.0))


def _competitive() -> str:
    return _sbml(build_mm_competitive_antimony(0.03, 0.25, 0.1, 10.0, 1.0))


# ---------------------------------------------------------------------------
# The number the feature answers to
# ---------------------------------------------------------------------------


def test_mm_goes_from_fifteen_problems_to_zero():
    """Both halves asserted. A checker that stopped finding problems in
    the UNDECLARED file would make the zero below vacuous, and 15 is the
    exact figure ADR 0150's row claims to have removed."""
    bare = _mm()
    assert _unit_problems(bare) == 15

    outcome = declare_units(bare, MM_UNITS, domain="mm")
    assert outcome.refusals == []
    assert _unit_problems(outcome.sbml) == 0


def test_competitive_declares_to_zero_including_the_literal():
    """The competitive law contains a literal `1` in (1 + I/Ki), which is
    dimensionless and must be DECLARED dimensionless -- libSBML cannot
    verify an expression around an unitless literal ([99505]), and that
    was the one finding left after everything else was declared."""
    outcome = declare_units(_competitive(), COMP_UNITS, domain="mm_competitive_inhibition")
    assert outcome.refusals == []
    assert _unit_problems(outcome.sbml) == 0
    assert 'units="dimensionless"' in outcome.sbml


def test_the_declared_model_integrates_identically():
    """The kinetic-law x compartment rewrite must be numerically invisible.

    Every point of both trajectories, compared exactly -- not a tolerance.
    At a 1-litre compartment `law * 1.0` is the same double, and anything
    weaker here would let a real semantic change (a 2x, a wrong
    compartment) hide inside an epsilon.
    """
    roadrunner = pytest.importorskip("roadrunner")

    for label, bare, units, domain in [
        ("mm", _mm(), MM_UNITS, "mm"),
        ("competitive", _competitive(), COMP_UNITS, "mm_competitive_inhibition"),
    ]:
        declared = declare_units(bare, units, domain=domain)
        assert declared.refusals == [], label
        a = roadrunner.RoadRunner(bare).simulate(0, 10, 51)
        b = roadrunner.RoadRunner(declared.sbml).simulate(0, 10, 51)
        assert (a == b).all(), f"{label}: declaring units changed the trajectory"


def test_the_declared_scale_matches_the_stated_unit():
    """libSBML's consistency check CANNOT catch this: 10^-3 and 10^-6 mole
    are the same dimension, so a declaration off by a thousandfold passes
    every dimensional check while telling a reader the wrong number. The
    scale attribute is asserted directly -- this is the suite's only
    defence against a plausible-looking wrong declaration, which is worse
    than none (a reader trusts declarations and merely guesses at
    absences)."""
    for unit, expected_scale in (("mM", -3), ("uM", -6)):
        units = {name: unit if not u.endswith("/s") else f"{unit}/s"
                 for name, u in MM_UNITS.items()}
        outcome = declare_units(_mm(), units, domain="mm")
        assert outcome.refusals == []
        model = libsbml.readSBMLFromString(outcome.sbml).getModel()
        for i in range(model.getNumUnitDefinitions()):
            definition = model.getUnitDefinition(i)
            for j in range(definition.getNumUnits()):
                part = definition.getUnit(j)
                if part.getKind() == libsbml.UNIT_KIND_MOLE:
                    assert part.getScale() == expected_scale, (
                        f"{unit}: {definition.getId()} carries mole scale "
                        f"{part.getScale()}, stated system implies {expected_scale}"
                    )


# ---------------------------------------------------------------------------
# Refusals: named, total, and side-effect-free
# ---------------------------------------------------------------------------


def test_a_missing_parameter_unit_refuses_and_names_it():
    units = dict(MM_UNITS)
    del units["Km"]
    outcome = declare_units(_mm(), units, domain="mm")
    assert outcome.declared == []
    assert any(symbol == "Km" for symbol, _ in outcome.refusals)


def test_mixed_concentration_scales_refuse():
    outcome = declare_units(_mm(), {**MM_UNITS, "Km": "uM"}, domain="mm")
    assert outcome.declared == []
    assert outcome.refusals, "two scales in one model must not declare either"


def test_a_non_second_rate_refuses():
    """`mM/min` is a real unit the declarations cannot state -- they
    hard-code per-second. Refusing is the honest outcome; converting the
    VALUE is the CLI's job and it already happened upstream (ADR 0146)."""
    outcome = declare_units(_mm(), {**MM_UNITS, "Vmax": "mM/min"}, domain="mm")
    assert outcome.declared == []
    assert any(symbol == "Vmax" for symbol, _ in outcome.refusals)


def test_an_unmapped_domain_refuses():
    """SIR species are population counts. Declaring molar concentrations
    on them would be a confident lie, so the domain gate refuses before
    anything is written."""
    outcome = declare_units(_mm(), MM_UNITS, domain="sir")
    assert outcome.declared == []
    assert any(symbol == "domain" for symbol, _ in outcome.refusals)


def test_a_refusal_returns_the_document_byte_identical():
    """All-or-nothing is the contract: a half-declared file reads as a
    checked one. Byte equality, not structural -- a rewrite that reordered
    attributes would be evidence something WAS touched."""
    bare = _mm()
    outcome = declare_units(bare, {}, domain="mm")
    assert outcome.refusals
    assert outcome.sbml == bare


# ---------------------------------------------------------------------------
# Through the real exporter, as the CLI drives it
# ---------------------------------------------------------------------------


def test_the_exporter_delivers_the_verdict_end_to_end():
    """One subprocess run of the real seam: per-row units in, zero
    problems and the declared list out. The detail keys are the CLI's
    only view -- a verdict computed in the module and dropped by the
    exporter would be the house defect inside the fix for it."""
    payload = {
        "domain": "mm",
        "parameters": {"km": 0.03, "vmax": 0.25, "s0": 10.0},
        "format": "sbml",
        "provenance": {
            "km": {"origin": "resolved", "unit": "mM"},
            "vmax": {"origin": "resolved", "unit": "mM/s"},
            "s0": {"origin": "user", "unit": "mM"},
        },
        "units": {"concentration": "mM", "time": "s"},
    }
    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "export_annotated_model.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    out = json.loads(completed.stdout)
    assert out["unitsRefused"] == []
    assert set(out["unitsDeclared"]) == {"S", "P", "Vmax", "Km"}
    assert _unit_problems(out["model"]) == 0


def test_a_non_second_time_base_refuses_at_the_exporter():
    payload = {
        "domain": "mm",
        "parameters": {"km": 0.03, "vmax": 0.25, "s0": 10.0},
        "format": "sbml",
        "provenance": {"s0": {"origin": "user", "unit": "mM"}},
        "units": {"concentration": "mM", "time": "min"},
    }
    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "export_annotated_model.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = json.loads(completed.stdout)
    assert out["unitsDeclared"] == []
    assert any(r["symbol"] == "time" for r in out["unitsRefused"])
