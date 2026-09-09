"""The compose module's answers, checked against each other.

Two halves, and the second is the point.

The first pins that every cross-check AGREES on models that are known
sound, and prefers models whose answers can be written down. First-order
turnover has steady state ks/kd, settling time 1/kd and sensitivities of
exactly +1 and -1. A -> B has all of those AND a conservation law, so it
is the one all five checks run on together. The three-tier cascade has
none of them in closed form and is here for the opposite reason: it is
nine species with derived conservation laws and a saturating steady state,
which is the population this package actually serves.

The second breaks each check's subject on purpose and pins that the check
catches it. A validator nobody has ever seen fail is not a validator: it is
a function that returns "agree", and the models in the library are all
sound, so nothing here would ever have distinguished the two. Every check
therefore has a test that hands it a wrong answer -- a state that is not a
fixed point, a trajectory whose conserved total drifts, a settling time off
by a factor of ten, a sensitivity with its sign flipped, a rate constant
declared in the wrong unit -- and asserts on the verdict AND on the module
the finding tells the reader to doubt.
"""

from __future__ import annotations

import importlib.util
import math
from dataclasses import replace

import pytest

from Terium.compose.builder import Composition
from Terium.compose.grammar import Recognition
from Terium.compose.library import (
    MASS_ACTION_CONVERSION, SYNTHESIS_DEGRADATION,
)
from Terium.compose.motifs import (
    KIND_RATE_CONSTANT, Motif, MotifParameter, Port, ReactionTemplate,
    ROLE_PRODUCT, ROLE_SUBSTRATE,
)
from Terium.compose.pipeline import ComposedModel, compose
from Terium.compose.sensitivity import analyse as sensitivity_analyse
from Terium.compose.sensitivity import steady_state_of
from Terium.compose.validate import (
    AGREE, CHECKS, CHECK_CONSERVATION, CHECK_DIMENSIONS, CHECK_FIXED_POINT,
    CHECK_SENSITIVITY, CHECK_SETTLING, CONTRADICTION, COARSE_SPAN,
    DIVERGENCE, Finding, SETTLING_FRACTION, SETTLING_TOLERANCE_FACTOR,
    UNCHECKED, ValidationError, ValidationReport, conservation_findings,
    dimension_findings, fixed_point_findings, fixed_point_verdict,
    observed_timescale, residual_at, sensitivity_findings,
    sensitivity_verdict, settling_findings_from, settling_verdict,
    state_scale, validate,
)

#: The trajectory half of these checks needs libRoadRunner; the arithmetic
#: half does not. Marked per-class rather than skipping the module, so an
#: installation without the engine still runs every verdict, every refusal
#: and every analytic measurement -- which is most of what is here.
needs_engine = pytest.mark.skipif(
    importlib.util.find_spec("roadrunner") is None,
    reason="the trajectory half of these checks needs the simulation engine",
)


# ---------------------------------------------------------------------------
# Models whose answers are known in closed form
# ---------------------------------------------------------------------------
#
# dX/dt = ks - kd*X, with the library's ks = 1 and kd = 0.1. Every quantity
# these checks compare has an exact value here:
#
#     steady state      ks / kd  = 10
#     settling time     1  / kd  = 10
#     dS/d(ks)                   = +1
#     dS/d(kd)                   = -1
#
# so a cross-check that agrees with itself but disagrees with the algebra is
# still caught. Cross-checks that can only be tested against each other
# would be a closed circle.

TURNOVER_STEADY_STATE = 10.0
TURNOVER_TIMESCALE = 10.0


def _as_model(composition: Composition, name: str) -> ComposedModel:
    """A `ComposedModel` around a hand-built composition.

    `simulate.run` reads the composition's dimensional findings before it
    will integrate, so these checks need the composition and not only the
    network. `compose()` is the usual way to get one; a test that wants a
    composition the grammar cannot produce -- a motif with a deliberately
    wrong unit -- has to assemble the wrapper itself.
    """
    network = composition.to_network()
    return ComposedModel(
        query=name,
        recognition=Recognition(composition, rule=name, reading="built by hand"),
        network=network,
        resolvable=composition.quantities_to_resolve(),
        chosen=composition.chosen_quantities(),
        subject=None,
    )


@pytest.fixture(scope="module")
def turnover() -> ComposedModel:
    composition = Composition("turnover")
    composition.add(SYNTHESIS_DEGRADATION, "x")
    return _as_model(composition, "turnover")


