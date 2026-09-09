"""Whether a conclusion survives the numbers it was computed from.

WHY THE TESTS HERE ARE MOSTLY ABOUT WHAT IS *NOT* CLAIMED
----------------------------------------------------------
A robustness figure is the easiest number in this module to over-read. "78 of
100 samples" looks like a probability, reads like a verdict, and is neither --
it is a count over a box that was chosen for want of a measured one.

So these pin the arithmetic against cases with known answers, and then spend
most of their length pinning the disclaimers: that a failed sample is not a
false one, that the box is reported alongside the fraction, that "every sample"
is never rendered as "always", and that varying rate constants and varying
concentrations are different questions with different answers.
"""

from __future__ import annotations

import math

import pytest

from Terium.compose.builder import Composition
from Terium.compose.library import SYNTHESIS_DEGRADATION
from Terium.compose.pipeline import compose
from Terium.compose.robustness import (
    DEFAULT_SAMPLES, SPREAD_DECADES, RobustnessError, RobustnessReport, Sample,
    assess, assess_model, exceeds, is_bistable, is_monostable, oscillates,
    settles_within,
)


def _turnover():
    composition = Composition("turnover")
    composition.add(SYNTHESIS_DEGRADATION, "x")
    return composition.to_network()


class TestAgainstAnAnalyticAnswer:
    def test_a_conclusion_true_everywhere_holds_in_every_sample(self) -> None:
        """dX/dt = ks - kd*X settles at ks/kd, which is positive for every
        positive ks and kd. No draw from a log-uniform box of positive
        values can make it negative, so this is exactly 100% and any other
        answer is arithmetic error rather than sampling noise.
        """
        report = assess(
            _turnover(), exceeds("x_X", 0.0),
            conclusion_name="x_X is positive", samples=40,
        )
        assert report.fraction == 1.0
        assert not report.failed

    def test_a_conclusion_false_everywhere_holds_in_none(self) -> None:
        report = assess(
            _turnover(), exceeds("x_X", 1e12),
            conclusion_name="x_X exceeds 1e12", samples=40,
        )
        assert report.fraction == 0.0

    def test_a_threshold_at_the_centre_splits_the_box(self) -> None:
        """The steady state is ks/kd = 10 at the placeholder values, and the
        box is symmetric in the logarithm around it. Sampling ks and kd
        independently over +/-1 decade makes log10(ks/kd) a symmetric
        triangular distribution centred on 1, so the fraction above 10 must
        be close to one half -- and, being symmetric, must not be close to 0
        or 1.
        """
        report = assess(
            _turnover(), exceeds("x_X", 10.0),
            conclusion_name="x_X exceeds its central value", samples=400, seed=3,
        )
        assert report.fraction == pytest.approx(0.5, abs=0.08)

    def test_the_binomial_error_shrinks_with_more_samples(self) -> None:
        small = assess(_turnover(), exceeds("x_X", 10.0), samples=50, seed=1)
        large = assess(_turnover(), exceeds("x_X", 10.0), samples=800, seed=1)
        assert large.uncertainty < small.uncertainty
        # And it shrinks like 1/sqrt(n), not arbitrarily.
        assert large.uncertainty == pytest.approx(
            small.uncertainty * math.sqrt(50 / 800), rel=0.5
        )


class TestDeterminism:
    def test_two_runs_of_the_same_seed_agree_exactly(self) -> None:
        # A robustness figure that moved between runs could not be cited.
        first = assess(_turnover(), exceeds("x_X", 10.0), samples=60, seed=7)
        second = assess(_turnover(), exceeds("x_X", 10.0), samples=60, seed=7)
        assert first.held_count == second.held_count
        assert [s.values for s in first.samples] == [s.values for s in second.samples]

    def test_a_different_seed_draws_different_values(self) -> None:
        # The seed is a real knob, not decoration.
        first = assess(_turnover(), exceeds("x_X", 10.0), samples=60, seed=1)
        second = assess(_turnover(), exceeds("x_X", 10.0), samples=60, seed=2)
        assert [s.values for s in first.samples] != [s.values for s in second.samples]

    def test_the_seed_is_reported(self) -> None:
        report = assess(_turnover(), exceeds("x_X", 10.0), samples=10, seed=11)
        assert report.seed == 11
        assert "seed 11" in report.summary()


