"""Sweeping a parameter and finding where the behaviour changes.

A stability analysis says what a model does at the parameters it has. The
question a modeller actually has is the next one: at what cooperativity does
this toggle switch become bistable? These tests pin that answer against a
case where it is known analytically, and pin the two ways a sweep can
mislead: naming a bifurcation it has not identified, and reporting a solver
gap as a change in behaviour.
"""

from __future__ import annotations

from typing import Any

import pytest

from caterva.compose.bifurcation import (
    CONTINUATION_TOLERANCE, FOLD, HOPF, UNNAMED, SweepPoint, SweepReport,
    linear_values, logarithmic_values, sweep,
)
from caterva.compose.grammar import recognise


class TestSweepValues:
    def test_linear_values_include_both_endpoints(self) -> None:
        values = linear_values(1.0, 3.0, 5)
        assert values[0] == pytest.approx(1.0)
        assert values[-1] == pytest.approx(3.0)
        assert len(values) == 5

    def test_logarithmic_values_are_evenly_spaced_in_log(self) -> None:
        # A rate constant spans decades. A linear sweep from 0.1 to 100
        # spends nine tenths of its samples above 10 and resolves the
        # interesting end not at all.
        values = logarithmic_values(0.01, 100.0, 5)
        ratios = [b / a for a, b in zip(values, values[1:])]
        assert all(r == pytest.approx(ratios[0]) for r in ratios)

    def test_a_logarithmic_sweep_through_zero_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive endpoints"):
            logarithmic_values(0.0, 10.0)

    def test_a_sweep_of_one_value_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not a sweep"):
            linear_values(1.0, 2.0, 1)


class TestTheToggleSwitch:
    """Where a switch starts switching, which is the number a paper reports."""

    def test_cooperativity_below_one_gives_a_single_state(self) -> None:
        # Mutual repression with n = 1 is not bistable: the nullclines cross
        # once. This is the textbook condition and the reason `n` is a
        # declared parameter of the motif rather than a 1.
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", [1.0])
        assert report.points[0].stable_count == 1

    def test_cooperativity_above_one_gives_two(self) -> None:
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", [2.0])
        assert report.points[0].stable_count == 2

    def test_the_sweep_finds_the_transition_between_them(self) -> None:
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", linear_values(1.0, 3.0, 11))

        counts = {point.stable_count for point in report.points}
        assert counts >= {1, 2}, counts
        assert report.bifurcations, report.summary()

        found = report.bifurcations[0]
        assert found.kind == FOLD
        assert found.below <= 1.4 and found.above >= 1.2

    def test_the_regions_partition_the_swept_range(self) -> None:
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", linear_values(1.0, 3.0, 11))
        regions = report.regions()
        assert regions[0][0] == pytest.approx(1.0)
        assert regions[-1][1] == pytest.approx(3.0)


