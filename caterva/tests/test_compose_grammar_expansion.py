"""Whether the new motif libraries can be REACHED, and what swallows what.

WHY A SEPARATE FILE FOR THIS
----------------------------
Three libraries were added beside `library.py` -- expression, enzymology,
transport -- and a motif nobody can name is not a capability. `test_compose`
pins what the grammar builds; this pins that every new shape has a phrase
that gets to it, and that adding those phrases did not quietly take the
phrases that were already there.

THE HALF THAT MATTERS IS THE COLLISIONS
---------------------------------------
Rule selection in `grammar.py` is SUBSTRING matching over trigger words, and
the biochemistry it has to separate is adversarial about substrings:

    "competitive"  is inside  "uncompetitive"  and  "noncompetitive"

Those are three different rate laws with three different Lineweaver-Burk
signatures -- competitive raises apparent Km, uncompetitive lowers Km and
Vmax together, non-competitive lowers Vmax alone -- so confusing them does
not degrade an answer, it replaces one. And it replaces it silently: the
wrong model has the same species, integrates fine, and plots a smooth curve.

This repository has already shipped that defect twice. `requires=("compet",)`
on the competition rule made "competitive inhibition of an enzyme by a
substrate analogue" build two enzymes sharing a substrate pool, because a
prefix matched a word it was not about and competition outranks inhibition.
The fix was a narrowing, and a narrowing is exactly the kind of change a
later trigger word undoes by accident.

So the tests here are mostly about words that must NOT match. They are
written against a pinned table of query to winning rule rather than against
"it built something", because "it built something" is what the bug looked
like both times.

WHAT IS ASSERTED WHEN A LIBRARY IS ABSENT
-----------------------------------------
These libraries are written independently of the grammar and any of them can
be missing from a checkout. That is not an excuse for a soft test. Two
claims are made unconditionally either way:

  * the SHAPE is recognised -- the query reaches a rule, always, because
    reachability is what this file exists to check and it does not depend on
    any library being present;
  * the outcome is either a built model or a `MissingMotifLibrary` that
    NAMES the file it wanted, so a refusal is actionable rather than a
    shrug.

A test that accepted "built, or refused for any reason at all" would pass
against a grammar that had forgotten the rule entirely, which is the
regression it is here to catch.
"""

from __future__ import annotations

import importlib

import pytest

from caterva.compose.grammar import (
    EXPANSION_LIBRARIES, MissingMotifLibrary, RULES, UnrecognisedShape,
    recognise, shapes,
)


# ---------------------------------------------------------------------------
# Reading the rule table the way `recognise` does
# ---------------------------------------------------------------------------
#
# Duplicated from `recognise` on purpose. Calling `recognise` answers "what
# was built", and half of what is pinned here is "which rule was in the
# running", which a Recognition cannot report -- the two prefix bugs were
# both about a rule that should never have been a candidate.


def _candidates(query: str) -> list:
    lowered = query.lower()
    return [
        rule for rule in RULES
        if all(word in lowered for word in rule.requires)
        and (not rule.triggers or any(trigger in lowered for trigger in rule.triggers))
    ]


def _winning_rule(query: str):
    """The rule `recognise` would pick, or None if nothing matches."""
    candidates = _candidates(query)
    return max(candidates, key=lambda rule: rule.priority).name if candidates else None


def _library_present(module: str) -> bool:
    try:
        importlib.import_module(f"caterva.compose.{module}")
    except ImportError:
        return False
    return True


AVAILABLE = {module for module in EXPANSION_LIBRARIES if _library_present(module)}


# ---------------------------------------------------------------------------
# What each new phrase must reach
# ---------------------------------------------------------------------------
#
# (query, rule in RULES that must win, Recognition.rule it must produce,
#  the expansion library it needs or None for the core one).
#
# Both rule names are pinned because they answer different questions. The
# RULES name says the query got to the right FAMILY and no other family
# outranked it; the Recognition name says the branch inside that family
# chose the right MECHANISM. The inhibition collisions live entirely in the
# second, which is why "it matched the inhibition rule" is not enough.

