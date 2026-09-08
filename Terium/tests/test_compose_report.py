"""The dossier: everything known about a composed model, in one document.

WHY THESE TESTS ARE MOSTLY ABOUT PLACEMENT
------------------------------------------
The report's whole job is that the caveats sit NEXT TO the results they
qualify. A reader who stops halfway must not have been misled by the half
they read. So these tests check where things are, not only that they exist:
that the placeholder warning is in the behaviour section rather than in a
footnote, that the influence ranking is inside the table of unmeasured
constants rather than in a section after it, and that a table which cannot
be ranked is printed in its original order rather than in a guessed one.

They also pin the two sentences that stop the ranking being over-read --
that it is local, and that influence is not priority -- because a ranked
list is exactly the kind of output a hurried reader treats as a verdict.
"""

from __future__ import annotations

import pytest

from Terium.compose.pipeline import compose
from Terium.compose.report import ModelDossier, _default_target, dossier


# -- shared, because these are expensive ------------------------------------
#
# Building the cascade and ranking its twelve constants costs twenty-five
# steady-state solves. Twenty-odd tests want the same two values, and
# recomputing them per test added minutes to the engine suite for no extra
# coverage. Both are frozen and no test mutates them.


@pytest.fixture(scope="module")
def model():
    return compose("three step phosphorylation cascade")


@pytest.fixture(scope="module")
def ranking(model):
    from Terium.compose.sensitivity import rank_unmeasured

    return rank_unmeasured(model, "tier3_Xp")


class TestTheUnmeasuredTable:
    def test_without_a_ranking_it_keeps_its_own_order(self, model) -> None:
        """An unranked list is honest; a mis-ranked one is not.

        When no sensitivity report is available the table must not invent an
        ordering -- the reader would read the top row as the thing to
        measure first.
        """
        report = ModelDossier(query="q", model=model, sensitivity=None)
        rendered = "\n".join(report.provenance_section())

        assert "| influence |" not in rendered
        order = [
            line.split("`")[1] for line in rendered.splitlines()
            if line.startswith("| `")
        ]
        assert order == [q.parameter_id for q in model.resolvable]

    def test_with_a_ranking_the_table_is_sorted_by_influence(self, model, ranking) -> None:
        sensitivity = ranking
        report = ModelDossier(query="q", model=model, sensitivity=sensitivity)
        rendered = "\n".join(report.provenance_section())

        assert "| influence |" in rendered
        influence = {s.parameter: abs(s.relative) for s in sensitivity.sensitivities}
        order = [
            line.split("`")[1] for line in rendered.splitlines()
            if line.startswith("| `")
        ]
        scores = [influence.get(name) for name in order]
        ranked = [s for s in scores if s is not None]
        assert ranked == sorted(ranked, reverse=True)

    def test_an_unrankable_constant_sorts_last_and_says_so(self, model, ranking) -> None:
        """Not judged is not judged unimportant.

        A constant the sensitivity run skipped -- its value is zero, say --
        must not be sorted as though it scored zero, which would put it
        among the ones measured to be negligible.
        """
        sensitivity = ranking
        trimmed = _drop_first(sensitivity)
        missing = sensitivity.sensitivities[0].parameter

        report = ModelDossier(query="q", model=model, sensitivity=trimmed)
        lines = [
            line for line in report.provenance_section() if line.startswith("| `")
        ]
        assert "_not ranked_" in lines[-1]
        assert missing in lines[-1]

    def test_a_negligible_row_keeps_its_number(self, model, ranking) -> None:
        """The column's whole job is the spread.

        An earlier version printed "negligible here" for every row of a
        saturated cascade. True, and useless: those twelve constants span
        four orders of magnitude, from 9e-5 down to 1e-9, and that spread IS
        the ranking. Collapsing it to one word threw away the column.
        """
        sensitivity = ranking
        assert all(s.negligible for s in sensitivity.sensitivities), "the premise"

        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        for entry in sensitivity.sensitivities:
            assert f"S = {entry.relative:+.2g}" in rendered
        assert "_(negligible)_" in rendered

        # And the spread survives into the document, not just the data.
        magnitudes = {abs(s.relative) for s in sensitivity.sensitivities}
        assert max(magnitudes) > 1000 * min(magnitudes)

    def test_a_row_below_the_noise_floor_prints_no_number(self) -> None:
        # There the number really would be meaningless -- it is the
        # quantity's own error divided by the step.
        from Terium.compose.report import _influence_cell
        from Terium.compose.sensitivity import Sensitivity

        unresolvable = Sensitivity("p", 1.0, 1e-12, 1e-12, 1e-9)
        assert unresolvable.unresolvable
        cell = _influence_cell(unresolvable)
        assert "noise floor" in cell
        assert "1e-12" not in cell

    def test_an_actionable_row_is_emphasised(self) -> None:
        from Terium.compose.report import _influence_cell
        from Terium.compose.sensitivity import Sensitivity

        actionable = _influence_cell(Sensitivity("p", 1.0, 2.0, 2.0, 1e-9))
        assert "**S = +2**" in actionable
        assert "negligible" not in actionable

    def test_the_ranking_is_next_to_the_table_and_not_in_its_own_section(
        self, model, ranking,
    ) -> None:
        # The ordering is the property that turns this table from a list
        # into a plan. A reader who stops at the table must already have it.
        report = ModelDossier(
            query="q", model=model, sensitivity=ranking
        )
        provenance = "\n".join(report.provenance_section())
        assert "Ordered by influence" in provenance
        assert "## " not in provenance.split("Ordered by influence")[1]


