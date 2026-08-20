"""The band section of the report.

ADR 0134 keeps two ensembles and binds them with a property. Both belong in
the document: the enumeration says which paper gives which answer, the band
says how much the answer depends on which paper was picked.
"""
from __future__ import annotations

from lab_report import build_report


class FakeEnvelope:
    def __init__(self, column):
        self.column = column
        self.times = [0.0, 10.0]
        self.low, self.p05, self.median = [10.0, 7.5], [10.0, 7.5], [10.0, 7.6]
        self.p95, self.high = [10.0, 7.6], [10.0, 7.6]


class FakeBand:
    envelopes = [FakeEnvelope("[S]")]
    succeeded = 40
    failed = []
    seed = 20260820
    disclaimer = "It is NOT an uncertainty estimate."


class FakeBandWithFailures(FakeBand):
    succeeded = 38
    failed = [object(), object()]


def report(**kw):
    return build_report(title="t", question="q", resolved={}, supplied=[], **kw)


def test_the_band_reports_the_seed_that_reproduces_it():
    """`sample_ensemble` makes the seed a required argument because an
    ensemble nobody can reproduce is not evidence. Dropping it from the
    document undoes that requirement at the last step."""
    text = report(bands={"km": FakeBand()}).markdown
    assert "20260820" in text
    assert "reproduces this band exactly" in text


def test_runs_that_failed_are_declared_not_dropped():
    """A band computed from the survivors and presented as if every draw
    had run is narrower than the evidence, and says nothing about why."""
    text = report(bands={"km": FakeBandWithFailures()}).markdown
    assert "2 run(s) did not complete" in text


def test_no_failure_line_when_every_run_completed():
    """A line reading "0 run(s) did not complete" on every clean band is
    noise, and noise is how the lines that matter stop being read."""
    assert "did not complete" not in report(bands={"km": FakeBand()}).markdown


def test_the_disclaimer_is_quoted_from_the_module_that_computed_the_band():
    """A second wording here would be a second claim (ADR 0003)."""
    text = report(bands={"km": FakeBand()}).markdown
    assert FakeBand.disclaimer in text


def test_a_banded_parameter_counts_as_a_disagreement():
    """A reader scanning `disagreements` must find the parameter whether it
    was enumerated, banded, or both."""
    assert report(bands={"km": FakeBand()}).disagreements == ["km"]


def test_an_empty_band_renders_nothing():
    """A heading with no figures under it implies a result that does not
    exist."""

    class Empty:
        envelopes = []

    assert "across the evidence" not in report(bands={"km": Empty()}).markdown
