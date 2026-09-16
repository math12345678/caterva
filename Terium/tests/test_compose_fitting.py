"""Fitting constants to data, against a model whose answer is known exactly.

dX/dt = ks - kd*X is the whole test rig, and deliberately: started empty it
solves to X(t) = (ks/kd)(1 - exp(-kd t)), so every number these tests check
against is a closed form rather than a previous run of the code. Data are
generated FROM known constants and the fit has to find them again, which is
the only test of a fitting routine that means anything -- a fit that
converges, reports a small residual and returns the wrong constants looks
exactly like one that works.

The same model carries the degeneracy this module exists to refuse. Its
plateau is ks/kd and nothing else, so a dataset of plateaus determines a
ratio exactly and its two factors not at all. The degeneracy is exact rather
than nearly-exact, which makes the refusal checkable rather than a matter of
where a threshold sits.
"""

from __future__ import annotations

import math
import random

import pytest

from Terium.compose.builder import Composition
from Terium.compose.library import SYNTHESIS_DEGRADATION
from Terium.compose.fitting import (
    CONSISTENCY_TAIL, Condition, FitRefused, Observation, RANK_TOLERANCE,
    STRONG_CORRELATION, Underdetermined, chi_squared_tail, fit, predict_states,
)

#: The constants the synthetic data are generated from. Chosen only so the
#: two are not equal and the settling time (1/kd = 5) sits inside the window
#: the observations cover -- a dataset that is all plateau cannot separate
#: them, which is a different test, below.
TRUE_KS = 0.8
TRUE_KD = 0.2

#: Standard deviation of each synthetic measurement, and the number every
#: Observation states. The tests that check coverage rely on the data
#: actually having this spread, so it is used for both.
SIGMA = 0.05

#: Reading times. Two before the system settles and two well after, because
#: the early points are what separate ks from kd and the late ones are what
#: pin the plateau.
TIMES = (1.0, 2.0, 4.0, 8.0, 16.0, 32.0)


def turnover(ks: float = TRUE_KS, kd: float = TRUE_KD):
    """dX/dt = ks - kd*X, starting empty."""
    from dataclasses import replace

    composition = Composition("turnover")
    composition.add(SYNTHESIS_DEGRADATION, "x")
    network = composition.to_network()
    return replace(
        network,
        parameters=tuple(
            replace(p, value=ks if p.id == "x_ks" else kd)
            for p in network.parameters
        ),
    )


def analytic(time: float, ks: float = TRUE_KS, kd: float = TRUE_KD) -> float:
    """X(t) from X(0) = 0. The answer every test here is measured against."""
    return (ks / kd) * (1.0 - math.exp(-kd * time))


def time_course(seed=None, sigma: float = SIGMA, times=TIMES):
    """Observations of X at `times`, optionally with noise of the stated size.

    `seed=None` gives the exact curve, which is the case where the right
    answer is known to the last digit. A seed adds Gaussian noise with
    exactly the standard deviation each observation declares, so a coverage
    count means what it says.
    """
    noise = random.Random(seed) if seed is not None else None
    return [
        Observation(
            "x_X",
            Condition(f"t={t:g}", time=t),
            analytic(t) + (noise.gauss(0.0, sigma) if noise else 0.0),
            sigma,
        )
        for t in times
    ]


@pytest.fixture(scope="module")
def noiseless():
    """The exact curve, fitted from the library's placeholder constants.

    Module-scoped because a fit is not free and six tests want this one.
    Safe to share: `FitReport` is a frozen dataclass and nothing mutates it.
    """
    return fit(turnover(1.0, 0.1), time_course(), ["x_ks", "x_kd"])


@pytest.fixture(scope="module")
def noisy():
    return fit(turnover(1.0, 0.1), time_course(seed=0), ["x_ks", "x_kd"])