NEW_SHAPES = (
    # -- gene expression ---------------------------------------------------
    ("two stage gene expression",
     "gene_expression", "two_stage_expression", "library_expression"),
    ("transcription and translation of a gene",
     "gene_expression", "two_stage_expression", "library_expression"),
    ("the central dogma: mrna then protein",
     "gene_expression", "two_stage_expression", "library_expression"),
    ("translation of an mrna by a ribosome",
     "gene_expression", "translation", "library_expression"),
    ("a constitutive promoter",
     "gene_expression", "constitutive_promoter", "library_expression"),
    ("a repressed promoter",
     "gene_expression", "repressed_promoter", "library_expression"),
    ("an activated promoter",
     "gene_expression", "activated_promoter", "library_expression"),
    ("mrna degradation",
     "gene_expression", "mrna_degradation", "library_expression"),
    ("ssra tagged protein degradation",
     "gene_expression", "tagged_degradation", "library_expression"),
    ("a negatively autoregulated gene",
     "autoregulated_gene", "autoregulated_gene", "library_expression"),
    ("an autoregulated gene",
     "autoregulated_gene", "autoregulated_gene", "library_expression"),

    # -- enzyme mechanisms already served by the core library --------------
    ("uncompetitive inhibition of an enzyme",
     "inhibition", "uncompetitive_inhibition", None),
    ("noncompetitive inhibition of an enzyme",
     "inhibition", "noncompetitive_inhibition", None),
    ("non-competitive inhibition of an enzyme",
     "inhibition", "noncompetitive_inhibition", None),
    ("mixed inhibition of an enzyme",
     "inhibition", "mixed_inhibition", None),
    ("product inhibition of an enzyme",
     "inhibition", "product_inhibition", None),
    ("competitive inhibition of an enzyme",
     "inhibition", "competitive_inhibition", None),
    ("a ping pong bi bi mechanism",
     "bi_substrate", "ping_pong_bi_bi", None),
    ("an ordered bi-bi mechanism",
     "bi_substrate", "ordered_bi_bi", None),

    # -- enzymology library ------------------------------------------------
    ("the mwc concerted model of an allosteric enzyme",
     "mwc_allostery", "mwc_allostery", "library_enzymology"),
    ("a concerted allosteric transition between tense and relaxed states",
     "mwc_allostery", "mwc_allostery", "library_enzymology"),
    ("a futile cycle",
     "futile_cycle", "futile_cycle", "library_enzymology"),
    ("a substrate cycle run by a kinase and phosphatase",
     "futile_cycle", "futile_cycle", "library_enzymology"),
    ("substrate channelling between two enzymes",
     "substrate_channeling", "substrate_channeling", "library_enzymology"),
    ("a metabolon",
     "substrate_channeling", "substrate_channeling", "library_enzymology"),

    # -- transport ---------------------------------------------------------
    ("facilitated diffusion of glucose",
     "transport", "facilitated_transport", None),
    ("sodium glucose symport",
     "transport", "symport", "library_transport"),
    ("a sodium calcium antiport exchanger",
     "transport", "antiport", "library_transport"),
    ("primary active transport by an atp driven pump",
     "transport", "primary_active_transport", "library_transport"),
    ("a passive leak across the membrane",
     "transport", "passive_leak", "library_transport"),
    ("receptor mediated endocytosis",
     "receptor_internalisation", "receptor_internalisation", "library_transport"),
    ("receptor internalisation after ligand binding",
     "receptor_internalisation", "receptor_internalisation", "library_transport"),

    # -- signalling and metabolic ------------------------------------------
    #
    # Added when `library_signaling` and `library_metabolic` were registered
    # in `EXPANSION_LIBRARIES`, because
    # `test_every_registered_library_has_a_query_that_reaches_it` is what
    # demands it: a library in that mapping with no phrase that reaches it
    # is a capability nobody can name. One representative row per library is
    # what that invariant needs; the full sweep over the new shapes, and the
    # collisions they introduced, live in
    # `test_compose_grammar_expansion2.py`.
    ("an incoherent feedforward loop",
     "feedforward_loop", "incoherent_feedforward", "library_signaling"),
    ("a coherent feed-forward loop",
     "feedforward_loop", "coherent_feedforward", "library_signaling"),
    ("a two component system",
     "two_component_system", "two_component_system", "library_signaling"),
    ("a gpcr activation cycle",
     "gpcr_cycle", "gpcr_activation", "library_signaling"),
    ("a linear metabolic pathway of four steps",
     "metabolic_pathway", "linear_metabolic_pathway", "library_metabolic"),
    ("a branch point where one metabolite feeds two enzymes",
     "branch_point", "branch_point", "library_metabolic"),
    ("a moiety conserved cycle",
     "moiety_cycle", "moiety_conserved_cycle", "library_metabolic"),
    # Core, deliberately: `library_signaling.ULTRASENSITIVE_CYCLE` is a name
    # bound to `library.PHOSPHORYLATION_CYCLE` rather than a second
    # definition, so this shape needs no expansion library to build.
    ("an ultrasensitive phosphorylation cycle",
     "ultrasensitive_cycle", "ultrasensitive_cycle", None),
)


