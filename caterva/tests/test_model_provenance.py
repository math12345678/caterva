"""Provenance written into the model file — ADR 0024 / Sauro's mechanism.

The load-bearing test in this file is `test_annotation_does_not_change_the
_model`. Everything else is about wording; that one is about whether a
comment can silently alter a simulation.
"""
from __future__ import annotations

import pytest

from caterva.continuous.model_building import (
    antimony_to_sbml,
    build_michaelis_menten_antimony,
    build_mm_competitive_antimony,
    build_sir_antimony,
)
from caterva.core.model_provenance import (
    NO_PROVENANCE_MARKER,
    ParameterProvenance,
    annotate_antimony,
    parameters_in,
    strip_annotations,
    unsourced_parameters,
)

RESOLVED_KM = ParameterProvenance(
    origin="resolved",
    citation="BRENDA ref 740253",
    organism="Homo sapiens",
    source="brenda_exact",
    citation_status="verified",
    reliability=(("assay completeness", "complete"), ("organism match", "exact")),
)

CROSS_SPECIES_VMAX = ParameterProvenance(
    origin="resolved",
    citation="BRENDA ref 649716",
    organism="Oryctolagus cuniculus",
    source="brenda_cross_species",
    citation_status="flagged",
    cross_species=True,
    reliability=(("organism match", "related"),),
)

USER_S0 = ParameterProvenance(origin="user")

DEFAULTED = ParameterProvenance(
    origin="default", note="no value in BRENDA or PubMed for this system"
)


# ---------------------------------------------------------------------------
# The property everything else depends on
# ---------------------------------------------------------------------------

MODELS = [
    build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0),
    build_mm_competitive_antimony(km=2.5, vmax=5.0, ki=1.2, s0=10.0, i=0.5),
    build_sir_antimony(beta=0.3, gamma=0.1, s0=990.0, i0=10.0, r0_recovered=0.0),
]


@pytest.mark.parametrize("model", MODELS, ids=["mm", "mm_competitive", "sir"])
def test_annotation_does_not_change_the_model(model):
    """Strip the annotations and you must get the original text back.

    A provenance comment that alters the model would be the worst possible
    outcome of this feature: it would change simulation results in the name
    of documenting them, and it would do so in a diff that looks like
    documentation.
    """
    result = annotate_antimony(
        model, {name: RESOLVED_KM for name in parameters_in(model)}
    )
    assert strip_annotations(result.text) == model


@pytest.mark.parametrize("model", MODELS, ids=["mm", "mm_competitive", "sir"])
def test_annotated_model_still_translates_to_sbml(model):
    """Round-tripping the TEXT is not enough.

    `strip_annotations` is our own inverse, so it agreeing with our own
    annotator proves only that the two are consistent with each other.
    Antimony's parser is the independent check, and it is the one that would
    catch a comment token that is not a comment token.
    """
    annotated = annotate_antimony(
        model, {name: RESOLVED_KM for name in parameters_in(model)}
    ).text
    plain_sbml = antimony_to_sbml(model)
    annotated_sbml = antimony_to_sbml(annotated)

    # Compare the parsed model, not the SBML text: libsbml embeds
    # timestamps and notes that differ between calls.
    assert plain_sbml.count("<parameter") == annotated_sbml.count("<parameter")
    assert plain_sbml.count("<species") == annotated_sbml.count("<species")
    assert plain_sbml.count("<reaction") == annotated_sbml.count("<reaction")


def test_annotation_is_idempotent_on_the_model_itself():
    """Annotating twice must not double the model, whatever it does to the
    comments. Guards the case where a caller pipes an exported file back in."""
    model = MODELS[0]
    once = annotate_antimony(model, {"Km": RESOLVED_KM}).text
    twice = annotate_antimony(once, {"Km": RESOLVED_KM}).text
    assert strip_annotations(twice) == model


# ---------------------------------------------------------------------------
# Silence is the failure mode
# ---------------------------------------------------------------------------