@pytest.fixture(scope="module")
def conversion() -> ComposedModel:
    """A -> B. One reaction, one conservation law: `c_A + c_B`."""
    composition = Composition("conversion")
    composition.add(MASS_ACTION_CONVERSION, "c")
    return _as_model(composition, "conversion")


@pytest.fixture(scope="module")
def cascade() -> ComposedModel:
    # Expensive, and shared: the steady-state search behind several of
    # these runs a root find from sixty-four starting points.
    return compose("three step phosphorylation cascade")


def _exponential_approach(
    timescale: float, target: float, start: float, end: float, points: int
):
    """The exact trajectory of dX/dt = ks - kd*X, as (times, columns).

    Written from the closed-form solution rather than integrated, so the
    measurement being tested is checked against algebra instead of against
    another of Terrium's numerical answers. The whole file would otherwise
    be a closed circle of approximations agreeing with each other.
    """
    times = tuple(end * i / (points - 1) for i in range(points))
    values = tuple(
        target + (start - target) * math.exp(-t / timescale) for t in times
    )
    return times, {"x_X": values}


# ---------------------------------------------------------------------------
# Every check agrees on models that are sound
# ---------------------------------------------------------------------------


class TestSoundModelsPass:
    def test_the_library_motifs_balance_dimensionally(
        self, turnover, cascade
    ) -> None:
        """Both compositions, because they exercise different rate laws.

        The turnover motif's laws are a bare constant and a first-order
        term; the cascade's are two saturating ones with an enzyme in each.
        """
        for model in (turnover, cascade):
            findings = dimension_findings(model.recognition.composition)
            assert [f.severity for f in findings] == [AGREE], model.query
        assert dimension_findings(turnover.recognition.composition)[0].check == (
            CHECK_DIMENSIONS
        )

    def test_the_turnover_sensitivities_survive_a_coarse_re_solve(
        self, turnover
    ) -> None:
        """The analytic case, both ways.

        S = +1 for ks and -1 for kd exactly, for every value of both. The
        fine difference takes a step of a few parts in a million; the coarse
        one re-solves ten percent away. They must agree, and they must agree
        with the algebra.
        """
        findings = sensitivity_findings(
            turnover.network, steady_state_of("x_X")
        )
        by_name = {f.subject: f for f in findings}
        assert set(by_name) == {"x_ks", "x_kd"}
        assert by_name["x_ks"].severity == AGREE, by_name["x_ks"].describe()
        assert by_name["x_kd"].severity == AGREE, by_name["x_kd"].describe()
        assert by_name["x_ks"].measured["fine"] == pytest.approx(1.0, rel=1e-4)
        assert by_name["x_kd"].measured["coarse"] == pytest.approx(-1.0, rel=0.02)

    def test_an_agreement_carries_no_doubt(self, turnover) -> None:
        # There is nothing to doubt when two independent routes agree, and
        # a `doubt` on an agreement would be a suspect nobody accused.
        findings = sensitivity_findings(
            turnover.network, steady_state_of("x_X")
        )
        assert all(f.doubt == "" for f in findings)

    @needs_engine
    def test_the_turnover_steady_state_does_not_move(self, turnover) -> None:
        """The root finder's answer, handed to the integrator.

        Two compilations of one rate law -- Python's `eval` on one side,
        Antimony and libRoadRunner on the other -- and one arithmetic must
        not undo the other.
        """
        findings = fixed_point_findings(turnover)
        assert [f.severity for f in findings] == [AGREE], [
            f.describe() for f in findings
        ]
        assert findings[0].measured["relative_drift"] < 1e-4

    @needs_engine
    def test_the_cascade_conservation_laws_survive_its_trajectory(
        self, cascade
    ) -> None:
        from Terium.compose.simulate import run

        trajectory = run(cascade, points=101)
        findings = conservation_findings(cascade.network, trajectory.columns)
        assert len(findings) >= 3, "the cascade conserves protein in each tier"
        assert all(f.severity == AGREE for f in findings), [
            f.describe() for f in findings
        ]

    @needs_engine
    def test_the_turnover_settling_time_matches_its_trajectory(
        self, turnover
    ) -> None:
        """1/kd = 10, predicted from an eigenvalue and measured from a curve.

        The prediction comes from the smallest real part of a
        finite-difference Jacobian; the measurement comes from when the
        integrator's trajectory got within a twentieth of where it started.
        Nothing connects the two but the model.
        """
        from Terium.compose.analysis import analyse
        from Terium.compose.simulate import run

        point = analyse(turnover.network).stable_points[0]
        assert point.slowest_timescale == pytest.approx(
            TURNOVER_TIMESCALE, rel=1e-6
        )

        trajectory = run(turnover, end=80.0, points=801)
        findings = settling_findings_from(
            trajectory.times, trajectory.columns, point.state,
            point.slowest_timescale, window=80.0,
        )
        assert [f.severity for f in findings] == [AGREE], findings[0].describe()
        assert findings[0].measured["observed"] == pytest.approx(
            TURNOVER_TIMESCALE, rel=1e-3
        )

    @needs_engine
    def test_all_five_checks_agree_on_a_model_with_closed_form_answers(
        self, conversion
    ) -> None:
        """A -> B at rate k*A, where every answer this module compares is
        known without a computer.

        Steady state A = 0, B = 1. Settling time 1/k = 1. `c_A + c_B` is
        conserved, so B's steady value does not depend on k at all and every
        sensitivity is exactly zero. Five checks, five closed-form answers,
        and if the package disagreed with any of them the disagreement would
        be with algebra rather than with itself.
        """
        report = validate(conversion, species="c_B")
        assert not report.contradictions, report.summary()
        assert set(report.checks_run()) == set(CHECKS), report.summary()

    @needs_engine
    def test_the_cascade_is_self_consistent(self, cascade) -> None:
        """The model the grammar exists for, and the refusal to guess.

        No species is named, so the sensitivity cross-check reports itself
        unchecked rather than picking one of nine and quietly deciding which
        of the model's conclusions gets examined. The other four run, and
        this is the model whose conservation laws and nine-species steady
        state make them worth running.
        """
        report = validate(cascade, points=201)
        assert not report.contradictions, report.summary()
        assert set(report.checks_run()) == set(CHECKS) - {CHECK_SENSITIVITY}
        unchecked = [f for f in report.unchecked if f.check == CHECK_SENSITIVITY]
        assert unchecked and "no quantity was named" in unchecked[0].detail


