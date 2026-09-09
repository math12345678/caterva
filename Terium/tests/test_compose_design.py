"""Which measurement to make next.

The model these tests are built on is the one whose answer is known in
closed form. dX/dt = ks - kd*X settles at ks/kd and gets there with time
constant 1/kd, so the two sensitivity vectors are exactly (+1, -1) and
(0, -1), the angle between the second and the span of the first is exactly
45 degrees, and the combination the first cannot see is exactly "scale both
by the same factor". Every number in the class below is checkable by hand.

That matters more here than in most modules, because a design ranking is
easy to make plausible and hard to make right: any monotone function of
"how different is this from what I have" produces a ranking that looks
sensible. The turnover model is the case where sensible and correct can be
told apart.

The rest pin the two things a ranking like this gets wrong in the field --
claiming a repeat measurement helps, and quietly implying it knows what an
experiment costs.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from Terium.compose.builder import Composition, couple
from Terium.compose.library import (
    HILL_ACTIVATION, HILL_REPRESSION, SYNTHESIS_DEGRADATION,
)
from Terium.compose.design import (
    DIRECTION_FLOOR, DesignError, Direction, NoInformativeMeasurement,
    Observation, best_next_measurement, blind_directions,
    candidate_observations, measurement_floor, orthonormal_span,
    oscillation_period, period_of, rank_observations, residual_after,
    sensitivity_rows, unit_direction,
)
from Terium.compose.sensitivity import (
    SensitivityUnavailable, settling_time, steady_state_of,
)

STEADY_STATE = "steady_state:x_X"
SETTLING = "settling_time"


# -- shared, because every one of these re-solves a steady state -------------
#
# Each `rank_observations` call differentiates every candidate against every
# parameter, and each of those is a root solve. Module-scoped rather than
# session-scoped so a failure here cannot leak into another file's fixtures,
# and safe to share because the reports are frozen dataclasses no test
# mutates.


@pytest.fixture(scope="module")
def turnover():
    """dX/dt = ks - kd*X, with x_ks = 1.0 and x_kd = 0.1."""
    composition = Composition("turnover")
    composition.add(SYNTHESIS_DEGRADATION, "x")
    return composition.to_network()


@pytest.fixture(scope="module")
def spiral():
    """A two-gene negative feedback loop: A activates B, B represses A.

    At the library's default constants this is a stable spiral, so the
    approach to steady state rings -- which is the only way to reach the
    period observation, and the only way to reach the amplitude decline that
    applies to a ring-down rather than to a system with no oscillation at all.
    """
    composition = Composition("negative_feedback")
    repressed = composition.add(HILL_REPRESSION, "a")
    activated = composition.add(HILL_ACTIVATION, "b")
    couple(composition, repressed, "X", activated, "A")
    couple(composition, activated, "X", repressed, "R")
    return composition.to_network()


@pytest.fixture(scope="module")
def nothing_measured(turnover):
    return rank_observations(turnover, ["x_ks", "x_kd"])


@pytest.fixture(scope="module")
def after_steady_state(turnover):
    return rank_observations(
        turnover, ["x_ks", "x_kd"], already_measured=[STEADY_STATE]
    )


def _gain(report, key):
    return next(g for g in report.gains if g.observation.key == key)


def power_law(exponents):
    """A quantity whose log-sensitivities are exactly `exponents`.

    y = prod(p_j ** a_j) has d(log y)/d(log p_j) = a_j exactly, at every
    value of every parameter. That lets a test STATE the geometry it wants
    to check and then check it, instead of hunting for a real model that
    happens to produce the two vectors the claim is about. The claim being
    tested here -- that the ranking is by the length of the new component
    and not by the angle -- needs a long vector at a shallow angle and a
    short one at a right angle, and no motif in the library offers that
    pair.

    Verified against `sensitivity_rows` in the first test of the class, so
    the helper cannot quietly be wrong about its own exponents.
    """

    def quantity(network):
        value = 1.0
        for parameter in network.parameters:
            exponent = exponents.get(parameter.id, 0.0)
            if exponent:
                value *= float(parameter.value) ** exponent
        return value

    return quantity


class TestAgainstTheClosedFormAnswer:
    """The case where the right answer is known exactly.

    ks/kd and 1/kd. If the ranking cannot reproduce these, its ranking of
    anything harder is not worth reading.
    """

    def test_the_two_sensitivity_vectors_are_the_ones_in_the_textbook(
        self, turnover
    ) -> None:
        # The premise the whole module rests on. X* = ks/kd gives (+1, -1);
        # the settling time is 1/kd, which does not depend on ks at all.
        observations = [
            Observation(STEADY_STATE, "steady state", steady_state_of("x_X")),
            Observation(SETTLING, "settling time", settling_time()),
        ]
        rows, unavailable = sensitivity_rows(
            turnover, observations, ["x_ks", "x_kd"]
        )
        assert unavailable == {}
        assert rows[0].vector == pytest.approx((1.0, -1.0), rel=1e-4)
        assert rows[1].vector[1] == pytest.approx(-1.0, rel=1e-3)
        # Not asserted as exactly zero: the settling time is read off an
        # eigenvalue of a finite-difference Jacobian, so its floor is five
        # orders of magnitude coarser than the steady state's. Zero to
        # within ITS OWN floor is the honest claim.
        assert abs(rows[1].vector[0]) < rows[1].resolution

    def test_the_settling_time_sits_forty_five_degrees_off_the_steady_state(
        self, after_steady_state
    ) -> None:
        # (0, -1) against the span of (1, -1)/sqrt(2): the projection has
        # length 1/sqrt(2) and so does what is left, which is 45 degrees.
        gain = _gain(after_steady_state, SETTLING)
        assert gain.angle_degrees == pytest.approx(45.0, abs=1e-2)
        assert gain.novelty == pytest.approx(1.0 / math.sqrt(2.0), rel=1e-3)
        assert gain.independence == pytest.approx(1.0 / math.sqrt(2.0), rel=1e-3)

    def test_the_settling_time_is_the_best_next_measurement(
        self, turnover
    ) -> None:
        """THE KEY TEST.

        Having measured only the steady state, you know ks/kd and nothing
        else. The settling time is 1/kd, and it is the one observation on
        the menu that breaks that degeneracy. This is exact, and it is the
        claim the module exists to make.
        """
        best = best_next_measurement(turnover, [STEADY_STATE], ["x_ks", "x_kd"])
        assert best.observation.key == SETTLING
        assert best.rank_before == 1
        assert best.rank_after == 2
        assert best.informative

    def test_it_pins_exactly_the_combination_the_steady_state_cannot_see(
        self, after_steady_state
    ) -> None:
        """The geometric statement, checked as geometry rather than as prose.

        A steady state of ks/kd is blind to scaling both constants together.
        The direction the settling time adds must therefore BE that
        direction, not merely some new one.
        """
        assert after_steady_state.rank_before == 1
        assert len(after_steady_state.blind) == 1
        blind = after_steady_state.blind[0]
        # Equal weights: raise ks and kd by the same fraction and ks/kd does
        # not move.
        assert blind.weights["x_ks"] == pytest.approx(
            blind.weights["x_kd"], rel=1e-6
        )
        pinned = _gain(after_steady_state, SETTLING).pins
        assert pinned is not None
        assert pinned.weights["x_ks"] == pytest.approx(
            blind.weights["x_ks"], rel=1e-3
        )
        assert pinned.weights["x_kd"] == pytest.approx(
            blind.weights["x_kd"], rel=1e-3
        )

    def test_with_nothing_measured_the_steady_state_leads(
        self, nothing_measured
    ) -> None:
        # |(1, -1)| = sqrt(2) against |(0, -1)| = 1. With no span to be
        # orthogonal to, the whole vector is new, so the ranking is by
        # length -- and the steady state moves with both constants where the
        # settling time moves with one.
        assert nothing_measured.rank_before == 0
        assert nothing_measured.best is not None
        assert nothing_measured.best.observation.key == STEADY_STATE
        assert nothing_measured.best.novelty == pytest.approx(
            math.sqrt(2.0), rel=1e-4
        )

    def test_nothing_is_pinned_before_anything_is_measured(
        self, nothing_measured
    ) -> None:
        assert len(nothing_measured.blind) == 2
        assert not nothing_measured.identified


class TestLengthAndNotOnlyAngle:
    """The choice the module docstring argues for, pinned.

    An observation exactly orthogonal to everything measured raises the rank
    on paper however small it is. Ranking on the angle alone would therefore
    put a sensitivity of 1e-3 above one of 1.0 that happens to sit at 45
    degrees -- and send a researcher after three digits nobody's assay will
    see. The two rules disagree on exactly this pair, and nothing in the
    library produces it, so the vectors are constructed.
    """

    def _menu(self):
        return [
            Observation("along_ks", "moves with ks alone",
                        power_law({"x_ks": 1.0})),
            Observation("long_and_oblique", "moves with both",
                        power_law({"x_ks": 1.0, "x_kd": 1.0})),
            Observation("short_and_orthogonal", "moves faintly with kd",
                        power_law({"x_kd": 1e-3})),
        ]

    def test_the_constructed_vectors_are_the_ones_intended(
        self, turnover
    ) -> None:
        # The helper checked against the machinery, before anything is
        # concluded from it.
        rows, unavailable = sensitivity_rows(
            turnover,
            [Observation("probe", "a probe", power_law({"x_ks": 2.0, "x_kd": -3.0}))],
            ["x_ks", "x_kd"],
        )
        assert unavailable == {}
        assert rows[0].vector == pytest.approx((2.0, -3.0), rel=1e-6)

    def test_the_long_oblique_observation_outranks_the_short_orthogonal_one(
        self, turnover
    ) -> None:
        report = rank_observations(
            turnover, ["x_ks", "x_kd"],
            already_measured=["along_ks"], candidates=self._menu(),
        )
        assert [g.observation.key for g in report.informative] == [
            "long_and_oblique", "short_and_orthogonal",
        ]

    def test_and_the_angles_are_the_other_way_round(self, turnover) -> None:
        # The premise: on the angle alone, the loser would win.
        report = rank_observations(
            turnover, ["x_ks", "x_kd"],
            already_measured=["along_ks"], candidates=self._menu(),
        )
        assert _gain(report, "short_and_orthogonal").angle_degrees == pytest.approx(
            90.0, abs=1e-3
        )
        assert _gain(report, "long_and_oblique").angle_degrees == pytest.approx(
            45.0, abs=1e-3
        )

    def test_both_still_count_as_informative(self, turnover) -> None:
        # The point is the ORDER, not that the small one is dismissed: 1e-3
        # is six orders above the floor and does raise the rank.
        report = rank_observations(
            turnover, ["x_ks", "x_kd"],
            already_measured=["along_ks"], candidates=self._menu(),
        )
        assert _gain(report, "short_and_orthogonal").informative
        assert _gain(report, "short_and_orthogonal").rank_after == 2


class TestMeasuringTheSameThingTwice:
    """The failure mode a plausible-looking design tool has.

    A ranking built on "how big is this sensitivity" recommends the steady
    state again, forever. The residual against what is already measured is
    what stops it, and it has to stop it to within a floor rather than
    exactly, because the two evaluations are not bit-identical.
    """

    def test_it_adds_nothing(self, after_steady_state) -> None:
        gain = _gain(after_steady_state, STEADY_STATE)
        assert not gain.informative
        assert gain.novelty < gain.floor
        assert gain.rank_after == gain.rank_before

    def test_the_module_says_so_rather_than_ranking_it_last(
        self, after_steady_state
    ) -> None:
        # A silent zero at the bottom of a list reads as "least useful".
        # "Adds nothing" is a different claim and is the true one.
        gain = _gain(after_steady_state, STEADY_STATE)
        assert "adds nothing" in gain.describe()
        assert "add nothing" in after_steady_state.summary()

    def test_a_fully_measured_model_refuses_instead_of_naming_a_winner(
        self, turnover
    ) -> None:
        with pytest.raises(NoInformativeMeasurement, match="already pinned"):
            best_next_measurement(
                turnover, [STEADY_STATE, SETTLING], ["x_ks", "x_kd"]
            )

    def test_and_reports_no_blind_directions_left(self, turnover) -> None:
        report = rank_observations(
            turnover,
            ["x_ks", "x_kd"],
            already_measured=[STEADY_STATE, SETTLING],
        )
        assert report.rank_before == 2
        assert report.identified
        assert report.blind == ()


class TestWhenNothingHelps:
    """The refusal that is the actual product.

    A design tool that always names a winner cannot say the one thing worth
    saying: that the remaining unknown is not reachable by measuring this
    system again, and the EXPERIMENT has to change. Each of the three ways
    that happens gets its own sentence, because the reader's next move
    differs.
    """

    def test_a_degeneracy_no_candidate_can_break_is_refused(
        self, turnover
    ) -> None:
        # Every observation on this menu moves with ks alone, so kd is
        # unreachable however many of them are measured.
        menu = [
            Observation("along_ks", "moves with ks", power_law({"x_ks": 1.0})),
            Observation("along_ks_again", "moves with ks, harder",
                        power_law({"x_ks": 2.0})),
        ]
        with pytest.raises(NoInformativeMeasurement, match="change the EXPERIMENT"):
            best_next_measurement(
                turnover, ["along_ks"], ["x_ks", "x_kd"], candidates=menu,
            )

    def test_the_refusal_names_the_combination_that_stays_invisible(
        self, turnover
    ) -> None:
        # "No measurement helps" is not actionable on its own; "kd is what
        # you cannot see" is.
        menu = [
            Observation("along_ks", "moves with ks", power_law({"x_ks": 1.0})),
        ]
        with pytest.raises(NoInformativeMeasurement, match="x_kd"):
            best_next_measurement(
                turnover, ["along_ks"], ["x_ks", "x_kd"], candidates=menu,
            )

    def test_nothing_computable_is_a_different_refusal_from_nothing_useful(
        self, turnover
    ) -> None:
        """Not the same finding, and not the same sentence.

        "Every observation repeats what you have" is a result. "No
        observation could be evaluated" is the absence of a result, and
        saying the first when the second happened would report a measurement
        nobody took.
        """
        menu = [
            Observation("steady_state:ghost", "a species that is not here",
                        steady_state_of("ghost")),
        ]
        with pytest.raises(NoInformativeMeasurement, match="nothing can be ranked"):
            best_next_measurement(
                turnover, [], ["x_ks", "x_kd"], candidates=menu,
            )


class TestItSaysWhatItDoesNotKnow:
    """The honesty requirement, asserted rather than trusted to the prose.

    This ranking is about information and nothing else. A reader who takes
    the top entry as "do this next" without knowing that has been misled by
    the tool, so the disclaimer is part of the output and is tested like any
    other output.
    """

    def test_the_summary_says_cost_and_feasibility_are_not_modelled(
        self, after_steady_state
    ) -> None:
        summary = after_steady_state.summary()
        assert "RANKED BY INFORMATION ONLY" in summary
        assert "Cost, feasibility" in summary
        assert "not modelled" in summary

    def test_the_summary_says_it_even_when_it_has_a_clear_winner(
        self, nothing_measured
    ) -> None:
        # The case where the tool is most likely to be believed.
        assert nothing_measured.best is not None
        assert "not modelled" in nothing_measured.summary()

    def test_the_module_docstring_carries_the_same_warning(self) -> None:
        from Terium.compose import design

        assert "RANKED BY INFORMATION ONLY" in (design.__doc__ or "")

    def test_the_summary_names_the_degeneracy_rather_than_counting_it(
        self, after_steady_state
    ) -> None:
        # "rank deficiency 1" is not something a reader can act on;
        # "x_ks and x_kd move together" is.
        summary = after_steady_state.summary()
        assert "x_ks" in summary
        assert "x_kd" in summary


class TestTheMenu:
    def test_it_offers_the_steady_state_and_the_settling_time(
        self, turnover
    ) -> None:
        menu = candidate_observations(turnover)
        assert sorted(o.key for o in menu) == [SETTLING, STEADY_STATE]

    def test_no_period_is_offered_for_a_system_that_does_not_ring(
        self, turnover
    ) -> None:
        # dX/dt = ks - kd*X has one real eigenvalue. Offering a period would
        # send somebody to look for a frequency that is not there.
        menu = candidate_observations(turnover)
        reasons = {d.key: d.reason for d in menu.declined}
        assert "oscillation_period" in reasons
        assert "imaginary part" in reasons["oscillation_period"]

    def test_the_amplitude_is_declined_with_a_reason_rather_than_omitted(
        self, turnover
    ) -> None:
        menu = candidate_observations(turnover)
        reasons = {d.key: d.reason for d in menu.declined}
        assert "oscillation_amplitude" in reasons
        assert "no oscillation" in reasons["oscillation_amplitude"]

    def test_an_unknown_key_is_refused_with_the_list_of_known_ones(
        self, turnover
    ) -> None:
        menu = candidate_observations(turnover)
        with pytest.raises(DesignError, match="Available"):
            menu.by_key("steady_state:not_a_species")


class TestRefusals:
    def test_no_target_parameters_is_refused(self, turnover) -> None:
        with pytest.raises(DesignError, match="nothing for a measurement"):
            rank_observations(turnover, [])

    def test_a_parameter_that_is_not_in_the_network_is_refused(
        self, turnover
    ) -> None:
        with pytest.raises(DesignError, match="not parameters of this network"):
            rank_observations(turnover, ["x_ks", "not_a_parameter"])

    def test_an_unknown_already_measured_observation_is_refused(
        self, turnover
    ) -> None:
        # Passing `candidates` keeps this from re-running the steady-state
        # search; the refusal being tested is about the key, not the menu.
        menu = [Observation(STEADY_STATE, "steady state", steady_state_of("x_X"))]
        with pytest.raises(DesignError, match="not an observation of this model"):
            rank_observations(
                turnover,
                ["x_ks", "x_kd"],
                already_measured=["measured_it_in_1998"],
                candidates=menu,
            )

    def test_one_uncomputable_candidate_does_not_take_the_report_with_it(
        self, turnover
    ) -> None:
        """A fact about one candidate is not a fact about the ranking.

        Aborting here would lose the observations that DO work, which is the
        opposite of useful: the reader wants to know what they can measure,
        and being told only that one thing failed is not that.
        """
        menu = [
            Observation(STEADY_STATE, "steady state", steady_state_of("x_X")),
            Observation(
                "steady_state:ghost", "a species that is not here",
                steady_state_of("ghost"),
            ),
        ]
        report = rank_observations(turnover, ["x_ks", "x_kd"], candidates=menu)
        assert [g.observation.key for g in report.gains] == [STEADY_STATE]
        assert "steady_state:ghost" in report.unavailable
        assert "no species" in report.unavailable["steady_state:ghost"]

    def test_a_measurement_this_module_cannot_reproduce_is_not_counted_silently(
        self, turnover
    ) -> None:
        """Two numbers that would otherwise contradict each other.

        The header says how many observations the caller has measured; the
        rank says how many of them landed in the span. When a measured
        observation cannot be evaluated here those two differ, and the
        reader would believe the larger one.
        """
        menu = [
            Observation("along_ks", "moves with ks", power_law({"x_ks": 1.0})),
            Observation("steady_state:ghost", "a species that is not here",
                        steady_state_of("ghost")),
        ]
        report = rank_observations(
            turnover, ["x_ks", "x_kd"],
            already_measured=["along_ks", "steady_state:ghost"],
            candidates=menu,
        )
        assert report.rank_before == 1
        assert len(report.already_measured) == 2
        assert "LOWER bound on what you know" in report.summary()

    def test_the_identifiability_cross_check_reports_its_own_status(
        self, nothing_measured
    ) -> None:
        """Whether or not that module exists yet, the report says which.

        `identifiability.py` is being written alongside this one. The import
        is lazy and guarded, so the ranking works either way -- but "the
        cross-check did not run" and "the cross-check agreed" are different
        facts and the report must not be silent about which one happened.
        """
        assert any("identifiability" in note for note in nothing_measured.notes)


class TestTheOscillation:
    """The third observation, and the one that is easiest to get wrong.

    A negative feedback loop -- A activates B, B represses A -- is a stable
    spiral at these values, so the approach to steady state rings. The period
    of that ringing IS a function of the rate constants and is offered; the
    amplitude is not, and is declined with the reason rather than omitted.
    """

    def test_a_downstream_species_adds_nothing_about_upstream_constants(
        self, spiral
    ) -> None:
        """A structural degeneracy, and one a bigger menu makes worse.

        b_X is a fixed function of a_X at steady state, so moving one of a's
        constants moves b_X only through a_X: the two rows are scalar
        multiples and the second carries no direction the first does not.
        Assaying the second protein is a real experiment that would return a
        real number and tell the reader nothing new about these three
        constants. A tool that ranked by "how strongly does this respond"
        would have recommended it.
        """
        report = rank_observations(
            spiral, ["a_ks", "a_kd", "a_K"],
            already_measured=["steady_state:a_X"],
        )
        assert not _gain(report, "steady_state:b_X").informative
        assert report.rank_before == 1

    def test_a_ringing_system_is_offered_a_period(self, spiral) -> None:
        menu = candidate_observations(spiral)
        assert "oscillation_period" in {o.key for o in menu}

    def test_the_period_is_the_one_the_eigenvalue_gives(self, spiral) -> None:
        # Checked against the linearisation directly rather than against a
        # remembered number, so it stays true if the fixture's defaults move.
        from Terium.compose.analysis import analyse as analyse_stability

        point = analyse_stability(spiral, starts_per_species=16).stable_points[0]
        expected = 2.0 * math.pi / max(abs(v.imag) for v in point.eigenvalues)
        assert oscillation_period()(spiral) == pytest.approx(expected, rel=1e-9)

    def test_the_amplitude_is_declined_as_a_property_of_the_disturbance(
        self, spiral
    ) -> None:
        """The honest refusal, and the one a plausible tool would skip.

        A ring-down's amplitude is set by how far the system was displaced.
        Ranking a sensitivity of it would rank a sensitivity of the
        experimenter's own pipetting.
        """
        menu = candidate_observations(spiral)
        reasons = {d.key: d.reason for d in menu.declined}
        assert "oscillation_amplitude" in reasons
        assert "how far you displaced" in reasons["oscillation_amplitude"]

    def test_the_surviving_mode_sets_the_period_not_the_fastest_one(
        self,
    ) -> None:
        """Which of several oscillatory modes the number comes from.

        Driven on a synthetic spectrum, because a two-species model has one
        conjugate pair and cannot tell the two rules apart. An experiment
        timing peak to peak sees the mode that outlives the others, so the
        period is 2*pi/2 = pi and not 2*pi/10.
        """
        point = SimpleNamespace(
            eigenvalues=(
                -0.1 + 2.0j, -0.1 - 2.0j, -5.0 + 10.0j, -5.0 - 10.0j,
            )
        )
        assert period_of(point) == pytest.approx(math.pi)

    def test_a_state_with_no_imaginary_part_has_no_period(self) -> None:
        point = SimpleNamespace(eigenvalues=(-1.0 + 0j, -3.0 + 0j))
        with pytest.raises(SensitivityUnavailable, match="no oscillation"):
            period_of(point)

    def test_an_imaginary_part_under_the_marginal_cutoff_is_not_an_oscillation(
        self,
    ) -> None:
        # Rounding in the finite-difference Jacobian puts a tiny imaginary
        # part on real eigenvalues. Reading one as a frequency would report a
        # period of 6e9 time units and send somebody to watch for it.
        point = SimpleNamespace(eigenvalues=(-1.0 + 1e-12j, -1.0 - 1e-12j))
        with pytest.raises(SensitivityUnavailable, match="no oscillation"):
            period_of(point)


class TestTheFloor:
    """The number that decides "new direction" from "rounding".

    Derived, not picked: sqrt(k * sum eps_i^2) over the k parameters and the
    rows involved. `identifiability.py` derives the same bound for its
    singular-value threshold, and the two are written out separately so that
    neither borrows the other at run time -- a floor that changed with the
    import graph would give the same question two answers.
    """

    def test_it_is_the_frobenius_bound_and_nothing_else(self) -> None:
        # sqrt(2 * (3^2 + 4^2)) = sqrt(50). Checkable by hand, which is the
        # only reason to test a three-line function.
        assert measurement_floor([3.0, 4.0], 2) == pytest.approx(math.sqrt(50.0))

    def test_a_coarser_row_raises_it(self, after_steady_state) -> None:
        # The settling time is read off a finite-difference Jacobian and is
        # five orders coarser than a steady state, so the pair's floor is set
        # by it. A single floor for both would have to be wrong for one.
        settling = _gain(after_steady_state, SETTLING)
        steady = _gain(after_steady_state, STEADY_STATE)
        assert settling.floor > 1e4 * steady.floor

    def test_no_parameters_is_refused_rather_than_returning_zero(self) -> None:
        with pytest.raises(DesignError, match="floor on nothing"):
            measurement_floor([1e-9], 0)

    def test_a_zero_resolution_is_refused(self) -> None:
        # It would claim the arithmetic is exact, and then every residual --
        # including a projection's own rounding -- counts as a new direction.
        with pytest.raises(DesignError, match="claim the arithmetic is exact"):
            measurement_floor([0.0, 0.0], 2)


class TestTheGeometry:
    """The primitives, driven directly.

    Split out so they can fail. Through `rank_observations` these are only
    ever fed sensitivity vectors from real models, and the cases that tell a
    correct projection from a sloppy one -- exactly parallel, exactly
    orthogonal, a direction and its negative -- are not among them.
    """

    def test_an_orthogonal_vector_survives_the_projection_whole(self) -> None:
        residual = residual_after([0.0, 3.0], [[1.0, 0.0]])
        assert residual == pytest.approx([0.0, 3.0])

    def test_a_parallel_vector_leaves_nothing(self) -> None:
        residual = residual_after([2.0, 0.0], [[1.0, 0.0]])
        assert residual == pytest.approx([0.0, 0.0], abs=1e-15)

    def test_the_span_of_two_parallel_rows_is_one_dimensional(self) -> None:
        basis = orthonormal_span([[1.0, -1.0], [2.0, -2.0]], 1e-9)
        assert len(basis) == 1

    def test_a_row_under_the_floor_is_not_admitted_to_the_span(self) -> None:
        # A second row that differs only by 1e-12 is rounding, not a
        # measurement, and admitting it would report a rank of two.
        basis = orthonormal_span([[1.0, 0.0], [1.0, 1e-12]], 1e-9)
        assert len(basis) == 1

    def test_the_complement_of_a_single_row_names_the_blind_combination(
        self,
    ) -> None:
        # The analytic case, done in pure arithmetic: a measurement that
        # moves as (+1, -1) is blind to (+1, +1).
        basis = orthonormal_span([[1.0, -1.0]], 1e-9)
        directions = blind_directions(basis, ["ks", "kd"], 1e-9)
        assert len(directions) == 1
        assert directions[0].weights["ks"] == pytest.approx(
            directions[0].weights["kd"]
        )

    def test_a_full_rank_span_leaves_no_blind_direction(self) -> None:
        basis = orthonormal_span([[1.0, -1.0], [0.0, -1.0]], 1e-9)
        assert blind_directions(basis, ["ks", "kd"], 1e-9) == ()

    def test_a_direction_and_its_negative_are_the_same_direction(self) -> None:
        # Otherwise the combination an observation pins and the combination
        # that was blind print with opposite signs and read as different
        # findings.
        assert unit_direction([1.0, 1.0]) == pytest.approx(
            unit_direction([-1.0, -1.0])
        )

    def test_a_zero_vector_has_no_direction_rather_than_a_division(
        self,
    ) -> None:
        assert unit_direction([0.0, 0.0]) == (0.0, 0.0)

    def test_a_described_direction_names_both_parameters_and_their_signs(
        self,
    ) -> None:
        text = Direction({"ks": 0.7071, "kd": 0.7071}).describe()
        assert "ks +1%" in text
        assert "kd +1%" in text

    def test_a_component_under_the_readability_floor_is_counted_not_dropped(
        self,
    ) -> None:
        # Silently omitting it would make a twelve-parameter direction look
        # like a two-parameter one.
        text = Direction(
            {"ks": 1.0, "kd": 1.0, "kx": DIRECTION_FLOOR / 100}
        ).describe()
        assert "kx" not in text
        assert "1 further parameter(s)" in text
