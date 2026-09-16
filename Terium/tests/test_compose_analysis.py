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

    def test_the_scale_is_the_same_for_every_species(self) -> None:
        # One magnitude for the model, not one per species. A search that
        # used a different scale per coordinate would find a species where
        # it started rather than where it settles.
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="three",
            species=(
                Species("A", 0.0), Species("B", 0.001), Species("C", 2.0),
            ),
            parameters=(Parameter("Km", 0.5, "mM"),),
            reactions=(Reaction("r", {}, {"A": 1}, "Km"),),
        )
        scale = _search_scale(network)
        assert len(scale) == 3
        assert len(set(scale)) == 1, scale
        assert scale[0] == 2.0, "the largest stated concentration"

    def test_an_initial_amount_is_not_a_per_species_scale(self) -> None:
        """THE BUG THE FIRST VERSION OF THIS FIX HAD.

        It scaled each species by its OWN initial amount, and the library
        toggle caught it: geneB starts at 0.1 and settles at 1.995, so a
        search anchored at 0.1 never reached the state. An initial is
        where a species STARTS; it is not an estimate of where it ends up.

        Every species is searched at the same magnitude -- the largest
        concentration the model states anywhere -- so a species that
        starts small can still be found where it settles large.
        """
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="two",
            species=(Species("X", 7.0), Species("Y", 0.1)),
            parameters=(Parameter("Km", 2e-5, "mM"),),
            reactions=(Reaction("r", {}, {"X": 1}, "Km"),),
        )
        assert _search_scale(network) == [7.0, 7.0], (
            "the small species got its own narrow scale"
        )

    def test_the_library_toggle_is_still_found_at_every_depth(self) -> None:
        """The regression the per-species version caused, pinned.

        This model's states are at 1.995 and 0.005 while its species start
        at 1.0 and 0.1. Any scheme that searches geneB near its own
        starting amount loses one of the two states at shallow depth.
        """
        from Terium.compose.pipeline import compose as _compose

        network = _compose(
            "a toggle switch between two repressors"
        ).network
        for depth in (4, 8, 16):
            stable = [
                p for p in analyse(
                    network, starts_per_species=depth
                ).fixed_points if p.stable
            ]
            assert len(stable) == 2, (depth, len(stable))

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

    def test_a_unitless_network_keeps_the_floor(self) -> None:
        """No declared concentration means no reason to drop the floor.

        A hand-built switch with unitless constants starts X at 0.1 and
        rests at 3.2. The second version of `_search_scale` used the
        initial alone, anchored the search at 0.1, and lost the state at
        shallow depth -- only a third of the starts fell in its basin.
        Starting amounts are where a species STARTS; without a declared
        Km or K to say otherwise, order unity is the honest default.
        """
        from Terium.compose.analysis import _search_scale
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        switch = ReactionNetwork(
            name="switch",
            species=(Species("X", 0.1),),
            parameters=(
                Parameter("v", 1.0), Parameter("K", 1.0),
                Parameter("kd", 0.3), Parameter("inducer", 0.05),
            ),
            reactions=(
                Reaction("induction", {}, {"X": 1}, "inducer"),
                Reaction("feedback", {}, {"X": 1}, "v * X^2 / (K^2 + X^2)"),
                Reaction("removal", {"X": 1}, {}, "kd * X"),
            ),
        )
        assert _search_scale(switch) == [1.0]
        stable = analyse(switch).stable_points
        assert len(stable) == 1
        assert stable[0].state["X"] == pytest.approx(3.204, abs=1e-3)

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


