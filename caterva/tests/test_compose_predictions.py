"""Whether the model's OUTPUT is physically possible, not just its input.

WHAT THIS MODULE EXISTS TO CATCH, STATED ONCE
---------------------------------------------
`scale.py` checks every number that goes in and never looks at what comes
out. A synthesis rate of 1 mM/s and a degradation rate of 1e-5 /s are two
ordinary numbers, each inside every range scale.py knows about, whose
steady state is 100 M -- twenty thousand times the entire protein content
of a cell.

`analysis.FixedPoint` carries a flag called `physical`, which sounds like
this check and is not: it means "no species is negative". A fixed point at
100 M is `physical`.
"""

from __future__ import annotations

import math

import pytest

from caterva.compose.analysis import analyse
from caterva.compose.pipeline import compose
from caterva.compose.predictions import (
    IMPOSSIBLE, POSSIBLE, QUESTIONABLE, UNEXAMINED, VERDICTS,
    Excess, PredictionRefused, PredictionReport,
    check_state, check_steady_states, check_trajectory,
)
from caterva.compose.scale import (
    ERROR, ONE_MOLECULE_PER_BACTERIUM_MOLAR, QUESTION,
    TOTAL_CELLULAR_PROTEIN_MOLAR,
)
from caterva.compose.timeseries import Series


class TestTheBoundThatWasMissing:
    def test_a_steady_state_above_total_protein_is_impossible(self) -> None:
        # X is named a protein: the bound on total cellular protein reaches
        # only species the caller says are proteins, because applying it
        # to everything called measured glutamate impossible.
        report = check_state({"X": 100.0}, unit="M", proteins=("X",))
        assert report.verdict == IMPOSSIBLE
        assert len(report.impossible) == 1
        assert report.impossible[0].severity == ERROR
        assert "total cellular protein" in report.impossible[0].against

    def test_it_says_by_how_much(self) -> None:
        """A factor is checkable; "too high" is not.

        A reader deciding whether to believe this needs to be able to redo
        the division, which means seeing both numbers and the ratio.
        """
        report = check_state({"X": 100.0}, unit="M", proteins=("X",))
        detail = report.impossible[0].detail
        expected = 100.0 / TOTAL_CELLULAR_PROTEIN_MOLAR
        assert f"{expected:.3g}x" in detail
        assert report.impossible[0].molar == pytest.approx(100.0)

    def test_it_names_why_the_input_check_missed_it(self) -> None:
        # The point a professor would ask about: scale.py passed every
        # parameter, so why is this wrong?
        detail = check_state(
            {"X": 100.0}, unit="M", proteins=("X",)
        ).impossible[0].detail
        assert "their combination is not" in detail
        assert "checking the inputs did not catch it" in detail

    def test_a_plausible_state_is_possible(self) -> None:
        # The cry-wolf direction. 1 uM is an ordinary intracellular
        # concentration and must not be flagged.
        report = check_state({"X": 1e-6}, unit="M")
        assert report.verdict == POSSIBLE
        assert not report.findings
        assert "X" in report.examined

    def test_the_boundary_is_not_flagged(self) -> None:
        # Exactly at the bound is not above it. A strict comparison keeps
        # the check from firing on the number it was derived from.
        report = check_state(
            {"X": TOTAL_CELLULAR_PROTEIN_MOLAR}, unit="M", proteins=("X",)
        )
        assert report.verdict == POSSIBLE


class TestBelowOneMoleculeIsAQuestionNotAnError:
    """A fraction of a molecule is not a small amount of something.

    It is the statement that the deterministic model has stopped applying,
    and the answer is a stochastic run rather than a different number.
    Reporting it as an ERROR would tell a student their model is broken
    when what it needs is a different solver.
    """

    def test_it_is_a_question(self) -> None:
        report = check_state({"X": 1e-10}, unit="M")
        assert report.verdict == QUESTIONABLE
        assert report.questionable[0].severity == QUESTION
        assert not report.impossible

    def test_it_names_the_solver_to_use_instead(self) -> None:
        detail = check_state({"X": 1e-10}, unit="M").questionable[0].detail
        assert "compose/stochastic.py" in detail
        assert "rather than a different value" in detail

    def test_it_says_how_many_molecules(self) -> None:
        value = 1e-10
        report = check_state({"X": value}, unit="M")
        expected = value / ONE_MOLECULE_PER_BACTERIUM_MOLAR
        assert f"{expected:.3g} molecules" in report.questionable[0].detail

    def test_exactly_zero_is_not_questionable(self) -> None:
        # An absent species is a real state, not a sub-molecular one. A
        # knockout is exactly this, and flagging it would fire on every
        # deliberate one.
        report = check_state({"X": 0.0}, unit="M")
        assert report.verdict == POSSIBLE
        assert "X" in report.examined

    def test_one_molecule_itself_is_not_questionable(self) -> None:
        report = check_state(
            {"X": ONE_MOLECULE_PER_BACTERIUM_MOLAR}, unit="M"
        )
        assert report.verdict == POSSIBLE


