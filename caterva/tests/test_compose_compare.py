"""Two hypotheses, and the experiment that decides between them.

The module under test answers three questions in order -- are these two
models or one, where do their predictions differ, and can you measure the
difference -- and the tests here are built around the case where all three
have a known answer.

Competitive and uncompetitive inhibition are that case. They have the same
species, the same reaction and the same stoichiometry, and differ only in
what the rate law does with the inhibitor. Their rates are closed-form, so
every prediction below can be checked against algebra rather than against a
previous run:

    competitive     v = kcat*E*S / (Km*(1 + I/Ki) + S)
    uncompetitive   v = kcat*E*S / (Km + S*(1 + I/Ki))

Three facts follow from those two lines and nothing else, and they are what
this file pins:

    they CROSS at exactly S = Km, for every kcat, E, I and Ki, so an assay
    run there separates them by nothing at any precision;

    they diverge most at SATURATING substrate, because competitive
    inhibition is surmountable -- v -> kcat*E as S grows, whatever the
    inhibitor does -- and uncompetitive inhibition is not, settling at
    kcat*E/(1 + I/Ki);

    with NO inhibitor both collapse to Michaelis-Menten and are the same
    model, so there is no experiment and the honest answer is to say so.

The last one is the reason the module has a refusal in it at all.
"""

from __future__ import annotations

import math
import time
from dataclasses import replace

import pytest

from caterva.compose import compare
from caterva.compose.builder import Composition
from caterva.compose.compare import (
    DECISIVE, DEFAULT_DOSE_DECADES, DEFAULT_DOSE_POINTS, DEFAULT_PRECISION,
    MAX_PARTIAL_ASSIGNMENTS, MAX_SPECIES_FOR_ISOMORPHISM, MEASURABLE,
    STEADY_STATE_PRECISION, ComparisonRefused, ComparisonTooLarge, Dose,
    ModelsIndistinguishable, Observation, Precision, behavioural_difference,
    default_doses, default_readouts, discriminating_experiment,
    initial_rate_of, steady_state_of, structurally_identical,
)
from caterva.compose.library import (
    CATALYTIC_STEP, COMPETITIVE_INHIBITION, NONCOMPETITIVE_INHIBITION,
    UNCOMPETITIVE_INHIBITION,
)
from caterva.core.network import Parameter, Reaction, ReactionNetwork, Species


# -- the two models, and the constants they are built from ------------------
#
# Read from the motif rather than written down here. The analytic
# expressions below are checked against the model's OWN constants, so the
# tests stay analytic if the library's illustrative values ever move -- which
# they should be free to do, since they are placeholders.


def _default(motif, name: str) -> float:
    return float(next(p.default for p in motif.parameters if p.name == name))


def _initial(motif, name: str) -> float:
    return float(motif.port(name).default_initial)


#: The inhibitor is set to its own Ki, so 1 + I/Ki is exactly 2. Any positive
#: level would do; this one makes the algebra below checkable by eye.
INHIBITOR = _default(COMPETITIVE_INHIBITION, "Ki")
ALPHA = 1.0 + INHIBITOR / _default(COMPETITIVE_INHIBITION, "Ki")


def _inhibited(motif, name: str, inhibitor: float = INHIBITOR):
    composition = Composition(name)
    composition.add(motif, "reaction")
    composition.set_initial("reaction_I", inhibitor)
    return composition.to_network()


def _constants(network):
    values = {p.id: float(p.value) for p in network.parameters}
    initials = {s.id: float(s.initial) for s in network.species}
    return (
        values["reaction_kcat"], values["reaction_Km"], values["reaction_Ki"],
        initials["reaction_E"], initials["reaction_I"],
    )


def competitive_rate(substrate: float, network) -> float:
    kcat, km, ki, enzyme, inhibitor = _constants(network)
    return kcat * enzyme * substrate / (km * (1 + inhibitor / ki) + substrate)


def uncompetitive_rate(substrate: float, network) -> float:
    kcat, km, ki, enzyme, inhibitor = _constants(network)
    return kcat * enzyme * substrate / (km + substrate * (1 + inhibitor / ki))


@pytest.fixture(scope="module")
def competitive():
    return _inhibited(COMPETITIVE_INHIBITION, "competitive")


@pytest.fixture(scope="module")
def uncompetitive():
    return _inhibited(UNCOMPETITIVE_INHIBITION, "uncompetitive")


@pytest.fixture(scope="module")
def experiment(competitive, uncompetitive):
    """The default search, which several tests read. Shared because it
    evaluates 36 observations and no test mutates it."""
    return discriminating_experiment(competitive, uncompetitive)


class TestAModelComparedWithItself:
    """The degenerate case, which has to come out exactly right.

    Not a formality: it is the case every other answer is measured against,
    and a module that reported a 1e-16 difference here would report one
    everywhere.
    """

    def test_it_is_structurally_identical(self, competitive) -> None:
        report = structurally_identical(competitive, competitive)
        assert report.identical
        assert report.same_wiring
        assert report.values_match

    def test_the_renaming_it_finds_is_the_identity(self, competitive) -> None:
        # Every species, parameter and reaction maps to itself. A renaming
        # that permuted two interchangeable species would also be correct,
        # and this asserts the module does not go looking for one when the
        # obvious answer is right in front of it.
        report = structurally_identical(competitive, competitive)
        assert all(key == value for key, value in report.renaming.items())
        assert len(report.renaming) == (
            len(competitive.species) + len(competitive.parameters)
            + len(competitive.reactions)
        )

    def test_the_behavioural_difference_is_exactly_zero(self, competitive) -> None:
        report = behavioural_difference(
            competitive, competitive, initial_rate_of("reaction_P"),
            Dose("reaction_S", (0.01, 1.0, 100.0), basis="a stated range"),
        )
        assert report.identical
        assert [o.difference for o in report.observations] == [0.0, 0.0, 0.0]
        assert report.widest.separation == 0.0

    def test_no_experiment_is_offered_and_the_refusal_says_why(
        self, competitive,
    ) -> None:
        with pytest.raises(ModelsIndistinguishable) as caught:
            discriminating_experiment(competitive, competitive)
        message = str(caught.value)
        assert "Every difference was exactly zero" in message
        assert "No instrument, at any precision, separates them" in message
        # And it does not dress the finding up as a failure to search.
        assert "one prediction written twice" in message

    def test_the_structural_summary_says_there_is_nothing_to_decide(
        self, competitive,
    ) -> None:
        summary = structurally_identical(competitive, competitive).summary()
        assert "one model written twice" in summary
        assert "two identical mechanisms are not two hypotheses" in summary