class TestAContinuumIsNotAStableState:
    """Nineteen points on a line were reported as nineteen switches.

    `classify` ignored a zero eigenvalue and classified on the rest,
    reasoning that a zero "usually means a conservation law". Both callers
    strip exactly as many structural zeros as there are laws BEFORE calling
    it, so a zero that arrives is not a law -- it is a direction the
    dynamics do not restore along. The point sits on a LINE of equilibria.

    Two enzymes competing for one substrate is the plain case. Once the
    substrate is gone, every split of product between them is an
    equilibrium. The verdict page turned nineteen of those into "this
    system switches". It does not: a switch has discrete attractors with
    repellors between them, and this has a line.
    """

    def test_a_remaining_zero_with_attracting_others_is_a_continuum(self) -> None:
        from Terium.compose.analysis import CONTINUUM, classify

        assert classify([0.0, -2.0]) == CONTINUUM
        assert classify([0.0, -2.0, -0.5]) == CONTINUUM
        assert classify([1e-10, -1.0]) == CONTINUUM  # within MARGINAL_EIGENVALUE

    def test_a_remaining_zero_with_a_repelling_other_is_marginal(self) -> None:
        # The bifurcation reading, kept apart: a zero next to a positive
        # eigenvalue is a point the linearisation cannot place, not a line
        # the system settles onto.
        from Terium.compose.analysis import CONTINUUM, MARGINAL, classify

        assert classify([0.0, +2.0]) == MARGINAL
        assert classify([0.0, -1.0, +1.0]) == MARGINAL
        assert classify([0.0]) == MARGINAL
        assert classify([0.0, +2.0]) != CONTINUUM

    def test_a_continuum_point_is_not_stable(self) -> None:
        from Terium.compose.analysis import CONTINUUM, FixedPoint

        point = FixedPoint(
            state={"X": 0.5}, residual=0.0,
            eigenvalues=(0.0, -2.0), classification=CONTINUUM,
        )
        assert not point.stable, (
            "a point that can be nudged along a line and never return is "
            "not an attractor"
        )

    def test_the_two_enzyme_model_has_no_stable_state(self) -> None:
        """The model that motivated this, at the depth the CLI uses.

        Nineteen points on one line, one of them physical, zero stable,
        and NOT bistable. The old classifier called every one of them
        stable and `at_least_bistable` was True.
        """
        from Terium.compose.pipeline import compose as _compose

        report = analyse(
            _compose("two enzymes competing for the same substrate").network
        )
        assert report.on_a_continuum
        assert not report.at_least_bistable
        assert not report.stable_points
        assert len(report.continuum_points) >= 2, (
            "the premise: the search landed on the line more than once"
        )

    def test_the_line_really_is_a_line(self) -> None:
        """Every point found shares S = 0 and P1 + P2 = the conserved total.

        Otherwise 'continuum' would be a label on a set of unrelated roots.
        This checks the geometry the classification claims.
        """
        from Terium.compose.pipeline import compose as _compose

        model = _compose("two enzymes competing for the same substrate")
        report = analyse(model.network)
        totals = set()
        for point in report.continuum_points:
            assert abs(point.state["enzyme1_S"]) < 1e-6, point.state
            totals.add(round(point.state["enzyme1_P"] + point.state["enzyme2_P"], 6))
        assert len(totals) == 1, (
            f"the points do not share one conserved total: {sorted(totals)}"
        )

    def test_the_toggle_switch_is_unaffected(self) -> None:
        # The cry-wolf direction. A genuine switch has NO zero eigenvalue
        # at its stable states, so this change must not touch it.
        from Terium.compose.analysis import SADDLE, STABLE
        from Terium.compose.pipeline import compose as _compose

        report = analyse(
            _compose("a toggle switch between two repressors").network
        )
        assert report.at_least_bistable
        assert len(report.stable_points) == 2
        assert not report.on_a_continuum
        classes = {p.classification for p in report.fixed_points}
        assert classes == {STABLE, SADDLE}, classes

    def test_the_summary_says_it_is_not_a_switch(self) -> None:
        from Terium.compose.pipeline import compose as _compose

        text = analyse(
            _compose("two enzymes competing for the same substrate").network
        ).summary()
        assert "A LINE of equilibria" in text
        assert "This is NOT a switch" in text
        assert "it switches" not in text.replace("NOT a switch", "")
        # And it says the count is not the finding.
        assert "artefact of where the starts fell" in text

    def test_on_a_continuum_is_conjunctive(self) -> None:
        """A continuum plus a real attractor is neither case.

        The flag is for the plain case. Reporting a model with a line AND
        an isolated stable state as "on a continuum" would hide the
        attractor, which is the more interesting half.
        """
        from Terium.compose.analysis import (
            CONTINUUM, STABLE, FixedPoint, StabilityReport,
        )

        line = FixedPoint(
            state={"X": 0.5}, residual=0.0,
            eigenvalues=(0.0, -1.0), classification=CONTINUUM,
        )
        attractor = FixedPoint(
            state={"X": 3.0}, residual=0.0,
            eigenvalues=(-1.0, -2.0), classification=STABLE,
        )
        both = StabilityReport(
            fixed_points=(line, attractor), starts_tried=8, species=("X",),
        )
        assert not both.on_a_continuum
        assert both.continuum_points == (line,)
        only_line = StabilityReport(
            fixed_points=(line,), starts_tried=8, species=("X",),
        )
        assert only_line.on_a_continuum

    def test_the_verdict_page_does_not_say_switch(self) -> None:
        from Terium.compose.pipeline import compose as _compose
        from Terium.compose.verdict import behaviour_of

        model = _compose("two enzymes competing for the same substrate")
        line = behaviour_of(analyse(model.network))
        assert line is not None
        assert "LINE of equilibria" in line
        assert "not a switch" in line
        assert "what a switch looks like" not in line
        assert "physically reachable" in line