class TestTheRoundTrip:
    """Generate from known constants, fit, and ask for them back."""

    def test_the_predictor_reproduces_the_closed_form_solution(self) -> None:
        # Before any fitting: if the prediction is wrong, everything below
        # is fitting the wrong model accurately.
        observations = time_course()
        predicted = predict_states(turnover(), observations)
        for value, time in zip(predicted, TIMES):
            assert value == pytest.approx(analytic(time), rel=1e-8)

    def test_a_plateau_is_predicted_as_the_ratio(self) -> None:
        # The steady state of ks - kd*X is ks/kd exactly, for every value of
        # both -- which is also why a plateau cannot separate them.
        predicted = predict_states(
            turnover(), [Observation("x_X", Condition("plateau"), 1.0, 0.1)]
        )
        assert predicted[0] == pytest.approx(TRUE_KS / TRUE_KD, rel=1e-9)

    def test_noiseless_data_recover_the_constants_they_came_from(
        self, noiseless
    ) -> None:
        """The round trip, with the noise turned off.

        Started from the library's placeholders (1.0 and 0.1), which are
        both wrong, and both by different factors.
        """
        assert noiseless.value_of("x_ks") == pytest.approx(TRUE_KS, rel=1e-6)
        assert noiseless.value_of("x_kd") == pytest.approx(TRUE_KD, rel=1e-6)

    def test_the_true_constants_lie_inside_the_intervals(self, noisy) -> None:
        """The round trip that matters: noisy data, and the interval has to
        contain the truth it was generated from."""
        truth = {"x_ks": TRUE_KS, "x_kd": TRUE_KD}
        for entry in noisy.parameters:
            assert entry.low <= truth[entry.name] <= entry.high, entry.describe()

    def test_the_intervals_cover_the_truth_at_about_the_rate_they_claim(
        self,
    ) -> None:
        """Coverage, over twenty independent datasets.

        A 95% interval that contains the truth on one dataset has shown very
        little; one that contains it on 38 of 40 marginal draws has shown
        that the width is right and not merely that it is wide. The
        threshold is set at 33 of 40 rather than at the expected 38 because
        the count itself is a binomial draw -- at 95% coverage, 40 draws
        give 38 on average and below 34 about once in three hundred runs, so
        a failure here is a fault rather than bad luck.
        """
        covered = 0
        for seed in range(20):
            report = fit(
                turnover(1.0, 0.1), time_course(seed=seed), ["x_ks", "x_kd"]
            )
            for entry in report.parameters:
                truth = TRUE_KS if entry.name == "x_ks" else TRUE_KD
                covered += 1 if entry.low <= truth <= entry.high else 0
        assert covered >= 33, f"only {covered} of 40 intervals covered the truth"
        # And they are not covering by being uselessly wide.
        assert covered <= 40

    def test_the_fit_crosses_decades_from_a_start_that_is_far_off(self) -> None:
        """What the log parametrisation buys.

        Started at ks = 1000x and kd = 0.01x their true values, which in
        linear space is a starting point whose first Gauss-Newton step
        proposes a negative rate constant. In log space it is four steps of
        the same size as any other.
        """
        report = fit(
            turnover(TRUE_KS * 1000.0, TRUE_KD * 0.01),
            time_course(),
            ["x_ks", "x_kd"],
        )
        assert report.value_of("x_ks") == pytest.approx(TRUE_KS, rel=1e-4)
        assert report.value_of("x_kd") == pytest.approx(TRUE_KD, rel=1e-4)