class TestTheSameMotifUnderTwoPrefixes:
    """Identity up to renaming, which is the only kind of identity there is.

    A composed model's names are `<prefix>_<port>`, so two instances of one
    motif are the same mechanism with every symbol different. A comparison
    that worked by name would call them two models, which would make the
    whole module useless for its actual job -- comparing a hypothesis
    somebody composed against one somebody else composed.
    """

    def _placed(self, prefix: str, name: str):
        composition = Composition(name)
        composition.add(CATALYTIC_STEP, prefix)
        return composition.to_network()

    def test_two_prefixes_are_identical_up_to_renaming(self) -> None:
        report = structurally_identical(
            self._placed("aaa", "one"), self._placed("zzz", "two")
        )
        assert report.identical
        assert report.values_match

    def test_the_renaming_is_the_prefix_swap_and_nothing_else(self) -> None:
        report = structurally_identical(
            self._placed("aaa", "one"), self._placed("zzz", "two")
        )
        assert dict(report.renaming) == {
            "aaa_S": "zzz_S", "aaa_P": "zzz_P", "aaa_E": "zzz_E",
            "aaa_kcat": "zzz_kcat", "aaa_Km": "zzz_Km",
            "aaa_catalysis": "zzz_catalysis",
        }

    def test_the_renaming_is_what_makes_the_pair_comparable(self) -> None:
        # The point of returning it. Two models whose names differ cannot be
        # compared by name, and this is the map that fixes that.
        left, right = self._placed("aaa", "one"), self._placed("zzz", "two")
        renaming = structurally_identical(left, right).renaming
        report = behavioural_difference(
            left, right, initial_rate_of("aaa_P"), None,
            correspondence=renaming,
        )
        assert report.identical

    def test_without_the_renaming_it_refuses_rather_than_finding_no_difference(
        self,
    ) -> None:
        """The failure mode this refusal exists to stop.

        Comparing `aaa_P` against a model that has no such species could
        return "no difference found", which reads as evidence and is the
        opposite of what happened -- nothing was compared at all.
        """
        left, right = self._placed("aaa", "one"), self._placed("zzz", "two")
        with pytest.raises(ComparisonRefused) as caught:
            behavioural_difference(left, right, initial_rate_of("aaa_P"))
        message = str(caught.value)
        assert "not a species of" in message
        assert "correspondence" in message

    def test_a_species_that_exists_in_neither_is_still_refused(self) -> None:
        left, right = self._placed("aaa", "one"), self._placed("aaa", "two")
        with pytest.raises(ComparisonRefused, match="not a species of"):
            behavioural_difference(left, right, initial_rate_of("nope"))