# Every query the suite already relied on, with the rule that must keep
# winning it. `None` means the grammar must keep matching nothing, which for
# the catalogue's own domains -- an epidemic, genetic drift, PCR -- is the
# correct answer and the one a new trigger word is most likely to break.
UNCHANGED = {
    "michaelis menten kinetics for hexokinase": "michaelis_menten",
    "enzyme kinetics with a competitive inhibitor": "inhibition",
    "SIR model of a measles outbreak in a school": None,
    "SEIR epidemic with an exposed class": None,
    "genetic drift in a small population": None,
    "predator prey population cycles": None,
    "stochastic simulation of a chemical reaction": None,
    "PCR amplification over 30 cycles": None,
    "repressilator oscillations": "repressilator",
    "cell cycle oscillator dynamics": None,
    "three step phosphorylation cascade": "phosphorylation_cascade",
    "glycolysis in yeast": None,
    "a MAP kinase cascade with negative feedback": "phosphorylation_cascade",
    "reversible binding of a ligand to a receptor": "binding",
    "substrate inhibition at high substrate concentration": "inhibition",
    "two enzymes competing for the same substrate": "competition",
    "a toggle switch between two repressors": "toggle_switch",
    "sequential feedback inhibition in amino acid synthesis": "feedback_inhibition",
    "an open system with constant substrate inflow": "open_system",
    "allosteric activation of an enzyme by its product": "allosteric",
    # The two queries `test_compose` uses to pin ordering. They are repeated
    # here because a new trigger that matched either would break that file
    # in a way whose cause was in this one.
    "an allosteric inhibitor binding to a receptor": "inhibition",
    "competitive inhibition of an enzyme by a substrate analogue": "inhibition",
    "signalling in a cell": None,
    "a phosphorylation cascade": "phosphorylation_cascade",
    "a MAP kinase cascade": "phosphorylation_cascade",
}


def _outcome(query: str):
    """(rule name, None) if it built, (None, exception) if it refused."""
    try:
        return recognise(query).rule, None
    except UnrecognisedShape as refused:
        return None, refused


