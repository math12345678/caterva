"""Steady states and stability of composed models.

WHY A TRAJECTORY IS NOT AN ANSWER
---------------------------------
"Is this toggle switch bistable?" is not answered by one trajectory: a
bistable system reached from one starting point looks exactly like a
monostable one, and the second stable state is invisible unless something
goes and looks for it.

These tests pin the analysis against cases with known answers -- a
first-order system whose steady state is exactly ks/kd, a symmetric toggle
whose three fixed points are analytically locatable -- and pin the two
conclusions it must never draw: that it found everything, and that many
steady states on many conservation leaves are many attractors.
"""

from __future__ import annotations

import math

import pytest

from Terium.compose.analysis import (
    MARGINAL, OSCILLATORY_STABLE, OSCILLATORY_UNSTABLE, SADDLE, STABLE,
    UNSTABLE, analyse, classify, derivative_function, jacobian,
)
from Terium.compose.builder import Composition
from Terium.compose.grammar import recognise
from Terium.compose.library import SYNTHESIS_DEGRADATION


class TestAgainstAnalyticAnswers:
    def test_a_first_order_system_settles_at_ks_over_kd(self) -> None:
        """The one case where the answer is known in closed form.

        dX/dt = ks - kd*X has its steady state at exactly ks/kd, and its
        single eigenvalue is exactly -kd. If the machinery cannot reproduce
        that, nothing it says about a harder model is worth reading.
        """
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(composition.to_network())

        assert len(report.physical_points) == 1
        point = report.physical_points[0]
        # Library defaults: ks = 1.0, kd = 0.1.
        assert point.state["x_X"] == pytest.approx(10.0, rel=1e-6)
        assert point.classification == STABLE
        assert point.eigenvalues[0].real == pytest.approx(-0.1, rel=1e-4)
        # And the settling time is 1/kd.
        assert point.slowest_timescale == pytest.approx(10.0, rel=1e-3)

    def test_the_jacobian_matches_the_analytic_one(self) -> None:
        # d/dX (ks - kd*X) = -kd, exactly.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        rhs, species = derivative_function(composition.to_network())
        matrix = jacobian(rhs, [10.0])
        assert matrix == [[pytest.approx(-0.1, rel=1e-5)]]

    def test_the_symmetric_toggle_has_a_saddle_between_two_stable_states(self) -> None:
        """The textbook shape of a switch.

        Two mutually repressing genes with cooperative repression have three
        fixed points: a symmetric saddle on the separatrix, and two stable
        states that are each other's mirror image.
        """
        report = analyse(recognise("a toggle switch between two repressors").network())
        assert len(report.physical_points) == 3

        saddles = [p for p in report.physical_points if p.classification == SADDLE]
        stables = report.stable_points
        assert len(saddles) == 1 and len(stables) == 2

        # The saddle is on the diagonal.
        saddle = saddles[0]
        assert saddle.state["geneA_X"] == pytest.approx(saddle.state["geneB_X"], rel=1e-6)

        # And the two stable states are mirror images.
        low, high = sorted(stables, key=lambda p: p.state["geneA_X"])
        assert low.state["geneA_X"] == pytest.approx(high.state["geneB_X"], rel=1e-4)
        assert low.state["geneB_X"] == pytest.approx(high.state["geneA_X"], rel=1e-4)

        assert report.at_least_bistable
        assert "it switches" in report.summary()