class TestCompetitiveAgainstUncompetitive:
    """The textbook case, and the one that proves the module found the real
    answer rather than an argmax that happened to land somewhere."""

    def test_they_have_the_same_wiring_and_a_different_law(
        self, competitive, uncompetitive,
    ) -> None:
        report = structurally_identical(competitive, uncompetitive)
        assert not report.identical
        assert report.same_wiring
        assert any("rate law" in d for d in report.differences)

    def test_the_summary_names_that_as_the_shape_of_a_mechanism_question(
        self, competitive, uncompetitive,
    ) -> None:
        summary = structurally_identical(competitive, uncompetitive).summary()
        assert "same species and the same reactions" in summary
        assert "the argument is about the rate law" in summary

    def test_the_predicted_rates_are_the_closed_form_ones(
        self, competitive, uncompetitive,
    ) -> None:
        """Against algebra, not against a previous run.

        The readout is the rate of product appearance, which for a
        single-reaction model is exactly v. If these do not match the
        Michaelis-Menten expressions the rest of the file is measuring
        something else.
        """
        doses = Dose("reaction_S", (0.01, 1.0, 100.0), basis="a stated range")
        report = behavioural_difference(
            competitive, uncompetitive, initial_rate_of("reaction_P"), doses,
        )
        for observation in report.observations:
            assert observation.left == pytest.approx(
                competitive_rate(observation.level, competitive), rel=1e-12
            )
            assert observation.right == pytest.approx(
                uncompetitive_rate(observation.level, uncompetitive), rel=1e-12
            )

    def test_competitive_is_surmountable_and_uncompetitive_is_not(
        self, competitive, uncompetitive,
    ) -> None:
        """The mechanism, stated as the limit it is.

        Saturate the substrate and a competitive inhibitor is outcompeted:
        the rate goes to kcat*E as though no inhibitor were there. An
        uncompetitive inhibitor binds the ES complex, so more substrate makes
        MORE of what it binds, and the rate settles at kcat*E/(1 + I/Ki).
        That gap is the discrimination, and it is why the experiment belongs
        at high substrate.
        """
        kcat, km, _, enzyme, _ = _constants(competitive)
        saturating = 1000.0 * km

        assert competitive_rate(saturating, competitive) == pytest.approx(
            kcat * enzyme, rel=0.01
        )
        assert uncompetitive_rate(saturating, uncompetitive) == pytest.approx(
            kcat * enzyme / ALPHA, rel=0.01
        )

    def test_the_discriminating_experiment_is_at_saturating_substrate(
        self, competitive, uncompetitive, experiment,
    ) -> None:
        """The headline.

        Nothing tells the module about Lineweaver-Burk plots. It evaluates
        both models over a stated dose range and reports where the gap is
        widest relative to what can be measured -- and that comes out at the
        top of the substrate series, which is where the textbook puts it.
        """
        _, km, _, _, _ = _constants(competitive)
        series = default_doses(competitive, uncompetitive)
        assert [d.species for d in series] == ["reaction_S"], "the premise"

        chosen = experiment.observation
        assert chosen.varied == "reaction_S"
        assert chosen.level == max(series[0].levels)
        # Saturating, and not merely the largest number in the list: the
        # substrate is three orders of magnitude above the Km, which is where
        # "surmountable" and "not surmountable" have separated.
        assert chosen.level > 100 * km
        assert chosen.decisive

    def test_the_chosen_observation_carries_the_two_limiting_rates(
        self, competitive, uncompetitive, experiment,
    ) -> None:
        # The readout can be read as substrate depletion or product
        # appearance -- the same experiment, opposite signs -- so the check
        # is on the magnitudes.
        kcat, _, _, enzyme, _ = _constants(competitive)
        chosen = experiment.observation
        assert abs(chosen.left) == pytest.approx(kcat * enzyme, rel=0.01)
        assert abs(chosen.right) == pytest.approx(
            kcat * enzyme / ALPHA, rel=0.01
        )

    def test_substrate_depletion_and_product_appearance_tie(
        self, experiment,
    ) -> None:
        """A tie reported rather than broken silently.

        d[S]/dt and d[P]/dt are the same measurement read two ways and they
        separate the models identically. Naming one of them as THE experiment
        would present the declaration order of the species list as a finding.
        """
        chosen = experiment.observation
        assert chosen.target in {"reaction_S", "reaction_P"}
        partners = {o.target for o in experiment.ties if o.level == chosen.level}
        assert partners == {"reaction_S", "reaction_P"} - {chosen.target}

    def test_the_two_mechanisms_cross_at_exactly_the_michaelis_constant(
        self, competitive, uncompetitive,
    ) -> None:
        """An analytic zero, not a small number.

        Setting the two rate laws equal gives Km*alpha + S = Km + S*alpha,
        so (S - Km)*(1 - alpha) = 0 and the curves meet at S = Km for every
        kcat, E, I and Ki. Below it the uncompetitive rate is higher, above
        it the competitive one is, and at it they are the same number.
        """
        _, km, _, _, _ = _constants(competitive)
        assert competitive_rate(km, competitive) == uncompetitive_rate(
            km, uncompetitive
        ), "the algebra"

        report = behavioural_difference(
            competitive, uncompetitive, initial_rate_of("reaction_P"),
            Dose("reaction_S", (km / 10, km, km * 10), basis="around the Km"),
        )
        below, crossing, above = report.observations
        assert crossing.difference == 0.0
        assert crossing.agree
        # And the sign flips across it, which is what a crossing means.
        assert below.difference > 0 > above.difference

    def test_the_crossing_is_reported_as_separating_nothing(
        self, competitive, uncompetitive,
    ) -> None:
        _, km, _, _, _ = _constants(competitive)
        report = behavioural_difference(
            competitive, uncompetitive, initial_rate_of("reaction_P"),
            Dose("reaction_S", (km, km * 1000), basis="the crossing and above"),
        )
        assert [o.agree for o in report.observations] == [True, False]
        summary = report.summary()
        assert "IDENTICAL predictions" in summary
        assert "the curves cross" in summary

    def test_the_experiment_is_not_placed_at_the_crossing(
        self, competitive, uncompetitive, experiment,
    ) -> None:
        # The default dose series contains the Km exactly, so the argmax had
        # the chance to land on the one condition that separates nothing, and
        # did not.
        _, km, _, _, _ = _constants(competitive)
        levels = default_doses(competitive, uncompetitive)[0].levels
        assert km in levels, "the premise: the crossing is inside the search"
        assert experiment.observation.level != km

    def test_with_no_inhibitor_they_are_the_same_model(self) -> None:
        """The case the refusal exists for.

        Set I = 0 and both rate laws become kcat*E*S/(Km + S). They are still
        two different mechanisms on paper and they make identical predictions
        at every substrate concentration, so there is no experiment -- and
        the module must say that rather than returning the largest of
        thirty-six zeros.
        """
        left = _inhibited(COMPETITIVE_INHIBITION, "competitive", inhibitor=0.0)
        right = _inhibited(UNCOMPETITIVE_INHIBITION, "uncompetitive", inhibitor=0.0)

        with pytest.raises(ModelsIndistinguishable) as caught:
            discriminating_experiment(left, right)
        message = str(caught.value)
        assert "Every difference was exactly zero" in message
        assert "the failure is in the question rather than in the assay" in message

    def test_the_structure_still_differs_when_the_predictions_do_not(
        self,
    ) -> None:
        # The other half of the same finding: identical predictions do not
        # make the two mechanisms one mechanism, and the refusal points at
        # the function that says so.
        left = _inhibited(COMPETITIVE_INHIBITION, "competitive", inhibitor=0.0)
        right = _inhibited(UNCOMPETITIVE_INHIBITION, "uncompetitive", inhibitor=0.0)
        assert not structurally_identical(left, right).identical

    def test_the_steady_state_cannot_tell_them_apart_at_all(
        self, competitive, uncompetitive,
    ) -> None:
        """Why the default readout is the initial rate and not the endpoint.

        Both models conserve S + P, so started at S = 1 and P = 0 both end
        with P = 1 whatever the inhibitor does. The steady state is the one
        observation on which every mechanism conserving the same moiety is
        guaranteed to agree, and an experiment designed against it would be
        designed against the place two mechanisms cannot differ.
        """
        readout = steady_state_of("reaction_P")
        assert readout.measure(competitive, "reaction_P") == pytest.approx(
            1.0, abs=1e-9
        )
        assert readout.measure(uncompetitive, "reaction_P") == pytest.approx(
            1.0, abs=1e-9
        )

        with pytest.raises(ModelsIndistinguishable) as caught:
            discriminating_experiment(
                competitive, uncompetitive, readouts=[readout], doses=[],
            )
        assert "below that readout's own arithmetic floor" in str(caught.value)


