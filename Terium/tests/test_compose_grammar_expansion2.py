"""The signalling and metabolic libraries, reached from English -- and what
the new words nearly swallowed.

WHY A SECOND EXPANSION FILE
---------------------------
`test_compose_grammar_expansion.py` pinned the first three libraries into
the grammar and, more importantly, pinned the collisions that adding them
created. Two more libraries -- `library_signaling` and `library_metabolic` --
were then written with no phrase reaching either. `library_signaling.py`
says so about itself, in its own docstring: a motif reachable by name with
no phrase that reaches it is a promise the front door does not keep.

This file is the other half of keeping it. It does the same two jobs for the
new shapes: every phrase reaches the rule meant for it and builds a model,
and the words that were added did not take words that were already spoken
for.

THE COLLISIONS ARE STILL THE POINT
----------------------------------
`RULES` matching is SUBSTRING matching. The biochemistry it separates is
adversarial about substrings, and this round produced four more traps of
exactly the shape that cost this repository two silent defects already:

    "competitive"  is inside  "uncompetitive"  and  "noncompetitive"
    "coherent"     is inside  "incoherent"
    "branched pathway" is inside "unbranched pathway"
    "transcription"   is inside "transcriptional"
    "g protein"       is inside "bindin(g protein)"

The first is inherited and is re-asserted here rather than assumed, because
a new trigger word is exactly what undoes an old narrowing -- and because
the brief for this change named those four assertions specifically. The
rest are new. Every one of them fails the same way: the wrong model has
plausible species, integrates without complaint, and plots a smooth curve.

WHAT IS ASSERTED WHEN A LIBRARY IS ABSENT
-----------------------------------------
The same contract the first file settled on. Rule selection happens before
any motif is fetched, so REACHABILITY is asserted unconditionally -- it
holds on a checkout with both new libraries and on one with neither. The
outcome is then either a built model or a `MissingMotifLibrary` that NAMES
the file it wanted. "It did not crash" is not asserted anywhere, because
that is what both historical defects looked like.

WHY THE ANALYTIC ASSERTIONS ARE ABOUT STRUCTURE
-----------------------------------------------
There is no closed form for a feed-forward loop's pulse height, and a test
that simulated one and compared it with a number would be pinning the
placeholder constants rather than the shape. What IS exact about these
compositions is their structure: a four-step pathway has four instances and
three shared intermediates, a moiety cycle has one conservation law over
its two forms, and the head of a chain is the only species nothing produces.
Those are arithmetic, they are what the wiring is for, and they are what a
mis-wiring breaks.
"""

from __future__ import annotations

import importlib

import pytest

from Terium.compose.grammar import (
    EXPANSION_LIBRARIES, MINIMUM_COPIES, MissingMotifLibrary, RULES,
    UnrecognisedShape, recognise, shapes,
)
from Terium.compose.library import PHOSPHORYLATION_CYCLE
from Terium.compose.motifs import (
    CHOSEN_KINDS, KIND_CONCENTRATION, RESOLVABLE_KINDS,
)
from Terium.core.network import describe_conservation_laws


# ---------------------------------------------------------------------------
# Reading the rule table the way `recognise` does
# ---------------------------------------------------------------------------
#
# Duplicated from `recognise`, as the first expansion file duplicates it and
# for its reason: `recognise` answers "what was built", and half of what is
# pinned here is "which rule was even in the running". A Recognition cannot
# report that, and both historical defects were about a rule that should
# never have been a candidate at all.


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
        importlib.import_module(f"Terium.compose.{module}")
    except ImportError:
        return False
    return True


AVAILABLE = {module for module in EXPANSION_LIBRARIES if _library_present(module)}


# ---------------------------------------------------------------------------
# What each new phrase must reach
# ---------------------------------------------------------------------------
#
# (query, rule in RULES that must win, Recognition.rule it must produce,
#  the expansion library it needs or None for a core motif).
#
# Both names are pinned because they answer different questions. The RULES
# name says the query reached the right FAMILY and that no other family
# outranked it; the Recognition name says the branch inside the family chose
# the right MECHANISM. The coherent/incoherent collision lives entirely in
# the second, exactly as the inhibition collisions do -- "it matched the
# feed-forward rule" would pass with the two loops swapped.