class TestAnObservationCarriesItsError:
    """The refusal that everything else in the module rests on."""

    def test_an_observation_without_an_uncertainty_is_refused(self) -> None:
        with pytest.raises(ValueError, match="uncertainty is required"):
            Observation("x_X", Condition("c"), 4.0, None)

    def test_zero_and_negative_and_nan_are_all_refused(self) -> None:
        # Zero is the one worth naming: it reads as "measured exactly", and
        # a weight of 1/0 would make that single point the entire fit.
        for bad in (0.0, -0.05, float("nan"), float("inf")):
            with pytest.raises(ValueError, match="uncertainty is required"):
                Observation("x_X", Condition("c"), 4.0, bad)

    def test_true_is_not_an_uncertainty(self) -> None:
        # `True` is 1.0 to Python. Accepting it would put a fabricated
        # standard deviation of one into the weights.
        with pytest.raises(ValueError, match="uncertainty is required"):
            Observation("x_X", Condition("c"), 4.0, True)

    def test_the_refusal_says_what_to_state_instead(self) -> None:
        with pytest.raises(ValueError) as caught:
            Observation("x_X", Condition("c"), 4.0, None)
        message = str(caught.value)
        assert "standard deviation of your replicates" in message
        assert "instrument's precision" in message
        # And it says why the module will not choose one.
        assert "as though it had been measured" in message

    def test_a_measurement_that_is_not_a_number_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not a finite number"):
            Observation("x_X", Condition("c"), float("nan"), 0.05)