class TestThePrecisionDecidesWhetherThereIsAnExperiment:
    """The argument the module is built around.

    An argmax over predicted differences always returns something. Whether
    what it returns is an experiment depends on a number that has nothing to
    do with the models -- how well the thing can be measured -- and the
    module refuses rather than handing back the widest of a set of
    differences nobody could see.
    """

    def _slightly_faster(self, network, fraction: float):
        """The same model with kcat raised by a stated fraction.

        A pure scaling of the whole rate curve, so the two models differ by
        exactly that fraction at every substrate concentration. The cleanest
        possible "small difference": nothing about the shape changes, only
        the size.
        """
        return replace(network, name=f"{network.name}_faster", parameters=tuple(
            replace(p, value=p.value * (1.0 + fraction))
            if p.id == "reaction_kcat" else p
            for p in network.parameters
        ))

    def test_a_difference_below_the_stated_precision_is_indistinguishable(
        self, competitive,
    ) -> None:
        faster = self._slightly_faster(competitive, 0.005)
        assert DEFAULT_PRECISION.relative == 0.1, "the premise: a 10% assay"

        with pytest.raises(ModelsIndistinguishable) as caught:
            discriminating_experiment(competitive, faster)
        message = str(caught.value)
        assert "The difference is REAL and it is inside your error bar" in message

    def test_the_refusal_says_what_precision_would_be_needed(
        self, competitive,
    ) -> None:
        """A refusal that names the next step.

        The two models differ by half a percent everywhere, so the number the
        assay has to beat is computable and specific -- and it is the
        difference between "this cannot be done" and "this needs a better
        instrument, and here is how much better".
        """
        faster = self._slightly_faster(competitive, 0.005)
        with pytest.raises(ModelsIndistinguishable) as caught:
            discriminating_experiment(competitive, faster)
        assert "you would need a measurement error below" in str(caught.value)
        assert "0.50% of the value" in str(caught.value)

    def test_the_same_pair_separates_once_the_instrument_is_good_enough(
        self, competitive,
    ) -> None:
        """The other side, and what makes the test above mean something.

        Nothing about the models changed. Only the stated precision did, and
        the same pair goes from "no experiment exists" to "decisive at every
        condition" -- which is the module's whole claim about where the
        answer comes from.
        """
        faster = self._slightly_faster(competitive, 0.005)
        fine = Precision(
            relative=0.001, basis="a stated 0.1% assay, for this test"
        )
        found = discriminating_experiment(competitive, faster, precision=fine)
        assert found.observation.decisive
        assert found.observation.separation > DECISIVE

    def test_a_pure_scaling_separates_equally_well_everywhere(
        self, competitive,
    ) -> None:
        """A finding, not a defect in the search.

        kcat multiplies the whole rate curve, so the two models differ by the
        same FRACTION at every substrate concentration. With a relative
        precision there is no best condition to run -- every one is as good
        as every other -- and the honest answer is that the experiment needs
        a better instrument rather than a better choice of dose.
        """
        faster = self._slightly_faster(competitive, 0.005)
        fine = Precision(
            relative=0.001, basis="a stated 0.1% assay, for this test"
        )
        report = behavioural_difference(
            competitive, faster, initial_rate_of("reaction_P"),
            Dose("reaction_S", (0.01, 1.0, 100.0), basis="a stated range"),
            precision=fine,
        )
        separations = [o.separation for o in report.observations]
        assert all(s == pytest.approx(separations[0], rel=1e-6) for s in separations)
        assert all(o.measurable for o in report.observations)

    def test_the_two_thresholds_are_different_claims(self) -> None:
        """`MEASURABLE` is the floor of meaning; `DECISIVE` is a judgement.

        Stated on constructed observations rather than computed ones, on
        purpose: the point is the definition, and a test that depended on
        where a particular model happened to land would break every time the
        library's illustrative values moved.
        """
        def at(separation: float) -> Observation:
            return Observation(
                readout="a readout", target="X", varied=None, level=None,
                unit="", left=1.0, right=1.0 + separation * 0.1,
                error=0.1, numerical_floor=1e-15,
            )

        assert not at(0.5).measurable
        assert at(1.5).measurable and not at(1.5).decisive
        assert at(4.0).decisive
        assert MEASURABLE < DECISIVE

    def test_a_precision_of_zero_is_refused(self) -> None:
        # A perfect instrument makes every difference measurable, including
        # the arithmetic's own rounding, and every pair of models would come
        # back distinguishable.
        with pytest.raises(ComparisonRefused, match="perfect instrument"):
            Precision(relative=0.0, absolute=0.0, basis="nothing")

    def test_a_precision_with_no_stated_basis_is_refused(self) -> None:
        # Every verdict the module reaches rests on this number, so it may
        # not arrive anonymously.
        with pytest.raises(ComparisonRefused, match="no stated basis"):
            Precision(relative=0.1, basis="   ")

    def test_the_default_precision_says_it_is_a_placeholder(self) -> None:
        # It is not a measurement of anybody's assay and must not read as
        # one, and nothing cites a paper for it.
        assert "illustrative placeholder" in DEFAULT_PRECISION.basis
        assert "Not a measurement of your assay" in DEFAULT_PRECISION.basis

    def test_an_absolute_floor_takes_over_when_the_signal_is_small(self) -> None:
        # The term that decides where a dose-response should be run: a
        # relative error shrinks with the signal and an absolute one does
        # not, so at a low dose the absolute one is what you are fighting.
        precision = Precision(
            relative=0.1, absolute=0.5, basis="a stated detector floor",
        )
        assert precision.error_in(0.1, 0.2) == 0.5
        assert precision.error_in(100.0, 90.0) == pytest.approx(10.0)


