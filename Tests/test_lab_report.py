"""One document a student can hand in.

Caterva had nine capabilities and nothing a person could give a teacher.
The resolver, the provenance, the assay conditions, the reliability grades,
the ensemble, the BibTeX exporter, the annotated model and the engine were
each an answer to a question nobody asks in isolation.

The assertions here are mostly about what the document REFUSES to leave
out. A report that silently omits what could not be sourced is this
project's own defect at document scale — computed, correct, undelivered —
and it is the section that distinguishes a Caterva report from a printout.
"""
from __future__ import annotations

import pytest

from fallback_logic import resolve_kinetic_value
from fixture_lineages import fixture_lineage_provider
from lab_report import SuppliedValue, build_report
from spread_consequence import consequence_of
from test_fallback_logic import (
    fake_taxon_id_provider,
    fake_uniprot_provider,
    load_fixture,
    make_html_provider,
)

LDH = "1.1.1.27"


def ask(substrate: str, organism: str = "Homo sapiens", quantity: str = "km"):
    return resolve_kinetic_value(
        LDH, organism, substrate,
        html_provider=make_html_provider(
            {LDH: load_fixture("brenda_ldh_fixture.html")}
        ),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False, allow_cross_species=False,
        quantity=quantity, lineage_provider=fixture_lineage_provider,
    )


def report(**overrides):
    kwargs = dict(
        title="Human LDH",
        question="How fast is lactate consumed?",
        resolved={"km": ask("lactate")},
        supplied=[SuppliedValue(name="s0", value=10.0, unit="mM")],
    )
    kwargs.update(overrides)
    return build_report(**kwargs)


# ---------------------------------------------------------------------------
# A sourced number and a chosen number are never the same kind of thing
# ---------------------------------------------------------------------------


def test_a_literature_value_carries_its_citation_into_the_document():
    text = report().markdown
    assert "10.73" in text
    assert "BRENDA ref 740253" in text


def test_a_value_the_student_chose_is_marked_as_theirs():
    """`s0` is the experiment, not the enzyme.

    Presenting it in one undifferentiated table with a Km is how a reader
    comes to believe the tool sourced something it did not — the failure
    the whole provenance layer exists to prevent.

    ASSERTED ON THE ROW, NOT THE DOCUMENT. The first version checked
    `"**yours**" in text`, and mutation showed what that was worth:
    labelling supplied values `literature` in the table left it green,
    because the explanatory sentence *below* the table contains the words
    "A value marked **yours** describes the experiment". The assertion
    matched the prose that is always there.

    Third time this session that explanatory prose has handed a test
    something to match for free.
    """
    text = report().markdown
    row = next(line for line in text.splitlines() if line.startswith("| s0 "))
    assert "**yours**" in row, f"s0 is not marked as the student's: {row}"
    assert "literature" not in row
    assert "describes the experiment, not the enzyme" in text


def test_the_two_kinds_are_counted_separately():
    result = report()
    assert result.sourced == ["km"]
    assert result.supplied == ["s0"]


# ---------------------------------------------------------------------------
# The section that makes it a Caterva report
# ---------------------------------------------------------------------------


def test_an_unsourced_parameter_becomes_a_refusal_rather_than_a_gap():
    """A parameter that quietly vanishes is indistinguishable from one
    nobody asked about. The student cannot defend a gap they cannot see."""
    result = report(resolved={"km": ask("lactate"), "ki": ask("lactate", quantity="ki")})

    assert any(r.startswith("ki:") for r in result.refusals)
    assert "## What Caterva would not do" in result.markdown
    assert "These are not omissions" in result.markdown


def test_an_unsourced_parameter_still_has_a_row_in_the_table():
    """The refusal below is not a substitute for the row above.

    A reader scanning the Parameters table for `ki` must find it there,
    marked, rather than have to notice its absence and go looking. Absence
    is precisely what a reader cannot see.

    WHY THIS EXISTS SEPARATELY FROM THE TEST ABOVE
    ----------------------------------------------
    Deleting the `not sourced` row while leaving the refusals section intact
    passed all 16 tests in this file. `scripts/mutate.py` reported it NOT
    CAUGHT while re-deriving ADR 0133's table, which had claimed the
    behaviour was covered.

    The two halves are separate code paths -- one renders the table, one
    builds the refusal list -- and testing the second says nothing about the
    first. That is ADR 0038's rule about call sites, applied inside a single
    function.
    """
    result = report(resolved={"km": ask("lactate"), "ki": ask("lactate", quantity="ki")})

    rows = [
        line for line in result.markdown.splitlines() if line.startswith("| ki |")
    ]
    assert rows, "the unsourced parameter has no row in the Parameters table"
    assert "not sourced" in rows[0]
    # Points at where the reason lives, so the row is actionable on its own.
    assert "What Caterva would" in rows[0]


