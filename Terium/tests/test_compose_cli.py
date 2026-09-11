"""Every analysis module, reachable from a terminal.

WHAT THESE TESTS ARE FOR
------------------------
`compose/` had seventeen modules and one caller. Each module has its own
test file pinning what it computes; not one of them could tell you whether a
researcher could ask the question. That is the gap ADR 0090 names, and it is
the only gap this file is about: these tests check that the flag exists, that
it reaches the module named, and that its output arrives -- not that the
arithmetic inside is right, which is the business of
`test_compose_crnt.py`, `test_compose_scale.py` and the rest.

So the assertions here are deliberately about the SEAM. A test that
re-checked a deficiency calculation would pass while the flag was wired to
the wrong module.

The one exception is the deficiency arithmetic on a two-complex network,
which is asserted because it is checkable by hand from the reaction table --
A + B <-> AB has 2 complexes in 1 linkage class with a stoichiometric
subspace of rank 1, so delta = 2 - 1 - 1 = 0. That one number proves the
flag reached `crnt` and not something that merely prints a heading.

WHY `main(argv)` AND NOT A SUBPROCESS, EXCEPT ONCE
--------------------------------------------------
Every test here but one calls `main` in-process. A subprocess pays a fresh
interpreter and a fresh import of numpy and the motif library for each
invocation, which on this suite is most of the runtime and buys nothing: the
exit code is `main`'s return value either way, and the streams are
capturable either way.

The exception is `test_the_module_runs_from_a_terminal`, which does use a
subprocess. It is the only test that establishes the claim this whole file
exists for -- that `python -m Terium.compose` works from a shell -- and an
in-process call cannot establish it, because it never exercises the
`__main__` entry at all.

WHY THE EXPENSIVE RUNS ARE MODULE-SCOPED FIXTURES
--------------------------------------------------
Asking for every analysis at once costs several full steady-state searches,
a robustness resampling and an exact SSA. Nine tests want that one run's
output. Re-running it nine times would add minutes for no extra coverage,
and `capsys` cannot be used at module scope -- hence the local `run` helper,
which redirects the two streams itself.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import subprocess
import sys
from dataclasses import dataclass

import pytest

from Terium.compose.__main__ import (
    DEFAULT_SEED, SAMPLES_UNSTATED, build_parser, main,
)
from Terium.compose.grammar import shapes

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Three species, two parameters, two mass-action rate laws. Chosen because
#: every module has something to say about it and the whole battery runs in
#: a few seconds -- a cascade's twelve constants would put this file in the
#: slow suite for no additional wiring coverage.
BINDING = "reversible binding of a ligand to a receptor"

#: A saturating rate law, which is NOT mass action. Chosen for the opposite
#: reason: `--crnt` and `--stochastic` both decline it, truthfully and for
#: the same underlying fact, which is what makes it the model that proves a
#: refusal does not cost the reader the rest of the report.
SATURATING = "substrate inhibition at high substrate concentration"


def _sbml_toolchain_present() -> bool:
    try:
        import antimony  # noqa: F401
        import libsbml  # noqa: F401
    except ImportError:
        return False
    return True


needs_sbml = pytest.mark.skipif(
    not _sbml_toolchain_present(),
    reason="python-libsbml and antimony are needed to export SBML",
)


@dataclass(frozen=True)
class Run:
    """One invocation: what it returned and what it wrote where."""

    code: int
    out: str
    err: str


def run(*argv: str) -> Run:
    """`main(argv)` with both streams captured.

    The streams are redirected rather than captured by `capsys` so that an
    expensive invocation can live in a module-scoped fixture. `Sections`
    reads `sys.stdout` when it is constructed, which is inside this
    redirect, so the report lands here rather than on the terminal.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return Run(code=code, out=out.getvalue(), err=err.getvalue())


# ---------------------------------------------------------------------------
# The whole battery, once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def every_analysis() -> Run:
    """One run asking for every analysis flag at once.

    `--rank-against complex_AB` is passed because three different sections
    need a species named -- the influence ranking, the perturbation readout
    and the quantity `--validate` differentiates -- and the CLI routes all
    three through that one flag on purpose. Naming it here exercises that
    routing; omitting it would leave the sensitivity cross-check unrun.
    """
    return run(
        BINDING,
        "--no-simulate",
        "--rank-against", "complex_AB",
        "--crnt",
        "--scale",
        "--reduction",
        "--identifiability",
        "--design",
        "--robustness", "4",
        "--knockout", "complex_A",
        "--overexpress", "complex_B",
        "--screen",
        "--stochastic", "1e-15",
        "--stochastic-end", "0.001",
        "--validate",
    )