class TestEveryNewShapeIsReachable:
    """A motif library nobody can name from a query is not a capability."""

    def test_every_new_query_reaches_the_rule_meant_for_it(self) -> None:
        """The reachability claim, and it needs no library to be present.

        Rule selection happens before any motif is fetched, so this is the
        one assertion in the file that holds identically on a checkout with
        all three libraries and on one with none. If a trigger word is
        misspelled, or a higher-priority rule swallows the phrase, it fails
        here rather than showing up as a strange model later.
        """
        wrong = [
            (query, expected, _winning_rule(query))
            for query, expected, _, _ in NEW_SHAPES
            if _winning_rule(query) != expected
        ]
        assert wrong == []

    def test_every_new_rule_is_reached_by_at_least_one_query(self) -> None:
        # The other direction: a rule in the table that no phrase gets to is
        # dead weight, and it is the exact shape of the defect this file is
        # named after.
        added = {
            "gene_expression", "autoregulated_gene", "receptor_internalisation",
            "futile_cycle", "substrate_channeling", "mwc_allostery",
        }
        reached = {rule for _, rule, _, _ in NEW_SHAPES}
        assert added - reached == set()
        # And every name in that set is really in the table, so a rename
        # cannot make this pass by comparing two empty sets.
        assert added <= {rule.name for rule in RULES}

    def test_each_new_query_builds_or_names_the_file_it_wanted(self) -> None:
        """Built where the library is here; a refusal that names it where not.

        The second half is the interesting one. "I cannot do that" is not an
        answer a user can act on; "caterva/compose/library_transport.py is not
        in this checkout" is. Asserting only "it did not crash" would pass
        against a grammar that had lost the rule.
        """
        failures = []
        for query, _, expected_rule, module in NEW_SHAPES:
            built, refused = _outcome(query)
            if module is None or module in AVAILABLE:
                if built != expected_rule:
                    failures.append(
                        f"{query!r} -> {built or refused!r}, wanted {expected_rule!r}"
                    )
                continue
            if not isinstance(refused, MissingMotifLibrary):
                failures.append(f"{query!r} refused with {refused!r}, wanted a "
                                f"MissingMotifLibrary naming {module}")
            elif refused.module != module or module not in str(refused):
                failures.append(f"{query!r} refused without naming {module}")
        assert failures == []

    def test_the_libraries_this_run_actually_had_are_reported(self) -> None:
        # So a green run says WHICH half it proved. A run with no expansion
        # library still proves reachability and the refusals; it cannot
        # prove a single model builds, and that difference should be
        # readable without re-deriving it from the code.
        print(
            "expansion libraries present: "
            + (", ".join(sorted(AVAILABLE)) or "none")
            + "; absent: "
            + (", ".join(sorted(set(EXPANSION_LIBRARIES) - AVAILABLE)) or "none")
        )
        # The detector several tests above lean on has to be able to say
        # "no". A `_library_present` that returned True for everything would
        # silently turn every build-or-refuse assertion into a build-only
        # one, and nothing else here would notice.
        assert not _library_present("library_that_nobody_wrote")
        assert _library_present("library"), "the core library must always import"


class TestTheInhibitionCollisions:
    """The point of the file.

    "competitive" is a substring of "uncompetitive" and of
    "noncompetitive", and the three are different rate laws. Every
    assertion below is about a word that must not swallow another.
    """

    def test_uncompetitive_inhibition_does_not_build_a_competitive_model(self) -> None:
        recognition = recognise("uncompetitive inhibition of an enzyme")
        assert recognition.rule != "competitive_inhibition"
        assert recognition.rule == "uncompetitive_inhibition"

    def test_noncompetitive_inhibition_does_not_build_a_competitive_model(self) -> None:
        for spelling in (
            "noncompetitive inhibition of an enzyme",
            "non-competitive inhibition of an enzyme",
        ):
            recognition = recognise(spelling)
            assert recognition.rule != "competitive_inhibition", spelling
            assert recognition.rule == "noncompetitive_inhibition", spelling
        # An unconditional assertion outside the loop, so an empty or
        # renamed spelling list cannot make this pass by iterating nothing.
        assert recognise("noncompetitive inhibition").rule == "noncompetitive_inhibition"

    def test_competitive_inhibition_still_builds_competitive_inhibition(self) -> None:
        # The boundary bites in both directions or it is not a boundary: a
        # narrowing that fixed the uncompetitive case by breaking this one
        # would have traded a wrong model for a different wrong model.
        assert recognise("competitive inhibition").rule == "competitive_inhibition"
        assert recognise(
            "competitive inhibition of an enzyme by a substrate analogue"
        ).rule == "competitive_inhibition"

    def test_the_four_inhibition_words_reach_four_different_models(self) -> None:
        """Stated as a set, because pairwise checks miss a two-way swap.

        Four phrases, four distinct rate laws. If any two collapsed onto one
        model the set shrinks and this fails, whichever direction the
        collapse went.
        """
        built = {
            recognise(query).rule
            for query in (
                "competitive inhibition of an enzyme",
                "uncompetitive inhibition of an enzyme",
                "noncompetitive inhibition of an enzyme",
                "mixed inhibition of an enzyme",
            )
        }
        assert built == {
            "competitive_inhibition", "uncompetitive_inhibition",
            "noncompetitive_inhibition", "mixed_inhibition",
        }

    def test_competing_enzymes_still_build_the_competition_model(self) -> None:
        """The original defect, in the direction it originally went.

        "Competing" is about two enzymes drawing on one substrate pool and
        has nothing to do with a competitive inhibitor. The prefix that
        confused them was removed once; this is what keeps it removed.
        """
        for query in (
            "two enzymes competing for the same substrate",
            "competition between two enzymes for a substrate",
        ):
            recognition = recognise(query)
            assert recognition.rule == "enzyme_competition", query
        assert "inhibition" not in recognise(
            "two enzymes competing for the same substrate"
        ).rule

    def test_no_inhibition_query_is_a_candidate_for_the_competition_rule(self) -> None:
        # One level below the built model: the competition rule must not
        # even be IN THE RUNNING for these. It outranks inhibition, so if it
        # ever became a candidate again the wrong model would follow
        # immediately.
        for query in (
            "competitive inhibition of an enzyme",
            "uncompetitive inhibition of an enzyme",
            "noncompetitive inhibition of an enzyme",
        ):
            names = {rule.name for rule in _candidates(query)}
            assert "competition" not in names, query
            assert "competition_noun" not in names, query
        assert _winning_rule("uncompetitive inhibition of an enzyme") == "inhibition"


