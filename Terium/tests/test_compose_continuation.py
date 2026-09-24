"""Following a branch around a fold, which a parameter sweep cannot do.

These tests are built on the saddle-node normal form, dx/dt = mu - x^2,
because every answer about it is known in closed form: the steady states are
x = +/- sqrt(mu), the eigenvalue is exactly -2x, the fold is exactly at
mu = 0, and below mu = 0 there is no real steady state at all. A test whose
right answer is known exactly is worth more than a test on a realistic model
whose right answer is whatever the code produced last week.

The central test is `TestItGoesRoundTheFold`. A sweep in mu marches mu down,
finds a state until mu = 0 and then finds nothing -- and the arm at x < 0 is
unreachable to it at every value, because two states share every mu above the
fold and none exists below it. Continuation follows the branch through the
turn and onto that arm, and `test_a_sweep_cannot_reach_the_other_arm` runs
both on the same model so the difference is a fact in the suite rather than
a claim in a docstring.
"""

from __future__ import annotations

import math

import pytest

from Terium.compose.analysis import STABLE, UNSTABLE
from Terium.compose.bifurcation import sweep
from Terium.compose.continuation import (
    FOLD_TANGENT_TOLERANCE, MAX_TURN_COSINE, STOPPED_MAX_POINTS,
    STOPPED_OUT_OF_RANGE, Branch, ContinuationError, continue_branch,
)
from Terium.core.network import (
    Parameter, RateRule, Reaction, ReactionNetwork, Species,
)


def saddle_node(mu: float = 1.0, x: float = 1.0) -> ReactionNetwork:
    """dx/dt = mu - x^2, as two reactions.

    Written as a network directly rather than composed from motifs: no motif
    in the library IS the normal form, and inventing one to reach it would
    put a modelling choice between the test and the closed-form answer it
    checks.
    """
    return ReactionNetwork(
        name="saddle_node_normal_form",
        species=(Species(id="x", initial=x),),
        parameters=(Parameter(id="mu", value=mu),),
        reactions=(
            Reaction(id="birth", reactants={}, products={"x": 1}, rate_law="mu"),
            Reaction(id="death", reactants={"x": 1}, products={}, rate_law="x * x"),
        ),
    )


def linear_branch(mu: float = 1.0) -> ReactionNetwork:
    """dx/dt = mu - x, whose branch is exactly the straight line x = mu.

    The control case. It has a steady state at every mu, no turning point,
    and a tangent that never changes -- so anything this reports as a fold
    is a false positive, and a sweep would do just as well on it.
    """
    return ReactionNetwork(
        name="linear_branch",
        species=(Species(id="x", initial=1.0),),
        parameters=(Parameter(id="mu", value=mu),),
        reactions=(
            Reaction(id="birth", reactants={}, products={"x": 1}, rate_law="mu"),
            Reaction(id="death", reactants={"x": 1}, products={}, rate_law="x"),
        ),
    )


@pytest.fixture(scope="module")
def round_the_fold() -> Branch:
    """One run of the normal form, from the stable arm, down through mu = 0.

    Module-scoped because eight tests ask questions of the same branch and
    the run is the expensive part. Safe to share: `Branch` and everything on
    it are frozen dataclasses and no test mutates one.
    """
    return continue_branch(
        saddle_node(mu=1.0),
        "mu",
        initial_state={"x": 1.0},
        direction=-1.0,
        max_points=120,
        parameter_range=(-0.5, 2.0),
    )


class TestTheBranchIsTheAnalyticOne:
    """Every point, checked against x^2 = mu rather than against a fixture."""

    def test_every_point_lies_on_the_analytic_branch(self, round_the_fold) -> None:
        # The steady states of dx/dt = mu - x^2 are exactly the parabola
        # mu = x^2. Nothing here is a tolerance on a remembered number: the
        # curve is known and every point is measured against it.
        worst = max(
            abs(point.state["x"] ** 2 - point.parameter)
            for point in round_the_fold.points
        )
        assert worst < 1e-8, worst

    def test_the_eigenvalue_at_every_point_is_minus_two_x(self, round_the_fold) -> None:
        # d/dx (mu - x^2) = -2x, exactly, everywhere on the branch. The
        # tolerance is the finite-difference Jacobian's, not the branch's.
        worst = 0.0
        for point in round_the_fold.points:
            expected = -2.0 * point.state["x"]
            assert len(point.eigenvalues) == 1
            worst = max(worst, abs(point.eigenvalues[0].real - expected))
        assert worst < 1e-6, worst

    def test_the_residual_at_every_point_is_below_the_tolerance(
        self, round_the_fold
    ) -> None:
        assert max(point.residual for point in round_the_fold.points) <= 1e-9

    def test_the_tangent_is_a_unit_vector_at_every_point(self, round_the_fold) -> None:
        worst = 0.0
        for point in round_the_fold.points:
            length = math.hypot(point.tangent_state["x"], point.tangent_parameter)
            worst = max(worst, abs(length - 1.0))
        assert worst < 1e-12, worst