ANALYSIS_HEADINGS = [
    "## Reaction network structure",   # --crnt
    "## Physical scale",               # --scale
    "## Timescale separation",         # --reduction
    "## Identifiability",              # --identifiability
    "## What to measure next",         # --design
    "## Robustness to the placeholders",  # --robustness
    "## Perturbations",                # --knockout/--overexpress/--screen
    "## Stochastic simulation",        # --stochastic
    "## Cross-checks",                 # --validate
]


class TestEveryFlagReachesItsModule:
    @pytest.mark.parametrize("heading", ANALYSIS_HEADINGS)
    def test_the_section_is_in_the_report(self, every_analysis, heading) -> None:
        assert heading in every_analysis.out

    def test_the_report_itself_is_still_there(self, every_analysis) -> None:
        """The analyses are additions, not a replacement.

        A flag that swallowed the dossier would pass every heading check
        above while removing the structure, the invariants and the
        provenance table -- which are the parts that do not depend on a
        placeholder being right.
        """
        assert "## Structure" in every_analysis.out
        assert "## Where the numbers come from" in every_analysis.out
        assert "## Invariants" in every_analysis.out

    def test_crnt_reports_the_deficiency_this_network_actually_has(
        self, every_analysis
    ) -> None:
        """A + B <-> AB: 2 complexes, 1 linkage class, rank 1, delta 0.

        Checkable by hand from the reaction table, and the one assertion in
        this file that would survive the flag being wired to a module that
        merely prints a heading.
        """
        assert "Deficiency = n - l - s = 2 - 1 - 1 = 0" in every_analysis.out

    def test_the_deficiency_theorems_both_report_a_verdict(
        self, every_analysis
    ) -> None:
        # Mass action, deficiency zero, weakly reversible -- the hypotheses
        # of both theorems hold, so both must say APPLIES rather than
        # declining. A section that printed the counts and then silently
        # dropped the verdicts would pass the test above.
        assert "Deficiency Zero Theorem: APPLIES." in every_analysis.out
        assert "Deficiency One Theorem: APPLIES." in every_analysis.out

    def test_the_scale_check_says_where_the_units_came_from(
        self, every_analysis
    ) -> None:
        """The known gap, stated in the report rather than only in a docstring.

        `core.network.Parameter` has an id and a value and no unit. A scale
        report that did not say its units were recovered from the motifs
        would read as though the network carried them.
        """
        assert "scale.units_from_model" in every_analysis.out

    def test_the_perturbations_name_the_readout_they_are_fold_changes_in(
        self, every_analysis
    ) -> None:
        # A fold change with no readout named is not a result. The readout
        # is the same species the influence ranking used, which is the
        # point of routing both through --rank-against.
        assert "Effect on complex_AB" in every_analysis.out

    def test_the_ssa_reports_the_volume_and_the_unit_it_counted_with(
        self, every_analysis
    ) -> None:
        # Counts are concentration x volume x Avogadro. Neither factor is
        # in the network IR, so a trajectory that did not state both would
        # be unreproducible and wrong by an unknown power of ten.
        assert "in mM at 1e-15 L" in every_analysis.out

    def test_the_ssa_states_the_seed_it_used(self, every_analysis) -> None:
        """No seed was typed, so the stated default is the one that must appear.

        ADR 0005 wants the seed explicit. A CLI still has to have an answer
        when nobody types one, and the answer is only reproducible if the
        output says what it was -- a trajectory reported without its seed
        cannot be regenerated by anyone, including its author.
        """
        assert f"from seed {DEFAULT_SEED}" in every_analysis.out

    def test_naming_a_species_lets_the_sensitivity_cross_check_run(
        self, every_analysis
    ) -> None:
        """--rank-against is what makes --validate's fifth check possible.

        `validate` refuses to guess the quantity to differentiate, so
        without a species named it reports that check unchecked. All five
        running is the evidence that the CLI passed the species through.
        """
        assert (
            "checks produced a result (dimensions, conservation, fixed "
            "point, settling time, sensitivity)"
        ) in every_analysis.out

    def test_only_the_one_inapplicable_analysis_declined(
        self, every_analysis
    ) -> None:
        """Exactly one refusal, and it is the true one.

        This model has a single dynamic mode -- the other two species are
        fixed by conservation laws -- so there is no ratio between
        timescales and `--reduction` declines. Every other section answers.
        Counting rather than merely looking for the word catches a section
        that quietly refused while another one printed.
        """
        assert every_analysis.out.count("**Refused.**") == 1
        assert "## Timescale separation\n\n**Refused.**" in every_analysis.out

    def test_the_exit_code_says_something_declined(self, every_analysis) -> None:
        # 3, not 0: everything asked for was not produced, and a script
        # piping this into a report generator has to be able to tell.
        assert every_analysis.code == 3

    def test_stderr_names_the_section_that_declined(self, every_analysis) -> None:
        # The reason is in the report, next to the heading it qualifies.
        # stderr carries only the pointer, so a redirected report is intact
        # and a watching human still knows to look.
        assert "Timescale separation" in every_analysis.err
        assert "1 refusal(s) in 1 section(s)" in every_analysis.err


