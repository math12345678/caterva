"""The ensemble of MODELS — Sauro's "you can sample and get an ensemble".

`test_ensemble.py` covers the weighting. This covers what happens when those
draws are turned into runs, and it is mostly about honesty regarding the
band's support: an envelope is a claim about a family of runs, and the ways
to lie with one are to draw it over fewer runs than you imply, over runs that
are not comparable, or over parameter sets nobody sampled.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model_ensemble import run_model_ensemble  # noqa: E402


@dataclass
class FakeResult:
    colnames: list
    data: list


def linear(*, slope: float, points: int = 3, end: float = 2.0):
    """y = slope * t, on a fixed grid. Trivial so the assertions are exact."""
    times = [end * i / (points - 1) for i in range(points)]
    return FakeResult(colnames=["time", "y"], data=[[t, slope * t] for t in times])


class TestTheBandDescribesTheRunsItWasDrawnOver:
    def test_low_and_high_bracket_every_run(self) -> None:
        result = run_model_ensemble(
            simulate=linear,
            base_parameters={"points": 3, "end": 2.0},
            parameter_draws={"slope": [1.0, 2.0, 3.0]},
            seed=1,
        )
        env = result.envelopes[0]
        # At t=2 the runs are 2, 4, 6.
        assert env.low[-1] == 2.0
        assert env.high[-1] == 6.0
        assert env.low[-1] <= env.median[-1] <= env.high[-1]

    def test_a_percentile_is_always_a_value_some_run_produced(self) -> None:
        """Nearest-rank, not interpolated. With a handful of distinct
        parameter values the runs cluster heavily, and a smoothed percentile
        would invent the smoothness.
        """
        result = run_model_ensemble(
            simulate=linear,
            base_parameters={"points": 3, "end": 2.0},
            parameter_draws={"slope": [1.0, 5.0]},
            seed=1,
        )
        env = result.envelopes[0]
        for value in (env.p05[-1], env.median[-1], env.p95[-1]):
            assert value in (2.0, 10.0), f"interpolated: {value}"

    def test_one_column_per_output(self) -> None:
        def two_outputs(*, slope: float):
            return FakeResult(
                colnames=["time", "a", "b"], data=[[0.0, 0.0, 0.0], [1.0, slope, -slope]]
            )

        result = run_model_ensemble(
            simulate=two_outputs,
            base_parameters={},
            parameter_draws={"slope": [1.0, 2.0]},
            seed=1,
        )
        assert [e.column for e in result.envelopes] == ["a", "b"]


class TestFailuresAreCountedNeverDropped:
    def test_a_failing_run_is_reported_not_silently_excluded(self) -> None:
        """An envelope over 2 of 3 runs, with the third unmentioned, is a
        quiet lie about its own support.
        """
        def sometimes(*, slope: float):
            if slope == 2.0:
                raise ZeroDivisionError("solver blew up")
            return linear(slope=slope)

        result = run_model_ensemble(
            simulate=sometimes,
            base_parameters={},
            parameter_draws={"slope": [1.0, 2.0, 3.0]},
            seed=1,
        )
        assert result.succeeded == 2
        assert len(result.failed) == 1
        assert result.attempted == 3
        assert "ZeroDivisionError" in result.failed[0].reason
        # The parameter set that failed is kept, so it can be reproduced.
        assert result.failed[0].parameters["slope"] == 2.0

    def test_the_support_note_is_stated_even_when_nothing_failed(self) -> None:
        """A note that appears only on failure trains a reader to skim past it
        exactly when it matters.
        """
        clean = run_model_ensemble(
            simulate=linear, base_parameters={}, parameter_draws={"slope": [1.0, 2.0]}, seed=1
        )
        assert "all 2 runs" in clean.support_note()

    def test_the_note_names_the_shortfall_when_there_is_one(self) -> None:
        def sometimes(*, slope: float):
            if slope > 2.0:
                raise ValueError("nope")
            return linear(slope=slope)

        result = run_model_ensemble(
            simulate=sometimes,
            base_parameters={},
            parameter_draws={"slope": [1.0, 2.0, 3.0, 4.0]},
            seed=1,
        )
        note = result.support_note()
        assert "2 of 4" in note
        # Named as a numerical failure, not as a claim about the biology.
        assert "not a judgement about the biology" in note

    def test_all_runs_failing_raises_rather_than_returning_an_empty_band(self) -> None:
        def always_fails(*, slope: float):
            raise RuntimeError("no")

        with pytest.raises(ValueError, match="every one of the"):
            run_model_ensemble(
                simulate=always_fails,
                base_parameters={},
                parameter_draws={"slope": [1.0, 2.0]},
                seed=1,
            )

    def test_a_run_producing_no_rows_is_a_failure(self) -> None:
        def empty(*, slope: float):
            if slope == 2.0:
                return FakeResult(colnames=["time", "y"], data=[])
            return linear(slope=slope)

        result = run_model_ensemble(
            simulate=empty, base_parameters={}, parameter_draws={"slope": [1.0, 2.0]}, seed=1
        )
        assert result.succeeded == 1
        assert "no rows" in result.failed[0].reason


class TestRunsMustBeComparable:
    def test_a_different_time_grid_is_a_failure_not_something_to_interpolate(
        self,
    ) -> None:
        """"The median at t=3" across mismatched grids compares different
        quantities, and interpolating onto a reference grid would manufacture
        values no run produced.
        """
        def wobbly(*, slope: float):
            return linear(slope=slope, points=3 if slope == 1.0 else 5)

        result = run_model_ensemble(
            simulate=wobbly, base_parameters={}, parameter_draws={"slope": [1.0, 2.0]}, seed=1
        )
        assert result.succeeded == 1
        assert "time points" in result.failed[0].reason

    def test_draw_i_of_each_parameter_forms_one_coherent_run(self) -> None:
        """Two parameters sampled independently and then combined arbitrarily
        would explore parameter sets no source supports. Draw i stays with
        draw i.
        """
        seen = []

        def record(*, a: float, b: float):
            seen.append((a, b))
            return FakeResult(colnames=["time", "y"], data=[[0.0, a + b]])

        run_model_ensemble(
            simulate=record,
            base_parameters={},
            parameter_draws={"a": [1.0, 2.0], "b": [10.0, 20.0]},
            seed=1,
        )
        assert seen == [(1.0, 10.0), (2.0, 20.0)]

    def test_unequal_draw_lengths_are_refused(self) -> None:
        with pytest.raises(ValueError, match="different lengths"):
            run_model_ensemble(
                simulate=linear,
                base_parameters={},
                parameter_draws={"a": [1.0, 2.0], "b": [1.0]},
                seed=1,
            )

    def test_varying_nothing_is_refused(self) -> None:
        """An ensemble over zero sampled parameters is one run, and calling it
        an ensemble would overstate it.
        """
        with pytest.raises(ValueError, match="nothing to vary"):
            run_model_ensemble(
                simulate=linear, base_parameters={}, parameter_draws={}, seed=1
            )


class TestWhatItSaysAboutItself:
    def test_the_cap_is_visible_rather_than_a_silent_truncation(self) -> None:
        result = run_model_ensemble(
            simulate=linear,
            base_parameters={},
            parameter_draws={"slope": [1.0, 2.0, 3.0, 4.0, 5.0]},
            seed=1,
            max_runs=2,
        )
        assert result.attempted == 2

    def test_the_disclaimer_travels_with_the_band(self) -> None:
        """The band is a spread over published values, not an uncertainty
        estimate — there is still no validation step. ADR 0024's objection
        applies to the trajectories exactly as it applies to the parameters.
        """
        result = run_model_ensemble(
            simulate=linear, base_parameters={}, parameter_draws={"slope": [1.0]}, seed=1
        )
        assert "NOT an uncertainty estimate" in result.disclaimer

    def test_it_records_what_was_varied(self) -> None:
        result = run_model_ensemble(
            simulate=linear,
            base_parameters={"end": 2.0},
            parameter_draws={"slope": [1.0, 2.0]},
            seed=7,
        )
        assert result.swept == ("slope",)
        assert result.seed == 7