# ---------------------------------------------------------------------------
# The fixed-point check, broken on purpose
# ---------------------------------------------------------------------------


class TestTheFixedPointCheckCatchesAStateThatIsNotOne:
    """The check exists for one failure and this is it.

    `analysis.analyse` says the system rests at x = 10. If the integrator
    were handed some other state and reported it as resting, the two modules
    would be describing different equations and every steady-state
    conclusion in the package would be built on the disagreement.
    """

    def test_the_residual_at_a_wrong_state_is_the_analytic_one(
        self, turnover
    ) -> None:
        # ks - kd*X at X = 5 is 1 - 0.5. Exactly, on this rate law, in
        # floating point -- there is nothing iterative in the evaluation.
        assert residual_at(turnover.network, {"x_X": 5.0}) == pytest.approx(0.5)

    def test_the_residual_at_the_true_state_is_zero(self, turnover) -> None:
        assert residual_at(
            turnover.network, {"x_X": TURNOVER_STEADY_STATE}
        ) == pytest.approx(0.0, abs=1e-15)

    def test_a_state_missing_a_species_is_refused_not_padded(
        self, turnover
    ) -> None:
        # Padding with zeros would evaluate the rate laws somewhere nobody
        # asked about and report the residual as though it were the
        # caller's.
        with pytest.raises(ValidationError, match="missing"):
            residual_at(turnover.network, {})

    @needs_engine
    def test_a_state_that_is_not_a_fixed_point_is_caught(
        self, turnover
    ) -> None:
        """The deliberate break, end to end through the integrator.

        x = 5 is half the steady state. The trajectory climbs to 10 and the
        check must say so rather than reporting a quiet agreement.
        """
        findings = fixed_point_findings(turnover, states=[{"x_X": 5.0}])
        assert len(findings) == 1
        finding = findings[0]
        assert finding.severity == CONTRADICTION, finding.describe()
        assert finding.measured["residual"] == pytest.approx(0.5)
        assert finding.measured["relative_drift"] > 0.1
        assert "whatever produced this state" in finding.doubt

    def test_the_residual_is_what_picks_the_suspect(self) -> None:
        """The attribution, driven directly.

        Two failures look identical from the drift alone and want opposite
        advice. A state that was never a root implicates whatever produced
        it, and the integrator is behaving correctly by leaving. A state
        that IS a root and drifts anyway implicates the path between the two
        modules -- and no model in the library can produce that case, which
        is exactly why it is driven here instead of hoped for.
        """
        stale_severity, stale_detail, stale_doubt = fixed_point_verdict(
            0.5, 5.0, 10.0
        )
        assert stale_severity == CONTRADICTION
        assert "whatever produced this state" in stale_doubt
        assert "integrator is behaving correctly" in stale_detail

        severity, _, disagreement = fixed_point_verdict(1e-15, 5.0, 10.0)
        assert severity == CONTRADICTION
        assert "the path through the integrator" in disagreement
        assert "compile_to_antimony" in disagreement
        assert "whatever produced this state" not in disagreement

    def test_a_state_that_stays_put_is_an_agreement(self) -> None:
        severity, detail, doubt = fixed_point_verdict(1e-15, 1e-9, 10.0)
        assert severity == AGREE
        assert doubt == ""
        assert "does not move" in detail

    def test_the_tolerance_bites_on_both_sides(self) -> None:
        from Terium.compose.validate import FIXED_POINT_DRIFT_TOLERANCE

        under = fixed_point_verdict(0.0, FIXED_POINT_DRIFT_TOLERANCE * 0.5, 1.0)
        over = fixed_point_verdict(0.0, FIXED_POINT_DRIFT_TOLERANCE * 2.0, 1.0)
        assert under[0] == AGREE
        assert over[0] == CONTRADICTION

    def test_the_state_is_measured_against_one_scale(self) -> None:
        # A cascade's enzymes sit at 1e-3 and its substrates at 1. Dividing
        # each species' drift by its own value would make a 1e-9 wobble on
        # an enzyme outrank a 1e-4 move of the substrate.
        assert state_scale({"enzyme": 1e-3, "substrate": 2.0}) == 2.0
        assert state_scale({"nothing": 0.0}) == pytest.approx(1e-12)

    @needs_engine
    def test_a_model_with_no_stable_state_is_unchecked_not_passed(self) -> None:
        """An open system that runs away has nothing to check.

        Reporting that as an agreement would let a model the check could not
        examine read as one it examined and approved.
        """
        from Terium.compose.library import CONSTANT_INFLOW

        composition = Composition("unbounded")
        composition.add(CONSTANT_INFLOW, "feed")
        findings = fixed_point_findings(_as_model(composition, "unbounded"))
        assert [f.severity for f in findings] == [UNCHECKED]
        assert "no stable steady state" in findings[0].detail