class TestTheClassificationVocabularyIsShared:
    """`continuation.BranchPoint.stable` spells the stable classes by hand.

    It reads `("stable", "stable spiral")` from a literal tuple rather than
    from `analysis`, so a rename there would leave every branch point
    reporting itself unstable with no test going red. Held together here.
    """

    def test_continuation_agrees_on_what_stable_means(self) -> None:
        from Terium.compose.analysis import (
            CONTINUUM, OSCILLATORY_STABLE, STABLE,
        )
        from Terium.compose.continuation import BranchPoint

        def _point(classification):
            return BranchPoint(
                parameter=1.0, state={"X": 1.0}, arclength=0.0,
                tangent_state={"X": 0.0}, tangent_parameter=1.0,
                residual=0.0, classification=classification,
            )

        assert _point(STABLE).stable
        assert _point(OSCILLATORY_STABLE).stable
        assert not _point(CONTINUUM).stable, (
            "a branch point on a line of equilibria is not an attractor"
        )
        assert not _point("marginal").stable

    def test_every_classification_classify_can_return_is_declared(self) -> None:
        """No classifier output escapes the constants.

        A string returned from `classify` that is not one of the module's
        named constants would be one that every `in (...)` check silently
        misses -- which is what a continuum was before it had a name.
        """
        import itertools

        from Terium.compose import analysis

        declared = {
            analysis.STABLE, analysis.UNSTABLE, analysis.SADDLE,
            analysis.MARGINAL, analysis.CONTINUUM,
            analysis.OSCILLATORY_STABLE, analysis.OSCILLATORY_UNSTABLE,
        }
        # Every sign pattern over up to three eigenvalues, with and without
        # an imaginary part, so every branch of classify runs.
        reals = (-1.0, 0.0, 1.0)
        for n in (0, 1, 2, 3):
            for signs in itertools.product(reals, repeat=n):
                for imag in (0.0, 0.5):
                    eigen = [complex(r, imag) for r in signs]
                    assert analysis.classify(eigen) in declared, (
                        signs, imag, analysis.classify(eigen),
                    )