class TestTheTwoFloors:
    """A difference has to clear the arithmetic before it clears the assay.

    The distinction `sensitivity.py` had to learn between its own noise floor
    and its judgement about biochemistry, in the form it takes here.
    """

    def test_a_difference_below_the_arithmetic_floor_is_not_measurable(
        self,
    ) -> None:
        # Even with an instrument stated to be a thousand times better than
        # the gap. The gap is not small; it is not there. One float apart is
        # the smallest difference that exists at all -- 1.0 + 1e-16 IS 1.0,
        # so `nextafter` is the only honest way to write "barely different".
        observation = Observation(
            readout="a readout", target="X", varied=None, level=None, unit="",
            left=1.0, right=math.nextafter(1.0, 2.0),
            error=1e-19, numerical_floor=1e-15,
        )
        assert observation.separation > DECISIVE
        assert not observation.resolvable
        assert not observation.measurable
        assert not observation.decisive

    def test_the_steady_state_declares_a_coarser_floor_than_machine_precision(
        self,
    ) -> None:
        """The measurement behind `STEADY_STATE_PRECISION`.

        Competitive inhibition conserves S + P, so from S = 1 and P = 0 the
        steady state of P is exactly 1 -- an answer known in closed form,
        whatever the kinetics are. The solver returns it to about 1.8e-14,
        which is a hundred times worse than the 1.8e-16 `sensitivity.py`
        measured on a first-order model. At machine precision that gap would
        clear the arithmetic floor and be reported as a real difference
        between two mechanisms that provably agree there.
        """
        network = _inhibited(COMPETITIVE_INHIBITION, "competitive")
        value = steady_state_of("reaction_P").measure(network, "reaction_P")

        error = abs(value - 1.0)
        assert error > compare.MACHINE_PRECISION * 10, (
            "the solver became exact on this model; if so, "
            "STEADY_STATE_PRECISION is now a pessimistic claim and should be "
            "re-measured rather than left standing"
        )
        assert error < STEADY_STATE_PRECISION
        assert steady_state_of("reaction_P").numerical_precision == (
            STEADY_STATE_PRECISION
        )
        assert initial_rate_of("reaction_P").numerical_precision == (
            compare.MACHINE_PRECISION
        )

    def test_an_exact_agreement_is_reported_as_stronger_than_a_small_one(
        self,
    ) -> None:
        # `agree` and `not resolvable` are different findings: one says no
        # instrument helps, the other says this solver cannot tell.
        agreeing = Observation(
            readout="r", target="X", varied=None, level=None, unit="",
            left=2.0, right=2.0, error=0.1, numerical_floor=1e-15,
        )
        rounding = Observation(
            readout="r", target="X", varied=None, level=None, unit="",
            left=2.0, right=math.nextafter(2.0, 3.0),
            error=0.1, numerical_floor=1e-15,
        )
        assert agreeing.agree and not rounding.agree
        assert not agreeing.resolvable and not rounding.resolvable
        assert "however well it is measured" in agreeing.describe()
        assert "not the same as there being none" in rounding.describe()


class TestTheSearchRefusesRatherThanHanging:
    """A search that never returns reads, to a user, like a model that
    differs. That is the worst way to be wrong here, so both guards raise."""

    def _parallel(self, branches: int, modified=None, name="net"):
        """N independent reactions A_i -> B_i, optionally with one law changed.

        The worst case this search has. Every A is interchangeable with every
        other by its degree signature, so each has N candidates, and when one
        branch's rate law differs the answer is no only after the assignments
        have been tried.
        """
        species, parameters, reactions = [], [], []
        for index in range(branches):
            species += [Species(f"A{index}", 1.0), Species(f"B{index}", 0.0)]
            parameters.append(Parameter(f"k{index}", 1.0))
            law = (
                f"k{index} * A{index} * A{index}" if index == modified
                else f"k{index} * A{index}"
            )
            reactions.append(
                Reaction(f"r{index}", {f"A{index}": 1}, {f"B{index}": 1}, law)
            )
        return ReactionNetwork(
            name=name, species=tuple(species),
            parameters=tuple(parameters), reactions=tuple(reactions),
        )

    def test_a_network_above_the_size_limit_is_refused_with_its_size(
        self,
    ) -> None:
        big = self._parallel(MAX_SPECIES_FOR_ISOMORPHISM, name="big")
        assert len(big.species) > MAX_SPECIES_FOR_ISOMORPHISM, "the premise"

        with pytest.raises(ComparisonTooLarge) as caught:
            structurally_identical(big, big)
        message = str(caught.value)
        assert f"{len(big.species)} species" in message
        assert str(MAX_SPECIES_FOR_ISOMORPHISM) in message

    def test_the_worst_case_at_sixteen_species_still_answers(self) -> None:
        """The measurement `MAX_PARTIAL_ASSIGNMENTS` is set from.

        Eight interchangeable branches, one of which differs. The bound is
        deliberately loose -- this is a guard against an exponential
        regression, not a benchmark, and a tight bound would fail on a busy
        machine for no reason.
        """
        left = self._parallel(8, None, "left")
        right = self._parallel(8, 7, "right")

        started = time.perf_counter()
        report = structurally_identical(left, right)
        elapsed = time.perf_counter() - started

        assert report.same_wiring
        assert not report.identical
        assert elapsed < 60.0

    def test_the_worst_case_at_eighteen_species_refuses_with_its_budget(
        self,
    ) -> None:
        left = self._parallel(9, None, "left")
        right = self._parallel(9, 8, "right")

        with pytest.raises(ComparisonTooLarge) as caught:
            structurally_identical(left, right)
        message = str(caught.value)
        assert str(MAX_PARTIAL_ASSIGNMENTS) in message
        assert "18 and 18 species" in message

    def test_a_refusal_is_not_a_verdict_that_the_models_differ(self) -> None:
        """The sentence that stops the refusal being read as an answer.

        A caller who catches this and carries on as though the models were
        found to differ would be acting on a search that was abandoned.
        """
        left = self._parallel(9, None, "left")
        right = self._parallel(9, 8, "right")
        with pytest.raises(ComparisonTooLarge) as caught:
            structurally_identical(left, right)
        assert "NOTHING HERE SAYS THE MODELS DIFFER" in str(caught.value)

    def test_the_realistic_worst_case_is_nowhere_near_the_limit(self) -> None:
        # The largest model the motif library composes is a three-tier
        # cascade. The limits exist for hand-built networks, not for anything
        # the composer produces.
        from caterva.compose.pipeline import compose

        cascade = compose("three step phosphorylation cascade").network
        assert len(cascade.species) < MAX_SPECIES_FOR_ISOMORPHISM
        report = structurally_identical(cascade, cascade)
        assert report.identical