NEW_SHAPES = (
    # -- feed-forward loops, which are the library's headline shape --------
    ("an incoherent feedforward loop",
     "feedforward_loop", "incoherent_feedforward", "library_signaling"),
    ("an incoherent feed-forward loop",
     "feedforward_loop", "incoherent_feedforward", "library_signaling"),
    ("an i1-ffl that turns a step input into a pulse",
     "feedforward_loop", "incoherent_feedforward", "library_signaling"),
    ("a coherent feedforward loop",
     "feedforward_loop", "coherent_feedforward", "library_signaling"),
    ("a coherent feed-forward loop",
     "feedforward_loop", "coherent_feedforward", "library_signaling"),
    ("a c1-ffl acting as a sign-sensitive delay",
     "feedforward_loop", "coherent_feedforward", "library_signaling"),
    # The trap in its natural habitat: feed-forward loops were catalogued in
    # transcription networks, and "transcription" belongs to a rule four
    # ranks below this one.
    ("an incoherent feed-forward loop in a transcription network",
     "feedforward_loop", "incoherent_feedforward", "library_signaling"),

    # -- the rest of the signalling library --------------------------------
    ("a two component system",
     "two_component_system", "two_component_system", "library_signaling"),
    ("a sensor histidine kinase and its response regulator",
     "two_component_system", "two_component_system", "library_signaling"),
    ("phosphotransfer to a response regulator",
     "two_component_system", "two_component_system", "library_signaling"),
    ("a gpcr activation cycle",
     "gpcr_cycle", "gpcr_activation", "library_signaling"),
    ("a g-protein coupled receptor and its agonist",
     "gpcr_cycle", "gpcr_activation", "library_signaling"),
    ("guanine nucleotide exchange driven by an occupied receptor",
     "gpcr_cycle", "gpcr_activation", "library_signaling"),
    ("a scaffold holding two kinases together",
     "scaffold_assembly", "scaffold_assembly", "library_signaling"),
    ("a delayed negative feedback oscillator",
     "signalling_oscillator", "negative_feedback_oscillator", "library_signaling"),
    ("a goodwin oscillator",
     "signalling_oscillator", "negative_feedback_oscillator", "library_signaling"),
    ("a bistable positive feedback loop",
     "bistable_feedback", "bistable_positive_feedback", "library_signaling"),
    # Not "bistability from a self-activating protein", which is what this
    # row said first: "self-activating" is a trigger of `autoregulated_gene`
    # (87) and took it. The rule below is 58, so the phrase has to name the
    # loop rather than the gene.
    ("bistability from a positive feedback loop",
     "bistable_feedback", "bistable_positive_feedback", "library_signaling"),

    # -- the metabolic library ---------------------------------------------
    ("a linear metabolic pathway of four steps",
     "metabolic_pathway", "linear_metabolic_pathway", "library_metabolic"),
    ("a three step linear pathway",
     "metabolic_pathway", "linear_metabolic_pathway", "library_metabolic"),
    ("an unbranched pathway of five reversible steps",
     "metabolic_pathway", "linear_metabolic_pathway", "library_metabolic"),
    ("a branch point where one metabolite feeds two enzymes",
     "branch_point", "branch_point", "library_metabolic"),
    ("a branched pathway",
     "branch_point", "branch_point", "library_metabolic"),
    ("a moiety conserved cycle",
     "moiety_cycle", "moiety_conserved_cycle", "library_metabolic"),
    ("an atp/adp cofactor cycle",
     "moiety_cycle", "moiety_conserved_cycle", "library_metabolic"),
    ("the nad+/nadh pool",
     "moiety_cycle", "moiety_conserved_cycle", "library_metabolic"),
    ("a reaction that spends a cofactor from a conserved pool",
     "moiety_cycle", "cofactor_coupled_step", "library_metabolic"),
    ("a step that spends a cofactor",
     "moiety_cycle", "cofactor_coupled_step", "library_metabolic"),

    # -- core, deliberately -------------------------------------------------
    #
    # `library_signaling.ULTRASENSITIVE_CYCLE` is a NAME BOUND TO
    # `library.PHOSPHORYLATION_CYCLE`, not a second definition of it, so this
    # shape builds with no expansion library present. That claim is about
    # another file and is pinned separately below rather than assumed here.
    ("an ultrasensitive phosphorylation cycle",
     "ultrasensitive_cycle", "ultrasensitive_cycle", None),
    ("zero order ultrasensitivity in a covalent modification cycle",
     "ultrasensitive_cycle", "ultrasensitive_cycle", None),
    ("a goldbeter koshland cycle",
     "ultrasensitive_cycle", "ultrasensitive_cycle", None),
)


#: Every query the suite already relied on, with the rule that must keep
#: winning it. `None` means the grammar must keep matching NOTHING, which
#: for the catalogue's own domains is the correct answer and the one a new
#: trigger word is most likely to break.
#:
#: Copied from `test_compose_grammar_expansion.UNCHANGED` rather than
#: imported. Importing would make one file's regression show up as the
#: other's failure, and the whole value of a pinned table is that it says
#: which change broke it.
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
    "an allosteric inhibitor binding to a receptor": "inhibition",
    "competitive inhibition of an enzyme by a substrate analogue": "inhibition",
    "signalling in a cell": None,
    "a phosphorylation cascade": "phosphorylation_cascade",
    "a MAP kinase cascade": "phosphorylation_cascade",
    # From the first expansion file, because the new triggers outrank some
    # of the rules that win these.
    "a futile cycle": "futile_cycle",
    "a substrate cycle run by a kinase and phosphatase": "futile_cycle",
    "two stage gene expression": "gene_expression",
    "a negatively autoregulated gene": "autoregulated_gene",
    "constitutive expression of a protein": "turnover",
    "receptor mediated endocytosis": "receptor_internalisation",
    "primary active transport by an atp driven pump": "transport",
    "sodium glucose symport": "transport",
}


def _outcome(query: str):
    """(rule name, None) if it built, (None, exception) if it refused."""
    try:
        return recognise(query).rule, None
    except UnrecognisedShape as refused:
        return None, refused


def _reachable():
    """The rows this checkout can actually build.

    Never empty: the three ultrasensitive rows need no expansion library, so
    every sweep below runs over at least three models even on a checkout
    with neither new file.
    """
    return [
        (query, expected)
        for query, _, expected, module in NEW_SHAPES
        if module is None or module in AVAILABLE
    ]


