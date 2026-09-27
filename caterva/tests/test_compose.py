"""The compositional builder: what it builds, and what it refuses to.

WHY THIS EXISTS
---------------
The catalogue answers three of twenty realistic queries. Eleven of the
seventeen failures are compositional -- a cascade, a toggle switch, two
enzymes competing -- and no catalogue reaches them, because "three step"
becomes "four step" and each length would need its own entry.

These tests pin the pieces, the wiring, and the two refusals. They pin
hardest the things a composition gets quietly wrong: a shared species that
is actually two species, an intermediate that starts full instead of empty,
and a cascade wired as a conversion chain -- all of which simulate happily
and describe nothing.
"""

from __future__ import annotations

import pytest

from caterva.compose.builder import (
    Composition, CompositionError, chain, compete, couple,
)
from caterva.compose.grammar import (
    MAX_INFERRED_STAGES, RULES, UnrecognisedShape, recognise, shapes,
)
from caterva.compose.library import (
    CATALYTIC_STEP, HILL_REPRESSION, LIBRARY, PHOSPHORYLATION_CYCLE,
    REVERSIBLE_BINDING, motif,
)
from caterva.compose.motifs import (
    CHOSEN_KINDS, KIND_CONCENTRATION, KIND_EXPONENT, Motif, MotifError, Port,
    ReactionTemplate, RESOLVABLE_KINDS, ROLE_SUBSTRATE,
)
from caterva.core.network import describe_conservation_laws


class TestTheLibrary:
    def test_every_motif_validates_itself(self) -> None:
        # `Motif.__post_init__` checks that every rate-law placeholder is a
        # port or a parameter. Constructing the library at import time is
        # therefore already a test; this makes the coverage explicit.
        assert len(LIBRARY) >= 13
        for name, m in LIBRARY.items():
            assert m.name == name
            assert m.summary, f"{name} has no summary"
            assert m.basis, f"{name} does not say what assumption licenses it"

    def test_a_rate_law_referencing_an_unknown_symbol_is_rejected(self) -> None:
        with pytest.raises(MotifError, match="neither a port nor a parameter"):
            Motif(
                name="broken", summary="", ports=(Port("S", ROLE_SUBSTRATE),),
                parameters=(),
                reactions=(ReactionTemplate("r", {"S": 1}, {}, "{k} * {S}"),),
            )

    def test_a_name_used_as_both_port_and_parameter_is_rejected(self) -> None:
        # The rate-law formatter substitutes by name, so a collision would
        # silently resolve to whichever came last.
        from caterva.compose.motifs import KIND_RATE_CONSTANT, MotifParameter

        with pytest.raises(MotifError, match="both a port and a parameter"):
            Motif(
                name="clash", summary="", ports=(Port("k", ROLE_SUBSTRATE),),
                parameters=(MotifParameter("k", KIND_RATE_CONSTANT, 1.0, "1/s"),),
                reactions=(),
            )

    def test_no_motif_has_a_vmax(self) -> None:
        """The property that makes composed models resolvable.

        `Vmax` is kcat x [E]0 and is blocked forever (ADR 0013) because no
        paper can supply the [E]0 of your assay. Writing the mechanism out
        -- kcat as a literature parameter, the enzyme as a species whose
        amount is a scenario choice -- removes the lumped quantity that had
        to be refused rather than working around it.
        """
        for name, m in LIBRARY.items():
            names = {p.name.lower() for p in m.parameters}
            assert "vmax" not in names, f"{name} reintroduced a lumped Vmax"


