"""Jeske's conditions, inside the artifact rather than on the screen.

    Reaction conditions: pH value, temperature, cofactors, and buffers play
    a huge role in the reactions. The values in BRENDA come from thousands
    of different papers, each with different laboratory conditions. If you
    simply mix these together, the simulation will end up calculating with
    "fantasy numbers".
        — Lisa Jeske, BRENDA curation team, Leibniz Institute DSMZ

Terrium parsed all of this (ADR 0010, 0026, 0028) and it reached the
screen. Measured before this module existed, the notes on an exported Km
read:

    Reliability [...] assay completeness: complete — pH and temperature
    both reported

The file told a reader the conditions existed and not what they were. The
artifact is what outlives the terminal session — it is shared, attached to
a report, opened months later — so it is exactly where that sentence needed
to survive, and the one place it did not.
"""
from __future__ import annotations

import re

import antimony
import pytest

from Terium.core.model_provenance import ParameterProvenance
from Terium.core.sbml_provenance import SbmlParameterProvenance, annotate_sbml

PLAIN = """model michaelis_menten
  S = 10; P = 0;
  Km = 2.5;
  Vmax = 0.25;
  J0: S -> P; Vmax * S / (Km + S);
end"""

COMPLETE_GRADE = (("assay completeness", "complete", "pH and temperature both reported"),)


@pytest.fixture
def base_sbml() -> str:
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(PLAIN) >= 0, antimony.getLastError()
    return antimony.getSBMLString(antimony.getMainModuleName())


def notes_for(sbml: str, prov: SbmlParameterProvenance, parameter: str = "Km") -> str:
    """The parameter's notes as flat readable text."""
    out = annotate_sbml(sbml, {parameter.lower(): prov})
    block = re.search(rf'<parameter[^>]*id="{parameter}".*?</parameter>', out.sbml, re.S)
    assert block, f"no {parameter} parameter in the emitted SBML"
    body = re.search(r"<notes>(.*?)</notes>", block.group(0), re.S)
    assert body, f"no notes on {parameter}"
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.group(1))).strip()


# ---------------------------------------------------------------------------
# The conditions reach the file
# ---------------------------------------------------------------------------


def test_the_values_are_in_the_exported_model(base_sbml):
    """Not "both reported" — the numbers."""
    text = notes_for(
        base_sbml,
        SbmlParameterProvenance(
            origin="resolved", citation="BRENDA ref 740253",
            assay_ph=7.4, assay_temperature_c=25.0, assay_buffer="Tris-HCl",
        ),
    )
    assert "pH 7.4" in text
    assert "25 °C" in text
    assert "Tris-HCl" in text


def test_a_condition_the_source_did_not_report_is_named(base_sbml):
    """An omitted line reads as an oversight by whoever made the file.

    A line saying the source is silent is a fact about the publication,
    and it is the fact ADR 0010 exists to preserve. `assay_ph=None` alone
    cannot carry it.
    """
    text = notes_for(
        base_sbml,
        SbmlParameterProvenance(
            origin="resolved", assay_ph=7.4,
            assay_unreported=("temperature", "buffer"),
        ),
    )
    assert "Not reported by the source: temperature, buffer" in text
    assert "STRENDA" in text


def test_nothing_is_said_when_nothing_is_known(base_sbml):
    """A conditions line on every parameter of a model whose conditions
    were never parsed is noise, and noise is how the lines that matter
    stop being read (ADR 0028)."""
    text = notes_for(base_sbml, SbmlParameterProvenance(origin="resolved"))
    assert "Measured at" not in text
    assert "Not reported by the source" not in text


def test_a_condition_cannot_be_both_reported_and_unreported(base_sbml):
    """A payload can say both. The file must not.

    Hand-assembled payloads arrive in this shape, and a document stating
    "measured at pH 7.4" and "the source did not report ph" in adjacent
    sentences teaches a reader to stop believing either.
    """
    text = notes_for(
        base_sbml,
        SbmlParameterProvenance(
            origin="resolved", assay_ph=7.4,
            assay_unreported=("ph", "temperature"),
        ),
    )
    assert "pH 7.4" in text
    assert "Not reported by the source: temperature" in text
    assert "ph, temperature" not in text.lower().replace("ph 7.4", "")