class TestTheNewTriggersTookNothing:
    """Six rules were added above the middle of the table. Anything they
    outrank could have been swallowed silently."""

    def test_every_query_the_suite_already_relied_on_wins_the_same_rule(self) -> None:
        moved = [
            (query, expected, _winning_rule(query))
            for query, expected in UNCHANGED.items()
            if _winning_rule(query) != expected
        ]
        assert moved == []

    def test_the_catalogue_s_own_domains_still_match_nothing(self) -> None:
        # Stated separately from the table above because it is a different
        # claim: not "the same rule wins" but "no rule may win at all". A
        # composer that answered "SIR model of a measles outbreak" by
        # assembling reaction motifs would be inventing epidemiology out of
        # chemistry.
        for query in (
            "SIR model of a measles outbreak in a school",
            "genetic drift in a small population",
            "predator prey population cycles",
            "PCR amplification over 30 cycles",
            "cell cycle oscillator dynamics",
        ):
            assert _candidates(query) == [], query
        assert _candidates("cell cycle oscillator dynamics") == []

    def test_a_bare_cycle_does_not_reach_the_futile_cycle_rule(self) -> None:
        # "futile cycle" and "substrate cycle", never "cycle": the catalogue
        # owns the cell cycle, and "a phosphorylation cycle" is a different
        # motif again.
        assert _winning_rule("cell cycle oscillator dynamics") is None
        assert _winning_rule("a futile cycle") == "futile_cycle"

    def test_a_bare_receptor_does_not_reach_the_internalisation_rule(self) -> None:
        # `binding` and `inhibition` both own queries containing "receptor",
        # and internalisation outranks both.
        assert _winning_rule("reversible binding of a ligand to a receptor") == "binding"
        assert _winning_rule("an allosteric inhibitor binding to a receptor") == "inhibition"
        assert _winning_rule("receptor mediated endocytosis") == "receptor_internalisation"

    def test_a_bare_channel_does_not_reach_the_channelling_rule(self) -> None:
        # "channel" is a prefix of "channelling" and an ion channel is a
        # different mechanism entirely, so the trigger is the longer word.
        assert _winning_rule("a potassium channel in the membrane") != "substrate_channeling"
        assert _winning_rule("substrate channelling between two enzymes") == "substrate_channeling"

    def test_expression_did_not_take_constitutive_expression(self) -> None:
        # `turnover` owns "constitutive expression" and builds the lumped
        # one-stage model. The gene rule triggers on "gene expression", not
        # on "expression", precisely so this still holds.
        assert _winning_rule("constitutive expression of a protein") == "turnover"
        assert _winning_rule("two stage gene expression") == "gene_expression"

    def test_autoregulation_did_not_take_the_repressor_queries(self) -> None:
        # None of its triggers is a bare "repress": "repressilator" and "two
        # repressors" both contain it.
        assert _winning_rule("repressilator oscillations") == "repressilator"
        assert _winning_rule("a toggle switch between two repressors") == "toggle_switch"
        assert _winning_rule("a negatively autoregulated gene") == "autoregulated_gene"


