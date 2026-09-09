"""Whether the experiment could have returned the constants at all.

The case that matters most is the one with an exact answer. dX/dt = ks -
kd*X settles at ks/kd, so a steady state measured on its own moves with both
constants and determines neither: scale ks and kd together and the number
does not budge. A sensitivity ranking says "both matter"; this file pins
that "both matter" and "you can measure both" are different sentences.

Then the other half, on the same model with one more observation. The
settling time is 1/kd, which breaks the tie, and the rank goes from 1 to 2.
Same equations, same values, a different experiment -- which is the whole
claim this module makes.

The linear algebra is driven on matrices written down by hand as well as on
ones computed from a model, because the cases where the right answer is
known in closed form -- a row of (1, -1), a row of (1, 1), a column of
zeroes -- should not depend on finding a model that happens to produce them.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from Terium.compose.builder import Composition
from Terium.compose.identifiability import (
    IdentifiabilityUnavailable, SensitivityMatrix, analyse, decompose,
    identifiable_subset, rank_of, sensitivity_matrix,
    singular_value_threshold, unidentifiable_combinations,
)
from Terium.compose.library import SYNTHESIS_DEGRADATION
from Terium.compose.sensitivity import (
    MACHINE_PRECISION, NEGLIGIBLE, SOLVER_PRECISION, resolution_for,
    settling_time, steady_state_of,
)


# -- shared, because the steady-state solves are the expensive part ---------
#
# Each report re-solves the model twice per parameter. Module-scoped so a
# failure cannot leak into another file's fixtures, and safe to share
# because everything returned is a frozen dataclass no test mutates.


@pytest.fixture(scope="module")
def turnover():
    """dX/dt = ks - kd*X. Steady state ks/kd, settling time 1/kd."""
    composition = Composition("turnover")
    composition.add(SYNTHESIS_DEGRADATION, "x")
    return composition.to_network()


@pytest.fixture(scope="module")
def from_the_steady_state(turnover):
    return analyse(
        turnover, [steady_state_of("x_X")], parameters=["x_ks", "x_kd"]
    )


@pytest.fixture(scope="module")
def from_both(turnover):
    return analyse(
        turnover,
        [steady_state_of("x_X"), settling_time()],
        parameters=["x_ks", "x_kd"],
    )


class TestTheModelWhereTheAnswerIsExact:
    """dX/dt = ks - kd*X, observed only at steady state.

    The single most important case in the file. The steady state is ks/kd
    for every ks and every kd, so the deficiency is not an artefact of the
    point, of the step, or of the solver: it is the whole truth about that
    experiment, and any implementation that misses it is not worth running
    on a model whose answer nobody knows.
    """

    def test_the_matrix_is_the_analytic_plus_and_minus_one(
        self, from_the_steady_state
    ) -> None:
        matrix = from_the_steady_state.matrix
        assert matrix.entry("steady-state x_X", "x_ks") == pytest.approx(
            1.0, rel=1e-4
        )
        assert matrix.entry("steady-state x_X", "x_kd") == pytest.approx(
            -1.0, rel=1e-4
        )

    def test_synthesis_and_degradation_are_not_separately_identifiable(
        self, from_the_steady_state
    ) -> None:
        report = from_the_steady_state
        assert report.rank == 1
        assert report.deficiency == 1
        assert identifiable_subset(report) == ()

    def test_the_direction_it_cannot_see_is_scaling_both_together(
        self, from_the_steady_state
    ) -> None:
        # v = (1, 1): multiply ks and kd by the same factor and the steady
        # state does not move. That is what "only the ratio" means, written
        # as a vector.
        (combination,) = unidentifiable_combinations(from_the_steady_state)
        first, second = combination.exponents
        assert first == pytest.approx(second, rel=1e-4)
        assert combination.involved == ("x_ks", "x_kd")

    def test_it_says_which_combination_survives(
        self, from_the_steady_state
    ) -> None:
        (combination,) = unidentifiable_combinations(from_the_steady_state)
        described = combination.describe()
        assert "only the combination x_ks * x_kd^-1 is determined" in described
        assert "not separately identifiable" in described

    def test_the_null_direction_is_unique_up_to_sign_here(
        self, from_the_steady_state
    ) -> None:
        # One dimension, so this is the only way to say it. Above one
        # dimension the SVD returns an arbitrary basis and the report has to
        # say so -- see TestReadingTheNullSpace.
        assert from_the_steady_state.basis_is_canonical

    def test_the_finding_is_about_the_model_and_not_about_the_arithmetic(
        self, turnover
    ) -> None:
        """The independent check, run without going near this module.

        If ks and kd are genuinely unrecoverable from a steady state, then
        two different parameter sets must give the SAME steady state. They
        do: scale both by three. And the settling time must tell them apart,
        or the next class is testing nothing.
        """
        tripled = replace(
            turnover,
            parameters=tuple(
                replace(p, value=p.value * 3.0) for p in turnover.parameters
            ),
        )
        here = steady_state_of("x_X")(turnover)
        there = steady_state_of("x_X")(tripled)
        assert there == pytest.approx(here, rel=1e-9), (
            "two parameter sets a factor of three apart must give the same "
            "steady state, or ks/kd is not what this model settles at"
        )
        assert settling_time()(tripled) == pytest.approx(
            settling_time()(turnover) / 3.0, rel=1e-5
        )


class TestOneMoreObservationChangesTheAnswer:
    def test_the_settling_time_makes_both_identifiable(
        self, from_the_steady_state, from_both
    ) -> None:
        """Same model, same values, one more measurement.

        The rank rises from 1 to 2 and the null space empties. Asserted
        against the one-observation report in the same test, because the
        rise is the finding -- rank 2 on its own says nothing about what the
        second observation bought.
        """
        assert from_the_steady_state.rank == 1
        assert from_both.rank == 2
        assert from_both.deficiency == 0
        assert from_both.null_space == ()
        assert set(identifiable_subset(from_both)) == {"x_ks", "x_kd"}

    def test_the_settling_time_does_not_depend_on_the_synthesis_rate(
        self, from_both
    ) -> None:
        # 1/kd exactly, so its row is (0, -1) and the rank it adds comes
        # entirely from being a DIFFERENT direction, not a bigger one.
        matrix = from_both.matrix
        floor = matrix.resolutions[matrix.quantities.index("settling time")]
        assert abs(matrix.entry("settling time", "x_ks")) < floor
        assert matrix.entry("settling time", "x_kd") == pytest.approx(
            -1.0, rel=1e-3
        )

    def test_the_summary_says_both_are_recoverable(self, from_both) -> None:
        summary = from_both.summary()
        assert "Every parameter is separately identifiable" in summary
        assert "not a proof" in summary


class TestTheThresholdIsDerived:
    """The number that decides what counts as a zero singular value.

    Derived from the rows' declared accuracy through Weyl's inequality, not
    picked -- see the module docstring. These drive it directly, because a
    threshold only checkable through a model is a threshold nobody can argue
    with.
    """

    def test_it_is_the_radius_of_the_error_ball(self) -> None:
        # sqrt(columns * sum of squared row resolutions), which for one row
        # is sqrt(columns) * that row's resolution.
        assert singular_value_threshold((NEGLIGIBLE,), 4) == pytest.approx(
            2.0 * NEGLIGIBLE, rel=1e-12
        )
        two_rows = singular_value_threshold((NEGLIGIBLE, NEGLIGIBLE), 2)
        assert two_rows == pytest.approx(2.0 * NEGLIGIBLE, rel=1e-12)

    def test_singular_values_straddling_it_are_split(self) -> None:
        """The behaviour the derivation exists for, driven from both sides.

        A diagonal matrix whose two singular values are the threshold times
        ten and the threshold over ten. The first is information and the
        second is rounding, and nothing about the shape of the matrix says
        which -- only the declared accuracy of the rows does.
        """
        threshold = singular_value_threshold((NEGLIGIBLE, NEGLIGIBLE), 2)
        matrix = SensitivityMatrix(
            quantities=("loud", "quiet"),
            parameters=("a", "b"),
            rows=((10.0 * threshold, 0.0), (0.0, threshold / 10.0)),
            resolutions=(NEGLIGIBLE, NEGLIGIBLE),
        )
        report = decompose(matrix)
        assert report.rank == 1
        assert identifiable_subset(report) == ("a",)
        assert report.unidentifiable() == ("b",)

    def test_a_singular_value_exactly_on_it_does_not_count(self) -> None:
        # It is by construction the one that cannot be told from zero, so
        # counting it would contradict the derivation it came from.
        assert rank_of((2.0, 1.0, 0.5), 1.0) == 1
        assert rank_of((), 1.0) == 0

    def test_it_follows_the_coarsest_observation(self) -> None:
        """A settling time is five orders of magnitude less accurate than a
        steady state, so a matrix containing one gets a coarser threshold.
        A single fixed cutoff would have had to be wrong for one of them.
        """
        exact = singular_value_threshold((resolution_for(MACHINE_PRECISION),), 2)
        approximate = singular_value_threshold(
            (resolution_for(MACHINE_PRECISION), resolution_for(SOLVER_PRECISION)),
            2,
        )
        assert approximate > 1e4 * exact

    def test_a_resolution_claiming_exactness_is_refused(self) -> None:
        # A row error bound of zero would say the arithmetic is exact, and
        # the threshold derived from it would count rounding as rank.
        with pytest.raises(ValueError, match="positive"):
            singular_value_threshold((0.0,), 2)

    def test_a_matrix_with_no_rows_or_no_columns_has_no_threshold(self) -> None:
        with pytest.raises(ValueError, match="tautology"):
            singular_value_threshold((), 2)
        with pytest.raises(ValueError, match="no columns"):
            singular_value_threshold((NEGLIGIBLE,), 0)


class TestReadingTheNullSpace:
    """Hand-written matrices whose answers are known by inspection."""

    def _matrix(self, parameters, rows, quantities=None):
        quantities = quantities or tuple(
            f"observation {i + 1}" for i in range(len(rows))
        )
        return SensitivityMatrix(
            quantities=tuple(quantities),
            parameters=tuple(parameters),
            rows=tuple(tuple(float(x) for x in row) for row in rows),
            resolutions=tuple(NEGLIGIBLE for _ in rows),
        )

    def test_a_row_of_ones_leaves_the_product_determined(self) -> None:
        # y = a*b gives d ln y / d ln a = d ln y / d ln b = 1, and what the
        # observation fixes is the product. The ratio case is the sign flip
        # of this one, which is why both are worth pinning.
        report = decompose(self._matrix(("a", "b"), ((1.0, 1.0),)))
        (combination,) = unidentifiable_combinations(report)
        assert "only the product a*b is determined" in combination.describe()
        assert identifiable_subset(report) == ()

    def test_a_parameter_nothing_responds_to_is_named_on_its_own(self) -> None:
        report = decompose(self._matrix(("a", "b", "c"), ((1.0, -1.0, 0.0),)))
        alone = [
            c for c in unidentifiable_combinations(report)
            if c.involved == ("c",)
        ]
        assert len(alone) == 1
        assert "no observation here responds to c on its own" in (
            alone[0].describe()
        )

    def test_a_parameter_outside_every_null_direction_is_identifiable(
        self,
    ) -> None:
        # a and b enter only as a ratio; c is measured directly. The verdict
        # on c must not be contaminated by the pair it shares a matrix with.
        report = decompose(
            self._matrix(
                ("a", "b", "c"), ((1.0, -1.0, 0.0), (0.0, 0.0, 1.0))
            )
        )
        assert report.rank == 2
        assert identifiable_subset(report) == ("c",)
        (combination,) = unidentifiable_combinations(report)
        assert combination.involved == ("a", "b")

    def test_a_higher_dimensional_null_space_admits_its_basis_is_arbitrary(
        self,
    ) -> None:
        """Honesty about what the printed directions are.

        With two dimensions the SVD returns one orthonormal basis of
        infinitely many. The per-parameter verdict does not depend on that
        choice; the printed directions do, and the summary says so rather
        than presenting a rotation as a result.
        """
        report = decompose(self._matrix(("a", "b", "c"), ((1.0, -1.0, 0.0),)))
        assert len(report.null_space) == 2
        assert not report.basis_is_canonical
        assert "not the only one" in report.summary()

    def test_a_matrix_of_zeroes_blames_the_observations(self) -> None:
        # Rank zero is not "every parameter trades against another" -- there
        # is nothing to trade. The distinction matters because the advice
        # differs: this asks for a different measurement, not a better fit.
        report = decompose(self._matrix(("a", "b"), ((0.0, 0.0),)))
        assert report.rank == 0
        assert identifiable_subset(report) == ()
        summary = report.summary()
        assert "No observation responds to any parameter" in summary
        assert "respond to nothing at all above their own noise floor" in summary

    def test_the_verdict_survives_rescaling_one_parameter(self) -> None:
        """Why the matrix is built in log space.

        Relative sensitivities are invariant under a change of a parameter's
        units, so the rank cannot depend on whether Km was written in mM or
        in uM. Driven here as the property it is: the same model in two unit
        systems is the same matrix.
        """
        report = decompose(self._matrix(("a", "b"), ((2.0, -2.0), (1.0, 1.0))))
        assert report.rank == 2
        assert set(identifiable_subset(report)) == {"a", "b"}


class TestRefusals:
    def test_a_zero_valued_parameter_is_refused_by_name(self, turnover) -> None:
        # Its column cannot exist: a fractional change in zero is undefined,
        # and log space has no room for it. Refused rather than dropped,
        # because a parameter missing from the matrix is a parameter missing
        # from the verdict.
        zeroed = replace(
            turnover,
            parameters=tuple(
                replace(p, value=0.0) if p.id == "x_ks" else p
                for p in turnover.parameters
            ),
        )
        with pytest.raises(IdentifiabilityUnavailable) as caught:
            sensitivity_matrix(zeroed, [lambda n: 1.0], ["x_ks", "x_kd"])
        message = str(caught.value)
        assert "x_ks" in message
        assert "zero has no logarithm" in message

    def test_an_observation_that_will_not_evaluate_is_refused(
        self, turnover
    ) -> None:
        """A missing row is not a smaller answer, it is a wrong one.

        Dropping it can only lower the rank, so the report would call
        parameters unrecoverable on the evidence of an experiment that was
        not in the matrix.
        """
        def unreadable(network):
            raise RuntimeError("the plate reader saturated")

        with pytest.raises(IdentifiabilityUnavailable) as caught:
            analyse(
                turnover,
                [unreadable],
                parameters=["x_ks", "x_kd"],
                quantity_names=["the saturated plate"],
            )
        message = str(caught.value)
        assert "the saturated plate" in message
        assert "the plate reader saturated" in message, (
            "the original reason must survive; naming the row is the only "
            "thing this wrapper adds"
        )
        assert "lower bound reported as an answer" in message

    def test_no_observations_is_a_tautology_not_a_finding(
        self, turnover
    ) -> None:
        with pytest.raises(IdentifiabilityUnavailable, match="tautology"):
            analyse(turnover, [], parameters=["x_ks"])

    def test_no_parameters_has_no_answer_worth_printing(
        self, turnover
    ) -> None:
        with pytest.raises(IdentifiabilityUnavailable, match="empty set"):
            analyse(turnover, [lambda n: 1.0], parameters=[])

    def test_a_repeated_parameter_is_refused_before_it_looks_like_biology(
        self, turnover
    ) -> None:
        # Two identical columns are dependent whatever the model does, and
        # the report would blame the mechanism for the caller's list.
        with pytest.raises(IdentifiabilityUnavailable, match="more than once"):
            analyse(
                turnover, [lambda n: 1.0], parameters=["x_ks", "x_ks"]
            )

    def test_an_unknown_parameter_names_the_real_ones(self, turnover) -> None:
        with pytest.raises(KeyError, match="x_ks"):
            analyse(turnover, [lambda n: 1.0], parameters=["nope"])

    def test_a_non_finite_entry_is_refused_rather_than_decomposed(self) -> None:
        # An infinite relative sensitivity means the observation is zero at
        # this point. Its singular values are undefined and numpy would
        # raise something that says nothing about the model.
        matrix = SensitivityMatrix(
            quantities=("y",),
            parameters=("a", "b"),
            rows=((float("inf"), 1.0),),
            resolutions=(NEGLIGIBLE,),
        )
        with pytest.raises(IdentifiabilityUnavailable, match="non-finite"):
            decompose(matrix)

    def test_a_row_that_does_not_match_its_label_is_refused(self) -> None:
        with pytest.raises(ValueError, match="same thing"):
            SensitivityMatrix(
                quantities=("y", "z"),
                parameters=("a",),
                rows=((1.0,),),
                resolutions=(NEGLIGIBLE,),
            )


class TestTheClaimIsLocalAndNotStructural:
    """The honesty requirement, pinned where a reader would look for it.

    This computes local, practical identifiability by finite differences at
    one point. Structural identifiability is a different question with a
    different method, and a module that blurred them would let a reader
    quote a full-rank result as proof that a model is identifiable.
    """

    def test_the_module_says_local_and_not_structural(self) -> None:
        from Terium.compose import identifiability

        prose = " ".join(identifiability.__doc__.lower().split())
        assert "local, practical identifiability" in prose
        assert "not structural identifiability" in prose
        assert "finite-difference" in prose

    def test_the_module_says_full_rank_is_not_proof(self) -> None:
        from Terium.compose import identifiability

        prose = " ".join(identifiability.__doc__.lower().split())
        assert "not proof of identifiability" in prose
        assert "global ambiguity" in prose

    def test_every_summary_carries_the_caveat(
        self, from_the_steady_state, from_both
    ) -> None:
        # Both the deficient and the full-rank report, because the full-rank
        # one is where a reader is most tempted to over-read.
        for report in (from_the_steady_state, from_both):
            summary = report.summary()
            assert "Local and practical, not structural" in summary
            assert "Full rank is not proof of identifiability" in summary
        assert from_both.rank == 2, "the full-rank half of the premise"

    def test_the_report_says_where_it_was_evaluated(
        self, from_the_steady_state
    ) -> None:
        # A local claim that does not name the point is not checkable.
        summary = from_the_steady_state.summary()
        assert "Evaluated at x_ks=1" in summary
        assert "x_kd=0.1" in summary