def test_a_parameter_with_no_provenance_is_marked_not_left_bare():
    """The single most likely way an unsourced number escapes.

    A file where three parameters carry citations and the fourth carries
    nothing reads as a file where the fourth was fine.
    """
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(model, {"Km": RESOLVED_KM})

    lines = {
        line.split("=")[0].strip(): line
        for line in result.text.splitlines()
        if "=" in line and not line.strip().startswith("//")
    }
    assert NO_PROVENANCE_MARKER in lines["Vmax"]
    assert NO_PROVENANCE_MARKER in lines["S"]
    assert NO_PROVENANCE_MARKER not in lines["Km"]


def test_every_assignment_carries_a_comment():
    """No bare assignment survives annotation, whatever its provenance."""
    model = build_mm_competitive_antimony(
        km=2.5, vmax=5.0, ki=1.2, s0=10.0, i=0.5
    )
    result = annotate_antimony(model, {"Km": RESOLVED_KM, "Vmax": CROSS_SPECIES_VMAX})

    for line in result.text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if "=" in stripped and stripped.endswith(";"):
            pytest.fail(f"assignment left without a provenance comment: {stripped!r}")


# ---------------------------------------------------------------------------
# Wording that has to survive
# ---------------------------------------------------------------------------

def test_cross_species_is_shouted_on_the_assignment_line():
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(model, {"Vmax": CROSS_SPECIES_VMAX})
    vmax_line = next(
        line for line in result.text.splitlines()
        if line.strip().startswith("Vmax =")
    )
    assert "CROSS-SPECIES" in vmax_line
    assert "Oryctolagus cuniculus" in vmax_line


def test_a_user_supplied_value_is_not_dressed_up_as_a_measurement():
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(model, {"S": USER_S0})
    s_line = next(
        line for line in result.text.splitlines() if line.strip().startswith("S =")
    )
    assert "supplied by you" in s_line
    assert "BRENDA" not in s_line


def test_a_default_says_it_is_not_sourced():
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(model, {"Km": DEFAULTED})
    km_line = next(
        line for line in result.text.splitlines() if line.strip().startswith("Km =")
    )
    assert "DEFAULT, not sourced" in km_line
    assert "no value in BRENDA" in km_line


def test_header_explains_the_markers_it_uses():
    """A marker a reader cannot decode is decoration."""
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    header = annotate_antimony(model, {}, query="simulate mm", run_id="abc123").text
    assert "CROSS-SPECIES" in header
    assert NO_PROVENANCE_MARKER in header
    assert "simulate mm" in header
    assert "abc123" in header


def test_footer_lists_every_citation_in_full():
    """The inline trailer is a summary. Someone re-finding the source needs
    the whole record, and needs it without the original terminal."""
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(
        model, {"Km": RESOLVED_KM, "Vmax": CROSS_SPECIES_VMAX}
    )
    assert "PROVENANCE IN FULL" in result.text
    assert "BRENDA ref 740253" in result.text
    assert "BRENDA ref 649716" in result.text
    assert "reliability / assay completeness: complete" in result.text


# ---------------------------------------------------------------------------
# Disagreement between the resolver and the model
# ---------------------------------------------------------------------------

def test_provenance_for_a_parameter_that_is_not_in_the_model_is_reported():
    """Not dropped. A silent drop hides a real disagreement: the reader gets
    a complete-looking file that omits a parameter somebody believed they
    had sourced."""
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(model, {"Km": RESOLVED_KM, "Ki": RESOLVED_KM})

    assert result.unannotated == ("ki",)
    assert "do not appear" in result.text
    assert "ki" in result.text


def test_lookup_is_case_insensitive_between_resolver_and_model():
    """The resolution layer says `km`, Antimony says `Km`. A case-sensitive
    match would annotate nothing while appearing to work."""
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(model, {"km": RESOLVED_KM, "vmax": CROSS_SPECIES_VMAX})
    assert result.unannotated == ()
    assert set(result.annotated) == {"km", "vmax"}


