"""Whether a model may be made smaller, tested where the answer is known.

A quasi-steady-state reduction is licensed by a ratio of timescales, and a
ratio of timescales is a thing that can be constructed exactly. Two decoupled
first-order turnovers have a diagonal Jacobian whose eigenvalues ARE the two
degradation constants, so the ratio the module should report is a number the
test chose. A linear chain has a triangular Jacobian whose eigenvectors are
writable in closed form, so the participation the module should report is
too.

Everything below is pinned against one of those, or against a refusal. The
refusals matter most: a module that decides whether a reduction is allowed
is only worth having if it says no, and says why, and names the number that
made it say so.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from caterva.compose import analysis
from caterva.compose.builder import Composition
from caterva.compose.library import (
    CONSTANT_INFLOW,
    FIRST_ORDER_OUTFLOW,
    MASS_ACTION_CONVERSION,
    PHOSPHORYLATION_CYCLE,
    REVERSIBLE_BINDING,
    SYNTHESIS_DEGRADATION,
)
from caterva.compose.pipeline import compose
from caterva.compose.reduction import (
    FAST_PARTICIPATION,
    LAYER_TOLERANCE,
    SEPARATION_THRESHOLD,
    Candidate,
    Mode,
    ReductionRefused,
    TimescaleSeparation,
    candidates_for_elimination,
    timescale_separation,
    validity_report,
)


def with_values(network, **values):
    """The same network with these parameters set to these numbers.

    `Composition` emits each motif's placeholder default and has no way to
    override one, so a test that wants a CHOSEN spectrum has to set the
    constants after the network is built. Same `dataclasses.replace` walk
    `sensitivity.analyse` uses to perturb a parameter, and it asserts the
    names exist -- a typo would otherwise leave the default in place and the
    test would be pinning the library's numbers rather than its own.
    """
    known = {p.id for p in network.parameters}
    unknown = sorted(set(values) - known)
    assert not unknown, f"{unknown} are not parameters of this network: {sorted(known)}"
    return replace(
        network,
        parameters=tuple(
            replace(p, value=float(values[p.id])) if p.id in values else p
            for p in network.parameters
        ),
    )


def two_turnovers(fast_kd: float, slow_kd: float = 0.1):
    """dX/dt = ks - kd*X, twice, coupled to nothing.

    THE JACOBIAN IS EXACTLY diag(-fast_kd, -slow_kd). Each species' rate law
    mentions only itself, so every off-diagonal entry is a central
    difference between two identical numbers -- exactly zero, not nearly --
    and the eigenvalues of a diagonal matrix are its diagonal. The timescale
    ratio is therefore fast_kd / slow_kd with no numerics in between, which
    is what makes the assertions here analytic rather than golden.
    """
    composition = Composition("two turnovers")
    composition.add(SYNTHESIS_DEGRADATION, "fast")
    composition.add(SYNTHESIS_DEGRADATION, "slow")
    return with_values(composition.to_network(), fast_kd=fast_kd, slow_kd=slow_kd)


def draining_pool(k: float, k_out: float):
    """Feed -> A -> B -> out, all first order except the feed.

    dA/dt = v_in - k*A
    dB/dt = k*A - k_out*B

    Lower triangular, so the eigenvalues are -k and -k_out exactly, and the
    eigenvectors are writable: the slow one is (0, 1) -- the slow mode does
    not move A at all -- and the fast one is (-(k - k_out)/k, 1) normalised.
    That gives A a fast participation of exactly 1 and B one of
    1 / (a^2 + 2) with a = (k - k_out)/k, both of which the tests below
    assert against the formula rather than against a recorded number.

    It is also the textbook case: a pool that drains quickly sits at a
    quasi-steady state A = v_in / k, and eliminating it leaves
    dB/dt = v_in - k_out*B. The right answer is that A goes and B stays.
    """
    composition = Composition("draining pool")
    composition.add(CONSTANT_INFLOW, "feed")
    composition.add(MASS_ACTION_CONVERSION, "conv", {"A": "feed_S"})
    composition.add(FIRST_ORDER_OUTFLOW, "drain", {"S": "conv_B"})
    return with_values(composition.to_network(), conv_k=k, drain_k_out=k_out)


# -- shared, because the steady-state search behind each is the slow part ---


@pytest.fixture(scope="module")
def separated():
    """A hundredfold separation: kd of 10 against kd of 0.1."""
    return two_turnovers(fast_kd=10.0)


@pytest.fixture(scope="module")
def unseparated():
    """Two identical turnovers. The ratio is exactly one."""
    return two_turnovers(fast_kd=0.1)


@pytest.fixture(scope="module")
def chain():
    return draining_pool(k=100.0, k_out=1.0)


class TestAnAnalyticTimescaleRatio:
    """Two decoupled turnovers, where every number is chosen not measured."""

    def test_the_eigenvalues_are_the_degradation_constants_negated(
        self, separated
    ) -> None:
        report = timescale_separation(separated)
        reals = sorted(mode.eigenvalue.real for mode in report.modes)
        assert reals == pytest.approx([-10.0, -0.1], rel=1e-6)

    def test_the_gap_is_the_ratio_of_the_two_constants(self, separated) -> None:
        # 10 / 0.1. Not a number this test recorded from a run -- a number
        # it set, one line up, by choosing the constants.
        assert timescale_separation(separated).gap == pytest.approx(100.0, rel=1e-6)

    def test_the_timescales_are_the_reciprocals_fastest_first(
        self, separated
    ) -> None:
        report = timescale_separation(separated)
        assert [m.timescale for m in report.modes] == pytest.approx(
            [0.1, 10.0], rel=1e-6
        )

    def test_the_split_puts_one_mode_on_each_side(self, separated) -> None:
        report = timescale_separation(separated)
        assert report.split == 1
        assert len(report.fast_modes) == 1
        assert len(report.slow_modes) == 1
        assert report.fast_timescale == pytest.approx(0.1, rel=1e-6)
        assert report.slow_timescale == pytest.approx(10.0, rel=1e-6)

    def test_a_hundredfold_gap_is_licensed(self, separated) -> None:
        report = timescale_separation(separated)
        assert report.licensed
        assert "is licensed" in report.summary()

    def test_the_fast_species_is_the_one_with_the_larger_constant(
        self, separated
    ) -> None:
        """The Jacobian is diagonal, so the eigenvectors are the axes.

        Each species moves in exactly one mode and not at all in the other,
        which makes the participations exactly 1 and exactly 0 -- the one
        case where the heuristic has no judgement left in it.
        """
        rows = {row.species: row for row in candidates_for_elimination(separated)}
        assert rows["fast_X"].participation == pytest.approx(1.0, abs=1e-9)
        assert rows["slow_X"].participation == pytest.approx(0.0, abs=1e-9)
        assert rows["fast_X"].eliminable
        assert not rows["slow_X"].eliminable

    def test_every_species_is_returned_ranked_not_only_the_winners(
        self, separated
    ) -> None:
        # A species just under the line is the row a reader most needs, so
        # the function returns all of them and marks the ones that cleared.
        rows = candidates_for_elimination(separated)
        assert [row.species for row in rows] == ["fast_X", "slow_X"]


class TestTheRefusalWhenNothingIsFaster:
    """The most valuable output in the module.

    Two identical turnovers have identical eigenvalues. The participation
    arithmetic still runs on them, still ranks the two species, and still
    puts one first -- so without a check on the gap the module would hand
    back a recommendation to eliminate a variable that is not fast at all.
    """

    def test_the_ratio_of_two_equal_eigenvalues_is_one(self, unseparated) -> None:
        assert timescale_separation(unseparated).gap == pytest.approx(1.0, rel=1e-6)

    def test_reporting_the_spectrum_does_not_raise(self, unseparated) -> None:
        # The absence of a gap is a finding about the model and the caller
        # may want to print it. Only the RECOMMENDATION is refused.
        report = timescale_separation(unseparated)
        assert not report.licensed
        assert "no reduction is licensed" in report.summary()

    def test_asking_which_species_to_eliminate_is_refused(self, unseparated) -> None:
        with pytest.raises(ReductionRefused) as caught:
            candidates_for_elimination(unseparated)
        assert "cannot be reduced" in str(caught.value)

    def test_the_refusal_names_the_ratio_it_actually_found(
        self, unseparated
    ) -> None:
        """A refusal that says only "no separation" leaves the reader unable
        to tell a model that missed by a hair from one whose modes are
        identical, and those call for different next steps.
        """
        report = timescale_separation(unseparated)
        with pytest.raises(ReductionRefused) as caught:
            candidates_for_elimination(unseparated)
        message = str(caught.value)
        assert f"{report.gap:.2f}" in message
        assert "1.00" in message, message
        assert f"{SEPARATION_THRESHOLD:g}" in message

    def test_the_refusal_says_what_to_do_instead(self, unseparated) -> None:
        with pytest.raises(ReductionRefused) as caught:
            candidates_for_elimination(unseparated)
        message = str(caught.value)
        assert "integrate the model as it stands" in message
        assert "sweep" in message

    def test_the_error_it_would_have_introduced_is_the_size_of_the_answer(
        self, unseparated
    ) -> None:
        # The argument the refusal is making, in the units a reader cares
        # about: eps = 1 / 1 = 1, so the reduced model would be wrong by of
        # order the whole thing.
        report = validity_report(timescale_separation(unseparated))
        assert report.relative_error == pytest.approx(1.0, rel=1e-6)
        assert not report.licensed


class TestTheThresholdIsAStatedJudgement:
    """A factor of ten, argued for in the constant's comment.

    The two cases here are constructed FROM the constant rather than from
    the number ten, so raising or lowering it moves the tests with it. What
    they pin is that the constant is the thing the decision is made on, not
    that ten in particular is right.
    """

    def test_the_threshold_is_the_usual_factor_of_ten(self) -> None:
        assert SEPARATION_THRESHOLD == 10.0

    def test_a_ratio_just_under_the_threshold_is_refused(self) -> None:
        slow = 0.1
        network = two_turnovers(fast_kd=slow * SEPARATION_THRESHOLD * 0.9, slow_kd=slow)
        report = timescale_separation(network)
        assert report.gap == pytest.approx(SEPARATION_THRESHOLD * 0.9, rel=1e-6)
        assert not report.licensed
        with pytest.raises(ReductionRefused, match="cannot be reduced"):
            candidates_for_elimination(network)

    def test_a_ratio_just_over_the_threshold_is_licensed(self) -> None:
        slow = 0.1
        network = two_turnovers(fast_kd=slow * SEPARATION_THRESHOLD * 1.1, slow_kd=slow)
        report = timescale_separation(network)
        assert report.gap == pytest.approx(SEPARATION_THRESHOLD * 1.1, rel=1e-6)
        assert report.licensed
        rows = candidates_for_elimination(network)
        assert [row.species for row in rows if row.eliminable] == ["fast_X"]

    def test_a_caller_may_demand_a_stricter_one(self, separated) -> None:
        # The threshold is an argument, not a constant baked into a
        # comparison, so a reader who wants 1% error can ask for it -- and
        # the hundredfold gap that passes at ten is refused at a thousand.
        assert timescale_separation(separated, threshold=1000.0).licensed is False
        with pytest.raises(ReductionRefused, match="at least 1000"):
            candidates_for_elimination(separated, threshold=1000.0)


class TestWhichSpeciesAreFast:
    """A chain, where the eigenvectors are not the coordinate axes.

    The decoupled model cannot tell a correct participation from a
    permutation of the species list: each species sits in exactly one mode
    either way. Here the fast eigenvector has a component on BOTH species
    and the answer is still that only the upstream pool may go, which is a
    property of the eigenvectors rather than of the labelling.
    """

    def test_the_gap_is_the_ratio_of_the_two_rate_constants(self, chain) -> None:
        # Triangular Jacobian: the eigenvalues are the diagonal, -100 and -1.
        assert timescale_separation(chain).gap == pytest.approx(100.0, rel=1e-6)

    def test_the_fast_draining_pool_is_the_candidate(self, chain) -> None:
        """Exactly 1, and the reason is structural.

        The slow eigenvector is (0, 1): the slow mode does not move the
        upstream pool at all. So none of that species' motion is slow, at
        any rate constants, and the participation is not a number that
        happened to land above a threshold.
        """
        rows = {row.species: row for row in candidates_for_elimination(chain)}
        assert rows["feed_S"].participation == pytest.approx(1.0, abs=1e-9)
        assert rows["feed_S"].eliminable

    def test_the_downstream_species_matches_the_closed_form(self, chain) -> None:
        # a = (k - k_out) / k from the fast eigenvector (-a, 1); its
        # normalised square over species B is 1 / (a^2 + 1), against a slow
        # weight of exactly 1, so the participation is 1 / (a^2 + 2).
        a = (100.0 - 1.0) / 100.0
        rows = {row.species: row for row in candidates_for_elimination(chain)}
        assert rows["conv_B"].participation == pytest.approx(
            1.0 / (a * a + 2.0), rel=1e-6
        )

    def test_the_downstream_species_must_stay_a_differential_variable(
        self, chain
    ) -> None:
        # 0.34, under the half. Eliminating B would remove the only variable
        # the reduced model is about.
        rows = {row.species: row for row in candidates_for_elimination(chain)}
        assert not rows["conv_B"].eliminable
        assert "must stay a differential variable" in rows["conv_B"].describe()

    def test_the_candidate_count_does_not_exceed_the_fast_subspace(
        self, chain
    ) -> None:
        # One fast mode, one candidate. The check that would fire if a third
        # species were flagged into a two-dimensional fast subspace.
        report = timescale_separation(chain)
        rows = candidates_for_elimination(chain, separation=report)
        validity = validity_report(report, rows)
        assert validity.rank_limit == 1
        assert validity.flagged == 1
        assert not validity.over_reduced


class TestRefusalsWhenThereIsNoSpectrum:
    """Cases where the honest output is not a small number but no number."""

    def test_a_model_with_one_dynamic_mode_has_no_ratio(self) -> None:
        """A phosphorylation cycle conserves total protein, total kinase and
        total phosphatase -- three laws over four species -- so exactly one
        direction moves. There is nothing for it to be fast relative to.
        """
        composition = Composition("one cycle")
        composition.add(PHOSPHORYLATION_CYCLE, "cycle")
        with pytest.raises(ReductionRefused) as caught:
            timescale_separation(composition.to_network())
        assert "one dynamic mode" in str(caught.value)
        assert "conservation laws rather than being slow" in str(caught.value)

    def test_a_model_with_no_steady_state_is_refused(self) -> None:
        # An inflow and nothing else: dS/dt = v_in > 0 forever. There is no
        # state to linearise about, so there are no eigenvalues to compare.
        composition = Composition("inflow only")
        composition.add(CONSTANT_INFLOW, "feed")
        composition.add(CONSTANT_INFLOW, "feed2")
        with pytest.raises(ReductionRefused) as caught:
            timescale_separation(composition.to_network())
        assert "no stable steady state" in str(caught.value)
        assert "starting points" in str(caught.value)

    def test_a_bistable_model_is_refused_and_told_how_to_ask_again(self) -> None:
        """Each state has its own Jacobian and its own answer.

        Refusing is not a dead end here: the message names `at=`, and the
        second half of this test uses it, so the way out the refusal
        describes is one that exists.
        """
        model = compose("a toggle switch between two repressors")
        with pytest.raises(ReductionRefused) as caught:
            timescale_separation(model.network)
        assert "stable states were found" in str(caught.value)
        assert "`at=`" in str(caught.value)

        states = analysis.analyse(model.network, starts_per_species=16).stable_points
        assert len(states) == 2, "the premise"
        for state in states:
            report = timescale_separation(model.network, at=state)
            assert len(report.modes) == 2
            assert report.gap >= 1.0

    def test_the_two_branches_of_a_switch_get_their_own_spectra(self) -> None:
        # And the reason the refusal above is not pedantry: the two states
        # are not the same state, so a spectrum reported without saying
        # which one would be reporting one of two answers at random.
        model = compose("a toggle switch between two repressors")
        states = analysis.analyse(model.network, starts_per_species=16).stable_points
        reports = [timescale_separation(model.network, at=s) for s in states]
        assert reports[0].state != reports[1].state


class TestTheSpectrumAgreesWithTheAnalysisModule:
    """The duplication this module could not avoid, made falsifiable.

    `analysis.analyse` computes eigenvalues and drops one near-zero per
    conservation law. `reduction` has to redo the decomposition because it
    needs the eigenVECTORS, so it reimplements the dropping rule -- and a
    rule kept in two places drifts. This is the test that turns red when it
    does, on a model that actually has conservation laws to drop.
    """

    @staticmethod
    def _mixed():
        composition = Composition("turnover and binding")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        composition.add(REVERSIBLE_BINDING, "b")
        return composition.to_network()

    def test_the_model_has_conservation_laws_to_drop(self) -> None:
        # Without this the test would pass on a model where the rule never
        # fires, which is the shape of a guard that guards nothing.
        network = self._mixed()
        assert len(network.conservation_laws()) == 2

    def test_the_retained_eigenvalues_are_the_same_set(self) -> None:
        network = self._mixed()
        point = analysis.analyse(network, starts_per_species=16).stable_points[0]
        theirs = sorted((v.real, v.imag) for v in point.eigenvalues)
        mine = sorted(
            (m.eigenvalue.real, m.eigenvalue.imag)
            for m in timescale_separation(network, at=point).modes
        )
        assert len(mine) == len(theirs) == len(network.species) - 2
        # Flattened: `approx` compares sequences of numbers, and a sequence
        # of pairs is not one.
        assert [x for pair in mine for x in pair] == pytest.approx(
            [x for pair in theirs for x in pair], rel=1e-6, abs=1e-12
        )


class TestAFastModeMustRelax:
    """A wide gap is not enough: the fast modes have to be going somewhere.

    Quasi-steady state means the fast subsystem has settled. A fast mode
    with a positive real part has not settled and will not; setting its
    variable's derivative to zero replaces something that is running away
    with a constraint it is running away from. The gap can be enormous and
    the reduction still meaningless.

    Constructed directly rather than found in a model, for the reason the
    sensitivity suite constructs a `Sensitivity` to test its threshold: the
    property is about the classification, and a test that had to locate a
    saddle with a fast unstable direction would be pinning which model
    happens to have one.
    """

    @staticmethod
    def _with_a_growing_fast_mode() -> TimescaleSeparation:
        fast = Mode(eigenvalue=complex(+100.0, 0.0), timescale=0.01)
        slow = Mode(eigenvalue=complex(-1.0, 0.0), timescale=1.0)
        return TimescaleSeparation(
            state={"A": 1.0, "B": 1.0},
            species=("A", "B"),
            modes=(fast, slow),
            ratios=(100.0,),
            split=1,
            gap=100.0,
            threshold=SEPARATION_THRESHOLD,
        )

    def test_a_growing_fast_mode_is_not_licensed_however_wide_the_gap(self) -> None:
        report = self._with_a_growing_fast_mode()
        assert report.gap > SEPARATION_THRESHOLD, "the gap alone would allow it"
        assert not report.fast_modes_relax
        assert not report.licensed

    def test_the_same_spectrum_with_the_sign_flipped_is_licensed(self) -> None:
        # Otherwise the test above would pass on an implementation that
        # refused everything.
        report = replace(
            self._with_a_growing_fast_mode(),
            modes=(
                Mode(eigenvalue=complex(-100.0, 0.0), timescale=0.01),
                Mode(eigenvalue=complex(-1.0, 0.0), timescale=1.0),
            ),
        )
        assert report.fast_modes_relax
        assert report.licensed

    def test_a_growing_SLOW_mode_does_not_block_the_reduction(self) -> None:
        # Slow instability is exactly what a slow manifold is for: the fast
        # variables relax onto it and the interesting dynamics happen along
        # it. Only the FAST modes have to be attracting.
        report = replace(
            self._with_a_growing_fast_mode(),
            modes=(
                Mode(eigenvalue=complex(-100.0, 0.0), timescale=0.01),
                Mode(eigenvalue=complex(+1.0, 0.0), timescale=1.0),
            ),
        )
        assert report.licensed

    def test_asking_for_candidates_refuses_and_says_which_fact_did_it(
        self,
    ) -> None:
        # The network is `None` on purpose: this refusal must be reached
        # before anything is computed from the model, and a run that touched
        # it would raise an AttributeError instead of the refusal.
        report = self._with_a_growing_fast_mode()
        with pytest.raises(ReductionRefused) as caught:
            candidates_for_elimination(None, separation=report)
        message = str(caught.value)
        assert "GROW rather than relax" in message
        # And it does NOT claim the gap was too small, which it was not.
        assert "cannot be reduced at this state" not in message

    def test_the_summary_says_so_rather_than_calling_it_licensed(self) -> None:
        summary = self._with_a_growing_fast_mode().summary()
        assert "At least one fast mode GROWS" in summary
        assert "is licensed" not in summary


class TestWhatTheReductionCosts:
    def test_the_error_is_one_over_the_gap(self, separated) -> None:
        # eps = tau_fast / tau_slow, which for this model is 0.1 / 10.
        report = validity_report(timescale_separation(separated))
        assert report.relative_error == pytest.approx(0.01, rel=1e-6)

    def test_the_initial_layer_is_the_fast_timescale_times_the_decay(
        self, separated
    ) -> None:
        # The reduced model replaces the fast transient with a jump, so it
        # says nothing until the transient is over. ln(1/0.01) = 4.6 fast
        # timescales, which at tau_fast = 0.1 is 0.46 time units.
        report = validity_report(timescale_separation(separated))
        assert report.initial_layer == pytest.approx(
            0.1 * math.log(1.0 / LAYER_TOLERANCE), rel=1e-6
        )

    def test_the_summary_refuses_to_treat_the_steady_state_as_evidence(
        self, separated
    ) -> None:
        """The trap this paragraph exists to close.

        A quasi-steady-state reduction sets the fast derivatives to zero,
        which the full model's fixed point already satisfies -- so the
        reduced model has the same fixed point at EVERY gap, including a gap
        of one. Somebody checking a reduction by comparing endpoints would
        find agreement and conclude nothing at all.
        """
        summary = validity_report(timescale_separation(separated)).summary()
        assert "same fixed point by construction" in summary
        assert "the error lives entirely in the approach" in summary

    def test_the_error_is_reported_as_an_order_and_not_as_a_bound(
        self, separated
    ) -> None:
        summary = validity_report(timescale_separation(separated)).summary()
        assert "of order" in summary
        assert "not a bound" in summary

    def test_more_candidates_than_fast_directions_is_flagged(self) -> None:
        """Three species can share a two-dimensional fast subspace.

        Each of them then carries most of its motion in the fast directions
        and the participation ranking flags all three, but eliminating three
        variables removes a dimension the fast subspace does not have. The
        rank limit is the number of fast modes and nothing about the
        per-species ranking can see it.
        """
        separation = TimescaleSeparation(
            state={"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0},
            species=("A", "B", "C", "D"),
            modes=(
                Mode(complex(-100.0, 0.0), 0.01),
                Mode(complex(-90.0, 0.0), 1.0 / 90.0),
                Mode(complex(-1.0, 0.0), 1.0),
                Mode(complex(-0.9, 0.0), 1.0 / 0.9),
            ),
            ratios=(100.0 / 90.0, 90.0, 1.0 / 0.9),
            split=2,
            gap=90.0,
            threshold=SEPARATION_THRESHOLD,
        )
        flagged = tuple(
            Candidate(name, 0.9, 0.9, 0.1, FAST_PARTICIPATION) for name in "ABC"
        )
        report = validity_report(separation, flagged)
        assert report.rank_limit == 2
        assert report.flagged == 3
        assert report.over_reduced
        assert "At most 2 variable(s) may go" in report.summary()

    def test_a_reduction_within_its_rank_is_not_flagged(self) -> None:
        # The same check must not fire on the ordinary case, or it would be
        # a warning people learn to ignore.
        separation = TimescaleSeparation(
            state={"A": 1.0, "B": 1.0},
            species=("A", "B"),
            modes=(Mode(complex(-100.0, 0.0), 0.01), Mode(complex(-1.0, 0.0), 1.0)),
            ratios=(100.0,),
            split=1,
            gap=100.0,
            threshold=SEPARATION_THRESHOLD,
        )
        one = (Candidate("A", 0.99, 0.99, 0.01, FAST_PARTICIPATION),)
        assert not validity_report(separation, one).over_reduced


class TestTheModeItself:
    def test_a_real_eigenvalue_has_no_period(self) -> None:
        assert Mode(complex(-2.0, 0.0), 0.5).period is None
        assert not Mode(complex(-2.0, 0.0), 0.5).oscillatory

    def test_a_complex_pair_reports_a_period_distinct_from_its_timescale(
        self,
    ) -> None:
        # Decay time and period are different numbers about different
        # things: this mode rings roughly six times before it dies.
        mode = Mode(complex(-1.0, 1.0), 1.0)
        assert mode.oscillatory
        assert mode.period == pytest.approx(2.0 * math.pi, rel=1e-9)
        assert "ringing with period" in mode.describe()

    def test_a_growing_mode_says_so_in_its_description(self) -> None:
        assert "GROWING, not relaxing" in Mode(complex(+1.0, 0.0), 1.0).describe()
        assert "GROWING" not in Mode(complex(-1.0, 0.0), 1.0).describe()


class TestTheParticipationThresholdIsAStatedJudgement:
    def test_it_is_a_half(self) -> None:
        assert FAST_PARTICIPATION == 0.5

    def test_a_species_split_evenly_lands_on_the_eliminable_side(self) -> None:
        # Stated rather than left to a comparison operator: exactly half is
        # a coin flip either way, and which way it falls should be a
        # decision somebody made.
        assert Candidate("A", 0.5, 0.5, 0.5, FAST_PARTICIPATION).eliminable
        assert not Candidate("A", 0.49, 0.49, 0.51, FAST_PARTICIPATION).eliminable

    def test_the_row_carries_the_number_and_not_only_the_verdict(self) -> None:
        row = Candidate("A", 0.51, 0.51, 0.49, FAST_PARTICIPATION)
        assert "51%" in row.describe()