# ---------------------------------------------------------------------------
# A refusal does not cost the reader the rest of the report
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def saturating_report() -> Run:
    """A Michaelis-Menten-shaped model, asked four questions.

    Two of them decline on the same true fact -- a saturating rate law is
    not mass action, so it has no deficiency verdict and no propensity --
    and two answer. The ordering matters: `--crnt` declines FIRST and
    `--validate` answers LAST, so a report that aborted on the first
    refusal would visibly lose the sections after it.
    """
    return run(
        SATURATING,
        "--no-analysis", "--no-simulate", "--no-ranking",
        "--crnt", "--scale", "--stochastic", "1e-15", "--validate",
    )


class TestARefusalDoesNotLoseTheRest:
    def test_the_first_section_declined(self, saturating_report) -> None:
        assert "Deficiency Zero Theorem: **Refused.**" in saturating_report.out
        assert "Deficiency One Theorem: **Refused.**" in saturating_report.out

    def test_the_refusal_says_why_and_what_to_do_instead(
        self, saturating_report
    ) -> None:
        """A refusal with no reason in it is indistinguishable from a bug.

        The module's own text names the cause (a saturating rate law is a
        different function, not an approximation to mass action) and the
        way forward (write the elementary steps). Both must survive the
        trip through the CLI.
        """
        assert "NOT mass action" in saturating_report.out
        assert "E + S -> ES" in saturating_report.out

    def test_a_later_section_still_answered(self, saturating_report) -> None:
        # --scale comes after --crnt and has nothing to do with kinetics.
        assert "## Physical scale" in saturating_report.out
        assert (
            "Every checked number is physically possible"
            in saturating_report.out
        )

    def test_the_last_section_still_answered(self, saturating_report) -> None:
        # --validate runs after --stochastic declined. If a refusal aborted
        # the run, this is the section that would be missing.
        assert "## Cross-checks" in saturating_report.out
        assert "Cross-checked substrate_inhibition" in saturating_report.out

    def test_the_stochastic_diagnosis_survived_its_own_simulation_refusing(
        self, saturating_report
    ) -> None:
        """Two parts under one heading, and only the second one declines.

        `discreteness_matters` deliberately does not require mass action --
        it is the diagnosis, and telling the reader the enzyme sits at 600
        copies is the most useful thing available for a model the SSA
        cannot touch. Losing it because the SSA declined would throw away
        the half that worked.
        """
        assert "the scarcest species is reaction_E" in saturating_report.out
        assert "has no propensity description" in saturating_report.out

    def test_the_exit_code_is_a_refusal_not_a_crash(
        self, saturating_report
    ) -> None:
        assert saturating_report.code == 3

    def test_stderr_counts_the_refusals_and_the_sections_separately(
        self, saturating_report
    ) -> None:
        """Three refusals under two headings, and the line says so.

        `--crnt` asks three questions under one heading and two of them
        decline. Reporting "3 sections" would name a heading twice;
        reporting "1 section" would understate what was lost.
        """
        assert "3 refusal(s) in 2 section(s)" in saturating_report.err


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_a_report_that_produced_everything_exits_zero(self) -> None:
        result = run(BINDING, "--no-analysis", "--no-simulate", "--no-ranking")
        assert result.code == 0
        assert "## Structure" in result.out

    def test_an_analysis_that_answered_does_not_move_the_code(self) -> None:
        # --crnt applies to this network, so nothing declined and the code
        # stays 0. Without this, a 3 from any use of any new flag would
        # pass the refusal tests above while being useless to a script.
        result = run(
            BINDING, "--no-analysis", "--no-simulate", "--no-ranking", "--crnt"
        )
        assert result.code == 0
        assert "## Reaction network structure" in result.out

    def test_no_description_prints_the_help_and_exits_two(self) -> None:
        result = run()
        assert result.code == 2
        assert "the mechanism to build" in result.out

    def test_an_unrecognised_shape_exits_three_with_the_reason(self) -> None:
        result = run("glycolysis")
        assert result.code == 3
        assert "Not built." in result.err
        assert "'glycolysis' is a named pathway, not a shape" in result.err

    def test_an_unknown_flag_is_rejected_rather_than_ignored(self) -> None:
        """argparse's job, and it must keep it.

        A flag accepted and silently dropped is the dangerous failure: the
        user typed it, the run reported success, and nothing said the
        request was not honoured.
        """
        out, err = io.StringIO(), io.StringIO()
        with pytest.raises(SystemExit) as raised:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                main([BINDING, "--not-a-flag"])
        assert raised.value.code == 2
        assert "--not-a-flag" in err.getvalue()

    def test_a_stochastic_modifier_with_no_stochastic_run_is_rejected(self) -> None:
        """The silently-ignored-flag defect, closed at the parser.

        `--stochastic-end 5` with no `--stochastic` has nothing to modify.
        Accepting it and running a deterministic report would report success
        on a request that was never honoured.
        """
        out, err = io.StringIO(), io.StringIO()
        with pytest.raises(SystemExit) as raised:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                main([BINDING, "--stochastic-end", "5"])
        assert raised.value.code == 2
        assert "no stochastic run was asked for" in err.getvalue()

    def test_a_sample_count_below_one_is_rejected(self) -> None:
        # A fraction over zero draws is not a small number, it is no
        # number. Refused at the parser rather than producing a report
        # whose robustness section divides by zero.
        out, err = io.StringIO(), io.StringIO()
        with pytest.raises(SystemExit) as raised:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                main([BINDING, "--robustness", "0"])
        assert raised.value.code == 2
        assert "at least one sample" in err.getvalue()