class TestImpossibleInTheOtherDirection:
    def test_a_negative_prediction_is_impossible(self) -> None:
        report = check_state({"X": -1.0}, unit="mM")
        assert report.verdict == IMPOSSIBLE
        assert "does not exist" in report.impossible[0].against

    def test_it_names_the_two_causes(self) -> None:
        # A negative prediction is either the integrator stepping past
        # zero or a sign error in a rate law, and which one it is changes
        # what the reader should do.
        detail = check_state({"X": -1.0}, unit="mM").impossible[0].detail
        assert "stepped past zero" in detail
        assert "producing what it should consume" in detail

    def test_a_non_finite_prediction_is_impossible(self) -> None:
        report = check_state({"X": float("nan")}, unit="mM")
        assert report.verdict == IMPOSSIBLE
        assert "finite" in report.impossible[0].against

    def test_a_non_finite_prediction_says_it_is_a_divergence(self) -> None:
        # Distinguishing "the model predicts something enormous" from
        # "the integration failed" is the difference between a modelling
        # error and a numerical one.
        detail = check_state({"X": float("inf")}, unit="mM").impossible[0].detail
        assert "diverged or divided by zero" in detail
        assert "rather than that the model predicts something large" in detail


class TestNothingExaminedIsNotPossible:
    """The bug this module committed on its first run.

    `examined_nothing` was `not examined and not unexamined`. A state whose
    every species was SKIPPED has a non-empty `unexamined`, so the
    conjunction was False and `verdict` fell through to POSSIBLE. A report
    reading "0 examined, 1 skipped" called the state possible -- this
    module approving what it never read, which is the exact failure it
    exists to prevent.
    """

    def test_a_state_in_an_unrecognised_unit_is_unexamined(self) -> None:
        report = check_state({"n": 2.0}, unit="dimensionless")
        assert report.verdict == UNEXAMINED
        assert report.verdict != POSSIBLE
        assert report.examined_nothing

    def test_an_empty_state_is_unexamined(self) -> None:
        report = check_state({}, unit="mM")
        assert report.verdict == UNEXAMINED
        assert report.examined_nothing

    def test_the_two_are_distinguishable(self) -> None:
        """Both examined nothing, for different reasons, and say so.

        "nothing was examined" alone invites the reader to assume the
        state was empty, when the commoner cause is a unit this module
        does not recognise -- a fixable thing and a different
        conversation.
        """
        skipped = check_state({"n": 2.0}, unit="dimensionless")
        empty = check_state({}, unit="mM")
        assert skipped.verdict == empty.verdict == UNEXAMINED
        assert skipped.coverage != empty.coverage
        assert "skipped for want of a concentration unit" in skipped.coverage
        assert "nothing was skipped either" in empty.coverage

    def test_the_summary_refuses_a_verdict(self) -> None:
        text = check_state({"n": 2.0}, unit="dimensionless").summary()
        assert "NOTHING WAS EXAMINED" in text
        assert "only an absence of one" in text
        assert "are at amounts a cell could hold" not in text

    def test_a_partly_readable_state_is_still_judged(self) -> None:
        # Skipping some must not suppress the verdict on the rest.
        report = check_state({"X": 100.0, "Y": 1e-6}, unit="M")
        assert report.verdict == IMPOSSIBLE
        assert len(report.examined) == 2