class TestWhatTheRankingMustNotBeReadAs:
    def test_it_says_the_ordering_is_local(self, model, ranking) -> None:
        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=ranking)
            .provenance_section()
        )
        assert "local" in rendered
        assert "two decades away" in rendered

    def test_it_distinguishes_influence_from_priority(self, model, ranking) -> None:
        """The distinction the whole table turns on.

        A constant with high influence that BRENDA already holds is not
        work. A modest one nobody has measured is. Ranking by influence and
        calling the result a priority list would send a researcher to the
        bench for a number they could have looked up.
        """
        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=ranking)
            .provenance_section()
        )
        assert "influence, not" in rendered
        assert "priority" in rendered

    def test_it_names_the_floor_the_negligible_rows_were_judged_against(
        self, model, ranking,
    ) -> None:
        sensitivity = ranking
        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        assert f"{sensitivity.resolution:.1g}" in rendered

    def test_a_table_where_nothing_is_actionable_says_the_opposite_advice(
        self, model, ranking,
    ) -> None:
        """"Measure the top of this list" is wrong at saturation.

        The top of the list is not worth measuring either. The caption has
        to follow what was found rather than being fixed prose, and it has
        to say the saturation is itself an artefact of the placeholders --
        otherwise it reads as a licence to leave the model ungrounded.
        """
        sensitivity = ranking
        assert all(s.negligible for s in sensitivity.sensitivities), "the premise"

        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        assert "would not move this answer" in rendered
        assert "reason to ground the model, not a reason to leave it" in rendered
        assert "Measuring the top of this list" not in rendered

    def test_a_table_with_an_actionable_row_keeps_the_usual_advice(self, model, ranking) -> None:
        sensitivity = _promote_first(ranking)
        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        assert "Measuring the top of this list" in rendered
        assert "would not move this answer" not in rendered

    def test_it_names_the_quantity_the_ordering_is_about(self, model, ranking) -> None:
        # "Influence" with no object is not a claim. The same constant
        # ranks differently against a steady state and against a settling
        # time.
        sensitivity = ranking
        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        assert sensitivity.quantity in rendered
        assert "tier3_Xp" in sensitivity.quantity


class TestThePlaceholderWarning:
    def test_it_sits_in_the_behaviour_section(self, model) -> None:
        """Where the reader forms the belief it qualifies.

        A bistability claim means something different when every constant in
        the model is the library's illustrative value. Putting that in
        provenance and the claim in behaviour separates them by a screen.
        """
        from Terium.compose.analysis import analyse

        report = ModelDossier(
            query="q", model=model, stability=analyse(model.network)
        )
        behaviour = "\n".join(report.behaviour_section())
        assert "about the model's SHAPE" in behaviour

    def test_a_grounded_model_gets_no_such_warning(self, model) -> None:
        # The warning is about placeholders. A model with none must not
        # carry it, or it becomes noise that readers learn to skip.
        assert model.structure_only, "the premise"
        assert ModelDossier(query="q", model=model).placeholder_warning() is not None

        class _Grounded:
            structure_only = False
            resolvable = model.resolvable

        assert ModelDossier(query="q", model=_Grounded()).placeholder_warning() is None

    def test_a_model_with_nothing_left_to_resolve_gets_no_warning(self) -> None:
        # The count is the subject of the sentence. "All 0 rate constants
        # are illustrative values" is not a warning, it is a bug.
        class _Complete:
            structure_only = True
            resolvable = ()

        assert ModelDossier(query="q", model=_Complete()).placeholder_warning() is None