def test_a_withheld_cross_species_value_says_so_and_says_why():
    """Not "no value" — a value EXISTS and was not substituted. Those are
    different facts with different remedies (ADR 0024)."""
    result = report(resolved={"km": ask("pyruvate", organism="Danio rerio")})

    joined = " ".join(result.refusals)
    assert "another organism" in joined
    assert "species-specific" in joined


def test_a_substrate_miss_names_the_labels_that_would_have_worked():
    """The work ADR 0118 did is wasted if the report says only "not found".

    A substrate-name miss is fixable by the reader in one edit; a genuine
    gap is not. Saying "not found" for both discards the distinction the
    resolver established.
    """
    result = report(resolved={"km": ask("L-lactate")})
    joined = " ".join(result.refusals)
    assert "(S)-lactate" in joined
    assert "does not substitute" in joined


def test_the_absence_of_refusals_is_stated_rather_than_left_blank():
    """An empty section reads as an unfinished document. "Nothing was
    withheld" is a claim, and it is the one a reader wants.

    `resolved={}` rather than the shared `report()` fixture, and that is
    the whole point of the test. The default fixture resolves a real km
    whose candidate rows mix diseased and healthy breast tissue, so it
    now carries a source-mixture refusal -- which means this test was
    asserting the no-refusals sentence against a document that had a
    refusal in it, and had been failing rather than covering the branch
    it names. The else-branch in `_refusals_section` was reachable only
    by a report with nothing withheld, and no test built one.

    The refusal list is asserted empty first. Without that, a future
    change that stopped emitting refusals entirely would make this test
    pass for exactly the wrong reason.
    """
    result = report(resolved={})
    assert result.refusals == []
    text = result.markdown
    assert "## What Caterva would not do" in text
    assert (
        "Nothing was withheld: every parameter resolved to a cited value "
        "or was supplied by you." in text
    )


def test_a_preparation_caveat_reaches_the_report():
    """ADR 0092: the value returned may be an immobilised or tagged
    enzyme's. That belongs in a document somebody submits."""
    ki = resolve_kinetic_value(
        LDH, "Homo sapiens", "NADH",
        html_provider=make_html_provider(
            {LDH: load_fixture("brenda_ldh_ki_fixture.html")}
        ),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False, allow_cross_species=False,
        quantity="ki", lineage_provider=fixture_lineage_provider,
    )
    if not (ki.preparation and ki.preparation.differs_from_the_free_enzyme):
        pytest.skip("this fixture's winning row is not a modified preparation")

    result = report(resolved={"ki": ki})
    assert any("not the free enzyme" in r for r in result.refusals)


# ---------------------------------------------------------------------------
# The conditions, because Jeske's sentence is the whole risk
# ---------------------------------------------------------------------------


def test_the_conditions_each_value_was_measured_under_are_shown():
    text = report().markdown
    assert "## Conditions the values were measured under" in text
    assert "pH 8" in text


def test_a_condition_the_source_did_not_report_is_named():
    """An omitted line reads as an oversight by whoever made the document.
    A line saying the source is silent is a fact about the publication."""
    text = report().markdown
    assert "did not report" in text


# ---------------------------------------------------------------------------
# Disagreement is quoted from the module that owns the reasoning
# ---------------------------------------------------------------------------


def test_an_ensemble_is_quoted_not_paraphrased():
    """`spread_consequence` argued over that sentence. A second wording
    here would be a second claim, and the two would drift (ADR 0003)."""
    withheld = ask("pyruvate", organism="Danio rerio")
    verdict = consequence_of(
        withheld.cross_species_candidates, parameter="km", vmax=0.25, s0=10.0
    )
    result = report(resolved={"km": withheld}, ensembles={"km": verdict})

    assert "km" in result.disagreements
    assert verdict.reason in result.markdown, "the reason was reworded"
    assert "NOT an uncertainty estimate" in result.markdown


def test_every_candidate_value_appears_with_its_outcome():
    withheld = ask("pyruvate", organism="Danio rerio")
    verdict = consequence_of(
        withheld.cross_species_candidates, parameter="km", vmax=0.25, s0=10.0
    )
    text = report(resolved={"km": withheld}, ensembles={"km": verdict}).markdown
    for candidate in withheld.cross_species_candidates:
        assert f"{candidate.value:.6g}" in text


# ---------------------------------------------------------------------------
# The run and the bibliography
# ---------------------------------------------------------------------------


def test_the_trajectory_is_summarised_not_dumped():
    """A lab report is not a data dump. First and last row, and a pointer
    to the CSV for the rest."""

    class Trajectory:
        colnames = ["time", "[S]", "[P]"]
        data = [[0.0, 10.0, 0.0], [5.0, 6.0, 4.0], [10.0, 3.0, 7.0]]

    text = report(simulation=Trajectory()).markdown
    assert "## Result" in text
    assert "3 time points" in text
    assert "| 0 | 10 | 0 |" in text
    assert "| 10 | 3 | 7 |" in text
    assert "| 5 | 6 | 4 |" not in text, "the middle of the trajectory was dumped"


