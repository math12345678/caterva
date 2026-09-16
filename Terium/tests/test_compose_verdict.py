"""The page above the dossier: what the model supports, and what it does not.

WHY MOST OF THESE TESTS ARE ABOUT WHAT IT REFUSES TO SAY
---------------------------------------------------------
A summary page is the most-read and least-checked thing in any report. It is
where a score would go if there were one, and a score is exactly what must not
be there: a reader would cite the number and never read the sentence under it.

So these pin the refusals. No score. No averaging -- a model that is
structurally sound and numerically absurd is not "medium", it has one specific
problem and naming it is the whole point. One next step, not nine. And a check
that did not run is reported as unexamined rather than passed, which is the
failure this entire package is built against.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from Terium.compose.builder import Composition
from Terium.compose.library import CATALYTIC_STEP
from Terium.compose.pipeline import compose
from Terium.compose.verdict import (
    BROKEN, GROUNDED, LICENCE, ROBUST, STRUCTURAL, VERDICTS, Concern, Verdict,
    form,
)


@pytest.fixture(scope="module")
def cascade():
    return compose("three step phosphorylation cascade")


class TestTheNormalCase:
    """A composed model with placeholder constants is STRUCTURAL.

    Not a criticism, and the page must not read as one: it is the state of
    every model this package builds before anyone names an enzyme, and it
    supports real questions -- just not questions about a particular cell.
    """

    def test_a_placeholder_model_is_structural_not_broken(self, cascade) -> None:
        result = form(cascade)
        assert result.verdict == STRUCTURAL
        assert result.usable

    def test_it_says_what_that_licenses(self, cascade) -> None:
        summary = form(cascade).summary()
        assert "Questions about the MECHANISM" in summary
        assert "Not questions about any particular enzyme" in summary

    def test_the_placeholders_are_a_concern_but_not_a_fault(self, cascade) -> None:
        result = form(cascade)
        provenance = [c for c in result.concerns if c.source == "provenance"]
        assert provenance
        assert provenance[0].severity == STRUCTURAL
        assert provenance[0].severity != BROKEN

    def test_the_next_step_is_actionable(self, cascade) -> None:
        # A concern with no action is a complaint.
        step = form(cascade).next_step()
        assert step
        assert "name the enzyme" in step


class TestItRefusesToScore:
    def test_there_is_no_numeric_score_anywhere(self, cascade) -> None:
        """The most quotable thing in the package would also be the least
        defensible. A reader cites the 7.3 and never reads the sentence.
        """
        result = form(cascade)
        assert not hasattr(result, "score")
        assert not hasattr(result, "grade_value")
        assert result.verdict in VERDICTS

    def test_the_summary_says_why_there_is_no_score(self, cascade) -> None:
        summary = form(cascade).summary()
        assert "deliberately no score" in summary
        assert "worst finding sets the verdict" in summary

    def test_usable_is_not_called_valid(self, cascade) -> None:
        # It answers one question -- whether to keep reading -- and the name
        # must not imply more.
        result = form(cascade)
        assert not hasattr(result, "valid")
        assert "whether to keep reading" in Verdict.usable.__doc__


class TestTheWorstFindingSetsTheVerdict:
    """No averaging. A model that is structurally sound and numerically
    absurd has one specific, nameable problem.
    """

    def test_one_broken_concern_makes_the_whole_verdict_broken(self) -> None:
        # Constructed, because a real model that trips this is a model with
        # a bug, and the point is the arithmetic of the verdict.
        result = Verdict(
            verdict=BROKEN,
            concerns=(
                Concern("scale", BROKEN, "a Km tighter than avidin-biotin"),
                Concern("provenance", STRUCTURAL, "placeholders"),
            ),
        )
        assert not result.usable
        assert len(result.blocking) == 1

    def test_concerns_are_ordered_worst_first(self) -> None:
        # So that next_step() returns the most valuable action rather than
        # the first one constructed.
        assert VERDICTS.index(BROKEN) < VERDICTS.index(STRUCTURAL)
        assert VERDICTS.index(STRUCTURAL) < VERDICTS.index(GROUNDED)
        assert VERDICTS.index(GROUNDED) < VERDICTS.index(ROBUST)

    def test_a_physically_impossible_constant_makes_it_broken(self) -> None:
        """The end-to-end version: a real model, one absurd number.

        A Km of 1e-16 mM is 1e-19 M, tighter than avidin-biotin. Nothing
        downstream of that is worth reading, and the page says so instead of
        reporting a steady state computed from it.
        """
        model = compose("substrate inhibition at high substrate concentration")
        broken = replace(
            model.network,
            parameters=tuple(
                replace(p, value=1e-16) if p.id.endswith("_Km") else p
                for p in model.network.parameters
            ),
        )

        class _Broken:
            network = broken
            recognition = model.recognition
            resolvable = model.resolvable
            structure_only = model.structure_only

        result = form(_Broken())
        assert result.verdict == BROKEN
        assert not result.usable
        assert any("avidin" in c.detail for c in result.blocking)

    def test_the_broken_licence_says_to_stop_reading(self) -> None:
        assert "Nothing." in LICENCE[BROKEN]
        assert "before reading any other number" in LICENCE[BROKEN]


class TestOneNextStepNotNine:
    def test_next_step_returns_a_single_action(self, cascade) -> None:
        """A report ending with nine suggestions has prioritised nothing,
        and the reader picks the easiest rather than the most valuable.
        """
        step = form(cascade).next_step()
        assert isinstance(step, str)
        assert "\n" not in step

    def test_it_is_the_worst_concern_s_remedy(self) -> None:
        result = Verdict(
            verdict=BROKEN,
            concerns=(
                Concern("scale", BROKEN, "impossible", "fix the units"),
                Concern("provenance", STRUCTURAL, "placeholders", "name the enzyme"),
            ),
        )
        assert result.next_step() == "fix the units"

    def test_no_concerns_means_no_next_step(self) -> None:
        assert Verdict(verdict=GROUNDED, concerns=()).next_step() is None


class TestACheckThatDidNotRunIsNotAPass:
    """The failure this whole package is built against.

    Silence about a check that did not run reads exactly like a check that
    passed, and the difference is the entire value of the page.
    """

    def test_an_unrun_check_is_reported_as_unavailable(self, cascade) -> None:
        result = form(cascade)  # no robustness, no validation passed in
        assert "robustness" in result.unavailable
        assert "validate" in result.unavailable

    def test_the_summary_says_they_were_not_examined(self, cascade) -> None:
        summary = form(cascade).summary()
        assert "did NOT run" in summary
        assert "unexamined, not passed" in summary

    def test_a_check_that_ran_is_reported_with_what_it_found(
        self, cascade
    ) -> None:
        result = form(cascade)
        assert "scale" in result.consulted
        assert "units" in result.consulted
        assert "provenance" in result.consulted
        # And the note says something, not just that it ran.
        assert result.consulted["scale"]

    def test_running_a_check_moves_it_out_of_unavailable(self, cascade) -> None:
        class _Clean:
            findings = ()

        result = form(cascade, validation=_Clean())
        assert "validate" not in result.unavailable
        assert result.consulted["validate"] == "cross-checks agree"


class TestTheRobustnessPath:
    def test_a_disagreement_between_modules_is_blocking(self, cascade) -> None:
        """Two independent routes to the same fact disagreeing is the most
        informative thing this package can find about itself, so it is not
        buried in a subsection.
        """
        class _Finding:
            severity = "error"
            detail = "the root finder and the integrator disagree"

        class _Failed:
            findings = (_Finding(),)

        result = form(cascade, validation=_Failed())
        assert result.verdict == BROKEN
        assert any("disagree" in c.detail for c in result.blocking)
        assert "most informative" in result.blocking[0].remedy

    def test_a_grounded_model_whose_conclusion_always_held_is_robust(self) -> None:
        class _Grounded:
            # Grounded the way the verdict now understands it: provenance
            # present, everything measured, nothing a placeholder. The old
            # stand-in said `structure_only = False`, which was the flag
            # the bug read -- naming a subject was enough to be "grounded".
            structure_only = False
            resolvable = ()
            measured = ("kcat",)
            placeholders = ()

            class recognition:
                class composition:
                    instances = ()

                    @staticmethod
                    def unit_findings():
                        return ()

            class network:
                parameters = ()
                species = ()

        class _Perfect:
            fraction = 1.0
            held_count = 40
            evaluated = tuple(range(40))
            conclusion = "bistable"

        result = form(_Grounded(), robustness=_Perfect())
        assert result.verdict == ROBUST
        assert result.conclusion == "bistable"

    def test_robust_licences_more_than_grounded(self) -> None:
        assert "survived the measured uncertainty" in LICENCE[ROBUST]
        assert "survived" not in LICENCE[GROUNDED]

    def test_the_conclusion_tested_is_named(self) -> None:
        # "Robust" with no statement of robust-to-what is not a claim.
        result = Verdict(verdict=ROBUST, concerns=(), conclusion="bistable")
        assert "The conclusion tested: bistable" in result.summary()


class TestEveryVerdictHasALicence:
    def test_no_verdict_is_a_bare_label(self) -> None:
        """A verdict without its licence is a label, and labels get quoted
        without their qualifications.
        """
        for verdict in VERDICTS:
            assert verdict in LICENCE
            assert len(LICENCE[verdict]) > 60, verdict

    def test_the_grounded_licence_names_its_limits(self) -> None:
        # Grounded is the one most likely to be over-read.
        licence = LICENCE[GROUNDED]
        assert "AT the conditions those constants were measured at" in licence
        assert "other organisms" in licence


class TestThePageCanTellTwoModelsApart:
    """The defect that made this class necessary.

    Swept across the eleven models the composer builds, this page returned
    an identical verdict for every one: STRUCTURAL, one concern, the same
    next step. True of all eleven, and useless -- it said the same thing
    about a toggle switch and about an open system with no steady state at
    all.

    The package already knew they were different. analysis.analyse reports
    2 stable states for the toggle, 0 for the open system, and a spiral for
    the repressilator. The verdict simply never asked.
    """

    def _behaviour(self, query: str) -> str:
        from Terium.compose.analysis import analyse
        from Terium.compose.sensitivity import STARTS_PER_SPECIES

        model = compose(query)
        stability = analyse(model.network, starts_per_species=STARTS_PER_SPECIES)
        verdict = form(model, stability=stability)
        assert verdict.behaviour, query
        return verdict.behaviour

    def test_a_switch_and_an_open_system_do_not_read_the_same(self) -> None:
        switch = self._behaviour("a toggle switch between two repressors")
        open_system = self._behaviour("an open system with constant substrate inflow")
        assert switch != open_system
        assert "2 stable states" in switch
        assert "no steady state was found" in open_system

    def test_an_open_system_says_the_question_is_wrong_for_it(self) -> None:
        # Not merely "no steady state" -- every steady-state number below it
        # is the wrong question, and a reader should be told before reading
        # them rather than after.
        described = self._behaviour("an open system with constant substrate inflow")
        assert "runs forever rather than settling" in described
        assert "wrong question for it" in described

    def test_a_stable_spiral_is_not_reported_as_a_plain_steady_state(self) -> None:
        """The repressilator at library defaults RINGS AND SETTLES.

        That is a real property of those constants and the most interesting
        thing this page can say about a mechanism built to oscillate.
        Reporting only "one stable state" threw it away.
        """
        described = self._behaviour("repressilator oscillations")
        assert "SPIRALS" in described
        assert "not a sustained one" in described
        assert "these particular constants do not make it" in described

    def test_a_monotonic_model_is_not_called_a_spiral(self) -> None:
        # The discriminator has to cut both ways or it is decoration.
        described = self._behaviour("three step phosphorylation cascade")
        assert "SPIRALS" not in described
        assert "one stable state was found" in described

    def test_it_reports_what_the_search_found_not_what_the_system_is(self) -> None:
        """analysis.py says "at least two stable states were FOUND", never
        "this system is bistable". This page must not upgrade that on the
        way past.
        """
        switch = self._behaviour("a toggle switch between two repressors")
        assert "were found" in switch
        assert "is bistable" not in switch

        cascade = self._behaviour("three step phosphorylation cascade")
        assert "did not find another" in cascade
        assert "is monostable" not in cascade

    def test_without_a_stability_report_it_says_so_rather_than_guessing(
        self, cascade
    ) -> None:
        verdict = form(cascade)          # no stability passed
        assert verdict.behaviour is None
        assert "stability" in verdict.unavailable
        assert "cannot say what the model does" in verdict.unavailable["stability"]

    def test_the_summary_leads_with_the_behaviour(self) -> None:
        # It is the line that differs between two models, so it goes where a
        # reader meets it first rather than after three paragraphs they have
        # already read on another model.
        from Terium.compose.analysis import analyse
        from Terium.compose.sensitivity import STARTS_PER_SPECIES

        model = compose("a toggle switch between two repressors")
        stability = analyse(model.network, starts_per_species=STARTS_PER_SPECIES)
        summary = form(model, stability=stability).summary()

        assert "What this model does:" in summary
        assert summary.index("What this model does:") < summary.index("concern(s)")


class TestUnitsBalancedIsEarned:
    """The page said "units: balanced" about a check that never ran.

    `_dimensional_concerns` swallowed every exception into an empty list,
    with a comment saying the failure was "reported elsewhere". It was
    not; the caller wrote "balanced" over the empty list. And it read
    `unit_findings()`, which is also empty for a composition that declares
    no rate law -- "balanced" across zero laws. Two ways for a check that
    examined nothing to be printed as a check that passed.
    """

    def test_a_real_model_says_how_many_laws_balance(self) -> None:
        from Terium.compose.verdict import form

        verdict = form(compose("three step phosphorylation cascade"))
        note = verdict.consulted["units"]
        assert note != "balanced", "the bare word, with no count behind it"
        assert "rate law(s) balance" in note
        assert "units" not in verdict.unavailable

    def test_a_raise_is_unavailable_not_balanced(self) -> None:
        from Terium.compose.verdict import form

        verdict = form(object())  # no composition to ask at all
        assert "units" in verdict.unavailable
        assert "units" not in verdict.consulted
        assert "AttributeError" in verdict.unavailable["units"]

    def test_zero_rate_laws_is_unavailable_not_balanced(self) -> None:
        from Terium.compose.verdict import _dimensional_concerns

        class _Empty:
            class recognition:
                class composition:
                    @staticmethod
                    def unit_check():
                        return 0, ()

        concerns, note, failure = _dimensional_concerns(_Empty())
        assert not concerns
        assert note is None
        assert failure is not None
        assert "declares no rate law" in failure

    def test_a_problem_is_counted_against_the_laws_examined(self) -> None:
        from Terium.compose.verdict import _dimensional_concerns

        class _Finding:
            severity = "blocking"
            where = "r1"
            detail = "left side is mM/s, right side is mM"

        class _Bad:
            class recognition:
                class composition:
                    @staticmethod
                    def unit_check():
                        return 3, (_Finding(),)

        concerns, note, failure = _dimensional_concerns(_Bad())
        assert len(concerns) == 1
        assert failure is None
        assert note == "1 problem(s) across 3 rate law(s)"


class TestGroundedIsEarnedByProvenance:
    """Typing an enzyme's name flipped the page to GROUNDED.

    The verdict read `structure_only`, which means "no subject was named",
    and treated its negation as "constants resolved". So a query naming
    hexokinase -- no search run, every constant the library's placeholder
    -- was graded "grounded in measured constants, with the provenance to
    show it". This is the one claim the package exists never to make, made
    at the top of the page.

    GROUNDED now requires a model that carries provenance and whose every
    resolvable constant is measured. A bare `ComposedModel` carries none.
    """

    def _measurement(self, value, unit):
        from Terium.compose.export import Measurement

        return Measurement(
            value=value, unit=unit, citation="c", organism="Homo sapiens",
            source="brenda", citation_source="pubmed", reference_id="1",
        )

    def test_a_named_subject_with_no_search_is_structural(self) -> None:
        named = compose(
            "enzyme kinetics with a competitive inhibitor", subject="hexokinase"
        )
        verdict = form(named)
        assert verdict.verdict == STRUCTURAL
        assert verdict.verdict != GROUNDED

    def test_and_the_note_says_no_search_was_run(self) -> None:
        named = compose(
            "enzyme kinetics with a competitive inhibitor", subject="hexokinase"
        )
        note = form(named).consulted["provenance"]
        assert "'hexokinase' named, no search run" in note
        assert "resolved" not in note

    def test_the_remedy_names_the_search(self) -> None:
        named = compose(
            "enzyme kinetics with a competitive inhibitor", subject="hexokinase"
        )
        remedy = form(named).next_step()
        assert remedy is not None
        assert "literature search for 'hexokinase'" in remedy

    def test_no_subject_is_structural_as_before(self) -> None:
        verdict = form(compose("enzyme kinetics with a competitive inhibitor"))
        assert verdict.verdict == STRUCTURAL
        assert "no enzyme was named" in verdict.concerns[0].detail

    def test_full_provenance_is_grounded(self) -> None:
        from Terium.compose.export import provenance_of

        model = compose(
            "enzyme kinetics with a competitive inhibitor", subject="hexokinase"
        )
        measured = {
            "reaction_kcat": self._measurement(100.0, "1/s"),
            "reaction_Km": self._measurement(0.1, "mM"),
            "reaction_Ki": self._measurement(0.5, "mM"),
        }
        verdict = form(provenance_of(model, measured=measured))
        assert verdict.verdict == GROUNDED
        assert "all 3 constant(s) measured, with provenance" in (
            verdict.consulted["provenance"]
        )

    def test_partial_provenance_is_still_structural(self) -> None:
        """One measured out of three is not grounded.

        The licence for GROUNDED is "questions about the system whose
        constants these are"; with two placeholders the constants are not
        that system's, and the count is what the reader needs.
        """
        from Terium.compose.export import provenance_of

        model = compose(
            "enzyme kinetics with a competitive inhibitor", subject="hexokinase"
        )
        verdict = form(provenance_of(
            model, measured={"reaction_kcat": self._measurement(100.0, "1/s")}
        ))
        assert verdict.verdict == STRUCTURAL
        assert "1 measured, 2 unmeasured" in verdict.consulted["provenance"]

    def test_robust_still_requires_grounded(self) -> None:
        # A perfect robustness fraction on an unmeasured model must not
        # reach ROBUST via the old route either.
        class _Perfect:
            fraction = 1.0
            held_count = 40
            evaluated = tuple(range(40))
            conclusion = "one stable state"

        named = compose(
            "enzyme kinetics with a competitive inhibitor", subject="hexokinase"
        )
        verdict = form(named, robustness=_Perfect())
        assert verdict.verdict == STRUCTURAL, (
            "100% robust placeholders were graded ROBUST"
        )