class TestConservationLaws:
    def test_a_cascade_has_ONE_steady_state_not_nine(self) -> None:
        """The error this test exists to prevent, which shipped once.

        A three-tier cascade conserves total protein in each tier, so the
        state space is foliated and EVERY set of totals has its own steady
        state. An unconstrained multistart finds a different leaf from every
        start and reports them as separate attractors -- the first version
        of this analysis announced "at least 9 stable states were found, so
        this system switches" about a cascade, which does not switch.

        Constrained to the leaf of the declared initial condition, there is
        one.
        """
        report = analyse(recognise("three step phosphorylation cascade").network())
        assert len(report.physical_points) == 1
        assert not report.at_least_bistable
        assert "switches" not in report.summary()

    def test_the_state_found_lies_on_the_declared_leaf(self) -> None:
        # Total protein per tier is 1.0 in the declared initial condition,
        # and the steady state has to respect it.
        network = recognise("three step phosphorylation cascade").network()
        point = analyse(network).physical_points[0]
        for tier in ("tier1", "tier2", "tier3"):
            total = point.state[f"{tier}_X"] + point.state[f"{tier}_Xp"]
            assert total == pytest.approx(1.0, rel=1e-6), tier

    def test_a_different_leaf_gives_a_different_state(self) -> None:
        # The proof that the constraint is doing something: double the
        # protein and the steady state moves.
        recognition = recognise("three step phosphorylation cascade")
        composition = recognition.composition
        composition.set_initial("tier1_X", 2.0)
        moved = analyse(composition.to_network()).physical_points[0]
        assert moved.state["tier1_X"] + moved.state["tier1_Xp"] == pytest.approx(
            2.0, rel=1e-6
        )

    def test_structural_zeros_do_not_make_everything_marginal(self) -> None:
        # Each conservation law contributes a zero eigenvalue. Leaving them
        # in classifies every conserved system as `marginal`, which says
        # nothing about whether the state attracts ON its leaf.
        report = analyse(recognise("three step phosphorylation cascade").network())
        assert report.physical_points[0].classification != MARGINAL


class TestClassification:
    @pytest.mark.parametrize("eigenvalues,expected", [
        ((-1 + 0j, -2 + 0j), STABLE),
        ((1 + 0j, 2 + 0j), UNSTABLE),
        ((-1 + 0j, 2 + 0j), SADDLE),
        ((-1 + 3j, -1 - 3j), OSCILLATORY_STABLE),
        ((1 + 3j, 1 - 3j), OSCILLATORY_UNSTABLE),
    ])
    def test_it_names_the_shape_from_the_eigenvalues(self, eigenvalues, expected) -> None:
        assert classify(eigenvalues) == expected

    def test_a_marginal_eigenvalue_is_reported_as_marginal(self) -> None:
        # At a bifurcation the linearisation decides nothing, and rounding a
        # near-zero eigenvalue to one side reports a system as a switch when
        # it is sitting exactly on the boundary of being one.
        assert classify((0 + 0j, 1 + 0j, -1 + 0j)) == MARGINAL

    def test_an_empty_spectrum_is_marginal_not_stable(self) -> None:
        # The safe direction: nothing is known, so nothing is claimed.
        assert classify(()) == MARGINAL


class TestTheCaretBug:
    def test_a_power_in_a_rate_law_is_exponentiation_not_xor(self) -> None:
        """A silent wrong answer of exactly the shape this project refuses.

        Antimony and SBML write exponentiation as `^`. Python reads `^` as
        bitwise XOR, and `2^3` is 1, not 8 -- it does not error, it returns
        a different number. A Hill term evaluated without translating the
        operator computes something unrelated and integrates perfectly well.
        """
        from Terium.core.network import Parameter, Reaction, ReactionNetwork, Species

        network = ReactionNetwork(
            name="power",
            species=(Species("X", 2.0),),
            parameters=(Parameter("n", 3.0),),
            reactions=(
                Reaction(id="r", reactants={}, products={"X": 1}, rate_law="X^n"),
            ),
        )
        rhs, _ = derivative_function(network)
        # 2**3 = 8. The XOR reading of 2^3 is 1.
        assert rhs([2.0]) == [pytest.approx(8.0)]


