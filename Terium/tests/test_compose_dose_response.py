"""The curve a pharmacologist measures, computed from the mechanism.

The tests that matter here are ANALYTIC. A clamped catalytic step feeding a
first-order outflow settles at

    P = (kcat * E / k_out) * S / (Km + S)

which is a Michaelis-Menten curve in the dose exactly, so the fit must come
back with a Hill slope of 1 and an EC50 equal to Km -- not approximately,
to the last few bits. A cooperative motif with exponent h must give back h.
Numbers that merely looked plausible would not do either.

The other half of the file pins the REFUSALS, which are the reason to
prefer this module to fitting a logistic to anything four numbers will
accommodate: a biphasic curve has no EC50, a dose with two stable states
has no single readout, and a dose with none has nothing to plot.
"""

from __future__ import annotations

import inspect
import math
import re
import types

import pytest

from Terium.compose import dose_response
from Terium.compose.analysis import DEFAULT_STARTS_PER_SPECIES
from Terium.compose.bifurcation import logarithmic_values
from Terium.compose.builder import Composition
from Terium.compose.dose_response import (
    FLAT_TOLERANCE, MINIMUM_DOSES, MONOTONIC_TOLERANCE, PLATEAU_FRACTION,
    STARTS_PER_SPECIES, DosePoint, DoseResponse, DoseResponseUnavailable, HillFit,
    NotMonotonic, clamped, curve, curve_for_model, dose_unit_of,
    dynamic_range, ec50, emax, fit_hill, hill_response,
)
from Terium.compose.library import (
    CATALYTIC_STEP, COMPETITIVE_INHIBITION, COOPERATIVE_CATALYSIS,
    FIRST_ORDER_OUTFLOW, SUBSTRATE_INHIBITION,
)
from Terium.compose.pipeline import compose
from Terium.core.network import Parameter, Reaction, ReactionNetwork, Species


#: The dose ladder every curve below is computed on: six decades around the
#: library's Km of 0.1 mM, logarithmically spaced. Log spacing because a
#: dose-response IS a log-dose plot -- a linear ladder over the same range
#: would spend nine tenths of its points on the plateau and none where the
#: curve turns, which is where an EC50 lives.
DOSES = logarithmic_values(1e-4, 1e2, steps=25)


def _readout_network(motif, prefix: str = "e"):
    """A motif whose product is drained first order, so it has a steady state.

    The drain is not decoration. Clamping the substrate of a catalytic step
    leaves dP/dt strictly positive, so the product accumulates for ever and
    there is no steady state to read at any dose -- which is a refusal this
    file also tests. Adding a first-order outflow gives the readout somewhere
    to settle, and makes the steady state an exact function of the dose.
    """
    composition = Composition("dose_response")
    composition.add(motif, prefix)
    composition.add(FIRST_ORDER_OUTFLOW, "out", bindings={"S": f"{prefix}_P"})
    return composition.to_network()


def _with_parameter(network, name: str, value: float):
    from dataclasses import replace

    return replace(
        network,
        parameters=tuple(
            replace(p, value=float(value)) if p.id == name else p
            for p in network.parameters
        ),
    )


def _value_of(network, name: str) -> float:
    return next(p.value for p in network.parameters if p.id == name)


# -- shared, because each curve is 25 global steady-state searches ----------


@pytest.fixture(scope="module")
def michaelis_menten():
    return curve(_readout_network(CATALYTIC_STEP), "e_S", "e_P", DOSES)


@pytest.fixture(scope="module")
def substrate_inhibition():
    return curve(_readout_network(SUBSTRATE_INHIBITION), "e_S", "e_P", DOSES)


@pytest.fixture(scope="module")
def occupancy():
    """A receptor occupied by a clamped ligand -- the pharmacologist's own case.

    Built from a sentence rather than by hand, so it carries the model's
    unmeasured constants and its declared concentration unit with it.
    """
    model = compose("reversible binding of a ligand to a receptor")
    return model, curve_for_model(
        model, "complex_A", "complex_AB", logarithmic_values(1e-3, 1e1, steps=21)
    )