class TestHonesty:
    def test_a_solver_gap_is_not_reported_as_a_bifurcation(
        self, monkeypatch: Any,
    ) -> None:
        """A barren sample is a failure to converge, not a change.

        Manufacturing a bifurcation out of a solver failure would put a
        number in a paper that describes this software rather than the
        model.

        Built from a REAL sweep rather than a hand-made SweepReport. The
        first version constructed one with `points=()` and `barren=(1.0,
        2.0)`, which cannot occur -- barren values are derived FROM points
        -- so it tested a shape the code never produces and failed on an
        early return it should never have reached.

        The gap is now injected rather than waited for. The original
        constants' scale (a 10 mM steady state, above the cell's ~5 mM of
        total protein) made the root find fail at a sample right on the
        fold; the corrected scale does not, and pinning a real solver
        failure would be asserting the fix did not happen. So `analyse` is
        replaced at exactly one sampled value with the report shape a failed
        root find produces -- no fixed points -- and left genuinely real
        everywhere else. Barren is still derived from a point the sweep
        itself produced, which is the invariant the hand-made version
        violated.
        """
        from caterva.compose import bifurcation as module
        from caterva.compose.analysis import DEFAULT_STARTS_PER_SPECIES
        from caterva.compose.analysis import StabilityReport

        values = linear_values(1.0, 3.0, 11)
        gap = values[1]  # 1.2, the lattice point sitting on the fold
        real_analyse = module.analyse

        def analyse_with_gap(network: Any, /, **kw: Any) -> Any:
            n = next(p.value for p in network.parameters if p.id == "geneA_n")
            if n == pytest.approx(gap):
                return StabilityReport(
                    fixed_points=(),
                    starts_tried=kw.get(
                        "starts_per_species", DEFAULT_STARTS_PER_SPECIES
                    ),
                    species=tuple(s.id for s in network.species),
                )
            return real_analyse(network, **kw)

        monkeypatch.setattr(module, "analyse", analyse_with_gap)
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", values)
        assert report.barren, "the injected gap was not recorded as barren"
        assert "not a bifurcation and is not counted as one" in report.summary()
        # And every barren value really is one the search found nothing at.
        for value in report.barren:
            point = next(p for p in report.points if p.value == value)
            assert point.total_count == 0

    def test_a_gap_does_not_blind_the_detector_either(
        self, monkeypatch: Any,
    ) -> None:
        """The other half, and the bug this test was written for.

        A barren sample used to break the comparison on BOTH sides of
        itself, because each had one empty side. The toggle switch became
        bistable across exactly such a gap, and the report listed regions
        with different stable-state counts while announcing in the next
        sentence that no change had been seen.

        The gap is the same injected `analyse` emptiness as the sibling
        test, for the same reason: the corrected constants no longer trip
        the solver at the fold, and the honesty path must stay exercised
        deterministically rather than by asserting on the bug's absence.
        """
        from caterva.compose import bifurcation as module
        from caterva.compose.analysis import DEFAULT_STARTS_PER_SPECIES
        from caterva.compose.analysis import StabilityReport

        values = linear_values(1.0, 3.0, 11)
        gap = values[1]
        real_analyse = module.analyse

        def analyse_with_gap(network: Any, /, **kw: Any) -> Any:
            n = next(p.value for p in network.parameters if p.id == "geneA_n")
            if n == pytest.approx(gap):
                return StabilityReport(
                    fixed_points=(),
                    starts_tried=kw.get(
                        "starts_per_species", DEFAULT_STARTS_PER_SPECIES
                    ),
                    species=tuple(s.id for s in network.species),
                )
            return real_analyse(network, **kw)

        monkeypatch.setattr(module, "analyse", analyse_with_gap)
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", values)

        # Asserted, not guarded by `if report.barren`. With the condition in
        # an `if`, a change that stopped producing a gap would skip every
        # assertion and the test would pass while checking nothing -- which
        # the repository's Vacuous Test Guard caught. The gap is the
        # PRECONDITION this test needs, so its absence must fail here rather
        # than silently disarm it.
        assert report.barren, (
            "the injected solver gap was not recorded as barren, so it "
            "cannot test that a gap fails to blind the detector"
        )
        assert report.bifurcations, (
            "a gap silenced the detector: " + report.summary()
        )
        assert "spans a value where the root find returned nothing" in (
            " ".join(b.detail for b in report.bifurcations)
        )

    def test_the_summary_never_contradicts_its_own_regions(self) -> None:
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", linear_values(1.0, 3.0, 11))
        summary = report.summary()
        distinct = {count for _, _, count in report.regions()}

        # Same correction as above: the multi-region case is what this test
        # is about, so it is asserted rather than used as a guard.
        assert len(distinct) > 1, (
            f"this sweep no longer crosses a transition (regions: {distinct}), "
            f"so there is no contradiction to check for"
        )
        assert "No change in the number or stability" not in summary

    def test_a_bifurcation_is_reported_as_an_interval_not_a_point(self) -> None:
        # A sweep locates a transition no more precisely than its own step.
        # Quoting a midpoint would claim a precision the method lacks.
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", linear_values(1.0, 3.0, 11))
        for bifurcation in report.bifurcations:
            assert bifurcation.below < bifurcation.above
            assert bifurcation.bracket == (bifurcation.below, bifurcation.above)

    def test_it_says_it_is_not_continuation(self) -> None:
        # Proper numerical continuation follows a branch through turning
        # points. This re-solves at each step and misses branches that live
        # between samples; the limitation is stated, not implied.
        network = recognise("a toggle switch between two repressors").network()
        summary = sweep(network, "geneA_n", linear_values(1.0, 2.0, 3)).summary()
        assert "not by numerical continuation" in summary

    def test_the_resolution_is_reported(self) -> None:
        network = recognise("a toggle switch between two repressors").network()
        report = sweep(network, "geneA_n", linear_values(1.0, 3.0, 11))
        assert report.resolution == pytest.approx(0.2)
        assert "resolution" in report.summary()


class TestRefusals:
    def test_sweeping_an_unknown_parameter_names_the_real_ones(self) -> None:
        network = recognise("a toggle switch between two repressors").network()
        with pytest.raises(KeyError, match="geneA_n"):
            sweep(network, "not_a_parameter", [1.0, 2.0])

    def test_a_sweep_does_not_mutate_the_caller_s_network(self) -> None:
        # The network is a frozen dataclass whose `replace` returns a copy,
        # which is easy to forget to use.
        network = recognise("a toggle switch between two repressors").network()
        before = {p.id: p.value for p in network.parameters}
        sweep(network, "geneA_n", [1.0, 5.0])
        after = {p.id: p.value for p in network.parameters}
        assert before == after