class TestTheBoxIsLogUniformAndStated:
    def test_draws_stay_inside_the_stated_decades(self) -> None:
        base = {p.id: p.value for p in _turnover().parameters}
        report = assess(
            _turnover(), exceeds("x_X", 10.0), samples=300, spread_decades=1.0,
        )
        for sample in report.samples:
            for name, value in sample.values.items():
                ratio = abs(math.log10(value / base[name]))
                assert ratio <= 1.0 + 1e-9

    def test_the_draws_span_most_of_the_box(self) -> None:
        # A sampler that technically stayed in range but clustered at the
        # centre would explore nothing, and every conclusion would survive.
        base = {p.id: p.value for p in _turnover().parameters}
        report = assess(_turnover(), exceeds("x_X", 10.0), samples=300, seed=5)
        spans = []
        for name in report.varied:
            exponents = [
                math.log10(s.values[name] / base[name]) for s in report.samples
            ]
            spans.append(max(exponents) - min(exponents))
        assert min(spans) > 1.6, spans

    def test_a_wider_box_is_actually_wider(self) -> None:
        base = {p.id: p.value for p in _turnover().parameters}
        narrow = assess(_turnover(), exceeds("x_X", 10.0), samples=200,
                        spread_decades=0.5, seed=2)
        wide = assess(_turnover(), exceeds("x_X", 10.0), samples=200,
                      spread_decades=2.0, seed=2)

        def span(report):
            exps = [math.log10(s.values["x_ks"] / base["x_ks"])
                    for s in report.samples]
            return max(exps) - min(exps)

        assert span(wide) > 3 * span(narrow)

    def test_the_summary_states_the_box(self) -> None:
        # A fraction without its box is not a claim anyone can check.
        report = assess(
            _turnover(), exceeds("x_X", 10.0), samples=20, spread_decades=1.5,
        )
        summary = report.summary()
        assert "1.5 decade" in summary
        assert "log-uniformly" in summary

    def test_a_zero_width_box_is_refused(self) -> None:
        # Every draw would be the current values, so the fraction would be
        # 0 or 1 by construction and would look like evidence.
        with pytest.raises(RobustnessError, match="zero width"):
            assess(_turnover(), exceeds("x_X", 10.0), spread_decades=0.0)


class TestAFailedSampleIsNotAFalseOne:
    """The distinction that decides whether the number means anything.

    A steady-state search failing at an extreme corner of the box is a fact
    about the solver. Counting it against the mechanism would make every
    model look more fragile the wider the box got, which is exactly
    backwards.
    """

    def test_failures_are_excluded_from_the_fraction_not_counted_against(
        self,
    ) -> None:
        calls = {"n": 0}

        def flaky(network):
            calls["n"] += 1
            if calls["n"] % 2 == 0:
                raise RuntimeError("solver gave up")
            return True

        report = assess(_turnover(), flaky, samples=20)
        assert len(report.failed) == 10
        assert len(report.evaluated) == 10
        # Every evaluated sample was True, so the fraction is 1.0 -- not 0.5.
        assert report.fraction == 1.0

    def test_a_failure_is_none_and_not_false(self) -> None:
        def always_broken(network):
            raise RuntimeError("no")

        report = assess(_turnover(), always_broken, samples=5)
        assert all(s.held is None for s in report.samples)
        assert report.fraction is None
        assert "no sample could be evaluated" in report.describe_fraction()

    def test_the_summary_says_how_many_failed_and_why(self) -> None:
        def sometimes(network):
            raise RuntimeError("a very specific solver complaint")

        summary = assess(_turnover(), sometimes, samples=4).summary()
        assert "could not be evaluated" in summary
        assert "different facts" in summary
        assert "a very specific solver complaint" in summary


class TestWhatItRefusesToClaim:
    def test_a_full_pass_is_reported_as_every_sample_not_as_always(self) -> None:
        report = assess(_turnover(), exceeds("x_X", 0.0), samples=30)
        described = report.describe_fraction()
        assert "every one of the 30 sample(s)" in described
        assert "always" not in report.summary().lower()

    def test_the_summary_says_it_is_not_a_probability(self) -> None:
        report = assess(_turnover(), exceeds("x_X", 10.0), samples=20)
        summary = report.summary()
        assert "not a probability" in summary
        assert "may still fail just outside" in summary

    def test_bistability_is_named_for_what_the_search_found(self) -> None:
        # `analysis.py` reports "at least two stable states were FOUND",
        # never "this system is bistable". A robustness figure built on the
        # stronger reading would inherit that overclaim 200 times over.
        from Terium.compose import robustness

        assert "FOUND" in robustness.is_bistable.__doc__


class TestWhichParametersAreVaried:
    def test_a_composed_model_varies_only_its_unresolved_constants(self) -> None:
        """The rate constants are placeholders standing in for measurements.
        The concentrations are the user's scenario. Mixing them would make
        the headline number mean neither.
        """
        model = compose("three step phosphorylation cascade")
        report = assess_model(
            model, is_monostable(), conclusion_name="monostable", samples=4,
        )
        assert set(report.varied) == {q.parameter_id for q in model.resolvable}
        assert not any(name.endswith(("_X", "_Xp")) for name in report.varied)

    def test_including_concentrations_asks_a_different_question(self) -> None:
        model = compose("three step phosphorylation cascade")
        narrow = assess_model(model, is_monostable(), samples=2)
        wide = assess_model(
            model, is_monostable(), samples=2, include_concentrations=True,
        )
        assert set(narrow.varied) < set(wide.varied)

    def test_the_report_says_which_set_it_varied(self) -> None:
        model = compose("three step phosphorylation cascade")
        report = assess_model(model, is_monostable(), samples=2)
        assert f"{len(report.varied)} parameter(s) varied" in report.summary()

    def test_an_unknown_parameter_names_the_real_ones(self) -> None:
        with pytest.raises(RobustnessError, match="x_ks"):
            assess(_turnover(), exceeds("x_X", 1.0), vary=["nope"])