# ---------------------------------------------------------------------------
# The conservation check, broken on purpose
# ---------------------------------------------------------------------------


class TestTheConservationCheckCatchesADriftingTotal:
    """A fabricated trajectory, because a real drift needs a broken solver.

    The columns handed in here are what a too-loose integrator produces:
    `c_A + c_B` grows by five percent over the run while every individual
    curve looks entirely reasonable. That is the failure this check exists
    for, and the plot of it is indistinguishable from a correct one.
    """

    def _columns(self, drift: float):
        points = 21
        a = tuple(1.0 - i / (points - 1) for i in range(points))
        b = tuple(
            (i / (points - 1)) * (1.0 + drift * i / (points - 1))
            for i in range(points)
        )
        return {"c_A": a, "c_B": b}

    def test_a_conserved_total_is_reported_as_an_independent_check(
        self, conversion
    ) -> None:
        findings = conservation_findings(
            conversion.network, self._columns(0.0)
        )
        assert [f.severity for f in findings] == [AGREE]
        assert "left null space" in findings[0].detail

    def test_a_drifting_total_is_caught(self, conversion) -> None:
        findings = conservation_findings(
            conversion.network, self._columns(0.05)
        )
        assert [f.severity for f in findings] == [CONTRADICTION]
        assert findings[0].measured["relative"] == pytest.approx(0.05, rel=1e-9)

    def test_the_drift_is_blamed_on_the_integration_and_the_reason_is_given(
        self, conversion
    ) -> None:
        """Which of the two to doubt is not a toss-up here.

        The law is computed over `Fraction` from the stoichiometry, with no
        floating point in it anywhere; the trajectory is the approximation.
        A finding that said only "these disagree" would leave the reader to
        rediscover that.
        """
        finding = conservation_findings(
            conversion.network, self._columns(0.05)
        )[0]
        assert "the integration" in finding.doubt
        assert "Fraction" in finding.doubt
        assert "no tolerance" in finding.doubt

    def test_a_network_with_no_law_is_unchecked_rather_than_agreed(
        self, turnover
    ) -> None:
        """Turnover creates and destroys X, so nothing is conserved.

        "There was no law to check" and "the law held" are different
        sentences, and only one of them is evidence.
        """
        findings = conservation_findings(
            turnover.network, {"x_X": (0.0, 1.0, 2.0)}
        )
        assert [f.severity for f in findings] == [UNCHECKED]
        assert "open system" in findings[0].detail


# ---------------------------------------------------------------------------
# The settling-time check, broken on purpose
# ---------------------------------------------------------------------------