class TestWhatIsNotClaimed:
    def test_no_information_criterion_is_computed(self) -> None:
        """Deliberately absent, and the module says what one would assume.

        An AIC needs data this module runs before, and it compares the models
        it was handed rather than saying whether either is right. The
        docstring carries the assumptions so that adding one later cannot be
        done quietly.
        """
        assert not [name for name in dir(compare)
                    if name.lower() in {"aic", "bic", "aicc", "model_selection"}]

        prose = " ".join(compare.__doc__.split())
        assert "It needs data." in prose
        assert (
            "the best of two wrong models is still wrong" in prose
        )
        assert "the models were fitted to the SAME data" in prose

    def test_algebraic_equality_is_not_claimed(self) -> None:
        """Two laws that are the same function, written differently.

        `k * A` and `A * k` are equal and this module reports them as
        different, because deciding that is computer algebra. The error is
        always in the safe direction -- a false "different", never a false
        "identical" -- and the behavioural half catches it immediately.
        """
        def one(law: str, name: str):
            return ReactionNetwork(
                name=name,
                species=(Species("A", 1.0), Species("B", 0.0)),
                parameters=(Parameter("k", 2.0),),
                reactions=(Reaction("r", {"A": 1}, {"B": 1}, law),),
            )

        report = structurally_identical(one("k * A", "left"), one("A * k", "right"))
        assert report.same_wiring
        assert not report.identical

        with pytest.raises(ModelsIndistinguishable) as caught:
            discriminating_experiment(one("k * A", "left"), one("A * k", "right"))
        assert "Every difference was exactly zero" in str(caught.value)

    def test_rate_rules_are_refused_rather_than_quietly_ignored(self) -> None:
        """Comparing the half that is reactions would invent an identity.

        A model whose dynamics live partly in rate rules would be reported
        identical to another on the strength of the part that was looked at,
        which is the one answer that ends the inquiry.
        """
        from caterva.core.network import RateRule

        with_rule = ReactionNetwork(
            name="driven",
            species=(Species("A", 1.0), Species("B", 0.0)),
            parameters=(Parameter("k", 1.0),),
            reactions=(),
            rate_rules=(RateRule("A", "-k * A"), RateRule("B", "k * A")),
        )
        with pytest.raises(ComparisonRefused) as caught:
            structurally_identical(with_rule, with_rule)
        message = str(caught.value)
        assert "rate rule" in message
        assert "the half that was looked at" in message

    def test_same_structure_and_different_numbers_is_one_mechanism(
        self, competitive,
    ) -> None:
        """The third finding, kept apart from the other two.

        A parameter change is not a mechanism change, and calling it one is
        how a model comparison ends up answering a question about operating
        points with a sentence about mechanisms.
        """
        faster = replace(competitive, parameters=tuple(
            replace(p, value=p.value * 2) if p.id == "reaction_kcat" else p
            for p in competitive.parameters
        ))
        report = structurally_identical(competitive, faster)
        assert report.identical
        assert report.values_match is False
        summary = report.summary()
        assert "ONE mechanism at two operating points" in summary
        assert "will not answer a question about mechanism" in summary

    def test_every_summary_says_the_constants_may_be_placeholders(
        self, competitive, uncompetitive, experiment,
    ) -> None:
        # "Measure the rate at saturating substrate" reads like advice about
        # biochemistry, and until the constants are grounded it is advice
        # about two particular sets of placeholder numbers.
        report = behavioural_difference(
            competitive, uncompetitive, initial_rate_of("reaction_P"),
            Dose("reaction_S", (1.0,), basis="a stated range"),
        )
        assert "illustrative placeholders" in report.summary()
        assert "rather than two mechanisms" in experiment.summary()

    def test_the_search_says_what_it_did_not_vary(self, experiment) -> None:
        # The inhibitor is a modifier, not a reactant, so the default never
        # doses it -- and an inhibitor dose-response is a real and sometimes
        # better discrimination.
        assert experiment.varied == ("reaction_S",)
        summary = experiment.summary()
        assert "one input was varied at a time" in summary
        assert "would not have been found here" in summary

    def test_the_separation_is_not_called_a_p_value(self, experiment) -> None:
        assert "not a p-value" in experiment.summary()