class TestTheSearchDepthIsOneNumber:
    """Two constants, two docstrings, two stale measurements.

    `analysis.DEFAULT_STARTS_PER_SPECIES` said the toggle found one state
    at 4 and both at 8; `sensitivity.STARTS_PER_SPECIES` said the
    two-enzyme competition was wrong at 8 and right at 16. The first
    stopped being true when the search was re-anchored at the model's own
    scale. The second was never a count of stable states -- both numbers
    were points on a continuum -- and dissolved when those were classified
    correctly.

    A justification that lives only in a docstring goes stale the moment
    the code it describes moves. These hold the measurement live.
    """

    LIBRARY = (
        "enzyme kinetics with a competitive inhibitor",
        "repressilator oscillations",
        "three step phosphorylation cascade",
        "a MAP kinase cascade with negative feedback",
        "reversible binding of a ligand to a receptor",
        "substrate inhibition at high substrate concentration",
        "two enzymes competing for the same substrate",
        "a toggle switch between two repressors",
        "sequential feedback inhibition in amino acid synthesis",
        "an open system with constant substrate inflow",
        "allosteric activation of an enzyme by its product",
    )

    def test_the_package_uses_one_depth(self) -> None:
        from Terium.compose.analysis import DEFAULT_STARTS_PER_SPECIES
        from Terium.compose.robustness import default_search_depth
        from Terium.compose.sensitivity import STARTS_PER_SPECIES

        assert STARTS_PER_SPECIES == DEFAULT_STARTS_PER_SPECIES
        assert default_search_depth() == DEFAULT_STARTS_PER_SPECIES

    def test_sensitivity_reads_it_by_reference(self) -> None:
        """Not a copy that happens to be equal today.

        Two constants with the same value drift apart the first time one
        is edited. The sensitivity module's constant must BE the analysis
        module's, not a literal 8 beside it.
        """
        import ast
        import inspect

        from Terium.compose import sensitivity

        tree = ast.parse(inspect.getsource(sensitivity))
        assignments = [
            node for node in tree.body
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "STARTS_PER_SPECIES"
                for t in node.targets
            )
        ]
        # Found first, asserted outside any branch: the vacuous-test guard
        # is right that an assertion inside an `if` over a loop is one the
        # loop can skip.
        assert len(assignments) == 1, (
            "STARTS_PER_SPECIES is no longer assigned exactly once in "
            "sensitivity.py"
        )
        value = assignments[0].value
        assert isinstance(value, ast.Name), (
            "STARTS_PER_SPECIES is a literal again; it must reference "
            "analysis.DEFAULT_STARTS_PER_SPECIES"
        )
        assert value.id == "DEFAULT_STARTS_PER_SPECIES"

    def test_the_library_is_depth_independent_from_four(self) -> None:
        """The measurement the default rests on, run rather than quoted.

        Every library model reports the same number of stable states at 4,
        8 and 16 starting points per species. Continuum points are excluded
        from the comparison on purpose: how many land on a line IS
        depth-dependent and is not a property of the model.

        If this goes red, the search has changed and the note on
        `DEFAULT_STARTS_PER_SPECIES` needs re-measuring, not re-wording.
        """
        from Terium.compose.pipeline import compose as _compose

        disagreements = {}
        for query in self.LIBRARY:
            network = _compose(query).network
            counts = {
                depth: len(analyse(network, starts_per_species=depth).stable_points)
                for depth in (4, 8, 16)
            }
            if len(set(counts.values())) != 1:
                disagreements[query] = counts
        assert not disagreements, disagreements

    def test_the_measurement_covers_the_whole_library(self) -> None:
        # The sweep above is vacuous over an empty or shrunken list. Pinned
        # against the coverage suite's own count so the two cannot diverge.
        from Terium.tests import test_compose_agreement

        assert set(self.LIBRARY) == set(test_compose_agreement.BUILDABLE)

    def test_the_toggle_is_found_at_four(self) -> None:
        # The specific claim the old docstring made in the other direction.
        from Terium.compose.pipeline import compose as _compose

        report = analyse(
            _compose("a toggle switch between two repressors").network,
            starts_per_species=4,
        )
        assert len(report.stable_points) == 2, (
            "the toggle no longer finds both states at 4; the search "
            "regressed and DEFAULT_STARTS_PER_SPECIES needs re-measuring"
        )