class TestWiring:
    def test_a_cascade_makes_each_tier_the_next_tier_s_kinase(self) -> None:
        """The difference between a cascade and a chain of conversions.

        In a real cascade the ACTIVE form of one tier is the ENZYME of the
        next -- Raf-P phosphorylates MEK. Wiring product-to-substrate
        instead gives a linear conversion that simulates fine and is not a
        cascade.

        Asserted through `recognise()`, not on a hand-built composition. The
        first version of this test built its own chain, so mutating the
        GRAMMAR's wiring to product-to-substrate left it passing -- the most
        important biochemical property in this module, tested in a way that
        could not see the code that decides it.
        """
        network = recognise("three step phosphorylation cascade").network()
        laws = {r.id: r.rate_law for r in network.reactions}

        # Tier 2 is phosphorylated BY tier 1's active form.
        assert "tier1_Xp" in laws["tier2_phosphorylation"]
        assert "tier2_Xp" in laws["tier3_phosphorylation"]
        # And tier 2 acts on its OWN protein, not on tier 1's.
        assert "tier2_X" in laws["tier2_phosphorylation"]
        # The giveaway that it is NOT a conversion chain: tier 1's active
        # form is never consumed by tier 2.
        tier2 = next(r for r in network.reactions if r.id == "tier2_phosphorylation")
        assert "tier1_Xp" not in tier2.reactants
        assert "tier1_Xp" not in tier2.products

    def test_a_cascade_intermediate_is_created_by_the_upstream_port(self) -> None:
        # Asserted through `recognise()` for the same reason. Each tier's
        # own protein starts present; nothing else silently does.
        network = recognise("three step phosphorylation cascade").network()
        initials = {s.id: s.initial for s in network.species}
        for tier in ("tier1", "tier2", "tier3"):
            assert initials[f"{tier}_X"] == 1.0, tier
            assert initials[f"{tier}_Xp"] == 0.0, tier

    def test_one_phosphatase_serves_every_tier(self) -> None:
        composition = Composition("cascade")
        chain(
            composition, PHOSPHORYLATION_CYCLE, 3, prefix="tier",
            upstream_port="Xp", downstream_port="kinase",
            shared=("phosphatase",),
        )
        network = composition.to_network()
        phosphatases = [s.id for s in network.species if "phosphatase" in s.id]
        assert phosphatases == ["tier1_phosphatase"], phosphatases

    def test_an_intermediate_starts_empty_not_full(self) -> None:
        """Whose default wins when two ports share a species.

        A chained catalytic step joins step1's product to step2's substrate.
        The product default is 0 and the substrate default is 1; an
        intermediate that starts at 1 is a different experiment. The rule is
        that the UPSTREAM port creates the species, so this cannot depend on
        which motif was added first.
        """
        composition = Composition("chain")
        chain(
            composition, CATALYTIC_STEP, 3, prefix="step",
            upstream_port="P", downstream_port="S", head_initial=1.0,
        )
        initials = {s.id: s.initial for s in composition.to_network().species}
        assert initials["step1_S"] == 1.0, "the head substrate should be present"
        assert initials["step1_P"] == 0.0, "an intermediate should start empty"
        assert initials["step2_P"] == 0.0
        assert initials["step3_P"] == 0.0

    def test_competition_is_one_pool_not_two(self) -> None:
        # If each enzyme got its own substrate the model would run and the
        # enzymes would not compete at all -- the failure that looks most
        # like success.
        composition = Composition("competition")
        compete(composition, CATALYTIC_STEP, 2, prefix="enzyme", shared_port="S")
        network = composition.to_network()
        substrates = [s.id for s in network.species if s.id.endswith("_S")]
        assert substrates == ["enzyme1_S"], substrates
        for reaction in network.reactions:
            assert "enzyme1_S" in reaction.rate_law

    def test_competition_needs_at_least_two_competitors(self) -> None:
        composition = Composition("c")
        with pytest.raises(CompositionError, match="at least two"):
            compete(composition, CATALYTIC_STEP, 1, prefix="e", shared_port="S")

    def test_coupling_retires_the_species_it_replaced(self) -> None:
        # Otherwise the network carries an orphan that nothing produces or
        # consumes, which the validator would rightly complain about.
        composition = Composition("toggle")
        first = composition.add(HILL_REPRESSION, "a")
        second = composition.add(HILL_REPRESSION, "b")
        couple(composition, first, "X", second, "R")
        assert "b_R" not in composition.species_ids

    def test_binding_to_a_species_that_does_not_exist_is_refused(self) -> None:
        # A typo would otherwise create a second, disconnected copy of a
        # pathway that still simulates.
        composition = Composition("c")
        composition.add(CATALYTIC_STEP, "step1")
        with pytest.raises(CompositionError, match="no motif has created"):
            composition.add(CATALYTIC_STEP, "step2", {"S": "step1_Q"})

    def test_a_reused_prefix_is_refused(self) -> None:
        composition = Composition("c")
        composition.add(CATALYTIC_STEP, "step")
        with pytest.raises(CompositionError, match="already used"):
            composition.add(CATALYTIC_STEP, "step")