class TestTheSettlingCheckCatchesAPredictionTheCurveDoesNotMeet:
    """Measured against algebra, then broken.

    The trajectory used here is the closed-form solution of
    dX/dt = ks - kd*X, so the observed settling time has an exact answer --
    1/kd -- and the measurement is checked against that rather than against
    another numerical result.
    """

    def _trajectory(self, timescale: float = TURNOVER_TIMESCALE):
        return _exponential_approach(
            timescale, TURNOVER_STEADY_STATE, 0.0, 8.0 * timescale, 801
        )

    def test_the_measured_timescale_is_the_analytic_one(self) -> None:
        times, columns = self._trajectory()
        observed = observed_timescale(
            times, columns, {"x_X": TURNOVER_STEADY_STATE}
        )
        assert observed == pytest.approx(TURNOVER_TIMESCALE, rel=1e-6)

    def test_the_crossing_time_is_divided_by_the_log_and_not_reported_raw(
        self,
    ) -> None:
        """The obvious way to write this check wrong.

        A system with a settling time of 10 takes 10*ln(20) = 30 to fall to
        a twentieth of its initial deviation. Comparing that 30 against the
        eigenvalue's 10 would report every correct model in the library as
        three times slower than predicted, and the tolerance would then have
        been widened until the check meant nothing.
        """
        times, columns = self._trajectory()
        observed = observed_timescale(
            times, columns, {"x_X": TURNOVER_STEADY_STATE}
        )
        raw_crossing = TURNOVER_TIMESCALE * math.log(1.0 / SETTLING_FRACTION)
        assert raw_crossing == pytest.approx(29.957, rel=1e-3)
        assert observed == pytest.approx(TURNOVER_TIMESCALE, rel=1e-6)
        assert abs(observed - raw_crossing) > 10.0

    def test_a_matching_prediction_agrees(self) -> None:
        times, columns = self._trajectory()
        findings = settling_findings_from(
            times, columns, {"x_X": TURNOVER_STEADY_STATE}, TURNOVER_TIMESCALE,
        )
        assert [f.severity for f in findings] == [AGREE]

    def test_a_prediction_ten_times_too_slow_is_caught(self) -> None:
        # The trajectory settles in 10; the linearisation is told to claim
        # 100. Nothing about the curve changes -- only the claim about it.
        times, columns = self._trajectory()
        findings = settling_findings_from(
            times, columns, {"x_X": TURNOVER_STEADY_STATE},
            10.0 * TURNOVER_TIMESCALE,
        )
        assert [f.severity for f in findings] == [DIVERGENCE]
        assert findings[0].measured["observed"] == pytest.approx(
            TURNOVER_TIMESCALE, rel=1e-6
        )
        assert "arrives sooner" in findings[0].detail

    def test_a_prediction_ten_times_too_fast_is_caught(self) -> None:
        times, columns = self._trajectory()
        findings = settling_findings_from(
            times, columns, {"x_X": TURNOVER_STEADY_STATE},
            TURNOVER_TIMESCALE / 10.0,
        )
        assert [f.severity for f in findings] == [DIVERGENCE]
        assert "choose_window" in findings[0].doubt

    def test_the_two_directions_do_not_get_the_same_advice(self) -> None:
        """Slower than predicted and faster than predicted are not one bug.

        Slower means a plot window derived from the eigenvalue cuts the
        approach off, which a reader has to act on. Faster means the slow
        eigendirection carried little of the initial displacement, which
        makes the window generous -- the harmless direction.
        """
        slow = settling_verdict(
            30.0, 10.0, final_deviation=0.0, initial_deviation=1.0, window=80.0
        )
        fast = settling_verdict(
            3.0, 10.0, final_deviation=0.0, initial_deviation=1.0, window=80.0
        )
        assert slow[0] == fast[0] == DIVERGENCE
        assert slow[2] != fast[2]
        assert "too short" in slow[2]
        assert "generous" in fast[2]

    def test_the_tolerance_is_a_factor_and_bites_both_ways(self) -> None:
        inside = settling_verdict(
            10.0 * SETTLING_TOLERANCE_FACTOR * 0.9, 10.0,
            final_deviation=0.0, initial_deviation=1.0, window=80.0,
        )
        outside = settling_verdict(
            10.0 * SETTLING_TOLERANCE_FACTOR * 1.1, 10.0,
            final_deviation=0.0, initial_deviation=1.0, window=80.0,
        )
        assert inside[0] == AGREE
        assert outside[0] == DIVERGENCE

    def test_a_trajectory_that_leaves_the_state_is_a_contradiction(
        self,
    ) -> None:
        """A different finding, and a different suspect.

        "Slower than the linearisation says" and "not going there at all"
        both arrive as an unmeasurable settling time. The second means the
        eigenvalues called a point stable that the integrator runs away
        from, or that the search missed the attractor the trajectory is
        actually heading for -- and that is worth more than a timing
        mismatch.
        """
        times, columns = _exponential_approach(-20.0, 0.0, 1.0, 40.0, 201)
        findings = settling_findings_from(
            times, columns, {"x_X": 0.0}, 10.0, window=40.0,
        )
        assert [f.severity for f in findings] == [CONTRADICTION]
        assert "did not approach this state at all" in findings[0].detail
        assert "the classification" in findings[0].doubt

    def test_a_trajectory_that_starts_at_the_state_is_unchecked(self) -> None:
        # No approach, so no settling time -- which is not a failure of the
        # prediction, it is the wrong trajectory to have asked.
        findings = settling_findings_from(
            (0.0, 1.0), {"x_X": (10.0, 10.0)}, {"x_X": 10.0}, 10.0,
        )
        assert [f.severity for f in findings] == [UNCHECKED]

    def test_a_missing_column_is_refused_rather_than_measured_over_the_rest(
        self,
    ) -> None:
        """A distance over some of the coordinates is not a distance.

        Dropping a species with no column would make the trajectory look
        closer to the steady state than it is, and the settling time read
        off it shorter than it is -- wrong in the direction that makes the
        report look good, which is the direction worth refusing.
        """
        times, columns = self._trajectory()
        findings = settling_findings_from(
            times, columns,
            {"x_X": TURNOVER_STEADY_STATE, "x_enzyme": 1.0}, TURNOVER_TIMESCALE,
        )
        assert [f.severity for f in findings] == [UNCHECKED]
        assert "x_enzyme" in findings[0].detail

    def test_a_fraction_outside_zero_to_one_is_refused(self) -> None:
        times, columns = self._trajectory()
        with pytest.raises(ValidationError, match="between 0 and 1"):
            observed_timescale(
                times, columns, {"x_X": TURNOVER_STEADY_STATE}, fraction=1.5
            )


