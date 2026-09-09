"""The enzymology motifs, tested against the answers that are known exactly.

WHY THESE TESTS ARE ARITHMETIC AND NOT PLOTS
--------------------------------------------
Every mechanism here is distinguished from its neighbours by a closed-form
signature, and every one of those signatures is a number a test can compute
independently of the code under test:

    competitive inhibition    at saturating S the rate reaches the
                              UNINHIBITED kcat*[E]; more substrate wins
    uncompetitive             at saturating S it reaches kcat*[E]/(1+[I]/Ki)
                              and no amount of substrate rescues it
    non-competitive           IS mixed inhibition with Kic = Kiu, so the two
                              motifs must agree to the last bit
    product inhibition        the half-maximal point moves to Km*(1+[P]/Kp)
                              and the ceiling does not move at all
    ping-pong bi-bi           the Lineweaver-Burk slope in 1/[A] is
                              Kma/(kcat*[E]) whatever [B] is -- parallel lines
    ordered bi-bi             that slope carries an extra Kia*Kmb/(kcat*[E]*B)
                              term, so the lines intersect
    MWC at L = 0              collapses to an exact rectangular hyperbola for
                              every subunit count
    MWC at Kt = Kr            is Michaelis-Menten with Vmax/(1+L) and the
                              SAME Km, so the sigmoid is gone
    futile cycle              d[Xp]/dt = 0 while d[ATP]/dt is not
    channelling               transfer-to-escape flux ratio is exactly
                              k_transfer/k_escape

So none of these tests asks whether the code ran. Each computes what the
biochemistry says the answer is and demands that number.

WHY THE RATES COME THROUGH derivative_function
-----------------------------------------------
A test could re-implement each rate law and compare. That would pass with a
motif whose rate law was never compiled, never validated by
`ReactionNetwork`, and never wired to the right species -- the three things
that actually go wrong. `derivative_function` is the path the analysis and
sensitivity modules use, so a rate read through it is a rate the rest of
the package would see.
"""

from __future__ import annotations

from dataclasses import replace
from typing import ClassVar

import pytest

from Terium.compose.analysis import derivative_function
from Terium.compose.builder import Composition
from Terium.compose.library import (
    CATALYTIC_STEP, COMPETITIVE_INHIBITION, COOPERATIVE_CATALYSIS, LIBRARY,
)
from Terium.compose.library_enzymology import (
    ALIASES, ENZYMOLOGY_LIBRARY, FULL_LIBRARY, FUTILE_CYCLE, HILL_KINETICS,
    MIXED_INHIBITION, MWC_ALLOSTERY, NONCOMPETITIVE_INHIBITION, ORDERED_BI_BI,
    PING_PONG_BI_BI, PRODUCT_INHIBITION, SUBSTRATE_CHANNELING,
    UNCOMPETITIVE_INHIBITION, enzymology_motif,
)
from Terium.compose.motifs import (
    KIND_CONCENTRATION, KIND_EXPONENT, RESOLVABLE_KINDS,
)


# -- machinery ---------------------------------------------------------------