class TestTheDefaultTarget:
    def test_it_is_the_last_thing_the_mechanism_produces(self, model) -> None:
        # A cascade's bottom tier is what a reader means by "the answer".
        assert _default_target(model) == "tier3_Xp"

    def test_it_is_not_the_last_product_of_the_last_reaction(self, model) -> None:
        """The bug this rule replaced, pinned so it cannot come back.

        A cascade tier's LAST reaction is the phosphatase step, whose
        product is the DEPHOSPHORYLATED form. Reading the target off
        reaction order therefore ranked every constant against the opposite
        of the question, confidently.
        """
        network = model.network
        last_product = None
        for reaction in reversed(network.reactions):
            if reaction.products:
                last_product = list(reaction.products)[-1]
                break
        assert last_product == "tier3_X"
        assert _default_target(model) != last_product

    def test_it_prefers_a_product_over_an_enzyme(self) -> None:
        # The competition model's last instance declares both. An enzyme is
        # never what "the answer" means.
        model = compose("two enzymes competing for the same substrate")
        assert _default_target(model) == "enzyme2_P"

    def test_a_composition_declaring_no_product_gets_no_target(self) -> None:
        """`None` rather than a fallback to some species.

        Ranking against an arbitrary species would put a confident ordering
        next to the wrong question, which is worse than no ordering -- and
        is exactly the failure the reaction-order rule had.
        """
        class _Model:
            class recognition:
                class composition:
                    instances = ()

        assert _default_target(_Model()) is None


class TestAssembly:
    def test_a_refused_ranking_costs_a_note_and_not_the_report(self) -> None:
        """Every refusal in the sensitivity module is a real one.

        No unique stable state, a continuum, a quantity that will not
        evaluate. None of them should cost the reader the structure, the
        units, or the conservation laws, which are the parts that always
        work.
        """
        report = dossier(
            "two enzymes competing for the same substrate",
            analyse_stability=False, simulate=False,
        )
        assert report.sensitivity is None
        notes = " ".join(report.model.recognition.composition.notes)
        assert "no influence ranking" in notes
        assert "## Structure" in report.markdown()

    def test_the_ranking_can_be_turned_off(self) -> None:
        report = dossier(
            "three step phosphorylation cascade",
            analyse_stability=False, simulate=False, rank_unmeasured=False,
        )
        assert report.sensitivity is None
        assert "| influence |" not in report.markdown()

    def test_the_markdown_holds_every_section_it_has_data_for(self) -> None:
        report = dossier(
            "three step phosphorylation cascade",
            simulate=False, rank_unmeasured=False,
        )
        rendered = report.markdown()
        for heading in (
            "## Structure", "## Where the numbers come from", "## Behaviour"
        ):
            assert heading in rendered

    def test_it_says_no_language_model_was_involved(self) -> None:
        # The claim the whole builder rests on, and the one an institution
        # will check first.
        report = dossier(
            "three step phosphorylation cascade",
            analyse_stability=False, simulate=False, rank_unmeasured=False,
        )
        assert "no language model was involved" in report.markdown()


# -- helpers ---------------------------------------------------------------


def _drop_first(report):
    from dataclasses import replace

    return replace(report, sensitivities=report.sensitivities[1:])


def _promote_first(report):
    """The same report with its top row raised above the act-on threshold.

    Constructed rather than found: no query in the library currently builds
    a model with an actionable unmeasured constant, and a test that waited
    for one would silently check nothing until one appeared.
    """
    from dataclasses import replace

    rows = list(report.sensitivities)
    rows[0] = replace(rows[0], relative=2.0)
    return replace(report, sensitivities=tuple(rows))