class TestWhatComesOut:
    def test_every_composed_network_validates(self) -> None:
        for query in (
            "three step phosphorylation cascade",
            "a toggle switch between two repressors",
            "two enzymes competing for the same substrate",
            "an open system with constant substrate inflow",
            "reversible binding of a ligand to a receptor",
            "substrate inhibition at high substrate concentration",
            "repressilator",
        ):
            network = recognise(query).network()
            assert network.problems() == [], (query, network.problems())

    def test_conservation_laws_are_derived_not_declared(self) -> None:
        # Nobody told this that a phosphorylation cycle conserves total
        # protein; it falls out of the stoichiometry matrix.
        network = recognise("three step phosphorylation cascade").network()
        laws = describe_conservation_laws(network)
        assert any("tier1_X" in law and "tier1_Xp" in law for law in laws), laws

    def test_an_open_system_conserves_nothing_over_the_fed_species(self) -> None:
        # The point of an inflow: with a zero-order source there is no
        # conservation law over what is fed, and the steady state reached is
        # not an equilibrium.
        network = recognise("an open system with constant substrate inflow").network()
        laws = describe_conservation_laws(network)
        assert not any("feed_S" in law for law in laws), laws

    def test_the_quantities_to_resolve_exclude_choices(self) -> None:
        # Concentrations and Hill coefficients are not looked up: nobody
        # publishes how much enzyme is in your tube, and n is a modelling
        # choice with a conventional value.
        recognition = recognise("a toggle switch between two repressors")
        resolvable = {q.parameter_name for q in recognition.composition.quantities_to_resolve()}
        assert "n" not in resolvable
        assert {"ks", "kd", "K"} <= resolvable

    def test_each_resolvable_quantity_says_what_it_is(self) -> None:
        # `tier2_kcat_kin` means nothing to a scout on its own.
        recognition = recognise("three step phosphorylation cascade")
        for quantity in recognition.composition.quantities_to_resolve():
            assert quantity.unit
            assert quantity.motif_name
            assert quantity.description or quantity.table

    def test_composition_is_deterministic(self) -> None:
        # Same query, same model. This is the property the LLM path cannot
        # offer and the reason this path exists.
        first = recognise("three step phosphorylation cascade").network()
        second = recognise("three step phosphorylation cascade").network()
        assert [s.id for s in first.species] == [s.id for s in second.species]
        assert [(r.id, r.rate_law) for r in first.reactions] == [
            (r.id, r.rate_law) for r in second.reactions
        ]

    def test_it_compiles_to_antimony(self) -> None:
        from caterva.core.network import compile_to_antimony

        text = compile_to_antimony(recognise("three step phosphorylation cascade").network())
        assert "tier1_phosphorylation" in text
        assert "tier2_phosphorylation" in text