def _probe(motif, prefix, **values):
    """One motif alone in a composition, with its parameters set.

    Parameter values are pushed onto the built network with
    `dataclasses.replace` rather than into the motif, because a motif's
    defaults are illustrative placeholders shared by every test in the
    process and mutating one here would silently change another.
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

    Species not named default to the network's declared initial rather than
    to zero: a silent zero for the enzyme would make every rate zero and
    every comparison trivially true.
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


#: Far enough past Km that the saturating limit is reached to well under the
#: tolerances asserted below, and not so far that (1 + S/Kr)^n overflows in
#: the MWC law.
SATURATING = 1e8


# -- inhibition, against its analytic signatures -----------------------------


class TestCompetitiveVersusUncompetitive:
    """The pair the double-reciprocal plot was invented to separate.

    Both slow the enzyme down and they fail in opposite directions at high
    substrate, which is the only place the difference is unambiguous.
    """

    def test_competitive_inhibition_is_outrun_by_substrate(self) -> None:
        # The inhibitor binds free enzyme, so substrate that has already
        # bound cannot be displaced: as S grows the inhibitor is squeezed
        # out and the rate returns to the UNINHIBITED kcat*[E].
        network = _probe(COMPETITIVE_INHIBITION, "c", kcat=50.0, Km=0.2, Ki=0.5)
        rate = _rate(network, "c_P", c_S=SATURATING, c_E=2e-3, c_I=0.5)
        assert rate == pytest.approx(50.0 * 2e-3, rel=1e-6)

    def test_uncompetitive_inhibition_is_not_outrun_by_substrate(self) -> None:
        # The inhibitor binds the ES complex, so more substrate makes MORE
        # of what the inhibitor wants. The ceiling is kcat*[E]/(1 + I/Ki),
        # and with I = Ki that is exactly half.
        network = _probe(UNCOMPETITIVE_INHIBITION, "u", kcat=50.0, Km=0.2, Ki=0.5)
        rate = _rate(network, "u_P", u_S=SATURATING, u_E=2e-3, u_I=0.5)
        assert rate == pytest.approx(0.5 * 50.0 * 2e-3, rel=1e-6)

    def test_the_two_ceilings_differ_by_the_inhibitor_saturation_factor(self) -> None:
        # Stated as one comparison because it is the discrimination itself:
        # at saturating substrate the competitive rate is (1 + I/Ki) times
        # the uncompetitive one, for every kcat and every Km.
        competitive = _probe(COMPETITIVE_INHIBITION, "c", kcat=50.0, Km=0.2, Ki=0.5)
        uncompetitive = _probe(UNCOMPETITIVE_INHIBITION, "u", kcat=50.0, Km=0.9, Ki=0.5)
        fast = _rate(competitive, "c_P", c_S=SATURATING, c_E=2e-3, c_I=1.5)
        slow = _rate(uncompetitive, "u_P", u_S=SATURATING, u_E=2e-3, u_I=1.5)
        assert fast / slow == pytest.approx(1.0 + 1.5 / 0.5, rel=1e-6)

    def test_uncompetitive_lowers_km_and_vmax_by_the_same_factor(self) -> None:
        """The property that makes the Lineweaver-Burk lines parallel.

        Apparent Vmax is kcat*[E]/(1+i) and apparent Km is Km/(1+i) with
        i = [I]/Ki, so the half-maximal point sits at Km/(1+i) and the rate
        there is exactly half of the apparent Vmax. Checking both at once
        is what pins that it is the SAME factor; checking either alone
        would pass for a motif that scaled only one of them.
        """
        km, ki, inhibitor, kcat, enzyme = 0.2, 0.5, 1.5, 50.0, 2e-3
        factor = 1.0 + inhibitor / ki
        network = _probe(UNCOMPETITIVE_INHIBITION, "u", kcat=kcat, Km=km, Ki=ki)

        ceiling = _rate(network, "u_P", u_S=SATURATING, u_E=enzyme, u_I=inhibitor)
        half = _rate(network, "u_P", u_S=km / factor, u_E=enzyme, u_I=inhibitor)

        assert ceiling == pytest.approx(kcat * enzyme / factor, rel=1e-6)
        assert half == pytest.approx(ceiling / 2.0, rel=1e-9)


class TestNoncompetitiveIsMixedWithEqualConstants:
    """Non-competitive inhibition is not a separate mechanism.

    It is the point of the mixed model where the inhibitor cannot tell free
    enzyme from the ES complex. Two motifs exist because the two rate laws
    are written differently and a reader looks for the name -- so the thing
    worth pinning is that the two laws are the SAME function, not merely
    similar.
    """

    SUBSTRATES = (0.01, 0.1, 0.5, 1.0, 10.0, 1000.0)

    def _rates(self, motif, prefix, **values):
        network = _probe(motif, prefix, **values)
        return [
            _rate(
                network, f"{prefix}_P",
                **{f"{prefix}_S": s, f"{prefix}_E": 2e-3, f"{prefix}_I": 0.7},
            )
            for s in self.SUBSTRATES
        ]

    def test_the_two_rate_laws_agree_to_the_last_bit(self) -> None:
        noncompetitive = self._rates(
            NONCOMPETITIVE_INHIBITION, "nc", kcat=50.0, Km=0.2, Ki=0.5
        )
        mixed = self._rates(
            MIXED_INHIBITION, "mx", kcat=50.0, Km=0.2, Kic=0.5, Kiu=0.5
        )
        # Asserted on the whole list, outside any loop, so nothing can be
        # skipped -- and on a positive minimum, because two lists of zeros
        # would agree perfectly and mean nothing.
        assert min(noncompetitive) > 0.0
        assert noncompetitive == pytest.approx(mixed, rel=1e-12)

    def test_unequal_constants_do_not_agree(self) -> None:
        # The control for the test above. Without it, a mixed motif that
        # ignored Kiu entirely would pass -- it would agree with
        # non-competitive at Kic = Kiu and be wrong everywhere else.
        noncompetitive = self._rates(
            NONCOMPETITIVE_INHIBITION, "nc", kcat=50.0, Km=0.2, Ki=0.5
        )
        mixed = self._rates(
            MIXED_INHIBITION, "mx", kcat=50.0, Km=0.2, Kic=0.5, Kiu=4.0
        )
        assert noncompetitive != pytest.approx(mixed, rel=1e-6)

    def test_mixed_reaches_competitive_as_the_complex_constant_grows(self) -> None:
        # Kiu -> infinity means the inhibitor cannot bind ES at all.
        mixed = _probe(MIXED_INHIBITION, "mx", kcat=50.0, Km=0.2, Kic=0.5, Kiu=1e12)
        competitive = _probe(COMPETITIVE_INHIBITION, "c", kcat=50.0, Km=0.2, Ki=0.5)
        assert _rate(mixed, "mx_P", mx_S=0.3, mx_E=2e-3, mx_I=0.7) == pytest.approx(
            _rate(competitive, "c_P", c_S=0.3, c_E=2e-3, c_I=0.7), rel=1e-9
        )

    def test_mixed_reaches_uncompetitive_as_the_free_constant_grows(self) -> None:
        # And Kic -> infinity means it cannot bind free enzyme.
        mixed = _probe(MIXED_INHIBITION, "mx", kcat=50.0, Km=0.2, Kic=1e12, Kiu=0.5)
        uncompetitive = _probe(UNCOMPETITIVE_INHIBITION, "u", kcat=50.0, Km=0.2, Ki=0.5)
        assert _rate(mixed, "mx_P", mx_S=0.3, mx_E=2e-3, mx_I=0.7) == pytest.approx(
            _rate(uncompetitive, "u_P", u_S=0.3, u_E=2e-3, u_I=0.7), rel=1e-9
        )


class TestProductInhibition:
    def test_the_ceiling_does_not_move(self) -> None:
        # The product competes for free enzyme, so like any competitive
        # inhibitor it is outrun: at saturating substrate the rate is the
        # uninhibited kcat*[E] however much product is present.
        network = _probe(PRODUCT_INHIBITION, "pi", kcat=50.0, Km=0.2, Kp=0.4)
        assert _rate(
            network, "pi_P", pi_S=SATURATING, pi_E=2e-3, pi_P=5.0
        ) == pytest.approx(50.0 * 2e-3, rel=1e-6)

    def test_the_half_maximal_point_moves_to_km_times_one_plus_p_over_kp(self) -> None:
        # Apparent Km is Km*(1 + P/Kp), so the rate at exactly that
        # substrate is half the UNCHANGED ceiling. Both halves matter: a
        # motif that lowered the ceiling instead would fail the first
        # assertion, one that left Km alone would fail the second.
        km, kp, product, kcat, enzyme = 0.2, 0.4, 0.8, 50.0, 2e-3
        network = _probe(PRODUCT_INHIBITION, "pi", kcat=kcat, Km=km, Kp=kp)
        apparent_km = km * (1.0 + product / kp)
        half = _rate(network, "pi_P", pi_S=apparent_km, pi_E=enzyme, pi_P=product)
        assert half == pytest.approx(kcat * enzyme / 2.0, rel=1e-9)
        assert apparent_km > km


# -- two substrates ----------------------------------------------------------


class TestOrderedVersusPingPong:
    """Parallel lines against intersecting ones, computed rather than drawn.

    1/v is exactly linear in 1/[A] for both mechanisms, so two points give
    the slope with no fitting and no numerical derivative. The slope is
    where the mechanisms differ: ping-pong's does not depend on [B] and
    ordered's does, which is the whole content of the double-reciprocal
    diagnosis.
    """

    KCAT, ENZYME = 40.0, 2e-3
    KMA, KMB, KIA = 0.3, 0.7, 1.1
    A_LOW, A_HIGH = 0.25, 4.0

    def _slope(self, network, prefix, b_value):
        reciprocals = []
        for a in (self.A_LOW, self.A_HIGH):
            rate = _rate(
                network, f"{prefix}_P",
                **{
                    f"{prefix}_A": a,
                    f"{prefix}_B": b_value,
                    f"{prefix}_E": self.ENZYME,
                },
            )
            reciprocals.append(1.0 / rate)
        return (reciprocals[0] - reciprocals[1]) / (1.0 / self.A_LOW - 1.0 / self.A_HIGH)

    def test_ping_pong_lines_are_parallel_at_the_analytic_slope(self) -> None:
        network = _probe(
            PING_PONG_BI_BI, "pp", kcat=self.KCAT, Kma=self.KMA, Kmb=self.KMB
        )
        expected = self.KMA / (self.KCAT * self.ENZYME)
        low = self._slope(network, "pp", 0.5)
        high = self._slope(network, "pp", 25.0)
        assert low == pytest.approx(expected, rel=1e-9)
        assert high == pytest.approx(expected, rel=1e-9)

    def test_ordered_lines_intersect_because_the_slope_carries_kia(self) -> None:
        network = _probe(
            ORDERED_BI_BI, "ob",
            kcat=self.KCAT, Kma=self.KMA, Kmb=self.KMB, Kia=self.KIA,
        )
        base = self.KMA / (self.KCAT * self.ENZYME)
        for b in (0.5, 25.0):
            expected = base + self.KIA * self.KMB / (self.KCAT * self.ENZYME * b)
            assert self._slope(network, "ob", b) == pytest.approx(expected, rel=1e-9)
        # The discrimination itself, outside the loop: the two slopes are
        # not the same number, which is what "intersecting" means.
        assert self._slope(network, "ob", 0.5) > 1.5 * self._slope(network, "ob", 25.0)

    def test_the_ordered_mechanism_is_ping_pong_plus_one_term(self) -> None:
        # Kia -> 0 removes the ternary-complex term and the two mechanisms
        # become the same function. This is why the KiA*Kmb term is the
        # signature rather than an incidental difference in the algebra.
        ordered = _probe(
            ORDERED_BI_BI, "ob", kcat=self.KCAT, Kma=self.KMA, Kmb=self.KMB, Kia=0.0
        )
        ping_pong = _probe(
            PING_PONG_BI_BI, "pp", kcat=self.KCAT, Kma=self.KMA, Kmb=self.KMB
        )
        assert _rate(
            ordered, "ob_P", ob_A=0.4, ob_B=0.9, ob_E=self.ENZYME
        ) == pytest.approx(
            _rate(ping_pong, "pp_P", pp_A=0.4, pp_B=0.9, pp_E=self.ENZYME), rel=1e-12
        )


# -- allostery ---------------------------------------------------------------


class TestMwcAgainstItsExactLimits:
    """MWC has two limits where the answer is a hyperbola, exactly.

    Both are worth pinning because both are places a wrong exponent or a
    misplaced parenthesis survives a plot: the curve still looks like
    enzyme kinetics, it is simply the wrong enzyme kinetics.
    """

    KCAT, ENZYME, KR = 7.0, 2e-3, 0.3
    SUBSTRATES = (0.01, 0.3, 3.0, 300.0)

    def _michaelis_menten(self, s):
        return self.KCAT * self.ENZYME * s / (self.KR + s)

    def test_no_allosteric_constant_is_michaelis_menten_for_any_subunit_count(self) -> None:
        # L = 0 means the T state is never occupied, so there is nothing to
        # be cooperative about and the sigmoid must vanish COMPLETELY --
        # not approximately, and not only for n = 1.
        network = _probe(
            MWC_ALLOSTERY, "mwc",
            kcat=self.KCAT, Kr=self.KR, Kt=9.0, L=0.0, n=4.0,
        )
        observed = [
            _rate(network, "mwc_P", mwc_S=s, mwc_E=self.ENZYME)
            for s in self.SUBSTRATES
        ]
        expected = [self._michaelis_menten(s) for s in self.SUBSTRATES]
        assert min(observed) > 0.0
        assert observed == pytest.approx(expected, rel=1e-12)

    def test_equal_state_affinities_scale_vmax_and_leave_km_alone(self) -> None:
        # Kt = Kr means substrate cannot tell R from T, so it cannot pull
        # the equilibrium: the curve is Michaelis-Menten with the SAME Km
        # and Vmax divided by (1 + L). Anything that changed Km here would
        # be a sign the T state was leaking into the affinity.
        allosteric_constant = 3.0
        network = _probe(
            MWC_ALLOSTERY, "mwc",
            kcat=self.KCAT, Kr=self.KR, Kt=self.KR, L=allosteric_constant, n=4.0,
        )
        observed = [
            _rate(network, "mwc_P", mwc_S=s, mwc_E=self.ENZYME)
            for s in self.SUBSTRATES
        ]
        expected = [
            self._michaelis_menten(s) / (1.0 + allosteric_constant)
            for s in self.SUBSTRATES
        ]
        assert min(observed) > 0.0
        assert observed == pytest.approx(expected, rel=1e-12)

    def test_the_curve_is_sigmoid_only_when_the_states_bind_differently(self) -> None:
        """Sigmoid means doubling the substrate more than doubles the rate.

        A hyperbola can never do that -- v(2S)/v(S) < 2 everywhere, for
        every Km. So the same comparison separates the two curves without
        any fitting, and the Michaelis-Menten arm is asserted alongside so
        the test can fail from either direction.
        """
        sigmoid = _probe(
            MWC_ALLOSTERY, "mwc", kcat=100.0, Kr=0.1, Kt=10.0, L=1e4, n=4.0
        )
        hyperbola = _probe(CATALYTIC_STEP, "mm", kcat=100.0, Km=0.1)
        low = _rate(sigmoid, "mwc_P", mwc_S=0.05, mwc_E=1e-3)
        high = _rate(sigmoid, "mwc_P", mwc_S=0.10, mwc_E=1e-3)
        flat_low = _rate(hyperbola, "mm_P", mm_S=0.05, mm_E=1e-3)
        flat_high = _rate(hyperbola, "mm_P", mm_S=0.10, mm_E=1e-3)
        assert high / low > 2.0
        assert flat_high / flat_low < 2.0

    def test_a_substrate_binding_t_state_holds_the_ceiling_below_kcat_times_e(self) -> None:
        # With c = Kr/Kt > 0 some enzyme stays in T even at infinite
        # substrate, so the saturating rate is kcat*[E]/(1 + L*c^n) and not
        # kcat*[E]. A model that reached kcat*[E] would be the exclusive-
        # binding special case wearing the general case's parameters.
        kcat, enzyme, kr, kt, allosteric, subunits = 100.0, 1e-3, 0.1, 10.0, 1e4, 4.0
        network = _probe(
            MWC_ALLOSTERY, "mwc", kcat=kcat, Kr=kr, Kt=kt, L=allosteric, n=subunits
        )
        ceiling = kcat * enzyme / (1.0 + allosteric * (kr / kt) ** subunits)
        assert _rate(
            network, "mwc_P", mwc_S=SATURATING, mwc_E=enzyme
        ) == pytest.approx(ceiling, rel=1e-6)
        assert ceiling < kcat * enzyme

    def test_the_subunit_count_is_chosen_and_the_allosteric_constant_is_not(self) -> None:
        """The kinds are the whole provenance argument for this motif.

        n is a structural count the caller states; L is a conformational
        equilibrium constant that a paper can supply and no BRENDA table
        does. If n ever became resolvable the pipeline would send a scout
        looking for a number nobody publishes, and if L became chosen the
        caller would be inventing one.
        """
        by_name = {p.name: p for p in MWC_ALLOSTERY.parameters}
        assert by_name["n"].kind == KIND_EXPONENT
        assert by_name["n"].resolvable is False
        assert by_name["L"].resolvable is True
        assert by_name["L"].table is None
        assert "resolvable only from a paper" in by_name["L"].description


class TestHillIsAFitAndSaysSo:
    def test_the_basis_denies_that_the_coefficient_is_a_subunit_count(self) -> None:
        """The specific error this basis exists to head off.

        Reading a Hill coefficient as a site count converts a curve-fitting
        parameter into a structural claim about the protein. The sentence
        is asserted literally because the point of the basis string is that
        a reader sees it, and a paraphrase that dropped the denial would
        leave the motif looking mechanistic when it is not.
        """
        basis = HILL_KINETICS.basis
        assert "NOT a subunit count" in basis
        assert "PHENOMENOLOGICAL" in basis

    def test_the_coefficient_is_an_exponent_and_never_searched_for(self) -> None:
        coefficient = next(p for p in HILL_KINETICS.parameters if p.name == "h")
        assert coefficient.kind == KIND_EXPONENT
        assert coefficient.resolvable is False

    def test_hill_kinetics_is_the_existing_motif_and_not_a_second_copy(self) -> None:
        # The alias is the point: one rate law, reachable under the name the
        # literature uses. A copy would be a second answer to a question
        # that already had one.
        assert HILL_KINETICS is COOPERATIVE_CATALYSIS
        assert ALIASES["hill_kinetics"] == COOPERATIVE_CATALYSIS.name
        assert enzymology_motif("hill_kinetics") is COOPERATIVE_CATALYSIS

    def test_a_coefficient_of_one_is_michaelis_menten(self) -> None:
        # The sanity check the empirical form has to pass: with no
        # cooperativity the sigmoid is a hyperbola.
        hill = _probe(HILL_KINETICS, "h", kcat=9.0, K=0.4, h=1.0)
        michaelis = _probe(CATALYTIC_STEP, "mm", kcat=9.0, Km=0.4)
        observed = [_rate(hill, "h_P", h_S=s, h_E=1e-3) for s in (0.05, 0.4, 4.0)]
        expected = [_rate(michaelis, "mm_P", mm_S=s, mm_E=1e-3) for s in (0.05, 0.4, 4.0)]
        assert min(observed) > 0.0
        assert observed == pytest.approx(expected, rel=1e-12)


# -- channelling and cycling -------------------------------------------------


class TestSubstrateChanneling:
    def test_the_channelled_fraction_is_exactly_the_ratio_of_two_rate_constants(self) -> None:
        # Written as a race, so the split between the tunnel and the bulk
        # is k_transfer : k_escape and nothing else. This is what replaces
        # the dimensionless "channelling efficiency" that no parameter kind
        # could have honestly carried.
        network = _probe(
            SUBSTRATE_CHANNELING, "ch",
            kcat1=50.0, Km1=0.1, k_transfer=200.0, k_escape=1.0,
            kcat2=50.0, Km2=0.1,
        )
        state = dict(ch_S=1.0, ch_EI=0.02, ch_I=0.0, ch_C=1e-3)
        to_product = _rate(network, "ch_P", **state)
        to_bulk = _rate(network, "ch_I", **state)
        assert to_product / to_bulk == pytest.approx(200.0 / 1.0, rel=1e-12)

    def test_a_bulk_scavenger_cannot_touch_the_channelled_flux(self) -> None:
        """The isotope-dilution experiment, as a composition.

        A second enzyme is wired onto the BULK intermediate only. It drains
        that pool -- which is the control showing it is really connected --
        and leaves the flux through the tunnel exactly where it was. An
        implementation that routed the intermediate through solution would
        fail the second assertion.
        """
        composition = Composition("channelling with a scavenger")
        composition.add(SUBSTRATE_CHANNELING, "ch")
        composition.add(CATALYTIC_STEP, "scav", bindings={"S": "ch_I"})
        with_scavenger = composition.to_network()

        alone = Composition("channelling alone")
        alone.add(SUBSTRATE_CHANNELING, "ch")
        without = alone.to_network()

        state = dict(ch_S=1.0, ch_EI=0.02, ch_I=0.5, ch_C=1e-3)
        channelled = _rate(with_scavenger, "ch_P", scav_E=1e-3, scav_P=0.0, **state)
        assert channelled == pytest.approx(_rate(without, "ch_P", **state), rel=1e-12)
        assert _rate(with_scavenger, "ch_I", scav_E=1e-3, scav_P=0.0, **state) < _rate(
            without, "ch_I", **state
        )

    def test_no_parameter_is_a_dimensionless_efficiency(self) -> None:
        # The design rule, asserted rather than only argued in the
        # docstring. A dimensionless factor here would fit no kind: not a
        # rate constant or an affinity, so unresolvable; not a
        # concentration or an exponent, so not honestly choosable either.
        units = {p.unit for p in SUBSTRATE_CHANNELING.parameters}
        assert "dimensionless" not in units
        assert all(p.kind in RESOLVABLE_KINDS for p in SUBSTRATE_CHANNELING.parameters)


class TestFutileCycle:
    """The measurement that names the mechanism.

    Parameters are chosen so the two arms balance EXACTLY at the state
    probed: kcat_kin = 2 with ATP at its Km halves the kinase arm, and the
    two Michaelis terms are equal at X = Xp. So the protein pools are
    stationary by construction and any ATP flux left over is the cycle's
    cost rather than a transient.
    """

    BALANCED: ClassVar[dict] = dict(
        kcat_kin=2.0, Km_kin=1.0, Km_atp=1.0, kcat_pptase=1.0, Km_pptase=1.0
    )
    STATE: ClassVar[dict] = dict(
        fc_X=1.0, fc_Xp=1.0, fc_ATP=1.0, fc_kinase=1e-3, fc_phosphatase=1e-3
    )

    def test_atp_is_spent_while_the_protein_pools_stand_still(self) -> None:
        network = _probe(FUTILE_CYCLE, "fc", **self.BALANCED)
        cycling = 2.0 * 1e-3 * 0.5 * 0.5
        assert _rate(network, "fc_Xp", **self.STATE) == pytest.approx(0.0, abs=1e-18)
        assert _rate(network, "fc_X", **self.STATE) == pytest.approx(0.0, abs=1e-18)
        assert _rate(network, "fc_ATP", **self.STATE) == pytest.approx(-cycling, rel=1e-12)
        assert _rate(network, "fc_ADP", **self.STATE) == pytest.approx(cycling, rel=1e-12)

    def test_the_phosphate_released_matches_the_atp_consumed(self) -> None:
        # One ATP in, one Pi out, per pass. If these ever disagreed the
        # cycle would be creating or destroying phosphate, which is the
        # kind of error a plot of [Xp] would never show.
        network = _probe(FUTILE_CYCLE, "fc", **self.BALANCED)
        assert _rate(network, "fc_Pi", **self.STATE) == pytest.approx(
            -_rate(network, "fc_ATP", **self.STATE), rel=1e-12
        )

    def test_starving_the_cycle_of_atp_stops_the_kinase_arm(self) -> None:
        # The control that makes the cost real rather than decorative: with
        # ATP folded into the kinase's rate constant there would be nothing
        # to remove, and this test could not be written.
        network = _probe(FUTILE_CYCLE, "fc", **self.BALANCED)
        starved = {**self.STATE, "fc_ATP": 0.0}
        assert _rate(network, "fc_ATP", **starved) == 0.0
        assert _rate(network, "fc_Xp", **starved) < 0.0

    def test_the_cycling_rate_is_not_the_net_rate(self) -> None:
        # The distinction the motif exists to make visible. Net conversion
        # is zero; the ATPase activity is not; and no measurement of [Xp]
        # alone can tell a balanced cycle from a dead one.
        network = _probe(FUTILE_CYCLE, "fc", **self.BALANCED)
        net_conversion = abs(_rate(network, "fc_Xp", **self.STATE))
        hydrolysis = abs(_rate(network, "fc_ATP", **self.STATE))
        assert net_conversion == pytest.approx(0.0, abs=1e-18)
        assert hydrolysis > 1e-6


# -- the module as a whole ---------------------------------------------------


class TestEveryRateLawBalances:
    def test_no_motif_in_the_registry_produces_a_unit_finding(self) -> None:
        """Run at composition time, over everything the module exposes.

        A dimensionally wrong rate law integrates perfectly well and
        produces a smooth curve that is wrong by whatever factor the
        mistake introduced. There is no later point at which that becomes
        visible, so it is checked here before anything compiles.
        """
        findings = []
        for name, motif in sorted(FULL_LIBRARY.items()):
            composition = Composition(f"unit probe {name}")
            composition.add(motif, "p")
            findings.extend(
                f"{name}: {finding.severity}: {finding.detail}"
                for finding in composition.unit_findings()
            )
        assert len(FULL_LIBRARY) >= 28
        assert findings == []

    def test_the_new_motifs_reintroduce_no_lumped_vmax(self) -> None:
        # ADR 0013. Vmax is kcat x [E]0 and [E]0 is the caller's, so a
        # lumped Vmax can never be resolved from any paper.
        for name, motif in ENZYMOLOGY_LIBRARY.items():
            names = {p.name.lower() for p in motif.parameters}
            assert "vmax" not in names, f"{name} reintroduced a lumped Vmax"
        assert len(ENZYMOLOGY_LIBRARY) == 3

    def test_no_concentration_is_a_parameter_of_a_new_motif(self) -> None:
        # A concentration is what is in the tube, so it is a species with an
        # initial amount, never a constant the literature could be asked
        # for. ATP is the interesting case: it is a species of
        # `futile_cycle`, not a number folded into the kinase's rate.
        offenders = [
            f"{name}.{p.name}"
            for name, motif in ENZYMOLOGY_LIBRARY.items()
            for p in motif.parameters
            if p.kind == KIND_CONCENTRATION
        ]
        assert offenders == []
        assert "ATP" in {p.name for p in FUTILE_CYCLE.ports}

    def test_every_new_motif_states_what_licenses_it_and_where_it_fails(self) -> None:
        for name, motif in ENZYMOLOGY_LIBRARY.items():
            assert motif.summary, f"{name} has no summary"
            assert "fails" in motif.basis, (
                f"{name}'s basis does not say where the mechanism stops "
                f"holding, which is the half of it that is worth reading"
            )
        assert set(ENZYMOLOGY_LIBRARY) == {
            "mwc_allostery", "substrate_channeling", "futile_cycle"
        }


class TestTheRegistryRefusesRatherThanGuessing:
    def test_nothing_here_redefines_a_motif_library_already_has(self) -> None:
        """The decision this module is built around.

        Six of the ten mechanisms it was asked for already existed. They are
        re-exported, not rewritten, and this pins that -- a duplicate rate
        law is a second answer to a question that already had one, and the
        merged dictionary would pick a winner without saying so.
        """
        assert set(LIBRARY) & set(ENZYMOLOGY_LIBRARY) == set()
        for motif in (
            UNCOMPETITIVE_INHIBITION, MIXED_INHIBITION, NONCOMPETITIVE_INHIBITION,
            PRODUCT_INHIBITION, ORDERED_BI_BI, PING_PONG_BI_BI,
        ):
            assert LIBRARY[motif.name] is motif
        assert len(FULL_LIBRARY) == len(LIBRARY) + len(ENZYMOLOGY_LIBRARY)

    def test_an_unknown_name_is_refused_with_the_names_that_exist(self) -> None:
        with pytest.raises(KeyError) as raised:
            enzymology_motif("mwc_alostery")
        message = str(raised.value)
        assert "mwc_allostery" in message
        assert "Aliases" in message

    def test_a_known_name_comes_back_as_the_registry_s_own_object(self) -> None:
        assert enzymology_motif("mwc_allostery") is MWC_ALLOSTERY
        assert enzymology_motif("futile_cycle") is FUTILE_CYCLE
        assert enzymology_motif("substrate_channeling") is SUBSTRATE_CHANNELING
