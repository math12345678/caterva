"""The transport motifs, tested against the answers transport theory fixes.

WHY THESE TESTS ARE ARITHMETIC AND NOT PLOTS
--------------------------------------------
Each mechanism here is separated from its neighbours by where it STOPS, and
every one of those stopping points is a number a test can compute without
running the code under test:

    facilitated diffusion   ceiling kcat*[T] at saturating cis and empty
                            trans; exactly half of it at Out = Kt; exactly
                            zero at Out = In, and negative past it
    passive leak            equal concentrations, whatever the volumes,
                            and an approach that is a single exponential
                            with rate constant k*(1 + 1/volume_ratio)
    symport                 zero flux exactly when A_out*S_out = A_in*S_in,
                            which is why it carries cargo uphill
    antiport                zero flux exactly when A_out*B_in = A_in*B_out
    pump                    zero without ATP, and -- the limitation its
                            basis names -- the SAME rate against a gradient
                            of any steepness
    internalisation         the receptor comes back as
                            k_rec/(k_rec + k_deg) of what went in

WHY THE RATES COME THROUGH derivative_function
-----------------------------------------------
Following `test_compose_library_enzymology`: a test could re-implement each
rate law and compare, and would pass with a motif whose law was never
compiled, never validated by `ReactionNetwork` and never wired to the right
species -- the three things that actually go wrong.
`analysis.derivative_function` is the path the analysis and sensitivity
modules take, so a rate read through it is a rate the rest of the package
would see.

WHY THE INTEGRATOR IS FOUR LINES OF RUNGE-KUTTA
-----------------------------------------------
Two tests need a time course rather than a derivative: the leak's
equilibrium and the recycled fraction. Both are linear systems with time
constants of minutes, so a fixed-step RK4 at a fraction of that is exact to
far better than the tolerances asserted, and it keeps these tests
independent of which solver is installed. Nothing here is testing the
integrator.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, List, Tuple

import pytest

from caterva.compose.analysis import derivative_function
from caterva.compose.builder import Composition
from caterva.compose.library import FACILITATED_TRANSPORT, LIBRARY
from caterva.compose.library_transport import (
    ANTIPORT, FACILITATED_DIFFUSION, FULL_LIBRARY, PASSIVE_LEAK,
    PRIMARY_ACTIVE_TRANSPORT, RECEPTOR_LIGAND_INTERNALIZATION, SYMPORT,
    TRANSPORT_LIBRARY, TransportMotifWithheld, VOLUME_RATIO, WITHHELD,
    transport_motif,
)
from caterva.compose.motifs import (
    CHOSEN_KINDS, KIND_CONCENTRATION, RESOLVABLE_KINDS,
)
from caterva.compose.units import UnitError, check_rate_law, parse_unit
from caterva.core.network import describe_conservation_laws


# -- machinery ---------------------------------------------------------------


def _probe(motif, prefix="m", **values):
    """One motif alone in a composition, with its parameters set.

    Values are pushed onto the built network with `dataclasses.replace`
    rather than into the motif, because a motif's defaults are illustrative
    placeholders shared by every test in the process and mutating one here
    would silently change another. Borrowed wholesale from
    `test_compose_library_enzymology`, so the two files fail the same way.
    """
    composition = Composition(f"probe {motif.name}")
    composition.add(motif, prefix)
    network = composition.to_network()
    ids = {f"{prefix}_{name}": value for name, value in values.items()}
    unknown = set(ids) - {p.id for p in network.parameters}
    if unknown:
        raise AssertionError(
            f"the test set {sorted(unknown)}, which {motif.name} has no "
            f"parameter for. It has "
            f"{sorted(p.id for p in network.parameters)}."
        )
    return replace(
        network,
        parameters=tuple(
            replace(p, value=float(ids[p.id])) if p.id in ids else p
            for p in network.parameters
        ),
    )


def _rate(network, target, **state):
    """d[target]/dt at a state, through the package's own compiled rate laws.

    Species not named keep the network's declared initial rather than
    dropping to zero: a silent zero for the carrier would make every rate
    zero and every comparison trivially true.
    """
    rhs, order = derivative_function(network)
    initial = {s.id: s.initial for s in network.species}
    unknown = set(state) - set(order)
    if unknown:
        raise AssertionError(
            f"the test set {sorted(unknown)}, which this network has no "
            f"species for. It has {sorted(order)}."
        )
    point = [float(state.get(name, initial[name])) for name in order]
    return rhs(point)[order.index(target)]


def _time_course(
    network, *, dt: float, steps: int, every: int = 1, **initial
) -> List[Tuple[float, Dict[str, float]]]:
    """(time, state) samples from fixed-step RK4 over the emitted network."""
    rhs, order = derivative_function(network)
    declared = {s.id: s.initial for s in network.species}
    unknown = set(initial) - set(order)
    if unknown:
        raise AssertionError(
            f"the test set {sorted(unknown)}, which this network has no "
            f"species for. It has {sorted(order)}."
        )
    state = [float(initial.get(name, declared[name])) for name in order]

    def step(current: List[float]) -> List[float]:
        k1 = rhs(current)
        a = [x + 0.5 * dt * d for x, d in zip(current, k1)]
        k2 = rhs(a)
        b = [x + 0.5 * dt * d for x, d in zip(current, k2)]
        k3 = rhs(b)
        c = [x + dt * d for x, d in zip(current, k3)]
        k4 = rhs(c)
        return [
            x + dt * (p + 2 * q + 2 * r + s) / 6.0
            for x, p, q, r, s in zip(current, k1, k2, k3, k4)
        ]

    samples = [(0.0, dict(zip(order, state)))]
    for index in range(steps):
        state = step(state)
        if (index + 1) % every == 0:
            samples.append((dt * (index + 1), dict(zip(order, state))))
    return samples


def _net_stoichiometry(motif) -> Dict[str, int]:
    """Port -> (produced - consumed), summed over the motif's reactions.

    A translocation is written as two half-reactions (see the module
    docstring of `library_transport`), so "what does this motif do to the
    outside pool" is a question about the pair rather than about either
    half.
    """
    net: Dict[str, int] = {}
    for reaction in motif.reactions:
        for port, count in reaction.reactants.items():
            net[port] = net.get(port, 0) - int(count)
        for port, count in reaction.products.items():
            net[port] = net.get(port, 0) + int(count)
    return net


#: The motifs that move something between the two compartments, and are
#: therefore the ones a volume ratio applies to.
ACROSS_THE_MEMBRANE = (
    PASSIVE_LEAK, FACILITATED_DIFFUSION, SYMPORT, ANTIPORT,
    PRIMARY_ACTIVE_TRANSPORT,
)


# -- stoichiometry: does the motif do what its name says ---------------------


class TestStoichiometryMatchesTheName:
    """The claim in the name, checked against the reactions.

    A symporter whose two solutes went opposite ways would still simulate,
    still balance dimensionally and still saturate. The only thing wrong
    with it would be that it was an antiporter.
    """

    def test_symport_moves_both_solutes_the_same_way(self) -> None:
        outer = next(
            r for r in SYMPORT.reactions if r.name == "loading_at_the_outer_face"
        )
        inner = next(
            r for r in SYMPORT.reactions
            if r.name == "release_at_the_inner_face"
        )
        # Both solutes leave the outside, on the same reaction.
        assert outer.reactants == {"A_out": 1, "S_out": 1}
        assert outer.products == {}
        # Both arrive inside, on the same reaction.
        assert inner.reactants == {}
        assert inner.products == {"A_in": 1, "S_in": 1}
        # And the pair, summed: outside down, inside up, for both.
        net = _net_stoichiometry(SYMPORT)
        assert net["A_out"] == -1 and net["S_out"] == -1
        assert net["A_in"] == +1 and net["S_in"] == +1

    def test_antiport_moves_the_two_solutes_opposite_ways(self) -> None:
        outer = next(
            r for r in ANTIPORT.reactions
            if r.name == "exchange_at_the_outer_face"
        )
        inner = next(
            r for r in ANTIPORT.reactions
            if r.name == "exchange_at_the_inner_face"
        )
        # A leaves the outside and B arrives there, one for one.
        assert outer.reactants == {"A_out": 1}
        assert outer.products == {"B_out": 1}
        # Inside, the exchange runs the other way.
        assert inner.reactants == {"B_in": 1}
        assert inner.products == {"A_in": 1}
        net = _net_stoichiometry(ANTIPORT)
        assert net["A_out"] == -1 and net["A_in"] == +1
        assert net["B_in"] == -1 and net["B_out"] == +1
        # The signs are opposed, which is the whole difference from symport.
        assert net["A_in"] == -net["B_in"]
        assert net["A_out"] == -net["B_out"]

    def test_the_two_motifs_disagree_only_about_which_way_the_second_goes(
        self,
    ) -> None:
        # Stated as a comparison because that is how a reader tells them
        # apart: the driver does the same thing in both, and the partner
        # does the opposite.
        symport = _net_stoichiometry(SYMPORT)
        antiport = _net_stoichiometry(ANTIPORT)
        assert symport["A_out"] == antiport["A_out"] == -1
        assert symport["A_in"] == antiport["A_in"] == +1
        assert symport["S_out"] == -antiport["B_out"]
        assert symport["S_in"] == -antiport["B_in"]

    def test_the_pump_spends_one_atp_for_every_solute_it_moves(self) -> None:
        net = _net_stoichiometry(PRIMARY_ACTIVE_TRANSPORT)
        assert net["In"] == -1 and net["Out"] == +1
        assert net["ATP"] == -1 and net["ADP"] == +1
        # The pump itself is a modifier of both halves, never consumed.
        assert "Pump" not in net
        for reaction in PRIMARY_ACTIVE_TRANSPORT.reactions:
            assert "Pump" in reaction.modifiers


# -- facilitated diffusion, against its analytic signature -------------------


class TestFacilitatedDiffusionSaturates:
    """A carrier has a ceiling and a pore does not.

    kcat and [T] are set to 1 here so that the ceiling is 1 and every
    number below is the fraction of it, which is the quantity the claims
    are actually about.
    """

    def _network(self, **parameters):
        network = _probe(FACILITATED_DIFFUSION, "fd", kcat=1.0, Kt=1.0, **parameters)
        return replace(
            network,
            species=tuple(
                replace(s, initial=1.0) if s.id == "fd_T" else s
                for s in network.species
            ),
        )

    def test_the_flux_climbs_to_the_ceiling_and_never_past_it(self) -> None:
        network = self._network()
        ceiling = 1.0  # kcat * [T]
        rates = [
            _rate(network, "fd_In", fd_Out=out, fd_In=0.0)
            for out in (1e-2, 1e0, 1e2, 1e4, 1e6, 1e8)
        ]
        for lower, higher in zip(rates, rates[1:]):
            assert higher > lower, "the flux stopped being monotone in Out"
        for rate in rates:
            assert rate < ceiling, "a carrier flux exceeded kcat * [T]"
        # Within a part in ten thousand of the ceiling four orders past Kt.
        assert rates[-2] == pytest.approx(ceiling, rel=1e-4)
        assert rates[-1] == pytest.approx(ceiling, rel=1e-6)

    def test_half_the_ceiling_at_exactly_the_half_saturation_constant(
        self,
    ) -> None:
        # The definition of Kt, and the reason it is the OPERATIONAL
        # constant rather than a microscopic dissociation constant.
        network = self._network()
        assert _rate(network, "fd_In", fd_Out=1.0, fd_In=0.0) == pytest.approx(0.5)

    def test_it_is_first_order_far_below_the_half_saturation(self) -> None:
        # v -> kcat*[T]*Out/Kt as Out -> 0, which is the regime where a
        # carrier is indistinguishable from a leak.
        network = self._network()
        for out in (1e-6, 1e-5, 1e-4):
            assert _rate(network, "fd_In", fd_Out=out, fd_In=0.0) == pytest.approx(
                out, rel=1e-3
            )

    def test_it_stalls_at_equal_concentrations_and_reverses_past_them(
        self,
    ) -> None:
        """The property `library.facilitated_transport` does not have.

        Nothing pays for this movement, so it cannot end anywhere but at
        equal concentrations -- and the existing motif's law has no `In` in
        it at all, so it carries solute up a gradient of any size for ever.
        """
        network = self._network()
        for both in (0.1, 1.0, 100.0):
            assert _rate(network, "fd_In", fd_Out=both, fd_In=both) == 0.0
        assert _rate(network, "fd_In", fd_Out=1.0, fd_In=5.0) < 0.0
        # The motif it is being contrasted with, for the record: its rate
        # law does not mention the inside concentration at all, which is
        # what makes it the zero-trans limit and not an equilibrating one.
        existing = FACILITATED_TRANSPORT.reactions[0].rate_law
        assert "{In}" not in existing
        assert "{In}" in FACILITATED_DIFFUSION.reactions[0].rate_law


# -- passive leak, against the closed form -----------------------------------


class TestPassiveLeakEquilibrates:
    def test_equal_concentrations_are_a_fixed_point(self) -> None:
        # Exact, for every value and every volume ratio: the driving force
        # is the difference, so both halves vanish together.
        network = _probe(PASSIVE_LEAK, "leak", k_leak=0.01, volume_ratio=7.0)
        assert _rate(network, "leak_In", leak_Out=3.0, leak_In=3.0) == 0.0
        assert _rate(network, "leak_Out", leak_Out=3.0, leak_In=3.0) == 0.0

    def test_the_time_course_is_the_analytic_exponential(self) -> None:
        """Both compartments, against the closed form, at equal volumes.

        Out(t) = 0.5*(1 + exp(-2*k*t)) and In(t) = 0.5*(1 - exp(-2*k*t))
        from Out(0) = 1, In(0) = 0. The rate constant of the approach is
        2*k and not k, because both compartments move.
        """
        k = 0.01
        network = _probe(PASSIVE_LEAK, "leak", k_leak=k, volume_ratio=1.0)
        course = _time_course(
            network, dt=0.5, steps=800, every=100, leak_Out=1.0, leak_In=0.0
        )
        for time, state in course:
            decay = math.exp(-2.0 * k * time)
            assert state["leak_Out"] == pytest.approx(0.5 * (1 + decay), abs=1e-9)
            assert state["leak_In"] == pytest.approx(0.5 * (1 - decay), abs=1e-9)
        # And where it ends up: equal, at the mean of where it started.
        final = course[-1][1]
        assert final["leak_Out"] == pytest.approx(0.5, abs=1e-3)
        assert final["leak_In"] == pytest.approx(0.5, abs=1e-3)

    def test_unequal_volumes_still_end_equal_but_somewhere_else(self) -> None:
        """What the volume ratio is FOR.

        With the outside four times the inside, the same total substance
        settles at 4*c + c = 4*1.0, so both compartments end at 0.8 rather
        than at 0.5. A model that ignored the ratio would report 0.5 and
        would look exactly as convincing.
        """
        network = _probe(PASSIVE_LEAK, "leak", k_leak=0.01, volume_ratio=4.0)
        course = _time_course(
            network, dt=0.5, steps=4000, every=500, leak_Out=1.0, leak_In=0.0
        )
        final = course[-1][1]
        assert final["leak_Out"] == pytest.approx(0.8, abs=1e-4)
        assert final["leak_In"] == pytest.approx(0.8, abs=1e-4)

    def test_moles_are_conserved_even_though_the_stoichiometry_cannot_say_so(
        self,
    ) -> None:
        """The cost of the two-half-reaction form, measured.

        `volume_ratio*Out + In` is exactly constant -- that is the mole
        balance -- while `Out + In` is not, because concentration is not
        what is conserved when the volumes differ. And the network derives
        NO conservation law over the pair, because the left null space of
        two half-reactions is empty: the invariant is enforced by the two
        rate laws agreeing, not by the stoichiometry, so
        `simulate.check_invariants` has nothing to check here.
        """
        ratio = 4.0
        network = _probe(PASSIVE_LEAK, "leak", k_leak=0.01, volume_ratio=ratio)
        course = _time_course(
            network, dt=0.5, steps=4000, every=250, leak_Out=1.0, leak_In=0.0
        )
        moles = [ratio * s["leak_Out"] + s["leak_In"] for _, s in course]
        for value in moles:
            assert value == pytest.approx(ratio, rel=1e-9)
        concentration = [s["leak_Out"] + s["leak_In"] for _, s in course]
        assert max(concentration) - min(concentration) > 0.5
        assert describe_conservation_laws(network) == []


# -- secondary active transport, against its stalling point ------------------


class TestSymportRunsOnTheDriversGradient:
    def test_it_stalls_exactly_where_the_products_match(self) -> None:
        # Zero flux when A_out*S_out = A_in*S_in, for every set of values
        # that satisfies it -- not merely when each solute is balanced.
        network = _probe(SYMPORT, "sym", kcat=1.0, Ka=10.0, Ks=0.1)
        for a_out, s_out, a_in, s_in in (
            (100.0, 0.1, 10.0, 1.0),
            (100.0, 1.0, 1.0, 100.0),
            (5.0, 5.0, 5.0, 5.0),
            (0.4, 2.5, 2.0, 0.5),
        ):
            assert _rate(
                network, "sym_S_in",
                sym_A_out=a_out, sym_S_out=s_out,
                sym_A_in=a_in, sym_S_in=s_in,
            ) == pytest.approx(0.0, abs=1e-12)

    def test_it_carries_the_cargo_uphill_while_the_driver_runs_downhill(
        self,
    ) -> None:
        """The reason a symporter is worth having as its own motif.

        The cargo is ten times more concentrated INSIDE and still moves in,
        because the product on the outside is the larger one. Nothing was
        told to do this; it is the sign of A_out*S_out - A_in*S_in.
        """
        network = _probe(SYMPORT, "sym", kcat=1.0, Ka=10.0, Ks=0.1)
        uphill = dict(
            sym_A_out=100.0, sym_A_in=1.0, sym_S_out=0.1, sym_S_in=1.0
        )
        assert _rate(network, "sym_S_in", **uphill) > 0.0
        # ... and the driver is paying for it, one for one.
        assert _rate(network, "sym_A_in", **uphill) == pytest.approx(
            _rate(network, "sym_S_in", **uphill)
        )
        # Take the driver's gradient away and the cargo falls back down.
        downhill = dict(uphill, sym_A_out=1.0)
        assert _rate(network, "sym_S_in", **downhill) < 0.0

    def test_the_ceiling_is_the_turnover_number_times_the_carrier(self) -> None:
        # Operational kcat: the maximum of the NET flux, not of a
        # microscopic reorientation. See the module docstring of
        # library_transport for why the difference is a factor of two.
        network = _probe(SYMPORT, "sym", kcat=1.0, Ka=10.0, Ks=0.1)
        network = replace(
            network,
            species=tuple(
                replace(s, initial=1.0) if s.id == "sym_T" else s
                for s in network.species
            ),
        )
        saturated = _rate(
            network, "sym_S_in",
            sym_A_out=1e9, sym_S_out=1e9, sym_A_in=0.0, sym_S_in=0.0,
        )
        assert saturated == pytest.approx(1.0, rel=1e-6)
        assert saturated < 1.0


class TestAntiportExchanges:
    def test_it_stalls_exactly_where_the_ratios_match(self) -> None:
        network = _probe(ANTIPORT, "anti", kcat=1.0, Ka=10.0, Kb=1.0)
        for a_out, b_in, a_in, b_out in (
            (100.0, 1.0, 10.0, 10.0),
            (10.0, 10.0, 10.0, 10.0),
            (2.0, 3.0, 6.0, 1.0),
        ):
            assert _rate(
                network, "anti_A_in",
                anti_A_out=a_out, anti_B_in=b_in,
                anti_A_in=a_in, anti_B_out=b_out,
            ) == pytest.approx(0.0, abs=1e-12)

    def test_it_reverses_when_the_driver_gradient_does(self) -> None:
        """The Na+/Ca2+ exchanger running backwards, in one assertion.

        The same carrier with the same constants, on either side of its
        stalling point.
        """
        network = _probe(ANTIPORT, "anti", kcat=1.0, Ka=10.0, Kb=1.0)
        forward = dict(
            anti_A_out=100.0, anti_A_in=10.0, anti_B_in=1.0, anti_B_out=1.0
        )
        assert _rate(network, "anti_A_in", **forward) > 0.0
        assert _rate(network, "anti_B_out", **forward) > 0.0
        reverse = dict(forward, anti_A_out=1.0, anti_A_in=100.0)
        assert _rate(network, "anti_A_in", **reverse) < 0.0
        assert _rate(network, "anti_B_out", **reverse) < 0.0

    def test_an_empty_exchanger_divides_by_zero_exactly_as_its_basis_says(
        self,
    ) -> None:
        """The failure mode the basis names, asserted rather than promised.

        An obligatory exchanger holding nothing cannot reorient, and the
        law has no turnover to report there: numerator and denominator are
        both zero. `derivative_function` catches the ZeroDivisionError and
        reports a non-finite derivative rather than crashing, which is what
        makes this a documented sharp edge rather than a crash.
        """
        network = _probe(ANTIPORT, "anti", kcat=1.0, Ka=10.0, Kb=1.0)
        rate = _rate(
            network, "anti_A_in",
            anti_A_out=0.0, anti_A_in=0.0, anti_B_in=0.0, anti_B_out=0.0,
        )
        assert not math.isfinite(rate)
        assert "denominator is zero" in ANTIPORT.basis


# -- the pump, and the limitation it admits to -------------------------------


class TestThePumpSpendsATP:
    def test_it_stops_dead_without_atp(self) -> None:
        # Exactly zero, not merely small: this is what makes the energetic
        # cost visible in a trajectory rather than folded into a constant.
        network = _probe(PRIMARY_ACTIVE_TRANSPORT, "pump")
        assert _rate(network, "pump_Out", pump_ATP=0.0) == 0.0
        assert _rate(network, "pump_In", pump_ATP=0.0) == 0.0
        assert _rate(network, "pump_Out", pump_ATP=3.0) > 0.0

    def test_it_moves_the_solute_against_its_gradient(self) -> None:
        network = _probe(PRIMARY_ACTIVE_TRANSPORT, "pump")
        uphill = dict(pump_In=0.1, pump_Out=100.0)
        assert _rate(network, "pump_Out", **uphill) > 0.0
        assert _rate(network, "pump_In", **uphill) < 0.0

    def test_it_pumps_just_as_hard_against_a_gradient_of_any_size(self) -> None:
        """The limitation, asserted so that it cannot be quietly forgotten.

        The law is irreversible and has no back-pressure term, so the rate
        does not depend on the trans concentration at all. That is wrong
        for a real pump, which stalls; the basis says so, and this test
        fails if either the law or the sentence changes without the other.
        """
        network = _probe(PRIMARY_ACTIVE_TRANSPORT, "pump")
        gentle = _rate(network, "pump_Out", pump_In=1.0, pump_Out=1.0)
        absurd = _rate(network, "pump_Out", pump_In=1.0, pump_Out=1e9)
        assert gentle == absurd
        assert "back-pressure" in PRIMARY_ACTIVE_TRANSPORT.basis

    def test_the_atp_it_spends_is_the_solute_it_moves(self) -> None:
        network = _probe(PRIMARY_ACTIVE_TRANSPORT, "pump")
        state = dict(pump_In=1.0, pump_Out=1.0, pump_ATP=3.0)
        assert _rate(network, "pump_ATP", **state) == pytest.approx(
            -_rate(network, "pump_Out", **state)
        )
        assert _rate(network, "pump_ADP", **state) == pytest.approx(
            _rate(network, "pump_Out", **state)
        )


# -- receptor trafficking, against the sorting race --------------------------


class TestReceptorInternalisation:
    def test_the_receptor_comes_back_as_the_race_between_two_constants(
        self,
    ) -> None:
        """The recycled fraction is derived, not declared.

        Started with everything internalised and no free ligand, so nothing
        rebinds: the endosomal pool drains into recycling and degradation
        in the ratio of their rate constants, and the surface receptor ends
        at exactly k_rec/(k_rec + k_deg) of what went in.
        """
        k_rec, k_deg = 2e-3, 1e-3
        network = _probe(
            RECEPTOR_LIGAND_INTERNALIZATION, "rec", k_rec=k_rec, k_deg=k_deg,
        )
        course = _time_course(
            network, dt=1.0, steps=8000, every=1000,
            rec_L=0.0, rec_R=0.0, rec_LR=0.0, rec_LRi=1.0,
        )
        final = course[-1][1]
        assert final["rec_R"] == pytest.approx(k_rec / (k_rec + k_deg), abs=1e-6)
        assert final["rec_LRi"] == pytest.approx(0.0, abs=1e-6)
        # The ligand does not come back with it.
        assert final["rec_L"] == 0.0

    def test_neither_fate_returns_the_ligand(self) -> None:
        # The modelling choice the basis argues with itself about. A
        # transferrin-like receptor would return it, and would be a
        # different motif.
        recycling = next(
            r for r in RECEPTOR_LIGAND_INTERNALIZATION.reactions
            if r.name == "recycling"
        )
        degradation = next(
            r for r in RECEPTOR_LIGAND_INTERNALIZATION.reactions
            if r.name == "lysosomal_degradation"
        )
        assert recycling.products == {"R": 1}
        assert degradation.products == {}
        assert "does not come back" in RECEPTOR_LIGAND_INTERNALIZATION.basis

    def test_binding_is_reversible_and_only_the_occupied_receptor_goes_in(
        self,
    ) -> None:
        by_name = {
            r.name: r for r in RECEPTOR_LIGAND_INTERNALIZATION.reactions
        }
        assert by_name["binding"].reactants == {"L": 1, "R": 1}
        assert by_name["unbinding"].products == {"L": 1, "R": 1}
        assert by_name["internalisation"].reactants == {"LR": 1}
        # No reaction internalises the free receptor, which the basis names
        # as an omission rather than leaving it to be discovered.
        assert "R" not in by_name["internalisation"].reactants


# -- units, kinds, and the compartment convention ----------------------------


class TestUnitsAndKinds:
    @pytest.mark.parametrize(
        "motif", sorted(TRANSPORT_LIBRARY.values(), key=lambda m: m.name),
        ids=sorted(TRANSPORT_LIBRARY),
    )
    def test_every_motif_balances_dimensionally(self, motif) -> None:
        composition = Composition(f"units {motif.name}")
        composition.add(motif, "m")
        findings = composition.unit_findings()
        assert findings == (), [f.detail for f in findings]

    @pytest.mark.parametrize(
        "motif", ACROSS_THE_MEMBRANE, ids=[m.name for m in ACROSS_THE_MEMBRANE],
    )
    def test_the_volume_ratio_is_chosen_and_never_resolved(self, motif) -> None:
        """The point of declaring it at all.

        A volume ratio is a fact about the scenario's geometry. If it were
        resolvable a scout would be sent to find "the" volume ratio, which
        is not a quantity any paper reports about a molecule.
        """
        composition = Composition(f"kinds {motif.name}")
        composition.add(motif, "m")
        declared = {p.name: p for p in motif.parameters}
        assert "volume_ratio" in declared
        assert declared["volume_ratio"] is VOLUME_RATIO
        assert VOLUME_RATIO.kind in CHOSEN_KINDS
        assert not VOLUME_RATIO.resolvable
        assert parse_unit(VOLUME_RATIO.unit).dimensionless
        assert "m_volume_ratio" in composition.chosen_quantities()
        assert "m_volume_ratio" not in [
            q.parameter_id for q in composition.quantities_to_resolve()
        ]

    def test_exactly_the_motifs_that_cross_the_membrane_carry_one(self) -> None:
        """Both directions, because both mistakes are possible.

        A motif that moves something across without a ratio is silently
        assuming equal volumes, which is the thing this module refuses to
        do. A motif that carries one without crossing anything is
        advertising a choice that changes nothing.
        """
        with_ratio = {
            name for name, motif in TRANSPORT_LIBRARY.items()
            if any(p.name == "volume_ratio" for p in motif.parameters)
        }
        crossing = {motif.name for motif in ACROSS_THE_MEMBRANE}
        assert with_ratio == crossing
        # The exception, and it is an argued one: everything in the
        # trafficking motif is referred to a single volume.
        assert RECEPTOR_LIGAND_INTERNALIZATION.name not in with_ratio
        assert "ONE reference volume" in RECEPTOR_LIGAND_INTERNALIZATION.basis

    def test_the_two_halves_of_a_translocation_share_one_driving_law(
        self,
    ) -> None:
        """The invariant `_membrane_pair` exists to guarantee.

        If the two halves ever stop being the same expression over the
        volume ratio, the pair creates or destroys molecules at a rate
        nothing reports. Asserted on the strings, because that is the level
        at which somebody would break it -- by editing one of the two.
        """
        for motif in ACROSS_THE_MEMBRANE:
            inside, outside = motif.reactions
            assert outside.rate_law == f"({inside.rate_law}) / {{volume_ratio}}"

    def test_no_amount_arrives_as_a_parameter(self) -> None:
        # Every concentration here is a species, so its value is a scenario
        # choice the caller makes rather than a parameter that looks
        # resolvable by accident.
        amounts = [
            f"{name}.{parameter.name}"
            for name, motif in TRANSPORT_LIBRARY.items()
            for parameter in motif.parameters
            if parameter.kind == KIND_CONCENTRATION
        ]
        assert amounts == []

    def test_no_parameter_is_a_lumped_maximal_rate(self) -> None:
        # ADR 0013 in this module's terms: a transporter's Vmax is
        # kcat*[T], and [T] is the caller's. Every law here writes the
        # carrier out as a species instead.
        named = [
            f"{name}.{parameter.name}"
            for name, motif in TRANSPORT_LIBRARY.items()
            for parameter in motif.parameters
            if parameter.name.lower() in {"vmax", "v_max", "jmax", "j_max"}
        ]
        assert named == []

    def test_every_rate_constant_and_affinity_is_resolvable(self) -> None:
        composition = Composition("resolvable")
        for index, motif in enumerate(
            sorted(TRANSPORT_LIBRARY.values(), key=lambda m: m.name)
        ):
            composition.add(motif, f"m{index}")
        resolvable = {q.parameter_name for q in composition.quantities_to_resolve()}
        assert "volume_ratio" not in resolvable
        assert {"kcat", "Kt", "Ka", "Ks", "Kb", "k_leak", "kon"} <= resolvable
        for quantity in composition.quantities_to_resolve():
            assert quantity.kind in RESOLVABLE_KINDS
            assert quantity.description, quantity.parameter_id

    def test_every_motif_says_what_licenses_it_and_where_it_fails(self) -> None:
        for name, motif in TRANSPORT_LIBRARY.items():
            assert motif.summary, name
            assert motif.basis, name
            # "fails", "cannot", "omits", "not tracked": a basis that only
            # states the assumption has done half the job.
            assert any(
                word in motif.basis
                for word in ("fails", "cannot", "not tracked", "absent", "omits")
            ), f"{name} does not say where it stops being right"


# -- refusals ----------------------------------------------------------------


class TestTheWithheldMotifs:
    """The electrical mechanisms, and the reason they are not here.

    A refusal is a deliverable in this package, so it is tested like one:
    that it happens, that it says why, and -- the part that matters -- that
    the reason it gives is actually true of the code it names.
    """

    @pytest.mark.parametrize("name", sorted(WITHHELD), ids=sorted(WITHHELD))
    def test_asking_by_name_gets_the_reason(self, name) -> None:
        with pytest.raises(TransportMotifWithheld) as raised:
            transport_motif(name)
        message = str(raised.value)
        assert "units.py" in message
        assert "would have to change" in message or "fixable" in message
        assert name in message

    def test_a_mechanism_nobody_wrote_is_a_different_error(self) -> None:
        # Not the same situation and not the same sentence: a typo needs
        # the available names, a withheld mechanism needs the argument.
        with pytest.raises(KeyError) as raised:
            transport_motif("teleportation")
        message = str(raised.value)
        assert "passive_leak" in message
        assert "ion_channel_ohmic" in message

    def test_the_alias_and_the_library_both_resolve(self) -> None:
        assert transport_motif("receptor_ligand_internalization") is (
            RECEPTOR_LIGAND_INTERNALIZATION
        )
        assert transport_motif("symport") is SYMPORT
        # library.py's motifs stay reachable through the same door.
        assert transport_motif("catalytic_step") is LIBRARY["catalytic_step"]

    def test_the_unit_system_really_cannot_read_a_millivolt(self) -> None:
        """The refusal's premise, checked rather than asserted in prose.

        If units.py ever learns a volt, this test fails and the withheld
        entry becomes a lie that nobody would otherwise notice.
        """
        for text in ("mV", "V", "nS", "pA", "L"):
            with pytest.raises(UnitError):
                parse_unit(text)
        # ... and the contrast: molar with a metric prefix, which is what
        # it does read, and reads with the scale that separates mM from uM.
        millimolar = parse_unit("mM")
        assert millimolar.same_dimensions(parse_unit("M"))
        assert millimolar.scale == pytest.approx(1e-3)

    def test_the_unit_checker_really_cannot_see_through_an_exponential(
        self,
    ) -> None:
        # The second, independent blocker on a voltage-gated conductance:
        # the rate-law parser has no function calls at all, so a Boltzmann
        # term is unverifiable even before the volts are considered.
        environment = {"V": parse_unit("dimensionless"), "C": parse_unit("mM")}
        with pytest.raises(UnitError):
            check_rate_law("exp(V) * C", environment)
        assert "exp" in WITHHELD["voltage_gated_channel"]

    def test_nothing_here_redefines_a_motif_the_library_already_has(self) -> None:
        # The import-time guard, restated as a test so that the reason
        # survives a refactor of the guard.
        assert set(LIBRARY) & set(TRANSPORT_LIBRARY) == set()
        assert set(FULL_LIBRARY) == set(LIBRARY) | set(TRANSPORT_LIBRARY)
        # And the one it is most easily confused with is re-exported, not
        # copied: same object, one rate law.
        assert FULL_LIBRARY["facilitated_transport"] is FACILITATED_TRANSPORT