# ---------------------------------------------------------------------------
# The sensitivity cross-check, broken on purpose
# ---------------------------------------------------------------------------


class TestTheSensitivityCrossCheckCatchesTheBugsItIsFor:
    """Sign errors and gross scaling, which is what these bugs look like.

    The break is applied to the FINE report, which is the estimate the
    coarse one exists to police: it divides a difference of a few parts in a
    million by a step of the same size, so a quantity noisier than its
    declared precision returns something with an arbitrary sign. The coarse
    estimate re-solves ten percent away, where no rounding error is large
    enough to matter.
    """

    @pytest.fixture(scope="class")
    def fine(self, turnover):
        return sensitivity_analyse(turnover.network, steady_state_of("x_X"))

    def test_the_premise(self, fine) -> None:
        # If the fine report were not right, breaking it would prove
        # nothing.
        by_name = {s.parameter: s.relative for s in fine.sensitivities}
        assert by_name["x_ks"] == pytest.approx(1.0, rel=1e-4)
        assert by_name["x_kd"] == pytest.approx(-1.0, rel=1e-4)

    def test_a_flipped_sign_is_caught(self, turnover, fine) -> None:
        broken = replace(
            fine,
            sensitivities=tuple(
                replace(s, relative=-s.relative) for s in fine.sensitivities
            ),
        )
        findings = sensitivity_findings(
            turnover.network, steady_state_of("x_X"), fine=broken
        )
        assert {f.severity for f in findings} == {CONTRADICTION}, [
            f.describe() for f in findings
        ]
        assert all("OPPOSITE SIGNS" in f.detail for f in findings)
        assert all("the fine difference" in f.doubt for f in findings)

    def test_a_tenfold_scaling_error_is_caught(self, turnover, fine) -> None:
        broken = replace(
            fine,
            sensitivities=tuple(
                replace(s, relative=10.0 * s.relative)
                for s in fine.sensitivities
            ),
        )
        findings = sensitivity_findings(
            turnover.network, steady_state_of("x_X"), fine=broken
        )
        assert {f.severity for f in findings} == {CONTRADICTION}
        assert all("does not close the gap" in f.detail for f in findings)

    def test_curvature_is_reported_as_curvature_and_not_as_a_bug(self) -> None:
        """The discriminator, driven directly.

        A secant over a finite span is the derivative plus a curvature term
        that falls as the span squared. Narrowing the span by four should
        cut the gap sixteenfold if curvature is all there is. A check
        without this would call every nonlinear model broken.
        """
        severity, detail, doubt = sensitivity_verdict(
            fine=1.0, coarse=1.5, refined=1.05, floor=0.01, span=COARSE_SPAN,
        )
        assert severity == DIVERGENCE
        assert "curvature, not disagreement" in detail
        assert "neither number" in doubt

    def test_a_gap_that_survives_the_refinement_is_a_contradiction(
        self,
    ) -> None:
        # Same gap, and the refinement does not close it: the two are
        # disagreeing about the slope rather than about where it is taken.
        severity, _, doubt = sensitivity_verdict(
            fine=1.0, coarse=1.5, refined=1.5, floor=0.01, span=COARSE_SPAN,
        )
        assert severity == CONTRADICTION
        assert "the fine difference" in doubt

    def test_the_floor_is_the_ranking_s_own_act_on_threshold(self) -> None:
        """A deliberate blindness, stated rather than discovered.

        Below |S| = 0.01 `sensitivity.py` already declines to advise anyone
        to go and measure. Two estimates that disagree down there disagree
        about advice nobody was going to take, and a check that reported it
        would fire on every saturated model in the library until the report
        stopped being read.
        """
        quiet = sensitivity_verdict(
            fine=0.004, coarse=-0.004, refined=-0.004, floor=0.01,
            span=COARSE_SPAN,
        )
        loud = sensitivity_verdict(
            fine=0.4, coarse=-0.4, refined=-0.4, floor=0.01, span=COARSE_SPAN,
        )
        assert quiet[0] == AGREE
        assert loud[0] == CONTRADICTION

    def test_an_agreement_between_two_zeros_says_it_is_a_weak_one(self) -> None:
        """Two numbers below the floor agree for a reason worth stating.

        A closed system's steady state is fixed by its conservation law, so
        every rate constant has sensitivity exactly zero and both routes
        return it. That IS an agreement, and it is nothing like two
        independent estimates landing on 1.0 -- neither number is being
        told apart from zero. Saying so with the same sentence would credit
        the check with a confirmation it did not make.
        """
        _, weak, _ = sensitivity_verdict(
            fine=0.0, coarse=0.0, refined=0.0, floor=0.01, span=COARSE_SPAN,
        )
        _, strong, _ = sensitivity_verdict(
            fine=1.0, coarse=1.01, refined=1.0, floor=0.01, span=COARSE_SPAN,
        )
        assert "the agreement is weak" in weak
        assert "neither route found influence" in weak
        assert "the agreement is weak" not in strong

    def test_a_quantity_that_cannot_be_computed_is_unchecked(
        self, turnover
    ) -> None:
        # A species this model does not have. The check must say it could
        # not run, not return an empty agreement.
        findings = sensitivity_findings(
            turnover.network, steady_state_of("no_such_species")
        )
        assert [f.severity for f in findings] == [UNCHECKED]
        assert "could not be computed" in findings[0].detail


