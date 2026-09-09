"""Whether the smooth curve is the answer, and refusing to fake it when not.

Everything here is pinned against a CLOSED FORM, because a stochastic module
is the easiest place in a codebase to write a test that cannot fail: any
number is "within the noise" of something. So the immigration-death process
is used as the reference, since its stationary distribution is exactly
Poisson -- mean and variance both equal k/d -- and a sampled mean alone
would not distinguish it from a dozen wrong implementations that get the
average right and the spread wrong.

The refusals are pinned against the motif library itself rather than against
hand-written strings, so they are checked on the rate laws Terrium actually
emits: `catalytic_step` is Michaelis-Menten, `hill_repression` raises a
species to a fitted exponent, and `zero_order_degradation` consumes a
species its rate law does not mention. All three are refused, and the
mass-action motifs next to them are not -- which is what stops the refusal
tests from passing because the checker refuses everything.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import replace

import pytest

from Terium.compose.builder import Composition
from Terium.compose.library import (
    AUTOCATALYSIS, CATALYTIC_STEP, DIMERISATION, HILL_REPRESSION,
    MASS_ACTION_CONVERSION, REVERSIBLE_BINDING, SYNTHESIS_DEGRADATION,
    ZERO_ORDER_DEGRADATION,
)
from Terium.compose.stochastic import (
    AVOGADRO, DISCRETENESS_THRESHOLD, ENDED_ABSORBED, ENDED_AT_HORIZON,
    PARAMETER_UNCERTAINTY, NotMassAction, StochasticRefusal, check_mass_action,
    discreteness_matters, mass_action_problems, molecules_per_concentration,
    simulate_ssa, to_propensities,
)
from Terium.core.network import Parameter, RateRule, Reaction, ReactionNetwork, Species


#: The volume in which one nanomolar is exactly one molecule.
#:
#: 1.66 fL -- the order of a bacterial cell, which is why "1 nM is about one
#: molecule per E. coli" is a rule of thumb. Chosen so that Omega = 1 and
#: every expected count below is the concentration itself, which keeps the
#: analytic answers exact instead of exact-times-a-conversion.
ONE_MOLECULE_PER_NM = 1.0 / (1e-9 * AVOGADRO)

#: Immigration-death: birth at ks (zero order), death at kd per molecule.
#: The stationary distribution is Poisson with mean ks/kd = 24 molecules,
#: which sits just under DISCRETENESS_THRESHOLD -- deliberately, so the
#: verdict tests are about a system that really is in the regime.
BIRTH_RATE = 24.0
DEATH_RATE = 1.0
POISSON_MEAN = BIRTH_RATE / DEATH_RATE

#: Five death time constants (1/kd = 1 s). Starting AT the stationary mean,
#: the variance approaches its stationary value as 1 - exp(-2*kd*t), so five
#: leaves a shortfall of exp(-10) = 4.5e-5 -- four orders below the sampling
#: tolerance, so the burn-in is not what the test is measuring.
BURN_IN = 5.0

#: Independent trajectories behind the stationary statistics. 2000 runs of
#: about 270 events each takes ~2.5 s, and buys tolerances (below) tight
#: enough to separate a Poisson from anything that merely has the right
#: mean.
REPLICATES = 2000

#: How many standard errors a sample statistic may sit from its true value.
#:
#: The seeds are fixed, so this is not a flake budget -- the test either
#: passes or fails, always the same way. It is the SIZE of the defect the
#: test can see: at four standard errors the mean is pinned to +/-0.44
#: molecules of 24 and the variance to +/-3.1 of 24, so an implementation
#: whose spread is wrong by more than 13% cannot pass. Three would be
#: tighter and would start to fail on a different numpy's stream for no
#: defect; five would let a real error through.
SIGMAS = 4.0


def immigration_death_network() -> ReactionNetwork:
    """Birth at a constant rate, death first order. Poisson at stationarity.

    Written out as a network rather than composed from `synthesis_degradation`
    only so that ks and kd are the test's numbers rather than the library's
    illustrative ones; the two reactions are the same two reactions.
    """
    return ReactionNetwork(
        name="immigration_death",
        species=(Species("X", POISSON_MEAN),),
        parameters=(Parameter("ks", BIRTH_RATE), Parameter("kd", DEATH_RATE)),
        reactions=(
            Reaction("birth", {}, {"X": 1}, "ks"),
            Reaction("death", {"X": 1}, {}, "kd * X"),
        ),
    )


def network_of(motif, prefix: str = "m") -> ReactionNetwork:
    """One motif on its own, as a network."""
    composition = Composition("one_motif")
    composition.add(motif, prefix)
    return composition.to_network()


def with_values(network: ReactionNetwork, **values: float) -> ReactionNetwork:
    """The same network with chosen initial amounts and parameter values.

    The motif library's defaults are declared illustrative placeholders, and
    a test needs numbers that put the system at a copy number worth
    simulating. What is under test is the library's RATE LAWS and
    STOICHIOMETRY, which this does not touch.
    """
    return replace(
        network,
        species=tuple(
            Species(s.id, values.get(s.id, s.initial)) for s in network.species
        ),
        parameters=tuple(
            Parameter(p.id, values.get(p.id, p.value)) for p in network.parameters
        ),
    )


@pytest.fixture(scope="module")
def poisson_samples():
    """`REPLICATES` independent draws from the stationary distribution.

    Module-scoped because it is the expensive fixture in the file and three
    tests ask the same question of it -- the mean, the variance, and that
    they agree with each other. Safe to share: nothing mutates the list.

    Each replicate starts at the stationary mean and runs BURN_IN, so the
    final count is a draw from (very nearly) the stationary law. Replicate
    seeds come from one master generator, the same derivation
    `simulate_gillespie_ssa_replicates` uses, so the whole ensemble is
    reproducible from the single number below.
    """
    import numpy as np

    system = to_propensities(
        immigration_death_network(),
        volume=ONE_MOLECULE_PER_NM,
        concentration_unit="nM",
    )
    master = np.random.default_rng(20260908)
    seeds = [int(value) for value in master.integers(0, 2**63, size=REPLICATES)]
    return [
        simulate_ssa(system, BURN_IN, seed).final_counts()["X"] for seed in seeds
    ]


class TestAgainstAnAnalyticAnswer:
    """Immigration-death, whose stationary law is exactly Poisson(ks/kd)."""

    def test_the_volume_makes_one_nanomolar_exactly_one_molecule(self) -> None:
        # The rest of this class reads counts as concentrations, which is
        # only legitimate because Omega is 1. Asserted rather than assumed:
        # if this drifts, every "24" below silently means something else.
        system = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        assert system.molecules_per_concentration == pytest.approx(1.0, rel=1e-12)
        assert system.initial_counts == (24,)

    def test_the_stationary_mean_is_the_poisson_mean(self, poisson_samples) -> None:
        # A Poisson's mean is its parameter. The standard error of a mean of
        # n draws is sqrt(lambda/n), so this pins ks/kd to about half a
        # molecule in 24.
        tolerance = SIGMAS * math.sqrt(POISSON_MEAN / REPLICATES)
        assert statistics.fmean(poisson_samples) == pytest.approx(
            POISSON_MEAN, abs=tolerance
        )

    def test_the_stationary_variance_is_also_the_poisson_mean(
        self, poisson_samples
    ) -> None:
        """The half of the test that a wrong implementation fails.

        For a Poisson the variance EQUALS the mean, so the mean alone is a
        weak test: a deterministic solver rounded to integers, a Gaussian
        approximation with any spread at all, or a propensity that used
        n^2 where it should have used n*(n-1) can all land the average on
        24. The spread is what separates them.

        The standard error of a sample variance is
        sqrt((mu4 - sigma^4*(n-3)/(n-1)) / n), which for a Poisson is very
        nearly sqrt((lambda + 2*lambda^2)/n).
        """
        standard_error = math.sqrt(
            (POISSON_MEAN + 2 * POISSON_MEAN**2) / REPLICATES
        )
        assert statistics.variance(poisson_samples) == pytest.approx(
            POISSON_MEAN, abs=SIGMAS * standard_error
        )

    def test_the_fano_factor_is_one(self, poisson_samples) -> None:
        # Variance over mean. One is the signature of a Poisson process and
        # is what a birth-death system at stationarity must show; it is
        # stated separately because it is the quantity an experimentalist
        # measures, and because it is dimensionless and so does not depend
        # on the volume at all.
        mean = statistics.fmean(poisson_samples)
        variance = statistics.variance(poisson_samples)
        tolerance = SIGMAS * math.sqrt(
            (POISSON_MEAN + 2 * POISSON_MEAN**2) / REPLICATES
        ) / POISSON_MEAN
        assert variance / mean == pytest.approx(1.0, abs=tolerance)

    def test_no_trajectory_ever_holds_a_negative_or_fractional_count(self) -> None:
        # The property that makes this a different object from the ODE. A
        # state is a tuple of non-negative integers, always.
        system = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        trajectory = simulate_ssa(system, BURN_IN, 11)
        assert trajectory.events > 0
        for row in trajectory.counts:
            assert all(isinstance(count, int) and count >= 0 for count in row)

    def test_the_conserved_combination_is_exact_on_every_event(self) -> None:
        """M + 2D is conserved for dimerisation, and in counts it is EXACT.

        The ODE conserves it to the integrator's tolerance and
        `compose/simulate.py` measures the drift. A count trajectory has no
        tolerance to conserve it to: the stoichiometry is integer, so the
        invariant either holds in every row or the state update is wrong.
        This is the strongest available check that `orders` (what has to
        meet) and `net` (what changes) were not conflated.
        """
        network = with_values(
            network_of(DIMERISATION),
            m_M=100.0, m_D=0.0, m_kon=0.01, m_koff=1.0,
        )
        system = to_propensities(
            network, volume=ONE_MOLECULE_PER_NM, concentration_unit="nM"
        )
        monomer = system.species.index("m_M")
        dimer = system.species.index("m_D")

        trajectory = simulate_ssa(system, 2.0, 5)
        assert trajectory.events > 20, (
            "too few events to be a test of the update rule; the rate "
            "constants above no longer put this system in motion"
        )
        for row in trajectory.counts:
            assert row[monomer] + 2 * row[dimer] == 100


class TestThePropensityIsTheTextbookOne:
    """Propensities against the closed forms, with no simulation involved."""

    def test_a_zero_order_rate_becomes_events_per_time_via_the_volume(self) -> None:
        # A synthesis rate ks (concentration/time) is ks*Omega molecules per
        # time. This is the only place the volume enters a zero-order
        # reaction, and it enters linearly.
        system = to_propensities(
            immigration_death_network(),
            volume=10 * ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        birth = next(r for r in system.reactions if r.id == "birth")
        assert birth.order == 0
        assert birth.coefficient == pytest.approx(BIRTH_RATE * 10.0, rel=1e-12)

    def test_a_first_order_rate_does_not_depend_on_the_volume_at_all(self) -> None:
        # k*[X] per volume becomes k*n per time: the two factors of Omega
        # cancel. A first-order constant is the one rate constant that means
        # the same thing in both descriptions, and an implementation that
        # scaled it would be wrong in a way no dimensional check would see.
        small = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        large = to_propensities(
            immigration_death_network(),
            volume=1000 * ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        death_small = next(r for r in small.reactions if r.id == "death")
        death_large = next(r for r in large.reactions if r.id == "death")
        assert death_small.coefficient == pytest.approx(DEATH_RATE, rel=1e-12)
        assert death_large.coefficient == pytest.approx(DEATH_RATE, rel=1e-12)

    def test_a_second_order_propensity_is_kon_times_the_two_counts_over_omega(
        self,
    ) -> None:
        network = network_of(REVERSIBLE_BINDING)
        system = to_propensities(
            network, volume=1e-15, concentration_unit="mM"
        )
        omega = system.molecules_per_concentration
        association = next(r for r in system.reactions if r.id.endswith("association"))
        kon = next(p.value for p in network.parameters if p.id.endswith("kon"))

        assert association.order == 2
        assert association.coefficient == pytest.approx(kon / omega, rel=1e-12)

        counts = [0] * len(system.species)
        counts[system.species.index("m_A")] = 7
        counts[system.species.index("m_B")] = 5
        index = system.reactions.index(association)
        assert system.propensity_vector(counts)[index] == pytest.approx(
            kon * 7 * 5 / omega, rel=1e-12
        )

    def test_dimerisation_uses_a_falling_factorial_and_not_a_square(self) -> None:
        """n*(n-1), not n^2 -- a molecule cannot collide with itself.

        The two agree to O(1/n) and disagree completely where this module is
        used. At two molecules the naive form is twice the truth, and at one
        molecule it is positive for a reaction that cannot happen at all.
        """
        network = with_values(
            network_of(DIMERISATION), m_kon=0.01, m_koff=1.0,
        )
        system = to_propensities(
            network, volume=ONE_MOLECULE_PER_NM, concentration_unit="nM"
        )
        omega = system.molecules_per_concentration
        dimerise = next(r for r in system.reactions if r.id.endswith("dimerise"))
        index = system.reactions.index(dimerise)
        monomer = system.species.index("m_M")

        def propensity(count: int) -> float:
            state = [0] * len(system.species)
            state[monomer] = count
            return system.propensity_vector(state)[index]

        assert propensity(10) == pytest.approx(0.01 * 10 * 9 / omega, rel=1e-12)
        assert propensity(2) == pytest.approx(0.01 * 2 * 1 / omega, rel=1e-12)
        assert propensity(1) == 0.0
        assert propensity(0) == 0.0

    def test_a_catalyst_is_a_collision_partner_but_not_a_product(self) -> None:
        """`orders` and `net` answer different questions.

        Autocatalysis is S + X -> 2X: X takes part in the collision AND its
        count changes, by +1 rather than by the 2 in the products. Getting
        this from `products - reactants` rather than from the rate law is
        what keeps the stoichiometry and the propensity independent.
        """
        network = network_of(AUTOCATALYSIS)
        system = to_propensities(
            network, volume=1e-15, concentration_unit="mM"
        )
        reaction = system.reactions[0]
        substrate = system.species.index("m_S")
        catalyst = system.species.index("m_X")

        assert dict(reaction.orders) == {substrate: 1, catalyst: 1}
        assert dict(reaction.net) == {substrate: -1, catalyst: 1}


class TestTheMassActionRefusal:
    """The most valuable thing in the module: not simulating what it cannot."""

    def test_a_michaelis_menten_rate_law_is_refused_naming_mass_action(self) -> None:
        with pytest.raises(NotMassAction) as caught:
            to_propensities(
                network_of(CATALYTIC_STEP),
                volume=1e-15,
                concentration_unit="mM",
            )
        message = str(caught.value)
        assert "MASS-ACTION" in message
        assert "Michaelis-Menten" in message
        assert "coarse-graining" in message

    def test_the_refusal_says_what_to_write_instead(self) -> None:
        # A refusal that only says no leaves the caller where they started.
        # The mechanism the quasi-steady-state assumption replaced is a
        # model this library can already build, and the message names it.
        with pytest.raises(NotMassAction) as caught:
            to_propensities(
                network_of(CATALYTIC_STEP),
                volume=1e-15,
                concentration_unit="mM",
            )
        message = str(caught.value)
        assert "E + S <-> ES -> E + P" in message
        assert "reversible_binding" in message

    def test_a_hill_exponent_is_refused_as_not_a_number_of_molecules(self) -> None:
        with pytest.raises(NotMassAction) as caught:
            to_propensities(
                network_of(HILL_REPRESSION),
                volume=1e-15,
                concentration_unit="mM",
            )
        message = str(caught.value)
        assert "MASS-ACTION" in message
        assert "Hill coefficient" in message
        assert "integer LITERAL" in message

    def test_consuming_a_species_the_rate_law_omits_is_refused(self) -> None:
        """`zero_order_degradation` -- and the motif already says why.

        Its own basis records that the law "would drive the species
        negative". In an ODE that is a caveat about a floor; in an exact
        simulation the propensity stays positive at zero copies and the next
        event moves the count to -1, which is not a state.
        """
        with pytest.raises(NotMassAction) as caught:
            to_propensities(
                network_of(ZERO_ORDER_DEGRADATION),
                volume=1e-15,
                concentration_unit="mM",
            )
        message = str(caught.value)
        assert "does not mention it" in message
        assert "Mass action requires" in message

    def test_a_rate_rule_has_no_event_to_have_a_propensity_for(self) -> None:
        network = ReactionNetwork(
            name="driven",
            species=(Species("X", 1.0),),
            parameters=(Parameter("k", 1.0),),
            rate_rules=(RateRule("X", "-k * X"),),
        )
        problems = mass_action_problems(network)
        assert len(problems) == 1
        assert "RATE RULE" in problems[0]

    def test_every_offending_reaction_is_named_not_only_the_first(self) -> None:
        # Two Michaelis-Menten steps in one model. Told about one at a time,
        # a caller edits and re-runs; told about both, they can see the
        # model is the wrong shape for this method.
        composition = Composition("two steps")
        composition.add(CATALYTIC_STEP, "first")
        composition.add(CATALYTIC_STEP, "second")
        problems = mass_action_problems(composition.to_network())
        assert len(problems) == 2
        assert any("first_catalysis" in problem for problem in problems)
        assert any("second_catalysis" in problem for problem in problems)

    def test_the_mass_action_motifs_are_not_refused(self) -> None:
        """The test that stops the ones above from being free.

        A checker that refused everything would pass every refusal test in
        this class. These five library motifs are mass action and must come
        back clean.
        """
        for motif in (
            MASS_ACTION_CONVERSION, SYNTHESIS_DEGRADATION, REVERSIBLE_BINDING,
            DIMERISATION, AUTOCATALYSIS,
        ):
            assert mass_action_problems(network_of(motif)) == (), motif.name
            check_mass_action(network_of(motif))


class TestTheVolumeIsRequired:
    """A stochastic result at an unstated volume is not a result."""

    def test_omitting_the_volume_is_a_type_error(self) -> None:
        # Not a default, not a guess, not a warning. The noise magnitude is
        # set entirely by the copy number and the copy number is set
        # entirely by this.
        with pytest.raises(TypeError):
            to_propensities(
                immigration_death_network(), concentration_unit="nM"
            )

    def test_omitting_the_concentration_unit_is_a_type_error(self) -> None:
        # mM and uM are dimensionally identical and differ by a thousand in
        # copy number, so a default here would be a silent factor of 1000.
        with pytest.raises(TypeError):
            to_propensities(
                immigration_death_network(), volume=ONE_MOLECULE_PER_NM
            )

    def test_discreteness_also_refuses_to_guess_the_volume(self) -> None:
        with pytest.raises(TypeError):
            discreteness_matters(
                immigration_death_network(), concentration_unit="nM"
            )

    def test_the_conversion_is_the_volume_times_avogadro(self) -> None:
        # One molar in one litre is a mole. Everything else in the module
        # is this number scaled.
        assert molecules_per_concentration(1.0, "M") == pytest.approx(
            AVOGADRO, rel=1e-15
        )
        assert molecules_per_concentration(1e-15, "nM") == pytest.approx(
            1e-15 * 1e-9 * AVOGADRO, rel=1e-12
        )
        # The rule of thumb this makes exact: 1 nM is about one molecule in
        # a bacterium-sized volume.
        assert molecules_per_concentration(
            ONE_MOLECULE_PER_NM, "nM"
        ) == pytest.approx(1.0, rel=1e-12)

    def test_a_thousandfold_volume_is_a_thousandfold_copy_number(self) -> None:
        small = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        large = to_propensities(
            immigration_death_network(),
            volume=1000 * ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        assert small.initial_counts == (24,)
        assert large.initial_counts == (24000,)

    def test_a_zero_or_negative_volume_is_refused(self) -> None:
        for volume in (0.0, -1e-15, float("inf")):
            with pytest.raises(StochasticRefusal):
                molecules_per_concentration(volume, "nM")

    def test_a_time_is_not_a_concentration(self) -> None:
        with pytest.raises(StochasticRefusal) as caught:
            molecules_per_concentration(1e-15, "1/s")
        assert "not a concentration" in str(caught.value)

    def test_a_species_that_rounds_to_no_molecules_is_refused(self) -> None:
        """Half a molecule is not a small amount, it is a different model.

        Rounded silently to zero, every reaction this species takes part in
        switches off and the run looks completely normal.
        """
        network = with_values(immigration_death_network(), X=0.4)
        with pytest.raises(StochasticRefusal) as caught:
            to_propensities(
                network, volume=ONE_MOLECULE_PER_NM, concentration_unit="nM"
            )
        message = str(caught.value)
        assert "rounds to zero" in message
        # And it says the volume at which the species would be one molecule,
        # so the caller has a number to act on rather than an instruction to
        # try something bigger.
        assert "L, where this species is" in message


class TestTheSameSeedGivesTheSameTrajectory:
    """An unreproducible stochastic result is not evidence."""

    def test_two_runs_with_one_seed_are_identical(self) -> None:
        system = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        first = simulate_ssa(system, BURN_IN, 4242)
        second = simulate_ssa(system, BURN_IN, 4242)
        assert first.times == second.times
        assert first.counts == second.counts
        assert first.events == second.events

    def test_a_different_seed_is_a_different_realisation(self) -> None:
        # Otherwise the seed would not be doing anything and the test above
        # would pass for a deterministic stub.
        system = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        first = simulate_ssa(system, BURN_IN, 4242)
        other = simulate_ssa(system, BURN_IN, 4243)
        assert first.counts != other.counts

    def test_the_seed_is_carried_on_the_trajectory(self) -> None:
        system = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        trajectory = simulate_ssa(system, BURN_IN, 4242)
        assert trajectory.seed == 4242
        assert str(4242) in trajectory.summary()


class TestHowARunEnds:
    def test_a_run_that_reaches_the_horizon_says_so(self) -> None:
        system = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        trajectory = simulate_ssa(system, BURN_IN, 7)
        assert trajectory.ended == ENDED_AT_HORIZON
        assert trajectory.times[-1] == BURN_IN

    def test_a_run_with_nothing_left_to_do_says_something_different(self) -> None:
        """Pure death with no birth ends absorbed, not out of time.

        The two have identical last rows and completely different meanings,
        so the reason is carried rather than inferred: 26 molecules decaying
        at 5/s are gone long before t=100, and the run stopped because the
        total propensity reached zero.
        """
        network = ReactionNetwork(
            name="pure_death",
            species=(Species("X", 26.0),),
            parameters=(Parameter("kd", 5.0),),
            reactions=(Reaction("death", {"X": 1}, {}, "kd * X"),),
        )
        system = to_propensities(
            network, volume=ONE_MOLECULE_PER_NM, concentration_unit="nM"
        )
        trajectory = simulate_ssa(system, 100.0, 3)
        assert trajectory.ended == ENDED_ABSORBED
        assert trajectory.final_counts() == {"X": 0}
        assert trajectory.events == 26

    def test_hitting_the_event_ceiling_is_refused_not_truncated(self) -> None:
        # A truncated trajectory has a final state that looks like an
        # answer, and an ensemble of them is biased in a direction nothing
        # in the output shows.
        system = to_propensities(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        with pytest.raises(StochasticRefusal) as caught:
            simulate_ssa(system, BURN_IN, 9, max_events=5)
        assert "ceiling of 5 events" in str(caught.value)


class TestDiscretenessMatters:
    """The check that says whether the deterministic answer can be trusted."""

    def test_the_threshold_is_where_the_fluctuation_meets_the_uncertainty(
        self,
    ) -> None:
        # DERIVED, not chosen: 1/sqrt(N) < 0.2 exactly when N > 25. If
        # either constant is edited without the other, this fails.
        assert 1.0 / math.sqrt(DISCRETENESS_THRESHOLD) == pytest.approx(
            PARAMETER_UNCERTAINTY, rel=1e-12
        )

    def test_the_copy_number_is_the_steady_state_times_the_volume(self) -> None:
        # dX/dt = ks - kd*X settles at ks/kd = 24 nM, which in this volume
        # is 24 molecules. Both halves are exact.
        report = discreteness_matters(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        assert report.minimum_species == "X"
        assert report.minimum == pytest.approx(POISSON_MEAN, rel=1e-6)
        assert report.relative_fluctuation == pytest.approx(
            1.0 / math.sqrt(POISSON_MEAN), rel=1e-6
        )
        assert report.matters is True

    def test_a_thousandfold_larger_volume_does_not_need_the_ssa(self) -> None:
        # Same model, same concentrations, same kinetics: only the volume
        # changed, and with it the entire verdict. That is the argument for
        # the volume being required in one assertion.
        report = discreteness_matters(
            immigration_death_network(),
            volume=1000 * ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        assert report.minimum == pytest.approx(1000 * POISSON_MEAN, rel=1e-6)
        assert report.matters is False
        assert "weaker claim" in report.summary()

    def test_it_diagnoses_a_model_it_would_refuse_to_simulate(self) -> None:
        """Diagnosis and treatment are separate on purpose.

        A Michaelis-Menten model has no propensities, so it cannot be
        simulated exactly -- but the most useful thing to tell its author is
        that the enzyme is at 32 copies, at which point the
        quasi-steady-state assumption behind that rate law has already
        failed. So `discreteness_matters` runs on any network and
        `to_propensities` refuses this one.

        Steady state: ks = kcat*E*X/(Km + X) with kcat*E = 48 and Km = 24
        gives X = 24 exactly, and the enzyme sits above it at 32.
        """
        network = ReactionNetwork(
            name="saturating_removal",
            species=(Species("X", 24.0), Species("E", 32.0)),
            parameters=(
                Parameter("ks", 24.0),
                Parameter("kcat", 1.5),
                Parameter("Km", 24.0),
            ),
            reactions=(
                Reaction("birth", {}, {"X": 1}, "ks"),
                Reaction("removal", {"X": 1}, {}, "kcat * E * X / (Km + X)"),
            ),
        )
        report = discreteness_matters(
            network, volume=ONE_MOLECULE_PER_NM, concentration_unit="nM"
        )
        assert report.minimum == pytest.approx(24.0, rel=1e-6)
        assert report.minimum_species == "X"

        with pytest.raises(NotMassAction):
            to_propensities(
                network, volume=ONE_MOLECULE_PER_NM, concentration_unit="nM"
            )

    def test_a_system_with_no_steady_state_is_refused(self) -> None:
        """A source and no sink has no resting level, and none is invented.

        Reporting the copy number at the initial condition and calling it
        the steady state would answer a question nobody asked with a number
        that looks like the one they wanted.
        """
        network = ReactionNetwork(
            name="inflow_only",
            species=(Species("S", 0.0),),
            parameters=(Parameter("v_in", 1.0),),
            reactions=(Reaction("inflow", {}, {"S": 1}, "v_in"),),
        )
        with pytest.raises(StochasticRefusal) as caught:
            discreteness_matters(
                network, volume=ONE_MOLECULE_PER_NM, concentration_unit="nM"
            )
        message = str(caught.value)
        assert "no stable steady state was found" in message
        assert "simulate_ssa" in message

    def test_the_summary_says_what_it_does_not_claim(self) -> None:
        # A threshold on the mean says nothing about rare events, and a
        # report that let a reader think otherwise would be worse than none.
        report = discreteness_matters(
            immigration_death_network(),
            volume=ONE_MOLECULE_PER_NM,
            concentration_unit="nM",
        )
        summary = report.summary()
        assert "Rare events" in summary
        assert "never reach zero" in summary
