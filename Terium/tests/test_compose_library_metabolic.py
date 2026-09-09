"""What a metabolic motif has to get right that a kinetic one does not.

A pathway model can be wrong in a way a single rate law cannot: it can run
uphill. A reversible step whose four kinetic constants came from four
different papers will in general imply an equilibrium constant that the
reaction's free energy does not permit, and the resulting model integrates
beautifully while describing an enzyme that moves its own equilibrium.

Nothing else in this package can catch that. The dimensional checker says
the law balances -- it does. The steady-state solver finds a steady state
-- there is one. So these tests are where it is caught, and the central one
is analytic: at the concentrations the equilibrium constant names, the net
rate must be EXACTLY zero, and the arithmetic that says so is a line long.

The rest pin the surrounding claims: that the conserved pool's law comes
from the stoichiometry rather than from a parameter, that a branch point's
split is the two rate laws and nothing else, that the Haldane relationship
is written down where a reader will find it, and that every motif here
balances dimensionally.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Mapping

import pytest

from Terium.compose.analysis import derivative_function
from Terium.compose.builder import Composition, CompositionError
from Terium.compose.library import (
    LIBRARY, PHOSPHORYLATION_CYCLE, REVERSIBLE_CATALYSIS,
)
from Terium.compose.library_metabolic import (
    ALIASES, ALLOSTERIC_FEEDBACK, BRANCH_POINT, COFACTOR_COUPLED_STEP,
    FULL_LIBRARY, HALDANE_TOLERANCE, LINEAR_PATHWAY_SEGMENT,
    METABOLIC_LIBRARY, MOIETY_CONSERVED_CYCLE, REVERSIBLE_MICHAELIS_MENTEN,
    TRANSPORTER_LIMITED_UPTAKE, ThermodynamicError, check_haldane,
    check_segment_drive, check_symport_gradient, haldane_kcat_r, haldane_keq,
    haldane_residual, linear_pathway, metabolic_motif,
    segment_equilibrium_constant, symport_ceiling,
)
from Terium.compose.motifs import (
    CHOSEN_KINDS, KIND_CONCENTRATION, RESOLVABLE_KINDS,
)
from Terium.core.network import describe_conservation_laws


# ---------------------------------------------------------------------------
# Evaluating one rate law at one point
# ---------------------------------------------------------------------------
#
# `Composition` builds every parameter at its motif default, and these tests
# need specific numbers -- the whole point of an analytic check is that the
# answer is known for THOSE values. So the network is built once and its
# parameters and initials are replaced before it is differentiated.
#
# `_derivatives` refuses an unknown key rather than ignoring it. A test that
# sets `kcat_F` where the model has `kcat_f` would otherwise run against the
# placeholder, agree with a formula computed from the placeholder, and pass
# while checking nothing.


def _derivatives(network, values: Mapping[str, float]) -> Dict[str, float]:
    """dx/dt for every species, with `values` overriding parameters and initials."""
    known = set(network.species_ids()) | set(network.parameter_ids())
    unknown = sorted(set(values) - known)
    if unknown:
        raise KeyError(
            f"{unknown} name nothing in this network. Known species and "
            f"parameters: {sorted(known)}. Silently ignoring the name would "
            f"leave the test running against a placeholder."
        )
    species = tuple(
        replace(s, initial=float(values[s.id])) if s.id in values else s
        for s in network.species
    )
    parameters = tuple(
        replace(p, value=float(values[p.id])) if p.id in values else p
        for p in network.parameters
    )
    concrete = replace(network, species=species, parameters=parameters)
    rhs, order = derivative_function(concrete)
    initial = {s.id: s.initial for s in concrete.species}
    return dict(zip(order, rhs([initial[name] for name in order])))


def _one(motif, prefix: str):
    """A network holding a single instance of one motif."""
    composition = Composition(f"probe_{prefix}")
    composition.add(motif, prefix)
    return composition.to_network()


# ---------------------------------------------------------------------------


class TestTheReversibleLawIsZeroAtEquilibrium:
    """The test that proves the thermodynamics, and it is arithmetic.

    Reversible Michaelis-Menten:

        v = (kcat_f*E*S/Kms - kcat_r*E*P/Kmp) / (1 + S/Kms + P/Kmp)

    v = 0 requires kcat_f*S/Kms = kcat_r*P/Kmp, i.e. P/S = kcat_f*Kmp /
    (kcat_r*Kms), which is the Haldane relationship and is the equilibrium
    constant. So the net rate at P = Keq*S is zero for every parameter set,
    and a law that is not zero there is describing a reaction that keeps
    running after equilibrium.
    """

    def test_the_motif_defaults_imply_an_equilibrium_constant_of_fifty(self) -> None:
        # The four defaults of `reversible_catalysis` are kcat_f = 100,
        # kcat_r = 10, Kms = 0.1, Kmp = 0.5. Keq = 100*0.5 / (10*0.1) = 50.
        # Pinned so the numbers the rest of this class uses are visible.
        defaults = {p.name: p.default for p in REVERSIBLE_MICHAELIS_MENTEN.parameters}
        assert haldane_keq(
            defaults["kcat_f"], defaults["kcat_r"],
            defaults["Kms"], defaults["Kmp"],
        ) == pytest.approx(50.0)

    def test_the_four_constant_law_is_exactly_zero_at_that_ratio(self) -> None:
        network = _one(REVERSIBLE_MICHAELIS_MENTEN, "rev")
        rates = _derivatives(network, {
            "rev_kcat_f": 100.0, "rev_kcat_r": 10.0,
            "rev_Kms": 0.1, "rev_Kmp": 0.5,
            "rev_E": 1e-3,
            "rev_S": 0.02, "rev_P": 1.0,      # P/S = 50 = Keq
        })
        # Not "small": zero. The two halves of the numerator are equal, so
        # the tolerance here is floating-point noise on a quantity of order
        # 2e-2, not a physical smallness.
        assert rates["rev_S"] == pytest.approx(0.0, abs=1e-12)
        assert rates["rev_P"] == pytest.approx(0.0, abs=1e-12)

    @pytest.mark.parametrize(
        "displacement, expected_sign",
        [(0.1, +1.0), (0.5, +1.0), (2.0, -1.0), (10.0, -1.0)],
    )
    def test_it_runs_towards_equilibrium_from_either_side(
        self, displacement: float, expected_sign: float
    ) -> None:
        # Below the equilibrium ratio the step runs forward; above it, the
        # SAME law runs backwards. That sign change is the only thing that
        # separates a reversible step from an irreversible one written with
        # a product term.
        substrate = 0.02
        network = _one(REVERSIBLE_MICHAELIS_MENTEN, "rev")
        rates = _derivatives(network, {
            "rev_kcat_f": 100.0, "rev_kcat_r": 10.0,
            "rev_Kms": 0.1, "rev_Kmp": 0.5, "rev_E": 1e-3,
            "rev_S": substrate, "rev_P": 50.0 * substrate * displacement,
        })
        assert rates["rev_P"] * expected_sign > 0.0

    @pytest.mark.parametrize(
        "kcat_f, Kms, Kmp, keq",
        [
            (100.0, 0.1, 0.5, 50.0),
            (1.0, 2.0, 2.0, 1.0),
            (37.0, 0.004, 11.0, 1e-3),
            (5.0, 1.0, 1.0, 250.0),
        ],
    )
    def test_the_segment_form_is_zero_at_equilibrium_whatever_the_constants(
        self, kcat_f: float, Kms: float, Kmp: float, keq: float
    ) -> None:
        """The segment cannot be given constants that break this.

        `linear_pathway_segment` has Keq as a parameter and derives kcat_r
        from it, so the numerator is kcat_f*E*(S - P/Keq)/Kms and vanishes
        at P = Keq*S identically. There is no set of four numbers that
        makes it fail, which is the property the motif exists to have.
        """
        substrate = 0.3
        network = _one(LINEAR_PATHWAY_SEGMENT, "seg")
        rates = _derivatives(network, {
            "seg_kcat_f": kcat_f, "seg_Kms": Kms, "seg_Kmp": Kmp,
            "seg_Keq": keq, "seg_E": 1e-3,
            "seg_S": substrate, "seg_P": keq * substrate,
        })
        assert rates["seg_P"] == pytest.approx(0.0, abs=1e-12)

    @pytest.mark.parametrize("substrate, product", [(1.0, 0.0), (0.2, 5.0), (3.0, 3.0)])
    def test_the_segment_and_the_four_constant_law_are_the_same_function(
        self, substrate: float, product: float
    ) -> None:
        """Substituting the Haldane relationship changes nothing but the slots.

        Given kcat_r = kcat_f*Kmp/(Kms*Keq), the two rate laws are
        algebraically identical. If they ever disagree, one of them has been
        mistyped -- and the segment's whole claim is that it is the same
        function with one degree of freedom removed, not a different model.
        """
        kcat_f, Kms, Kmp, keq = 100.0, 0.1, 0.5, 7.0
        kcat_r = haldane_kcat_r(kcat_f, Kms, Kmp, keq)

        four = _derivatives(_one(REVERSIBLE_MICHAELIS_MENTEN, "rev"), {
            "rev_kcat_f": kcat_f, "rev_kcat_r": kcat_r,
            "rev_Kms": Kms, "rev_Kmp": Kmp, "rev_E": 1e-3,
            "rev_S": substrate, "rev_P": product,
        })
        three = _derivatives(_one(LINEAR_PATHWAY_SEGMENT, "seg"), {
            "seg_kcat_f": kcat_f, "seg_Kms": Kms, "seg_Kmp": Kmp,
            "seg_Keq": keq, "seg_E": 1e-3,
            "seg_S": substrate, "seg_P": product,
        })
        assert three["seg_P"] == pytest.approx(four["rev_P"], rel=1e-12, abs=1e-15)


class TestTheHaldaneRelationshipIsWrittenDown:
    """A constraint a reader cannot see is a constraint nobody applies."""

    def test_the_reversible_motif_states_the_equation_and_not_only_its_name(
        self,
    ) -> None:
        basis = REVERSIBLE_MICHAELIS_MENTEN.basis
        assert "Keq = (kcat_f * Kmp) / (kcat_r * Kms)" in basis

    def test_the_reversible_motif_says_the_four_are_not_independent(self) -> None:
        # The sentence the resolver's author has to read. Without it the
        # motif's four resolvable parameters look like four independent
        # search jobs, which is exactly the mistake.
        basis = REVERSIBLE_MICHAELIS_MENTEN.basis.upper()
        assert "CANNOT BE RESOLVED INDEPENDENTLY" in basis

    def test_the_segment_states_it_too_and_names_the_substitution(self) -> None:
        basis = LINEAR_PATHWAY_SEGMENT.basis
        assert "Keq = (kcat_f * Kmp) / (kcat_r * Kms)" in basis
        assert "kcat_r = kcat_f*Kmp/(Kms*Keq)" in basis

    def test_reversible_michaelis_menten_is_the_library_motif_not_a_copy(self) -> None:
        # `is`, not `==`. A second Motif object with the same fields would
        # satisfy equality and would be the duplicate the registry refuses.
        assert REVERSIBLE_MICHAELIS_MENTEN is REVERSIBLE_CATALYSIS

    def test_the_alias_resolves_to_it(self) -> None:
        assert metabolic_motif("reversible_michaelis_menten") is REVERSIBLE_CATALYSIS


class TestTheHaldaneCheck:
    """A parameter set that violates the relationship is refused, with numbers."""

    def test_a_consistent_set_passes_and_has_a_residual_of_one(self) -> None:
        kcat_f, Kms, Kmp, keq = 42.0, 0.3, 1.7, 12.0
        kcat_r = haldane_kcat_r(kcat_f, Kms, Kmp, keq)
        assert haldane_residual(kcat_f, kcat_r, Kms, Kmp, keq) == pytest.approx(1.0)
        # Returns None; the assertion is that it does not raise.
        assert check_haldane(kcat_f, kcat_r, Kms, Kmp, keq, tolerance=1.0 + 1e-9) is None

    def test_a_set_implying_the_wrong_equilibrium_is_refused(self) -> None:
        # kcat_f=100, kcat_r=10, Kms=0.1, Kmp=0.5 implies Keq = 50. Telling
        # it the equilibrium constant is 1 is a factor of fifty out, which
        # is not measurement scatter -- it is a different reaction.
        with pytest.raises(ThermodynamicError) as caught:
            check_haldane(100.0, 10.0, 0.1, 0.5, 1.0)
        message = str(caught.value)
        assert "50" in message
        assert "kcat_r" in message

    def test_the_refusal_names_a_kcat_r_that_would_satisfy_it(self) -> None:
        """"Inconsistent" is not actionable; a number is.

        The refusal says which reverse turnover number the other three
        constants and the equilibrium constant force. This checks that the
        number it names actually passes the check it just failed.
        """
        repaired = haldane_kcat_r(100.0, 0.1, 0.5, 1.0)
        assert repaired == pytest.approx(500.0)
        assert check_haldane(100.0, repaired, 0.1, 0.5, 1.0, tolerance=1.0 + 1e-9) is None

    def test_a_factor_inside_the_tolerance_is_not_a_finding(self) -> None:
        # The tolerance is a FACTOR because kinetic constants from
        # different papers differ by factors. A 1.5x discrepancy under a
        # 2x tolerance is scatter, not a thermodynamic impossibility.
        kcat_r = haldane_kcat_r(100.0, 0.1, 0.5, 1.0) * 1.5
        assert haldane_residual(100.0, kcat_r, 0.1, 0.5, 1.0) == pytest.approx(1.5)
        assert check_haldane(100.0, kcat_r, 0.1, 0.5, 1.0) is None
        assert HALDANE_TOLERANCE == 2.0

    def test_the_residual_is_symmetric_in_the_direction_of_the_error(self) -> None:
        # Too fast and too slow are equally wrong. A signed residual would
        # rank one direction as better than the other for no reason.
        high = haldane_residual(100.0, 20.0, 0.1, 0.5, 50.0)
        low = haldane_residual(100.0, 5.0, 0.1, 0.5, 50.0)
        assert high == pytest.approx(2.0)
        assert low == pytest.approx(2.0)

    def test_a_tolerance_below_one_is_refused_rather_than_silently_clamped(self) -> None:
        # No parameter set can satisfy a factor below 1, not even an exact
        # one, so accepting it would make every call fail for a reason the
        # caller did not intend.
        with pytest.raises(ThermodynamicError, match="FACTOR"):
            check_haldane(100.0, 10.0, 0.1, 0.5, 50.0, tolerance=0.5)

    @pytest.mark.parametrize(
        "kcat_f, kcat_r, Kms, Kmp, keq",
        [
            (0.0, 10.0, 0.1, 0.5, 50.0),
            (100.0, -1.0, 0.1, 0.5, 50.0),
            (100.0, 10.0, 0.0, 0.5, 50.0),
            (100.0, 10.0, 0.1, 0.5, 0.0),
        ],
    )
    def test_a_non_positive_constant_is_refused_not_divided_by(
        self, kcat_f: float, kcat_r: float, Kms: float, Kmp: float, keq: float
    ) -> None:
        with pytest.raises(ThermodynamicError):
            check_haldane(kcat_f, kcat_r, Kms, Kmp, keq)


class TestTheConservedPool:
    """The conservation law comes from the stoichiometry, not from a parameter."""

    def test_the_cycle_conserves_its_moiety(self) -> None:
        composition = Composition("pool_only")
        composition.add(MOIETY_CONSERVED_CYCLE, "pool")
        laws = describe_conservation_laws(composition.to_network())
        assert "pool_C_active + pool_C_spent" in laws

    def test_the_pool_survives_a_step_that_spends_it(self) -> None:
        """The law is the point of the motif, so adding a consumer must not
        break it. A coupled step that took the cofactor as a MODIFIER would
        leave this law standing while consuming nothing; one that consumed
        it without returning the spent form would destroy the law entirely.
        Only the correct stoichiometry keeps both.
        """
        composition = Composition("pool_and_load")
        composition.add(MOIETY_CONSERVED_CYCLE, "pool")
        composition.add(
            COFACTOR_COUPLED_STEP, "step",
            bindings={"C_active": "pool_C_active", "C_spent": "pool_C_spent"},
        )
        laws = describe_conservation_laws(composition.to_network())
        assert "pool_C_active + pool_C_spent" in laws

    def test_the_coupled_step_really_consumes_the_cofactor(self) -> None:
        # If the cofactor were a modifier this derivative would be zero and
        # the pool could never run down -- which is the failure the motif's
        # basis says it exists to avoid.
        composition = Composition("pool_and_load")
        composition.add(MOIETY_CONSERVED_CYCLE, "pool")
        step = composition.add(
            COFACTOR_COUPLED_STEP, "step",
            bindings={"C_active": "pool_C_active", "C_spent": "pool_C_spent"},
        )
        assert step.species_for("C_active") == "pool_C_active"
        network = composition.to_network()
        # Regeneration and demand switched off, so only the coupled step
        # moves the pool and the sign is unambiguous.
        rates = _derivatives(network, {
            "pool_kcat_regen": 1e-12, "pool_kcat_demand": 1e-12,
            "pool_C_active": 1.0, "pool_C_spent": 0.0,
            "step_S": 1.0, "step_P": 0.0, "step_E": 1e-3,
        })
        assert rates["pool_C_active"] < 0.0
        assert rates["pool_C_spent"] > 0.0

    def test_no_motif_here_declares_the_pool_total_as_a_parameter(self) -> None:
        """A total would be a lumped scenario quantity (ADR 0013).

        It is the sum of two initial concentrations, both chosen by the
        caller. As a parameter it would be redundant with them, so a model
        could state a total contradicting its own initial conditions.
        """
        offenders = [
            f"{motif.name}.{parameter.name}"
            for motif in METABOLIC_LIBRARY.values()
            for parameter in motif.parameters
            if parameter.kind == KIND_CONCENTRATION or "total" in parameter.name.lower()
        ]
        assert offenders == []

    def test_the_cycle_is_not_the_phosphorylation_cycle_under_another_name(self) -> None:
        # They share their algebra and not their stoichiometry: the moiety
        # here is a small molecule other reactions consume, so its ports are
        # partners rather than a substrate/product pair owned by one enzyme
        # pair. Pinned because "same equations, therefore duplicate" is the
        # argument that would delete this motif.
        assert MOIETY_CONSERVED_CYCLE.name not in LIBRARY
        assert {p.name for p in MOIETY_CONSERVED_CYCLE.ports} != {
            p.name for p in PHOSPHORYLATION_CYCLE.ports
        }


class TestTheBranchPoint:
    """The split is the two rate laws and nothing else."""

    @pytest.mark.parametrize("substrate", [0.001, 0.05, 1.0, 100.0])
    def test_each_branch_carries_its_own_michaelis_menten_flux(
        self, substrate: float
    ) -> None:
        kcat_1, Km_1, kcat_2, Km_2, enzyme = 100.0, 10.0, 10.0, 0.01, 1e-3
        network = _one(BRANCH_POINT, "fork")
        rates = _derivatives(network, {
            "fork_kcat_1": kcat_1, "fork_Km_1": Km_1,
            "fork_kcat_2": kcat_2, "fork_Km_2": Km_2,
            "fork_E1": enzyme, "fork_E2": enzyme,
            "fork_S": substrate, "fork_P1": 0.0, "fork_P2": 0.0,
        })
        expected_1 = kcat_1 * enzyme * substrate / (Km_1 + substrate)
        expected_2 = kcat_2 * enzyme * substrate / (Km_2 + substrate)
        assert rates["fork_P1"] == pytest.approx(expected_1, rel=1e-12)
        assert rates["fork_P2"] == pytest.approx(expected_2, rel=1e-12)
        # The shared metabolite loses exactly the sum. Competition is the
        # shared pool, not a term in either law.
        assert rates["fork_S"] == pytest.approx(-(expected_1 + expected_2), rel=1e-12)

    def test_the_preferred_branch_reverses_across_the_substrate_range(self) -> None:
        """Why a branch point is a control point and not a fixed splitter.

        Branch 1 is fast and sloppy (kcat 100, Km 10), branch 2 slow and
        tight (kcat 10, Km 0.01). Far below both Michaelis constants the
        split tends to the ratio of specificity constants, kcat/Km, and
        branch 2 wins by a hundredfold. At saturation the constants cancel
        and branch 1 wins by ten. A model that reported one split ratio
        would be wrong on one side or the other.
        """
        settings = {
            "fork_kcat_1": 100.0, "fork_Km_1": 10.0,
            "fork_kcat_2": 10.0, "fork_Km_2": 0.01,
            "fork_E1": 1e-3, "fork_E2": 1e-3,
            "fork_P1": 0.0, "fork_P2": 0.0,
        }
        network = _one(BRANCH_POINT, "fork")
        # Four orders below the smaller Km and two above the larger one, so
        # each limit is reached rather than approached -- the point is the
        # reversal, not how quickly it happens.
        low = _derivatives(network, {**settings, "fork_S": 1e-7})
        high = _derivatives(network, {**settings, "fork_S": 1e6})

        assert low["fork_P2"] > low["fork_P1"]
        assert high["fork_P1"] > high["fork_P2"]
        # And the limits are the ones the basis names.
        assert low["fork_P1"] / low["fork_P2"] == pytest.approx(
            (100.0 / 10.0) / (10.0 / 0.01), rel=1e-3
        )
        assert high["fork_P1"] / high["fork_P2"] == pytest.approx(
            100.0 / 10.0, rel=1e-3
        )


class TestFeedbackAndUptake:
    def test_the_feedback_term_is_one_with_no_end_product_and_a_half_at_ki(
        self,
    ) -> None:
        # Ki^n / (Ki^n + F^n) is 1 at F = 0 and 1/2 at F = Ki, for every n.
        # Those two points are what make Ki readable as "the concentration
        # giving half inhibition" rather than as a fitted opaque constant.
        network = _one(ALLOSTERIC_FEEDBACK, "committed")
        common = {
            "committed_kcat": 100.0, "committed_Km": 0.1,
            "committed_Ki": 0.05, "committed_n": 3.0,
            "committed_E": 1e-3, "committed_S": 1.0,
        }
        free = _derivatives(network, {**common, "committed_F": 0.0})
        half = _derivatives(network, {**common, "committed_F": 0.05})
        uninhibited = 100.0 * 1e-3 * 1.0 / (0.1 + 1.0)
        assert free["committed_P"] == pytest.approx(uninhibited, rel=1e-12)
        assert half["committed_P"] == pytest.approx(uninhibited / 2.0, rel=1e-12)

    def test_a_sharper_exponent_makes_the_feedback_sharper(self) -> None:
        # n is what turns a sagging hyperbola into a setpoint. At twice Ki,
        # a larger n must shut the step down harder; if it did not, the
        # exponent would be decoration.
        network = _one(ALLOSTERIC_FEEDBACK, "committed")
        common = {
            "committed_kcat": 100.0, "committed_Km": 0.1,
            "committed_Ki": 0.05, "committed_E": 1e-3,
            "committed_S": 1.0, "committed_F": 0.1,
        }
        shallow = _derivatives(network, {**common, "committed_n": 1.0})
        steep = _derivatives(network, {**common, "committed_n": 4.0})
        assert steep["committed_P"] < shallow["committed_P"]

    def test_uptake_moves_one_ion_per_solute(self) -> None:
        # The stoichiometry is the claim. An uptake step that carried the
        # ion as a modifier would accumulate the solute for free, which is
        # what the motif's basis says it refuses to do.
        network = _one(TRANSPORTER_LIMITED_UPTAKE, "uptake")
        rates = _derivatives(network, {
            "uptake_kcat": 10.0, "uptake_Kt": 0.01, "uptake_Kh": 1e-4,
            "uptake_T": 1e-3,
            "uptake_S_out": 1.0, "uptake_S_in": 0.0,
            "uptake_H_out": 1e-4, "uptake_H_in": 1e-4,
        })
        assert rates["uptake_S_in"] == pytest.approx(-rates["uptake_S_out"], rel=1e-12)
        assert rates["uptake_H_out"] == pytest.approx(rates["uptake_S_out"], rel=1e-12)
        assert rates["uptake_S_in"] > 0.0

    def test_the_ceiling_is_the_ion_gradient_and_the_check_refuses_above_it(
        self,
    ) -> None:
        # A tenfold ion gradient buys a tenfold accumulation for a 1:1
        # symport, and no more.
        assert symport_ceiling(1e-4, 1e-5) == pytest.approx(10.0)
        assert check_symport_gradient(9.0, 1.0, 1e-4, 1e-5) is None
        with pytest.raises(ThermodynamicError, match="irreversible"):
            check_symport_gradient(11.0, 1.0, 1e-4, 1e-5)

    def test_a_two_to_one_symport_squares_the_ceiling(self) -> None:
        assert symport_ceiling(1e-4, 1e-5, ions_per_solute=2) == pytest.approx(100.0)

    def test_the_membrane_potential_is_an_argument_and_not_an_invention(self) -> None:
        # Default 1.0 means "no potential term", which makes the ceiling a
        # LOWER bound rather than a guess. A caller with a measured
        # potential can raise it; nothing here computes one.
        bare = symport_ceiling(1e-4, 1e-5)
        driven = symport_ceiling(1e-4, 1e-5, potential_factor=5.0)
        assert driven == pytest.approx(5.0 * bare)


class TestPathwaySegments:
    def test_equilibrium_constants_multiply_along_a_segment(self) -> None:
        # Free energies add, so equilibrium constants multiply. Three
        # tenfold steps make a thousandfold segment.
        assert segment_equilibrium_constant([10.0, 10.0, 10.0]) == pytest.approx(1000.0)

    def test_an_empty_segment_has_no_equilibrium_constant(self) -> None:
        # Returning 1.0 would report a pathway somebody forgot to build as
        # poised at equilibrium.
        with pytest.raises(ThermodynamicError, match="zero steps"):
            segment_equilibrium_constant([])

    def test_end_concentrations_past_the_overall_keq_are_refused(self) -> None:
        assert check_segment_drive([10.0, 10.0], 1.0, 50.0) is None
        with pytest.raises(ThermodynamicError, match="equilibrium constant"):
            check_segment_drive([10.0, 10.0], 1.0, 150.0)

    def test_chaining_shares_the_intermediates(self) -> None:
        composition = Composition("three_step")
        placed = linear_pathway(composition, 3, prefix="s")
        assert len(placed) == 3
        # Step 1's product IS step 2's substrate -- one species, not two
        # that happen to be named alike. If they were duplicated the model
        # would run and conserve nothing.
        assert placed[0].species_for("P") == placed[1].species_for("S")
        assert placed[1].species_for("P") == placed[2].species_for("S")
        assert len(composition.species_ids) == 3 + 1 + 3  # S, 2 intermediates, P, 3 enzymes

    def test_consecutive_steps_get_their_own_enzymes_unless_asked(self) -> None:
        shared_off = Composition("distinct")
        steps = linear_pathway(shared_off, 2, prefix="s")
        assert steps[0].species_for("E") != steps[1].species_for("E")

        shared_on = Composition("shared")
        both = linear_pathway(shared_on, 2, prefix="s", shared_enzyme=True)
        assert both[0].species_for("E") == both[1].species_for("E")

    def test_a_segment_of_zero_steps_is_refused(self) -> None:
        with pytest.raises(CompositionError, match="not a segment"):
            linear_pathway(Composition("empty"), 0)


class TestEveryMotifBalances:
    """Dimensional checking, at composition time, on every motif here.

    A rate law that does not balance still parses, still compiles and still
    integrates; the trajectory is simply wrong by whatever factor the
    mistake introduced. There is no later point at which that shows up.
    """

    @pytest.mark.parametrize("name", sorted(METABOLIC_LIBRARY))
    def test_the_motif_has_no_unit_findings(self, name: str) -> None:
        composition = Composition(f"units_{name}")
        composition.add(METABOLIC_LIBRARY[name], "m")
        findings = composition.unit_findings()
        assert findings == (), [
            f"{getattr(f, 'where', '?')}: {getattr(f, 'detail', f)}" for f in findings
        ]

    def test_the_aliased_reversible_motif_balances_too(self) -> None:
        # It is re-exported, not redefined, so nothing here changed it --
        # but this module puts it in front of callers under a new name, and
        # a name this module ships is a name this module is answerable for.
        composition = Composition("units_alias")
        composition.add(REVERSIBLE_MICHAELIS_MENTEN, "m")
        assert composition.unit_findings() == ()

    @pytest.mark.parametrize("name", sorted(METABOLIC_LIBRARY))
    def test_a_composed_pair_still_balances(self, name: str) -> None:
        # One motif in isolation cannot show a mM/uM clash between two.
        # Every motif here is declared in mM, and this is what pins it.
        composition = Composition(f"pair_{name}")
        composition.add(METABOLIC_LIBRARY[name], "a")
        composition.add(LINEAR_PATHWAY_SEGMENT, "b")
        assert composition.unit_findings() == ()


class TestProvenanceOfEveryNumber:
    """Nothing here is a measurement and nothing here is lumped."""

    @pytest.mark.parametrize("name", sorted(METABOLIC_LIBRARY))
    def test_every_resolvable_default_says_it_is_a_placeholder(self, name: str) -> None:
        # The default of a resolvable parameter is a number the pipeline
        # will go and replace. One that does not say so reads as a value
        # somebody stood behind.
        missing = [
            parameter.name
            for parameter in METABOLIC_LIBRARY[name].parameters
            if parameter.resolvable and "placeholder" not in parameter.description.lower()
        ]
        assert missing == []

    @pytest.mark.parametrize("name", sorted(METABOLIC_LIBRARY))
    def test_no_parameter_here_is_a_concentration(self, name: str) -> None:
        """A concentration is never resolvable, and never a parameter here.

        Amounts belong to species, where they are the caller's. A
        concentration wearing a parameter's clothes is what sends a scout
        to look for how much enzyme is in somebody else's tube.
        """
        kinds = {p.kind for p in METABOLIC_LIBRARY[name].parameters}
        assert KIND_CONCENTRATION not in kinds

    @pytest.mark.parametrize("name", sorted(METABOLIC_LIBRARY))
    def test_no_parameter_here_is_a_lumped_maximal_rate(self, name: str) -> None:
        # Vmax = kcat * [E]0 mixes a measurement with a scenario choice and
        # can never be resolved (ADR 0013). Every rate law here writes the
        # enzyme out as a species instead, and the enzyme is a PORT.
        lumped = {"vmax", "v_max", "vf", "vr", "ks", "vmax_f", "vmax_r"}
        offenders = [
            p.name for p in METABOLIC_LIBRARY[name].parameters
            if p.name.lower() in lumped
        ]
        assert offenders == []

    @pytest.mark.parametrize("name", sorted(METABOLIC_LIBRARY))
    def test_every_kind_is_one_the_pipeline_knows_how_to_treat(self, name: str) -> None:
        # A kind outside these two sets has no defined behaviour: nobody
        # searches for it and nobody may supply it.
        motif = METABOLIC_LIBRARY[name]
        assert motif.parameters, f"{name} declares no parameters at all"
        for parameter in motif.parameters:
            assert parameter.kind in RESOLVABLE_KINDS | CHOSEN_KINDS

    def test_every_enzyme_is_a_species_and_appears_in_its_rate_law(self) -> None:
        # The structural version of the no-Vmax rule: if a catalytic rate
        # law did not reference an enzyme PORT, the turnover number would
        # be doing a Vmax's job under a kcat's name.
        assert METABOLIC_LIBRARY, "the registry is empty; this test checked nothing"
        for motif in METABOLIC_LIBRARY.values():
            enzymes = {p.name for p in motif.ports_with_role("enzyme")}
            assert enzymes, f"{motif.name} has no enzyme port"
            for reaction in motif.reactions:
                assert any(
                    "{" + enzyme + "}" in reaction.rate_law for enzyme in enzymes
                ), f"{motif.name}.{reaction.name} does not use any enzyme"

    def test_the_keq_placeholder_asserts_nothing_about_direction(self) -> None:
        # Any value but 1.0 would encode a claim about which way the
        # reaction runs, which is precisely the kind of number this project
        # refuses to invent.
        keq = next(
            p for p in LINEAR_PATHWAY_SEGMENT.parameters if p.name == "Keq"
        )
        assert keq.default == 1.0
        assert keq.table is None


class TestTheRegistry:
    def test_nothing_here_redefines_a_motif_library_py_already_has(self) -> None:
        # `_refuse_duplicates` runs at import, so reaching this line already
        # proves it passed. Asserted anyway, because a guard that only fires
        # at import is invisible in a test report.
        assert set(LIBRARY) & set(METABOLIC_LIBRARY) == set()

    def test_the_full_library_is_both_and_loses_nothing(self) -> None:
        assert set(FULL_LIBRARY) == set(LIBRARY) | set(METABOLIC_LIBRARY)
        assert len(FULL_LIBRARY) == len(LIBRARY) + len(METABOLIC_LIBRARY)

    def test_every_motif_is_reachable_under_its_own_name(self) -> None:
        assert len(METABOLIC_LIBRARY) == 6
        for name, motif in METABOLIC_LIBRARY.items():
            assert metabolic_motif(name) is motif

    def test_an_unknown_name_is_refused_with_the_available_ones(self) -> None:
        # A near-miss handed back a plausible neighbour would be worse than
        # a failure, so the refusal has to carry the spelling.
        with pytest.raises(KeyError) as caught:
            metabolic_motif("reversible_michaelis_menton")
        message = str(caught.value)
        assert "branch_point" in message
        assert "reversible_michaelis_menten" in message

    def test_the_alias_table_points_at_something_real(self) -> None:
        # An empty table would make the loop below assert nothing, and the
        # alias is the whole reason this module can offer the reversible
        # law under the name the literature uses.
        assert set(ALIASES) == {"reversible_michaelis_menten"}
        for alias, target in ALIASES.items():
            assert target in FULL_LIBRARY
            assert alias not in FULL_LIBRARY