# ---------------------------------------------------------------------------
# The dimensional check, broken on purpose
# ---------------------------------------------------------------------------


#: A motif whose rate constant is declared in the wrong unit.
#:
#: `{k} * {A}` with k in mM/s evaluates to mM^2/s, and a reaction rate is
#: mM/s. The model still compiles, still integrates and still draws a smooth
#: curve; only the declaration says otherwise, which is the entire reason
#: the declaration exists.
WRONGLY_DECLARED = Motif(
    name="wrongly_declared",
    summary="A first-order conversion whose rate constant is mis-declared.",
    basis=(
        "Not a mechanism. Built for the dimensional check's own test: the "
        "rate law is the ordinary first-order one and only the declared "
        "unit of its constant is wrong."
    ),
    ports=(Port("A", ROLE_SUBSTRATE, 1.0), Port("B", ROLE_PRODUCT, 0.0)),
    parameters=(
        MotifParameter(
            "k", KIND_RATE_CONSTANT, 1.0, "mM/s",
            description="declared as a zero-order rate and used as a "
                        "first-order one, on purpose",
        ),
    ),
    reactions=(ReactionTemplate("conversion", {"A": 1}, {"B": 1}, "{k} * {A}"),),
)


class TestTheDimensionalCheckCatchesAMisDeclaredUnit:
    def test_a_wrong_unit_is_a_contradiction(self) -> None:
        composition = Composition("mis-declared")
        composition.add(WRONGLY_DECLARED, "w")
        findings = dimension_findings(composition)
        assert [f.severity for f in findings] == [CONTRADICTION], [
            f.describe() for f in findings
        ]
        assert findings[0].subject == "w_conversion"

    def test_the_finding_names_both_halves_of_the_motif(self) -> None:
        """The honest attribution here is that it cannot pick one.

        The `unit` string and the `rate_law` sit side by side in the same
        motif and either could be the mistake. A finding that guessed would
        send the reader to the wrong line half the time; one that names both
        and says why sends them to the right file every time.
        """
        composition = Composition("mis-declared")
        composition.add(WRONGLY_DECLARED, "w")
        doubt = dimension_findings(composition)[0].doubt
        assert "MotifParameter" in doubt
        assert "ReactionTemplate" in doubt
        assert "NOT in doubt is the numbers" in doubt

    def test_a_sound_composition_says_scale_was_checked_too(self) -> None:
        # mM and uM have identical dimensions and differ by a thousand. An
        # agreement that only covered dimensions would be worth much less
        # than it sounds.
        composition = Composition("sound")
        composition.add(MASS_ACTION_CONVERSION, "c")
        finding = dimension_findings(composition)[0]
        assert finding.severity == AGREE
        assert "SCALE" in finding.detail