def test_the_bibliography_is_embedded_for_a_reference_manager():
    text = report(bibtex="@misc{brenda740253,\n  title = {x}\n}").markdown
    assert "```bibtex" in text
    assert "brenda740253" in text
    assert "absent rather than invented" in text


def test_no_bibliography_section_when_there_is_nothing_to_cite():
    """An empty "Citations" heading implies sources that do not exist."""
    assert "## Citations" not in report(bibtex=None).markdown


# ---------------------------------------------------------------------------
# The claim the document makes about itself
# ---------------------------------------------------------------------------


def test_an_empty_report_is_not_called_defensible():
    """A POSITIVE test. `not refusals` would call a report with no
    parameters at all defensible, and an empty report is not a strong one —
    it is an empty one.
    """
    empty = build_report(title="t", question="q", resolved={}, supplied=[])
    assert not empty.is_defensible
    assert report().is_defensible


# ---------------------------------------------------------------------------
# How the document says it was produced.
#
# The band section already claimed "Seed N — re-running with it reproduces
# this band exactly." True, and unusable: re-running with WHICH version? A
# report carried no commit, no date, no command. For a tool whose entire
# argument is that its numbers can be re-derived, that is the house defect
# at the worst address — the claim delivered, the means withheld.
# ---------------------------------------------------------------------------

import lab_report as _lab_report


def test_a_report_records_the_commit_and_the_time():
    report = build_report(
        title="t", question="q", resolved={}, supplied=[
            SuppliedValue(name="s0", value=10.0, unit="mM")
        ],
    )
    assert "## How this document was produced" in report.markdown
    assert "Caterva commit" in report.markdown
    assert "Generated" in report.markdown


def test_a_dirty_tree_is_not_reported_as_a_commit(monkeypatch):
    """The state that matters, and the easy one to get wrong.

    Printing `commit abc1234` while the tree has uncommitted changes is the
    most confident kind of wrong: a reader checks out abc1234, gets
    different numbers, and cannot discover why. The code that ran was not
    that commit.
    """
    monkeypatch.setattr(
        _lab_report, "_code_version",
        lambda: ("abc1234 plus 3 uncommitted change(s)", "the working tree was modified"),
    )
    report = build_report(title="t", question="q", resolved={})

    assert "not reproducible as it stands" in report.markdown
    # And it must NOT also print the invitation to check the commit out.
    assert "should come back identical" not in report.markdown


def test_a_clean_tree_says_how_to_reproduce(monkeypatch):
    monkeypatch.setattr(_lab_report, "_code_version", lambda: ("abc1234", None))
    report = build_report(title="t", question="q", resolved={})

    assert "`abc1234`" in report.markdown
    assert "should come back identical" in report.markdown
    # No warning attached to a clean run: a caveat that fires on the
    # ordinary case is one nobody reads on the case that matters (ADR 0028).
    assert "not reproducible as it stands" not in report.markdown


def test_not_a_git_checkout_is_its_own_answer(monkeypatch):
    """'I do not know' must not render as a blank a reader takes for
    'nothing to report'. A tarball install is a real way to run this."""
    monkeypatch.setattr(
        _lab_report, "_code_version",
        lambda: ("unknown", "this is not a git checkout"),
    )
    report = build_report(title="t", question="q", resolved={})

    assert "`unknown`" in report.markdown
    assert "not reproducible as it stands" in report.markdown


def _git(*args, cwd):
    import subprocess
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def test_the_dirty_tree_DETECTION_works_against_a_real_repository(tmp_path):
    """Drives `_code_version` itself, not a stub of it.

    The four tests above monkeypatch `_code_version` wholesale, so they
    check the RENDERING. Deleting the dirty-tree branch left every one of
    them passing — verified by mutation, and it is the exact shape this
    project keeps recording: a test of the wording standing in for a test of
    the logic.
    """
    _git("init", "-q", cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=tmp_path)
    _git("config", "user.name", "t", cwd=tmp_path)
    (tmp_path / "a.txt").write_text("one\n")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-qm", "first", cwd=tmp_path)

    version, caveat = _lab_report._code_version(tmp_path)
    assert caveat is None, f"a clean checkout reported a caveat: {caveat}"
    assert "uncommitted" not in version

    (tmp_path / "a.txt").write_text("two\n")
    version, caveat = _lab_report._code_version(tmp_path)
    assert caveat is not None, "a modified tree was reported as reproducible"
    assert "uncommitted change" in version


def test_a_directory_that_is_not_a_repository_says_so(tmp_path):
    version, caveat = _lab_report._code_version(tmp_path)
    assert version == "unknown"
    assert caveat and "not a git checkout" in caveat