class TestWhatItRefusesToConclude:
    def test_bistability_is_reported_as_at_least_not_as_exactly(self) -> None:
        # A multistart search reports what it converged to. It cannot prove
        # there is no third state, nor that it did not miss a second one.
        report = analyse(recognise("a toggle switch between two repressors").network())
        assert hasattr(report, "at_least_bistable")
        assert not hasattr(report, "is_bistable")

    def test_finding_nothing_is_not_reported_as_proof_of_nothing(self) -> None:
        from Terium.compose.analysis import StabilityReport

        empty = StabilityReport(fixed_points=(), starts_tried=32, species=("X",))
        assert "not proof there is none" in empty.summary()

    def test_the_number_of_starts_is_reported(self) -> None:
        # "Found two states" means something different after 8 starts than
        # after 800.
        report = analyse(recognise("a toggle switch between two repressors").network())
        assert f"from {report.starts_tried} starting points" in report.summary()

    def test_it_says_the_results_are_numerical(self) -> None:
        # The conservation laws are derived exactly over Fraction; these are
        # what a solver converged to. Flattening that difference is the
        # thing this codebase spends its time undoing.
        report = analyse(recognise("a toggle switch between two repressors").network())
        assert "numerical results from a root find" in report.summary()
        assert "conservation laws this model reports ARE derived" in report.summary()

    def test_negative_states_are_kept_and_marked_not_hidden(self) -> None:
        """A negative fixed point is a real property of the equations.

        The first version of this looped over `fixed_points` and asserted
        only inside `if not point.physical`. On a model with no negative
        states the loop body never ran, so a mutation marking EVERY state
        physical survived the whole suite. Asserted directly instead.
        """
        from Terium.compose.analysis import FixedPoint, StabilityReport

        negative = FixedPoint(
            state={"X": -1.5}, residual=0.0, eigenvalues=(-1 + 0j,),
            classification=STABLE, physical=False,
        )
        positive = FixedPoint(
            state={"X": 2.0}, residual=0.0, eigenvalues=(-1 + 0j,),
            classification=STABLE, physical=True,
        )
        assert "NEGATIVE" in negative.describe()
        assert "NEGATIVE" not in positive.describe()

        report = StabilityReport(
            fixed_points=(negative, positive), starts_tried=8, species=("X",),
        )
        # Kept in `fixed_points`, excluded from `physical_points`, and the
        # summary says how many were set aside and why.
        assert len(report.fixed_points) == 2
        assert report.physical_points == (positive,)
        assert "at negative concentrations" in report.summary()
        assert not report.at_least_bistable

    def test_a_negative_root_is_FOUND_and_marked_by_analyse(self) -> None:
        """The derivation of `physical`, not just its reporting.

        The previous test constructs FixedPoint objects with physical=False
        by hand, so it exercises the report and never the line in `analyse`
        that computes the flag -- and a mutation setting every state
        physical survived it. None of the library's models have a negative
        fixed point, so this builds one that does.

        dX/dt = -k(X+0.5)(X-2) has roots at X = -0.5 and X = 2. The first
        is a real property of the equations and the system cannot reach it.

        The negative root is -0.5 and not -1 on purpose. At -1 exactly, a
        mutation loosening the tolerance to `value > -1.0` still rejects it
        -- the boundary coincides -- and the mutation survived. A root
        strictly inside a plausible wrong threshold is what makes the
        threshold testable.
        """
        from Terium.core.network import Parameter, Reaction, ReactionNetwork, Species

        network = ReactionNetwork(
            name="two_roots",
            species=(Species("X", 1.0),),
            parameters=(Parameter("k", 1.0),),
            reactions=(
                Reaction(id="r", reactants={"X": 1}, products={},
                         rate_law="k * (X + 0.5) * (X - 2)"),
            ),
        )
        report = analyse(network)
        values = sorted(round(p.state["X"], 6) for p in report.fixed_points)
        assert values == [-0.5, 2.0], values

        negative = next(p for p in report.fixed_points if p.state["X"] < 0)
        positive = next(p for p in report.fixed_points if p.state["X"] > 0)
        assert negative.physical is False
        assert positive.physical is True
        assert report.physical_points == (positive,)
        assert "NEGATIVE" in negative.describe()

    def test_a_species_at_exactly_zero_is_still_physical(self) -> None:
        """Why the physicality test carries a tolerance rather than `> 0`.

        Autocatalysis runs to completion: S + X -> 2X ends with every
        substrate converted, and the solver reports that state as
        `S = -0.0`. Negative zero. Under a strict `value > 0` test it is
        marked unphysical and filtered out of the report -- and the state
        removed is the actual end state of the reaction, the one thing
        anybody running this model wants to see.

        A tolerance is not laxness here. It is the difference between
        "slightly negative because the equations have a root there" and
        "zero, arrived at from the other side by floating-point
        arithmetic".
        """
        from Terium.compose.builder import Composition
        from Terium.compose.library import AUTOCATALYSIS

        composition = Composition("autocatalytic")
        composition.add(AUTOCATALYSIS, "r")
        report = analyse(composition.to_network())

        converted = next(
            p for p in report.fixed_points if p.state["r_X"] > 1.0
        )
        assert converted.state["r_S"] == pytest.approx(0.0, abs=1e-9)
        assert math.copysign(1.0, converted.state["r_S"]) == -1.0, (
            "this test is only meaningful while the solver returns negative "
            "zero here; if it stops doing so, the case it guards is gone"
        )
        assert converted.physical, "the completed reaction was filtered out"
        assert converted in report.physical_points
        assert converted.stable

    def test_a_system_with_no_steady_state_reports_none(self) -> None:
        """The residual filter, which a mutation removing it survived.

        `least_squares` always returns SOMETHING -- the point minimising the
        residual norm. For a system with no steady state that point is not a
        root, and reporting it as one would invent a fixed point for a model
        that has none. Constant inflow with no removal is exactly that: the
        species rises forever.
        """
        from Terium.compose.library import CONSTANT_INFLOW

        composition = Composition("unbounded")
        composition.add(CONSTANT_INFLOW, "feed")
        report = analyse(composition.to_network())

        assert report.fixed_points == ()
        assert "No steady state was found" in report.summary()
        assert "not proof there is none" in report.summary()