class TestSteadyStates:
    def test_a_library_model_predicts_possible_amounts(self) -> None:
        report = check_steady_states(
            analyse(compose("three step phosphorylation cascade").network)
        )
        assert report, "the premise: this model has a steady state"
        for one in report:
            assert one.verdict == POSSIBLE, one.summary()
            assert one.examined, one.coverage

    def test_each_point_gets_its_own_report(self) -> None:
        """Alternatives are not merged, and the reason matters.

        A bistable switch with one possible branch and one impossible one
        is a real and interesting result. Merging them would produce a
        verdict about no single state the system can be in, and would call
        the whole model impossible on the strength of a branch it may
        never reach.
        """
        report = analyse(
            compose("a toggle switch between two repressors").network
        )
        reports = check_steady_states(report)
        assert len(reports) == len(report.fixed_points)
        for index, one in enumerate(reports):
            assert one.subject == f"steady state {index + 1} of {len(reports)}"

    def test_no_fixed_points_is_refused_not_answered(self) -> None:
        class _None:
            fixed_points = ()

        with pytest.raises(PredictionRefused) as raised:
            check_steady_states(_None())
        assert "no fixed point was found" in str(raised.value)
        assert "belongs to the analysis that searched" in str(raised.value)

    def test_the_wrong_type_is_refused_with_the_right_one_named(self) -> None:
        with pytest.raises(PredictionRefused) as raised:
            check_steady_states(object())
        assert "analysis.StabilityReport" in str(raised.value)


class TestTrajectories:
    """A transient can be impossible while the steady state is fine."""

    def test_an_overshoot_is_caught(self) -> None:
        series = Series.of([0.0, 1.0, 2.0, 3.0], [1e-3, 50.0, 1e-2, 1e-3], "X")
        report = check_trajectory(series, unit="M")
        assert report.verdict == IMPOSSIBLE
        assert report.impossible[0].at_time == pytest.approx(1.0)

    def test_the_steady_state_alone_would_have_missed_it(self) -> None:
        """The whole argument for reading the run and not just the end.

        The final value here is an ordinary 1 mM. A check of where the
        system settled sees nothing, and the curve a student plots has a
        spike in it they will try to interpret.
        """
        series = Series.of([0.0, 1.0, 2.0, 3.0], [1e-3, 50.0, 1e-2, 1e-3], "X")
        assert check_state({"X": 1e-3}, unit="M").verdict == POSSIBLE
        assert check_trajectory(series, unit="M").verdict == IMPOSSIBLE

    def test_one_finding_per_species_not_per_sample(self) -> None:
        """A thousand samples over the line is one problem, not a thousand.

        Reporting each would be the cry-wolf failure ADR 0028 names: the
        reader scrolls past a wall of identical findings and stops reading
        the section.

        THE FIRST VERSION OF THIS TEST COULD NOT FAIL. It used 500 samples
        all at the same value, so the two extremes coincided and only ONE
        index was ever examined -- a mutation that appended a finding per
        index instead of keeping the worst passed it untouched. The
        property only bites when both extremes are findings, so the series
        below goes impossibly high AND sub-molecular.
        """
        times = [float(i) for i in range(500)]
        values = [1e-12 if i % 2 else 50.0 for i in range(500)]
        report = check_trajectory(Series.of(times, values, "X"), unit="M")
        assert len(report.findings) == 1, [
            f.describe() for f in report.findings
        ]
        assert len(report.examined) == 1

    def test_two_species_each_get_one_finding(self) -> None:
        # And the collapse is per species, not per report: two bad species
        # must not collapse into one finding about whichever was worse.
        times = [0.0, 1.0]
        source = Series.of(times, [1e-12, 50.0], "X")
        source.columns["Y"] = (50.0, 1e-12)
        report = check_trajectory(source, unit="M")
        assert len(report.findings) == 2
        assert {f.species for f in report.findings} == {"X", "Y"}

    def test_a_dip_below_zero_is_caught_even_if_it_recovers(self) -> None:
        # The extreme is taken in BOTH directions. Reading only the
        # maximum would miss an integrator that stepped negative and came
        # back, which is a numerical fault worth knowing about.
        series = Series.of([0.0, 1.0, 2.0], [1e-3, -1e-4, 1e-3], "X")
        report = check_trajectory(series, unit="M")
        assert report.verdict == IMPOSSIBLE
        assert "does not exist" in report.impossible[0].against

    def test_an_error_outranks_a_question_at_the_other_extreme(self) -> None:
        # A run that goes both sub-molecular and impossibly high reports
        # the impossible one: the worse of the two extremes is kept.
        series = Series.of([0.0, 1.0], [1e-12, 50.0], "X")
        report = check_trajectory(series, unit="M")
        assert report.verdict == IMPOSSIBLE
        # Both extremes produced a finding; only the worse is reported.
        assert len(report.findings) == 1
        assert report.findings[0].severity == ERROR

    def test_a_non_finite_sample_wins_over_any_extreme(self) -> None:
        # A NaN anywhere is the most informative thing in the record, and
        # max/min over a list containing one are not usefully defined.
        series = Series.of([0.0, 1.0, 2.0], [1e-3, float("nan"), 50.0], "X")
        report = check_trajectory(series, unit="M")
        assert report.verdict == IMPOSSIBLE
        assert "finite" in report.impossible[0].against

    def test_a_healthy_run_is_possible(self) -> None:
        times = [float(i) for i in range(20)]
        series = Series.of(times, [1e-6 + 1e-8 * i for i in range(20)], "X")
        report = check_trajectory(series, unit="M")
        assert report.verdict == POSSIBLE
        assert "X" in report.examined

    def test_a_real_simulated_model_is_possible(self) -> None:
        from caterva.compose.simulate import run

        trajectory = run(compose("three step phosphorylation cascade"))
        report = check_trajectory(trajectory)
        assert report.verdict == POSSIBLE, report.summary()
        assert report.examined, report.coverage

    def test_a_mismatched_column_is_refused(self) -> None:
        class _Ragged:
            times = (0.0, 1.0, 2.0)
            columns = {"X": (1.0, 2.0)}

        with pytest.raises(PredictionRefused) as raised:
            check_trajectory(_Ragged())
        assert "window that silently ended early" in str(raised.value)

    def test_a_trajectory_with_no_species_is_refused(self) -> None:
        class _Empty:
            times = (0.0, 1.0)
            columns: dict = {}

        with pytest.raises(PredictionRefused) as raised:
            check_trajectory(_Empty())
        assert "would be clean and mean nothing" in str(raised.value)