# ---------------------------------------------------------------------------
# A finding has to name a suspect, and a report must not overclaim
# ---------------------------------------------------------------------------


class TestAFindingMustNameASuspect:
    """The invariant that makes this module worth more than a boolean.

    Enforced in the constructor rather than left to whoever adds the sixth
    check to remember. "These two disagree" hands the reader a bisection;
    "doubt this one, because its arithmetic is a single evaluation and the
    other one's is an adaptive solver" hands them a place to start.
    """

    def test_a_contradiction_without_a_doubt_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="which answer to doubt"):
            Finding(
                check=CHECK_FIXED_POINT,
                severity=CONTRADICTION,
                subject="x",
                detail="they disagree",
            )

    def test_a_divergence_without_a_doubt_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="which answer to doubt"):
            Finding(
                check=CHECK_SETTLING,
                severity=DIVERGENCE,
                subject="x",
                detail="they differ",
            )

    def test_an_agreement_needs_no_doubt(self) -> None:
        finding = Finding(
            check=CHECK_DIMENSIONS, severity=AGREE, subject="x",
            detail="both routes agree",
        )
        assert finding.agreed
        assert finding.doubt == ""

    def test_an_unchecked_finding_must_say_why(self) -> None:
        # An unexplained gap reads as a pass.
        with pytest.raises(ValidationError, match="unchecked without saying why"):
            Finding(
                check=CHECK_CONSERVATION, severity=UNCHECKED, subject="x",
                detail="",
            )

    def test_an_unknown_severity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not one of"):
            Finding(
                check=CHECK_FIXED_POINT, severity="probably fine", subject="x",
                detail="hmm",
            )


class TestTheReportDoesNotOverclaim:
    def _report(self) -> ValidationReport:
        return ValidationReport(
            model="example",
            findings=(
                Finding(CHECK_DIMENSIONS, AGREE, "law", "balances"),
                Finding(
                    CHECK_CONSERVATION, UNCHECKED, "net",
                    "the engine is not installed",
                ),
                Finding(
                    CHECK_SETTLING, DIVERGENCE, "state", "three times slower",
                    doubt="the linearisation",
                ),
            ),
        )

    def test_an_unchecked_check_is_not_counted_as_an_agreement(self) -> None:
        report = self._report()
        assert len(report.agreements) == 1
        assert len(report.unchecked) == 1
        assert report.checks_run() == (CHECK_DIMENSIONS, CHECK_SETTLING)

    def test_the_summary_says_what_did_not_run(self) -> None:
        summary = self._report().summary()
        assert "did not run, which is not the same as passing" in summary
        assert "the engine is not installed" in summary

    def test_the_summary_refuses_to_call_agreement_correctness(self) -> None:
        """Every check here compares Terrium against Terrium.

        Two routes that share the rate laws, the stoichiometry and the
        parameter values can be wrong together, and a reader who takes a
        clean report as validation of the biology has been misled by this
        module rather than helped by it.
        """
        summary = self._report().summary()
        assert "not that the model is right" in summary

    def test_there_is_no_boolean_that_could_be_read_as_valid(self) -> None:
        # A `report.valid` would be read as "the model is right" by every
        # caller in a hurry, and this module cannot support that claim. The
        # absence is a decision; this test is where it is recorded.
        for name in ("valid", "is_valid", "sound", "ok", "passed"):
            assert not hasattr(ValidationReport, name), name
        assert hasattr(ValidationReport, "contradictions")