class TestDosesAndDefaults:
    def test_a_bare_list_of_numbers_is_not_a_dose_series(
        self, competitive, uncompetitive,
    ) -> None:
        # The same three numbers mean different experiments for a substrate
        # and for an inhibitor, so a sequence with no subject is refused.
        with pytest.raises(ComparisonRefused, match="what it is a dose OF"):
            behavioural_difference(
                competitive, uncompetitive, initial_rate_of("reaction_P"),
                [0.1, 1.0, 10.0],
            )

    def test_a_negative_dose_is_refused(self) -> None:
        with pytest.raises(ComparisonRefused, match="add to a tube"):
            Dose("S", (-1.0,), basis="a stated range")

    def test_an_empty_dose_series_is_refused(self) -> None:
        with pytest.raises(ComparisonRefused, match="not an input range"):
            Dose("S", (), basis="a stated range")

    def test_the_default_series_contains_the_amount_the_model_holds(
        self, competitive, uncompetitive,
    ) -> None:
        # An odd number of points around the current amount, so the
        # conditions include the one the model already describes.
        series = default_doses(competitive, uncompetitive)
        held = {s.id: s.initial for s in competitive.species}["reaction_S"]
        assert len(series) == 1
        assert len(series[0].levels) == DEFAULT_DOSE_POINTS
        assert held in series[0].levels
        assert max(series[0].levels) == pytest.approx(
            held * 10 ** DEFAULT_DOSE_DECADES
        )

    def test_the_default_doses_the_input_and_not_the_product_or_the_enzyme(
        self, competitive, uncompetitive,
    ) -> None:
        """A species a reaction eats and nothing makes is what you put in.

        The product is an output, and the enzyme and the inhibitor are
        modifiers -- none of them is the axis a mechanism discrimination is
        drawn against, and dosing them describes different experiments that
        the caller can ask for by name.
        """
        assert [d.species for d in default_doses(competitive, uncompetitive)] == [
            "reaction_S"
        ]

    def test_the_default_readouts_are_the_shared_species(
        self, competitive, uncompetitive,
    ) -> None:
        readouts = default_readouts(competitive, uncompetitive)
        assert [r.target for r in readouts] == list(
            s.id for s in competitive.species
        )
        assert all(r.kind == compare.KIND_INITIAL_RATE for r in readouts)

    def test_models_sharing_no_species_are_refused_not_compared(self) -> None:
        left = _inhibited(COMPETITIVE_INHIBITION, "competitive")
        composition = Composition("elsewhere")
        composition.add(CATALYTIC_STEP, "other")
        with pytest.raises(ComparisonRefused, match="share no species"):
            discriminating_experiment(left, composition.to_network())

    def test_a_dose_series_around_zero_is_refused_rather_than_invented(
        self,
    ) -> None:
        # There is no geometric range around zero, and inventing one would be
        # this module making up a number.
        with pytest.raises(ComparisonRefused, match="no amount to scale"):
            compare.dose_series("S", 0.0)

    def test_the_composed_model_supplies_the_unit_the_network_lost(self) -> None:
        """`core.network.Species` carries an amount and no unit.

        The composition knows, so a dose built from a composed model prints
        its concentrations in mM and one built from a bare network prints
        them bare -- visibly missing rather than silently assumed.
        """
        from caterva.compose.pipeline import compose

        model = compose("enzyme kinetics with a competitive inhibitor")
        series = default_doses(model, model)
        assert series, "the premise: this model has a pure input"
        assert series[0].unit == "mM"
        assert default_doses(model.network, model.network)[0].unit == ""


class TestNoncompetitiveIsADifferentMechanismAgain:
    """A third hypothesis, to show the pair above was not a special case."""

    def test_it_shares_the_wiring_and_differs_in_the_law(self) -> None:
        left = _inhibited(COMPETITIVE_INHIBITION, "competitive")
        right = _inhibited(NONCOMPETITIVE_INHIBITION, "noncompetitive")
        report = structurally_identical(left, right)
        assert report.same_wiring
        assert not report.identical

    def test_saturating_substrate_does_not_rescue_a_noncompetitive_inhibitor(
        self,
    ) -> None:
        """Which is why the discrimination is where it is.

        A non-competitive inhibitor binds free enzyme and the complex alike,
        so it divides the whole curve and no amount of substrate outruns it.
        Against competitive inhibition -- which saturating substrate does
        outrun -- the gap is again widest at the top of the range.
        """
        left = _inhibited(COMPETITIVE_INHIBITION, "competitive")
        right = _inhibited(NONCOMPETITIVE_INHIBITION, "noncompetitive")
        found = discriminating_experiment(left, right)
        series = default_doses(left, right)
        assert found.observation.level == max(series[0].levels)
        assert found.observation.decisive


class TestTheRankingIsBySeparationAndNotBySize:
    """The distinction the module exists for, on a case that tells them apart.

    A big difference on big numbers can be entirely invisible while a small
    difference on small ones is decisive. Ranking by the size of the gap --
    the obvious implementation, and the one an argmax reaches for -- picks
    the first and then reports that no experiment exists, because the gap it
    chose is inside the error bar. Ranking by the gap in units of the error
    picks the second and hands back a real experiment.
    """

    def _two_reactions(self, name: str, fast: float, slow: float):
        """A model with a large, nearly identical flux and a small, very
        different one. Independent reactions, so each readout is one flux."""
        return ReactionNetwork(
            name=name,
            species=(
                Species("A", 1000.0), Species("B", 0.0),
                Species("C", 1.0), Species("D", 0.0),
            ),
            parameters=(Parameter("k1", fast), Parameter("k2", slow)),
            reactions=(
                Reaction("r1", {"A": 1}, {"B": 1}, "k1 * A"),
                Reaction("r2", {"C": 1}, {"D": 1}, "k2 * C"),
            ),
        )

    def test_the_larger_gap_is_the_one_that_cannot_be_measured(self) -> None:
        # The premise, stated in numbers: 10 against 1000 is 1%, and 0.5
        # against 1.5 is a third. With a 10% assay only the second is visible.
        left = self._two_reactions("left", 1.0, 1.0)
        right = self._two_reactions("right", 1.01, 1.5)
        readings = {
            report.observations[0].target: report.observations[0]
            for report in discriminating_experiment(
                left, right, doses=[]
            ).reports
        }
        assert abs(readings["A"].difference) == pytest.approx(10.0)
        assert abs(readings["C"].difference) == pytest.approx(0.5)
        assert not readings["A"].measurable
        assert readings["C"].decisive

    def test_the_experiment_chosen_is_the_measurable_one(self) -> None:
        """And ranking by size would have refused outright.

        The gap of 10 is twenty times the gap of 0.5 and sits at a tenth of
        one measurement error. An argmax over raw differences returns it, the
        precision check then finds it unmeasurable, and a pair of models with
        a perfectly good experiment between them comes back as
        indistinguishable.
        """
        left = self._two_reactions("left", 1.0, 1.0)
        right = self._two_reactions("right", 1.01, 1.5)
        found = discriminating_experiment(left, right, doses=[])

        assert found.observation.target in {"C", "D"}
        assert found.observation.decisive
        assert abs(found.observation.difference) == pytest.approx(0.5)