class TestRefusal:
    def test_a_named_pathway_is_refused_with_the_reason(self) -> None:
        """The refusal that matters most.

        Glycolysis has ten enzymes and a specific stoichiometry. A grammar
        that produced SOMETHING for it would produce a plausible wrong
        pathway, which is worse than a refusal and is why
        UnrecognizedQueryError exists at all.
        """
        with pytest.raises(UnrecognisedShape) as caught:
            recognise("glycolysis in yeast")
        message = str(caught.value)
        assert "named pathway" in message
        assert "KEGG" in message or "Reactome" in message
        # It must not read as "I do not know that word".
        assert "does not yet read" in message

    def test_an_unrecognised_shape_lists_what_it_can_build(self) -> None:
        with pytest.raises(UnrecognisedShape) as caught:
            recognise("signalling in a cell")
        assert "Shapes this can build" in str(caught.value)

    def test_a_cascade_with_no_number_is_refused(self) -> None:
        # The number of tiers changes the model. Picking one would be an
        # invisible decision about the biology.
        with pytest.raises(UnrecognisedShape, match="needs a number of stages"):
            recognise("a phosphorylation cascade")

    def test_a_map_kinase_cascade_is_three_by_definition(self) -> None:
        # The exception, and it is a real one: MAPK cascades are three-tiered
        # (Raf/MEK/ERK and the same architecture elsewhere), so the number IS
        # stated -- by the name.
        recognition = recognise("a MAP kinase cascade")
        assert "three tiers by definition" in recognition.reading
        assert len(recognition.composition.instances) == 3

    def test_an_empty_query_is_refused(self) -> None:
        with pytest.raises(UnrecognisedShape, match="describes nothing"):
            recognise("   ")

    def test_an_absurd_stage_count_is_not_built(self) -> None:
        # A hundred-step cascade is a hundred unresolvable rate constants.
        with pytest.raises(UnrecognisedShape):
            recognise("a 500 step phosphorylation cascade")


class TestHonestyAboutWhatItDidNot_Do:
    def test_feedback_is_noted_rather_than_guessed(self) -> None:
        """The place this could most easily invent biology.

        "MAP kinase cascade with negative feedback" is a real request, and
        ERK feeds back on both SOS and Raf by different routes. Picking one
        would be inventing a mechanism. The model is built without it and
        the note says so, which is a different thing from silently omitting
        it.
        """
        recognition = recognise("a MAP kinase cascade with negative feedback")
        notes = " ".join(recognition.composition.notes)
        assert "NOT wired" in notes
        assert "State the target" in notes

    def test_sequential_feedback_says_which_step_it_would_need(self) -> None:
        recognition = recognise("sequential feedback inhibition in amino acid synthesis")
        notes = " ".join(recognition.composition.notes)
        assert "not wired" in notes.lower()
        assert "committed" in notes

    def test_the_toggle_switch_explains_its_asymmetric_start(self) -> None:
        # From a symmetric start the system sits on the separatrix and
        # neither gene wins -- a real property and a confusing first plot.
        recognition = recognise("a toggle switch between two repressors")
        notes = " ".join(recognition.composition.notes)
        assert "separatrix" in notes
        assert "unequal" in notes