class TestItGoesRoundTheFold:
    """The reason this module exists, and the thing a sweep cannot do."""

    def test_the_parameter_turns_around(self, round_the_fold) -> None:
        # Set off with mu DECREASING. If the run only ever decreased mu it
        # would have stopped at the fold like a sweep does; the branch
        # coming back up is the turn.
        values = round_the_fold.parameter_values
        assert values[1] < values[0]
        assert max(values[2:]) > values[0]

    def test_it_reaches_the_arm_a_sweep_cannot_see(self, round_the_fold) -> None:
        # x = -sqrt(mu) exists at every mu above the fold and no sweep in mu
        # reaches it, because the solver called at that mu finds the other
        # root. Continuation gets there by going round.
        negative = [p for p in round_the_fold.points if p.state["x"] < -0.1]
        assert negative, round_the_fold.summary()

    def test_the_fold_is_found_and_sits_at_mu_zero(self, round_the_fold) -> None:
        """The fold of dx/dt = mu - x^2 is at mu = 0 exactly.

        The tolerance quoted is not a guess. Bisection drives |dp/ds| below
        FOLD_TANGENT_TOLERANCE = 1e-9, and the corrector holds the rate
        equation to 1e-9, so mu at the located point is |x|^2 +/- 1e-9 with
        |x| of order 1e-9 -- about 1e-9 in total. 1e-6 leaves three orders
        of headroom and would still fail loudly if the refinement stopped
        working.
        """
        assert len(round_the_fold.folds) == 1, round_the_fold.summary()
        fold = round_the_fold.folds[0]
        assert fold.value == pytest.approx(0.0, abs=1e-6)
        assert fold.parameter == "mu"
        assert fold.state["x"] == pytest.approx(0.0, abs=1e-3)

    def test_the_fold_is_refined_past_its_own_bracket(self, round_the_fold) -> None:
        """The bracket does not contain the answer, and the report says so.

        Both bracketing points sit ABOVE the fold in mu -- that is what a
        turning point means -- so quoting the bracket's width as the
        accuracy would be wrong in the flattering direction. This pins the
        refinement actually happening: the located value is below both ends
        of the bracket it came from.
        """
        fold = round_the_fold.folds[0]
        assert fold.refined
        assert abs(fold.tangent_parameter) <= FOLD_TANGENT_TOLERANCE
        assert fold.value < min(fold.bracket)
        assert "SECOND order" in fold.describe()

    def test_one_branch_carries_a_stable_arm_and_an_unstable_one(
        self, round_the_fold
    ) -> None:
        # x = +sqrt(mu) has eigenvalue -2sqrt(mu) and x = -sqrt(mu) has
        # +2sqrt(mu). Both arms are on ONE branch, which is the fact a
        # re-solve at each parameter value cannot show.
        classifications = {point.classification for point in round_the_fold.points}
        assert STABLE in classifications
        assert UNSTABLE in classifications

    def test_the_unstable_arm_is_at_negative_concentrations_and_is_kept(
        self, round_the_fold
    ) -> None:
        # The equations have those points and the system cannot reach them.
        # They are flagged, not filtered -- dropping them would delete the
        # turn that was the reason for continuing.
        unphysical = [p for p in round_the_fold.points if not p.physical]
        assert unphysical
        assert all(p.state["x"] < 0 for p in unphysical)
        # Said on both surfaces a reader meets: the branch-level report and
        # the point itself.
        assert "at negative concentrations" in round_the_fold.summary()
        assert "NEGATIVE concentrations" in unphysical[0].describe()

    def test_a_sweep_cannot_reach_the_other_arm(self, round_the_fold) -> None:
        """The comparison, run rather than asserted in prose.

        `bifurcation.sweep` re-solves at each value of mu. On this model it
        finds one state above the fold and none below, and never reaches
        x < 0 at any value -- which is the limitation continuation removes.
        """
        report = sweep(saddle_node(), "mu", [1.0, 0.5, 0.25, 0.0, -0.25, -0.5])
        found = [
            point.state["x"]
            for sample in report.points
            for point in sample.report.physical_points
        ]
        assert found, report.summary()
        assert min(found) >= 0.0
        assert min(p.state["x"] for p in round_the_fold.points) < 0.0
        assert report.barren, report.summary()