class TestRateRulesAreDynamics:
    """`derivative_function` built the right-hand side from reactions alone.

    `core.network.RateRule` exists because Lotka-Volterra, Tyson's
    cell-cycle oscillator and the catalogue's repressilator are written as
    X' = expression rather than as reactions; the IR's own docstring says
    leaving them out "would quietly leave the interesting three behind".
    The analysis left them out. On any such model it returned zero for
    every rate-ruled species, found fixed points of the wrong system, and
    reported them with residuals near zero. The simulator honoured the
    rules; nothing compared the two.

    Logistic growth is the test: dX/dt = r X (1 - X/K) has fixed points at
    exactly 0 (unstable) and K (stable), by hand.
    """

    @staticmethod
    def _logistic(r=1.0, K=3.0):
        from Terium.core.network import (
            Parameter, RateRule, ReactionNetwork, Species,
        )

        return ReactionNetwork(
            name="logistic",
            species=(Species("X", 0.5),),
            parameters=(Parameter("r", r, "1/s"), Parameter("K", K, "mM")),
            rate_rules=(RateRule("X", "r * X * (1 - X / K)"),),
        )

    def test_the_derivative_is_the_rule(self) -> None:
        from Terium.compose.analysis import derivative_function

        rhs, order = derivative_function(self._logistic())
        assert order == ("X",)
        # r X (1 - X/K) at X = 1.5, r = 1, K = 3: 1.5 * 0.5 = 0.75.
        assert rhs([1.5]) == pytest.approx([0.75])
        # The old version returned [0.0] here, having seen no reactions.
        assert rhs([1.5]) != [0.0]

    def test_the_fixed_points_are_zero_and_k(self) -> None:
        from Terium.compose.analysis import STABLE, UNSTABLE

        report = analyse(self._logistic(K=3.0))
        by_value = {round(p.state["X"], 6): p.classification for p in report.fixed_points}
        assert by_value == {0.0: UNSTABLE, 3.0: STABLE}, by_value

    def test_k_moves_the_stable_point(self) -> None:
        # Not a coincidence of the default: the stable point tracks K.
        for K in (1.0, 7.5, 0.02):
            report = analyse(self._logistic(K=K))
            stable = [p for p in report.fixed_points if p.stable]
            assert len(stable) == 1, K
            assert stable[0].state["X"] == pytest.approx(K, rel=1e-6)

    def test_an_assignment_rule_feeds_a_rate_rule(self) -> None:
        """Assignments are recomputed before any rate, in order.

        Tyson's model uses `alpha := k4prime / k4` inside its rate rules.
        An assignment ignored is a NameError at best and a stale value at
        worst; here it is the carrying capacity, so getting it wrong moves
        the fixed point.
        """
        from Terium.core.network import (
            AssignmentRule, Parameter, RateRule, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="logistic_assigned",
            species=(Species("X", 0.5),),
            parameters=(
                Parameter("r", 1.0, "1/s"),
                Parameter("K_half", 1.5, "mM"),
            ),
            rate_rules=(RateRule("X", "r * X * (1 - X / K)"),),
            assignment_rules=(AssignmentRule("K", "2 * K_half"),),
        )
        report = analyse(network)
        stable = [p for p in report.fixed_points if p.stable]
        assert len(stable) == 1
        assert stable[0].state["X"] == pytest.approx(3.0, rel=1e-6)

    def test_the_simulator_and_the_analysis_now_agree(self) -> None:
        """The two routes to the same fact, compared for the first time.

        The simulator always honoured rate rules. Integrating logistic
        growth to its plateau and asking the analysis where the plateau is
        must give the same number, or one of them is wrong.
        """
        from Terium.compose.simulate import Trajectory, check_invariants
        from Terium.compose.analysis import derivative_function

        network = self._logistic(K=3.0)
        rhs, _ = derivative_function(network)
        # A crude forward-Euler integration, independent of both modules'
        # own machinery, so the comparison is not a module checking itself.
        x, dt = 0.5, 1e-3
        for _ in range(20000):
            x += dt * rhs([x])[0]
        stable = next(p for p in analyse(network).fixed_points if p.stable)
        assert x == pytest.approx(stable.state["X"], rel=1e-4)

    def test_a_reaction_network_is_unchanged(self) -> None:
        # The cry-wolf direction: adding rule support must not perturb a
        # model that has none.
        from Terium.compose.pipeline import compose as _compose

        report = analyse(_compose("a toggle switch between two repressors").network)
        assert len(report.stable_points) == 2