class TestDeterminism:
    def test_two_runs_agree(self) -> None:
        # A stability analysis that changed between runs would be
        # unciteable. The starting points come from a local generator
        # seeded here, not from global interpreter state.
        network = recognise("a toggle switch between two repressors").network()
        first = analyse(network)
        second = analyse(network)
        assert [sorted(p.state.items()) for p in first.fixed_points] == [
            sorted(p.state.items()) for p in second.fixed_points
        ]

    def test_a_different_seed_may_search_differently(self) -> None:
        # The seed is a real knob, not decoration: it must change where the
        # search looks.
        network = recognise("a toggle switch between two repressors").network()
        assert analyse(network, seed=1).starts_tried == analyse(network, seed=2).starts_tried


class TestExplicitStartingPoints:
    """Handing the search a place to start, for continuation.

    A caller walking a parameter a fraction of a percent at a time already
    knows where the fixed point sits. Making the search rediscover it from
    scratch is not only slow -- a global multistart makes no promise to
    return the same branch twice, so the difference between two such answers
    is not a derivative of anything. See `compose/sensitivity.py`.
    """

    def test_an_explicit_start_is_tried_first(self) -> None:
        network = recognise("a toggle switch between two repressors").network()
        full = analyse(network)
        assert len(full.stable_points) == 2, "the premise of this test"

        # Continue from ONE of them, with no global search at all.
        anchor = [full.stable_points[0].state[s.id] for s in network.species]
        local = analyse(network, starts_per_species=0, extra_starts=[anchor])
        assert len(local.fixed_points) == 1
        for name, value in full.stable_points[0].state.items():
            assert local.fixed_points[0].state[name] == pytest.approx(value, abs=1e-9)

    def test_a_local_solve_does_not_wander_to_the_other_branch(self) -> None:
        # The whole point. A global search returns both states and no
        # guarantee about order; a continuation must stay where it was put.
        network = recognise("a toggle switch between two repressors").network()
        full = analyse(network)
        for point in full.stable_points:
            anchor = [point.state[s.id] for s in network.species]
            local = analyse(network, starts_per_species=0, extra_starts=[anchor])
            assert len(local.fixed_points) == 1
            for name, value in point.state.items():
                assert local.fixed_points[0].state[name] == pytest.approx(
                    value, abs=1e-9
                )

    def test_a_start_of_the_wrong_length_is_refused(self) -> None:
        # Padding or truncating would produce a converged answer to a
        # question nobody asked.
        from Terium.compose.analysis import AnalysisError

        network = recognise("a toggle switch between two repressors").network()
        with pytest.raises(AnalysisError, match="coordinates"):
            analyse(network, extra_starts=[[1.0]])

    def test_searching_nowhere_is_refused_rather_than_reported_as_empty(self) -> None:
        """The check that stops a silent lie.

        Zero starts with no explicit ones would find no steady states and
        report exactly what a model with none reports. Those are different
        facts and must not share a rendering.
        """
        from Terium.compose.analysis import AnalysisError

        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        with pytest.raises(AnalysisError, match="would look nowhere"):
            analyse(composition.to_network(), starts_per_species=0)

    def test_zero_starts_per_species_generates_none(self) -> None:
        from Terium.compose.analysis import _starting_points

        assert _starting_points(3, [1.0, 1.0, 1.0], 0, 64, 0) == []
        # ...but asking for a search always gets one, floor of four.
        assert len(_starting_points(1, [1.0], 1, 64, 0)) == 4