class TestAgainstAnAnalyticAnswer:
    """The case where the answer is known in closed form.

    A clamped catalytic step draining first order has

        P(S) = (kcat * E / k_out) * S / (Km + S)

    -- a rectangular hyperbola in the dose. Its Hill slope is 1 and its
    half-maximal dose is Km, for every value of every other constant. If the
    machinery cannot reproduce that, nothing it says about a harder curve is
    worth reading.
    """

    def test_the_hill_slope_of_a_michaelis_menten_readout_is_exactly_one(
        self, michaelis_menten,
    ) -> None:
        # Measured at 1.0 to every bit. The tolerance is 1e-9 rather than
        # exact equality so that a solver upgrade losing the last three
        # digits does not fail a test about biochemistry -- but 1e-9 is
        # still eight orders tighter than the difference between a slope of
        # 1 and any other number anyone would report.
        fit = fit_hill(michaelis_menten)
        assert fit.hill_slope == pytest.approx(1.0, abs=1e-9)

    def test_its_ec50_is_the_michaelis_constant(self, michaelis_menten) -> None:
        # Read off the network rather than written as 0.1, so the test still
        # means what it says if the library's illustrative Km changes.
        km = _value_of(_readout_network(CATALYTIC_STEP), "e_Km")
        assert fit_hill(michaelis_menten).ec50 == pytest.approx(km, rel=1e-9)
        assert ec50(michaelis_menten) == pytest.approx(km, rel=1e-9)

    def test_every_computed_point_is_the_michaelis_menten_expression(
        self, michaelis_menten,
    ) -> None:
        """The curve itself, before any fitting.

        A fit that recovered the right EC50 from the wrong points would be a
        coincidence; this is the check that the steady states are the
        analytic ones, which is what makes the fit's agreement mean
        something.
        """
        network = _readout_network(CATALYTIC_STEP)
        top = (
            _value_of(network, "e_kcat")
            * next(s.initial for s in network.species if s.id == "e_E")
            / _value_of(network, "out_k_out")
        )
        km = _value_of(network, "e_Km")

        assert top == pytest.approx(1.0), "the premise: an asymptote of 1"
        for point in michaelis_menten.points:
            expected = top * point.dose / (km + point.dose)
            assert point.response == pytest.approx(expected, rel=1e-9), point.dose

    def test_the_fit_reproduces_the_curve_to_machine_precision(
        self, michaelis_menten,
    ) -> None:
        # The residual is reported because a Hill fit will return four
        # numbers for any curve at all. Here it is the evidence that those
        # four numbers describe THIS curve rather than merely summarising it.
        fit = fit_hill(michaelis_menten)
        assert fit.residual < 1e-12
        assert fit.relative_residual < 1e-12
        assert fit.degrees_of_freedom == len(DOSES) - 4

    def test_emax_is_the_largest_response_observed_not_the_asymptote(
        self, michaelis_menten,
    ) -> None:
        """Two different numbers, and the difference is the point.

        The fitted asymptote is the response at infinite dose, which no
        experiment applies. `emax` is the largest readout at a dose that was
        actually used -- here 0.999 against an asymptote of 1.0, because the
        top dose is a thousand Km rather than infinitely many.
        """
        fit = fit_hill(michaelis_menten)
        assert emax(michaelis_menten) == pytest.approx(
            michaelis_menten.points[-1].response
        )
        assert emax(michaelis_menten) < fit.saturated
        assert fit.saturated == pytest.approx(1.0, rel=1e-9)

    def test_dynamic_range_is_a_span_and_not_a_fold_change(
        self, michaelis_menten,
    ) -> None:
        # A fold change would be the more familiar number and is undefined
        # here: this readout starts at essentially zero, and a ratio against
        # it is arbitrarily large.
        span = emax(michaelis_menten) - michaelis_menten.baseline
        assert dynamic_range(michaelis_menten) == pytest.approx(span)
        assert michaelis_menten.baseline < 1e-3, "the premise: near-zero basal"

    def test_a_receptor_occupied_by_a_ligand_has_ec50_equal_to_kd(
        self, occupancy,
    ) -> None:
        """The second exact case, and the one pharmacology is written about.

        Clamped ligand on a reversible binding motif gives occupancy
        R_total * L / (Kd + L) with Kd = koff / kon, so the EC50 is the
        dissociation constant exactly and the slope is 1 -- one site, no
        cooperativity, nothing to be cooperative with.
        """
        model, response = occupancy
        kon = _value_of(model.network, "complex_kon")
        koff = _value_of(model.network, "complex_koff")
        fit = fit_hill(response)

        assert fit.ec50 == pytest.approx(koff / kon, rel=1e-9)
        assert fit.hill_slope == pytest.approx(1.0, abs=1e-9)


class TestCooperativity:
    """A motif with exponent h must give back h, and a different h.

    The second half matters as much as the first: a fit that always returned
    1 would pass a test that only ever asked about a Hill-1 curve, and a fit
    that always returned the same constant would pass a test that only ever
    asked one value of h.
    """

    @pytest.mark.parametrize("exponent", [1.5, 3.0, 4.0])
    def test_the_slope_comes_back_as_the_motifs_own_exponent(
        self, exponent,
    ) -> None:
        network = _with_parameter(
            _readout_network(COOPERATIVE_CATALYSIS), "e_h", exponent
        )
        fit = fit_hill(curve(network, "e_S", "e_P", DOSES))

        assert fit.hill_slope == pytest.approx(exponent, rel=1e-6)
        # And the midpoint is the motif's own half-saturation constant, so
        # the slope was not bought by sliding the curve sideways.
        assert fit.ec50 == pytest.approx(_value_of(network, "e_K"), rel=1e-6)

    def test_a_non_integer_exponent_gives_a_non_integer_slope(self) -> None:
        """The sharpest form of "this is not a subunit count".

        1.5 is not a number of binding sites. A mechanism can produce it, a
        fit recovers it, and any reading of the slope as a count has to
        explain half a site.
        """
        network = _with_parameter(
            _readout_network(COOPERATIVE_CATALYSIS), "e_h", 1.5
        )
        slope = fit_hill(curve(network, "e_S", "e_P", DOSES)).hill_slope

        assert slope == pytest.approx(1.5, rel=1e-6)
        assert abs(slope - round(slope)) > 0.4, "nowhere near an integer"