class TestTheRuleTableAfterTheAdditions:
    def test_priorities_are_unique(self) -> None:
        # Two rules on one priority means `max` breaks the tie by list
        # order, which is the invisible decision ADR 0170 describes.
        priorities = [rule.priority for rule in RULES]
        assert len(set(priorities)) == len(priorities), priorities

    def test_priorities_are_strictly_descending_in_list_order(self) -> None:
        priorities = [rule.priority for rule in RULES]
        assert priorities == sorted(priorities, reverse=True), priorities

    def test_rule_names_are_unique(self) -> None:
        # `shapes()` is one line per rule and a refusal prints it. Two rules
        # sharing a name would print one line for two behaviours.
        names = [rule.name for rule in RULES]
        assert len(set(names)) == len(names), names
        assert len(shapes()) == len(RULES)

    def test_every_rule_still_describes_itself(self) -> None:
        undescribed = [rule.name for rule in RULES if not rule.describes]
        assert undescribed == []

    def test_the_new_rules_slot_between_the_old_ones(self) -> None:
        # The additions were given free priorities rather than renumbering
        # the table, so every pre-existing rule keeps the rank it had. Those
        # ranks were argued for one at a time and re-deriving them was not
        # part of this change.
        by_name = {rule.name: rule.priority for rule in RULES}
        assert by_name["phosphorylation_cascade"] == 90
        assert by_name["competition"] == 84
        assert by_name["inhibition"] == 70
        assert by_name["binding"] == 60
        # And the new ones sit where the collisions need them to.
        assert by_name["autoregulated_gene"] > by_name["gene_expression"]
        assert by_name["receptor_internalisation"] > by_name["binding"]
        assert by_name["mwc_allostery"] > by_name["allosteric"]
        assert by_name["mwc_allostery"] > by_name["cooperative_enzyme"]


class TestRefusalsThatAreNotAboutAMissingFile:
    """Two places the grammar declines to choose for the reader."""

    def test_cotransport_without_a_direction_is_refused(self) -> None:
        """Symport and antiport are both cotransport.

        They differ in the sign of one stoichiometric coefficient and
        therefore in which way the driven solute moves. Defaulting to either
        would decide the answer, so this refuses with the distinction spelled
        out -- the same treatment an unqualified two-substrate query gets.
        """
        with pytest.raises(UnrecognisedShape) as caught:
            recognise("cotransport of sodium and glucose")
        message = str(caught.value)
        assert "symport" in message.lower()
        assert "antiport" in message.lower()
        # And it must not be the missing-file refusal wearing a different
        # hat: this one is about the query, not about the checkout.
        assert not isinstance(caught.value, MissingMotifLibrary)

    def test_naming_both_signs_of_autoregulation_is_refused(self) -> None:
        # Negative autoregulation speeds the approach to steady state and
        # positive slows it. There is no reading that covers both.
        with pytest.raises(UnrecognisedShape, match="opposite models"):
            recognise("a gene with both positive and negative autoregulation")

    def test_a_named_pathway_is_still_refused_before_any_rule_runs(self) -> None:
        # The pathway check happens ahead of rule matching, and the new
        # triggers must not have created a way past it. "Transcription" and
        # "pump" are both in a query somebody could write about glycolysis.
        for query in (
            "glycolysis in yeast",
            "transcription of the glycolysis genes",
            "the proton pump of oxidative phosphorylation",
        ):
            with pytest.raises(UnrecognisedShape, match="named pathway"):
                recognise(query)
        assert "glycolysis" in str(
            pytest.raises(UnrecognisedShape, recognise, "glycolysis in yeast").value
        )