class TestWhatThisDoesNotClaim:
    def test_the_docstring_says_it_is_not_correctness(self) -> None:
        """Capacity is not truth, and the module must not imply it is.

        A prediction inside these bounds has not been shown right; it has
        not been ruled out on grounds of capacity. A reader who took
        POSSIBLE for a clean bill of health would be worse off than one
        who ran no check.
        """
        import caterva.compose.predictions as module

        prose = " ".join((module.__doc__ or "").split())
        assert "does not decide whether the model is RIGHT" in prose
        assert "it has merely not been ruled out" in prose

    def test_the_clean_summary_says_so_too(self) -> None:
        text = check_state({"X": 1e-6}, unit="M").summary()
        assert "not a claim the model is right" in text

    def test_every_verdict_is_in_the_declared_set(self) -> None:
        for state, unit in (
            ({"X": 1e-6}, "M"), ({"X": 100.0}, "M"),
            ({"X": 1e-12}, "M"), ({"n": 1.0}, "dimensionless"),
        ):
            assert check_state(state, unit=unit).verdict in VERDICTS

    def test_unexamined_is_a_verdict_and_not_an_absence(self) -> None:
        # It is in VERDICTS deliberately: a caller switching on the
        # verdict must be made to handle it rather than falling into an
        # else that reads as approval.
        assert UNEXAMINED in VERDICTS
        assert len(set(VERDICTS)) == 4