class TestTheHillSlopeIsNotASubunitCount:
    """The correction has to travel with the number.

    This is the most commonly misread quantity in the subject, and a module
    that computes it and stays quiet has published the misreading. These
    tests pin the correction in the three places a reader can meet the
    number: the module's own account of itself, the field it is stored on,
    and the sentence printed beside the value.
    """

    def test_the_module_docstring_says_so(self) -> None:
        assert "A FITTED HILL SLOPE IS NOT A SUBUNIT COUNT" in dose_response.__doc__
        assert "Haemoglobin has four sites" in dose_response.__doc__

    def test_the_field_it_is_stored_on_says_so(self) -> None:
        source = inspect.getsource(HillFit)
        assert "NOT a count of binding sites" in source
        assert "NOT a count of subunits" in source
        assert "Haemoglobin has four sites" in source

    def test_the_printed_result_says_so(self, michaelis_menten) -> None:
        """Not only in a docstring nobody reads at the terminal."""
        described = fit_hill(michaelis_menten).describe()
        assert "THE HILL SLOPE IS NOT A SUBUNIT COUNT" in described
        assert "not the number of binding sites" in described

    def test_it_says_why_a_slope_computed_from_a_rate_law_is_worse(
        self, michaelis_menten,
    ) -> None:
        # The slope here agrees with the exponent in the rate law BECAUSE
        # somebody wrote that exponent down. Presenting the agreement
        # without saying so would promote a modelling assumption into a
        # finding about a protein.
        described = fit_hill(michaelis_menten).describe()
        assert "assumption of the model rather than a measurement" in described


class TestABiphasicCurveIsRefused:
    """Substrate inhibition, which the library ships as a motif.

    v = kcat * E * S / (Km + S + S^2/Ksi) rises to a maximum at
    sqrt(Km * Ksi) and falls away on both sides of it. Every response
    between the ends is reached at TWO doses, so "the dose at half-maximal
    response" names two numbers, and an EC50 fitted to it would be a number
    with no referent.
    """

    def test_the_curve_really_does_turn_around(self, substrate_inhibition) -> None:
        """The premise, and the analytic check on it.

        The peak of substrate inhibition sits at sqrt(Km * Ksi), which for
        the library's illustrative values is exactly 1 -- and 1 is one of
        the doses on the ladder, so the computed peak lands on it.
        """
        network = _readout_network(SUBSTRATE_INHIBITION)
        predicted = math.sqrt(
            _value_of(network, "e_Km") * _value_of(network, "e_Ksi")
        )
        assert substrate_inhibition.peak.dose == pytest.approx(predicted, rel=1e-9)
        assert not substrate_inhibition.monotonic
        assert substrate_inhibition.reversal > 0.5

    def test_fitting_it_is_refused_and_the_refusal_names_the_peak(
        self, substrate_inhibition,
    ) -> None:
        with pytest.raises(NotMonotonic) as caught:
            fit_hill(substrate_inhibition)

        message = str(caught.value)
        assert "biphasic" in message
        assert "TWO doses at every response" in message
        # The dose it turns at, so the reader can act on the refusal rather
        # than only be stopped by it.
        assert f"{substrate_inhibition.peak.dose:.4g}" in message

    def test_the_named_readout_refuses_too(self, substrate_inhibition) -> None:
        # `ec50` is the function somebody actually calls; a refusal that
        # lived only in `fit_hill` would be routed around by accident.
        with pytest.raises(NotMonotonic):
            ec50(substrate_inhibition)

    def test_the_refusal_says_what_to_report_instead(
        self, substrate_inhibition,
    ) -> None:
        with pytest.raises(NotMonotonic) as caught:
            fit_hill(substrate_inhibition)

        message = str(caught.value)
        assert "Report instead" in message
        assert "sqrt(Km * Ksi)" in message
        assert "the mechanism's own constants" in message

    def test_emax_and_dynamic_range_are_still_returned(
        self, substrate_inhibition,
    ) -> None:
        """The refusal is narrow on purpose.

        The peak really is the largest response and the span really is the
        span; only the EC50 and the slope assume a shape this curve does not
        have. Refusing the whole curve would be a larger claim than the true
        one and would throw away two readouts that are fine.
        """
        assert emax(substrate_inhibition) == pytest.approx(
            substrate_inhibition.peak.response
        )
        assert dynamic_range(substrate_inhibition) > 0.5

    def test_it_is_a_distinct_exception_from_a_failure_to_compute(self) -> None:
        # A caller retrying on DoseResponseUnavailable must not retry this
        # one: no number of extra doses makes a quantity exist that does not.
        assert issubclass(NotMonotonic, DoseResponseUnavailable)
        assert NotMonotonic is not DoseResponseUnavailable

    def test_a_monotone_curve_is_not_refused(self, michaelis_menten) -> None:
        # Without this the refusal above would pass on an implementation
        # that refused everything.
        assert michaelis_menten.monotonic
        assert fit_hill(michaelis_menten).ec50 > 0

    def test_the_threshold_separates_the_two_measured_curves_by_orders(
        self, michaelis_menten, substrate_inhibition,
    ) -> None:
        """The constant is a measurement, not a taste.

        The Michaelis-Menten curve reverses by 0.0 and substrate inhibition
        by 0.89. If those two ever came within an order of magnitude of each
        other the threshold would be deciding the answer, and this test is
        what would say so.
        """
        assert michaelis_menten.reversal < MONOTONIC_TOLERANCE / 100
        assert substrate_inhibition.reversal > MONOTONIC_TOLERANCE * 100