class TestTheCaptionFollowsTheCause:
    """An all-zero table has two possible causes and opposite advice.

    Saturation: nothing is worth measuring anywhere. Conservation: the
    question was asked of the wrong quantity, and the kinetics answer a
    different one. Captioning the second as the first attaches a plausible
    wrong reason to a correct number.
    """

    def _pinned(self):
        from Terium.compose.sensitivity import rank_unmeasured

        model = compose("substrate inhibition at high substrate concentration")
        return model, rank_unmeasured(model, "reaction_P")

    def test_a_conserved_target_gets_the_structural_caption(self) -> None:
        model, sensitivity = self._pinned()
        assert sensitivity.conserved_by, "the premise"

        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        assert sensitivity.conserved_by in rendered
        assert "the reason is structural" in rendered
        assert "how FAST the system arrives, never WHERE" in rendered
        assert "settling time or the time course" in rendered

    def test_it_does_not_call_a_conserved_target_saturated(self) -> None:
        model, sensitivity = self._pinned()
        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        assert "saturation" not in rendered

    def test_a_saturated_target_still_gets_the_saturation_caption(
        self, model, ranking
    ) -> None:
        # The cascade's target IS in a conservation law, so a weaker
        # discriminator would reroute it to the structural caption.
        assert ranking.conserved_by is None, "the premise"
        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=ranking)
            .provenance_section()
        )
        assert "saturation" in rendered
        assert "the reason is structural" not in rendered


class TestTheBindingMotifHasATarget:
    def test_a_motif_with_no_product_falls_back_to_its_complex(self) -> None:
        """Previously silence, not a refusal.

        `_default_target` looked only for product ports, so a binding motif
        -- which declares partners and a complex -- returned None and the
        dossier simply had no ranking, with nothing saying why.
        """
        model = compose("reversible binding of a ligand to a receptor")
        assert _default_target(model) == "complex_AB"

    def test_a_product_still_wins_over_a_complex(self) -> None:
        # Products are tried across every instance before complexes are,
        # so a composition that both produces and binds ranks against the
        # thing produced.
        assert _default_target(compose("three step phosphorylation cascade")) == (
            "tier3_Xp"
        )

    def test_the_dossier_now_ranks_a_binding_model(self) -> None:
        report = dossier(
            "reversible binding of a ligand to a receptor",
            analyse_stability=False, simulate=False,
        )
        assert report.sensitivity is not None
        assert "| influence |" in report.markdown()


class TestTheTableWhenNothingCouldBeMeasured:
    def _inert(self):
        from Terium.compose.sensitivity import rank_unmeasured

        model = compose("allosteric activation of an enzyme by its product")
        return model, rank_unmeasured(model, "regulated_X")

    def test_it_says_nothing_was_measured_rather_than_nothing_matters(
        self,
    ) -> None:
        model, sensitivity = self._inert()
        assert sensitivity.sensitivities == (), "the premise"

        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        assert "No influence could be computed for any of these" in rendered
        assert "nothing was measured" in rendered
        assert "saturation" not in rendered

    def test_it_does_not_claim_an_ordering_it_did_not_make(self) -> None:
        # "Ordered by influence on X" above an unranked table is a caption
        # for a thing that did not happen.
        model, sensitivity = self._inert()
        rendered = "\n".join(
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
        )
        assert "Ordered by influence" not in rendered

    def test_every_row_is_marked_unranked(self) -> None:
        model, sensitivity = self._inert()
        rows = [
            line for line in
            ModelDossier(query="q", model=model, sensitivity=sensitivity)
            .provenance_section()
            if line.startswith("| `")
        ]
        assert rows
        assert all("_not ranked_" in row for row in rows)


class TestTheTableExplainsASwitchedQuantity:
    def _pinned_dossier(self):
        return dossier(
            "substrate inhibition at high substrate concentration",
            analyse_stability=False, simulate=False,
        )

    def test_it_says_why_it_is_ranking_a_settling_time(self) -> None:
        """`kcat` at S = -1 with no explanation reads as a claim about
        where the system lands, which is the opposite of what it means.
        """
        rendered = "\n".join(self._pinned_dossier().provenance_section())

        assert "reaction_S + reaction_P" in rendered
        assert "is conserved" in rendered
        assert "how fast it arrives" in rendered
        assert "settling time" in rendered

    def test_it_still_gives_the_ordinary_advice(self) -> None:
        # The list IS actionable now, unlike the pinned steady-state one.
        rendered = "\n".join(self._pinned_dossier().provenance_section())
        assert "Measuring the top of this list" in rendered

    def test_the_column_carries_the_settling_numbers(self) -> None:
        rendered = "\n".join(self._pinned_dossier().provenance_section())
        assert "**S = -1**" in rendered
        assert "**S = +1**" in rendered