class TestTheRuleTable:
    def test_priorities_are_unique_so_ordering_is_not_accidental(self) -> None:
        # ADR 0170 describes the defect this avoids: a matcher where two
        # candidates tie and list order silently decides.
        priorities = [rule.priority for rule in RULES]
        assert len(set(priorities)) == len(priorities), priorities

    def test_priority_decides_when_two_rules_match(self) -> None:
        """The test that found a wrong model.

        "Competitive inhibition ... by a substrate analogue" matches the
        inhibition rule and used to match the competition rule too, because
        that one required the PREFIX "compet". Competition outranks
        inhibition, so the query built two enzymes sharing a substrate pool
        -- a completely different model, silently, from a phrase that names
        its own mechanism.

        Both halves are asserted: that the right rule wins, and that the
        loser was genuinely in the running, so this cannot pass by the
        candidate set being narrowed to one.
        """
        # After the narrowing, the offending query matches only one rule --
        # which is the fix, and means it can no longer exercise ordering. So
        # ordering is tested on a query where three rules genuinely compete.
        query = "an allosteric inhibitor binding to a receptor"
        lowered = query.lower()
        matching = [
            rule.name for rule in RULES
            if all(word in lowered for word in rule.requires)
            and (not rule.triggers or any(t in lowered for t in rule.triggers))
        ]
        assert set(matching) == {"inhibition", "allosteric", "binding"}, matching
        # `inhibition` (70) outranks `allosteric` (68) and `binding` (60).
        assert recognise(query).rule == "competitive_inhibition"

        # And the query that started this: it must now match ONE rule, and
        # that rule must be the one it names.
        named = "competitive inhibition of an enzyme by a substrate analogue"
        named_lower = named.lower()
        named_matches = [
            rule.name for rule in RULES
            if all(word in named_lower for word in rule.requires)
            and (not rule.triggers or any(t in named_lower for t in rule.triggers))
        ]
        assert named_matches == ["inhibition"], named_matches
        assert recognise(named).rule == "competitive_inhibition"

    def test_list_order_and_priority_agree(self) -> None:
        """Why a mutation replacing max(priority) with candidates[0] survives.

        It survives because it is CORRECT: the tuple is written in
        descending priority order, so the first match is always the
        highest-priority match and the two selections cannot differ.

        That is worth pinning rather than leaving implicit. `priority` still
        earns its place -- it states the intent, and it means a rule can be
        inserted anywhere in the tuple later without silently re-ranking its
        neighbours, which is the defect ADR 0170 describes in the domain
        matcher. This test is what keeps that promise true: break the
        ordering and the redundancy stops being harmless.
        """
        priorities = [rule.priority for rule in RULES]
        assert priorities == sorted(priorities, reverse=True), priorities
        assert len(set(priorities)) == len(priorities), priorities

    def test_a_one_step_cascade_is_refused_as_not_a_cascade(self) -> None:
        # A cascade of one is a single phosphorylation cycle. Building it
        # under the name asked for answers a different question, and the
        # amplification a cascade exists for needs at least two tiers.
        with pytest.raises(UnrecognisedShape, match="not a cascade"):
            recognise("a one step phosphorylation cascade")

    def test_a_two_step_cascade_is_allowed(self) -> None:
        # The boundary bites in both directions or it is not a boundary.
        recognition = recognise("a two step phosphorylation cascade")
        assert len(recognition.composition.instances) == 2

    def test_the_word_competing_still_reaches_the_competition_rule(self) -> None:
        # The narrowing must not overshoot: the queries that SHOULD build a
        # shared substrate pool still do.
        for query in (
            "two enzymes competing for the same substrate",
            "competition between two enzymes for a substrate",
        ):
            assert recognise(query).rule == "enzyme_competition", query

    def test_every_rule_describes_itself_for_the_refusal_message(self) -> None:
        for rule in RULES:
            assert rule.describes
        assert len(shapes()) == len(RULES)


