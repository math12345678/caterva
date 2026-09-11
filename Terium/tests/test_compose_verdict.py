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
            structure_only = False
            resolvable = ()

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