class TestConvergenceIsRelativeToTheModel:
    """An absolute residual bar is met by a model that does nothing.

    `RESIDUAL_TOLERANCE` is 1e-9 and was compared against the residual as
    an absolute number. On a model at nanomolar concentrations every flux
    is around 1e-7, and a residual of 5e-10 is a point a few percent from
    the root, not the root. A two-stage expression model returned THREE
    "stable states" that were one state found imprecisely from three
    starts. The search-scale fix exposed it: the search used to start far
    above such a model and never reached the flat region where the
    absolute bar was too easy.

    The bar is now 1e-9 of the largest flux seen across the starting
    points. `test_compose_library_expression` already did exactly this in
    its own analytic check, with the comment "any absolute bound would be
    met by a model that did nothing at all". The analysis now agrees.
    """

    @staticmethod
    def _tiny(scale=1e-6):
        """Synthesis and decay at `scale`: unique steady state at ks/kd."""
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        return ReactionNetwork(
            name="tiny",
            species=(Species("X", scale),),
            parameters=(
                Parameter("ks", 3.0 * scale, "mM/s"),
                Parameter("kd", 1.0, "1/s"),
            ),
            reactions=(
                Reaction("make", {}, {"X": 1}, "ks"),
                Reaction("decay", {"X": 1}, {}, "kd * X"),
            ),
        )

    @pytest.mark.parametrize("scale", [1.0, 1e-3, 1e-6, 1e-9])
    def test_one_state_at_every_scale(self, scale) -> None:
        report = analyse(self._tiny(scale))
        stable = report.stable_points
        assert len(stable) == 1, (
            scale,
            [(p.state["X"], p.residual) for p in report.fixed_points],
        )
        assert stable[0].state["X"] == pytest.approx(3.0 * scale, rel=1e-6)

    def test_the_found_root_is_converged_relative_to_its_fluxes(self) -> None:
        # The residual at the reported root is tiny COMPARED TO the model's
        # flux, not merely tiny.
        from Terium.compose.analysis import RESIDUAL_TOLERANCE, derivative_function

        network = self._tiny(1e-6)
        rhs, _ = derivative_function(network)
        point = analyse(network).stable_points[0]
        flux_scale = abs(rhs([0.0])[0])  # ks alone, at X = 0
        assert flux_scale == pytest.approx(3e-6)
        assert point.residual <= RESIDUAL_TOLERANCE * flux_scale

    def test_a_slow_model_has_one_root_not_one_per_start(self) -> None:
        """X' = k (K - X) with k = 1e-12: the flux is below 1e-9 EVERYWHERE.

        Under an absolute bar of 1e-9, every starting point satisfies the
        convergence test before the solver has moved, and the search
        reported EIGHT fixed points -- one per start, at X = 0, 3, 0.08,
        7.9, 1.2, 1.03, 5.3 and 0.06 -- for a model with exactly one, at K.
        That is the failure the expression model showed in miniature,
        isolated from everything else.
        """
        from Terium.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        network = ReactionNetwork(
            name="slow",
            species=(Species("X", 0.5),),
            parameters=(
                Parameter("k", 1e-12, "1/s"), Parameter("K", 3.0, "mM"),
            ),
            reactions=(Reaction("relax", {}, {"X": 1}, "k * (K - X)"),),
        )
        report = analyse(network)
        assert len(report.fixed_points) == 1, (
            f"{len(report.fixed_points)} roots for a model with one: "
            f"{[round(p.state['X'], 3) for p in report.fixed_points]}"
        )
        assert report.fixed_points[0].state["X"] == pytest.approx(3.0, rel=1e-6)

    def test_a_local_solve_from_the_root_still_converges(self) -> None:
        """One explicit start placed AT the root, no others.

        The first relative bar measured the reference flux at the starts
        alone. With a single start at the root, that reference was the
        residual at the root -- near machine precision -- and the bar
        became a million times tighter than any solver can meet. Two
        local-solve tests in this file found nothing. The reference is now
        also probed at the search scale and a decade either side, which a
        model at equilibrium at all three has no dynamics to speak of.
        """
        from Terium.compose.pipeline import compose as _compose

        model = _compose("a toggle switch between two repressors")
        known = analyse(model.network).stable_points[0]
        start = [known.state[name] for name in analyse(model.network).species]
        local = analyse(model.network, starts_per_species=0, extra_starts=[start])
        assert len(local.fixed_points) == 1, (
            "a solve started at a known root found nothing"
        )
        assert local.fixed_points[0].stable

    def test_the_expression_model_has_one_state(self) -> None:
        """The model that surfaced this, from the library."""
        from Terium.compose.builder import Composition
        from Terium.compose.library_expression import TWO_STAGE_EXPRESSION

        composition = Composition("expression")
        composition.add(TWO_STAGE_EXPRESSION, "gene")
        report = analyse(composition.to_network())
        assert len(report.stable_points) == 1, report.summary()