class TestTheCaseTheInputCheckCannotCatch:
    """The module's whole reason for existing, end to end on a real network.

    Not a unit test of a bound: a network built the way a user would build
    one, run through BOTH checks, where the first says possible and the
    second says impossible. If this ever passes both, the module has
    stopped earning its place.
    """

    @staticmethod
    def _leaky_pool(synthesis=1.0, decay=1e-5):
        """X made at a constant rate, lost first-order. Steady state ks/kd.

        1 mM/s of synthesis and 1e-5 /s of decay are both ordinary numbers
        -- a protein made steadily and turned over slowly. Their ratio is
        100 M.
        """
        from caterva.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        return ReactionNetwork(
            name="leaky_pool",
            species=(Species("X", 0.0),),
            parameters=(
                Parameter("ks", synthesis, "mM/s"),
                Parameter("kd", decay, "1/s"),
            ),
            reactions=(
                Reaction("make", {}, {"X": 1}, "ks"),
                Reaction("decay", {"X": 1}, {}, "kd * X"),
            ),
        )

    def test_the_input_check_passes_it(self) -> None:
        """Both parameters are inside every range scale.py knows.

        This is the premise. If scale.py ever starts refusing these, the
        contrast below stops being the point and this test should say so
        rather than quietly agreeing with whatever changed.
        """
        from caterva.compose.scale import check

        report = check(self._leaky_pool())
        assert report.physically_possible, [
            f.describe() for f in report.errors
        ]

    def test_the_output_check_refuses_it(self) -> None:
        from caterva.compose.analysis import analyse

        reports = check_steady_states(analyse(self._leaky_pool()), unit="mM")
        assert len(reports) == 1
        assert reports[0].verdict == IMPOSSIBLE
        excess = reports[0].impossible[0]
        assert excess.species == "X"
        # ks/kd = 1.0 / 1e-5 = 1e5 mM = 100 M, analytically.
        assert excess.molar == pytest.approx(100.0, rel=1e-3)

    def test_the_two_checks_disagree_and_that_is_the_point(self) -> None:
        from caterva.compose.analysis import analyse
        from caterva.compose.scale import check

        network = self._leaky_pool()
        assert check(network).physically_possible
        assert check_steady_states(
            analyse(network), unit="mM"
        )[0].verdict == IMPOSSIBLE

    def test_a_sensible_ratio_passes_both(self) -> None:
        """The cry-wolf direction, on the same network shape.

        Same two reactions, a decay rate four orders of magnitude faster:
        steady state 1e-2 mM, an ordinary intracellular concentration.
        Without this, a module that returned IMPOSSIBLE unconditionally
        would pass every test above.
        """
        from caterva.compose.analysis import analyse
        from caterva.compose.scale import check

        network = self._leaky_pool(synthesis=1e-4, decay=1e-2)
        assert check(network).physically_possible
        report = check_steady_states(analyse(network), unit="mM")[0]
        assert report.verdict == POSSIBLE, report.summary()


class TestEveryLibraryModelPredictsSomethingPossible:
    """The sweep, across every model the composer builds.

    Worth pinning for the reason the cross-module agreement sweep is: the
    value is entirely in the day it stops being true. A library model that
    starts predicting an impossible amount is a defect in the library's
    default constants, and it would otherwise be found by a user.
    """

    BUILDABLE = (
        "enzyme kinetics with a competitive inhibitor",
        "repressilator oscillations",
        "three step phosphorylation cascade",
        "a MAP kinase cascade with negative feedback",
        "reversible binding of a ligand to a receptor",
        "substrate inhibition at high substrate concentration",
        "two enzymes competing for the same substrate",
        "a toggle switch between two repressors",
        "sequential feedback inhibition in amino acid synthesis",
        "allosteric activation of an enzyme by its product",
    )

    def test_no_steady_state_is_impossible(self) -> None:
        from caterva.compose.analysis import analyse

        checked = 0
        for query in self.BUILDABLE:
            try:
                reports = check_steady_states(analyse(compose(query).network))
            except PredictionRefused:
                # No fixed point is a finding about the model, not about
                # its predicted amounts. Counted as not-checked rather
                # than silently passed.
                continue
            for report in reports:
                if report.already_flagged_nonphysical:
                    # A negative root the analysis already labelled. Real
                    # mathematics, kept there on purpose, and not this
                    # module's discovery to announce.
                    continue
                assert report.verdict != IMPOSSIBLE, (query, report.summary())
                checked += 1
        assert checked, (
            "no model produced a steady state to check, so this sweep "
            "asserted nothing"
        )

    def test_the_sweep_would_notice(self) -> None:
        """The assertion above passes over an empty set of reports.

        Every sweep in this suite carries one of these, because a sweep
        that finds nothing and a sweep that checks nothing are the same
        green. This drives the same comparison with a state that IS
        impossible.
        """
        report = check_state({"X": 100.0}, unit="M")
        assert report.verdict == IMPOSSIBLE