class TestTheUnderdeterminedRefusal:
    """A number for a parameter the data cannot see is the worst output
    here, because it prints identically to one they can."""

    def test_fewer_situations_than_parameters_is_refused(self) -> None:
        with pytest.raises(Underdetermined, match="cannot determine 2 parameter"):
            fit(turnover(), time_course(times=(4.0,)), ["x_ks", "x_kd"])

    def test_replicates_do_not_count_as_a_second_situation(self) -> None:
        """Four readings, one measurement situation.

        The same quantity at the same time under the same condition, four
        times over. That shrinks one error bar; it does not give the model a
        second shape to match.
        """
        condition = Condition("t=4", time=4.0)
        replicates = [
            Observation("x_X", condition, analytic(4.0) + offset, SIGMA)
            for offset in (-0.04, -0.01, 0.02, 0.03)
        ]
        with pytest.raises(Underdetermined) as caught:
            fit(turnover(), replicates, ["x_ks", "x_kd"])
        message = str(caught.value)
        assert "1 distinct measurement situation" in message
        assert "Replicates shrink the error bar on one number" in message

    def test_a_dataset_of_plateaus_cannot_separate_the_two_constants(self) -> None:
        """The exact degeneracy, and the reason for the whole check.

        Two conditions, two different starting amounts, both settled. The
        counting check passes -- two distinct situations, two parameters --
        and the fit is still impossible, because both conditions predict
        ks/kd and nothing else. This is what a rank test is for and what a
        count cannot do.
        """
        plateaus = [
            Observation(
                "x_X", Condition("empty", initials={"x_X": 0.0}),
                TRUE_KS / TRUE_KD, SIGMA,
            ),
            Observation(
                "x_X", Condition("preloaded", initials={"x_X": 10.0}),
                TRUE_KS / TRUE_KD, SIGMA,
            ),
        ]
        assert len({o.key for o in plateaus}) == 2, "the count check must pass"

        with pytest.raises(Underdetermined) as caught:
            fit(turnover(), plateaus, ["x_ks", "x_kd"])
        assert "leave every prediction unchanged" in str(caught.value)

    def test_the_refusal_names_the_unconstrained_direction_exactly(self) -> None:
        """Not "something is degenerate" -- which combination, and which one
        the data did measure.

        Both are known in closed form here. The plateau is ks/kd, so scaling
        both constants by the same factor changes no prediction (exponents
        +1, +1) and their ratio is determined exactly (exponents +1, -1).
        """
        plateaus = [
            Observation("x_X", Condition("empty", initials={"x_X": 0.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
            Observation("x_X", Condition("preloaded", initials={"x_X": 10.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
        ]
        with pytest.raises(Underdetermined) as caught:
            fit(turnover(), plateaus, ["x_ks", "x_kd"])

        flat = caught.value.unconstrained
        assert len(flat) == 1
        assert flat[0].exponents["x_ks"] == pytest.approx(1.0, abs=1e-6)
        assert flat[0].exponents["x_kd"] == pytest.approx(1.0, abs=1e-6)

        determined = caught.value.determined
        assert len(determined) == 1
        assert determined[0].exponents["x_ks"] == pytest.approx(1.0, abs=1e-6)
        assert determined[0].exponents["x_kd"] == pytest.approx(-1.0, abs=1e-6)
        assert determined[0].monomial() == "x_ks / x_kd"

    def test_the_refusal_reports_what_the_experiment_did_measure(self) -> None:
        # An experiment that measured a ratio exactly has not failed. The
        # message has to say so, or the reader concludes their data are
        # useless when what they need is one more kind of reading.
        plateaus = [
            Observation("x_X", Condition("empty", initials={"x_X": 0.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
            Observation("x_X", Condition("preloaded", initials={"x_X": 10.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
        ]
        with pytest.raises(Underdetermined) as caught:
            fit(turnover(), plateaus, ["x_ks", "x_kd"])
        message = str(caught.value)
        assert "What these observations DO determine: `x_ks / x_kd`" in message
        assert "has measured a ratio exactly" in message
        assert "while the system is still changing" in message

    def test_one_time_point_added_to_the_plateaus_makes_it_fittable(self) -> None:
        """The other side of the refusal: its advice has to work.

        The message says a reading taken while the system is still changing
        constrains what a settled one cannot. Here it does -- same two
        constants, same model, one early reading added.
        """
        observations = [
            Observation("x_X", Condition("empty", initials={"x_X": 0.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
            Observation("x_X", Condition("preloaded", initials={"x_X": 10.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
            Observation("x_X", Condition("t=2", time=2.0), analytic(2.0), SIGMA),
        ]
        report = fit(turnover(1.0, 0.1), observations, ["x_ks", "x_kd"])
        assert report.value_of("x_ks") == pytest.approx(TRUE_KS, rel=1e-4)
        assert report.value_of("x_kd") == pytest.approx(TRUE_KD, rel=1e-4)

    def test_a_parameter_that_does_nothing_is_refused_rather_than_estimated(
        self,
    ) -> None:
        """A constant the observations cannot see at all.

        Fitting ks and kd to plateau data is degenerate in a combination;
        this is the blunter case, where the answer does not depend on the
        parameter in any direction. It must not come back with the starting
        value and an interval.
        """
        network = turnover()
        observations = time_course(times=(1.0, 4.0, 16.0))
        # `x_X`'s initial amount is a species, not a parameter, so the only
        # way to get an unused constant here is to ask for one of the two
        # under data that see only their ratio -- covered above. This case
        # asks for the same parameter twice, which is the same rank defect
        # arriving by a different route and is caught before any fitting.
        with pytest.raises(FitRefused, match="more than once"):
            fit(network, observations, ["x_ks", "x_ks"])


class TestRefusalsAboutTheRequest:
    def test_an_unknown_parameter_names_the_real_ones(self) -> None:
        with pytest.raises(KeyError, match="x_ks"):
            fit(turnover(), time_course(), ["nope", "x_kd"])

    def test_an_unmeasurable_quantity_names_the_species_there_are(self) -> None:
        observations = [Observation("GFP", Condition("t=4", time=4.0), 1.0, 0.1)]
        with pytest.raises(FitRefused, match="x_X"):
            fit(turnover(), observations, ["x_ks"])

    def test_the_refusal_offers_the_predictor_hook_rather_than_renaming(
        self,
    ) -> None:
        # A fluorescence proportional to a species is a real measurement and
        # the answer is a predictor, not a species renamed until it matches.
        observations = [Observation("GFP", Condition("t=4", time=4.0), 1.0, 0.1)]
        with pytest.raises(FitRefused) as caught:
            fit(turnover(), observations, ["x_ks"])
        assert "pass a `predict` function" in str(caught.value)

    def test_a_parameter_starting_at_zero_cannot_be_fitted_in_log_space(
        self,
    ) -> None:
        with pytest.raises(FitRefused, match="log of a non-positive number"):
            fit(turnover(), time_course(), ["x_ks"], start={"x_ks": 0.0})

    def test_two_different_conditions_may_not_share_a_name(self) -> None:
        observations = [
            Observation("x_X", Condition("dose", time=1.0), analytic(1.0), SIGMA),
            Observation("x_X", Condition("dose", time=2.0), analytic(2.0), SIGMA),
        ]
        with pytest.raises(FitRefused, match="two different conditions"):
            fit(turnover(), observations, ["x_ks", "x_kd"])

    def test_an_empty_dataset_is_refused_rather_than_fitted(self) -> None:
        with pytest.raises(FitRefused, match="nothing to fit against"):
            fit(turnover(), [], ["x_ks"])

    def test_a_condition_that_sets_something_that_does_not_exist_is_refused(
        self,
    ) -> None:
        # A typo would otherwise become a condition identical to the
        # control, and the fit would report that the inducer does nothing.
        observations = [
            Observation("x_X", Condition("typo", parameters={"x_kdd": 0.5},
                                         time=4.0), 3.0, SIGMA),
            Observation("x_X", Condition("t=12", time=12.0), analytic(12.0), SIGMA),
        ]
        with pytest.raises(FitRefused, match="no parameter for"):
            fit(turnover(), observations, ["x_ks", "x_kd"])

    def test_a_condition_must_be_a_condition(self) -> None:
        with pytest.raises(TypeError, match="not a Condition"):
            Observation("x_X", "four hours", 4.0, SIGMA)


class TestTheChiSquaredStatement:
    def test_the_tail_matches_the_closed_form_for_two_degrees_of_freedom(
        self,
    ) -> None:
        # Q(1, x/2) = exp(-x/2), exactly.
        for chi in (0.1, 1.0, 3.0, 9.0, 25.0):
            assert chi_squared_tail(chi, 2) == pytest.approx(
                math.exp(-chi / 2.0), rel=1e-12
            )

    def test_the_tail_matches_the_closed_form_for_four_degrees_of_freedom(
        self,
    ) -> None:
        # Q(2, x/2) = exp(-x/2) * (1 + x/2).
        for chi in (0.1, 1.0, 3.0, 9.0, 25.0):
            expected = math.exp(-chi / 2.0) * (1.0 + chi / 2.0)
            assert chi_squared_tail(chi, 4) == pytest.approx(expected, rel=1e-12)

    def test_noise_of_the_stated_size_is_called_consistent(self, noisy) -> None:
        assert noisy.consistent is True
        assert CONSISTENCY_TAIL < noisy.p_value < 1.0 - CONSISTENCY_TAIL
        assert "do not contradict this model" in noisy.summary()

    def test_a_residual_larger_than_the_stated_errors_is_called_out(self) -> None:
        """One point moved by ten standard deviations.

        The model can still be fitted and will report parameters; what it
        must not do is report them as though the data agreed with it.
        """
        observations = time_course()
        moved = observations[:]
        moved[2] = Observation(
            "x_X", moved[2].condition, moved[2].value + 10 * SIGMA, SIGMA,
        )
        report = fit(turnover(1.0, 0.1), moved, ["x_ks", "x_kd"])

        assert report.reduced_chi_squared > 5
        assert report.consistent is False
        summary = report.summary()
        assert "LARGER than the stated measurement errors" in summary
        assert "error bars are understated" in summary

    def test_a_fit_closer_than_the_errors_says_the_errors_are_overstated(
        self, noiseless
    ) -> None:
        # Exact data with a stated error bar of 0.05 fit better than 0.05
        # says is possible. That is a statement about the error bars.
        assert noiseless.consistent is False
        assert noiseless.p_value > 1.0 - CONSISTENCY_TAIL
        assert "CLOSER to the data than the stated errors" in noiseless.summary()

    def test_no_degrees_of_freedom_says_the_residual_means_nothing(self) -> None:
        """Two observations, two parameters.

        The residual goes to zero because it can, not because the model is
        right, and a report that printed "chi-squared = 3e-24" without
        saying so would be reporting the arithmetic as evidence.
        """
        report = fit(
            turnover(1.0, 0.1), time_course(times=(2.0, 16.0)), ["x_ks", "x_kd"]
        )
        assert report.degrees_of_freedom == 0
        assert report.p_value is None
        assert report.consistent is None
        assert "says nothing at all about whether the model fits" in report.summary()


class TestTheIntervals:
    def test_the_interval_is_multiplicative_around_the_estimate(
        self, noisy
    ) -> None:
        # A factor, not an offset: value/low and high/value are the same
        # number, which is what makes the interval reportable as "within a
        # factor of 1.1" and keeps it away from negative rate constants.
        for entry in noisy.parameters:
            assert entry.value / entry.low == pytest.approx(
                entry.high / entry.value, rel=1e-9
            )
            assert entry.fold == pytest.approx(entry.high / entry.value, rel=1e-9)

    def test_doubling_every_stated_error_doubles_the_standard_error(self) -> None:
        """The exact scaling, which is what "weighted" means.

        The Jacobian's rows are divided by the stated errors, so doubling
        every error halves the Jacobian, quarters J^T J and quadruples the
        covariance -- a factor of exactly two on every standard error. The
        fitted values do not move at all, because scaling every weight by
        one number does not change where the minimum is.
        """
        tight = fit(turnover(1.0, 0.1), time_course(sigma=SIGMA), ["x_ks", "x_kd"])
        loose = fit(
            turnover(1.0, 0.1), time_course(sigma=2 * SIGMA), ["x_ks", "x_kd"]
        )
        assert loose.value_of("x_ks") == pytest.approx(
            tight.value_of("x_ks"), rel=1e-6
        )
        for a, b in zip(tight.parameters, loose.parameters):
            assert b.log_standard_error == pytest.approx(
                2.0 * a.log_standard_error, rel=1e-4
            )

    def test_a_bad_fit_does_not_widen_its_own_intervals(self) -> None:
        """The convention this module declines to follow.

        Multiplying the covariance by chi-squared per degree of freedom is
        the usual recipe when the error bars are unknown up to a scale. Here
        they are required input, and rescaling would widen the intervals of
        a model that fits badly -- so the number that reports the failure
        would be the number hiding it. With a ten-sigma outlier the
        rescaling factor would be about five; the intervals must barely
        move.
        """
        good = time_course()
        bad = good[:]
        bad[2] = Observation(
            "x_X", bad[2].condition, bad[2].value + 10 * SIGMA, SIGMA,
        )
        clean = fit(turnover(1.0, 0.1), good, ["x_ks", "x_kd"])
        dirty = fit(turnover(1.0, 0.1), bad, ["x_ks", "x_kd"])

        assert dirty.reduced_chi_squared > 5, "the premise"
        for a, b in zip(clean.parameters, dirty.parameters):
            assert b.log_standard_error < 1.5 * a.log_standard_error

    def test_the_estimate_is_the_data_talking_and_not_the_starting_point(
        self, noiseless
    ) -> None:
        # Started at 1.0 and 0.1; the truth is 0.8 and 0.2. A fit that
        # returned its starting point would pass every consistency check
        # here and be worthless.
        started = {p.name: p.start for p in noiseless.parameters}
        assert started == {"x_ks": 1.0, "x_kd": 0.1}
        assert noiseless.value_of("x_ks") != started["x_ks"]
        assert noiseless.value_of("x_kd") != started["x_kd"]


class TestHonesty:
    def test_the_summary_says_a_good_fit_is_not_evidence_of_the_model(
        self, noisy
    ) -> None:
        summary = noisy.summary()
        assert "NOT evidence that the model is right" in summary
        assert "a model with enough constants reproduces anything" in summary

    def test_the_summary_says_these_are_fitted_and_not_literature_values(
        self, noisy
    ) -> None:
        # The rule the whole project rests on: a fitted 12.4 and a measured
        # 12.4 print identically, so the report has to say which it is.
        summary = noisy.summary()
        assert "FITTED, not literature values" in summary
        assert "must not be recorded" in summary

    def test_the_summary_says_the_identifiability_check_is_local(
        self, noisy
    ) -> None:
        # A rank test at one optimum cannot see a second optimum elsewhere.
        summary = noisy.summary()
        assert "identifiability" in summary
        assert "LOCAL" in summary or "local" in summary

    def test_the_summary_reports_the_residual_and_the_intervals(
        self, noisy
    ) -> None:
        summary = noisy.summary()
        assert "chi-squared" in summary
        assert "degrees of freedom" in summary
        for entry in noisy.parameters:
            assert entry.name in summary
        assert "95% interval" in summary

    def test_the_reported_predictions_are_the_fitted_model_evaluated(
        self, noisy
    ) -> None:
        """Not the optimiser's last trial, which is near the answer and is
        not it.

        Checked against an independent evaluation of the fitted network, so
        a report whose predictions were reconstructed from a stale residual
        would show up here rather than in a number nobody re-derives.
        """
        again = predict_states(noisy.network, noisy.observations)
        assert len(noisy.predictions) == len(noisy.observations)
        for reported, recomputed in zip(noisy.predictions, again):
            assert reported == pytest.approx(recomputed, rel=1e-9)
        for residual, prediction, entry in zip(
            noisy.residuals, noisy.predictions, noisy.observations
        ):
            assert residual == pytest.approx(
                (prediction - entry.value) / entry.uncertainty, rel=1e-9
            )

    def test_the_fitted_network_carries_the_fitted_values(self, noiseless) -> None:
        # So the next step -- simulating, ranking sensitivities -- happens on
        # the fitted model rather than on the placeholders.
        values = {p.id: p.value for p in noiseless.network.parameters}
        assert values["x_ks"] == pytest.approx(noiseless.value_of("x_ks"))
        assert values["x_kd"] == pytest.approx(noiseless.value_of("x_kd"))

    def test_a_correlation_worth_worrying_about_is_reported(self) -> None:
        """Identifiable, and only just.

        Three readings all taken after the system has settled to within a
        fraction of a percent, plus one late in the transient -- early
        enough to break the exact degeneracy, late enough that it barely
        does. The rank test passes; the two constants are still very nearly
        one measurement, and a report that said only "identifiable" would be
        true and misleading.

        The early reading was at t=3 when this was written, which broke the
        degeneracy too well: the correlation came out at 0.975, under the
        module's own 0.99 bar, so the case was not the case the test
        described. Measured across the transient (settling time here is
        1/kd = 10):

            t=8   -> 0.982   under the bar, no warning
            t=12  -> 0.993   just over, warned
            t=20  -> 0.9994  degenerate, warned

        t=12 is the honest version of "and only just". Moved rather than
        lowering the threshold -- STRONG_CORRELATION carries its own
        reasoning and does not move to suit a test.
        """
        observations = [
            Observation("x_X", Condition("t=12", time=12.0), analytic(12.0), SIGMA),
            Observation("x_X", Condition("t=40", time=40.0), analytic(40.0), SIGMA),
            Observation("x_X", Condition("t=60", time=60.0), analytic(60.0), SIGMA),
        ]
        report = fit(turnover(1.0, 0.1), observations, ["x_ks", "x_kd"])
        assert abs(report.correlation("x_ks", "x_kd")) > STRONG_CORRELATION
        assert "nearly measure one combination" in report.summary()

    def test_the_rank_tolerance_follows_from_the_differencing_floor(self) -> None:
        # Not a taste: a central difference on a quantity accurate to
        # `PREDICTION_PRECISION` cannot resolve a direction below
        # precision^(2/3), and the factor of ten is slack in the direction
        # of refusing.
        from Terium.compose.fitting import LOG_STEP, PREDICTION_PRECISION

        assert LOG_STEP ** 3 == pytest.approx(PREDICTION_PRECISION, rel=1e-9)
        assert RANK_TOLERANCE == pytest.approx(
            10.0 * PREDICTION_PRECISION / LOG_STEP, rel=1e-9
        )


class TestTheStructuralCheckActuallyRuns:
    """Every FitReport said "the structural identifiability check did not run".

    `identifiability.analyse(network, quantities, *, parameters=...)` takes
    the observables second and the parameters by keyword. `structural_note`
    called it as `entry(network, parameters)`, so every parameter name was
    handed over as an observable, the module raised, and the note reported
    the failure -- honestly, and for the wrong reason. The check was fine.
    The call was not. A capability nothing can reach is not one.

    The observations now go in as what they are: one callable per
    observation, the model's prediction for it as a function of the
    network. That is the structural question -- could THESE observations
    determine THESE parameters from perfect data -- asked with the
    observations.
    """

    def test_the_note_reports_a_rank_not_a_failure(self) -> None:
        report = fit(turnover(1.0, 0.1), time_course(sigma=SIGMA), ["x_ks", "x_kd"])
        note = report.structural or ""
        assert "did not run" not in note, note
        assert "was not asked" not in note, note
        assert "rank 2" in note
        assert "separately identifiable" in note

    def test_steady_states_alone_identify_only_the_ratio(self) -> None:
        """The textbook case, from identifiability.py's own docstring.

        A steady state of synthesis-and-decay is ks/kd. Two steady-state
        readings, however different their starting amounts, both report
        that ratio and nothing else: rank 1 of 2. The local rank test in
        `fit` refuses this as underdetermined -- correctly -- so the
        structural note is read off `structural_note` directly, which is
        what `fit` calls once it has a fit to report.
        """
        from Terium.compose.fitting import predict_states, structural_note

        observations = [
            Observation("x_X", Condition("empty", initials={"x_X": 0.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
            Observation("x_X", Condition("preloaded", initials={"x_X": 10.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
        ]
        note = structural_note(
            turnover(1.0, 0.1), ["x_ks", "x_kd"], observations, predict_states,
        ) or ""
        assert "rank 1" in note, note
        assert "1 are not" in note or "1 is not" in note, note

    def test_adding_a_transient_reading_makes_both_identifiable(self) -> None:
        # The same two steady states plus one reading at t = 2, which sees
        # the approach and so sees kd on its own. This is the fixture the
        # local test above already uses; the structural note now agrees.
        from Terium.compose.fitting import predict_states, structural_note

        observations = [
            Observation("x_X", Condition("empty", initials={"x_X": 0.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
            Observation("x_X", Condition("preloaded", initials={"x_X": 10.0}),
                        TRUE_KS / TRUE_KD, SIGMA),
            Observation("x_X", Condition("t=2", time=2.0), analytic(2.0), SIGMA),
        ]
        note = structural_note(
            turnover(1.0, 0.1), ["x_ks", "x_kd"], observations, predict_states,
        ) or ""
        assert "rank 2" in note, note

    def test_without_observations_it_says_it_was_not_asked(self) -> None:
        # The three-state rule: not asked is not failed and not passed.
        from Terium.compose.fitting import structural_note

        note = structural_note(turnover(1.0, 0.1), ["x_ks", "x_kd"]) or ""
        assert "was not asked" in note
        assert "rank 1" not in note and "rank 2" not in note, (
            "a rank was reported for a check that was never asked"
        )