# ---------------------------------------------------------------------------
# The summary a CLI can print
# ---------------------------------------------------------------------------

def test_unsourced_parameters_finds_every_kind_of_unsourced():
    model = build_mm_competitive_antimony(
        km=2.5, vmax=5.0, ki=1.2, s0=10.0, i=0.5
    )
    result = annotate_antimony(
        model,
        {"Km": RESOLVED_KM, "Vmax": CROSS_SPECIES_VMAX, "Ki": DEFAULTED, "S": USER_S0},
    )
    flagged = set(unsourced_parameters(result.text))

    assert "Vmax" in flagged, "cross-species is not a clean source"
    assert "Ki" in flagged, "a default is not a source"
    assert "I" in flagged, "an unrecorded parameter is not a source"
    assert "Km" not in flagged
    # A user-supplied experimental condition is NOT unsourced -- it is a
    # choice, and it is a category error to ask it for a citation
    # (ADR 0012/0013).
    assert "S" not in flagged


def test_reaction_lines_are_never_mistaken_for_assignments():
    """`J0: S -> P; Vmax * S / (Km + S);` contains parameter names and a
    semicolon. Treating it as an assignment would put a comment in the
    middle of a rate law."""
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    assert "J0" not in parameters_in(model)
    result = annotate_antimony(model, {"Km": RESOLVED_KM})
    reaction = next(line for line in result.text.splitlines() if "J0:" in line)
    assert "//" not in reaction


# ---------------------------------------------------------------------------
# A user citation is not a resolved one
#
# `--cite` exists because Caterva's own refusal told users to hardcode a
# number, which is the outcome Sauro predicted. Recording their source is a
# large improvement. Presenting it with the authority of a BRENDA reference
# would be the most damaging thing the feature could do.
# ---------------------------------------------------------------------------

USER_CITED = ParameterProvenance(
    origin="user_cited",
    citation="Smith 2019, PMID 12345",
)


def test_a_user_citation_says_it_is_unverified_on_the_assignment_line():
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(model, {"Km": USER_CITED})
    km_line = next(
        line for line in result.text.splitlines() if line.strip().startswith("Km =")
    )
    assert "CITED BY YOU" in km_line
    assert "unverified by Caterva" in km_line
    assert "Smith 2019, PMID 12345" in km_line


def test_a_user_citation_is_not_dressed_up_as_a_database_record():
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(model, {"Km": USER_CITED})
    km_line = next(
        line for line in result.text.splitlines() if line.strip().startswith("Km =")
    )
    # The vocabulary of a resolved value must not appear.
    assert "brenda_exact" not in km_line
    assert "CROSS-SPECIES" not in km_line


def test_a_user_citation_still_counts_as_unsourced_in_the_summary():
    """Better than a bare number, and still not something Caterva checked.
    The summary line has to stay honest about what the file rests on."""
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(
        model, {"Km": USER_CITED, "Vmax": RESOLVED_KM, "S": USER_S0}
    )
    flagged = set(unsourced_parameters(result.text))
    assert "Km" in flagged
    assert "Vmax" not in flagged


def test_a_user_citation_with_no_source_text_does_not_print_none():
    """The shape that produced "Both jobs used the undefined model"."""
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    result = annotate_antimony(
        model, {"Km": ParameterProvenance(origin="user_cited")}
    )
    km_line = next(
        line for line in result.text.splitlines() if line.strip().startswith("Km =")
    )
    assert "None" not in km_line
    assert "source not stated" in km_line


def test_the_header_explains_the_new_marker():
    model = build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0)
    header = annotate_antimony(model, {}).text
    assert "CITED BY YOU" in header
    assert "did not check" in header


# ---------------------------------------------------------------------------
# The provenance has to survive being used, not just being read
# ---------------------------------------------------------------------------


