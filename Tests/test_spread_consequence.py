"""What the disagreement among equally-evidenced values does to the model.

The assertions that matter here are the REFUSALS. This module sits one step
from the thing ADR 0024 declined — Bakker's ensemble — and the difference
between "the literature reports these three values, here is the model under
each" and "here is an uncertainty estimate" is entirely in what it will not
do without being told.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile

import pytest

from selection_tie import TiedCandidate
from spread_consequence import (
    VARIABLE_PARAMETERS,
    consequence_of,
    substrate_remaining,
)

# Two Km values a source could plausibly report for one enzyme, with the
# selected one first, as `SelectionTie.candidates` orders them.
TWO_KM = [
    TiedCandidate(
        value=0.5, unit="mM", reference_id="740253",
        conditions="pH 7.4, 25°C", selected=True,
    ),
    TiedCandidate(
        value=2.5, unit="mM", reference_id="740999",
        conditions="pH 7.0, 37°C", selected=False,
    ),
]


# ---------------------------------------------------------------------------
# What it refuses to do without being told
# ---------------------------------------------------------------------------


def test_a_missing_experimental_setting_is_a_refusal_naming_it():
    """`vmax` and `s0` are the caller's, exactly as `s0` already is.

    Inventing one would not merely mis-score a value — it would change the
    trajectory the reader is shown while looking like a result. The same
    refusal `reliabilityScore.ts` makes for "physiological pH and T".
    """
    verdict = consequence_of(TWO_KM, parameter="km", vmax=0.25)
    assert verdict.status == "not_assessed"
    assert not verdict.is_assessed
    assert "s0 not supplied" in verdict.reason
    assert verdict.outcomes == []


def test_a_kcat_tie_is_refused_because_it_needs_an_enzyme_concentration():
    """The tie this module was built looking at is a kcat tie.

    Through the real resolver, LDH kcat returns 170.7 with 276.5 ranked
    equal. Neither is an input to the model: `vmax = kcat · [E]`, and
    BRENDA does not report the assay's enzyme concentration. Treating a
    turnover number as a rate would simulate something nobody measured.
    """
    verdict = consequence_of(TWO_KM, parameter="kcat", vmax=1.0, s0=1.0)
    assert verdict.status == "not_assessed"
    assert "enzyme concentration" in verdict.reason
    assert "kcat" not in VARIABLE_PARAMETERS


def test_one_candidate_is_not_a_disagreement():
    """Nothing turned on the choice, so there is nothing to propagate.

    Distinct from a refusal: reported as such rather than as a failure,
    because a report on every single-valued resolution is noise and noise
    is how the reports that matter stop being read (ADR 0028).
    """
    verdict = consequence_of(TWO_KM[:1], parameter="km", vmax=0.25, s0=10.0)
    assert verdict.status == "not_assessed"
    assert "Nothing turned on the choice" in verdict.reason


def test_no_aggregate_is_offered():
    """No mean outcome, ever.

    A mean over values whose weights are unknown is the invented total
    `reliabilityScore.ts` refuses via `noAggregateReason` — and Bakker's
    weighting question is the one she has not answered. An average here
    would be that unanswered question, silently given an answer.
    """
    verdict = consequence_of(TWO_KM, parameter="km", vmax=0.25, s0=10.0)
    payload = verdict.model_dump()
    for forbidden in ("mean", "average", "std", "stdev", "confidence"):
        assert not any(forbidden in key.lower() for key in payload), forbidden
    assert "NOT an uncertainty estimate" in verdict.reason


def test_it_runs_only_at_values_that_were_measured():
    """No interpolation between candidates, ever.

    Running the model at a number nobody reported is the fabrication this
    project exists to refuse. The values simulated must be exactly the
    values handed in.
    """
    verdict = consequence_of(TWO_KM, parameter="km", vmax=0.25, s0=10.0)
    assert sorted(o.value for o in verdict.outcomes) == [0.5, 2.5]


# ---------------------------------------------------------------------------
# What it does
# ---------------------------------------------------------------------------


def test_the_model_is_run_at_each_candidate_and_the_outcomes_differ():
    verdict = consequence_of(TWO_KM, parameter="km", vmax=0.25, s0=10.0, end=10.0)
    assert verdict.is_assessed
    assert verdict.parameter == "km"
    assert "substrate remaining" in verdict.observable

    outcomes = {o.value: o.outcome for o in verdict.outcomes}
    # A larger Km is a slower enzyme at this substrate concentration, so
    # MORE substrate is left. Asserting the DIRECTION rather than the
    # digits: the numbers are RoadRunner's, but the ordering is the
    # Michaelis-Menten equation and would survive a solver change.
    assert outcomes[2.5] > outcomes[0.5]
    assert verdict.outcome_low == pytest.approx(min(outcomes.values()))
    assert verdict.outcome_high == pytest.approx(max(outcomes.values()))


def test_the_selected_value_is_marked_among_the_others():
    """A reader must be able to see which one they were given."""
    verdict = consequence_of(TWO_KM, parameter="km", vmax=0.25, s0=10.0)
    selected = [o for o in verdict.outcomes if o.selected]
    assert len(selected) == 1
    assert selected[0].value == 0.5


def test_each_outcome_carries_the_conditions_that_produced_it():
    """Two numbers differ for a reason the source usually states.

    Without the commentary a reader sees two Km values and no way to
    prefer either; with it they see one was measured at 25 °C and one at
    37 °C and can make the judgement themselves.
    """
    verdict = consequence_of(TWO_KM, parameter="km", vmax=0.25, s0=10.0)
    assert {o.conditions for o in verdict.outcomes} == {"pH 7.4, 25°C", "pH 7.0, 37°C"}
    assert {o.reference_id for o in verdict.outcomes} == {"740253", "740999"}


# ---------------------------------------------------------------------------
# Failure is reported, not hidden
# ---------------------------------------------------------------------------


def test_a_candidate_that_cannot_be_simulated_is_kept_and_named():
    """Dropping it would narrow the reported spread.

    That is the one direction this module must never move in: a silently
    discarded candidate makes the remaining values look more agreed than
    the literature is.
    """
    candidates = [TiedCandidate(value=0.5, selected=True), TiedCandidate(value=-2.0)]
    verdict = consequence_of(candidates, parameter="km", vmax=0.25, s0=10.0)

    assert len(verdict.outcomes) == 2, "the failing candidate was dropped"
    failed = [o for o in verdict.outcomes if o.failure]
    assert len(failed) == 1
    assert failed[0].value == -2.0
    assert failed[0].outcome is None
    assert "could not be simulated" in verdict.reason


def test_attempts_are_not_results():
    """Found by running it, not by reasoning about it.

    Two candidates that both failed produced `status="assessed"`, two
    entries in `outcomes`, and `is_assessed=True` — while the model had
    said nothing at all. `len(outcomes) > 1` counted attempts. A
    comparison needs two RESULTS.
    """
    both_fail = [TiedCandidate(value=-1.0, selected=True), TiedCandidate(value=-2.0)]
    verdict = consequence_of(both_fail, parameter="km", vmax=0.25, s0=10.0)

    assert verdict.status == "not_assessed"
    assert not verdict.is_assessed
    assert len(verdict.outcomes) == 2, "the failures must still be visible"
    assert verdict.outcome_fold_range is None

    # And one result is no better than none for a comparison.
    one_runs = [TiedCandidate(value=0.5, selected=True), TiedCandidate(value=-2.0)]
    assert not consequence_of(one_runs, parameter="km", vmax=0.25, s0=10.0).is_assessed


# ---------------------------------------------------------------------------
# The observable
# ---------------------------------------------------------------------------


def test_the_substrate_column_is_found_by_name():
    """`data[-1][1]` would keep returning a number after a reorder.

    It would answer with the product instead of the substrate and nothing
    would say so — the same shape as reading the wrong column of a table.
    """

    class Reordered:
        colnames = ["time", "[P]", "[S]"]
        data = [[0.0, 0.0, 10.0], [10.0, 7.0, 3.0]]

    assert substrate_remaining(Reordered()) == 3.0

    class NoSubstrate:
        colnames = ["time", "[P]"]
        data = [[10.0, 7.0]]

    with pytest.raises(KeyError, match=r"\[S\]"):
        substrate_remaining(NoSubstrate())


def test_the_observable_reads_the_END_of_the_trajectory():
    """The first row is the initial condition and is the same for every
    candidate — an observable read from it would report perfect agreement
    no matter how far apart the values were."""

    class Trajectory:
        colnames = ["time", "[S]"]
        data = [[0.0, 10.0], [5.0, 6.0], [10.0, 3.0]]

    assert substrate_remaining(Trajectory()) == 3.0


# ---------------------------------------------------------------------------
# The reachable end
# ---------------------------------------------------------------------------


def _run_the_script(payload: dict) -> dict:
    """Invoke the script as a caller does — a subprocess, from elsewhere.

    ADR 0107: `export_citations.py` had been dead on its import line in
    HEAD because every test imported the library directly, where pytest
    has already put the repository root on `sys.path`.
    """
    script = (
        pathlib.Path(__file__).resolve().parents[1]
        / "scripts"
        / "report_spread_consequence.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=tempfile.gettempdir(),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_the_script_runs_end_to_end():
    result = _run_the_script(
        {
            "parameter": "km",
            "vmax": 0.25,
            "s0": 10.0,
            "candidates": [
                {"value": 0.5, "selected": True, "conditions": "pH 7.4, 25°C"},
                {"value": 2.5, "conditions": "pH 7.0, 37°C"},
            ],
        }
    )
    assert result["ok"] is True
    assert result["consequence"]["status"] == "assessed"
    assert len(result["consequence"]["outcomes"]) == 2


def test_the_script_refuses_a_missing_setting_rather_than_defaulting_it():
    """The refusal has to survive the trip through the boundary.

    A script that filled in a plausible `s0` to avoid returning an error
    would be the whole point of this module, undone at the last step.
    """
    result = _run_the_script(
        {
            "parameter": "km",
            "vmax": 0.25,
            "candidates": [{"value": 0.5, "selected": True}, {"value": 2.5}],
        }
    )
    assert result["ok"] is True
    assert result["consequence"]["status"] == "not_assessed"
    assert "s0 not supplied" in result["consequence"]["reason"]


def test_the_script_rejects_a_payload_with_no_candidates():
    script = (
        pathlib.Path(__file__).resolve().parents[1]
        / "scripts"
        / "report_spread_consequence.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps({"parameter": "km", "vmax": 1, "s0": 1}),
        capture_output=True,
        text=True,
        cwd=tempfile.gettempdir(),
    )
    assert completed.returncode != 0
    assert "candidate" in (completed.stdout + completed.stderr).lower()


# ---------------------------------------------------------------------------
# Through the real resolver
# ---------------------------------------------------------------------------


def test_the_tie_this_was_built_for_is_real():
    """Not a constructed example.

    `resolve_kinetic_value` on the LDH kcat fixture returns 170.7 with
    276.5 ranked equally credible — the same paper, immobilised versus
    soluble enzyme. This asserts the tie exists so the module is not
    reasoning about a situation that never arises.
    """
    from fallback_logic import resolve_kinetic_value
    from fixture_lineages import fixture_lineage_provider
    from test_fallback_logic import (
        fake_taxon_id_provider,
        fake_uniprot_provider,
        load_fixture,
        make_html_provider,
    )

    result = resolve_kinetic_value(
        "1.1.1.27", "Mus musculus", "pyruvate",
        html_provider=make_html_provider(
            {"1.1.1.27": load_fixture("brenda_ldh_kcat_fixture.html")}
        ),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False, allow_cross_species=True, quantity="kcat",
        lineage_provider=fixture_lineage_provider,
    )

    tie = result.selection_tie
    assert tie is not None and tie.is_tied
    assert len(tie.candidates) > 1

    # And a kcat tie is exactly the case this module refuses, so the
    # refusal is exercised on the real thing rather than only on a
    # constructed list.
    verdict = consequence_of(tie.candidates, parameter="kcat", vmax=1.0, s0=1.0)
    assert verdict.status == "not_assessed"
    assert "enzyme concentration" in verdict.reason