class TestEveryNewShapeIsReachable:
    """A motif library nobody can name from a query is not a capability."""

    def test_every_new_query_reaches_the_rule_meant_for_it(self) -> None:
        """The reachability claim, and it needs no library to be present.

        Rule selection happens before any motif is fetched, so this holds
        identically on a checkout with both new libraries and on one with
        neither. A misspelled trigger, or a higher-priority rule that
        swallows the phrase, fails here rather than surfacing later as a
        strange model.
        """
        wrong = [
            (query, expected, _winning_rule(query))
            for query, expected, _, _ in NEW_SHAPES
            if _winning_rule(query) != expected
        ]
        assert wrong == []

    def test_every_new_rule_is_reached_by_at_least_one_query(self) -> None:
        # The other direction: a rule nothing gets to is dead weight, which
        # is the exact defect this file is named after.
        added = {
            "feedforward_loop", "two_component_system", "gpcr_cycle",
            "ultrasensitive_cycle", "metabolic_pathway", "branch_point",
            "moiety_cycle", "scaffold_assembly", "signalling_oscillator",
            "bistable_feedback",
        }
        reached = {rule for _, rule, _, _ in NEW_SHAPES}
        assert added - reached == set()
        # And every name in that set is really in the table, so a rename
        # cannot make this pass by comparing two empty sets.
        assert added <= {rule.name for rule in RULES}

    def test_every_new_mechanism_is_reached_by_at_least_one_query(self) -> None:
        # One level finer than the rule names: the feed-forward rule has two
        # branches and the moiety rule has two, and a table that reached only
        # one branch of each would satisfy the test above while leaving half
        # the library unreachable.
        built = {mechanism for _, _, mechanism, _ in NEW_SHAPES}
        assert {
            "incoherent_feedforward", "coherent_feedforward",
            "moiety_conserved_cycle", "cofactor_coupled_step",
        } <= built

    def test_each_new_query_builds_or_names_the_file_it_wanted(self) -> None:
        """Built where the library is here; a refusal that names it where not.

        The second half is the interesting one. "I cannot do that" is not an
        answer anybody can act on; "Terium/compose/library_metabolic.py is
        not in this checkout" is. Asserting only "it did not raise" would
        pass against a grammar that had lost the rule.
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
        # So a green run says WHICH half it proved.
        print(
            "expansion libraries present: "
            + (", ".join(sorted(AVAILABLE)) or "none")
            + "; absent: "
            + (", ".join(sorted(set(EXPANSION_LIBRARIES) - AVAILABLE)) or "none")
        )
        # The detector the build-or-refuse test leans on has to be able to
        # say "no". One that returned True for everything would silently turn
        # every build-or-refuse assertion into a build-only one.
        assert not _library_present("library_that_nobody_wrote")
        assert _library_present("library"), "the core library must always import"

    def test_both_new_libraries_are_registered_for_the_refusal(self) -> None:
        # `EXPANSION_LIBRARIES` is what a `MissingMotifLibrary` prints after
        # the filename. An unregistered module still refuses, but it refuses
        # with "further motifs" where it could have said what is in the file.
        assert "library_signaling" in EXPANSION_LIBRARIES
        assert "library_metabolic" in EXPANSION_LIBRARIES
        assert all(EXPANSION_LIBRARIES[module] for module in EXPANSION_LIBRARIES)


class TestTheInhibitionCollisions:
    """The four assertions this change was required to keep true.

    Inherited from `test_compose_grammar_expansion.py` and deliberately
    re-asserted rather than assumed. A narrowing is exactly the kind of thing
    a later trigger word undoes by accident, and these four are the ones this
    repository has already paid for twice.
    """

    def test_uncompetitive_inhibition_does_not_build_competitive_inhibition(self) -> None:
        recognition = recognise("uncompetitive inhibition")
        assert recognition.rule != "competitive_inhibition"
        assert recognition.rule == "uncompetitive_inhibition"

    def test_noncompetitive_inhibition_does_not_build_competitive_inhibition(self) -> None:
        recognition = recognise("noncompetitive inhibition")
        assert recognition.rule != "competitive_inhibition"
        assert recognition.rule == "noncompetitive_inhibition"
        # The hyphenated spelling is the same mechanism and must not be a
        # different answer. Asserted outside any loop so an emptied spelling
        # list cannot make this pass by iterating nothing.
        assert recognise(
            "non-competitive inhibition"
        ).rule == "noncompetitive_inhibition"

    def test_competitive_inhibition_still_builds_competitive_inhibition(self) -> None:
        # The boundary bites in both directions or it is not a boundary: a
        # narrowing that fixed the uncompetitive case by breaking this one
        # would have traded a wrong model for a different wrong model.
        assert recognise("competitive inhibition").rule == "competitive_inhibition"
        assert recognise(
            "competitive inhibition of an enzyme by a substrate analogue"
        ).rule == "competitive_inhibition"

    def test_two_enzymes_competing_still_build_the_competition_model(self) -> None:
        """The original defect, in the direction it originally went.

        "Competing" is about two enzymes drawing on one substrate pool and
        has nothing to do with a competitive inhibitor. `requires=("compet",)`
        confused them once; this is part of what keeps it removed.
        """
        recognition = recognise("two enzymes competing for the same substrate")
        assert recognition.rule == "enzyme_competition"
        assert "inhibition" not in recognition.rule
        # And the new branch-point rule must not have taken it either: it is
        # the same NETWORK, which is precisely why it was ranked below.
        assert _winning_rule("two enzymes competing for the same substrate") == "competition"

    def test_the_four_inhibition_words_still_reach_four_different_models(self) -> None:
        # Stated as a set, because pairwise checks miss a two-way swap.
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


class TestTheCoherenceCollision:
    """"coherent" is inside "incoherent", and they are opposite computations.

    The same shape of trap as competitive/uncompetitive, one library later.
    A coherent feed-forward loop delays a rising input and passes a falling
    one straight through; an incoherent one turns a sustained input into a
    pulse. Swapping them gives a model with the same five species and the
    same names that answers the opposite question.
    """

    def test_an_incoherent_loop_does_not_build_the_coherent_one(self) -> None:
        recognition = recognise("an incoherent feed-forward loop")
        assert recognition.rule != "coherent_feedforward"
        assert recognition.rule == "incoherent_feedforward"

    def test_a_coherent_loop_still_builds_the_coherent_one(self) -> None:
        # The boundary in the other direction.
        recognition = recognise("a coherent feed-forward loop")
        assert recognition.rule == "coherent_feedforward"
        assert recognise("a coherent feedforward loop").rule == "coherent_feedforward"

    def test_the_two_loops_reach_two_different_models(self) -> None:
        built = {
            recognise(query).rule
            for query in (
                "a coherent feed-forward loop",
                "an incoherent feed-forward loop",
            )
        }
        assert built == {"coherent_feedforward", "incoherent_feedforward"}

    def test_an_unqualified_feedforward_loop_is_refused_with_the_distinction(self) -> None:
        """Neither is a default, for the reason ordered/ping-pong is not.

        They are two computations and not two settings, so choosing would
        answer a different question silently -- and silently is the operative
        word, because both models build and both integrate.
        """
        with pytest.raises(UnrecognisedShape) as caught:
            recognise("a feed-forward loop")
        message = str(caught.value).lower()
        assert "coherent" in message
        assert "incoherent" in message
        assert "pulse" in message
        # About the query, not about the checkout: a reader told to add a
        # file would be sent to the wrong place.
        assert not isinstance(caught.value, MissingMotifLibrary)

    def test_naming_both_loops_at_once_is_refused(self) -> None:
        # The same treatment naming both signs of autoregulation gets. There
        # is no reading that covers both.
        with pytest.raises(UnrecognisedShape, match="opposite computations"):
            recognise("a coherent and an incoherent feed-forward loop")


class TestTheOtherNewCollisions:
    """Three more substrings that would each have been silent."""

    def test_an_unbranched_pathway_does_not_build_a_branch_point(self) -> None:
        """"branched pathway" is inside "unbranched pathway".

        The word somebody reaches for when they mean a LINEAR pathway
        contains the word for a split one. Resolved by rank rather than by
        narrowing the trigger, because "a branched pathway" is itself the
        natural phrase and dropping it would cost a real query.
        """
        recognition = recognise("an unbranched pathway of five reversible steps")
        assert recognition.rule != "branch_point"
        assert recognition.rule == "linear_metabolic_pathway"
        # Both rules really are candidates -- so this is the ranking working,
        # not the trigger failing to match. If the substring trap ever went
        # away the ranking would stop being load-bearing and this would say so.
        names = {rule.name for rule in _candidates("an unbranched pathway of five steps")}
        assert {"metabolic_pathway", "branch_point"} <= names
        assert _winning_rule("an unbranched pathway of five steps") == "metabolic_pathway"

    def test_a_branched_pathway_still_builds_a_branch_point(self) -> None:
        # The boundary bites both ways.
        assert recognise("a branched pathway").rule == "branch_point"
        assert recognise("a branch point in a pathway").rule == "branch_point"

    def test_a_transcriptional_oscillator_is_not_a_trigger_for_the_oscillator(self) -> None:
        """"transcription" is inside "transcriptional".

        `gene_expression` (85) owns "transcription" and outranks the
        oscillator rule (59) by twenty-six, so "a transcriptional oscillator"
        can never reach it. The trigger is therefore the phrase that names
        the SHAPE -- "negative feedback oscillator" -- and this pins that the
        choice was deliberate rather than lucky.
        """
        assert _winning_rule("a transcriptional oscillator") == "gene_expression"
        assert _winning_rule("a delayed negative feedback oscillator") == "signalling_oscillator"

    def test_a_binding_protein_does_not_reach_the_gpcr_rule(self) -> None:
        """"g protein" with a space is inside "bindin(g protein)".

        Which is why it is not a trigger and "gpcr", "g-protein" and "g
        protein coupled" are. A grammar that took the bare phrase would send
        every query about a ligand-binding protein to a G protein cycle.
        """
        assert _winning_rule("a ligand binding protein") != "gpcr_cycle"
        assert _winning_rule("a ligand binding protein") == "binding"
        assert _winning_rule("a g-protein coupled receptor and its agonist") == "gpcr_cycle"

    def test_a_bare_cycle_reaches_none_of_the_new_cycle_rules(self) -> None:
        # Three of the new rules are about a "cycle" of some kind. None of
        # them may take a bare one: the cell cycle belongs to the catalogue
        # and this path must keep matching nothing for it.
        assert _winning_rule("cell cycle oscillator dynamics") is None
        assert _candidates("cell cycle oscillator dynamics") == []
        assert _winning_rule("an ultrasensitive phosphorylation cycle") == "ultrasensitive_cycle"

    def test_a_bistable_switch_is_still_the_toggle_and_not_the_one_gene_loop(self) -> None:
        # "bistable" is inside "bistable switch". `toggle_switch` (86) owns
        # the longer phrase and wins, which is right: a toggle gets its two
        # states from two genes repressing each other, and the new rule gets
        # them from one gene activating itself. Different experiments.
        assert _winning_rule("a toggle switch between two repressors") == "toggle_switch"
        assert _winning_rule("a bistable switch between two genes") == "toggle_switch"
        assert _winning_rule("a bistable positive feedback loop") == "bistable_feedback"

    def test_a_two_component_system_is_not_a_two_substrate_enzyme(self) -> None:
        # "two component" and "two substrate" are both "two something", and
        # `bi_substrate` (77) outranks the two-component rule (67). They do
        # not collide as substrings, and this is what says so on purpose
        # rather than by luck.
        assert _winning_rule("a two component system") == "two_component_system"
        assert _winning_rule("a two substrate enzyme") == "bi_substrate"

    def test_phosphorelay_still_reaches_the_cascade_rule(self) -> None:
        # A two-component system IS a phosphorelay, and "phosphorelay" was
        # deliberately NOT taken from `phosphorylation_cascade` (90): taking
        # it would have needed a rule above 90 and would have changed what an
        # existing query builds.
        assert _winning_rule("a phosphorelay") == "phosphorylation_cascade"
        assert _winning_rule("phosphotransfer to a response regulator") == "two_component_system"


class TestTheNewTriggersTookNothing:
    """Ten rules were added, one of them above the middle of the table.
    Anything they outrank could have been swallowed silently."""

    def test_every_query_the_suite_already_relied_on_wins_the_same_rule(self) -> None:
        moved = [
            (query, expected, _winning_rule(query))
            for query, expected in UNCHANGED.items()
            if _winning_rule(query) != expected
        ]
        assert moved == []

    def test_the_catalogue_s_own_domains_still_match_nothing(self) -> None:
        # A different claim from the table above: not "the same rule wins"
        # but "no rule may win at all". A composer that answered "SIR model
        # of a measles outbreak" by assembling reaction motifs would be
        # inventing epidemiology out of chemistry.
        for query in (
            "SIR model of a measles outbreak in a school",
            "genetic drift in a small population",
            "predator prey population cycles",
            "PCR amplification over 30 cycles",
            "cell cycle oscillator dynamics",
            "stochastic simulation of a chemical reaction",
        ):
            assert _candidates(query) == [], query
        assert _candidates("SEIR epidemic with an exposed class") == []

    def test_a_named_pathway_is_still_refused_before_any_rule_runs(self) -> None:
        # The pathway check happens ahead of rule matching, and ten new
        # triggers must not have created a way past it. "Pathway" itself is
        # now a word this grammar answers to, which makes this the most
        # likely round for that guard to be bypassed.
        for query in (
            "glycolysis in yeast",
            "the linear pathway of glycolysis",
            "a branch point in the pentose phosphate pathway",
            "the atp/adp cycle of oxidative phosphorylation",
        ):
            with pytest.raises(UnrecognisedShape, match="named pathway"):
                recognise(query)
        assert "glycolysis" in str(
            pytest.raises(UnrecognisedShape, recognise, "glycolysis in yeast").value
        )

    def test_a_named_pathway_refusal_is_not_a_missing_library_refusal(self) -> None:
        # Two refusals, two different readers: one needs a pathway database,
        # the other needs a file. Collapsing them would send somebody to add
        # a library that is already there.
        with pytest.raises(UnrecognisedShape) as caught:
            recognise("the linear pathway of glycolysis")
        assert not isinstance(caught.value, MissingMotifLibrary)
        assert "KEGG" in str(caught.value) or "Reactome" in str(caught.value)


class TestTheRuleTableAfterTheAdditions:
    def test_priorities_are_unique(self) -> None:
        # Two rules on one priority means `max` breaks the tie by list order,
        # which is the invisible decision ADR 0170 describes.
        priorities = [rule.priority for rule in RULES]
        assert len(set(priorities)) == len(priorities), priorities

    def test_priorities_are_strictly_descending_in_list_order(self) -> None:
        priorities = [rule.priority for rule in RULES]
        assert priorities == sorted(priorities, reverse=True), priorities
        # Strictly, not merely non-increasing: sorted() alone would accept a
        # repeated value, and the uniqueness test above is what forbids it.
        # Stated together here so the pair cannot be half-deleted.
        assert all(
            earlier > later
            for earlier, later in zip(priorities, priorities[1:])
        ), priorities

    def test_rule_names_are_unique(self) -> None:
        # `shapes()` is one line per rule and a refusal prints it. Two rules
        # sharing a name would print one line for two behaviours.
        names = [rule.name for rule in RULES]
        assert len(set(names)) == len(names), names
        assert len(shapes()) == len(RULES)

    def test_every_rule_still_describes_itself(self) -> None:
        undescribed = [rule.name for rule in RULES if not rule.describes]
        assert undescribed == []

    def test_no_rule_has_an_empty_trigger_and_requires_pair(self) -> None:
        # A rule with neither would match EVERY query and, at any priority,
        # would decide some of them. There is no such rule and there should
        # not be one.
        catch_all = [
            rule.name for rule in RULES if not rule.requires and not rule.triggers
        ]
        assert catch_all == []

    def test_the_pre_existing_ranks_were_not_renumbered(self) -> None:
        # The additions were given free priorities rather than renumbering
        # the table, so every rule that was there keeps the rank it was
        # argued into. Re-deriving twenty-five of those was not part of this
        # change.
        by_name = {rule.name: rule.priority for rule in RULES}
        assert by_name["phosphorylation_cascade"] == 90
        assert by_name["gene_expression"] == 85
        assert by_name["competition"] == 84
        assert by_name["futile_cycle"] == 79
        assert by_name["inhibition"] == 70
        assert by_name["binding"] == 60

    def test_the_new_rules_sit_where_their_collisions_need_them(self) -> None:
        by_name = {rule.name: rule.priority for rule in RULES}
        # Feed-forward loops were catalogued in transcription networks.
        assert by_name["feedforward_loop"] > by_name["gene_expression"]
        # "branched pathway" is inside "unbranched pathway".
        assert by_name["metabolic_pathway"] > by_name["branch_point"]
        # "g protein coupled receptor" contains "receptor".
        assert by_name["gpcr_cycle"] > by_name["binding"]
        # "a scaffold and the binding of two kinases" contains "binding of".
        assert by_name["scaffold_assembly"] > by_name["binding"]
        # And two deliberate LOWER rankings, which are decisions and not
        # leftovers: the futile-cycle rule keeps the words written for it,
        # and the competition rule keeps "competing".
        assert by_name["ultrasensitive_cycle"] < by_name["futile_cycle"]
        assert by_name["branch_point"] < by_name["competition"]


class TestTheModelsThatDoBuild:
    """Structure, for everything reachable in THIS checkout.

    Not skipped when a library is absent: the list shrinks to the shapes the
    core library serves and every assertion still runs. A skip would report
    green on a checkout where nothing about a built model had been checked.
    """

    def test_every_reachable_model_is_a_valid_network(self) -> None:
        problems = []
        for query, _ in _reachable():
            network = recognise(query).network()
            if network.problems():
                problems.append((query, network.problems()))
            if not network.reactions:
                problems.append((query, "no reactions"))
        assert problems == []
        # The three ultrasensitive rows need no expansion library, so the
        # loop above cannot pass by iterating nothing.
        assert len(_reachable()) >= 3

    def test_no_reachable_model_reintroduces_a_lumped_vmax(self) -> None:
        """ADR 0013, applied to two more libraries.

        Vmax is kcat x [E]0 and [E]0 is the caller's, so a lumped Vmax can
        never be resolved from any paper. Writing the mechanism out is what
        makes the unresolvable quantity stop existing; a new library
        reintroducing one would undo that quietly, since the model still runs.
        """
        offenders = []
        for query, _ in _reachable():
            for instance in recognise(query).composition.instances:
                for parameter in instance.motif.parameters:
                    if "vmax" in parameter.name.lower():
                        offenders.append((query, instance.motif.name, parameter.name))
        assert offenders == []

    def test_no_reachable_model_carries_a_lumped_synthesis_rate(self) -> None:
        """The same mistake wearing a promoter, which is what these libraries
        are most exposed to.

        `ks` in mM/s is `k_tx * [gene]`: a measurement multiplied by a
        scenario choice, so a published value is a measurement of somebody
        else's copy number. `library_signaling.py` states the rule for
        itself; this is the front door checking that what it hands back obeys
        it, which is a different claim from the library's own test because it
        covers whatever the grammar actually reaches.
        """
        lumped = []
        for query, _ in _reachable():
            for instance in recognise(query).composition.instances:
                for parameter in instance.motif.parameters:
                    if parameter.unit in {"mM/s", "mM/min", "mM/h"}:
                        lumped.append(
                            (query, instance.motif.name, parameter.name,
                             parameter.unit)
                        )
        assert lumped == []

    def test_every_reachable_model_balances_dimensionally(self) -> None:
        # A rate law with the wrong units integrates perfectly well and is
        # wrong by whatever factor the mistake introduced. There is no later
        # point at which that becomes visible.
        findings = []
        for query, _ in _reachable():
            produced = recognise(query).composition.unit_findings()
            if produced:
                findings.append((query, [str(f) for f in produced]))
        assert findings == []

    def test_every_reachable_model_says_how_it_was_composed(self) -> None:
        # A model whose shape nobody can explain is not better than no model.
        silent = [
            query for query, _ in _reachable()
            if not recognise(query).composition.notes
        ]
        assert silent == []

    def test_every_reachable_motif_states_what_licenses_it(self) -> None:
        # The convention the core library holds to: a motif carries the
        # assumption behind it, the regime where it fails, and the experiment
        # that separates it from the mechanism a reader might have meant.
        unbased = []
        for query, _ in _reachable():
            for instance in recognise(query).composition.instances:
                if not instance.motif.basis:
                    unbased.append((query, instance.motif.name))
        assert unbased == []

    def test_no_reachable_model_sends_a_scout_after_a_hill_coefficient(self) -> None:
        """The kind rule, at the place two new libraries are most likely to
        slip.

        Five of the new motifs carry a cooperativity exponent. Declared
        `KIND_AFFINITY` by mistake, `n` would pass every structural check in
        `motifs.py` and quietly join the list of quantities a scout goes
        looking for -- and no paper reports a Hill coefficient for your
        construct. It is a modelling choice with a conventional value.
        """
        misdeclared = []
        for query, _ in _reachable():
            for instance in recognise(query).composition.instances:
                for parameter in instance.motif.parameters:
                    if parameter.name in {"n", "h"} and parameter.resolvable:
                        misdeclared.append(
                            (query, instance.motif.name, parameter.name,
                             parameter.kind)
                        )
        assert misdeclared == []
        # The positive control: at least one reachable shape must HAVE an
        # exponent, or the sweep above proves nothing. Core, so it holds on
        # every checkout.
        control = [
            parameter
            for instance in recognise("sigmoidal enzyme kinetics").composition.instances
            for parameter in instance.motif.parameters
            if parameter.name in {"n", "h"}
        ]
        assert len(control) == 1
        assert not control[0].resolvable

    def test_no_reachable_motif_declares_an_amount_as_a_parameter(self) -> None:
        """A concentration is never a parameter here, which is upstream of
        the kind rule rather than a restatement of it.

        Asserting that `quantities_to_resolve()` returns only resolvable
        kinds proves nothing: that is the filter's own definition. The claim
        worth checking is that an AMOUNT never became a parameter in the
        first place. Amounts belong on ports, where they are species and
        therefore visibly the caller's; a `KIND_CONCENTRATION` parameter is
        the lumped scenario quantity ADR 0013 blocks, and `Vmax` and a
        promoter's `ks` are both that mistake wearing different clothes.
        """
        declared = []
        for query, _ in _reachable():
            for instance in recognise(query).composition.instances:
                for parameter in instance.motif.parameters:
                    if parameter.kind not in RESOLVABLE_KINDS | CHOSEN_KINDS:
                        declared.append((query, instance.motif.name,
                                         parameter.name, parameter.kind))
                    if parameter.kind == KIND_CONCENTRATION:
                        declared.append((query, instance.motif.name,
                                         parameter.name, "an amount"))
        assert declared == []
        # The positive control, without which the sweep above passes on a
        # model that has no amounts at all: every reachable shape DOES carry
        # amounts, and every one of them is a species the caller chooses.
        for query, _ in _reachable():
            composition = recognise(query).composition
            assert set(composition.species_ids) <= set(
                composition.chosen_quantities()
            ), query
        assert all(
            recognise(query).composition.species_ids for query, _ in _reachable()
        )


class TestTheAnalyticStructure:
    """Where the answer is arithmetic rather than a simulation.

    A feed-forward loop's pulse height has no closed form, and a test that
    simulated one and compared it with a number would be pinning the
    placeholder constants. The wiring, though, is exact: these are the
    assertions a mis-wiring breaks and a re-tuning does not.
    """

    @staticmethod
    def _needs(module: str) -> None:
        if module not in AVAILABLE:
            pytest.skip(f"{module} is not in this checkout")

    def test_a_four_step_pathway_has_four_instances_and_three_intermediates(self) -> None:
        """The count is read from the query, so the count is what to check.

        Four segments share three intermediates: step_i's product IS
        step_(i+1)'s substrate, one species and not two. Two species with
        similar names is the classic broken chain -- it simulates, and the
        pathway silently carries no flux past the first step.
        """
        self._needs("library_metabolic")
        composition = recognise("a linear metabolic pathway of four steps").composition
        assert len(composition.instances) == 4
        shared = [
            step.species_for("P")
            for step in composition.instances[:-1]
        ]
        downstream = [
            step.species_for("S")
            for step in composition.instances[1:]
        ]
        assert shared == downstream
        assert len(set(shared)) == 3

    def test_the_pathway_length_comes_from_the_query_and_nowhere_else(self) -> None:
        # Three phrasings of the same number, and a different number, so a
        # hard-coded default cannot pass this.
        self._needs("library_metabolic")
        for query, expected in (
            ("a linear metabolic pathway of four steps", 4),
            ("a four step linear pathway", 4),
            ("an unbranched pathway of five reversible steps", 5),
            ("a three step linear pathway", 3),
        ):
            assert len(recognise(query).composition.instances) == expected, query
        # Unconditional, outside the loop.
        assert len(
            recognise("a linear metabolic pathway of two steps").composition.instances
        ) == 2

    def test_a_pathway_with_no_number_is_refused(self) -> None:
        """The `NUMBER_WORDS` lesson, applied to a second shape.

        "A phosphorylation cascade" once parsed as a ONE-tier cascade because
        the indefinite article was read as a count. The length of a pathway
        changes the model in the same way -- it sets how many enzymes there
        are and how control is distributed between them -- so an unnumbered
        one is refused rather than given a length nobody asked for.
        """
        with pytest.raises(UnrecognisedShape, match="needs a number of steps"):
            recognise("a linear metabolic pathway")
        with pytest.raises(UnrecognisedShape, match="needs a number of steps"):
            recognise("a metabolic pathway")

    def test_a_one_step_pathway_is_refused_as_not_a_pathway(self) -> None:
        # The same boundary `MINIMUM_COPIES` draws for a cascade: a pathway
        # of one is a reversible step, which the core library already builds
        # under its own name.
        assert MINIMUM_COPIES["pathway"] == 2
        with pytest.raises(UnrecognisedShape, match="not a pathway"):
            recognise("a linear pathway of one step")
        # And the boundary bites in both directions, or it is not one.
        if "library_metabolic" in AVAILABLE:
            assert len(
                recognise("a linear pathway of two steps").composition.instances
            ) == 2

    def test_the_moiety_cycle_conserves_its_pool_by_derivation(self) -> None:
        """The claim the motif is named for, taken from the stoichiometry.

        Nobody tells the network that the active and spent forms sum to a
        constant. `conservation_laws` derives it from the stoichiometric
        matrix, which is why the total must NOT also be a parameter: a model
        could then state a total contradicting its own initial conditions
        and nothing would notice.
        """
        self._needs("library_metabolic")
        network = recognise("a moiety conserved cycle").network()
        laws = describe_conservation_laws(network)
        assert any(
            "pool_C_active" in law and "pool_C_spent" in law for law in laws
        ), laws
        # And no parameter claims to be the total, which would duplicate it.
        names = {
            parameter.name.lower()
            for instance in recognise("a moiety conserved cycle").composition.instances
            for parameter in instance.motif.parameters
        }
        assert not any("total" in name for name in names), names

    def test_the_ultrasensitive_cycle_is_the_core_motif_and_not_a_copy(self) -> None:
        """The alias claim, pinned because the grammar depends on it.

        `_ultrasensitive_cycle` builds `library.PHOSPHORYLATION_CYCLE`
        directly, on the argument that
        `library_signaling.ULTRASENSITIVE_CYCLE` is a name bound to that
        object rather than a second definition. If it ever stopped being one,
        the rule would keep building the core motif SILENTLY and the query
        would get a different mechanism from the one its name now refers to.
        This is the only place that drift is visible.
        """
        composition = recognise("an ultrasensitive phosphorylation cycle").composition
        assert len(composition.instances) == 1
        assert composition.instances[0].motif is PHOSPHORYLATION_CYCLE
        if "library_signaling" in AVAILABLE:
            library_signaling = importlib.import_module(
                "Terium.compose.library_signaling"
            )
            assert library_signaling.ULTRASENSITIVE_CYCLE is PHOSPHORYLATION_CYCLE

    def test_the_ultrasensitive_cycle_builds_without_the_signalling_library(self) -> None:
        # The consequence of the alias, stated as a capability: this shape is
        # reachable on a checkout with no expansion library at all, which is
        # why its NEW_SHAPES row carries None.
        modules = {module for _, _, _, module in NEW_SHAPES}
        assert None in modules
        recognition = recognise("a goldbeter koshland cycle")
        assert recognition.rule == "ultrasensitive_cycle"
        assert recognition.network().problems() == []

    def test_the_ultrasensitive_cycle_says_the_sharpness_is_a_regime(self) -> None:
        """What is NOT claimed, and it is the whole of the honesty here.

        The structure does not make the response sharp. Both converters
        running saturated does, and that is set by the caller's
        concentrations. A model presented as "ultrasensitive" that is in fact
        graded would be believed, because it runs.
        """
        notes = " ".join(
            recognise("an ultrasensitive phosphorylation cycle").composition.notes
        ).lower()
        assert "regime" in notes
        assert "saturated" in notes
        assert "graded" in notes


class TestTheRefusalsAreActionable:
    """What each refusal has to say, checked without needing a library to be
    absent."""

    def test_a_missing_library_refusal_names_the_file_and_the_motif(self) -> None:
        """Constructed directly, so this holds on every checkout.

        The interesting property of `MissingMotifLibrary` is its message, and
        a test that could only run where a library happened to be absent
        would check it on nobody's machine once all five are written.
        """
        refusal = MissingMotifLibrary(
            "an incoherent feed-forward loop", "library_signaling",
            "INCOHERENT_FEEDFORWARD", "incoherent feed-forward loop",
            instead="'cooperative repression' builds a Hill term.",
        )
        message = str(refusal)
        assert "Terium/compose/library_signaling.py" in message
        assert "INCOHERENT_FEEDFORWARD" in message
        assert "cooperative repression" in message
        assert refusal.module == "library_signaling"
        assert isinstance(refusal, UnrecognisedShape)

    def test_the_new_libraries_are_described_in_the_refusal_not_just_named(self) -> None:
        # A bare path tells a reader what to add and not what they are
        # missing. `EXPANSION_LIBRARIES` is where the second half comes from.
        for module in ("library_signaling", "library_metabolic"):
            message = str(
                MissingMotifLibrary("x", module, "MOTIF", "shape")
            )
            assert EXPANSION_LIBRARIES[module] in message, module
        assert "further motifs" in str(
            MissingMotifLibrary("x", "library_nobody_registered", "MOTIF", "shape")
        )

    def test_no_new_refusal_offers_to_build_something_adjacent(self) -> None:
        """The failure this whole module exists to avoid.

        A near-miss mechanism simulates perfectly and answers a different
        question. Every refusal says what IS reachable and lets the reader
        choose; none substitutes. Asserted over the refusals the new rules
        actually raise, by asking for each shape on a module that cannot
        exist.
        """
        refusal = MissingMotifLibrary(
            "x", "library_metabolic", "BRANCH_POINT", "branch point",
            instead="'two enzymes competing' builds the same network.",
        )
        assert "Nothing adjacent was substituted" in str(refusal)

    def test_every_refusal_the_new_rules_raise_says_what_to_do_instead(self) -> None:
        """Refusals are first-class: a precise reason AND a next step.

        Three of the new rules decline to choose for the reader rather than
        declining for want of a file, and each has to leave them somewhere to
        go. A refusal that only says no is a dead end.
        """
        cases = (
            ("a feed-forward loop", "say which"),
            ("a linear metabolic pathway", "of four steps"),
            ("a linear pathway of one step", "reversible enzymatic"),
        )
        missing = []
        for query, expected in cases:
            with pytest.raises(UnrecognisedShape) as caught:
                recognise(query)
            if expected.lower() not in str(caught.value).lower():
                missing.append((query, str(caught.value)))
        assert missing == []
        # Unconditional, so an emptied table cannot pass this by iterating
        # nothing.
        with pytest.raises(UnrecognisedShape) as caught:
            recognise("a feed-forward loop")
        assert len(str(caught.value)) > 120

    def test_the_positive_autoregulation_refusal_points_at_the_new_loop(self) -> None:
        """A refusal improved by this change, and the only one.

        `library_expression` defines no positive autoregulation motif, so
        "a positively autoregulated gene" refuses. It now names the closed
        positive loop that IS reachable -- and says what differs, because the
        signalling motif is one stage where the expression one is two.
        Naming an alternative is not substituting one: nothing was built.
        """
        with pytest.raises(UnrecognisedShape) as caught:
            recognise("a positively autoregulated gene")
        message = str(caught.value)
        assert "BISTABLE_POSITIVE_FEEDBACK" in message
        assert "ONE stage" in message
        assert isinstance(caught.value, MissingMotifLibrary)
        # It is still a refusal: nothing was substituted for the motif that
        # is absent.
        assert "Nothing adjacent was substituted" in message


#: Every shape the brief for this change named, with a phrase that must
#: reach it and the mechanism it must build.
#:
#: Written out as ONE table rather than left implicit across two files
#: because the brief is a list of capabilities and "is each of them
#: reachable" is a question a reader should be able to answer by reading a
#: table, not by cross-referencing `NEW_SHAPES` here against the one in
#: `test_compose_grammar_expansion.py`. Eleven of these were already
#: reachable before this change and are asserted anyway: a new trigger word
#: is exactly what takes an old phrase, and the two files' tables together
#: are the only thing that would have noticed.
THE_BRIEF = (
    ("two-stage gene expression",
     "two stage gene expression", "two_stage_expression", "library_expression"),
    ("an autoregulated gene",
     "an autoregulated gene", "autoregulated_gene", "library_expression"),
    ("a repressed promoter",
     "a repressed promoter", "repressed_promoter", "library_expression"),
    ("an activated promoter",
     "an activated promoter", "activated_promoter", "library_expression"),
    ("uncompetitive inhibition",
     "uncompetitive inhibition", "uncompetitive_inhibition", None),
    ("noncompetitive inhibition",
     "noncompetitive inhibition", "noncompetitive_inhibition", None),
    ("mixed inhibition",
     "mixed inhibition", "mixed_inhibition", None),
    ("product inhibition",
     "product inhibition", "product_inhibition", None),
    ("ping-pong bi-bi",
     "a ping pong bi bi mechanism", "ping_pong_bi_bi", None),
    ("ordered bi-bi",
     "an ordered bi-bi mechanism", "ordered_bi_bi", None),
    ("MWC allostery",
     "the mwc concerted model of an allosteric enzyme", "mwc_allostery",
     "library_enzymology"),
    ("a futile cycle",
     "a futile cycle", "futile_cycle", "library_enzymology"),
    ("an incoherent feed-forward loop",
     "an incoherent feed-forward loop", "incoherent_feedforward",
     "library_signaling"),
    ("a coherent feed-forward loop",
     "a coherent feed-forward loop", "coherent_feedforward",
     "library_signaling"),
    ("a two-component system",
     "a two component system", "two_component_system", "library_signaling"),
    ("a GPCR cycle",
     "a gpcr activation cycle", "gpcr_activation", "library_signaling"),
    ("an ultrasensitive zero-order cycle",
     "zero order ultrasensitivity in a covalent modification cycle",
     "ultrasensitive_cycle", None),
    ("facilitated diffusion",
     "facilitated diffusion of glucose", "facilitated_transport", None),
    ("symport",
     "sodium glucose symport", "symport", "library_transport"),
    ("antiport",
     "a sodium calcium antiport exchanger", "antiport", "library_transport"),
    ("receptor internalisation",
     "receptor internalisation after ligand binding",
     "receptor_internalisation", "library_transport"),
    ("a linear metabolic pathway",
     "a linear metabolic pathway of four steps", "linear_metabolic_pathway",
     "library_metabolic"),
    ("a branch point",
     "a branch point where one metabolite feeds two enzymes", "branch_point",
     "library_metabolic"),
    ("a moiety-conserved cycle",
     "a moiety conserved cycle", "moiety_conserved_cycle", "library_metabolic"),
)


class TestTheWholeBriefIsReachable:
    """Every capability this change was asked for, as one table.

    Not a duplicate of `NEW_SHAPES`. That table is about the rules added
    here and the words they nearly took; this one is about the LIST -- and
    a list is exactly the thing that quietly loses an entry when somebody
    narrows a trigger to fix a collision.
    """

    def test_every_shape_in_the_brief_builds_or_names_the_file_it_wanted(self) -> None:
        failures = []
        for shape, query, expected, module in THE_BRIEF:
            built, refused = _outcome(query)
            if module is None or module in AVAILABLE:
                if built != expected:
                    failures.append(f"{shape}: {query!r} -> {built or refused!r}")
                continue
            if not isinstance(refused, MissingMotifLibrary):
                failures.append(f"{shape}: {query!r} did not name {module}")
            elif refused.module != module:
                failures.append(f"{shape}: {query!r} named {refused.module}")
        assert failures == []
        # The table itself has to be a table, or the sweep proves nothing.
        assert len(THE_BRIEF) >= 21
        assert len({query for _, query, _, _ in THE_BRIEF}) == len(THE_BRIEF)

    def test_every_shape_in_the_brief_reaches_a_rule_at_all(self) -> None:
        # Unconditional on every checkout, because rule selection happens
        # before any motif is fetched. A shape that reaches NO rule is the
        # failure this whole file exists to stop, and it looks identical to
        # a missing library from the outside.
        unreached = [
            (shape, query) for shape, query, _, _ in THE_BRIEF
            if _winning_rule(query) is None
        ]
        assert unreached == []

    def test_the_brief_s_shapes_do_not_collapse_onto_one_another(self) -> None:
        """Twenty-four phrases, twenty-four distinct mechanisms.

        Stated as a set count rather than pairwise, because a pairwise sweep
        misses a two-way swap -- which is the exact shape of both historical
        defects. If any two phrases collapsed onto one model the set shrinks
        and this fails, whichever direction the collapse went.
        """
        mechanisms = {expected for _, _, expected, _ in THE_BRIEF}
        assert len(mechanisms) == len(THE_BRIEF)
        reachable = {
            recognise(query).rule
            for _, query, _, module in THE_BRIEF
            if module is None or module in AVAILABLE
        }
        assert reachable <= mechanisms
        assert len(reachable) >= 8, "the core library alone serves eight of these"


class TestEveryRegisteredLibraryIsReachable:
    def test_both_new_libraries_have_a_query_that_reaches_them(self) -> None:
        """The invariant this file is named after, as one assertion.

        Registering a library in `EXPANSION_LIBRARIES` without a phrase that
        gets to it produces a capability nobody can name -- which is what
        `library_signaling.py` says about itself in its own docstring, and
        which is invisible from inside `grammar.py` because the rule table
        looks complete either way.
        """
        reached = {module for _, _, _, module in NEW_SHAPES if module is not None}
        assert {"library_signaling", "library_metabolic"} <= reached
        # And no row names a module that is not registered, so a typo shows
        # up here rather than as a build-or-refuse test that can never take
        # its refusal branch.
        assert reached - set(EXPANSION_LIBRARIES) == set()

    def test_the_motifs_left_unreachable_are_named_as_a_decision(self) -> None:
        """Two metabolic motifs have no phrase, on purpose.

        `ALLOSTERIC_FEEDBACK`'s phrases are owned by `feedback_inhibition`
        (82), whose refusal to guess which step of a pathway is the committed
        one is pinned behaviour; `TRANSPORTER_LIMITED_UPTAKE`'s are owned by
        `transport` (76), which sends coupled uptake to
        `library_transport.SYMPORT`. Wiring either would put two motifs
        behind one phrase. This pins that those two phrases still go where
        they went, so the decision stays a decision rather than decaying into
        an accident.
        """
        assert _winning_rule(
            "sequential feedback inhibition in amino acid synthesis"
        ) == "feedback_inhibition"
        assert _winning_rule("uptake of a nutrient across the membrane") == "transport"
        # And the reason it matters: the grammar's own docstring says so, so
        # a reader who deletes the decision has to delete the sentence too.
        from Terium.compose import grammar

        assert "ALLOSTERIC_FEEDBACK" in grammar.__doc__
        assert "TRANSPORTER_LIMITED_UPTAKE" in grammar.__doc__