class TestTheModelsThatDoBuild:
    """Structure, for everything reachable in THIS checkout.

    Not skipped when an expansion library is absent: the list shrinks to the
    nine shapes the core library serves and every assertion still runs. A
    skip would make the file report green on a checkout where it had checked
    nothing about a built model.
    """

    @staticmethod
    def _reachable():
        return [
            (query, expected)
            for query, _, expected, module in NEW_SHAPES
            if module is None or module in AVAILABLE
        ]

    def test_every_reachable_model_is_a_valid_network(self) -> None:
        problems = []
        for query, _ in self._reachable():
            network = recognise(query).network()
            if network.problems():
                problems.append((query, network.problems()))
            if not network.reactions:
                problems.append((query, "no reactions"))
        assert problems == []
        # The core library alone guarantees this list is never empty, so the
        # loop above cannot pass by iterating nothing.
        assert len(self._reachable()) >= 9

    def test_no_reachable_model_reintroduces_a_lumped_vmax(self) -> None:
        """ADR 0013, applied to the new libraries.

        Vmax is kcat x [E]0 and [E]0 is the caller's, so a lumped Vmax can
        never be resolved from any paper. The whole point of writing the
        mechanism out is that the quantity needing refusal stops existing --
        a new library reintroducing one would undo that quietly, since the
        model still runs.
        """
        offenders = []
        for query, _ in self._reachable():
            for instance in recognise(query).composition.instances:
                for parameter in instance.motif.parameters:
                    if "vmax" in parameter.name.lower():
                        offenders.append((query, instance.motif.name, parameter.name))
        assert offenders == []

    def test_every_reachable_model_balances_dimensionally(self) -> None:
        # A rate law with the wrong units integrates perfectly well and is
        # wrong by whatever factor the mistake introduced. There is no later
        # point at which that becomes visible.
        findings = []
        for query, _ in self._reachable():
            produced = recognise(query).composition.unit_findings()
            if produced:
                findings.append((query, [str(f) for f in produced]))
        assert findings == []

    def test_every_reachable_model_says_how_it_was_composed(self) -> None:
        # A model whose shape nobody can explain is not better than no
        # model. Every rule leaves at least one note, and the report prints
        # them.
        silent = [
            query for query, _ in self._reachable()
            if not recognise(query).composition.notes
        ]
        assert silent == []

    def test_every_reachable_motif_states_what_licenses_it(self) -> None:
        # The convention the core library holds to: a motif carries the
        # assumption behind it. A new library dropping it would make the
        # composed model unable to explain its own shape.
        unbased = []
        for query, _ in self._reachable():
            for instance in recognise(query).composition.instances:
                if not instance.motif.basis:
                    unbased.append((query, instance.motif.name))
        assert unbased == []

    def test_no_reachable_model_sends_a_scout_after_a_hill_coefficient(self) -> None:
        """The kind rule, at the place a new library is most likely to slip.

        `quantities_to_resolve()` filters by kind, so asserting that it
        returns only resolvable kinds proves nothing -- it is the filter's
        own definition. The claim worth checking is upstream: that the
        cooperativity exponent was DECLARED an exponent. Written as
        `MotifParameter("n", KIND_AFFINITY, ...)` it would pass every
        structural check in `motifs.py` and quietly join the list of things
        a scout goes looking for, and no paper reports a Hill coefficient
        for your construct -- it is a modelling choice with a conventional
        value.

        Matched by NAME, which is normally the wrong way to decide anything
        here. It is defensible in this one place because `n` and `h` are
        this library's own convention for the Hill exponent, used by eight
        motifs across three files, and the alternative is not checking at
        all.
        """
        misdeclared = []
        for query, _ in self._reachable():
            for instance in recognise(query).composition.instances:
                for parameter in instance.motif.parameters:
                    if parameter.name in {"n", "h"} and parameter.resolvable:
                        misdeclared.append(
                            (query, instance.motif.name, parameter.name,
                             parameter.kind)
                        )
        assert misdeclared == []

    def test_the_exponents_that_do_appear_are_dimensionless_and_chosen(self) -> None:
        """The positive control for the test above.

        That one passes trivially if nothing reachable has an exponent at
        all, and on a checkout with no expansion library nothing does. So
        the control is a CORE shape -- sigmoidal kinetics, always
        buildable -- and the sweep is over whatever else this checkout can
        reach.
        """
        control = [
            parameter
            for instance in recognise("sigmoidal enzyme kinetics").composition.instances
            for parameter in instance.motif.parameters
            if parameter.name in {"n", "h"}
        ]
        assert len(control) == 1
        assert not control[0].resolvable
        assert control[0].unit == "dimensionless"

        units = {
            parameter.unit
            for query, _ in self._reachable()
            for instance in recognise(query).composition.instances
            for parameter in instance.motif.parameters
            if parameter.name in {"n", "h"}
        }
        assert units <= {"dimensionless"}, units