class TestThePipeline:
    """Composition joined to the literature layer, and what it refuses to ask."""

    def test_nothing_is_searched_for_when_nothing_was_named(self) -> None:
        """The decision that keeps a composed model honest.

        "Two enzymes competing for the same substrate" has four unknown
        constants and no subject. Sending scouts anyway would return "not
        found" four times and report a failed search that never happened.
        The empty request list is a decision, and `structure_only` says so.
        """
        from caterva.compose.pipeline import compose

        model = compose("two enzymes competing for the same substrate")
        assert model.structure_only
        assert model.parameter_requests() == []
        assert len(model.resolvable) == 4
        assert "No enzyme was named, so nothing was searched for" in model.summary()

    def test_naming_a_subject_produces_real_requests(self) -> None:
        from caterva.compose.pipeline import compose

        model = compose(
            "enzyme kinetics with a competitive inhibitor", subject="hexokinase",
        )
        assert not model.structure_only
        requests = model.parameter_requests()
        assert {r.table for r in requests} == {"kcat", "km", "ki"}
        assert all(r.subject == "hexokinase" for r in requests)
        # The unit travels, so substitution can be checked rather than assumed.
        assert all(r.expected_unit for r in requests)

    def test_a_constant_with_no_database_table_is_not_requested(self) -> None:
        # `ks` and `kd` in a Hill motif are real rate constants with no
        # BRENDA table. Asking for them would produce "searched and not
        # found" for something never searchable.
        from caterva.compose.pipeline import compose

        model = compose("a toggle switch between two repressors", subject="LacI")
        requested = {r.quantity for r in model.parameter_requests()}
        assert not any(name.endswith("_ks") for name in requested), requested

    def test_the_subject_is_never_inferred_from_the_query(self) -> None:
        # "A MAP kinase cascade" must not silently become MAP2K1 and attach
        # a real protein's measured constants to a generic three-tier model
        # -- the adjacent-paper miscitation of ADR 0076 in other clothes.
        from caterva.compose.pipeline import compose

        assert compose("a MAP kinase cascade").subject is None

    def test_an_unnamed_model_returns_no_search_rather_than_an_empty_one(self) -> None:
        # An empty ModelSearch would report a completed search over zero
        # quantities, which reads as a parameterised model.
        from caterva.compose.pipeline import compose_and_parameterise

        model, search = compose_and_parameterise("a toggle switch between two repressors")
        assert search is None
        assert model.structure_only

    def test_the_summary_says_a_conservation_law_was_derived(self) -> None:
        from caterva.compose.pipeline import compose

        summary = compose("three step phosphorylation cascade").summary()
        assert "left null space" in summary
        assert "Nobody asserted these" in summary

    def test_an_open_system_names_the_species_it_does_not_conserve(self) -> None:
        """The binary "are there laws" question misses the point.

        An open system still conserves its enzyme, so it HAS laws -- while
        the fed species, the one the openness is about, appears in none of
        them. The first version of this reported only the count and said
        nothing about the thing the model was built to show.
        """
        from caterva.compose.pipeline import compose

        model = compose("an open system with constant substrate inflow")
        summary = model.summary()
        assert "feed_S" in summary
        assert "appear(s) in no conservation law" in summary
        assert "what makes the system open" in summary
        # The enzyme IS conserved, and must not be listed as open.
        assert "reaction_E appear" not in summary

    def test_a_closed_model_lists_no_unconserved_species(self) -> None:
        # The other direction: every species in a phosphorylation cascade
        # sits in some law, so nothing should be reported as open.
        from caterva.compose.pipeline import compose

        summary = compose("three step phosphorylation cascade").summary()
        assert "appear(s) in no conservation law" not in summary


class TestCoverage:
    """Which of the twenty benchmark queries this path can build.

    Pinned so the number cannot drift unnoticed in either direction: a
    regression that stops building one, or a change that starts building
    something it should refuse.
    """

    BUILDS = (
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

    REFUSES = (
        # These are the CATALOGUE's queries -- epidemiology, population
        # genetics, PCR. The compositional path should not be answering
        # them, and a version that started to would be reaching past what
        # its motifs describe.
        "SIR model of a measles outbreak in a school",
        "genetic drift in a small population",
        "predator prey population cycles",
        "PCR amplification over 30 cycles",
        # And the named pathway.
        "glycolysis in yeast",
    )

    def test_it_builds_what_it_claims_to(self) -> None:
        from caterva.compose.pipeline import compose

        for query in self.BUILDS:
            model = compose(query)
            assert model.network.problems() == [], query
            assert model.network.reactions, query

    def test_it_refuses_what_belongs_to_another_path(self) -> None:
        from caterva.compose.pipeline import compose

        for query in self.REFUSES:
            with pytest.raises(UnrecognisedShape):
                compose(query)

    def test_the_two_lists_do_not_overlap(self) -> None:
        # A query in both would make one of the two assertions vacuous.
        assert not (set(self.BUILDS) & set(self.REFUSES))