class TestTheSearchLooksWhereTheModelLives:
    """The multistart was anchored at order 1 for every model.

    `scale` was `max(abs(s.initial), 1.0)` per species. The floor is the
    whole bug: for any model whose concentrations sit below one in its own
    unit, the search looked at order 1 and the fixed points were orders of
    magnitude below that.

    A toggle switch at realistic transcription-factor concentrations --
    around a micromolar, which in the library's mM is 1e-3 -- returned ONE
    fixed point and NO stable states. The same model at the library's
    default values returns three points and two stable ones, and the
    mathematics is identical: scaling every synthesis rate and affinity by
    one factor scales the steady states by that factor and changes nothing
    else. Only the search moved.

    That is the concentration range real regulatory biology occupies, and
    the failure was silent -- a confident "no steady state was found",
    not a refusal.
    """

    @staticmethod
    def _scaled_toggle(factor):
        """The toggle switch with every concentration scaled by `factor`.

        ks and K are the two concentration-carrying constants; scaling both
        with the species initials leaves the dimensionless dynamics exactly
        invariant, so any change in the reported number of stable states is
        the SEARCH changing its answer, not the model.
        """
        from dataclasses import replace

        from Terium.compose.pipeline import compose

        model = compose("a toggle switch between two repressors")
        parameters = tuple(
            replace(p, value=p.value * factor)
            if (p.id.endswith("_ks") or p.id.endswith("_K")) else p
            for p in model.network.parameters
        )
        species = tuple(
            replace(s, initial=s.initial * factor)
            for s in model.network.species
        )
        return replace(model.network, parameters=parameters, species=species)

    @pytest.mark.parametrize("factor", [1.0, 1e-2, 1e-4, 1e-6])
    def test_bistability_survives_a_change_of_scale(self, factor) -> None:
        report = analyse(self._scaled_toggle(factor))
        stable = [p for p in report.fixed_points if p.stable]
        assert len(stable) == 2, (
            factor,
            f"{len(report.fixed_points)} point(s), {len(stable)} stable -- "
            f"the same model at a different concentration scale",
        )

    def test_the_states_scale_with_the_model(self) -> None:
        """Not just the COUNT: the values track the scaling exactly.

        A search that found two stable states at the wrong magnitudes
        would pass the count test above and still be wrong.
        """
        reference = sorted(
            max(p.state.values())
            for p in analyse(self._scaled_toggle(1.0)).fixed_points
            if p.stable
        )
        scaled = sorted(
            max(p.state.values())
            for p in analyse(self._scaled_toggle(1e-4)).fixed_points
            if p.stable
        )
        assert len(reference) == len(scaled) == 2
        for one, other in zip(reference, scaled):
            assert other == pytest.approx(one * 1e-4, rel=1e-3)

    def test_the_scale_comes_from_a_declared_concentration(self) -> None:
        # The mechanism, directly: a species with no initial takes its
        # scale from the model's concentration-valued parameters.
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="tiny",
            species=(Species("X", 0.0),),
            parameters=(
                Parameter("Km", 2e-5, "mM"),
                Parameter("k", 3.0, "1/s"),
            ),
            reactions=(Reaction("r", {}, {"X": 1}, "k"),),
        )
        assert _search_scale(network) == [2e-5]

    def test_a_species_with_an_initial_keeps_it(self) -> None:
        # The user's own statement about the size of the thing wins over
        # anything inferred from the parameters.
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="tiny",
            species=(Species("X", 7.0),),
            parameters=(Parameter("Km", 2e-5, "mM"),),
            reactions=(Reaction("r", {}, {"X": 1}, "Km"),),
        )
        assert _search_scale(network) == [7.0]

    def test_the_largest_declared_concentration_wins(self) -> None:
        """Not the smallest, and the asymmetry is deliberate.

        A steady state can sit well above the affinity that shapes it -- a
        pool of 10 uM regulated by a 10 nM binding constant is ordinary --
        so anchoring the search at the smallest constant would put it three
        decades below where the answer is. Overshooting costs less than
        undershooting, because starts are spread over decades around this
        anyway and the failure this whole class exists for was an
        undershoot.

        A mutation from max to min passed every other test here, because
        every model used above has one distinct concentration value.
        """
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="tiny",
            species=(Species("X", 0.0),),
            parameters=(
                Parameter("Kd", 1e-5, "mM"),
                Parameter("pool", 1e-2, "mM"),
                Parameter("k", 3.0, "1/s"),
            ),
            reactions=(Reaction("r", {}, {"X": 1}, "k"),),
        )
        assert _search_scale(network) == [1e-2], (
            "the search anchored on the smallest concentration, three "
            "decades below the pool it should be looking at"
        )

    def test_units_are_compared_in_one_scale_not_mixed(self) -> None:
        """A bare `max` over mixed units would pick the biggest NUMBER.

        1 nM and 0.5 M are not comparable as floats -- 1 beats 0.5 and is
        a billion times smaller. Recorded here as a known limitation
        rather than left to be discovered: the library writes every
        concentration in mM, so mixing does not arise in a composed model,
        and a network built by hand with mixed units gets a scale drawn
        from whichever number is largest.

        WHEN THIS STOPS BEING TRUE THIS TEST GOES RED. Convert through
        `scale._TO_MOLAR` before comparing, and delete it.
        """
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="mixed",
            species=(Species("X", 0.0),),
            parameters=(
                Parameter("big", 0.5, "M"),
                Parameter("small", 1.0, "nM"),
            ),
            reactions=(Reaction("r", {}, {"X": 1}, "big"),),
        )
        assert _search_scale(network) == [1.0], (
            "mixed units are now converted -- good; delete this test"
        )

    def test_a_rate_constant_is_not_read_as_a_concentration(self) -> None:
        """`1/s` must not set the search scale.

        A model with a fast rate constant and no stated concentration
        would otherwise be searched at the magnitude of a rate, which is
        a different quantity entirely and would be a unit confusion
        inside the module that finds the answers.
        """
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="tiny",
            species=(Species("X", 0.0),),
            parameters=(Parameter("k", 5000.0, "1/s"),),
            reactions=(Reaction("r", {}, {"X": 1}, "k"),),
        )
        assert _search_scale(network) == [1.0], (
            "a rate constant set the concentration scale"
        )

    def test_a_network_with_no_units_falls_back_to_one(self) -> None:
        # A network built outside the composer carries no units, and 1.0
        # is the honest answer when the model has stated nothing better.
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="tiny",
            species=(Species("X", 0.0),),
            parameters=(Parameter("k", 5.0),),
            reactions=(Reaction("r", {}, {"X": 1}, "k"),),
        )
        assert _search_scale(network) == [1.0]

    def test_the_concentration_units_have_not_drifted(self) -> None:
        """Duplicated from scale.py, held together here.

        The root finder must not depend on the physical-bounds module to
        decide where to look, so the unit list is copied. A copy nobody
        checks is a copy that diverges.
        """
        from Terium.compose.analysis import _CONCENTRATION_UNITS
        from Terium.compose.scale import _TO_MOLAR

        assert _CONCENTRATION_UNITS == frozenset(_TO_MOLAR)