class TestTheRefusalsAreActionable:
    """What a missing library must say, checked without needing one to be
    missing."""

    def test_a_missing_library_refusal_names_the_file_and_the_motif(self) -> None:
        """Constructed directly, so this holds on every checkout.

        The interesting property of `MissingMotifLibrary` is its message,
        and a test that could only run where a library happened to be absent
        would check it on nobody's machine once all three are written.
        """
        refusal = MissingMotifLibrary(
            "sodium glucose symport", "library_transport", "SYMPORT",
            "symport", instead="'facilitated diffusion' builds a carrier.",
        )
        message = str(refusal)
        assert "caterva/compose/library_transport.py" in message
        assert "SYMPORT" in message
        assert "facilitated diffusion" in message
        assert refusal.module == "library_transport"
        # It is a refusal like any other, so every caller that already
        # handles one keeps working.
        assert isinstance(refusal, UnrecognisedShape)

    def test_a_present_library_with_a_drifted_name_says_so_instead(self) -> None:
        # Different fix: a rename to chase, not a file to add. Flattening
        # the two would send somebody looking for a file that is already
        # there.
        absent = MissingMotifLibrary(
            "x", "library_transport", "SYMPORT", "symport",
        )
        drifted = MissingMotifLibrary(
            "x", "library_transport", "SYMPORT", "symport", module_present=True,
        )
        assert "is not in this checkout" in str(absent)
        assert "is not in this checkout" not in str(drifted)
        assert "name has drifted" in str(drifted)

    def test_no_refusal_offers_to_build_something_adjacent(self) -> None:
        # The failure this whole module exists to avoid: a near-miss
        # mechanism that simulates perfectly and answers a different
        # question. The message says what IS reachable and lets the reader
        # choose; it never substitutes.
        refusal = MissingMotifLibrary(
            "x", "library_transport", "SYMPORT", "symport",
        )
        assert "Nothing adjacent was substituted" in str(refusal)

    def test_every_expansion_library_is_described_for_the_refusal(self) -> None:
        # The description is what a refusal prints after the filename, and a
        # blank one turns an actionable message into a path.
        undescribed = [
            module for module, holds in EXPANSION_LIBRARIES.items() if not holds
        ]
        assert undescribed == []
        assert EXPANSION_LIBRARIES

    def test_every_registered_library_has_a_query_that_reaches_it(self) -> None:
        """The invariant this whole file is named after, as one assertion.

        Registering a library in `EXPANSION_LIBRARIES` without a rule and a
        phrase that gets to it produces a capability nobody can reach --
        which is the thing this work existed to stop, and which is invisible
        from inside `grammar.py` because the rule table looks complete
        either way. Adding a library here means adding a row to
        `NEW_SHAPES`, and this is what says so.
        """
        reached = {module for _, _, _, module in NEW_SHAPES if module is not None}
        assert set(EXPANSION_LIBRARIES) - reached == set()
        # And the reverse, so a typo in a NEW_SHAPES module name shows up as
        # a failure here rather than as a build-or-refuse test that can
        # never take its refusal branch.
        assert reached - set(EXPANSION_LIBRARIES) == set()
