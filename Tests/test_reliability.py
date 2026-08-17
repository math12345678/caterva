"""Bakker's reliability axes, graded against the SHARED case file.

Every case in Tests/reliability_cases.json is asserted here and in
Science-Agent-Pipeline/.../reliabilityScore.test.ts. If the two
implementations ever disagree, one of the two suites goes red.

Adding a rule to only one language is the failure this file exists to make
impossible.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from reliability import (
    NO_AGGREGATE_REASON,
    PhysiologicalReference,
    score_reliability,
)

CASES_PATH = pathlib.Path(__file__).parent / "reliability_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def _reference(spec):
    if spec is None:
        return None
    return PhysiologicalReference(
        ph=spec["ph"],
        temperature_c=spec["temperature_c"],
        basis=spec["basis"],
        ph_tolerance=spec["ph_tolerance"],
        temperature_tolerance_c=spec["temperature_tolerance_c"],
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_shared_case(case):
    assay = case["assay"]
    score = score_reliability(
        ph=assay.get("ph"),
        temperature_c=assay.get("temperature_c"),
        unreported=case["unreported"],
        reference=_reference(case["reference"]),
        requested_organism=case["requested_organism"],
        measured_organism=case["measured_organism"],
        cross_species=case["cross_species"],
        relatedness=case["relatedness"],
    )
    expect = case["expect"]
    assert score.assay_completeness.grade == expect["assay_completeness"]
    assert score.condition_proximity.grade == expect["condition_proximity"]
    assert score.organism_match.grade == expect["organism_match"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_every_grade_carries_a_reason(case):
    """A grade with no reason is a number the reader must take on faith,
    which is the failure mode this whole module exists to correct."""
    assay = case["assay"]
    score = score_reliability(
        ph=assay.get("ph"),
        temperature_c=assay.get("temperature_c"),
        unreported=case["unreported"],
        reference=_reference(case["reference"]),
        requested_organism=case["requested_organism"],
        measured_organism=case["measured_organism"],
        cross_species=case["cross_species"],
        relatedness=case["relatedness"],
    )
    for axis in (score.assay_completeness, score.condition_proximity, score.organism_match):
        assert len(axis.reason.strip()) > 20, axis


def test_there_is_no_total():
    """The refusal a later contributor is most likely to helpfully 'fix'."""
    score = score_reliability(ph=7.4, temperature_c=37.0)
    assert not hasattr(score, "total")
    assert not hasattr(score, "score")
    assert not hasattr(score, "confidence")
    assert "deliberately not combined" in score.no_aggregate_reason
    assert "ADR 0024" in NO_AGGREGATE_REASON


def test_nan_is_an_absence_not_a_value():
    score = score_reliability(ph=float("nan"), temperature_c=float("nan"))
    assert score.assay_completeness.grade == "absent"


def test_booleans_are_not_numbers():
    """`True` is an int in Python. Grading `ph=True` as pH 1.0 would be a
    silent nonsense value, and Python is the only one of the two languages
    where this is even possible -- so it is tested only here."""
    score = score_reliability(ph=True, temperature_c=True)
    assert score.assay_completeness.grade == "absent"


def test_case_file_is_not_empty_and_covers_every_grade():
    """A shared case file that drifts toward covering nothing is a cross-
    language guard that cannot fail."""
    grades = {axis: set() for axis in
              ("assay_completeness", "condition_proximity", "organism_match")}
    for case in CASES:
        for axis, grade in case["expect"].items():
            grades[axis].add(grade)

    assert grades["assay_completeness"] == {"complete", "partial", "absent"}
    assert grades["condition_proximity"] == {"near", "far", "not_assessed"}
    assert grades["organism_match"] == {"exact", "related", "distant", "unknown"}
