"""The attribution block in an exported model.

Jeske raised BRENDA's CC BY 4.0 obligations; `NOTICE` answers them for the
repository. These tests cover the part `NOTICE` cannot reach — the model
file, which leaves without it.

The assertions are written against the licence clauses rather than against
the current wording, so rephrasing the block does not fail them but dropping
a required element does.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from caterva.core.data_sources import (  # noqa: E402
    SOURCES,
    attribution_lines,
    sources_used,
)
from caterva.core.model_provenance import (  # noqa: E402
    ParameterProvenance,
    annotate_antimony,
    strip_annotations,
)

def flatten(lines) -> str:
    """Comment block to one line, stripping the marker at LINE STARTS only.

    `text.replace("//", " ")` also eats the `//` in `https://`, so a URL
    assertion written against it passes or fails for the wrong reason. The
    first version of these tests did that, and
    `test_both_encodings_state_the_same_licence` failed on a licence URI
    that was present -- the helper had mangled it, not the renderer.
    """
    if not isinstance(lines, str):
        lines = "\n".join(lines)
    stripped = [re.sub(r"^\s*//\s?", "", line) for line in lines.splitlines()]
    return " ".join(" ".join(stripped).split())


MODEL = "model m\n  J0: S -> P; Vmax * S / (Km + S);\n  Km = 2.5;\n  S = 1.0;\nend\n"


def brenda(**kwargs) -> ParameterProvenance:
    return ParameterProvenance(
        origin="resolved",
        citation=kwargs.pop("citation", "BRENDA ref 740253"),
        source=kwargs.pop("source", "brenda_exact"),
        **kwargs,
    )


def user() -> ParameterProvenance:
    return ParameterProvenance(origin="user")


# ---------------------------------------------------------------------------
# What CC BY 4.0 3(a)(1) asks to be retained
# ---------------------------------------------------------------------------


def test_the_block_carries_every_element_the_licence_asks_for() -> None:
    """3(a)(1)(A) creator, (C) licence + URI, (A)(v) source URI, (B) changes.

    Asserted element by element rather than against a fixed string: the
    wording is allowed to change, the elements are not.
    """
    source = next(s for s in SOURCES if s.tokens[0] == "brenda")

    flat = flatten(attribution_lines({"km": brenda()}))
    assert " ".join(source.creator.split()) in flat, "3(a)(1)(A)(i) creator"
    assert "CC BY 4.0" in flat, "3(a)(1)(C) the licence"
    assert "creativecommons.org/licenses/by/4.0" in flat, "3(a)(1)(C) licence URI"
    assert "brenda-enzymes.org" in flat, "3(a)(1)(A)(v) URI to the material"
    assert "filtered" in flat, "3(a)(1)(B) indication of modification"
    assert "NOTICE" in flat, "3(a)(2) pointer to the full information"


def test_the_block_disclaims_endorsement() -> None:
    """2(a)(6) forbids implying the licensor endorses this use.

    Not boilerplate here: a researcher already read a Caterva outreach email
    as claiming credit that was not ours, and a block naming DSMZ beside
    Caterva's generated numbers is the same shape. The disclaimer is load
    bearing.
    """
    flat = flatten(attribution_lines({"km": brenda()})).lower()
    assert "endorse" in flat
    assert "caterva's, not theirs" in flat


# ---------------------------------------------------------------------------
# Crediting only what actually contributed
# ---------------------------------------------------------------------------


def test_a_model_with_no_resolved_values_credits_nobody() -> None:
    """Naming a source that contributed nothing is a false provenance claim,
    and under 2(a)(6) it is also the endorsement the licence forbids
    implying. Silence is correct here."""
    assert attribution_lines({"km": user(), "s0": user()}) == []


def test_a_source_is_credited_only_when_it_appears_in_the_provenance() -> None:
    used = {s.tokens[0] for s, _ in sources_used({"km": brenda()}) if s}
    assert used == {"brenda"}, (
        "NCBI Taxonomy is described in the table but contributed nothing to "
        "this model, so it must not be credited"
    )


def test_an_undescribed_source_is_named_not_dropped() -> None:
    """A source with no licence record must not render the same as no
    source at all. Three-state discipline: "we do not know the terms" is
    not "there are no terms"."""
    entry = ParameterProvenance(
        origin="resolved", citation="SABIO-RK ref 41221", source="sabio_rk"
    )
    flat = flatten(attribution_lines({"km": entry}))
    assert "SABIO-RK ref 41221" in flat
    assert "NOT RECORDED" in flat


def test_user_and_structural_notes_are_not_mistaken_for_databases() -> None:
    """The guard must not cry wolf on the common case.

    `origin: user` and a model-structure note are not sources, and an
    "unknown licence" warning on every hand-supplied value would train a
    reader to ignore the block — the reasoning ADR 0028 used for buffers.
    """
    entries = {
        "s0": user(),
        "p": ParameterProvenance(
            origin="user",
            note="model structure: fixed by the model definition, not measured",
        ),
    }
    assert attribution_lines(entries) == []


# ---------------------------------------------------------------------------
# The block must not damage the model
# ---------------------------------------------------------------------------


def test_attribution_does_not_change_the_model() -> None:
    """The property the whole annotator is built around. A licence notice
    that alters a simulation would be a worse defect than the one it fixes."""
    result = annotate_antimony(MODEL, {"km": brenda(), "s0": user()})
    assert "DATA SOURCES" in result.text, "premise: the block was actually added"
    assert strip_annotations(result.text) == MODEL


def test_the_block_reaches_a_real_annotated_model() -> None:
    """Rendering it in isolation proves nothing about delivery — the shape
    of ADR 0027, where a score was computed correctly and discarded at the
    boundary."""
    text = annotate_antimony(MODEL, {"km": brenda()}).text
    assert "CC BY 4.0" in text
    assert "brenda-enzymes.org" in text


@pytest.mark.parametrize("line", MODEL.strip().splitlines())
def test_every_original_line_survives_annotation(line: str) -> None:
    text = annotate_antimony(MODEL, {"km": brenda()}).text
    assert line.rstrip(";").split(";")[0].strip() in text


# ---------------------------------------------------------------------------
# SBML — the format that travels furthest
# ---------------------------------------------------------------------------


def test_the_sbml_export_carries_the_attribution() -> None:
    """`build_sbml` strips the Antimony comments before converting, rightly
    — so the credit has to be restated in SBML's own idiom or the most
    portable export is the one with none.

    Measured before the fix: the SBML named `BRENDA ref 740253` and carried
    no licence, no licensor and no URI.
    """
    libsbml = pytest.importorskip(
        "libsbml", reason="python-libsbml is required to build SBML"
    )
    from caterva.core.sbml_provenance import SbmlParameterProvenance, annotate_sbml

    plain = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" '
        'level="3" version="1"><model id="m">'
        '<listOfParameters>'
        '<parameter id="Km" value="2.5" constant="true"/>'
        "</listOfParameters></model></sbml>"
    )
    outcome = annotate_sbml(
        plain,
        {
            "Km": SbmlParameterProvenance(
                origin="resolved",
                citation="BRENDA ref 740253",
                source="brenda_exact",
            )
        },
    )
    assert "CC BY 4.0" in outcome.sbml
    assert "Leibniz" in outcome.sbml
    assert "endorsed" in outcome.sbml

    # It must still be valid SBML. A licence notice that breaks the file it
    # is in is worse than no notice.
    document = libsbml.readSBMLFromString(outcome.sbml)
    fatal = [
        document.getError(i).getMessage()
        for i in range(document.getNumErrors())
        if document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
    ]
    assert not fatal, fatal
    assert document.getModel().isSetNotes()


def test_an_sbml_model_from_user_values_carries_no_attribution() -> None:
    pytest.importorskip("libsbml")
    from caterva.core.sbml_provenance import SbmlParameterProvenance, annotate_sbml

    plain = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" '
        'level="3" version="1"><model id="m">'
        '<listOfParameters>'
        '<parameter id="Km" value="2.5" constant="true"/>'
        "</listOfParameters></model></sbml>"
    )
    outcome = annotate_sbml(
        plain, {"Km": SbmlParameterProvenance(origin="user")}
    )
    assert "CC BY" not in outcome.sbml
    assert not outcome.sbml.count("DATA SOURCES")


def test_both_encodings_state_the_same_licence() -> None:
    """The Antimony comments and the SBML notes are two encodings of one
    fact, which is the shape that drifts (ADR 0003, ADR 0027). They are
    rendered from `attribution_fields`, and this asserts they agree."""
    from caterva.core.data_sources import attribution_fields, attribution_xhtml

    provenance = {"km": brenda()}
    comments = flatten(attribution_lines(provenance))
    xhtml = " ".join(attribution_xhtml(provenance).split())

    for _subject, fields in attribution_fields(provenance):
        for _label, value in fields:
            flat = " ".join(value.split())
            assert flat in comments, f"missing from Antimony: {flat!r}"
            assert flat.replace("'", "&apos;") in xhtml or flat in xhtml, (
                f"missing from SBML notes: {flat!r}"
            )