# ---------------------------------------------------------------------------
# The flags that were already here
# ---------------------------------------------------------------------------


class TestTheExistingSurfaceIsUnchanged:
    def test_shapes_lists_every_shape_and_exits_zero(self) -> None:
        result = run("--shapes")
        assert result.code == 0
        assert [name for name in shapes() if name not in result.out] == []

    def test_shapes_still_says_what_it_will_not_recognise(self) -> None:
        # The sentence that keeps the listing from reading as a menu of
        # subjects. 'glycolysis' is not on it and the listing says so.
        result = run("--shapes")
        assert "recognises a SHAPE, never a SUBJECT" in result.out

    def test_antimony_emits_source_instead_of_a_report(self) -> None:
        result = run(BINDING, "--antimony")
        assert result.code == 0
        assert "## Structure" not in result.out
        assert "complex_AB" in result.out

    def test_a_sweep_still_gets_its_own_section(self) -> None:
        result = run(
            BINDING, "--no-simulate", "--no-ranking",
            "--sweep", "complex_kon", "--sweep-steps", "4",
        )
        assert result.code == 0
        assert "## Parameter sweeps" in result.out
        assert "Swept complex_kon from 0.1 to 10 in 4 steps" in result.out

    def test_rank_against_still_chooses_the_species_ranked(self) -> None:
        result = run(BINDING, "--no-simulate", "--rank-against", "complex_AB")
        assert result.code == 0
        assert "influence on **steady-state complex_AB**" in result.out

    def test_no_ranking_leaves_the_table_without_an_influence_column(self) -> None:
        result = run(BINDING, "--no-simulate", "--no-ranking")
        assert "| quantity | what it is | unit | source table |" in result.out
        assert "| source table | influence |" not in result.out

    def test_no_analysis_says_so_rather_than_omitting_the_section(self) -> None:
        result = run(BINDING, "--no-analysis", "--no-simulate", "--no-ranking")
        assert "No stability analysis was run." in result.out

    def test_no_simulate_leaves_out_the_time_course(self) -> None:
        result = run(BINDING, "--no-analysis", "--no-simulate", "--no-ranking")
        assert "## Time course" not in result.out

    def test_the_module_runs_from_a_terminal(self) -> None:
        """The claim this whole file is about, and the only test that proves it.

        An in-process `main([...])` never touches the `python -m` entry, so
        it would keep passing if the module stopped being executable.
        """
        result = subprocess.run(
            [sys.executable, "-m", "Terium.compose", "--shapes"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "phosphorylation_cascade" in result.stdout


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExport:
    def test_the_parameter_csv_has_its_header_and_nothing_before_it(self) -> None:
        """A commented preamble would be friendlier and would break csv.reader.

        Which is why `--export` takes over stdout instead of appending the
        artefact to a report: a CSV with markdown in front of it is a CSV
        no parser reads.
        """
        result = run(BINDING, "--export", "csv")
        assert result.code == 0
        assert result.out.splitlines()[0].startswith("identifier,role,origin,")

    def test_the_methods_paragraph_is_markdown_ready_to_paste(self) -> None:
        result = run(BINDING, "--export", "methods")
        assert result.code == 0
        assert result.out.startswith("## Methods")

    def test_the_annotated_antimony_carries_every_value_s_origin(self) -> None:
        # The difference from --antimony, which emits the compiled source
        # with no provenance on it at all.
        result = run(BINDING, "--export", "antimony")
        assert result.code == 0
        assert "CHOSEN" in result.out

    @needs_sbml
    def test_the_sbml_is_sbml(self) -> None:
        result = run(BINDING, "--export", "sbml")
        assert result.code == 0
        assert result.out.lstrip().startswith("<?xml")
        assert "<sbml" in result.out

    def test_an_unrecognised_shape_still_exits_three(self) -> None:
        # The refusal path reaches the export route too: there is no model
        # to export, and that is a refusal with information in it rather
        # than a crash.
        result = run("glycolysis", "--export", "csv")
        assert result.code == 3
        assert "Not built." in result.err

    def test_export_will_not_silently_drop_an_analysis_asked_for(self) -> None:
        """Rejected, not ignored, and the message says what to do instead.

        `--export csv --scale` has no honest output: the scale report
        cannot go in the CSV and the CSV cannot carry it.
        """
        out, err = io.StringIO(), io.StringIO()
        with pytest.raises(SystemExit) as raised:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                main([BINDING, "--export", "csv", "--scale"])
        assert raised.value.code == 2
        assert "two commands" in err.getvalue()

    def test_export_and_antimony_do_not_both_take_stdout(self) -> None:
        # Both write one artefact and nothing else, and they write
        # different ones: --antimony the compiled source, --export antimony
        # the same model with every value's origin beside it.
        out, err = io.StringIO(), io.StringIO()
        with pytest.raises(SystemExit) as raised:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                main([BINDING, "--export", "antimony", "--antimony"])
        assert raised.value.code == 2
        assert "Pick one." in err.getvalue()

    def test_an_unknown_format_is_rejected_by_the_parser(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with pytest.raises(SystemExit) as raised:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                main([BINDING, "--export", "matlab"])
        assert raised.value.code == 2
        assert "matlab" in err.getvalue()


# ---------------------------------------------------------------------------
# The parser, where the arithmetic is cheap enough to check directly
# ---------------------------------------------------------------------------


class TestTheParser:
    def test_robustness_distinguishes_absent_from_present_without_a_number(
        self,
    ) -> None:
        """Three states, and argparse can only give `None` to one of them.

        `--robustness` with no count has to mean "the module's default",
        which is not the same as the flag being absent. A single `None`
        for both would silently resample every model anyone ever asked
        anything about.
        """
        parser = build_parser()
        assert parser.parse_args([BINDING]).robustness is None
        assert parser.parse_args(
            [BINDING, "--robustness"]
        ).robustness == SAMPLES_UNSTATED
        assert parser.parse_args([BINDING, "--robustness", "7"]).robustness == 7

    def test_the_sentinel_cannot_be_mistaken_for_a_sample_count(self) -> None:
        # It is negative on purpose: any real count is at least 1, so no
        # user-supplied number can collide with it.
        assert SAMPLES_UNSTATED < 1

    def test_knockout_and_overexpress_are_repeatable(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [BINDING, "--knockout", "a", "--knockout", "b", "--overexpress", "c"]
        )
        assert args.knockout == ["a", "b"]
        assert args.overexpress == ["c"]

    def test_the_ssa_seed_distinguishes_absent_from_zero(self) -> None:
        """`0` is a legitimate seed, so it cannot double as "not given".

        With `default=0` the parser could not tell a typed zero from no
        flag at all, and the check that rejects a modifier with nothing to
        modify would have let `--stochastic-seed 0` through.
        """
        parser = build_parser()
        assert parser.parse_args([BINDING]).stochastic_seed is None
        assert parser.parse_args(
            [BINDING, "--stochastic-seed", "0"]
        ).stochastic_seed == 0
        assert DEFAULT_SEED == 0

    def test_the_stochastic_volume_is_read_as_a_number_of_litres(self) -> None:
        # A string would reach `molecules_per_concentration`, which refuses
        # anything that is not a number -- a worse error message for a
        # mistake argparse can catch.
        args = build_parser().parse_args([BINDING, "--stochastic", "1e-15"])
        assert args.stochastic == pytest.approx(1e-15)