class TestParametersThatCannotBeSampled:
    def test_a_zero_valued_parameter_is_fixed_with_the_reason(self) -> None:
        """log(0) is not a number, and substituting a small positive value
        would change the model's STRUCTURE rather than its parameters -- a
        zero rate constant means a reaction that does not happen.
        """
        from dataclasses import replace

        network = _turnover()
        zeroed = replace(
            network,
            parameters=tuple(
                replace(p, value=0.0) if p.id == "x_ks" else p
                for p in network.parameters
            ),
        )
        report = assess(zeroed, lambda n: True, samples=5)
        assert "x_ks" in report.fixed
        assert "logarithm" in report.fixed["x_ks"]
        assert "x_ks" not in report.varied

    def test_the_summary_lists_what_was_held_fixed(self) -> None:
        from dataclasses import replace

        network = _turnover()
        zeroed = replace(
            network,
            parameters=tuple(
                replace(p, value=0.0) if p.id == "x_ks" else p
                for p in network.parameters
            ),
        )
        summary = assess(zeroed, lambda n: True, samples=5).summary()
        assert "held fixed" in summary
        assert "x_ks" in summary

    def test_nothing_samplable_is_refused_rather_than_reported_as_certain(
        self,
    ) -> None:
        # A box with no width in any direction would report the same answer
        # N times and call it a fraction.
        from dataclasses import replace

        network = _turnover()
        all_zero = replace(
            network,
            parameters=tuple(replace(p, value=0.0) for p in network.parameters),
        )
        with pytest.raises(RobustnessError, match="one repeated answer"):
            assess(all_zero, lambda n: True, samples=5)

    def test_a_model_with_nothing_unresolved_is_refused_with_the_alternative(
        self,
    ) -> None:
        class _Grounded:
            resolvable = ()

            class network:
                parameters = ()

        with pytest.raises(RobustnessError, match="include_concentrations"):
            assess_model(_Grounded(), lambda n: True)


class TestTheReadyMadeConclusions:
    def test_monostable_is_not_the_negation_of_bistable(self) -> None:
        """A draw where the search found NO stable state is neither. Folding
        that into "monostable" would report a model with no steady state as
        a model with one.
        """
        from Terium.compose import robustness

        assert "NOT the negation" in robustness.is_monostable.__doc__

        model = compose("an open system with constant substrate inflow")
        mono = assess_model(model, is_monostable(), samples=6)
        bi = assess_model(model, is_bistable(), samples=6)
        # An open system has no steady state at all: both must be false.
        assert mono.held_count == 0
        assert bi.held_count == 0

    def test_oscillation_excludes_a_stable_spiral(self) -> None:
        # A stable spiral rings and settles, which is not what anyone means
        # by "this oscillates". The distinction is the sign of the real part.
        from Terium.compose import robustness

        doc = robustness.oscillates.__doc__
        assert "stable spiral is excluded" in doc
        assert "positive real part" in doc

    def test_a_threshold_conclusion_refuses_on_two_stable_states(self) -> None:
        # "Does the output exceed 1 mM" has no answer when the system has
        # two outputs and which one it reaches depends on where it started.
        model = compose("a toggle switch between two repressors")
        report = assess_model(
            model, exceeds("geneA_X", 1.0), samples=4, spread_decades=0.05,
        )
        assert report.failed
        assert "no single answer" in report.failed[0].reason

    def test_settles_within_compares_against_the_stated_time(self) -> None:
        quick = assess(_turnover(), settles_within(1e9), samples=20)
        slow = assess(_turnover(), settles_within(1e-9), samples=20)
        assert quick.fraction == 1.0
        assert slow.fraction == 0.0


class TestTheStatedConstants:
    def test_the_spread_is_a_stated_judgement_with_its_reasoning(self) -> None:
        import inspect

        from Terium.compose import robustness

        source = inspect.getsource(robustness)
        assert "SPREAD_DECADES = 1.0" in source
        # It argues for itself rather than just existing.
        assert "Three decades would make almost every conclusion fail" in source

    def test_the_default_sample_count_is_justified_by_its_error(self) -> None:
        # sqrt(p(1-p)/n) at p = 0.5, n = 200 is about 3.5 percentage points.
        error = math.sqrt(0.25 / DEFAULT_SAMPLES)
        assert 0.03 < error < 0.04

    def test_a_sample_count_below_one_is_refused(self) -> None:
        with pytest.raises(RobustnessError, match="not a sample"):
            assess(_turnover(), lambda n: True, samples=0)
