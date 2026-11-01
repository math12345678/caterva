"""The band has to reach the document, not just exist.

`build_report` grew a `bands` parameter and nothing passed it. The section
rendered correctly, was tested, and could not appear in any report a person
could produce — computed, correct, undelivered, which is the defect this
repository has spent most of its effort on, occurring in the feature added
to display the results of the last one.

So these test `band_for` at the seam where the command builds it: given
candidates, a seed and the model's inputs, does a band come back, and when
one cannot be produced is the reason a sentence somebody can act on?
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from report_lab import band_for  # noqa: E402
from selection_tie import TiedCandidate  # noqa: E402

TWO = [
    TiedCandidate(value=0.5, organism="Homo sapiens", reference_id="740253"),
    TiedCandidate(value=2.5, organism="Sus scrofa", reference_id="740999"),
]
INPUTS = {"km": 0.5, "vmax": 0.25, "s0": 10.0}
SEED = 20260820


def test_a_band_is_produced_and_can_reach_the_report():
    band, refusal = band_for(
        TWO, parameter="km", inputs=INPUTS, seed=SEED, draws=40
    )
    assert refusal is None
    assert band is not None
    assert band.envelopes, "a band with no envelopes renders nothing"
    assert band.seed == SEED


def test_no_seed_means_no_band_AND_a_sentence_saying_why():
    """`sample_ensemble` makes the seed required because an ensemble nobody
    can reproduce is not evidence. Defaulting one here would undo that at
    the last step: the report would carry a band, print a seed the caller
    never chose, and look reproducible."""
    band, refusal = band_for(
        TWO, parameter="km", inputs=INPUTS, seed=None, draws=40
    )
    assert band is None
    assert refusal is not None
    assert "nobody can reproduce is not evidence" in refusal
    # Actionable, not merely regretful.
    assert "--seed" in refusal


def test_a_missing_model_input_is_named():
    """Asserted on the SENTENCE, not on the substring "s0".

    Mutation showed why: deleting the check let the code reach
    `inputs["s0"]`, raise `KeyError('s0')`, and land in the generic
    handler — whose message contains "s0" too. The assertion passed while
    the check it named was gone.

    Fifth time this session an assertion has been satisfied by something
    adjacent to what it tests.
    """
    band, refusal = band_for(
        TWO, parameter="km", inputs={"km": 0.5, "vmax": 0.25},
        seed=SEED, draws=40,
    )
    assert band is None
    assert refusal == "no band was produced for km: the model cannot be run without s0."


def test_one_candidate_is_silent_rather_than_refused():
    """Nothing turned on the choice, so there is no band to want and
    nothing to explain. A refusal here would fire on the ordinary case and
    be ignored on the one that matters (ADR 0028)."""
    band, refusal = band_for(
        TWO[:1], parameter="km", inputs=INPUTS, seed=SEED, draws=40
    )
    assert band is None
    assert refusal is None


def test_a_band_that_cannot_compute_reports_rather_than_raises():
    """This runs while a document is being assembled. A traceback here
    replaces a report that says what it could not do with no report at
    all."""
    band, refusal = band_for(
        [TiedCandidate(value=-1.0), TiedCandidate(value=-2.0)],
        parameter="km",
        inputs={"km": -1.0, "vmax": 0.25, "s0": 10.0},
        seed=SEED,
        draws=10,
    )
    assert band is None or band.envelopes == []
    if band is None:
        assert refusal and "no band was produced" in refusal


def test_the_seed_travels_so_the_band_can_be_repeated():
    """Two runs with the same seed must give the same band, or the sentence
    the report prints about reproducing it is false."""
    first, _ = band_for(TWO, parameter="km", inputs=INPUTS, seed=SEED, draws=40)
    second, _ = band_for(TWO, parameter="km", inputs=INPUTS, seed=SEED, draws=40)
    assert first is not None and second is not None
    assert [e.median[-1] for e in first.envelopes] == [
        e.median[-1] for e in second.envelopes
    ]