class TestTheStepSizeAdapts:
    def test_no_accepted_step_exceeds_the_stated_maximum(self, round_the_fold) -> None:
        steps = _steps(round_the_fold)
        assert steps
        assert max(steps) <= round_the_fold.step_bounds[1] + 1e-12

    def test_no_accepted_step_falls_below_the_stated_minimum(
        self, round_the_fold
    ) -> None:
        steps = _steps(round_the_fold)
        assert steps
        assert min(steps) >= round_the_fold.step_bounds[0] - 1e-15

    def test_the_step_actually_varies(self, round_the_fold) -> None:
        # A "adaptive" step that never moved would pass both bounds tests
        # above and adapt nothing. The turn forces it down and the flat arms
        # let it grow, so a run round a fold must show both.
        steps = _steps(round_the_fold)
        assert max(steps) > min(steps) * 1.5, steps

    def test_the_tangent_never_turns_more_than_the_stated_cosine(
        self, round_the_fold
    ) -> None:
        # The guard that stops a long step cutting the corner at the fold
        # and skipping the turn entirely.
        worst = 1.0
        for before, after in zip(round_the_fold.points, round_the_fold.points[1:]):
            worst = min(
                worst,
                before.tangent_state["x"] * after.tangent_state["x"]
                + before.tangent_parameter * after.tangent_parameter,
            )
        assert worst >= MAX_TURN_COSINE - 1e-12, worst


class TestABranchWithNoTurn:
    """dx/dt = mu - x, whose branch is the line x = mu."""

    def test_the_branch_is_exactly_the_line(self) -> None:
        branch = continue_branch(
            linear_branch(), "mu", initial_state={"x": 1.0},
            max_points=20, parameter_range=(0.0, 5.0),
        )
        worst = max(
            abs(point.state["x"] - point.parameter) for point in branch.points
        )
        assert worst < 1e-9, worst

    def test_the_tangent_is_the_same_everywhere(self) -> None:
        # The line x = mu has unit tangent (1, 1)/sqrt(2) at every point.
        branch = continue_branch(
            linear_branch(), "mu", initial_state={"x": 1.0},
            max_points=20, parameter_range=(0.0, 5.0),
        )
        expected = 1.0 / math.sqrt(2.0)
        worst = max(
            abs(point.tangent_parameter - expected) for point in branch.points
        )
        assert worst < 1e-9, worst

    def test_no_fold_is_invented(self) -> None:
        branch = continue_branch(
            linear_branch(), "mu", initial_state={"x": 1.0},
            max_points=20, parameter_range=(0.0, 5.0),
        )
        assert branch.folds == ()
        assert not branch.turned

    def test_finding_no_fold_is_not_reported_as_a_property_of_the_branch(
        self,
    ) -> None:
        # It is a statement about the stretch that was followed. A branch
        # that folds a hundred units further on folds just the same.
        branch = continue_branch(
            linear_branch(), "mu", initial_state={"x": 1.0},
            max_points=20, parameter_range=(0.0, 5.0),
        )
        assert "about the stretch followed" in branch.summary()

    def test_leaving_the_requested_range_stops_the_run(self) -> None:
        branch = continue_branch(
            linear_branch(), "mu", initial_state={"x": 1.0},
            max_points=200, parameter_range=(0.0, 5.0),
        )
        assert branch.stopped_because == STOPPED_OUT_OF_RANGE
        # The last point lies just outside: a step lands where arclength
        # takes it, and truncating it back would report a point nothing
        # solved for.
        assert branch.points[-1].parameter > 5.0

    def test_running_out_of_points_is_reported_as_a_budget_not_a_result(
        self,
    ) -> None:
        branch = continue_branch(
            linear_branch(), "mu", initial_state={"x": 1.0}, max_points=5,
        )
        assert len(branch.points) == 5
        assert branch.stopped_because == STOPPED_MAX_POINTS