class TestAnAbsoluteDetectorFloorChangesTheAnswer:
    """The term `DEFAULT_PRECISION` leaves at zero, doing its work.

    A relative-only precision shrinks with the signal, so a measurement of a
    tiny rate at a low dose looks exactly as good as a measurement of a large
    rate at a high one. Real detectors do not do that, and it is the absolute
    floor that ruins the low-dose end of a dose-response -- which is the
    other half of why the classical discriminations are run at saturation.
    """

    def test_the_lowest_dose_survives_a_relative_only_precision(
        self, competitive, uncompetitive,
    ) -> None:
        report = behavioural_difference(
            competitive, uncompetitive, initial_rate_of("reaction_P"),
            default_doses(competitive, uncompetitive)[0],
        )
        lowest = min(report.observations, key=lambda o: o.level)
        assert lowest.decisive, "the premise: with no detector floor it passes"

    def test_a_stated_detector_floor_removes_it(
        self, competitive, uncompetitive,
    ) -> None:
        # Nothing about the models changed; the instrument did.
        floor = Precision(
            relative=0.1, absolute=0.005,
            basis="a stated detector floor, for this test",
        )
        report = behavioural_difference(
            competitive, uncompetitive, initial_rate_of("reaction_P"),
            default_doses(competitive, uncompetitive)[0], precision=floor,
        )
        lowest = min(report.observations, key=lambda o: o.level)
        highest = max(report.observations, key=lambda o: o.level)
        assert not lowest.measurable
        assert highest.decisive

    def test_the_report_orders_its_own_conditions_the_same_way(self) -> None:
        """`DifferenceReport.widest` means widest RELATIVE TO THE ERROR.

        Stated on constructed observations rather than computed ones, for
        the reason the class above gives: the point is the ordering rule, and
        a test that leaned on where a particular model happened to land would
        break whenever the library's illustrative values moved.
        """
        def observed(level: float, gap: float, error: float) -> Observation:
            return Observation(
                readout="a readout", target="X", varied="S", level=level,
                unit="mM", left=100.0, right=100.0 + gap, error=error,
                numerical_floor=1e-12,
            )

        huge_gap_huge_error = observed(1.0, gap=10.0, error=100.0)
        small_gap_tiny_error = observed(2.0, gap=0.5, error=0.01)
        report = compare.DifferenceReport(
            left="left", right="right", readout="a readout", dose=None,
            precision=DEFAULT_PRECISION,
            observations=(huge_gap_huge_error, small_gap_tiny_error),
        )

        assert abs(huge_gap_huge_error.difference) > abs(
            small_gap_tiny_error.difference
        ), "the premise: the first gap is the bigger number"
        assert report.widest is small_gap_tiny_error
        assert report.ranked[0] is small_gap_tiny_error


class TestWhatTokenForTokenDoesAndDoesNotNormalise:
    """The rate-law comparison is textual, with two deliberate exceptions.

    Whitespace and the spelling of a number. `2 * A` and `2.0*A` are the same
    law written twice and a purely textual comparison would call them two
    mechanisms -- which would make every model that had been through a
    formatter look like a new hypothesis.
    """

    def _one(self, law: str, name: str):
        return ReactionNetwork(
            name=name,
            species=(Species("A", 1.0), Species("B", 0.0)),
            parameters=(Parameter("k", 2.0),),
            reactions=(Reaction("r", {"A": 1}, {"B": 1}, law),),
        )

    def test_the_same_constant_written_two_ways_is_the_same_law(self) -> None:
        report = structurally_identical(
            self._one("2 * k * A", "left"), self._one("2.0*k*A", "right")
        )
        assert report.identical
        assert report.values_match

    def test_a_different_constant_is_a_different_law(self) -> None:
        # The other side, without which the test above would pass on an
        # implementation that ignored numbers altogether.
        report = structurally_identical(
            self._one("2 * k * A", "left"), self._one("3 * k * A", "right")
        )
        assert not report.identical
        assert report.same_wiring

    def test_a_renaming_is_a_bijection_and_not_merely_a_substitution(
        self,
    ) -> None:
        """Two independent constants are not one constant used twice.

        `k1*A + k2*A` and `k*A + k*A` have the same shape and the same number
        of parameters, and mapping both k1 and k2 onto k would carry one law
        onto the other. It is still not a renaming: the left model has two
        constants that can move independently and the right has one, which is
        a real difference in mechanism and exactly the kind of thing a fit
        would discover the hard way.
        """
        def two_constants(law: str, names, name: str):
            return ReactionNetwork(
                name=name,
                species=(Species("A", 1.0), Species("B", 0.0)),
                parameters=tuple(Parameter(n, 1.0) for n in names),
                reactions=(Reaction("r", {"A": 1}, {"B": 1}, law),),
            )

        left = two_constants("k1 * A + k2 * A", ("k1", "k2"), "independent")
        right = two_constants("k * A + k * A", ("k", "unused"), "shared")
        report = structurally_identical(left, right)
        assert report.same_wiring
        assert not report.identical


class TestNumbersAreComparedExactly:
    """Structure and numbers are separate questions, and the second one is
    answered without a tolerance nobody argued for."""

    def test_a_different_starting_amount_is_a_different_model(
        self, competitive,
    ) -> None:
        """A species initial is a number like any other.

        Twice as much substrate is the same mechanism in a different tube,
        and `values_match` is what says so. Without this the comparison would
        report two experiments as one model.
        """
        doubled = replace(competitive, name="more substrate", species=tuple(
            replace(s, initial=s.initial * 2) if s.id == "reaction_S" else s
            for s in competitive.species
        ))
        report = structurally_identical(competitive, doubled)
        assert report.identical
        assert report.values_match is False

    def test_one_float_apart_is_not_the_same_number(self, competitive) -> None:
        # No tolerance, deliberately: a threshold here would stand between
        # "the same model" and "a different one" with nothing behind it.
        # Where the difference matters, `behavioural_difference` measures what
        # it does to the predictions, which is what a tolerance would have
        # been a proxy for.
        nudged = replace(competitive, name="nudged", parameters=tuple(
            replace(p, value=math.nextafter(p.value, math.inf))
            if p.id == "reaction_Km" else p
            for p in competitive.parameters
        ))
        report = structurally_identical(competitive, nudged)
        assert report.identical
        assert report.values_match is False