# ---------------------------------------------------------------------------
# The grade and the values are two encodings of one fact
# ---------------------------------------------------------------------------


def test_a_completeness_claim_with_no_conditions_says_it_cannot_show_its_working(
    base_sbml,
):
    text = notes_for(
        base_sbml, SbmlParameterProvenance(origin="resolved", reliability=COMPLETE_GRADE)
    )
    assert "not supplied to this export" in text
    assert "nothing here demonstrates it" in text


def test_a_completeness_claim_contradicted_by_the_source_says_which_to_trust(
    base_sbml,
):
    """The two failures need different sentences.

    A grade contradicted by the source is a defect in the scoring; a grade
    whose conditions never reached the export is a defect in the payload.
    Telling a reader only "inconsistent" leaves them unable to act on
    either.
    """
    text = notes_for(
        base_sbml,
        SbmlParameterProvenance(
            origin="resolved", reliability=COMPLETE_GRADE,
            assay_ph=7.4, assay_unreported=("temperature",),
        ),
    )
    assert "Both cannot be true" in text
    assert "Trust the statement about the source" in text
    assert "not supplied to this export" not in text


def test_no_discrepancy_is_reported_when_there_is_none(base_sbml):
    """The common case must stay silent, or the warning is worthless."""
    text = notes_for(
        base_sbml,
        SbmlParameterProvenance(
            origin="resolved", reliability=COMPLETE_GRADE,
            assay_ph=7.4, assay_temperature_c=25.0,
        ),
    )
    assert "Both cannot be true" not in text
    assert "not supplied to this export" not in text


def test_an_ungraded_parameter_is_not_nagged_about_conditions(base_sbml):
    """No grade means no claim, so there is nothing to contradict."""
    text = notes_for(base_sbml, SbmlParameterProvenance(origin="resolved", citation="x"))
    assert "grade says" not in text


# ---------------------------------------------------------------------------
# Both artifacts, or neither
# ---------------------------------------------------------------------------


def test_the_antimony_footer_carries_the_same_conditions():
    """A fact present in one export and missing from the other is worse
    than one absent from both: it makes the omission look like a property
    of the measurement rather than of the export path."""
    prov = ParameterProvenance(
        origin="resolved", citation="BRENDA ref 740253",
        assay_ph=7.4, assay_temperature_c=25.0, assay_buffer="Tris-HCl",
    )
    line = prov.assay_line()
    assert line is not None
    assert "pH 7.4" in line and "25 C" in line and "Tris-HCl" in line
    assert line in prov.detail_lines()


def test_the_antimony_footer_names_what_the_source_omitted():
    prov = ParameterProvenance(
        origin="resolved", assay_ph=7.4, assay_unreported=("temperature",)
    )
    assert "NOT REPORTED by the source: temperature" in (prov.assay_line() or "")


def test_the_antimony_footer_is_silent_when_nothing_is_known():
    assert ParameterProvenance(origin="resolved").assay_line() is None


def test_both_exports_agree_about_one_parameter():
    """The two renderers, run on the same facts, must not disagree.

    Not asserting identical strings — one is an Antimony comment and one is
    XHTML, and forcing them to match character for character would be a
    style rule rather than a correctness one. Asserting that the same
    FACTS appear in both.
    """
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(PLAIN) >= 0
    sbml = antimony.getSBMLString(antimony.getMainModuleName())

    shared = dict(assay_ph=7.4, assay_temperature_c=25.0, assay_unreported=("buffer",))
    comment = ParameterProvenance(origin="resolved", **shared).assay_line() or ""
    notes = notes_for(sbml, SbmlParameterProvenance(origin="resolved", **shared))

    for fact in ("7.4", "25", "buffer"):
        assert fact in comment, f"{fact} missing from the Antimony footer"
        assert fact in notes, f"{fact} missing from the SBML notes"