class TestRefusals:
    def test_no_steady_state_to_start_from(self) -> None:
        """dx/dt = -1 - x^2 has no real root. Nothing to continue.

        The refusal this module needs most: a short branch and no branch at
        all are different findings, and a caller that cannot tell them apart
        reads the second as the first.
        """
        with pytest.raises(ContinuationError, match="no steady state at mu"):
            continue_branch(saddle_node(mu=-1.0), "mu", initial_state={"x": 1.0})

    def test_that_refusal_reports_the_residual_and_says_what_to_do(self) -> None:
        with pytest.raises(ContinuationError) as caught:
            continue_branch(saddle_node(mu=-1.0), "mu", initial_state={"x": 0.5})
        message = str(caught.value)
        assert "largest time derivative" in message
        assert "analysis.analyse" in message
        assert "does not find one" in message

    def test_starting_exactly_on_the_fold_is_refused(self) -> None:
        # At mu = 0, x = 0 the branch is vertical in mu, so "set off toward
        # increasing mu" does not name a direction. Guessing one would pick
        # an arm at random.
        with pytest.raises(ContinuationError, match="name a direction"):
            continue_branch(
                saddle_node(mu=0.0), "mu", initial_state={"x": 0.0}
            )

    def test_an_unknown_parameter_is_refused(self) -> None:
        with pytest.raises(KeyError, match="not a parameter"):
            continue_branch(saddle_node(), "kcat")

    def test_a_starting_state_naming_an_unknown_species_is_refused(self) -> None:
        # A dict lookup drops the typo silently and the solve starts
        # somewhere else entirely.
        with pytest.raises(ContinuationError, match="no species for"):
            continue_branch(saddle_node(), "mu", initial_state={"X": 1.0})

    def test_a_starting_state_missing_a_species_is_refused(self) -> None:
        network = ReactionNetwork(
            name="two_pools",
            species=(Species(id="x", initial=1.0), Species(id="y", initial=1.0)),
            parameters=(Parameter(id="mu", value=1.0),),
            reactions=(
                Reaction(id="birth", reactants={}, products={"x": 1}, rate_law="mu"),
                Reaction(id="death", reactants={"x": 1}, products={}, rate_law="x"),
                Reaction(id="ybirth", reactants={}, products={"y": 1}, rate_law="mu"),
                Reaction(id="ydeath", reactants={"y": 1}, products={}, rate_law="y"),
            ),
        )
        with pytest.raises(ContinuationError, match="no value for"):
            continue_branch(network, "mu", initial_state={"x": 1.0})

    def test_a_rate_rule_network_is_refused_rather_than_silently_frozen(self) -> None:
        """The refusal that stops a confident answer about the wrong model.

        `analysis.derivative_function` compiles REACTIONS. A species driven
        by a rate rule would get dx/dt = 0 from it, and continuation would
        follow a branch of a different system to a small residual.
        """
        network = ReactionNetwork(
            name="rate_rule_model",
            species=(Species(id="x", initial=1.0),),
            parameters=(Parameter(id="mu", value=1.0),),
            rate_rules=(RateRule(target="x", expression="mu - x * x"),),
        )
        with pytest.raises(ContinuationError, match="rate rule"):
            continue_branch(network, "mu")

    def test_a_single_point_is_not_a_branch(self) -> None:
        with pytest.raises(ValueError, match="max_points"):
            continue_branch(saddle_node(), "mu", max_points=1)

    def test_no_direction_is_refused(self) -> None:
        with pytest.raises(ValueError, match="direction"):
            continue_branch(saddle_node(), "mu", direction=0)

    def test_incoherent_step_bounds_are_refused(self) -> None:
        with pytest.raises(ValueError, match="step bounds"):
            continue_branch(
                saddle_node(), "mu", step=1.0, min_step=2.0, max_step=3.0
            )

    def test_an_unknown_species_is_refused_by_state_values(
        self, round_the_fold
    ) -> None:
        # An empty plot of a real branch is a lie a typo can produce.
        with pytest.raises(KeyError, match="not a species"):
            round_the_fold.state_values("X")


class TestWhatItRefusesToConclude:
    def test_the_report_says_it_followed_one_branch_from_one_point(
        self, round_the_fold
    ) -> None:
        """The claim that must never be flattened into "these are the states".

        A toggle switch's two stable states may lie on branches that never
        meet, and following one says nothing about the other.
        """
        summary = round_the_fold.summary()
        assert "ONE BRANCH, FROM ONE STARTING POINT" in summary
        assert "disconnected" in summary
        assert "analysis.analyse" in summary

    def test_a_branch_with_no_points_does_not_read_as_a_model_with_none(
        self,
    ) -> None:
        empty = Branch(parameter="mu", points=())
        assert "did not start" in empty.summary()
        assert empty.parameter_range() is None

    def test_the_step_bounds_are_reported_so_the_run_is_reproducible(
        self, round_the_fold
    ) -> None:
        # The defaults are fractions of the starting point's own magnitude,
        # so the module constants alone do not reproduce a run and the
        # bounds that applied have to travel with the result.
        low, high = round_the_fold.step_bounds
        assert 0.0 < low < high
        assert all(step <= high for step in _steps(round_the_fold))

    def test_the_stopping_reason_is_always_given(self, round_the_fold) -> None:
        assert round_the_fold.stopped_because


def _steps(branch: Branch) -> list:
    """Arclength actually taken between consecutive accepted points."""
    return [
        after.arclength - before.arclength
        for before, after in zip(branch.points, branch.points[1:])
    ]
