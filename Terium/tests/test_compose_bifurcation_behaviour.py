"""A sweep labelled the repressilator's oscillating range "no steady state".

`SweepReport.regions` groups by stable-state count, and its summary
called zero "no steady state". A sustained oscillation has zero STABLE
states and one steady state -- an unstable spiral, which
`SweepPoint.unstable_spiral` already detects -- so the whole range where
the repressilator does the one thing it is built to do was labelled as
though the model had run away. A line of equilibria is a third zero-stable
case with a meaning of its own.

In its own file because `test_compose_bifurcation.py` is being edited in
another session; `regions()` is untouched and those tests still hold.
"""

from __future__ import annotations

import pytest

from Terium.compose.bifurcation import SweepPoint, logarithmic_values, sweep
from Terium.compose.pipeline import compose


class TestABehaviourIsMoreThanACount:
    @pytest.fixture(scope="class")
    def repressilator_sweep(self):
        model = compose("repressilator oscillations")
        return sweep(model.network, "gene1_n", logarithmic_values(1.0, 4.0, 7))

    def test_the_oscillating_range_is_named_as_such(self, repressilator_sweep) -> None:
        labels = {label for _, _, label in repressilator_sweep.behaviours()}
        assert "sustained oscillation" in labels, labels
        assert "no steady state" not in labels, (
            "the oscillating range is still labelled as though the model ran away"
        )

    def test_the_summary_says_oscillation(self, repressilator_sweep) -> None:
        text = repressilator_sweep.summary()
        assert "sustained oscillation" in text
        assert "no steady state" not in text

    def test_regions_is_unchanged_for_its_other_callers(self, repressilator_sweep) -> None:
        # The count-based view is kept; only the wording moved.
        for start, end, count in repressilator_sweep.regions():
            assert isinstance(count, int)
        # And where behaviours says "oscillation", regions says zero.
        by_start_b = {s: l for s, _, l in repressilator_sweep.behaviours()}
        by_start_r = {s: c for s, _, c in repressilator_sweep.regions()}
        for start, label in by_start_b.items():
            if label == "sustained oscillation":
                assert by_start_r.get(start) == 0

    def test_a_point_with_an_unstable_spiral_is_an_oscillation(self) -> None:
        from Terium.compose.analysis import FixedPoint, StabilityReport, OSCILLATORY_UNSTABLE

        point = SweepPoint(value=3.0, report=StabilityReport(
            fixed_points=(FixedPoint(
                state={"X": 1.0}, residual=0.0,
                eigenvalues=(complex(0.1, 2.0), complex(0.1, -2.0)),
                classification=OSCILLATORY_UNSTABLE,
            ),),
            starts_tried=8, species=("X",),
        ))
        assert point.stable_count == 0
        assert point.behaviour == "sustained oscillation"

    def test_a_point_with_nothing_is_no_steady_state(self) -> None:
        from Terium.compose.analysis import StabilityReport

        point = SweepPoint(value=3.0, report=StabilityReport(
            fixed_points=(), starts_tried=8, species=("X",),
        ))
        assert point.behaviour == "no steady state"

    def test_a_continuum_point_is_named_as_one(self) -> None:
        from Terium.compose.analysis import CONTINUUM, FixedPoint, StabilityReport

        point = SweepPoint(value=1.0, report=StabilityReport(
            fixed_points=(FixedPoint(
                state={"X": 0.5}, residual=0.0,
                eigenvalues=(0.0, -1.0), classification=CONTINUUM,
            ),),
            starts_tried=8, species=("X",),
        ))
        assert point.behaviour == "a line of equilibria"

    def test_a_saddle_alone_is_no_stable_state_not_no_steady_state(self) -> None:
        # Zero stable, one steady: the fourth zero-stable case, told apart
        # from the model having run away.
        from Terium.compose.analysis import SADDLE, FixedPoint, StabilityReport

        point = SweepPoint(value=1.0, report=StabilityReport(
            fixed_points=(FixedPoint(
                state={"X": 0.5}, residual=0.0,
                eigenvalues=(1.0, -1.0), classification=SADDLE,
            ),),
            starts_tried=8, species=("X",),
        ))
        assert point.behaviour == "no stable state"

    def test_a_toggle_sweep_counts_its_states(self) -> None:
        model = compose("a toggle switch between two repressors")
        report = sweep(model.network, "geneA_n", logarithmic_values(1.0, 4.0, 5))
        labels = {label for _, _, label in report.behaviours()}
        assert "2 stable states" in labels