class TestADoseWithNoSingleReadoutIsNamedNotDropped:
    """The point that is missing is a behaviour, not a number.

    Dropping it would close the gap and draw a smooth curve through what is
    left, which is a picture of a different mechanism.
    """

    def _switch(self):
        """X with quadratic positive feedback, first-order removal, and a
        clamped inducer feeding it.

            dX/dt = inducer + v * X^2 / (K^2 + X^2) - kd * X

        With v = K = 1 and kd = 0.3 the zero-dose system has two stable
        states -- X = 0 and X = 3 -- because 0.3 is below the maximum of
        X / (1 + X^2), which is 0.5. Raising the inducer lifts the low
        branch until it annihilates with the unstable one near 0.024, above
        which the system is monostable. Hand-built rather than composed: no
        motif in the library wires a species to its own activation.
        """
        return ReactionNetwork(
            name="switch",
            species=(Species("X", 0.1), Species("inducer", 0.0)),
            parameters=(
                Parameter("v", 1.0), Parameter("K", 1.0), Parameter("kd", 0.3),
            ),
            reactions=(
                Reaction("induction", {}, {"X": 1}, "inducer"),
                Reaction("feedback", {}, {"X": 1}, "v * X^2 / (K^2 + X^2)"),
                Reaction("removal", {"X": 1}, {}, "kd * X"),
            ),
        )

    def test_two_stable_states_at_a_dose_is_a_refusal_naming_that_dose(
        self,
    ) -> None:
        with pytest.raises(DoseResponseUnavailable) as caught:
            curve(self._switch(), "inducer", "X", [0.005, 0.05, 0.5])

        message = str(caught.value)
        assert "2 stable steady states at a dose of 0.005" in message
        assert "hysteresis" in message
        assert "averaging them would report a state the system is never in" in message

    def test_the_same_model_gives_a_curve_where_it_is_monostable(self) -> None:
        """So the refusal is about the dose, not about the model.

        Above the fold the switch has one stable state at every dose and the
        curve computes without complaint -- which is what makes the refusal
        above a finding rather than a limitation.
        """
        response = curve(
            self._switch(), "inducer", "X", [0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        )
        assert len(response.points) == 6
        assert response.monotonic

    def test_no_stable_state_at_a_dose_is_a_refusal_naming_that_dose(self) -> None:
        """A catalytic step with nothing draining its product.

        dP/dt is strictly positive at any dose above zero, so the product
        accumulates for ever. There is no steady state to read, and the
        honest output is to say which dose and why rather than to plot the
        doses that happened to converge.
        """
        composition = Composition("undrained")
        composition.add(CATALYTIC_STEP, "e")

        with pytest.raises(DoseResponseUnavailable) as caught:
            curve(composition.to_network(), "e_S", "e_P", [0.05, 0.5])

        message = str(caught.value)
        assert "no stable steady state at a dose of 0.05" in message
        assert "This point is NOT dropped" in message
        assert "time course" in message

    def test_the_search_is_as_deep_as_the_refusal_needs(self) -> None:
        """A refusal about multiplicity is only as good as the search.

        This used to assert `STARTS_PER_SPECIES > DEFAULT_STARTS_PER_SPECIES`
        on the strength of a measurement that the analysis default missed
        a second state. That measurement was of continuum points, not
        stable states, and once they were classified correctly the two
        depths were unified by reference. What is still worth holding: this
        module searches at the package's one depth, and a caller can go
        shallower and see that it did.
        """
        network = _readout_network(CATALYTIC_STEP)
        deep = curve(network, "e_S", "e_P", [0.1, 1.0])
        shallow = curve(network, "e_S", "e_P", [0.1, 1.0], starts_per_species=2)

        assert deep.starts_per_species == STARTS_PER_SPECIES
        assert STARTS_PER_SPECIES == DEFAULT_STARTS_PER_SPECIES
        assert deep.points[0].starts_tried > shallow.points[0].starts_tried


class TestTheDoseIsHeldNotConsumed:
    """Why the input is clamped, stated as the thing that goes wrong otherwise.

    A closed Michaelis-Menten model conserves S + P, so its steady state is
    P = S0 whatever the kinetics are. The "dose-response" that falls out is
    the line P = dose: every point correct, the figure meaningless.
    """

    def test_clamping_moves_the_species_to_a_parameter(self) -> None:
        network = _readout_network(CATALYTIC_STEP)
        held = clamped(network, "e_S", 0.25)

        assert "e_S" not in [s.id for s in held.species]
        assert next(p.value for p in held.parameters if p.id == "e_S") == 0.25
        # The rate law is untouched: every symbol that meant the species now
        # means the parameter, which is the whole trick.
        assert held.reactions[0].rate_law == network.reactions[0].rate_law
        assert held.problems() == []

    def test_clamping_takes_the_species_out_of_the_stoichiometry(self) -> None:
        """And so removes the conservation law that pinned the readout.

        Exact, from the left null space of the stoichiometry matrix, so this
        is a structural statement rather than a numerical one. Shown on the
        CLOSED model -- a catalytic step with nothing draining its product
        -- because that is the one whose readout the law pins.
        """
        composition = Composition("closed")
        composition.add(CATALYTIC_STEP, "e")
        network = composition.to_network()

        before = [set(law) for law in network.conservation_laws()]
        after = [set(law) for law in clamped(network, "e_S", 0.25).conservation_laws()]

        assert {"e_S", "e_P"} in before
        assert {"e_S", "e_P"} not in after
        assert {"e_E"} in after, "the enzyme is still conserved"

    def test_the_closed_model_answers_the_mass_balance_instead(self) -> None:
        """The wrong answer, computed, so the design is not taken on trust.

        Started at S = 0.5 the closed model ends at P = 0.5 -- and does so
        for a Km a hundred-fold different, because the destination is set by
        the conservation law and not by the kinetics at all.
        """
        from dataclasses import replace

        from Terium.compose.analysis import analyse

        composition = Composition("closed")
        composition.add(CATALYTIC_STEP, "e")
        closed = composition.to_network()

        landings = []
        for km in (0.1, 10.0):
            network = replace(
                closed,
                species=tuple(
                    replace(s, initial=0.5) if s.id == "e_S" else s
                    for s in closed.species
                ),
                parameters=tuple(
                    replace(p, value=km) if p.id == "e_Km" else p
                    for p in closed.parameters
                ),
            )
            report = analyse(network, starts_per_species=STARTS_PER_SPECIES)
            landings.append(report.stable_points[0].state["e_P"])

        assert landings[0] == pytest.approx(0.5, abs=1e-9)
        assert landings[1] == pytest.approx(0.5, abs=1e-9)

    def test_clamping_something_that_is_not_a_species_is_refused(self) -> None:
        network = _readout_network(CATALYTIC_STEP)
        with pytest.raises(DoseResponseUnavailable, match="no species"):
            clamped(network, "e_Km", 1.0)

    def test_dosing_a_parameter_points_at_the_sweep_instead(self) -> None:
        # A rate constant is not something anyone pipettes, and the question
        # "what if the enzyme were faster" has its own tool.
        network = _readout_network(CATALYTIC_STEP)
        with pytest.raises(DoseResponseUnavailable) as caught:
            curve(network, "e_kcat", "e_P", DOSES)
        assert "bifurcation" in str(caught.value)


class TestTheDirectionIsCarriedByTheAsymptotes:
    """An inhibitor falls, and its slope is still positive.

    The model is invariant under swapping the asymptotes and negating the
    slope, so allowing both would make the fit non-identifiable and which of
    the two equivalent answers came back would depend on the starting guess.
    """

    @pytest.fixture(scope="class")
    def inhibition(self):
        """Competitive inhibition with the substrate held and the drug dosed.

        P = kcat*E*S / (k_out * (Km*(1 + I/Ki) + S)), which is exactly a
        falling Hill-1 curve in I with

            IC50 = Ki * (Km + S) / Km

        -- 5.5 mM for the library's illustrative values at S = 1.
        """
        network = clamped(_readout_network(COMPETITIVE_INHIBITION), "e_S", 1.0)
        return network, curve(
            network, "e_I", "e_P", logarithmic_values(1e-2, 1e3, steps=25)
        )

    def test_the_ic50_is_the_analytic_one(self, inhibition) -> None:
        network, response = inhibition
        predicted = (
            _value_of(network, "e_Ki")
            * (_value_of(network, "e_Km") + _value_of(network, "e_S"))
            / _value_of(network, "e_Km")
        )
        fit = fit_hill(response)

        assert predicted == pytest.approx(5.5), "the premise"
        assert fit.ec50 == pytest.approx(predicted, rel=1e-9)

    def test_the_slope_stays_positive_and_the_asymptotes_swap(
        self, inhibition,
    ) -> None:
        _, response = inhibition
        fit = fit_hill(response)

        assert fit.hill_slope == pytest.approx(1.0, abs=1e-9)
        assert fit.saturated < fit.basal
        assert not fit.rising

    def test_a_falling_curve_is_described_as_an_ic50(self, inhibition) -> None:
        # Same arithmetic, different word, because that is the word the
        # literature the number is being compared with uses.
        _, response = inhibition
        described = fit_hill(response).describe()
        assert described.startswith("IC50 = 5.5")
        assert "EC50" not in described.split(".")[0]

    def test_negating_the_slope_and_swapping_the_asymptotes_is_the_same_curve(
        self,
    ) -> None:
        """The non-identifiability the positive bound removes, stated exactly.

            b + (s - b) * sigma(n * ln(d/e))
              == s + (b - s) * sigma(-n * ln(d/e))

        for every dose, because sigma(-x) = 1 - sigma(x). The two
        parameterisations are not merely similar: they are the same
        function, so a fit free to choose between them is choosing on the
        starting guess rather than on the data, and the sign of a reported
        Hill slope would stop meaning anything.

        Tested against `hill_response` rather than through a fit, because
        through a fit it currently cannot be violated -- the optimiser
        starts at +1 and never has a reason to cross zero. A mutation
        removing the bound came back NOT CAUGHT for exactly that reason, so
        the claim is pinned where it can actually fail.
        """
        for dose in (1e-6, 0.001, 0.05, 0.3, 2.0, 50.0, 1e6):
            rising = hill_response(dose, 0.2, 1.4, 0.3, 2.0)
            falling = hill_response(dose, 1.4, 0.2, 0.3, -2.0)
            assert rising == pytest.approx(falling, rel=1e-12), dose
        # And the curve is not constant, or the equality above would hold
        # for a function that ignored its arguments.
        assert hill_response(1e-6, 0.2, 1.4, 0.3, 2.0) < hill_response(
            50.0, 0.2, 1.4, 0.3, 2.0
        )


class TestTheFitReportsItsOwnLimits:
    def test_a_curve_that_never_plateaus_says_the_top_is_extrapolated(self) -> None:
        """The commonest way a published EC50 is wrong, and it is invisible
        in the number.

        EC50 is defined against the maximum. Stop dosing before the plateau
        and the fit supplies a maximum nobody observed, which propagates
        straight into the half-maximal dose. These doses stop at three times
        the Km, which is 75% of the way up.
        """
        response = curve(
            _readout_network(CATALYTIC_STEP), "e_S", "e_P",
            logarithmic_values(1e-3, 0.3, steps=15),
        )
        fit = fit_hill(response)

        assert fit.approach == pytest.approx(0.75, rel=1e-6)
        assert not fit.saturating
        assert fit.approach < PLATEAU_FRACTION
        assert "THE PLATEAU WAS NOT REACHED" in fit.describe()

    def test_a_curve_that_does_plateau_does_not_say_it(
        self, michaelis_menten,
    ) -> None:
        fit = fit_hill(michaelis_menten)
        assert fit.saturating
        assert "THE PLATEAU WAS NOT REACHED" not in fit.describe()

    def test_too_few_doses_is_refused_rather_than_interpolated(self) -> None:
        """Four points fix four parameters and the residual stops meaning
        anything."""
        response = curve(
            _readout_network(CATALYTIC_STEP), "e_S", "e_P", [0.01, 0.1, 1.0, 10.0]
        )
        with pytest.raises(DoseResponseUnavailable) as caught:
            fit_hill(response)

        assert "degrees of freedom" in str(caught.value)
        assert len(response.points) < MINIMUM_DOSES

    def test_a_flat_curve_is_refused_with_the_reason(self) -> None:
        """An EC50 fitted to a flat line is the dose at the middle of nothing.

        Reached here by dosing an inhibitor that is not there: the
        uncompetitive term is present in the rate law, so the dose IS
        connected to the readout, but at a Ki far above every dose tested
        nothing moves.
        """
        network = _with_parameter(
            clamped(_readout_network(COMPETITIVE_INHIBITION), "e_S", 1.0),
            "e_Ki", 1e12,
        )
        response = curve(network, "e_I", "e_P", [1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0])

        assert response.flat
        with pytest.raises(DoseResponseUnavailable) as caught:
            fit_hill(response)
        assert "no curve here to find a midpoint of" in str(caught.value)

    def test_the_hill_function_is_the_hill_equation(self) -> None:
        """The logistic form the fit evaluates, against the textbook one.

        Written as a logistic in log dose so it cannot overflow at a steep
        slope far from the midpoint; that is an arithmetic change and must
        not be an algebraic one.
        """
        for dose in (1e-6, 0.01, 0.3, 1.0, 7.0, 1e6):
            for slope in (0.5, 1.0, 2.8, 6.0):
                direct = dose**slope / (0.3**slope + dose**slope)
                assert hill_response(dose, 0.0, 1.0, 0.3, slope) == pytest.approx(
                    direct, rel=1e-12
                ), (dose, slope)
        # A dose of zero is the vehicle control, not a limit to approach.
        assert hill_response(0.0, 0.2, 1.0, 0.3, 2.0) == 0.2


class TestTheUnitIsRecoveredNotAssumed:
    """An EC50 without its unit cannot be compared with a measured one.

    Neither `Species` nor `Parameter` carries a unit in the IR -- the unit
    lives on the MotifParameter and is dropped at build time -- so the unit
    has to be recovered from the composition, with `scale.units_from_model`
    as the check on it.
    """

    def _model_with_unit(self, unit: str):
        composition = Composition("units", concentration_unit=unit)
        composition.add(CATALYTIC_STEP, "e")
        composition.add(FIRST_ORDER_OUTFLOW, "out", bindings={"S": "e_P"})
        return types.SimpleNamespace(
            recognition=types.SimpleNamespace(composition=composition),
            network=composition.to_network(),
            resolvable=(),
        )

    def test_a_composed_model_carries_its_unit_onto_the_ec50(
        self, occupancy,
    ) -> None:
        model, response = occupancy
        assert dose_unit_of(model) == "mM"
        assert response.dose_unit == "mM"
        assert "EC50 = 0.1 mM" in fit_hill(response).describe()

    def test_a_bare_network_gets_no_unit_rather_than_an_assumed_one(
        self, michaelis_menten,
    ) -> None:
        # A wrong unit on a number offered for comparison is worse than no
        # unit, because the comparison will be made either way.
        assert michaelis_menten.dose_unit is None
        assert "mM" not in fit_hill(michaelis_menten).describe()
        assert dose_unit_of(types.SimpleNamespace()) is None

    def test_an_affinity_in_another_unit_is_refused_rather_than_guessed(
        self,
    ) -> None:
        """The rate law adds Km to S. In different units that is wrong by a
        factor of a thousand, and an EC50 read off it would be quoted in one
        of two units with nothing to choose between them."""
        with pytest.raises(DoseResponseUnavailable) as caught:
            dose_unit_of(self._model_with_unit("uM"))

        message = str(caught.value)
        assert "species are in uM but e_Km is declared in mM" in message
        assert "added together inside a rate law" in message

    def test_the_units_it_accepts_are_the_ones_that_agree(self) -> None:
        # Without this the refusal above would pass on an implementation
        # that refused every model.
        assert dose_unit_of(self._model_with_unit("mM")) == "mM"


class TestWhatTheNumberIsNot:
    def test_the_summary_names_the_constants_with_no_measured_value(
        self, occupancy,
    ) -> None:
        """An EC50 computed on placeholders is a property of the SHAPE.

        The model's own account of what it could not resolve, not a guess
        from the parameter names.
        """
        model, response = occupancy
        summary = response.summary()

        assert set(response.unmeasured) == {
            q.parameter_id for q in model.resolvable
        }
        assert response.unmeasured, "the premise: nothing was grounded"
        assert "have no measured value behind them" in summary
        assert "not a prediction about any particular protein" in summary

    def test_a_bare_network_claims_nothing_about_grounding(
        self, michaelis_menten,
    ) -> None:
        # Empty means "not established", never "all grounded", so the
        # caveat is simply absent rather than replaced by a reassurance.
        assert michaelis_menten.unmeasured == ()
        assert "no measured value" not in michaelis_menten.summary()
        assert "grounded" not in michaelis_menten.summary()

    def test_the_summary_says_the_dose_was_held_rather_than_consumed(
        self, michaelis_menten,
    ) -> None:
        assert "held fixed at each point" in michaelis_menten.summary()
        assert "Computed from the mechanism, not fitted to data" in (
            michaelis_menten.summary()
        )

    def test_no_number_here_is_offered_with_a_citation(self) -> None:
        """A computed EC50 is not a measurement and must never look like one.

        Nothing in the module's output carries a reference, a DOI or a
        table name, because every number it produces is a consequence of
        the model rather than something read out of the literature.
        """
        source = inspect.getsource(dose_response)
        for pattern in (r"\bdoi\b", r"\bDOI\b", r"\bBRENDA\b",
                        r"\bet al\b", r"https?://"):
            assert not re.search(pattern, source), pattern


class TestTheCurveRefusesQuestionsWithNoAnswer:
    def test_reading_out_the_dose_itself_is_refused(self) -> None:
        network = _readout_network(CATALYTIC_STEP)
        with pytest.raises(DoseResponseUnavailable) as caught:
            curve(network, "e_S", "e_S", DOSES)
        assert "y = x" in str(caught.value)

    def test_a_dose_no_rate_law_mentions_is_refused(self) -> None:
        """A flat curve for a STRUCTURAL reason must not be reported as a
        pharmacological finding.

        `bystander` is declared and never referred to, so dosing it cannot
        change anything. Reporting the flat curve that results would invite
        the reading that the dose was tried and had no effect, which is a
        pharmacological claim about a model that never had the term in it.
        """
        network = ReactionNetwork(
            name="bystander_model",
            species=(Species("X", 1.0), Species("bystander", 1.0)),
            parameters=(Parameter("k", 1.0),),
            reactions=(Reaction("decay", {"X": 1}, {}, "k * X"),),
        )
        assert network.problems() == [], "the premise: a legal network"

        with pytest.raises(DoseResponseUnavailable) as caught:
            curve(network, "bystander", "X", DOSES)
        assert "no rate law in this network mentions" in str(caught.value)

    def test_a_negative_dose_is_refused(self) -> None:
        network = _readout_network(CATALYTIC_STEP)
        with pytest.raises(DoseResponseUnavailable) as caught:
            curve(network, "e_S", "e_P", [-1.0, 0.1, 1.0])
        assert "not a small dose" in str(caught.value)

    def test_one_dose_is_not_a_curve(self) -> None:
        network = _readout_network(CATALYTIC_STEP)
        with pytest.raises(DoseResponseUnavailable, match="not a curve"):
            curve(network, "e_S", "e_P", [0.1])

    def test_a_species_that_is_only_a_substring_of_another_is_not_mentioned(
        self,
    ) -> None:
        """`X` must not match `Xp`, which is the same rule as
        `sensitivity.law_mentions` and is here for the same reason.

        This network dephosphorylates Xp to X. Nothing reads X -- it is a
        pure sink -- so dosing it cannot change anything and the refusal is
        correct. A substring rule would find `X` inside `k * Xp`, conclude
        the dose was connected to the mechanism, and return a flat curve
        that reads as "the dose was tried and did nothing". Split out into
        its own test because that is where the token rule and the substring
        rule actually disagree, and a rule that cannot be told from its own
        bug is not yet a rule.
        """
        network = ReactionNetwork(
            name="dephosphorylation",
            species=(Species("X", 0.0), Species("Xp", 1.0)),
            parameters=(Parameter("k", 1.0),),
            reactions=(Reaction("dephos", {"Xp": 1}, {"X": 1}, "k * Xp"),),
        )
        assert network.problems() == [], "the premise: a legal network"

        with pytest.raises(DoseResponseUnavailable) as caught:
            curve(network, "X", "Xp", DOSES)
        assert "no rate law in this network mentions 'X'" in str(caught.value)

    def test_an_unknown_readout_is_refused_by_name(self) -> None:
        network = _readout_network(CATALYTIC_STEP)
        with pytest.raises(DoseResponseUnavailable) as caught:
            curve(network, "e_S", "e_Q", DOSES)
        assert "no species 'e_Q' to read out" in str(caught.value)


class TestAnInhibitorHasAnEmax:
    """`emax` and `dynamic_range` read the PEAK, the largest response.

    For a rising curve that is the maximal effect. For a falling one --
    an inhibitor titrated against a readout it suppresses -- the largest
    response is at the lowest dose, where nothing has happened yet. So an
    inhibitor's Emax was reported as its vehicle control, and its dynamic
    range as `baseline - baseline`: exactly zero, for every inhibitor,
    always. Emax is maximal EFFECT, and for an inhibitor the effect is the
    fall.
    """

    @staticmethod
    def _curve(responses):
        points = tuple(
            DosePoint(dose=float(i), response=float(r), residual=0.0, starts_tried=8)
            for i, r in enumerate(responses)
        )
        return DoseResponse(input_species="I", readout="P", points=points)

    def test_a_falling_curve_has_a_negative_dynamic_range(self) -> None:
        falling = self._curve([1.0, 0.8, 0.5, 0.2, 0.1])
        assert dynamic_range(falling) == pytest.approx(-0.9)
        assert dynamic_range(falling) != 0.0, "every inhibitor's range was zero"

    def test_a_falling_curve_emax_is_its_lowest_response(self) -> None:
        falling = self._curve([1.0, 0.8, 0.5, 0.2, 0.1])
        assert emax(falling) == pytest.approx(0.1)
        assert emax(falling) != falling.baseline, (
            "the vehicle control was reported as the drug's Emax"
        )

    def test_a_rising_curve_is_unchanged(self) -> None:
        rising = self._curve([0.1, 0.3, 0.6, 0.9, 1.0])
        assert emax(rising) == pytest.approx(1.0)
        assert dynamic_range(rising) == pytest.approx(0.9)
        assert rising.extreme is rising.peak

    def test_the_sign_is_the_direction(self) -> None:
        assert dynamic_range(self._curve([0.1, 1.0])) > 0
        assert dynamic_range(self._curve([1.0, 0.1])) < 0

    def test_a_biphasic_curve_still_reports_its_peak(self) -> None:
        # Substrate inhibition rises then falls; the extreme is wherever the
        # readout got furthest from where it started, which here is the peak.
        biphasic = self._curve([0.1, 0.6, 1.0, 0.7, 0.4])
        assert emax(biphasic) == pytest.approx(1.0)
        assert biphasic.extreme is biphasic.peak

    def test_a_biphasic_curve_that_ends_below_its_start(self) -> None:
        # ...and when the fall goes further than the rise, the extreme is
        # the fall. Whichever effect is larger is the maximal one.
        overshoot = self._curve([0.5, 0.7, 0.6, 0.2, 0.0])
        assert emax(overshoot) == pytest.approx(0.0)
        assert dynamic_range(overshoot) == pytest.approx(-0.5)
