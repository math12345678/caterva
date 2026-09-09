"""Structural results, checked against cases whose answers are already known.

Every other test file in `compose/` measures a model at particular values.
These pin claims that hold for EVERY positive rate constant, so they are
checked the way such claims should be: against textbook networks whose
complexes, linkage classes, rank and deficiency can be counted by hand, and
against closed-form steady states the theorem's conclusion must agree with.
The hand arithmetic is written out in comments so a reader can check the
counting without running anything.

The most important test here is `TestTheGuardIsLoadBearing`. The toggle
switch's reaction graph has deficiency zero and is weakly reversible, so
every STRUCTURAL hypothesis of the Deficiency Zero Theorem holds for it --
and the theorem's conclusion is that the system has exactly one steady state
and cannot switch. The toggle switch measurably has two. The only thing
standing between this module and that sentence is the mass-action check, and
that test is what keeps it standing.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from Terium.compose.analysis import derivative_function
from Terium.compose.builder import Composition
from Terium.compose.crnt import (
    Complex, KineticsNotMassAction, NotAReactionNetwork, classify_kinetics,
    complexes, deficiency, deficiency_one_verdict, deficiency_zero_verdict,
    describe, exact_rank, is_mass_action, is_weakly_reversible,
    linkage_class_deficiencies, linkage_classes, stoichiometric_rank,
    strong_linkage_classes, terminal_strong_linkage_classes,
)
from Terium.compose.library import (
    CATALYTIC_STEP, DIMERISATION, HILL_REPRESSION, PHOSPHORYLATION_CYCLE,
    REVERSIBLE_BINDING, SYNTHESIS_DEGRADATION,
)
from Terium.compose.pipeline import compose
from Terium.core.network import (
    AssignmentRule, Parameter, RateRule, Reaction, ReactionNetwork, Species,
)


def _settle(network, start, *, dt=0.01, tolerance=1e-10, limit=2_000_000):
    """Integrate to rest with forward Euler, and say where it stopped.

    WHY NOT `compose.analysis.analyse`. That is the repository's real
    steady-state search and it needs scipy. These cross-checks do not need a
    SEARCH: the algebra in each docstring already names the answer, and what
    is being confirmed is that this module's structural verdict and the
    repository's own equations are talking about the same model. Euler on a
    two- or three-species, well-scaled model is enough for that, and it keeps
    a structural test file free of a numerical dependency it does not need.

    Raises rather than returning wherever it got to. An assertion made about
    a state that is not a steady state would be an assertion about the step
    count.
    """
    rhs, order = derivative_function(network)
    state = [float(value) for value in start]
    for _ in range(limit):
        derivative = rhs(state)
        if max(abs(value) for value in derivative) < tolerance:
            return dict(zip(order, state))
        state = [x + dt * d for x, d in zip(state, derivative)]
    raise AssertionError(
        f"{network.name} did not settle from {list(start)} within {limit} "
        f"steps of {dt}; the test's premise is broken, not its conclusion"
    )


# -- textbook networks, built directly ---------------------------------------
#
# Built as `ReactionNetwork`s rather than through the motif library on
# purpose. These are the cases the theorems are stated on, and their whole
# value is that the complexes are exactly the textbook ones; a motif library
# would put prefixed species names and its own extra reactions between the
# reader and the arithmetic they are trying to check. The library motifs get
# their own class further down, where the point is different.


def _reversible_isomerisation() -> ReactionNetwork:
    """A <-> B.

    BY HAND. Complexes: {A} and {B}, so n = 2. One linkage class (the two
    reactions connect them), so l = 1. Reaction vectors, in species order
    (A, B): (-1, +1) and (+1, -1), which span a line, so s = 1.

        delta = n - l - s = 2 - 1 - 1 = 0

    Weakly reversible: A -> B -> A is a cycle, so the single linkage class is
    strongly connected.
    """
    return ReactionNetwork(
        name="reversible_isomerisation",
        species=(Species("A", 1.0), Species("B", 0.0)),
        parameters=(Parameter("k1", 1.0), Parameter("k2", 2.0)),
        reactions=(
            Reaction("forward", {"A": 1}, {"B": 1}, "k1 * A"),
            Reaction("backward", {"B": 1}, {"A": 1}, "k2 * B"),
        ),
    ).validate()


def _irreversible_isomerisation() -> ReactionNetwork:
    """A -> B.

    BY HAND. Same two complexes and the same single linkage class as above,
    n = 2 and l = 1. One reaction vector (-1, +1), so s = 1 and again

        delta = 2 - 1 - 1 = 0

    but the linkage class {A, B} is NOT strongly connected: nothing leads
    back from B. So this is the second half of the Deficiency Zero Theorem
    rather than the first, and the conclusion inverts.
    """
    return ReactionNetwork(
        name="irreversible_isomerisation",
        species=(Species("A", 1.0), Species("B", 0.0)),
        parameters=(Parameter("k1", 1.0),),
        reactions=(Reaction("forward", {"A": 1}, {"B": 1}, "k1 * A"),),
    ).validate()


def _autocatalytic_ladder() -> ReactionNetwork:
    """A <-> 2A <-> 3A, the deficiency-one case with a closed-form answer.

    BY HAND. Complexes: {A}, {2A}, {3A}, so n = 3. All connected, so l = 1.
    Every reaction vector is a multiple of (+1) in the single species A, so
    s = 1.

        delta = 3 - 1 - 1 = 1

    Weakly reversible, since every arrow has its reverse. The single linkage
    class therefore has delta_1 = 3 - 1 - 1 = 1, which is <= 1 and sums to
    the network's own delta, and the whole graph is one terminal strong
    linkage class. All three Deficiency One hypotheses hold.

    And the conclusion is checkable in closed form. With rate constants
    k1..k4 on the four reactions,

        dA/dt = k1*A - k2*A^2 + k3*A^2 - k4*A^3

    so a positive steady state satisfies k4*A^2 + (k2 - k3)*A - k1 = 0. The
    product of that quadratic's roots is -k1/k4, which is negative, so
    exactly one root is positive -- for every positive choice of the
    constants, which is what the theorem asserts. At k1=2, k2=3, k3=1, k4=1
    it is A^2 + 2A - 2 = 0, so A* = sqrt(3) - 1.
    """
    return ReactionNetwork(
        name="autocatalytic_ladder",
        species=(Species("A", 1.0),),
        parameters=(
            Parameter("k1", 2.0), Parameter("k2", 3.0),
            Parameter("k3", 1.0), Parameter("k4", 1.0),
        ),
        reactions=(
            Reaction("grow_one", {"A": 1}, {"A": 2}, "k1 * A"),
            Reaction("shrink_one", {"A": 2}, {"A": 1}, "k2 * A * A"),
            Reaction("grow_two", {"A": 2}, {"A": 3}, "k3 * A * A"),
            Reaction("shrink_two", {"A": 3}, {"A": 2}, "k4 * A * A * A"),
        ),
    ).validate()


def _split_linkage_classes() -> ReactionNetwork:
    """A <-> B together with 2A -> 2B.

    BY HAND. Complexes: {A}, {B}, {2A}, {2B}, so n = 4. Two linkage classes,
    {A, B} and {2A, 2B}, because no reaction connects a singleton complex to
    a doubled one; l = 2. Every reaction vector is a multiple of (-1, +1), so
    s = 1.

        delta = 4 - 2 - 1 = 1

    But each linkage class has deficiency zero on its own: {A, B} has
    2 - 1 - 1 = 0 and {2A, 2B} has 2 - 1 - 1 = 0. Their sum is 0, not 1, so
    the Deficiency One Theorem's third hypothesis fails while the other two
    hold -- which is the case the verdict has to name precisely rather than
    reporting a bare "does not apply".
    """
    return ReactionNetwork(
        name="split_linkage_classes",
        species=(Species("A", 1.0), Species("B", 0.0)),
        parameters=(
            Parameter("k1", 1.0), Parameter("k2", 1.0), Parameter("k3", 1.0),
        ),
        reactions=(
            Reaction("forward", {"A": 1}, {"B": 1}, "k1 * A"),
            Reaction("backward", {"B": 1}, {"A": 1}, "k2 * B"),
            Reaction("pair", {"A": 2}, {"B": 2}, "k3 * A * A"),
        ),
    ).validate()


def _branching_outflow() -> ReactionNetwork:
    """A -> B and A -> C: one linkage class with TWO terminal ends.

    BY HAND. Complexes {A}, {B}, {C}, so n = 3, all in one linkage class
    because both reactions leave A; l = 1. Reaction vectors in species order
    (A, B, C) are (-1, +1, 0) and (-1, 0, +1), which are independent, so
    s = 2 and delta = 3 - 1 - 2 = 0.

    Nothing leads out of {B} or out of {C}, so this single linkage class has
    two terminal strong linkage classes and the Deficiency One Theorem's
    FIRST hypothesis fails -- while its other two hold, since the one
    linkage class has deficiency 3 - 1 - 2 = 0 and that sums to the
    network's own zero.
    """
    return ReactionNetwork(
        name="branching_outflow",
        species=(Species("A", 1.0), Species("B", 0.0), Species("C", 0.0)),
        parameters=(Parameter("k1", 1.0), Parameter("k2", 1.0)),
        reactions=(
            Reaction("to_b", {"A": 1}, {"B": 1}, "k1 * A"),
            Reaction("to_c", {"A": 1}, {"C": 1}, "k2 * A"),
        ),
    ).validate()


def _single_motif(motif) -> ReactionNetwork:
    composition = Composition(motif.name)
    composition.add(motif, "m")
    return composition.to_network().validate()


class TestComplexesAreMultisets:
    """The canonicalisation everything else is counted from.

    n is a term in the deficiency. Count `A + B` and `B + A` as two nodes and
    a deficiency-zero network reads as deficiency-one, which silently
    withdraws a theorem; count `A` and `2A` as one and it reads the other
    way, which silently grants one.
    """

    def test_a_plus_b_and_b_plus_a_are_the_same_complex(self) -> None:
        # Written in opposite orders on the two sides on purpose.
        network = ReactionNetwork(
            name="ordering",
            species=(Species("A", 1.0), Species("B", 1.0), Species("C", 0.0)),
            parameters=(Parameter("k1", 1.0), Parameter("k2", 1.0)),
            reactions=(
                Reaction("bind", {"A": 1, "B": 1}, {"C": 1}, "k1 * A * B"),
                Reaction("unbind", {"C": 1}, {"B": 1, "A": 1}, "k2 * C"),
            ),
        ).validate()
        assert Complex.of({"A": 1, "B": 1}) == Complex.of({"B": 1, "A": 1})
        assert len(complexes(network)) == 2

    def test_two_a_is_not_the_same_complex_as_a(self) -> None:
        # Multiplicity is part of the identity: dimerisation and
        # isomerisation are different chemistry and different nodes.
        assert Complex.of({"A": 2}) != Complex.of({"A": 1})
        assert len(complexes(_split_linkage_classes())) == 4

    def test_the_zero_complex_is_a_node_and_not_a_missing_one(self) -> None:
        """`-> X` reacts the zero complex to X.

        This is why `synthesis_degradation` is weakly reversible at all: the
        degradation reaction leads back to the same node the synthesis
        reaction left. Treating an empty side as "no complex" would make the
        linkage class {X} alone and lose the cycle.
        """
        network = _single_motif(SYNTHESIS_DEGRADATION)
        nodes = complexes(network)
        assert Complex.of({}) in nodes
        assert str(Complex.of({})) == "0"
        assert len(nodes) == 2

    def test_a_complex_prints_its_multiplicities(self) -> None:
        assert str(Complex.of({"A": 2})) == "2 A"
        assert str(Complex.of({"B": 1, "A": 1})) == "A + B"

    def test_a_non_integer_multiplicity_is_refused(self) -> None:
        # A multiset has whole-number multiplicities. Rounding 1.5 to
        # something would invent a complex nobody wrote.
        with pytest.raises(NotAReactionNetwork, match="not an integer"):
            Complex.of({"A": 1.5})


class TestTheReversibleIsomerisation:
    """A <-> B: the smallest network the Deficiency Zero Theorem covers.

    See `_reversible_isomerisation` for the arithmetic done by hand.
    """

    def test_the_counts_are_the_ones_counted_by_hand(self) -> None:
        network = _reversible_isomerisation()
        assert len(complexes(network)) == 2
        assert len(linkage_classes(network)) == 1
        assert stoichiometric_rank(network) == 1
        assert deficiency(network) == 0

    def test_it_is_weakly_reversible(self) -> None:
        network = _reversible_isomerisation()
        assert is_weakly_reversible(network)
        # The whole linkage class is one strong linkage class, which is what
        # weak reversibility means.
        assert len(strong_linkage_classes(network)) == 1

    def test_the_theorem_applies_and_asserts_uniqueness_and_stability(self) -> None:
        verdict = deficiency_zero_verdict(_reversible_isomerisation())
        assert verdict.applies
        assert "exactly one steady state" in verdict.conclusion
        assert "asymptotically stable" in verdict.conclusion
        assert all(hypothesis.holds for hypothesis in verdict.hypotheses)

    def test_the_dynamics_agree_with_what_the_theorem_asserted(self) -> None:
        """The closed form the theorem's conclusion has to be consistent with.

        dA/dt = -k1*A + k2*B with A + B conserved at T. The steady state is
        A* = k2*T/(k1+k2), and the reduced equation on the leaf is
        dA/dt = k2*T - (k1+k2)*A, which is linear with a negative slope: one
        root, and every trajectory on the leaf runs to it. With k1 = 1,
        k2 = 2 and T = 1 that is A* = 2/3.

        Started from both ends of the leaf, because "one steady state and it
        attracts" is the theorem's claim and a single start would only show
        that the point exists.

        This does not prove the theorem. It checks that this module's verdict
        and this repository's equations are talking about the same model --
        the failure a structural claim is most exposed to, since nothing else
        about it can be observed.
        """
        network = _reversible_isomerisation()
        from_a = _settle(network, [1.0, 0.0])
        from_b = _settle(network, [0.0, 1.0])
        assert from_a["A"] == pytest.approx(2.0 / 3.0)
        assert from_b["A"] == pytest.approx(2.0 / 3.0)


class TestTheIrreversibleIsomerisation:
    """A -> B: deficiency zero, and the OTHER half of the theorem.

    Worth its own class because the two halves reach opposite conclusions
    from the same deficiency, and weak reversibility is the only thing
    separating them.
    """

    def test_it_has_deficiency_zero_and_is_not_weakly_reversible(self) -> None:
        network = _irreversible_isomerisation()
        assert deficiency(network) == 0
        assert not is_weakly_reversible(network)

    def test_the_verdict_is_that_no_positive_steady_state_exists(self) -> None:
        verdict = deficiency_zero_verdict(_irreversible_isomerisation())
        assert verdict.applies
        assert "NO steady state with all species strictly positive" in verdict.conclusion
        assert "exactly one" not in verdict.conclusion

    def test_the_dynamics_settle_on_the_boundary_as_the_theorem_says(self) -> None:
        # A -> B with A + B = 1 runs to A = 0, B = 1. The theorem forbids a
        # steady state with every species strictly positive, and the state
        # this settles to has A on the boundary rather than inside it.
        network = _irreversible_isomerisation()
        rest = _settle(network, [1.0, 0.0])
        assert rest["A"] == pytest.approx(0.0, abs=1e-9)
        assert rest["B"] == pytest.approx(1.0)


class TestMichaelisMentenIsRefused:
    """The refusal this module exists to make.

    A Michaelis-Menten law is not an approximation to mass action, it is a
    different function: `kcat*E*S/(Km+S)` saturates and `k*S` does not. The
    deficiency theorems say nothing about it, and a verdict issued anyway
    would carry a theorem's authority with none of its content.
    """

    def test_a_catalytic_step_refuses_and_names_mass_action(self) -> None:
        network = _single_motif(CATALYTIC_STEP)
        with pytest.raises(KineticsNotMassAction) as caught:
            deficiency_zero_verdict(network)
        text = str(caught.value)
        assert "MASS-ACTION" in text
        assert "mass action" in text

    def test_the_refusal_says_which_reaction_and_why(self) -> None:
        # "Not mass action" on its own is not actionable. The reader has to
        # be told which rate law and what about it.
        network = _single_motif(CATALYTIC_STEP)
        with pytest.raises(KineticsNotMassAction) as caught:
            deficiency_one_verdict(network)
        text = str(caught.value)
        assert "m_catalysis" in text
        assert "Michaelis-Menten" in text
        assert "denominator" in text

    def test_the_refusal_says_what_to_do_instead(self) -> None:
        # Two ways forward: write the elementary steps, which ARE mass
        # action, or use the numerical analysis that does not need the
        # hypothesis.
        network = _single_motif(PHOSPHORYLATION_CYCLE)
        with pytest.raises(KineticsNotMassAction) as caught:
            deficiency_zero_verdict(network)
        text = str(caught.value)
        assert "E + S -> ES" in text
        assert "compose/analysis.py" in text

    def test_a_hill_law_is_refused_with_the_exponent_named(self) -> None:
        network = _single_motif(HILL_REPRESSION)
        findings = {f.reaction_id: f for f in classify_kinetics(network)}
        assert not findings["m_repressed_synthesis"].mass_action
        assert "Hill" in findings["m_repressed_synthesis"].reason
        # And the first-order degradation in the SAME motif is mass action,
        # so the classifier is discriminating rather than refusing wholesale.
        assert findings["m_degradation"].mass_action

    def test_a_catalyst_outside_the_arrow_is_not_mass_action(self) -> None:
        """The case that looks most like mass action and is not.

        `k * E * S` is a product of concentrations, so it passes the FORM
        half of the check. It fails the second half: the reaction as written
        is `S -> P`, whose reactant complex is S alone, and mass action for
        that reaction cannot mention E. To be visible to these theorems the
        enzyme has to be in the complexes.
        """
        network = ReactionNetwork(
            name="catalyst_outside_the_arrow",
            species=(Species("S", 1.0), Species("P", 0.0), Species("E", 0.1)),
            parameters=(Parameter("k", 1.0),),
            reactions=(Reaction("cat", {"S": 1}, {"P": 1}, "k * E * S"),),
        ).validate()
        finding = classify_kinetics(network)[0]
        assert not finding.mass_action
        assert "E" in finding.reason
        assert "not in its reactant complex" in finding.reason

    def test_one_bad_rate_law_refuses_the_whole_network(self) -> None:
        """The theorems are about the system of ODEs, not about a reaction.

        A network that is mass action everywhere except one Michaelis-Menten
        step is not a mass-action system, and a verdict covering "most of
        it" would be a verdict about a model nobody has.
        """
        composition = Composition("mostly_mass_action")
        composition.add(SYNTHESIS_DEGRADATION, "src")
        composition.add(CATALYTIC_STEP, "enz", {"S": "src_X"})
        network = composition.to_network().validate()

        findings = classify_kinetics(network)
        assert sum(1 for f in findings if f.mass_action) == 2
        assert not is_mass_action(network)
        with pytest.raises(KineticsNotMassAction):
            deficiency_zero_verdict(network)


class TestTheGuardIsLoadBearing:
    """What the mass-action check is actually preventing, measured.

    The toggle switch's reaction graph is three complexes -- 0, geneA_X and
    geneB_X -- in one linkage class, with a stoichiometric subspace of rank
    two:

        delta = 3 - 1 - 2 = 0

    and it is weakly reversible, because every species is both synthesised
    from the zero complex and degraded back to it. Every STRUCTURAL
    hypothesis of the Deficiency Zero Theorem holds.

    Its conclusion would be that the system has exactly one steady state in
    each positive compatibility class, that the state is asymptotically
    stable, and that no cyclic trajectory exists. The toggle switch has TWO
    stable states; switching between them is the entire point of the model,
    and `test_compose_sensitivity.py` refuses to differentiate through it for
    that reason.

    So the difference between this module and a confidently wrong structural
    proof about a real, shipped motif is one check. This class is what keeps
    that check honest -- and it fails loudly if the check is removed, rather
    than merely losing coverage.
    """

    def test_the_toggle_switch_passes_every_structural_hypothesis(self) -> None:
        network = compose("a toggle switch between two repressors").network
        assert deficiency(network) == 0
        assert is_weakly_reversible(network)

    def test_and_is_refused_anyway_because_the_kinetics_are_not_covered(self) -> None:
        network = compose("a toggle switch between two repressors").network
        assert not is_mass_action(network)
        with pytest.raises(KineticsNotMassAction, match="MASS-ACTION"):
            deficiency_zero_verdict(network)

    def test_and_the_verdict_it_would_have_given_is_false(self) -> None:
        """The measurement that makes the two tests above matter.

        Without this, "the guard fires" would be a statement about the guard.
        This is the statement about the model: the conclusion the theorem
        would have reached is contradicted by what the equations do.

        The toggle has no conservation law -- it is an open system, made from
        the zero complex and degraded back to it -- so there is one
        stoichiometric compatibility class and it is the whole positive
        orthant. Two attracting states in it is precisely what the
        deficiency-zero conclusion forbids.
        """
        network = compose("a toggle switch between two repressors").network
        assert network.conservation_laws() == []

        a_wins = _settle(network, [5.0, 0.0], dt=0.05)
        b_wins = _settle(network, [0.0, 5.0], dt=0.05)
        assert a_wins["geneA_X"] - b_wins["geneA_X"] > 1.0
        assert min(a_wins.values()) > 0.0 and min(b_wins.values()) > 0.0


class TestTheDeficiencyIsExactAndAnInteger:
    """delta = n - l - s is an integer identity, so s is computed as one.

    Deciding a rank by "is this pivot below 1e-12" makes an integer fact a
    fact about the tolerance.
    """

    def test_the_deficiency_is_an_int_and_never_negative(self) -> None:
        for network in (
            _reversible_isomerisation(),
            _irreversible_isomerisation(),
            _autocatalytic_ladder(),
            _split_linkage_classes(),
            _single_motif(REVERSIBLE_BINDING),
            _single_motif(DIMERISATION),
        ):
            value = deficiency(network)
            assert isinstance(value, int) and not isinstance(value, bool)
            assert value >= 0

    def test_the_rank_agrees_with_the_networks_own_exact_null_space(self) -> None:
        """Rank-nullity, against the other exact computation in the repo.

        `ReactionNetwork.conservation_laws()` is the left null space of the
        stoichiometry matrix over `Fraction`. Its dimension plus the rank of
        the same matrix is the number of species. The two computations are
        independent -- different file, different algorithm, one solving for a
        null space and one counting pivots -- so agreement is evidence, and
        disagreement would mean one of them is wrong about a model.
        """
        for network in (
            _reversible_isomerisation(),
            _autocatalytic_ladder(),
            _split_linkage_classes(),
            _single_motif(REVERSIBLE_BINDING),
            _single_motif(DIMERISATION),
            _single_motif(PHOSPHORYLATION_CYCLE),
        ):
            assert stoichiometric_rank(network) + len(
                network.conservation_laws()
            ) == len(network.species)

    def test_exact_rank_sees_a_difference_floating_point_cannot(self) -> None:
        """The claim of exactness, exercised where it is the whole answer.

        These two rows differ by 1e-20 in one entry. Over the rationals they
        are independent and the rank is 2. In floating point the difference
        does not exist at all -- the second entry rounds to exactly the first
        -- so any float elimination reports rank 1, whatever its tolerance.

        A reaction network's own vectors are small integers, so this cannot
        be provoked through a network. Exercising the helper directly is what
        keeps "computed exactly" a demonstrated property rather than a
        docstring.
        """
        tiny = Fraction(1, 10**20)
        rows = [
            [Fraction(1), Fraction(1)],
            [Fraction(1), Fraction(1) + tiny],
        ]
        assert exact_rank(rows) == 2
        # The premise: floats cannot hold the distinguishing entry.
        assert float(Fraction(1) + tiny) == float(Fraction(1))

    def test_exact_rank_agrees_on_the_ordinary_cases(self) -> None:
        # A guard that only ever reports 2 would pass the test above.
        assert exact_rank([]) == 0
        assert exact_rank([[Fraction(0), Fraction(0)]]) == 0
        assert exact_rank([[Fraction(1), Fraction(2)], [Fraction(2), Fraction(4)]]) == 1


class TestTheDeficiencyOneTheorem:
    """Its hypotheses, checked exactly, and its conclusion checked in closed
    form on a network where the answer is known."""

    def test_the_ladder_meets_every_hypothesis(self) -> None:
        network = _autocatalytic_ladder()
        assert deficiency(network) == 1
        assert linkage_class_deficiencies(network) == (1,)
        assert len(terminal_strong_linkage_classes(network)) == 1
        assert is_weakly_reversible(network)

    def test_and_the_verdict_asserts_exactly_one_positive_steady_state(self) -> None:
        verdict = deficiency_one_verdict(_autocatalytic_ladder())
        assert verdict.applies
        assert "exactly one steady state" in verdict.conclusion

    def test_the_closed_form_has_exactly_one_positive_root(self) -> None:
        """The theorem's conclusion, verified by hand for this network.

        dA/dt = k1*A - k2*A^2 + k3*A^2 - k4*A^3, so a positive steady state
        solves k4*A^2 + (k2 - k3)*A - k1 = 0. At k1=2, k2=3, k3=1, k4=1 that
        is A^2 + 2A - 2 = 0, whose positive root is sqrt(3) - 1 and whose
        other root is negative. Exactly one, as asserted.
        """
        network = _autocatalytic_ladder()
        # From either side of it, since "exactly one" means the trajectory
        # cannot find a second one to rest at.
        from_below = _settle(network, [0.1], dt=0.001)
        from_above = _settle(network, [2.0], dt=0.001)
        assert from_below["A"] == pytest.approx(math.sqrt(3.0) - 1.0)
        assert from_above["A"] == pytest.approx(math.sqrt(3.0) - 1.0)

    def test_the_verdict_claims_nothing_about_stability(self) -> None:
        """The mistake a reader arriving from a Deficiency Zero verdict makes.

        That theorem hands out asymptotic stability; this one does not, and
        the disclaimer has to travel with the verdict rather than living in a
        docstring nobody reads at the point of use. The numerics happen to
        find this particular steady state stable -- and the theorem still did
        not say so, which is the distinction being kept.
        """
        verdict = deficiency_one_verdict(_autocatalytic_ladder())
        assert "STABILITY" in verdict.not_claimed
        assert "stable" not in verdict.conclusion

    def test_a_failed_hypothesis_is_named_rather_than_summarised(self) -> None:
        """`_split_linkage_classes` fails exactly one hypothesis.

        Its linkage classes have deficiencies 0 and 0, which sum to 0 while
        the network's deficiency is 1. The other two hypotheses hold, so a
        verdict that said only "does not apply" would leave the reader
        unable to tell which of three conditions to look at.
        """
        network = _split_linkage_classes()
        assert deficiency(network) == 1
        assert linkage_class_deficiencies(network) == (0, 0)

        verdict = deficiency_one_verdict(network)
        assert not verdict.applies
        assert "sum to the network deficiency" in verdict.reason
        failed = [h.name for h in verdict.hypotheses if not h.holds]
        assert failed == ["the linkage-class deficiencies sum to the network deficiency"]

    def test_two_terminal_ends_in_one_linkage_class_fail_the_first_hypothesis(
        self,
    ) -> None:
        """The other hypothesis, exercised in the direction that fails.

        Every other network here has exactly one terminal strong linkage
        class per linkage class, so the first hypothesis was only ever
        satisfied -- and a check that is never seen to fail could be
        inverted without a test noticing. `A -> B` and `A -> C` gives one
        linkage class with two dead ends.
        """
        network = _branching_outflow()
        assert len(linkage_classes(network)) == 1
        assert len(terminal_strong_linkage_classes(network)) == 2

        verdict = deficiency_one_verdict(network)
        assert not verdict.applies
        failed = [h.name for h in verdict.hypotheses if not h.holds]
        assert failed == [
            "one terminal strong linkage class per linkage class"
        ]

    def test_deficiency_zero_declines_the_same_network_for_its_own_reason(self) -> None:
        # A deficiency of one is not a defect: it is what makes several
        # steady states possible at all. The verdict should say that rather
        # than reading as a failure.
        verdict = deficiency_zero_verdict(_split_linkage_classes())
        assert not verdict.applies
        assert "deficiency 1" in verdict.reason


class TestTheLibraryMotifs:
    """The mass-action motifs Terrium actually ships, and what follows for them.

    These are the payoff: real motifs, every rate constant still an
    illustrative placeholder, and a conclusion that holds regardless.
    """

    def test_synthesis_degradation_is_deficiency_zero_and_weakly_reversible(
        self,
    ) -> None:
        # BY HAND: complexes 0 and X, so n = 2; one linkage class through the
        # zero complex, l = 1; one reaction vector, s = 1; delta = 0. Weakly
        # reversible because `-> X` and `X ->` close the cycle.
        network = _single_motif(SYNTHESIS_DEGRADATION)
        assert deficiency(network) == 0
        assert is_weakly_reversible(network)
        assert deficiency_zero_verdict(network).applies

    def test_and_its_analytic_steady_state_is_the_one_it_settles_to(self) -> None:
        # dX/dt = ks - kd*X has the single root ks/kd = 1.0/0.1 = 10 and
        # slope -kd < 0 everywhere, so that root is unique and attracting --
        # which is what the theorem asserted without looking at ks or kd.
        network = _single_motif(SYNTHESIS_DEGRADATION)
        assert _settle(network, [0.0], dt=0.05)["m_X"] == pytest.approx(10.0)
        assert _settle(network, [40.0], dt=0.05)["m_X"] == pytest.approx(10.0)

    def test_reversible_binding_is_deficiency_zero(self) -> None:
        # BY HAND: complexes {A + B} and {AB}, n = 2; one linkage class,
        # l = 1; one reaction vector (-1, -1, +1), s = 1; delta = 0. Weakly
        # reversible, since association and dissociation are both present.
        network = _single_motif(REVERSIBLE_BINDING)
        assert deficiency(network) == 0
        assert is_weakly_reversible(network)
        assert "exactly one steady state" in deficiency_zero_verdict(network).conclusion

    def test_and_binding_settles_at_the_root_the_algebra_gives(self) -> None:
        """The closed form, on the compatibility class the initials pick out.

        A and B both start at 1 and AB at 0, so A = B = 1 - AB throughout.
        At steady state kon*A*B = koff*AB, so (1 - AB)^2 = (koff/kon)*AB.
        With kon = 1 and koff = 0.1 that is AB^2 - 2.1*AB + 1 = 0, whose
        roots are (2.1 +/- sqrt(0.41))/2. Only the smaller lies below 1 and
        so inside the positive compatibility class -- exactly one, which is
        what the theorem asserted.
        """
        network = _single_motif(REVERSIBLE_BINDING)
        expected = (2.1 - math.sqrt(0.41)) / 2.0
        rest = _settle(network, [1.0, 1.0, 0.0])
        assert rest["m_AB"] == pytest.approx(expected)
        # The other root of the same quadratic is above 1 and so outside the
        # compatibility class the initial condition picks out. The theorem
        # counted the ones inside it.
        assert (2.1 + math.sqrt(0.41)) / 2.0 > 1.0

    def test_dimerisation_keeps_its_stoichiometry_in_the_complex(self) -> None:
        # The reactant complex is 2M, not M. If it were canonicalised to M
        # the rate law `kon * M * M` would stop matching and a shipped
        # mass-action motif would be refused.
        network = _single_motif(DIMERISATION)
        assert Complex.of({"m_M": 2}) in complexes(network)
        assert is_mass_action(network)
        assert deficiency(network) == 0


class TestRefusalsThatAreNotAboutKinetics:
    def test_a_model_with_no_reactions_has_no_deficiency(self) -> None:
        # Not a deficiency of zero. Deficiency counts complexes against
        # reaction vectors, and there are neither.
        empty = ReactionNetwork(
            name="nothing_happens",
            species=(Species("A", 1.0),),
            parameters=(),
            reactions=(),
        )
        with pytest.raises(NotAReactionNetwork, match="no reactions"):
            deficiency(empty)

    def test_a_rate_rule_makes_the_theorems_inapplicable(self) -> None:
        """A species driven by a rate rule changes outside the stoichiometry.

        The deficiency of the reaction part is still a fact and is still
        reported; what is refused is reading dynamics into it, because the
        rate rule is free to do things no reaction vector describes.
        """
        network = ReactionNetwork(
            name="half_reactions",
            species=(Species("A", 1.0), Species("B", 0.0), Species("C", 1.0)),
            parameters=(Parameter("k", 1.0),),
            reactions=(Reaction("go", {"A": 1}, {"B": 1}, "k * A"),),
            rate_rules=(RateRule("C", "k * C"),),
        ).validate()

        assert deficiency(network) == 0
        with pytest.raises(NotAReactionNetwork, match="rate rule"):
            deficiency_zero_verdict(network)

    def test_a_rate_law_built_from_an_assignment_rule_is_refused(self) -> None:
        """Why `_require_mass_action` needs no branch for assignment rules.

        A rate law that uses one references a symbol that is neither a
        species nor a parameter, and the classifier already declines to call
        that mass action. The refusal comes out of the general rule rather
        than a special case, which is the claim the comment in `crnt.py`
        makes and this is what keeps it true.
        """
        network = ReactionNetwork(
            name="derived_symbol",
            species=(Species("A", 1.0), Species("B", 0.0)),
            parameters=(Parameter("k", 1.0),),
            reactions=(Reaction("go", {"A": 1}, {"B": 1}, "alpha * A"),),
            assignment_rules=(AssignmentRule("alpha", "k / 2"),),
        ).validate()
        finding = classify_kinetics(network)[0]
        assert not finding.mass_action
        assert "alpha" in finding.reason
        with pytest.raises(KineticsNotMassAction):
            deficiency_zero_verdict(network)

    def test_weak_reversibility_is_undefined_without_arrows(self) -> None:
        # Not False. Weak reversibility is a property of arrows, and
        # returning False for a network with none would read as "this model
        # cannot reach a positive steady state", which is a real claim about
        # a model that has no dynamics at all.
        empty = ReactionNetwork(
            name="nothing_happens",
            species=(Species("A", 1.0),),
            parameters=(),
            reactions=(),
        )
        with pytest.raises(NotAReactionNetwork, match="no reactions"):
            is_weakly_reversible(empty)

    def test_a_negative_multiplicity_is_not_a_complex(self) -> None:
        with pytest.raises(NotAReactionNetwork, match="other side of the arrow"):
            Complex.of({"A": -1})

    def test_a_ragged_matrix_has_no_rank(self) -> None:
        # Defensive, but the alternative is a rank computed from rows that
        # were never the same matrix.
        with pytest.raises(ValueError, match="not the same length"):
            exact_rank([[Fraction(1), Fraction(1)], [Fraction(1)]])

    def test_an_undeclared_species_in_a_reaction_is_refused(self) -> None:
        # Constructed without validate(), which is the only way to get here.
        # The structure cannot be read off a model whose stoichiometry names
        # something that does not exist.
        broken = ReactionNetwork(
            name="dangling",
            species=(Species("A", 1.0),),
            parameters=(Parameter("k", 1.0),),
            reactions=(Reaction("go", {"A": 1}, {"Z": 1}, "k * A"),),
        )
        with pytest.raises(NotAReactionNetwork, match="not a declared species"):
            stoichiometric_rank(broken)


class TestTheCaveatThatTheConstantsMustBePositive:
    """Both theorems quantify over STRICTLY POSITIVE rate constants.

    That quantifier is what lets a verdict be given while every constant is
    an unmeasured placeholder. It is also what a placeholder of zero falls
    outside, and the verdict has to say so rather than being read as a
    statement about the model as it currently stands.
    """

    def _with_value(self, value: float) -> ReactionNetwork:
        return ReactionNetwork(
            name="reversible_isomerisation",
            species=(Species("A", 1.0), Species("B", 0.0)),
            parameters=(Parameter("k1", 1.0), Parameter("k2", value)),
            reactions=(
                Reaction("forward", {"A": 1}, {"B": 1}, "k1 * A"),
                Reaction("backward", {"B": 1}, {"A": 1}, "k2 * B"),
            ),
        ).validate()

    def test_a_positive_placeholder_produces_no_caveat(self) -> None:
        # Stated first: without it the test below would pass on an
        # implementation that caveated every verdict unconditionally.
        assert deficiency_zero_verdict(self._with_value(2.0)).caveats == ()

    def test_a_zero_rate_constant_is_flagged_by_name(self) -> None:
        verdict = deficiency_zero_verdict(self._with_value(0.0))
        assert verdict.applies
        assert len(verdict.caveats) == 1
        assert "k2" in verdict.caveats[0]
        assert "k1" not in verdict.caveats[0]

    def test_the_caveat_travels_in_the_summary(self) -> None:
        verdict = deficiency_zero_verdict(self._with_value(-1.0))
        assert verdict.caveats[0] in verdict.summary()


class TestTheClassifierErrsTowardRefusing:
    """Every branch that cannot be PROVED mass action reports that it is not.

    A false "not mass action" costs a refused verdict the reader can argue
    with. A false "mass action" costs a theorem applied to a model it does
    not cover, which nobody would catch.
    """

    def _one_reaction(self, rate_law: str) -> ReactionNetwork:
        # Not validated: several of these rate laws are deliberately outside
        # what the network validator accepts, and the classifier must still
        # decline rather than crash on them.
        return ReactionNetwork(
            name="probe",
            species=(Species("A", 1.0), Species("B", 0.0)),
            parameters=(Parameter("k", 1.0), Parameter("n", 2.0)),
            reactions=(Reaction("go", {"A": 1}, {"B": 1}, rate_law),),
        )

    @pytest.mark.parametrize(
        "rate_law",
        [
            "k * A / (k + A)",     # saturating
            "k * A ^ n",           # exponent is a parameter: a Hill law
            "k * A + k * B",       # a sum: two mechanisms in one reaction
            "-k * A",              # negative
            "k * A * time",        # not autonomous
            "exp(k) * A",          # a function call
            "k * A ^ 0.5",         # fractional order: empirical
            "k * missing",         # an undeclared symbol
            "k * (A",              # unparseable
            "0 * A",               # a non-positive constant
        ],
    )
    def test_a_rate_law_that_is_not_provably_mass_action_is_refused(
        self, rate_law: str
    ) -> None:
        finding = classify_kinetics(self._one_reaction(rate_law))[0]
        assert not finding.mass_action
        assert finding.reason

    @pytest.mark.parametrize(
        "rate_law", ["k * A", "A * k", "A", "k * A ^ 1", "k / n * A", "2 * k * A"]
    )
    def test_the_forms_that_ARE_mass_action_are_accepted(
        self, rate_law: str
    ) -> None:
        # Without this the class above would pass on a classifier that
        # refused everything, which would be useless rather than cautious.
        finding = classify_kinetics(self._one_reaction(rate_law))[0]
        assert finding.mass_action
        assert finding.reason == ""

    def test_antimony_exponentiation_is_read_as_a_power_and_not_as_xor(
        self,
    ) -> None:
        """`^` means power in Antimony and xor in Python.

        Left untranslated, `k * A^2` parses as `(k*A) ^ 2` -- a bitwise xor
        -- and the classifier would be reasoning about an expression the
        model does not contain. Checked on a reaction whose stoichiometry
        makes the right reading and the wrong reading disagree.
        """
        network = ReactionNetwork(
            name="power",
            species=(Species("A", 1.0), Species("B", 0.0)),
            parameters=(Parameter("k", 1.0),),
            reactions=(Reaction("go", {"A": 2}, {"B": 1}, "k * A^2"),),
        ).validate()
        assert classify_kinetics(network)[0].mass_action
        assert deficiency(network) == 0


class TestTheReportSaysWhatItCounted:
    def test_describe_reports_the_terms_before_the_verdict(self) -> None:
        # n, l and s are checkable by hand against the model text; a
        # conclusion is not. A reader who disagrees has to be able to find
        # out where the disagreement starts.
        text = describe(_reversible_isomerisation())
        assert "2 complex(es)" in text
        assert "1 linkage class(es)" in text
        assert "rank 1" in text
        assert "Deficiency = n - l - s = 2 - 1 - 1 = 0" in text

    def test_describe_names_the_offending_rate_laws_when_there_are_any(self) -> None:
        text = describe(_single_motif(CATALYTIC_STEP))
        assert "NOT mass action" in text
        assert "m_catalysis" in text

    def test_a_verdict_carries_its_disclaimer_wherever_it_travels(self) -> None:
        """`not_claimed` is a field, not prose in a docstring.

        The hazard is a theorem's authority attaching to a claim the theorem
        never made, and the counter-claim has to be as portable as the claim
        -- including into a report that only ever prints `summary()`.
        """
        verdict = deficiency_zero_verdict(_reversible_isomerisation())
        assert "Global Attractor Conjecture" in verdict.not_claimed
        assert verdict.not_claimed in verdict.summary()