class TestTheVerdictDoesNotRepeatTheAnalysis:
    """Two modules saying the same thing in different words is noise.

    `analysis` keeps negative roots deliberately -- they are a real
    property of the equations, and hiding them makes the positive ones
    look like the whole story -- and it already labels them
    `physical=False`. A root find over a competitive-inhibition model
    returns twenty-odd points and several are non-physical by
    construction.

    The verdict page raised each one again as a BROKEN concern. On "two
    enzymes competing for the same substrate" that read "5 species cannot
    exist at the amount predicted, across 26 steady state(s)" -- a
    sentence that sounds like a model defect and is a restatement of
    something the section above it already said.
    """

    def test_a_flagged_point_is_not_raised_again(self) -> None:
        from caterva.compose.analysis import analyse
        from caterva.compose.verdict import form

        model = compose("two enzymes competing for the same substrate")
        stability = analyse(model.network)
        assert any(
            not p.physical for p in stability.fixed_points
        ), "the premise: this model has non-physical roots"

        verdict = form(model, stability=stability)
        assert not [c for c in verdict.concerns if c.source == "predictions"]

    def test_the_note_says_how_many_it_set_aside(self) -> None:
        # Set aside, not silently dropped: a reader who wants to know why
        # the counts do not add up gets told.
        from caterva.compose.analysis import analyse
        from caterva.compose.verdict import form

        model = compose("two enzymes competing for the same substrate")
        note = form(
            model, stability=analyse(model.network)
        ).consulted["predictions"]
        assert "already non-physical, not re-counted here" in note

    def test_a_genuinely_impossible_point_is_still_raised(self) -> None:
        """The cry-wolf direction, and the one that matters.

        Skipping already-flagged points must not become skipping
        everything. A point the analysis calls physical, predicting more
        than the cell can hold, is exactly what this check exists for.
        """
        from caterva.compose.verdict import _prediction_concerns

        class _Point:
            physical = True
            state = {"X": 100.0}

        class _Stability:
            fixed_points = (_Point(),)

        concerns, note = _prediction_concerns(_Stability(), unit="M")
        assert len(concerns) == 1
        assert concerns[0].source == "predictions"
        assert "cannot exist at the amount predicted" in note


class TestTheProteinBoundIsScopedHereToo:
    """The same false alarm, in this module's own copy of the bound.

    `check_state` applied the protein bound to every species, so a steady
    state predicting glutamate at its measured concentration was
    IMPOSSIBLE. `proteins` names the species it applies to; the rest get
    the solute bound and, above the most abundant measured metabolite, a
    question rather than an error.
    """

    def test_measured_glutamate_is_a_possible_prediction(self) -> None:
        assert check_state({"glutamate": 96.0}, unit="mM").verdict == POSSIBLE

    def test_a_named_protein_keeps_the_protein_bound(self) -> None:
        report = check_state({"TF": 9.6}, unit="mM", proteins=("TF",))
        assert report.verdict == IMPOSSIBLE
        assert "this one protein" in report.impossible[0].detail

    def test_an_unnamed_species_at_ten_millimolar_is_possible(self) -> None:
        assert check_state({"X": 9.6}, unit="mM").verdict == POSSIBLE

    def test_above_measured_metabolites_is_questionable(self) -> None:
        report = check_state({"X": 150.0}, unit="mM")
        assert report.verdict == QUESTIONABLE
        # And it says what the protein bound WOULD have said, so a reader
        # who knows X is a protein can read it as the error it would be.
        assert "over that bound" in report.questionable[0].detail

    def test_past_a_molar_is_impossible_for_anything(self) -> None:
        report = check_state({"X": 1500.0}, unit="mM")
        assert report.verdict == IMPOSSIBLE
        assert "displaced the water" in report.impossible[0].detail

    def test_the_verdict_page_names_the_proteins(self) -> None:
        from caterva.compose.verdict import _protein_species_of

        model = compose("a toggle switch between two repressors")
        named = _protein_species_of(model)
        assert set(named) == set(model.recognition.composition.protein_species())
        assert named, "the premise: repressors are proteins"

    def test_a_model_with_no_composition_names_none(self) -> None:
        # The conservative direction: with nothing to ask, every species
        # gets the weaker bound rather than a guessed protein bound.
        from caterva.compose.verdict import _protein_species_of

        assert _protein_species_of(object()) == ()

    def test_the_trajectory_check_threads_them(self) -> None:
        series = Series.of([0.0, 1.0], [1e-3, 9.6], "TF")
        as_protein = check_trajectory(series, unit="mM", proteins=("TF",))
        as_unknown = check_trajectory(series, unit="mM")
        assert as_protein.verdict == IMPOSSIBLE
        assert as_unknown.verdict == POSSIBLE