def _round_trip(antimony_text: str) -> str:
    """Antimony -> SBML -> Antimony, through the real library.

    The claim under test is about what a conversion keeps, so it is measured
    against the thing that does the converting. A hand-written expectation
    here would be an assertion about my beliefs, not about libSBML.
    """
    import pytest

    antimony = pytest.importorskip(
        "antimony", reason="antimony not installed; see requirements.txt"
    )
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(antimony_text) >= 0, antimony.getLastError()
    sbml = antimony.getSBMLString(antimony.getMainModuleName())
    antimony.clearPreviousLoads()
    assert antimony.loadSBMLString(sbml) >= 0, antimony.getLastError()
    return antimony.getAntimonyString(antimony.getMainModuleName())


def test_comments_do_not_survive_a_conversion_and_notes_do():
    """The measurement this whole change rests on.

    Lucian Smith, asked where per-parameter provenance should live in
    Antimony given that a comment is the intuitive place (personal
    communication, 2026-08-25): "the correct way to add human-readable text
    to an element is to use 'notes'".

    Asserted in BOTH directions on purpose. "The note survives" alone would
    pass on a library that preserved everything, and would not establish
    that the comment this project used for months was being discarded.
    """
    model = (
        "model demo()\n"
        "  km = 0.31;  // a comment nobody keeps\n"
        '  km notes "a note that is kept"\n'
        "  S = 10;\n"
        "end\n"
    )
    back = _round_trip(model)
    assert "a note that is kept" in back
    assert "a comment nobody keeps" not in back


def test_the_assay_conditions_survive_a_conversion():
    """pH, temperature and buffer are the part that decides comparability.

    They lived only in the footer's "PROVENANCE IN FULL" comment block, so
    every one of them was discarded the first time anyone loaded an exported
    model into a tool -- in the export whose entire purpose is that a value
    travels with its source.
    """
    result = annotate_antimony(
        "model demo()\n  km = 0.31;\nend\n",
        {
            "km": ParameterProvenance(
                origin="resolved",
                citation="BRENDA ref 740253",
                organism="Homo sapiens",
                source="BRENDA",
                assay_ph=7.4,
                assay_temperature_c=30.0,
                assay_buffer="phosphate",
                assay_unreported=("cofactors",),
            )
        },
    )
    back = _round_trip(result.text)
    for fragment in ("740253", "pH 7.4", "30 C", "phosphate", "cofactors",
                     "Homo sapiens"):
        assert fragment in back, f"{fragment!r} was lost in conversion"


def test_an_unsourced_parameter_is_still_marked_after_a_conversion():
    """This file's own rule, applied to the artifact that leaves the building.

    The header says "an absent comment would read as approval, so there is
    never one". That holds only if the marker survives. Without it, a model
    converted once arrives with citations on every parameter but this one,
    and silence beside a number surrounded by sourced ones is the strongest
    endorsement the file can give it.
    """
    result = annotate_antimony(
        "model demo()\n  km = 0.31;\n  S = 10;\nend\n",
        {"km": ParameterProvenance(origin="resolved", citation="BRENDA ref 740253")},
    )
    back = _round_trip(result.text)
    assert "NO PROVENANCE RECORDED" in back


def test_a_quote_in_a_citation_does_not_produce_an_unparseable_model():
    """Antimony has no escape for `"` inside a notes string.

    Measured: `\\"` is a syntax error ("unexpected element name"), so a
    citation containing a quotation mark would produce a model file that
    will not load. A tool that emits a broken model is worse than one that
    emits a plain number, because the failure arrives later and elsewhere.
    """
    result = annotate_antimony(
        "model demo()\n  km = 0.31;\nend\n",
        {
            "km": ParameterProvenance(
                origin="resolved", citation='Smith 1998 "lactate dehydrogenase"'
            )
        },
    )
    back = _round_trip(result.text)  # asserts it loads at all
    assert "Smith 1998" in back
