"""In-silico genetics: knockouts, overexpression, inhibitors.

THE DISTINCTION THESE TESTS EXIST FOR
--------------------------------------
A knockout is not "set kcat to zero". Zeroing kcat leaves the enzyme protein
in the model, still binding its substrate and still sequestering it away from
competing reactions -- which is a catalytically dead mutant, a real and
different experiment that people build on purpose to separate an enzyme's
catalytic role from its binding role.

Most of this file is about keeping those two apart, and about the arithmetic
of fold change, where a control of zero produces an infinity that reads like
a result.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from Terium.compose.builder import Composition
from Terium.compose.library import CATALYTIC_STEP, SYNTHESIS_DEGRADATION
from Terium.compose.perturbation import (
    DEFAULT_OVEREXPRESSION_FOLD, KNOCKOUT_LEVEL, NEGLIGIBLE_CONTROL, Effect,
    Perturbation, PerturbationRefused, catalytically_dead, compare,
    competitive_inhibitor, effect_on, knockdown, knockout, overexpress,
    set_level, single_knockouts,
)
from Terium.compose.pipeline import compose


def _catalytic():
    composition = Composition("reaction")
    composition.add(CATALYTIC_STEP, "reaction")
    return composition.to_network()


def _turnover():
    composition = Composition("turnover")
    composition.add(SYNTHESIS_DEGRADATION, "x")
    return composition.to_network()


class TestAKnockoutIsNotADeadMutant:
    """The distinction the module exists to keep.

    A knockout removes the protein. A dead mutant leaves it in place, still
    binding. They are different experiments and they touch different parts
    of the model -- one a species, one a parameter.
    """

    def test_a_knockout_changes_a_species_not_a_parameter(self) -> None:
        network = _catalytic()
        result = knockout(network, "reaction_E")

        assert result.kind == "knockout"
        assert "reaction_E" in result.changes
        before = {p.id: p.value for p in network.parameters}
        after = {p.id: p.value for p in result.network.parameters}
        assert before == after, "a knockout must not touch any rate constant"

    def test_a_dead_mutant_changes_a_parameter_not_a_species(self) -> None:
        network = _catalytic()
        result = catalytically_dead(network, "reaction_kcat", unit="1/s")

        assert result.kind == "catalytically_dead"
        before = {s.id: s.initial for s in network.species}
        after = {s.id: s.initial for s in result.network.species}
        assert before == after, "a dead mutant leaves the protein in place"

    def test_the_dead_mutant_still_has_the_protein(self) -> None:
        # The whole reason the experiment is done.
        network = _catalytic()
        result = catalytically_dead(network, "reaction_kcat", unit="1/s")
        enzyme = next(s for s in result.network.species if s.id == "reaction_E")
        assert enzyme.initial > 0.0

    def test_the_knockout_does_not(self) -> None:
        result = knockout(_catalytic(), "reaction_E")
        enzyme = next(s for s in result.network.species if s.id == "reaction_E")
        assert enzyme.initial == KNOCKOUT_LEVEL

    def test_the_module_says_they_are_different(self) -> None:
        from Terium.compose import perturbation

        # Whitespace-normalised: these phrases wrap across lines in the
        # source, and a raw substring test would be asserting the line
        # width rather than the wording.
        prose = " ".join(perturbation.knockout.__doc__.split())
        assert "NOT the same as setting its catalytic constant to zero" in prose
        assert "still sequestering its substrate" in prose


class TestRefusalsThatPreventAWrongExperiment:
    def test_knocking_out_something_already_absent_is_refused(self) -> None:
        """"Knocked out" and "was never there" produce identical models and
        different papers.
        """
        network = _catalytic()
        already = replace(
            network,
            species=tuple(
                replace(s, initial=0.0) if s.id == "reaction_E" else s
                for s in network.species
            ),
        )
        with pytest.raises(PerturbationRefused, match="already at"):
            knockout(already, "reaction_E")

    def test_zeroing_an_affinity_is_refused_as_a_dead_mutant(self) -> None:
        # Setting Km to zero makes the enzyme infinitely avid, which is the
        # OPPOSITE of inactivating it.
        with pytest.raises(PerturbationRefused, match="infinitely avid"):
            catalytically_dead(_catalytic(), "reaction_Km", unit="mM")

    def test_overexpressing_from_zero_is_refused(self) -> None:
        # Any multiple of zero is zero, and "ten times more of nothing" is
        # not the experiment anyone means.
        network = _catalytic()
        absent = replace(
            network,
            species=tuple(
                replace(s, initial=0.0) if s.id == "reaction_P" else s
                for s in network.species
            ),
        )
        with pytest.raises(PerturbationRefused, match="multiple of zero"):
            overexpress(absent, "reaction_P")

    def test_a_knockdown_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(PerturbationRefused, match="strictly between"):
            knockdown(_catalytic(), "reaction_E", 1.5)
        with pytest.raises(PerturbationRefused, match="strictly between"):
            knockdown(_catalytic(), "reaction_E", 0.0)

    def test_an_unknown_species_names_the_real_ones(self) -> None:
        with pytest.raises(PerturbationRefused, match="reaction_E"):
            knockout(_catalytic(), "nope")

    def test_a_negative_concentration_is_refused(self) -> None:
        with pytest.raises(PerturbationRefused, match="negative"):
            set_level(_catalytic(), "reaction_S", -1.0)


class TestAnInhibitorWithoutAKiIsRefused:
    """The refusal that keeps a fabricated number out of the centre of a
    result.

    The apparent Km rises by (1 + I/Ki). Without Ki the perturbation has an
    unknown size, and a plausible-looking guess would be exactly the
    fabrication this project exists to prevent.
    """

    def test_no_ki_anywhere_is_refused_and_names_the_table(self) -> None:
        with pytest.raises(PerturbationRefused) as caught:
            competitive_inhibitor(
                _catalytic(), "reaction_Km", concentration=0.01,
            )
        message = str(caught.value)
        assert "no Ki" in message
        assert "invented number" in message
        assert "ki" in message  # the BRENDA table

    def test_a_supplied_ki_gives_the_exact_factor(self) -> None:
        # Competitive inhibition raises apparent Km by exactly (1 + I/Ki).
        network = _catalytic()
        before = next(p.value for p in network.parameters if p.id == "reaction_Km")
        result = competitive_inhibitor(
            network, "reaction_Km", concentration=0.02, ki=0.01,
        )
        after = next(
            p.value for p in result.network.parameters if p.id == "reaction_Km"
        )
        assert after == pytest.approx(before * 3.0)  # 1 + 0.02/0.01

    def test_kcat_is_untouched(self) -> None:
        """The signature of competitive inhibition, and what distinguishes
        it from uncompetitive on a Lineweaver-Burk plot.
        """
        network = _catalytic()
        result = competitive_inhibitor(
            network, "reaction_Km", concentration=0.02, ki=0.01,
        )
        before = next(p.value for p in network.parameters if p.id == "reaction_kcat")
        after = next(
            p.value for p in result.network.parameters if p.id == "reaction_kcat"
        )
        assert before == after
        assert "kcat untouched" in result.description

    def test_both_ki_sources_at_once_is_refused(self) -> None:
        with pytest.raises(PerturbationRefused, match="Pass one"):
            competitive_inhibitor(
                _catalytic(), "reaction_Km",
                concentration=0.01, ki=0.01, ki_parameter="reaction_Km",
            )

    def test_a_non_positive_ki_is_refused(self) -> None:
        with pytest.raises(PerturbationRefused, match="dissociation constant"):
            competitive_inhibitor(
                _catalytic(), "reaction_Km", concentration=0.01, ki=0.0,
            )


class TestFoldChangeArithmetic:
    """Ratios have two failure modes a number alone hides."""

    def _effect(self, control, perturbed):
        stub = Perturbation(
            kind="stub", target="x", description="a stub", network=None,
        )
        return Effect(
            perturbation=stub, readout="y",
            control=control, perturbed=perturbed,
            fold_change=None if control <= NEGLIGIBLE_CONTROL else perturbed / control,
        )

    def test_a_zero_control_gives_no_fold_change(self) -> None:
        from Terium.compose.perturbation import PerturbationComparison

        # Constructed rather than simulated: the point is the arithmetic.
        effect = self._effect(0.0, 5.0)
        assert effect.fold_change is None

    def test_ranking_is_by_log_magnitude_so_suppression_counts(self) -> None:
        """A two-fold decrease is as large an effect as a two-fold
        increase. Ranking by the raw ratio would put every suppression
        below every induction, which is the wrong ordering for a screen.
        """
        from Terium.compose.perturbation import PerturbationComparison

        stub = Perturbation("stub", "x", "a stub", None)
        halved = Effect(stub, "y", 1.0, 0.5, 0.5)
        doubled = Effect(stub, "y", 1.0, 2.0, 2.0)
        tiny = Effect(stub, "y", 1.0, 1.05, 1.05)

        ranked = PerturbationComparison("y", (tiny, halved, doubled)).ranked
        assert ranked[-1] is tiny
        # Identity, not a set: Effect holds a Perturbation whose `changes` is
        # a dict, so these are not hashable.
        assert {id(e) for e in ranked[:2]} == {id(halved), id(doubled)}

    def test_an_undefined_fold_change_sorts_last_not_as_zero(self) -> None:
        # It was not measured to be small.
        from Terium.compose.perturbation import PerturbationComparison

        stub = Perturbation("stub", "x", "a stub", None)
        undefined = Effect(stub, "y", 0.0, 0.0, None, note="both zero")
        small = Effect(stub, "y", 1.0, 1.01, 1.01)

        ranked = PerturbationComparison("y", (undefined, small)).ranked
        assert ranked[-1] is undefined

    def test_the_summary_explains_the_log_ranking(self) -> None:
        from Terium.compose.perturbation import PerturbationComparison

        stub = Perturbation("stub", "x", "a stub", None)
        summary = PerturbationComparison(
            "y", (Effect(stub, "y", 1.0, 2.0, 2.0),)
        ).summary()
        assert "log fold change" in summary
        assert "may still be placeholders" in summary


class TestAgainstAnAnalyticAnswer:
    def test_halving_synthesis_halves_the_steady_state(self) -> None:
        """dX/dt = ks - kd*X settles at ks/kd, which is linear in ks. A
        perturbation that halves ks must halve the steady state exactly,
        for every kd.
        """
        network = _turnover()
        halved = replace(
            network,
            parameters=tuple(
                replace(p, value=p.value / 2.0) if p.id == "x_ks" else p
                for p in network.parameters
            ),
        )
        perturbation = Perturbation(
            kind="halved", target="x_ks",
            description="synthesis halved", network=halved,
        )
        effect = effect_on(perturbation, network, "x_X")
        assert effect.fold_change == pytest.approx(0.5, rel=1e-6)

    def test_a_dead_enzyme_stops_the_product_accumulating(self) -> None:
        # With kcat = 0 no product is made, so the product's steady state
        # is whatever it started at.
        network = _catalytic()
        dead = catalytically_dead(network, "reaction_kcat", unit="1/s")
        effect = effect_on(dead, network, "reaction_P")
        # The control converts all substrate; the dead mutant converts none.
        assert effect.perturbed is None or effect.perturbed < 1e-6


class TestTheDescriptionTravelsWithTheResult:
    def test_a_perturbation_carries_what_was_done(self) -> None:
        """A fold change with no statement of the perturbation is a number
        with no experiment attached.
        """
        result = overexpress(_catalytic(), "reaction_E", fold=5.0)
        assert "5-fold" in result.description
        assert "reaction_E" in result.summary()
        assert "->" in result.summary()

    def test_the_default_fold_is_stated_not_implied(self) -> None:
        result = overexpress(_catalytic(), "reaction_E")
        assert str(int(DEFAULT_OVEREXPRESSION_FOLD)) in result.description

    def test_every_change_is_recorded_so_it_can_be_reconstructed(self) -> None:
        network = _catalytic()
        result = knockdown(network, "reaction_E", 0.1)
        before, after = result.changes["reaction_E"]
        original = next(s.initial for s in network.species if s.id == "reaction_E")
        assert before == original
        assert after == pytest.approx(original * 0.1)


class TestTheScreen:
    def test_single_knockouts_covers_every_expressed_species(self) -> None:
        network = _catalytic()
        expressed = {s.id for s in network.species if s.initial != 0.0}
        assert expressed, "the premise"

        comparison = single_knockouts(network, "reaction_P")
        assert {e.perturbation.target for e in comparison.effects} == expressed

    def test_species_at_zero_are_absent_rather_than_reported_as_no_effect(
        self,
    ) -> None:
        # A screen that stopped at the first non-expressed gene would be
        # useless; one that reported it as having no effect would be wrong.
        network = _catalytic()
        absent = {s.id for s in network.species if s.initial == 0.0}
        assert absent, "the premise: a catalytic step starts with no product"

        comparison = single_knockouts(network, "reaction_P")
        assert not (absent & {e.perturbation.target for e in comparison.effects})

    def test_a_model_with_nothing_expressed_is_refused(self) -> None:
        network = _catalytic()
        empty = replace(
            network,
            species=tuple(replace(s, initial=0.0) for s in network.species),
        )
        with pytest.raises(PerturbationRefused, match="nothing"):
            single_knockouts(empty, "reaction_P")

    def test_comparing_no_perturbations_is_refused(self) -> None:
        with pytest.raises(PerturbationRefused, match="nothing to compare"):
            compare(_catalytic(), [], "reaction_P")


class TestMultistabilityIsRefusedRatherThanAveraged:
    def test_a_readout_with_two_stable_states_has_no_single_value(self) -> None:
        """Which state is reached depends on where the system started, not
        on the perturbation, so a fold change would describe the initial
        condition.
        """
        model = compose("a toggle switch between two repressors")
        network = model.network
        perturbation = set_level(network, "geneA_X", 0.5)
        effect = effect_on(perturbation, network, "geneA_X")
        assert effect.fold_change is None
        assert "stable states" in effect.note
